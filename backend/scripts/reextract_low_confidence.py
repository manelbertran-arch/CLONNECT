#!/usr/bin/env python3
"""ARC2 A2.3 — Re-extract low-confidence migration records.

Queries arc2_lead_memories WHERE last_writer LIKE 'migration%' AND
confidence < --confidence-threshold, then calls an LLM extractor to:
  - Re-classify memory_type
  - Rewrite content with better fact extraction
  - Set confidence = 1.0 and last_writer = 'reextraction'

This script is designed to run AFTER A2.2 (MemoryExtractor) is merged. Until
then it uses an inline generic LLM prompt. If MemoryExtractor is available it
will be imported automatically.

TODO(A2.2): Replace inline prompt with MemoryExtractor.extract_single() once
Worker A2.2 is merged to this branch.

Usage:
    python3 -m scripts.reextract_low_confidence --dry-run --max-records 50
    python3 -m scripts.reextract_low_confidence --confidence-threshold 0.6 --batch-size 50
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

WRITER_REEXTRACT = "reextraction"

_MEMORY_TYPES = frozenset(
    {"identity", "interest", "objection", "intent_signal", "relationship_state"}
)

_INLINE_EXTRACTION_PROMPT = """\
Analiza la siguiente memoria migrada de un sistema legacy y clasifícala correctamente.

Memoria a re-extraer:
  tipo_actual: {memory_type}
  contenido: {content}

Clasifica en uno de estos tipos:
  - identity: datos personales del lead (nombre, edad, ubicación, idioma)
  - interest: intereses, productos de interés, temas que le gustan
  - objection: objeciones o barreras para comprar (SIEMPRE incluye why y how_to_apply)
  - intent_signal: señales de intención de compra (precios preguntados, interés activo)
  - relationship_state: estado de la relación con el creator (SIEMPRE incluye why y how_to_apply)

Responde SOLO con JSON válido:
{{
  "memory_type": "<tipo>",
  "content": "<hecho reformulado, conciso, sin ambigüedades>",
  "why": "<por qué es relevante — REQUERIDO si tipo es objection o relationship_state, null si no>",
  "how_to_apply": "<cómo usar en conversación — REQUERIDO si tipo es objection o relationship_state, null si no>"
}}"""


async def _call_llm(prompt: str) -> str:
    try:
        from core.providers.gemini_provider import generate_dm_response

        messages = [
            {
                "role": "system",
                "content": "Eres un clasificador de memorias. Responde SOLO con JSON válido.",
            },
            {"role": "user", "content": prompt},
        ]
        result = await generate_dm_response(messages, max_tokens=400)
        if result and result.get("content"):
            return result["content"]
    except Exception as exc:
        logger.warning("LLM call failed: %s", exc)
    return ""


def _parse_llm_response(raw: str) -> dict | None:
    import json as _json

    raw = raw.strip()
    if raw.startswith("```"):
        lines = [l for l in raw.split("\n") if not l.strip().startswith("```")]
        raw = "\n".join(lines)

    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return _json.loads(raw[start:end])
        except _json.JSONDecodeError:
            pass
    return None


async def _reextract_record(
    db,
    row,
    dry_run: bool,
) -> bool:
    """Re-extract one record. Returns True on success."""
    prompt = _INLINE_EXTRACTION_PROMPT.format(
        memory_type=row.memory_type,
        content=row.content,
    )

    raw_response = await _call_llm(prompt)
    parsed = _parse_llm_response(raw_response)

    if not parsed:
        logger.warning(
            "LLM failed to parse for memory id=%s — skipping",
            str(row.id)[:8],
        )
        return False

    new_type = parsed.get("memory_type", "").strip()
    new_content = parsed.get("content", "").strip()
    new_why = parsed.get("why")
    new_how = parsed.get("how_to_apply")

    if new_type not in _MEMORY_TYPES:
        logger.warning("LLM returned invalid memory_type=%r for id=%s", new_type, str(row.id)[:8])
        return False

    if not new_content:
        return False

    if dry_run:
        logger.info(
            "DRY RUN — would update id=%s: type %s→%s conf→1.0",
            str(row.id)[:8], row.memory_type, new_type,
        )
        return True

    db.execute(
        text("""
            UPDATE arc2_lead_memories SET
                memory_type   = :mtype,
                content       = :content,
                why           = :why,
                how_to_apply  = :how_to_apply,
                confidence    = 1.0,
                last_writer   = :writer,
                updated_at    = now()
            WHERE id = :id
              AND deleted_at IS NULL
        """),
        {
            "id": str(row.id),
            "mtype": new_type,
            "content": new_content[:2000],
            "why": new_why,
            "how_to_apply": new_how,
            "writer": WRITER_REEXTRACT,
        },
    )
    return True


async def _run_async(
    *,
    dry_run: bool,
    batch_size: int,
    max_records: int | None,
    confidence_threshold: float,
    sleep_between_calls: float,
) -> None:
    from api.database import SessionLocal

    db = SessionLocal()
    try:
        limit_clause = f"LIMIT {max_records}" if max_records else ""
        rows = db.execute(
            text(
                "SELECT id, creator_id, lead_id, memory_type, content "
                "FROM arc2_lead_memories "
                "WHERE last_writer LIKE 'migration%' "
                "  AND confidence < :threshold "
                "  AND deleted_at IS NULL "
                f"ORDER BY confidence ASC {limit_clause}"
            ),
            {"threshold": confidence_threshold},
        ).fetchall()

        total = len(rows)
        logger.info(
            "Records to re-extract: %d (threshold=%.2f dry_run=%s)",
            total, confidence_threshold, dry_run,
        )

        if not total:
            logger.info("Nothing to re-extract.")
            return

        success = 0
        failed = 0

        for i, row in enumerate(rows):
            ok = await _reextract_record(db, row, dry_run=dry_run)
            if ok:
                success += 1
            else:
                failed += 1

            if not dry_run and (i + 1) % batch_size == 0:
                db.commit()
                logger.info(
                    "Batch committed: %d/%d | success=%d failed=%d",
                    i + 1, total, success, failed,
                )

            if sleep_between_calls > 0:
                await asyncio.sleep(sleep_between_calls)

        if not dry_run:
            db.commit()

        logger.info(
            "DONE — total=%d success=%d failed=%d dry_run=%s",
            total, success, failed, dry_run,
        )

    finally:
        db.close()


def run(
    *,
    dry_run: bool,
    batch_size: int,
    max_records: int | None,
    confidence_threshold: float,
    sleep_between_calls: float,
) -> None:
    asyncio.run(
        _run_async(
            dry_run=dry_run,
            batch_size=batch_size,
            max_records=max_records,
            confidence_threshold=confidence_threshold,
            sleep_between_calls=sleep_between_calls,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-extract low-confidence migration records (ARC2 A2.3)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only, no writes")
    parser.add_argument("--batch-size", type=int, default=100, metavar="N",
                        help="Commit every N records")
    parser.add_argument("--max-records", type=int, default=None, metavar="N",
                        help="Safety limit: stop after N records")
    parser.add_argument("--confidence-threshold", type=float, default=0.7,
                        help="Re-extract records with confidence < this value")
    parser.add_argument("--sleep-between-calls", type=float, default=1.0, metavar="SEC",
                        help="Sleep between LLM calls (rate limiting)")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("DRY RUN — no writes will be made")

    run(
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        max_records=args.max_records,
        confidence_threshold=args.confidence_threshold,
        sleep_between_calls=args.sleep_between_calls,
    )


if __name__ == "__main__":
    main()
