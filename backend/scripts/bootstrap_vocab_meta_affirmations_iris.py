"""Bootstrap personality_docs.vocab_meta.content.affirmations via data-derived mining.

Pre-requisite for activating ENABLE_QUESTION_CONTEXT=true in Railway (unblocks the
arm B of the CCEE A/B for PR #82 / bot_question_analyzer refactor). Without this
bootstrap, is_short_affirmation(msg, creator_id) falls back to the universal
emoji-only detector, which makes the A/B measurement uninformative.

Algorithm: zero-hardcoding linguistic mining per spec
`docs/forensic/bot_question_analyzer/07_vocab_mining_dependency.md §2.2`.
Data-derived threshold (percentile 75 with floor=3), top-K=50.

Run:
    railway run python3 scripts/bootstrap_vocab_meta_affirmations_iris.py --dry-run
    railway run python3 scripts/bootstrap_vocab_meta_affirmations_iris.py --creator iris_bertran

Idempotent: replaces only the `affirmations` key inside the vocab_meta JSON
(preserves blacklist_words, approved_emojis, etc.). Re-running produces the
same result unless the underlying corpus changes.

Exit codes:
    0 OK (mined, upserted, or dry-run)
    2 import error (cannot reach api.database)
    3 creator not found in DB
    4 empty mining result (no candidate rows — CEO decides next step)
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("bootstrap_vocab_meta_affirmations_iris")

# Mining parameters — kept in sync with core/bot_question_analyzer (see spec 07 §2.2).
_PUNCT_CHARS = "!.,?¡¿"
_PUNCT_ONLY_RE = re.compile(r"^[\s!.,?¡¿]+$")
MAX_LEN = 15
MIN_FREQ_PERCENTILE = 75.0
MIN_FREQ_FLOOR = 3
TOP_K = 50


def _normalize(msg: str) -> str:
    return msg.lower().strip()


def _is_candidate(msg: str) -> bool:
    if not msg:
        return False
    m = _normalize(msg)
    if not m or len(m) > MAX_LEN:
        return False
    if _PUNCT_ONLY_RE.match(m):
        return False
    return True


def _extract_tokens(msg: str) -> list[str]:
    m = _normalize(msg)
    yielded: list[str] = []
    if len(m) <= MAX_LEN:
        yielded.append(m)
    words = m.split()
    if 1 < len(words) <= 3:
        for w in words:
            clean = w.strip(_PUNCT_CHARS)
            if clean and len(clean) <= 8:
                yielded.append(clean)
    return yielded


def _resolve_creator_uuid(session, creator_slug: str) -> str:
    """Resolve creator slug → UUID. Raises LookupError if not found."""
    from sqlalchemy import text as sql

    row = session.execute(
        sql("SELECT id FROM creators WHERE name = :slug LIMIT 1"),
        {"slug": creator_slug},
    ).fetchone()
    if not row:
        raise LookupError(f"Creator {creator_slug!r} not found in creators table")
    return str(row.id)


def mine_affirmations(session, creator_slug: str, creator_uuid: str) -> tuple[list[str], dict]:
    """Query (bot_msg, next_lead_msg) pairs and derive affirmation tokens."""
    from sqlalchemy import text as sql

    query = sql(
        """
        WITH ordered AS (
            SELECT m.id, m.lead_id, m.role, m.content, m.created_at,
                   LAG(m.role) OVER (PARTITION BY m.lead_id ORDER BY m.created_at) AS prev_role,
                   LAG(m.content) OVER (PARTITION BY m.lead_id ORDER BY m.created_at) AS prev_content
            FROM messages m
            JOIN leads l ON l.id = m.lead_id
            WHERE l.creator_id = :cid
        )
        SELECT content
        FROM ordered
        WHERE role = 'user'
          AND prev_role = 'assistant'
          AND prev_content LIKE '%?%'
        """
    )
    rows = session.execute(query, {"cid": creator_uuid}).fetchall()

    counter: Counter = Counter()
    total_candidates = 0
    for r in rows:
        if _is_candidate(r.content):
            total_candidates += 1
            for token in _extract_tokens(r.content):
                counter[token] += 1

    if not counter:
        return [], {
            "total_candidates": 0,
            "unique_tokens": 0,
            "threshold_freq": 0,
            "top_k_after_sanity": 0,
            "blacklist_excluded": 0,
        }

    freqs = sorted(counter.values())
    idx = int(len(freqs) * MIN_FREQ_PERCENTILE / 100)
    threshold = max(
        freqs[idx] if idx < len(freqs) else MIN_FREQ_FLOOR,
        MIN_FREQ_FLOOR,
    )

    ranked = sorted(
        [(tok, cnt) for tok, cnt in counter.items() if cnt >= threshold],
        key=lambda x: -x[1],
    )[:TOP_K]

    existing_vocab = session.execute(
        sql(
            """
            SELECT pd.content
            FROM personality_docs pd
            JOIN creators c ON c.id::text = pd.creator_id
            WHERE c.name = :slug AND pd.doc_type = 'vocab_meta'
            LIMIT 1
            """
        ),
        {"slug": creator_slug},
    ).fetchone()
    blacklist: set[str] = set()
    if existing_vocab and existing_vocab.content:
        try:
            parsed = json.loads(existing_vocab.content)
            blacklist = {w.lower() for w in parsed.get("blacklist_words", [])}
        except (ValueError, TypeError):
            logger.warning("Could not parse existing vocab_meta.content as JSON; ignoring blacklist filter")

    final = [tok for tok, _ in ranked if tok not in blacklist]
    excluded = len(ranked) - len(final)

    stats = {
        "total_candidates": total_candidates,
        "unique_tokens": len(counter),
        "threshold_freq": threshold,
        "top_k_after_sanity": len(final),
        "blacklist_excluded": excluded,
    }
    return final, stats


def upsert_affirmations(session, creator_uuid: str, affirmations: list[str]) -> None:
    """Idempotent UPSERT of the `affirmations` key in personality_docs.vocab_meta."""
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

    if existing:
        try:
            vocab = json.loads(existing.content) if existing.content else {}
        except (ValueError, TypeError):
            logger.warning("Existing vocab_meta.content is not valid JSON; starting from empty dict")
            vocab = {}
        vocab["affirmations"] = affirmations
        new_content = json.dumps(vocab, ensure_ascii=False, sort_keys=True)
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
        new_vocab = {"affirmations": affirmations}
        session.execute(
            sql(
                """
                INSERT INTO personality_docs (id, creator_id, doc_type, content, created_at, updated_at)
                VALUES (gen_random_uuid(), :cid, 'vocab_meta', :content, NOW(), NOW())
                ON CONFLICT (creator_id, doc_type)
                DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()
                """
            ),
            {
                "cid": creator_uuid,
                "content": json.dumps(new_vocab, ensure_ascii=False, sort_keys=True),
            },
        )
    session.commit()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    ap.add_argument("--creator", default="iris_bertran", help="Creator slug (default: iris_bertran)")
    ap.add_argument("--dry-run", action="store_true", help="Print stats without writing to DB")
    args = ap.parse_args()

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

        try:
            affirmations, stats = mine_affirmations(session, args.creator, creator_uuid)
        except Exception:
            session.rollback()
            raise

        logger.info("=== Mining stats for %s ===", args.creator)
        for k, v in stats.items():
            logger.info("  %s: %s", k, v)
        logger.info("=== Top-%d affirmations ===", len(affirmations))
        for i, tok in enumerate(affirmations, 1):
            logger.info("  %3d. %r", i, tok)

        if not affirmations:
            logger.warning(
                "No affirmations mined (corpus insufficient or all below threshold). "
                "The `affirmations` key will NOT be written; is_short_affirmation falls "
                "back to the universal emoji-only detector for %s.",
                args.creator,
            )
            return 4

        if args.dry_run:
            logger.info("[DRY-RUN] No DB write.")
            return 0

        try:
            upsert_affirmations(session, creator_uuid, affirmations)
        except Exception:
            session.rollback()
            raise
        logger.info("Upserted %d affirmations for %s", len(affirmations), args.creator)
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
