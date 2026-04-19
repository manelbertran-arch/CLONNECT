"""
Tests for core/dm/budget/tokenizer.py
Covers: fallback path (no tiktoken/genai), tiktoken path (mocked),
        gemini path (mocked), truncate behaviour, edge cases.
"""

from unittest.mock import MagicMock, patch

import pytest

from core.dm.budget.tokenizer import TokenCounter


class TestFallbackProvider:
    """Provider 'unknown' → always uses chars//4 fallback."""

    def _tc(self) -> TokenCounter:
        tc = TokenCounter(provider="unknown", model="some-model")
        tc._impl = None
        return tc

    def test_count_empty_string(self):
        assert self._tc().count("") == 0

    def test_count_chars_div_4(self):
        tc = self._tc()
        text = "a" * 400
        assert tc.count(text) == 100

    def test_count_odd_length(self):
        tc = self._tc()
        assert tc.count("abc") == 0  # 3 // 4 == 0

    def test_truncate_empty(self):
        assert self._tc().truncate("", 100) == ""

    def test_truncate_max_zero(self):
        assert self._tc().truncate("hello", 0) == ""

    def test_truncate_chars_times_4(self):
        tc = self._tc()
        text = "x" * 100
        result = tc.truncate(text, 10)
        assert result == "x" * 40


class TestOpenAIProvider:
    """tiktoken path (openai provider)."""

    def _make_mock_encoding(self):
        enc = MagicMock()
        enc.encode.side_effect = lambda text: list(range(len(text.split())))
        enc.decode.side_effect = lambda tokens: " ".join(str(t) for t in tokens)
        return enc

    def test_count_delegates_to_tiktoken(self):
        enc = self._make_mock_encoding()
        tc = TokenCounter.__new__(TokenCounter)
        tc.provider = "openai"
        tc.model = "gpt-4o"
        tc._impl = enc

        tc.count("hello world")
        enc.encode.assert_called_once_with("hello world")

    def test_count_returns_token_length(self):
        enc = MagicMock()
        enc.encode.return_value = [1, 2, 3, 4, 5]
        tc = TokenCounter.__new__(TokenCounter)
        tc.provider = "openai"
        tc.model = "gpt-4o"
        tc._impl = enc

        assert tc.count("some text") == 5

    def test_truncate_uses_encode_decode(self):
        enc = MagicMock()
        enc.encode.return_value = [10, 20, 30, 40, 50]
        enc.decode.return_value = "truncated"
        tc = TokenCounter.__new__(TokenCounter)
        tc.provider = "openai"
        tc.model = "gpt-4o"
        tc._impl = enc

        result = tc.truncate("some long text", max_tokens=3)
        enc.encode.assert_called_once()
        enc.decode.assert_called_once_with([10, 20, 30])
        assert result == "truncated"

    def test_openrouter_uses_same_path(self):
        enc = MagicMock()
        enc.encode.return_value = [1, 2]
        tc = TokenCounter.__new__(TokenCounter)
        tc.provider = "openrouter"
        tc.model = "gpt-4o-mini"
        tc._impl = enc

        assert tc.count("hi") == 2

    def test_resolve_falls_back_on_import_error(self):
        with patch("builtins.__import__", side_effect=ImportError):
            tc = TokenCounter(provider="openai", model="gpt-4o")
        assert tc._impl is None

    def test_count_empty_openai(self):
        enc = MagicMock()
        enc.encode.return_value = []
        tc = TokenCounter.__new__(TokenCounter)
        tc.provider = "openai"
        tc.model = "gpt-4o"
        tc._impl = enc

        assert tc.count("") == 0


class TestGeminiProvider:
    """google.generativeai path (gemini provider)."""

    def _make_tc(self):
        model_mock = MagicMock()
        model_mock.count_tokens.return_value = MagicMock(total_tokens=42)
        tc = TokenCounter.__new__(TokenCounter)
        tc.provider = "gemini"
        tc.model = "gemini-2.5-flash-lite"
        tc._impl = model_mock
        return tc, model_mock

    def test_count_calls_count_tokens(self):
        tc, model_mock = self._make_tc()
        result = tc.count("some text")
        model_mock.count_tokens.assert_called_once_with("some text")
        assert result == 42

    def test_count_empty(self):
        tc, _ = self._make_tc()
        assert tc.count("") == 0

    def test_count_falls_back_on_exception(self):
        tc = TokenCounter.__new__(TokenCounter)
        tc.provider = "gemini"
        tc.model = "gemini-2.5-flash-lite"
        bad_model = MagicMock()
        bad_model.count_tokens.side_effect = RuntimeError("API down")
        tc._impl = bad_model

        text = "a" * 80
        result = tc.count(text)
        assert result == 80 // 4

    def test_truncate_uses_char_ratio(self):
        tc, model_mock = self._make_tc()
        model_mock.count_tokens.return_value = MagicMock(total_tokens=100)
        text = "x" * 1000
        result = tc.truncate(text, max_tokens=50)
        assert len(result) == 500

    def test_truncate_empty(self):
        tc, _ = self._make_tc()
        assert tc.truncate("", 50) == ""

    def test_truncate_max_zero(self):
        tc, _ = self._make_tc()
        assert tc.truncate("hello", 0) == ""

    def test_resolve_falls_back_on_import_error(self):
        with patch.dict("sys.modules", {"google.generativeai": None}):
            tc = TokenCounter(provider="gemini", model="gemini-2.5-flash-lite")
        assert tc._impl is None
