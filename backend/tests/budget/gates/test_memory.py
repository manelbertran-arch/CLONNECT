"""Unit tests for memory gate (A1.4)."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from core.dm.budget.gates.memory import build
from core.dm.budget.section import Priority


def _make_inputs(hier_memory_context="", cognitive_metadata=None):
    inp = MagicMock()
    inp.hier_memory_context = hier_memory_context
    inp.cognitive_metadata = cognitive_metadata or {}
    return inp


class TestMemoryGate:
    def test_returns_none_when_no_content(self):
        inp = _make_inputs(hier_memory_context="")
        result = asyncio.get_event_loop().run_until_complete(build(inp))
        assert result is None

    def test_high_priority_when_memory_recalled(self):
        inp = _make_inputs(
            hier_memory_context="User prefers morning calls.",
            cognitive_metadata={"memory_recalled": True},
        )
        section = asyncio.get_event_loop().run_until_complete(build(inp))
        assert section is not None
        assert section.priority == Priority.HIGH
        assert section.name == "memory"

    def test_high_priority_when_episodic_recalled(self):
        inp = _make_inputs(
            hier_memory_context="Episodic memory data.",
            cognitive_metadata={"episodic_recalled": True},
        )
        section = asyncio.get_event_loop().run_until_complete(build(inp))
        assert section is not None
        assert section.priority == Priority.HIGH

    def test_low_priority_when_not_recalled(self):
        inp = _make_inputs(
            hier_memory_context="Some memory.",
            cognitive_metadata={"memory_recalled": False, "episodic_recalled": False},
        )
        section = asyncio.get_event_loop().run_until_complete(build(inp))
        assert section is not None
        assert section.priority == Priority.LOW

    def test_value_score_high_when_recalled(self):
        inp = _make_inputs(
            hier_memory_context="Memory.",
            cognitive_metadata={"memory_recalled": True},
        )
        section = asyncio.get_event_loop().run_until_complete(build(inp))
        assert section is not None
        assert section.value_score >= 0.70

    def test_value_score_low_when_not_recalled(self):
        inp = _make_inputs(
            hier_memory_context="Memory.",
            cognitive_metadata={},
        )
        section = asyncio.get_event_loop().run_until_complete(build(inp))
        assert section is not None
        assert section.value_score < 0.70

    def test_returns_none_on_exception(self):
        inp = MagicMock()
        inp.hier_memory_context = "non-empty"
        inp.cognitive_metadata = MagicMock()
        inp.cognitive_metadata.get = MagicMock(side_effect=RuntimeError("boom"))
        result = asyncio.get_event_loop().run_until_complete(build(inp))
        assert result is None
