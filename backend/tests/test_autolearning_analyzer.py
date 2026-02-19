"""Tests for services/autolearning_analyzer.py"""

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def enable_autolearning():
    """Enable the feature flag for all tests."""
    with patch("services.autolearning_analyzer.ENABLE_AUTOLEARNING", True):
        yield


@pytest.mark.asyncio
@patch("services.learning_rules_service.update_rule_feedback")
@patch("services.learning_rules_service.get_applicable_rules")
async def test_approval_no_llm(mock_get_rules, mock_update):
    """Approval does not call LLM — only reinforces existing rules."""
    from services.autolearning_analyzer import analyze_creator_action

    mock_get_rules.return_value = [{"id": str(uuid.uuid4())}]

    await analyze_creator_action(
        action="approved",
        creator_id="test_creator",
        creator_db_id=uuid.uuid4(),
        suggested_response="Hola!",
        intent="greeting",
    )

    mock_get_rules.assert_called_once()
    mock_update.assert_called_once()


@pytest.mark.asyncio
@patch("services.learning_rules_service.create_rule")
@patch("core.providers.gemini_provider.generate_simple", new_callable=AsyncMock)
async def test_edit_calls_llm(mock_generate, mock_create):
    """Edit action calls LLM and creates a rule."""
    mock_generate.return_value = json.dumps({
        "rule_text": "Usa respuestas mas cortas",
        "pattern": "shorten_response",
        "example_bad": "Hola como estas espero que bien te queria preguntar",
        "example_good": "Hola! Te cuento rapido",
    })
    mock_create.return_value = {"id": str(uuid.uuid4()), "deduplicated": False}

    from services.autolearning_analyzer import analyze_creator_action

    await analyze_creator_action(
        action="edited",
        creator_id="test_creator",
        creator_db_id=uuid.uuid4(),
        suggested_response="Hola como estas espero que bien te queria preguntar algo",
        final_response="Hola! Te cuento rapido",
        intent="greeting",
        lead_stage="nuevo",
    )

    mock_generate.assert_called_once()
    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args
    assert call_kwargs[1]["confidence"] == 0.5
    assert call_kwargs[1]["pattern"] == "shorten_response"


@pytest.mark.asyncio
@patch("services.learning_rules_service.create_rule")
@patch("core.providers.gemini_provider.generate_simple", new_callable=AsyncMock)
async def test_edit_llm_timeout(mock_generate, mock_create):
    """Graceful handling when LLM times out."""
    mock_generate.side_effect = asyncio.TimeoutError()

    from services.autolearning_analyzer import analyze_creator_action

    # Should not raise
    await analyze_creator_action(
        action="edited",
        creator_id="test_creator",
        creator_db_id=uuid.uuid4(),
        suggested_response="Bot original response here that is long enough",
        final_response="Short",
        intent="greeting",
    )

    mock_create.assert_not_called()  # No rule created on timeout


@pytest.mark.asyncio
@patch("services.learning_rules_service.create_rule")
@patch("core.providers.gemini_provider.generate_simple", new_callable=AsyncMock)
async def test_discard_higher_confidence(mock_generate, mock_create):
    """Discard rules start at confidence 0.6 (higher than edits)."""
    mock_generate.return_value = json.dumps({
        "rule_text": "No preguntes por el presupuesto directamente",
        "pattern": "soften_pitch",
        "example_bad": "Cual es tu presupuesto?",
        "example_good": None,
    })
    mock_create.return_value = {"id": str(uuid.uuid4())}

    from services.autolearning_analyzer import analyze_creator_action

    await analyze_creator_action(
        action="discarded",
        creator_id="test_creator",
        creator_db_id=uuid.uuid4(),
        suggested_response="Cual es tu presupuesto?",
        discard_reason="too aggressive",
        intent="question_product",
    )

    mock_create.assert_called_once()
    assert mock_create.call_args[1]["confidence"] == 0.6


@pytest.mark.asyncio
async def test_feature_flag_disabled():
    """Noop when ENABLE_AUTOLEARNING=false."""
    with patch("services.autolearning_analyzer.ENABLE_AUTOLEARNING", False):
        from services.autolearning_analyzer import analyze_creator_action

        # Should return immediately without any side effects
        await analyze_creator_action(
            action="edited",
            creator_id="test_creator",
            creator_db_id=uuid.uuid4(),
            suggested_response="test",
            final_response="edited",
        )
        # No assertions needed — just verifying no exception


@pytest.mark.asyncio
async def test_missing_suggested_response():
    """Skips gracefully when no suggested_response provided."""
    from services.autolearning_analyzer import analyze_creator_action

    # Should not raise
    await analyze_creator_action(
        action="edited",
        creator_id="test_creator",
        creator_db_id=uuid.uuid4(),
        suggested_response=None,
        final_response="manual text",
    )


@pytest.mark.asyncio
@patch("services.learning_rules_service.create_rule")
@patch("core.providers.gemini_provider.generate_simple", new_callable=AsyncMock)
async def test_llm_returns_markdown_fences(mock_generate, mock_create):
    """Handles LLM response wrapped in markdown code fences."""
    mock_generate.return_value = "```json\n" + json.dumps({
        "rule_text": "No uses emojis",
        "pattern": "remove_emoji",
        "example_bad": "Hola! \U0001f60a",
        "example_good": "Hola!",
    }) + "\n```"
    mock_create.return_value = {"id": str(uuid.uuid4())}

    from services.autolearning_analyzer import analyze_creator_action

    await analyze_creator_action(
        action="edited",
        creator_id="test_creator",
        creator_db_id=uuid.uuid4(),
        suggested_response="Hola! \U0001f60a Como estas?",
        final_response="Hola! Como estas?",
        intent="greeting",
    )

    mock_create.assert_called_once()


@pytest.mark.asyncio
@patch("services.learning_rules_service.create_rule")
@patch("core.providers.gemini_provider.generate_simple", new_callable=AsyncMock)
async def test_llm_returns_invalid_json(mock_generate, mock_create):
    """Handles LLM returning non-JSON gracefully."""
    mock_generate.return_value = "I cannot generate a rule for this case."

    from services.autolearning_analyzer import analyze_creator_action

    await analyze_creator_action(
        action="edited",
        creator_id="test_creator",
        creator_db_id=uuid.uuid4(),
        suggested_response="Original long response with details",
        final_response="Short",
        intent="greeting",
    )

    mock_create.assert_not_called()
