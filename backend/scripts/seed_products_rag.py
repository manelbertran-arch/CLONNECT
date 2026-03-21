"""
Seed product/service chunks into content_chunks and generate embeddings.

Usage: DATABASE_URL=... OPENAI_API_KEY=... python3 scripts/seed_products_rag.py

This script:
1. Inserts product chunks from iris_products_from_posts.json into content_chunks
2. Generates OpenAI embeddings for ALL un-embedded chunks (existing + new)
3. Stores embeddings in content_embeddings
"""

import json
import os
import sys
import uuid

import psycopg2
from openai import OpenAI

DATABASE_URL = os.environ["DATABASE_URL"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
CREATOR_ID = "iris_bertran"
EMBEDDING_MODEL = "text-embedding-3-small"

def load_products():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(script_dir, "..", "analysis", "iris_products_from_posts.json")
    with open(path) as f:
        return json.load(f)

def build_product_chunks(data):
    """Build text chunks from product catalog for RAG ingestion."""
    chunks = []

    # One chunk per service with confirmed pricing
    for svc in data["services"]:
        parts = [f"SERVICIO: {svc['name']}"]
        parts.append(f"Categoria: {svc['category']}")
        parts.append(f"Descripcion: {svc['description']}")

        if "schedule" in svc:
            schedule_parts = []
            for k, v in svc["schedule"].items():
                if k != "notes":
                    schedule_parts.append(f"  {k}: {v}")
            if schedule_parts:
                parts.append("Horario:\n" + "\n".join(schedule_parts))
            if "notes" in svc["schedule"]:
                parts.append(f"Nota horario: {svc['schedule']['notes']}")

        if "pricing" in svc:
            pricing_parts = []
            for k, v in svc["pricing"].items():
                if not k.startswith("source_"):
                    pricing_parts.append(f"  {k}: {v}")
            if pricing_parts:
                parts.append("Precios:\n" + "\n".join(pricing_parts))

        if "booking" in svc:
            parts.append(f"Reserva: {svc['booking']}")

        if "payment" in svc:
            parts.append(f"Pago: {svc['payment']}")

        if "notes" in svc:
            parts.append(f"Notas: {svc['notes']}")

        content = "\n".join(parts)
        chunk_id = f"product_{svc['id']}_{CREATOR_ID}"

        chunks.append({
            "chunk_id": chunk_id,
            "content": content,
            "source_type": "product_catalog",
            "source_id": f"iris_products_v2_{svc['id']}",
            "source_url": svc.get("instagram_posts", [None])[0],
            "title": f"Producto: {svc['name']}",
        })

    # Summary chunks
    # Pricing summary
    pricing_lines = [f"RESUMEN DE PRECIOS - Iris Bertran (@iris_bertran)"]
    for k, v in data["pricing_summary"].items():
        pricing_lines.append(f"  {k.replace('_', ' ')}: {v}")
    chunks.append({
        "chunk_id": f"product_pricing_summary_{CREATOR_ID}",
        "content": "\n".join(pricing_lines),
        "source_type": "product_catalog",
        "source_id": "iris_products_v2_pricing",
        "source_url": None,
        "title": "Resumen de precios - Iris Bertran",
    })

    # Schedule summary
    schedule_lines = [f"HORARIO SEMANAL - Iris Bertran (@iris_bertran)"]
    for day, activity in data["schedule_summary"].items():
        schedule_lines.append(f"  {day}: {activity}")
    chunks.append({
        "chunk_id": f"product_schedule_summary_{CREATOR_ID}",
        "content": "\n".join(schedule_lines),
        "source_type": "product_catalog",
        "source_id": "iris_products_v2_schedule",
        "source_url": None,
        "title": "Horario semanal - Iris Bertran",
    })

    # Location & payment
    loc = data["location"]
    pay = data["payment_methods"]
    info_lines = [
        f"INFORMACION GENERAL - Iris Bertran",
        f"Ubicacion: {loc['gym']} - {loc['city']}",
        f"Estudio personal: {loc['studio_personal']}",
        f"Notas ubicacion: {loc['notes']}",
        f"Pago Bizum: {pay['bizum']}",
        f"Pago recepcion: {pay['recepcion_dinamic']}",
        f"Nota pagos: {pay['notes']}",
    ]
    chunks.append({
        "chunk_id": f"product_info_general_{CREATOR_ID}",
        "content": "\n".join(info_lines),
        "source_type": "product_catalog",
        "source_id": "iris_products_v2_info",
        "source_url": None,
        "title": "Info general - Iris Bertran",
    })

    return chunks


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    client = OpenAI(api_key=OPENAI_API_KEY)

    # --- Step 1: Insert product chunks ---
    print("=== STEP 1: Inserting product chunks ===")
    data = load_products()
    chunks = build_product_chunks(data)

    inserted = 0
    skipped = 0
    for chunk in chunks:
        cur.execute("SELECT 1 FROM content_chunks WHERE chunk_id = %s", (chunk["chunk_id"],))
        if cur.fetchone():
            skipped += 1
            continue

        cur.execute("""
            INSERT INTO content_chunks (id, creator_id, chunk_id, content, source_type, source_id, source_url, title, chunk_index, total_chunks, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, 1, NOW())
        """, (
            str(uuid.uuid4()),
            CREATOR_ID,
            chunk["chunk_id"],
            chunk["content"],
            chunk["source_type"],
            chunk["source_id"],
            chunk["source_url"],
            chunk["title"],
        ))
        inserted += 1

    conn.commit()
    print(f"  Inserted: {inserted}, Skipped (already exist): {skipped}")

    # --- Step 2: Find all un-embedded chunks ---
    print("\n=== STEP 2: Finding un-embedded chunks ===")
    cur.execute("""
        SELECT cc.chunk_id, cc.content
        FROM content_chunks cc
        LEFT JOIN content_embeddings ce ON cc.chunk_id = ce.chunk_id
        WHERE cc.creator_id = %s AND ce.chunk_id IS NULL
        ORDER BY cc.created_at
    """, (CREATOR_ID,))
    unembedded = cur.fetchall()
    print(f"  Un-embedded chunks: {len(unembedded)}")

    if not unembedded:
        print("  Nothing to embed!")
        cur.close()
        conn.close()
        return

    # --- Step 3: Generate embeddings in batches ---
    print("\n=== STEP 3: Generating embeddings ===")
    BATCH_SIZE = 20
    total_embedded = 0

    for i in range(0, len(unembedded), BATCH_SIZE):
        batch = unembedded[i:i+BATCH_SIZE]
        texts = [row[1][:30000] for row in batch]  # truncate to safe limit
        chunk_ids = [row[0] for row in batch]

        print(f"  Batch {i//BATCH_SIZE + 1}: {len(batch)} chunks...", end=" ", flush=True)

        response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)

        for item in response.data:
            cid = chunk_ids[item.index]
            embedding = item.embedding
            embedding_str = "[" + ",".join(str(x) for x in embedding) + "]"

            cur.execute("""
                INSERT INTO content_embeddings (chunk_id, creator_id, content_preview, embedding)
                VALUES (%s, %s, %s, CAST(%s AS vector))
                ON CONFLICT (chunk_id) DO UPDATE SET
                    embedding = CAST(%s AS vector),
                    updated_at = NOW()
            """, (
                cid,
                CREATOR_ID,
                texts[item.index][:500],
                embedding_str,
                embedding_str,
            ))
            total_embedded += 1

        conn.commit()
        print(f"OK ({total_embedded} total)")

    # --- Step 4: Final counts ---
    print("\n=== FINAL COUNTS ===")
    cur.execute("SELECT COUNT(*) FROM content_chunks WHERE creator_id = %s", (CREATOR_ID,))
    total_chunks = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM content_embeddings WHERE creator_id = %s", (CREATOR_ID,))
    total_embeddings = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FROM content_chunks cc
        LEFT JOIN content_embeddings ce ON cc.chunk_id = ce.chunk_id
        WHERE cc.creator_id = %s AND ce.chunk_id IS NULL
    """, (CREATOR_ID,))
    still_unembedded = cur.fetchone()[0]

    print(f"  Chunks:      {total_chunks}")
    print(f"  Embeddings:  {total_embeddings}")
    print(f"  Un-embedded: {still_unembedded}")
    print(f"  Product chunks inserted this run: {inserted}")
    print(f"  Embeddings generated this run:    {total_embedded}")

    cur.close()
    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
