"""RAG Health Check — validates data integrity post-deploy.

Checks:
1. Embedding coverage per creator (>80% chunks have embeddings)
2. No UUID creator_ids in content_chunks (should be slugs)
3. No duplicate chunk_ids
4. RAG search functional (embedding generation + pgvector query)
5. No empty/broken chunks

Exit code 0 = healthy, 1 = problems found.

Usage:
  railway run python3 scripts/rag_health_check.py
  python3 scripts/rag_health_check.py  # with DATABASE_URL set
"""

import os
import sys

sys.path.insert(0, ".")


def check_rag_health():
    errors = []
    warnings = []

    try:
        from api.database import SessionLocal
        from sqlalchemy import text
    except Exception as e:
        print(f"FAIL: Cannot import database modules: {e}")
        sys.exit(1)

    s = SessionLocal()
    try:
        # ── 1. Embedding coverage per creator ────────────────────────
        creators = s.execute(
            text(
                "SELECT creator_id, COUNT(*) as total "
                "FROM content_chunks "
                "WHERE content IS NOT NULL AND LENGTH(content) > 20 "
                "GROUP BY creator_id"
            )
        ).fetchall()

        for row in creators:
            cid, total = row[0], row[1]
            with_emb = s.execute(
                text(
                    "SELECT COUNT(DISTINCT cc.chunk_id) "
                    "FROM content_chunks cc "
                    "JOIN content_embeddings ce ON ce.chunk_id = cc.chunk_id "
                    "WHERE cc.creator_id = :cid "
                    "AND cc.content IS NOT NULL AND LENGTH(cc.content) > 20"
                ),
                {"cid": cid},
            ).scalar()
            pct = with_emb / max(total, 1) * 100
            if pct < 50:
                errors.append(
                    f"Embeddings {cid}: {pct:.0f}% ({with_emb}/{total}) — below 50%"
                )
            elif pct < 80:
                warnings.append(
                    f"Embeddings {cid}: {pct:.0f}% ({with_emb}/{total}) — below 80%"
                )
            else:
                print(f"  OK  Embeddings {cid}: {pct:.0f}% ({with_emb}/{total})")

        # ── 2. No UUID creator_ids ───────────────────────────────────
        uuid_cids = s.execute(
            text("SELECT COUNT(*) FROM content_chunks WHERE creator_id ~ '^[0-9a-f]{8}-'")
        ).scalar()
        if uuid_cids > 0:
            warnings.append(f"UUID creator_ids: {uuid_cids} chunks (should be slug)")
        else:
            print("  OK  Creator IDs: all slugs")

        # ── 3. No duplicate chunk_ids ────────────────────────────────
        dupes = s.execute(
            text(
                "SELECT COUNT(*) FROM ("
                "  SELECT chunk_id FROM content_chunks "
                "  WHERE chunk_id IS NOT NULL "
                "  GROUP BY chunk_id HAVING COUNT(*) > 1"
                ") sub"
            )
        ).scalar()
        if dupes > 0:
            errors.append(f"Duplicate chunk_ids: {dupes}")
        else:
            print("  OK  Duplicates: 0")

        # ── 4. RAG search functional ─────────────────────────────────
        try:
            from core.embeddings import generate_embedding

            emb = generate_embedding("cuánto cuesta barre")
            if emb:
                # Verify pgvector search works
                from core.embeddings import search_similar

                results = search_similar(emb, "iris_bertran", top_k=1, min_similarity=0.3)
                if results:
                    print(
                        f"  OK  RAG search: functional "
                        f"(top={results[0]['similarity']:.3f})"
                    )
                else:
                    errors.append("RAG search returned 0 results for 'cuánto cuesta barre'")
            else:
                errors.append("generate_embedding returned None (check OPENAI_API_KEY)")
        except Exception as e:
            errors.append(f"RAG search error: {e}")

        # ── 5. Content quality ───────────────────────────────────────
        empty = s.execute(
            text(
                "SELECT COUNT(*) FROM content_chunks "
                "WHERE content IS NULL OR LENGTH(content) < 10"
            )
        ).scalar()
        if empty > 10:
            warnings.append(f"Empty/tiny chunks: {empty}")
        else:
            print(f"  OK  Content quality: {empty} empty/tiny chunks")

        # ── 6. Orphan embeddings (embedding without chunk) ───────────
        orphans = s.execute(
            text(
                "SELECT COUNT(*) FROM content_embeddings ce "
                "LEFT JOIN content_chunks cc ON ce.chunk_id = cc.chunk_id "
                "WHERE cc.chunk_id IS NULL"
            )
        ).scalar()
        if orphans > 0:
            warnings.append(f"Orphan embeddings: {orphans} (no matching chunk)")
        else:
            print("  OK  Orphan embeddings: 0")

    finally:
        s.close()

    # ── Report ───────────────────────────────────────────────────────
    print()
    if errors:
        print("=" * 50)
        print(f"RAG HEALTH: {len(errors)} ERROR(S)")
        print("=" * 50)
        for e in errors:
            print(f"  FAIL  {e}")
        for w in warnings:
            print(f"  WARN  {w}")
        sys.exit(1)
    elif warnings:
        print("=" * 50)
        print(f"RAG HEALTH: OK ({len(warnings)} warning(s))")
        print("=" * 50)
        for w in warnings:
            print(f"  WARN  {w}")
        sys.exit(0)
    else:
        print("RAG HEALTH: ALL OK")
        sys.exit(0)


if __name__ == "__main__":
    check_rag_health()
