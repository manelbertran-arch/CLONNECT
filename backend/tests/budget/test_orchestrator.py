"""
Tests for core/dm/budget/orchestrator.py
Covers: pack() greedy algorithm, CRITICAL forcing, compression, truncation,
        drop logic, utilization calc, edge cases, _replace helper.
"""

from unittest.mock import MagicMock

import pytest

from core.dm.budget.orchestrator import BudgetOrchestrator, _replace
from core.dm.budget.section import AssembledContext, Priority, Section
from core.dm.budget.tokenizer import TokenCounter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_tokenizer(char_ratio: int = 4) -> TokenCounter:
    """Tokenizer mock: count = len(text) // char_ratio, truncate = text[:max*ratio]."""
    tc = MagicMock(spec=TokenCounter)
    tc.count.side_effect = lambda text: len(text) // char_ratio if text else 0
    tc.truncate.side_effect = lambda text, max_t: text[: max_t * char_ratio]
    return tc


def _section(
    name: str,
    content: str,
    priority: Priority = Priority.HIGH,
    cap: int = 10_000,
    value: float = 0.5,
    compressor=None,
) -> Section:
    return Section(
        name=name,
        content=content,
        priority=priority,
        cap_tokens=cap,
        value_score=value,
        compressor=compressor,
    )


# ---------------------------------------------------------------------------
# Basic pack behaviour
# ---------------------------------------------------------------------------

class TestPackBasic:
    def test_empty_sections_returns_empty_context(self):
        tc = _fake_tokenizer()
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        result = orch.pack([])
        assert result.combined == ""
        assert result.total_tokens == 0
        assert result.utilization == 0.0

    def test_single_section_fits(self):
        tc = MagicMock(spec=TokenCounter)
        tc.count.return_value = 10
        s = _section("style", "hello world", priority=Priority.CRITICAL, cap=100)
        orch = BudgetOrchestrator(tc, budget_tokens=100)
        result = orch.pack([s])
        assert len(result.sections_selected) == 1
        assert result.sections_dropped == []
        assert result.total_tokens == 10

    def test_combined_joins_with_double_newline(self):
        tc = _fake_tokenizer()
        tc.count.side_effect = lambda text: 5 if text else 0
        s1 = _section("a", "AAA", priority=Priority.CRITICAL)
        s2 = _section("b", "BBB", priority=Priority.HIGH)
        orch = BudgetOrchestrator(tc, budget_tokens=100)
        result = orch.pack([s1, s2])
        assert "AAA" in result.combined
        assert "BBB" in result.combined
        assert "\n\n" in result.combined

    def test_utilization_calculation(self):
        tc = MagicMock(spec=TokenCounter)
        tc.count.return_value = 40
        s = _section("s", "x" * 160, priority=Priority.CRITICAL, cap=10_000)
        orch = BudgetOrchestrator(tc, budget_tokens=100)
        result = orch.pack([s])
        assert abs(result.utilization - 0.40) < 1e-6


# ---------------------------------------------------------------------------
# CRITICAL forcing
# ---------------------------------------------------------------------------

class TestCriticalForcing:
    def test_critical_always_included(self):
        tc = _fake_tokenizer()
        tc.count.return_value = 5
        tc.truncate.return_value = "truncated"
        critical = _section("style", "x" * 20, priority=Priority.CRITICAL, cap=10_000)
        non_crit = _section("rag", "y" * 20, priority=Priority.HIGH)
        orch = BudgetOrchestrator(tc, budget_tokens=6)  # only enough for critical
        result = orch.pack([critical, non_crit])
        names = [s.name for s in result.sections_selected]
        assert "style" in names

    def test_critical_compressed_when_over_cap(self):
        compressor = MagicMock(return_value="short")
        tc = _fake_tokenizer()
        # First call (original) = 200, second (compressed) = 5
        tc.count.side_effect = [200, 5]
        critical = _section(
            "style", "x" * 800, priority=Priority.CRITICAL, cap=100, compressor=compressor
        )
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        result = orch.pack([critical])
        compressor.assert_called_once()
        assert len(result.sections_compressed) == 1

    def test_critical_hard_truncated_when_no_compressor_and_overflows(self):
        tc = _fake_tokenizer()
        tc.count.return_value = 500
        tc.truncate.return_value = "trunc"
        critical = _section(
            "style", "x" * 2000, priority=Priority.CRITICAL, cap=10_000, compressor=None
        )
        orch = BudgetOrchestrator(tc, budget_tokens=50)
        result = orch.pack([critical])
        tc.truncate.assert_called_once()
        assert len(result.sections_compressed) == 1

    def test_multiple_critical_both_included(self):
        tc = _fake_tokenizer()
        tc.count.return_value = 10
        c1 = _section("style", "A" * 40, priority=Priority.CRITICAL)
        c2 = _section("fewshots", "B" * 40, priority=Priority.CRITICAL)
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        result = orch.pack([c1, c2])
        names = {s.name for s in result.sections_selected}
        assert "style" in names and "fewshots" in names


# ---------------------------------------------------------------------------
# Greedy ordering for non-CRITICAL
# ---------------------------------------------------------------------------

class TestGreedyOrdering:
    def test_high_value_score_wins_budget(self):
        tc = _fake_tokenizer()
        # Each section costs 50 tokens; budget = 80 → only one fits
        tc.count.return_value = 50
        low_val = _section("low", "L" * 200, priority=Priority.HIGH, value=0.1)
        high_val = _section("high", "H" * 200, priority=Priority.HIGH, value=0.9)
        orch = BudgetOrchestrator(tc, budget_tokens=80)
        result = orch.pack([low_val, high_val])
        names = [s.name for s in result.sections_selected]
        assert "high" in names
        assert "low" in names or "low" in [s.name for s in result.sections_dropped]

    def test_dropped_section_recorded(self):
        tc = _fake_tokenizer()
        tc.count.return_value = 60
        s1 = _section("rag", "R" * 240, priority=Priority.HIGH, value=0.8)
        s2 = _section("kb", "K" * 240, priority=Priority.LOW, value=0.1)
        orch = BudgetOrchestrator(tc, budget_tokens=80)
        result = orch.pack([s1, s2])
        # s1 uses 60 tokens, s2 needs 60 but only 20 remain → dropped
        dropped_names = [s.name for s in result.sections_dropped]
        assert "kb" in dropped_names

    def test_budget_exhausted_remaining_dropped(self):
        tc = _fake_tokenizer()
        tc.count.return_value = 100
        sections = [
            _section(f"s{i}", "x" * 400, priority=Priority.HIGH, value=float(i) / 10)
            for i in range(5)
        ]
        orch = BudgetOrchestrator(tc, budget_tokens=150)
        result = orch.pack(sections)
        total_selected = len(result.sections_selected)
        total_dropped = len(result.sections_dropped)
        assert total_selected + total_dropped == 5


# ---------------------------------------------------------------------------
# Cap enforcement
# ---------------------------------------------------------------------------

class TestCapEnforcement:
    def test_cap_limits_effective_tokens(self):
        tc = _fake_tokenizer()
        tc.count.return_value = 500  # over cap
        s = _section("rag", "x" * 2000, priority=Priority.HIGH, cap=100)
        orch = BudgetOrchestrator(tc, budget_tokens=200)
        result = orch.pack([s])
        # effective_tok = min(500, 100) = 100 → section fits
        assert "rag" in [sec.name for sec in result.sections_selected]

    def test_compressor_invoked_when_over_cap_non_critical(self):
        compressor = MagicMock(return_value="compressed")
        tc = _fake_tokenizer()
        tc.count.side_effect = [200, 50]  # original, compressed
        s = _section(
            "rag", "x" * 800, priority=Priority.HIGH, cap=100, compressor=compressor
        )
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        result = orch.pack([s])
        compressor.assert_called_once()
        assert len(result.sections_compressed) == 1


# ---------------------------------------------------------------------------
# AssembledContext fields
# ---------------------------------------------------------------------------

class TestAssembledContextFields:
    def test_budget_tokens_preserved(self):
        tc = _fake_tokenizer()
        tc.count.return_value = 0
        orch = BudgetOrchestrator(tc, budget_tokens=4000)
        result = orch.pack([])
        assert result.budget_tokens == 4000

    def test_sections_selected_list_type(self):
        tc = _fake_tokenizer()
        tc.count.return_value = 5
        s = _section("style", "hi", priority=Priority.CRITICAL)
        orch = BudgetOrchestrator(tc, budget_tokens=100)
        result = orch.pack([s])
        assert isinstance(result.sections_selected, list)
        assert isinstance(result.sections_dropped, list)
        assert isinstance(result.sections_compressed, list)

    def test_utilization_zero_on_empty(self):
        tc = _fake_tokenizer()
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        result = orch.pack([])
        assert result.utilization == 0.0

    def test_utilization_full_budget(self):
        tc = _fake_tokenizer()
        tc.count.return_value = 1000
        tc.truncate.return_value = "t"
        s = _section("style", "x" * 4000, priority=Priority.CRITICAL, cap=10_000)
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        result = orch.pack([s])
        assert result.utilization <= 1.0


# ---------------------------------------------------------------------------
# _replace helper
# ---------------------------------------------------------------------------

class TestReplace:
    def test_replace_content(self):
        s = _section("style", "original", priority=Priority.CRITICAL, cap=800)
        s2 = _replace(s, content="new content")
        assert s2.content == "new content"
        assert s2.name == "style"
        assert s2.priority == Priority.CRITICAL

    def test_replace_preserves_compressor(self):
        comp = lambda text, cap: text[:cap]
        s = _section("style", "x", priority=Priority.CRITICAL, cap=800, compressor=comp)
        s2 = _replace(s, content="y")
        assert s2.compressor is comp

    def test_replace_original_unchanged(self):
        s = _section("style", "original", priority=Priority.CRITICAL, cap=800)
        _replace(s, content="changed")
        assert s.content == "original"
