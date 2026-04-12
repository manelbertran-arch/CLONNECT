"""
Memory Consolidator — Gates, lock, scheduling, and orchestration.

Adapted from Claude Code's autoDream pattern:
  src/services/autoDream/autoDream.ts      — gates + orchestration
  src/services/autoDream/config.ts         — feature flag
  src/services/autoDream/consolidationLock.ts — lock + timestamp

Operations (Phase 1-4) live in memory_consolidation_ops.py.

Gate order (cheapest first, from autoDream.ts:5-8):
  1. Feature flag: ENABLE_MEMORY_CONSOLIDATION
  2. Memory engine gate: ENABLE_MEMORY_ENGINE (CC: autoDream.ts:98)
  3. Time: hours since lastConsolidatedAt >= minHours
  4. Scan throttle: don't re-scan within cooldown (CC: autoDream.ts:56)
  5. Activity: messages since lastConsolidatedAt >= minMessages
  6. Lock: no other process mid-consolidation (pg advisory lock)

Feature flag: ENABLE_MEMORY_CONSOLIDATION (default OFF)
"""

import asyncio
import hashlib
import logging
import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATED ENV PARSING (from CC autoDream.ts:73-93 — defensive per-field)
# CC validates each field: isFinite, > 0, fallback to default.
# ═══════════════════════════════════════════════════════════════════════════════

def _validated_env_float(name: str, default: float) -> float:
    """Parse env var as float with CC-style validation (autoDream.ts:80-86).

    Checks: parseable, finite, >= 0. Falls back to default on any failure.
    0 is valid: means "no minimum" — equivalent to CC with no lock file
    (readLastConsolidatedAt returns 0 → hoursSince is huge → gate always passes).
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        val = float(raw)
        if math.isfinite(val) and val >= 0:
            return val
    except (ValueError, TypeError):
        pass
    logger.warning(
        "[Consolidator] Invalid env %s=%r — using default %.1f", name, raw, default,
    )
    return default


def _validated_env_int(name: str, default: int) -> int:
    """Parse env var as int with CC-style validation (autoDream.ts:87-92).

    Checks: parseable, >= 0. Falls back to default on any failure.
    0 is valid: means "no minimum" — equivalent to CC with no lock file.
    """
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        val = int(raw)
        if val >= 0:
            return val
    except (ValueError, TypeError):
        pass
    logger.warning(
        "[Consolidator] Invalid env %s=%r — using default %d", name, raw, default,
    )
    return default


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE FLAG + CONFIGURATION (from config.ts:13-21, autoDream.ts:58-93)
# All from env vars, zero hardcoding. Validated per CC pattern.
# ═══════════════════════════════════════════════════════════════════════════════

ENABLE_MEMORY_CONSOLIDATION = (
    os.getenv("ENABLE_MEMORY_CONSOLIDATION", "false").lower() == "true"
)

# Gate thresholds — CC defaults: minHours=24, minSessions=5 (autoDream.ts:64-65)
MIN_CONSOLIDATION_HOURS = _validated_env_float("CONSOLIDATION_MIN_HOURS", 24.0)
# CC counts sessions; Clonnect counts messages (≈5 sessions × 4 msgs = 20)
MIN_MESSAGES_SINCE = _validated_env_int("CONSOLIDATION_MIN_MESSAGES", 20)

# Scan throttle: CC uses 10min (autoDream.ts:56)
SCAN_THROTTLE_SECONDS = _validated_env_int("CONSOLIDATION_SCAN_THROTTLE_SECONDS", 600)


# ═══════════════════════════════════════════════════════════════════════════════
# SCAN THROTTLE (from autoDream.ts:56, SESSION_SCAN_INTERVAL_MS)
# In-memory throttle per creator — prevents re-scanning when time gate passes
# but activity gate doesn't (CC: autoDream.ts:143-151)
# ═══════════════════════════════════════════════════════════════════════════════

_last_scan_at: Dict[str, float] = {}


def _is_scan_throttled(creator_id: str) -> bool:
    """Check if we should skip scanning (CC: autoDream.ts:143-151)."""
    last = _last_scan_at.get(creator_id, 0)
    return (time.time() - last) < SCAN_THROTTLE_SECONDS


def _record_scan(creator_id: str) -> None:
    """Record that we scanned this creator."""
    _last_scan_at[creator_id] = time.time()


def reset_scan_state() -> None:
    """Reset scan throttle state. For tests (fixes G12 — CC: autoDream.ts:10-11)."""
    _last_scan_at.clear()


# ═══════════════════════════════════════════════════════════════════════════════
# LOCK: PostgreSQL advisory lock (adapted from consolidationLock.ts:46-84)
# CC uses file lock with PID + mtime. Clonnect uses pg_try_advisory_lock.
# ═══════════════════════════════════════════════════════════════════════════════

def _creator_lock_key(creator_id: str) -> int:
    """Deterministic int64 lock key from creator UUID.

    CC uses file lock keyed on memory dir path (consolidationLock.ts:21).
    Clonnect hashes creator_id for pg advisory lock.
    """
    h = hashlib.md5(f"consolidation:{creator_id}".encode()).hexdigest()
    # pg_try_advisory_lock takes bigint — use first 15 hex chars (60 bits)
    return int(h[:15], 16)


async def _try_acquire_lock(creator_id: str) -> Tuple[bool, Any]:
    """Try to acquire advisory lock (CC: consolidationLock.ts:46-84).

    Returns (True, session) if acquired, (False, None) otherwise.
    pg_try_advisory_lock is atomic — no race possible (CC P14 N/A).
    Lock auto-releases on session close (CC P13 stale detection N/A).
    """
    def _sync():
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            key = _creator_lock_key(creator_id)
            row = session.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": key},
            ).fetchone()
            acquired = bool(row[0]) if row else False
            if not acquired:
                session.close()
                return False, None
            return True, session
        except Exception:
            session.close()
            raise
    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.error("[Consolidator] Lock acquire failed: %s", e)
        return False, None


async def _release_lock(session) -> None:
    """Release advisory lock by closing session (CC: lock mtime stays on success)."""
    if session is None:
        return
    def _sync():
        try:
            session.close()
        except Exception:
            pass
    await asyncio.to_thread(_sync)


def is_consolidation_locked(creator_id: str) -> bool:
    """Non-blocking check: is consolidation currently running for this creator?

    FIX Gap 1 (audit): Lets memory_engine.add() detect concurrent consolidation.
    Uses pg_try_advisory_lock + immediate unlock in a short-lived session.
    Returns True if locked (consolidation in progress), False otherwise.

    IMPORTANT: This is non-blocking. DM pipeline must never be blocked by
    consolidation — this is informational only (log warning + continue).
    """
    try:
        from api.database import SessionLocal
        from sqlalchemy import text
        key = _creator_lock_key(creator_id)
        session = SessionLocal()
        try:
            row = session.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": key},
            ).fetchone()
            acquired = bool(row[0]) if row else False
            if acquired:
                # We acquired it → nobody else had it → unlock immediately
                session.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": key},
                )
                return False  # Not locked
            return True  # Someone else holds it
        finally:
            session.close()
    except Exception:
        return False  # On error, assume not locked (don't block DM)


# ═══════════════════════════════════════════════════════════════════════════════
# GATE: last consolidated at (from consolidationLock.ts:29-36)
# ═══════════════════════════════════════════════════════════════════════════════

async def _get_last_consolidated_at(creator_id: str) -> Optional[datetime]:
    """Get timestamp of last consolidation.

    CC: lock file mtime IS lastConsolidatedAt (consolidationLock.ts:29-36).
    Clonnect: creators.last_consolidated_at column (per-creator, no fake rows).
    """
    def _sync():
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            row = session.execute(
                text(
                    "SELECT last_consolidated_at FROM creators "
                    "WHERE id = CAST(:cid AS uuid)"
                ),
                {"cid": creator_id},
            ).fetchone()
            return row[0] if row else None
        finally:
            session.close()
    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.error("[Consolidator] _get_last_consolidated_at failed: %s", e)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# GATE: activity since last consolidation (from autoDream.ts:153-171)
# ═══════════════════════════════════════════════════════════════════════════════

async def _count_messages_since(creator_id: str, since: datetime) -> int:
    """Count messages since timestamp.

    CC counts session files by mtime (consolidationLock.ts:118-124).
    Clonnect counts messages in DB.
    """
    def _sync():
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            row = session.execute(
                text(
                    "SELECT count(*) FROM messages "
                    "WHERE creator_id = CAST(:cid AS uuid) "
                    "AND created_at > :since"
                ),
                {"cid": creator_id, "since": since},
            ).fetchone()
            return row[0] if row else 0
        finally:
            session.close()
    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        logger.error("[Consolidator] _count_messages_since failed: %s", e)
        return 0


# ═══════════════════════════════════════════════════════════════════════════════
# ORCHESTRATOR — consolidate_creator()
# Runs the 4-phase protocol for a single creator
# (from autoDream.ts:125-272)
# ═══════════════════════════════════════════════════════════════════════════════

async def consolidate_creator(creator_id: str):
    """Run the full 4-phase consolidation for a single creator.

    Adapted from autoDream.ts:125-272 (runAutoDream closure).
    Returns ConsolidationResult.
    """
    from services.memory_consolidation_ops import (
        ConsolidationResult,
        _lead_needs_work,
        _orient_find_leads_needing_work,
        _gather_load_facts,
        consolidate_lead,
        cross_lead_dedup,
        record_consolidation,
        MAX_LEADS_PER_RUN,
    )

    start_time = time.time()
    result = ConsolidationResult(creator_id=creator_id)

    try:
        # PHASE 1: ORIENT — lazy scan (CC: consolidationPrompt.ts:27-31)
        logger.info("[Consolidator] Phase 1 — Orient: scanning for creator=%s", creator_id[:8])
        lead_summaries = await _orient_find_leads_needing_work(creator_id)
        logger.info("[Consolidator] Orient: %d leads with facts >= 2", len(lead_summaries))

        # PHASE 2: GATHER — filter + targeted load (CC: consolidationPrompt.ts:33-42)
        logger.info("[Consolidator] Phase 2 — Gather: filtering leads that need work")
        leads_to_process = []
        for summary in lead_summaries:
            reason = _lead_needs_work(summary)
            if reason:
                leads_to_process.append((summary, reason))
        leads_to_process = leads_to_process[:MAX_LEADS_PER_RUN]
        logger.info("[Consolidator] Gather: %d leads need work", len(leads_to_process))

        # PHASE 3: CONSOLIDATE — per-lead (CC: consolidationPrompt.ts:44-52)
        logger.info("[Consolidator] Phase 3 — Consolidate: processing %d leads", len(leads_to_process))
        for summary, reason in leads_to_process:
            try:
                facts = await _gather_load_facts(creator_id, summary.lead_id)
                if not facts:
                    continue
                await consolidate_lead(creator_id, summary.lead_id, facts, result)
            except Exception as lead_err:
                logger.error("[Consolidator] Failed for lead=%s: %s", summary.lead_id[:8], lead_err)

        # PHASE 4: PRUNE — cross-lead dedup (CC: consolidationPrompt.ts:54-58)
        logger.info("[Consolidator] Phase 4 — Prune: cross-lead dedup")
        result.facts_cross_deduped = await cross_lead_dedup(creator_id, result)

        # Record consolidation timestamp (CC: lock mtime stays at now)
        await record_consolidation(creator_id)

    except Exception as e:
        result.error = str(e)
        logger.error("[Consolidator] consolidate_creator failed: %s", e, exc_info=True)

    result.duration_seconds = time.time() - start_time
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEDULER ENTRY POINT — consolidation_job()
# (from autoDream.ts:319-324, executeAutoDream)
# ═══════════════════════════════════════════════════════════════════════════════

async def consolidation_job() -> None:
    """Background job entry point, registered with TaskScheduler.

    CC: executeAutoDream() from stopHooks per-turn (autoDream.ts:319-324).
    Clonnect: runs on TaskScheduler interval (webhook arch, no per-turn hooks).
    """
    # Gate 1: Feature flag (CC: config.ts:13-21)
    if not ENABLE_MEMORY_CONSOLIDATION:
        logger.debug("[Consolidator] Disabled via ENABLE_MEMORY_CONSOLIDATION=false")
        return

    # Gate 2: Memory engine must be enabled (CC: autoDream.ts:98, fixes G5)
    from services.memory_engine import ENABLE_MEMORY_ENGINE
    if not ENABLE_MEMORY_ENGINE:
        logger.debug("[Consolidator] Skipped — ENABLE_MEMORY_ENGINE=false")
        return

    # Get all active creators
    def _get_creators():
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            rows = session.execute(
                text("SELECT id FROM creators WHERE bot_active = true")
            ).fetchall()
            return [str(r[0]) for r in rows]
        finally:
            session.close()

    try:
        creator_ids = await asyncio.to_thread(_get_creators)
    except Exception as e:
        logger.error("[Consolidator] Failed to get creators: %s", e)
        return

    total_results = []
    for creator_id in creator_ids:
        try:
            # Gate 3: TIME (CC: autoDream.ts:131-141)
            last_at = await _get_last_consolidated_at(creator_id)
            if last_at is not None:
                last_at_utc = last_at if last_at.tzinfo else last_at.replace(tzinfo=timezone.utc)
                hours_since = (datetime.now(timezone.utc) - last_at_utc).total_seconds() / 3600
                if hours_since < MIN_CONSOLIDATION_HOURS:
                    logger.debug(
                        "[Consolidator] Skip creator=%s — %.1fh < %.0fh",
                        creator_id[:8], hours_since, MIN_CONSOLIDATION_HOURS,
                    )
                    continue

                # Gate 4: SCAN THROTTLE (CC: autoDream.ts:143-151)
                if _is_scan_throttled(creator_id):
                    logger.debug("[Consolidator] Skip creator=%s — scan throttled", creator_id[:8])
                    continue
                _record_scan(creator_id)

                # Gate 5: ACTIVITY (CC: autoDream.ts:153-171)
                msg_count = await _count_messages_since(creator_id, last_at_utc)
                if msg_count < MIN_MESSAGES_SINCE:
                    logger.debug(
                        "[Consolidator] Skip creator=%s — %d msgs < %d",
                        creator_id[:8], msg_count, MIN_MESSAGES_SINCE,
                    )
                    continue

            # Gate 6: LOCK (CC: consolidationLock.ts:46-84)
            acquired, lock_session = await _try_acquire_lock(creator_id)
            if not acquired:
                logger.debug("[Consolidator] Skip creator=%s — locked", creator_id[:8])
                continue

            try:
                logger.info("[Consolidator] Starting for creator=%s", creator_id[:8])
                result = await consolidate_creator(creator_id)
                total_results.append(result)
                logger.info(
                    "[Consolidator] Done creator=%s: leads=%d deduped=%d expired=%d "
                    "cross=%d memos=%d total_deact=%d duration=%.1fs",
                    creator_id[:8], result.leads_processed, result.facts_deduped,
                    result.facts_expired, result.facts_cross_deduped,
                    result.memos_refreshed, result.total_deactivations,
                    result.duration_seconds,
                )
            finally:
                # Release lock (CC: session close releases advisory lock)
                await _release_lock(lock_session)

        except Exception as e:
            logger.error("[Consolidator] Error for creator=%s: %s", creator_id[:8], e)

    # Summary log (CC: analytics events — P34/P35/P36)
    if total_results:
        logger.info(
            "[Consolidator] Job complete: %d creators, leads=%d deduped=%d expired=%d cross=%d memos=%d",
            len(total_results),
            sum(r.leads_processed for r in total_results),
            sum(r.facts_deduped for r in total_results),
            sum(r.facts_expired for r in total_results),
            sum(r.facts_cross_deduped for r in total_results),
            sum(r.memos_refreshed for r in total_results),
        )
