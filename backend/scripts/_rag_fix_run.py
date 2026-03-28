"""Temporary fix script — run with: railway run python3 scripts/_rag_fix_run.py"""
import sys, os

sys.path.insert(0, ".")
from sqlalchemy import create_engine, text

engine = create_engine(os.environ["DATABASE_URL"])

with engine.connect() as conn:
    # ====================================================================
    # FIX 1: Normalize content_embeddings + content_chunks UUID → slug
    # ====================================================================
    r1 = conn.execute(text("""
        UPDATE content_embeddings ce
        SET creator_id = c.name
        FROM creators c
        WHERE ce.creator_id = c.id::text
          AND ce.creator_id <> c.name
    """))
    conn.commit()
    print(f"FIX 1a content_embeddings: {r1.rowcount} rows UUID→slug")

    r2 = conn.execute(text("""
        UPDATE content_chunks cc
        SET creator_id = c.name
        FROM creators c
        WHERE cc.creator_id = c.id::text
          AND cc.creator_id <> c.name
    """))
    conn.commit()
    print(f"FIX 1b content_chunks:     {r2.rowcount} rows UUID→slug")

    # Verify
    dist = conn.execute(text(
        "SELECT creator_id, COUNT(*) FROM content_embeddings GROUP BY creator_id ORDER BY COUNT(*) DESC"
    )).fetchall()
    print("\ncontent_embeddings after fix 1:")
    for r in dist:
        flag = "✅" if "-" not in str(r[0]) else "❌ UUID still"
        print(f"  {flag} {str(r[0])[:40]}: {r[1]}")

    # ====================================================================
    # FIX 3: Dedup content_chunks — keep latest per chunk_id
    # ====================================================================
    dup_count_before = conn.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT chunk_id FROM content_chunks
            WHERE chunk_id IS NOT NULL
            GROUP BY chunk_id HAVING COUNT(*) > 1
        ) t
    """)).scalar()
    print(f"\nFIX 3: duplicate chunk_id groups before: {dup_count_before}")

    r3 = conn.execute(text("""
        DELETE FROM content_chunks
        WHERE ctid NOT IN (
            SELECT MAX(ctid)
            FROM content_chunks
            WHERE chunk_id IS NOT NULL
            GROUP BY chunk_id
        )
        AND chunk_id IN (
            SELECT chunk_id FROM content_chunks
            WHERE chunk_id IS NOT NULL
            GROUP BY chunk_id HAVING COUNT(*) > 1
        )
    """))
    conn.commit()
    print(f"FIX 3: deleted {r3.rowcount} duplicate rows")

    dup_count_after = conn.execute(text("""
        SELECT COUNT(*) FROM (
            SELECT chunk_id FROM content_chunks
            WHERE chunk_id IS NOT NULL
            GROUP BY chunk_id HAVING COUNT(*) > 1
        ) t
    """)).scalar()
    print(f"FIX 3: duplicate chunk_id groups after: {dup_count_after}")

    # ====================================================================
    # COVERAGE CHECK before embedding generation
    # ====================================================================
    total = conn.execute(text("SELECT COUNT(*) FROM content_chunks")).scalar()
    with_emb = conn.execute(text("""
        SELECT COUNT(DISTINCT cc.chunk_id)
        FROM content_chunks cc
        JOIN content_embeddings ce ON ce.chunk_id = cc.chunk_id
    """)).scalar()
    print(f"\nCoverage: {with_emb}/{total} chunks have embeddings ({with_emb/max(total,1)*100:.0f}%)")

    # How many are still missing?
    missing_rows = conn.execute(text("""
        SELECT cc.chunk_id, cc.content, cc.creator_id, cc.source_type
        FROM content_chunks cc
        LEFT JOIN content_embeddings ce ON ce.chunk_id = cc.chunk_id
        WHERE ce.chunk_id IS NULL
          AND cc.content IS NOT NULL
          AND LENGTH(cc.content) > 20
        ORDER BY cc.creator_id, cc.source_type
    """)).fetchall()
    print(f"Missing embeddings: {len(missing_rows)}")

    # By creator/type breakdown
    from collections import Counter
    breakdown = Counter((r[2], r[3]) for r in missing_rows)
    for (creator, stype), n in sorted(breakdown.items()):
        print(f"  {creator[:20]:22s} {stype:20s} {n}")

print("\nFix 1 + Fix 3 DONE. Ready for embedding generation (Fix 2).")
