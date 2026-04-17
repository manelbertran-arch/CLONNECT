"""
PersonaCompiler (System B) — Compiles accumulated feedback signals into Doc D persona updates.

Absorbs logic from:
  - core/autolearning_evaluator.py (daily/weekly evaluation)
  - services/pattern_analyzer.py (LLM judge, pair formatting, audit trail)
  - services/autolearning_analyzer.py (LLM response parsing)
  - services/learning_rules_service.py (sanitization, contradiction detection)
  - services/learning_consolidator.py (rule consolidation)
  - services/gold_examples_service.py (language detection)

Pipeline: collect signals → categorize evidence → LLM-compile Doc D sections → diff & apply → persist.

Feature flag: ENABLE_PERSONA_COMPILER (default false)
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENABLE_PERSONA_COMPILER = os.getenv("ENABLE_PERSONA_COMPILER", "false").lower() == "true"
PERSONA_COMPILER_MIN_EVIDENCE = int(os.getenv("PERSONA_COMPILER_MIN_EVIDENCE", "3"))
PERSONA_COMPILER_MAX_EVIDENCE_PER_CATEGORY = 10

_BEHAVIORAL_CATEGORIES = [
    "tone", "length", "emoji", "questions", "cta",
    "structure", "personalization", "greetings", "language_mix",
]

# Tag format for Doc D sections managed by PersonaCompiler
_TAG_PATTERN = re.compile(
    r'\[PERSONA_COMPILER:(\w+)\](.*?)\[/PERSONA_COMPILER:\1\]', re.DOTALL
)

# Max chars per pair for LLM context
PATTERN_ANALYSIS_MAX_CHARS = 300

# Session boundary: 4h gap
_SESSION_GAP_HOURS = 4

# Compilation prompt template (from spec)
_COMPILATION_PROMPT_TEMPLATE = """Current Doc D section for "{category}":
---
{current_section_text}
---

New evidence from {evidence_count} creator corrections:
{formatted_evidence}

Generate an UPDATED section that:
1. Preserves valid existing instructions
2. Integrates new patterns naturally
3. Resolves contradictions (newer evidence wins if evidence_count >= 3)
4. Writes in the SAME LANGUAGE as the creator's responses
5. Max 150 words
6. Imperative mood ("Responde brevemente", not "El bot debería...")

Output ONLY the updated section text, no JSON or markdown."""

_COMPILATION_SYSTEM_PROMPT = (
    "You are a persona compiler that updates creator persona descriptions "
    "based on observed behavior patterns. Write concise, actionable instructions "
    "in the same language as the creator's responses. Output ONLY the section text."
)

# ---------------------------------------------------------------------------
# Reused: Language detection (from gold_examples_service.py)
# ---------------------------------------------------------------------------

_CA_WORDS = re.compile(
    r'\b(vaig|però|molt|avui|demà|tinc|estic|puc|podem|que fas|que et|que em|'
    r'gràcies|fins|dilluns|dimarts|dimecres|dijous|divendres|dissabte|diumenge|'
    r'doncs|ara|anem|hem|heu|han|venir|vine|vindràs|bon dia|bona)\b',
    re.IGNORECASE,
)
_ES_WORDS = re.compile(
    r'\b(tengo|tienes|tiene|tenemos|pero|muy|mucho|estoy|estás|estamos|'
    r'soy|eres|fue|fui|hoy|mañana|gracias|señor|señora|buenas|buenos|'
    r'qué tal|cómo estás|hasta luego|me llamo|me ha|lo que|lo sé)\b',
    re.IGNORECASE,
)
_ES_TILDE_N = re.compile(r'[ñÑ]')


def detect_language(text: str) -> str:
    """Detect language of text. Returns 'ca', 'es', 'mixto', or 'unknown'."""
    ca = len(_CA_WORDS.findall(text))
    es = len(_ES_WORDS.findall(text)) + len(_ES_TILDE_N.findall(text))
    if ca > 0 and es > 0:
        return "mixto"
    if ca > 0:
        return "ca"
    if es > 0:
        return "es"
    return "unknown"


# ---------------------------------------------------------------------------
# Absorbed from autolearning_analyzer (real-time path removed, batch-only now)
# ---------------------------------------------------------------------------

_NON_TEXT_PREFIXES = ("[🎤 Audio]", "[🏷️ Sticker]", "[📷", "[🎥", "[📎")


def _is_non_text_response(text: str) -> bool:
    """Check if a response is audio, sticker, or media."""
    if not text:
        return True
    return any(text.startswith(prefix) for prefix in _NON_TEXT_PREFIXES)


async def analyze_creator_action(**kwargs) -> None:
    """No-op: real-time rule extraction removed. System B is batch-only now."""
    logger.debug("[AUTOLEARN] analyze_creator_action is a no-op (batch-only mode)")


# ---------------------------------------------------------------------------
# Reused: Sanitization (from learning_rules_service.py)
# ---------------------------------------------------------------------------

_MAX_RULE_TEXT_LENGTH = 500

_INJECTION_PATTERNS = re.compile(
    r"(?i)"
    r"(ignore\s+(all\s+)?previous\s+instructions?"
    r"|you\s+are\s+now"
    r"|system\s*:"
    r"|assistant\s*:"
    r"|<\s*/?\s*(?:system|instructions?|prompt|role)\s*>)",
)

# Contradiction keyword pairs: (positive_keywords, negative_keywords)
_CONTRADICTION_PAIRS = [
    (["usa ", "incluye", "incluir", "añade", "añadir", "utiliza", "usar"],
     ["no uses", "no incluyas", "no incluir", "evita", "evitar", "no utilices", "no usar", "elimina"]),
    (["breve", "corto", "corta", "conciso"],
     ["largo", "detallado", "extenso", "explica bien", "elabora"]),
    (["emoji", "emojis", "emoticono"],
     ["sin emoji", "no emoji", "evita emoji", "no uses emoji"]),
    (["formal", "usted"],
     ["informal", "coloquial", "casual", "tú"]),
    (["pregunta", "pregunta abierta"],
     ["no preguntes", "sin pregunta", "evita preguntar"]),
]


def sanitize_rule_text(text: str) -> str:
    """Strip prompt injection patterns and enforce max length."""
    if not text:
        return ""
    cleaned = _INJECTION_PATTERNS.sub("", text).strip()
    if len(cleaned) > _MAX_RULE_TEXT_LENGTH:
        cleaned = cleaned[:_MAX_RULE_TEXT_LENGTH].rsplit(" ", 1)[0]
    return cleaned


def filter_contradictions(rules: List[Dict]) -> List[Dict]:
    """Remove contradictory rules — keep the one with higher confidence."""
    if len(rules) <= 1:
        return rules

    to_remove = set()
    for i, r1 in enumerate(rules):
        if i in to_remove:
            continue
        t1 = r1["rule_text"].lower()
        for j, r2 in enumerate(rules):
            if j <= i or j in to_remove:
                continue
            t2 = r2["rule_text"].lower()
            for positives, negatives in _CONTRADICTION_PAIRS:
                r1_pos = any(kw in t1 for kw in positives)
                r1_neg = any(kw in t1 for kw in negatives)
                r2_pos = any(kw in t2 for kw in positives)
                r2_neg = any(kw in t2 for kw in negatives)
                if (r1_pos and r2_neg) or (r1_neg and r2_pos):
                    loser = j if r1["confidence"] >= r2["confidence"] else i
                    to_remove.add(loser)
                    logger.info(
                        f"[PERSONA] Contradiction filtered: "
                        f"kept={'r1' if loser == j else 'r2'} "
                        f"({rules[loser]['rule_text'][:60]}...)"
                    )
                    break

    return [r for idx, r in enumerate(rules) if idx not in to_remove]


# ---------------------------------------------------------------------------
# Reused: LLM response parsing (from autolearning_analyzer.py)
# ---------------------------------------------------------------------------

def _parse_llm_response(text: str) -> Optional[dict]:
    """Parse LLM JSON response, handling markdown fences."""
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip()
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(f"[PERSONA] LLM returned non-JSON: {text[:200]}")
        return None

    if not isinstance(data, dict):
        return None
    if not data.get("rule_text") or not data.get("pattern"):
        logger.warning(f"[PERSONA] Missing required fields: {data}")
        return None

    data["rule_text"] = data["rule_text"][:500]
    data["pattern"] = data["pattern"][:50]

    rule_lower = data["rule_text"].lower()
    _INJECTION_MARKERS = ("ignore all", "ignore previous", "system:", "assistant:", "```", "\\n\\n")
    if any(marker in rule_lower for marker in _INJECTION_MARKERS):
        logger.warning(f"[PERSONA] Rejected rule with injection marker: {data['rule_text'][:100]}")
        return None

    return data


# ---------------------------------------------------------------------------
# Reused: Pair formatting (from pattern_analyzer.py)
# ---------------------------------------------------------------------------

def _format_pair(pair) -> str:
    """Format a single preference pair for the judge prompt."""
    chosen = (pair.chosen or "")[:PATTERN_ANALYSIS_MAX_CHARS]
    rejected = (pair.rejected or "")[:PATTERN_ANALYSIS_MAX_CHARS]
    parts = []
    if chosen:
        parts.append(f'  CHOSEN: "{chosen}"')
    if rejected:
        parts.append(f'  REJECTED: "{rejected}"')
    if pair.action_type:
        parts.append(f"  ACTION: {pair.action_type}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Reused: LLM judge call (from pattern_analyzer.py)
# ---------------------------------------------------------------------------

_PATTERN_SYSTEM_PROMPT = (
    "You are a preference-pattern analyst for DM conversations. "
    "You identify recurring rules from CHOSEN/REJECTED pairs. "
    "Output rule_text, example_bad, and example_good in the SAME LANGUAGE "
    "as the creator's responses (auto-detect from the pairs). "
    "Respond ONLY with valid JSON."
)


async def _call_judge(prompt: str) -> List[dict]:
    """Call LLM with judge prompt, parse JSON array response."""
    try:
        from core.providers.gemini_provider import generate_simple

        result = await generate_simple(prompt, _PATTERN_SYSTEM_PROMPT, max_tokens=500)
        if not result:
            return []

        text = result.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [r for r in parsed if isinstance(r, dict) and r.get("rule_text")]
        return []

    except (json.JSONDecodeError, Exception) as e:
        logger.debug("[PERSONA] Judge parse error: %s", e)
        return []


# ---------------------------------------------------------------------------
# Reused: Audit trail (from pattern_analyzer.py)
# ---------------------------------------------------------------------------

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
        logger.warning("[PERSONA] Failed to persist run record: %s", e)


# ---------------------------------------------------------------------------
# Reused: Daily/Weekly evaluation (from autolearning_evaluator.py)
# ---------------------------------------------------------------------------

async def run_daily_evaluation(creator_id: str, creator_db_id, eval_date: Optional[date] = None):
    """
    Run daily evaluation for a single creator.

    Collects all copilot actions from the past 24 hours,
    aggregates them, detects patterns, and stores the result.
    """
    from sqlalchemy import func

    from api.database import SessionLocal
    from api.models import CopilotEvaluation, Lead, Message

    if eval_date is None:
        eval_date = date.today()

    since = datetime.combine(eval_date - timedelta(days=1), datetime.min.time()).replace(tzinfo=timezone.utc)
    until = datetime.combine(eval_date, datetime.min.time()).replace(tzinfo=timezone.utc)

    session = SessionLocal()
    try:
        # Check if already evaluated
        existing = (
            session.query(CopilotEvaluation.id)
            .filter_by(creator_id=creator_db_id, eval_type="daily", eval_date=eval_date)
            .first()
        )
        if existing:
            logger.debug(f"[AUTOLEARN] Daily eval already exists for {creator_id} on {eval_date}")
            return {"skipped": True}

        # Aggregate actions
        rows = (
            session.query(
                Message.copilot_action,
                func.count().label("cnt"),
                func.avg(Message.response_time_ms).label("avg_rt"),
                func.avg(Message.confidence_score).label("avg_conf"),
            )
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator_db_id,
                Message.role == "assistant",
                Message.copilot_action.isnot(None),
                Message.created_at >= since,
                Message.created_at < until,
            )
            .group_by(Message.copilot_action)
            .all()
        )

        if not rows:
            logger.debug(f"[AUTOLEARN] No copilot actions for {creator_id} on {eval_date}")
            return {"skipped": True, "reason": "no_actions"}

        # Build metrics
        action_counts = {}
        total = 0
        avg_response_time = None
        avg_confidence = None
        for action, cnt, avg_rt, avg_conf in rows:
            action_counts[action] = cnt
            total += cnt
            if avg_rt and action != "resolved_externally":
                avg_response_time = round(float(avg_rt))
            if avg_conf:
                avg_confidence = round(float(avg_conf), 3)

        approved = action_counts.get("approved", 0)
        edited = action_counts.get("edited", 0)
        discarded = action_counts.get("discarded", 0)
        manual = action_counts.get("manual_override", 0)
        resolved_ext = action_counts.get("resolved_externally", 0)

        # Clone Accuracy
        clone_accuracy = None
        clone_accuracy_n = 0
        if resolved_ext > 0:
            sim_rows = (
                session.query(Message.msg_metadata)
                .join(Lead, Message.lead_id == Lead.id)
                .filter(
                    Lead.creator_id == creator_db_id,
                    Message.role == "assistant",
                    Message.copilot_action == "resolved_externally",
                    Message.msg_metadata.isnot(None),
                    Message.created_at >= since,
                    Message.created_at < until,
                )
                .all()
            )
            scores = [
                float(meta["similarity_score"])
                for (meta,) in sim_rows
                if isinstance(meta, dict)
                and "similarity_score" in meta
                and isinstance(meta["similarity_score"], (int, float))
                and 0 <= meta["similarity_score"] <= 1
            ]
            if scores:
                clone_accuracy = round(sum(scores) / len(scores), 3)
                clone_accuracy_n = len(scores)

        metrics = {
            "total_actions": total,
            "approved": approved,
            "edited": edited,
            "discarded": discarded,
            "manual_override": manual,
            "resolved_externally": resolved_ext,
            "approval_rate": round((approved + edited) / total, 3) if total else 0,
            "edit_rate": round(edited / total, 3) if total else 0,
            "discard_rate": round(discarded / total, 3) if total else 0,
            "avg_response_time_ms": avg_response_time,
            "avg_confidence": avg_confidence,
            "clone_accuracy": clone_accuracy,
            "clone_accuracy_n": clone_accuracy_n,
        }

        # Detect patterns from edit diffs
        patterns = _detect_daily_patterns(session, creator_db_id, since, until)

        evaluation = CopilotEvaluation(
            creator_id=creator_db_id,
            eval_type="daily",
            eval_date=eval_date,
            metrics=metrics,
            patterns=patterns,
        )
        session.add(evaluation)
        session.commit()

        logger.info(
            f"[AUTOLEARN] Daily eval for {creator_id}: "
            f"{total} actions, {metrics['approval_rate']*100:.0f}% approval, "
            f"{len(patterns)} patterns"
        )
        return {"stored": True, "metrics": metrics, "patterns": patterns}

    except Exception as e:
        logger.error(f"[AUTOLEARN] Daily eval error for {creator_id}: {e}")
        session.rollback()
        return {"error": str(e)}
    finally:
        session.close()


def _detect_daily_patterns(session, creator_db_id, since, until) -> list:
    """Detect recurring edit patterns from the day's actions."""
    from api.models import Lead, Message

    patterns = []

    diffs = (
        session.query(Message.edit_diff)
        .join(Lead, Message.lead_id == Lead.id)
        .filter(
            Lead.creator_id == creator_db_id,
            Message.copilot_action == "edited",
            Message.edit_diff.isnot(None),
            Message.created_at >= since,
            Message.created_at < until,
        )
        .all()
    )

    if not diffs:
        return patterns

    category_counts = {}
    total_diffs = 0
    total_length_delta = 0
    for (diff,) in diffs:
        if isinstance(diff, dict):
            total_diffs += 1
            total_length_delta += diff.get("length_delta", 0)
            for cat in diff.get("categories", []):
                category_counts[cat] = category_counts.get(cat, 0) + 1

    if total_diffs == 0:
        return patterns

    if category_counts.get("shortened", 0) >= total_diffs * 0.5:
        patterns.append({
            "type": "consistent_shortening",
            "frequency": round(category_counts["shortened"] / total_diffs, 2),
            "avg_delta": round(total_length_delta / total_diffs),
            "suggestion": "Reduce max_tokens or add conciseness instruction to system prompt",
        })

    if category_counts.get("removed_question", 0) >= total_diffs * 0.4:
        patterns.append({
            "type": "question_removal",
            "frequency": round(category_counts["removed_question"] / total_diffs, 2),
            "suggestion": "Reduce question frequency in system prompt",
        })

    if category_counts.get("complete_rewrite", 0) >= total_diffs * 0.3:
        patterns.append({
            "type": "high_rewrite_rate",
            "frequency": round(category_counts["complete_rewrite"] / total_diffs, 2),
            "suggestion": "Review system prompt — bot tone may not match creator style",
        })

    if category_counts.get("removed_emoji", 0) >= total_diffs * 0.4:
        patterns.append({
            "type": "emoji_removal",
            "frequency": round(category_counts["removed_emoji"] / total_diffs, 2),
            "suggestion": "Reduce emoji usage in system prompt",
        })

    return patterns


async def run_weekly_recalibration(creator_id: str, creator_db_id, week_end: Optional[date] = None):
    """
    Run weekly recalibration for a creator.

    Analyzes the last 7 daily evaluations, detects trends,
    and generates confidence threshold recommendations.
    After storing weekly eval, triggers compile_persona() if recommendations exist.
    """
    from api.database import SessionLocal
    from api.models import CopilotEvaluation

    if week_end is None:
        week_end = date.today()

    week_start = week_end - timedelta(days=7)

    session = SessionLocal()
    try:
        existing = (
            session.query(CopilotEvaluation.id)
            .filter_by(creator_id=creator_db_id, eval_type="weekly", eval_date=week_end)
            .first()
        )
        if existing:
            return {"skipped": True}

        daily_evals = (
            session.query(CopilotEvaluation)
            .filter(
                CopilotEvaluation.creator_id == creator_db_id,
                CopilotEvaluation.eval_type == "daily",
                CopilotEvaluation.eval_date >= week_start,
                CopilotEvaluation.eval_date <= week_end,
            )
            .order_by(CopilotEvaluation.eval_date)
            .all()
        )

        if len(daily_evals) < 3:
            logger.debug(f"[AUTOLEARN] Not enough daily evals for weekly ({len(daily_evals)}/3)")
            return {"skipped": True, "reason": "insufficient_data"}

        total_actions = sum(e.metrics.get("total_actions", 0) for e in daily_evals)
        if total_actions == 0:
            return {"skipped": True, "reason": "no_actions"}

        approval_rates = [e.metrics.get("approval_rate", 0) for e in daily_evals if e.metrics.get("total_actions", 0) > 0]
        edit_rates = [e.metrics.get("edit_rate", 0) for e in daily_evals if e.metrics.get("total_actions", 0) > 0]
        discard_rates = [e.metrics.get("discard_rate", 0) for e in daily_evals if e.metrics.get("total_actions", 0) > 0]

        clone_scores = [
            e.metrics.get("clone_accuracy")
            for e in daily_evals
            if e.metrics.get("clone_accuracy") is not None
        ]
        avg_clone_accuracy = round(sum(clone_scores) / len(clone_scores), 3) if clone_scores else None

        metrics = {
            "total_actions": total_actions,
            "days_with_data": len(daily_evals),
            "avg_approval_rate": round(sum(approval_rates) / len(approval_rates), 3) if approval_rates else 0,
            "avg_edit_rate": round(sum(edit_rates) / len(edit_rates), 3) if edit_rates else 0,
            "avg_discard_rate": round(sum(discard_rates) / len(discard_rates), 3) if discard_rates else 0,
            "avg_clone_accuracy": avg_clone_accuracy,
            "clone_accuracy_days": len(clone_scores),
        }

        recommendations = _generate_weekly_recommendations(daily_evals, metrics)

        all_patterns = []
        for ev in daily_evals:
            if ev.patterns:
                all_patterns.extend(ev.patterns)

        pattern_summary = {}
        for p in all_patterns:
            ptype = p.get("type", "unknown")
            if ptype not in pattern_summary:
                pattern_summary[ptype] = {"count": 0, "suggestion": p.get("suggestion", "")}
            pattern_summary[ptype]["count"] += 1

        weekly_eval = CopilotEvaluation(
            creator_id=creator_db_id,
            eval_type="weekly",
            eval_date=week_end,
            metrics=metrics,
            patterns=list(pattern_summary.values()) if pattern_summary else None,
            recommendations=recommendations,
        )
        session.add(weekly_eval)
        session.commit()

        clone_str = f"{avg_clone_accuracy*100:.0f}%" if avg_clone_accuracy is not None else "n/a"
        logger.info(
            f"[AUTOLEARN] Weekly recalibration for {creator_id}: "
            f"{total_actions} actions, clone_accuracy={clone_str}, "
            f"approval={metrics['avg_approval_rate']*100:.0f}%, "
            f"{len(recommendations)} recommendations"
        )

        # NEW: Trigger compile_persona if recommendations exist (TextGrad pattern)
        if recommendations and ENABLE_PERSONA_COMPILER:
            try:
                asyncio.create_task(compile_persona(creator_id, creator_db_id))
                logger.info(f"[PERSONA] Triggered compilation for {creator_id} after weekly recalibration")
            except Exception as comp_err:
                logger.error(f"[PERSONA] compile_persona trigger failed for {creator_id}: {comp_err}")

        return {"stored": True, "metrics": metrics, "recommendations": recommendations}

    except Exception as e:
        logger.error(f"[AUTOLEARN] Weekly recalibration error for {creator_id}: {e}")
        session.rollback()
        return {"error": str(e)}
    finally:
        session.close()


def _generate_weekly_recommendations(daily_evals, metrics: dict) -> list:
    """Generate actionable recommendations based on weekly patterns."""
    recommendations = []

    avg_approval = metrics.get("avg_approval_rate", 0)
    avg_edit = metrics.get("avg_edit_rate", 0)
    avg_discard = metrics.get("avg_discard_rate", 0)
    avg_clone = metrics.get("avg_clone_accuracy")

    if len(daily_evals) >= 3:
        first_half = daily_evals[: len(daily_evals) // 2]
        second_half = daily_evals[len(daily_evals) // 2:]

        first_clone = [e.metrics.get("clone_accuracy") for e in first_half if e.metrics.get("clone_accuracy") is not None]
        second_clone = [e.metrics.get("clone_accuracy") for e in second_half if e.metrics.get("clone_accuracy") is not None]
        if first_clone and second_clone:
            fc_avg = sum(first_clone) / len(first_clone)
            sc_avg = sum(second_clone) / len(second_clone)
            if sc_avg > fc_avg + 0.05:
                recommendations.append({
                    "type": "clone_accuracy_improving",
                    "detail": f"Clone accuracy improved {fc_avg*100:.0f}% → {sc_avg*100:.0f}%",
                    "action": "none",
                })
            elif fc_avg > sc_avg + 0.05:
                recommendations.append({
                    "type": "clone_accuracy_degrading",
                    "detail": f"Clone accuracy dropped {fc_avg*100:.0f}% → {sc_avg*100:.0f}%",
                    "action": "review_system_prompt",
                })

        first_approval = sum(
            e.metrics.get("approval_rate", 0) for e in first_half
            if e.metrics.get("total_actions", 0) > 0
        ) / max(1, len(first_half))
        second_approval = sum(
            e.metrics.get("approval_rate", 0) for e in second_half
            if e.metrics.get("total_actions", 0) > 0
        ) / max(1, len(second_half))

        if second_approval > first_approval + 0.1:
            recommendations.append({
                "type": "improving_trend",
                "detail": f"Approval rate improved from {first_approval*100:.0f}% to {second_approval*100:.0f}%",
                "action": "none",
            })
        elif first_approval > second_approval + 0.1:
            recommendations.append({
                "type": "degrading_trend",
                "detail": f"Approval rate dropped from {first_approval*100:.0f}% to {second_approval*100:.0f}%",
                "action": "review_system_prompt",
            })

    if avg_discard > 0.4:
        recommendations.append({
            "type": "high_discard_rate",
            "detail": f"Discard rate is {avg_discard*100:.0f}% — bot responses often off-target",
            "action": "review_system_prompt",
        })

    if avg_edit > 0.5:
        recommendations.append({
            "type": "high_edit_rate",
            "detail": f"Edit rate is {avg_edit*100:.0f}% — bot tone needs tuning",
            "action": "adjust_tone_profile",
        })

    if avg_approval > 0.85 and metrics.get("total_actions", 0) >= 20:
        recommendations.append({
            "type": "high_performance",
            "detail": f"Approval rate is {avg_approval*100:.0f}% — consider switching to auto mode",
            "action": "suggest_auto_mode",
        })

    return recommendations


# ---------------------------------------------------------------------------
# NEW: Signal collection
# ---------------------------------------------------------------------------

def _collect_signals(session, creator_db_id, since: datetime) -> Dict[str, List]:
    """Read unprocessed preference_pairs + recent evaluator_feedback + copilot_evaluations."""
    from api.models import CopilotEvaluation, EvaluatorFeedback, PreferencePair

    # Unprocessed preference pairs
    pairs = (
        session.query(PreferencePair)
        .filter(
            PreferencePair.creator_id == creator_db_id,
            PreferencePair.batch_analyzed_at.is_(None),
        )
        .order_by(PreferencePair.created_at.desc())
        .limit(200)
        .all()
    )

    # Recent evaluator feedback
    feedback = (
        session.query(EvaluatorFeedback)
        .filter(
            EvaluatorFeedback.creator_id == creator_db_id,
            EvaluatorFeedback.created_at >= since,
        )
        .order_by(EvaluatorFeedback.created_at.desc())
        .limit(100)
        .all()
    )

    # Recent copilot evaluations (daily/weekly)
    evaluations = (
        session.query(CopilotEvaluation)
        .filter(
            CopilotEvaluation.creator_id == creator_db_id,
            CopilotEvaluation.eval_date >= since.date(),
        )
        .order_by(CopilotEvaluation.eval_date.desc())
        .limit(14)
        .all()
    )

    return {
        "pairs": pairs,
        "feedback": feedback,
        "evaluations": evaluations,
    }


# ---------------------------------------------------------------------------
# NEW: Evidence categorization
# ---------------------------------------------------------------------------

# Map edit_diff categories → behavioral categories
_EDIT_CATEGORY_MAP = {
    "shortened": "length",
    "lengthened": "length",
    "removed_question": "questions",
    "added_question": "questions",
    "removed_emoji": "emoji",
    "added_emoji": "emoji",
    "complete_rewrite": "tone",
    "removed_cta": "cta",
    "added_cta": "cta",
    "changed_greeting": "greetings",
}


def _categorize_evidence(signals: Dict[str, List]) -> Dict[str, List[Dict]]:
    """Group signals by behavioral dimension.

    Returns: {"tone": [evidence_items], "length": [...], ...}
    Each evidence_item: {"text": str, "direction": str, "quality": float, "source": str}
    """
    categories: Dict[str, List[Dict]] = defaultdict(list)

    # Categorize from preference pairs
    for pair in signals.get("pairs", []):
        chosen = (pair.chosen or "")[:300]
        rejected = (pair.rejected or "")[:300]

        # Use edit_diff categories if available
        if pair.edit_diff and isinstance(pair.edit_diff, dict):
            for edit_cat in pair.edit_diff.get("categories", []):
                behavioral_cat = _EDIT_CATEGORY_MAP.get(edit_cat, "tone")
                direction = "less" if edit_cat.startswith("removed") or edit_cat == "shortened" else "more"
                categories[behavioral_cat].append({
                    "text": f'CHOSEN: "{chosen}" | REJECTED: "{rejected}"',
                    "direction": direction,
                    "quality": 0.8,
                    "source": f"pair_{pair.action_type}",
                })
        else:
            # Default: categorize by content analysis
            if chosen and rejected:
                # Length difference → length category
                if abs(len(chosen) - len(rejected)) > 20:
                    direction = "less" if len(chosen) < len(rejected) else "more"
                    categories["length"].append({
                        "text": f'CHOSEN: "{chosen}" | REJECTED: "{rejected}"',
                        "direction": direction,
                        "quality": 0.6,
                        "source": f"pair_{pair.action_type}",
                    })
                # Default to tone
                categories["tone"].append({
                    "text": f'CHOSEN: "{chosen}" | REJECTED: "{rejected}"',
                    "direction": "change",
                    "quality": 0.6,
                    "source": f"pair_{pair.action_type}",
                })

    # Categorize from evaluator feedback patterns
    for fb in signals.get("feedback", []):
        if fb.error_tags:
            for tag in (fb.error_tags if isinstance(fb.error_tags, list) else []):
                tag_lower = tag.lower()
                if "emoji" in tag_lower:
                    categories["emoji"].append({
                        "text": f"Error tag: {tag}",
                        "direction": "change",
                        "quality": (fb.lo_enviarias or 3) / 5.0,
                        "source": "evaluator",
                    })
                elif "tono" in tag_lower or "tone" in tag_lower:
                    categories["tone"].append({
                        "text": f"Error tag: {tag}",
                        "direction": "change",
                        "quality": (fb.lo_enviarias or 3) / 5.0,
                        "source": "evaluator",
                    })
                elif "largo" in tag_lower or "corto" in tag_lower or "length" in tag_lower:
                    categories["length"].append({
                        "text": f"Error tag: {tag}",
                        "direction": "change",
                        "quality": (fb.lo_enviarias or 3) / 5.0,
                        "source": "evaluator",
                    })

    # Categorize from daily evaluation patterns
    for ev in signals.get("evaluations", []):
        if ev.patterns:
            for pattern in ev.patterns:
                ptype = pattern.get("type", "")
                if "shortening" in ptype:
                    categories["length"].append({
                        "text": f"Daily pattern: {ptype} (freq={pattern.get('frequency', 0)})",
                        "direction": "less",
                        "quality": 0.7,
                        "source": "daily_eval",
                    })
                elif "question" in ptype:
                    categories["questions"].append({
                        "text": f"Daily pattern: {ptype} (freq={pattern.get('frequency', 0)})",
                        "direction": "less",
                        "quality": 0.7,
                        "source": "daily_eval",
                    })
                elif "emoji" in ptype:
                    categories["emoji"].append({
                        "text": f"Daily pattern: {ptype} (freq={pattern.get('frequency', 0)})",
                        "direction": "less",
                        "quality": 0.7,
                        "source": "daily_eval",
                    })
                elif "rewrite" in ptype:
                    categories["tone"].append({
                        "text": f"Daily pattern: {ptype} (freq={pattern.get('frequency', 0)})",
                        "direction": "change",
                        "quality": 0.7,
                        "source": "daily_eval",
                    })

    # Cap evidence per category
    for cat in categories:
        categories[cat] = categories[cat][:PERSONA_COMPILER_MAX_EVIDENCE_PER_CATEGORY]

    return dict(categories)


# ---------------------------------------------------------------------------
# NEW: Doc D section extraction and application
# ---------------------------------------------------------------------------

def _extract_current_sections(doc_d: str) -> Dict[str, str]:
    """Parse [PERSONA_COMPILER:*] sections from Doc D text."""
    sections = {}
    for match in _TAG_PATTERN.finditer(doc_d):
        category = match.group(1)
        content = match.group(2).strip()
        sections[category] = content
    return sections


def _apply_sections(doc_d: str, updates: Dict[str, str]) -> str:
    """Replace [PERSONA_COMPILER:*] sections in Doc D. Add new sections at end."""
    result = doc_d

    # Replace existing sections
    replaced = set()
    for category, new_text in updates.items():
        tag_re = re.compile(
            rf'\[PERSONA_COMPILER:{re.escape(category)}\].*?\[/PERSONA_COMPILER:{re.escape(category)}\]',
            re.DOTALL,
        )
        new_block = f"[PERSONA_COMPILER:{category}]\n{new_text}\n[/PERSONA_COMPILER:{category}]"
        if tag_re.search(result):
            result = tag_re.sub(new_block, result)
            replaced.add(category)

    # Add new sections at end
    new_sections = []
    for category, new_text in updates.items():
        if category not in replaced:
            new_sections.append(f"\n[PERSONA_COMPILER:{category}]\n{new_text}\n[/PERSONA_COMPILER:{category}]")

    if new_sections:
        result = result.rstrip() + "\n" + "\n".join(new_sections) + "\n"

    return result


# ---------------------------------------------------------------------------
# NEW: LLM section compilation
# ---------------------------------------------------------------------------

async def _compile_section(
    category: str,
    evidence: List[Dict],
    current_section: str,
) -> Optional[str]:
    """LLM call to generate updated Doc D section from evidence.
    Returns updated section text or None if no meaningful change."""
    # Format evidence
    formatted_lines = []
    for i, ev in enumerate(evidence[:PERSONA_COMPILER_MAX_EVIDENCE_PER_CATEGORY], 1):
        formatted_lines.append(f"{i}. [{ev['direction']}] {ev['text']} (quality={ev['quality']:.1f})")
    formatted_evidence = "\n".join(formatted_lines)

    prompt = _COMPILATION_PROMPT_TEMPLATE.format(
        category=category,
        current_section_text=current_section or "(no existing section)",
        evidence_count=len(evidence),
        formatted_evidence=formatted_evidence,
    )

    try:
        from core.providers.gemini_provider import generate_simple

        result = await generate_simple(prompt, _COMPILATION_SYSTEM_PROMPT, max_tokens=300)
        if not result:
            return None

        # Sanitize output
        section_text = sanitize_rule_text(result.strip())
        if len(section_text) < 10:
            return None

        return section_text

    except Exception as e:
        logger.error(f"[PERSONA] _compile_section error for {category}: {e}")
        return None


# ---------------------------------------------------------------------------
# NEW: Version control
# ---------------------------------------------------------------------------

def _snapshot_doc_d(
    session,
    creator_db_id,
    doc_d_text: str,
    trigger: str,
    categories_updated: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Save current Doc D to doc_d_versions before update. Returns version ID.

    SHA256 dedup: if identical content was already snapshotted for this creator
    in the last 24 hours, skip the INSERT and return the existing row's ID.
    """
    from sqlalchemy import text

    content_hash = hashlib.sha256((doc_d_text or "").encode()).hexdigest()

    # Dedup check: same hash within last 24h?
    existing = session.execute(
        text("""
            SELECT id FROM doc_d_versions
            WHERE creator_id = CAST(:cid AS uuid)
              AND content_hash = :hash
              AND created_at > now() - INTERVAL '24 hours'
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"cid": str(creator_db_id), "hash": content_hash},
    ).fetchone()

    if existing:
        return str(existing[0])

    version_id = str(uuid.uuid4())
    meta = metadata or {}

    session.execute(
        text("""
            INSERT INTO doc_d_versions
                (id, creator_id, doc_d_text, trigger, categories_updated, content_hash, metadata)
            VALUES (
                CAST(:vid AS uuid),
                CAST(:cid AS uuid),
                :doc_d,
                :trigger,
                CAST(:cats AS jsonb),
                :content_hash,
                CAST(:metadata AS jsonb)
            )
        """),
        {
            "vid": version_id,
            "cid": str(creator_db_id),
            "doc_d": doc_d_text or "",
            "trigger": trigger,
            "cats": json.dumps(categories_updated or []),
            "content_hash": content_hash,
            "metadata": json.dumps(meta),
        },
    )
    return version_id


def get_active_doc_d_version_id(session, creator_name: str) -> Optional[str]:
    """Return the latest doc_d_versions.id for a creator slug. None if none exists."""
    from sqlalchemy import text

    creator_row = session.execute(
        text("SELECT id FROM creators WHERE name = :name LIMIT 1"),
        {"name": creator_name},
    ).fetchone()

    if not creator_row:
        return None

    version_row = session.execute(
        text("""
            SELECT id FROM doc_d_versions
            WHERE creator_id = CAST(:cid AS uuid)
            ORDER BY created_at DESC
            LIMIT 1
        """),
        {"cid": str(creator_row[0])},
    ).fetchone()

    return str(version_row[0]) if version_row else None


def _get_current_doc_d(session, creator_db_id) -> str:
    """Read current Doc D from personality_docs.content (doc_type='doc_d').

    QW5 fix: the Creator ORM has no `doc_d` column; runtime stores the doc in
    personality_docs keyed by (creator_id, doc_type). Returns "" when missing.
    """
    from sqlalchemy import text

    row = session.execute(
        text(
            """
            SELECT content FROM personality_docs
            WHERE creator_id = :cid AND doc_type = 'doc_d'
            """
        ),
        {"cid": str(creator_db_id)},
    ).fetchone()
    return row[0] if row and row[0] is not None else ""


def _set_current_doc_d(session, creator_db_id, new_text: str) -> None:
    """Upsert Doc D content to personality_docs.

    Mirrors the canonical pattern in core/personality_extraction/extractor.py:366
    (INSERT … ON CONFLICT DO UPDATE). Unique constraint
    `uq_personality_docs_creator_type` guarantees single row per doc_type.
    """
    from sqlalchemy import text

    session.execute(
        text(
            """
            INSERT INTO personality_docs (id, creator_id, doc_type, content)
            VALUES (CAST(:id AS uuid), :cid, 'doc_d', :content)
            ON CONFLICT (creator_id, doc_type)
            DO UPDATE SET content = EXCLUDED.content,
                          updated_at = now()
            """
        ),
        {
            "id": str(uuid.uuid4()),
            "cid": str(creator_db_id),
            "content": new_text or "",
        },
    )


async def rollback_doc_d(creator_db_id, version_id) -> Dict:
    """Restore Doc D from a previous version snapshot."""
    from api.database import SessionLocal
    from api.models import Creator
    from sqlalchemy import text

    session = SessionLocal()
    try:
        # Fetch version
        row = session.execute(
            text("SELECT doc_d_text FROM doc_d_versions WHERE id = CAST(:vid AS uuid) AND creator_id = CAST(:cid AS uuid)"),
            {"vid": str(version_id), "cid": str(creator_db_id)},
        ).fetchone()

        if not row:
            return {"status": "error", "message": "Version not found"}

        old_text = row[0]

        # Snapshot current before rollback
        creator = session.query(Creator).filter_by(id=creator_db_id).first()
        if not creator:
            return {"status": "error", "message": "Creator not found"}

        _snapshot_doc_d(
            session,
            creator_db_id,
            _get_current_doc_d(session, creator_db_id),
            "rollback",
        )

        # Apply rollback (QW5: writes to personality_docs; Creator has no doc_d column)
        _set_current_doc_d(session, creator_db_id, old_text)
        session.commit()

        logger.info(f"[PERSONA] Rolled back Doc D for creator {creator_db_id} to version {version_id}")
        return {"status": "rolled_back", "version_id": str(version_id)}

    except Exception as e:
        logger.error(f"[PERSONA] rollback_doc_d error: {e}")
        session.rollback()
        return {"status": "error", "message": str(e)}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# MAIN ENTRY POINT: compile_persona()
# ---------------------------------------------------------------------------

async def compile_persona(creator_id: str, creator_db_id) -> Dict[str, Any]:
    """Weekly batch: analyze signals → compile Doc D updates.
    Returns {status, categories_updated, doc_d_version_id}."""
    from api.database import SessionLocal
    from api.models import Creator, PatternAnalysisRun, PreferencePair

    session = SessionLocal()
    try:
        # Step 1: Determine since when to collect
        last_run = (
            session.query(PatternAnalysisRun)
            .filter(PatternAnalysisRun.creator_id == creator_db_id)
            .order_by(PatternAnalysisRun.ran_at.desc())
            .first()
        )
        since = last_run.ran_at if last_run else (datetime.now(timezone.utc) - timedelta(days=30))

        # Step 1: Collect signals
        signals = _collect_signals(session, creator_db_id, since)

        total_evidence = len(signals.get("pairs", [])) + len(signals.get("feedback", [])) + len(signals.get("evaluations", []))
        if total_evidence < PERSONA_COMPILER_MIN_EVIDENCE:
            result = {"status": "skipped", "reason": "insufficient_evidence", "total_evidence": total_evidence}
            await _persist_run(creator_db_id, result)
            return result

        # Step 2: Categorize
        categories = _categorize_evidence(signals)

        # Step 3: Get current Doc D
        creator = session.query(Creator).filter_by(id=creator_db_id).first()
        if not creator:
            return {"status": "error", "message": "Creator not found"}

        # QW5: Doc D lives in personality_docs, not on the Creator row
        current_doc_d = _get_current_doc_d(session, creator_db_id)
        current_sections = _extract_current_sections(current_doc_d)

        # Step 4: Compile each category with enough evidence
        updates = {}
        for cat, evidence in categories.items():
            if len(evidence) >= PERSONA_COMPILER_MIN_EVIDENCE:
                new_section = await _compile_section(cat, evidence, current_sections.get(cat, ""))
                if new_section:
                    updates[cat] = new_section

        if not updates:
            result = {"status": "no_updates", "categories_analyzed": list(categories.keys())}
            await _persist_run(creator_db_id, result)
            return result

        # Step 5: Snapshot + apply + persist
        version_id = _snapshot_doc_d(session, creator_db_id, current_doc_d, "weekly_compilation", list(updates.keys()))
        new_doc_d = _apply_sections(current_doc_d, updates)
        # QW5: persist new Doc D to personality_docs (upsert by creator_id, doc_type)
        _set_current_doc_d(session, creator_db_id, new_doc_d)

        # Mark pairs as analyzed
        pair_ids = [p.id for p in signals.get("pairs", [])]
        if pair_ids:
            now = datetime.now(timezone.utc)
            session.query(PreferencePair).filter(
                PreferencePair.id.in_(pair_ids)
            ).update({"batch_analyzed_at": now}, synchronize_session=False)

        session.commit()

        result = {
            "status": "done",
            "categories_updated": list(updates.keys()),
            "doc_d_version_id": version_id,
            "pairs_analyzed": len(pair_ids),
        }
        await _persist_run(creator_db_id, result)

        logger.info(
            f"[PERSONA] Compiled persona for {creator_id}: "
            f"categories={list(updates.keys())}, pairs_analyzed={len(pair_ids)}"
        )
        return result

    except Exception as e:
        logger.error(f"[PERSONA] compile_persona error for {creator_id}: {e}")
        session.rollback()
        result = {"status": "error", "error": str(e)}
        await _persist_run(creator_db_id, result)
        return result
    finally:
        session.close()


# ---------------------------------------------------------------------------
# ALL CREATORS: compile_persona_all()
# ---------------------------------------------------------------------------

async def compile_persona_all() -> Dict[str, Any]:
    """Run persona compilation for all active creators. Used by background job."""
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
            result = await compile_persona(creator_name, creator_db_id)
            if result.get("status") != "skipped":
                results[creator_name] = result
        except Exception as e:
            logger.error("[PERSONA] Error for %s: %s", creator_name, e)
            results[creator_name] = {"status": "error", "error": str(e)}

    return results
