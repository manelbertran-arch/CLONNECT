#!/usr/bin/env python3
"""Filter contaminated records from sft_sprint7.jsonl.

Removes training records with response cosine sim ≥ 0.92 vs any eval case.
Indices pre-computed by 05_coverage_check.py / PASO 2 identification step.

Usage:
    python3 scripts/finetuning/sprint7/06_filter_contaminated.py \
        [--indices /tmp/train_indices_to_remove.txt]
"""

import json
import sys
from collections import Counter
from pathlib import Path

INPUT        = Path("data/dpo/trl/sprint7/sft_sprint7.jsonl")
OUTPUT       = Path("data/dpo/trl/sprint7/sft_sprint7.jsonl")   # in-place
INDICES_FILE = Path(
    sys.argv[sys.argv.index("--indices") + 1]
    if "--indices" in sys.argv
    else "/tmp/train_indices_to_remove.txt"
)


def main() -> None:
    if not INDICES_FILE.exists():
        print(f"ERROR: indices file not found: {INDICES_FILE}")
        sys.exit(1)

    indices_to_remove: set[int] = set()
    with INDICES_FILE.open() as f:
        for line in f:
            line = line.strip()
            if line:
                indices_to_remove.add(int(line))

    print(f"Indices to remove: {len(indices_to_remove)}")

    records: list = []
    with INPUT.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    print(f"Original:  {len(records)}")

    filtered = [r for i, r in enumerate(records) if i not in indices_to_remove]
    n_removed = len(records) - len(filtered)

    print(f"Removed:   {n_removed}")
    print(f"Filtered:  {len(filtered)}")

    src = Counter(r.get("source") for r in filtered)
    print(f"Sources:   {dict(src)}")

    with OUTPUT.open("w", encoding="utf-8") as f:
        for r in filtered:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Wrote {len(filtered)} records to {OUTPUT}")


if __name__ == "__main__":
    main()
