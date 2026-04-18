"""Unit tests for audio gate (A1.4)."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from core.dm.budget.gates.audio import build
from core.dm.budget.section import Priority


def _make_inputs(audio_context="", cognitive_metadata=None):
    inp = MagicMock()
    inp.audio_context = audio_context
    inp.cognitive_metadata = cognitive_metadata or {}
    return inp


class TestAudioGate:
    def test_returns_none_when_no_content(self):
        inp = _make_inputs(audio_context="")
        result = asyncio.get_event_loop().run_until_complete(build(inp))
        assert result is None

    def test_returns_none_when_audio_intel_absent(self):
        inp = _make_inputs(
            audio_context="Audio content.",
            cognitive_metadata={"audio_intel": False},
        )
        result = asyncio.get_event_loop().run_until_complete(build(inp))
        assert result is None

    def test_returns_section_when_audio_intel_set(self):
        inp = _make_inputs(
            audio_context="Audio transcription here.",
            cognitive_metadata={"audio_intel": True},
        )
        section = asyncio.get_event_loop().run_until_complete(build(inp))
        assert section is not None
        assert section.name == "audio"
        assert section.priority == Priority.HIGH
        assert "Audio transcription here." in section.content

    def test_cap_tokens_applied(self):
        inp = _make_inputs(
            audio_context="Audio.",
            cognitive_metadata={"audio_intel": True},
        )
        section = asyncio.get_event_loop().run_until_complete(build(inp))
        assert section is not None
        assert section.cap_tokens > 0

    def test_returns_none_on_exception(self):
        inp = MagicMock()
        inp.audio_context = "non-empty"
        inp.cognitive_metadata = MagicMock()
        inp.cognitive_metadata.get = MagicMock(side_effect=RuntimeError("boom"))
        result = asyncio.get_event_loop().run_until_complete(build(inp))
        assert result is None
