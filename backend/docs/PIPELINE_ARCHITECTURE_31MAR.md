# Pipeline Architecture — Clonnect DM Agent
**Fecha**: 2026-03-31 | **Branch**: main | **Estado**: post-sesiones 21-31 marzo

---

## Pipeline en una línea

```
Instagram/WhatsApp Webhook
    → Phase 0: Pre-processing (audio, media, early save)
    → Phase 1: Detection (sensitive, frustration, pool)
    → Phase 2-3: Memory & Context (intent, RAG, memory, prompt)
    → Phase 4: LLM Generation (strategy, few-shot, Gemini call)
    → Phase 5: Post-processing (fixes, SBS/PPA, normalizer, format)
    → Phase 6: Background (lead score, memory write, commitment, escalation)
    → DMResponse → Copilot pending_approval → Creator approval → Send
```

---

## ASCII Diagram — Cadena completa

```
┌─────────────────────────────────────────────────────────────┐
│  INSTAGRAM / WHATSAPP WEBHOOK                               │
│  evolution_webhook.py / dispatch.py                         │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│  PHASE 0: PRE-PROCESSING                                    │
│  ┌─ [#1] Audio Transcription    (Groq→Gemini→OpenAI)  ON   │
│  ├─ [#2] Audio Intelligence     (4-layer pipeline)     ON   │
│  ├─ [#3] Media Type Detector    (photo/video/reel)     ON   │
│  ├─ [#4] Early Save             (DB + SSE notify)      ON   │
│  └─ [#5] Creator Auto-Provisioner (ensure_profiles)   ON   │
└───────────────────────┬─────────────────────────────────────┘
                        │ (text content ready)
┌───────────────────────▼─────────────────────────────────────┐
│  PHASE 1: DETECTION  [detection.py]                         │
│  ┌─ [#6]  Media Placeholder Detector                   ON   │
│  ├─ [#7]  Sensitive Content Detector       ENV FLAG    ON   │
│  ├─ [#8]  Crisis Response Generator        (early ret) ON   │
│  ├─ [#9]  Frustration Detector            ENV FLAG    ON   │
│  ├─ [#10] Context Detector (sarcasm/B2B)  ENV FLAG    ON   │
│  ├─ [#11] Pool Response System            (short ≤80c) ON   │
│  └─ [#12] Multi-Bubble Response           (30% prob)   ON   │
│                                                             │
│  ↳ Pool match → EARLY RETURN (bypasses LLM)                 │
└───────────────────────┬─────────────────────────────────────┘
                        │ (no early return)
┌───────────────────────▼─────────────────────────────────────┐
│  PHASE 2-3: MEMORY & CONTEXT  [context.py]                  │
│                                                             │
│  ── INTENT ──────────────────────────────────────────────   │
│  [#13] Intent Classifier         (GPT-4o-mini, ~40% bypass) │
│                                                             │
│  ── PARALLEL IO (asyncio.gather) ───────────────────────    │
│  [#14] Memory Store              (follower JSON files)  ON  │
│  [#15] DNA Context Builder       (_build_ctx)           ON  │
│  [#16] Conversation State Machine (read+write)          ON  │
│                                                             │
│  ── MEMORY SYSTEMS ─────────────────────────────────────    │
│  [#17] Memory Engine Recall      ENV FLAG  ENABLE_MEMORY_ENGINE ON │
│  [#18] Episodic/Semantic Memory  ENV FLAG  ENABLE_EPISODIC_MEMORY OFF │
│  [#19] Hierarchical Memory       ENV FLAG  ENABLE_HIERARCHICAL_MEMORY OFF │
│  [#20] COMEDY Compressive Memory (leads >50 msgs)       ON  │
│                                                             │
│  ── RAG ────────────────────────────────────────────────    │
│  [#21] Query Expander            ENABLE_QUERY_EXPANSION ON  │
│  [#22] RAG Semantic Search       ENABLE_RAG            ON   │
│  [#23] BM25 Hybrid + Reranker    ENABLE_BM25_HYBRID    ON   │
│                                                             │
│  ── RELATIONSHIP & STYLE ───────────────────────────────    │
│  [#24] Relationship Detector     ENABLE_RELATIONSHIP_DETECTION ON │
│  [#25] ECHO RelationshipAdapter  (relational_block)     ON  │
│  [#26] ECHO StyleProfile Inject  ENABLE_STYLE_ANALYZER  ON  │
│                                                             │
│  ── EXTRA CONTEXT ──────────────────────────────────────    │
│  [#27] Bot Question Analyzer     ENABLE_QUESTION_CONTEXT ON │
│  [#28] Citation Service          ENABLE_CITATIONS       ON  │
│  [#29] Audio Context Extractor   (from msg_metadata)    ON  │
│  [#30] Calibration Few-Shot      (calibrations/*.json)  ON  │
│  [#31] KB Context Loader         (knowledge_base table) ON  │
│  [#32] Advanced Prompts Section  ENABLE_ADVANCED_PROMPTS ON │
│                                                             │
│  ↳ OUTPUT: ContextBundle + system_prompt assembled          │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│  PHASE 4: LLM GENERATION  [generation.py]                   │
│                                                             │
│  ── PROMPT ENRICHMENT ──────────────────────────────────    │
│  [#33] Response Strategy Determiner  (strategy.py)      ON  │
│  [#34] Learning Rules Injector  ENABLE_LEARNING_RULES   OFF │
│  [#35] Preference Profile       ENABLE_PREFERENCE_PROFILE OFF │
│  [#36] Gold Examples Injector   ENABLE_GOLD_EXAMPLES    OFF │
│  [#37] Q-Suppression Hint       (_maybe_question_hint)  ON  │
│  [#38] Context Truncator        (>12K chars → smart trunc) ON │
│                                                             │
│  ── GENERATION ─────────────────────────────────────────    │
│  [#39] Chain of Thought         ENABLE_CHAIN_OF_THOUGHT OFF │
│  [#40] Best-of-N (3 candidates) ENABLE_BEST_OF_N       OFF  │
│  [#41] Gemini Flash-Lite        PRIMARY — always         ON  │
│  [#42] GPT-4o-mini Fallback     (on Gemini failure)     ON  │
│  [#43] Self-Consistency         ENABLE_SELF_CONSISTENCY OFF  │
│  [#44] Loop Truncator           (mid-gen loop detect)  OFF  │
│         (DISABLED: MIN_SUB=10 too aggressive)               │
└───────────────────────┬─────────────────────────────────────┘
                        │ raw LLM response
┌───────────────────────▼─────────────────────────────────────┐
│  PHASE 5: POST-PROCESSING  [postprocessing.py]              │
│                                                             │
│  ── LOOP / REPETITION GUARDS ───────────────────────────    │
│  [#45] A2  Exact Duplicate Detector    (LOG ONLY)       ON  │
│  [#46] A2b Intra-Response Repetition   (regex, >50c)    ON  │
│  [#47] A2c Sentence Deduplication      (3+ repeats)     ON  │
│                                                             │
│  ── CONTENT FIXES ──────────────────────────────────────    │
│  [#48] Output Validator (link check)  ENABLE_OUTPUT_VALIDATION ON │
│  [#49] Response Fixes (typos/format)  ENABLE_RESPONSE_FIXES   ON │
│  [#50] Blacklist Replacement          (from calibration)  ON │
│  [#51] Question Remover               ENABLE_QUESTION_REMOVAL ON │
│  [#52] Reflexion Engine               ENABLE_REFLEXION     OFF │
│                                                             │
│  ── QUALITY GATE (SBS / PPA) ───────────────────────────    │
│  [#53] Score Before You Speak (SBS)   ENABLE_SCORE_BEFORE_SPEAK OFF │
│         (when ON: replaces PPA; retry at temp=0.5 if <0.7)  │
│  [#54] Post Persona Alignment (PPA)   ENABLE_PPA           OFF │
│         (fallback when SBS OFF; LLM re-alignment call)      │
│                                                             │
│  ── FORMATTING & OUTPUT ────────────────────────────────    │
│  [#55] Guardrails (hallucination/URL) ENABLE_GUARDRAILS     ON │
│  [#56] Length Controller              (enforce_length)      ON │
│  [#57] Style Normalizer  ★NEW★        ENABLE_STYLE_NORMALIZER ON │
│         (emoji_rate + excl_rate matching from baseline)     │
│  [#58] Instagram Formatter            (format_message)      ON │
│  [#59] Payment Link Injector          (purchase_intent)     ON │
│                                                             │
│  ── REAL-TIME SCORING ──────────────────────────────────    │
│  [#60] Clone Score Engine  ENABLE_CLONE_SCORE              OFF │
│  [#61] Confidence Scorer   (calculate_confidence)           ON │
└───────────────────────┬─────────────────────────────────────┘
                        │ formatted DMResponse
┌───────────────────────▼─────────────────────────────────────┐
│  PHASE 6: BACKGROUND TASKS (asyncio.create_task)           │
│                                                             │
│  [#62] Lead Score Update        (sync, blocking)        ON  │
│  [#63] Conversation State Update (fire-and-forget)      ON  │
│  [#64] Email Capture            ENABLE_EMAIL_CAPTURE    OFF │
│  [#65] Memory Engine Writer     ENABLE_MEMORY_ENGINE    ON  │
│  [#66] Commitment Tracker       ENABLE_COMMITMENT_TRACKING ON │
│  [#67] Escalation Notifier      (async, lightweight)    ON  │
│  [#68] Message Splitter         ENABLE_MESSAGE_SPLITTING ON  │
│  [#69] Follower Memory Update   (JSON file, last 20)    ON  │
│  [#70] Gold Example Writer      ENABLE_AUTOLEARNING     OFF │
│  [#71] Identity Resolution Trigger (async)              ON  │
└─────────────────────────────────────────────────────────────┘
```

---

## Inventario de los 59 sistemas del pipeline DM

> Nota: el audit de 31-mar identificó ~59 componentes en el núcleo del pipeline (Phases 1-6).
> Phase 0 (webhook) y los background tasks de Phase 6 son infraestructura periférica.

### Leyenda de estado
- `ON` — activo en producción
- `OFF` — código presente, flag desactivado
- `DEAD` — referenciado en documentos pero no encontrado en código
- `★NEW★` — añadido después del 21-mar-2026

| # | Sistema | Archivo | ENV Flag (default) | Estado |
|---|---------|---------|-------------------|--------|
| 1 | Sensitive Content Detector | `core/sensitive_detector.py` | `ENABLE_SENSITIVE_DETECTION=true` | ON |
| 2 | Frustration Detector | `core/frustration_detector.py` | `ENABLE_FRUSTRATION_DETECTION=true` | ON |
| 3 | Context Detector (sarcasm/B2B) | `core/context_detector.py` | `ENABLE_CONTEXT_DETECTION=true` | ON |
| 4 | Pool Response System | `services/response_variator_v2.py` | conf threshold (0.85) | ON |
| 5 | Media Placeholder Detector | `core/dm/phases/detection.py` | hardcoded set | ON |
| 6 | Intent Classifier | `services/intent_service.py` | always | ON |
| 7 | Memory Store (JSON files) | `services/memory_store.py` | always | ON |
| 8 | DNA Context Builder | `core/dm/phases/context.py` | always | ON |
| 9 | Conversation State Machine | `core/conversation_state.py` | `ENABLE_CONVERSATION_STATE=true` | ON |
| 10 | Memory Engine Recall | `services/memory_engine.py` | `ENABLE_MEMORY_ENGINE=false` | ON (prod=true) |
| 11 | Query Expander | `core/query_expansion.py` | `ENABLE_QUERY_EXPANSION=true` | ON |
| 12 | RAG Semantic Search (pgvector) | `core/rag/semantic.py` | `ENABLE_RAG=true` | ON |
| 13 | BM25 Hybrid Reranker | `core/rag/reranker.py` | `ENABLE_BM25_HYBRID` / `ENABLE_RERANKING` | ON |
| 14 | Relationship Detector | `core/dm/phases/context.py` | `ENABLE_RELATIONSHIP_DETECTION=true` | ON |
| 15 | ECHO RelationshipAdapter | `core/style_analyzer.py` | `ENABLE_STYLE_ANALYZER=true` | ON |
| 16 | ECHO StyleProfile Injector | `core/dm/agent.py:_enrich_style_with_profile` | `ENABLE_STYLE_ANALYZER=true` | ON ★NEW★ |
| 17 | Bot Question Analyzer | `core/bot_question_analyzer.py` | `ENABLE_QUESTION_CONTEXT=true` | ON |
| 18 | Citation Service | `core/citation_service.py` | `ENABLE_CITATIONS=true` | ON |
| 19 | Audio Context Extractor | `core/dm/phases/context.py` | from `msg_metadata.audio_intel` | ON |
| 20 | Calibration Few-Shot Loader | `services/calibration_loader.py` | always (per-creator file) | ON |
| 21 | KB Context Loader | `core/dm/phases/context.py` | always | ON |
| 22 | Advanced Prompts Section | `core/dm/phases/context.py` | `ENABLE_ADVANCED_PROMPTS=false` | ON (prod=true) |
| 23 | COMEDY Compressive Memory | `core/dm/helpers.py` | always for >50 msgs | ON |
| 24 | Episodic/Semantic PgVector | `core/semantic_memory_pgvector.py` | `ENABLE_EPISODIC_MEMORY=false` | ON (prod=true) |
| 25 | Hierarchical Memory | (in context.py) | `ENABLE_HIERARCHICAL_MEMORY=false` | OFF |
| 26 | Response Strategy Determiner | `core/dm/strategy.py` | always | ON |
| 27 | Learning Rules Injector | `services/learning_rules_service.py` | `ENABLE_LEARNING_RULES=false` | OFF |
| 28 | Preference Profile Injector | `services/preference_profile_service.py` | `ENABLE_PREFERENCE_PROFILE=false` | OFF |
| 29 | Gold Examples Injector | `services/gold_examples_service.py` | `ENABLE_GOLD_EXAMPLES=false` | OFF |
| 30 | Q-Suppression Hint | `core/dm/phases/generation.py:_maybe_question_hint` | always (data-driven) | ON ★NEW★ |
| 31 | Chain of Thought | `core/reasoning/chain_of_thought.py` | `ENABLE_CHAIN_OF_THOUGHT=false` | OFF |
| 32 | Best-of-N (3 candidates) | `core/best_of_n.py` | `ENABLE_BEST_OF_N=false` | OFF |
| 33 | Gemini 2.5 Flash-Lite | `core/providers/gemini_provider.py` | primary | ON |
| 34 | GPT-4o-mini Fallback | `services/llm_service.py` | on Gemini failure | ON |
| 35 | Self-Consistency Validator | `core/reasoning/self_consistency.py` | `ENABLE_SELF_CONSISTENCY=false` | OFF |
| 36 | Loop Truncator (mid-gen) | `generation.py:_truncate_if_looping` | DISABLED in code | DEAD |
| 37 | A2 Exact Duplicate Guard | `postprocessing.py` | always (LOG ONLY) | ON |
| 38 | A2b Intra-Response Repetition | `postprocessing.py` | always (>50 chars) | ON |
| 39 | A2c Sentence Deduplication | `postprocessing.py` | always (3+ reps) | ON |
| 40 | Output Validator (links) | `core/output_validator.py` | `ENABLE_OUTPUT_VALIDATION=true` | ON |
| 41 | Response Fixes | `core/response_fixes.py` | `ENABLE_RESPONSE_FIXES=true` | ON |
| 42 | Blacklist Replacement | `services/calibration_loader.py` | always (per-creator) | ON |
| 43 | Question Remover | `services/question_remover.py` | `ENABLE_QUESTION_REMOVAL=true` | ON |
| 44 | Reflexion Engine | `core/reflexion_engine.py` | `ENABLE_REFLEXION=false` | OFF |
| 45 | Score Before You Speak (SBS) | `core/reasoning/ppa.py:score_before_speak` | `ENABLE_SCORE_BEFORE_SPEAK=false` | OFF |
| 46 | Post Persona Alignment (PPA) | `core/reasoning/ppa.py:apply_ppa` | `ENABLE_PPA=false` | OFF |
| 47 | Guardrails | `core/guardrails.py` | `ENABLE_GUARDRAILS=true` | ON |
| 48 | Length Controller | `services/length_controller.py` | always | ON |
| 49 | Style Normalizer | `core/dm/style_normalizer.py` | `ENABLE_STYLE_NORMALIZER=true` | ON ★NEW★ |
| 50 | Apply Emoji Limit | `core/dm/phases/postprocessing.py` | DISABLED (commit 0c0a2af3) | DEAD |
| 51 | Instagram Formatter | `services/instagram_service.py` | always | ON |
| 52 | Payment Link Injector | `postprocessing.py` (step 7d) | on purchase_intent | ON |
| 53 | Clone Score Engine | `services/clone_score_engine.py` | `ENABLE_CLONE_SCORE=false` | OFF |
| 54 | Confidence Scorer | `core/confidence_scorer.py` | always | ON |
| 55 | Lead Score Update | `services/lead_service.py` | always (sync) | ON |
| 56 | Conversation State Updater | `core/conversation_state.py` | always (bg) | ON |
| 57 | Memory Engine Writer | `services/memory_engine.py` | `ENABLE_MEMORY_ENGINE` | ON |
| 58 | Commitment Tracker | `services/commitment_tracker.py` | `ENABLE_COMMITMENT_TRACKING=true` | ON |
| 59 | Message Splitter | `services/message_splitter.py` | `ENABLE_MESSAGE_SPLITTING=true` | ON |

**Resumen de estado:**
- ON (activos): ~38 sistemas
- OFF (código presente, flag off): ~14 sistemas
- DEAD (obsoletos/phantoms): 2 sistemas (`apply_emoji_limit`, `_truncate_if_looping`)

---

## Los 7 sistemas nuevos (añadidos 21-31 marzo)

Antes del 21-mar el pipeline tenía **52 sistemas**. Entre Mar 29-31 se añadieron 7:

| # | Sistema | Commit / Sesión | Por qué |
|---|---------|-----------------|---------|
| 53 | **Style Normalizer** (`core/dm/style_normalizer.py`) | Mar 29 | Match cuantitativo emoji/excl vs baseline creator |
| 54 | **ECHO StyleProfile Injector** (`agent.py:_enrich_style_with_profile`) | Mar 29-31 | Inyecta métricas reales de estilo al system_prompt |
| 55 | **Creator Auto-Provisioner** (`services/creator_auto_provisioner.py`) | Mar 29 | Genera Doc D + profiles en primer contacto |
| 56 | **Creator Profile Service** (`services/creator_profile_service.py`) | Mar 29 | CRUD de perfiles cuantitativos por creator |
| 57 | **Compressed Doc D Builder** (`core/dm/compressed_doc_d.py`) | Mar 29 | 38K chars → 1.3K chars (3x mejora calidad) |
| 58 | **Q-Suppression Hint** (`generation.py:_maybe_question_hint`) | Mar 30-31 | Reduce question_rate a baseline data-driven |
| 59 | **Blacklist Replacement** (en `calibration_loader.py`) | Mar 29 | Reemplaza palabras/emojis prohibidos (Doc D) |

---

## Configuración óptima — Railway ENV vars

### Flags ON en producción (confirmados)

```bash
# Detection
ENABLE_SENSITIVE_DETECTION=true
ENABLE_FRUSTRATION_DETECTION=true
ENABLE_CONTEXT_DETECTION=true

# Context
ENABLE_RAG=true
ENABLE_BM25_HYBRID=true
ENABLE_RERANKING=true
ENABLE_QUERY_EXPANSION=true
ENABLE_RELATIONSHIP_DETECTION=true
ENABLE_STYLE_ANALYZER=true
ENABLE_QUESTION_CONTEXT=true
ENABLE_CITATIONS=true
ENABLE_CONVERSATION_STATE=true
ENABLE_ADVANCED_PROMPTS=true
ENABLE_MEMORY_ENGINE=true
ENABLE_EPISODIC_MEMORY=true
ENABLE_SEMANTIC_MEMORY_PGVECTOR=true

# Post-processing
ENABLE_OUTPUT_VALIDATION=true
ENABLE_RESPONSE_FIXES=true
ENABLE_QUESTION_REMOVAL=true
ENABLE_GUARDRAILS=true
ENABLE_MESSAGE_SPLITTING=true
ENABLE_STYLE_NORMALIZER=true
ENABLE_COMMITMENT_TRACKING=true

# Autolearning (copilot)
ENABLE_AUTOLEARNING=true
ENABLE_LEARNING_CONSOLIDATION=true
ENABLE_MEMORY_DECAY=true
```

### Flags OFF en producción (deliberadamente desactivados)

```bash
# Generación — too many LLM calls o sin reward model calibrado
ENABLE_BEST_OF_N=false          # +3 calls, sin ranking calibrado
ENABLE_SELF_CONSISTENCY=false   # +2 calls, degrada personalidad
ENABLE_CHAIN_OF_THOUGHT=false   # +1 call, costoso
ENABLE_LEARNING_RULES=false     # Reglas ruidosas auto-extraídas
ENABLE_PREFERENCE_PROFILE=false # Sin datos suficientes
ENABLE_GOLD_EXAMPLES=false      # Sin semantic retrieval calibrado

# Post-processing — probado, no mejora
ENABLE_REFLEXION=false          # Genera estilo genérico (+1 call)
ENABLE_PPA=false                # Off porque SBS lo sustituye
ENABLE_SCORE_BEFORE_SPEAK=false # Off hasta calibrar threshold

# Experimental
ENABLE_CLONE_SCORE=false
ENABLE_EMAIL_CAPTURE=false
ENABLE_HIERARCHICAL_MEMORY=false
```

### Parámetros críticos (NO cambiar sin autorización)

```bash
# LLM
GEMINI_MODEL=gemini-2.5-flash-lite  # Confirmado empíricamente mejor
# Fallback: GPT-4o-mini (automático)

# Temperatura y tokens (por creator, en calibration file)
# iris_bertran: temperature=0.7, max_tokens=100
# (NO cambiar DIRECTAMENTE — gestionar via calibration file)

# Pool threshold  
# conf >= 0.85 para activar pool (en AGENT_THRESHOLDS)
```

---

## Antes vs Después (21 mar → 31 mar)

### Estado pre-21 marzo (antes de la gran sesión)

| Área | Estado |
|------|--------|
| Doc D | 16,600 tokens (81% del prompt) — LLM ignoraba instrucciones cuantitativas |
| Few-shot | 0 calibration examples (archivo no existía) |
| RAG | 0 chunks buscables (93 chunks en DB pero sin embeddings por bug slug vs UUID) |
| Conversation State | Conectado pero `update_state()` sin llamadas — todos los leads en INICIO |
| Best-of-N | ON — +3 LLM calls, sin reward model → selección aleatoria |
| Self-consistency | ON — +2 LLM calls, degrada personalidad |
| Learning Rules | ON — inyectaba ~5 reglas ruidosas/contradictorias por llamada |
| Pool Responses | OFF (confidence=1.1, imposible de alcanzar) |
| Memory budget | 1,200 chars (insuficiente) |
| Style Normalizer | NO EXISTÍA |
| Score | ~17.1% SequenceMatcher / ~2.5/10 LLM-judge |

### Cambios realizados 21 mar

| Cambio | Impacto |
|--------|---------|
| Desactivar Best-of-N, Self-consistency, Reflexion, Learning Rules | 7-8 LLM calls → 1-2. Latencia -60% |
| Doc D: 16,600 → 1,870 tokens (89% reducción) | Prompt 5x más corto, control cuantitativo |
| Calibration file: 50 few-shot examples reales | 0 → 10 ejemplos por llamada |
| Fix RAG embeddings (slug vs UUID) | 0 → 118 chunks buscables |
| Conectar `update_state()` al pipeline | Leads transicionan por fases |
| Memory budget: 1,200 → 3,000 chars | 3x más contexto del lead |
| PPA (Post Persona Alignment) | Re-scoring post-generación |
| COMEDY compressive memory | Leads con historial largo |
| Anti-loop guardrail: prefix → exact match | Elimina 5 false positives |
| Reordenar prompt: static first | Maximiza prefix cache Gemini (90% desc.) |
| **Score final** | 34.2% SM / 6.6/10 LLM-judge (+164%) |

### Cambios realizados 25-31 mar

| Cambio | Sesión | Impacto |
|--------|--------|---------|
| CPE Framework v1 (L0-L2) | Mar 29 | Sistema de evaluación científica |
| Compressed Doc D builder | Mar 29 | 38K chars → 1.3K (3x mejora L1 match 0.25→0.75) |
| Style Normalizer | Mar 29 | Corrección post-proceso emoji/excl rate |
| Creator Profile Service | Mar 29 | CRUD perfiles cuantitativos en DB |
| Creator Auto-Provisioner | Mar 29 | Generación Doc D automática en primer contacto |
| Fix referencia circular style normalizer | Mar 30 | Rates estables entre runs (antes oscilaban 0.28↔0.96) |
| Fix excl normalizer adaptativo | Mar 30 | `keep_prob = target/natural` sin hardcoded thresholds |
| Prometheus 7B local (Ollama) como juez | Mar 30 | L2 eval sin costo ($0) |
| Q-Suppression Hint | Mar 30-31 | Reduce question_rate data-driven |
| DISABLE `apply_emoji_limit` | Mar 31 | Style Normalizer es el único controlador de emojis |
| Audit 59 sistemas | Mar 31 | Identificó 2 phantoms (apply_emoji_limit, loop truncator) |

### Estado actual (31 mar)

| Métrica | Valor |
|---------|-------|
| L1 Match (aislado, Iris) | **0.83** (estable post-fix circular) |
| L1 Match (pipeline) | **0.42** (gap aún no cerrado) |
| Emoji rate (bot) | 0.38 (vs GT 0.38) ✅ |
| Excl rate (bot) | 0.30 (vs GT 0.30) ✅ |
| L2 Overall (Prometheus, config3b) | 2.31/5 |
| L2 Persona Fidelity | 1.82/5 (gap principal) |
| LLM calls/mensaje | 1-2 (vs 7-8 pre-Mar21) |
| Latencia | ~600ms (Gemini Flash-Lite) |
| DPO-ready preference pairs | ~1,587 (shadow mode) |

---

## CPE v2 — Instrumento de medición (NO parte del pipeline)

CPE (Clone Persona Evaluation) es el sistema de evaluación científica del clon. **No interviene en la generación de respuestas** — mide el output del pipeline desde afuera.

```
Pipeline DM → respuestas generadas
                      ↓
    ┌─────────────────────────────────┐
    │  CPE v2 (evaluación externa)    │
    │                                 │
    │  L0: Test Set Generation        │
    │  L1: Quantitative Metrics ($0)  │
    │      emoji_rate, excl_rate,     │
    │      length, vocab, pet_names   │
    │  L2: LLM-as-Judge (~$0/run)    │
    │      Prometheus 7B (Ollama)     │
    │      5 dimensiones 1-5          │
    │  L3: BFI Human Eval             │
    │      (en curso)                 │
    │  L4: Production Metrics         │
    │      (pendiente)                │
    └─────────────────────────────────┘
```

### Por qué NO LLM-as-Judge para decisiones de ablación

> Decisión de diseño (Mar 30): Los LLM jueces en español/catalán inflan scores
> ~0.36 pts cuando falta reference_answer (GT). GPT-4o-mini inflaba 0.6 pts vs GPT-4o.
> Las métricas L1 cuantitativas (BERTScore, lexical) no tienen este sesgo.
> → Usar L1 para ablaciones. Usar L2 solo para checkpoints con GT correcto.

### Scripts CPE v2

```bash
# Level 1 — quantitative (no LLM, $0)
railway run python3 tests/cpe_level1_quantitative.py --creator iris_bertran

# Level 2 — Prometheus local (no costo)
railway run python3 tests/cpe_level2_llm_judge.py \
    --judge-model ollama/vicgalle/prometheus-7b-v2.0 --n 33

# Level 2 — GPT-4o (medición definitiva, ~$2.50/50 evals)
railway run python3 tests/cpe_level2_llm_judge.py --judge-model gpt-4o

# BERTScore semantic similarity
python3 tests/cpe_bertscore.py --creator iris_bertran

# Shadow lexical comparison
python3 tests/cpe_shadow_comparison.py --creator iris_bertran
```

---

## Archivos clave del pipeline

| Archivo | Rol |
|---------|-----|
| `core/dm/agent.py` | Orquestador principal (singleton pattern, cache TTL) |
| `core/dm/phases/detection.py` | Phase 1: sensitive, frustration, pool |
| `core/dm/phases/context.py` | Phase 2-3: intent, RAG, memory, prompt assembly |
| `core/dm/phases/generation.py` | Phase 4: prompt final + LLM call + fallback chain |
| `core/dm/phases/postprocessing.py` | Phase 5: fixes, SBS/PPA, normalizer, format |
| `core/dm/post_response.py` | Phase 6: background tasks |
| `core/dm/style_normalizer.py` | Normalización emoji/excl post-generación |
| `core/dm/compressed_doc_d.py` | Builder Doc D comprimido (38K→1.3K) |
| `services/calibration_loader.py` | Few-shot examples por creator (file-based) |
| `services/creator_auto_provisioner.py` | Auto-generación de perfiles en primer contacto |
| `services/creator_profile_service.py` | CRUD perfiles cuantitativos (DB) |
| `core/reasoning/ppa.py` | SBS + PPA (quality gates, off by default) |
| `core/providers/gemini_provider.py` | Cliente Gemini + fallback GPT-4o-mini |
| `core/rag/semantic.py` | Semantic search + BM25 hybrid |
| `core/best_of_n.py` | 3 candidatos T=[0.2, 0.7, 1.4] (off) |
| `calibrations/iris_bertran.json` | 50 few-shot examples curados (file system) |

---

## Próximos pasos pendientes (al 31 mar)

1. **Cerrar pipeline gap**: L1 aislado=0.83 pero pipeline=0.42. Investigar qué degradan las fases (conversation state inyecta preguntas extra).
2. **Persona Fidelity 1.82-2.76/5**: El bot no usa pet names (cuca, nena, reina) ni emojis en el momento correcto.
3. **Question rate**: bot=0.16, GT=0.26 — el bot hace pocas preguntas. Q-Suppression Hint puede agravar esto.
4. **Stefano Bonanno**: CPE L0+L1+L2 sin ejecutar. Doc D comprimido pendiente.
5. **Config6b excl_rate**: 0.60 vs GT 0.30 — los calibration anchors no reducen exclamaciones.
6. **L3 BFI interview**: en curso con Iris.
7. **L5 formulario Iris**: enviado, pendiente respuestas.

---

*Documento generado: 2026-03-31*
*Fuentes: core/dm/agent.py, phases/*.py, docs/PIPELINE_AUDIT.md, docs/SESSION_2026_03_21_COMPLETE.md, docs/logtech_29mar.md, docs/logtech_30mar.md*
