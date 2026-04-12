#!/bin/bash
# CCEE Gemma 4 26B — FULL PIPELINE (P0 + P1 = 23 systems)

# === MODEL ===
export LLM_PRIMARY_PROVIDER=openrouter
export OPENROUTER_MODEL=google/gemma-4-31b-it
export ACTIVE_MODEL=gemma-4-31b-it
export USE_TEMPLATE_SYSTEM=true

# === P0 (10 systems) ===
export USE_COMPRESSED_DOC_D=true
export ENABLE_STYLE_NORMALIZER=true
export ENABLE_FEW_SHOT=true
export ENABLE_POOL_MATCHING=true
export ENABLE_INTENT_CONFIDENCE_SCORE=true
export ENABLE_MEMORY_ENGINE=true
export ENABLE_DNA_TRIGGERS=true
export ENABLE_CONVERSATION_STATE=true
export ENABLE_LENGTH_HINTS=true
export GUARDRAILS=true

# === P1 INJECTION (8 systems) ===
export ENABLE_CONTEXT_DETECTION=true
export ENABLE_FRUSTRATION_DETECTION=true
export ENABLE_SENSITIVE_DETECTION=true
export ENABLE_RELATIONSHIP_DETECTION=true
export ENABLE_RAG=true
export ENABLE_RERANKING=false
export ENABLE_EPISODIC_MEMORY=true
export ENABLE_CITATIONS=true

# === P1 POST-PROCESSING (5 systems) ===
export ENABLE_QUESTION_REMOVAL=true
export ENABLE_OUTPUT_VALIDATION=true
export ENABLE_RESPONSE_FIXES=true
export ENABLE_MESSAGE_SPLITTING=true
export ENABLE_BLACKLIST_REPLACEMENT=true

# === CONFIRMED OFF (measured damage) ===
export ENABLE_GOLD_EXAMPLES=false
export ENABLE_RELATIONSHIP_ADAPTER=false
export ENABLE_PREFERENCE_PROFILE=false
export ENABLE_SCORE_BEFORE_SPEAK=false
export ENABLE_PPA=false
export ENABLE_ECHO=false

# === PROMPT SIZE CONTROL (S1 fix) ===
# Gemma-4-26B-A4B has a 1024-token sliding-window. Limiting RAG to 1 result
# and adding a style anchor at the end prevents Doc D from falling outside
# the attention window, recovering S1_style_fidelity lost with 23 systems.
export MAX_RAG_RESULTS=1
export ENABLE_STYLE_ANCHOR=true

# === INFRASTRUCTURE ===
export OPENROUTER_API_KEY="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"
export CCEE_NO_FALLBACK=1
export OPENROUTER_TIMEOUT=120
export CCEE_INTER_CASE_DELAY=3
export TOKENIZERS_PARALLELISM=false

echo "✓ CCEE Gemma 4 FULL PIPELINE (23 systems)"
echo "  Model: $OPENROUTER_MODEL (via OpenRouter)"
