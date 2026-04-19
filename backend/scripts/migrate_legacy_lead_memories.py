#!/usr/bin/env python3
"""ARC2 A2.3 — Migrate legacy lead_memories → arc2_lead_memories.

Source: `lead_memories` table (migration 030) — MemoryEngine facts with pgvector
embeddings (vector(1536)).

Maps legacy fact_type → arc2 memory_type:
  personal_info  → identity
  preference     → interest
  objection      → objection  (needs why + how_to_apply)
  commitment     → intent_signal
  purchase_history → intent_signal
  topic          → interest
  compressed_memo → SKIPPED  (narrative summaries, not discrete facts)

Embeddings are preserved (fact_embedding → embedding, both vector(1536)).

By default, rows with Ebbinghaus decay_factor below --decay-threshold are skipped
unless --include-decayed is passed.

Idempotent: ON CONFLICT DO NOTHING.

Usage:
    python3 -m scripts.migrate_legacy_lead_memories [--dry-run]
    python3 -m scripts.migrate_legacy_lead_memories --batch-size 500 --include-decayed
"""

import argparse
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

WRITER = "migration_memory_engine"
CONFIDENCE_MIGRATED = 0.7

# Mapping from legacy fact_type → arc2 memory_type
_TYPE_MAP: dict[str, str] = {
    "personal_info": "identity",
    "preference": "interest",
    "objection": "objection",
    "commitment": "intent_signal",
    "purchase_history": "intent_signal",
    "topic": "interest",
}

# Types skipped (not migrated)
_SKIP_TYPES: frozenset[str] = frozenset({"compressed_memo"})

# Types that require why + how_to_apply in arc2
_REQUIRES_WHY_HOW: frozenset[str] = frozenset({"objection", "relationship_state"})


def _map_type(fact_type: str) -> str | None:
    if fact_type in _SKIP_TYPES:
        return None
    mapped = _TYPE_MAP.get(fact_type)
    if not mapped:
        logger.debug("Unknown fact_type=%r — mapping to 'identity'", fact_type)
        return "identity"
    return mapped


def _insert_memory(
    db,
    *,
    creator_uuid: str,
    lead_uuid: str,
    memory_type: str,
    content: str,
    why: str | None,
    how_to_apply: str | None,
    confidence: float,
    embedding_str: str | None,
    source_message_id: str | None,
    dry_run: bool,
) -> bool:
    if not content or not content.strip():
        return False
    content = content.strip()[:2000]

    if dry_run:
        return True

    if embedding_str:
        db.execute(
            text("""
                INSERT INTO arc2_lead_memories
                    (creator_id, lead_id, memory_type, content, why, how_to_apply,
                     body_extras, confidence, last_writer, source_message_id, embedding)
                VALUES
                    (:cid, :lid, :mtype, :content, :why, :how_to_apply,
                     '{}', :conf, :writer, :src, CAST(:emb AS vector))
                ON CONFLICT (creator_id, lead_id, memory_type, content) DO NOTHING
            """),
            {
                "cid": creator_uuid,
                "lid": lead_uuid,
                "mtype": memory_type,
                "content": content,
                "why": why,
                "how_to_apply": how_to_apply,
                "conf": confidence,
                "writer": WRITER,
                "src": source_message_id,
                "emb": embedding_str,
            },
        )
    else:
        db.execute(
            text("""
                INSERT INTO arc2_lead_memories
                    (creator_id, lead_id, memory_type, content, why, how_to_apply,
                     body_extras, confidence, last_writer, source_message_id)
                VALUES
                    (:cid, :lid, :mtype, :content, :why, :how_to_apply,
                     '{}', :conf, :writer, :src)
                ON CONFLICT (creator_id, lead_id, memory_type, content) DO NOTHING
            """),
            {
                "cid": creator_uuid,
                "lid": lead_uuid,
                "mtype": memory_type,
                "content": content,
                "why": why,
                "how_to_apply": how_to_apply,
                "conf": confidence,
                "writer": WRITER,
                "src": source_message_id,
            },
        )
    return True


def run(
    *,
    dry_run: bool,
    batch_size: int,
    include_decayed: bool,
    sleep_between_batches: float = 2.0,
) -> None:
    from api.database import SessionLocal

    db = SessionLocal()
    try:
        active_filter = "" if include_decayed else "AND is_active = true"

        count_row = db.execute(
            text(f"SELECT COUNT(*) FROM lead_memories WHERE fact_type != 'compressed_memo' {active_filter}")
        ).fetchone()
        total = int(count_row[0]) if count_row else 0

        logger.info(
            "lead_memories rows to process: %d (include_decayed=%s dry_run=%s)",
            total, include_decayed, dry_run,
        )

        if total == 0:
            logger.info("Nothing to migrate.")
            return

        offset = 0
        total_inserted = 0
        total_skipped = 0
        total_errors = 0
        batch_num = 0

        while offset < total:
            rows = db.execute(
                text(
                    "SELECT id, creator_id, lead_id, fact_type, fact_text, "
                    "confidence, source_message_id, "
                    "CAST(fact_embedding AS text) AS embedding_text "
                    f"FROM lead_memories WHERE fact_type != 'compressed_memo' {active_filter} "
                    "ORDER BY created_at "
                    "LIMIT :limit OFFSET :offset"
                ),
                {"limit": batch_size, "offset": offset},
            ).fetchall()

            if not rows:
                break

            for row in rows:
                try:
                    memory_type = _map_type(str(row.fact_type or ""))
                    if memory_type is None:
                        total_skipped += 1
                        continue

                    content = str(row.fact_text or "").strip()
                    if not content:
                        total_skipped += 1
                        continue

                    why: str | None = None
                    how_to_apply: str | None = None
                    if memory_type in _REQUIRES_WHY_HOW:
                        why = "Migrado de MemoryEngine legacy (fact_type=objection)"
                        how_to_apply = "(pending re-extraction) — manejar antes de continuar"

                    embedding_str: str | None = None
                    raw_emb = getattr(row, "embedding_text", None)
                    if raw_emb and str(raw_emb).strip():
                        embedding_str = str(raw_emb).strip()

                    src = str(row.source_message_id) if row.source_message_id else None

                    original_conf = float(row.confidence) if row.confidence else CONFIDENCE_MIGRATED
                    # Confidence from MemoryEngine is reliable — keep it, but cap at 0.9
                    final_conf = min(0.9, original_conf)

                    if _insert_memory(
                        db,
                        creator_uuid=str(row.creator_id),
                        lead_uuid=str(row.lead_id),
                        memory_type=memory_type,
                        content=content,
                        why=why,
                        how_to_apply=how_to_apply,
                        confidence=final_conf,
                        embedding_str=embedding_str,
                        source_message_id=src,
                        dry_run=dry_run,
                    ):
                        total_inserted += 1
                    else:
                        total_skipped += 1

                except Exception as exc:
                    logger.error("Error processing row id=%s: %s", getattr(row, "id", "?"), exc)
                    total_errors += 1

            if not dry_run:
                db.commit()

            batch_num += 1
            offset += len(rows)
            logger.info(
                "Batch %d: processed %d/%d rows | inserted=%d skipped=%d errors=%d",
                batch_num, offset, total, total_inserted, total_skipped, total_errors,
            )

            if sleep_between_batches > 0 and offset < total:
                time.sleep(sleep_between_batches)

        logger.info(
            "DONE — rows_scanned=%d inserted=%d skipped=%d errors=%d dry_run=%s",
            total, total_inserted, total_skipped, total_errors, dry_run,
        )

    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate legacy lead_memories → arc2_lead_memories (ARC2 A2.3)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only, no writes")
    parser.add_argument("--batch-size", type=int, default=500, metavar="N")
    parser.add_argument("--include-decayed", action="store_true",
                        help="Include rows with is_active=false (Ebbinghaus-decayed)")
    parser.add_argument("--sleep-between-batches", type=float, default=2.0, metavar="SEC")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("DRY RUN — no writes will be made")

    run(
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        include_decayed=args.include_decayed,
        sleep_between_batches=args.sleep_between_batches,
    )


if __name__ == "__main__":
    main()
