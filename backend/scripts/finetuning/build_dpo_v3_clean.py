"""
Build dpo_iris_v3_clean.jsonl — Sprint 10 BUG-4 fix.

Filters applied:
  F1: prompt not None and not empty
  F2: chosen and rejected >= 5 chars
  F3: rejected is not copilot/system text
  F4: near-duplicate filter (similarity <= 0.85, Razin 2024)
  F5: identical pairs
  F6: chosen not excessively long (>250 chars)

Usage:
  python scripts/finetuning/build_dpo_v3_clean.py
"""
import json
import random
from collections import Counter
from difflib import SequenceMatcher
from statistics import mean, stdev

INPUT = "data/dpo/trl/dpo_iris_v2.jsonl"
OUTPUT = "data/dpo/trl/dpo_iris_v3_clean.jsonl"

_COPILOT_MARKERS = [
    "copilot", "[copilot]", "system message", "your role is",
    "you are an ai", "as an ai", "as a language model",
    "i'm an ai", "i am an ai",
]


def is_valid_pair(pair: dict) -> tuple[bool, str]:
    # F1: prompt not None and not empty
    prompt = pair.get("prompt")
    if not prompt or len(prompt.strip()) < 3:
        return False, "prompt_invalid"

    # F2: chosen and rejected >= 5 chars
    chosen = (pair.get("chosen") or "").strip()
    rejected = (pair.get("rejected") or "").strip()
    if len(chosen) < 5 or len(rejected) < 5:
        return False, "response_too_short"

    # F3: rejected is not copilot/system text
    rejected_lower = rejected.lower()
    if any(marker in rejected_lower for marker in _COPILOT_MARKERS):
        return False, "rejected_is_copilot"

    # F4: near-duplicate filter (Razin et al. 2024)
    similarity = SequenceMatcher(None, chosen, rejected).ratio()
    if similarity > 0.85:
        return False, "near_duplicate"

    # F5: identical
    if chosen == rejected:
        return False, "identical"

    # F6: chosen not excessively long
    if len(chosen) > 250:
        return False, "chosen_too_long"

    return True, "valid"


def main():
    reasons: Counter = Counter()
    clean_pairs: list[dict] = []

    with open(INPUT) as f:
        for line in f:
            pair = json.loads(line)
            valid, reason = is_valid_pair(pair)
            reasons[reason] += 1
            if valid:
                clean_pairs.append(pair)

    total = sum(reasons.values())
    retention = len(clean_pairs) / total * 100

    with open(OUTPUT, "w") as f:
        for pair in clean_pairs:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    print(f"Total input: {total}")
    print(f"Valid output: {len(clean_pairs)}")
    print(f"Retention rate: {retention:.1f}%")
    print(f"\nFiltered reasons:")
    for reason, count in reasons.most_common():
        pct = count / total * 100
        print(f"  {reason}: {count} ({pct:.1f}%)")

    # Quality stats
    prompt_lens = [len(p["prompt"]) for p in clean_pairs]
    chosen_lens = [len(p["chosen"]) for p in clean_pairs]
    rejected_lens = [len(p["rejected"]) for p in clean_pairs]
    print(f"\nQuality stats ({len(clean_pairs)} pairs):")
    print(f"  Avg prompt length:   {mean(prompt_lens):.0f} chars (σ={stdev(prompt_lens):.0f})")
    print(f"  Avg chosen length:   {mean(chosen_lens):.0f} chars (σ={stdev(chosen_lens):.0f})")
    print(f"  Avg rejected length: {mean(rejected_lens):.0f} chars (σ={stdev(rejected_lens):.0f})")

    # Sample 5 random pairs
    print("\n=== Sample 5 pairs ===")
    random.seed(42)
    for p in random.sample(clean_pairs, min(5, len(clean_pairs))):
        print(f"\nPrompt:   {p['prompt'][:120]}")
        print(f"Chosen:   {p['chosen'][:120]}")
        print(f"Rejected: {p['rejected'][:120]}")

    return {
        "total_input": total,
        "total_output": len(clean_pairs),
        "retention_pct": round(retention, 1),
        "reasons": dict(reasons),
        "avg_prompt_len": round(mean(prompt_lens), 0),
        "avg_chosen_len": round(mean(chosen_lens), 0),
        "avg_rejected_len": round(mean(rejected_lens), 0),
    }


if __name__ == "__main__":
    main()
