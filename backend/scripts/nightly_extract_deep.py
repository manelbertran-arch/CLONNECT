"""Nightly deep memory extraction job.

Iterates over active leads (last 48h of messages) and runs MemoryExtractor.extract_deep()
to populate memory types that regex sync cannot detect: objection, interest, relationship_state.

Usage:
    python3 scripts/nightly_extract_deep.py [--dry-run] [--batch-size N] [--creator-id UUID] [--max-leads N]

Cron: run daily at low-traffic hour (e.g. 03:00 UTC).
Scheduler: registered in api/startup/handlers.py as "nightly_extract_deep" (ENABLE_NIGHTLY_EXTRACT_DEEP=false default).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from collections import defaultdict
from typing import Any, Callable, Coroutine, Optional
from uuid import UUID

# Ensure project root is importable when run as a standalone script.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("nightly_extract_deep")

# ── Constants ────────────────────────────────────────────────────────────────

LAST_WRITER = "extract_deep_nightly"
ACTIVE_WINDOW_HOURS = 48
MAX_CONVERSATION_TURNS = 20
LEAD_SLEEP_SECONDS = 1.0
OPENROUTER_MAX_TOKENS = 1024
OPENROUTER_TEMPERATURE = 0.1


# ── LLM caller factory ───────────────────────────────────────────────────────

async def _build_llm_caller() -> Callable[[str], Coroutine[Any, Any, str]]:
    """Return an async str→str LLM caller using OpenRouter."""
    from core.providers.openrouter_provider import call_openrouter

    async def _caller(prompt: str) -> str:
        result = await call_openrouter(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=OPENROUTER_MAX_TOKENS,
            temperature=OPENROUTER_TEMPERATURE,
        )
        if result and result.get("content"):
            return result["content"]
        return ""

    return _caller


# ── DB helpers ───────────────────────────────────────────────────────────────

def _fetch_active_lead_pairs(
    session: Any,
    creator_id_filter: Optional[str],
    max_leads: int,
) -> list[tuple[str, str]]:
    """Return (creator_id_str, lead_id_str) pairs active in last ACTIVE_WINDOW_HOURS."""
    from sqlalchemy import text

    params: dict[str, Any] = {"hours": ACTIVE_WINDOW_HOURS, "max_leads": max_leads}
    creator_clause = ""
    if creator_id_filter:
        creator_clause = "AND l.creator_id = :creator_id"
        params["creator_id"] = creator_id_filter

    rows = session.execute(
        text(f"""
            SELECT DISTINCT l.creator_id::text, m.lead_id::text
            FROM messages m
            JOIN leads l ON l.id = m.lead_id
            WHERE m.created_at > NOW() - (INTERVAL '1 hour' * :hours)
            {creator_clause}
            ORDER BY l.creator_id, m.lead_id
            LIMIT :max_leads
        """),
        params,
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def _fetch_recent_conversation(session: Any, lead_id: str) -> list[dict]:
    """Load last N messages for a lead in chronological order."""
    from sqlalchemy import text

    rows = session.execute(
        text("""
            SELECT role, content
            FROM messages
            WHERE lead_id = :lead_id
              AND content IS NOT NULL AND content != ''
            ORDER BY created_at DESC
            LIMIT :limit
        """),
        {"lead_id": lead_id, "limit": MAX_CONVERSATION_TURNS},
    ).fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def _fetch_existing_memories(session: Any, creator_id: str, lead_id: str) -> list[Any]:
    """Return ExtractedMemory objects for already-known facts."""
    from sqlalchemy import text
    from services.memory_extractor import ExtractedMemory

    rows = session.execute(
        text("""
            SELECT memory_type, content, why, how_to_apply, confidence
            FROM arc2_lead_memories
            WHERE creator_id = :cid AND lead_id = :lid AND deleted_at IS NULL
            ORDER BY created_at
            LIMIT 20
        """),
        {"cid": creator_id, "lid": lead_id},
    ).fetchall()

    result = []
    for r in rows:
        try:
            result.append(ExtractedMemory(
                type=r[0],
                fact=(r[1] or "")[:100],
                why=r[2] or "",
                how_to_apply=r[3] or "",
                confidence=float(r[4]) if r[4] is not None else 0.7,
            ))
        except Exception:
            continue
    return result


def _detect_language(conversation: list[dict]) -> str:
    """Heuristic language detection from first lead messages."""
    catalan_markers = {"tinc", "soc", "gràcies", "però", "també", "molt", "visc", "dic"}
    english_markers = {"i'm", "i am", "my name", "how much", "what is", "i want", "tell me"}
    sample = " ".join(
        m["content"].lower()
        for m in conversation[:6]
        if m.get("role") == "user" and m.get("content")
    )
    if any(marker in sample for marker in catalan_markers):
        return "ca"
    if any(marker in sample for marker in english_markers):
        return "en"
    return "es"


# ── Core job ─────────────────────────────────────────────────────────────────

async def run_nightly(
    dry_run: bool = False,
    batch_size: int = 50,
    creator_id_filter: Optional[str] = None,
    max_leads: int = 1000,
) -> dict[str, Any]:
    """Main nightly job. Returns stats dict.

    Fail-silent per lead: one LLM error never blocks the rest.
    Idempotent: LeadMemoryService.upsert uses ON CONFLICT dedup.
    """
    from api.database import SessionLocal
    from services.memory_extractor import MemoryExtractor
    from services.lead_memory_service import LeadMemoryService

    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL not configured — cannot start nightly_extract_deep")

    llm_caller = None if dry_run else await _build_llm_caller()
    extractor = MemoryExtractor(llm_caller=llm_caller)

    session = SessionLocal()
    try:
        lead_pairs = _fetch_active_lead_pairs(session, creator_id_filter, max_leads)
    finally:
        session.close()

    total = len(lead_pairs)
    logger.info("[nightly_extract_deep] candidates=%d dry_run=%s max_leads=%d", total, dry_run, max_leads)

    if dry_run:
        logger.info(
            "[nightly_extract_deep] DRY-RUN complete — %d leads would be processed (no LLM calls made)",
            total,
        )
        return {"dry_run": True, "candidates": total}

    stats: dict[str, Any] = {
        "leads_processed": 0,
        "leads_skipped": 0,
        "leads_errored": 0,
        "memories_created": defaultdict(int),
        "elapsed_seconds": 0.0,
    }
    t_start = time.monotonic()

    for i, (c_id, l_id) in enumerate(lead_pairs):
        try:
            session = SessionLocal()
            try:
                conversation = _fetch_recent_conversation(session, l_id)
                if not conversation:
                    stats["leads_skipped"] += 1
                    continue

                already_known = _fetch_existing_memories(session, c_id, l_id)
                language = _detect_language(conversation)

                memories = await extractor.extract_deep(
                    conversation=conversation,
                    lead_id=UUID(l_id),
                    language=language,
                    already_known=already_known,
                )

                if memories:
                    svc = LeadMemoryService(session)
                    for mem in memories:
                        svc.upsert(
                            creator_id=UUID(c_id),
                            lead_id=UUID(l_id),
                            memory_type=mem.type,
                            content=mem.fact,
                            why=mem.why,
                            how_to_apply=mem.how_to_apply,
                            confidence=mem.confidence,
                            last_writer=LAST_WRITER,
                        )
                        stats["memories_created"][mem.type] += 1

                stats["leads_processed"] += 1

            finally:
                session.close()

        except Exception as exc:
            stats["leads_errored"] += 1
            logger.warning(
                "[nightly_extract_deep] lead=%s error=%s — skipping",
                l_id[:8] if l_id else "?", exc,
            )

        if (i + 1) % 50 == 0:
            logger.info(
                "[nightly_extract_deep] progress %d/%d — memories so far: %s",
                i + 1, total, dict(stats["memories_created"]),
            )

        await asyncio.sleep(LEAD_SLEEP_SECONDS)

    stats["elapsed_seconds"] = round(time.monotonic() - t_start, 1)
    stats["memories_created"] = dict(stats["memories_created"])

    logger.info(
        "[nightly_extract_deep] DONE — processed=%d skipped=%d errored=%d "
        "memories=%s elapsed=%.1fs",
        stats["leads_processed"],
        stats["leads_skipped"],
        stats["leads_errored"],
        stats["memories_created"],
        stats["elapsed_seconds"],
    )
    return stats


# ── CLI entry point ───────────────────────────────────────────────────────────

def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Nightly deep memory extraction job for Clonnect ARC2.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true", help="Count candidates without calling LLM")
    parser.add_argument("--batch-size", type=int, default=50, metavar="N", help="(informational) leads per batch (default: 50)")
    parser.add_argument("--creator-id", type=str, default=None, metavar="UUID", help="Limit to one creator UUID")
    parser.add_argument("--max-leads", type=int, default=1000, metavar="N", help="Safety cap (default: 1000)")
    return parser


def main() -> None:
    args = _build_argparser().parse_args()
    asyncio.run(run_nightly(
        dry_run=args.dry_run,
        batch_size=args.batch_size,
        creator_id_filter=args.creator_id,
        max_leads=args.max_leads,
    ))


if __name__ == "__main__":
    main()
