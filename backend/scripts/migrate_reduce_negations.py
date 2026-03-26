"""
Migration: Apply universal negation reducer to all existing Doc Ds.

Reads every row in personality_docs (doc_d, doc_d_distilled, doc_d_v1),
applies reduce_negations() to the §4.1 system prompt section, and saves
the cleaned version back to the DB.

Also updates Iris's on-disk file (data/personality_extractions/...).

Run with:
    railway run python3 scripts/migrate_reduce_negations.py
    # or locally if DATABASE_URL is set:
    python3 scripts/migrate_reduce_negations.py

Flags:
    --dry-run    Print changes without writing to DB/disk (default: apply)
    --creator    Only process a specific creator (e.g. --creator iris_bertran)
"""

import os
import re
import sys
import argparse
from pathlib import Path

# Resolve backend root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.personality_extraction.negation_reducer import reduce_negations


# ── Doc D section regex: matches §4.1 SYSTEM PROMPT backtick block ──────────
_SECTION_RE = re.compile(
    r"(## 4\.1 SYSTEM PROMPT[^\n]*\n```\n)(.*?)(```)",
    re.DOTALL,
)


def apply_to_doc_d(content: str) -> tuple[str, int, int]:
    """Apply reduce_negations to §4.1 system prompt within a Doc D document.

    Returns (updated_content, n_kept, n_removed).
    If no §4.1 section is found, returns (content, 0, 0) unchanged.
    """
    match = _SECTION_RE.search(content)
    if not match:
        # Fallback: treat the whole content as system prompt (e.g. raw files)
        cleaned, kept, removed = reduce_negations(content)
        return cleaned, kept, removed

    prefix, sysprompt, suffix = match.group(1), match.group(2), match.group(3)
    cleaned_sysprompt, kept, removed = reduce_negations(sysprompt)

    if removed == 0:
        return content, 0, 0  # no change needed

    updated = content[: match.start()] + prefix + cleaned_sysprompt + suffix + content[match.end() :]
    return updated, kept, removed


def migrate_db(dry_run: bool, creator_filter: str | None) -> None:
    """Apply reducer to all personality_docs rows in PostgreSQL."""
    from sqlalchemy import create_engine, text

    DATABASE_URL = os.environ.get("DATABASE_URL")
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        query = """
            SELECT pd.id, pd.doc_type, pd.content, c.name as creator
            FROM personality_docs pd
            JOIN creators c ON c.id::text = pd.creator_id
            WHERE pd.doc_type IN ('doc_d', 'doc_d_distilled', 'doc_d_v1')
        """
        params = {}
        if creator_filter:
            query += " AND c.name = :creator"
            params["creator"] = creator_filter

        rows = conn.execute(text(query), params).fetchall()

    print(f"Found {len(rows)} Doc D entries in DB")
    print()

    total_removed = 0
    updated_count = 0

    with engine.connect() as conn:
        for row in rows:
            doc_id, doc_type, content, creator = row.id, row.doc_type, row.content, row.creator

            updated_content, kept, removed = apply_to_doc_d(content)

            print(f"  [{creator}] {doc_type}: {len(content)} chars → {len(updated_content)} chars "
                  f"| removed={removed}, kept={kept}")

            if removed == 0:
                print(f"    (no negations to remove)")
                continue

            # Show what's being removed
            orig_lines = set(content.split("\n"))
            new_lines = set(updated_content.split("\n"))
            removed_lines = [l for l in orig_lines - new_lines if l.strip()]
            for rl in removed_lines[:10]:
                print(f"    - REMOVE: {rl.strip()[:100]}")

            if not dry_run:
                conn.execute(
                    text("UPDATE personality_docs SET content = :content WHERE id = :id"),
                    {"content": updated_content, "id": doc_id},
                )
                conn.commit()
                print(f"    ✓ Updated in DB")
            else:
                print(f"    [DRY RUN] Would update {doc_id}")

            total_removed += removed
            updated_count += 1

        print()
        print(f"Summary: {updated_count}/{len(rows)} docs updated, "
              f"{total_removed} total negation lines removed")
        if dry_run:
            print("(DRY RUN — no changes written)")


def migrate_disk(dry_run: bool, creator_filter: str | None) -> None:
    """Apply reducer to on-disk doc_d_bot_configuration.md files."""
    extractions_dir = ROOT / "data" / "personality_extractions"
    if not extractions_dir.exists():
        print(f"No extractions dir found at {extractions_dir}")
        return

    disk_files = list(extractions_dir.glob("*/doc_d_bot_configuration.md"))
    if not disk_files:
        print("No on-disk doc_d files found")
        return

    print(f"\nFound {len(disk_files)} on-disk Doc D files")

    for path in disk_files:
        creator = path.parent.name
        if creator_filter and creator != creator_filter:
            continue

        content = path.read_text(encoding="utf-8")
        updated_content, kept, removed = apply_to_doc_d(content)

        print(f"  [{creator}] disk: {len(content)} chars → {len(updated_content)} chars "
              f"| removed={removed}, kept={kept}")

        if removed == 0:
            print(f"    (no negations to remove)")
            continue

        orig_lines = set(content.split("\n"))
        new_lines = set(updated_content.split("\n"))
        removed_lines = [l for l in orig_lines - new_lines if l.strip()]
        for rl in removed_lines[:10]:
            print(f"    - REMOVE: {rl.strip()[:100]}")

        if not dry_run:
            path.write_text(updated_content, encoding="utf-8")
            print(f"    ✓ Updated on disk: {path}")
        else:
            print(f"    [DRY RUN] Would write {path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply negation reducer to all Doc Ds")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    parser.add_argument("--creator", default=None, help="Only process a specific creator slug")
    args = parser.parse_args()

    print("=" * 60)
    print("Negation Reducer Migration")
    print("=" * 60)
    if args.dry_run:
        print("MODE: DRY RUN (no writes)")
    else:
        print("MODE: APPLY (writing to DB and disk)")
    if args.creator:
        print(f"FILTER: creator={args.creator}")
    print()

    migrate_db(dry_run=args.dry_run, creator_filter=args.creator)
    migrate_disk(dry_run=args.dry_run, creator_filter=args.creator)
