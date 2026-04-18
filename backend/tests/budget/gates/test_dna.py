"""Unit tests for dna gate (A1.4)."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from core.dm.budget.gates.dna import build
from core.dm.budget.section import Priority


def _make_inputs(dna_context="", cognitive_metadata=None):
    inp = MagicMock()
    inp.dna_context = dna_context
    inp.cognitive_metadata = cognitive_metadata or {}
    return inp


class TestDnaGate:
    def test_returns_none_when_no_content(self):
        inp = _make_inputs(dna_context="")
        result = asyncio.get_event_loop().run_until_complete(build(inp))
        assert result is None

    def test_returns_section_with_content(self):
        inp = _make_inputs(dna_context="Relation DNA: user likes music.")
        section = asyncio.get_event_loop().run_until_complete(build(inp))
        assert section is not None
        assert section.name == "dna"
        assert section.priority == Priority.MEDIUM
        assert "Relation DNA: user likes music." in section.content

    def test_value_score_static_positive(self):
        inp = _make_inputs(dna_context="Some DNA context.")
        section = asyncio.get_event_loop().run_until_complete(build(inp))
        assert section is not None
        assert section.value_score > 0.0

    def test_cap_tokens_within_design_limit(self):
        inp = _make_inputs(dna_context="DNA.")
        section = asyncio.get_event_loop().run_until_complete(build(inp))
        assert section is not None
        assert section.cap_tokens <= 400

    def test_returns_none_on_exception(self):
        inp = MagicMock()
        inp.dna_context = "non-empty"
        inp.cognitive_metadata = MagicMock()
        inp.cognitive_metadata.get = MagicMock(side_effect=RuntimeError("boom"))
        result = asyncio.get_event_loop().run_until_complete(build(inp))
        assert result is None
