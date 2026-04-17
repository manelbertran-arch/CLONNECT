#!/usr/bin/env python3
"""
Manual Doc D snapshot utility.

Creates a row in doc_d_versions for a given creator with an optional tag.
Safe to run before any experiment — idempotent within 24h for identical content.

Usage:
    python3 scripts/doc_d_snapshot.py --creator iris_bertran --tag pre_arc1_experiment
    python3 scripts/doc_d_snapshot.py --creator iris_bertran  # tag defaults to "manual"
"""

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(description="Manual Doc D snapshot")
    parser.add_argument("--creator", required=True, help="Creator slug (e.g. iris_bertran)")
    parser.add_argument("--tag", default="manual", help="Human-readable label for this snapshot")
    args = parser.parse_args()

    creator_name = args.creator
    tag = args.tag

    from sqlalchemy import create_engine, text

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL env var not set")
        sys.exit(1)

    engine = create_engine(db_url, pool_pre_ping=True)

    with engine.connect() as conn:
        # Resolve creator UUID
        row = conn.execute(
            text("SELECT id FROM creators WHERE name = :n LIMIT 1"),
            {"n": creator_name},
        ).fetchone()
        if not row:
            print(f"ERROR: Creator '{creator_name}' not found in DB")
            sys.exit(1)
        creator_db_id = row[0]

        # Fetch current Doc D from personality_docs
        doc_row = conn.execute(
            text("""
                SELECT content FROM personality_docs
                WHERE creator_id = :cid AND doc_type = 'doc_d'
            """),
            {"cid": str(creator_db_id)},
        ).fetchone()

        if not doc_row or not doc_row[0]:
            print(f"WARNING: No Doc D found for '{creator_name}' in personality_docs")
            doc_d_text = ""
        else:
            doc_d_text = doc_row[0]

        print(f"  Creator : {creator_name} ({creator_db_id})")
        print(f"  Doc D   : {len(doc_d_text):,} chars")
        print(f"  Tag     : {tag}")

        # Use the shared snapshot helper (handles dedup)
        from services.persona_compiler import _snapshot_doc_d

        class _FakeSession:
            """Thin adapter so _snapshot_doc_d works with a raw SQLAlchemy connection."""
            def __init__(self, c):
                self._c = c

            def execute(self, stmt, params=None):
                return self._c.execute(stmt, params or {})

            def commit(self):
                self._c.commit()

            def rollback(self):
                self._c.rollback()

        session = _FakeSession(conn)
        version_id = _snapshot_doc_d(
            session,
            creator_db_id,
            doc_d_text,
            "manual_snapshot",
            metadata={"tag": tag, "trigger": "manual_snapshot", "snapshot_at": datetime.now().isoformat()},
        )
        conn.commit()

    print(f"\n  Snapshot ID : {version_id}")
    print(f"  Done. Run: SELECT * FROM doc_d_versions WHERE id = '{version_id}';")


if __name__ == "__main__":
    main()
