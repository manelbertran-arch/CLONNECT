#!/usr/bin/env python3
"""
Pre-training hook: verifica que Doc D NO cambió desde freeze Sprint 7.
Bloquea training si version_id != frozen.
"""
import hashlib
import sys
from pathlib import Path

DOC_D_PATH = Path("data/personality_extractions/iris_bertran/doc_d_bot_configuration.md")
FROZEN_HASH_FILE = Path("scripts/finetuning/.sprint7_frozen_hash")


def compute_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if not DOC_D_PATH.exists():
        print(f"ABORT: Doc D not found at {DOC_D_PATH}")
        sys.exit(1)

    if not FROZEN_HASH_FILE.exists():
        print(f"ABORT: frozen hash file missing at {FROZEN_HASH_FILE}. Run snapshot first.")
        sys.exit(1)

    current_hash = compute_hash(DOC_D_PATH)
    frozen_hash = FROZEN_HASH_FILE.read_text().strip()

    if current_hash != frozen_hash:
        print(f"ABORT: Doc D changed since Sprint 7 freeze")
        print(f"  Frozen:  {frozen_hash}")
        print(f"  Current: {current_hash}")
        print(f"  Action:  update frozen hash if change is intentional, or investigate drift")
        sys.exit(1)

    print(f"OK: Doc D version unchanged ({current_hash[:12]}...)")
    sys.exit(0)


if __name__ == "__main__":
    main()
