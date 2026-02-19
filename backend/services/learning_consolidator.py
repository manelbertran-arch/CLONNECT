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
    "Eres un optimizador de reglas de comportamiento para un bot de DMs. "
    "Tu trabajo es fusionar reglas similares en una regla concisa y clara."
)

_CONSOLIDATION_PROMPT_TEMPLATE = """Estas reglas del patron "{pattern}" se solapan:

{rules_text}

Fusiona en 1-2 reglas consolidadas. Responde en JSON array:
[
  {{
    "rule_text": "Regla consolidada concisa (max 100 palabras)",
    "pattern": "{pattern}",
    "example_bad": "Ejemplo de lo que NO hacer",
    "example_good": "Ejemplo de lo que SI hacer"
  }}
]

Responde SOLO con el JSON array, sin markdown ni explicaciones."""


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

        consolidated = await _consolidate_group(pattern, group_rules)
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
            )
            if result:
                new_rule_ids.append(result["id"])
                total_consolidated += 1

        # Deactivate original rules, pointing to first consolidated rule
        superseded_by = new_rule_ids[0] if new_rule_ids else None
        for old_rule in group_rules:
            deactivate_rule(old_rule["id"], superseded_by=superseded_by)
            total_deactivated += 1

    logger.info(
        f"[CONSOLIDATE] {creator_id}: consolidated={total_consolidated} "
        f"deactivated={total_deactivated}"
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
