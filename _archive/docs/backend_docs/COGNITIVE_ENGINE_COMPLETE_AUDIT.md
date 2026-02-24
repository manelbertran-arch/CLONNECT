# CLONNECT COGNITIVE ENGINE v3.0 - Complete System Audit
**Date:** 2026-02-07
**Auditor:** Claude AI
**Version:** v2.5 Cognitive Integration (17 flags active)

---

## Executive Summary

The Clonnect Cognitive Engine is a multi-layered AI system that processes Instagram DMs through 50+ coordinated modules across 10 architectural layers. The orchestrator (`dm_agent_v2.py`, 1,433 lines) coordinates all cognitive systems via 17 feature flags, enabling fine-grained control over each capability.

**Key metrics:**
- 10 architectural layers
- 50+ cognitive modules
- 17 feature flags (14 active, 3 disabled by default)
- 6-phase message processing pipeline
- 1,433 lines in the orchestrator

---

## 1. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                   WEBHOOK ENTRY                          │
│              (Instagram / Telegram)                       │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  LAYER 1: SECURITY (Guardian)                            │
│  sensitive_detector → output_validator → response_fixes  │
│  → guardrails                                            │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  LAYER 2: CONTEXT (Compass)                              │
│  intent_classifier → frustration_detector →              │
│  context_detector → bot_question_analyzer →              │
│  query_expansion → lead_categorizer →                    │
│  conversation_state → relationship_detector              │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  LAYER 3: REASONING (Cortex)                             │
│  chain_of_thought → prompt_builder → reflexion_engine    │
│  → advanced_prompts → self_consistency                   │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  LAYER 4: MEMORY (Hippocampus)                           │
│  memory_store → conversation_memory → fact_tracking      │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  LAYER 5: DNA (Personalization)                          │
│  dna_update_triggers → relationship_analyzer →           │
│  writing_patterns → tone_service → style_loader          │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  LAYER 6: RESPONSE (Output)                              │
│  response_variator → edge_case_handler →                 │
│  length_controller → message_splitter                    │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  LAYER 7: DATA INFRASTRUCTURE (RAG)                      │
│  semantic_search → reranker → citation_service →         │
│  embedding_service → semantic_chunker                    │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  LAYER 8: ANALYTICS (Intelligence)                       │
│  insights_engine → audience_aggregator →                 │
│  audience_intelligence → analytics_manager               │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  LAYER 9: LIFECYCLE (Nurturing)                          │
│  ghost_reactivation → nurturing → nurturing_db           │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│  LAYER 10: INTEGRATION (External)                        │
│  webhook_routing → instagram_handler → instagram_api →   │
│  rate_limiter → telegram_adapter → media_capture →       │
│  cloudinary_service                                      │
└─────────────────────────────────────────────────────────┘
```

---

## 2. Layer-by-Layer Detailed Inventory

### LAYER 1: Security (Guardian)

#### 2.1.1 sensitive_detector (`core/sensitive_detector.py`)
- **Purpose:** Detect sensitive/crisis content in user messages
- **Flag:** `ENABLE_SENSITIVE_DETECTION=true`
- **Integration point:** Pre-pipeline (before all other processing)
- **7 Sensitive Types:**
  - SUICIDE, SELF_HARM, ABUSE, VIOLENCE, EATING_DISORDER, SUBSTANCE_ABUSE, CRISIS
- **Actions per type:** crisis_response, redirect_professional, empathetic_redirect
- **Thresholds:** confidence >= 0.7 triggers logging, >= 0.85 returns crisis resources
- **Crisis resources:** Localized per language (es, en)
- **Functions:** `detect_sensitive_content(text)`, `get_crisis_resources(language)`

#### 2.1.2 output_validator (`core/output_validator.py`)
- **Purpose:** Validate LLM response quality (prices, links, format)
- **Flag:** `ENABLE_OUTPUT_VALIDATION=true`
- **Integration point:** Phase 5 (post-LLM)
- **5 Validation checks:**
  1. Price accuracy against product catalog
  2. Link validity and known-link matching
  3. Response length bounds
  4. Language consistency
  5. Format verification
- **Functions:** `validate_prices(text, known_prices)`, `validate_links(text, known_links)`
- **Returns:** List of issues + corrected text for links

#### 2.1.3 response_fixes (`core/response_fixes.py`)
- **Purpose:** Fix common LLM output issues
- **Flag:** `ENABLE_RESPONSE_FIXES=true`
- **Version:** v1.5.2
- **6 Fix types:**
  1. Double greeting removal
  2. Emoji overuse reduction
  3. Exclamation mark normalization
  4. Self-reference removal ("como IA", "como asistente")
  5. Repetition removal
  6. Truncation handling
- **Function:** `apply_all_response_fixes(text)`

#### 2.1.4 guardrails (`core/guardrails.py`)
- **Purpose:** Final safety net before sending response
- **Flag:** `ENABLE_GUARDRAILS=true`
- **Integration point:** Phase 5 (after response_fixes)
- **5 Guard checks:**
  1. Competitor mention prevention
  2. Promise/guarantee detection
  3. Personal opinion boundaries
  4. Medical/legal advice prevention
  5. Inappropriate content filtering
- **Singleton:** `get_response_guardrail()`
- **Returns:** `{valid: bool, reason: str, corrected_response: str}`

### LAYER 2: Context (Compass)

#### 2.2.1 intent_classifier (`services/intent_service.py`)
- **Purpose:** Classify user message intent
- **Flag:** None (always active)
- **18+ Intent types:** GREETING, FAREWELL, INTEREST_WEAK, INTEREST_STRONG, PURCHASE_INTENT, OBJECTION_PRICE, OBJECTION_TIME, OBJECTION_DOUBT, OBJECTION_LATER, OBJECTION_WORKS, OBJECTION_NOT_FOR_ME, QUESTION_PRODUCT, QUESTION_PRICE, QUESTION_GENERAL, SUPPORT, ESCALATION, FEEDBACK_POSITIVE, FEEDBACK_NEGATIVE, OTHER
- **NON_CACHEABLE_INTENTS:** 10 intents that skip response cache

#### 2.2.2 frustration_detector (`core/frustration_detector.py`)
- **Purpose:** Detect user frustration level from message + history
- **Flag:** `ENABLE_FRUSTRATION_DETECTION=true`
- **4 Frustration levels:** LOW (0.0-0.3), MODERATE (0.3-0.5), HIGH (0.5-0.7), CRITICAL (0.7-1.0)
- **Signal types:** repeated_questions, caps_usage, negative_sentiment, explicit_frustration
- **Integration:** Phase 1, if level > 0.3 logs, if > 0.5 injects empathy prompt
- **Function:** `analyze_message(text, sender_id, prev_messages)` -> (signals, level)

#### 2.2.3 context_detector (`core/context_detector.py`)
- **Purpose:** Detect conversational context signals
- **Flag:** `ENABLE_CONTEXT_DETECTION=true`
- **10-step detection pipeline:** sarcasm, urgency, B2B context, time_sensitivity, price_comparison, competitor_mention, group_buying, technical_level, emotional_state, language_switching
- **Function:** `detect_all(message, history)` -> ContextSignals (with .alerts list)

#### 2.2.4 bot_question_analyzer (`core/bot_question_analyzer.py`)
- **Purpose:** Analyze what the bot's last question was about (for context on short replies)
- **Flag:** `ENABLE_QUESTION_CONTEXT=true`
- **7 Question types:** PRICING, AVAILABILITY, FEATURE, CONFIRMATION, OPEN_ENDED, PREFERENCE, UNKNOWN
- **Trigger:** Only for short affirmations (si, ok, vale, claro, etc.)
- **Function:** `analyze_with_confidence(last_bot_message)` -> (QuestionType, confidence)
- **Helper:** `is_short_affirmation(text)` -> bool

#### 2.2.5 query_expansion (`core/query_expansion.py`)
- **Purpose:** Expand user queries with synonyms for better RAG retrieval
- **Flag:** `ENABLE_QUERY_EXPANSION=true`
- **60+ synonym mappings** for Spanish product/course terminology
- **Integration:** Phase 3, BEFORE RAG retrieve
- **Function:** `expand(text, max_expansions=2)` -> list of expanded queries

#### 2.2.6 lead_categorizer (`core/lead_categorizer.py`)
- **Purpose:** Advanced lead categorization based on conversation analysis
- **Flag:** `ENABLE_LEAD_CATEGORIZER=true`
- **5 Categories:** NUEVO, INTERESADO, CALIENTE, CLIENTE, FANTASMA
- **Integration:** `_get_lead_stage()` - uses as primary, falls back to score-based
- **Function:** `categorize(messages, is_customer)` -> (category, score, reason)

#### 2.2.7 conversation_state (`core/conversation_state.py`)
- **Purpose:** Track conversation phase and provide phase-specific instructions
- **Flag:** `ENABLE_CONVERSATION_STATE=false` (adds DB queries)
- **7 Phases:** INITIAL, DISCOVERY, PRESENTATION, OBJECTION_HANDLING, CLOSING, POST_SALE, REACTIVATION
- **Integration:** Phase 2, builds enhanced prompt with phase instructions
- **Functions:** `get_state(follower_id, creator_id)`, `build_enhanced_prompt(state)`

#### 2.2.8 relationship_type_detector (`services/relationship_type_detector.py`)
- **Purpose:** Classify the type of relationship between creator and follower
- **Flag:** `ENABLE_RELATIONSHIP_DETECTION=false`
- **6 Relationship types:** FAN, POTENTIAL_CUSTOMER, ACTIVE_CUSTOMER, FRIEND, COLLABORATOR, UNKNOWN
- **Integration:** Phase 2, before DNA context loading
- **Function:** `detect(history)` -> {type, confidence, signals}

### LAYER 3: Reasoning (Cortex)

#### 2.3.1 chain_of_thought (`core/reasoning/chain_of_thought.py`)
- **Purpose:** Complex reasoning for difficult queries
- **Flag:** `ENABLE_CHAIN_OF_THOUGHT=true`
- **3 Query types:** SIMPLE (skip CoT), MODERATE (brief reasoning), COMPLEX (full CoT)
- **Integration:** `_init_services()` creates ChainOfThoughtReasoner(llm_service)
- **Note:** Expensive - adds extra LLM call

#### 2.3.2 prompt_builder (`services/prompt_service.py` + `core/prompt_builder.py`)
- **Purpose:** Build system and user prompts with all context sections
- **Flag:** `ENABLE_ADVANCED_PROMPTS=false` (changes prompt significantly)
- **8 Prompt sections:** personality, products, style, RAG context, DNA context, state context, advanced rules, custom instructions
- **`build_rules_section(creator_name)`:** Anti-hallucination rules, response format rules
- **Integration:** Phase 3, combined_context assembled from all sources

#### 2.3.3 reflexion_engine (`core/reflexion_engine.py`)
- **Purpose:** Self-reflection on response quality
- **Flag:** `ENABLE_REFLEXION=true`
- **5 Quality checks:** repetition, hallucination risk, tone consistency, length appropriateness, context relevance
- **Integration:** Phase 5, after response_fixes
- **Function:** `analyze_response(response, user_message, previous_bot_responses)` -> ReflexionResult(needs_revision, issues, severity)

#### 2.3.4 self_consistency (`core/reasoning/self_consistency.py`)
- **Purpose:** Generate multiple responses and pick the most consistent
- **Status:** Module exists but NOT integrated into dm_agent_v2.py pipeline
- **Note:** Very expensive (multiple LLM calls)

### LAYER 4: Memory (Hippocampus)

#### 2.4.1 memory_store (`services/memory_service.py`)
- **Purpose:** Per-follower memory management
- **Flag:** `ENABLE_CONVERSATION_MEMORY=true`
- **25 fields per follower:** follower_id, username, name, platform, first_contact, last_contact, total_messages, interests, products_discussed, objections_raised, purchase_intent_score, is_lead, is_customer, status, preferred_language, last_messages (last 20), tags, source, email, phone, notes, deal_value, assigned_to, weighted_interests, preferences
- **Functions:** `get_or_create()`, `get()`, `save()`
- **Storage:** PostgreSQL (primary) + JSON files (fallback)

#### 2.4.2 conversation_memory (`models/conversation_memory.py`)
- **Purpose:** Structured conversation fact storage
- **9 Fact types:** PRICE_GIVEN, LINK_SHARED, PRODUCT_MENTIONED, OBJECTION_RAISED, INTEREST_EXPRESSED, APPOINTMENT_SET, CONTACT_SHARED, QUESTION_ASKED, COMMITMENT_MADE
- **Integration:** Used by fact_tracking in `_update_follower_memory()`

#### 2.4.3 fact_tracking (inline in dm_agent_v2.py)
- **Purpose:** Track key facts in bot responses
- **Flag:** `ENABLE_FACT_TRACKING=true`
- **Currently tracks:** PRICE_GIVEN (regex for euros/$), LINK_SHARED (https/http)
- **Integration:** `_update_follower_memory()` lines 911-924
- **Storage:** Added as `facts` list in message dict

### LAYER 5: DNA (Personalization)

#### 2.5.1 dna_update_triggers (`services/dna_update_triggers.py`)
- **Purpose:** Determine when to regenerate RelationshipDNA for a lead
- **Flag:** `ENABLE_DNA_TRIGGERS=true`
- **Thresholds:**
  - Minimum messages: 5
  - New message threshold: 10 (messages since last DNA update)
  - Cooldown: 24 hours between updates
  - Stale threshold: 30 days
- **Integration:** Phase 5, after memory update
- **Functions:** `should_update(existing_dna, total_messages)`, `schedule_async_update(creator_id, follower_id, messages)`

#### 2.5.2 relationship_analyzer (`services/relationship_analyzer.py`)
- **Purpose:** Generate full RelationshipDNA profile for a lead
- **Output:** trust_level, communication_preferences, topics_of_interest, purchase_readiness, engagement_style, recommended_approach
- **6 Relationship types analyzed:** FAN, POTENTIAL_CUSTOMER, ACTIVE_CUSTOMER, FRIEND, COLLABORATOR, UNKNOWN
- **Vocabulary analysis:** Extracts key phrases, response length patterns

#### 2.5.3 writing_patterns (`models/writing_patterns.py`)
- **Purpose:** Stefan's writing style fingerprint from real messages
- **Data:** 3,056 analyzed messages
- **Metrics:** avg message length (12-50 chars), emoji frequency, punctuation style, capitalization patterns, common phrases, response time distribution
- **Usage:** Loaded by creator_style_loader for style prompts

#### 2.5.4 tone_service (`core/tone_service.py`)
- **Purpose:** Manage creator tone profiles
- **Fields:** dialect, formality, energy, humor, emojis, signature_phrases, topics_to_avoid
- **Storage:** PostgreSQL ToneProfile table + JSON backup

#### 2.5.5 creator_style_loader (`services/creator_style_loader.py`)
- **Purpose:** Load complete style prompt from writing patterns + tone profile
- **Integration:** `_load_creator_data()` calls `get_creator_style_prompt(creator_id)`
- **Output:** Combined style prompt string

#### 2.5.6 dm_agent_context_integration (`services/dm_agent_context_integration.py`)
- **Purpose:** Load RelationshipDNA context for a specific lead
- **Function:** `get_context_for_dm_agent(creator_id, follower_id)` -> context string
- **Integration:** Phase 3, loaded alongside RAG context

### LAYER 6: Response (Output)

#### 2.6.1 response_variator_v2 (`services/response_variator_v2.py`)
- **Purpose:** Pool-based fast responses for simple messages
- **Flag:** None (always active)
- **12 Response categories** with pre-built response pools
- **Fast path:** If pool confidence >= 0.8, SKIP LLM entirely
- **Integration:** Phase 1, Step 1c (early exit)
- **Function:** `try_pool_response(message)` -> PoolResult(matched, confidence, response, category)

#### 2.6.2 edge_case_handler (`services/edge_case_handler.py`)
- **Purpose:** Handle edge cases that need special treatment
- **7 Edge types:** EMPTY_MESSAGE, VERY_LONG_MESSAGE, MEDIA_ONLY, REPEATED_MESSAGE, SPAM_DETECTED, FIRST_MESSAGE, RETURNING_AFTER_ABSENCE
- **Status:** Initialized in `_init_services()` but NOT auto-called in pipeline
- **Note:** Must be called explicitly by other code

#### 2.6.3 length_controller (`services/length_controller.py`)
- **Purpose:** Enforce response length based on message type
- **Flag:** None (always active)
- **Stefan targets:** 12-50 characters (very short, DM-style)
- **Message types detected:** greeting, question, objection, purchase_intent, general
- **Integration:** Phase 5, Step 7b
- **Functions:** `detect_message_type(message)`, `enforce_length(response, msg_type)`

#### 2.6.4 message_splitter (`services/message_splitter.py`)
- **Purpose:** Split long responses into multiple messages
- **Status:** Module exists but NOT integrated into dm_agent_v2.py pipeline
- **Note:** Would need explicit integration for multi-message responses

### LAYER 7: Data Infrastructure (RAG)

#### 2.7.1 semantic_search (`core/rag/semantic.py`)
- **Purpose:** Hybrid search combining pgvector + BM25
- **Stack:** PostgreSQL pgvector extension + keyword search
- **Integration:** Phase 3, `rag_service.retrieve()`
- **Config:** `rag_similarity_threshold=0.3`, `rag_top_k=3`

#### 2.7.2 reranker (`core/rag/reranker.py`)
- **Purpose:** Re-rank RAG results for better relevance
- **Flag:** `ENABLE_RERANKING` (import-level constant)
- **Integration:** Phase 3, Step 4b (after initial retrieval)
- **Function:** `rerank(query, results, top_k=3)`

#### 2.7.3 citation_service (`core/citation_service.py`)
- **Purpose:** Add source citations to responses
- **6 Content types:** product, faq, blog, testimonial, policy, general
- **Status:** Available but not directly called in pipeline

#### 2.7.4 embedding_service (`core/embeddings.py`)
- **Purpose:** Generate text embeddings
- **Model:** OpenAI text-embedding-3-small
- **Dimensions:** 1536
- **Used by:** RAG service, semantic search

#### 2.7.5 semantic_chunker (`core/semantic_chunker.py`)
- **Purpose:** Split documents into semantic chunks for indexing
- **Used by:** Knowledge ingestion pipeline

### LAYER 8: Analytics (Intelligence)

#### 2.8.1 insights_engine (`core/insights_engine.py`)
- **Purpose:** Generate conversation insights and analytics
- **Metrics:** response_rate, avg_response_time, conversion_rate, engagement_score

#### 2.8.2 audience_aggregator (`core/audience_aggregator.py`)
- **Purpose:** Aggregate audience data across all followers
- **8 Tabs:** overview, demographics, interests, engagement, conversion, retention, growth, segments

#### 2.8.3 audience_intelligence (`core/audience_intelligence.py`)
- **Purpose:** AI-powered audience analysis
- **Features:** Trend detection, segment prediction, churn risk

#### 2.8.4 analytics_manager (`core/analytics/analytics_manager.py`)
- **Purpose:** Centralized analytics collection and reporting

### LAYER 9: Lifecycle (Nurturing)

#### 2.9.1 ghost_reactivation (`core/ghost_reactivation.py`)
- **Purpose:** Re-engage followers who stopped responding
- **Config:** 7-90 days absence range, 30-day cooldown, max 5 per cycle
- **Trigger:** Scheduled, not in real-time pipeline

#### 2.9.2 nurturing (`core/nurturing.py`)
- **Purpose:** Automated follow-up sequences
- **12 Sequence types:** welcome, education, testimonial, offer, check-in, etc.
- **Trigger:** Scheduled

#### 2.9.3 nurturing_db (`core/nurturing_db.py`)
- **Purpose:** Database persistence for nurturing state

### LAYER 10: Integration (External)

#### 2.10.1 webhook_routing (`core/webhook_routing.py`)
- **Purpose:** Route webhooks to correct creator
- **Multi-creator:** Checks `instagram_additional_ids` JSONB column
- **Cache:** 5-minute TTL

#### 2.10.2 instagram_handler (`core/instagram_handler.py`)
- **Purpose:** Process incoming Instagram messages and route to DM agent
- **Entry point:** Main webhook handler

#### 2.10.3 instagram_api (`core/instagram.py`)
- **Purpose:** Instagram Graph API client
- **API version:** v21.0
- **Functions:** send_message, get_user_info, get_conversations, get_messages

#### 2.10.4 rate_limiter (`core/instagram_rate_limiter.py`)
- **Purpose:** Enforce Instagram API rate limits
- **Limits:** 15/min, 190/hour, 4500/day
- **Strategy:** Exponential backoff

#### 2.10.5 telegram_adapter (`core/telegram_adapter.py`)
- **Purpose:** Telegram bot integration (secondary platform)

#### 2.10.6 media_capture_service (`services/media_capture_service.py`)
- **Purpose:** Capture and process media from DMs (images, stories, reels)

#### 2.10.7 cloudinary_service (`services/cloudinary_service.py`)
- **Purpose:** Cloud media storage and optimization

---

## 3. Complete Message Processing Flow

### 3.1 Flow Diagram

```
INCOMING DM (webhook)
     │
     ▼
┌─────────────────────────────────────────────────┐
│ PRE-PIPELINE: SENSITIVE DETECTION               │
│ sensitive_detector.detect_sensitive_content()    │
│ confidence >= 0.85 → EARLY EXIT (crisis)        │
└────────────┬────────────────────────────────────┘
             │ (pass)
             ▼
┌─────────────────────────────────────────────────┐
│ PHASE 1: DETECTION                              │
│ 1a. frustration_detector.analyze_message()      │
│ 1b. context_detector.detect_all()               │
│ 1c. response_variator.try_pool_response()       │
│     confidence >= 0.8 → EARLY EXIT (pool)       │
└────────────┬────────────────────────────────────┘
             │ (pass)
             ▼
┌─────────────────────────────────────────────────┐
│ PHASE 2: CONTEXT & MEMORY                       │
│ 2a. intent_classifier.classify()                │
│ 2b. bot_question_analyzer (short affirmations)  │
│ 2c. memory_store.get_or_create()                │
│ 2d. relationship_type_detector.detect()         │
│ 2e. dm_agent_context_integration.get_context()  │
│ 2f. lead_categorizer.categorize()               │
│ 2g. conversation_state.get_state()              │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│ PHASE 3: RAG & PROMPT BUILDING                  │
│ 3a. query_expansion.expand() (before RAG)       │
│ 3b. rag_service.retrieve()                      │
│ 3c. rag_rerank() (if ENABLE_RERANKING)          │
│ 3d. Build combined_context:                     │
│     style_prompt + rag_context + dna_context    │
│     + state_context + advanced_section          │
│ 3e. prompt_builder.build_system_prompt()        │
│ 3f. prompt_builder.build_user_context()         │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│ PHASE 4: LLM GENERATION                        │
│ - Inject frustration context if level > 0.5     │
│ - llm_service.generate(prompt, system_prompt)   │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│ PHASE 5: POST-PROCESSING                        │
│ 5a. output_validator: validate_prices + links   │
│ 5b. response_fixes: apply_all_response_fixes()  │
│ 5c. reflexion_engine: analyze_response()        │
│ 5d. guardrails: validate_response()             │
│ 5e. length_controller: enforce_length()         │
│ 5f. instagram_service: format_message()         │
└────────────┬────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│ PHASE 6: MEMORY UPDATE & NOTIFICATIONS          │
│ 6a. _update_follower_memory() + fact_tracking   │
│ 6b. dna_update_triggers: schedule if needed     │
│ 6c. _update_lead_score()                        │
│ 6d. _check_and_notify_escalation()              │
└────────────┬────────────────────────────────────┘
             │
             ▼
        DMResponse returned
```

### 3.2 Early Exit Paths

| Exit Point | Condition | Response Source | LLM Call? |
|------------|-----------|----------------|-----------|
| Pre-pipeline | Sensitive confidence >= 0.85 | Crisis resources | No |
| Phase 1c | Pool confidence >= 0.8 | Response pool | No |
| Error | Any unhandled exception | Error template | No |

### 3.3 Exact Code Flow (line references in dm_agent_v2.py)

1. **Pre-pipeline** (lines 479-498): sensitive_detector
2. **Phase 1a** (lines 505-520): frustration_detector
3. **Phase 1b** (lines 524-531): context_detector
4. **Phase 1c** (lines 534-545): response_variator pool
5. **Phase 2a** (lines 552-554): intent_classifier
6. **Phase 2b** (lines 557-575): bot_question_analyzer
7. **Phase 2c** (lines 578-582): memory_store
8. **Phase 3a** (lines 590-597): query_expansion
9. **Phase 3b** (line 598): RAG retrieve
10. **Phase 3c** (lines 601-606): reranking
11. **Phase 2d** (lines 611-619): relationship_detection
12. **Phase 2e** (lines 622-624): DNA context
13. **Phase 2f** (lines 627): lead stage
14. **Phase 2g** (lines 631-638): conversation_state
15. **Phase 3d-3f** (lines 643-678): prompt building
16. **Phase 4** (lines 685-697): LLM generation
17. **Phase 5a** (lines 706-727): output validation
18. **Phase 5b** (lines 730-737): response fixes
19. **Phase 5c** (lines 740-756): reflexion
20. **Phase 5d** (lines 759-772): guardrails
21. **Phase 5e** (lines 775-780): length control
22. **Phase 5f** (line 783): Instagram formatting
23. **Phase 6a** (line 786): memory update + facts
24. **Phase 6b** (lines 789-798): DNA triggers
25. **Phase 6c** (line 801): lead score update
26. **Phase 6d** (lines 804-810): escalation check

---

## 4. Feature Flags Matrix

| # | Flag | Default | Priority | Effect When Disabled |
|---|------|---------|----------|---------------------|
| 1 | ENABLE_SENSITIVE_DETECTION | true | P0 | No crisis detection |
| 2 | ENABLE_OUTPUT_VALIDATION | true | P0 | No price/link validation |
| 3 | ENABLE_RESPONSE_FIXES | true | P0 | No auto-fixes on LLM output |
| 4 | ENABLE_FRUSTRATION_DETECTION | true | pre-v2.5 | No empathy injection |
| 5 | ENABLE_CONTEXT_DETECTION | true | pre-v2.5 | No sarcasm/B2B detection |
| 6 | ENABLE_CONVERSATION_MEMORY | true | pre-v2.5 | No follower memory |
| 7 | ENABLE_GUARDRAILS | true | pre-v2.5 | No safety guardrails |
| 8 | ENABLE_CHAIN_OF_THOUGHT | true | P2 | No complex reasoning |
| 9 | ENABLE_QUESTION_CONTEXT | true | P1 | Short replies lose context |
| 10 | ENABLE_QUERY_EXPANSION | true | P1 | No synonym expansion for RAG |
| 11 | ENABLE_REFLEXION | true | P1 | No self-reflection on quality |
| 12 | ENABLE_LEAD_CATEGORIZER | true | P2 | Falls back to score-based |
| 13 | ENABLE_CONVERSATION_STATE | **false** | P2 | No phase tracking |
| 14 | ENABLE_FACT_TRACKING | true | P2 | No fact extraction |
| 15 | ENABLE_ADVANCED_PROMPTS | **false** | P2 | No anti-hallucination rules |
| 16 | ENABLE_DNA_TRIGGERS | true | P3 | No auto DNA updates |
| 17 | ENABLE_RELATIONSHIP_DETECTION | **false** | P3 | No relationship typing |

**Active (true default):** 14 flags
**Disabled (false default):** 3 flags (CONVERSATION_STATE, ADVANCED_PROMPTS, RELATIONSHIP_DETECTION)

---

## 5. Key Thresholds & Constants

| Module | Constant | Value | Meaning |
|--------|----------|-------|---------|
| sensitive_detector | confidence_log | 0.7 | Log sensitive content |
| sensitive_detector | confidence_crisis | 0.85 | Return crisis resources |
| frustration_detector | level_log | 0.3 | Log frustration |
| frustration_detector | level_empathy | 0.5 | Inject empathy prompt |
| response_variator | pool_confidence | 0.8 | Skip LLM, use pool |
| rag_service | similarity_threshold | 0.3 | Min RAG relevance |
| rag_service | top_k | 3 | Max RAG results |
| lead_service | hot_threshold | 0.7 | Hot lead score |
| lead_service | interested_threshold | 0.4 | Interested lead score |
| lead_service | escalation_score | 0.8 | Hot lead notification |
| dna_triggers | min_messages | 5 | Min for DNA generation |
| dna_triggers | new_msg_threshold | 10 | Messages since last DNA |
| dna_triggers | cooldown | 24h | Between DNA updates |
| dna_triggers | stale_threshold | 30d | Force DNA refresh |
| memory_store | history_limit | 20 | Messages kept per follower |
| manual_message | history_limit | 50 | Messages for manual saves |
| dm_agent_cache | TTL | 600s (10min) | Agent singleton cache |
| ghost_reactivation | absence_range | 7-90d | Days before reactivation |
| ghost_reactivation | cooldown | 30d | Between reactivation attempts |
| ghost_reactivation | max_per_cycle | 5 | Max reactivations per run |
| rate_limiter | per_minute | 15 | Instagram API |
| rate_limiter | per_hour | 190 | Instagram API |
| rate_limiter | per_day | 4500 | Instagram API |
| length_controller | stefan_min | 12 chars | Min response length |
| length_controller | stefan_max | 50 chars | Max response length |

---

## 6. Integration Status

| Metric | Count |
|--------|-------|
| Total cognitive modules | 50+ |
| Integrated in dm_agent_v2.py | 25 |
| Available but not in pipeline | 5 (self_consistency, edge_case auto-call, message_splitter, citation_service, question_remover) |
| Feature flags | 17 |
| Active by default | 14 |
| Disabled by default | 3 |
| Integration steps complete | 13/15 (87%) |
| Skipped (no source) | 2 (question_remover, vocabulary_extractor) |

---

## 7. Data Sources

### PostgreSQL Tables
- leads, follower_memories, messages, conversation_states, user_profiles
- tone_profiles, products, lead_magnets, dismissed_leads
- relationship_dna, writing_patterns
- With pgvector extension for embeddings

### JSON Files (Fallback)
- `data/followers/{creator}/` - Per-follower memory files
- `data/stefan_knowledge/` - Knowledge base content

### External APIs
- Instagram Graph API v21.0
- OpenAI (GPT-4, text-embedding-3-small)
- Cloudinary (media storage)

---

## 8. Known Gaps & Recommendations

1. **self_consistency** - Module exists but not integrated (expensive, multiple LLM calls)
2. **message_splitter** - Module exists but not integrated (no multi-message support)
3. **edge_case_handler** - Initialized but not auto-called in pipeline
4. **citation_service** - Available but not in response flow
5. **CONVERSATION_STATE** - Disabled (adds DB queries per message)
6. **ADVANCED_PROMPTS** - Disabled (changes prompt significantly)
7. **RELATIONSHIP_DETECTION** - Disabled (extra processing)
8. **Cache limitation** - In-memory cache not shared between Railway workers
9. **Fact tracking** - Only tracks PRICE_GIVEN and LINK_SHARED (9 types available)
10. **Historical data** - 6 months of Stefan's DMs not processed through cognitive engine
