"""
Generate synthetic preference pairs using Pseudo Preference Tuning approach.
(Takayama et al., COLING 2025)

chosen = real Iris response (manual, copilot_action IS NULL)
rejected = generic LLM response WITHOUT personality/Doc D

Usage: DATABASE_URL=... GOOGLE_API_KEY=... python3 scripts/generate_pseudo_prefs.py
"""

import asyncio
import json
import os
import sys
import time
import uuid
from datetime import datetime

import httpx
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]
GOOGLE_API_KEY = os.environ["GOOGLE_API_KEY"]

CREATOR_UUID = "8e9d1705-4772-40bd-83b1-c6821c5593bf"
MODEL = "gemini-2.5-flash-lite"
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"

GENERIC_SYSTEM_PROMPT = (
    "Eres un asistente de atención al cliente. "
    "Responde brevemente al siguiente mensaje."
)

MAX_PAIRS = 500
BATCH_SIZE = 10  # Gemini calls per batch before sleeping


async def call_gemini(system_prompt: str, user_message: str) -> str:
    url = f"{GEMINI_API_URL}/{MODEL}:generateContent?key={GOOGLE_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": user_message}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {"maxOutputTokens": 150, "temperature": 0.7},
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def fetch_conversations(conn, limit: int) -> list:
    """Fetch manual Iris responses with context (last 3 months)."""
    cur = conn.cursor()

    # Get manual Iris responses with their lead message
    cur.execute("""
        WITH iris_manual AS (
            SELECT m.id as iris_msg_id, m.lead_id, m.content as iris_response,
                   m.created_at as iris_ts, l.username
            FROM messages m
            JOIN leads l ON l.id = m.lead_id
            WHERE l.creator_id = %s
              AND m.role = 'assistant'
              AND m.copilot_action IS NULL
              AND m.content NOT LIKE '[%%'
              AND length(m.content) BETWEEN 3 AND 200
              AND m.created_at > NOW() - interval '3 months'
            ORDER BY m.created_at DESC
            LIMIT %s
        )
        SELECT im.iris_msg_id, im.lead_id, im.iris_response, im.iris_ts, im.username,
               prev.content as lead_message, prev.id as lead_msg_id
        FROM iris_manual im
        JOIN LATERAL (
            SELECT id, content FROM messages
            WHERE lead_id = im.lead_id
              AND role = 'user'
              AND created_at < im.iris_ts
              AND content NOT LIKE '[%%'
              AND length(content) > 2
            ORDER BY created_at DESC
            LIMIT 1
        ) prev ON true
    """, (CREATOR_UUID, limit * 2))  # fetch extra, some will be filtered

    rows = cur.fetchall()
    cur.close()
    return rows


def fetch_context(conn, lead_id: str, before_ts, max_turns: int = 5) -> list:
    """Fetch last N turns of conversation before a timestamp."""
    cur = conn.cursor()
    cur.execute("""
        SELECT role, content FROM messages
        WHERE lead_id = %s
          AND created_at < %s
          AND content NOT LIKE '[%%'
          AND length(content) > 1
        ORDER BY created_at DESC
        LIMIT %s
    """, (lead_id, before_ts, max_turns))
    rows = cur.fetchall()
    cur.close()
    # Reverse to chronological order
    return [(r[0], r[1]) for r in reversed(rows)]


def check_existing(conn, iris_msg_id: str) -> bool:
    """Check if we already have a pair for this message."""
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM preference_pairs WHERE source_message_id = %s AND action_type = 'pseudo_preference'",
        (iris_msg_id,)
    )
    exists = cur.fetchone() is not None
    cur.close()
    return exists


def format_context_for_prompt(context_turns: list, lead_message: str) -> str:
    """Format conversation context into a prompt string."""
    parts = []
    if context_turns:
        history = []
        for role, content in context_turns:
            label = "Cliente" if role == "user" else "Agente"
            history.append(f"{label}: {content}")
        parts.append("Historial reciente:\n" + "\n".join(history))
    parts.append(f"Mensaje del cliente: {lead_message}")
    return "\n\n".join(parts)


async def main():
    conn = psycopg2.connect(DATABASE_URL)

    print("=== Pseudo Preference Pair Generation ===")
    print(f"Model for rejected: {MODEL}")
    print(f"Max pairs: {MAX_PAIRS}")

    # Fetch conversations
    rows = fetch_conversations(conn, MAX_PAIRS)
    print(f"Fetched {len(rows)} candidate conversations")

    # Filter out already-processed
    candidates = []
    for row in rows:
        iris_msg_id, lead_id, iris_response, iris_ts, username, lead_message, lead_msg_id = row
        if not check_existing(conn, str(iris_msg_id)):
            candidates.append(row)
        if len(candidates) >= MAX_PAIRS:
            break

    print(f"After dedup: {len(candidates)} new pairs to generate")

    if not candidates:
        print("Nothing to do!")
        conn.close()
        return

    cur = conn.cursor()
    generated = 0
    errors = 0

    for i, row in enumerate(candidates):
        iris_msg_id, lead_id, iris_response, iris_ts, username, lead_message, lead_msg_id = row

        # Fetch conversation context
        context_turns = fetch_context(conn, str(lead_id), iris_ts, max_turns=5)
        prompt = format_context_for_prompt(context_turns, lead_message)

        # Generate generic (rejected) response
        try:
            rejected = await call_gemini(GENERIC_SYSTEM_PROMPT, prompt)
        except Exception as e:
            errors += 1
            if errors > 20:
                print(f"\nToo many errors ({errors}), stopping.")
                break
            print(f"  [ERR] {e}")
            continue

        # Build context JSON
        context_json = json.dumps([
            {"role": r, "content": c} for r, c in context_turns
        ], ensure_ascii=False)

        # Insert preference pair
        cur.execute("""
            INSERT INTO preference_pairs (
                id, creator_id, source_message_id, chosen, rejected,
                user_message, conversation_context, action_type, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, (
            str(uuid.uuid4()),
            CREATOR_UUID,
            str(iris_msg_id),
            iris_response,
            rejected,
            lead_message,
            context_json,
            "pseudo_preference",
        ))

        generated += 1

        if generated % 10 == 0:
            conn.commit()
            print(f"  [{generated}/{len(candidates)}] generated ({errors} errors)")

        # Rate limit: small delay between calls
        if generated % BATCH_SIZE == 0:
            await asyncio.sleep(0.5)

    conn.commit()

    # Final stats
    cur.execute("SELECT COUNT(*) FROM preference_pairs")
    total = cur.fetchone()[0]

    cur.execute("SELECT action_type, COUNT(*) FROM preference_pairs GROUP BY action_type ORDER BY COUNT(*) DESC")
    dist = cur.fetchall()

    cur.close()
    conn.close()

    print(f"\n=== RESULTS ===")
    print(f"New pairs generated: {generated}")
    print(f"Errors: {errors}")
    print(f"Total preference_pairs in DB: {total}")
    print(f"\nDistribution:")
    for action_type, count in dist:
        print(f"  {action_type:25s} {count}")


if __name__ == "__main__":
    asyncio.run(main())
