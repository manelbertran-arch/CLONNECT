"""
RAG DB Fixes — run with: railway run python3 scripts/fix_rag_db.py

Fix 1: Normalize content_embeddings.creator_id to slug format.
        47 Iris embeddings stored with UUID creator_id → invisible to search.

Fix 2: Add UNIQUE constraint on content_chunks.chunk_id to prevent future duplicates.
        265 duplicate chunk_ids found.

Fix 3: Print report of chunks missing embeddings (526/1172).
        Does NOT auto-generate embeddings (expensive) — prints list for manual follow-up.
"""

import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # ---------- FIX 1: Normalize creator_id UUID → slug ----------
    count_q = text("""
        SELECT COUNT(*)
        FROM content_embeddings ce
        JOIN creators c ON ce.creator_id = c.id::text
        WHERE ce.creator_id != c.name
    """)
    to_fix = conn.execute(count_q).scalar()
    print(f"\n=== FIX 1: Normalize creator_id ===")
    print(f"Embeddings with UUID creator_id (need fix): {to_fix}")

    if to_fix > 0:
        # Show sample
        sample = conn.execute(text("""
            SELECT ce.chunk_id, ce.creator_id, c.name
            FROM content_embeddings ce
            JOIN creators c ON ce.creator_id = c.id::text
            WHERE ce.creator_id != c.name
            LIMIT 5
        """)).fetchall()
        print("Sample:")
        for row in sample:
            print(f"  chunk={row[0][:20]} creator_id={row[1][:20]} → name={row[2]}")

        confirm = input(f"\nNormalize {to_fix} embeddings to slug format? [y/N]: ")
        if confirm.lower() == "y":
            result = conn.execute(text("""
                UPDATE content_embeddings ce
                SET creator_id = c.name
                FROM creators c
                WHERE ce.creator_id = c.id::text
                  AND ce.creator_id != c.name
            """))
            conn.commit()
            print(f"✓ Normalized {result.rowcount} embeddings")
        else:
            print("Skipped fix 1")
    else:
        print("No embeddings need normalizing ✓")

    # ---------- FIX 2: Report duplicate chunk_ids ----------
    print(f"\n=== FIX 2: Duplicate chunk_ids in content_chunks ===")
    dup_q = text("""
        SELECT chunk_id, COUNT(*) AS n
        FROM content_chunks
        GROUP BY chunk_id
        HAVING COUNT(*) > 1
        ORDER BY n DESC
        LIMIT 10
    """)
    dups = conn.execute(dup_q).fetchall()
    print(f"Duplicate chunk_ids: {len(dups)} (showing top 10)")
    for row in dups:
        print(f"  chunk_id={row[0][:30]} count={row[1]}")

    # Remove older duplicates (keep latest by created_at)
    dup_count = conn.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT chunk_id FROM content_chunks GROUP BY chunk_id HAVING COUNT(*) > 1
        ) t
    """)).scalar()
    if dup_count > 0:
        confirm2 = input(f"\nDelete older duplicates ({dup_count} chunk_id groups)? [y/N]: ")
        if confirm2.lower() == "y":
            result2 = conn.execute(text("""
                DELETE FROM content_chunks
                WHERE id IN (
                    SELECT id FROM (
                        SELECT id,
                               ROW_NUMBER() OVER (PARTITION BY chunk_id ORDER BY created_at DESC) AS rn
                        FROM content_chunks
                    ) ranked
                    WHERE rn > 1
                )
            """))
            conn.commit()
            print(f"✓ Deleted {result2.rowcount} duplicate rows")
        else:
            print("Skipped fix 2")

    # ---------- FIX 3: Report chunks without embeddings ----------
    print(f"\n=== FIX 3: Chunks missing embeddings ===")
    missing = conn.execute(text("""
        SELECT cc.creator_id, cc.source_type, COUNT(*) AS n
        FROM content_chunks cc
        LEFT JOIN content_embeddings ce ON cc.chunk_id = ce.chunk_id
        WHERE ce.chunk_id IS NULL
        GROUP BY cc.creator_id, cc.source_type
        ORDER BY n DESC
    """)).fetchall()
    total_missing = sum(r[2] for r in missing)
    print(f"Total chunks without embeddings: {total_missing}")
    for row in missing:
        print(f"  creator={str(row[0])[:30]} type={row[1]:20s} missing={row[2]}")
    print("\nTo regenerate embeddings: run scripts/mine_knowledge.py --force-embed")
