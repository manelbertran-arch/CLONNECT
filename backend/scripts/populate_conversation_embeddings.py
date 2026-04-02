"""
Phase 1: Populate conversation_embeddings for ALL messages of a creator.

Uses local SentenceTransformer (paraphrase-multilingual-MiniLM-L12-v2, 384 dims).
No external API calls needed.

Usage:
    railway run python3.11 scripts/populate_conversation_embeddings.py --creator-id UUID --creator-str slug
"""
import argparse
import json
import os
import sys
import time

import psycopg2
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BATCH_SIZE = 128


def main():
    parser = argparse.ArgumentParser(description="Populate conversation_embeddings for a creator")
    parser.add_argument("--creator-id", required=True, help="Creator UUID")
    parser.add_argument("--creator-str", required=True, help="Creator slug (e.g. iris_bertran)")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    creator_id = args.creator_id
    creator_str = args.creator_str

    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
    print(f"Model loaded: paraphrase-multilingual-MiniLM-L12-v2 ({model.get_sentence_embedding_dimension()} dims)")

    conn = psycopg2.connect(database_url)
    try:
        _run(conn, model, creator_id, creator_str)
    finally:
        conn.close()


def _run(conn, model, creator_id, creator_str):
    cur = conn.cursor()

    # Check what's already processed
    cur.execute("SELECT message_id FROM conversation_embeddings WHERE message_id IS NOT NULL")
    already_done = {str(r[0]) for r in cur.fetchall()}
    print(f"Already embedded: {len(already_done)} messages")

    # Get all messages for the creator's leads
    cur.execute("""
        SELECT m.id, m.lead_id, m.role, m.content, m.created_at, m.msg_metadata,
               l.platform_user_id
        FROM messages m
        JOIN leads l ON m.lead_id = l.id
        WHERE l.creator_id = %s
        ORDER BY m.created_at
    """, (creator_id,))

    all_messages = cur.fetchall()
    total = len(all_messages)
    print(f"Total messages to process: {total}")

    # Filter out already processed
    to_process = [m for m in all_messages if str(m[0]) not in already_done]
    print(f"Remaining to embed: {len(to_process)}")

    if not to_process:
        print("Nothing to do!")
        return

    inserted = 0
    errors = 0
    start_time = time.time()

    for batch_start in range(0, len(to_process), BATCH_SIZE):
        batch = to_process[batch_start : batch_start + BATCH_SIZE]
        texts = [(msg[3] or "empty").strip() or "empty message" for msg in batch]

        try:
            embeddings = model.encode(texts, normalize_embeddings=True, batch_size=BATCH_SIZE)
        except Exception as e:
            print(f"  ERROR batch {batch_start}: {e}")
            errors += len(batch)
            continue

        # Insert each message with its embedding, using savepoints for per-row safety
        for msg, emb in zip(batch, embeddings):
            msg_id, lead_id, role, content, created_at, metadata, platform_user_id = msg
            follower_id = platform_user_id or str(lead_id)
            emb_str = "[" + ",".join(str(float(x)) for x in emb) + "]"

            try:
                cur.execute("SAVEPOINT sp")
                cur.execute("""
                    INSERT INTO conversation_embeddings
                    (creator_id, follower_id, message_role, content, msg_metadata,
                     created_at, embedding, message_id)
                    VALUES (%s, %s, %s, %s, %s, %s, CAST(%s AS vector), %s)
                """, (
                    creator_str,
                    follower_id,
                    role,
                    content,
                    json.dumps(metadata) if metadata else None,
                    created_at,
                    emb_str,
                    str(msg_id),
                ))
                cur.execute("RELEASE SAVEPOINT sp")
                inserted += 1
            except psycopg2.Error as e:
                cur.execute("ROLLBACK TO SAVEPOINT sp")
                print(f"  INSERT ERROR msg {msg_id}: {e}")
                errors += 1

        conn.commit()

        processed = batch_start + len(batch)
        elapsed = time.time() - start_time
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (len(to_process) - processed) / rate if rate > 0 else 0

        if processed % 200 == 0 or processed == len(to_process):
            print(f"  Progress: {processed}/{len(to_process)} "
                  f"({processed*100//len(to_process)}%) "
                  f"inserted={inserted} errors={errors} "
                  f"rate={rate:.1f}/s ETA={eta:.0f}s")

    elapsed = time.time() - start_time
    print("\n=== COMPLETE ===")
    print(f"Inserted: {inserted}")
    print(f"Errors: {errors}")
    print(f"Time: {elapsed:.1f}s ({elapsed/60:.1f}m)")

    # Final count
    cur.execute("SELECT count(*) FROM conversation_embeddings")
    print(f"conversation_embeddings total: {cur.fetchone()[0]}")

    cur.execute("SELECT message_role, count(*) FROM conversation_embeddings GROUP BY message_role")
    for r in cur.fetchall():
        print(f"  {r[0]}: {r[1]}")


if __name__ == "__main__":
    main()
