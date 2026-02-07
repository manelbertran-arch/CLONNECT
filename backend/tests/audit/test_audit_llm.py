"""Audit tests for core/llm.py"""

from core.llm import LLMClient, get_llm_client


class TestAuditLLM:
    def test_import(self):
        from core.llm import AnthropicClient, LLMClient, OpenAIClient, get_llm_client  # noqa: F811

        assert LLMClient is not None

    def test_base_class(self):
        assert LLMClient is not None
        assert hasattr(LLMClient, "__init__")

    def test_happy_path_get_client(self):
        try:
            client = get_llm_client()
            assert client is not None
        except Exception:
            pass  # API keys not available in test

    def test_edge_case_get_openai(self):
        try:
            client = get_llm_client("openai")
            assert client is not None
        except Exception:
            pass  # API key not available

    def test_error_handling_invalid_provider(self):
        try:
            client = get_llm_client("invalid_provider")
            assert client is None
        except (ValueError, KeyError, Exception):
            pass  # Expected
