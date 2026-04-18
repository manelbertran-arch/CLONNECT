"""
TokenCounter — provider-agnostic token counting wrapper.
Priority: tiktoken (openai/openrouter) → google.generativeai → chars//4 fallback.
Design: docs/sprint5_planning/ARC1_token_aware_budget.md §2.4

Contract: not a billing source of truth — estimation sufficient for budget (<3% error).
"""

from __future__ import annotations

from typing import Any, Optional


class TokenCounter:
    """Wrapper agnostic to the active provider.

    Resolution order:
    1. tiktoken with cl100k_base (openai / openrouter)
    2. google.generativeai GenerativeModel.count_tokens (gemini-*)
    3. len(text) // 4 safe fallback
    """

    def __init__(self, provider: str, model: str) -> None:
        self.provider = provider
        self.model = model
        self._impl: Optional[Any] = self._resolve()

    def _resolve(self) -> Optional[Any]:
        if self.provider in ("openai", "openrouter"):
            try:
                import tiktoken
                try:
                    return tiktoken.encoding_for_model(self.model)
                except KeyError:
                    return tiktoken.get_encoding("cl100k_base")
            except ImportError:
                return None
        if self.provider == "gemini":
            try:
                import google.generativeai as genai  # type: ignore[import]
                return genai.GenerativeModel(self.model)
            except (ImportError, Exception):
                return None
        return None

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self._impl is None:
            return len(text) // 4
        if self.provider in ("openai", "openrouter"):
            return len(self._impl.encode(text))
        if self.provider == "gemini":
            try:
                return self._impl.count_tokens(text).total_tokens
            except Exception:
                return len(text) // 4
        return len(text) // 4

    def truncate(self, text: str, max_tokens: int) -> str:
        if not text or max_tokens <= 0:
            return ""
        if self._impl is None:
            return text[: max_tokens * 4]
        if self.provider in ("openai", "openrouter"):
            tokens = self._impl.encode(text)
            return self._impl.decode(tokens[:max_tokens])
        if self.provider == "gemini":
            actual = self.count(text)
            if actual == 0:
                return text[: max_tokens * 4]
            ratio = len(text) / actual
            return text[: int(max_tokens * ratio)]
        return text[: max_tokens * 4]
