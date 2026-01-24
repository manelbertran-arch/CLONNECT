"""
Cliente LLM simplificado para Clonnect Creators
Soporta Groq (default), OpenAI y Anthropic
"""

import os
from typing import Optional, List, Dict, Any
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

# Default provider - Groq es gratis con Llama 3.1
DEFAULT_PROVIDER = "groq"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"


class LLMClient(ABC):
    """Cliente LLM base"""

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str:
        pass

    @abstractmethod
    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        pass


class OpenAIClient(LLMClient):
    """Cliente OpenAI"""

    def __init__(self, api_key: str = None, model: str = "gpt-4o-mini"):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client

    async def generate(self, prompt: str, **kwargs) -> str:
        return await self.chat([{"role": "user", "content": prompt}], **kwargs)

    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        client = self._get_client()
        response = await client.chat.completions.create(
            model=kwargs.get("model", self.model),
            messages=messages,
            max_tokens=kwargs.get("max_tokens", 1000),
            temperature=kwargs.get("temperature", 0.7)
        )
        return response.choices[0].message.content


class AnthropicClient(LLMClient):
    """Cliente Anthropic"""

    def __init__(self, api_key: str = None, model: str = "claude-3-haiku-20240307"):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(api_key=self.api_key)
        return self._client

    async def generate(self, prompt: str, **kwargs) -> str:
        return await self.chat([{"role": "user", "content": prompt}], **kwargs)

    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        client = self._get_client()
        response = await client.messages.create(
            model=kwargs.get("model", self.model),
            messages=messages,
            max_tokens=kwargs.get("max_tokens", 1000)
        )
        return response.content[0].text


class GroqClient(LLMClient):
    """Cliente Groq - Llama 3.1 70B gratis"""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = (api_key or os.getenv("GROQ_API_KEY") or "").strip()
        self.model = model or DEFAULT_GROQ_MODEL
        self._client = None
        print(f"[GroqClient] Initialized with model={self.model}, api_key={'set' if self.api_key else 'NOT SET'}", flush=True)

    def _get_client(self):
        if self._client is None:
            print(f"[GroqClient] Creating AsyncGroq client...", flush=True)
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=self.api_key)
            print(f"[GroqClient] AsyncGroq client created", flush=True)
        return self._client

    async def generate(self, prompt: str, **kwargs) -> str:
        print(f"[GroqClient.generate] Prompt length: {len(prompt)}", flush=True)
        return await self.chat([{"role": "user", "content": prompt}], **kwargs)

    async def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        print(f"[GroqClient.chat] Starting with {len(messages)} messages", flush=True)
        client = self._get_client()
        try:
            print(f"[GroqClient.chat] Calling Groq API with model={kwargs.get('model', self.model)}...", flush=True)
            response = await client.chat.completions.create(
                model=kwargs.get("model", self.model),
                messages=messages,
                max_tokens=kwargs.get("max_tokens", 1000),
                temperature=kwargs.get("temperature", 0.7)
            )
            print(f"[GroqClient.chat] Groq API returned successfully", flush=True)
            return response.choices[0].message.content
        except Exception as e:
            print(f"[GroqClient.chat] EXCEPTION: {e}", flush=True)
            logger.error(f"Groq API error: {e}")
            raise


def get_llm_client(provider: str = None) -> LLMClient:
    """Factory para obtener cliente LLM

    Providers disponibles:
    - groq (default): Llama 3.1 70B - GRATIS
    - openai: GPT-4o-mini
    - anthropic: Claude 3 Haiku
    """
    if provider is None:
        provider = os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER)

    provider = provider.lower()
    logger.info(f"Usando LLM provider: {provider}")

    if provider == "groq":
        return GroqClient()
    elif provider == "openai":
        return OpenAIClient()
    elif provider == "anthropic":
        return AnthropicClient()
    else:
        logger.warning(f"Provider {provider} no reconocido, usando Groq")
        return GroqClient()
