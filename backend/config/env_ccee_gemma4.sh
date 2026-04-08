#!/usr/bin/env bash
# =============================================================================
# CCEE Evaluation — Gemma 4 — Solo sistemas P0
# =============================================================================
# Uso:  source config/env_ccee_gemma4.sh
# Luego: python3 tests/run_ccee_gemma4.py
#
# Sistemas P0 ENCENDIDOS:
#   1. Doc D comprimido    (compressed_doc_d.py)   — USE_COMPRESSED_DOC_D + USE_TEMPLATE_SYSTEM
#   2. Style Normalizer    (style_normalizer.py)   — ENABLE_STYLE_NORMALIZER
#   3. Pool Matcher        (detection.py)           — ENABLE_POOL_MATCHING
#   4. Few-Shot            (context.py)             — ENABLE_FEW_SHOT
#   5. Creator Style Loader (creator_style_loader)  — USE_COMPRESSED_DOC_D (mismo flag que #1)
#   6. Intent Service      (intent_service.py)      — SIN FLAG (siempre activo)
#
# Sistemas NO-P0 APAGADOS: ver sección "SISTEMAS NO-P0" más abajo
# =============================================================================

# ---------------------------------------------------------------------------
# MODELO — Google AI Studio (Gemma 4)
# ---------------------------------------------------------------------------
export LLM_PRIMARY_PROVIDER="google_ai_studio"
export GOOGLE_AI_STUDIO_MODEL="gemma-4-26b-a4b-it"
export GOOGLE_AI_STUDIO_MODEL_ID="gemma4_26b_a4b"
export ACTIVE_MODEL="gemma-4-26b-a4b-it"           # Selects gemma4_26b template in compressed_doc_d.py
# export GOOGLE_API_KEY="your_google_api_key"  # ← SET THIS MANUALLY o usa .env local

# Para Gemma 4 31B: cambia las tres líneas anteriores a:
#   export GOOGLE_AI_STUDIO_MODEL="gemma-4-31b-it"
#   export GOOGLE_AI_STUDIO_MODEL_ID="gemma4_31b"
#   export ACTIVE_MODEL="gemma-4-31b-it"

# ---------------------------------------------------------------------------
# P0 SISTEMA 1 — Doc D comprimido + Template System
# Fuente: services/creator_style_loader.py:28, core/dm/compressed_doc_d.py:360
# ---------------------------------------------------------------------------
export USE_COMPRESSED_DOC_D=true
export USE_TEMPLATE_SYSTEM=true

# ---------------------------------------------------------------------------
# P0 SISTEMA 2 — Style Normalizer
# Fuente: core/dm/style_normalizer.py:29
# ---------------------------------------------------------------------------
export ENABLE_STYLE_NORMALIZER=true

# ---------------------------------------------------------------------------
# P0 SISTEMA 3 — Pool Matcher
# Fuente: core/feature_flags.py:36 → ENABLE_POOL_MATCHING
# ---------------------------------------------------------------------------
export ENABLE_POOL_MATCHING=true

# ---------------------------------------------------------------------------
# P0 SISTEMA 4 — Few-Shot
# Fuente: core/dm/phases/context.py:33 → ENABLE_FEW_SHOT
# ---------------------------------------------------------------------------
export ENABLE_FEW_SHOT=true

# ---------------------------------------------------------------------------
# P0 SISTEMA 5 — Creator Style Loader
# Fuente: services/creator_style_loader.py — SIN FLAG propio
# Activado por: USE_COMPRESSED_DOC_D=true
# ---------------------------------------------------------------------------
# (no flag needed — always active; USE_COMPRESSED_DOC_D routes to compressed path)

# ---------------------------------------------------------------------------
# P0 SISTEMA 6 — Intent Service
# Fuente: services/intent_service.py — SIN FLAG
# Integración P0 audit: core/dm/phases/context.py:37
# ---------------------------------------------------------------------------
export ENABLE_INTENT_CONFIDENCE_SCORE=true

# ---------------------------------------------------------------------------
# MONITOREO P0
# Fuente: core/dm/phases/generation.py:118
# ---------------------------------------------------------------------------
export ENABLE_COMPLETENESS_MONITORING=true

# ---------------------------------------------------------------------------
# INFRAESTRUCTURA MÍNIMA (no desactivable — pipeline no funciona sin esto)
# ---------------------------------------------------------------------------
export ENABLE_SENSITIVE_DETECTION=true          # core/feature_flags.py:29 — gate crítico
export ENABLE_MEDIA_PLACEHOLDER_DETECTION=true  # core/feature_flags.py:35 — gate crítico
export ENABLE_GUARDRAILS=true                   # core/feature_flags.py:33 — postprocessing
export ENABLE_OUTPUT_VALIDATION=true            # core/feature_flags.py:34 — postprocessing
export ENABLE_RESPONSE_FIXES=true               # core/feature_flags.py:41 — dedup/format fixes
export ENABLE_CONVERSATION_MEMORY=true          # core/feature_flags.py:32 — historial DB básico

# ---------------------------------------------------------------------------
# SISTEMAS NO-P0: APAGADOS
# (ordenados por fuente — central registry primero, inline flags después)
# ---------------------------------------------------------------------------

# -- Central registry (core/feature_flags.py) --
export ENABLE_FRUSTRATION_DETECTION=false       # line 30 — señal emocional
export ENABLE_CONTEXT_DETECTION=false           # line 31 — context signals
export ENABLE_PROMPT_INJECTION_DETECTION=false  # line 37 — solo observabilidad
export ENABLE_CLONE_SCORE=false                 # line 38 — scoring
export ENABLE_MEMORY_ENGINE=false               # line 39 — advanced memory
export ENABLE_COMMITMENT_TRACKING=false         # line 40 — commitment DB
export ENABLE_QUESTION_CONTEXT=false            # line 42 — pregunta anterior
export ENABLE_QUERY_EXPANSION=false             # line 43 — expande RAG queries
export ENABLE_REFLEXION=false                   # line 44 — self-correction loop
export ENABLE_LEAD_CATEGORIZER=false            # line 45 — categorización lead (interfería −0.30)
export ENABLE_CONVERSATION_STATE=false          # line 46 — state machine
export ENABLE_FACT_TRACKING=false               # line 47 — fact extraction
export ENABLE_ADVANCED_PROMPTS=false            # line 48 — variantes avanzadas
export ENABLE_DNA_TRIGGERS=false                # line 49 — DNA update triggers
export ENABLE_DNA_AUTO_CREATE=false             # line 50 — DNA auto-creation
export ENABLE_RELATIONSHIP_DETECTION=false      # line 51 — family/friend/follower
export ENABLE_CITATIONS=false                   # line 52 — citas RAG
export ENABLE_MESSAGE_SPLITTING=false           # line 53 — split mensajes largos
export ENABLE_QUESTION_REMOVAL=false            # line 54 — elimina preguntas extra
export ENABLE_VOCABULARY_EXTRACTION=false       # line 55 — vocab extraction
export ENABLE_SELF_CONSISTENCY=false            # line 58 — self-consistency
export ENABLE_FINETUNED_MODEL=false             # line 59 — fine-tuned model
export ENABLE_EMAIL_CAPTURE=false               # line 60 — email capture
export ENABLE_BEST_OF_N=false                   # line 61 — best-of-N generation
export ENABLE_GOLD_EXAMPLES=false               # line 62 — gold examples (generation.py)
export ENABLE_PREFERENCE_PROFILE=false          # line 63 — preference profile
export ENABLE_SCORE_BEFORE_SPEAK=false          # line 64 — score antes de enviar
export ENABLE_PPA=false                         # line 65 — probabilistic preference
export ENABLE_RERANKING=false                   # line 68 — RAG cross-encoder reranking
export ENABLE_BM25_HYBRID=false                 # line 69 — RAG BM25 hybrid
export ENABLE_INTELLIGENCE=false                # line 72 — intelligence engine
export ENABLE_STYLE_ANALYZER=false              # line 73 — style analyzer background
export ENABLE_CONFIDENCE_SCORER=false           # line 76 — unaudited
export ENABLE_BLACKLIST_REPLACEMENT=false       # line 77 — unaudited
export ENABLE_NURTURING=false                   # line 78 — nurturing sequences
export ENABLE_UNIFIED_PROFILE=false             # line 79 — unaudited
export ENABLE_IDENTITY_RESOLVER=false           # line 80 — unaudited

# -- Inline flags (core/dm/phases/context.py) --
export ENABLE_RAG=false                         # context.py:25 — RAG retrieval
export ENABLE_HIERARCHICAL_MEMORY=false         # context.py:31 — hierarchical memory
export ENABLE_EPISODIC_MEMORY=false             # context.py:32 — episodic memory
export ENABLE_LENGTH_HINTS=false                # context.py:34 — length hints
export ENABLE_QUESTION_HINTS=false              # context.py:35 — question hints
export ENABLE_DNA_AUTO_ANALYZE=false            # context.py:36 — DNA auto-analyze

# -- Inline flags (services/) --
export ENABLE_MEMORY_DECAY=false                # services/memory_engine.py:37
export ENABLE_AUDIO_INTELLIGENCE=false          # services/audio_intelligence.py:26
export ENABLE_PERSONA_COMPILER=false            # services/persona_compiler.py:33

# ---------------------------------------------------------------------------
# VERIFICACIÓN
# ---------------------------------------------------------------------------
echo "✓ CCEE Gemma 4 P0-only env configurado"
echo "  Modelo:   ${GOOGLE_AI_STUDIO_MODEL} via google_ai_studio"
echo "  Template: ACTIVE_MODEL=${ACTIVE_MODEL}"
echo "  GOOGLE_API_KEY: $([ -n "${GOOGLE_API_KEY}" ] && echo 'SET' || echo '⚠ NO SET — export GOOGLE_API_KEY=...')"
echo ""
echo "  P0 ON:  USE_COMPRESSED_DOC_D=true  USE_TEMPLATE_SYSTEM=true"
echo "          ENABLE_STYLE_NORMALIZER=${ENABLE_STYLE_NORMALIZER}  ENABLE_POOL_MATCHING=${ENABLE_POOL_MATCHING}"
echo "          ENABLE_FEW_SHOT=${ENABLE_FEW_SHOT}  ENABLE_INTENT_CONFIDENCE_SCORE=${ENABLE_INTENT_CONFIDENCE_SCORE}"
echo ""
echo "  Infraestructura: GUARDRAILS=${ENABLE_GUARDRAILS}  OUTPUT_VALIDATION=${ENABLE_OUTPUT_VALIDATION}"
