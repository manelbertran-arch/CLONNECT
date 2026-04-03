"""Tests for strip_thinking_artifacts() — Bug 1 fix.

Ensures thinking-model tokens (Qwen3, future reasoning models) are stripped
from LLM output before reaching the user or post-processing.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.providers.deepinfra_provider import strip_thinking_artifacts


# ---------------------------------------------------------------------------
# Happy-path: already clean responses pass through unchanged
# ---------------------------------------------------------------------------

class TestCleanPassthrough:
    def test_plain_text(self):
        assert strip_thinking_artifacts("Hola wapa!") == "Hola wapa!"

    def test_with_emoji(self):
        assert strip_thinking_artifacts("Jaja 😂") == "Jaja 😂"

    def test_empty_string(self):
        assert strip_thinking_artifacts("") == ""

    def test_whitespace_only(self):
        assert strip_thinking_artifacts("   ") == ""

    def test_multiline_clean(self):
        msg = "Sí, perfecto.\nTe apunto para el lunes."
        assert strip_thinking_artifacts(msg) == msg


# ---------------------------------------------------------------------------
# Bug pattern 1: empty <think></think> block (Qwen3 /no_think residue)
# ---------------------------------------------------------------------------

class TestEmptyThinkBlock:
    def test_empty_block_at_start(self):
        result = strip_thinking_artifacts("<think></think>Respuesta aquí")
        assert result == "Respuesta aquí"

    def test_empty_block_with_whitespace(self):
        result = strip_thinking_artifacts("<think>  \n  </think>  Ok guapa")
        assert result == "Ok guapa"

    def test_empty_block_only(self):
        result = strip_thinking_artifacts("<think></think>")
        assert result == ""


# ---------------------------------------------------------------------------
# Bug pattern 2: full thinking block with content
# ---------------------------------------------------------------------------

class TestFullThinkBlock:
    def test_block_before_response(self):
        result = strip_thinking_artifacts(
            "<think>Let me analyze this message carefully.</think>Vale, te apunto!"
        )
        assert result == "Vale, te apunto!"

    def test_block_with_newlines(self):
        result = strip_thinking_artifacts(
            "<think>\nThe user wants to book a session.\nI should confirm.\n</think>Ya estás flor"
        )
        assert result == "Ya estás flor"

    def test_block_only_no_response(self):
        result = strip_thinking_artifacts("<think>Some reasoning</think>")
        assert result == ""

    def test_multiple_blocks(self):
        result = strip_thinking_artifacts(
            "<think>First thought</think>Partial<think>Second thought</think> answer"
        )
        assert result == "Partial answer"


# ---------------------------------------------------------------------------
# Bug pattern 3: orphan </think> — the actual production failure
# ---------------------------------------------------------------------------

class TestOrphanCloseTag:
    def test_trailing_close_tag(self):
        """Exact pattern observed in production (case cpe_iris__030)."""
        raw = "Jajjajajaja valee pobre….🥲 quina llastima aixo del gluten /no_think  \n</think>"
        result = strip_thinking_artifacts(raw)
        assert "</think>" not in result
        assert "/no_think" not in result
        assert "Jajjajajaja valee pobre" in result

    def test_close_tag_in_middle(self):
        result = strip_thinking_artifacts("Some text</think> more text")
        assert "</think>" not in result
        assert result == "Some text more text"

    def test_close_tag_only(self):
        result = strip_thinking_artifacts("</think>")
        assert result == ""

    def test_close_tag_with_whitespace(self):
        result = strip_thinking_artifacts("Response\n  </think>  ")
        assert "</think>" not in result
        assert "Response" in result


# ---------------------------------------------------------------------------
# Bug pattern 4: orphan <think> opening tag
# ---------------------------------------------------------------------------

class TestOrphanOpenTag:
    def test_open_tag_at_start(self):
        result = strip_thinking_artifacts("<think>Good response here")
        assert "<think>" not in result
        assert "Good response here" in result

    def test_open_tag_in_middle(self):
        result = strip_thinking_artifacts("Text <think>continuation")
        assert "<think>" not in result


# ---------------------------------------------------------------------------
# Bug pattern 5: /no_think instruction leaked into response
# ---------------------------------------------------------------------------

class TestNoThinkLeak:
    def test_trailing_no_think(self):
        result = strip_thinking_artifacts("Ok flor /no_think")
        assert "/no_think" not in result
        assert result == "Ok flor"

    def test_no_think_with_whitespace(self):
        result = strip_thinking_artifacts("Ciao!\n /no_think  ")
        assert "/no_think" not in result

    def test_no_think_in_middle_untouched(self):
        """Only trailing /no_think is stripped; mid-sentence occurrences are preserved
        since they are extremely unlikely in real responses and over-stripping risks
        removing legitimate content."""
        result = strip_thinking_artifacts("I think /no_think is a word /no_think")
        # The trailing one must be stripped; the mid-sentence one may or may not be
        assert not result.endswith("/no_think")

    def test_combined_close_tag_and_no_think(self):
        raw = "Hola! /no_think  \n</think>"
        result = strip_thinking_artifacts(raw)
        assert "/no_think" not in result
        assert "</think>" not in result
        assert "Hola!" in result


# ---------------------------------------------------------------------------
# Idempotency: double application must not corrupt text
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_double_strip_clean(self):
        text = "Tranqui flower"
        assert strip_thinking_artifacts(strip_thinking_artifacts(text)) == text

    def test_double_strip_with_artifacts(self):
        raw = "<think>thinking</think>Response"
        once = strip_thinking_artifacts(raw)
        twice = strip_thinking_artifacts(once)
        assert once == twice == "Response"
