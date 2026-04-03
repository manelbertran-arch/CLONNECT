"""
Pattern Analyzer — LLM-as-Judge batch recognition of recurring patterns in preference pairs.

Analyzes accumulated preference pairs grouped by (intent, lead_stage) to find
recurring patterns (3+ pairs) and extracts high-confidence learning rules.

Feature flag: ENABLE_PATTERN_ANALYZER (default false)
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

PATTERN_ANALYSIS_MIN_PAIRS = int(os.getenv("PATTERN_ANALYSIS_MIN_PAIRS", "3"))
PATTERN_ANALYSIS_MAX_PAIRS_PER_GROUP = 10
PATTERN_ANALYSIS_MAX_CHARS = 300

_PATTERN_SYSTEM_PROMPT = (
    "You are a preference-pattern analyst for DM conversations. "
    "You identify recurring rules from CHOSEN/REJECTED pairs. "
    "Output rule_text, example_bad, and example_good in the SAME LANGUAGE "
    "as the creator's responses (auto-detect from the pairs). "
    "Respond ONLY with valid JSON."
)


def _format_pair(pair) -> str:
    """Format a single preference pair for the judge prompt."""
    chosen = (pair.chosen or "")[:PATTERN_ANALYSIS_MAX_CHARS]
    rejected = (pair.rejected or "")[:PATTERN_ANALYSIS_MAX_CHARS]
    parts = []
    if chosen:
        parts.append(f"  CHOSEN: \"{chosen}\"")
    if rejected:
        parts.append(f"  REJECTED: \"{rejected}\"")
    if pair.action_type:
        parts.append(f"  ACTION: {pair.action_type}")
    return "\n".join(parts)


def _build_judge_prompt(pairs, intent: str, lead_stage: str) -> str:
    """Build the LLM judge prompt for pattern analysis."""
    formatted = []
    for i, pair in enumerate(pairs[:PATTERN_ANALYSIS_MAX_PAIRS_PER_GROUP], 1):
        formatted.append(f"Pair {i}:\n{_format_pair(pair)}")

    pairs_text = "\n\n".join(formatted)

    return f"""Analyze these {len(formatted)} preference pairs from the creator.
Each pair shows: CHOSEN (what they preferred) vs REJECTED (what they didn't want).

{pairs_text}

Context: intent={intent or 'general'}, lead_stage={lead_stage or 'unknown'}

Find RECURRING PATTERNS in 2+ pairs. Respond ONLY with a valid JSON array:
[{{"rule_text": "concise rule in the SAME LANGUAGE as the creator's responses", "pattern": "{intent or 'general'}", "example_bad": "short example of what NOT to do", "example_good": "short example of what TO do", "evidence_count": N}}]

IMPORTANT: Write rule_text, example_bad, and example_good in the same language as the creator's CHOSEN/REJECTED texts.
If no clear patterns, respond: []
IMPORTANT: Only JSON, no additional text."""


def _persist_run_sync(creator_db_id, result: Dict[str, Any]) -> None:
    """Insert one row into pattern_analysis_runs for audit trail (sync)."""
    from api.database import SessionLocal
    from api.models import PatternAnalysisRun

    s = SessionLocal()
    try:
        run = PatternAnalysisRun(
            creator_id=creator_db_id,
            status=result.get("status", "error"),
            pairs_analyzed=result.get("pairs_analyzed", 0),
            rules_created=result.get("rules_created", 0),
            groups_processed=result.get("groups_processed", 0),
            details=result,
        )
        s.add(run)
        s.commit()
    finally:
        s.close()


async def _persist_run(creator_db_id, result: Dict[str, Any]) -> None:
    """Insert one row into pattern_analysis_runs for audit trail."""
    try:
        await asyncio.to_thread(_persist_run_sync, creator_db_id, result)
    except Exception as e:
        logger.warning("[PATTERN] Failed to persist run record: %s", e)


async def run_pattern_analysis(creator_id: str, creator_db_id) -> Dict[str, Any]:
    """Analyze unprocessed preference pairs for a single creator.

    Returns dict with status, rules_created, pairs_analyzed counts.
    Persists a run record to pattern_analysis_runs for audit trail.
    """
    from api.database import SessionLocal
    from api.models import PreferencePair

    session = SessionLocal()
    try:
        # Load unanalyzed pairs
        pairs = (
            session.query(PreferencePair)
            .filter(
                PreferencePair.creator_id == creator_db_id,
                PreferencePair.batch_analyzed_at.is_(None),
            )
            .order_by(PreferencePair.created_at.desc())
            .limit(100)
            .all()
        )

        if len(pairs) < PATTERN_ANALYSIS_MIN_PAIRS:
            result = {
                "status": "skipped",
                "reason": f"Only {len(pairs)} unanalyzed pairs (min: {PATTERN_ANALYSIS_MIN_PAIRS})",
                "pairs_available": len(pairs),
            }
            await _persist_run(creator_db_id, result)
            return result

        # Group by (intent, lead_stage)
        groups: Dict[str, List] = {}
        for pair in pairs:
            key = f"{pair.intent or 'general'}:{pair.lead_stage or 'unknown'}"
            groups.setdefault(key, []).append(pair)

        total_rules = 0
        total_pairs_analyzed = 0
        pair_ids_analyzed = []

        for group_key, group_pairs in groups.items():
            if len(group_pairs) < PATTERN_ANALYSIS_MIN_PAIRS:
                continue

            intent, lead_stage = group_key.split(":", 1)

            # Build and call LLM judge
            prompt = _build_judge_prompt(group_pairs, intent, lead_stage)
            rules_data = await _call_judge(prompt)

            if rules_data:
                from services.learning_rules_service import create_rule, sanitize_rule_text

                for rule_data in rules_data:
                    rule_text = sanitize_rule_text(rule_data.get("rule_text", ""))
                    if not rule_text:
                        continue
                    evidence = rule_data.get("evidence_count", 2)
                    confidence = min(0.9, 0.5 + (evidence * 0.1))
                    result = create_rule(
                        creator_id=creator_db_id,
                        rule_text=rule_text,
                        pattern=rule_data.get("pattern", intent),
                        example_bad=rule_data.get("example_bad"),
                        example_good=rule_data.get("example_good"),
                        confidence=confidence,
                        source="pattern_batch",
                    )
                    if result:
                        total_rules += 1

            # Mark pairs as analyzed
            for pair in group_pairs:
                pair_ids_analyzed.append(pair.id)
            total_pairs_analyzed += len(group_pairs)

        # Bulk mark analyzed
        if pair_ids_analyzed:
            now = datetime.now(timezone.utc)
            (
                session.query(PreferencePair)
                .filter(PreferencePair.id.in_(pair_ids_analyzed))
                .update({"batch_analyzed_at": now}, synchronize_session=False)
            )
            session.commit()

        result = {
            "status": "done",
            "pairs_analyzed": total_pairs_analyzed,
            "rules_created": total_rules,
            "groups_processed": len([g for g in groups.values() if len(g) >= PATTERN_ANALYSIS_MIN_PAIRS]),
        }
        logger.info(
            "[PATTERN] %s: analyzed=%d pairs, created=%d rules from %d groups",
            creator_id, total_pairs_analyzed, total_rules, len(groups),
        )
        await _persist_run(creator_db_id, result)
        return result

    except Exception as e:
        logger.error("[PATTERN] run_pattern_analysis error for %s: %s", creator_id, e)
        session.rollback()
        result = {"status": "error", "error": str(e)}
        await _persist_run(creator_db_id, result)
        return result
    finally:
        session.close()


async def _call_judge(prompt: str) -> List[dict]:
    """Call LLM with judge prompt, parse JSON array response."""
    try:
        from core.providers.gemini_provider import generate_simple

        result = await generate_simple(prompt, _PATTERN_SYSTEM_PROMPT, max_tokens=500)
        if not result:
            return []

        # Extract JSON from response (may have markdown fences)
        text = result.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [r for r in parsed if isinstance(r, dict) and r.get("rule_text")]
        return []

    except (json.JSONDecodeError, Exception) as e:
        logger.debug("[PATTERN] Judge parse error: %s", e)
        return []


async def run_pattern_analysis_all() -> Dict[str, Any]:
    """Run pattern analysis for all active creators. Used by background job."""
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

    results = {}
    for creator_db_id, creator_name in creators:
        try:
            result = await run_pattern_analysis(creator_name, creator_db_id)
            if result.get("status") != "skipped":
                results[creator_name] = result
        except Exception as e:
            logger.error("[PATTERN] Error for %s: %s", creator_name, e)
            results[creator_name] = {"status": "error", "error": str(e)}

    return results
