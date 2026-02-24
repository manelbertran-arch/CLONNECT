# Clonnect Cognitive Engine v3.0 - Complete Audit

**Date:** 2026-02-07
**Scope:** Full inventory of all 10 processing layers, 50+ modules, 17 feature flags
**Orchestrator:** `core/dm_agent_v2.py` (~1,433 lines)

---

## Executive Summary

The Clonnect Cognitive Engine is a multi-layered AI pipeline that processes incoming Instagram/Telegram DMs, applies security screening, contextual analysis, reasoning, personalization, and post-processing before sending a response on behalf of the creator.

| Metric | Value |
|--------|-------|
| Processing Layers | 10 |
| Total Modules | 50+ |
| Feature Flags | 17 (all active in production) |
| Orchestrator Size | ~1,433 lines (`dm_agent_v2.py`) |
| Intents Recognized | 18+ |
| Sensitive Categories | 7 |
| Lead Categories | 5 |
| Conversation Phases | 7 |
| Relationship Types | 6 |
| Response Fix Rules | 6 |
| Guardrail Checks | 5 |
| Nurturing Sequences | 12 |

---

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────┐
│              INCOMING MESSAGE                    │
├─────────────────────────────────────────────────┤
│ L1: SECURITY (Guardian)                         │
│   sensitive_detector → output_validator →        │
│   response_fixes                                │
├─────────────────────────────────────────────────┤
│ L2: CONTEXT (Compass)                           │
│   intent_classifier → frustration_detector →    │
│   context_detector → bot_question_analyzer →    │
│   query_expansion → lead_categorizer →          │
│   conversation_state → relationship_detector    │
├─────────────────────────────────────────────────┤
│ L3: REASONING (Cortex)                          │
│   chain_of_thought → prompt_builder →           │
│   reflexion_engine → advanced_prompts           │
├─────────────────────────────────────────────────┤
│ L4: MEMORY (Hippocampus)                        │
│   memory_store → fact_tracking →                │
│   conversation_memory → dna_update_triggers     │
├─────────────────────────────────────────────────┤
│ L5: PERSONALIZATION (DNA)                       │
│   relationship_analyzer → RelationshipDNA →     │
│   vocabulary_patterns → writing_patterns →      │
│   creator_style_loader → tone_service           │
├─────────────────────────────────────────────────┤
│ L6: RESPONSE (Output)                           │
│   response_variator → edge_case_handler →       │
│   length_controller → message_splitter →        │
│   guardrails                                    │
├─────────────────────────────────────────────────┤
│ L7: DATA (Infrastructure)                       │
│   RAG_service → rag_reranker →                  │
│   citation_service → embedding_service          │
├─────────────────────────────────────────────────┤
│ L8: ANALYTICS (Intelligence)                    │
│   lead_scoring → insights_engine →              │
│   audience_aggregator → intelligence_engine     │
├─────────────────────────────────────────────────┤
│ L9: LIFECYCLE (Nurturing)                       │
│   ghost_reactivation → nurturing_service →      │
│   escalation_service                            │
├─────────────────────────────────────────────────┤
│ L10: INTEGRATION (External)                     │
│   instagram_handler → meta_api →                │
│   media_capture → cloudinary → telegram         │
├─────────────────────────────────────────────────┤
│              RESPONSE SENT                      │
└─────────────────────────────────────────────────┘
```

---

## 2. Layer-by-Layer Inventory

---

### Layer 1: Security (Guardian)

The first line of defense. Screens incoming messages for sensitive content, validates outgoing responses for factual accuracy, and applies technical fixes before delivery.

#### 1.1 sensitive_detector

| Attribute | Value |
|-----------|-------|
| **File** | `core/sensitive_detector.py` |
| **Purpose** | Detect crisis, abuse, and manipulation patterns in user messages |
| **Invocation** | Pre-pipeline, before any other processing |

**Sensitive Categories & Confidence Thresholds:**

| Category | Confidence | Action |
|----------|------------|--------|
| SELF_HARM | 0.95 | `escalate_immediate` |
| THREAT | 0.85 | `block_response` |
| PHISHING | 0.90 | `no_response` |
| SPAM | 0.90 | `no_response` |
| EATING_DISORDER | 0.80 | `empathetic_response` |
| MINOR | 0.75 - 0.95 | `no_pressure_sale` |
| ECONOMIC_DISTRESS | 0.75 | `no_pressure_sale` |

**Behavior:**
- Score >= 0.7: logs warning to monitoring
- Score >= 0.85: returns crisis resources immediately (bypasses entire pipeline)
- Crisis resources include suicide hotline numbers and professional help links

---

#### 1.2 output_validator

| Attribute | Value |
|-----------|-------|
| **File** | `core/output_validator.py` |
| **Purpose** | Validate LLM output for factual accuracy against known data |
| **Invocation** | Post-generation (Phase 5) |

**5 Validation Checks:**

| # | Check | Tolerance | Severity | On Fail |
|---|-------|-----------|----------|---------|
| 1 | Price validation | +/- 1 EUR | ERROR | Mark invalid |
| 2 | Link validation | Allowed domains only | ERROR | Mark invalid |
| 3 | Product name match | Fuzzy match | WARNING | Info only |
| 4 | Action completion | Auto-detect missing links | AUTO-FIX | Insert link |
| 5 | Smart truncate | 400 chars max | AUTO-FIX | Truncate (protects URLs/prices) |

**Auto-fix behavior:**
- Removes hallucinated links (domains not in allowed list)
- Adds missing action links when context implies next step
- Smart truncation preserves URLs and prices within the truncated text

---

#### 1.3 response_fixes

| Attribute | Value |
|-----------|-------|
| **File** | `core/response_fixes.py` |
| **Version** | v1.5.2 |
| **Purpose** | Apply deterministic regex-based fixes to LLM output |
| **Invocation** | Post-generation (Phase 5) |

**6 Fix Rules:**

| # | Fix | Pattern | Replacement |
|---|-----|---------|-------------|
| 1 | Price typo | `22?` | `22EUR` |
| 2 | Product deduplication | Repeated product names | Single mention |
| 3 | Broken links | `://www` | `https://www` |
| 4 | Identity claim | `Soy Stefano` | `Soy el asistente de Stefano` |
| 5 | Clean raw CTAs | `QUIERO SER PARTE`, `COMPRA AHORA`, etc. | Removed or softened |
| 6 | Hide technical errors | `ERROR:`, `Traceback`, etc. | Removed entirely |

---

### Layer 2: Context (Compass)

The largest layer. Analyzes incoming messages from 8 different angles to build a rich context object that informs all downstream processing.

#### 2.1 intent_classifier

| Attribute | Value |
|-----------|-------|
| **Files** | `core/intent_classifier.py`, `services/intent_service.py` |
| **Purpose** | Classify user message into one of 18+ intent categories |
| **Quick classify** | Confidence >= 0.85 skips LLM call |

**18+ Intent Categories:**

| Intent | Description |
|--------|-------------|
| `GREETING` | Hello, hi, hey |
| `THANKS` | Thank you, gracias |
| `QUESTION_PRODUCT` | Asking about a specific product |
| `QUESTION_GENERAL` | General information question |
| `INTEREST_SOFT` | Mild curiosity |
| `INTEREST_STRONG` | Strong buying signal |
| `PURCHASE_INTENT` | Ready to buy |
| `OBJECTION_PRICE` | Too expensive |
| `OBJECTION_TIME` | No time right now |
| `OBJECTION_DOUBT` | Not sure it works |
| `OBJECTION_LATER` | Maybe later |
| `OBJECTION_WORKS` | Does it really work? |
| `OBJECTION_NOT_FOR_ME` | Not for me |
| `ESCALATION` | Wants to talk to a human |
| `SUPPORT` | Technical or service issue |
| `FEEDBACK_POSITIVE` | Praise or positive review |
| `FEEDBACK_NEGATIVE` | Complaint or negative review |
| `OTHER` | Unclassified |

---

#### 2.2 frustration_detector

| Attribute | Value |
|-----------|-------|
| **File** | `core/frustration_detector.py` |
| **Purpose** | Measure user frustration level to adjust response empathy |
| **Integration** | Injects empathy context when frustration > 0.5 |

**Frustration Levels:**

| Level | Score Range | Signals |
|-------|-------------|---------|
| `none` | 0.0 | No frustration indicators |
| `mild` | 0.2 - 0.3 | Minor negative words |
| `moderate` | 0.4 - 0.6 | Repeated questions, some CAPS |
| `severe` | >= 0.6 | Heavy CAPS, insults, multiple `??` |

**Detection Signals:**
- CAPS ratio > 30% of message
- Repeated questions (40% overlap with previous)
- Multiple question marks (`??`, `???`)
- Negative sentiment keywords

---

#### 2.3 context_detector

| Attribute | Value |
|-----------|-------|
| **File** | `core/context_detector.py` |
| **Purpose** | Multi-dimensional context extraction in 10 sequential steps |
| **Output** | Formatted alert strings for LLM injection |

**10-Step Detection Pipeline:**

| Step | Detection | Alert Format |
|------|-----------|--------------|
| 1 | Frustration level | `WARNING FRUSTRADO` |
| 2 | Sarcasm detection | `SARCASMO` |
| 3 | B2B context | `B2B` |
| 4 | Name extraction | `NOMBRE: {name}` |
| 5 | Intent classification | (intent label) |
| 6 | Interest level | `Alta intencion` |
| 7 | Meta-message detection | (meta context) |
| 8 | Correction detection | (correction context) |
| 9 | Objection type | (objection label) |
| 10 | Positive sentiment | (sentiment context) |

---

#### 2.4 bot_question_analyzer

| Attribute | Value |
|-----------|-------|
| **File** | `core/bot_question_analyzer.py` |
| **Purpose** | Detect when user's short reply is answering a previous bot question |
| **Trigger** | Activated for short affirmation messages |

**7 Question Types & Confidence:**

| Type | Confidence | Description |
|------|------------|-------------|
| `INTEREST` | 0.85 | "Te interesa?" |
| `PURCHASE` | 0.92 | "Quieres comprarlo?" |
| `INFORMATION` | 0.75 | "Quieres saber mas?" |
| `CONFIRMATION` | 0.70 | "Confirmas?" |
| `BOOKING` | 0.88 | "Reservamos?" |
| `PAYMENT_METHOD` | 0.90 | "Como quieres pagar?" |
| `UNKNOWN` | N/A | Fallback |

**Affirmation Words (30+):**
`si`, `vale`, `dale`, `claro`, `perfecto`, `ok`, `bueno`, `genial`, `va`, `venga`, `hecho`, `listo`, `obvio`, `seguro`, `porfa`, `quiero`, `me interesa`, `vamos`, `eso`, `ya`, `correcto`, `exacto`, `afirmativo`, `por supuesto`, `como no`, `de una`, `dale que va`, `metele`, `manda`, `envia`

Supports voseo variants (Argentine Spanish).

---

#### 2.5 query_expansion

| Attribute | Value |
|-----------|-------|
| **File** | `core/query_expansion.py` |
| **Purpose** | Expand search queries with synonyms and acronyms for better RAG recall |
| **Impact** | Improves RAG recall 15-25% |

**Key Data:**
- 60+ synonym pairs for Spanish infoproduct terminology
- 9 acronym expansions:

| Acronym | Expansion |
|---------|-----------|
| IA | Inteligencia Artificial |
| ML | Machine Learning |
| SaaS | Software as a Service |
| B2B | Business to Business |
| B2C | Business to Consumer |
| ROI | Return on Investment |
| KPI | Key Performance Indicator |
| CRM | Customer Relationship Management |
| SEO | Search Engine Optimization |

---

#### 2.6 lead_categorizer

| Attribute | Value |
|-----------|-------|
| **File** | `core/lead_categorizer.py` |
| **Purpose** | Assign one of 5 lead categories based on conversation signals |
| **Evaluation Order** | CLIENTE -> CALIENTE -> FANTASMA -> INTERESADO -> NUEVO |

**5 Lead Categories:**

| Category | DB Value | Icon | Criteria |
|----------|----------|------|----------|
| New | `nuevo` | (white) | Default, just started |
| Interested | `interesado` | (yellow) | 20+ engagement keywords matched |
| Hot | `caliente` | (red) | 30+ keywords (price + purchase + booking signals) |
| Customer | `cliente` | (green) | Confirmed purchase |
| Ghost | `fantasma` | (ghost) | No response for 7+ days |

---

#### 2.7 conversation_state

| Attribute | Value |
|-----------|-------|
| **File** | `core/conversation_state.py` |
| **Purpose** | Track which sales phase the conversation is in |
| **Persistence** | PostgreSQL |

**7 Conversation Phases:**

| Phase | Name | System Prompt Focus |
|-------|------|-------------------|
| 1 | `INICIO` | Warm greeting, build rapport |
| 2 | `CUALIFICACION` | Ask qualifying questions |
| 3 | `DESCUBRIMIENTO` | Understand needs and pain points |
| 4 | `PROPUESTA` | Present relevant product/service |
| 5 | `OBJECIONES` | Handle objections with empathy |
| 6 | `CIERRE` | Close the sale, provide next steps |
| 7 | `ESCALAR` | Escalate to human creator |

**Context Extraction:**
- Situation (what the user is dealing with)
- Goal (what the user wants to achieve)
- Constraints (budget, time, location)
- Age (if mentioned)

---

#### 2.8 relationship_type_detector

| Attribute | Value |
|-----------|-------|
| **File** | `services/relationship_type_detector.py` |
| **Purpose** | Classify the relationship type between creator and follower |
| **Method** | Word weights + emoji weights per type |

**6 Relationship Types:**

| Type | Description |
|------|-------------|
| `INTIMA` | Intimate/romantic relationship |
| `AMISTAD_CERCANA` | Close friendship |
| `AMISTAD_CASUAL` | Casual acquaintance |
| `CLIENTE` | Business/customer relationship |
| `COLABORADOR` | Collaborator/partner |
| `DESCONOCIDO` | Unknown/new contact |

**Confidence Calculation:**
```
confidence = 0.6 + (score - threshold) * 0.05
```
Capped at 0.95 maximum.

---

### Layer 3: Reasoning (Cortex)

The thinking layer. Builds complex prompts, applies chain-of-thought reasoning for difficult queries, and validates response quality.

#### 3.1 chain_of_thought

| Attribute | Value |
|-----------|-------|
| **File** | `core/reasoning/chain_of_thought.py` |
| **Purpose** | Apply structured reasoning for complex queries |
| **Activation** | Health questions, product comparisons, 50+ word queries |

**Output Format:**
```
[RAZONAMIENTO]
1. Step one...
2. Step two...
3. Step three...

[RESPUESTA]
Final answer to user...
```

**Reasoning Types:**
| Type | Trigger |
|------|---------|
| `health` | Health-related questions |
| `product` | Product comparison or detailed product queries |
| `general` | Any query over 50 words |

---

#### 3.2 prompt_builder

| Attribute | Value |
|-----------|-------|
| **File** | `core/prompt_builder.py` |
| **Purpose** | Assemble the complete system prompt from all context sources |
| **Output Size** | 5,000 - 15,000 characters |

**8 Prompt Sections (in order):**

| # | Section | Content |
|---|---------|---------|
| 1 | IDENTITY | Creator name, role, personality, tone |
| 2 | ALERTS | Context detector alerts (frustration, B2B, etc.) |
| 3 | SPECIAL CONTEXT | Conversation state phase instructions |
| 4 | DATA | RAG results, product info, knowledge base |
| 5 | USER CONTEXT | Follower memory, relationship DNA, facts |
| 6 | RULES | Anti-hallucination rules, behavioral constraints |
| 7 | ACTIONS | Available actions (send link, escalate, etc.) |
| 8 | CONVERSION | Sales conversion micro-instructions |

**Anti-Hallucination Rules:**
- NEVER invent prices
- NEVER invent products
- NEVER invent links/URLs
- NEVER invent testimonials
- If unsure, say "let me check" or defer to creator

**Conversion Instructions:**
1. Answer the question
2. Add a relevant benefit
3. Invite the next step

---

#### 3.3 reflexion_engine

| Attribute | Value |
|-----------|-------|
| **File** | `core/reflexion_engine.py` |
| **Purpose** | Post-generation quality check (regex-based, NOT LLM-based) |
| **Behavior** | Logs issues for monitoring; does NOT re-generate responses |

**5 Quality Checks:**

| # | Check | Criteria | Severity |
|---|-------|----------|----------|
| 1 | Length | 20-300 characters | `medium` if outside range |
| 2 | Unanswered questions | Question in user msg not addressed | `high` |
| 3 | Repetition | > 60% overlap with recent responses | `high` |
| 4 | Phase appropriateness | Response matches conversation phase | `low` |
| 5 | Price inclusion | Price mentioned when not asked | `medium` |

**Severity Levels:** `none`, `low`, `medium`, `high`

---

#### 3.4 advanced_prompts

| Attribute | Value |
|-----------|-------|
| **Implemented via** | `build_rules_section()` in prompt_builder |
| **Feature Flag** | `ENABLE_ADVANCED_PROMPTS` (default: false, Railway: true) |

**Injected Sections:**
- Anti-hallucination rules block (detailed prohibitions)
- B2B section (professional tone, formal language)
- Frustration section (severity-based response instructions)

---

### Layer 4: Memory (Hippocampus)

Persistent memory for conversations, facts, and relationship evolution. Dual storage in JSON files and PostgreSQL.

#### 4.1 memory_store

| Attribute | Value |
|-----------|-------|
| **File** | `services/memory_service.py` |
| **Purpose** | Store and retrieve per-follower memory |
| **Storage** | JSON + PostgreSQL dual storage |

**25 Fields Per Follower:**
Includes: interests, objections, score, status, name, location, language, products_discussed, links_shared, prices_given, last_contact_at, message_count, and more.

**Message History:** Last 20 messages kept per follower (FIFO).

---

#### 4.2 fact_tracking

| Attribute | Value |
|-----------|-------|
| **Implemented in** | `dm_agent_v2.py` |
| **Purpose** | Track specific facts shared in assistant messages |
| **Detection** | Regex patterns in assistant output |

**Fact Types:**

| Type | Detection Pattern |
|------|------------------|
| `PRICE_GIVEN` | Currency symbols, EUR amounts in response |
| `LINK_SHARED` | URLs in response |

**Storage:** `follower.last_messages[-1]["facts"]`

---

#### 4.3 conversation_memory

| Attribute | Value |
|-----------|-------|
| **File** | `models/conversation_memory.py` |
| **Purpose** | Structured memory to prevent repetition |
| **Repetition Rule** | 6-day cooldown before re-sharing same fact |

**9 Fact Types Tracked:**
Prices given, links shared, products discussed, objections raised, questions asked, actions taken, commitments made, personal details, and preferences.

---

#### 4.4 dna_update_triggers

| Attribute | Value |
|-----------|-------|
| **File** | `services/dna_update_triggers.py` |
| **Purpose** | Schedule RelationshipDNA re-analysis based on conversation activity |
| **Execution** | Background thread (non-blocking) |

**Trigger Thresholds:**

| Trigger | Threshold |
|---------|-----------|
| First analysis | >= 5 messages |
| New message trigger | 10 new messages since last analysis |
| Cooldown | 24 hours between analyses |
| Stale data | 30 days since last analysis -> force re-analysis |

---

### Layer 5: Personalization (DNA)

The identity layer. Makes responses feel like they come from the real creator, not a generic bot.

#### 5.1 relationship_analyzer

| Attribute | Value |
|-----------|-------|
| **File** | `services/relationship_analyzer.py` |
| **Purpose** | Generate RelationshipDNA profile for a creator-follower pair |
| **Output** | RelationshipDNA object |

**RelationshipDNA Fields:**
- `vocabulary_uses`: Words/phrases to use
- `vocabulary_avoids`: Words/phrases to avoid
- `emojis`: Emoji set appropriate for relationship
- `tone`: Communication tone
- `trust_score`: Trust level (0.0 - 1.0)
- `depth_level`: Conversation depth (0-4)

**Trust Scores by Relationship Type:**

| Type | Trust Score |
|------|-------------|
| INTIMA | 0.9 |
| AMISTAD_CERCANA | 0.75 |
| AMISTAD_CASUAL | 0.5 |
| CLIENTE | 0.3 |
| COLABORADOR | 0.5 |
| DESCONOCIDO | 0.1 |

**Depth Levels:**

| Level | Message Count |
|-------|--------------|
| 0 | < 10 messages |
| 1 | 10-25 messages |
| 2 | 25-50 messages |
| 3 | 50-100 messages |
| 4 | 100+ messages |

---

#### 5.2 writing_patterns

| Attribute | Value |
|-----------|-------|
| **File** | `models/writing_patterns.py` |
| **Purpose** | Statistical model of creator's writing style |
| **Training Data** | Stefan's 3,056 real messages |

**Stefan's Writing Statistics:**

| Metric | Value |
|--------|-------|
| Messages analyzed | 3,056 |
| Mean length | 37.6 chars |
| Median length | 22 chars |
| Starts uppercase | 86.6% |
| Ends with `!` | 15.4% |
| Ends with `.` | 1.1% |
| Uses emojis | 22.4% |
| Uses laughs ("jaja") | 6.7% |
| Top emojis | (smiling)(heart)(prayer hands) |

**Abbreviations Detected:**

| Abbreviation | Expansion | Frequency |
|--------------|-----------|-----------|
| q | que | 89x |
| xq | porque | 1x |

---

#### 5.3 creator_style_loader

| Attribute | Value |
|-----------|-------|
| **File** | `services/creator_style_loader.py` |
| **Purpose** | Combine all style sources into a single style prompt |
| **Injected as** | `style_prompt` in dm_agent_v2 initialization |

**Combined Sources:**
1. `WritingPatterns` (statistical style model)
2. `CreatorDMStyle` (manual style configuration)
3. `ToneProfile` (tone characteristics)

---

#### 5.4 tone_service

| Attribute | Value |
|-----------|-------|
| **File** | `core/tone_service.py` |
| **Purpose** | Manage ToneProfile CRUD and persistence |
| **Storage** | PostgreSQL (primary) + JSON (backup) |

**ToneProfile Fields:**

| Field | Description | Example |
|-------|-------------|---------|
| `dialect` | Regional Spanish variant | "espanol neutro" |
| `formality` | Formal/informal scale | "informal" |
| `energy` | Energy level | "high" |
| `humor` | Humor style | "playful" |
| `emojis` | Emoji usage frequency | "moderate" |
| `signature_phrases` | Characteristic phrases | ["vamos!", "genial"] |
| `topics_to_avoid` | Off-limits topics | ["politica", "religion"] |

---

### Layer 6: Response (Output)

The final shaping layer. Controls response style, length, formatting, and safety before delivery.

#### 6.1 response_variator_v2

| Attribute | Value |
|-----------|-------|
| **File** | `services/response_variator_v2.py` |
| **Purpose** | Match common message types to pre-built response pools |
| **Performance** | Pool confidence >= 0.8 skips LLM entirely (90%+ faster) |

**Key Characteristics:**
- 12 response categories with weighted random selection
- Based on Stefan's 3,056 real messages
- Categories include: greetings, confirmations, thanks, goodbyes, affirmations, etc.

---

#### 6.2 edge_case_handler

| Attribute | Value |
|-----------|-------|
| **File** | `services/edge_case_handler.py` |
| **Purpose** | Handle unusual or difficult message types |
| **Status** | Initialized but NOT automatically called in main pipeline |

**7 Edge Case Types:**

| Type | Strategy |
|------|----------|
| `AGGRESSIVE` | Escalate to human |
| `COMPLAINTS` | Empathy-first response |
| `PERSONAL_QUESTIONS` | Deflect gracefully |
| `OFF_TOPIC` | Deflect back to relevant topics |
| `SARCASM` | Playful acknowledgment |
| `IRONY` | LLM-generated contextual response |
| `UNKNOWN` | 30% chance of "no se" honest response |

---

#### 6.3 length_controller

| Attribute | Value |
|-----------|-------|
| **File** | `services/length_controller.py` |
| **Purpose** | Enforce creator-specific message length targets |
| **Basis** | Stefan's real message length distribution |

**Stefan's Length Targets:**

| Message Type | Target Length (chars) |
|--------------|---------------------|
| `greeting` | 12 |
| `confirmation` | 15 |
| `normal` | 28 |
| `emotional` | 50 |

8 message types with specific limits. Short replacement pools for common response types.

---

#### 6.4 message_splitter

| Attribute | Value |
|-----------|-------|
| **File** | `services/message_splitter.py` |
| **Purpose** | Split long responses into multiple messages for natural feel |
| **Status** | NOT integrated into dm_agent_v2 pipeline yet |

**Split Configuration:**

| Parameter | Value |
|-----------|-------|
| Split threshold | >= 80 characters |
| Max parts | 4 |
| Split priority | Paragraphs -> Newlines -> Sentences -> Commas |
| Typing delay | `len(text) / 50.0 * random(0.8, 1.2)` seconds |

---

#### 6.5 guardrails

| Attribute | Value |
|-----------|-------|
| **File** | `core/guardrails.py` |
| **Purpose** | Final safety and quality validation |
| **Output** | `{valid, reason, issues, corrected_response}` |

**5 Guardrail Checks:**

| # | Check | Threshold / Rule |
|---|-------|-----------------|
| 1 | Price validation | +/- 1 EUR tolerance |
| 2 | URL validation | 12+ allowed domains whitelist |
| 3 | Hallucination patterns | Known hallucination regex |
| 4 | Off-topic detection | bitcoin, politica, religion blocked |
| 5 | Length limit | 2000 chars maximum |

---

### Layer 7: Data Infrastructure

RAG (Retrieval Augmented Generation) pipeline and supporting services for knowledge retrieval.

#### 7.1 RAG Service

| Attribute | Value |
|-----------|-------|
| **File** | `core/rag/semantic.py` |
| **Purpose** | Semantic search over creator's knowledge base |
| **Embedding Model** | OpenAI `text-embedding-3-small` |
| **Vector DB** | pgvector (1536-dimensional embeddings) |

**Search Modes:**
- **Primary:** Semantic search (cosine similarity)
- **Optional:** BM25 hybrid search with Reciprocal Rank Fusion
- **Optional:** Cross-encoder reranking for precision

---

#### 7.2 citation_service

| Attribute | Value |
|-----------|-------|
| **File** | `core/citation_service.py` |
| **Purpose** | Inject natural content references into responses |
| **Min Relevance** | 0.6 for injection |

**6 Content Types:**

| Type | Natural Reference Style |
|------|------------------------|
| `instagram_post` | "en un post que hice..." |
| `reel` | "en un reel que subi..." |
| `youtube` | "en mi video de YouTube..." |
| `podcast` | "en mi podcast..." |
| `pdf` | "en mi guia..." |
| `faq` | "como menciono en las preguntas frecuentes..." |

---

#### 7.3 semantic_chunker

| Attribute | Value |
|-----------|-------|
| **File** | `core/semantic_chunker.py` |
| **Purpose** | Split documents into semantically meaningful chunks for embedding |

**Chunking Configuration:**

| Parameter | Value |
|-----------|-------|
| Chunk size | 100 - 800 characters |
| Overlap | 1 sentence |
| Respects | Headers (##, ###), paragraphs, sentences |
| HTML support | Via BeautifulSoup |

---

### Layer 8: Analytics (Intelligence)

Business intelligence layer for creator dashboards and strategic recommendations.

#### 8.1 insights_engine

| Attribute | Value |
|-----------|-------|
| **File** | `core/insights_engine.py` |
| **Purpose** | Generate daily and weekly intelligence reports |

**Report Types:**

| Report | Contents |
|--------|----------|
| **TODAY MISSION** | Urgent actions, hot leads, objections to handle |
| **WEEKLY INSIGHTS** | Conversion rate, top objections, audience growth |

7-day comparison with delta percentages for trend analysis.

---

#### 8.2 audience_aggregator

| Attribute | Value |
|-----------|-------|
| **File** | `core/audience_aggregator.py` |
| **Purpose** | Aggregate audience intelligence across all conversations |

**8 Analysis Tabs:**

| # | Tab | Description |
|---|-----|-------------|
| 1 | Topics | What followers talk about |
| 2 | Passions | What followers are passionate about |
| 3 | Frustrations | What followers struggle with |
| 4 | Competition | Competitors mentioned by followers |
| 5 | Trends | Emerging topics and patterns |
| 6 | Content Requests | What followers want to see |
| 7 | Purchase Objections | Why followers don't buy |
| 8 | Perception | How followers perceive the creator |

10+ objection type mappings with suggested responses.

---

#### 8.3 intelligence_engine

| Attribute | Value |
|-----------|-------|
| **Exposed via** | `api/routers/intelligence.py` |
| **Purpose** | Predictive analytics and strategic recommendations |

**Predictions:**
- Conversion probability
- Churn risk
- Revenue forecast
- Engagement score
- Best contact time

**Recommendations:**
- Content suggestions
- Action items
- Product development
- Pricing adjustments
- Timing optimization

**Weekly Reports:** LLM-generated comprehensive insights with data-backed analysis.

---

### Layer 9: Lifecycle (Nurturing)

Proactive engagement layer for re-activating ghosts, nurturing leads, and escalating to humans.

#### 9.1 ghost_reactivation

| Attribute | Value |
|-----------|-------|
| **File** | `core/ghost_reactivation.py` |
| **Purpose** | Re-engage inactive followers |

**Configuration:**

| Parameter | Value |
|-----------|-------|
| Trigger | 7 - 90 days inactive |
| Cooldown | 30 days between attempts |
| Max per cycle | 5 followers |
| Message templates | 3 randomized reactivation messages |

---

#### 9.2 nurturing_service

| Attribute | Value |
|-----------|-------|
| **File** | `core/nurturing.py` |
| **Purpose** | Automated drip sequences based on lead status and intent |

**12 Sequence Types:**

| # | Sequence | Trigger |
|---|----------|---------|
| 1 | `INTEREST_COLD` | Soft interest, no follow-up |
| 2 | `OBJECTION_PRICE` | Price objection raised |
| 3 | `ABANDONED` | Started conversation, stopped |
| 4 | `RE_ENGAGEMENT` | Was active, went quiet |
| 5 | `POST_PURCHASE` | After completed purchase |
| 6-12 | Additional sequences | Various intent-to-sequence mappings |

**Personalization:** Via Reflexion AI for message customization.

**Scheduler:**
- Light operations: every 5 minutes
- Heavy operations: every 30 minutes

---

#### 9.3 escalation_service

| Attribute | Value |
|-----------|-------|
| **Implemented in** | `dm_agent_v2.py` |
| **Purpose** | Escalate conversations to human creator when needed |
| **Execution** | Non-blocking async |

**Escalation Triggers:**

| Trigger | Condition |
|---------|-----------|
| `ESCALATION` intent | User explicitly asks for human |
| `SUPPORT` intent | Technical support needed |
| `FEEDBACK_NEGATIVE` intent | Complaint or negative feedback |
| Hot lead | Score >= 0.8 + `INTEREST_STRONG` intent |

**Output:** `EscalationNotification` with conversation summary sent to creator.

---

### Layer 10: Integration (External)

External service integrations for message delivery, media handling, and platform APIs.

#### 10.1 instagram_handler

| Attribute | Value |
|-----------|-------|
| **Files** | `core/instagram_handler.py` + routers |
| **API** | Meta Graph API v21.0 |

**Rate Limits:**

| Window | Limit |
|--------|-------|
| Per minute | 15 requests |
| Per hour | 190 requests |
| Per day | 4,500 requests |

**Backoff:** Exponential, 5s initial -> 300s maximum.

**Features:**
- Multi-creator routing via `instagram_additional_ids` JSONB column
- Ice breakers (conversation starters)
- Persistent menu
- Story reply handling

---

#### 10.2 telegram

| Attribute | Value |
|-----------|-------|
| **File** | `core/telegram_adapter.py` |
| **Purpose** | Telegram bot integration |

**Features:**
- Multi-bot registry
- Direct + proxy (Cloudflare Workers) fallback delivery
- Deduplication cache (60s TTL)
- HTML `parse_mode` + inline keyboards

---

#### 10.3 media_capture

| Attribute | Value |
|-----------|-------|
| **File** | `services/media_capture_service.py` |
| **Purpose** | Capture and persist ephemeral media (especially Instagram Stories) |

**Pipeline:**
1. CDN URL detection (5 patterns)
2. **Primary:** Cloudinary upload -> permanent URL
3. **Fallback:** base64 data URI (5MB max)
4. Story thumbnail capture before 24h expiration

---

#### 10.4 cloudinary

| Attribute | Value |
|-----------|-------|
| **File** | `services/cloudinary_service.py` |
| **Purpose** | Cloud media storage and transformation |

**Configuration:**
- Upload from URL or file
- Folder structure: `clonnect/{creator_id}/{date}`
- Supported types: image, video, audio, raw

---

## 3. Complete Message Flow

```
WEBHOOK ARRIVES (Instagram/Telegram)
    |
    v
[L10] ROUTING: extract_all_instagram_ids() -> find_creator_for_webhook()
    |
    v
[PRE-PIPELINE] SENSITIVE DETECTION (if >=0.85 -> return crisis resources)
    |
    v
[L2] PHASE 1: DETECTION
    |-- Frustration detection -> level (0.0-1.0)
    |-- Context detection -> alerts, B2B, sarcasm, interest
    '-- Pool response check -> if matched >=0.8 -> RETURN (skip LLM)
    |
    v
[L2] PHASE 2: CONTEXT & MEMORY
    |-- Intent classification -> 18+ intents
    |-- Bot question analysis (if short affirmation)
    |-- Get/create follower memory
    |-- Conversation state -> phase + instructions
    '-- Relationship detection -> type + confidence
    |
    v
[L7] PHASE 3: RAG RETRIEVAL
    |-- Query expansion (synonyms)
    |-- RAG retrieve (semantic search)
    |-- Reranking (if enabled)
    |-- DNA context loading
    |-- Lead stage determination
    '-- Prompt building (style + RAG + DNA + state + advanced + override)
    |
    v
[L3] PHASE 4: LLM GENERATION
    |-- Frustration context injection (if >0.5)
    |-- Chain of thought (if complex query)
    '-- LLM.generate(full_prompt, system_prompt)
    |
    v
[L1+L6] PHASE 5: POST-PROCESSING
    |-- Output validation (prices, links)
    |-- Response fixes (6 fixes)
    |-- Reflexion analysis (5 checks)
    |-- Guardrails validation
    |-- Length control (type-based limits)
    '-- Instagram formatting
    |
    v
[L4] PHASE 6: MEMORY UPDATE
    |-- Update follower messages (keep last 20)
    |-- Fact tracking (PRICE_GIVEN, LINK_SHARED)
    |-- DNA trigger check (schedule if needed)
    |-- Lead score update
    '-- Escalation check (if warranted)
    |
    v
RESPONSE SENT
```

---

## 4. Feature Flags Matrix

All 17 cognitive feature flags. Flags 13, 15, and 17 are disabled by default but explicitly enabled in Railway production environment.

| # | Flag | Default | Railway | Layer | Purpose |
|---|------|---------|---------|-------|---------|
| 1 | `ENABLE_SENSITIVE_DETECTION` | true | true | Security | Crisis and abuse detection |
| 2 | `ENABLE_OUTPUT_VALIDATION` | true | true | Security | Price and link validation |
| 3 | `ENABLE_RESPONSE_FIXES` | true | true | Security | Technical output fixes |
| 4 | `ENABLE_FRUSTRATION_DETECTION` | true | true | Context | Frustration level measurement |
| 5 | `ENABLE_CONTEXT_DETECTION` | true | true | Context | B2B, intent, interest detection |
| 6 | `ENABLE_CONVERSATION_MEMORY` | true | true | Memory | Fact persistence and repetition prevention |
| 7 | `ENABLE_GUARDRAILS` | true | true | Response | Anti-hallucination and safety |
| 8 | `ENABLE_CHAIN_OF_THOUGHT` | true | true | Reasoning | Complex query structured reasoning |
| 9 | `ENABLE_QUESTION_CONTEXT` | true | true | Context | Short affirmation analysis |
| 10 | `ENABLE_QUERY_EXPANSION` | true | true | Context | Synonym expansion for RAG |
| 11 | `ENABLE_REFLEXION` | true | true | Reasoning | Response quality monitoring |
| 12 | `ENABLE_LEAD_CATEGORIZER` | true | true | Context | 5-tier lead funnel classification |
| 13 | `ENABLE_CONVERSATION_STATE` | **false** | **true** | Context | Sales phase tracking |
| 14 | `ENABLE_FACT_TRACKING` | true | true | Memory | Price and link fact tracking |
| 15 | `ENABLE_ADVANCED_PROMPTS` | **false** | **true** | Reasoning | Anti-hallucination rules injection |
| 16 | `ENABLE_DNA_TRIGGERS` | true | true | Memory | Auto RelationshipDNA re-analysis |
| 17 | `ENABLE_RELATIONSHIP_DETECTION` | **false** | **true** | DNA | Relationship type classification |

---

## 5. Key Thresholds & Constants

### Security Thresholds

| Constant | Value | Module | Description |
|----------|-------|--------|-------------|
| Sensitive warning log | >= 0.7 | sensitive_detector | Log warning to monitoring |
| Sensitive crisis return | >= 0.85 | sensitive_detector | Return crisis resources, bypass pipeline |
| Price tolerance | +/- 1 EUR | output_validator | Acceptable price deviation |
| Smart truncate limit | 400 chars | output_validator | Max response length before truncation |
| Max response length | 2000 chars | guardrails | Absolute maximum response size |

### Context Thresholds

| Constant | Value | Module | Description |
|----------|-------|--------|-------------|
| Quick classify confidence | >= 0.85 | intent_classifier | Skip LLM for intent |
| Frustration empathy injection | > 0.5 | frustration_detector | Add empathy to prompt |
| CAPS frustration signal | > 30% | frustration_detector | Detect frustration from caps |
| Repeated question overlap | 40% | frustration_detector | Detect repeated questions |
| Pool response confidence | >= 0.8 | response_variator_v2 | Skip LLM entirely |
| Ghost inactivity | 7 days | lead_categorizer | Mark as ghost |
| Citation min relevance | 0.6 | citation_service | Min score for citation injection |

### Memory & DNA Thresholds

| Constant | Value | Module | Description |
|----------|-------|--------|-------------|
| Message history limit | 20 messages | memory_service | FIFO per follower |
| Fact repetition cooldown | 6 days | conversation_memory | Days before re-sharing same fact |
| DNA first analysis | >= 5 messages | dna_update_triggers | Minimum messages for first DNA |
| DNA new message trigger | 10 messages | dna_update_triggers | New messages to trigger re-analysis |
| DNA cooldown | 24 hours | dna_update_triggers | Min time between analyses |
| DNA stale threshold | 30 days | dna_update_triggers | Force re-analysis after this |
| Max confidence | 0.95 | relationship_type_detector | Cap on relationship confidence |

### Response Thresholds

| Constant | Value | Module | Description |
|----------|-------|--------|-------------|
| Reflexion min length | 20 chars | reflexion_engine | Minimum acceptable response |
| Reflexion max length | 300 chars | reflexion_engine | Maximum preferred response |
| Repetition overlap | > 60% | reflexion_engine | Flag as repetitive |
| Message split threshold | >= 80 chars | message_splitter | When to split into parts |
| Message max parts | 4 | message_splitter | Maximum message splits |
| CoT word threshold | 50 words | chain_of_thought | Activate chain of thought |

### Lifecycle Thresholds

| Constant | Value | Module | Description |
|----------|-------|--------|-------------|
| Ghost min inactivity | 7 days | ghost_reactivation | Minimum days before reactivation |
| Ghost max inactivity | 90 days | ghost_reactivation | Maximum days (too old to reactivate) |
| Ghost cooldown | 30 days | ghost_reactivation | Between reactivation attempts |
| Ghost max per cycle | 5 | ghost_reactivation | Max followers per cycle |
| Escalation score | >= 0.8 | dm_agent_v2 | Lead score for auto-escalation |
| Nurturing light interval | 5 min | nurturing_service | Scheduler for light operations |
| Nurturing heavy interval | 30 min | nurturing_service | Scheduler for heavy operations |

### Integration Rate Limits

| Constant | Value | Module | Description |
|----------|-------|--------|-------------|
| Instagram per minute | 15 | instagram_handler | API rate limit |
| Instagram per hour | 190 | instagram_handler | API rate limit |
| Instagram per day | 4,500 | instagram_handler | API rate limit |
| Backoff initial | 5s | instagram_handler | Exponential backoff start |
| Backoff maximum | 300s | instagram_handler | Exponential backoff cap |
| Telegram dedup TTL | 60s | telegram_adapter | Message deduplication window |
| Media fallback max | 5 MB | media_capture_service | Base64 fallback size limit |

---

## 6. Known Limitations & Technical Debt

### Critical (P0)

| Issue | Impact | Mitigation |
|-------|--------|------------|
| Cache not shared across Railway workers | Cache misses on different workers, inconsistent response times | Need Redis for shared cache |
| JSON file persistence | Single-point-of-failure for follower memory, tone profiles | PostgreSQL is primary, JSON is backup but still used |

### High (P1)

| Issue | Impact | Mitigation |
|-------|--------|------------|
| `admin.py` is 5,717 lines | Maintenance nightmare, merge conflicts | Needs split into multiple router files |
| `message_splitter` not integrated | Long responses sent as single message (unnatural) | Module exists, needs pipeline integration |
| `edge_case_handler` not automatically called | Aggressive/sarcasm messages use generic handling | Module initialized but not in main pipeline |

### Medium (P2)

| Issue | Impact | Mitigation |
|-------|--------|------------|
| Writing patterns only for Stefan | Other creators get generic style | Need per-creator pattern training |
| Reflexion is regex-based, not LLM-based | Limited quality detection capability | Sufficient for current scale |
| Duplicate 008 migrations | Potential migration conflicts | Needs cleanup |
| 2 modules missing implementation | `question_remover`, `vocabulary_extractor` referenced but not built | Low priority features |

### Low (P3)

| Issue | Impact | Mitigation |
|-------|--------|------------|
| Multi-worker cache limitation | Partial cache benefit only | Acceptable with current traffic |
| Affirmation words Spanish-only | Non-Spanish speakers may not be matched | Current user base is Spanish-speaking |

---

## 7. File Index

### Layer 1: Security (Guardian)
| File | Module |
|------|--------|
| `core/sensitive_detector.py` | Sensitive content detection |
| `core/output_validator.py` | Output validation (prices, links) |
| `core/response_fixes.py` | Deterministic response fixes |

### Layer 2: Context (Compass)
| File | Module |
|------|--------|
| `core/intent_classifier.py` | Intent classification (rules) |
| `services/intent_service.py` | Intent classification (LLM) |
| `core/frustration_detector.py` | Frustration detection |
| `core/context_detector.py` | Multi-dimensional context detection |
| `core/bot_question_analyzer.py` | Bot question analysis |
| `core/query_expansion.py` | Query synonym expansion |
| `core/lead_categorizer.py` | Lead category assignment |
| `core/conversation_state.py` | Conversation phase tracking |
| `services/relationship_type_detector.py` | Relationship type classification |

### Layer 3: Reasoning (Cortex)
| File | Module |
|------|--------|
| `core/reasoning/chain_of_thought.py` | Chain of thought reasoning |
| `core/prompt_builder.py` | System prompt assembly |
| `core/reflexion_engine.py` | Response quality checking |

### Layer 4: Memory (Hippocampus)
| File | Module |
|------|--------|
| `services/memory_service.py` | Follower memory store |
| `models/conversation_memory.py` | Structured conversation memory |
| `services/dna_update_triggers.py` | DNA re-analysis triggers |

### Layer 5: Personalization (DNA)
| File | Module |
|------|--------|
| `services/relationship_analyzer.py` | RelationshipDNA generation |
| `models/writing_patterns.py` | Creator writing statistics |
| `services/creator_style_loader.py` | Style prompt assembly |
| `core/tone_service.py` | ToneProfile management |

### Layer 6: Response (Output)
| File | Module |
|------|--------|
| `services/response_variator_v2.py` | Pool-based response matching |
| `services/edge_case_handler.py` | Edge case handling (not integrated) |
| `services/length_controller.py` | Response length enforcement |
| `services/message_splitter.py` | Message splitting (not integrated) |
| `core/guardrails.py` | Final safety validation |

### Layer 7: Data Infrastructure
| File | Module |
|------|--------|
| `core/rag/semantic.py` | RAG semantic search |
| `core/citation_service.py` | Natural content citations |
| `core/semantic_chunker.py` | Document chunking |

### Layer 8: Analytics (Intelligence)
| File | Module |
|------|--------|
| `core/insights_engine.py` | Daily/weekly intelligence |
| `core/audience_aggregator.py` | Audience intelligence |
| `api/routers/intelligence.py` | Predictive analytics API |

### Layer 9: Lifecycle (Nurturing)
| File | Module |
|------|--------|
| `core/ghost_reactivation.py` | Ghost follower reactivation |
| `core/nurturing.py` | Drip sequence nurturing |

### Layer 10: Integration (External)
| File | Module |
|------|--------|
| `core/instagram_handler.py` | Instagram Graph API integration |
| `core/telegram_adapter.py` | Telegram bot integration |
| `services/media_capture_service.py` | Ephemeral media capture |
| `services/cloudinary_service.py` | Cloud media storage |

### Orchestrator
| File | Module |
|------|--------|
| `core/dm_agent_v2.py` | Main pipeline orchestrator (~1,433 lines) |

### Supporting Infrastructure
| File | Module |
|------|--------|
| `api/cache.py` | In-memory query cache |
| `api/startup.py` | Cache warming and refresh |
| `api/models.py` | SQLAlchemy models |
| `core/webhook_routing.py` | Multi-creator webhook routing |
| `services/prompt_service.py` | Prompt generation service |
| `services/db_service.py` | Database service layer |

---

*Document generated: 2026-02-07*
*Audit scope: Complete cognitive engine inventory across all 10 processing layers*
