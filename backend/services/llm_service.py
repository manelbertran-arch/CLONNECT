"""
LLM (Large Language Model) Service.

Extracted from dm_agent.py as part of REFACTOR-PHASE2.
Provides unified interface for multiple LLM providers.
"""
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    GROQ = "groq"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass
class LLMResponse:
    """
    Response from LLM generation.

    Attributes:
        content: Generated text content
        model: Model used for generation
        tokens_used: Total tokens consumed
        metadata: Additional response metadata
        created_at: Timestamp of response
    """

    content: str
    model: str
    tokens_used: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_empty(self) -> bool:
        """Check if response content is empty."""
        return not self.content or not self.content.strip()


class LLMService:
    """
    Service for LLM text generation.

    Supports multiple providers: Groq, OpenAI, Anthropic.
    Provides unified interface for chat and text generation.
    """

    # Default models per provider
    DEFAULT_MODELS = {
        LLMProvider.GROQ: "llama-3.3-70b-versatile",
        LLMProvider.OPENAI: "gpt-4o-mini",
        LLMProvider.ANTHROPIC: "claude-3-haiku-20240307",
    }

    # Available models per provider
    AVAILABLE_MODELS = {
        LLMProvider.GROQ: [
            "llama-3.3-70b-versatile",
            "llama-3.1-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
        ],
        LLMProvider.OPENAI: [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
        ],
        LLMProvider.ANTHROPIC: [
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
        ],
    }

    def __init__(
        self,
        provider: LLMProvider = LLMProvider.OPENAI,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        api_key: Optional[str] = None,
    ) -> None:
        """
        Initialize LLM service.

        Args:
            provider: LLM provider to use (default: OpenAI)
            model: Specific model name (uses provider default if not set)
            temperature: Generation temperature 0-1
            max_tokens: Maximum tokens in response
            api_key: API key (falls back to environment variable)
        """
        self.provider = provider
        self.model = model or self.DEFAULT_MODELS.get(provider)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._api_key = api_key or self._get_api_key_from_env()
        self._client = None

        logger.info(
            f"[LLMService] Initialized: provider={provider.value}, "
            f"model={self.model}"
        )

    def _get_api_key_from_env(self) -> Optional[str]:
        """Get API key from environment variables."""
        key_map = {
            LLMProvider.GROQ: "GROQ_API_KEY",
            LLMProvider.OPENAI: "OPENAI_API_KEY",
            LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
        }
        env_var = key_map.get(self.provider, "")
        return os.getenv(env_var)

    def _get_client(self) -> Any:
        """Get or create async LLM client."""
        if self._client:
            return self._client

        try:
            if self.provider == LLMProvider.GROQ:
                from groq import AsyncGroq
                self._client = AsyncGroq(api_key=self._api_key)
            elif self.provider == LLMProvider.OPENAI:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=self._api_key)
            elif self.provider == LLMProvider.ANTHROPIC:
                from anthropic import AsyncAnthropic
                self._client = AsyncAnthropic(api_key=self._api_key)
        except ImportError as e:
            logger.warning(f"[LLMService] Provider SDK not installed: {e}")
            self._client = None
        except Exception as e:
            logger.error(f"[LLMService] Failed to create client: {e}")
            self._client = None

        return self._client

    def _build_messages(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Build messages array for chat completion.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt

        Returns:
            List of message dicts with role and content
        """
        messages = []

        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt,
            })

        messages.append({
            "role": "user",
            "content": prompt,
        })

        return messages

    def _build_chat_messages(
        self,
        history: List[Dict[str, str]],
        new_message: str,
        system_prompt: Optional[str] = None,
    ) -> List[Dict[str, str]]:
        """
        Build messages from conversation history.

        Args:
            history: Previous messages
            new_message: New user message
            system_prompt: Optional system prompt

        Returns:
            List of message dicts
        """
        messages = []

        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt,
            })

        # Add history
        messages.extend(history)

        # Add new message
        messages.append({
            "role": "user",
            "content": new_message,
        })

        return messages

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs,
    ) -> LLMResponse:
        """
        Generate text completion.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            **kwargs: Additional generation parameters

        Returns:
            LLMResponse with generated content
        """
        messages = self._build_messages(prompt, system_prompt)
        return await self._call_provider(messages, **kwargs)

    async def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs,
    ) -> LLMResponse:
        """
        Chat completion with message history.

        Args:
            messages: List of message dicts
            **kwargs: Additional generation parameters

        Returns:
            LLMResponse with generated content
        """
        return await self._call_provider(messages, **kwargs)

    async def _call_provider(
        self,
        messages: List[Dict[str, str]],
        **kwargs,
    ) -> LLMResponse:
        """
        Call the LLM provider.

        Args:
            messages: Chat messages
            **kwargs: Additional parameters

        Returns:
            LLMResponse
        """
        client = self._get_client()

        if not client:
            logger.warning("[LLMService] No client available")
            return LLMResponse(
                content="[LLM not configured]",
                model=self.model or "unknown",
                tokens_used=0,
                metadata={"error": "client_not_available"},
            )

        try:
            temperature = kwargs.get("temperature", self.temperature)
            max_tokens = kwargs.get("max_tokens", self.max_tokens)

            if self.provider == LLMProvider.GROQ:
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return self._parse_groq_response(response)

            elif self.provider == LLMProvider.OPENAI:
                response = await client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return self._parse_openai_response(response)

            elif self.provider == LLMProvider.ANTHROPIC:
                # Extract system prompt for Anthropic's format
                system = None
                user_messages = []
                for msg in messages:
                    if msg["role"] == "system":
                        system = msg["content"]
                    else:
                        user_messages.append(msg)

                response = await client.messages.create(
                    model=self.model,
                    system=system or "",
                    messages=user_messages,
                    max_tokens=max_tokens,
                )
                return self._parse_anthropic_response(response)

        except Exception as e:
            logger.error(f"[LLMService] API call failed ({self.provider.value}): {e}")

            # Auto-failover: try other providers
            failover_result = await self._try_failover(messages, **kwargs)
            if failover_result:
                return failover_result

            return LLMResponse(
                content="",
                model=self.model or "unknown",
                tokens_used=0,
                metadata={"error": str(e), "failover_attempted": True},
            )

        return LLMResponse(
            content="",
            model=self.model or "unknown",
            tokens_used=0,
            metadata={"error": "unknown_provider"},
        )

    async def _try_failover(
        self,
        messages: List[Dict[str, str]],
        **kwargs,
    ) -> Optional[LLMResponse]:
        """
        Try alternative providers when primary fails.

        Iterates through available providers (excluding current)
        and attempts generation with each.

        Returns:
            LLMResponse from backup provider, or None if all fail.
        """
        original_provider = self.provider
        original_model = self.model
        original_key = self._api_key
        original_client = self._client

        # Provider priority order for failover
        failover_order = [LLMProvider.OPENAI, LLMProvider.GROQ, LLMProvider.ANTHROPIC]

        for provider in failover_order:
            if provider == original_provider:
                continue

            # Check if this provider has an API key configured
            key_map = {
                LLMProvider.GROQ: "GROQ_API_KEY",
                LLMProvider.OPENAI: "OPENAI_API_KEY",
                LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
            }
            api_key = os.getenv(key_map.get(provider, ""))
            if not api_key:
                continue

            try:
                logger.info(f"[LLMService] Failover: trying {provider.value}")
                self.provider = provider
                self.model = self.DEFAULT_MODELS.get(provider)
                self._api_key = api_key
                self._client = None  # Force new client

                client = self._get_client()
                if not client:
                    continue

                temperature = kwargs.get("temperature", self.temperature)
                max_tokens = kwargs.get("max_tokens", self.max_tokens)

                if provider == LLMProvider.GROQ:
                    response = await client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    result = self._parse_groq_response(response)
                elif provider == LLMProvider.OPENAI:
                    response = await client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    result = self._parse_openai_response(response)
                elif provider == LLMProvider.ANTHROPIC:
                    system = None
                    user_messages = []
                    for msg in messages:
                        if msg["role"] == "system":
                            system = msg["content"]
                        else:
                            user_messages.append(msg)
                    response = await client.messages.create(
                        model=self.model,
                        system=system or "",
                        messages=user_messages,
                        max_tokens=max_tokens,
                    )
                    result = self._parse_anthropic_response(response)
                else:
                    continue

                result.metadata["failover_from"] = original_provider.value
                result.metadata["failover_to"] = provider.value
                logger.info(
                    f"[LLMService] Failover SUCCESS: {original_provider.value} -> {provider.value}"
                )
                return result

            except Exception as e:
                logger.warning(f"[LLMService] Failover to {provider.value} failed: {e}")
                continue

            finally:
                # Restore original provider state
                self.provider = original_provider
                self.model = original_model
                self._api_key = original_key
                self._client = original_client

        logger.error("[LLMService] All failover providers failed")
        return None

    def _parse_groq_response(self, response: Any) -> LLMResponse:
        """Parse Groq API response."""
        content = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else 0
        return LLMResponse(
            content=content or "",
            model=response.model,
            tokens_used=tokens,
            metadata={
                "finish_reason": response.choices[0].finish_reason,
                "provider": "groq",
            },
        )

    def _parse_openai_response(self, response: Any) -> LLMResponse:
        """Parse OpenAI API response."""
        content = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else 0
        return LLMResponse(
            content=content or "",
            model=response.model,
            tokens_used=tokens,
            metadata={
                "finish_reason": response.choices[0].finish_reason,
                "provider": "openai",
            },
        )

    def _parse_anthropic_response(self, response: Any) -> LLMResponse:
        """Parse Anthropic API response."""
        content = response.content[0].text if response.content else ""
        tokens = (
            response.usage.input_tokens + response.usage.output_tokens
            if response.usage
            else 0
        )
        return LLMResponse(
            content=content,
            model=response.model,
            tokens_used=tokens,
            metadata={
                "stop_reason": response.stop_reason,
                "provider": "anthropic",
            },
        )

    def get_available_models(self) -> List[str]:
        """Get list of available models for current provider."""
        return self.AVAILABLE_MODELS.get(self.provider, [])

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        return {
            "provider": self.provider.value,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "client_initialized": self._client is not None,
        }

    def switch_provider(
        self,
        provider: LLMProvider,
        model: Optional[str] = None,
    ) -> None:
        """
        Switch to a different provider.

        Args:
            provider: New provider to use
            model: Optional model name
        """
        self.provider = provider
        self.model = model or self.DEFAULT_MODELS.get(provider)
        self._client = None  # Reset client
        self._api_key = self._get_api_key_from_env()
        logger.info(
            f"[LLMService] Switched to: provider={provider.value}, "
            f"model={self.model}"
        )
