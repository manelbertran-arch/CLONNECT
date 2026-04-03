#!/usr/bin/env python3
"""
CCEE Human Evaluation Script

Interactive CLI for collecting human ratings (B3, H1, H3):
  B3 — Persona identification: "Did the creator write this?" (1-5 confidence)
  H1 — Turing Test: "Is this human or AI?" (binary)
  H3 — "Would you send this?" (1-5)

Usage:
    python3 scripts/human_eval.py --results tests/ccee_results/iris_bertran/baseline_real.json
    python3 scripts/human_eval.py --results tests/ccee_results/iris_bertran/baseline_real.json --resume
"""

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional


def _load_eval_cases(results_path: str) -> List[Dict]:
    """Load human_eval_cases from a CCEE results file."""
    with open(results_path, encoding="utf-8") as f:
        data = json.load(f)

    # Try human_eval_cases first, then per_case from first run
    cases = data.get("human_eval_cases", [])
    if not cases:
        # Fallback: build from first run's per_case data
        runs = data.get("runs", [])
        if runs:
            per_case = runs[0].get("S2_response_quality", {}).get("detail", {}).get("per_case", [])
            # This path doesn't have full case data, so check for raw_cases
            pass
    return cases


def _load_existing_ratings(output_path: str) -> Dict:
    """Load existing ratings for resume functionality."""
    if os.path.exists(output_path):
        with open(output_path, encoding="utf-8") as f:
            return json.load(f)
    return {"ratings": [], "metadata": {}}


def _save_ratings(ratings: Dict, output_path: str):
    """Save ratings to JSON file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(ratings, f, indent=2, ensure_ascii=False)


def _present_case(case: Dict, case_num: int, total: int) -> Optional[Dict]:
    """Present a single case for evaluation. Returns rating dict or None to quit."""
    print(f"\n{'='*60}")
    print(f"  Case {case_num}/{total}")
    print(f"{'='*60}")

    user_msg = case.get("user_input", case.get("user_message", "???"))
    bot_resp = case.get("bot_response", "???")
    real_resp = case.get("ground_truth", case.get("real_response", "???"))

    # Randomize order (blinded)
    if random.random() < 0.5:
        response_a, response_b = bot_resp, real_resp
        a_is_bot = True
    else:
        response_a, response_b = real_resp, bot_resp
        a_is_bot = False

    trust_seg = case.get("trust_segment", "?")
    print(f"\n  Trust segment: {trust_seg}")
    print(f"\n  Lead message: {user_msg}")
    print(f"\n  Response A: {response_a}")
    print(f"\n  Response B: {response_b}")
    print()

    # H1: Turing Test — which is human?
    while True:
        h1 = input("  H1 — Which response was written by the REAL creator? (A/B/skip/quit): ").strip().lower()
        if h1 in ("a", "b", "skip", "quit", "q"):
            break
        print("  Please enter A, B, skip, or quit")

    if h1 in ("quit", "q"):
        return None

    h1_correct = None
    if h1 != "skip":
        # A is bot if a_is_bot, so real is B
        human_choice = h1.upper()
        if a_is_bot:
            h1_correct = (human_choice == "B")  # B is real
        else:
            h1_correct = (human_choice == "A")  # A is real

    # B3: Persona confidence for the bot response
    while True:
        b3_input = input("  B3 — How confident are you the BOT response sounds like the creator? (1-5/skip): ").strip()
        if b3_input in ("skip", "quit", "q"):
            break
        try:
            b3 = int(b3_input)
            if 1 <= b3 <= 5:
                break
        except ValueError:
            pass
        print("  Please enter 1-5, skip, or quit")

    if b3_input in ("quit", "q"):
        return None
    b3_score = int(b3_input) if b3_input not in ("skip",) else None

    # H3: Would you send the bot response?
    while True:
        h3_input = input("  H3 — Would you send the bot response as the creator? (1-5/skip): ").strip()
        if h3_input in ("skip", "quit", "q"):
            break
        try:
            h3 = int(h3_input)
            if 1 <= h3 <= 5:
                break
        except ValueError:
            pass
        print("  Please enter 1-5, skip, or quit")

    if h3_input in ("quit", "q"):
        return None
    h3_score = int(h3_input) if h3_input not in ("skip",) else None

    return {
        "case_id": case.get("case_id", case_num),
        "user_input": user_msg,
        "bot_response": bot_resp,
        "real_response": real_resp,
        "trust_segment": trust_seg,
        "h1_turing_correct": h1_correct,
        "b3_persona_confidence": b3_score,
        "h3_would_send": h3_score,
        "a_was_bot": a_is_bot,
        "timestamp": datetime.utcnow().isoformat(),
    }


def compute_scores(ratings: List[Dict]) -> Dict:
    """Compute aggregate B3, H1, H3 scores from ratings."""
    h1_results = [r["h1_turing_correct"] for r in ratings if r.get("h1_turing_correct") is not None]
    b3_results = [r["b3_persona_confidence"] for r in ratings if r.get("b3_persona_confidence") is not None]
    h3_results = [r["h3_would_send"] for r in ratings if r.get("h3_would_send") is not None]

    scores = {}

    if h1_results:
        # H1: % of times the human was FOOLED (thought bot was real)
        # Higher = better clone (harder to distinguish)
        fooled_rate = sum(1 for x in h1_results if not x) / len(h1_results)
        scores["H1_turing_test"] = {
            "score": round(fooled_rate * 100, 2),
            "detail": {"total": len(h1_results), "fooled": sum(1 for x in h1_results if not x)},
        }

    if b3_results:
        # B3: Average persona confidence (1-5 → 0-100)
        avg = sum(b3_results) / len(b3_results)
        scores["B3_persona_identification"] = {
            "score": round((avg - 1) * 25, 2),  # 1→0, 5→100
            "detail": {"mean_rating": round(avg, 2), "n": len(b3_results)},
        }

    if h3_results:
        # H3: Average "would send" rating (1-5 → 0-100)
        avg = sum(h3_results) / len(h3_results)
        scores["H3_would_send"] = {
            "score": round((avg - 1) * 25, 2),
            "detail": {"mean_rating": round(avg, 2), "n": len(h3_results)},
        }

    return scores


def main():
    parser = argparse.ArgumentParser(description="CCEE Human Evaluation")
    parser.add_argument("--results", required=True, help="Path to CCEE results JSON")
    parser.add_argument("--output", help="Output path for ratings (default: alongside results)")
    parser.add_argument("--resume", action="store_true", help="Resume interrupted session")
    parser.add_argument("--max-cases", type=int, default=50, help="Max cases to evaluate")
    args = parser.parse_args()

    cases = _load_eval_cases(args.results)
    if not cases:
        print("ERROR: No evaluation cases found in results file.")
        print("Run CCEE with enough cases to generate human_eval_cases.")
        sys.exit(1)

    output_path = args.output or args.results.replace(".json", "_human_ratings.json")
    existing = _load_existing_ratings(output_path) if args.resume else {"ratings": [], "metadata": {}}
    completed_ids = {r.get("case_id") for r in existing.get("ratings", [])}

    remaining = [c for c in cases if c.get("case_id", cases.index(c)) not in completed_ids]
    remaining = remaining[:args.max_cases]

    if not remaining:
        print("All cases already evaluated!")
        scores = compute_scores(existing["ratings"])
        print(f"\nScores: {json.dumps(scores, indent=2)}")
        return

    print(f"\nCCEE Human Evaluation — {len(remaining)} cases to evaluate")
    print("Instructions:")
    print("  - You'll see two responses (A and B) for each lead message")
    print("  - One is from the bot, one is real — guess which is which")
    print("  - Rate the bot's response quality")
    print("  - Type 'quit' at any prompt to save and exit\n")

    ratings = existing.get("ratings", [])
    for i, case in enumerate(remaining, 1):
        rating = _present_case(case, i, len(remaining))
        if rating is None:
            print("\nSaving progress and exiting...")
            break
        ratings.append(rating)
        # Auto-save every 5 cases
        if i % 5 == 0:
            data = {"ratings": ratings, "metadata": {"last_saved": datetime.utcnow().isoformat()}}
            _save_ratings(data, output_path)
            print(f"  [Auto-saved {len(ratings)} ratings]")

    # Final save
    scores = compute_scores(ratings)
    data = {
        "ratings": ratings,
        "scores": scores,
        "metadata": {
            "source": args.results,
            "completed": datetime.utcnow().isoformat(),
            "total_rated": len(ratings),
        },
    }
    _save_ratings(data, output_path)
    print(f"\nSaved {len(ratings)} ratings to {output_path}")
    print(f"\nScores:")
    for k, v in scores.items():
        print(f"  {k}: {v['score']:.1f}")


if __name__ == "__main__":
    main()
