"""
SINGLE SOURCE OF TRUTH for all LLM model names and provider routing.

All code paths MUST import from here. Never hardcode model strings.

COST REFERENCE (as of 2026-03):
  gemini-2.5-flash-lite: $0.075/1M input, $0.30/1M output  ← USE THIS
  gemini-2.0-flash-lite: $0.075/1M input, $0.30/1M output  ← also safe
  gemini-2.5-flash:      $0.30/1M input,  $2.50/1M output  ← 6-8x expensive, BLOCKED
  gemini-2.5-pro:        $1.25/1M input, $10.00/1M output  ← 80x expensive, BLOCKED
  Qwen/Qwen3-32B (DeepInfra): ~$0.20/1M input, $0.20/1M output
"""
import logging
import os
import re

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PROVIDER ROUTING — which LLM provider to try first
# Options: "gemini" (default), "deepinfra", "openai"
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
    logger.warning("[LLM CONFIG] Primary provider: %s", LLM_PRIMARY_PROVIDER)
    logger.warning("[LLM CONFIG] Gemini model: %s", GEMINI_PRIMARY_MODEL)
    if LLM_PRIMARY_PROVIDER == "deepinfra":
        logger.warning("[LLM CONFIG] DeepInfra model: %s", DEEPINFRA_MODEL)
        has_key = bool(os.getenv("DEEPINFRA_API_KEY"))
        logger.warning("[LLM CONFIG] DEEPINFRA_API_KEY: %s", "set" if has_key else "NOT SET")
    env_val = os.getenv("GEMINI_MODEL", "(not set — using default)")
    logger.warning("[LLM CONFIG] GEMINI_MODEL env var: %s", env_val)
    _model_key_hints = {"MODEL", "LLM", "GEMINI", "GPT", "OPENAI", "PROVIDER", "DEEPINFRA"}
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
