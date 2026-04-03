"""Tests for services/autolearning_analyzer.py (shim)

analyze_creator_action is now a no-op (System B is batch-only).
Tests verify: no exception, no downstream calls, returns None.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_approval_no_llm():
    """Approval is a no-op — no rules or LLM calls."""
    from services.autolearning_analyzer import analyze_creator_action

    with patch("services.learning_rules_service.update_rule_feedback") as mock_update, \
         patch("services.learning_rules_service.get_applicable_rules") as mock_get:
        result = await analyze_creator_action(
            action="approved",
            creator_id="test_creator",
            creator_db_id=uuid.uuid4(),
            suggested_response="Hola!",
            intent="greeting",
        )

    assert result is None
    mock_get.assert_not_called()
    mock_update.assert_not_called()


@pytest.mark.asyncio
async def test_edit_no_llm():
    """Edit is a no-op — no LLM call, no rule created."""
    from services.autolearning_analyzer import analyze_creator_action

    with patch("core.providers.gemini_provider.generate_simple", new_callable=AsyncMock) as mock_gen, \
         patch("services.learning_rules_service.create_rule") as mock_create:
        result = await analyze_creator_action(
            action="edited",
            creator_id="test_creator",
            creator_db_id=uuid.uuid4(),
            suggested_response="Hola como estas?",
            final_response="Hola!",
            intent="greeting",
        )

    assert result is None
    mock_gen.assert_not_called()
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_discard_no_llm():
    """Discard is a no-op — no LLM call, no rule created."""
    from services.autolearning_analyzer import analyze_creator_action

    with patch("core.providers.gemini_provider.generate_simple", new_callable=AsyncMock) as mock_gen, \
         patch("services.learning_rules_service.create_rule") as mock_create:
        result = await analyze_creator_action(
            action="discarded",
            creator_id="test_creator",
            creator_db_id=uuid.uuid4(),
            suggested_response="Cual es tu presupuesto?",
            discard_reason="too aggressive",
            intent="question_product",
        )

    assert result is None
    mock_gen.assert_not_called()
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_missing_suggested_response():
    """No exception when suggested_response is None."""
    from services.autolearning_analyzer import analyze_creator_action

    result = await analyze_creator_action(
        action="edited",
        creator_id="test_creator",
        creator_db_id=uuid.uuid4(),
        suggested_response=None,
        final_response="manual text",
    )

    assert result is None


@pytest.mark.asyncio
async def test_unknown_action():
    """Unknown action type does not raise."""
    from services.autolearning_analyzer import analyze_creator_action

    result = await analyze_creator_action(
        action="unknown_action_xyz",
        creator_id="test_creator",
        creator_db_id=uuid.uuid4(),
    )

    assert result is None


@pytest.mark.asyncio
async def test_no_kwargs():
    """Called with minimal args does not raise."""
    from services.autolearning_analyzer import analyze_creator_action

    result = await analyze_creator_action()
    assert result is None


@pytest.mark.asyncio
async def test_is_non_text_response():
    """_is_non_text_response correctly identifies media prefixes."""
    from services.autolearning_analyzer import _is_non_text_response

    assert _is_non_text_response("[🎤 Audio] something") is True
    assert _is_non_text_response("[🏷️ Sticker] x") is True
    assert _is_non_text_response("[📷 photo]") is True
    assert _is_non_text_response("Hola como estas") is False
    assert _is_non_text_response("") is True
    assert _is_non_text_response(None) is True
