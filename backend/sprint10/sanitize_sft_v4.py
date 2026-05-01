"""
Sprint 10 — Sanitize SFT v4 dataset.

Filters records whose tokenized length exceeds MAX_TOKENS using the actual
Qwen3-32B tokenizer. This is more accurate than the char-based estimate used
in build_sft_v4.py.

Input:  data/dpo/trl/sft_v4_multiturn.jsonl
Output: data/dpo/trl/sft_v4_multiturn_filtered.jsonl

Usage:
  HF_TOKEN=<token> python sprint10/sanitize_sft_v4.py [--input PATH] [--output PATH]
"""

import argparse
import json
import sys
from pathlib import Path


MAX_TOKENS = 8000  # Safety margin under max_seq_len=8192


def sanitize(input_path: str, output_path: str) -> None:
    try:
        from transformers import AutoTokenizer
    except ImportError:
        print("ERROR: transformers not installed. Run: pip install transformers")
        sys.exit(1)

    print(f"Loading Qwen/Qwen3-32B tokenizer...")
    tok = AutoTokenizer.from_pretrained("Qwen/Qwen3-32B", trust_remote_code=True)
    print("Tokenizer loaded.")

    stats = {"total": 0, "kept": 0, "filtered_too_long": 0}
    token_lens = []

    with open(input_path) as fin, open(output_path, "w") as fout:
        for line in fin:
            rec = json.loads(line)
            text = tok.apply_chat_template(
                rec["messages"], tokenize=False, add_generation_prompt=False
            )
            n_tokens = len(tok(text, add_special_tokens=False).input_ids)
            token_lens.append(n_tokens)
            stats["total"] += 1

            if n_tokens <= MAX_TOKENS:
                fout.write(line)
                stats["kept"] += 1
            else:
                stats["filtered_too_long"] += 1

            if stats["total"] % 1000 == 0:
                print(f"  Processed {stats['total']} / {stats['total']} ...")

    import statistics
    retention = stats["kept"] / stats["total"] * 100
    filtered_pct = stats["filtered_too_long"] / stats["total"] * 100

    print(f"\n=== Sanitize stats ===")
    print(f"Input:    {stats['total']} records")
    print(f"Kept:     {stats['kept']} ({retention:.1f}%)")
    print(f"Filtered: {stats['filtered_too_long']} ({filtered_pct:.1f}%) — exceeded {MAX_TOKENS} tokens")
    print(f"Token length: min={min(token_lens)}, max={max(token_lens)}, "
          f"mean={statistics.mean(token_lens):.0f}, p95={sorted(token_lens)[int(len(token_lens)*0.95)]}")

    if filtered_pct > 5.0:
        print(f"\n⚠ WARNING: {filtered_pct:.1f}% filtered (>5% threshold)")
        print("  Consider raising MAX_SEQ_LEN or re-running build_sft_v4.py with stricter char filter")
    else:
        print(f"\n✓ Retention {retention:.1f}% within expected range (95-99%)")

    output_size = Path(output_path).stat().st_size / 1024 / 1024
    print(f"Output:   {output_path} ({output_size:.1f} MB)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        default="data/dpo/trl/sft_v4_multiturn.jsonl",
        help="Input JSONL path",
    )
    parser.add_argument(
        "--output",
        default="data/dpo/trl/sft_v4_multiturn_filtered.jsonl",
        help="Output JSONL path",
    )
    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f"ERROR: Input not found: {args.input}")
        sys.exit(1)

    sanitize(args.input, args.output)


if __name__ == "__main__":
    main()
