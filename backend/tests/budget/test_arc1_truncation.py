"""
Tests for ARC1-TRUNCATION bug fix — core/dm/budget/orchestrator.py.

Bug: non-CRITICAL sections with tok > cap concatenated full content while
accounting only cap tokens against remaining, producing prompt overbudget
up to 25% in worst case (recalling: cap=400 but content 500-1000 tokens).

Fix: _fit() now truncates non-CRITICAL content to cap when compressor=None,
mirroring the existing CRITICAL hard-truncate path.
"""

import logging
from unittest.mock import MagicMock, call, patch

import pytest

from core.dm.budget.orchestrator import BudgetOrchestrator
from core.dm.budget.section import SECTION_CAPS, Priority, Section
from core.dm.budget.tokenizer import TokenCounter


# ---------------------------------------------------------------------------
# Helpers (mirrored from test_orchestrator.py conventions)
# ---------------------------------------------------------------------------

def _fake_tokenizer(char_ratio: int = 4) -> TokenCounter:
    """count = len(text) // ratio; truncate = text[:max_t * ratio]."""
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
# Case 1 — non-CRITICAL tok=500, cap=400: content truncated, remaining correct
# ---------------------------------------------------------------------------

class TestNonCriticalOverCapTruncated:
    def test_content_truncated_to_cap(self):
        tc = _fake_tokenizer()
        # "x"*2000 → tok=500, cap=400 → truncated to "x"*1600 (400 tokens)
        s = _section("recalling", "x" * 2000, priority=Priority.HIGH, cap=400)
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        result = orch.pack([s])
        selected = result.sections_selected[0]
        assert tc.count(selected.content) == 400

    def test_remaining_decremented_by_cap_not_full_tok(self):
        tc = _fake_tokenizer()
        s = _section("recalling", "x" * 2000, priority=Priority.HIGH, cap=400)
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        result = orch.pack([s])
        # remaining = 1000 - 400 = 600 → total_tokens = 400
        assert result.total_tokens == 400

    def test_combined_token_count_does_not_exceed_budget(self):
        tc = _fake_tokenizer()
        s = _section("recalling", "x" * 2000, priority=Priority.HIGH, cap=400)
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        result = orch.pack([s])
        assert tc.count(result.combined) <= 1000

    def test_section_added_to_compressed_list(self):
        tc = _fake_tokenizer()
        s = _section("recalling", "x" * 2000, priority=Priority.HIGH, cap=400)
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        result = orch.pack([s])
        assert len(result.sections_compressed) == 1


# ---------------------------------------------------------------------------
# Case 2 — non-CRITICAL tok=300, cap=400: content intact, remaining = 300
# ---------------------------------------------------------------------------

class TestNonCriticalUnderCap:
    def test_content_unchanged_when_under_cap(self):
        tc = _fake_tokenizer()
        original = "x" * 1200  # tok=300, cap=400 → no truncation
        s = _section("recalling", original, priority=Priority.HIGH, cap=400)
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        result = orch.pack([s])
        assert result.sections_selected[0].content == original

    def test_remaining_decremented_by_actual_tok(self):
        tc = _fake_tokenizer()
        s = _section("recalling", "x" * 1200, priority=Priority.HIGH, cap=400)
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        result = orch.pack([s])
        assert result.total_tokens == 300

    def test_not_added_to_compressed_list(self):
        tc = _fake_tokenizer()
        s = _section("recalling", "x" * 1200, priority=Priority.HIGH, cap=400)
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        result = orch.pack([s])
        assert result.sections_compressed == []


# ---------------------------------------------------------------------------
# Case 3 — CRITICAL tok=500, cap=400: previous behavior preserved
#           Hard-truncates to remaining, NOT to cap
# ---------------------------------------------------------------------------

class TestCriticalBehaviorUnchanged:
    def test_critical_truncates_to_remaining_not_to_cap(self):
        tc = _fake_tokenizer()
        # Budget = 300 (< cap=400 < tok=500)
        # Expected: force-truncate to remaining=300, not cap=400
        s = _section(
            "style", "x" * 2000, priority=Priority.CRITICAL, cap=400, compressor=None
        )
        orch = BudgetOrchestrator(tc, budget_tokens=300)
        result = orch.pack([s])
        selected = result.sections_selected[0]
        # truncated to remaining=300: len = 300*4 = 1200, NOT cap*4=1600
        assert len(selected.content) == 300 * 4
        assert tc.count(selected.content) == 300

    def test_critical_added_to_compressed_list(self):
        tc = _fake_tokenizer()
        s = _section("style", "x" * 2000, priority=Priority.CRITICAL, cap=400)
        orch = BudgetOrchestrator(tc, budget_tokens=300)
        result = orch.pack([s])
        assert len(result.sections_compressed) == 1

    def test_elif_does_not_fire_for_critical(self):
        """Verify CRITICAL path doesn't go through the non-CRITICAL elif branch.

        If elif fired for CRITICAL, content would be truncated to cap (400) and
        the force-truncate block would find effective_tok=cap (400) > remaining (300)
        and truncate again to remaining. Net result would be same len, but truncate
        would be called twice. Verify it's called exactly once (force path only).
        """
        tc = _fake_tokenizer()
        s = _section("style", "x" * 2000, priority=Priority.CRITICAL, cap=400)
        orch = BudgetOrchestrator(tc, budget_tokens=300)
        orch.pack([s])
        # truncate should be called once: in the force=True block, to remaining
        truncate_calls = [c for c in tc.truncate.call_args_list]
        assert len(truncate_calls) == 1
        # The call should use remaining (300) as max_t, not cap (400)
        _, kwargs_or_args = truncate_calls[0]
        # call args: (content, max_t) positional
        called_max_t = truncate_calls[0][0][1]  # second positional arg
        assert called_max_t == 300


# ---------------------------------------------------------------------------
# Case 4 — Mix: 5 sections (CRITICAL + non-CRITICAL with overflow)
#           Combined token count must not exceed budget by >5%
# ---------------------------------------------------------------------------

class TestMixedSectionsOverbudgetBound:
    def _build_sections(self):
        return [
            _section("style",     "x" * 1200, priority=Priority.CRITICAL, cap=500, value=1.00),  # tok=300
            _section("few_shots", "x" * 800,  priority=Priority.CRITICAL, cap=500, value=0.95),  # tok=200
            _section("rag",       "x" * 3200, priority=Priority.HIGH,     cap=400, value=0.90),  # tok=800
            _section("recalling", "x" * 2800, priority=Priority.MEDIUM,   cap=300, value=0.70),  # tok=700
            _section("kb",        "x" * 2400, priority=Priority.LOW,      cap=200, value=0.30),  # tok=600
        ]

    def test_total_tokens_within_budget(self):
        tc = _fake_tokenizer()
        orch = BudgetOrchestrator(tc, budget_tokens=2000)
        result = orch.pack(self._build_sections())
        assert result.total_tokens <= result.budget_tokens

    def test_combined_token_count_within_5pct_of_budget(self):
        tc = _fake_tokenizer()
        orch = BudgetOrchestrator(tc, budget_tokens=2000)
        result = orch.pack(self._build_sections())
        combined_tok = tc.count(result.combined)
        # 5% margin accounts for "\n\n" separators not in budget accounting
        assert combined_tok <= result.budget_tokens * 1.05

    def test_non_critical_overflow_sections_were_truncated(self):
        tc = _fake_tokenizer()
        orch = BudgetOrchestrator(tc, budget_tokens=2000)
        result = orch.pack(self._build_sections())
        # All non-CRITICAL included sections must have content ≤ their cap
        for s in result.sections_selected:
            if s.priority != Priority.CRITICAL:
                assert tc.count(s.content) <= s.cap_tokens, (
                    f"Section {s.name!r} has {tc.count(s.content)} tokens, cap={s.cap_tokens}"
                )


# ---------------------------------------------------------------------------
# Case 5 — Regression: recalling prod case (500-1000 tokens, cap=400)
# ---------------------------------------------------------------------------

class TestRecallingProdRegression:
    @pytest.mark.parametrize("raw_tokens", [500, 700, 1000])
    def test_recalling_truncated_to_cap(self, raw_tokens):
        tc = _fake_tokenizer()
        cap = SECTION_CAPS["recalling"]  # 400
        content = "x" * (raw_tokens * 4)  # raw_tokens with char_ratio=4
        s = _section("recalling", content, priority=Priority.HIGH, cap=cap)
        orch = BudgetOrchestrator(tc, budget_tokens=2000)
        result = orch.pack([s])
        selected = result.sections_selected[0]
        assert tc.count(selected.content) <= cap, (
            f"recalling with raw_tokens={raw_tokens} not truncated: "
            f"got {tc.count(selected.content)} > cap={cap}"
        )

    def test_recalling_combined_does_not_overflow_budget(self):
        tc = _fake_tokenizer()
        cap = SECTION_CAPS["recalling"]
        content = "x" * (800 * 4)  # 800 tokens, well over cap=400
        s = _section("recalling", content, priority=Priority.HIGH, cap=cap)
        orch = BudgetOrchestrator(tc, budget_tokens=500)
        result = orch.pack([s])
        assert tc.count(result.combined) <= 500


# ---------------------------------------------------------------------------
# Case 6 — compressor ≠ None: compressor used, tokenizer.truncate NOT called
# ---------------------------------------------------------------------------

class TestCompressorTakesPriorityOverTruncate:
    def test_compressor_invoked_not_truncate(self):
        compressor = MagicMock(return_value="compressed_content")
        tc = _fake_tokenizer()
        # Two count calls: original (500) + compressed ("compressed_content"=18 chars → 4)
        tc.count.side_effect = [500, len("compressed_content") // 4]
        s = _section(
            "recalling", "x" * 2000, priority=Priority.HIGH, cap=400, compressor=compressor
        )
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        orch.pack([s])
        compressor.assert_called_once_with("x" * 2000, 400)
        tc.truncate.assert_not_called()

    def test_compressor_result_used_in_output(self):
        compressor = MagicMock(return_value="compressed!")
        tc = _fake_tokenizer()
        tc.count.side_effect = [500, 3]  # original, compressed
        s = _section("rag", "x" * 2000, priority=Priority.HIGH, cap=400, compressor=compressor)
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        result = orch.pack([s])
        assert result.sections_selected[0].content == "compressed!"


# ---------------------------------------------------------------------------
# Case 7 — emit_metric called with correct label on truncation
# ---------------------------------------------------------------------------

class TestEmitMetricOnTruncation:
    def test_metric_emitted_when_non_critical_truncated(self):
        tc = _fake_tokenizer()
        s = _section("recalling", "x" * 2000, priority=Priority.HIGH, cap=400)
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        with patch("core.dm.budget.orchestrator.emit_metric") as mock_emit:
            orch.pack([s])
        mock_emit.assert_called_once_with(
            "budget_section_truncation_total", section_name="recalling"
        )

    def test_metric_not_emitted_when_under_cap(self):
        tc = _fake_tokenizer()
        s = _section("recalling", "x" * 1200, priority=Priority.HIGH, cap=400)  # tok=300 < 400
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        with patch("core.dm.budget.orchestrator.emit_metric") as mock_emit:
            orch.pack([s])
        mock_emit.assert_not_called()

    def test_metric_not_emitted_for_critical_truncation(self):
        tc = _fake_tokenizer()
        s = _section("style", "x" * 2000, priority=Priority.CRITICAL, cap=400)
        orch = BudgetOrchestrator(tc, budget_tokens=300)
        with patch("core.dm.budget.orchestrator.emit_metric") as mock_emit:
            orch.pack([s])
        # CRITICAL force-truncate does NOT call emit_metric — different code path
        mock_emit.assert_not_called()


# ---------------------------------------------------------------------------
# Case 8 — logger.debug includes overflow_tokens
# ---------------------------------------------------------------------------

class TestDebugLogIncludesOverflow:
    def test_debug_log_emitted_with_overflow(self, caplog):
        tc = _fake_tokenizer()
        # tok=500, cap=400 → overflow=100
        s = _section("recalling", "x" * 2000, priority=Priority.HIGH, cap=400)
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        with caplog.at_level(logging.DEBUG, logger="core.dm.budget.orchestrator"):
            orch.pack([s])
        assert any("overflow" in r.message for r in caplog.records), (
            "Expected 'overflow' in debug log. Records: " +
            str([r.message for r in caplog.records])
        )

    def test_debug_log_not_emitted_when_under_cap(self, caplog):
        tc = _fake_tokenizer()
        s = _section("recalling", "x" * 1200, priority=Priority.HIGH, cap=400)  # tok=300
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        with caplog.at_level(logging.DEBUG, logger="core.dm.budget.orchestrator"):
            orch.pack([s])
        assert not any("overflow" in r.message for r in caplog.records)

    def test_debug_log_includes_section_name_and_token_counts(self, caplog):
        tc = _fake_tokenizer()
        s = _section("rag", "x" * 2000, priority=Priority.HIGH, cap=400)
        orch = BudgetOrchestrator(tc, budget_tokens=1000)
        with caplog.at_level(logging.DEBUG, logger="core.dm.budget.orchestrator"):
            orch.pack([s])
        log_text = " ".join(r.message for r in caplog.records)
        assert "rag" in log_text
        assert "500" in log_text   # original tok
        assert "400" in log_text   # effective tok (cap)
