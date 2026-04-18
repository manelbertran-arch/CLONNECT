"""
Tests for core/dm/budget/section.py
Covers: Priority ordering, Section immutability, AssembledContext fields,
        SECTION_CAPS table, compute_value_score heuristic.
"""

import pytest

from core.dm.budget.section import (
    SECTION_CAPS,
    AssembledContext,
    Priority,
    Section,
    compute_value_score,
)


class TestPriority:
    def test_critical_highest(self):
        assert Priority.CRITICAL > Priority.HIGH
        assert Priority.HIGH > Priority.MEDIUM
        assert Priority.MEDIUM > Priority.LOW
        assert Priority.LOW > Priority.FINAL

    def test_int_values(self):
        assert int(Priority.CRITICAL) == 4
        assert int(Priority.FINAL) == 0

    def test_sortable(self):
        priorities = [Priority.LOW, Priority.CRITICAL, Priority.FINAL, Priority.HIGH]
        assert sorted(priorities, reverse=True)[0] == Priority.CRITICAL
        assert sorted(priorities)[0] == Priority.FINAL


class TestSection:
    def _make(self, **kwargs) -> Section:
        defaults = dict(
            name="style",
            content="hello world",
            priority=Priority.CRITICAL,
            cap_tokens=800,
            value_score=1.0,
        )
        defaults.update(kwargs)
        return Section(**defaults)

    def test_frozen(self):
        s = self._make()
        with pytest.raises((AttributeError, TypeError)):
            s.name = "other"  # type: ignore[misc]

    def test_default_metadata_empty(self):
        s = self._make()
        assert s.metadata == {}

    def test_compressor_none_by_default(self):
        s = self._make()
        assert s.compressor is None

    def test_compressor_callable(self):
        def comp(text: str, cap: int) -> str:
            return text[:cap]

        s = self._make(compressor=comp)
        assert s.compressor is not None
        assert s.compressor("abcdef", 3) == "abc"

    def test_metadata_stored(self):
        s = self._make(metadata={"foo": "bar"})
        assert s.metadata["foo"] == "bar"


class TestAssembledContext:
    def _make_section(self, name: str = "s", value: float = 0.5) -> Section:
        return Section(
            name=name,
            content="x",
            priority=Priority.HIGH,
            cap_tokens=100,
            value_score=value,
        )

    def test_fields_accessible(self):
        s = self._make_section()
        ctx = AssembledContext(
            combined="x",
            sections_selected=[s],
            sections_dropped=[],
            sections_compressed=[],
            total_tokens=10,
            budget_tokens=100,
            utilization=0.1,
        )
        assert ctx.combined == "x"
        assert len(ctx.sections_selected) == 1
        assert ctx.utilization == 0.1

    def test_mutable(self):
        ctx = AssembledContext(
            combined="",
            sections_selected=[],
            sections_dropped=[],
            sections_compressed=[],
            total_tokens=0,
            budget_tokens=100,
            utilization=0.0,
        )
        ctx.combined = "updated"
        assert ctx.combined == "updated"


class TestSectionCaps:
    def test_known_sections_present(self):
        for name in ("style", "few_shots", "recalling", "audio", "rag", "history"):
            assert name in SECTION_CAPS

    def test_style_cap_800(self):
        assert SECTION_CAPS["style"] == 800

    def test_few_shots_cap_350(self):
        assert SECTION_CAPS["few_shots"] == 350

    def test_friend_context_cap_zero(self):
        assert SECTION_CAPS["friend_context"] == 0

    def test_citations_cap_50(self):
        assert SECTION_CAPS["citations"] == 50


class TestComputeValueScore:
    def test_style_always_1(self):
        assert compute_value_score("style", {}) == 1.0

    def test_few_shots_095(self):
        assert compute_value_score("few_shots", {}) == 0.95

    def test_audio_zero_without_signal(self):
        assert compute_value_score("audio", {}) == 0.0

    def test_audio_070_with_signal(self):
        assert compute_value_score("audio", {"audio_intel": True}) == 0.70

    def test_rag_low_without_signal(self):
        assert compute_value_score("rag", {}) == 0.30

    def test_rag_high_with_signal(self):
        assert compute_value_score("rag", {"rag_signal": True}) == 0.75

    def test_rag_purchase_intent_boost(self):
        score = compute_value_score(
            "rag", {"rag_signal": True, "intent_category": "purchase_intent"}
        )
        assert score == min(0.75 * 1.4, 1.0)

    def test_rag_casual_penalty(self):
        score = compute_value_score(
            "rag", {"rag_signal": True, "intent_category": "casual"}
        )
        assert abs(score - 0.75 * 0.5) < 1e-9

    def test_clamp_at_1(self):
        # purchase_intent boost on already-1.0 would exceed; clamp at 1.0
        score = compute_value_score("style", {"intent_category": "purchase_intent"})
        assert score <= 1.0

    def test_unknown_section_default_05(self):
        assert compute_value_score("unknown_section", {}) == 0.5

    def test_commitments_zero_without_pending(self):
        assert compute_value_score("commitments", {}) == 0.0

    def test_commitments_06_with_pending(self):
        assert compute_value_score("commitments", {"commitments_pending": True}) == 0.60
