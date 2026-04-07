"""
SINGLE SOURCE OF TRUTH for all LLM model names and provider routing.

All code paths MUST import from here. Never hardcode model strings.

COST REFERENCE (as of 2026-03):
  gemini-2.5-flash-lite: $0.075/1M input, $0.30/1M output  ← USE THIS
  gemini-2.0-flash-lite: $0.075/1M input, $0.30/1M output  ← also safe
  gemini-2.5-flash:      $0.30/1M input,  $2.50/1M output  ← 6-8x expensive, BLOCKED
  gemini-2.5-pro:        $1.25/1M input, $10.00/1M output  ← 80x expensive, BLOCKED
  Qwen/Qwen3-32B (DeepInfra): ~$0.20/1M input, $0.20/1M output
  Qwen/Qwen3-32B (Together):  ~$0.30/1M input, $0.50/1M output
  Qwen/Qwen3-8B  (Together):  ~$0.10/1M input, $0.10/1M output
  Qwen/Qwen3-8B  (Fireworks): ~$0.10/1M input, $0.10/1M output (LoRA serverless at base price)
"""
import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PROVIDER ROUTING — which LLM provider to try first
# Options: "gemini" (default), "together", "deepinfra", "fireworks", "openai"
# The cascade is always: PRIMARY → Gemini (if not primary) → GPT-4o-mini → None
# ---------------------------------------------------------------------------
LLM_PRIMARY_PROVIDER: str = os.getenv("LLM_PRIMARY_PROVIDER", "gemini")

# ---------------------------------------------------------------------------
# PRIMARY MODEL — override via GEMINI_MODEL env var in Railway
# ---------------------------------------------------------------------------
GEMINI_PRIMARY_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

# ---------------------------------------------------------------------------
# DEEPINFRA MODEL — override via DEEPINFRA_MODEL env var
# ---------------------------------------------------------------------------
DEEPINFRA_MODEL: str = os.getenv("DEEPINFRA_MODEL", "Qwen/Qwen3-32B")

# ---------------------------------------------------------------------------
# TOGETHER MODEL — override via TOGETHER_MODEL env var
# ---------------------------------------------------------------------------
TOGETHER_MODEL: str = os.getenv("TOGETHER_MODEL", "Qwen/Qwen3-32B")

# ---------------------------------------------------------------------------
# FIREWORKS MODEL — override via FIREWORKS_MODEL env var
# Supports LoRA serverless: fine-tuned adapters at base model price
# ---------------------------------------------------------------------------
FIREWORKS_MODEL: str = os.getenv("FIREWORKS_MODEL", "accounts/fireworks/models/qwen3-8b")

# ---------------------------------------------------------------------------
# GOOGLE AI STUDIO MODEL — override via GOOGLE_AI_STUDIO_MODEL env var
# Used when LLM_PRIMARY_PROVIDER=google_ai_studio (Gemma 4 and similar)
# GOOGLE_AI_STUDIO_MODEL_ID is the config file ID (e.g. "gemma4_26b_a4b")
# ---------------------------------------------------------------------------
GOOGLE_AI_STUDIO_MODEL: str = os.getenv("GOOGLE_AI_STUDIO_MODEL", "gemma-4-26b-a4b-it")
GOOGLE_AI_STUDIO_MODEL_ID: str = os.getenv("GOOGLE_AI_STUDIO_MODEL_ID", "gemma4_26b_a4b")

# ---------------------------------------------------------------------------
# ACTIVE MODEL SELECTION (preferred over LLM_PRIMARY_PROVIDER cascade)
# When set, LLM_MODEL_NAME selects a config from config/models/{name}.json
# and dispatches to the matching provider via generate_dm_response().
# When unset, the legacy LLM_PRIMARY_PROVIDER + per-provider env var path
# is used (current Railway behavior).
# Available configs: qwen3_14b, gemini_flash_lite, gemma4_26b_a4b, gemma4_31b,
#                    openrouter_default, fireworks_default, together_default, default
# ---------------------------------------------------------------------------
LLM_MODEL_NAME: Optional[str] = os.getenv("LLM_MODEL_NAME")


def get_active_model_config() -> Optional[dict]:
    """Return the active model config dict if LLM_MODEL_NAME is set, else None.

    Reads LLM_MODEL_NAME live from os.environ so tests can monkeypatch the
    env var without re-importing this module.
    """
    name = os.getenv("LLM_MODEL_NAME") or LLM_MODEL_NAME
    if not name:
        return None
    try:
        from core.providers.model_config import load_model_config
        return load_model_config(name)
    except FileNotFoundError as e:
        logger.error("[LLM CONFIG] LLM_MODEL_NAME=%s but config not found: %s", name, e)
        return None

# ---------------------------------------------------------------------------
# BLOCKED MODELS — too expensive for production DM inference
# Any code path that tries to use these is redirected to GEMINI_PRIMARY_MODEL
# ---------------------------------------------------------------------------
BLOCKED_MODELS: list[str] = [
    "gemini-2.5-flash",    # $0.30/1M input — 4x more expensive than flash-lite
    "gemini-2.5-pro",      # $1.25/1M input — 16x more expensive
    "gemini-3-flash",      # future model — block until cost confirmed safe
    "gemini-3-pro",        # future model — block until cost confirmed safe
    "gemini-2.0-flash",    # non-lite variant — block to force flash-lite
]


def safe_model(requested: str) -> str:
    """Return the requested model, or GEMINI_PRIMARY_MODEL if it's blocked.

    Call this before every Gemini API call:
        model = safe_model(requested_model)
    """
    if requested in BLOCKED_MODELS:
        logger.error(
            "[LLM CONFIG] BLOCKED expensive model '%s' — forcing '%s'. "
            "Update calling code to use GEMINI_PRIMARY_MODEL.",
            requested, GEMINI_PRIMARY_MODEL,
        )
        return GEMINI_PRIMARY_MODEL
    return requested


def log_model_config() -> None:
    """Log current model config at startup. Call once from api/main.py."""
    if LLM_MODEL_NAME:
        active_cfg = get_active_model_config()
        if active_cfg:
            prov = active_cfg.get("provider", {}) or {}
            logger.warning(
                "[LLM CONFIG] Active model: %s (provider=%s, model_string=%s)",
                LLM_MODEL_NAME,
                prov.get("name"),
                prov.get("model_string"),
            )
    logger.warning("[LLM CONFIG] Primary provider: %s", LLM_PRIMARY_PROVIDER)
    logger.warning("[LLM CONFIG] Gemini model: %s", GEMINI_PRIMARY_MODEL)
    if LLM_PRIMARY_PROVIDER == "together":
        logger.warning("[LLM CONFIG] Together model: %s", TOGETHER_MODEL)
        has_key = bool(os.getenv("TOGETHER_API_KEY"))
        logger.warning("[LLM CONFIG] TOGETHER_API_KEY: %s", "set" if has_key else "NOT SET")
    elif LLM_PRIMARY_PROVIDER == "deepinfra":
        logger.warning("[LLM CONFIG] DeepInfra model: %s", DEEPINFRA_MODEL)
        has_key = bool(os.getenv("DEEPINFRA_API_KEY"))
        logger.warning("[LLM CONFIG] DEEPINFRA_API_KEY: %s", "set" if has_key else "NOT SET")
    elif LLM_PRIMARY_PROVIDER == "fireworks":
        logger.warning("[LLM CONFIG] Fireworks model: %s", FIREWORKS_MODEL)
        has_key = bool(os.getenv("FIREWORKS_API_KEY"))
        logger.warning("[LLM CONFIG] FIREWORKS_API_KEY: %s", "set" if has_key else "NOT SET")
    elif LLM_PRIMARY_PROVIDER == "google_ai_studio":
        logger.warning("[LLM CONFIG] Google AI Studio model: %s", GOOGLE_AI_STUDIO_MODEL)
        logger.warning("[LLM CONFIG] Google AI Studio model ID: %s", GOOGLE_AI_STUDIO_MODEL_ID)
        has_key = bool(os.getenv("GOOGLE_API_KEY"))
        logger.warning("[LLM CONFIG] GOOGLE_API_KEY: %s", "set" if has_key else "NOT SET")
    env_val = os.getenv("GEMINI_MODEL", "(not set — using default)")
    logger.warning("[LLM CONFIG] GEMINI_MODEL env var: %s", env_val)
    _model_key_hints = {"MODEL", "LLM", "GEMINI", "GPT", "OPENAI", "PROVIDER", "DEEPINFRA", "TOGETHER", "FIREWORKS"}
    for key, val in os.environ.items():
        key_upper = key.upper()
        if not any(h in key_upper for h in _model_key_hints):
            continue
        if len(val) > 200:  # skip long values like commit messages
            continue
        for blocked in BLOCKED_MODELS:
            # Use word-boundary match: blocked must not be followed by more model chars
            # e.g. "gemini-2.5-flash" must NOT match inside "gemini-2.5-flash-lite"
            if re.search(r'(?<![a-zA-Z0-9-])' + re.escape(blocked) + r'(?![a-zA-Z0-9-])', val):
                logger.error(
                    "[LLM CONFIG] ALERT: blocked model '%s' found in env var %s=%s",
                    blocked, key, val,
                )
