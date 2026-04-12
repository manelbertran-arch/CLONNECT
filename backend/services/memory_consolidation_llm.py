"""
Memory Consolidation LLM — CC-faithful LLM-powered consolidation step.

Extracted from CC's consolidationPrompt.ts Phase 3 (lines 44-52):
  "Focus on:
   - Merging new signal into existing topic files rather than creating near-duplicates
   - Converting relative dates to absolute dates
   - Deleting contradicted facts — if today's investigation disproves an old memory"

CC pattern: Multi-turn forked agent with tools operating on filesystem.
Clonnect adaptation: Single-turn LLM call with structured JSON response.

Justification for single-turn (vs CC multi-turn):
  CC needs multi-turn because the agent must discover state via filesystem tools
  (ls, cat, grep). In Clonnect, Phase 1-2 already loaded all facts into memory
  as List[_FactRow]. No discovery loop needed — we pass facts as text, get
  structured actions back.

Justification for no tools (vs CC tool-equipped agent):
  CC gives tools because the agent operates on opaque files. Clonnect has already
  parsed data into _FactRow objects — the LLM analyzes, code executes.

Feature flag: ENABLE_LLM_CONSOLIDATION (default OFF, separate from ENABLE_MEMORY_CONSOLIDATION)
Fallback: When OFF or LLM fails, algorithmic Jaccard dedup + TTL expiry runs normally.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from services.memory_consolidator import _validated_env_float, _validated_env_int

# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE FLAG + CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

ENABLE_LLM_CONSOLIDATION = (
    os.getenv("ENABLE_LLM_CONSOLIDATION", "false").lower() == "true"
)

# Max actions (dedup + contradiction + date_fix) the LLM can propose per lead
MAX_LLM_ACTIONS_PER_LEAD = _validated_env_int(
    "CONSOLIDATION_MAX_LLM_ACTIONS_PER_LEAD", 20,
)

# Max tokens for LLM response — must be large enough for structured JSON output.
# Qwen3 (even with /no_think) may produce residual <think></think> tokens that
# consume budget; 2048 gives ample room for the JSON actions payload.
LLM_CONSOLIDATION_MAX_TOKENS = _validated_env_int(
    "CONSOLIDATION_LLM_MAX_TOKENS", 2048,
)


# ═══════════════════════════════════════════════════════════════════════════════
# PROMPT — adapted from CC consolidationPrompt.ts:44-52
# CC original: "For each thing worth remembering, write or update a memory file
#   at the top level of the memory directory."
# CC original: "Merging new signal... Converting relative dates... Deleting
#   contradicted facts..."
#
# Adaptation: Instead of operating on files, the LLM receives a numbered list
# of facts and returns structured JSON with actions.
# Language-agnostic and creator-agnostic — no hardcoded names or languages.
# ═══════════════════════════════════════════════════════════════════════════════

_CONSOLIDATION_LLM_PROMPT = """You are consolidating memory facts about a person. Today is {today}.

Facts (numbered):
{facts_list}

Analyze these facts and return a JSON object with three arrays:

1. "duplicates": Facts that say the same thing in different words.
   Each entry: {{"keep": <index to keep>, "remove": <index to remove>, "reason": "<brief>"}}
   Keep the one with more detail or more recent.

2. "contradictions": Facts that contradict each other (e.g., "likes meat" vs "is vegetarian since 2024").
   Each entry: {{"remove": <index of the wrong/outdated one>, "reason": "<brief>"}}
   Remove the older or less specific one. If unsure, do NOT remove either.

3. "date_fixes": Facts with relative dates ("tomorrow", "next week", "yesterday") that should be absolute.
   Each entry: {{"index": <fact index>, "fixed_text": "<complete fact text with the relative date replaced by absolute date>"}}
   Only fix if you can determine the absolute date from context + today's date.
   Return the FULL fact text, not just the date fragment.

Rules:
- Use fact indices (0-based) as shown in the list above.
- If no actions needed for a category, return an empty array.
- If a newer fact disproves an older one, remove the outdated one. If two facts say the same thing, keep the more complete one.
- Never remove both facts in a contradiction — only the wrong/outdated one.
- Maximum {max_actions} total actions.

Return ONLY valid JSON, no explanation."""


# ═══════════════════════════════════════════════════════════════════════════════
# LLM CALL — reuses existing generate_dm_response pattern
# (from memory_engine.py:856-875, _call_llm)
# ═══════════════════════════════════════════════════════════════════════════════

async def _call_consolidation_llm(facts_text: str, today: str) -> Optional[Dict]:
    """Call LLM for consolidation analysis.

    Uses generate_dm_response (gemini_provider.py:619) — same function as the DM
    pipeline. If LLM_MODEL_NAME is set (e.g. gemma4_31b → DeepInfra), it dispatches
    to that model first. Fallback: GPT-4o-mini if primary fails.

    This mirrors CC's forked agent reusing the same model as the main agent
    (autoDream.ts:224-232, runForkedAgent).

    Returns parsed JSON dict or None on failure.
    """
    prompt = _CONSOLIDATION_LLM_PROMPT.format(
        today=today,
        facts_list=facts_text,
        max_actions=MAX_LLM_ACTIONS_PER_LEAD,
    )

    try:
        from core.providers.gemini_provider import generate_dm_response

        messages = [
            {
                "role": "system",
                "content": (
                    "You analyze memory facts for duplicates, contradictions, "
                    "and date fixes. Respond ONLY with valid JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ]
        result = await generate_dm_response(
            messages, max_tokens=LLM_CONSOLIDATION_MAX_TOKENS,
        )

        if not result or not result.get("content"):
            logger.warning("[ConsolidatorLLM] Empty response from LLM")
            return None

        return _parse_llm_response(result["content"])

    except Exception as e:
        logger.error("[ConsolidatorLLM] LLM call failed: %s", e)
        return None


def _parse_llm_response(raw: str) -> Optional[Dict]:
    """Parse JSON from LLM response, handling markdown fences and thinking tokens.

    Same pattern as MemoryEngine._parse_json_response (memory_engine.py:910-933).
    Defense-in-depth: strips <think>...</think> blocks that Qwen3 may emit even
    when /no_think is appended (residual thinking tokens). The DeepInfra provider
    already strips these (strip_thinking_artifacts), but a provider path change
    or fallback to GPT-4o-mini could skip that step.
    """
    from core.providers.deepinfra_provider import strip_thinking_artifacts
    text = strip_thinking_artifacts(raw).strip()

    # Strip markdown fences
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try extracting JSON object from surrounding text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

    logger.warning("[ConsolidatorLLM] Failed to parse JSON: %s", text[:200])
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATION — sanitize LLM output before applying
# ═══════════════════════════════════════════════════════════════════════════════

def _validate_llm_actions(
    actions: Dict, num_facts: int,
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """Validate and sanitize LLM response.

    Returns (duplicates, contradictions, date_fixes) — each list contains
    only valid, in-range entries. Invalid entries are silently dropped.
    """
    def _valid_index(idx: Any) -> bool:
        return isinstance(idx, int) and 0 <= idx < num_facts

    duplicates = []
    for d in actions.get("duplicates", []):
        if (isinstance(d, dict)
                and _valid_index(d.get("keep"))
                and _valid_index(d.get("remove"))
                and d["keep"] != d["remove"]):
            duplicates.append(d)

    contradictions = []
    for c in actions.get("contradictions", []):
        if isinstance(c, dict) and _valid_index(c.get("remove")):
            contradictions.append(c)

    date_fixes = []
    for f in actions.get("date_fixes", []):
        if (isinstance(f, dict)
                and _valid_index(f.get("index"))
                and isinstance(f.get("fixed_text"), str)
                and len(f["fixed_text"].strip()) > 0):
            date_fixes.append(f)

    # Enforce max actions
    total = len(duplicates) + len(contradictions) + len(date_fixes)
    if total > MAX_LLM_ACTIONS_PER_LEAD:
        # Prioritize: contradictions > duplicates > date_fixes
        allowed = MAX_LLM_ACTIONS_PER_LEAD
        contradictions = contradictions[:allowed]
        allowed -= len(contradictions)
        duplicates = duplicates[:max(0, allowed)]
        allowed -= len(duplicates)
        date_fixes = date_fixes[:max(0, allowed)]

    return duplicates, contradictions, date_fixes


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API — called from consolidate_lead() in memory_consolidation_ops.py
# ═══════════════════════════════════════════════════════════════════════════════

async def llm_analyze_facts(
    facts: list,
) -> Optional[Tuple[List[Dict], List[Dict], List[Dict]]]:
    """Run LLM analysis on a lead's facts.

    Args:
        facts: List of _FactRow objects from memory_consolidation_ops.

    Returns:
        (duplicates, contradictions, date_fixes) or None if LLM disabled/failed.
        Each list contains dicts with indices referencing the input facts list.

    CC pattern (consolidationPrompt.ts:44-52):
      The LLM decides what to merge, what contradicts, what dates to fix.
      Code only executes the decisions.
    """
    if not ENABLE_LLM_CONSOLIDATION:
        return None

    if len(facts) < 2:
        return None

    # Build numbered facts list for the prompt
    lines = []
    for i, f in enumerate(facts):
        age = ""
        if f.created_at:
            days = (datetime.now(timezone.utc) - (
                f.created_at if f.created_at.tzinfo else f.created_at.replace(tzinfo=timezone.utc)
            )).days
            age = f" ({days}d ago)"
        lines.append(f"[{i}] [{f.fact_type}]{age} {f.fact_text}")

    facts_text = "\n".join(lines)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    raw_actions = await _call_consolidation_llm(facts_text, today)
    if raw_actions is None:
        return None

    duplicates, contradictions, date_fixes = _validate_llm_actions(
        raw_actions, len(facts),
    )

    total = len(duplicates) + len(contradictions) + len(date_fixes)
    if total > 0:
        logger.info(
            "[ConsolidatorLLM] Proposed: %d dupes, %d contradictions, %d date_fixes",
            len(duplicates), len(contradictions), len(date_fixes),
        )

    return duplicates, contradictions, date_fixes


async def apply_date_fixes(
    facts: list, date_fixes: List[Dict],
) -> int:
    """Apply date fixes from LLM analysis by updating fact_text in DB.

    CC pattern (consolidationPrompt.ts:50):
      "Converting relative dates ('yesterday', 'last week') to absolute dates
       so they remain interpretable after time passes"

    Returns number of facts updated.
    """
    if not date_fixes:
        return 0

    import asyncio

    updated = 0
    for fix in date_fixes:
        idx = fix["index"]
        fact = facts[idx]
        new_text = fix["fixed_text"].strip()

        if not new_text or new_text == fact.fact_text:
            continue

        # Update in DB — LLM already rewrote the full text, no string replace needed
        try:
            def _sync():
                from api.database import SessionLocal
                from sqlalchemy import text
                session = SessionLocal()
                try:
                    session.execute(
                        text(
                            "UPDATE lead_memories SET fact_text = :text, updated_at = NOW() "
                            "WHERE id = CAST(:fid AS uuid) AND is_active = true"
                        ),
                        {"fid": fact.id, "text": new_text},
                    )
                    session.commit()
                finally:
                    session.close()

            await asyncio.to_thread(_sync)
            updated += 1
            logger.info(
                "[ConsolidatorLLM] Date fix applied for fact=%s",
                fact.id[:8],
            )
        except Exception as e:
            logger.error("[ConsolidatorLLM] Date fix DB update failed: %s", e)

    return updated
