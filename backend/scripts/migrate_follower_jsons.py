#!/usr/bin/env python3
"""ARC2 A2.3 — Migrate FollowerMemory JSON files → arc2_lead_memories.

Reads FollowerMemory JSON files from `data/followers/` (default) and converts
each field into typed memories in arc2_lead_memories.

The JSON schema matches the FollowerMemory dataclass in services/memory_service.py:
  follower_id, creator_id, username, name, interests[], objections_raised[],
  products_discussed[], status, purchase_intent_score, preferred_language, …

One JSON file → multiple arc2_lead_memories rows (one per meaningful field value).

Idempotent: ON CONFLICT DO NOTHING.

Usage:
    python3 -m scripts.migrate_follower_jsons [--dry-run]
    python3 -m scripts.migrate_follower_jsons --creator-slug iris_bertran
    python3 -m scripts.migrate_follower_jsons --base-path /custom/path --dry-run
"""

import argparse
import json
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

WRITER = "migration_follower_json"

CONF_NAME = 0.7
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


def _process_file(db, json_path: Path, dry_run: bool) -> dict[str, int]:
    counts: dict[str, int] = {"inserted": 0, "skipped": 0, "errors": 0}

    try:
        with json_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON: %s — %s", json_path, exc)
        counts["errors"] += 1
        return counts
    except Exception as exc:
        logger.error("Cannot read file %s: %s", json_path, exc)
        counts["errors"] += 1
        return counts

    creator_slug = data.get("creator_id") or json_path.parent.name
    follower_id = data.get("follower_id") or json_path.stem

    creator_uuid = _resolve_creator_uuid(db, creator_slug)
    if not creator_uuid:
        logger.debug("Creator not found: %s", creator_slug)
        counts["skipped"] += 1
        return counts

    lead_uuid = _resolve_lead_uuid(db, creator_uuid, follower_id)
    if not lead_uuid:
        logger.debug("Lead not found: creator=%s follower=%s", creator_slug, follower_id)
        counts["skipped"] += 1
        return counts

    try:
        # Name → identity
        name = data.get("name") or ""
        if name.strip():
            if _insert_memory(
                db, creator_uuid=creator_uuid, lead_uuid=lead_uuid,
                memory_type="identity",
                content=f"Nombre: {name}",
                confidence=CONF_NAME,
                dry_run=dry_run,
            ):
                counts["inserted"] += 1

        # Username → identity (only if different from name)
        username = data.get("username") or ""
        if username.strip() and username != name:
            if _insert_memory(
                db, creator_uuid=creator_uuid, lead_uuid=lead_uuid,
                memory_type="identity",
                content=f"Usuario: {username}",
                confidence=CONF_NAME,
                dry_run=dry_run,
            ):
                counts["inserted"] += 1

        # Preferred language → identity
        lang = data.get("preferred_language") or ""
        if lang.strip() and lang not in ("es", ""):
            if _insert_memory(
                db, creator_uuid=creator_uuid, lead_uuid=lead_uuid,
                memory_type="identity",
                content=f"Idioma preferido: {lang}",
                confidence=CONF_NAME,
                dry_run=dry_run,
            ):
                counts["inserted"] += 1

        # Interests → interest
        for item in data.get("interests") or []:
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
        for item in data.get("products_discussed") or []:
            if item and str(item).strip():
                if _insert_memory(
                    db, creator_uuid=creator_uuid, lead_uuid=lead_uuid,
                    memory_type="interest",
                    content=f"Producto de interés: {item}",
                    confidence=CONF_PRODUCT,
                    dry_run=dry_run,
                ):
                    counts["inserted"] += 1

        # Objections raised → objection (requires why + how_to_apply)
        for item in data.get("objections_raised") or []:
            if item and str(item).strip():
                if _insert_memory(
                    db, creator_uuid=creator_uuid, lead_uuid=lead_uuid,
                    memory_type="objection",
                    content=str(item),
                    why="Objeción registrada en FollowerMemory JSON (migrada de legacy)",
                    how_to_apply="(pending re-extraction) — manejar antes de continuar la venta",
                    confidence=CONF_OBJECTION,
                    dry_run=dry_run,
                ):
                    counts["inserted"] += 1

        # Status → relationship_state (requires why + how_to_apply)
        status = data.get("status") or ""
        if status.strip() and status != "new":
            if _insert_memory(
                db, creator_uuid=creator_uuid, lead_uuid=lead_uuid,
                memory_type="relationship_state",
                content=f"Estado de la relación: {status}",
                why="Estado registrado en FollowerMemory JSON",
                how_to_apply="(pending re-extraction) — adaptar tono según estado",
                confidence=CONF_STATUS,
                dry_run=dry_run,
            ):
                counts["inserted"] += 1

        # Purchase intent score → intent_signal
        score = data.get("purchase_intent_score") or 0.0
        if float(score) >= 0.3:
            if _insert_memory(
                db, creator_uuid=creator_uuid, lead_uuid=lead_uuid,
                memory_type="intent_signal",
                content=f"Puntuación de intención de compra: {float(score):.1f}",
                confidence=CONF_INTENT,
                dry_run=dry_run,
            ):
                counts["inserted"] += 1

    except Exception as exc:
        logger.error("Error processing %s: %s", json_path, exc)
        counts["errors"] += 1

    return counts


def run(
    *,
    dry_run: bool,
    creator_slug: str | None,
    base_path: Path,
) -> None:
    if not base_path.exists():
        logger.warning("Base path does not exist: %s — nothing to migrate", base_path)
        return

    if creator_slug:
        creator_dirs = [base_path / creator_slug]
        if not creator_dirs[0].exists():
            logger.warning("Creator directory not found: %s", creator_dirs[0])
            return
    else:
        creator_dirs = [d for d in base_path.iterdir() if d.is_dir() and not d.name.startswith(".")]

    json_files: list[Path] = []
    for cdir in sorted(creator_dirs):
        json_files.extend(cdir.glob("*.json"))

    logger.info(
        "JSON files found: %d (base_path=%s creator=%s dry_run=%s)",
        len(json_files), base_path, creator_slug or "ALL", dry_run,
    )

    if not json_files:
        logger.info("Nothing to migrate.")
        return

    from api.database import SessionLocal

    db = SessionLocal()
    try:
        total_inserted = 0
        total_skipped = 0
        total_errors = 0
        total_files_ok = 0
        total_files_skipped = 0

        for i, json_path in enumerate(json_files):
            counts = _process_file(db, json_path, dry_run=dry_run)

            if counts["skipped"] > 0 and counts["inserted"] == 0 and counts["errors"] == 0:
                total_files_skipped += 1
            else:
                total_files_ok += 1

            total_inserted += counts["inserted"]
            total_skipped += counts["skipped"]
            total_errors += counts["errors"]

            if not dry_run and (i + 1) % 50 == 0:
                db.commit()

            if (i + 1) % 100 == 0:
                logger.info(
                    "Progress: %d/%d files | inserted=%d skipped=%d errors=%d",
                    i + 1, len(json_files), total_inserted, total_skipped, total_errors,
                )

        if not dry_run:
            db.commit()

        logger.info(
            "DONE — files_scanned=%d files_ok=%d files_skipped=%d "
            "memories_inserted=%d skipped_entries=%d errors=%d dry_run=%s",
            len(json_files), total_files_ok, total_files_skipped,
            total_inserted, total_skipped, total_errors, dry_run,
        )

    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate FollowerMemory JSON files → arc2_lead_memories (ARC2 A2.3)"
    )
    parser.add_argument("--dry-run", action="store_true", help="Report only, no writes")
    parser.add_argument("--creator-slug", type=str, default=None, metavar="SLUG",
                        help="Process only this creator's directory")
    parser.add_argument("--base-path", type=str, default="data/followers",
                        help="Root directory containing creator subdirs with JSON files")
    args = parser.parse_args()

    if args.dry_run:
        logger.info("DRY RUN — no writes will be made")

    run(
        dry_run=args.dry_run,
        creator_slug=args.creator_slug,
        base_path=Path(args.base_path),
    )


if __name__ == "__main__":
    main()
