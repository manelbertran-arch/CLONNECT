"""Unit tests for commitments gate (A1.4)."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from core.dm.budget.gates.commitments import build
from core.dm.budget.section import Priority


def _make_inputs(commitment_text="", cognitive_metadata=None):
    inp = MagicMock()
    inp.commitment_text = commitment_text
    inp.cognitive_metadata = cognitive_metadata or {}
    return inp


class TestCommitmentsGate:
    def test_returns_none_when_no_content(self):
        inp = _make_inputs(commitment_text="")
        result = asyncio.get_event_loop().run_until_complete(build(inp))
        assert result is None

    def test_returns_none_when_no_pending_flag(self):
        inp = _make_inputs(
            commitment_text="Will call tomorrow.",
            cognitive_metadata={"commitments_pending": False},
        )
        result = asyncio.get_event_loop().run_until_complete(build(inp))
        assert result is None

    def test_returns_section_when_commitments_pending(self):
        inp = _make_inputs(
            commitment_text="Will send info tomorrow.",
            cognitive_metadata={"commitments_pending": True},
        )
        section = asyncio.get_event_loop().run_until_complete(build(inp))
        assert section is not None
        assert section.name == "commitments"
        assert section.priority == Priority.MEDIUM
        assert "Will send info tomorrow." in section.content

    def test_cap_tokens_tight(self):
        inp = _make_inputs(
            commitment_text="Commitment.",
            cognitive_metadata={"commitments_pending": True},
        )
        section = asyncio.get_event_loop().run_until_complete(build(inp))
        assert section is not None
        assert section.cap_tokens <= 200

    def test_returns_none_on_exception(self):
        inp = MagicMock()
        inp.commitment_text = "non-empty"
        inp.cognitive_metadata = MagicMock()
        inp.cognitive_metadata.get = MagicMock(side_effect=RuntimeError("boom"))
        result = asyncio.get_event_loop().run_until_complete(build(inp))
        assert result is None
