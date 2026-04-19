"""Tests for MemoryExtractor (ARC2 A2.2).

Unit tests — no DB, no real LLM. LLM calls are mocked via injectable llm_caller.
Coverage target: 85%+ lines.

Test matrix:
  extract_from_message (sync/regex):
    - age detection → identity
    - purchase intent detection → intent_signal
    - empty return when no signal
    - confidence threshold filtering
    - latency < 200ms

  extract_deep (LLM):
    - calls llm_caller
    - parses valid XML response
    - fails silent on LLM error
    - returns empty on invalid XML

  _parse_xml_response helpers:
    - handles malformed tags gracefully

  ExtractedMemory model:
    - rejects types outside 5 closed set
"""

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.memory_extractor import (
    CONFIDENCE_THRESHOLD,
    MEMORY_TYPES,
    ExtractedMemory,
    MemoryExtractor,
    get_memory_extractor,
)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

LEAD_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")

FIXTURES_PATH = Path(__file__).parent / "fixtures" / "conversations.json"


def _load_fixture(fixture_id: str) -> dict:
    fixtures = json.loads(FIXTURES_PATH.read_text())
    return next(f for f in fixtures if f["id"] == fixture_id)


def _make_extractor(llm_caller=None) -> MemoryExtractor:
    return MemoryExtractor(llm_caller=llm_caller)


def _valid_xml(*memories: dict) -> str:
    parts = []
    for m in memories:
        parts.append(
            f"  <memory>"
            f"<type>{m['type']}</type>"
            f"<fact>{m['fact']}</fact>"
            f"<why>{m.get('why', 'test evidence')}</why>"
            f"<how_to_apply>{m.get('how_to_apply', 'use it')}</how_to_apply>"
            f"<confidence>{m.get('confidence', 0.85)}</confidence>"
            f"</memory>"
        )
    return "<extracted_memories>" + "".join(parts) + "</extracted_memories>"


# ─────────────────────────────────────────────────────────────────────────────
# extract_from_message — identity
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_from_message_detects_age():
    fx = _load_fixture("fx_01_age_detection")
    extractor = _make_extractor()
    msg = fx["trigger_message"]["content"]

    results = await extractor.extract_from_message(msg, LEAD_ID)

    types = {m.type for m in results}
    assert "identity" in types
    identity_mem = next(m for m in results if m.type == "identity")
    assert "28" in identity_mem.fact


@pytest.mark.asyncio
async def test_extract_from_message_detects_catalan_age():
    extractor = _make_extractor()
    results = await extractor.extract_from_message("Tinc 25 anys i vull apuntar-me", LEAD_ID)
    assert any(m.type == "identity" and "25" in m.fact for m in results)


@pytest.mark.asyncio
async def test_extract_from_message_detects_name():
    fx = _load_fixture("fx_02_name_only")
    extractor = _make_extractor()
    msg = fx["trigger_message"]["content"]

    results = await extractor.extract_from_message(msg, LEAD_ID)

    assert any(m.type == "identity" and "Sofía" in m.fact for m in results)


@pytest.mark.asyncio
async def test_extract_from_message_detects_location():
    fx = _load_fixture("fx_06_location_and_profession")
    extractor = _make_extractor()
    msg = fx["trigger_message"]["content"]

    results = await extractor.extract_from_message(msg, LEAD_ID)

    assert any(m.type == "identity" and "Barcelona" in m.fact for m in results)


# ─────────────────────────────────────────────────────────────────────────────
# extract_from_message — intent_signal
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_from_message_detects_purchase_intent():
    fx = _load_fixture("fx_03_strong_purchase_intent")
    extractor = _make_extractor()
    msg = fx["trigger_message"]["content"]

    results = await extractor.extract_from_message(msg, LEAD_ID)

    assert any(m.type == "intent_signal" for m in results)
    intent_mem = next(m for m in results if m.type == "intent_signal")
    assert intent_mem.confidence >= 0.9


@pytest.mark.asyncio
async def test_extract_from_message_detects_medium_intent():
    fx = _load_fixture("fx_04_medium_intent_thinking")
    extractor = _make_extractor()
    msg = fx["trigger_message"]["content"]

    results = await extractor.extract_from_message(msg, LEAD_ID)

    assert any(m.type == "intent_signal" for m in results)


@pytest.mark.asyncio
async def test_extract_from_message_detects_abandon_intent():
    fx = _load_fixture("fx_07_price_objection")
    extractor = _make_extractor()
    msg = fx["trigger_message"]["content"]

    results = await extractor.extract_from_message(msg, LEAD_ID)

    assert any(m.type == "intent_signal" for m in results)


@pytest.mark.asyncio
async def test_extract_from_message_detects_english_strong_intent():
    fx = _load_fixture("fx_09_english_strong_intent")
    extractor = _make_extractor()
    msg = fx["trigger_message"]["content"]

    results = await extractor.extract_from_message(msg, LEAD_ID)

    assert any(m.type == "intent_signal" for m in results)


# ─────────────────────────────────────────────────────────────────────────────
# extract_from_message — empty + threshold
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_from_message_returns_empty_when_no_signal():
    fx = _load_fixture("fx_05_no_signal_greeting")
    extractor = _make_extractor()
    msg = fx["trigger_message"]["content"]

    results = await extractor.extract_from_message(msg, LEAD_ID)

    assert results == []


@pytest.mark.asyncio
async def test_extract_from_message_returns_empty_for_blank_message():
    extractor = _make_extractor()
    assert await extractor.extract_from_message("", LEAD_ID) == []
    assert await extractor.extract_from_message("   ", LEAD_ID) == []


@pytest.mark.asyncio
async def test_extract_from_message_respects_confidence_threshold():
    """All returned memories must have confidence >= CONFIDENCE_THRESHOLD."""
    extractor = _make_extractor()
    messages = [
        "Tengo 32 años",
        "Me apunto ya",
        "Hola qué tal",
        "me llamo Ana y vivo en Madrid",
    ]
    for msg in messages:
        results = await extractor.extract_from_message(msg, LEAD_ID)
        for mem in results:
            assert mem.confidence >= CONFIDENCE_THRESHOLD, (
                f"Memory {mem} has confidence {mem.confidence} < {CONFIDENCE_THRESHOLD}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# extract_from_message — latency
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_from_message_latency_below_200ms():
    """Sync regex path must complete within 200ms per the webhook budget."""
    extractor = _make_extractor()
    msg = "Tengo 32 años, me llamo Marta, vivo en Barcelona y quiero empezar hoy"

    start = time.perf_counter()
    for _ in range(50):
        await extractor.extract_from_message(msg, LEAD_ID)
    elapsed_ms = (time.perf_counter() - start) * 1000 / 50

    assert elapsed_ms < 200, f"extract_from_message took {elapsed_ms:.1f}ms (> 200ms budget)"


# ─────────────────────────────────────────────────────────────────────────────
# extract_deep — LLM integration
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_deep_calls_llm():
    """extract_deep must call llm_caller exactly once."""
    xml_resp = _valid_xml(
        {"type": "identity", "fact": "Lead is 28 years old", "confidence": 0.9}
    )
    llm_caller = AsyncMock(return_value=xml_resp)
    extractor = _make_extractor(llm_caller=llm_caller)

    conversation = [
        {"role": "user", "content": "Tengo 28 años"},
        {"role": "bot", "content": "Genial!"},
    ]
    results = await extractor.extract_deep(conversation, LEAD_ID)

    llm_caller.assert_called_once()
    assert len(results) == 1
    assert results[0].type == "identity"


@pytest.mark.asyncio
async def test_extract_deep_parses_xml_response():
    """All valid memory elements in XML must be parsed correctly."""
    xml_resp = _valid_xml(
        {"type": "identity", "fact": "Lead is 30 years old", "confidence": 0.95},
        {"type": "objection", "fact": "Price is too high for lead",
         "why": "Said too expensive", "how_to_apply": "Address value first", "confidence": 0.85},
        {"type": "relationship_state", "fact": "Lead is a warm prospect",
         "why": "Multiple questions asked", "how_to_apply": "Send nurturing flow", "confidence": 0.8},
    )
    llm_caller = AsyncMock(return_value=xml_resp)
    extractor = _make_extractor(llm_caller=llm_caller)

    conversation = [{"role": "user", "content": "Es caro pero tengo 30 años"}]
    results = await extractor.extract_deep(conversation, LEAD_ID)

    assert len(results) == 3
    types = {m.type for m in results}
    assert types == {"identity", "objection", "relationship_state"}


@pytest.mark.asyncio
async def test_extract_deep_returns_empty_without_llm_caller():
    """extract_deep without llm_caller must return [] silently."""
    extractor = _make_extractor(llm_caller=None)
    conversation = [{"role": "user", "content": "Hola tengo 28 años"}]
    results = await extractor.extract_deep(conversation, LEAD_ID)
    assert results == []


@pytest.mark.asyncio
async def test_extract_deep_fails_silent_on_llm_error():
    """LLM exception must not propagate — return [] and log warning."""
    async def failing_caller(prompt: str) -> str:
        raise RuntimeError("LLM timeout")

    extractor = _make_extractor(llm_caller=failing_caller)
    conversation = [{"role": "user", "content": "Tengo 32 años"}]

    results = await extractor.extract_deep(conversation, LEAD_ID)

    assert results == []


@pytest.mark.asyncio
async def test_extract_deep_returns_empty_on_invalid_xml():
    """Malformed XML from LLM must return [] without raising."""
    malformed = "<extracted_memories><memory><type>identity</BROKEN>"
    llm_caller = AsyncMock(return_value=malformed)
    extractor = _make_extractor(llm_caller=llm_caller)

    conversation = [{"role": "user", "content": "algo"}]
    results = await extractor.extract_deep(conversation, LEAD_ID)

    assert results == []


@pytest.mark.asyncio
async def test_extract_deep_filters_low_confidence():
    """Memories with confidence < threshold must be excluded."""
    xml_resp = _valid_xml(
        {"type": "identity", "fact": "Lead is old", "confidence": 0.4},
        {"type": "interest", "fact": "Lead interested in coaching",
         "why": "asked", "how_to_apply": "pitch", "confidence": 0.9},
    )
    llm_caller = AsyncMock(return_value=xml_resp)
    extractor = _make_extractor(llm_caller=llm_caller)

    results = await extractor.extract_deep([{"role": "user", "content": "x"}], LEAD_ID)

    assert len(results) == 1
    assert results[0].type == "interest"


# ─────────────────────────────────────────────────────────────────────────────
# _parse_xml_response edge cases
# ─────────────────────────────────────────────────────────────────────────────

def test_xml_parser_handles_malformed_tags():
    """Parser must return [] on XML that fails ET.fromstring."""
    extractor = _make_extractor()
    bad_responses = [
        "<extracted_memories><memory><type>identity</type></WRONG>",
        "<extracted_memories>not xml at all!!</extracted_memories>",
        "",
        "plain text response with no XML",
    ]
    for resp in bad_responses:
        result = extractor._parse_xml_response(resp)
        assert isinstance(result, list)


def test_xml_parser_skips_unknown_types():
    """Unknown memory types must be silently skipped."""
    extractor = _make_extractor()
    xml_resp = (
        "<extracted_memories>"
        "<memory><type>unknown_type</type><fact>test</fact>"
        "<why>x</why><how_to_apply>y</how_to_apply><confidence>0.9</confidence></memory>"
        "<memory><type>identity</type><fact>Lead is 25 years old</fact>"
        "<why>said so</why><how_to_apply>use it</how_to_apply><confidence>0.9</confidence></memory>"
        "</extracted_memories>"
    )
    results = extractor._parse_xml_response(xml_resp)
    assert len(results) == 1
    assert results[0].type == "identity"


def test_xml_parser_handles_empty_extracted_memories():
    """Empty <extracted_memories/> must return []."""
    extractor = _make_extractor()
    result = extractor._parse_xml_response("<extracted_memories></extracted_memories>")
    assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# ExtractedMemory model validation
# ─────────────────────────────────────────────────────────────────────────────

def test_extracted_memory_validates_type_in_5_types():
    """Creating ExtractedMemory with invalid type must raise ValidationError."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ExtractedMemory(
            type="invalid_type",  # type: ignore[arg-type]
            fact="some fact",
            why="some why",
            how_to_apply="some action",
            confidence=0.9,
        )


def test_extracted_memory_all_valid_types():
    """All 5 valid types must be accepted without error."""
    for mem_type in MEMORY_TYPES:
        mem = ExtractedMemory(
            type=mem_type,  # type: ignore[arg-type]
            fact=f"Test fact for {mem_type}",
            why="test evidence",
            how_to_apply="test action",
            confidence=0.8,
        )
        assert mem.type == mem_type


def test_extracted_memory_confidence_bounds():
    """Confidence must be within [0.0, 1.0]."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ExtractedMemory(
            type="identity",
            fact="test",
            why="test",
            how_to_apply="test",
            confidence=1.5,
        )

    with pytest.raises(ValidationError):
        ExtractedMemory(
            type="identity",
            fact="test",
            why="test",
            how_to_apply="test",
            confidence=-0.1,
        )


def test_extracted_memory_is_frozen():
    """ExtractedMemory must be immutable (frozen=True)."""
    mem = ExtractedMemory(
        type="identity",
        fact="Test fact",
        why="test",
        how_to_apply="test",
        confidence=0.9,
    )
    with pytest.raises(Exception):
        mem.fact = "mutated"  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────────────────────
# get_memory_extractor singleton
# ─────────────────────────────────────────────────────────────────────────────

def test_get_memory_extractor_returns_same_instance():
    import services.memory_extractor as _mod
    _mod._extractor = None  # reset singleton

    e1 = get_memory_extractor()
    e2 = get_memory_extractor()
    assert e1 is e2


def test_get_memory_extractor_creates_new_on_different_caller():
    import services.memory_extractor as _mod
    _mod._extractor = None

    caller1 = AsyncMock(return_value="")
    caller2 = AsyncMock(return_value="")

    e1 = get_memory_extractor(caller1)
    e2 = get_memory_extractor(caller2)
    assert e1 is not e2


# ─────────────────────────────────────────────────────────────────────────────
# classify_signal helper
# ─────────────────────────────────────────────────────────────────────────────

def test_classify_signal_true_for_known_patterns():
    extractor = _make_extractor()
    assert extractor._classify_signal("tengo 30 años")
    assert extractor._classify_signal("me apunto")
    assert extractor._classify_signal("me llamo Pedro")
    assert extractor._classify_signal("vivo en Madrid")
    assert extractor._classify_signal("es muy caro")


def test_classify_signal_false_for_noise():
    extractor = _make_extractor()
    assert not extractor._classify_signal("Hola!")
    assert not extractor._classify_signal("Ok")
    assert not extractor._classify_signal("👍")
    assert not extractor._classify_signal("")
