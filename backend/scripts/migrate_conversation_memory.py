#!/usr/bin/env python3
"""ARC2 A2.3 — Migrate follower_memories → arc2_lead_memories.

The design-doc source called "conversation_memory table" maps to the actual
`follower_memories` DB table (migration 006), which stores per-follower
structured data (name, interests, objections_raised, products_discussed,
status, purchase_intent_score).

One DB row → multiple arc2_lead_memories rows, one per field value.

Idempotent: uses INSERT ... ON CONFLICT DO NOTHING on the unique index
(creator_id, lead_id, memory_type, content).

Usage:
    python3 -m scripts.migrate_conversation_memory [--dry-run] [--creator-slug iris_bertran]
    python3 -m scripts.migrate_conversation_memory --batch-size 500 --sleep-between-batches 1
"""

import argparse
import logging
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

WRITER = "migration_conversation_memory"

# Confidence levels per field type
CONF_NAME = 0.8
CONF_INTEREST = 0.6
CONF_OBJECTION = 0.6
CONF_PRODUCT = 0.6
CONF_STATUS = 0.5
CONF_INTENT = 0.5


def _resolve_creator_uuid(db, slug: str) -> str | None:
    row = db.execute(
        text("SELECT id FROM creators WHERE name = :slug LIMIT 1"),
        {"slug": slug},
    ).fetchone()
    return str(row[0]) if row else None


def _resolve_lead_uuid(db, creator_uuid: str, follower_id: str) -> str | None:
    raw = follower_id
    for prefix in ("ig_", "wa_", "tg_"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    row = db.execute(
        text(
            "SELECT id FROM leads "
            "WHERE creator_id = CAST(:cid AS uuid) "
            "AND platform_user_id = ANY(ARRAY[:pid, :raw, :ig, :wa, :tg]) "
            "LIMIT 1"
        ),
        {
            "cid": creator_uuid,
            "pid": follower_id,
            "raw": raw,
            "ig": f"ig_{raw}",
            "wa": f"wa_{raw}",
            "tg": f"tg_{raw}",
        },
    ).fetchone()
    return str(row[0]) if row else None


def _insert_memory(
    db,
    *,
    creator_uuid: str,
    lead_uuid: str,
    memory_type: str,
    content: str,
    why: str | None = None,
    how_to_apply: str | None = None,
    confidence: float,
    dry_run: bool,
) -> bool:
    """Insert one arc2_lead_memories row. Returns True if inserted (or would insert)."""
    if not content or not content.strip():
        return False
    content = content.strip()[:2000]

    if dry_run:
        return True

    db.execute(
        text("""
            INSERT INTO arc2_lead_memories
                (creator_id, lead_id, memory_type, content, why, how_to_apply,
                 body_extras, confidence, last_writer)
            VALUES
                (:cid, :lid, :mtype, :content, :why, :how_to_apply,
                 '{}', :conf, :writer)
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
        },
    )
    return True


def _process_row(db, row, dry_run: bool) -> dict[str, int]:
    """Process one follower_memories row. Returns counts of actions."""
    counts: dict[str, int] = {"inserted": 0, "skipped": 0, "errors": 0}

    creator_slug = str(row.creator_id)
    follower_id = str(row.follower_id)

    creator_uuid = _resolve_creator_uuid(db, creator_slug)
    if not creator_uuid:
        counts["skipped"] += 1
        logger.debug("Creator slug not found: %s", creator_slug)
        return counts

    lead_uuid = _resolve_lead_uuid(db, creator_uuid, follower_id)
    if not lead_uuid:
        counts["skipped"] += 1
        logger.debug("Lead not found for creator=%s follower=%s", creator_slug, follower_id)
        return counts

    try:
        # Name → identity
        if row.name and str(row.name).strip():
            if _insert_memory(
                db, creator_uuid=creator_uuid, lead_uuid=lead_uuid,
                memory_type="identity",
                content=f"Nombre: {row.name}",
                confidence=CONF_NAME,
                dry_run=dry_run,
            ):
                counts["inserted"] += 1

        # Interests → interest
        interests = row.interests or []
        for item in (interests if isinstance(interests, list) else []):
            if item and str(item).strip():
                if _insert_memory(
                    db, creator_uuid=creator_uuid, lead_uuid=lead_uuid,
                    memory_type="interest",
                    content=str(item),
                    confidence=CONF_INTEREST,
                    dry_run=dry_run,
                ):
                    counts["inserted"] += 1

        # Products discussed → interest
        products = row.products_discussed or []
        for item in (products if isinstance(products, list) else []):
            if item and str(item).strip():
                if _insert_memory(
                    db, creator_uuid=creator_uuid, lead_uuid=lead_uuid,
                    memory_type="interest",
                    content=f"Producto de interés: {item}",
                    confidence=CONF_PRODUCT,
                    dry_run=dry_run,
                ):
                    counts["inserted"] += 1

        # Objections → objection (needs why + how_to_apply)
        objections = row.objections_raised or []
        for item in (objections if isinstance(objections, list) else []):
            if item and str(item).strip():
                if _insert_memory(
                    db, creator_uuid=creator_uuid, lead_uuid=lead_uuid,
                    memory_type="objection",
                    content=str(item),
                    why="Objeción detectada en conversación (migrada de FollowerMemory)",
                    how_to_apply="(pending re-extraction) — manejar antes de continuar la venta",
                    confidence=CONF_OBJECTION,
                    dry_run=dry_run,
                ):
                    counts["inserted"] += 1

        # Status → relationship_state (needs why + how_to_apply)
        status = getattr(row, "status", None)
        if status and str(status).strip() and status != "new":
            if _insert_memory(
                db, creator_uuid=creator_uuid, lead_uuid=lead_uuid,
                memory_type="relationship_state",
                content=f"Estado de la relación: {status}",
                why="Estado registrado por FollowerMemory legacy",
                how_to_apply="(pending re-extraction) — adaptar tono según estado",
                confidence=CONF_STATUS,
                dry_run=dry_run,
            ):
                counts["inserted"] += 1

        # Purchase intent score → intent_signal (only if meaningful)
        score = getattr(row, "purchase_intent_score", None)
        if score and float(score) >= 0.3:
            if _insert_memory(
                db, creator_uuid=creator_uuid, lead_uuid=lead_uuid,
                memory_type="intent_signal",
                content=f"Puntuación de intención de compra: {float(score):.1f}",
                confidence=CONF_INTENT,
                dry_run=dry_run,
            ):
                counts["inserted"] += 1

    except Exception as exc:
        logger.error(
            "Error processing row creator=%s follower=%s: %s",
            creator_slug, follower_id, exc,
        )
        counts["errors"] += 1

    return counts


def run(
    *,
    dry_run: bool,
    batch_size: int,
    creator_slug: str | None,
    sleep_between_batches: float,
) -> None:
    from api.database import SessionLocal

    db = SessionLocal()
    try:
        # Build count query
        if creator_slug:
            count_row = db.execute(
                text("SELECT COUNT(*) FROM follower_memories WHERE creator_id = :slug"),
                {"slug": creator_slug},
            ).fetchone()
        else:
            count_row = db.execute(text("SELECT COUNT(*) FROM follower_memories")).fetchone()

        total = int(count_row[0]) if count_row else 0
        logger.info(
            "follower_memories rows to process: %d (creator_slug=%s dry_run=%s)",
            total, creator_slug or "ALL", dry_run,
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
            if creator_slug:
                rows = db.execute(
                    text(
                        "SELECT creator_id, follower_id, name, interests, "
                        "products_discussed, objections_raised, status, "
                        "purchase_intent_score "
                        "FROM follower_memories WHERE creator_id = :slug "
                        "ORDER BY creator_id, follower_id "
                        "LIMIT :limit OFFSET :offset"
                    ),
                    {"slug": creator_slug, "limit": batch_size, "offset": offset},
                ).fetchall()
            else:
                rows = db.execute(
                    text(
                        "SELECT creator_id, follower_id, name, interests, "
                        "products_discussed, objections_raised, status, "
                        "purchase_intent_score "
                        "FROM follower_memories "
                        "ORDER BY creator_id, follower_id "
                        "LIMIT :limit OFFSET :offset"
                    ),
                    {"limit": batch_size, "offset": offset},
                ).fetchall()

            if not rows:
                break

            for row in rows:
                counts = _process_row(db, row, dry_run=dry_run)
                total_inserted += counts["inserted"]
                total_skipped += counts["skipped"]
                total_errors += counts["errors"]

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
        description="Migrate follower_memories → arc2_lead_memories (ARC2 A2.3)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only, no writes")
    parser.add_argument("--batch-size", type=int, default=1000, metavar="N")
    parser.add_argument("--creator-slug", type=str, default=None, metavar="SLUG",
                        help="Filter by creator slug (e.g. iris_bertran)")
    parser.add_argument("--sleep-between-batches", type=float, default=2.0, metavar="SEC")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("DRY RUN — no writes will be made")

    run(
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        creator_slug=args.creator_slug,
        sleep_between_batches=args.sleep_between_batches,
    )


if __name__ == "__main__":
    main()
