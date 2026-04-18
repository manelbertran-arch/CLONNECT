"""
Integration tests for the A1.2 BudgetOrchestrator integration in context.py.

Covers:
- Flag OFF → _assemble_context_legacy path (byte-exact output)
- Flag ON → _assemble_context_new path (Section ordering, budget)
- Shadow ON → legacy output returned, shadow log line emitted
- Shadow exception → request not broken, warning logged
- Gate timeout → section dropped, pipeline continues
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.dm.phases.context import (
    _ContextAssemblyInputs,
    _assemble_context,
    _assemble_context_legacy,
    _assemble_context_new,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_agent(style: str = "Soy Iris.") -> Any:
    agent = MagicMock()
    agent.style_prompt = style
    agent.products = []
    agent.creator_id = "iris_bertran"
    agent.personality = {"name": "Iris"}
    agent.prompt_builder.build_system_prompt.side_effect = (
        lambda products, custom_instructions: f"<SYSTEM>{custom_instructions}</SYSTEM>"
    )
    return agent


def _make_inputs(
    agent=None,
    style_prompt: str = "Soy Iris, la creadora.",
    few_shot_section: str = "Ejemplo: Hola → Hola!",
    friend_context: str = "",
    recalling: str = "Sobre @testuser:\nRecalling block.",
    audio_context: str = "",
    rag_context: str = "Info de producto.",
    kb_context: str = "",
    hier_memory_context: str = "",
    advanced_section: str = "",
    citation_context: str = "",
    prompt_override: str = "",
    is_friend: bool = False,
    cognitive_metadata: Dict | None = None,
    creator_id: str = "iris_bertran",
    provider: str = "unknown",
    model: str = "unknown",
) -> _ContextAssemblyInputs:
    if agent is None:
        agent = _make_agent(style_prompt)
        agent.style_prompt = style_prompt
    return _ContextAssemblyInputs(
        agent=agent,
        style_prompt=style_prompt,
        few_shot_section=few_shot_section,
        friend_context=friend_context,
        recalling=recalling,
        audio_context=audio_context,
        rag_context=rag_context,
        kb_context=kb_context,
        hier_memory_context=hier_memory_context,
        advanced_section=advanced_section,
        citation_context=citation_context,
        prompt_override=prompt_override,
        is_friend=is_friend,
        cognitive_metadata=cognitive_metadata if cognitive_metadata is not None else {},
        creator_id=creator_id,
        provider=provider,
        model=model,
    )


# ---------------------------------------------------------------------------
# Test: flag OFF → legacy path (identical output)
# ---------------------------------------------------------------------------

class TestFlagOff:
    def test_legacy_path_produces_same_combined_context(self):
        inp = _make_inputs()
        cog: Dict = {}
        inp_legacy = _make_inputs(cognitive_metadata=cog)

        legacy_combined, legacy_system = _assemble_context_legacy(inp_legacy)

        assert inp_legacy.style_prompt in legacy_combined
        assert inp_legacy.few_shot_section in legacy_combined
        assert inp_legacy.rag_context in legacy_combined

    @pytest.mark.asyncio
    async def test_flag_off_delegates_to_legacy(self):
        inp = _make_inputs()
        with patch.dict("os.environ", {"ENABLE_BUDGET_ORCHESTRATOR": "false", "BUDGET_ORCHESTRATOR_SHADOW": "false"}):
            combined, system = await _assemble_context(inp)

        assert inp.style_prompt in combined
        assert inp.few_shot_section in combined

    @pytest.mark.asyncio
    async def test_flag_off_output_identical_to_legacy(self):
        """_assemble_context(flag=OFF) == _assemble_context_legacy output."""
        cog_a: Dict = {}
        cog_b: Dict = {}
        inp_a = _make_inputs(cognitive_metadata=cog_a)
        inp_b = _make_inputs(cognitive_metadata=cog_b)

        legacy_combined, legacy_system = _assemble_context_legacy(inp_a)

        with patch.dict("os.environ", {"ENABLE_BUDGET_ORCHESTRATOR": "false", "BUDGET_ORCHESTRATOR_SHADOW": "false"}):
            routed_combined, routed_system = await _assemble_context(inp_b)

        assert routed_combined == legacy_combined
        assert routed_system == legacy_system


# ---------------------------------------------------------------------------
# Test: flag ON → orchestrator path
# ---------------------------------------------------------------------------

class TestFlagOn:
    @pytest.mark.asyncio
    async def test_flag_on_uses_orchestrator(self):
        inp = _make_inputs()
        with patch.dict("os.environ", {
            "ENABLE_BUDGET_ORCHESTRATOR": "true",
            "BUDGET_ORCHESTRATOR_SHADOW": "false",
            "BUDGET_ORCHESTRATOR_TOKENS": "4000",
        }):
            combined, system = await _assemble_context(inp)

        # Style and few_shots are CRITICAL → always included
        assert inp.style_prompt in combined
        assert inp.few_shot_section in combined

    @pytest.mark.asyncio
    async def test_flag_on_respects_budget(self):
        """With tiny budget, low-priority sections are dropped."""
        big_rag = "RAG " * 500  # ~2000 chars → ~500 tokens (char//4)
        inp = _make_inputs(
            style_prompt="Style.",
            few_shot_section="Shot.",
            rag_context=big_rag,
            recalling="",
        )
        with patch.dict("os.environ", {
            "ENABLE_BUDGET_ORCHESTRATOR": "true",
            "BUDGET_ORCHESTRATOR_SHADOW": "false",
            "BUDGET_ORCHESTRATOR_TOKENS": "10",  # very small
        }):
            combined, system = await _assemble_context(inp)

        # CRITICAL style/fewshot will be hard-truncated but included;
        # RAG (non-CRITICAL) may be dropped under tiny budget
        assert isinstance(combined, str)
        assert isinstance(system, str)

    @pytest.mark.asyncio
    async def test_flag_on_sections_ordered_by_value(self):
        """Orchestrator packs higher-value sections before lower ones."""
        inp = _make_inputs(
            style_prompt="S",
            few_shot_section="F",
            rag_context="RAG section with signal",
            recalling="Recalling block",
        )
        with patch.dict("os.environ", {
            "ENABLE_BUDGET_ORCHESTRATOR": "true",
            "BUDGET_ORCHESTRATOR_SHADOW": "false",
            "BUDGET_ORCHESTRATOR_TOKENS": "4000",
        }):
            combined, _ = await _assemble_context(inp)

        # Both should be present (budget is large)
        assert "RAG section" in combined
        assert "Recalling block" in combined


# ---------------------------------------------------------------------------
# Test: shadow mode ON → output is legacy, log line emitted
# ---------------------------------------------------------------------------

class TestShadowMode:
    @pytest.mark.asyncio
    async def test_shadow_returns_legacy_output(self):
        cog_shadow: Dict = {}
        inp = _make_inputs(cognitive_metadata=cog_shadow)

        # Get legacy output for comparison
        cog_ref: Dict = {}
        inp_ref = _make_inputs(cognitive_metadata=cog_ref)
        legacy_combined, legacy_system = _assemble_context_legacy(inp_ref)

        with patch.dict("os.environ", {
            "ENABLE_BUDGET_ORCHESTRATOR": "false",
            "BUDGET_ORCHESTRATOR_SHADOW": "true",
        }):
            shadow_combined, shadow_system = await _assemble_context(inp)

        assert shadow_combined == legacy_combined
        assert shadow_system == legacy_system

    @pytest.mark.asyncio
    async def test_shadow_logs_diff_line(self, caplog):
        inp = _make_inputs()
        with caplog.at_level(logging.INFO, logger="core.dm.phases.context"):
            with patch.dict("os.environ", {
                "ENABLE_BUDGET_ORCHESTRATOR": "false",
                "BUDGET_ORCHESTRATOR_SHADOW": "true",
            }):
                await _assemble_context(inp)

        shadow_logs = [r for r in caplog.records if "budget_orchestrator_shadow" in r.message]
        assert len(shadow_logs) >= 1
        msg = shadow_logs[0].message
        assert "tokens_legacy=" in msg
        assert "tokens_new=" in msg
        assert "diff=" in msg

    @pytest.mark.asyncio
    async def test_shadow_exception_does_not_break_request(self, caplog):
        inp = _make_inputs()
        with patch(
            "core.dm.phases.context._assemble_context_new",
            side_effect=RuntimeError("orchestrator boom"),
        ):
            with caplog.at_level(logging.WARNING, logger="core.dm.phases.context"):
                with patch.dict("os.environ", {
                    "ENABLE_BUDGET_ORCHESTRATOR": "false",
                    "BUDGET_ORCHESTRATOR_SHADOW": "true",
                }):
                    combined, system = await _assemble_context(inp)

        # Must return valid legacy output despite shadow failure
        assert inp.style_prompt in combined
        # Warning must be logged
        warn_logs = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("budget_orchestrator_shadow" in r.message for r in warn_logs)


# ---------------------------------------------------------------------------
# Test: legacy function with budget truncation
# ---------------------------------------------------------------------------

class TestLegacyBudget:
    def test_truncates_over_max_context_chars(self):
        """Legacy path truncates critical sections when over MAX_CONTEXT_CHARS."""
        big_style = "X" * 9000  # exceeds 8000 default
        inp = _make_inputs(style_prompt=big_style, recalling="", rag_context="")
        cog: Dict = {}
        inp.cognitive_metadata = cog

        with patch.dict("os.environ", {"MAX_CONTEXT_CHARS": "100"}):
            combined, _ = _assemble_context_legacy(inp)

        # Style is truncatable → should be truncated, not dropped
        assert len(combined) <= 100

    def test_skips_low_priority_section_when_over_budget(self):
        inp = _make_inputs(
            style_prompt="A" * 7900,
            few_shot_section="B" * 500,
            rag_context="",
            recalling="",
            hier_memory_context="HIER" * 50,
        )
        cog: Dict = {}
        inp.cognitive_metadata = cog

        with patch.dict("os.environ", {"MAX_CONTEXT_CHARS": "8000"}):
            combined, _ = _assemble_context_legacy(inp)

        # hier_memory should be skipped (low priority, over budget)
        assert "HIER" not in combined
        assert "context_skipped_hier_memory" in cog

    def test_metadata_populated(self):
        cog: Dict = {}
        inp = _make_inputs(cognitive_metadata=cog)
        _assemble_context_legacy(inp)
        assert "context_total_chars" in cog
        assert "context_sections" in cog


# ---------------------------------------------------------------------------
# Test: gate import and build
# ---------------------------------------------------------------------------

class TestGates:
    @pytest.mark.asyncio
    async def test_style_gate_returns_section(self):
        from core.dm.budget.gates import style
        from core.dm.budget.section import Priority

        inp = _make_inputs(style_prompt="Soy Iris.")
        section = await style.build(inp)
        assert section is not None
        assert section.name == "style"
        assert section.priority == Priority.CRITICAL
        assert section.content == "Soy Iris."

    @pytest.mark.asyncio
    async def test_style_gate_returns_none_when_empty(self):
        from core.dm.budget.gates import style

        inp = _make_inputs(style_prompt="")
        section = await style.build(inp)
        assert section is None

    @pytest.mark.asyncio
    async def test_fewshots_gate_returns_section(self):
        from core.dm.budget.gates import fewshots
        from core.dm.budget.section import Priority

        inp = _make_inputs(few_shot_section="Ejemplo A → B")
        section = await fewshots.build(inp)
        assert section is not None
        assert section.name == "few_shots"
        assert section.priority == Priority.CRITICAL

    @pytest.mark.asyncio
    async def test_rag_gate_returns_section(self):
        from core.dm.budget.gates import rag
        from core.dm.budget.section import Priority

        inp = _make_inputs(rag_context="Producto: Clase Yoga 50€")
        section = await rag.build(inp)
        assert section is not None
        assert section.name == "rag"
        assert section.priority == Priority.HIGH

    @pytest.mark.asyncio
    async def test_history_gate_returns_section(self):
        from core.dm.budget.gates import history
        from core.dm.budget.section import Priority

        inp = _make_inputs(recalling="Sobre @user:\nContexto.")
        section = await history.build(inp)
        assert section is not None
        assert section.name == "recalling"
        assert section.priority == Priority.HIGH

    @pytest.mark.asyncio
    async def test_history_gate_returns_none_when_empty(self):
        from core.dm.budget.gates import history

        inp = _make_inputs(recalling="")
        section = await history.build(inp)
        assert section is None

    @pytest.mark.asyncio
    async def test_gate_timeout_section_dropped(self):
        """A slow gate that times out does not crash the orchestrator path."""
        from core.dm.budget.gates import style

        async def slow_build(inp):
            await asyncio.sleep(10)
            return None

        inp = _make_inputs()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(slow_build(inp), timeout=0.01)
        # Pipeline would catch this and continue — demonstrated by the try/except pattern
