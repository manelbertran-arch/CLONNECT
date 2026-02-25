"""
AI/ML scheduled jobs — copilot eval, copilot recalibration, learning
consolidation, pattern analyzer, gold examples, clone score,
memory decay, commitment cleanup, style recalculation.
"""

import asyncio
import logging
import os

logger = logging.getLogger(__name__)


# --- Copilot daily evaluation (24h) ---
async def copilot_daily_eval_job():
    enable = os.getenv("ENABLE_COPILOT_EVAL", "true").lower() == "true"
    if not enable:
        logger.debug("[COPILOT_EVAL] Disabled via env var, skipping")
        return
    from api.database import SessionLocal
    from api.models import Creator
    from core.autolearning_evaluator import run_daily_evaluation

    session = SessionLocal()
    try:
        creators = (
            session.query(Creator.id, Creator.name)
            .filter(Creator.bot_active.is_(True))
            .all()
        )
        results = []
        for creator_db_id, creator_name in creators:
            result = await run_daily_evaluation(creator_name, creator_db_id)
            if result.get("stored"):
                results.append(creator_name)
        if results:
            logger.info(
                f"[COPILOT_EVAL] Daily evals stored for: {', '.join(results)}"
            )
    finally:
        session.close()


# --- Copilot weekly recalibration (7 days) ---
async def copilot_weekly_recal_job():
    enable = os.getenv("ENABLE_COPILOT_RECAL", "true").lower() == "true"
    if not enable:
        logger.debug("[COPILOT_RECAL] Disabled via env var, skipping")
        return
    from api.database import SessionLocal
    from api.models import Creator
    from core.autolearning_evaluator import run_weekly_recalibration

    session = SessionLocal()
    try:
        creators = (
            session.query(Creator.id, Creator.name)
            .filter(Creator.bot_active.is_(True))
            .all()
        )
        results = []
        for creator_db_id, creator_name in creators:
            result = await run_weekly_recalibration(creator_name, creator_db_id)
            if result.get("stored"):
                results.append(creator_name)
        if results:
            logger.info(
                f"[COPILOT_RECAL] Weekly recalibration stored for: {', '.join(results)}"
            )
    finally:
        session.close()


# --- Learning rule consolidation (24h) ---
async def learning_consolidation_job():
    enable = os.getenv("ENABLE_LEARNING_CONSOLIDATION", "false").lower() == "true"
    if not enable:
        logger.debug("[LEARNING_CONSOLIDATION] Disabled via env var, skipping")
        return
    from api.database import SessionLocal
    from api.models import Creator
    from services.learning_consolidator import consolidate_rules_for_creator

    session = SessionLocal()
    try:
        creators = (
            session.query(Creator.id, Creator.name)
            .filter(Creator.bot_active.is_(True))
            .all()
        )
        for creator_db_id, creator_name in creators:
            try:
                result = await consolidate_rules_for_creator(
                    creator_name, creator_db_id
                )
                if result.get("status") == "done":
                    logger.info(
                        f"[LEARNING_CONSOLIDATION] {creator_name}: "
                        f"consolidated={result.get('consolidated', 0)} "
                        f"deactivated={result.get('deactivated', 0)}"
                    )
            except Exception as creator_err:
                logger.error(
                    f"[LEARNING_CONSOLIDATION] Error for {creator_name}: {creator_err}"
                )
    finally:
        session.close()


# --- Pattern analyzer (12h) ---
async def pattern_analyzer_job():
    enable = os.getenv("ENABLE_PATTERN_ANALYZER", "false").lower() == "true"
    if not enable:
        logger.debug("[PATTERN_ANALYZER] Disabled via env var, skipping")
        return
    from services.pattern_analyzer import run_pattern_analysis_all

    results = await run_pattern_analysis_all()
    for creator_name, result in results.items():
        if result.get("status") == "done":
            logger.info(
                f"[PATTERN_ANALYZER] {creator_name}: "
                f"pairs={result.get('pairs_analyzed', 0)} "
                f"rules={result.get('rules_created', 0)}"
            )


# --- Gold examples + preference pairs (12h) ---
async def gold_examples_job():
    enable_gold = os.getenv("ENABLE_GOLD_EXAMPLES", "false").lower() == "true"
    enable_profile = os.getenv("ENABLE_PREFERENCE_PROFILE", "false").lower() == "true"
    enable_pairs = os.getenv("ENABLE_PREFERENCE_PAIRS", "true").lower() == "true"
    if not enable_gold and not enable_profile and not enable_pairs:
        logger.debug("[GOLD_EXAMPLES] All sub-tasks disabled, skipping")
        return
    from api.database import SessionLocal
    from api.models import Creator

    session = SessionLocal()
    try:
        creators = (
            session.query(Creator.id, Creator.name)
            .filter(Creator.bot_active.is_(True))
            .all()
        )
    finally:
        session.close()

    for creator_db_id, creator_name in creators:
        try:
            if enable_gold:
                from services.gold_examples_service import curate_examples
                result = await curate_examples(creator_name, creator_db_id)
                if result.get("status") == "done":
                    logger.info(
                        f"[GOLD_EXAMPLES] {creator_name}: "
                        f"created={result.get('created', 0)} "
                        f"expired={result.get('expired', 0)}"
                    )
            if enable_pairs:
                from services.preference_pairs_service import curate_pairs
                pairs_result = await curate_pairs(creator_name, creator_db_id)
                if pairs_result.get("historical_created", 0) > 0:
                    logger.info(
                        f"[PREF_PAIRS] {creator_name}: "
                        f"historical_created={pairs_result.get('historical_created', 0)}"
                    )
        except Exception as creator_err:
            logger.error(f"[GOLD_EXAMPLES] Error for {creator_name}: {creator_err}")


# --- CloneScore daily evaluation (24h) ---
async def clone_score_daily_job():
    enable = os.getenv("ENABLE_CLONE_SCORE_EVAL", "false").lower() == "true"
    if not enable:
        logger.debug("[CLONE_SCORE] Disabled via ENABLE_CLONE_SCORE_EVAL, skipping")
        return
    from api.database import SessionLocal
    from api.models import Creator
    from services.clone_score_engine import get_clone_score_engine

    session = SessionLocal()
    try:
        creators = (
            session.query(Creator.id, Creator.name)
            .filter(Creator.bot_active.is_(True))
            .all()
        )
    finally:
        session.close()

    engine = get_clone_score_engine()
    for creator_db_id, creator_name in creators:
        try:
            result = await engine.evaluate_batch(
                creator_id=creator_name,
                creator_db_id=creator_db_id,
                sample_size=50,
            )
            if result.get("overall_score"):
                logger.info(
                    f"[CLONE_SCORE] {creator_name}: "
                    f"{result['overall_score']:.1f}"
                )
        except Exception as e:
            logger.error(
                f"[CLONE_SCORE] Error for {creator_name}: {e}"
            )
        await asyncio.sleep(30)


# --- Memory decay (24h) ---
async def memory_decay_job():
    enable = os.getenv("ENABLE_MEMORY_DECAY", "false").lower() == "true"
    if not enable:
        logger.debug("[MEMORY-DECAY] Disabled via ENABLE_MEMORY_DECAY, skipping")
        return
    from api.database import SessionLocal
    from services.memory_engine import get_memory_engine
    from sqlalchemy import text

    engine = get_memory_engine()
    session = SessionLocal()
    try:
        rows = session.execute(
            text("SELECT id FROM creators WHERE bot_active = true")
        ).fetchall()
        creator_ids = [str(r[0]) for r in rows]
    finally:
        session.close()

    total_deactivated = 0
    for cid in creator_ids:
        try:
            count = await engine.decay_memories(cid)
            total_deactivated += count
        except Exception as decay_err:
            logger.error(
                "[MEMORY-DECAY] Failed for creator %s: %s",
                cid[:8], decay_err,
            )

    logger.info(
        "[MEMORY-DECAY] Processed %d creators, deactivated %d memories",
        len(creator_ids),
        total_deactivated,
    )


# --- Commitment cleanup (24h) ---
async def commitment_cleanup_job():
    enable = os.getenv("ENABLE_COMMITMENT_CLEANUP", "true").lower() == "true"
    if not enable:
        logger.debug("[COMMITMENT_CLEANUP] Disabled via env var, skipping")
        return
    from api.database import SessionLocal
    from api.models import Creator
    from services.commitment_tracker import get_commitment_tracker

    tracker = get_commitment_tracker()
    session = SessionLocal()
    try:
        creators = (
            session.query(Creator.id, Creator.name)
            .filter(Creator.bot_active.is_(True))
            .all()
        )
    finally:
        session.close()

    total_expired = 0
    for creator_db_id, creator_name in creators:
        try:
            expired = tracker.expire_overdue(creator_name)
            total_expired += expired
        except Exception as creator_err:
            logger.error(
                f"[COMMITMENT_CLEANUP] Error for {creator_name}: {creator_err}"
            )

    if total_expired > 0:
        logger.info(
            f"[COMMITMENT_CLEANUP] Expired {total_expired} overdue "
            f"commitments across {len(creators)} creators"
        )


# --- Style recalculation (30 days) ---
async def style_recalc_job():
    enable = os.getenv("ENABLE_STYLE_RECALC", "true").lower() == "true"
    if not enable:
        logger.debug("[STYLE_RECALC] Disabled via ENABLE_STYLE_RECALC, skipping")
        return
    from api.database import SessionLocal
    from api.models import Creator
    from core.style_analyzer import analyze_and_persist

    session = SessionLocal()
    try:
        creators = (
            session.query(Creator.id, Creator.name)
            .filter(Creator.bot_active.is_(True))
            .all()
        )
    finally:
        session.close()

    for creator_db_id, creator_name in creators:
        try:
            result = await analyze_and_persist(
                creator_name, str(creator_db_id), force=True
            )
            if result:
                logger.info(
                    f"[STYLE_RECALC] {creator_name}: "
                    f"confidence={result.get('confidence', 0)}"
                )
        except Exception as creator_err:
            logger.error(
                f"[STYLE_RECALC] Error for {creator_name}: {creator_err}"
            )
        await asyncio.sleep(60)  # Stagger between creators


def register_ai_jobs(scheduler):
    """Register all AI/ML scheduled jobs with the task scheduler."""
    scheduler.register("copilot_daily_eval", copilot_daily_eval_job, interval_seconds=86400, initial_delay_seconds=420)
    scheduler.register("copilot_weekly_recal", copilot_weekly_recal_job, interval_seconds=604800, initial_delay_seconds=450)
    scheduler.register("learning_consolidation", learning_consolidation_job, interval_seconds=86400, initial_delay_seconds=510)
    scheduler.register("pattern_analyzer", pattern_analyzer_job, interval_seconds=43200, initial_delay_seconds=540)
    scheduler.register("gold_examples", gold_examples_job, interval_seconds=43200, initial_delay_seconds=570)
    scheduler.register("clone_score_daily", clone_score_daily_job, interval_seconds=86400, initial_delay_seconds=600)
    scheduler.register("memory_decay", memory_decay_job, interval_seconds=86400, initial_delay_seconds=630)
    scheduler.register("commitment_cleanup", commitment_cleanup_job, interval_seconds=86400, initial_delay_seconds=660)
    scheduler.register("style_recalc", style_recalc_job, interval_seconds=2592000, initial_delay_seconds=690)
