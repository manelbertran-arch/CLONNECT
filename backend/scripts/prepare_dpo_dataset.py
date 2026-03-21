"""
Prepare DPO dataset for fine-tuning from preference_pairs_export.jsonl.

Reads the exported JSONL and formats it for DPO fine-tuning with common
frameworks (TRL, OpenRLHF, Axolotl). Also creates train/val splits.

Usage:
    python3 scripts/prepare_dpo_dataset.py
    python3 scripts/prepare_dpo_dataset.py --format trl --val-split 0.1
    python3 scripts/prepare_dpo_dataset.py --format openai  # for OpenAI fine-tuning

Output:
    data/dpo/dpo_train.jsonl
    data/dpo/dpo_val.jsonl
    data/dpo/dpo_stats.json
"""

import argparse
import json
import random
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
INPUT_PATH = REPO_ROOT / "data" / "dpo" / "preference_pairs_export.jsonl"
OUTPUT_DIR = REPO_ROOT / "data" / "dpo"

SYSTEM_PROMPT = (
    "Eres Iris Bertran. Monitora de fitness en Dinamic Sport Gym, Igualada (Barcelona). "
    "Bilingüe catalán-castellano, mensajes ultra-breves, directa, informal, tuteo siempre. "
    "NO eres asistente virtual. Respondes DMs como persona real entre clases."
)


def load_pairs(path: Path):
    pairs = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                pairs.append(json.loads(line))
    return pairs


def format_trl(pair: dict) -> dict:
    """Format for HuggingFace TRL DPOTrainer."""
    return {
        "prompt": pair["prompt"],
        "chosen": pair["chosen"],
        "rejected": pair["rejected"],
    }


def format_openai(pair: dict) -> dict:
    """Format for OpenAI fine-tuning (chat completions DPO)."""
    messages_chosen = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": pair["prompt"]},
        {"role": "assistant", "content": pair["chosen"]},
    ]
    messages_rejected = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": pair["prompt"]},
        {"role": "assistant", "content": pair["rejected"]},
    ]
    return {
        "input": messages_chosen[:-1],
        "preferred_output": [messages_chosen[-1]],
        "non_preferred_output": [messages_rejected[-1]],
    }


def format_chatml(pair: dict) -> dict:
    """Format for Axolotl/ChatML DPO."""
    return {
        "system": SYSTEM_PROMPT,
        "question": pair["prompt"],
        "chosen": pair["chosen"],
        "rejected": pair["rejected"],
    }


FORMATTERS = {
    "trl": format_trl,
    "openai": format_openai,
    "chatml": format_chatml,
}


def main():
    parser = argparse.ArgumentParser(description="Prepare DPO dataset")
    parser.add_argument("--format", choices=list(FORMATTERS.keys()), default="trl")
    parser.add_argument("--val-split", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--input", type=str, default=str(INPUT_PATH))
    args = parser.parse_args()

    random.seed(args.seed)
    fmt = FORMATTERS[args.format]

    # Load
    pairs = load_pairs(Path(args.input))
    print(f"Loaded {len(pairs)} pairs from {args.input}")

    if not pairs:
        print("No pairs found. Run the export first.")
        sys.exit(1)

    # Shuffle and split
    random.shuffle(pairs)
    n_val = max(1, int(len(pairs) * args.val_split))
    val_pairs = pairs[:n_val]
    train_pairs = pairs[n_val:]

    print(f"Split: train={len(train_pairs)}, val={len(val_pairs)}")

    # Format and write
    train_path = OUTPUT_DIR / f"dpo_train.jsonl"
    val_path = OUTPUT_DIR / f"dpo_val.jsonl"

    for path, data in [(train_path, train_pairs), (val_path, val_pairs)]:
        with open(path, "w", encoding="utf-8") as f:
            for pair in data:
                f.write(json.dumps(fmt(pair), ensure_ascii=False) + "\n")

    # Stats
    chosen_lens = [len(p["chosen"]) for p in pairs]
    rejected_lens = [len(p["rejected"]) for p in pairs]

    stats = {
        "format": args.format,
        "total_pairs": len(pairs),
        "train_pairs": len(train_pairs),
        "val_pairs": len(val_pairs),
        "val_split": args.val_split,
        "seed": args.seed,
        "chosen_length": {
            "median": statistics.median(chosen_lens),
            "mean": round(statistics.mean(chosen_lens)),
            "min": min(chosen_lens),
            "max": max(chosen_lens),
        },
        "rejected_length": {
            "median": statistics.median(rejected_lens),
            "mean": round(statistics.mean(rejected_lens)),
            "min": min(rejected_lens),
            "max": max(rejected_lens),
        },
        "files": {
            "train": str(train_path),
            "val": str(val_path),
        },
    }

    stats_path = OUTPUT_DIR / "dpo_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    print(f"\nOutput:")
    print(f"  Train: {train_path} ({len(train_pairs)} pairs)")
    print(f"  Val:   {val_path} ({len(val_pairs)} pairs)")
    print(f"  Stats: {stats_path}")
    print(f"\nFormat: {args.format}")
    print(f"Chosen length:   median={statistics.median(chosen_lens):.0f}, mean={statistics.mean(chosen_lens):.0f}")
    print(f"Rejected length: median={statistics.median(rejected_lens):.0f}, mean={statistics.mean(rejected_lens):.0f}")


if __name__ == "__main__":
    main()
