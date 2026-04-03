"""
Autolearning Analyzer — Real-time rule extraction from creator actions.

Fired as fire-and-forget after each copilot action (approve/edit/discard/manual).
Uses LLM to compare bot vs creator responses and extract learning rules.

Entry point: analyze_creator_action() — async, never raises.
"""

import asyncio
import json
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

ENABLE_AUTOLEARNING = os.getenv("ENABLE_AUTOLEARNING", "false").lower() == "true"

# Minimum edit distance to trigger LLM analysis (trivial fixes are skipped)
_MIN_EDIT_CHARS = 3

# Patterns indicating non-text responses (audio, sticker, media)
_NON_TEXT_PREFIXES = ("[🎤 Audio]", "[🏷️ Sticker]", "[📷", "[🎥", "[📎")


def _is_non_text_response(text: str) -> bool:
    """Check if a response is audio, sticker, or media (not useful for text comparison)."""
    if not text:
        return True
    return any(text.startswith(prefix) for prefix in _NON_TEXT_PREFIXES)

_ANALYSIS_SYSTEM_PROMPT = (
    "You are a correction analyzer for a DM bot. "
    "Compare the bot response with the creator's version and extract a concise rule. "
    "IMPORTANT: Write the rule_text in the SAME LANGUAGE as the creator's response."
)

_ANALYSIS_PROMPT_TEMPLATE = """The bot suggested this response:
---
{bot_response}
---

The creator {action_description}:
---
{creator_response}
---

Context: intent={intent}, lead_stage={lead_stage}

Analyze the difference and generate ONE rule as JSON:
{{
  "rule_text": "Concise instruction in the SAME LANGUAGE as the creator's response (max 100 words)",
  "pattern": "shorten_response|tone_more_casual|remove_question|add_greeting|remove_emoji|add_emoji|tone_more_formal|restructure|personalize|remove_cta|soften_pitch|complete_rewrite|other",
  "example_bad": "What the bot should NOT say (short excerpt)",
  "example_good": "What the bot SHOULD say (short excerpt)"
}}

Respond ONLY with the JSON, no markdown or explanations."""


async def analyze_creator_action(
    action: str,
    creator_id: str,
    creator_db_id,
    suggested_response: Optional[str] = None,
    final_response: Optional[str] = None,
    edit_diff: Optional[dict] = None,
    intent: Optional[str] = None,
    lead_stage: Optional[str] = None,
    relationship_type: Optional[str] = None,
    discard_reason: Optional[str] = None,
    source_message_id=None,
) -> None:
    """Fire-and-forget analysis of a creator copilot action.

    Never raises — all errors are caught and logged.
    """
    if not ENABLE_AUTOLEARNING:
        return

    try:
        if action == "approved":
            await _handle_approval(creator_db_id, intent, lead_stage)
        elif action == "edited":
            await _handle_edit(
                creator_db_id, suggested_response, final_response,
                edit_diff, intent, lead_stage, relationship_type,
                source_message_id,
            )
        elif action == "discarded":
            await _handle_discard(
                creator_db_id, suggested_response, discard_reason,
                intent, lead_stage, relationship_type, source_message_id,
            )
        elif action == "resolved_externally":
            await _handle_resolved_externally(
                creator_db_id, suggested_response, final_response,
                intent, lead_stage, relationship_type, source_message_id,
            )
        elif action == "manual_override":
            await _handle_manual_override(
                creator_db_id, suggested_response, final_response,
                intent, lead_stage, relationship_type, source_message_id,
            )
        else:
            logger.debug(f"[AUTOLEARN] Unknown action: {action}")
    except Exception as e:
        logger.warning(f"[AUTOLEARN] analyze_creator_action error: {e}")


async def _handle_approval(creator_db_id, intent, lead_stage):
    """Approval = positive signal. No LLM call — just reinforce existing rules."""
    from services.learning_rules_service import get_applicable_rules, update_rule_feedback

    rules = await asyncio.to_thread(
        get_applicable_rules, creator_db_id, intent=intent, lead_stage=lead_stage
    )
    for rule in rules:
        await asyncio.to_thread(update_rule_feedback, rule["id"], was_helpful=True)

    if rules:
        logger.debug(f"[AUTOLEARN] Approval reinforced {len(rules)} rules")


async def _handle_edit(
    creator_db_id, suggested_response, final_response,
    edit_diff, intent, lead_stage, relationship_type,
    source_message_id,
):
    """Edit = medium signal. Call LLM to extract rule from the correction."""
    if not suggested_response:
        return

    # Skip if no final response (nothing to compare)
    if not final_response:
        return

    # Skip trivial edits
    if abs(len(final_response) - len(suggested_response)) < _MIN_EDIT_CHARS:
        # Check if text actually changed meaningfully
        if suggested_response.strip().lower() == final_response.strip().lower():
            return

    rule_data = await _llm_extract_rule(
        bot_response=suggested_response,
        creator_response=final_response,
        action_description="editó asi",
        intent=intent,
        lead_stage=lead_stage,
    )

    if rule_data:
        await asyncio.to_thread(
            _store_rule,
            creator_db_id, rule_data, confidence=0.5,
            intent=intent, lead_stage=lead_stage,
            relationship_type=relationship_type,
            source_message_id=source_message_id,
        )


async def _handle_discard(
    creator_db_id, suggested_response, discard_reason,
    intent, lead_stage, relationship_type, source_message_id,
):
    """Discard = strong signal. LLM extracts what went wrong."""
    if not suggested_response:
        return

    # Build action description
    action_desc = "descartó completamente"
    if discard_reason:
        action_desc += f" (razon: {discard_reason})"

    creator_response = discard_reason or "(el creador descartó sin escribir alternativa)"

    rule_data = await _llm_extract_rule(
        bot_response=suggested_response,
        creator_response=creator_response,
        action_description=action_desc,
        intent=intent,
        lead_stage=lead_stage,
    )

    if rule_data:
        await asyncio.to_thread(
            _store_rule,
            creator_db_id, rule_data, confidence=0.6,
            intent=intent, lead_stage=lead_stage,
            relationship_type=relationship_type,
            source_message_id=source_message_id,
        )


async def _handle_resolved_externally(
    creator_db_id, suggested_response, final_response,
    intent, lead_stage, relationship_type, source_message_id,
):
    """Resolved externally = highest signal. Creator replied from app without seeing bot suggestion."""
    if not suggested_response and not final_response:
        return

    bot_text = suggested_response or "(no habia sugerencia del bot)"
    creator_text = final_response or "(el creador respondió directamente desde la app)"

    # Skip audio/sticker/media — bot vs audio is not a meaningful comparison
    if _is_non_text_response(creator_text):
        logger.debug("[AUTOLEARN] Skipping resolved_externally: creator response is audio/sticker/media")
        return

    rule_data = await _llm_extract_rule(
        bot_response=bot_text,
        creator_response=creator_text,
        action_description="ignoró la sugerencia del bot y respondió directamente desde la app",
        intent=intent,
        lead_stage=lead_stage,
    )

    if rule_data:
        await asyncio.to_thread(
            _store_rule,
            creator_db_id, rule_data, confidence=0.7,
            intent=intent, lead_stage=lead_stage,
            relationship_type=relationship_type,
            source_message_id=source_message_id,
            source="divergence",
        )


async def _handle_manual_override(
    creator_db_id, suggested_response, final_response,
    intent, lead_stage, relationship_type, source_message_id,
):
    """Manual override = strongest signal. Creator wrote from scratch."""
    if not suggested_response and not final_response:
        return

    bot_text = suggested_response or "(no habia sugerencia del bot)"
    creator_text = final_response or "(el creador escribió manualmente)"

    # Skip audio/sticker/media — not useful for text comparison
    if _is_non_text_response(creator_text):
        logger.debug("[AUTOLEARN] Skipping manual_override: creator response is audio/sticker/media")
        return

    rule_data = await _llm_extract_rule(
        bot_response=bot_text,
        creator_response=creator_text,
        action_description="reemplazó escribiendo manualmente",
        intent=intent,
        lead_stage=lead_stage,
    )

    if rule_data:
        await asyncio.to_thread(
            _store_rule,
            creator_db_id, rule_data, confidence=0.65,
            intent=intent, lead_stage=lead_stage,
            relationship_type=relationship_type,
            source_message_id=source_message_id,
        )


async def _llm_extract_rule(
    bot_response: str,
    creator_response: str,
    action_description: str,
    intent: Optional[str],
    lead_stage: Optional[str],
) -> Optional[dict]:
    """Call LLM to extract a learning rule from the bot vs creator comparison."""
    from core.providers.gemini_provider import generate_simple

    prompt = _ANALYSIS_PROMPT_TEMPLATE.format(
        bot_response=bot_response[:500],
        creator_response=creator_response[:500],
        action_description=action_description,
        intent=intent or "unknown",
        lead_stage=lead_stage or "unknown",
    )

    try:
        result = await asyncio.wait_for(
            generate_simple(prompt, _ANALYSIS_SYSTEM_PROMPT, max_tokens=512, temperature=0.1),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        logger.warning("[AUTOLEARN] LLM timeout (15s)")
        return None
    except Exception as e:
        logger.warning(f"[AUTOLEARN] LLM call failed: {e}")
        return None

    if not result:
        return None

    return _parse_llm_response(result)


def _parse_llm_response(text: str) -> Optional[dict]:
    """Parse LLM JSON response, handling markdown fences."""
    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip()
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(f"[AUTOLEARN] LLM returned non-JSON: {text[:200]}")
        return None

    # Validate required fields
    if not isinstance(data, dict):
        return None
    if not data.get("rule_text") or not data.get("pattern"):
        logger.warning(f"[AUTOLEARN] Missing required fields: {data}")
        return None

    # Truncate rule_text if too long
    data["rule_text"] = data["rule_text"][:500]
    data["pattern"] = data["pattern"][:50]

    # Sanitize: reject rules that look like prompt injection attempts
    rule_lower = data["rule_text"].lower()
    _INJECTION_MARKERS = ("ignore all", "ignore previous", "system:", "assistant:", "```", "\\n\\n")
    if any(marker in rule_lower for marker in _INJECTION_MARKERS):
        logger.warning(f"[AUTOLEARN] Rejected rule with injection marker: {data['rule_text'][:100]}")
        return None

    return data


def _store_rule(
    creator_db_id, rule_data: dict, confidence: float,
    intent=None, lead_stage=None, relationship_type=None,
    source_message_id=None, source: str = "realtime",
):
    """Store the extracted rule via learning_rules_service."""
    from services.learning_rules_service import create_rule

    applies_to_message_types = [intent] if intent else []
    applies_to_lead_stages = [lead_stage] if lead_stage else []
    applies_to_relationship_types = [relationship_type] if relationship_type else []

    create_rule(
        creator_id=creator_db_id,
        rule_text=rule_data["rule_text"],
        pattern=rule_data["pattern"],
        applies_to_message_types=applies_to_message_types,
        applies_to_lead_stages=applies_to_lead_stages,
        applies_to_relationship_types=applies_to_relationship_types,
        example_bad=rule_data.get("example_bad"),
        example_good=rule_data.get("example_good"),
        confidence=confidence,
        source_message_id=source_message_id,
        source=source,
    )
