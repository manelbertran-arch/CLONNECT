"""Tests for services/learning_consolidator.py"""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
@patch("services.learning_rules_service.get_rules_count")
async def test_below_threshold_skips(mock_count):
    """Below threshold returns skipped status."""
    from services.learning_consolidator import consolidate_rules_for_creator

    mock_count.return_value = 5  # Below default threshold of 20

    result = await consolidate_rules_for_creator("test_creator", uuid.uuid4())

    assert result["status"] == "skipped"
    assert result["active_rules"] == 5


@pytest.mark.asyncio
@patch("services.learning_rules_service.deactivate_rule")
@patch("services.learning_rules_service.create_rule")
@patch("core.providers.gemini_provider.generate_simple", new_callable=AsyncMock)
@patch("services.learning_rules_service.get_all_active_rules")
@patch("services.learning_rules_service.get_rules_count")
async def test_consolidation_merges(
    mock_count, mock_get_rules, mock_generate, mock_create, mock_deactivate,
):
    """5 rules with same pattern are consolidated into fewer rules."""
    mock_count.return_value = 25

    creator_db_id = uuid.uuid4()
    # 5 rules with same pattern
    rules = [
        {
            "id": str(uuid.uuid4()),
            "rule_text": f"Acorta la respuesta variante {i}",
            "pattern": "shorten_response",
            "confidence": 0.5,
            "times_applied": 0,
            "times_helped": 0,
            "example_bad": f"Respuesta larga {i}",
            "example_good": f"Respuesta corta {i}",
            "applies_to_relationship_types": [],
            "applies_to_message_types": [],
            "applies_to_lead_stages": [],
        }
        for i in range(5)
    ]
    mock_get_rules.return_value = rules

    # LLM returns consolidated rules
    mock_generate.return_value = json.dumps([
        {
            "rule_text": "Siempre acorta las respuestas a 1-2 frases",
            "pattern": "shorten_response",
            "example_bad": "Hola, como estas? Espero que bien, queria contarte...",
            "example_good": "Hola! Te cuento rapido...",
        },
    ])

    new_rule_id = str(uuid.uuid4())
    mock_create.return_value = {"id": new_rule_id, "deduplicated": False}

    from services.learning_consolidator import consolidate_rules_for_creator

    result = await consolidate_rules_for_creator("test_creator", creator_db_id)

    assert result["status"] == "done"
    assert result["consolidated"] == 1
    assert result["deactivated"] == 5
    mock_create.assert_called_once()
    assert mock_create.call_args[1]["confidence"] == 0.7  # Higher confidence
    assert mock_deactivate.call_count == 5


@pytest.mark.asyncio
@patch("services.learning_rules_service.deactivate_rule")
@patch("services.learning_rules_service.create_rule")
@patch("core.providers.gemini_provider.generate_simple", new_callable=AsyncMock)
@patch("services.learning_rules_service.get_all_active_rules")
@patch("services.learning_rules_service.get_rules_count")
async def test_old_rules_deactivated(
    mock_count, mock_get_rules, mock_generate, mock_create, mock_deactivate,
):
    """Superseded rules are deactivated with superseded_by set."""
    mock_count.return_value = 25

    creator_db_id = uuid.uuid4()
    rule_ids = [str(uuid.uuid4()) for _ in range(4)]
    rules = [
        {
            "id": rule_ids[i],
            "rule_text": f"Quita emojis variante {i}",
            "pattern": "remove_emoji",
            "confidence": 0.5,
            "times_applied": 0,
            "times_helped": 0,
            "example_bad": "Hola! \U0001f60a",
            "example_good": "Hola!",
            "applies_to_relationship_types": [],
            "applies_to_message_types": [],
            "applies_to_lead_stages": [],
        }
        for i in range(4)
    ]
    mock_get_rules.return_value = rules

    mock_generate.return_value = json.dumps([{
        "rule_text": "Nunca uses emojis",
        "pattern": "remove_emoji",
        "example_bad": "Hola! \U0001f60a",
        "example_good": "Hola!",
    }])

    new_rule_id = str(uuid.uuid4())
    mock_create.return_value = {"id": new_rule_id}

    from services.learning_consolidator import consolidate_rules_for_creator

    await consolidate_rules_for_creator("test_creator", creator_db_id)

    # All 4 original rules should be deactivated with superseded_by
    assert mock_deactivate.call_count == 4
    for call in mock_deactivate.call_args_list:
        # deactivate_rule(rule_id, superseded_by=new_rule_id)
        assert call[1].get("superseded_by") == new_rule_id


@pytest.mark.asyncio
@patch("core.providers.gemini_provider.generate_simple", new_callable=AsyncMock)
@patch("services.learning_rules_service.get_all_active_rules")
@patch("services.learning_rules_service.get_rules_count")
async def test_llm_timeout_skips_group(
    mock_count, mock_get_rules, mock_generate,
):
    """LLM timeout for a group is handled gracefully."""
    import asyncio

    mock_count.return_value = 25
    rules = [
        {
            "id": str(uuid.uuid4()),
            "rule_text": f"Rule {i}",
            "pattern": "some_pattern",
            "confidence": 0.5,
            "times_applied": 0,
            "times_helped": 0,
            "example_bad": None,
            "example_good": None,
            "applies_to_relationship_types": [],
            "applies_to_message_types": [],
            "applies_to_lead_stages": [],
        }
        for i in range(5)
    ]
    mock_get_rules.return_value = rules
    mock_generate.side_effect = asyncio.TimeoutError()

    from services.learning_consolidator import consolidate_rules_for_creator

    result = await consolidate_rules_for_creator("test_creator", uuid.uuid4())

    assert result["status"] == "done"
    assert result["consolidated"] == 0
    assert result["deactivated"] == 0
