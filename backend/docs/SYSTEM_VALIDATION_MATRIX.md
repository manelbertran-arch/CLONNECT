# Clonnect: System Validation Matrix

> Generated from real codebase analysis - 7 February 2026
> 81 core modules | 38 services | 44 routers | 90+ feature flags | 1,923 existing tests

---

## 1. COMPLETE FEATURE FLAGS INVENTORY

### Cognitive Engine (24 flags - in `core/dm_agent_v2.py`)

| Flag | Default | Line | Purpose | Test Coverage |
|------|---------|------|---------|---------------|
| `ENABLE_SENSITIVE_DETECTION` | `true` | 100 | Detect mental health, suicide, abuse | Indirect |
| `ENABLE_FRUSTRATION_DETECTION` | `true` | 101 | Detect user anger/frustration | Indirect |
| `ENABLE_CONTEXT_DETECTION` | `true` | 102 | Detect context switches | 69 tests |
| `ENABLE_CONVERSATION_MEMORY` | `true` | 103 | Use conversation memory | 23 tests |
| `ENABLE_GUARDRAILS` | `true` | 104 | Safety guardrails for responses | 25 tests |
| `ENABLE_OUTPUT_VALIDATION` | `true` | 105 | Validate LLM output before send | 46 tests |
| `ENABLE_RESPONSE_FIXES` | `true` | 106 | Auto-fix common response issues | 0 tests |
| `ENABLE_CHAIN_OF_THOUGHT` | `true` | 107 | Chain-of-thought reasoning | 2 tests |
| `ENABLE_QUESTION_CONTEXT` | `true` | 110 | Add question context | 5 tests |
| `ENABLE_QUERY_EXPANSION` | `true` | 111 | Expand queries for better RAG | 5 tests |
| `ENABLE_REFLEXION` | `true` | 112 | Self-improvement loop | 5 tests |
| `ENABLE_LEAD_CATEGORIZER` | `true` | 114 | Categorize leads (hot/warm/cold) | 5 tests |
| `ENABLE_CONVERSATION_STATE` | `false` | 115 | Track sales funnel stage | 4 tests |
| `ENABLE_FACT_TRACKING` | `true` | 116 | Track facts from conversations | 14 tests |
| `ENABLE_ADVANCED_PROMPTS` | `false` | 118 | Experimental advanced prompts | 4 tests |
| `ENABLE_DNA_TRIGGERS` | `true` | 119 | Personality DNA trigger analysis | 4 tests |
| `ENABLE_RELATIONSHIP_DETECTION` | `false` | 120 | Detect relationship context | 5 tests |
| `ENABLE_EDGE_CASE_DETECTION` | `true` | 124 | Detect edge cases | 39 tests |
| `ENABLE_CITATIONS` | `true` | 125 | Source attribution in responses | 37 tests |
| `ENABLE_MESSAGE_SPLITTING` | `true` | 126 | Split long messages | 26 tests |
| `ENABLE_QUESTION_REMOVAL` | `true` | 127 | Remove excessive questions | 4 tests |
| `ENABLE_VOCABULARY_EXTRACTION` | `true` | 128 | Extract creator vocabulary | 3 tests |
| `ENABLE_SELF_CONSISTENCY` | `false` | 129 | Verify response consistency | 2 tests |

**Active: 20/24 (83%) | Disabled: CONVERSATION_STATE, ADVANCED_PROMPTS, RELATIONSHIP_DETECTION, SELF_CONSISTENCY**

### RAG & Search (4 flags)

| Flag | Default | File | Purpose | Test Coverage |
|------|---------|------|---------|---------------|
| `ENABLE_RERANKING` | `false` | `core/rag/reranker.py:18` | Cross-encoder reranking (+100-200ms) | 25 tests |
| `ENABLE_BM25_HYBRID` | `false` | `core/rag/semantic.py:31` | BM25 keyword matching (+50ms) | 0 tests |
| `ENABLE_SEMANTIC_MEMORY` | `false` | `core/semantic_memory.py:23` | ChromaDB memory (deprecated) | 0 tests |
| `ENABLE_SEMANTIC_MEMORY_PGVECTOR` | `false` | `core/semantic_memory_pgvector.py:35` | pgvector memory | 0 tests |

### Infrastructure (8 flags)

| Flag | Default | File | Purpose |
|------|---------|------|---------|
| `ENABLE_JSON_FALLBACK` | `false` | `api/config.py:19` | DB fallback to JSON files |
| `ENABLE_DEMO_RESET` | `true` | `api/routers/admin/shared.py` | Allow demo data wipe |
| `RATE_LIMIT_ENABLED` | `true` | `api/middleware/rate_limit.py:126` | API rate limiting |
| `ENABLE_INTELLIGENCE` | `true` | `core/intelligence/engine.py:22` | Predictions & insights |
| `USER_PROFILES_USE_DB` | `true` | `core/user_profiles.py:24` | DB vs JSON for profiles |
| `NURTURING_DRY_RUN` | `false` | `api/routers/nurturing.py:28` | Test mode for nurturing |
| `NURTURING_USE_DB` | `false` | `core/nurturing_db.py:27` | DB vs JSON for nurturing |
| `PERSIST_CONVERSATION_STATE` | `true` | `core/conversation_state.py:22` | Persist state to DB |

### LLM Provider

| Variable | Default | Options |
|----------|---------|---------|
| `LLM_PROVIDER` | `groq` | `groq`, `openai`, `anthropic`, `xai` |

---

## 2. COMPLETE SERVICE MAP

### A. DM Processing Pipeline (Critical Path)

```
Instagram DM arrives
    |
    v
[messaging_webhooks.py] POST /webhook/instagram
    |
    v
[webhook_routing.py] find_creator_for_webhook()
    |--- Checks: page_id, user_id, instagram_additional_ids (JSONB)
    |
    v
[instagram_handler.py] InstagramHandler.process_dm()  (103KB)
    |
    v
[dm_agent_v2.py] DMResponderAgent.process_dm()  (63KB)
    |
    |--- 1. LOAD: creator_data_loader.get_creator_data() -> products, bookings, FAQs, tone
    |--- 2. DETECT: context_detector.detect_all() -> intent, emotion, urgency
    |--- 3. MEMORY: memory_service.get_follower_memory() -> history, interests
    |--- 4. STATE: conversation_state.get_state() -> funnel stage
    |--- 5. DNA: relationship_dna_service.get_dna() -> relationship profile
    |--- 6. RAG: rag_service.search() -> relevant knowledge chunks
    |--- 7. PROMPT: prompt_builder.build_system_prompt() -> system prompt with personality
    |--- 8. GENERATE: llm_service.generate() -> LLM response
    |--- 9. VALIDATE: output_validator.validate_links/prices() -> anti-hallucination
    |--- 10. GUARDRAILS: guardrails.check_safety() -> blocked topics check
    |--- 11. REFLEXION: reflexion_engine.refine() -> self-improvement
    |--- 12. POST-PROCESS: question_remover + length_controller + message_splitter
    |--- 13. UPDATE: memory + state + DNA + lead_score
    |
    v
[instagram_handler.py] send_message() -> Meta Graph API
    |
    v
[message_reconciliation.py] save to PostgreSQL
```

### B. All Services (38 files in `services/`)

| Service | File | Criticality | Inputs | Outputs | Dependencies | Tests |
|---------|------|-------------|--------|---------|--------------|-------|
| **LLM Service** | `llm_service.py` | CRITICAL | prompt, history | response text | OpenAI/Groq/Anthropic API | 22 |
| **RAG Service** | `rag_service.py` | CRITICAL | query, creator_id | relevant chunks | Embeddings, pgvector | 24 |
| **Memory Service** | `memory_service.py` | CRITICAL | follower_id | conversation context | PostgreSQL, JSON | 16 |
| **Prompt Service** | `prompt_service.py` | CRITICAL | personality, products | system prompt | None | 12 |
| **Intent Service** | `intent_service.py` | HIGH | message text | Intent enum | None | 8 |
| **Lead Service** | `lead_service.py` | HIGH | engagement metrics | score 0-100, stage | None | 28 |
| **Creator Knowledge** | `creator_knowledge_service.py` | HIGH | creator_id | knowledge base | PostgreSQL | 0 |
| **Creator DM Style** | `creator_dm_style_service.py` | HIGH | creator_id | writing style rules | PostgreSQL, JSON | 0 |
| **Context Memory** | `context_memory_service.py` | HIGH | lead_id, creator_id | conversation context | PostgreSQL | 0 |
| **Instagram Service** | `instagram_service.py` | HIGH | creator data | formatted messages | Instagram API | 20 |
| **Relationship Analyzer** | `relationship_analyzer.py` | MEDIUM | conversation history | relationship patterns | Embeddings | 12 |
| **Relationship DNA** | `relationship_dna_service.py` | MEDIUM | relationship data | DNA profile | DNA repository | 0 |
| **DNA Repository** | `relationship_dna_repository.py` | MEDIUM | lead_id | DNA persistence | PostgreSQL | 9 |
| **Vocabulary Extractor** | `vocabulary_extractor.py` | MEDIUM | content | common words/phrases | None | 8 |
| **Edge Case Handler** | `edge_case_handler.py` | MEDIUM | message, context | detection + response | Response variator | 0 |
| **Question Remover** | `question_remover.py` | MEDIUM | generated response | cleaned response | None | Indirect |
| **Length Controller** | `length_controller.py` | MEDIUM | message text | truncated message | None | Indirect |
| **Message Splitter** | `message_splitter.py` | MEDIUM | long message | split messages | None | 26 |
| **Response Variator** | `response_variator.py` | MEDIUM | lead stage, history | template response | Memory, timing | 27 |
| **Response Variator v2** | `response_variator_v2.py` | MEDIUM | same as v1 | multi-variant | Timing, memory | Indirect |
| **Bot Orchestrator** | `bot_orchestrator.py` | MEDIUM | message, context | full response | All services | 0 |
| **Timing Service** | `timing_service.py` | LOW | schedule, msg type | send time, delays | None | Indirect |
| **Creator Style Loader** | `creator_style_loader.py` | LOW | creator_id | DM style, tone | PostgreSQL, JSON | 0 |
| **Bot Instructions** | `bot_instructions_generator.py` | LOW | creator profile | bot instructions | None | 5 |
| **Cloudinary** | `cloudinary_service.py` | LOW | image/video | uploaded URL | Cloudinary API | 0 |
| **Media Capture** | `media_capture_service.py` | LOW | URL | screenshot | Playwright | 0 |
| **Post Analyzer** | `post_analyzer.py` | LOW | Instagram posts | content analysis | None | 8 |
| **Post Context** | `post_context_service.py` | LOW | post_id | post context | Repository | 6 |
| **Instagram Post Fetcher** | `instagram_post_fetcher.py` | LOW | access token | posts | Instagram API | 6 |
| **DNA Update Triggers** | `dna_update_triggers.py` | LOW | conversation signals | update needed? | DNA services | 4 |

### C. Core Modules (81 files in `core/`)

#### Critical Path Modules

| Module | File Size | Purpose | Tests |
|--------|-----------|---------|-------|
| `dm_agent_v2.py` | 63KB | Main DM agent (24 feature flags) | 23 + 87 unit |
| `instagram_handler.py` | 103KB | Instagram webhook + send | 0 |
| `prompt_builder.py` | 21KB | Build LLM prompts with personality | 46 |
| `context_detector.py` | 31KB | Detect intent, emotion, urgency | 69 |
| `output_validator.py` | 22KB | Anti-hallucination (URLs, prices) | 46 |
| `creator_data_loader.py` | 24KB | Load products, bookings, FAQs | 0 |
| `webhook_routing.py` | ~5KB | Multi-creator webhook routing | 0 |
| `message_reconciliation.py` | 36KB | Sync messages between API and DB | 0 |
| `conversation_state.py` | 18KB | Track conversation funnel stage | 0 |

#### Safety & Quality Modules

| Module | Purpose | Tests |
|--------|---------|-------|
| `guardrails.py` | Safety: blocked topics, escalation | 25 |
| `sensitive_detector.py` | Detect mental health, suicide, abuse | 0 |
| `reflexion_engine.py` | Self-refinement loop | 0 |
| `response_fixes.py` | Fix common issues (emojis, length, tone) | 0 |
| `frustration_detector.py` | Detect upset customers | 0 |

#### RAG & Knowledge Modules

| Module | Purpose | Tests |
|--------|---------|-------|
| `rag/semantic.py` | Semantic search (pgvector) | 24 |
| `rag/reranker.py` | Cross-encoder reranking | 25 |
| `rag/bm25.py` | Keyword-based retrieval | 0 |
| `embeddings.py` | OpenAI embedding generation | 0 |
| `semantic_chunker.py` | Document splitting | 31 |
| `query_expansion.py` | Expand queries for better search | 0 |

#### Platform Integration Modules

| Module | Purpose | Tests |
|--------|---------|-------|
| `instagram.py` (26KB) | Meta Graph API wrapper | 0 |
| `whatsapp.py` | WhatsApp handler | 0 |
| `telegram_adapter.py` | Telegram bot | 0 |
| `payments.py` (41KB) | Stripe/PayPal/Hotmart | 0 |
| `calendar.py` (37KB) | Calendly/Zoom/Google Cal | 0 |
| `copilot_service.py` (21KB) | AI copilot for creators | 0 |
| `notifications.py` (20KB) | Alert creators | 0 |

#### Infrastructure Modules

| Module | Purpose | Tests |
|--------|---------|-------|
| `llm.py` | LLM client factory (Groq/OpenAI/Anthropic/xAI) | 0 |
| `auth.py` | JWT authentication | 0 |
| `cache.py` | In-memory SimpleCache with TTL | 0 |
| `rate_limiter.py` | API throttling | 0 |
| `sync_worker.py` (23KB) | Background message sync | 0 |
| `token_refresh_service.py` | Refresh API tokens | 0 |
| `metrics.py` (18KB) | Prometheus metrics | 0 |
| `logging_config.py` | Logging setup | 0 |

### D. API Routers (44 in `api/routers/`)

| Category | Routes | Key Files | Tests |
|----------|--------|-----------|-------|
| **Messaging** | `/dm/*`, `/webhook/instagram`, `/messages/*` | `dm.py` (39KB), `messaging_webhooks.py`, `messages.py` (26KB) | 16 webhook tests |
| **Leads** | `/leads/*` | `leads.py` (40KB) | 3 |
| **Creator Config** | `/config/*`, `/creator/*`, `/tone/*`, `/bot/*` | Multiple | 0 |
| **Knowledge** | `/knowledge/*`, `/content/*`, `/citations/*` | Multiple | 0 |
| **Payments** | `/products/*`, `/payments/*`, `/webhook/stripe|paypal` | `products.py`, `payments.py`, `webhooks.py` | 16 |
| **Scheduling** | `/calendar/*`, `/booking/*` | `calendar.py` (26KB), `booking.py` | 7 |
| **Nurturing** | `/nurturing/*` | `nurturing.py` (34KB) | 0 |
| **Analytics** | `/intelligence/*`, `/insights/*`, `/audience/*` | Multiple | 0 |
| **OAuth** | `/oauth/instagram|whatsapp|google/*` | `oauth.py` (100KB) | 0 |
| **Admin** | `/admin/*`, `/maintenance/*`, `/debug/*` | 12 admin modules, `debug.py` (25KB) | 2 |
| **Health** | `/health`, `/health/llm`, `/health/cache` | `health.py` | 2 |

---

## 3. VALIDATION MATRIX: SYSTEMS x TESTING CATEGORIES

### Legend
- CRITICAL: Must test before any production deployment
- HIGH: Should test before scaling
- MEDIUM: Test for quality assurance
- LOW: Nice to have
- (blank): Not applicable

### Matrix

| System | Voice Fidelity | Coherence | Product Knowledge | Edge Cases | Performance | Conversion | Scalability | Current Tests |
|--------|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| **dm_agent_v2** | CRITICAL | CRITICAL | CRITICAL | CRITICAL | HIGH | CRITICAL | CRITICAL | 110 |
| **prompt_builder** | CRITICAL | HIGH | HIGH | MEDIUM | LOW | MEDIUM | HIGH | 46 |
| **output_validator** | HIGH | CRITICAL | CRITICAL | HIGH | LOW | MEDIUM | LOW | 46 |
| **context_detector** | LOW | CRITICAL | LOW | CRITICAL | MEDIUM | HIGH | MEDIUM | 69 |
| **llm_service** | CRITICAL | CRITICAL | MEDIUM | MEDIUM | CRITICAL | HIGH | CRITICAL | 22 |
| **rag_service** | MEDIUM | CRITICAL | CRITICAL | MEDIUM | HIGH | HIGH | CRITICAL | 24 |
| **memory_service** | HIGH | CRITICAL | LOW | MEDIUM | HIGH | MEDIUM | HIGH | 16 |
| **creator_dm_style** | CRITICAL | MEDIUM | - | LOW | LOW | MEDIUM | CRITICAL | 0 |
| **creator_knowledge** | LOW | HIGH | CRITICAL | LOW | MEDIUM | HIGH | MEDIUM | 0 |
| **writing_patterns** | CRITICAL | LOW | - | LOW | LOW | LOW | CRITICAL | 0 |
| **lead_service** | - | MEDIUM | LOW | LOW | LOW | CRITICAL | MEDIUM | 28 |
| **fact_tracking** | LOW | CRITICAL | HIGH | LOW | LOW | MEDIUM | LOW | 14 |
| **question_remover** | CRITICAL | MEDIUM | - | MEDIUM | LOW | MEDIUM | LOW | 4 |
| **length_controller** | CRITICAL | LOW | - | MEDIUM | LOW | MEDIUM | LOW | Indirect |
| **message_splitter** | HIGH | LOW | - | MEDIUM | LOW | LOW | LOW | 26 |
| **response_fixes** | CRITICAL | MEDIUM | - | MEDIUM | LOW | MEDIUM | LOW | 0 |
| **guardrails** | - | HIGH | MEDIUM | CRITICAL | LOW | LOW | LOW | 25 |
| **sensitive_detector** | - | LOW | - | CRITICAL | LOW | - | LOW | 0 |
| **reflexion_engine** | HIGH | HIGH | MEDIUM | MEDIUM | HIGH | MEDIUM | LOW | 0 |
| **edge_case_handler** | LOW | LOW | LOW | CRITICAL | LOW | MEDIUM | LOW | 39 |
| **conversation_state** | - | HIGH | LOW | MEDIUM | LOW | CRITICAL | MEDIUM | 4 |
| **relationship_dna** | MEDIUM | HIGH | LOW | LOW | LOW | MEDIUM | MEDIUM | 9 |
| **intent_service** | - | HIGH | MEDIUM | MEDIUM | LOW | HIGH | LOW | 8 |
| **webhook_routing** | - | - | - | CRITICAL | MEDIUM | CRITICAL | CRITICAL | 0 |
| **instagram_handler** | - | - | - | CRITICAL | CRITICAL | CRITICAL | CRITICAL | 0 |
| **message_reconciliation** | - | - | - | HIGH | HIGH | HIGH | HIGH | 0 |
| **copilot_service** | - | MEDIUM | LOW | HIGH | MEDIUM | MEDIUM | MEDIUM | 0 |
| **cache** | - | - | - | MEDIUM | CRITICAL | LOW | CRITICAL | 0 |
| **llm.py (factory)** | - | - | - | HIGH | CRITICAL | HIGH | CRITICAL | 0 |
| **sync_worker** | - | - | - | HIGH | HIGH | MEDIUM | CRITICAL | 0 |
| **payments** | - | - | CRITICAL | HIGH | MEDIUM | CRITICAL | MEDIUM | 16 |
| **nurturing** | MEDIUM | HIGH | MEDIUM | MEDIUM | MEDIUM | CRITICAL | MEDIUM | 0 |
| **Meta Graph API** | - | - | - | CRITICAL | CRITICAL | CRITICAL | CRITICAL | 13 contract |
| **OpenAI/Groq API** | CRITICAL | CRITICAL | MEDIUM | HIGH | CRITICAL | HIGH | CRITICAL | 0 |

---

## 4. SPECIFIC TESTS PER SYSTEM (3-5 each)

### dm_agent_v2 (Main Agent)

| # | Test | Category | Priority |
|---|------|----------|----------|
| 1 | Agent responds in creator's voice (avg length ~38 chars, 19% emoji) | Voice Fidelity | P0 |
| 2 | Agent uses correct product info when asked about pricing | Product Knowledge | P0 |
| 3 | Agent doesn't hallucinate URLs or prices not in knowledge base | Coherence | P0 |
| 4 | Agent escalates to human on sensitive topics (mental health, abuse) | Edge Cases | P0 |
| 5 | Agent response time < 5s for standard messages | Performance | P1 |

### prompt_builder

| # | Test | Category | Priority |
|---|------|----------|----------|
| 1 | System prompt includes creator name, tone, and vocabulary | Voice Fidelity | P0 |
| 2 | Products are formatted with correct prices in prompt | Product Knowledge | P0 |
| 3 | Prompt adapts to follower's relationship DNA (close friend vs stranger) | Voice Fidelity | P1 |
| 4 | Prompt doesn't exceed token limit (8K system prompt) | Performance | P1 |

### output_validator

| # | Test | Category | Priority |
|---|------|----------|----------|
| 1 | Blocks responses containing URLs not in knowledge base | Coherence | P0 |
| 2 | Blocks responses with incorrect product prices | Product Knowledge | P0 |
| 3 | Flags responses in wrong language (Spanish expected) | Edge Cases | P1 |
| 4 | Passes valid responses without modification | Performance | P1 |

### creator_dm_style (0 tests - NEEDS)

| # | Test | Category | Priority |
|---|------|----------|----------|
| 1 | Returns correct style for known creator (stefano: 38 avg chars, 19% emoji) | Voice Fidelity | P0 |
| 2 | Falls back to default style for unknown creator | Edge Cases | P0 |
| 3 | Style loads from DB when available, JSON as fallback | Scalability | P1 |
| 4 | Multi-creator: each creator gets their own style | Scalability | P1 |

### webhook_routing (0 tests - NEEDS)

| # | Test | Category | Priority |
|---|------|----------|----------|
| 1 | Routes webhook to correct creator by page_id | Edge Cases | P0 |
| 2 | Routes webhook using instagram_additional_ids JSONB | Edge Cases | P0 |
| 3 | Returns 404 for unmatched webhook (no crash) | Edge Cases | P0 |
| 4 | Handles concurrent webhooks from different creators | Scalability | P1 |
| 5 | Logs unmatched webhooks for debugging | Edge Cases | P1 |

### instagram_handler (0 tests - NEEDS)

| # | Test | Category | Priority |
|---|------|----------|----------|
| 1 | Verifies webhook signature correctly | Edge Cases | P0 |
| 2 | Processes incoming DM and routes to agent | Edge Cases | P0 |
| 3 | Sends response via Meta Graph API with retry | Performance | P0 |
| 4 | Handles rate limit (429) from Meta API gracefully | Scalability | P0 |
| 5 | Handles duplicate webhook deliveries (idempotent) | Edge Cases | P1 |

### llm_service

| # | Test | Category | Priority |
|---|------|----------|----------|
| 1 | Returns response within 5s for standard prompt | Performance | P0 |
| 2 | Falls back to alternate provider on failure | Edge Cases | P0 |
| 3 | Handles rate limit from LLM provider | Scalability | P0 |
| 4 | Streaming works correctly for long responses | Performance | P1 |
| 5 | Token counting is accurate for billing | Performance | P1 |

### rag_service

| # | Test | Category | Priority |
|---|------|----------|----------|
| 1 | Returns relevant chunks for product questions | Product Knowledge | P0 |
| 2 | Returns empty for completely unrelated queries | Coherence | P0 |
| 3 | Reranking improves relevance score | Coherence | P1 |
| 4 | Search latency < 500ms for 1000 chunks | Performance | P1 |

### cache

| # | Test | Category | Priority |
|---|------|----------|----------|
| 1 | Cache hit returns same data as DB query | Coherence | P0 |
| 2 | Cache expires after TTL (60s) | Edge Cases | P0 |
| 3 | Cache warming loads conversations on startup | Performance | P1 |
| 4 | Concurrent reads don't cause race conditions | Scalability | P1 |

### message_reconciliation (0 tests - NEEDS)

| # | Test | Category | Priority |
|---|------|----------|----------|
| 1 | Saves message to DB with correct metadata | Coherence | P0 |
| 2 | Deduplicates messages by platform_message_id | Edge Cases | P0 |
| 3 | Updates last_contact_at on new message | Conversion | P0 |
| 4 | Handles DB connection failure gracefully | Edge Cases | P1 |

### sensitive_detector (0 tests - NEEDS)

| # | Test | Category | Priority |
|---|------|----------|----------|
| 1 | Detects suicide/self-harm keywords | Edge Cases | P0 |
| 2 | Detects abuse/violence mentions | Edge Cases | P0 |
| 3 | Returns crisis resources when detected | Edge Cases | P0 |
| 4 | Does NOT false-positive on normal emotional messages | Voice Fidelity | P1 |

### question_remover

| # | Test | Category | Priority |
|---|------|----------|----------|
| 1 | Removes trailing questions ("Te gustaria saber mas?") | Voice Fidelity | P0 |
| 2 | Keeps questions that are part of natural conversation | Voice Fidelity | P0 |
| 3 | Stefan asks questions only 14.5% of the time | Voice Fidelity | P0 |

### response_fixes (0 tests - NEEDS)

| # | Test | Category | Priority |
|---|------|----------|----------|
| 1 | Fixes messages that are too long (>100 chars for Stefan) | Voice Fidelity | P0 |
| 2 | Adds emoji only when Stefan would (19% rate, at end) | Voice Fidelity | P0 |
| 3 | Removes formal phrases Stefan never uses ("En que puedo ayudarte?") | Voice Fidelity | P0 |
| 4 | Preserves message meaning after fixes | Coherence | P0 |

### nurturing (0 tests - NEEDS)

| # | Test | Category | Priority |
|---|------|----------|----------|
| 1 | Sends follow-up after configured delay | Conversion | P0 |
| 2 | Doesn't send to dismissed leads | Edge Cases | P0 |
| 3 | Respects DRY_RUN flag | Edge Cases | P0 |
| 4 | Handles multiple concurrent sequences | Scalability | P1 |
| 5 | Ghost reactivation triggers after 7+ days | Conversion | P1 |

### payments

| # | Test | Category | Priority |
|---|------|----------|----------|
| 1 | Stripe webhook verifies signature | Edge Cases | P0 |
| 2 | Payment success updates lead to "cliente" | Conversion | P0 |
| 3 | Handles duplicate webhook events | Edge Cases | P0 |
| 4 | PayPal callback processes correctly | Conversion | P1 |

---

## 5. DEPENDENCY MAP: IF X FAILS, WHAT BREAKS

```
OpenAI/Groq API DOWN
  |--- dm_agent_v2: Cannot generate responses (TOTAL FAILURE)
  |--- rag_service: Cannot generate embeddings for search
  |--- reflexion_engine: Cannot self-improve
  |--- chain_of_thought: Cannot reason
  |--- IMPACT: Bot stops responding entirely
  |--- FALLBACK: response_variator can serve pool templates (degraded)

PostgreSQL (Neon) DOWN
  |--- All DB reads/writes fail
  |--- memory_service: No conversation history
  |--- lead_service: No lead data
  |--- creator_data_loader: No products/FAQs
  |--- message_reconciliation: Messages lost
  |--- FALLBACK: JSON files (if ENABLE_JSON_FALLBACK=true)
  |--- IMPACT: Severe degradation, recent data lost

Meta Graph API DOWN
  |--- instagram_handler: Cannot send responses
  |--- webhook_routing: Webhooks still received but responses fail
  |--- sync_worker: Cannot sync new messages
  |--- IMPACT: Bot receives messages but can't reply
  |--- FALLBACK: Queue messages for retry (NOT IMPLEMENTED)

Cache Service FAIL
  |--- API responses slow (cold DB queries every time)
  |--- /dm/leads: 39s instead of 0.6s
  |--- /dm/conversations: 20s instead of 0.6s
  |--- IMPACT: Degraded performance, not total failure

webhook_routing FAIL
  |--- All incoming DMs are lost (not routed)
  |--- IMPACT: TOTAL FAILURE for all creators
  |--- No fallback exists

creator_data_loader FAIL
  |--- dm_agent_v2: No personality, products, or FAQs
  |--- prompt_builder: Generic prompt (sounds robotic)
  |--- IMPACT: Bot responds as generic assistant, not as creator

output_validator FAIL
  |--- Hallucinated URLs/prices can reach users
  |--- IMPACT: Trust damage, incorrect product info
  |--- FALLBACK: guardrails provides secondary check

memory_service FAIL
  |--- No conversation context
  |--- Bot doesn't remember previous interactions
  |--- IMPACT: Repetitive/inconsistent responses

sensitive_detector FAIL
  |--- Crisis messages not escalated
  |--- IMPACT: Ethical/legal risk
  |--- FALLBACK: guardrails may catch some cases
```

### Cascade Failure Scenarios

| Trigger | Cascade | Total Impact |
|---------|---------|--------------|
| OpenAI API key revoked | LLM -> Agent -> All responses | Bot goes silent |
| Neon DB maintenance | DB -> Memory + Leads + Products | Degraded to JSON fallback |
| Meta API rate limit | Sending -> Responses queue up | Delayed responses |
| Railway restart | Cache cleared -> Cold starts | 16-39s first requests |
| DNS failure | All external APIs | Total system failure |

---

## 6. VULNERABILITIES & HARDCODED VALUES

### CRITICAL (Fix immediately)

| # | Vulnerability | File | Line | Details |
|---|--------------|------|------|---------|
| 1 | **Hardcoded API keys** | `api/init_db.py` | 203, 219 | `api_key="clonnect_manel_key"`, `api_key="clonnect_stefano_key"` |
| 2 | **Hardcoded admin secret** | `scripts/api_test_suite.py` | 18 | `"clonnect_admin_secret_2024"` as fallback |
| 3 | **SQL injection** | `api/routers/admin/dangerous.py` | 253 | `f"DELETE FROM {table}"` with f-string |
| 4 | **SQL injection** | `api/init_db.py` | 110-129 | `f"ALTER TABLE {table}"` with f-string |
| 5 | **SQL injection** | `core/embeddings.py` | - | `f"INSERT INTO content_embeddings ('{chunk_id}'..."` |

### HIGH (Fix within 1 week)

| # | Vulnerability | File | Details |
|---|--------------|------|---------|
| 6 | **Hardcoded webhook tokens** | `api/config.py:30` | `"clonnect_verify_2024"` default |
| 7 | **Hardcoded webhook tokens** | `core/whatsapp.py:72` | `"clonnect_whatsapp_verify_2024"` default |
| 8 | **Bare except clauses** | 5+ files | `except:` catches ALL exceptions silently |
| 9 | **No retry on external APIs** | `core/copilot_service.py:499` | Single attempt, no backoff |
| 10 | **Admin endpoint no rate limit** | `admin/dangerous.py` | `/reset-db` with no protection |
| 11 | **Hardcoded creator references** | `services/creator_dm_style_service.py:20-23` | Stefan UUID + name in code |
| 12 | **DEMO_RESET defaults to true** | `admin/shared.py` | Production can be wiped |

### Stefan-Specific Hardcoded Values

| File | What's Hardcoded | Line |
|------|-----------------|------|
| `services/creator_dm_style_service.py` | `"stefano_bonanno": STEFAN_DM_STYLE` | 20 |
| `services/creator_dm_style_service.py` | UUID `"5e5c2364-c99a-4484-b986-741bb84a11cf"` | 21 |
| `models/writing_patterns.py` | `STEFAN_WRITING_PATTERNS` dataclass | Full file |
| `models/creator_dm_style.py` | `STEFAN_DM_STYLE` dataclass | Full file |
| `api/init_db.py` | `clone_name="Stefano Bonanno"` | 226 |
| `api/init_db.py` | `name="stefano_auto"` | 222 |
| `api/config.py` | `DEFAULT_CREATOR_ID = "manel"` | 24 |

### Single Points of Failure

| System | Risk | Mitigation Status |
|--------|------|-------------------|
| OpenAI/Groq API | Total bot failure | LLM_PROVIDER switch exists but no auto-failover |
| PostgreSQL (Neon) | Data loss | JSON fallback exists (disabled by default) |
| Meta Graph API | Can't send/receive | No message queue for retry |
| Railway (single instance) | Cache lost on restart | Cache warming on startup helps |
| In-memory cache | Not shared between workers | Partial cache hits only |

---

## 7. TEST COVERAGE GAPS (Priority Order)

### P0: Must Test Before Production Scale

| Module | Current Tests | Needed Tests | Why Critical |
|--------|--------------|--------------|--------------|
| `instagram_handler.py` | 0 | 10+ | Gateway for ALL incoming DMs |
| `webhook_routing.py` | 0 | 5+ | Routes DMs to correct creator |
| `message_reconciliation.py` | 0 | 8+ | Data integrity for all messages |
| `creator_data_loader.py` | 0 | 6+ | Loads personality for every response |
| `sensitive_detector.py` | 0 | 8+ | Ethical/legal obligation |
| `auth.py` | 0 | 5+ | Security boundary |
| `sync_worker.py` | 0 | 6+ | Background data synchronization |

### P1: Should Test Before Multi-Creator

| Module | Current Tests | Needed Tests | Why Important |
|--------|--------------|--------------|---------------|
| `creator_dm_style_service.py` | 0 | 5+ | Multi-creator style isolation |
| `creator_knowledge_service.py` | 0 | 4+ | Knowledge isolation per creator |
| `response_fixes.py` | 0 | 5+ | Voice fidelity enforcement |
| `reflexion_engine.py` | 0 | 4+ | Response quality improvement |
| `cache.py` | 0 | 5+ | Performance under load |
| `llm.py` (factory) | 0 | 4+ | Provider switching |
| `copilot_service.py` | 0 | 5+ | Creator approval flow |
| `nurturing.py` | 0 | 6+ | Automated follow-ups |
| `conversation_state.py` | 0 (only 4 via agent) | 6+ | Sales funnel tracking |

### P2: Should Test for Quality

| Module | Current Tests | Needed Tests |
|--------|--------------|--------------|
| `frustration_detector.py` | 0 | 4+ |
| `ghost_reactivation.py` | 0 | 4+ |
| `query_expansion.py` | 0 | 3+ |
| `response_variation.py` | 0 | 4+ |
| `embeddings.py` | 0 | 3+ |
| `rag/bm25.py` | 0 | 3+ |
| `payments.py` (core logic) | 0 | 5+ |
| `notifications.py` | 0 | 3+ |

### Total Gap

| Category | Files | Tests Existing | Tests Needed |
|----------|-------|---------------|--------------|
| **Core modules with 0 tests** | 47 | 0 | ~200 |
| **Services with 0 tests** | 11 | 0 | ~50 |
| **Routers without dedicated tests** | 31 | 0 | ~100 |
| **TOTAL GAP** | **89 modules** | **0** | **~350 tests** |

---

## 8. TESTING FRAMEWORK RECOMMENDATION

### Test Categories Definition

| Category | What to Test | Example |
|----------|-------------|---------|
| **Voice Fidelity** | Bot sounds like creator, not generic AI | Message length ~38 chars, 19% emoji, uses "jaja" not "jajaja" |
| **Coherence** | No contradictions, hallucinations, or wrong info | Never invent URLs, prices match DB |
| **Product Knowledge** | Correct product info, pricing, availability | 5 products with real prices |
| **Edge Cases** | Unexpected inputs, failures, boundaries | Empty messages, abuse, spam, 10K char messages |
| **Performance** | Speed, latency, resource usage | Response < 5s, search < 500ms |
| **Conversion** | Sales funnel advancement, lead scoring accuracy | Hot leads detected, follow-ups sent |
| **Scalability** | Multi-creator, high volume, concurrent requests | 10 creators, 1000 leads each |

### Suggested Test Infrastructure

```
tests/
  conftest.py                    # Existing - 375 lines, good fixtures
  unit/                          # Existing - 87 tests for dm_agent modules
  services/                      # Existing - 204 tests
  contracts/                     # Existing - 36 tests
  routers/                       # Existing - 50 tests
  integration/                   # Existing - 22 tests
  NEW: voice_fidelity/           # Test creator voice matching
    test_stefan_voice.py         # Stefan-specific voice tests
    test_multi_creator_voice.py  # Multi-creator isolation
  NEW: coherence/                # Test factual accuracy
    test_anti_hallucination.py   # URLs, prices, product info
    test_memory_consistency.py   # No contradictions over time
  NEW: edge_cases/               # Test boundary conditions
    test_sensitive_content.py    # Crisis detection
    test_webhook_failures.py     # API failures
    test_concurrent_requests.py  # Race conditions
  NEW: performance/              # Existing 10 tests + new
    test_response_latency.py     # End-to-end timing
    test_cache_effectiveness.py  # Cache hit rates
  NEW: conversion/               # Test sales pipeline
    test_lead_scoring.py         # Scoring accuracy
    test_nurturing_sequences.py  # Follow-up timing
```

---

## 9. ARCHITECTURE SUMMARY

### By the Numbers

| Metric | Count |
|--------|-------|
| Feature flags | 90+ (24 cognitive, 4 RAG, 8 infra, 54+ env vars) |
| Core modules | 81 files |
| Services | 38 files |
| API routers | 44 endpoints |
| Database tables | 12+ (Creator, Lead, Message, Product, etc.) |
| External APIs | 5 (Meta, OpenAI/Groq, Stripe, PayPal, Cloudinary) |
| LLM providers supported | 4 (Groq, OpenAI, Anthropic, xAI) |
| Existing tests | 1,923 across 135 files |
| Modules with 0 tests | 89 (47 core + 11 services + 31 routers) |
| Test gap | ~350 tests needed |
| Critical vulnerabilities | 5 (SQL injection, hardcoded keys) |
| High vulnerabilities | 8 (webhook tokens, bare except, no retry) |

### Risk Assessment

| Risk | Probability | Impact | Status |
|------|------------|--------|--------|
| Bot sends wrong price | MEDIUM | HIGH | `output_validator` exists but not 100% tested |
| Bot sounds robotic | LOW (after fix) | HIGH | Writing patterns corrected, `response_fixes` untested |
| Crisis message missed | LOW | CRITICAL | `sensitive_detector` has 0 tests |
| Webhook routing fails | LOW | CRITICAL | 0 tests, but code is simple |
| Data loss on restart | LOW | HIGH | Cache warming exists, DB is persistent |
| OpenAI outage | MEDIUM | CRITICAL | No auto-failover between providers |
| Multi-creator interference | MEDIUM | HIGH | Style isolation untested |
| SQL injection attack | LOW | CRITICAL | 3 locations with f-string SQL |

---

> Report generated from real codebase analysis
> Backend: /Users/manelbertranluque/Desktop/CLONNECT/backend/
> Total files analyzed: 200+
> Analysis date: 7 February 2026
