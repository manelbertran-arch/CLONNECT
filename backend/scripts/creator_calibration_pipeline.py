"""
Creator Calibration Pipeline - Extract personalization data from real conversations.

Produces a calibration JSON with:
  - baseline: median_length, soft_max, emoji_pct, question_pct, excl_pct
  - context_soft_max: per-context P75 length (v9.2)
  - response_pools: categorized pools for pool responses (v10.1)
  - few_shot_examples: diverse examples for LLM prompting
  - tone_targets: emoji, question, exclamation targets

Usage:
    cd backend && python -m scripts.creator_calibration_pipeline \
        --creator-id "5e5c2364-c99a-4484-b986-741bb84a11cf"
"""

import argparse
import json
import os
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from collections import Counter
from typing import Any, Dict, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.backtest.contamination_filter import (
    detect_contaminated_conversations,
    filter_turns,
    is_bot_response,
)
from services.length_controller import classify_lead_context

CREATOR_ID_DEFAULT = "5e5c2364-c99a-4484-b986-741bb84a11cf"


def load_conversation_pairs(creator_id: str) -> Tuple[List[Dict], List[Dict]]:
    """
    Load real conversation pairs from PostgreSQL.

    Returns:
        (conversations, all_turns)
    """
    import sqlalchemy as sa

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    engine = sa.create_engine(database_url)

    query = sa.text("""
        SELECT
            m.lead_id,
            m.role,
            m.content,
            m.status,
            m.approved_by,
            m.created_at,
            l.username as lead_username
        FROM messages m
        JOIN leads l ON m.lead_id = l.id
        WHERE l.creator_id = :creator_id
        AND m.content IS NOT NULL
        AND m.content != ''
        ORDER BY m.lead_id, m.created_at ASC
    """)

    with engine.connect() as conn:
        rows = conn.execute(query, {"creator_id": creator_id}).fetchall()

    print(f"Loaded {len(rows)} messages")

    # Group by lead
    convs_raw = defaultdict(list)
    lead_usernames = {}
    for row in rows:
        convs_raw[row.lead_id].append({
            "role": row.role,
            "content": row.content,
            "status": row.status or "",
            "approved_by": row.approved_by or "",
        })
        if row.lead_username:
            lead_usernames[row.lead_id] = row.lead_username

    # Build pairs
    conversations = []
    all_turns = []
    for lead_id, msgs in convs_raw.items():
        username = lead_usernames.get(lead_id, str(lead_id))
        turns = []
        for i in range(1, len(msgs)):
            curr = msgs[i]
            prev = msgs[i - 1]
            if curr["role"] != "assistant" or curr["status"] != "sent":
                continue
            if curr["approved_by"] not in ("", "creator", "creator_manual"):
                continue
            if prev["role"] != "user":
                continue

            turn = {
                "user_message": prev["content"],
                "real_response": curr["content"],
                "real_length": len(curr["content"]),
                "lead_username": username,
                "context": classify_lead_context(prev["content"]),
            }
            turns.append(turn)
            all_turns.append(turn)

        if turns:
            conversations.append({
                "lead_username": username,
                "turns": turns,
            })

    print(f"Built {len(conversations)} conversations, {len(all_turns)} turns")
    return conversations, all_turns


def compute_baseline(clean_turns: List[Dict]) -> Dict[str, Any]:
    """Compute baseline statistics from clean turns."""
    lengths = [t["real_length"] for t in clean_turns]
    responses = [t["real_response"] for t in clean_turns]

    has_emoji = sum(1 for r in responses if re.search(
        r"[\U00010000-\U0010ffff]|[\u2600-\u27bf]", r
    ))
    has_question = sum(1 for r in responses if "?" in r)
    has_excl = sum(1 for r in responses if "!" in r)

    n = len(clean_turns)
    sorted_lengths = sorted(lengths)

    return {
        "n_turns": n,
        "median_length": int(statistics.median(lengths)),
        "mean_length": round(statistics.mean(lengths), 1),
        "p25_length": sorted_lengths[n // 4] if n > 4 else sorted_lengths[0],
        "p75_length": sorted_lengths[3 * n // 4] if n > 4 else sorted_lengths[-1],
        "p90_length": sorted_lengths[int(n * 0.9)] if n > 10 else sorted_lengths[-1],
        "soft_max": sorted_lengths[int(n * 0.75)] if n > 4 else 60,
        "emoji_pct": round(100 * has_emoji / n, 1),
        "question_frequency_pct": round(100 * has_question / n, 1),
        "exclamation_pct": round(100 * has_excl / n, 1),
    }


def compute_context_soft_max(clean_turns: List[Dict], baseline_soft_max: int) -> Dict[str, int]:
    """Compute P75 length per context (v9.2)."""
    context_lengths: Dict[str, List[int]] = defaultdict(list)
    for turn in clean_turns:
        ctx = turn.get("context", "otro")
        context_lengths[ctx].append(turn["real_length"])

    context_soft_max = {}
    for ctx, lengths in context_lengths.items():
        if len(lengths) >= 5:
            sorted_l = sorted(lengths)
            context_soft_max[ctx] = sorted_l[int(len(sorted_l) * 0.75)]
        else:
            context_soft_max[ctx] = baseline_soft_max

    return context_soft_max


def extract_response_pools(clean_turns: List[Dict], max_pool_length: int = 60) -> Dict[str, List[str]]:
    """
    Extract response pools from short creator responses.

    Pools = responses short enough to use verbatim.
    Categorized into sub-pools (v10.1).
    """
    short_responses = [
        t["real_response"] for t in clean_turns
        if t["real_length"] <= max_pool_length
    ]

    # Deduplicate
    unique = list(set(short_responses))
    print(f"Pool candidates: {len(unique)} unique short responses (<={max_pool_length}c)")

    # Categorize into sub-pools
    pools = categorize_pool_responses(unique)

    # Also keep a flat "all_short" pool
    pools["all_short"] = unique

    return pools


def categorize_pool_responses(responses: List[str]) -> Dict[str, List[str]]:
    """Split pool responses into sub-categories (v10.1)."""
    cats: Dict[str, List[str]] = {
        "humor": [],
        "greeting": [],
        "encouragement": [],
        "gratitude": [],
        "reaction": [],
        "farewell": [],
        "conversational": [],
    }

    for resp in responses:
        text = resp.lower().strip()

        if any(w in text for w in ["jaja", "jeje", "ajaj", "😂", "🤣"]):
            cats["humor"].append(resp)
        elif any(w in text for w in ["hola", "buenas", "buen día", "buenos días", "hey"]):
            cats["greeting"].append(resp)
        elif any(w in text for w in ["vamos", "dale que", "podés", "fuerza", "ánimo", "grande", "crack", "máquina"]):
            cats["encouragement"].append(resp)
        elif any(w in text for w in ["gracias", "agradec", "te quiero", "abrazo", "nada!"]):
            cats["gratitude"].append(resp)
        elif any(w in text for w in ["que lindo", "hermoso", "que bueno", "genial", "increíble", "espectacular"]):
            cats["reaction"].append(resp)
        elif any(w in text for w in ["chau", "abrazo", "hablamos", "cuídate", "hasta"]):
            cats["farewell"].append(resp)
        else:
            cats["conversational"].append(resp)

    # Only keep categories with enough responses
    return {k: v for k, v in cats.items() if len(v) >= 3}


SPANISH_STOPWORDS = {
    "de", "la", "el", "en", "y", "a", "los", "que", "es", "un",
    "una", "por", "con", "no", "se", "del", "las", "para", "al",
    "lo", "como", "más", "pero", "sus", "le", "ya", "o", "fue",
    "este", "ha", "si", "porque", "esta", "son", "entre", "está",
    "cuando", "muy", "sin", "sobre", "ser", "también", "me", "hasta",
    "hay", "donde", "han", "quien", "están", "desde", "todo", "nos",
    "durante", "te", "ni", "mi", "tu", "yo", "eso", "ese", "esa",
    "esto", "aquí", "así", "algo", "ahí", "qué", "cómo", "hola",
    "bien", "sí", "jaja", "jajaja", "gracias", "era", "tiene",
    "vas", "vos", "sos", "ella", "ellos", "mío", "tuyo",
}


def extract_creator_vocabulary(
    creator_responses: List[str], top_n: int = 30
) -> List[str]:
    """Extract the top-N most used words by the creator (excluding stopwords)."""
    words: List[str] = []
    for resp in creator_responses:
        for word in resp.lower().split():
            clean = "".join(c for c in word if c.isalpha() or c == "ñ")
            if clean and len(clean) > 2 and clean not in SPANISH_STOPWORDS:
                words.append(clean)

    counter = Counter(words)
    return [word for word, _ in counter.most_common(top_n)]


def extract_context_response_pools(
    clean_turns: List[Dict], max_length: int = 80
) -> Dict[str, List[str]]:
    """Extract creator responses grouped by conversation context.

    Unlike category pools (humor, greeting, etc.), these are grouped by the
    classify_lead_context result, so the mock LLM can select context-matched
    responses for better semantic similarity.
    """
    pools: Dict[str, List[str]] = defaultdict(list)
    for turn in clean_turns:
        ctx = turn.get("context", "otro")
        resp = turn["real_response"]
        if len(resp) <= max_length:
            pools[ctx].append(resp)

    # Deduplicate within each context
    return {ctx: list(set(resps)) for ctx, resps in pools.items() if len(resps) >= 3}


def extract_few_shot(clean_turns: List[Dict], n_examples: int = 12) -> List[Dict]:
    """
    Extract diverse few-shot examples for LLM prompting.

    Selects examples across different contexts for diversity.
    """
    by_context = defaultdict(list)
    for turn in clean_turns:
        ctx = turn.get("context", "otro")
        by_context[ctx].append(turn)

    examples = []
    # Round-robin across contexts
    contexts = sorted(by_context.keys(), key=lambda c: -len(by_context[c]))
    idx = 0
    while len(examples) < n_examples and idx < 100:
        ctx = contexts[idx % len(contexts)]
        ctx_turns = by_context[ctx]
        turn_idx = idx // len(contexts)
        if turn_idx < len(ctx_turns):
            turn = ctx_turns[turn_idx]
            examples.append({
                "context": ctx,
                "user_message": turn["user_message"],
                "response": turn["real_response"],
                "length": turn["real_length"],
            })
        idx += 1

    return examples[:n_examples]


def run_calibration(creator_id: str, output_dir: str = "calibrations") -> Dict[str, Any]:
    """Run the full calibration pipeline."""
    print(f"\n{'='*60}")
    print(f"CALIBRATION PIPELINE - {creator_id}")
    print(f"{'='*60}\n")

    # Step 1: Load data
    conversations, all_turns = load_conversation_pairs(creator_id)

    # Step 2: Filter contamination (CRITICAL - v9.1)
    clean_turns, excluded, filter_stats = filter_turns(
        conversations, all_turns
    )
    print(f"\nContamination filter: {len(clean_turns)} clean / {len(excluded)} excluded")
    if filter_stats.get("contaminated_conversations"):
        print(f"  Contaminated conversations: {filter_stats['contaminated_conversations']}")

    # Step 3: Compute baseline
    baseline = compute_baseline(clean_turns)
    print(f"\nBaseline stats:")
    print(f"  Median length: {baseline['median_length']}c")
    print(f"  Emoji: {baseline['emoji_pct']}%")
    print(f"  Questions: {baseline['question_frequency_pct']}%")
    print(f"  Exclamations: {baseline['exclamation_pct']}%")

    # Step 4: Per-context soft_max (v9.2)
    context_soft_max = compute_context_soft_max(clean_turns, baseline["soft_max"])
    print(f"\nPer-context soft_max:")
    for ctx, sm in sorted(context_soft_max.items()):
        n_ctx = sum(1 for t in clean_turns if t.get("context") == ctx)
        print(f"  {ctx:25s}: {sm:4d}c  (n={n_ctx})")

    # Step 5: Extract pools (v10.1)
    pools = extract_response_pools(clean_turns)
    print(f"\nResponse pools:")
    for name, items in sorted(pools.items(), key=lambda x: -len(x[1])):
        print(f"  {name:20s}: {len(items):3d} responses")

    # Step 6: Extract few-shot examples
    few_shot = extract_few_shot(clean_turns)
    print(f"\nFew-shot examples: {len(few_shot)}")

    # Step 6.5: Extract context-matched response pools
    context_pools = extract_context_response_pools(clean_turns)
    print(f"\nContext response pools:")
    for ctx, resps in sorted(context_pools.items(), key=lambda x: -len(x[1])):
        print(f"  {ctx:25s}: {len(resps):3d} unique responses")

    # Step 6.6: Extract creator vocabulary
    creator_responses = [t["real_response"] for t in clean_turns]
    vocabulary = extract_creator_vocabulary(creator_responses, top_n=30)
    print(f"\nCreator vocabulary (top 30): {', '.join(vocabulary[:15])}...")

    # Step 7: Context distribution
    context_dist = defaultdict(int)
    for turn in clean_turns:
        context_dist[turn.get("context", "otro")] += 1
    print(f"\nContext distribution:")
    for ctx, count in sorted(context_dist.items(), key=lambda x: -x[1]):
        print(f"  {ctx:25s}: {count:4d} ({100*count/len(clean_turns):.1f}%)")

    # Build calibration output
    calibration = {
        "creator_id": creator_id,
        "version": "v9",
        "n_clean_turns": len(clean_turns),
        "n_excluded_turns": len(excluded),
        "baseline": baseline,
        "context_soft_max": context_soft_max,
        "response_pools": {k: v for k, v in pools.items() if k != "all_short"},
        "context_response_pools": context_pools,
        "few_shot_examples": few_shot,
        "creator_vocabulary": vocabulary,
        "filter_stats": filter_stats,
        "context_distribution": dict(context_dist),
    }

    # Save
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"{creator_id}.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(calibration, f, indent=2, ensure_ascii=False)

    print(f"\nCalibration saved to: {output_path}")
    return calibration


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run calibration pipeline")
    parser.add_argument("--creator-id", default=CREATOR_ID_DEFAULT)
    parser.add_argument("--output-dir", default="calibrations")
    args = parser.parse_args()

    run_calibration(args.creator_id, args.output_dir)
