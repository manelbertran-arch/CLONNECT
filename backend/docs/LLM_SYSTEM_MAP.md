# CLONNECT LLM SYSTEM MAP — Complete Token & Cost Analysis

**Generated**: 2026-03-14
**System**: Clonnect AI Clone Platform
**Creators**: 2 (beta)
**Volume**: ~245 messages/day
**Primary Model**: Gemini 2.0 Flash-Lite
**Fallback Model**: GPT-4o-mini

---

## PRICING REFERENCE (as of 2026-03)

| Model | Input ($/M tokens) | Output ($/M tokens) | Notes |
|-------|-------------------|---------------------|-------|
| Gemini 2.0 Flash-Lite | $0.075 | $0.30 | Primary — cheapest |
| Gemini 2.5 Flash | $0.15 / $0.60 (>200K) | $0.60 / $3.50 (thinking) | **DO NOT USE** — 2-8x more expensive |
| GPT-4o-mini | $0.15 | $0.60 | Fallback only |
| text-embedding-3-small | $0.02 | N/A | RAG embeddings |
| Whisper (Groq) | Free (Tier 0) | N/A | Audio transcription |
| Whisper (OpenAI) | $0.006/min | N/A | Audio fallback |

---

## SECTION 1: MESSAGE PIPELINE (per incoming DM)

```
MESSAGE ARRIVES (webhook)
  │
  ├─ Step 1: Detection (NO LLM)
  ├─ Step 2: Context Loading (NO LLM, but embedding query)
  ├─ Step 3: Intent Classification (LLM CALL — conditional)
  ├─ Step 4: DM Response Generation (LLM CALL — always)
  ├─ Step 4b: Best-of-N (3x LLM CALLS — disabled)
  ├─ Step 4c: Chain of Thought (LLM CALL — disabled)
  ├─ Step 5: Postprocessing (NO LLM — rule-based)
  ├─ Step 5b: Reflexion Re-generation (LLM CALL — rare)
  └─ Step 6: Background (embedding write, memory, logging)
```

---

### Step 1: Detection Phase (NO LLM)

- **File**: `core/dm/phases/detection.py:22-150`
- **Trigger**: Every incoming message
- **What it does**: Sensitive content detection, frustration analysis, pool response matching
- **LLM calls**: 0
- **Cost**: $0

---

### Step 2: Context Loading (Embedding Query Only)

- **File**: `core/dm/phases/context.py:32-200`
- **Trigger**: Every incoming message (unless pool response matched in Step 1)
- **What it does**: Loads conversation history (last 20 messages), RAG semantic search, memory engine recall, DNA context, commitment tracking
- **LLM calls**: 0 (but uses embedding API for RAG query)
- **Embedding call**: `text-embedding-3-small` for query vectorization
- **Tokens**: ~50 tokens per query embedding
- **Cost per call**: $0.000001 (negligible)
- **Dependencies**: RAG results feed into system prompt. If removed, responses lose product/FAQ knowledge
- **Quality impact**: HIGH — provides factual grounding for responses

---

### Step 3: Intent Classification

- **File**: `core/intent_classifier.py:209-226`
- **Trigger**: Every incoming message
- **Model**: OpenAI GPT-4o-mini (via `core/llm.py` default client)
- **Input**: Classification prompt (~500 tokens system) + user message (~50 tokens)
- **Output**: Intent label (greeting, question, purchase_intent, complaint, etc.)
- **max_tokens**: ~100 (implicit default)
- **temperature**: 0.7
- **Avg tokens**: ~550 in / ~20 out
- **Cost per call**: $0.000095
- **Cost per day** (245 msgs): $0.023
- **Cost per month**: $0.70
- **Has quick patterns fallback**: Yes — simple patterns (hi, hola, gracias) bypass LLM
- **Estimated LLM bypass rate**: ~40% (greetings/farewells skip LLM)
- **Effective cost per month**: ~$0.42
- **Dependencies**: Intent drives response strategy, RAG query, learning rule selection
- **Quality impact**: MEDIUM — wrong intent → wrong strategy, but response still generated
- **If removed**: All messages treated as generic; strategy hints become generic

---

### Step 4: DM Response Generation (PRIMARY — ALWAYS RUNS)

- **File**: `core/dm/phases/generation.py:262-303`
- **Calls**: `core/providers/gemini_provider.py:338-391` → `generate_dm_response()`
- **Trigger**: Every incoming message (unless pool response in Step 1)
- **Pipeline**: Gemini 2.0 Flash-Lite (5s timeout) → GPT-4o-mini fallback (10s timeout)

#### Primary: Gemini 2.0 Flash-Lite

- **File**: `core/providers/gemini_provider.py:186-220` → `generate_response_gemini()`
- **API**: `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:generateContent`
- **Model env**: `GEMINI_MODEL` (default: `gemini-2.0-flash-lite`)
- **max_tokens**: 150
- **temperature**: 0.7
- **Timeout**: 5s (env: `LLM_PRIMARY_TIMEOUT`)
- **Retry**: 3x with exponential backoff on 429
- **Circuit breaker**: After 2 consecutive failures → skip Gemini for 120s

**Input breakdown**:
| Component | Avg chars | Avg tokens | Source |
|-----------|-----------|-----------|--------|
| System prompt (Doc D personality) | ~4,000 | ~1,000 | `style_profiles` table |
| User context (follower profile) | ~2,000 | ~500 | Built by context_integration |
| Conversation history (last 20 msgs) | ~3,000 | ~750 | `messages` table |
| RAG context (top 3-5 docs) | ~2,000 | ~500 | pgvector semantic search |
| Bot instructions (DNA) | ~1,000 | ~250 | `relationship_dna` table |
| Learning rules section | ~500 | ~125 | `learning_rules` table (if enabled) |
| Strategy hint + frustration | ~200 | ~50 | Computed |
| User message | ~200 | ~50 | Incoming DM |
| **TOTAL INPUT** | **~13,000** | **~3,225** | |
| **System prompt cap** | 48,000 chars | ~12,000 tokens | Truncated if exceeds |

**Output**: ~37 tokens avg (short DM response, Instagram style)

- **Cost per call (Gemini)**: (3,225 × $0.075 + 37 × $0.30) / 1M = **$0.000253**
- **Cost per day** (245 msgs): **$0.062**
- **Cost per month**: **$1.86**

#### Fallback: GPT-4o-mini

- **File**: `core/providers/gemini_provider.py:279-331` → `_call_openai_mini()`
- **Model env**: `LLM_FALLBACK_MODEL` (default: `gpt-4o-mini`)
- **Timeout**: 10s (env: `LLM_FALLBACK_TIMEOUT`)
- **Estimated fallback rate**: ~5% (Gemini reliability is high)
- **Cost per call (GPT-4o-mini)**: (3,225 × $0.15 + 37 × $0.60) / 1M = **$0.000506**
- **Additional monthly cost from fallbacks**: ~$0.19

**Combined Step 4 cost per month**: **~$2.05**

- **Dependencies**: THIS IS THE CORE — generates the actual clone response
- **Quality impact**: CRITICAL — this IS the clone's voice
- **If removed**: No DM responses generated at all

---

### Step 4b: Best-of-N Candidate Generation (DISABLED)

- **File**: `core/best_of_n.py:58-162`
- **Trigger**: `ENABLE_BEST_OF_N=true` AND copilot_mode active
- **Current status**: **DISABLED** (`ENABLE_BEST_OF_N=false`)
- **What it does**: Generates 3 response candidates at temperatures [0.2, 0.7, 1.4], scores each, returns best
- **LLM calls**: 3 parallel calls to `generate_dm_response()`
- **max_tokens**: 150 each
- **Timeout**: 12s total (env: `BEST_OF_N_TIMEOUT`)
- **Cost if enabled**: 3x Step 4 = **$6.15/month**
- **Quality impact**: MODERATE — improves response diversity but scoring is rule-based (not LLM judge)
- **If disabled (current)**: Single response at temperature 0.7 — acceptable quality

---

### Step 4c: Chain of Thought Reasoning (DISABLED)

- **File**: `core/reasoning/chain_of_thought.py:224-303`
- **Trigger**: `ENABLE_CHAIN_OF_THOUGHT=true` AND complex query detected (health, product, multi-part, 50+ words)
- **Current status**: Flag exists but NOT integrated into production DM pipeline
- **Model**: OpenAI GPT-4o-mini (via `core/llm.py`)
- **max_tokens**: 500
- **temperature**: 0.5
- **Input**: ~1,000 tokens (reasoning prompt + message)
- **Cost if enabled**: ~$0.50/month (only triggers on complex queries, ~10% of messages)
- **Quality impact**: LOW-MEDIUM — helps with multi-step questions but adds latency

---

### Step 5: Postprocessing (NO LLM — Rule-Based)

- **File**: `core/dm/phases/postprocessing.py:32-299`
- **Trigger**: Every generated response
- **What it does**: Loop detection, price/link validation, typo fixes, tone enforcement, question removal, guardrails, length control, payment link injection
- **LLM calls**: 0 — all rule-based
- **Cost**: $0

---

### Step 5b: Reflexion Re-generation (RARE)

- **File**: `core/reflexion_engine.py:106-150` (analysis) + `core/dm/phases/postprocessing.py:125-175`
- **Trigger**: `ENABLE_REFLEXION=true` (default: true) AND analysis finds HIGH/MEDIUM severity issue
- **Current status**: Analysis is rule-based (no LLM). Re-generation only triggers if severe issue found.
- **Model**: Same cascade (Gemini → GPT-4o-mini)
- **max_tokens**: 150
- **temperature**: 0.3 (conservative re-write)
- **Estimated trigger rate**: ~3% of messages (safety violations, hallucinated prices)
- **Cost per month**: ~$0.06
- **Quality impact**: HIGH for the messages it catches — prevents harmful/incorrect responses
- **If removed**: Safety net gone; incorrect prices or inappropriate content could slip through

---

### Step 6: Background Tasks (Post-Response)

- **File**: `core/dm/phases/postprocessing.py:276-299`
- **What it does**: Memory fact extraction (pgvector write), LLM usage logging, DB updates
- **Embedding call**: `text-embedding-3-small` for memory vectorization (~100 tokens)
- **Cost per call**: $0.000002
- **Cost per month**: ~$0.01
- **Quality impact**: MEDIUM-LONG-TERM — builds lead memory for future conversations

---

### TOTAL COST PER MESSAGE (Current Production Config)

| Step | LLM Calls | Cost per msg | Monthly (245/day) |
|------|-----------|-------------|-------------------|
| Context (embedding query) | 0.5* | $0.000001 | $0.01 |
| Intent Classification | 0.6** | $0.000057 | $0.42 |
| **DM Response (Gemini)** | **1.0** | **$0.000253** | **$1.86** |
| DM Response (fallback) | 0.05 | $0.000025 | $0.19 |
| Reflexion re-gen | 0.03 | $0.000008 | $0.06 |
| Memory embedding write | 1.0 | $0.000002 | $0.01 |
| **TOTAL** | **~1.7** | **$0.000346** | **$2.55** |

\* RAG search skipped for simple intents (greetings, farewells)
\** Quick pattern match bypasses LLM for ~40% of messages

**Cost per creator per month** (122.5 msgs/day each): **~$1.28**

---

## SECTION 2: AUDIO MESSAGE PIPELINE

```
AUDIO MESSAGE ARRIVES
  │
  ├─ Tier 0: Groq Whisper v3 Turbo (FREE)
  ├─ Tier 1: Gemini 2.0 Flash (audio) — if Groq fails
  ├─ Tier 2: OpenAI Whisper-1 — if Gemini fails
  │
  └─ If ENABLE_AUDIO_INTELLIGENCE=true:
      ├─ Layer 2: Clean (LLM) — remove fillers
      ├─ Layer 3: Extract (LLM) — JSON entities
      └─ Layer 4: Synthesize (LLM) — smart summary
```

### Audio Transcription (3-Tier Cascade)

| Tier | File:Line | Model | Cost | Timeout | Status |
|------|-----------|-------|------|---------|--------|
| 0 | `ingestion/transcriber.py:236` | Groq Whisper v3 Turbo | **FREE** | 30s | Primary |
| 1 | `ingestion/transcriber.py:259` | Gemini 2.0 Flash (audio inline) | ~$0.001/min | 60s | Fallback |
| 2 | `ingestion/transcriber.py:310` | OpenAI Whisper-1 | $0.006/min | 30s | Last resort |

- **Frequency**: ~5% of messages are audio (~12/day)
- **Avg duration**: ~15 seconds
- **Monthly cost**: $0 (Groq handles 95%+), ~$0.02 if fallbacks trigger

### Audio Intelligence (DISABLED by default)

- **File**: `services/audio_intelligence.py:294-394`
- **Feature flag**: `ENABLE_AUDIO_INTELLIGENCE=false`
- **If enabled**: 3 additional LLM calls per audio (clean + extract + synthesize)
- **Model**: Gemini Flash-Lite → GPT-4o-mini
- **Cost if enabled**: ~$0.001 per audio × 12/day = $0.36/month
- **Quality impact**: LOW — raw Whisper text is usually sufficient for DM context

---

## SECTION 3: SCHEDULED JOBS (CRON)

### Jobs WITH LLM calls:

#### JOB: style_recalc (ENABLED)

- **File**: `core/style_analyzer.py:337-398` → `extract_qualitative_profile()`
- **Calls**: `generate_simple()` (Gemini → GPT-4o-mini)
- **Registration**: `api/startup/handlers.py:666-702`
- **Frequency**: Every 30 days
- **Feature flag**: `ENABLE_STYLE_RECALC=true` (default)
- **Input**: 30 representative creator messages (~3,000 tokens) + analysis prompt (~500 tokens)
- **max_tokens**: 1,024
- **temperature**: 0.1
- **Output**: Qualitative style profile (tone, humor, sales style, dialect, signature phrases)
- **Cost per run**: (3,500 × $0.075 + 1,024 × $0.30) / 1M = $0.000570
- **Cost per month**: ~$0.001 (2 creators × 1 run)
- **Quality impact**: MEDIUM — updates the ECHO StyleProfile that drives tone matching
- **If removed**: Style profile becomes stale; tone drift over time

---

#### JOB: learning_consolidation (DISABLED)

- **File**: `services/learning_consolidator.py:119-139`
- **Calls**: `generate_simple()`
- **Registration**: `api/startup/handlers.py:447-482`
- **Frequency**: Every 24h
- **Feature flag**: `ENABLE_LEARNING_CONSOLIDATION=false`
- **Trigger condition**: Creator has >20 active rules AND groups of >2 similar rules exist
- **Input**: Group of similar rules (~500 tokens) + merge prompt (~300 tokens)
- **max_tokens**: 512
- **temperature**: 0.1
- **Output**: 1-2 consolidated rules replacing N overlapping rules
- **Cost if enabled**: ~$0.001/day per creator = $0.06/month
- **Quality impact**: LOW — rule cleanup, not response quality

---

#### JOB: pattern_analyzer (DISABLED)

- **File**: `services/pattern_analyzer.py:191-213`
- **Calls**: `generate_simple()`
- **Registration**: `api/startup/handlers.py:484-501`
- **Frequency**: Every 12h
- **Feature flag**: `ENABLE_PATTERN_ANALYZER=false`
- **Trigger condition**: 3+ unanalyzed preference pairs exist for a (intent, lead_stage) group
- **Input**: Preference pairs (~1,000 tokens) + judge prompt (~500 tokens)
- **max_tokens**: 500
- **temperature**: 0.2
- **Output**: Extracted learning rules from user feedback patterns
- **Cost if enabled**: ~$0.002/day = $0.06/month
- **Quality impact**: MEDIUM — auto-learns from creator edits to improve future responses

---

#### JOB: clone_score_daily (DISABLED)

- **File**: `services/clone_score_engine.py:153+` → calls `services/llm_judge.py:45`
- **Registration**: `api/startup/handlers.py:548-587`
- **Frequency**: Every 24h
- **Feature flag**: `ENABLE_CLONE_SCORE_EVAL=false`
- **Model**: **GPT-4o-mini** (NOT Gemini — avoids self-bias)
- **LLM calls per run**: Up to 150 (3 dimensions × 50 samples)
  - `_compute_knowledge_accuracy()` — LLM judge per sample
  - `_compute_persona_consistency()` — LLM judge per sample
  - `_compute_tone_appropriateness()` — LLM judge per sample
- **max_tokens**: 512 per judge call
- **temperature**: 0.1
- **Input per judge call**: ~2,000 tokens (evaluation prompt + response + context)
- **Max prompt size**: 8,000 chars
- **Cost if enabled**: 150 calls × (2,000 × $0.15 + 512 × $0.60) / 1M = **$0.091/day = $2.73/month**
- **Quality impact**: HIGH for monitoring — detects accuracy drift, hallucinations, persona breaks
- **If disabled**: No automated quality monitoring; rely on manual review

---

### Jobs WITHOUT LLM calls:

| Job | Frequency | What it does | LLM? |
|-----|-----------|-------------|------|
| `copilot_daily_eval` | 24h | Aggregate approval rates, edit patterns | No — pure SQL |
| `copilot_weekly_recal` | 7d | Trend analysis of daily evals | No — pure SQL |
| `gold_examples` | 12h | Curate approved response examples | No — data mining |
| `token_refresh` | 6h | Instagram token refresh | No — Meta API |
| `profile_pic_refresh` | 6h | Update lead profile pictures | No — Meta API |
| `media_capture` | configurable | Capture new Instagram posts | No — Meta API |
| `post_context_refresh` | 12h | Refresh creator post context cache | No — cache update |
| `score_decay` | 24h | Lead scoring decay | No — math |
| `followup_cleanup` | 24h | Clean old followup records | No — DB cleanup |
| `activities_cleanup` | 24h | Clean activity logs | No — DB cleanup |
| `queue_cleanup` | 24h | Clean message queue | No — DB cleanup |
| `reconciliation` | 30min | Sync message state | No — DB reconciliation |
| `lead_enrichment` | 6h | Enrich lead data | No — Meta API |
| `ghost_reactivation` | 24h | Reactivate dormant leads | No — DB + DM trigger |
| `memory_decay` | 24h | Decay old memory facts | No — DB update |
| `commitment_cleanup` | 24h | Clean old commitments | No — DB cleanup |

---

### Scheduled Jobs Cost Summary

| Job | Status | Monthly Cost | Quality Impact |
|-----|--------|-------------|---------------|
| style_recalc | **ENABLED** | $0.001 | Medium |
| learning_consolidation | disabled | $0.06 if on | Low |
| pattern_analyzer | disabled | $0.06 if on | Medium |
| clone_score_daily | disabled | $2.73 if on | High (monitoring) |
| **TOTAL (current)** | | **$0.001** | |
| **TOTAL (all enabled)** | | **$2.85** | |

---

## SECTION 4: ONE-TIME / ON-DEMAND TASKS

### Personality Extraction Pipeline

- **Trigger**: Creator onboarding (`POST /onboarding/create_clone` or `/onboarding/extraction/{id}/start`)
- **Frequency**: Once per creator (can be re-run manually)
- **Orchestrator**: `core/personality_extraction/extractor.py:62-170`

| Phase | File:Line | LLM Calls | Model | max_tokens | Input | Cost per creator |
|-------|-----------|-----------|-------|-----------|-------|-----------------|
| Phase 0: Data Cleaning | `data_cleaner.py:178` | 0 | — | — | SQL query, all messages | $0 |
| Phase 1: Format Conversations | `conversation_formatter.py:103` | 0 | — | — | Formatted text | $0 |
| Phase 2: Lead Analysis | `lead_analyzer.py:108` | 1 per lead (max 50) | Gemini Flash-Lite | 8,192 | Full conv body per lead (capped at 40K chars) | ~$0.05 |
| Phase 3: Personality Profile | `personality_profiler.py:504-516` | 3 parallel | Gemini Flash-Lite | 8,192 | Trimmed doc_b (3K chars) + 10 conv samples (8K chars) | ~$0.005 |
| Phase 4: Bot Configuration | `bot_configurator.py:658-670` | 3 parallel + 1 JSON | Gemini Flash-Lite | 8,192 | Profile (4K chars) + stats + dictionary | ~$0.005 |
| Phase 5: Copilot Rules | `copilot_rules.py:122` | 1 | Gemini Flash-Lite | 8,192 | Profile + config summaries (2K) | ~$0.001 |
| **TOTAL** | | **~58 calls** | | | | **~$0.06** |

**Safeguards added (2026-03-14)**:
- `EXTRACTION_MAX_LEADS=50` — caps Phase 2 LLM calls (env configurable)
- `MAX_CONV_BODY_CHARS=40000` — caps conversation size per prompt

**Previous cost (before fixes)**: With `gemini-2.5-flash` + no lead limit + multiple dev runs → **€83/month**
**Current cost**: ~$0.06 per extraction run with flash-lite + limits

---

### Content Ingestion (V2 Pipeline)

- **Trigger**: Manual content ingestion, website scraping
- **Files**: `ingestion/v2/bio_extractor.py:163`, `ingestion/v2/faq_extractor.py:378,503`, `ingestion/v2/tone_detector.py:161`
- **Model**: Via `core/llm.py` → GPT-4o-mini (default)
- **Frequency**: During creator setup / content refresh
- **Cost per creator**: ~$0.05 (bio + FAQs + tone analysis)
- **Quality impact**: HIGH — builds the RAG knowledge base

---

### i18n Translation

- **File**: `core/i18n.py:306-362`
- **Trigger**: Non-Spanish message detected (pattern-based detection primary, LLM fallback)
- **Model**: Via `core/llm.py` → GPT-4o-mini
- **max_tokens**: `len(text) * 2`
- **temperature**: 0.3
- **Estimated frequency**: <1% of messages (both creators are Spanish-speaking)
- **Monthly cost**: ~$0.01
- **Quality impact**: HIGH for non-Spanish users, irrelevant for current beta

---

## SECTION 5: EMBEDDING GENERATION

| File:Line | Trigger | Model | Dimensions | Frequency | Monthly Cost |
|-----------|---------|-------|-----------|-----------|-------------|
| `core/embeddings.py` (query) | Per DM with RAG intent | text-embedding-3-small | 1536 | ~150/day | $0.01 |
| `core/embeddings.py` (index) | Content ingestion | text-embedding-3-small | 1536 | On-demand | ~$0.01 per batch |
| `services/memory_engine.py` (write) | Per DM response (fact extraction) | text-embedding-3-small | 1536 | ~245/day | $0.01 |
| **TOTAL** | | | | | **~$0.03/month** |

---

## SECTION 6: COMPLETE MONTHLY COST BREAKDOWN

### Current Production (all disabled features OFF)

| Category | Monthly Cost | % of Total |
|----------|------------|-----------|
| **DM Response Generation (Gemini primary)** | $1.86 | 53% |
| **Intent Classification (GPT-4o-mini)** | $0.42 | 12% |
| **DM Response Fallback (GPT-4o-mini)** | $0.19 | 5% |
| **Reflexion re-generation** | $0.06 | 2% |
| **Audio transcription** | $0.02 | 1% |
| **Embeddings (RAG + memory)** | $0.03 | 1% |
| **Scheduled jobs (style_recalc only)** | $0.001 | 0% |
| **TOTAL** | **$2.58** | |
| **Per creator per month** | **$1.29** | |
| **Per message** | **$0.00035** | |

### If ALL features enabled

| Category | Additional Monthly Cost |
|----------|----------------------|
| Best-of-N (3x responses) | +$6.15 |
| Clone Score Daily (LLM judge) | +$2.73 |
| Audio Intelligence (3 layers) | +$0.36 |
| Learning Consolidation | +$0.06 |
| Pattern Analyzer | +$0.06 |
| Chain of Thought | +$0.50 |
| **TOTAL with all features** | **$12.44/month** |
| **Per creator per month** | **$6.22** |

---

## SECTION 7: WHAT-IF ANALYSIS (Disable/Enable Impact)

| Component | Monthly Savings | Quality Impact | Recommendation |
|-----------|----------------|---------------|----------------|
| **Disable intent classification** | -$0.42 | Messages treated as generic; wrong strategy hints | ❌ Keep — cheap, valuable |
| **Disable RAG context** | -$0.01 | Responses lose product/FAQ knowledge | ❌ Keep — critical for accuracy |
| **Disable reflexion** | -$0.06 | Safety net removed; bad responses slip through | ❌ Keep — cheap insurance |
| **Disable memory engine** | -$0.01 | No long-term lead memory across conversations | ⚠️ OK for now — limited impact at beta scale |
| **Enable Best-of-N** | +$6.15 | Better response diversity; ~15% quality improvement | ⚠️ Wait — not worth 3x cost yet |
| **Enable Clone Score** | +$2.73 | Automated quality monitoring; detect drift | ✅ Enable when scaling — essential for QA |
| **Enable Pattern Analyzer** | +$0.06 | Auto-learn from creator edits | ✅ Enable — very cheap, builds learning |
| **Enable Audio Intelligence** | +$0.36 | Cleaner audio context in responses | ⚠️ Wait — raw transcription is adequate |

---

## SECTION 8: ALL LLM CALL SITES — MASTER INDEX

### Gemini Flash-Lite calls (via `generate_dm_response` / `generate_simple`)

| # | File | Line | Function | Trigger | max_tokens | temp |
|---|------|------|----------|---------|-----------|------|
| 1 | `core/providers/gemini_provider.py` | 338 | `generate_dm_response()` | Every DM | 150 | 0.7 |
| 2 | `core/providers/gemini_provider.py` | 223 | `generate_simple()` | Various background | varies | varies |
| 3 | `core/best_of_n.py` | 58 | `generate_best_of_n()` | 3x DM (disabled) | 150 | 0.2/0.7/1.4 |
| 4 | `core/style_analyzer.py` | 389 | Style qualitative extraction | 30-day cron | 1024 | 0.1 |
| 5 | `services/learning_consolidator.py` | 139 | Rule consolidation | 24h cron (disabled) | 512 | 0.1 |
| 6 | `services/pattern_analyzer.py` | 196 | Pattern judge | 12h cron (disabled) | 500 | 0.2 |
| 7 | `services/audio_intelligence.py` | 372 | Audio clean/extract/synth | Per audio (disabled) | 200-600 | 0.1-0.3 |

### Gemini Flash-Lite calls (via `call_gemini_extraction` — personality extraction)

| # | File | Line | Function | Trigger | max_tokens | temp |
|---|------|------|----------|---------|-----------|------|
| 8 | `core/personality_extraction/lead_analyzer.py` | 108 | Per-lead analysis | Onboarding | 8192 | 0.3 |
| 9 | `core/personality_extraction/personality_profiler.py` | 504 | Identity extraction | Onboarding | 8192 | 0.3 |
| 10 | `core/personality_extraction/personality_profiler.py` | 510 | Tone map extraction | Onboarding | 8192 | 0.3 |
| 11 | `core/personality_extraction/personality_profiler.py` | 516 | Sales method extraction | Onboarding | 8192 | 0.3 |
| 12 | `core/personality_extraction/bot_configurator.py` | 658 | System prompt identity | Onboarding | 8192 | varies |
| 13 | `core/personality_extraction/bot_configurator.py` | 664 | System prompt tone | Onboarding | 8192 | varies |
| 14 | `core/personality_extraction/bot_configurator.py` | 670 | System prompt vocab/sales | Onboarding | 8192 | varies |
| 15 | `core/personality_extraction/bot_configurator.py` | 818 | Template rules (JSON) | Onboarding | 8192 | 0.2 |
| 16 | `core/personality_extraction/copilot_rules.py` | 122 | Copilot rules extraction | Onboarding | 8192 | 0.3 |

### GPT-4o-mini calls (via OpenAI SDK)

| # | File | Line | Function | Trigger | max_tokens | temp |
|---|------|------|----------|---------|-----------|------|
| 17 | `core/providers/gemini_provider.py` | 279 | `_call_openai_mini()` | Gemini fallback | 150 | 0.7 |
| 18 | `core/intent_classifier.py` | 215 | `classify_intent()` | Every DM | ~100 | 0.7 |
| 19 | `services/llm_judge.py` | 51 | `execute_evaluation()` | Clone score (disabled) | 512 | 0.1 |
| 20 | `core/llm.py` | default | `get_llm_client()` | Various (CoT, i18n, ingestion) | varies | varies |
| 21 | `core/i18n.py` | 354 | `translate_response()` | Non-Spanish msgs (~1%) | len×2 | 0.3 |
| 22 | `core/personality_extraction/llm_client.py` | 141 | `call_openai_extraction()` | Extraction fallback | 8192 | 0.3 |

### Embedding calls (text-embedding-3-small)

| # | File | Function | Trigger | Tokens |
|---|------|----------|---------|--------|
| 23 | `core/embeddings.py` | `generate_embedding()` | RAG query | ~50 |
| 24 | `core/embeddings.py` | `generate_embeddings_batch()` | Content ingest | varies |
| 25 | `services/memory_engine.py` | `_generate_embedding()` | Memory write | ~100 |

### Audio transcription

| # | File | Line | Model | Trigger | Cost |
|---|------|------|-------|---------|------|
| 26 | `ingestion/transcriber.py` | 236 | Groq Whisper v3 Turbo | Audio (Tier 0) | FREE |
| 27 | `ingestion/transcriber.py` | 259 | Gemini 2.0 Flash (audio) | Audio (Tier 1) | ~$0.001/min |
| 28 | `ingestion/transcriber.py` | 310 | OpenAI Whisper-1 | Audio (Tier 2) | $0.006/min |

---

## SECTION 9: SAFEGUARDS & RECOMMENDATIONS

### Current Model Configuration Points (FRAGMENTED)

| File | How model is set | Current value |
|------|-----------------|---------------|
| `core/providers/gemini_provider.py:23` | `DEFAULT_GEMINI_MODEL` constant | `gemini-2.0-flash-lite` |
| `core/providers/gemini_provider.py:201` | `os.getenv("GEMINI_MODEL")` | `gemini-2.0-flash-lite` |
| `core/providers/gemini_provider.py:290` | `os.getenv("LLM_FALLBACK_MODEL")` | `gpt-4o-mini` |
| `core/personality_extraction/llm_client.py:47` | `DEFAULT_EXTRACTION_MODEL` constant | `gemini-2.0-flash-lite` |
| `core/personality_extraction/llm_client.py:68` | `os.getenv("EXTRACTION_MODEL")` | `gemini-2.0-flash-lite` |
| `services/llm_service.py:64-68` | `DEFAULT_MODELS` dict | `gemini-2.0-flash-lite` |
| `services/llm_judge.py:26` | `os.getenv("CLONE_SCORE_JUDGE_MODEL")` | `gpt-4o-mini` |
| `core/llm.py:15` | `DEFAULT_PROVIDER` | `openai` / `gpt-4o-mini` |
| `ingestion/transcriber.py:259` | Hardcoded | `gemini-2.0-flash` (audio only) |

### Recommended Safeguards

**1. Centralized Model Config** (future improvement)
- Create `core/config/models.py` with single source of truth for all model names
- All files import from there instead of hardcoding
- Env var `GEMINI_MODEL` already works for DM pipeline — extend to extraction

**2. Startup Model Audit**
- Add a startup log line in `api/startup/handlers.py` that prints:
  ```
  [MODELS] DM: gemini-2.0-flash-lite | Fallback: gpt-4o-mini | Extraction: gemini-2.0-flash-lite | Judge: gpt-4o-mini
  ```

**3. Cost Tracking**
- `llm_usage_log` table already tracks all calls from `gemini_provider.py`
- Gap: calls via `core/llm.py` (intent classification, i18n) are NOT logged
- Gap: personality extraction calls log to stdout but NOT to `llm_usage_log`

**4. Daily Cost Endpoint**
- Add `GET /admin/llm-costs` that queries `llm_usage_log` for daily aggregates:
  ```sql
  SELECT
    DATE(created_at) as day,
    provider, model, call_type,
    SUM(tokens_in) as total_in,
    SUM(tokens_out) as total_out,
    COUNT(*) as calls,
    AVG(latency_ms) as avg_latency
  FROM llm_usage_log
  WHERE created_at > NOW() - INTERVAL '30 days'
  GROUP BY day, provider, model, call_type
  ORDER BY day DESC
  ```

**5. Hard Cost Caps**
- `EXTRACTION_MAX_LEADS=50` ✅ (added 2026-03-14)
- `MAX_CONV_BODY_CHARS=40000` ✅ (added 2026-03-14)
- Consider: `MAX_LLM_CALLS_PER_HOUR` circuit breaker for runaway loops

---

## SECTION 10: ENVIRONMENT VARIABLES — COMPLETE LIST

### Model Selection
| Env Var | Default | Used By |
|---------|---------|---------|
| `GEMINI_MODEL` | `gemini-2.0-flash-lite` | DM response, generate_simple |
| `LLM_FALLBACK_MODEL` | `gpt-4o-mini` | DM fallback |
| `EXTRACTION_MODEL` | `gemini-2.0-flash-lite` | Personality extraction |
| `CLONE_SCORE_JUDGE_MODEL` | `gpt-4o-mini` | Clone quality judge |
| `LLM_PROVIDER` | `openai` | core/llm.py clients |

### Timeouts
| Env Var | Default | Used By |
|---------|---------|---------|
| `LLM_PRIMARY_TIMEOUT` | `5` (seconds) | Gemini DM timeout |
| `LLM_FALLBACK_TIMEOUT` | `10` (seconds) | GPT-4o-mini timeout |
| `BEST_OF_N_TIMEOUT` | `12` (seconds) | Best-of-N total |
| `CLONE_SCORE_JUDGE_TIMEOUT` | `15` (seconds) | Judge call timeout |

### Circuit Breaker
| Env Var | Default | Used By |
|---------|---------|---------|
| `GEMINI_CB_THRESHOLD` | `2` | Failures before circuit opens |
| `GEMINI_CB_COOLDOWN` | `120` (seconds) | Cooldown before retry |

### Feature Flags (LLM-relevant)
| Env Var | Default | Monthly cost impact |
|---------|---------|-------------------|
| `ENABLE_BEST_OF_N` | `false` | +$6.15 if enabled |
| `ENABLE_CHAIN_OF_THOUGHT` | `false` | +$0.50 if enabled |
| `ENABLE_CLONE_SCORE_EVAL` | `false` | +$2.73 if enabled |
| `ENABLE_AUDIO_INTELLIGENCE` | `false` | +$0.36 if enabled |
| `ENABLE_LEARNING_CONSOLIDATION` | `false` | +$0.06 if enabled |
| `ENABLE_PATTERN_ANALYZER` | `false` | +$0.06 if enabled |
| `ENABLE_STYLE_RECALC` | `true` | $0.001 |
| `ENABLE_REFLEXION` | `true` | $0.06 |
| `ENABLE_LEARNING_RULES` | `false` | $0 (no LLM, just injection) |
| `ENABLE_GOLD_EXAMPLES` | `false` | $0 (no LLM, just DB query) |
| `ENABLE_PREFERENCE_PROFILE` | `false` | $0 (no LLM, just metrics) |

### Extraction Limits
| Env Var | Default | Purpose |
|---------|---------|---------|
| `EXTRACTION_MAX_LEADS` | `50` | Cap leads in Phase 2 |

---

## QUICK REFERENCE: Cost Scaling Projections

| Creators | Msgs/day | Monthly Cost (current) | With all features |
|----------|----------|----------------------|-------------------|
| 2 | 245 | **$2.58** | $12.44 |
| 10 | 1,225 | ~$12.90 | ~$62.20 |
| 50 | 6,125 | ~$64.50 | ~$311.00 |
| 100 | 12,250 | ~$129.00 | ~$622.00 |
| 500 | 61,250 | ~$645.00 | ~$3,110 |

*Linear scaling assumed. Real costs may be lower due to caching, pattern bypasses, and batch efficiencies.*

---

*Document generated 2026-03-14 by Claude Code. Last verified against codebase commit state of that date.*
