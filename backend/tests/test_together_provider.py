"""Tests for Together.ai fine-tuned model provider."""

import httpx
import pytest

from core.providers.together_provider import generate_finetuned_response


@pytest.mark.asyncio
async def test_success(monkeypatch):
    """Successful API call returns content string."""
    mock_json = {
        "choices": [{"message": {"content": " Hola! Cómo estás? "}}]
    }

    async def mock_post(self, url, **kwargs):
        resp = httpx.Response(200, json=mock_json, request=httpx.Request("POST", url))
        return resp

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await generate_finetuned_response(
        messages=[{"role": "user", "content": "hola"}],
        api_key="test-key",
        model_id="test-model",
    )
    assert result == "Hola! Cómo estás?"


@pytest.mark.asyncio
async def test_timeout(monkeypatch):
    """Timeout returns None for fallback."""

    async def mock_post(self, url, **kwargs):
        raise httpx.TimeoutException("Connection timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    result = await generate_finetuned_response(
        messages=[{"role": "user", "content": "hola"}],
        api_key="test-key",
        model_id="test-model",
    )
    assert result is None


@pytest.mark.asyncio
async def test_missing_config():
    """Missing API key or model ID returns None without calling API."""
    result = await generate_finetuned_response(
        messages=[{"role": "user", "content": "hola"}],
        api_key=None,
        model_id=None,
    )
    assert result is None
