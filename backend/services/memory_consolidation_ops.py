"""
Memory Consolidation Operations — Phase 1-4 (from CC consolidationPrompt.ts:27-58).

Stateless ops; memory_consolidator.py has gates/lock/scheduling.
Phase 3 uses LLM (CC-faithful) with algorithmic Jaccard fallback.
Feature flag: ENABLE_LLM_CONSOLIDATION (default OFF).
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from services.memory_engine import (
    MemoryEngine, _is_temporal_fact, MEMO_COMPRESSION_THRESHOLD,
)
from services.memory_consolidator import _validated_env_float, _validated_env_int

# Configuration — all from env vars, validated per CC autoDream.ts:73-93
DEDUP_JACCARD_THRESHOLD = _validated_env_float("CONSOLIDATION_DEDUP_JACCARD_THRESHOLD", 0.85)
MAX_LEADS_PER_RUN = _validated_env_int("CONSOLIDATION_MAX_LEADS_PER_RUN", 50)
MAX_DEACTIVATIONS_PER_RUN = _validated_env_int("CONSOLIDATION_MAX_DEACTIVATIONS_PER_RUN", 500)
MEMO_REFRESH_MIN_NEW_FACTS = _validated_env_int("CONSOLIDATION_MEMO_REFRESH_MIN_NEW_FACTS", 3)


@dataclass
class _FactRow:
    """Lightweight fact for consolidation (avoids full LeadMemory overhead)."""
    id: str
    lead_id: str
    fact_type: str
    fact_text: str
    confidence: float
    created_at: Optional[datetime]
    times_accessed: int


@dataclass
class ConsolidationResult:
    """Result of a single consolidation run for a creator."""
    creator_id: str
    leads_processed: int = 0
    facts_deduped: int = 0
    facts_expired: int = 0
    facts_cross_deduped: int = 0
    memos_refreshed: int = 0
    llm_contradictions_resolved: int = 0
    llm_dates_fixed: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    total_deactivations: int = 0  # Safety net counter


# Phase 1 — Orient (CC: "ls memory dir", consolidationPrompt.ts:28)

@dataclass
class _LeadSummary:
    """Aggregated summary of a lead's facts (from DB, no full fact load)."""
    lead_id: str
    total_facts: int
    has_memo: bool
    memo_created_at: Optional[datetime]
    newest_fact_at: Optional[datetime]
    has_temporal_stale: bool  # computed after light query


async def _orient_find_leads_needing_work(creator_id: str) -> List[_LeadSummary]:
    """Phase 1: DB aggregation to find leads needing work (CC: ls + skim)."""
    def _sync():
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            rows = session.execute(
                text(
                    "SELECT "
                    "  lead_id, "
                    "  count(*) FILTER (WHERE fact_type != 'compressed_memo') AS real_facts, "
                    "  bool_or(fact_type = 'compressed_memo') AS has_memo, "
                    "  max(created_at) FILTER (WHERE fact_type = 'compressed_memo') AS memo_at, "
                    "  max(created_at) FILTER (WHERE fact_type != 'compressed_memo') AS newest_fact "
                    "FROM lead_memories "
                    "WHERE creator_id = CAST(:cid AS uuid) "
                    "AND is_active = true "
                    "AND fact_type NOT IN ('_conv_memory_state') "
                    "GROUP BY lead_id "
                    "HAVING count(*) FILTER (WHERE fact_type != 'compressed_memo') >= 2 "
                    "ORDER BY real_facts DESC"
                ),
                {"cid": creator_id},
            ).fetchall()
            return [
                _LeadSummary(
                    lead_id=str(r[0]),
                    total_facts=int(r[1]),
                    has_memo=bool(r[2]),
                    memo_created_at=r[3],
                    newest_fact_at=r[4],
                    has_temporal_stale=False,  # computed in Phase 2
                )
                for r in rows
            ]
        finally:
            session.close()
    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.error("[Consolidator] _orient_find_leads failed: %s", e)
        return []


# Phase 2 — Gather (CC: "Look for new information", consolidationPrompt.ts:35)

def _lead_needs_work(summary: _LeadSummary) -> Optional[str]:
    """Decide if a lead needs consolidation. Returns reason or None."""
    temporal_ttl_days = int(os.getenv("MEMORY_TEMPORAL_TTL_DAYS", "7"))

    # Needs compression (no memo yet, enough facts)
    if not summary.has_memo and summary.total_facts >= MEMO_COMPRESSION_THRESHOLD:
        return "needs_compression"

    # Memo outdated (new facts added since memo)
    if (
        summary.has_memo
        and summary.memo_created_at
        and summary.newest_fact_at
        and summary.newest_fact_at > summary.memo_created_at
        and summary.total_facts >= MEMO_COMPRESSION_THRESHOLD
    ):
        return "memo_outdated"

    # Enough facts for potential dedup (>= 2 already filtered by SQL)
    if summary.total_facts >= MEMO_COMPRESSION_THRESHOLD:
        return "potential_dedup"

    return None


async def _gather_load_facts(
    creator_id: str, lead_id: str,
) -> List[_FactRow]:
    """Load all active facts for a single lead (Phase 2 — targeted load)."""
    def _sync():
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            rows = session.execute(
                text(
                    "SELECT id, lead_id, fact_type, fact_text, confidence, "
                    "created_at, times_accessed "
                    "FROM lead_memories "
                    "WHERE creator_id = CAST(:cid AS uuid) "
                    "AND lead_id = CAST(:lid AS uuid) "
                    "AND is_active = true "
                    "AND fact_type NOT IN ('_conv_memory_state') "
                    "ORDER BY created_at"
                ),
                {"cid": creator_id, "lid": lead_id},
            ).fetchall()
            return [
                _FactRow(
                    id=str(r[0]),
                    lead_id=str(r[1]),
                    fact_type=r[2],
                    fact_text=r[3],
                    confidence=float(r[4]) if r[4] else 0.7,
                    created_at=r[5],
                    times_accessed=int(r[6]) if r[6] else 0,
                )
                for r in rows
            ]
        finally:
            session.close()
    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.error("[Consolidator] _gather_load_facts failed for lead=%s: %s", lead_id[:8], e)
        return []


def _find_near_duplicates(facts: List[_FactRow]) -> List[Tuple[str, str]]:
    """Find near-duplicate fact pairs by Jaccard similarity. Returns (deactivate_id, keep_id)."""
    dupes = []
    for i in range(len(facts)):
        for j in range(i + 1, len(facts)):
            sim = MemoryEngine._text_similarity(  # Reuse, not duplicate (G7 fix)
                facts[i].fact_text, facts[j].fact_text,
            )
            if sim >= DEDUP_JACCARD_THRESHOLD:
                # Keep the one with more accesses, or newer if tied
                if facts[i].times_accessed >= facts[j].times_accessed:
                    dupes.append((facts[j].id, facts[i].id))
                else:
                    dupes.append((facts[i].id, facts[j].id))
    return dupes


# Phase 3 — Consolidate (CC: consolidationPrompt.ts:44-52)

async def _deactivate_facts(fact_ids: List[str]) -> int:
    """Deactivate facts by ID."""
    if not fact_ids:
        return 0
    def _sync():
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            for fid in fact_ids:
                session.execute(
                    text(
                        "UPDATE lead_memories SET is_active = false, updated_at = NOW() "
                        "WHERE id = CAST(:fid AS uuid)"
                    ),
                    {"fid": fid},
                )
            session.commit()
            return len(fact_ids)
        finally:
            session.close()
    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.error("[Consolidator] _deactivate_facts failed: %s", e)
        return 0


async def consolidate_lead(
    creator_id: str,
    lead_id: str,
    facts: List[_FactRow],
    result: ConsolidationResult,
) -> None:
    """Phase 3: LLM analysis → algorithmic fallback → expire → re-compress."""
    real_facts = [f for f in facts if f.fact_type != "compressed_memo"]
    llm_removed_ids: set = set()

    # 3a. LLM-powered analysis (CC: consolidationPrompt.ts:44-52)
    # "Merging new signal... Converting relative dates... Deleting contradicted facts"
    try:
        from services.memory_consolidation_llm import (
            llm_analyze_facts, apply_date_fixes,
        )
        llm_result = await llm_analyze_facts(real_facts)
        if llm_result is not None:
            llm_dupes, llm_contradictions, llm_date_fixes = llm_result

            # Apply LLM-detected duplicates
            llm_dedup_ids = list({
                real_facts[d["remove"]].id for d in llm_dupes
                if d["remove"] < len(real_facts)
            })
            if llm_dedup_ids:
                if result.total_deactivations + len(llm_dedup_ids) <= MAX_DEACTIVATIONS_PER_RUN:
                    count = await _deactivate_facts(llm_dedup_ids)
                    result.facts_deduped += count
                    result.total_deactivations += count
                    llm_removed_ids.update(llm_dedup_ids)
                    if count > 0:
                        logger.info("[Consolidator] LLM deduped %d facts for lead=%s", count, lead_id[:8])

            # Apply LLM-detected contradictions (CC: "delete contradicted facts")
            contradiction_ids = list({
                real_facts[c["remove"]].id for c in llm_contradictions
                if c["remove"] < len(real_facts)
            } - llm_removed_ids)
            if contradiction_ids:
                if result.total_deactivations + len(contradiction_ids) <= MAX_DEACTIVATIONS_PER_RUN:
                    count = await _deactivate_facts(contradiction_ids)
                    result.facts_deduped += count  # counted as dedup in metrics
                    result.total_deactivations += count
                    llm_removed_ids.update(contradiction_ids)
                    if count > 0:
                        logger.info("[Consolidator] LLM resolved %d contradictions for lead=%s", count, lead_id[:8])

            # Apply date fixes (CC: "converting relative dates to absolute dates")
            if llm_date_fixes:
                date_count = await apply_date_fixes(real_facts, llm_date_fixes)
                if date_count > 0:
                    logger.info("[Consolidator] LLM fixed %d dates for lead=%s", date_count, lead_id[:8])

    except Exception as e:
        # LLM step is best-effort — never block consolidation (graceful degradation)
        logger.warning("[Consolidator] LLM analysis failed for lead=%s: %s — falling back to algorithmic", lead_id[:8], e)

    # 3b. Algorithmic dedup — Jaccard fallback for anything LLM missed
    # (CC: consolidationPrompt.ts:49 "Merging new signal... near-duplicates")
    # Runs on facts NOT already removed by LLM
    remaining_facts = [f for f in real_facts if f.id not in llm_removed_ids]
    dupes = _find_near_duplicates(remaining_facts)
    if dupes:
        ids_to_deactivate = list({d[0] for d in dupes} - llm_removed_ids)
        if ids_to_deactivate:
            if result.total_deactivations + len(ids_to_deactivate) > MAX_DEACTIVATIONS_PER_RUN:
                logger.warning(
                    "[Consolidator] Safety net: would exceed %d deactivations, stopping dedup for lead=%s",
                    MAX_DEACTIVATIONS_PER_RUN, lead_id[:8],
                )
            else:
                count = await _deactivate_facts(ids_to_deactivate)
                result.facts_deduped += count
                result.total_deactivations += count
                if count > 0:
                    logger.info("[Consolidator] Algorithmic deduped %d facts for lead=%s", count, lead_id[:8])

    # 3c. Expire stale temporal facts (CC: consolidationPrompt.ts:51 "delete contradicted")
    now = datetime.now(timezone.utc)
    temporal_ttl_days = int(os.getenv("MEMORY_TEMPORAL_TTL_DAYS", "7"))
    ids_to_expire = []
    for f in real_facts:
        if f.id in llm_removed_ids:
            continue  # Already handled by LLM
        if not _is_temporal_fact(f.fact_text):  # Reuse, not duplicate (G8 fix)
            continue
        if f.created_at is None:
            continue
        created = f.created_at if f.created_at.tzinfo else f.created_at.replace(tzinfo=timezone.utc)
        if (now - created).days > temporal_ttl_days:
            ids_to_expire.append(f.id)

    if ids_to_expire:
        if result.total_deactivations + len(ids_to_expire) > MAX_DEACTIVATIONS_PER_RUN:
            logger.warning(
                "[Consolidator] Safety net: would exceed %d deactivations, stopping expire for lead=%s",
                MAX_DEACTIVATIONS_PER_RUN, lead_id[:8],
            )
        else:
            count = await _deactivate_facts(ids_to_expire)
            result.facts_expired += count
            result.total_deactivations += count
            if count > 0:
                logger.info("[Consolidator] Expired %d temporal facts for lead=%s", count, lead_id[:8])

    # 3d. Re-compress memo if facts changed or threshold reached
    # (CC: "write or update a memory file" — consolidationPrompt.ts:46)
    from services.memory_engine import get_memory_engine
    engine = get_memory_engine()
    if (result.facts_deduped > 0 or result.facts_expired > 0
            or len(real_facts) >= MEMO_COMPRESSION_THRESHOLD):
        try:
            memo = await engine.compress_lead_memory(creator_id, lead_id, _skip_lock_check=True)
            if memo:
                result.memos_refreshed += 1
        except Exception as e:
            logger.error("[Consolidator] compress failed for lead=%s: %s", lead_id[:8], e)

    result.leads_processed += 1


# Phase 4 — Prune (CC: consolidationPrompt.ts:54-58)

async def cross_lead_dedup(creator_id: str, result: ConsolidationResult) -> int:
    """Phase 4: Cross-lead exact-text dedup. Keeps highest-access copy."""
    def _sync():
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            # Find exact-text duplicates across different leads
            rows = session.execute(
                text(
                    "SELECT lower(trim(fact_text)) AS norm, "
                    "  array_agg(id ORDER BY times_accessed DESC, created_at DESC) AS ids, "
                    "  count(*) AS cnt "
                    "FROM lead_memories "
                    "WHERE creator_id = CAST(:cid AS uuid) "
                    "AND is_active = true "
                    "AND fact_type NOT IN "
                    "  ('_conv_memory_state', 'compressed_memo') "
                    "GROUP BY lower(trim(fact_text)) "
                    "HAVING count(*) > 1 "
                    "  AND count(DISTINCT lead_id) > 1 "  # Cross-lead only
                    "ORDER BY cnt DESC "
                    "LIMIT :max_groups"
                ),
                {"cid": creator_id, "max_groups": MAX_LEADS_PER_RUN},
            ).fetchall()
            # For each group, keep first (highest access), deactivate rest
            ids_to_deactivate = []
            for row in rows:
                all_ids = row[1]  # array of UUIDs sorted by times_accessed DESC
                if len(all_ids) > 1:
                    ids_to_deactivate.extend(str(uid) for uid in all_ids[1:])
            return ids_to_deactivate
        finally:
            session.close()

    try:
        ids_to_deactivate = await asyncio.to_thread(_sync)
        if not ids_to_deactivate:
            return 0
        # Safety net
        if result.total_deactivations + len(ids_to_deactivate) > MAX_DEACTIVATIONS_PER_RUN:
            logger.warning(
                "[Consolidator] Safety net: would exceed %d deactivations in cross-lead dedup",
                MAX_DEACTIVATIONS_PER_RUN,
            )
            allowed = MAX_DEACTIVATIONS_PER_RUN - result.total_deactivations
            ids_to_deactivate = ids_to_deactivate[:max(0, allowed)]
        if not ids_to_deactivate:
            return 0
        count = await _deactivate_facts(ids_to_deactivate)
        result.total_deactivations += count
        if count > 0:
            logger.info("[Consolidator] Cross-lead deduped %d facts for creator=%s", count, creator_id[:8])
        return count
    except Exception as e:
        logger.error("[Consolidator] cross_lead_dedup failed: %s", e)
        return 0


async def record_consolidation(creator_id: str) -> None:
    """Record consolidation timestamp (CC: writeFile sets mtime=now, consolidationLock.ts:130-140).

    CC: recordConsolidation() writes PID to lock file — mtime becomes lastConsolidatedAt.
    Clonnect: UPDATE creators.last_consolidated_at = NOW(). Per-creator, no fake rows.
    """
    def _sync():
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            session.execute(
                text(
                    "UPDATE creators SET last_consolidated_at = NOW() "
                    "WHERE id = CAST(:cid AS uuid)"
                ),
                {"cid": creator_id},
            )
            session.commit()
        finally:
            session.close()
    try:
        await asyncio.to_thread(_sync)
    except Exception as e:
        logger.error("[Consolidator] record_consolidation failed: %s", e)
