"""Generate embeddings for content_chunks missing them.
Run: railway run python3 scripts/_rag_gen_embeddings.py
"""
import sys, os, time

sys.path.insert(0, ".")
from sqlalchemy import create_engine, text
from core.embeddings import generate_embedding, store_embedding

engine = create_engine(os.environ["DATABASE_URL"])

with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT cc.chunk_id, cc.content, cc.creator_id, cc.source_type
        FROM content_chunks cc
        LEFT JOIN content_embeddings ce ON ce.chunk_id = cc.chunk_id
        WHERE ce.chunk_id IS NULL
          AND cc.content IS NOT NULL
          AND LENGTH(cc.content) > 20
        ORDER BY cc.creator_id, cc.source_type
    """)).fetchall()
    print(f"Chunks to embed: {len(rows)}")

created = 0
errors = 0
for i, row in enumerate(rows):
    chunk_id, content, creator_id, source_type = row
    try:
        emb = generate_embedding(content[:4000])
        if emb:
            store_embedding(
                chunk_id=chunk_id,
                creator_id=creator_id,
                content=content,
                embedding=emb,
            )
            created += 1
            if created % 25 == 0:
                print(f"  [{i+1}/{len(rows)}] {created} done, {errors} errors")
    except Exception as e:
        errors += 1
        print(f"  Error chunk {chunk_id[:16]}: {e}")
        time.sleep(1.0)

print(f"\nDone: {created} embeddings created, {errors} errors")

# Final coverage
with engine.connect() as conn:
    total = conn.execute(text("SELECT COUNT(*) FROM content_chunks")).scalar()
    with_emb = conn.execute(text("""
        SELECT COUNT(DISTINCT cc.chunk_id)
        FROM content_chunks cc
        JOIN content_embeddings ce ON ce.chunk_id = cc.chunk_id
    """)).scalar()
    print(f"Final coverage: {with_emb}/{total} ({with_emb/max(total,1)*100:.0f}%)")
