"""
Knowledge Mining Script — Extract categorized knowledge chunks from conversation history.

Mines historical DM conversations for any creator and extracts Q&A pairs that represent
reusable knowledge (FAQ, expertise, objections, testimonials, values, policies).
Outputs chunks ready for insertion into content_chunks table.

Usage:
    railway run python3 scripts/mine_knowledge.py iris_bertran
    railway run python3 scripts/mine_knowledge.py iris_bertran --dry-run
    railway run python3 scripts/mine_knowledge.py iris_bertran --min-length 20 --limit 500
    railway run python3 scripts/mine_knowledge.py iris_bertran --insert
"""

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
import uuid
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MINE] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)
for name in ["httpx", "httpcore", "urllib3", "sqlalchemy.engine"]:
    logging.getLogger(name).setLevel(logging.WARNING)

# ──────────────────────────────────────────────────────────────
# Category taxonomy
# ──────────────────────────────────────────────────────────────

CATEGORIES = {
    "faq": "Preguntas frecuentes con respuesta concreta (horario, precio, ubicación, inscripción)",
    "expertise": "Conocimiento de dominio (beneficios del entrenamiento, técnica, salud, bienestar)",
    "objection_handling": "Manejo de dudas o resistencias (no tengo tiempo, es caro, no sé si puedo)",
    "testimonial": "Feedback positivo de cliente o reacción de Iris ante progreso de alguien",
    "values": "Valores y filosofía del creator (por qué hace lo que hace, su misión)",
    "policies": "Precios, reservas, cancelaciones, normas de clase, formas de pago",
}

NOISE_PATTERNS = [
    r"^\s*\[audio\]\s*$",
    r"^\s*\[imagen\]\s*$",
    r"^\s*\[video\]\s*$",
    r"^\s*\[sticker\]\s*$",
    r"^\s*(jajaj+a*|jeje+|hahah+|lol+|😂+|❤️+|👍+|🙏+)\s*$",
    r"^ok\s*$",
    r"^vale\s*$",
    r"^sí\s*$",
    r"^no\s*$",
    r"^gracias\s*$",
    r"^genial\s*$",
    r"^\s*$",
]
_NOISE_RE = re.compile("|".join(NOISE_PATTERNS), re.IGNORECASE)


def is_noise(text: str) -> bool:
    return bool(_NOISE_RE.match(text.strip()))


def make_chunk_id(creator_id: str, content: str) -> str:
    """Deterministic chunk_id so re-runs don't duplicate."""
    return hashlib.md5(f"{creator_id}::{content}".encode()).hexdigest()


# ──────────────────────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────────────────────

def fetch_creator_uuid(session, creator_name: str) -> Optional[str]:
    from sqlalchemy import text
    row = session.execute(
        text("SELECT id FROM creators WHERE name = :name"),
        {"name": creator_name},
    ).fetchone()
    return str(row[0]) if row else None


def fetch_qa_pairs(session, creator_uuid: str, min_user_len: int, limit: int) -> list[dict]:
    """
    Extract (user_msg, creator_reply) pairs from conversation history.

    Strategy:
    - For each user message, find the first assistant reply within 15 minutes on the same lead.
    - Filter out noise: media-only messages, very short messages, error responses.
    - Returns pairs ordered by recency (newest first).
    """
    from sqlalchemy import text

    sql = text("""
        SELECT DISTINCT ON (m1.id)
            m1.content            AS user_msg,
            m2.content            AS creator_resp,
            m1.created_at         AS ts
        FROM messages m1
        JOIN messages m2 ON (
            m2.lead_id      = m1.lead_id
            AND m2.role     = 'assistant'
            AND m2.created_at > m1.created_at
            AND m2.created_at < m1.created_at + INTERVAL '15 minutes'
        )
        JOIN leads l ON l.id = m1.lead_id
        WHERE m1.role  = 'user'
          AND l.creator_id = :cid
          AND length(m1.content)    >= :min_len
          AND length(m2.content)    >= 5
          AND m1.content NOT LIKE '%http%'
          AND m1.content NOT LIKE '%[audio]%'
          AND m1.content NOT ILIKE '%error%'
          AND m2.content NOT ILIKE '%lo siento%'
          AND m2.content NOT ILIKE '%hubo un error%'
          AND m2.content NOT ILIKE '%procesando tu mensaje%'
          AND m2.content NOT ILIKE '%intenta de nuevo%'
        ORDER BY m1.id, m2.created_at ASC
        LIMIT :lim
    """)
    rows = session.execute(sql, {
        "cid": creator_uuid,
        "min_len": min_user_len,
        "lim": limit,
    }).fetchall()

    pairs = []
    for row in rows:
        user_msg = (row[0] or "").strip()
        creator_resp = (row[1] or "").strip()
        if is_noise(user_msg) or is_noise(creator_resp):
            continue
        pairs.append({"user": user_msg, "creator": creator_resp})

    return pairs


def fetch_existing_chunk_ids(session, creator_name: str) -> set[str]:
    from sqlalchemy import text
    rows = session.execute(
        text("SELECT chunk_id FROM content_chunks WHERE creator_id = :cid"),
        {"cid": creator_name},
    ).fetchall()
    return {row[0] for row in rows}


def insert_chunks(session, chunks: list[dict]) -> int:
    from sqlalchemy import text
    inserted = 0
    for c in chunks:
        session.execute(text("""
            INSERT INTO content_chunks
                (id, creator_id, chunk_id, content, source_type, title,
                 chunk_index, total_chunks, extra_data, created_at)
            VALUES
                (:id, :creator_id, :chunk_id, :content, :source_type, :title,
                 :chunk_index, :total_chunks, :extra_data::json, NOW())
            ON CONFLICT DO NOTHING
        """), {
            "id": str(uuid.uuid4()),
            "creator_id": c["creator_id"],
            "chunk_id": c["chunk_id"],
            "content": c["content"],
            "source_type": c["source_type"],
            "title": c["title"],
            "chunk_index": c.get("chunk_index", 0),
            "total_chunks": c.get("total_chunks", 1),
            "extra_data": json.dumps(c.get("extra_data", {})),
        })
        inserted += 1
    session.commit()
    return inserted


# ──────────────────────────────────────────────────────────────
# LLM categorization (Gemini)
# ──────────────────────────────────────────────────────────────

def build_categorization_prompt(creator_name: str, pairs: list[dict]) -> str:
    category_desc = "\n".join(f"  - {k}: {v}" for k, v in CATEGORIES.items())
    pairs_text = "\n\n".join(
        f"[{i+1}]\nUSER: {p['user']}\nCREATOR: {p['creator']}"
        for i, p in enumerate(pairs)
    )
    return f"""You are analyzing conversation history of a content creator named {creator_name}.

Categorize each Q&A pair below into ONE of these categories:
{category_desc}
  - skip: casual/personal chat with no reusable knowledge value

For each pair, output a JSON line (one per pair, no markdown):
{{"idx": 1, "category": "faq", "title": "short title (max 8 words)", "content": "rewritten as factual knowledge chunk (1-3 sentences, clear and useful for a chatbot)"}}

Rules:
- "skip" pairs that are purely personal chat, inside jokes, or off-topic
- "content" must be rewritten as a standalone factual statement, not a raw transcript
- For faq/policies: state the fact clearly (e.g. "Barre classes are held every Thursday at 10:30 AM. Price: 5€/class.")
- For expertise: explain the concept or benefit
- For objection_handling: rephrase as a reassuring statement
- For testimonials: summarize the positive feedback
- For values: state the creator's belief or mission
- Title should be in the same language as the content
- Keep "content" under 300 characters

Q&A PAIRS:
{pairs_text}

Output one JSON line per pair, indexed 1 to {len(pairs)}. No other text."""


def call_gemini(prompt: str) -> str:
    import requests

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY / GOOGLE_API_KEY not set")

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    resp = requests.post(
        url,
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 4096},
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    candidates = data.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        if parts:
            return parts[0].get("text", "")
    return ""


def categorize_batch(creator_name: str, pairs: list[dict]) -> list[dict]:
    """Send a batch to Gemini and parse the JSON lines response."""
    prompt = build_categorization_prompt(creator_name, pairs)
    raw = call_gemini(prompt)

    results = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
            results.append(obj)
        except json.JSONDecodeError:
            pass

    return results


# ──────────────────────────────────────────────────────────────
# Main pipeline
# ──────────────────────────────────────────────────────────────

def run(
    creator_name: str,
    min_length: int = 15,
    limit: int = 300,
    batch_size: int = 30,
    dry_run: bool = True,
    insert: bool = False,
    output_file: Optional[str] = None,
):
    t0 = time.time()
    logger.info(f"Mining knowledge for: {creator_name}")

    from api.database import SessionLocal
    session = SessionLocal()

    try:
        # 1. Resolve creator
        creator_uuid = fetch_creator_uuid(session, creator_name)
        if not creator_uuid:
            logger.error(f"Creator not found: {creator_name}")
            return

        logger.info(f"Creator UUID: {creator_uuid}")

        # 2. Fetch Q&A pairs
        logger.info(f"Fetching Q&A pairs (min_length={min_length}, limit={limit})...")
        pairs = fetch_qa_pairs(session, creator_uuid, min_length, limit)
        logger.info(f"  {len(pairs)} pairs after noise filtering")

        if not pairs:
            logger.warning("No pairs found — check creator_name or DB data")
            return

        # 3. Fetch existing chunk_ids to avoid duplicates
        existing_ids = fetch_existing_chunk_ids(session, creator_name)
        logger.info(f"  {len(existing_ids)} existing chunks in content_chunks")

        # 4. Categorize in batches
        logger.info(f"Categorizing with Gemini (batch_size={batch_size})...")
        all_chunks: list[dict] = []
        skipped = 0
        errors = 0

        for batch_start in range(0, len(pairs), batch_size):
            batch = pairs[batch_start: batch_start + batch_size]
            logger.info(f"  Batch {batch_start // batch_size + 1}: pairs {batch_start+1}-{batch_start+len(batch)}")

            try:
                results = categorize_batch(creator_name, batch)
            except Exception as e:
                logger.error(f"  Batch failed: {e}")
                errors += len(batch)
                continue

            for r in results:
                idx = r.get("idx", 0) - 1
                category = r.get("category", "skip")
                content = (r.get("content") or "").strip()
                title = (r.get("title") or "").strip()

                if category == "skip" or not content:
                    skipped += 1
                    continue

                if 0 <= idx < len(batch):
                    original_pair = batch[idx]
                else:
                    continue

                chunk_id = make_chunk_id(creator_name, content)
                if chunk_id in existing_ids:
                    skipped += 1
                    continue

                all_chunks.append({
                    "creator_id": creator_name,
                    "chunk_id": chunk_id,
                    "content": content,
                    "source_type": f"conversation_{category}",
                    "title": title,
                    "chunk_index": 0,
                    "total_chunks": 1,
                    "extra_data": {
                        "category": category,
                        "original_user": original_pair["user"][:200],
                        "original_creator": original_pair["creator"][:200],
                        "mined_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    },
                })

            # Small sleep between batches to avoid rate limits
            if batch_start + batch_size < len(pairs):
                time.sleep(1)

        # 5. Report
        elapsed = time.time() - t0
        logger.info(f"\n{'='*50}")
        logger.info(f"RESULTS for {creator_name}:")
        logger.info(f"  Input pairs:     {len(pairs)}")
        logger.info(f"  Skipped/noise:   {skipped}")
        logger.info(f"  Errors:          {errors}")
        logger.info(f"  New chunks:      {len(all_chunks)}")
        logger.info(f"  Time:            {elapsed:.1f}s")
        logger.info(f"{'='*50}")

        # Category breakdown
        by_cat: dict[str, int] = {}
        for c in all_chunks:
            cat = c["extra_data"]["category"]
            by_cat[cat] = by_cat.get(cat, 0) + 1
        for cat, n in sorted(by_cat.items(), key=lambda x: -x[1]):
            logger.info(f"    {cat}: {n}")

        # 6. Preview
        logger.info("\n--- PREVIEW (first 5 chunks) ---")
        for c in all_chunks[:5]:
            logger.info(f"[{c['extra_data']['category']}] {c['title']}")
            logger.info(f"  {c['content'][:120]}")

        # 7. Save to file
        out_path = output_file or f"scripts/data/knowledge_{creator_name}.json"
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({
                "creator": creator_name,
                "mined_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "n_chunks": len(all_chunks),
                "by_category": by_cat,
                "chunks": all_chunks,
            }, f, ensure_ascii=False, indent=2)
        logger.info(f"\nSaved to: {out_path}")

        # 8. Insert if requested
        if insert and not dry_run:
            logger.info(f"\nInserting {len(all_chunks)} chunks into content_chunks...")
            n = insert_chunks(session, all_chunks)
            logger.info(f"  ✓ Inserted: {n}")
        elif dry_run:
            logger.info("\nDRY RUN — use --insert to write to DB")

    finally:
        session.close()


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Mine knowledge chunks from conversation history")
    parser.add_argument("creator", help="Creator name (e.g. iris_bertran)")
    parser.add_argument("--min-length", type=int, default=15,
                        help="Minimum user message length in characters (default: 15)")
    parser.add_argument("--limit", type=int, default=300,
                        help="Max Q&A pairs to process (default: 300)")
    parser.add_argument("--batch-size", type=int, default=30,
                        help="Pairs per Gemini call (default: 30)")
    parser.add_argument("--insert", action="store_true",
                        help="Write chunks to content_chunks table")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Preview only, do not insert (default: True)")
    parser.add_argument("--output", default=None,
                        help="Output JSON file path (default: scripts/data/knowledge_<creator>.json)")
    args = parser.parse_args()

    run(
        creator_name=args.creator,
        min_length=args.min_length,
        limit=args.limit,
        batch_size=args.batch_size,
        dry_run=not args.insert,
        insert=args.insert,
        output_file=args.output,
    )


if __name__ == "__main__":
    main()
