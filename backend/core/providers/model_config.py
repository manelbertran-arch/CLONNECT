"""Shared model-config loader.

Loads per-model JSON configs from config/models/. Used by every provider so
that hyperparameters (temperature, max_tokens, chat template, etc.) live in
config files, not in code.

Schema spec: see docs/DECISIONS.md (2026-04-07 entry).
"""
from pathlib import Path
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_MODEL_CONFIG_DIRS = [
    _BACKEND_ROOT / "config" / "models",
]

# In-process cache (model_id -> dict). Cleared by clear_cache() in tests.
_cache: dict[str, dict] = {}


def load_model_config(model_id: str) -> dict:
    """Load model config from config/models/{model_id}.json.

    Falls back to default_config.json if the file is not found.
    Raises FileNotFoundError if neither exists.
    """
    if model_id in _cache:
        return _cache[model_id]

    for d in _MODEL_CONFIG_DIRS:
        path = d / f"{model_id}.json"
        if path.is_file():
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            _cache[model_id] = cfg
            logger.info("[ModelConfig] loaded %s from %s", model_id, path)
            return cfg

    # Fallback to default
    for d in _MODEL_CONFIG_DIRS:
        default = d / "default_config.json"
        if default.is_file():
            with open(default, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            logger.warning(
                "[ModelConfig] %s not found — using default_config.json (conservative fallback)",
                model_id,
            )
            return cfg

    raise FileNotFoundError(
        f"No model config found for '{model_id}' in {[str(d) for d in _MODEL_CONFIG_DIRS]} "
        f"and no default_config.json fallback exists"
    )


def clear_cache() -> None:
    """Clear the in-process model-config cache. Used by tests."""
    _cache.clear()


# ── Accessor helpers — every provider reads through these ──
# Defaults documented inline; the schema spec lives in docs/DECISIONS.md.

def get_provider_info(cfg: dict) -> dict:
    """Return {name, api_key_env, model_string, base_url}."""
    p = cfg.get("provider", {}) or {}
    return {
        "name": p.get("name", ""),
        "api_key_env": p.get("api_key_env", ""),
        "model_string": p.get("model_string", cfg.get("model_id", "")),
        "base_url": p.get("base_url"),
    }


def get_sampling(cfg: dict) -> dict:
    """Return sampling block with safe defaults filled in."""
    s = cfg.get("sampling", {}) or {}
    return {
        "temperature": float(s.get("temperature", 0.7)),
        "top_p": float(s.get("top_p", 1.0)),
        "top_k": int(s.get("top_k", 64)),
        "max_tokens": int(s.get("max_tokens", 200)),
        "stop_sequences": list(s.get("stop_sequences") or []),
        "frequency_penalty": float(s.get("frequency_penalty", 0.0)),
        "presence_penalty": float(s.get("presence_penalty", 0.0)),
        "seed": s.get("seed"),
    }


def get_runtime(cfg: dict) -> dict:
    """Return runtime block with safe defaults filled in."""
    r = cfg.get("runtime", {}) or {}
    return {
        "timeout_seconds": int(r.get("timeout_seconds", 15)),
        "max_retries": int(r.get("max_retries", 2)),
    }


def get_chat_template(cfg: dict) -> dict:
    ct = cfg.get("chat_template", {}) or {}
    return {
        "filter_thought_blocks": bool(ct.get("filter_thought_blocks", False)),
        "strip_thinking_artifacts": bool(ct.get("strip_thinking_artifacts", False)),
    }


def get_thinking(cfg: dict) -> dict:
    t = cfg.get("thinking", {}) or {}
    return {
        "enabled": bool(t.get("enabled", False)),
        "token": t.get("token", "<|think|>"),
        "filter_from_history": bool(t.get("filter_from_history", False)),
        "no_think_suffix": t.get("no_think_suffix", ""),
    }


def get_safety(cfg: dict) -> dict:
    """Return safety block. Defaults to BLOCK_ONLY_HIGH for all categories."""
    s = cfg.get("safety", {}) or {}
    default = "BLOCK_ONLY_HIGH"
    return {
        "harassment": s.get("harassment", default),
        "hate_speech": s.get("hate_speech", default),
        "sexually_explicit": s.get("sexually_explicit", default),
        "dangerous_content": s.get("dangerous_content", default),
    }
