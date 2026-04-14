#!/bin/bash
# CCEE config: Gemma 4 31B via OpenRouter
# Usage: source config/env_ccee_gemma4_31b_openrouter.sh

export LLM_PRIMARY_PROVIDER=openrouter
export DEEPINFRA_MODEL=google/gemma-4-31b-it
export OPENROUTER_MODEL=google/gemma-4-31b-it
export DEEPINFRA_INCLUDE_REASONING=false
export DEEPINFRA_NO_FALLBACK=true

echo "[ENV] Loaded: Gemma 4 31B via OpenRouter"
