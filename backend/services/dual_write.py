"""
ARC2 A2.4 — Dual-Write Bridge.

Called by 3 legacy write points when ENABLE_DUAL_WRITE_LEAD_MEMORIES=true:
  - services/memory_extraction.py  (MemoryExtractor._do_extract)
  - services/memory_service.py     (MemoryStore.save)
  - services/memory_service.py     (ConversationMemoryService.save)

Design rules:
  - Fail-silent: every exception is caught, logged, NOT re-raised.
  - Flag OFF → zero overhead (early return before any work).
  - No LLM calls — classification is pure mapping (dict lookup).
  - ID resolution via asyncio.to_thread (non-blocking).
  - upsert ON CONFLICT handles dedup naturally.
"""

import asyncio
import logging
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# COUNTERS (in-process, for tests and metrics)
# ─────────────────────────────────────────────────────────────────────────────

_failure_counters: Dict[str, int] = {}


def get_failure_count(source: str) -> int:
    """Return total dual-write failures for a given source. Used in tests."""
    return _failure_counters.get(source, 0)


def reset_failure_counters() -> None:
    """Reset all counters. Call between tests."""
    _failure_counters.clear()


def _increment_failure(source: str) -> None:
    _failure_counters[source] = _failure_counters.get(source, 0) + 1
    logger.warning(
        "[DualWrite] Write failure for source=%s (total=%d)",
        source,
        _failure_counters[source],
    )


# ─────────────────────────────────────────────────────────────────────────────
# DATA MODEL
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DualWriteEntry:
    """One memory to upsert into arc2_lead_memories."""

    memory_type: str
    content: str
    why: Optional[str] = None
    how_to_apply: Optional[str] = None
    confidence: float = 0.7


# ─────────────────────────────────────────────────────────────────────────────
# CLASSIFICATION TABLES (no LLM, no regex — pure mapping)
# ─────────────────────────────────────────────────────────────────────────────

# Legacy MemoryExtractor fact types → ARC2 types
_MEMORY_EXTRACTION_MAP: Dict[str, Optional[str]] = {
    "personal_info": "identity",
    "preference": "interest",
    "objection": "objection",
    "purchase_history": "intent_signal",
    "commitment": "relationship_state",
    "topic": "interest",
    "compressed_memo": None,   # skip
}

# ConversationFact FactType.value → ARC2 types (lead-side only)
_CONV_FACT_MAP: Dict[str, Optional[str]] = {
    "interest": "interest",        # INTEREST_EXPRESSED
    "objection": "objection",      # OBJECTION_RAISED
    "name_used": "identity",       # NAME_USED
    "appointment": "intent_signal",  # APPOINTMENT_MENTIONED
    "price_given": None,           # bot-side → skip
    "link_shared": None,           # bot-side → skip
    "product_explained": None,     # bot-side → skip
    "question_asked": None,        # ambiguous → skip (too noisy)
    "question_answered": None,     # bot-side → skip
}

# ─────────────────────────────────────────────────────────────────────────────
# ID RESOLUTION  (slug/platform_id → UUID)
# ─────────────────────────────────────────────────────────────────────────────

async def _resolve_creator_uuid(creator_id: str) -> Optional[str]:
    try:
        _uuid.UUID(creator_id)
        return creator_id
    except (ValueError, AttributeError):
        pass

    def _lookup() -> Optional[str]:
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            row = session.execute(
                text("SELECT id FROM creators WHERE name = :name LIMIT 1"),
                {"name": creator_id},
            ).fetchone()
            return str(row[0]) if row else None
        finally:
            session.close()

    try:
        return await asyncio.to_thread(_lookup)
    except Exception:
        return None


async def _resolve_lead_uuid(creator_uuid: str, lead_id: str) -> Optional[str]:
    try:
        _uuid.UUID(lead_id)
        return lead_id
    except (ValueError, AttributeError):
        pass

    raw_id = lead_id
    for prefix in ("ig_", "wa_", "tg_"):
        if raw_id.startswith(prefix):
            raw_id = raw_id[len(prefix):]
            break

    def _lookup() -> Optional[str]:
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            row = session.execute(
                text(
                    "SELECT id FROM leads "
                    "WHERE creator_id = CAST(:cid AS uuid) "
                    "AND platform_user_id = ANY(ARRAY[:pid, :pid_raw]) "
                    "LIMIT 1"
                ),
                {"cid": creator_uuid, "pid": lead_id, "pid_raw": raw_id},
            ).fetchone()
            return str(row[0]) if row else None
        finally:
            session.close()

    try:
        return await asyncio.to_thread(_lookup)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SYNC WRITE KERNEL
# ─────────────────────────────────────────────────────────────────────────────

def _write_entries_sync(
    creator_uuid: str,
    lead_uuid: str,
    entries: List[DualWriteEntry],
    source: str,
) -> int:
    """Runs inside asyncio.to_thread. Returns count of written entries."""
    from api.database import SessionLocal
    from services.lead_memory_service import LeadMemoryService

    session = SessionLocal()
    written = 0
    try:
        svc = LeadMemoryService(session)
        for entry in entries:
            if entry.memory_type not in (
                "identity", "interest", "objection", "intent_signal", "relationship_state"
            ):
                continue

            # Enforce mandatory body_structure fields for constrained types
            why = entry.why
            how_to_apply = entry.how_to_apply
            if entry.memory_type in ("objection", "relationship_state"):
                if not why:
                    why = "Extracted from legacy memory system"
                if not how_to_apply:
                    how_to_apply = "Use as context for personalization"

            try:
                svc.upsert(
                    creator_id=_uuid.UUID(creator_uuid),
                    lead_id=_uuid.UUID(lead_uuid),
                    memory_type=entry.memory_type,
                    content=entry.content[:500],
                    why=why,
                    how_to_apply=how_to_apply,
                    confidence=max(0.0, min(1.0, entry.confidence)),
                    last_writer=source,
                )
                written += 1
            except Exception as exc:
                logger.debug(
                    "[DualWrite] Entry write failed type=%s source=%s: %s",
                    entry.memory_type, source, exc,
                )
    finally:
        session.close()

    return written


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: core maybe_dual_write
# ─────────────────────────────────────────────────────────────────────────────

async def maybe_dual_write(
    creator_id: str,
    lead_id: str,
    entries: List[DualWriteEntry],
    source: str,
) -> None:
    """Write entries to arc2_lead_memories if flag is ON. Always fail-silent.

    Args:
        creator_id: slug or UUID string.
        lead_id:    platform_user_id or UUID string.
        entries:    list of DualWriteEntry to upsert.
        source:     last_writer value (e.g. 'dual_write_memory_extraction').
    """
    from core.feature_flags import flags
    if not flags.dual_write_lead_memories:
        return

    if not entries:
        return

    try:
        creator_uuid = await _resolve_creator_uuid(creator_id)
        if not creator_uuid:
            logger.debug("[DualWrite] Unresolved creator_id=%s — skip", creator_id)
            return

        lead_uuid = await _resolve_lead_uuid(creator_uuid, lead_id)
        if not lead_uuid:
            logger.debug("[DualWrite] Unresolved lead_id=%s — skip", lead_id)
            return

        written = await asyncio.to_thread(
            _write_entries_sync, creator_uuid, lead_uuid, entries, source
        )
        if written:
            logger.info(
                "[DualWrite] source=%s wrote %d memories lead=%s",
                source, written, lead_uuid[:8],
            )
    except Exception as exc:
        _increment_failure(source)
        logger.warning("[DualWrite] maybe_dual_write failed source=%s: %s", source, exc)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC: per-source entry builders (called from the 3 hook points)
# ─────────────────────────────────────────────────────────────────────────────

async def dual_write_from_extraction(
    creator_id: str,
    lead_id: str,
    facts: List[dict],
) -> None:
    """Hook for services/memory_extraction.py after legacy _store_fact loop."""
    entries: List[DualWriteEntry] = []
    for fact in facts:
        arc2_type = _MEMORY_EXTRACTION_MAP.get(fact.get("type", ""))
        if not arc2_type:
            continue
        entries.append(DualWriteEntry(
            memory_type=arc2_type,
            content=(fact.get("text") or "")[:100],
            why="Extracted by legacy MemoryExtractor from DM conversation",
            how_to_apply="Use as context for clone personalization",
            confidence=float(fact.get("confidence", 0.7)),
        ))
    await maybe_dual_write(creator_id, lead_id, entries, "dual_write_memory_extraction")


async def dual_write_from_follower_memory(memory: object) -> None:
    """Hook for services/memory_service.py::MemoryStore.save()."""
    entries: List[DualWriteEntry] = []

    name: str = getattr(memory, "name", "") or ""
    if name.strip():
        entries.append(DualWriteEntry(
            memory_type="identity",
            content=f"Lead's name is {name.strip()[:80]}",
            why="Name stored in FollowerMemory",
            how_to_apply="Address lead by name for personalization",
            confidence=0.85,
        ))

    for interest in (getattr(memory, "interests", None) or []):
        if interest:
            entries.append(DualWriteEntry(
                memory_type="interest",
                content=str(interest)[:100],
                why="Explicitly stored in FollowerMemory interests list",
                how_to_apply="Prioritize related products and topics in conversation",
                confidence=0.75,
            ))

    for objection in (getattr(memory, "objections_raised", None) or []):
        if objection:
            entries.append(DualWriteEntry(
                memory_type="objection",
                content=str(objection)[:100],
                why="Explicitly stored in FollowerMemory objections list",
                how_to_apply="Address this objection proactively before next offer",
                confidence=0.75,
            ))

    is_customer: bool = getattr(memory, "is_customer", False) or False
    status: str = getattr(memory, "status", "") or ""
    if is_customer:
        entries.append(DualWriteEntry(
            memory_type="relationship_state",
            content="Lead is a customer",
            why="is_customer=True in FollowerMemory",
            how_to_apply="Use customer-appropriate tone and upsell opportunities",
            confidence=0.9,
        ))
    elif status and status not in ("", "new"):
        entries.append(DualWriteEntry(
            memory_type="relationship_state",
            content=f"Lead status: {status}",
            why=f"status={status!r} set in FollowerMemory",
            how_to_apply="Adapt engagement strategy to current lead status",
            confidence=0.7,
        ))

    creator_id: str = getattr(memory, "creator_id", "") or ""
    follower_id: str = getattr(memory, "follower_id", "") or ""
    if entries and creator_id and follower_id:
        await maybe_dual_write(creator_id, follower_id, entries, "dual_write_follower_memory")


async def dual_write_from_conversation_memory(memory: object) -> None:
    """Hook for services/memory_service.py::ConversationMemoryService.save()."""
    entries: List[DualWriteEntry] = []
    facts = getattr(memory, "facts", None) or []

    for fact in facts:
        fact_type_val: str = ""
        ft = getattr(fact, "fact_type", None)
        if ft is not None:
            fact_type_val = ft.value if hasattr(ft, "value") else str(ft)

        arc2_type = _CONV_FACT_MAP.get(fact_type_val)
        if not arc2_type:
            continue

        content: str = str(getattr(fact, "content", "") or "")[:100]
        if not content:
            continue

        conf: float = float(getattr(fact, "confidence", 0.8) or 0.8)

        if arc2_type == "identity":
            entry_content = f"Lead name: {content}"
            entries.append(DualWriteEntry(
                memory_type="identity",
                content=entry_content,
                why="Name extracted from DM conversation",
                how_to_apply="Use lead's name for personalization",
                confidence=conf * 0.9,
            ))
        elif arc2_type == "interest":
            entries.append(DualWriteEntry(
                memory_type="interest",
                content=content,
                why="Lead expressed interest in conversation",
                how_to_apply="Prioritize related products and topics",
                confidence=conf * 0.9,
            ))
        elif arc2_type == "objection":
            entries.append(DualWriteEntry(
                memory_type="objection",
                content=content,
                why="Lead raised objection in DM conversation",
                how_to_apply="Address this objection proactively before next offer",
                confidence=conf * 0.9,
            ))
        elif arc2_type == "intent_signal":
            entries.append(DualWriteEntry(
                memory_type="intent_signal",
                content=content,
                why="Appointment or intent signal detected in conversation",
                how_to_apply="Follow up on this signal in next interaction",
                confidence=conf * 0.9,
            ))

    creator_id: str = getattr(memory, "creator_id", "") or ""
    lead_id: str = getattr(memory, "lead_id", "") or ""
    if entries and creator_id and lead_id:
        await maybe_dual_write(
            creator_id, lead_id, entries, "dual_write_conversation_memory"
        )
