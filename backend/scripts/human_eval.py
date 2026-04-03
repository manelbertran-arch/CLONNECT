#!/usr/bin/env python3
"""
CCEE Human Evaluation Script (v2)

Interactive CLI for collecting human ratings with blind A/B comparison.

Metrics:
  H1 — Turing Test: "Which response was written by the REAL creator?" (A/B)
  B3 — Persona confidence: "How much does the bot sound like the creator?" (1-5)
  H3 — Would-send: "Would you send the bot response as the creator?" (1-5)

Features:
  - Uses test_set_v2_stratified.json (50 cases, ~39 valid text after media filter)
  - Filters media cases ([audio], [sticker], [image], [video])
  - Shows full conversation history with media placeholders
  - TRUE blind A/B randomization (seeded for reproducibility)
  - Free-text notes per case
  - Back/quit/resume support with incremental saves
  - End summary with scores and identification accuracy

Usage:
    python3 scripts/human_eval.py --creator iris_bertran --results tests/ccee_results/iris_bertran/baseline_real.json
    python3 scripts/human_eval.py --creator iris_bertran --results tests/ccee_results/iris_bertran/baseline_real.json --resume
    python3 scripts/human_eval.py --creator iris_bertran --test-set tests/cpe_data/iris_bertran/test_set_v2_stratified.json
"""

import argparse
import json
import os
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent

# ---------------------------------------------------------------------------
# Media filter (shared logic with cpe_level2_llm_judge.py)
# ---------------------------------------------------------------------------

_MEDIA_RE = re.compile(
    r"\[(audio|sticker|image|video|reel|🏷️\s*Sticker|🎤\s*Audio)\]",
    re.IGNORECASE,
)


def _is_media_case(conv: dict) -> bool:
    """Return True if test_input or ground_truth is a media-only message."""
    for field in ("test_input", "ground_truth"):
        text = conv.get(field, "").strip()
        if _MEDIA_RE.search(text) and len(_MEDIA_RE.sub("", text).strip()) == 0:
            return True
    return False


def _filter_media_cases(conversations: List[dict]) -> List[dict]:
    """Filter out cases where test_input or ground_truth is media-only."""
    before = len(conversations)
    filtered = [c for c in conversations if not _is_media_case(c)]
    excluded = before - len(filtered)
    if excluded:
        print(f"  Media filter: {before} → {len(filtered)} cases ({excluded} media excluded)")
    return filtered


# ---------------------------------------------------------------------------
# History formatter
# ---------------------------------------------------------------------------

MAX_HISTORY_TURNS = 15


def _format_history(turns: List[dict], creator_name: str) -> str:
    """Format conversation turns for display."""
    if not turns:
        return "  (no prior conversation)"

    if len(turns) > MAX_HISTORY_TURNS:
        omitted = len(turns) - MAX_HISTORY_TURNS
        turns = turns[-MAX_HISTORY_TURNS:]
        lines = [f"  ... ({omitted} earlier turns omitted)"]
    else:
        lines = []

    for t in turns:
        role = t.get("role", "")
        content = t.get("content", "").strip()
        if not content:
            continue

        label = f"[{creator_name}]" if role in ("iris", "assistant") else "[Lead]"

        # Replace media with descriptive placeholders
        if _MEDIA_RE.fullmatch(content):
            media_type = _MEDIA_RE.match(content).group(1).lower()
            content = f"(sent a {media_type})"
        elif content.startswith("[🎤 Audio]:"):
            content = content.replace("[🎤 Audio]: ", "(voice) ")
        elif content.startswith("[🏷️ Sticker]"):
            content = "(sent a sticker)"

        lines.append(f"  {label} {content}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Load cases from various sources
# ---------------------------------------------------------------------------

def _load_cases_from_results(results_path: str, test_set_path: Optional[str] = None) -> List[Dict]:
    """Load cases from a CCEE results file, enriching with test set data."""
    with open(results_path, encoding="utf-8") as f:
        results_data = json.load(f)

    # Try human_eval_cases first
    cases = results_data.get("human_eval_cases", [])

    # If no human_eval_cases, build from per_case data in runs
    if not cases:
        runs = results_data.get("runs", [])
        if runs:
            run = runs[0]
            per_case_s2 = run.get("S2_response_quality", {}).get("detail", {}).get("per_case", [])
            if per_case_s2:
                # We have scores but need the actual text — load from test set
                pass

    return cases


def _load_cases_from_test_set(
    creator_id: str,
    test_set_path: Optional[str] = None,
    results_path: Optional[str] = None,
) -> List[Dict]:
    """Load and merge test set conversations with bot responses from results."""
    # Load test set
    if test_set_path:
        ts_path = Path(test_set_path)
    else:
        ts_path = REPO_ROOT / "tests" / "cpe_data" / creator_id / "test_set_v2_stratified.json"

    if not ts_path.exists():
        print(f"ERROR: Test set not found: {ts_path}")
        sys.exit(1)

    with open(ts_path, encoding="utf-8") as f:
        ts_data = json.load(f)
    conversations = ts_data if isinstance(ts_data, list) else ts_data.get("conversations", ts_data.get("test_cases", []))

    # Merge bot responses from results if available
    if results_path and os.path.exists(results_path):
        with open(results_path, encoding="utf-8") as f:
            results_data = json.load(f)

        # Build bot response map from results
        bot_map = {}
        runs = results_data.get("runs", [])
        if runs:
            # Try to get per-case bot responses
            per_case = runs[0].get("S2_response_quality", {}).get("detail", {}).get("per_case_detail", [])
            for pc in per_case:
                case_id = pc.get("case_id", pc.get("id", ""))
                if case_id and pc.get("bot_response"):
                    bot_map[case_id] = pc["bot_response"]

        # Also check raw_responses if available
        raw = results_data.get("raw_responses", [])
        for r in raw:
            case_id = r.get("case_id", r.get("id", ""))
            if case_id and r.get("bot_response"):
                bot_map[case_id] = r["bot_response"]

        # Merge
        for conv in conversations:
            cid = conv.get("id", "")
            if cid in bot_map:
                conv["bot_response"] = bot_map[cid]

    return conversations


# ---------------------------------------------------------------------------
# Save / Load ratings
# ---------------------------------------------------------------------------

def _get_output_path(creator_id: str, results_path: Optional[str] = None) -> str:
    """Get the default output path for ratings."""
    if results_path:
        return results_path.replace(".json", "_human_eval.json")
    out_dir = REPO_ROOT / "tests" / "ccee_results" / creator_id
    out_dir.mkdir(parents=True, exist_ok=True)
    return str(out_dir / "human_eval.json")


def _load_existing(output_path: str) -> Dict:
    """Load existing ratings for resume."""
    if os.path.exists(output_path):
        with open(output_path, encoding="utf-8") as f:
            return json.load(f)
    return {"ratings": [], "metadata": {}}


def _save_ratings(data: Dict, output_path: str):
    """Save ratings incrementally."""
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Present a single case
# ---------------------------------------------------------------------------

def _present_case(
    conv: Dict,
    case_num: int,
    total: int,
    creator_name: str,
    seed_offset: int,
) -> Optional[Dict]:
    """Present a single case for blind A/B evaluation.

    Returns:
        Dict with rating data, or None if user typed 'quit',
        or string 'back' if user typed 'back'.
    """
    print(f"\n{'='*65}")
    print(f"  Case {case_num}/{total}")
    print(f"{'='*65}")

    # Context info
    category = conv.get("category", "?")
    language = conv.get("language", "?")
    trust = conv.get("trust_score", conv.get("trust_segment", "?"))
    if isinstance(trust, float):
        if trust < 0.3:
            trust_label = "low"
        elif trust < 0.7:
            trust_label = "medium"
        else:
            trust_label = "high"
    else:
        trust_label = str(trust)

    print(f"  Category: {category}  |  Language: {language}  |  Trust: {trust_label}")

    # Show conversation history
    turns = conv.get("turns", [])
    if turns:
        print(f"\n  Conversation history ({len(turns)} turns):")
        print(_format_history(turns, creator_name))

    # Lead message (test input)
    test_input = conv.get("test_input", conv.get("user_input", "???"))
    print(f"\n  Lead says: {test_input}")

    # Get bot and real responses
    bot_resp = conv.get("bot_response", "")
    real_resp = conv.get("ground_truth", conv.get("real_response", ""))

    if not bot_resp:
        print("  ⚠ No bot response available for this case — skipping")
        return "skip_no_response"

    if not real_resp:
        print("  ⚠ No ground truth available for this case — skipping")
        return "skip_no_gt"

    # Blind A/B randomization (deterministic per case via seed)
    rng = random.Random(seed_offset + case_num)
    if rng.random() < 0.5:
        response_a, response_b = bot_resp, real_resp
        a_is_bot = True
    else:
        response_a, response_b = real_resp, bot_resp
        a_is_bot = False

    print(f"\n  Response A: {response_a}")
    print(f"\n  Response B: {response_b}")
    print()

    # --- H1: Turing Test ---
    while True:
        h1 = input("  H1 — Which was written by the REAL creator? (A/B/skip/back/quit): ").strip().lower()
        if h1 in ("a", "b", "skip", "back", "quit", "q"):
            break
        print("  → Enter A, B, skip, back, or quit")

    if h1 in ("quit", "q"):
        return None
    if h1 == "back":
        return "back"

    h1_correct = None
    if h1 != "skip":
        if a_is_bot:
            h1_correct = (h1.upper() == "B")  # B is real
        else:
            h1_correct = (h1.upper() == "A")  # A is real

    # --- B3: Persona confidence ---
    while True:
        b3_raw = input("  B3 — How much does the BOT sound like the creator? (1-5/skip/back/quit): ").strip().lower()
        if b3_raw in ("skip", "back", "quit", "q"):
            break
        try:
            b3_val = int(b3_raw)
            if 1 <= b3_val <= 5:
                break
        except ValueError:
            pass
        print("  → Enter 1-5, skip, back, or quit")

    if b3_raw in ("quit", "q"):
        return None
    if b3_raw == "back":
        return "back"
    b3_score = int(b3_raw) if b3_raw not in ("skip",) else None

    # --- H3: Would you send it? ---
    while True:
        h3_raw = input("  H3 — Would you send the bot response as the creator? (1-5/skip/back/quit): ").strip().lower()
        if h3_raw in ("skip", "back", "quit", "q"):
            break
        try:
            h3_val = int(h3_raw)
            if 1 <= h3_val <= 5:
                break
        except ValueError:
            pass
        print("  → Enter 1-5, skip, back, or quit")

    if h3_raw in ("quit", "q"):
        return None
    if h3_raw == "back":
        return "back"
    h3_score = int(h3_raw) if h3_raw not in ("skip",) else None

    # --- Notes (optional) ---
    notes_raw = input("  Notes (optional — explain reasoning, flag issues, or quit/back): ").strip()
    if notes_raw.lower() in ("quit", "q"):
        return None
    if notes_raw.lower() == "back":
        return "back"
    notes = notes_raw

    return {
        "case_id": conv.get("id", f"case_{case_num}"),
        "test_input": test_input,
        "bot_response": bot_resp,
        "ground_truth": real_resp,
        "category": category,
        "language": language,
        "trust_segment": trust_label,
        "h1_turing_correct": h1_correct,
        "h1_raw_choice": h1 if h1 != "skip" else None,
        "b3_persona_confidence": b3_score,
        "h3_would_send": h3_score,
        "a_was_bot": a_is_bot,
        "notes": notes if notes else None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Compute aggregate scores
# ---------------------------------------------------------------------------

def compute_scores(ratings: List[Dict]) -> Dict:
    """Compute aggregate B3, H1, H3 scores from ratings."""
    h1_results = [r["h1_turing_correct"] for r in ratings if r.get("h1_turing_correct") is not None]
    b3_results = [r["b3_persona_confidence"] for r in ratings if r.get("b3_persona_confidence") is not None]
    h3_results = [r["h3_would_send"] for r in ratings if r.get("h3_would_send") is not None]

    scores = {}

    if h1_results:
        correct = sum(1 for x in h1_results if x)
        fooled = sum(1 for x in h1_results if not x)
        scores["H1_turing_test"] = {
            "identification_accuracy": round(correct / len(h1_results) * 100, 1),
            "fooled_rate": round(fooled / len(h1_results) * 100, 1),
            "correct": correct,
            "fooled": fooled,
            "total": len(h1_results),
        }

    if b3_results:
        avg = sum(b3_results) / len(b3_results)
        scores["B3_persona_confidence"] = {
            "score_0_100": round((avg - 1) * 25, 1),
            "mean_1_5": round(avg, 2),
            "n": len(b3_results),
        }

    if h3_results:
        avg = sum(h3_results) / len(h3_results)
        scores["H3_would_send"] = {
            "score_0_100": round((avg - 1) * 25, 1),
            "mean_1_5": round(avg, 2),
            "n": len(h3_results),
        }

    return scores


def _print_summary(ratings: List[Dict]):
    """Print end-of-session summary."""
    scores = compute_scores(ratings)

    print(f"\n{'='*65}")
    print(f"  HUMAN EVALUATION SUMMARY")
    print(f"{'='*65}")
    print(f"  Cases evaluated: {len(ratings)}")
    print()

    if "H1_turing_test" in scores:
        h1 = scores["H1_turing_test"]
        print(f"  H1 Turing Test:")
        print(f"    Correctly identified Iris: {h1['correct']}/{h1['total']} ({h1['identification_accuracy']}%)")
        print(f"    Fooled (thought bot was Iris): {h1['fooled']}/{h1['total']} ({h1['fooled_rate']}%)")

    if "B3_persona_confidence" in scores:
        b3 = scores["B3_persona_confidence"]
        print(f"  B3 Persona Confidence: {b3['mean_1_5']}/5 ({b3['score_0_100']}/100)")

    if "H3_would_send" in scores:
        h3 = scores["H3_would_send"]
        print(f"  H3 Would Send: {h3['mean_1_5']}/5 ({h3['score_0_100']}/100)")

    # Notes summary
    notes = [r for r in ratings if r.get("notes")]
    if notes:
        print(f"\n  Notes collected: {len(notes)}")
        for r in notes[:5]:
            print(f"    [{r['case_id']}] {r['notes'][:80]}")
        if len(notes) > 5:
            print(f"    ... and {len(notes) - 5} more")

    print(f"{'='*65}")
    return scores


# ---------------------------------------------------------------------------
# Auto-calibrate (TASK 4, step 15)
# ---------------------------------------------------------------------------

def _run_calibrator(ratings: List[Dict], creator_id: str, results_path: Optional[str]):
    """Run CCEECalibrator if we have matching CCEE evaluations."""
    if not results_path or not os.path.exists(results_path):
        print("  Calibrator: no CCEE results file to calibrate against")
        return

    try:
        sys.path.insert(0, str(REPO_ROOT))
        from core.evaluation.calibrator import CCEECalibrator

        with open(results_path, encoding="utf-8") as f:
            results_data = json.load(f)

        runs = results_data.get("runs", [])
        if not runs:
            print("  Calibrator: no runs found in results file")
            return

        # We need h3_would_send ratings paired with CCEE per-case scores
        h3_map = {}
        for r in ratings:
            if r.get("h3_would_send") is not None:
                h3_map[r["case_id"]] = r["h3_would_send"]

        if len(h3_map) < 10:
            print(f"  Calibrator: need ≥10 H3 ratings, have {len(h3_map)} — skipping")
            return

        print(f"  Calibrator: {len(h3_map)} paired ratings available")
        print("  (Full calibration requires per-case CCEE scores paired with ratings)")
        print("  Run CCEE baseline first, then re-run calibrator with matched IDs.")

    except Exception as e:
        print(f"  Calibrator error: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="CCEE Human Evaluation (v2)")
    parser.add_argument("--creator", required=True, help="Creator slug (e.g. iris_bertran)")
    parser.add_argument("--results", default=None, help="Path to CCEE results JSON (for bot responses)")
    parser.add_argument("--test-set", default=None, help="Custom test set path")
    parser.add_argument("--output", default=None, help="Output path for ratings")
    parser.add_argument("--resume", action="store_true", help="Resume interrupted session")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for A/B assignment")
    parser.add_argument("--include-media", action="store_true", help="Include media cases")
    args = parser.parse_args()

    creator = args.creator
    creator_name = creator.replace("_", " ").title()

    # Load conversations
    conversations = _load_cases_from_test_set(
        creator_id=creator,
        test_set_path=args.test_set,
        results_path=args.results,
    )

    if not conversations:
        # Fallback: try loading from results file directly
        if args.results:
            conversations = _load_cases_from_results(args.results)
        if not conversations:
            print("ERROR: No evaluation cases found.")
            print(f"Expected test set at: tests/cpe_data/{creator}/test_set_v2_stratified.json")
            sys.exit(1)

    # Media filter
    total_loaded = len(conversations)
    if not args.include_media:
        conversations = _filter_media_cases(conversations)
    print(f"  Valid text cases: {len(conversations)} (from {total_loaded} loaded)")

    # Output path
    output_path = args.output or _get_output_path(creator, args.results)

    # Resume support
    existing = _load_existing(output_path) if args.resume else {"ratings": [], "metadata": {}}
    completed_ids = {r.get("case_id") for r in existing.get("ratings", [])}
    resume_from = len(completed_ids)

    if args.resume and resume_from > 0:
        print(f"\n  Resuming from case {resume_from + 1} ({resume_from} already completed)")
        resp = input(f"  Continue from case {resume_from + 1}? (y/n): ").strip().lower()
        if resp not in ("y", "yes", ""):
            print("  Starting fresh.")
            existing = {"ratings": [], "metadata": {}}
            completed_ids = set()

    remaining = [c for i, c in enumerate(conversations) if c.get("id", f"case_{i+1}") not in completed_ids]
    total_remaining = len(remaining)

    if not remaining:
        print("\n  All cases already evaluated!")
        _print_summary(existing["ratings"])
        return

    print(f"\n{'='*65}")
    print(f"  CCEE Human Evaluation — @{creator}")
    print(f"{'='*65}")
    print(f"  Cases to evaluate: {total_remaining}")
    print(f"  Seed: {args.seed} (for reproducible A/B assignment)")
    print()
    print("  Instructions:")
    print("  - Two responses (A and B) shown for each lead message")
    print("  - One is bot, one is real — guess which is real")
    print("  - Rate bot response quality (1-5)")
    print("  - Type 'back' to revisit previous case")
    print("  - Type 'quit' to save progress and exit")
    print()

    ratings = list(existing.get("ratings", []))
    i = 0

    while i < len(remaining):
        conv = remaining[i]
        case_num = resume_from + i + 1
        total_display = resume_from + total_remaining

        result = _present_case(conv, case_num, total_display, creator_name, args.seed)

        if result is None:
            # Quit
            print("\n  Saving progress and exiting...")
            break
        elif result == "back":
            if i > 0:
                # Go back, skipping over auto-skipped cases (no bot_response / no GT)
                target = i - 1
                while target > 0:
                    prev_conv = remaining[target]
                    if prev_conv.get("bot_response") and prev_conv.get("ground_truth", prev_conv.get("real_response")):
                        break
                    target -= 1
                # Remove last rating if it matches the target case
                target_id = remaining[target].get("id", f"case_{resume_from + target + 1}")
                if ratings and ratings[-1].get("case_id") == target_id:
                    ratings.pop()
                i = target
                print(f"\n  ← Going back to case {resume_from + i + 1}")
            else:
                print("  Already at first case — can't go back")
            continue
        elif isinstance(result, str) and result.startswith("skip_"):
            # Auto-skip (no response or no GT)
            i += 1
            continue
        else:
            # Check if we're re-rating (went back)
            existing_idx = next(
                (j for j, r in enumerate(ratings) if r.get("case_id") == result.get("case_id")),
                None,
            )
            if existing_idx is not None:
                ratings[existing_idx] = result
            else:
                ratings.append(result)

            i += 1

            # Auto-save every 3 cases
            if len(ratings) % 3 == 0:
                save_data = {
                    "ratings": ratings,
                    "metadata": {
                        "creator": creator,
                        "seed": args.seed,
                        "last_saved": datetime.now(timezone.utc).isoformat(),
                        "total_rated": len(ratings),
                    },
                }
                _save_ratings(save_data, output_path)
                print(f"  [Auto-saved {len(ratings)} ratings]")

    # Final save
    scores = _print_summary(ratings)

    save_data = {
        "ratings": ratings,
        "scores": scores,
        "metadata": {
            "creator": creator,
            "seed": args.seed,
            "source_results": args.results,
            "source_test_set": args.test_set or str(REPO_ROOT / "tests" / "cpe_data" / creator / "test_set_v2_stratified.json"),
            "completed": datetime.now(timezone.utc).isoformat(),
            "total_rated": len(ratings),
            "total_cases": len(conversations),
        },
    }
    _save_ratings(save_data, output_path)
    print(f"\n  Saved {len(ratings)} ratings to {output_path}")

    # Auto-calibrate (step 15)
    _run_calibrator(ratings, creator, args.results)


if __name__ == "__main__":
    main()
