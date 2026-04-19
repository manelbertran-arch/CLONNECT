"""Unit tests for PromptSliceCompactor — ARC3 Phase 2."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from core.generation.compactor import (
    DEFAULT_RATIOS,
    PackResult,
    PromptSliceCompactor,
    SectionSpec,
    truncate_preserving_structure,
)

BUDGET = 8000


def _wl(name: str, content: str) -> SectionSpec:
    return SectionSpec(name=name, content=content, priority=1, is_whitelist=True)


def _nwl(name: str, content: str, priority: int = 5) -> SectionSpec:
    return SectionSpec(name=name, content=content, priority=priority, is_whitelist=False)


# ─────────────────────────────────────────────────────────────────────────────
# PromptSliceCompactor — async tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_sections():
    compactor = PromptSliceCompactor(budget_chars=BUDGET)
    result = await compactor.pack([])
    assert result.status == "OK"
    assert result.compaction_applied is False
    assert result.final_chars == 0


@pytest.mark.asyncio
async def test_all_sections_fit_returns_ok_no_compaction():
    sections = [
        _nwl("style_prompt", "s" * 500, priority=2),
        _nwl("lead_memories", "m" * 200, priority=3),
        _nwl("rag_hits", "r" * 100, priority=4),
    ]
    compactor = PromptSliceCompactor(budget_chars=BUDGET)
    result = await compactor.pack(sections)
    assert result.status == "OK"
    assert result.compaction_applied is False
    assert result.reason == "OK"
    assert result.final_chars == 800


@pytest.mark.asyncio
async def test_whitelist_overflow_circuit_break():
    sections = [
        _wl("system_instructions", "x" * 10000),
    ]
    compactor = PromptSliceCompactor(budget_chars=BUDGET)
    result = await compactor.pack(sections)
    assert result.status == "CIRCUIT_BREAK"
    assert result.reason == "CIRCUIT_BREAK"
    assert result.packed == {}


@pytest.mark.asyncio
async def test_style_prompt_triggers_distill():
    """style_prompt > remaining*0.4 and total over budget → distill called, distill_applied=True."""
    mock_distill = MagicMock()
    mock_distill.get_or_generate = AsyncMock(return_value="distilled" * 100)

    # remaining = 8000, style_prompt = 5000 > 0.4*8000 = 3200
    # total = 5000 + 4000 = 9000 > 8000 → reaches distill step
    sections = [
        _nwl("style_prompt", "s" * 5000, priority=2),
        _nwl("lead_memories", "m" * 4000, priority=3),
    ]
    compactor = PromptSliceCompactor(budget_chars=BUDGET, distill_service=mock_distill)
    result = await compactor.pack(sections, creator_id=uuid4())
    mock_distill.get_or_generate.assert_called_once()
    assert result.distill_applied is True
    assert result.reason == "DISTILL_APPLIED"


@pytest.mark.asyncio
async def test_ratio_caps_applied_when_over_budget():
    """Non-wl sections exceed budget, all have ratios → reason=RATIO_CAPS, sections_truncated non-empty."""
    sections = [
        _nwl("style_prompt", "s" * 5000, priority=2),
        _nwl("lead_memories", "m" * 4000, priority=3),
        _nwl("few_shots", "e" * 100, priority=5),
    ]
    compactor = PromptSliceCompactor(
        budget_chars=BUDGET, ratios=DEFAULT_RATIOS, distill_service=None
    )
    result = await compactor.pack(sections)
    assert result.compaction_applied is True
    assert len(result.sections_truncated) > 0
    assert result.reason == "RATIO_CAPS"
    assert len(result.packed["style_prompt"]) <= int(DEFAULT_RATIOS["style_prompt"] * BUDGET)


@pytest.mark.asyncio
async def test_aggressive_truncate_by_priority():
    """Sections exceed budget, no matching ratios → falls to aggressive truncation.
    Lowest priority (highest number) is truncated first."""
    tiny_budget = 500
    sections = [
        _nwl("custom_high_prio", "s" * 300, priority=2),  # high priority, kept
        _nwl("custom_low_prio", "e" * 300, priority=9),   # low priority, cut first
    ]
    # Ratios dict has no entries for our section names, so ratio-cap step is a no-op.
    # Note: ratios={} is falsy → __init__ falls back to DEFAULT_RATIOS, so use a
    # non-empty sentinel dict that still doesn't cover our section names.
    compactor = PromptSliceCompactor(budget_chars=tiny_budget, ratios={"__sentinel__": 0.01})
    result = await compactor.pack(sections)
    assert result.compaction_applied is True
    total = sum(len(v) for v in result.packed.values())
    assert total <= tiny_budget
    # reason must reflect aggressive truncation (not ratio caps)
    assert result.reason == "AGGRESSIVE_TRUNC"
    # low-priority section was truncated
    assert "custom_low_prio" in result.sections_truncated


# ─────────────────────────────────────────────────────────────────────────────
# truncate_preserving_structure — sync helpers, no asyncio needed
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_truncate_preserving_structure_paragraph():
    """text with \\n\\n at >80% position → truncated at paragraph boundary."""
    max_chars = 60
    # paragraph break at position 50; 50 > 60*0.8 = 48 → cuts there
    prefix = "a" * 50
    suffix = "\n\nmore content goes here over"
    text = prefix + suffix
    result = truncate_preserving_structure(text, max_chars)
    assert result == prefix
    assert "\n\n" not in result


@pytest.mark.asyncio
async def test_truncate_preserving_structure_sentence():
    """text with '. ' at >85% position but no paragraph break in range → truncated at sentence."""
    max_chars = 100
    # '. ' at position 88; 88 > 100*0.85 = 85 → cuts at last_period+1 (position 89)
    text = "x" * 88 + ". " + "y" * 20
    result = truncate_preserving_structure(text, max_chars)
    assert result.endswith(".")
    assert len(result) <= max_chars
    # Confirm no paragraph break was found (no \n\n in text)
    assert "\n\n" not in text


@pytest.mark.asyncio
async def test_truncate_preserving_structure_word():
    """text with ' ' at >90% position, no paragraph/sentence boundaries → truncated at word."""
    max_chars = 100
    # space at position 95; 95 > 100*0.9 = 90 → cuts there
    text = "x" * 95 + " " + "y" * 10
    result = truncate_preserving_structure(text, max_chars)
    assert len(result) <= max_chars
    # Should cut at the space (result has no trailing space from the content beyond)
    assert result == "x" * 95


@pytest.mark.asyncio
async def test_truncate_preserving_structure_hard_cut():
    """No clean boundaries anywhere → hard cut at max_chars."""
    text = "a" * 200
    result = truncate_preserving_structure(text, 100)
    assert result == "a" * 100
    assert len(result) == 100
