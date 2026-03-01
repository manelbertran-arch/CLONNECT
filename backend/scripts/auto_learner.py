#!/usr/bin/env python3
"""
Auto-learner: derive style rules, few-shot examples, and prompt refinements from data.

NO hardcoded rules — everything is extracted from real conversations.
What works for Stefano will be different for creator #2.

Pipeline:
1. Select best-match pairs as few-shot examples (gap < 5)
2. Extract style rules from real Stefano messages (data-driven, not assumed)
3. Compute per-category style variations
4. Generate optimized prompt fragments
5. Output learnings as JSON for injection into DM pipeline

Usage:
    python3.11 scripts/auto_learner.py --judge-input results/judge_results_XXX.json --conversations-input results/real_conversations_XXX.json
    python3.11 scripts/auto_learner.py --judge-input results/judge_results_XXX.json --conversations-input results/real_conversations_XXX.json --output results/
"""
import re
import sys
import json
import argparse
import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

logger = logging.getLogger(__name__)

DIMENSIONS = ["naturalidad", "relevancia", "estilo", "efectividad", "personalidad"]

# Emoji regex
EMOJI_RE = re.compile(
    "[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF"
    "\U00002702-\U000027B0\U0000FE00-\U0000FE0F]+",
    flags=re.UNICODE,
)


# ---------------------------------------------------------------------------
# 1. Few-shot example selection
# ---------------------------------------------------------------------------

def select_few_shot_examples(
    evaluations: list[dict],
    max_best: int = 10,
    max_worst: int = 5,
    gap_threshold_good: float = 5.0,
    gap_threshold_bad: float = 25.0,
) -> dict:
    """Select best-match and worst-match pairs for few-shot learning.

    Best matches: bot ≈ Stefano (use as positive examples)
    Worst matches: bot << Stefano (use as "DO THIS, NOT THAT" examples)
    """
    valid = [e for e in evaluations if "error" not in e]

    # Compute average gap for each pair
    for ev in valid:
        ss = ev.get("stefano_scores", {})
        bs = ev.get("bot_scores", {})
        gaps = []
        for dim in DIMENSIONS:
            s = ss.get(dim, 50)
            b = bs.get(dim, 50)
            if isinstance(s, (int, float)) and isinstance(b, (int, float)):
                gaps.append(s - b)
        ev["_avg_gap"] = sum(gaps) / len(gaps) if gaps else 0

    # Best matches (gap < threshold, sorted by smallest gap)
    best = sorted(
        [e for e in valid if e["_avg_gap"] < gap_threshold_good],
        key=lambda e: abs(e["_avg_gap"]),
    )

    # Diversify by category
    best_by_cat = defaultdict(list)
    for e in best:
        cat = e.get("lead_category", "OTRO")
        if len(best_by_cat[cat]) < 3:  # Max 3 per category
            best_by_cat[cat].append(e)

    best_diverse = []
    for cat_examples in best_by_cat.values():
        best_diverse.extend(cat_examples)
    best_diverse = best_diverse[:max_best]

    # Worst failures (large gap, sorted by worst)
    worst = sorted(
        [e for e in valid if e["_avg_gap"] > gap_threshold_bad],
        key=lambda e: -e["_avg_gap"],
    )[:max_worst]

    # Format examples
    positive_examples = []
    for e in best_diverse:
        positive_examples.append({
            "lead_message": e.get("lead_message", ""),
            "correct_response": e.get("stefano_real", ""),
            "category": e.get("lead_category", ""),
            "topic": e.get("topic", ""),
            "gap": round(e["_avg_gap"], 1),
        })

    negative_examples = []
    for e in worst:
        negative_examples.append({
            "lead_message": e.get("lead_message", ""),
            "correct_response": e.get("stefano_real", ""),
            "wrong_response": e.get("bot_response", ""),
            "category": e.get("lead_category", ""),
            "gap": round(e["_avg_gap"], 1),
        })

    return {
        "positive_examples": positive_examples,
        "negative_examples": negative_examples,
        "total_candidates_best": len(best),
        "total_candidates_worst": len(worst),
    }


# ---------------------------------------------------------------------------
# 2. Data-driven style rules extraction
# ---------------------------------------------------------------------------

def extract_style_rules(conversations: list[dict]) -> dict:
    """Extract style rules purely from Stefano's real messages.

    NO assumptions — everything derived from data.
    """
    # Collect all real Stefano messages
    all_msgs = []
    msgs_by_category = defaultdict(list)

    for conv in conversations:
        category = conv.get("lead_category", "OTRO")
        for turn in conv.get("turns", []):
            if turn.get("role") == "stefano_real":
                text = turn.get("content", "")
                if text.strip():
                    all_msgs.append(text)
                    msgs_by_category[category].append(text)

    if not all_msgs:
        return {"error": "No Stefano messages found"}

    # Message length distribution
    lengths = [len(m) for m in all_msgs]
    word_counts = [len(m.split()) for m in all_msgs]

    # Emoji analysis
    msgs_with_emoji = [m for m in all_msgs if EMOJI_RE.search(m)]
    emoji_rate = len(msgs_with_emoji) / len(all_msgs)

    all_emojis = []
    for m in all_msgs:
        all_emojis.extend(EMOJI_RE.findall(m))
    # Flatten individual emoji chars
    individual_emojis = []
    for group in all_emojis:
        individual_emojis.extend(list(group))
    top_emojis = [e for e, _ in Counter(individual_emojis).most_common(10)]

    # Emoji position (start, middle, end)
    emoji_at_end = sum(1 for m in msgs_with_emoji if EMOJI_RE.search(m[-5:])) / max(len(msgs_with_emoji), 1)

    # Question rate
    msgs_with_question = [m for m in all_msgs if "?" in m]
    question_rate = len(msgs_with_question) / len(all_msgs)

    # Exclamation rate
    msgs_with_excl = [m for m in all_msgs if "!" in m]
    exclamation_rate = len(msgs_with_excl) / len(all_msgs)

    # Period ending rate (formality indicator)
    msgs_end_period = [m for m in all_msgs if m.rstrip().endswith(".")]
    period_end_rate = len(msgs_end_period) / len(all_msgs)

    # Laugh patterns
    laugh_re = re.compile(r'\b(ja+(?:ja)*|je+(?:je)*|ji+(?:ji)*|ha+(?:ha)*)\b', re.IGNORECASE)
    laugh_msgs = [m for m in all_msgs if laugh_re.search(m)]
    laugh_rate = len(laugh_msgs) / len(all_msgs)

    laugh_patterns = Counter()
    for m in all_msgs:
        for match in laugh_re.finditer(m):
            laugh_patterns[match.group().lower()] += 1
    top_laughs = [p for p, _ in laugh_patterns.most_common(5)]

    # Abbreviations
    abbrev_patterns = {
        "q": re.compile(r'\bq\b'),
        "xq": re.compile(r'\bxq\b'),
        "tb": re.compile(r'\btb\b'),
        "tmb": re.compile(r'\btmb\b'),
        "pq": re.compile(r'\bpq\b'),
        "x": re.compile(r'\bx\b'),
    }
    abbreviations_found = {}
    for abbr, pattern in abbrev_patterns.items():
        count = sum(1 for m in all_msgs if pattern.search(m.lower()))
        if count > 0:
            abbreviations_found[abbr] = count

    # Greeting patterns
    greeting_re = re.compile(r'^(hola|buenas?|ey+|hey|que tal)', re.IGNORECASE)
    msgs_start_greeting = [m for m in all_msgs if greeting_re.match(m)]
    greeting_rate = len(msgs_start_greeting) / len(all_msgs)

    # Common openers (first 3 words)
    openers = Counter()
    for m in all_msgs:
        words = m.split()[:3]
        if words:
            openers[" ".join(words).lower()] += 1
    top_openers = [o for o, _ in openers.most_common(15)]

    # Common closers (last 3 words)
    closers = Counter()
    for m in all_msgs:
        words = m.split()[-3:]
        if words:
            closers[" ".join(words).lower()] += 1
    top_closers = [c for c, _ in closers.most_common(15)]

    # Muletillas / informal markers
    marker_candidates = [
        "jaja", "jajaja", "bro", "crack", "tio", "dale", "vamos", "genial",
        "tranqui", "hermano", "amigo", "buenas", "siii", "daleee", "buenaaas",
        "vamoooos", "eyyy", "oye", "mira", "venga",
    ]
    markers_found = {}
    for marker in marker_candidates:
        count = sum(1 for m in all_msgs if marker in m.lower())
        if count > 0:
            markers_found[marker] = count
    top_markers = sorted(markers_found.keys(), key=lambda k: -markers_found[k])

    # Uppercase start rate
    upper_start = sum(1 for m in all_msgs if m and m[0].isupper()) / len(all_msgs)

    # Per-category variations
    category_profiles = {}
    for cat, cat_msgs in msgs_by_category.items():
        if len(cat_msgs) < 5:
            continue
        cat_lengths = [len(m) for m in cat_msgs]
        cat_emoji_rate = sum(1 for m in cat_msgs if EMOJI_RE.search(m)) / len(cat_msgs)
        cat_question_rate = sum(1 for m in cat_msgs if "?" in m) / len(cat_msgs)
        cat_excl_rate = sum(1 for m in cat_msgs if "!" in m) / len(cat_msgs)

        category_profiles[cat] = {
            "message_count": len(cat_msgs),
            "avg_length": round(sum(cat_lengths) / len(cat_lengths), 1),
            "emoji_rate": round(cat_emoji_rate, 3),
            "question_rate": round(cat_question_rate, 3),
            "exclamation_rate": round(cat_excl_rate, 3),
        }

    rules = {
        "total_messages_analyzed": len(all_msgs),
        "message_length": {
            "mean": round(sum(lengths) / len(lengths), 1),
            "median": round(sorted(lengths)[len(lengths) // 2], 1),
            "p25": round(sorted(lengths)[int(len(lengths) * 0.25)], 1),
            "p75": round(sorted(lengths)[int(len(lengths) * 0.75)], 1),
            "word_mean": round(sum(word_counts) / len(word_counts), 1),
        },
        "emoji": {
            "rate": round(emoji_rate, 3),
            "top_emojis": top_emojis,
            "at_end_rate": round(emoji_at_end, 3),
        },
        "punctuation": {
            "question_rate": round(question_rate, 3),
            "exclamation_rate": round(exclamation_rate, 3),
            "period_end_rate": round(period_end_rate, 3),
        },
        "laughs": {
            "rate": round(laugh_rate, 3),
            "top_patterns": top_laughs,
        },
        "abbreviations": abbreviations_found,
        "informal_markers": top_markers[:15],
        "greeting_rate": round(greeting_rate, 3),
        "uppercase_start_rate": round(upper_start, 3),
        "top_openers": top_openers,
        "top_closers": top_closers,
        "category_profiles": category_profiles,
    }

    return rules


# ---------------------------------------------------------------------------
# 3. Prompt fragment generation
# ---------------------------------------------------------------------------

def generate_prompt_fragments(
    style_rules: dict,
    few_shots: dict,
) -> dict:
    """Generate optimized prompt fragments for injection into the DM pipeline.

    These replace hardcoded style instructions with data-derived rules.
    """
    r = style_rules

    # Style instructions block
    length_info = r.get("message_length", {})
    emoji_info = r.get("emoji", {})
    punct_info = r.get("punctuation", {})
    laugh_info = r.get("laughs", {})

    top_emojis_str = " ".join(emoji_info.get("top_emojis", [])[:6])
    top_laughs_str = ", ".join(laugh_info.get("top_patterns", [])[:3])
    markers_str = ", ".join(r.get("informal_markers", [])[:8])

    style_block = f"""=== PATRONES DE ESCRITURA (extraidos de {r.get('total_messages_analyzed', 0)} mensajes reales) ===
LONGITUD: {length_info.get('mean', 40):.0f} chars media, {length_info.get('word_mean', 8):.0f} palabras media. Rango normal: {length_info.get('p25', 15):.0f}-{length_info.get('p75', 60):.0f} chars.
EMOJIS: {emoji_info.get('rate', 0):.0%} de mensajes. Top: {top_emojis_str}. Pon al FINAL ({emoji_info.get('at_end_rate', 0):.0%} al final).
PUNTUACION: ! en {punct_info.get('exclamation_rate', 0):.0%}, ? en {punct_info.get('question_rate', 0):.0%}. NUNCA termines con punto ({punct_info.get('period_end_rate', 0):.0%} real).
RISAS: {top_laughs_str} (en {laugh_info.get('rate', 0):.0%} de msgs).
MULETILLAS: {markers_str}
MAYUSCULAS: {r.get('uppercase_start_rate', 0):.0%} empieza con mayuscula.
=== FIN PATRONES ==="""

    # Category-specific adjustments
    cat_profiles = r.get("category_profiles", {})
    cat_block = ""
    if cat_profiles:
        lines = ["=== VARIACIONES POR TIPO DE LEAD ==="]
        for cat, profile in sorted(cat_profiles.items()):
            lines.append(
                f"{cat}: {profile['avg_length']:.0f} chars, "
                f"emoji {profile['emoji_rate']:.0%}, "
                f"? {profile['question_rate']:.0%}, "
                f"! {profile['exclamation_rate']:.0%}"
            )
        lines.append("=== FIN VARIACIONES ===")
        cat_block = "\n".join(lines)

    # Few-shot examples block
    few_shot_block = ""
    positive = few_shots.get("positive_examples", [])
    if positive:
        lines = ["=== EJEMPLOS DE RESPUESTAS CORRECTAS ==="]
        for i, ex in enumerate(positive[:8], 1):
            lines.append(f"Ejemplo {i} ({ex['category']}/{ex['topic']}):")
            lines.append(f"  Lead: {ex['lead_message'][:100]}")
            lines.append(f"  Respuesta: {ex['correct_response'][:150]}")
        lines.append("=== FIN EJEMPLOS ===")
        few_shot_block = "\n".join(lines)

    # Negative examples block
    negative_block = ""
    negative = few_shots.get("negative_examples", [])
    if negative:
        lines = ["=== ERRORES A EVITAR ==="]
        for i, ex in enumerate(negative[:3], 1):
            lines.append(f"Error {i}:")
            lines.append(f"  Lead: {ex['lead_message'][:80]}")
            lines.append(f"  MAL: {ex['wrong_response'][:100]}")
            lines.append(f"  BIEN: {ex['correct_response'][:100]}")
        lines.append("=== FIN ERRORES ===")
        negative_block = "\n".join(lines)

    return {
        "style_block": style_block,
        "category_block": cat_block,
        "few_shot_block": few_shot_block,
        "negative_block": negative_block,
        "full_injection": "\n\n".join(
            b for b in [style_block, cat_block, few_shot_block, negative_block] if b
        ),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def print_learner_report(
    style_rules: dict,
    few_shots: dict,
    prompt_fragments: dict,
):
    """Print auto-learner summary."""
    print(f"\n{'='*60}")
    print(f"  Auto-Learner Report")
    print(f"{'='*60}")

    r = style_rules
    print(f"\n  Messages analyzed: {r.get('total_messages_analyzed', 0)}")

    ml = r.get("message_length", {})
    print(f"\n  Message Length:")
    print(f"    Mean:   {ml.get('mean', 0):.1f} chars, {ml.get('word_mean', 0):.1f} words")
    print(f"    Median: {ml.get('median', 0):.1f} chars")
    print(f"    P25-P75: {ml.get('p25', 0):.0f} - {ml.get('p75', 0):.0f} chars")

    em = r.get("emoji", {})
    print(f"\n  Emoji: {em.get('rate', 0):.1%} of messages")
    print(f"    Top: {' '.join(em.get('top_emojis', [])[:6])}")
    print(f"    At end: {em.get('at_end_rate', 0):.0%}")

    pu = r.get("punctuation", {})
    print(f"\n  Punctuation:")
    print(f"    Questions: {pu.get('question_rate', 0):.1%}")
    print(f"    Exclamations: {pu.get('exclamation_rate', 0):.1%}")
    print(f"    Period endings: {pu.get('period_end_rate', 0):.1%}")

    la = r.get("laughs", {})
    print(f"\n  Laughs: {la.get('rate', 0):.1%}")
    print(f"    Patterns: {', '.join(la.get('top_patterns', []))}")

    print(f"\n  Informal markers: {', '.join(r.get('informal_markers', [])[:10])}")

    cat = r.get("category_profiles", {})
    if cat:
        print(f"\n  Per-category profiles:")
        for cat_name, profile in sorted(cat.items()):
            print(f"    {cat_name}: {profile['message_count']} msgs, "
                  f"{profile['avg_length']:.0f} chars, "
                  f"emoji {profile['emoji_rate']:.0%}")

    print(f"\n  Few-shot examples selected:")
    print(f"    Positive (bot ≈ Stefano): {len(few_shots.get('positive_examples', []))}")
    print(f"    Negative (bot << Stefano): {len(few_shots.get('negative_examples', []))}")

    print(f"\n  Prompt injection size: {len(prompt_fragments.get('full_injection', ''))} chars")

    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Auto-Learner: data-driven style extraction")
    parser.add_argument("--judge-input", required=True, help="Path to judge results JSON")
    parser.add_argument("--conversations-input", required=True, help="Path to extracted conversations JSON")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Load judge results
    judge_path = Path(args.judge_input)
    with open(judge_path, "r", encoding="utf-8") as f:
        judge_data = json.load(f)
    evaluations = judge_data.get("evaluations", [])
    print(f"  Loaded {len(evaluations)} evaluations from {judge_path.name}")

    # Load conversations
    conv_path = Path(args.conversations_input)
    with open(conv_path, "r", encoding="utf-8") as f:
        conv_data = json.load(f)
    conversations = conv_data.get("conversations", [])
    print(f"  Loaded {len(conversations)} conversations from {conv_path.name}")

    # Step 1: Select few-shot examples
    print("\n  [1/3] Selecting few-shot examples...")
    few_shots = select_few_shot_examples(evaluations)

    # Step 2: Extract style rules from real messages
    print("  [2/3] Extracting style rules from data...")
    style_rules = extract_style_rules(conversations)

    # Step 3: Generate prompt fragments
    print("  [3/3] Generating prompt fragments...")
    prompt_fragments = generate_prompt_fragments(style_rules, few_shots)

    print_learner_report(style_rules, few_shots, prompt_fragments)

    # Save everything
    output_dir = Path(args.output) if args.output else judge_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # Save learnings
    learnings = {
        "learned_at": datetime.now(timezone.utc).isoformat(),
        "judge_input": str(judge_path),
        "conversations_input": str(conv_path),
        "style_rules": style_rules,
        "few_shot_examples": few_shots,
        "prompt_fragments": prompt_fragments,
    }

    learnings_path = output_dir / f"auto_learnings_{timestamp}.json"
    with open(learnings_path, "w", encoding="utf-8") as f:
        json.dump(learnings, f, ensure_ascii=False, indent=2, default=str)
    print(f"  Learnings saved to: {learnings_path}")

    # Save prompt injection (ready to use)
    injection_path = output_dir / f"prompt_injection_{timestamp}.txt"
    with open(injection_path, "w", encoding="utf-8") as f:
        f.write(prompt_fragments["full_injection"])
    print(f"  Prompt injection saved to: {injection_path}")
    print(f"  Injection size: {len(prompt_fragments['full_injection'])} chars")

    print(f"\n  Next steps:")
    print(f"  1. Review prompt_injection_{timestamp}.txt")
    print(f"  2. Inject into DM pipeline (dm_agent_v2.py system prompt)")
    print(f"  3. Re-run backtest: railway run python3.11 scripts/backtest_massive.py --mode re-eval --sample 100")
    print(f"  4. Compare: python3.11 scripts/compare_backtests.py --before <v1> --after <v2>")


if __name__ == "__main__":
    main()
