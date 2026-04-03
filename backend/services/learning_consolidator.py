"""
Learning Consolidator — Periodic rule merging via LLM.

When a creator accumulates many rules (>threshold), this service
groups them by pattern and uses LLM to merge/deduplicate into
consolidated rules. Old rules are deactivated and superseded.

Entry point: consolidate_rules_for_creator()
"""

import asyncio
import json
import logging
import os
import re
from collections import defaultdict
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

LEARNING_CONSOLIDATION_THRESHOLD = int(
    os.getenv("LEARNING_CONSOLIDATION_THRESHOLD", "20")
)

_CONSOLIDATION_SYSTEM_PROMPT = (
    "You are a behavior-rule optimizer for a DM bot. "
    "Your job is to merge similar rules into one concise, clear rule. "
    "Write consolidated rules in the SAME LANGUAGE as the input rules."
)

_CONSOLIDATION_PROMPT_TEMPLATE = """These rules for pattern "{pattern}" overlap:

{rules_text}

Merge into 1-2 consolidated rules. Respond in JSON array:
[
  {{
    "rule_text": "Concise consolidated rule (max 100 words, SAME LANGUAGE as input rules)",
    "pattern": "{pattern}",
    "example_bad": "Example of what NOT to do",
    "example_good": "Example of what TO do"
  }}
]

IMPORTANT: Write rule_text, example_bad, and example_good in the same language as the input rules above.
Respond ONLY with the JSON array, no markdown or explanations."""


async def consolidate_rules_for_creator(
    creator_id: str,
    creator_db_id,
) -> Dict:
    """Consolidate rules for a creator if threshold is exceeded.

    Returns: {status, consolidated, deactivated} or {status: "skipped"}
    """
    from services.learning_rules_service import (
        create_rule,
        deactivate_rule,
        get_all_active_rules,
        get_rules_count,
    )

    count = get_rules_count(creator_db_id)
    if count < LEARNING_CONSOLIDATION_THRESHOLD:
        return {"status": "skipped", "active_rules": count, "threshold": LEARNING_CONSOLIDATION_THRESHOLD}

    rules = get_all_active_rules(creator_db_id)
    if not rules:
        return {"status": "skipped", "active_rules": 0}

    # Group by pattern
    groups: Dict[str, List[Dict]] = defaultdict(list)
    for rule in rules:
        groups[rule["pattern"]].append(rule)

    total_consolidated = 0
    total_deactivated = 0

    for pattern, group_rules in groups.items():
        if len(group_rules) < 3:
            continue  # Only consolidate groups with 3+ rules

        try:
            consolidated = await _consolidate_group(pattern, group_rules)
        except Exception as e:
            logger.warning("[CONSOLIDATE] Error consolidating pattern %s: %s", pattern, e)
            continue

        if not consolidated:
            continue

        # Create consolidated rules
        new_rule_ids = []
        for merged in consolidated:
            result = create_rule(
                creator_id=creator_db_id,
                rule_text=merged["rule_text"],
                pattern=merged.get("pattern", pattern),
                example_bad=merged.get("example_bad"),
                example_good=merged.get("example_good"),
                confidence=0.7,  # Consolidated rules start at higher confidence
                source="consolidation",
            )
            if result:
                new_rule_ids.append(result["id"])
                total_consolidated += 1

        # Only deactivate originals if at least one consolidated rule was created
        if not new_rule_ids:
            continue

        # Deactivate original rules, pointing to first consolidated rule
        superseded_by = new_rule_ids[0]
        for old_rule in group_rules:
            deactivate_rule(old_rule["id"], superseded_by=superseded_by)
            total_deactivated += 1

    logger.info(
        "[CONSOLIDATE] %s: consolidated=%d deactivated=%d",
        creator_id, total_consolidated, total_deactivated,
    )

    return {
        "status": "done",
        "consolidated": total_consolidated,
        "deactivated": total_deactivated,
    }


async def _consolidate_group(pattern: str, rules: List[Dict]) -> Optional[List[Dict]]:
    """Use LLM to merge a group of similar rules into 1-2 consolidated rules."""
    from core.providers.gemini_provider import generate_simple

    rules_text = ""
    for i, r in enumerate(rules, 1):
        rules_text += f"{i}. {r['rule_text']}"
        if r.get("example_bad"):
            rules_text += f"\n   NO: {r['example_bad']}"
        if r.get("example_good"):
            rules_text += f"\n   SI: {r['example_good']}"
        rules_text += "\n"

    prompt = _CONSOLIDATION_PROMPT_TEMPLATE.format(
        pattern=pattern,
        rules_text=rules_text,
    )

    try:
        result = await asyncio.wait_for(
            generate_simple(prompt, _CONSOLIDATION_SYSTEM_PROMPT, max_tokens=512, temperature=0.1),
            timeout=20.0,
        )
    except asyncio.TimeoutError:
        logger.warning(f"[CONSOLIDATE] LLM timeout for pattern {pattern}")
        return None
    except Exception as e:
        logger.warning(f"[CONSOLIDATE] LLM error for pattern {pattern}: {e}")
        return None

    if not result:
        return None

    return _parse_consolidation_response(result)


def _parse_consolidation_response(text: str) -> Optional[List[Dict]]:
    """Parse LLM JSON array response."""
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip()
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning(f"[CONSOLIDATE] Non-JSON response: {text[:200]}")
        return None

    if not isinstance(data, list):
        # Maybe LLM returned a single object
        if isinstance(data, dict) and data.get("rule_text"):
            data = [data]
        else:
            return None

    # Validate each item
    valid = []
    for item in data:
        if isinstance(item, dict) and item.get("rule_text") and item.get("pattern"):
            item["rule_text"] = item["rule_text"][:500]
            item["pattern"] = item["pattern"][:50]
            valid.append(item)

    return valid if valid else None
