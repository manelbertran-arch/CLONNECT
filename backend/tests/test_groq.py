import pytest
import pytest
#!/usr/bin/env python3
"""
Test rápido para verificar que Groq funciona.
"""

import os
import sys
import asyncio

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set API key for test
os.environ["GROQ_API_KEY"] = "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"
os.environ["LLM_PROVIDER"] = "groq"

from core.llm import get_llm_client, GroqClient


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_groq_simple():
    """Test simple Groq call"""
    print("Testing Groq API...")

    client = get_llm_client("groq")
    assert isinstance(client, GroqClient), "Should return GroqClient"

    response = await client.generate("Responde solo con 'OK' si funcionas correctamente.")
    print(f"Response: {response}")

    assert response is not None
    assert len(response) > 0
    print("✓ Groq API funciona correctamente!")
    return True


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_groq_chat():
    """Test Groq chat completion"""
    print("\nTesting Groq chat...")

    client = GroqClient()
    messages = [
        {"role": "system", "content": "Eres Manel, un experto en automatización. Responde de forma breve."},
        {"role": "user", "content": "Hola, qué tal?"}
    ]

    response = await client.chat(messages)
    print(f"Chat response: {response}")

    assert response is not None
    assert len(response) > 0
    print("✓ Groq chat funciona correctamente!")
    return True


@pytest.mark.asyncio
@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_default_provider():
    """Test that default provider is Groq"""
    print("\nTesting default provider...")

    # Clear any existing setting
    if "LLM_PROVIDER" in os.environ:
        del os.environ["LLM_PROVIDER"]

    client = get_llm_client()
    assert isinstance(client, GroqClient), f"Default should be GroqClient, got {type(client)}"
    print("✓ Default provider es Groq!")
    return True


async def main():
    """Run all tests"""
    print("=" * 50)
    print("GROQ API TESTS")
    print("=" * 50)

    try:
        await test_groq_simple()
        await test_groq_chat()
        await test_default_provider()

        print("\n" + "=" * 50)
        print("✓ TODOS LOS TESTS PASARON!")
        print("=" * 50)
        return True
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
