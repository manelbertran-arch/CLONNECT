"""Backfill DNA vocabulary_uses for all records.

Extracts vocabulary from REAL creator messages using word-boundary
tokenization and TF-IDF distinctiveness scoring.

Usage:
  railway run python3.11 scripts/backfill_dna_vocabulary.py --creator iris_bertran
  railway run python3.11 scripts/backfill_dna_vocabulary.py --creator iris_bertran --dry-run
"""

import argparse
import json
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from services.vocabulary_extractor import (
    build_global_corpus,
    get_top_distinctive_words,
    tokenize,
)


def _get_write_session():
    """Get a session that can write — uses direct Neon endpoint (not pooler)."""
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    # Switch from pooler to direct endpoint for write access
    db_url = db_url.replace("-pooler.", ".")
    if "sslmode" not in db_url:
        sep = "&" if "?" in db_url else "?"
        db_url = f"{db_url}{sep}sslmode=require"
    engine = create_engine(db_url, echo=False, pool_pre_ping=True)
    return sessionmaker(bind=engine), engine


def main():
    parser = argparse.ArgumentParser(description="Backfill DNA vocabulary")
    parser.add_argument("--creator", required=True, help="Creator slug")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--batch-size", type=int, default=10)
    args = parser.parse_args()

    creator_id = args.creator
    print(f"=== Backfill DNA vocabulary for {creator_id} ===")
    print(f"  dry_run={args.dry_run}, batch_size={args.batch_size}")

    # Build global corpus once
    print("\n[1/3] Building global corpus...")
    global_vocab, total_leads, leads_per_word = build_global_corpus(creator_id, use_cache=False)
    print(f"  {total_leads} leads, {len(global_vocab)} unique words")

    if total_leads == 0:
        print("  ERROR: No leads found. Check creator_id.")
        return

    # Get all DNA records — use direct endpoint for write access
    WriteSession, write_engine = _get_write_session()
    s = WriteSession()
    try:
        cr = s.execute(
            text("SELECT id FROM creators WHERE name = :name LIMIT 1"),
            {"name": creator_id},
        ).fetchone()
        if not cr:
            print(f"  ERROR: Creator '{creator_id}' not found")
            return
        creator_uuid = str(cr[0])

        dnas = s.execute(
            text("""
                SELECT rd.follower_id, rd.vocabulary_uses, rd.relationship_type
                FROM relationship_dna rd
                WHERE rd.creator_id = :cid
                ORDER BY rd.created_at
            """),
            {"cid": creator_id},
        ).fetchall()

        print(f"\n[2/3] Processing {len(dnas)} DNA records...")
        updated = 0
        skipped = 0
        empty = 0

        for i, dna in enumerate(dnas):
            follower_id = dna[0]
            old_vocab = dna[1] or []
            rel_type = dna[2]

            # Fetch real creator messages for this lead
            msgs = s.execute(
                text("""
                    SELECT m.content FROM messages m
                    JOIN leads l ON m.lead_id = l.id
                    WHERE l.creator_id = CAST(:cid AS uuid)
                    AND l.platform_user_id = :fid
                    AND m.role = 'assistant'
                    AND m.content IS NOT NULL
                    AND LENGTH(m.content) > 2
                    AND m.deleted_at IS NULL
                    AND COALESCE(m.approved_by, 'human') NOT IN ('auto', 'autopilot')
                    ORDER BY m.created_at
                """),
                {"cid": creator_uuid, "fid": follower_id},
            ).fetchall()

            creator_messages = [m[0] for m in msgs]

            if len(creator_messages) < 3:
                skipped += 1
                continue

            # Extract vocabulary with TF-IDF
            new_vocab = get_top_distinctive_words(
                creator_messages,
                global_vocab=global_vocab,
                total_leads=total_leads,
                leads_per_word=leads_per_word,
                top_n=8,
                min_freq=2,
            )

            if not new_vocab:
                empty += 1
                continue

            print(f"  {follower_id[:25]:25s} type={rel_type:20s} "
                  f"msgs={len(creator_messages):3d} "
                  f"old={old_vocab} -> new={new_vocab}")

            if not args.dry_run:
                s.execute(
                    text("""
                        UPDATE relationship_dna
                        SET vocabulary_uses = :vocab,
                            version = COALESCE(version, 1) + 1
                        WHERE creator_id = :cid AND follower_id = :fid
                    """),
                    {"vocab": json.dumps(new_vocab), "cid": creator_id, "fid": follower_id},
                )
                updated += 1

                # Batch commit
                if updated % args.batch_size == 0:
                    s.commit()
                    time.sleep(1)

        if not args.dry_run and updated % args.batch_size != 0:
            s.commit()

        print(f"\n[3/3] Done: {updated} updated, {skipped} skipped (<3 msgs), "
              f"{empty} empty (no distinctive words)")

        if args.dry_run:
            print("  (dry-run: no changes written)")

    finally:
        s.close()
        write_engine.dispose()


if __name__ == "__main__":
    main()
