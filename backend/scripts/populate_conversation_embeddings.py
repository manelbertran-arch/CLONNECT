"""
Phase 1: Populate conversation_embeddings for ALL messages.
Generates embeddings via OpenAI text-embedding-3-small (1536 dim).
Processes in batches of 50, with 0.5s delay between batches.
"""
import os
import time
import json
import psycopg2
import httpx
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]
EMBEDDING_MODEL = "text-embedding-3-small"
BATCH_SIZE = 50
SLEEP_BETWEEN_BATCHES = 0.5
CREATOR_ID = "5e5c2364-c99a-4484-b986-741bb84a11cf"
CREATOR_STR = "stefano_bonanno"


def get_embeddings(texts: list[str], client: httpx.Client) -> list[list[float]]:
    """Call OpenAI embeddings API for a batch of texts."""
    # Truncate very long texts to avoid token limits
    truncated = [t[:8000] if len(t) > 8000 else t for t in texts]
    # Filter empty strings
    processed = [t if t.strip() else "empty message" for t in truncated]

    resp = client.post(
        "https://api.openai.com/v1/embeddings",
        json={"input": processed, "model": EMBEDDING_MODEL},
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    # Sort by index to maintain order
    data.sort(key=lambda x: x["index"])
    return [d["embedding"] for d in data]


def main():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    # Check what's already processed
    cur.execute("SELECT message_id FROM conversation_embeddings WHERE message_id IS NOT NULL")
    already_done = {str(r[0]) for r in cur.fetchall()}
    print(f"Already embedded: {len(already_done)} messages")

    # Get all messages for Stefano's leads
    cur.execute("""
        SELECT m.id, m.lead_id, m.role, m.content, m.created_at, m.msg_metadata,
               l.platform_user_id
        FROM messages m
        JOIN leads l ON m.lead_id = l.id
        WHERE l.creator_id = %s
        ORDER BY m.created_at
    """, (CREATOR_ID,))

    all_messages = cur.fetchall()
    total = len(all_messages)
    print(f"Total messages to process: {total}")

    # Filter out already processed
    to_process = [m for m in all_messages if str(m[0]) not in already_done]
    print(f"Remaining to embed: {len(to_process)}")

    if not to_process:
        print("Nothing to do!")
        return

    client = httpx.Client()
    inserted = 0
    errors = 0
    start_time = time.time()

    for batch_start in range(0, len(to_process), BATCH_SIZE):
        batch = to_process[batch_start : batch_start + BATCH_SIZE]
        texts = [msg[3] or "empty" for msg in batch]  # content field

        try:
            embeddings = get_embeddings(texts, client)
        except Exception as e:
            print(f"  ERROR batch {batch_start}: {e}")
            errors += len(batch)
            time.sleep(2)  # Back off on error
            continue

        # Insert each message with its embedding
        for msg, emb in zip(batch, embeddings):
            msg_id, lead_id, role, content, created_at, metadata, platform_user_id = msg
            follower_id = platform_user_id or str(lead_id)

            try:
                cur.execute("""
                    INSERT INTO conversation_embeddings
                    (creator_id, follower_id, message_role, content, msg_metadata,
                     created_at, embedding, message_id)
                    VALUES (%s, %s, %s, %s, %s, %s, CAST(%s AS vector), %s)
                """, (
                    CREATOR_STR,
                    follower_id,
                    role,
                    content,
                    json.dumps(metadata) if metadata else None,
                    created_at,
                    str(emb),
                    str(msg_id),
                ))
                inserted += 1
            except Exception as e:
                conn.rollback()
                print(f"  INSERT ERROR msg {msg_id}: {e}")
                errors += 1
                # Re-establish transaction
                cur = conn.cursor()

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

        time.sleep(SLEEP_BETWEEN_BATCHES)

    client.close()

    elapsed = time.time() - start_time
    print(f"\n=== PHASE 1 COMPLETE ===")
    print(f"Total processed: {inserted + errors}")
    print(f"Inserted: {inserted}")
    print(f"Errors: {errors}")
    print(f"Time: {elapsed:.1f}s ({elapsed/60:.1f}m)")

    # Final count
    cur.execute("SELECT count(*) FROM conversation_embeddings")
    print(f"conversation_embeddings total: {cur.fetchone()[0]}")

    cur.execute("SELECT message_role, count(*) FROM conversation_embeddings GROUP BY message_role")
    for r in cur.fetchall():
        print(f"  {r[0]}: {r[1]}")

    conn.close()


if __name__ == "__main__":
    main()
