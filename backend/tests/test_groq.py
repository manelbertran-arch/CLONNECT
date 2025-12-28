#!/usr/bin/env python3
"""
Test rápido para verificar que Groq funciona.
Skip if groq package not installed.
"""

import pytest
import os
import sys
import asyncio

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Check if groq is available
try:
    import groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

# Skip all tests if groq not installed
pytestmark = pytest.mark.skipif(not GROQ_AVAILABLE, reason="groq package not installed")

# Set API key for test
os.environ["GROQ_API_KEY"] = os.environ.get("GROQ_API_KEY", "test_key")
os.environ["LLM_PROVIDER"] = "groq"

from core.llm import get_llm_client, GroqClient


@pytest.mark.asyncio
async def test_groq_simple():
    """Test simple Groq call"""
    client = get_llm_client("groq")
    assert isinstance(client, GroqClient), "Should return GroqClient"

    response = await client.generate("Responde solo con 'OK' si funcionas correctamente.")
    assert response is not None
    assert len(response) > 0


@pytest.mark.asyncio
async def test_groq_chat():
    """Test Groq chat completion"""
    client = GroqClient()
    messages = [
        {"role": "system", "content": "Eres Manel, un experto en automatización. Responde de forma breve."},
        {"role": "user", "content": "Hola, qué tal?"}
    ]

    response = await client.chat(messages)
    assert response is not None
    assert len(response) > 0


@pytest.mark.asyncio
async def test_default_provider():
    """Test that default provider is Groq"""
    # Clear any existing setting
    old_provider = os.environ.pop("LLM_PROVIDER", None)

    try:
        client = get_llm_client()
        assert isinstance(client, GroqClient), f"Default should be GroqClient, got {type(client)}"
    finally:
        # Restore
        if old_provider:
            os.environ["LLM_PROVIDER"] = old_provider
