"""Shared DeepInfra client factory for all scripts."""
import os
from openai import OpenAI, AsyncOpenAI


def get_deepinfra_client() -> OpenAI:
    api_key = os.environ.get("DEEPINFRA_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPINFRA_API_KEY not set")
    return OpenAI(
        api_key=api_key,
        base_url="https://api.deepinfra.com/v1/openai",
    )


def get_deepinfra_async_client() -> AsyncOpenAI:
    api_key = os.environ.get("DEEPINFRA_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPINFRA_API_KEY not set")
    return AsyncOpenAI(
        api_key=api_key,
        base_url="https://api.deepinfra.com/v1/openai",
    )


JUDGE_MODEL = "Qwen/Qwen3-30B-A3B"
GEN_MODEL = "Qwen/Qwen3-32B"
