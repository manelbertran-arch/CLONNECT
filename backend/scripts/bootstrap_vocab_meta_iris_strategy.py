"""Bootstrap vocab_meta entries for Iris required by dm_strategy.py.

Idempotent 1-time migration that seeds the `personality_docs[doc_type='vocab_meta']`
JSON blob for Iris with the linguistic data that was hardcoded in strategy.py
before the forensic/dm-strategy-20260423 refactor.

Motivation: strategy.py now sources apelativos, openers_to_avoid,
anti_bugs_verbales and help_signals from `personality_docs.content`
(via services.calibration_loader._load_creator_vocab). Without this bootstrap
Iris would run with vocab empty → neutral fallback hints → measurable
regression in Iris CCEE arm B of E1.

Run:
    railway run python3 scripts/bootstrap_vocab_meta_iris_strategy.py
    railway run python3 scripts/bootstrap_vocab_meta_iris_strategy.py --dry-run
    python3 scripts/bootstrap_vocab_meta_iris_strategy.py --creator iris_bertran

Safe to re-run: merges incoming keys into the existing vocab_meta JSON
without overwriting arbitrary user-curated fields (blacklist_words,
approved_emojis, etc.). Only the four linguistic-data keys owned by this
script are inserted when absent. See docs/forensic/dm_strategy/03_bugs.md §6.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("bootstrap_vocab_meta_iris_strategy")

# These four lists are the exact values previously hardcoded in
# core/dm/strategy.py lines 57-61, 86 and 89-90 (commits 81467a92e,
# f561819c4). Re-seeding them preserves current behavior for Iris while
# enabling per-creator mining for all other creators.
IRIS_SEED: Dict[str, List[str] | List[Dict[str, str]]] = {
    "apelativos": ["nena", "tia", "flor", "cuca", "reina"],
    "anti_bugs_verbales": ["flower"],
    "openers_to_avoid": [
        "¿Que te llamó la atención?",
        "Que t'ha cridat l'atenció?",
    ],
    "help_signals": [
        "ayuda", "problema", "no funciona", "no puedo", "error",
        "cómo", "como hago", "necesito", "urgente", "no me deja",
        "no entiendo", "explícame", "explicame", "qué hago", "que hago",
    ],
}


def _merge(existing: Dict, seed: Dict) -> tuple[Dict, Dict[str, str]]:
    """Merge seed into existing vocab. Returns (merged, actions_taken)."""
    merged = dict(existing) if existing else {}
    actions: Dict[str, str] = {}
    for key, seed_value in seed.items():
        cur = merged.get(key)
        if cur is None:
            merged[key] = seed_value
            actions[key] = f"inserted ({len(seed_value)} entries)"
        elif isinstance(cur, list):
            # Union without duplicates, preserve seed order for new items
            existing_set = {json.dumps(x, ensure_ascii=False, sort_keys=True) for x in cur}
            additions = [x for x in seed_value
                         if json.dumps(x, ensure_ascii=False, sort_keys=True) not in existing_set]
            if additions:
                merged[key] = list(cur) + additions
                actions[key] = f"appended {len(additions)} new entries (kept {len(cur)} existing)"
            else:
                actions[key] = f"already covered ({len(cur)} entries — no-op)"
        else:
            actions[key] = f"SKIP: existing value is non-list ({type(cur).__name__})"
    return merged, actions


def bootstrap_creator(creator_id: str, dry_run: bool = False) -> int:
    """Upsert vocab_meta for the given creator. Returns exit code."""
    try:
        from api.database import SessionLocal
        from sqlalchemy import text
    except Exception as exc:  # pragma: no cover
        logger.error("Cannot import api.database.SessionLocal: %s", exc)
        return 2

    session = SessionLocal()
    try:
        row = session.execute(
            text(
                """
                SELECT pd.id, pd.content, c.id AS creator_uuid
                FROM personality_docs pd
                JOIN creators c ON c.id::text = pd.creator_id
                WHERE (c.name = :cid OR pd.creator_id = :cid)
                  AND pd.doc_type = 'vocab_meta'
                LIMIT 1
                """
            ),
            {"cid": creator_id},
        ).fetchone()

        if row is None:
            creator_row = session.execute(
                text("SELECT id FROM creators WHERE name = :cid"),
                {"cid": creator_id},
            ).fetchone()
            if creator_row is None:
                logger.error("Creator %r not found in creators table", creator_id)
                return 3
            creator_uuid = str(creator_row.id)
            existing: Dict = {}
            merged, actions = _merge(existing, IRIS_SEED)
            payload = json.dumps(merged, ensure_ascii=False, sort_keys=True)
            logger.info("No existing vocab_meta row for %s; will INSERT.", creator_id)
            for k, v in actions.items():
                logger.info("  %s: %s", k, v)
            if dry_run:
                logger.info("[DRY RUN] would insert vocab_meta for creator %s (%s)", creator_id, creator_uuid)
                return 0
            session.execute(
                text(
                    """
                    INSERT INTO personality_docs (id, creator_id, doc_type, content, created_at, updated_at)
                    VALUES (gen_random_uuid(), :cuuid, 'vocab_meta', :content, NOW(), NOW())
                    """
                ),
                {"cuuid": creator_uuid, "content": payload},
            )
            session.commit()
            logger.info("Inserted vocab_meta for %s.", creator_id)
            return 0

        existing = json.loads(row.content) if row.content else {}
        merged, actions = _merge(existing, IRIS_SEED)
        logger.info("Existing vocab_meta found for %s; merging.", creator_id)
        for k, v in actions.items():
            logger.info("  %s: %s", k, v)
        if merged == existing:
            logger.info("No changes required (fully idempotent, already seeded).")
            return 0
        if dry_run:
            logger.info("[DRY RUN] would update vocab_meta for %s with merged keys: %s",
                        creator_id, sorted(set(merged.keys()) - set(existing.keys()) | {k for k, v in actions.items() if 'append' in v or 'inserted' in v}))
            return 0
        payload = json.dumps(merged, ensure_ascii=False, sort_keys=True)
        session.execute(
            text(
                """
                UPDATE personality_docs
                SET content = :content, updated_at = NOW()
                WHERE id = :pid
                """
            ),
            {"content": payload, "pid": row.id},
        )
        session.commit()
        logger.info("Updated vocab_meta for %s.", creator_id)
        return 0

    except Exception as exc:
        session.rollback()
        logger.exception("Bootstrap failed: %s", exc)
        return 1
    finally:
        session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--creator", default="iris_bertran", help="Creator slug (default: iris_bertran)")
    parser.add_argument("--dry-run", action="store_true", help="Log planned changes, do not commit")
    args = parser.parse_args()
    return bootstrap_creator(args.creator, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
