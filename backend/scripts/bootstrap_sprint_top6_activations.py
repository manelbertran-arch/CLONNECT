"""Consolidated bootstrap for Sprint top-6 activations (2026-04-23).

Idempotent, UPSERT-based. Seeds or health-checks the data-plane prerequisites
for activating the six sprint systems on a given creator:

  1. Question Hints       → flag only (no bootstrap)
  2. Response Fixes       → flag only (no bootstrap)
  3. Query Expansion      → flag only (no bootstrap)
  4. Few-Shot Injection   → health-check: calibrations/<creator>_unified.json present + non-empty
  5. Commitment Tracker   → UPSERT vocab_meta.{commitment_patterns, temporal_patterns} from
                             cold-start Spanish fallback (Path A per state-of-the-art)
  6. DNA Engine create    → health-check: relationship_dna table reachable

Run:
    railway run python3 backend/scripts/bootstrap_sprint_top6_activations.py --dry-run
    railway run python3 backend/scripts/bootstrap_sprint_top6_activations.py --creator iris_bertran

Exit codes:
    0 OK
    2 import error
    3 creator not found
    4 calibration pack missing or empty (Few-Shot health-check failed)
    5 DB write failed mid-flight
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("bootstrap_sprint_top6")


# ── System 5: Commitment Tracker seeds (copied from the cold-start fallback) ──
_COMMITMENT_PATTERNS_SEED: List[Dict[str, str]] = [
    {"pattern": r"te\s+(envío|mando|paso|comparto)\b", "type": "delivery"},
    {"pattern": r"(mañana|esta semana|luego|después)\s+te\s+(envío|mando|paso)", "type": "delivery"},
    {"pattern": r"te\s+(lo|la|los|las)\s+(envío|mando|paso)\b", "type": "delivery"},
    {"pattern": r"te\s+(confirmo|aviso|digo|cuento)\b", "type": "info_request"},
    {"pattern": r"(voy\s+a|vamos\s+a)\s+(verificar|consultar|revisar|checar)", "type": "info_request"},
    {"pattern": r"(quedamos|nos\s+vemos|te\s+espero)\s+(el|la|a\s+las)", "type": "meeting"},
    {"pattern": r"(agend|reserv)(o|amos|é)\s+(una|la|tu)", "type": "meeting"},
    {"pattern": r"te\s+(escribo|contacto|llamo)\s+(mañana|luego|pronto)", "type": "follow_up"},
    {"pattern": r"(hago|haré)\s+(seguimiento|follow[\s-]?up)", "type": "follow_up"},
    {"pattern": r"te\s+(prometo|aseguro|garantizo)\b", "type": "promise"},
    {"pattern": r"sin\s+falta\s+te\b", "type": "promise"},
]

_TEMPORAL_PATTERNS_SEED: List[Dict[str, object]] = [
    {"pattern": r"\bmañana\b", "days": 1},
    {"pattern": r"\bpasado\s+mañana\b", "days": 2},
    {"pattern": r"\besta\s+semana\b", "days": 5},
    {"pattern": r"\bla\s+semana\s+que\s+viene\b", "days": 7},
    {"pattern": r"\bhoy\b", "days": 0},
    {"pattern": r"\bluego\b", "days": 0},
    {"pattern": r"\bpronto\b", "days": 2},
]


# ── System 4: Few-Shot — health-check helper ─────────────────────────────────

def _check_few_shot_calibration(creator_slug: str) -> Tuple[bool, Dict[str, object]]:
    """Return (ok, stats). Checks presence of calibrations/<creator>_unified.json or
    <creator>.json and reports n_examples."""
    try:
        from services.calibration_loader import CALIBRATIONS_DIR
    except ImportError:
        # Fallback path relative to ROOT
        CALIBRATIONS_DIR = str(ROOT / "calibrations")

    for filename in (f"{creator_slug}_unified.json", f"{creator_slug}.json"):
        path = os.path.join(CALIBRATIONS_DIR, filename)
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                examples = data.get("few_shot_examples", [])
                return True, {
                    "path": path,
                    "n_examples": len(examples),
                    "ok": len(examples) > 0,
                }
            except Exception as exc:
                return False, {"path": path, "error": str(exc)}
    return False, {"error": f"No calibration file found for {creator_slug!r}"}


# ── System 5: Commitment Tracker — UPSERT ────────────────────────────────────

def _resolve_creator_uuid(session, creator_slug: str) -> str:
    from sqlalchemy import text as sql
    row = session.execute(
        sql("SELECT id FROM creators WHERE name = :slug LIMIT 1"),
        {"slug": creator_slug},
    ).fetchone()
    if not row:
        raise LookupError(f"Creator {creator_slug!r} not found in creators table")
    return str(row.id)


def _upsert_commitment_patterns(session, creator_uuid: str, *, dry_run: bool) -> Dict[str, object]:
    from sqlalchemy import text as sql

    existing = session.execute(
        sql(
            """
            SELECT content FROM personality_docs
            WHERE creator_id = :cid AND doc_type = 'vocab_meta'
            LIMIT 1
            """
        ),
        {"cid": creator_uuid},
    ).fetchone()

    # Merge into existing vocab_meta JSON (preserve blacklist_words, approved_terms, etc.)
    if existing and existing.content:
        try:
            vocab = json.loads(existing.content)
        except (ValueError, TypeError):
            logger.warning("Existing vocab_meta.content is not valid JSON; starting from empty dict")
            vocab = {}
    else:
        vocab = {}

    pre_existing_cp = vocab.get("commitment_patterns", [])
    pre_existing_tp = vocab.get("temporal_patterns", [])

    # Path A per state-of-the-art: commit_patterns + temporal_patterns from seed.
    # Explicit override (no merge) — the creator can later override via manual DB edit.
    vocab["commitment_patterns"] = _COMMITMENT_PATTERNS_SEED
    vocab["temporal_patterns"] = _TEMPORAL_PATTERNS_SEED

    new_content = json.dumps(vocab, ensure_ascii=False, sort_keys=True)
    already_identical = (
        len(pre_existing_cp) == len(_COMMITMENT_PATTERNS_SEED)
        and len(pre_existing_tp) == len(_TEMPORAL_PATTERNS_SEED)
    )

    stats = {
        "pre_existing_commitment_patterns": len(pre_existing_cp),
        "pre_existing_temporal_patterns": len(pre_existing_tp),
        "new_commitment_patterns": len(_COMMITMENT_PATTERNS_SEED),
        "new_temporal_patterns": len(_TEMPORAL_PATTERNS_SEED),
        "already_identical": already_identical,
        "dry_run": dry_run,
    }

    if dry_run:
        return stats

    if existing:
        session.execute(
            sql(
                """
                UPDATE personality_docs
                SET content = :content, updated_at = NOW()
                WHERE creator_id = :cid AND doc_type = 'vocab_meta'
                """
            ),
            {"content": new_content, "cid": creator_uuid},
        )
    else:
        session.execute(
            sql(
                """
                INSERT INTO personality_docs (id, creator_id, doc_type, content, created_at, updated_at)
                VALUES (gen_random_uuid(), :cid, 'vocab_meta', :content, NOW(), NOW())
                ON CONFLICT (creator_id, doc_type)
                DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()
                """
            ),
            {"cid": creator_uuid, "content": new_content},
        )
    session.commit()
    return stats


# ── System 6: DNA Engine — health-check helper ───────────────────────────────

def _check_dna_table(session) -> Tuple[bool, Dict[str, object]]:
    from sqlalchemy import text as sql
    try:
        result = session.execute(sql("SELECT COUNT(*) AS n FROM relationship_dna")).fetchone()
        return True, {"reachable": True, "row_count": int(result.n) if result else 0}
    except Exception as exc:
        return False, {"reachable": False, "error": str(exc)}


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("--creator", default="iris_bertran", help="Creator slug (default: iris_bertran)")
    ap.add_argument("--dry-run", action="store_true", help="Print stats without writing to DB")
    ap.add_argument("--skip-few-shot-check", action="store_true",
                    help="Skip Few-Shot calibration health-check (for environments without calibrations/)")
    args = ap.parse_args()

    # System 1-3 (Q-Hints, Response-Fixes, Query-Expansion): nothing to do.
    logger.info("=== Sprint top-6 bootstrap for creator %s (dry_run=%s) ===", args.creator, args.dry_run)
    logger.info("Systems 1-3 (Question Hints, Response Fixes, Query Expansion): flags only, no bootstrap.")

    # System 4: Few-Shot
    if not args.skip_few_shot_check:
        ok, fs_stats = _check_few_shot_calibration(args.creator)
        logger.info("Few-Shot calibration check: %s", fs_stats)
        if not ok or fs_stats.get("n_examples", 0) == 0:
            logger.error("Few-Shot calibration missing or empty; deploy calibration pack first.")
            return 4

    # Systems 5-6 require DB.
    try:
        from api.database import SessionLocal
    except ImportError as exc:  # pragma: no cover
        logger.error("Cannot import api.database.SessionLocal: %s", exc)
        return 2

    session = SessionLocal()
    try:
        try:
            creator_uuid = _resolve_creator_uuid(session, args.creator)
        except LookupError as exc:
            logger.error(str(exc))
            return 3

        logger.info("Creator %s resolved to UUID %s", args.creator, creator_uuid)

        # System 5: Commitment Tracker
        try:
            ct_stats = _upsert_commitment_patterns(session, creator_uuid, dry_run=args.dry_run)
            logger.info("Commitment Tracker vocab_meta upsert stats: %s", ct_stats)
        except Exception:
            session.rollback()
            logger.exception("Commitment Tracker upsert failed")
            return 5

        # System 6: DNA Engine — health-check only (rows are created on-demand)
        ok, dna_stats = _check_dna_table(session)
        logger.info("DNA table health: %s", dna_stats)
        if not ok:
            logger.error("relationship_dna table unreachable — DNA auto-create cannot proceed safely.")
            return 5

        logger.info("=== Bootstrap completed OK for %s ===", args.creator)
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
