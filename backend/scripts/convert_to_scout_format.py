"""
Convert training data from OpenAI chat format to Unsloth conversational format for Llama 4 Scout.

Input:  JSONL with {"messages": [{"role": ..., "content": ...}]}
Output: JSONL with {"conversations": [{"role": ..., "content": ...}]}

Also generates dataset statistics.

Usage:
    cd backend && python -m scripts.convert_to_scout_format \
        --input ~/Desktop/SCOUT_TESTING/stefano_training_data_raw.jsonl \
        --output ~/Desktop/SCOUT_TESTING/scout_training_data.jsonl
"""

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path


def detect_language(text: str) -> str:
    """Simple language detection based on common words."""
    spanish_markers = {"que", "de", "la", "el", "en", "es", "un", "una", "los", "las", "por", "como", "con", "para"}
    english_markers = {"the", "is", "are", "and", "for", "you", "that", "this", "with", "have"}

    words = set(re.findall(r"\b\w+\b", text.lower()))
    es_count = len(words & spanish_markers)
    en_count = len(words & english_markers)

    if es_count > en_count:
        return "spanish"
    elif en_count > es_count:
        return "english"
    return "unknown"


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for Spanish."""
    return max(1, len(text) // 4)


def convert_and_stats(input_path: str, output_path: str) -> None:
    """Convert format and print statistics."""
    examples = []
    with open(input_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            examples.append(json.loads(line))

    print(f"Loaded {len(examples)} examples from {input_path}")

    # Convert to Unsloth conversational format
    converted = []
    input_lengths = []
    output_lengths = []
    input_tokens = []
    output_tokens = []
    languages = Counter()

    for ex in examples:
        msgs = ex.get("messages", [])
        conversations = []
        for msg in msgs:
            conversations.append({
                "role": msg["role"],
                "content": msg["content"],
            })

        converted.append({"conversations": conversations})

        # Stats: user message = input, assistant = output
        user_msg = next((m["content"] for m in msgs if m["role"] == "user"), "")
        asst_msg = next((m["content"] for m in msgs if m["role"] == "assistant"), "")

        input_lengths.append(len(user_msg))
        output_lengths.append(len(asst_msg))
        input_tokens.append(estimate_tokens(user_msg))
        output_tokens.append(estimate_tokens(asst_msg))

        lang = detect_language(asst_msg)
        languages[lang] += 1

    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        for item in converted:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"Converted {len(converted)} examples to {output_path}")

    # Print statistics
    print(f"\n{'=' * 60}")
    print("DATASET STATISTICS")
    print(f"{'=' * 60}")
    print(f"Total examples:          {len(converted)}")
    print(f"\nInput (user messages):")
    print(f"  Avg chars:             {statistics.mean(input_lengths):.0f}")
    print(f"  Median chars:          {statistics.median(input_lengths):.0f}")
    print(f"  Avg tokens (est):      {statistics.mean(input_tokens):.0f}")
    print(f"  Median tokens (est):   {statistics.median(input_tokens):.0f}")
    print(f"\nOutput (assistant responses):")
    print(f"  Avg chars:             {statistics.mean(output_lengths):.0f}")
    print(f"  Median chars:          {statistics.median(output_lengths):.0f}")
    print(f"  Avg tokens (est):      {statistics.mean(output_tokens):.0f}")
    print(f"  Median tokens (est):   {statistics.median(output_tokens):.0f}")
    print(f"\nResponse length distribution:")
    bins = [(0, 10), (10, 20), (20, 40), (40, 60), (60, 100), (100, 200), (200, 9999)]
    for lo, hi in bins:
        count = sum(1 for l in output_lengths if lo <= l < hi)
        pct = 100 * count / len(output_lengths)
        label = f"{lo}-{hi}c" if hi < 9999 else f"{lo}+c"
        bar = "#" * int(pct / 2)
        print(f"  {label:>8s}: {count:4d} ({pct:5.1f}%) {bar}")
    print(f"\nLanguage distribution:")
    for lang, count in languages.most_common():
        print(f"  {lang:>10s}: {count:4d} ({100 * count / len(converted):.1f}%)")

    # Save stats to JSON
    stats_path = output_path.replace(".jsonl", "_stats.json")
    stats = {
        "total_examples": len(converted),
        "input": {
            "avg_chars": round(statistics.mean(input_lengths), 1),
            "median_chars": round(statistics.median(input_lengths), 1),
            "avg_tokens_est": round(statistics.mean(input_tokens), 1),
            "median_tokens_est": round(statistics.median(input_tokens), 1),
        },
        "output": {
            "avg_chars": round(statistics.mean(output_lengths), 1),
            "median_chars": round(statistics.median(output_lengths), 1),
            "avg_tokens_est": round(statistics.mean(output_tokens), 1),
            "median_tokens_est": round(statistics.median(output_tokens), 1),
        },
        "languages": dict(languages.most_common()),
        "length_distribution": {
            f"{lo}-{hi}" if hi < 9999 else f"{lo}+": sum(1 for l in output_lengths if lo <= l < hi)
            for lo, hi in bins
        },
    }
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"\nStats saved to {stats_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert training data to Unsloth format")
    parser.add_argument("--input", required=True, help="Input JSONL (OpenAI format)")
    parser.add_argument("--output", required=True, help="Output JSONL (Unsloth format)")
    args = parser.parse_args()

    convert_and_stats(args.input, args.output)
