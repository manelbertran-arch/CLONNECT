"""Integration tests for A1.4: all 8 gates via _assemble_context_new.

Verifies that the 4 new gates (memory, audio, commitments, dna) integrate
correctly with the BudgetOrchestrator pipeline and that S4-proximity fix
(RECENT_LEAD_MESSAGE anchor) is present in style output.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.dm.phases.context import (
    _ContextAssemblyInputs,
    _assemble_context_new,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_agent(style: str = "Soy Iris.") -> MagicMock:
    agent = MagicMock()
    agent.style_prompt = style
    agent.products = []
    agent.creator_id = "iris_bertran"
    agent.personality = {"name": "Iris"}
    agent.prompt_builder.build_system_prompt.side_effect = (
        lambda products, custom_instructions: f"<SYSTEM>{custom_instructions}</SYSTEM>"
    )
    return agent


def _make_inputs(**overrides) -> _ContextAssemblyInputs:
    defaults = dict(
        agent=_make_agent(),
        style_prompt="Soy Iris, la creadora.",
        few_shot_section="Ejemplo: Hola → Hola!",
        friend_context="",
        recalling="Sobre @testuser:\nRecalling block.",
        audio_context="",
        rag_context="Info de producto.",
        kb_context="",
        hier_memory_context="",
        advanced_section="",
        citation_context="",
        prompt_override="",
        is_friend=False,
        cognitive_metadata={},
        creator_id="iris_bertran",
        provider="unknown",
        model="unknown",
        dna_context="",
        commitment_text="",
        message="",
    )
    defaults.update(overrides)
    return _ContextAssemblyInputs(**defaults)


# ---------------------------------------------------------------------------
# S4-Proximity fix tests
# ---------------------------------------------------------------------------

class TestS4ProximityFix:
    def test_recent_lead_message_appended_to_style(self):
        inp = _make_inputs(message="Hola, ¿cómo puedo comprar tu curso?")
        combined, _ = _assemble_context_new(inp)
        assert "RECENT_LEAD_MESSAGE" in combined

    def test_no_anchor_when_message_empty(self):
        inp = _make_inputs(message="")
        combined, _ = _assemble_context_new(inp)
        assert "RECENT_LEAD_MESSAGE" not in combined

    def test_anchor_contains_tail_of_message(self):
        long_msg = "x" * 300
        inp = _make_inputs(message=long_msg)
        combined, _ = _assemble_context_new(inp)
        assert "x" * 200 in combined


# ---------------------------------------------------------------------------
# Memory gate integration
# ---------------------------------------------------------------------------

class TestMemoryGateIntegration:
    def test_memory_included_when_recalled(self):
        inp = _make_inputs(
            hier_memory_context="Hierarchical memory block.",
            cognitive_metadata={"memory_recalled": True},
        )
        combined, _ = _assemble_context_new(inp)
        assert "Hierarchical memory block." in combined

    def test_memory_excluded_when_empty(self):
        inp = _make_inputs(hier_memory_context="")
        combined, _ = _assemble_context_new(inp)
        assert "Hierarchical memory block." not in combined


# ---------------------------------------------------------------------------
# Audio gate integration
# ---------------------------------------------------------------------------

class TestAudioGateIntegration:
    def test_audio_included_when_present(self):
        inp = _make_inputs(
            audio_context="Audio note: user asked about pricing.",
            cognitive_metadata={"audio_intel": True},
        )
        combined, _ = _assemble_context_new(inp)
        assert "Audio note: user asked about pricing." in combined

    def test_audio_excluded_when_not_present(self):
        inp = _make_inputs(
            audio_context="Audio note: user asked about pricing.",
            cognitive_metadata={"audio_intel": False},
        )
        combined, _ = _assemble_context_new(inp)
        assert "Audio note: user asked about pricing." not in combined


# ---------------------------------------------------------------------------
# Commitments gate integration
# ---------------------------------------------------------------------------

class TestCommitmentsGateIntegration:
    def test_commitments_included_when_pending(self):
        inp = _make_inputs(
            commitment_text="Enviar catálogo mañana.",
            cognitive_metadata={"commitments_pending": True},
        )
        combined, _ = _assemble_context_new(inp)
        assert "Enviar catálogo mañana." in combined

    def test_commitments_excluded_when_not_pending(self):
        inp = _make_inputs(
            commitment_text="Enviar catálogo mañana.",
            cognitive_metadata={"commitments_pending": False},
        )
        combined, _ = _assemble_context_new(inp)
        assert "Enviar catálogo mañana." not in combined


# ---------------------------------------------------------------------------
# DNA gate integration
# ---------------------------------------------------------------------------

class TestDnaGateIntegration:
    def test_dna_included_when_present(self):
        inp = _make_inputs(dna_context="DNA: user is a fitness enthusiast.")
        combined, _ = _assemble_context_new(inp)
        assert "DNA: user is a fitness enthusiast." in combined

    def test_dna_excluded_when_empty(self):
        inp = _make_inputs(dna_context="")
        combined, _ = _assemble_context_new(inp)
        assert "DNA: user is a fitness enthusiast." not in combined


# ---------------------------------------------------------------------------
# All 8 sections simultaneously
# ---------------------------------------------------------------------------

class TestAll8GatesTogether:
    def test_all_sections_present_under_budget(self):
        inp = _make_inputs(
            style_prompt="Soy Iris.",
            few_shot_section="Example.",
            rag_context="RAG info.",
            recalling="Recalling block.",
            hier_memory_context="Memory block.",
            audio_context="Audio block.",
            commitment_text="Commitment block.",
            dna_context="DNA block.",
            message="Hola!",
            cognitive_metadata={
                "memory_recalled": True,
                "audio_intel": True,
                "commitments_pending": True,
                "rag_used": True,
            },
        )
        combined, system = _assemble_context_new(inp)
        assert "Soy Iris." in combined
        assert "Example." in combined
        assert "RAG info." in combined
        assert "Memory block." in combined
        assert "Audio block." in combined
        assert "Commitment block." in combined
        assert "DNA block." in combined
        assert "RECENT_LEAD_MESSAGE" in combined
        assert system  # system prompt non-empty
