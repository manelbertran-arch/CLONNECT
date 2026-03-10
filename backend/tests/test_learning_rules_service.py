"""Tests for services/learning_rules_service.py"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

# Patch target: the lazy import inside each function
_DB_PATCH = "api.database.SessionLocal"


def _make_rule(**overrides):
    """Create a mock LearningRule object."""
    defaults = {
        "id": uuid.uuid4(),
        "creator_id": uuid.uuid4(),
        "rule_text": "Usa frases mas cortas",
        "pattern": "shorten_response",
        "applies_to_relationship_types": [],
        "applies_to_message_types": [],
        "applies_to_lead_stages": [],
        "example_bad": "Hola, como estas? Espero que bien, queria preguntarte...",
        "example_good": "Hola! Te cuento algo rapido...",
        "confidence": 0.5,
        "times_applied": 0,
        "times_helped": 0,
        "is_active": True,
        "version": 1,
        "created_at": datetime.now(timezone.utc),
        "source_message_id": None,
        "superseded_by": None,
    }
    defaults.update(overrides)
    rule = MagicMock()
    for k, v in defaults.items():
        setattr(rule, k, v)
    return rule


@patch(_DB_PATCH)
def test_create_rule_basic(mock_session_class):
    """Creating a new rule stores it and returns its ID."""
    from services.learning_rules_service import create_rule

    session = MagicMock()
    mock_session_class.return_value = session
    # No existing rule found (no dedup)
    session.query.return_value.filter.return_value.first.return_value = None

    creator_id = uuid.uuid4()
    result = create_rule(
        creator_id=creator_id,
        rule_text="Acorta las respuestas",
        pattern="shorten_response",
        confidence=0.6,
    )

    assert result is not None
    assert result["deduplicated"] is False
    assert result["confidence"] == 0.6
    session.add.assert_called_once()
    session.commit.assert_called_once()


@patch(_DB_PATCH)
def test_create_rule_dedup(mock_session_class):
    """Same pattern+text increments confidence instead of creating new rule."""
    from services.learning_rules_service import create_rule

    session = MagicMock()
    mock_session_class.return_value = session

    existing = _make_rule(confidence=0.5, version=1)
    session.query.return_value.filter.return_value.first.return_value = existing

    result = create_rule(
        creator_id=existing.creator_id,
        rule_text=existing.rule_text,
        pattern=existing.pattern,
    )

    assert result is not None
    assert result["deduplicated"] is True
    assert existing.confidence == 0.55  # +0.05
    assert existing.version == 2
    session.add.assert_not_called()  # No new row
    session.commit.assert_called_once()


@patch(_DB_PATCH)
def test_get_applicable_rules_context_scoring(mock_session_class):
    """Intent match scores higher than universal rules."""
    from services.learning_rules_service import get_applicable_rules, _rules_cache, _rules_cache_ts

    # Clear cache
    _rules_cache.clear()
    _rules_cache_ts.clear()

    session = MagicMock()
    mock_session_class.return_value = session

    creator_id = uuid.uuid4()

    # Rule 1: matches intent
    r1 = _make_rule(
        id=uuid.uuid4(),
        creator_id=creator_id,
        rule_text="Acorta respuestas de precio",
        pattern="question_product",
        applies_to_message_types=["question_product"],
        confidence=0.6,
    )
    # Rule 2: universal (no context)
    r2 = _make_rule(
        id=uuid.uuid4(),
        creator_id=creator_id,
        rule_text="No uses emojis",
        pattern="remove_emoji",
        confidence=0.5,
    )

    # The query chain is .filter(...).limit(100).all() — mock through limit()
    session.query.return_value.filter.return_value.limit.return_value.all.return_value = [r1, r2]

    rules = get_applicable_rules(creator_id, intent="question_product")

    assert len(rules) >= 1
    # First rule should be the intent-matched one (higher score)
    assert rules[0]["pattern"] == "question_product"


@patch(_DB_PATCH)
def test_get_applicable_rules_max_limit(mock_session_class):
    """Respects max_rules limit."""
    from services.learning_rules_service import get_applicable_rules, _rules_cache, _rules_cache_ts

    _rules_cache.clear()
    _rules_cache_ts.clear()

    session = MagicMock()
    mock_session_class.return_value = session

    creator_id = uuid.uuid4()
    rules = [
        _make_rule(
            id=uuid.uuid4(),
            creator_id=creator_id,
            rule_text=f"Rule {i}",
            pattern=f"pattern_{i}",
            confidence=0.5,
        )
        for i in range(10)
    ]
    session.query.return_value.filter.return_value.all.return_value = rules

    result = get_applicable_rules(creator_id, max_rules=3)
    assert len(result) <= 3


@patch(_DB_PATCH)
def test_update_rule_feedback(mock_session_class):
    """Adjusts times_helped and confidence correctly."""
    from services.learning_rules_service import update_rule_feedback

    session = MagicMock()
    mock_session_class.return_value = session

    rule = _make_rule(confidence=0.5, times_applied=2, times_helped=1)
    session.query.return_value.filter_by.return_value.first.return_value = rule

    # Helpful feedback
    result = update_rule_feedback(rule.id, was_helpful=True)
    assert result is True
    assert rule.times_applied == 3
    assert rule.times_helped == 2
    assert rule.confidence == 0.55

    # Unhelpful feedback
    rule.confidence = 0.5  # Reset
    update_rule_feedback(rule.id, was_helpful=False)
    assert rule.confidence == 0.45


@patch(_DB_PATCH)
def test_update_rule_feedback_not_found(mock_session_class):
    """Returns False when rule doesn't exist."""
    from services.learning_rules_service import update_rule_feedback

    session = MagicMock()
    mock_session_class.return_value = session
    session.query.return_value.filter_by.return_value.first.return_value = None

    result = update_rule_feedback(uuid.uuid4(), was_helpful=True)
    assert result is False
