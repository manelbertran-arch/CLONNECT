# AUDIT PART 2: DM Agent Detection + Context Building

**Date**: 2026-03-19
**Scope**: Systems 8-25 (Detection, Context, Memory, RAG, Prompt Assembly)
**Method**: Line-by-line code reading with 6 parallel analysis agents
**Status**: ANALYSIS ONLY — no code changes

---

## EXECUTIVE SUMMARY

| # | System | Status | Severity |
|---|--------|--------|----------|
| 8 | Sensitive Content Detector | WORKING BUT INCOMPLETE | MEDIUM |
| 9 | Frustration Analyzer | WORKING | LOW |
| 10 | Pool Response Matching | WORKING | LOW |
| 11 | Intent Classifier | WORKING | LOW |
| 12 | MemoryStore JSON | PARTIALLY WORKING | MEDIUM |
| 13 | DB Fallback | FULLY WORKING | NONE |
| 14 | Relationship DNA | WORKING | NONE |
| 15 | Conversation State | PARTIALLY WORKING | **CRITICAL** |
| 16 | Memory Engine | PARTIALLY WORKING | **HIGH** |
| 17 | Semantic RAG | BROKEN (INGESTION) | **HIGH** |
| 18 | Friend/Family Detection | WORKING | LOW |
| 19 | Audio Context Extraction | PARTIALLY WORKING | **HIGH** |
| 20 | Echo Relationship Adapter | WORKING | NONE |
| 21 | Calibration Loader | PARTIALLY WORKING | MEDIUM |
| 22 | Personality Loader / Doc D | WORKING | LOW |
| 23 | Knowledge Base | WORKING | NONE |
| 24 | Citation Service | WORKING | NONE |
| 25 | Prompt Builder | WORKING | NONE |

**Critical bugs found**: 3
1. Conversation State never updated (state machine is dead)
2. Memory Engine disabled by default + output truncated to 182 chars
3. RAG has only 24 content chunks (ingestion pipeline not active)

---

## SYSTEM 8: SENSITIVE CONTENT DETECTOR

**File**: `core/sensitive_detector.py` (360 lines)
**Verdict**: WORKING BUT INCOMPLETE

### Pattern Categories

| Category | Confidence | Pattern Count | Example Trigger |
|----------|-----------|---------------|-----------------|
| SELF_HARM | 0.95 | ~20 patterns | "quiero morir", "me corto", "suicidarme" |
| EATING_DISORDER | 0.80 | ~14 patterns | "como solo 300 calorias", "me provoco vomito" |
| MINOR | 0.95 | ~5 patterns | "tengo 15 anos", "soy menor" |
| PHISHING | 0.90 | ~9 patterns | "dame su email", "datos personales del creador" |
| SPAM | 0.90 | ~12 patterns | "check my profile", "ganar $500 al dia" |
| THREAT | 0.85 | ~6 patterns | "se donde vive", "te voy a encontrar" |
| ECONOMIC_DISTRESS | 0.75 | ~5 patterns | "estoy en el paro", "sin dinero" |

### Escalation Logic (detection.py:28-46)

```
confidence < 0.7  → ignored
0.7 <= conf < 0.85 → metadata tagged, LLM continues with awareness
conf >= 0.85      → IMMEDIATE RETURN with crisis resources (skips LLM)
```

Crisis resources include Spanish AND Catalan text (lines 295-324):
- Telefon de l'Esperanca: 717 003 717
- Telefon contra el Suicidi: 024

### CRITICAL GAP: No Catalan Keywords

All patterns are Spanish + English only. **Zero Catalan detection patterns.**

- "vull morir" (Catalan for "I want to die") → NOT CAUGHT
- "em tallo" (Catalan for "I cut myself") → NOT CAUGHT
- "es impossible" (Catalan "it's impossible") → NOT CAUGHT

The crisis response TEXT is available in Catalan, but the DETECTION that triggers it has no Catalan patterns.

### False Positive Risks

| Pattern | Risk | Example False Positive |
|---------|------|----------------------|
| PHISHING line 116: `dame...contacto` | MEDIUM | "Me pasas tu contacto?" (innocent) |
| THREAT line 147: `esto no va a quedar asi` | LOW | Innocent complaint about service |
| SELF_HARM: `me corto` | LOW | "me corto las unas" (I cut my nails) |

---

## SYSTEM 9: FRUSTRATION ANALYZER

**File**: `core/frustration_detector.py` (282 lines)
**Verdict**: WORKING

### Scoring Algorithm (lines 30-51)

```python
score = 0.0
score += min(repeated_questions * 0.2, 0.4)   # Max +0.4
score += min(negative_markers * 0.1, 0.3)     # Max +0.3
if caps_ratio > 0.3: score += 0.15            # Max +0.15
if explicit_frustration: score += 0.5          # Max +0.5
score += min(question_marks_excess * 0.05, 0.15) # Max +0.15
return min(score, 1.0)                         # Capped at 1.0
```

### Thresholds

| Threshold | Value | Action |
|-----------|-------|--------|
| Logging | > 0.3 | Sets `cognitive_metadata["frustration_level"]` |
| LLM injection | > 0.5 | Adds empathy instruction to prompt |
| Auto-escalation | NONE | Frustration never bypasses LLM (by design) |

### Explicit Frustration Patterns (lines 58-87)

Spanish: "no entiendes", "ya te dije", "esto no funciona", "dejalo", "inutil", "mierda", "joder", "estoy harto", "nadie me responde"
English: "you don't understand", "this doesn't work", "useless", "forget it"

### LLM Injection (generation.py:201-205)

When frustration > 0.5:
```
"NOTA: El usuario parece frustrado (nivel: 72%).
Responde con empatia y ofrece ayuda concreta."
```

**No Catalan patterns** (same gap as System 8).

---

## SYSTEM 10: POOL RESPONSE MATCHING

**Files**: `core/dm/phases/detection.py:76-132`, `services/response_variator_v2.py` (639 lines)
**Verdict**: WORKING

### Gate Conditions (detection.py:87-98)

A message gets a pool response only if ALL pass:
1. Length <= 80 characters
2. Does NOT mention a creator product (fuzzy name matching)
3. Category detected with confidence >= 0.8 (`AGENT_THRESHOLDS.pool_confidence`)

### Pool Categories (15 total)

| Category | Example Pool Responses | Trigger |
|----------|----------------------|---------|
| greeting | "Hola! :)", "Hey!", "Buenas!" | "Hola", "Hey" |
| confirmation | "Dale!", "Ok!", "Perfecto!", ":+1:" | "Ok", "Si", "Dale" |
| thanks | "Gracias!", "A ti!", "De nada!" | "Gracias", "Merci" |
| laugh | "Jaja", "Jajaja", ":joy:" | "Jaja", "Jeje" |
| emoji | ":blush:", ":blue_heart:", ":+1:", ":fire:" | Single emoji messages |
| celebration | "Genial!", "Que bien!", "Increible!" | "Genial", "Wow" |
| farewell | "Un abrazo!", "Cuidate!", "Hablamos!" | "Adios", "Chao" |
| dry | "Ok", "Dale", "Si", "Va" | Ultra-short confirms |
| empathy | "Entiendo", "Te entiendo", "Animo!" | Emotional sharing |
| affection | "Yo a ti! :blue_heart:", "Y yo a ti!" | "Te quiero" |
| praise | "Gracias! :blush:", "Que lindo!" | Compliments |
| meeting_request | "Imposible bro, me explota la agenda jaja" | "Podemos quedar?" |
| humor | "Jajaja :joy:", "Me hiciste reir" | Jokes |
| encouragement | "Vamos con toda! :muscle:", "Crack!" | Motivational |
| conversational | "Dale!", "Totalmente!", "Tal cual!" | Short agreements |

### Context-Aware Selection (lines 302-367)

- 60% context similarity (TF-IDF) + 40% engagement score
- Engagement hooks: "cuentame", "dime", "como", "y tu", "verdad"
- Conversation-level dedup prevents repetition (v10.3)

### Does "Yes!" Get Intercepted?

**YES** — "Si!" (4 chars, no product mention) → confirmation category at 0.95 confidence → pool response "Dale!" or "Ok!"

This is **appropriate** for simple acknowledgments. The system correctly handles:
- "Si, me interesa el Fitpack" → product mention detected → goes to LLM
- "Si" alone → pool response (no context needed)

### Potential LLM Bypass Risk

Messages like "Si, me interesa" (16 chars, no explicit product name) could get pool response if context classification fails to detect sales intent. The `classify_lead_context()` function should catch "pregunta_precio" context, but edge cases exist.

### Multi-Bubble (detection.py:101-121)

30% random gate for multi-bubble responses. If triggered and matched, returns multi-bubble immediately. Intentional randomization for natural-feeling conversations.

---

## SYSTEM 11: INTENT CLASSIFIER

**File**: `services/intent_service.py` (483 lines)
**Verdict**: WORKING

### 31 Intent Values

**Social**: GREETING, GENERAL_CHAT, THANKS, GOODBYE
**Sales**: INTEREST_SOFT, INTEREST_STRONG, PURCHASE_INTENT, PRICING
**Objections** (8 types): OBJECTION_PRICE, OBJECTION_TIME, OBJECTION_DOUBT, OBJECTION_LATER, OBJECTION_WORKS, OBJECTION_NOT_FOR_ME, OBJECTION_COMPLICATED, OBJECTION_ALREADY_HAVE
**Questions**: QUESTION_PRODUCT, QUESTION_GENERAL, PRODUCT_QUESTION
**Action**: LEAD_MAGNET, BOOKING, SUPPORT, ESCALATION
**Feedback**: FEEDBACK_NEGATIVE
**v10.2 sub-categories**: HUMOR, REACTION, ENCOURAGEMENT, CONTINUATION, CASUAL
**Fallback**: OTHER

### Classification Model

**Keyword-based (NOT LLM)** — deterministic, consistent, zero-cost.

Priority order (lines 384-483):
1. Sales intents (purchase, pricing, product questions)
2. Social intents (greeting, thanks, goodbye)
3. Objections + interest + escalation + support
4. v10.2 sub-categories (humor, reaction, encouragement)
5. Fallback: has "?" → QUESTION_GENERAL, else → OTHER

### Accuracy: MEDIUM (60-75%)

- No context-awareness (binary keyword matching)
- No semantic understanding
- Spanish-heavy patterns, minimal English
- v10.2 enhancement reduced OTHER misclassification from ~57% to <20%

### Downstream Impact

Intent is used EVERYWHERE:
- **Learning rules**: Filtered by `applies_to_message_types` matching intent
- **Gold examples**: Filtered by `intent` column
- **Response strategy**: Intent maps to VENTA/PERSONAL/AYUDA/BIENVENIDA
- **Conversation state**: Intent triggers phase transitions
- **Email capture**: Skipped for escalation/support/sensitive/crisis intents
- **Response caching**: Objection intents marked non-cacheable

---

## SYSTEM 12: MEMORYSTORE JSON

**Files**: `core/memory.py` (deprecated), `services/memory_service.py` (active)
**Verdict**: PARTIALLY WORKING

### FollowerMemory Fields

| Field | Type | Purpose |
|-------|------|---------|
| follower_id | str | Platform user ID |
| creator_id | str | Creator slug |
| username, name | str | Display info |
| first_contact, last_contact | ISO str | Timestamps |
| total_messages | int | Message count |
| interests | List[str] | Inferred topics |
| products_discussed | List[str] | Product mentions |
| objections_raised | List[str] | Objections |
| purchase_intent_score | float | 0-1 score |
| engagement_score | float | 0-1 score |
| is_lead, is_customer | bool | Flags |
| needs_followup | bool | Follow-up flag |
| preferred_language | str | Default "es" |
| conversation_summary | str | Summary text |
| last_messages | List[Dict] | Last 20 messages |

### Storage: `data/followers/{creator_id}/{follower_id}.json`

- Local dev: 1131 JSON files across 10 creator folders
- **Railway: EPHEMERAL** — files lost on every deploy/restart

### Why Files Don't Exist on Railway

Railway uses ephemeral filesystem. The Dockerfile creates `data/followers/` at build time, but runtime-generated JSON files are lost on container restart. This is the fundamental reason the DB fallback was added.

### Dual Implementation

| Aspect | `core/memory.py` | `services/memory_service.py` |
|--------|-----------------|------------------------------|
| Status | DEPRECATED | ACTIVE (primary) |
| Fields | 16 core | 31 expanded |
| Used by | Legacy imports | Agent pipeline |

---

## SYSTEM 13: DB FALLBACK

**File**: `core/dm/helpers.py:79-131`
**Verdict**: FULLY WORKING

### Implementation (get_history_from_db)

```python
def get_history_from_db(creator_id, follower_id, limit=20):
    # 1. Resolve creator slug -> UUID
    creator = resolve_creator_safe(session, creator_id)
    # 2. Find lead by creator UUID + platform_user_id
    lead = session.query(Lead).filter(
        Lead.creator_id == creator.id,
        Lead.platform_user_id == follower_id
    ).first()
    # 3. Query messages with filters
    messages = session.query(Message.role, Message.content).filter(
        Message.lead_id == lead.id,
        Message.status != "discarded",     # Excludes rejected copilot suggestions
        Message.deleted_at.is_(None),      # Excludes soft-deleted
    ).order_by(Message.created_at.desc()).limit(limit).all()
    # 4. Reverse to chronological order
    return [{"role": m.role, "content": m.content}
            for m in reversed(messages) if m.content]
```

### Verification Checklist

- [x] Status filter: `!= "discarded"` (line 113) — CORRECT
- [x] Message limit: 20 (default, configurable)
- [x] Chronological order: DESC query + reversed() = ASC — CORRECT
- [x] Lead matching: creator UUID + platform_user_id — CORRECT
- [x] asyncio.to_thread: Applied in context.py:405-407 — CORRECT
- [x] Error handling: try/except, logs warning, returns [] — ROBUST
- [x] Session management: finally block closes session — CORRECT

### Integration Flow (context.py:398-412)

```
1. Try JSON files (agent._get_history_from_follower)
2. If empty → DB fallback (get_history_from_db via asyncio.to_thread)
3. Backfill metadata["history"] for downstream code
```

---

## SYSTEM 14: RELATIONSHIP DNA

**File**: `services/relationship_dna_repository.py`, model in `api/models/creator.py`
**Verdict**: WORKING

### Storage

Database table `relationship_dna` with columns:
- `relationship_type`: ENUM (FAMILIA, INTIMA, AMISTAD_CERCANA, AMISTAD_CASUAL, CLIENTE, COLABORADOR, DESCONOCIDO)
- `trust_score`: 0.0-1.0
- `depth_level`: 0-4
- `vocabulary_uses`, `vocabulary_avoids`: JSON arrays
- `emojis`: JSON array
- `tone_description`: Text
- `recurring_topics`, `private_references`: JSON arrays
- **`bot_instructions`**: TEXT — injected directly into LLM prompt
- `golden_examples`: JSON array

### Creation

- **Auto**: Seeded in context.py:146-172 when lead has >= 2 messages and no existing DNA
- **Manual**: Via `relationship_dna_repository.create_relationship_dna()`

### Prompt Injection

`bot_instructions` extracted at context.py:130-135 and included in `combined_context`. Relationship type also affects strategy (FAMILIA/INTIMA → no selling).

---

## SYSTEM 15: CONVERSATION STATE

**File**: `core/conversation_state.py` (463 lines)
**Verdict**: PARTIALLY WORKING — **CRITICAL BUG**

### 7 Phases (Sales Funnel)

| Phase | Purpose | Instruction |
|-------|---------|-------------|
| INICIO | Greet, spark curiosity | No products, max 2 sentences |
| CUALIFICACION | Understand what user seeks | 1 question, no products |
| DESCUBRIMIENTO | Understand situation/obstacles | Explore constraints |
| PROPUESTA | Present adapted product | Include pricing |
| OBJECIONES | Address concerns | Empathy + social proof |
| CIERRE | Facilitate purchase | Give link, offer support |
| ESCALAR | Transfer to human | Notify creator |

### Transition Triggers

| From | To | Trigger |
|------|-----|---------|
| INICIO | CUALIFICACION | message_count >= 1 |
| CUALIFICACION | DESCUBRIMIENTO | goal extracted OR message_count >= 3 |
| DESCUBRIMIENTO | PROPUESTA | situation/constraints extracted OR message_count >= 4 |
| PROPUESTA | OBJECIONES | "objection" in intent |
| PROPUESTA | CIERRE | "interest_strong" OR purchase keywords |
| OBJECIONES | CIERRE | "interest_strong" OR agreement keywords |
| ANY | ESCALAR | "escalation" intent OR "hablar con humano" |

### Persistence

- DB table: `conversation_states` (migration 005)
- Unique constraint: (creator_id, follower_id)
- JSON context column stores accumulated user facts
- Feature flag: `PERSIST_CONVERSATION_STATE` (default true)

### **CRITICAL BUG: State Never Updated**

The `StateManager.update_state()` method exists (line 272) but is **NEVER CALLED** from the agent pipeline.

**Evidence**: No call to `update_state()` found in:
- `phase_detection.py`
- `phase_memory_and_context` (context.py)
- `phase_llm_generation` (generation.py)
- `phase_postprocessing` (postprocessing.py)
- `post_response.py`

**Impact**:
- State loaded from DB → injected into prompt (WORKS)
- But after response: message_count never incremented
- Context never enriched (goal, situation, constraints never extracted)
- Phase transitions NEVER occur
- **Every conversation stays in INICIO forever**

This is the **#1 critical bug** in the entire pipeline. The sales funnel state machine is effectively dead code.

---

## SYSTEM 16: MEMORY ENGINE

**File**: `services/memory_engine.py` (1274 lines)
**Verdict**: PARTIALLY WORKING — **HIGH SEVERITY**

### Fact Extraction

- LLM-based (Gemini Flash-Lite) using structured prompt (lines 99-124)
- 6 fact types: preference, commitment, topic, objection, personal_info, purchase_history
- Max 5 facts per extraction (`MAX_FACTS_PER_EXTRACTION`)
- Embeddings via OpenAI text-embedding-3-small (1536 dims)

### Semantic Recall

```sql
SELECT fact_text, 1 - (fact_embedding <=> :query) as similarity
FROM lead_memories
WHERE creator_id = :cid AND lead_id = :lid
  AND is_active = true AND fact_embedding IS NOT NULL
  AND 1 - (fact_embedding <=> :query) >= 0.4  -- MEMORY_MIN_SIMILARITY
ORDER BY fact_embedding <=> :query
LIMIT 10  -- MAX_FACTS_IN_PROMPT
```

### Why Only 182 Chars in Prompt (2,247 Facts Exist)

**Three compounding issues:**

1. **Feature flag DISABLED by default** (line 35):
   ```python
   ENABLE_MEMORY_ENGINE = os.getenv("ENABLE_MEMORY_ENGINE", "false").lower() == "true"
   ```
   If disabled → `recall()` returns `""` (empty string)

2. **Aggressive similarity filter** (0.4 threshold):
   - Most facts are not semantically similar to the current message
   - Query "hola que tal" matches very few facts about preferences/commitments

3. **Character budget truncates output** (line 1167):
   ```python
   max_chars: int = 1200  # Hard budget
   if chars_used + len(line) > char_budget:
       break  # EARLY EXIT
   ```
   If facts are verbose (~600 chars each), only 2 facts fit → 182 chars total

### UUID Resolution

`_resolve_creator_uuid()` (lines 146-171): Tries UUID parse first, falls back to `SELECT id FROM creators WHERE name = :name`.

---

## SYSTEM 17: SEMANTIC RAG

**File**: `core/rag/semantic.py` (537 lines)
**Verdict**: BROKEN (INGESTION)

### Search Pipeline

```
Query → Skip simple intents (greeting/farewell/thanks)
      → Check cache (5-min TTL)
      → Semantic search (OpenAI embedding → pgvector cosine)
      → BM25 hybrid fusion (0.7 semantic + 0.3 BM25) [if ENABLE_BM25_HYBRID=true]
      → Cross-encoder reranking [if ENABLE_RERANKING=true]
      → Return top_k results (default 5)
```

### Why Only 24 Content Chunks

**Ingestion pipeline not active.** Code exists but is disconnected:
- `ingestion/v2/youtube_ingestion.py` — exists, not integrated into scheduler
- `ingestion/v2/instagram_ingestion.py` — exists, disconnected
- `ingestion/content_indexer.py` — exists, unclear when called

The `content_chunks` table has only 24 rows (likely test data or partial ingestion).

### Why RAG Returns Only 32 Chars

With only 24 chunks of short content, search returns 0-2 results of 1-2 sentences each. The pipeline architecture is sound but starved of data.

### Similarity Thresholds

| System | Threshold | Default |
|--------|-----------|---------|
| Memory Engine | MEMORY_MIN_SIMILARITY | 0.4 |
| RAG | RAG_MIN_SIMILARITY | 0.5 |

### Feature Flags

- `ENABLE_BM25_HYBRID`: default TRUE
- `ENABLE_RERANKING`: default TRUE (adds ~100ms, improves precision)

---

## SYSTEM 18: FRIEND/FAMILY DETECTION

**File**: `services/relationship_type_detector.py`
**Verdict**: WORKING

### Detection Method

Keyword-based scoring with thresholds per type:

| Type | Threshold | Keywords | Emoji |
|------|-----------|----------|-------|
| FAMILIA | 8 | hijo, hija, papa, mama, padre, madre, abuelo | :family:, :house: |
| INTIMA | 10 | amor, te amo, te quiero, mi vida, carino | :blue_heart:, :heart:, :kiss: |
| AMISTAD_CERCANA | 6 | hermano, bro, circulo, espiritual | :pray:, :muscle:, :hugging: |

Confidence: `min(0.95, 0.6 + (max_score - threshold) * 0.05)`

### Prompt Changes for Friends

- FAMILIA: "NO intentes vender, ofrecer productos, ni hacer preguntas de cualificacion. Habla con carino y naturalidad."
- AMISTAD: "NO intentes vender, ofrecer productos. Habla natural, personal y relajada."
- Products list CLEARED: `prompt_products = [] if is_friend else agent.products`

### Accuracy

Conservative — requires strong signal (high thresholds). Casual friendships may slip through as regular leads. Acceptable behavior (false negatives are safer than false positives for sales suppression).

---

## SYSTEM 19: AUDIO CONTEXT EXTRACTION

**File**: `core/dm/phases/context.py:295-324`
**Verdict**: PARTIALLY WORKING — **HIGH SEVERITY**

### Fields Injected into Prompt

From `audio_intel` metadata dict (context.py:300-318):
1. `intent` — "Intencion del audio: {intent}"
2. `entities.people` — Named persons
3. `entities.places` — Locations
4. `entities.dates` — Temporal references
5. `entities.numbers` — Numeric data
6. `entities.products` — Products/services
7. `action_items` — Pending commitments
8. `emotional_tone` — Speaker's emotional state

### BUG: Full Transcription NOT in Prompt

**What the LLM sees**:
- Message text: `"[Audio]: {clean_text}"` (70-85% of original, filler removed)
- Audio context: Structured metadata only (intent, entities, tone)

**What's MISSING from the prompt**:
- `raw_text` (full Whisper output) — NOT included
- `summary` (Layer 4 synthesis) — NOT included
- `topics` (thematic tags) — NOT included

**Evidence** (evolution_webhook.py):
- Line 330: `display_text = ai.get("clean_text") or ai.get("summary") or audio_transcription`
- Line 929: `text = f"[Audio]: {ai_result.clean_text or raw_text}"`
- Line 1018: `clean = ai.get("clean_text") or msg_metadata.get("transcription", "")`

**Impact**: ~40-50% of semantic richness lost due to double filtering (raw → clean_text → extracted fields only). The 4-layer pipeline generates a summary but never injects it into the prompt.

---

## SYSTEM 20: ECHO RELATIONSHIP ADAPTER

**File**: `services/relationship_adapter.py`
**Verdict**: WORKING

### Per-Status Modulation

| Lead Status | Temperature | Max Tokens | Tone |
|-------------|------------|------------|------|
| nuevo | 0.6 | 200 | profesional-cercano |
| tibio | 0.65 | 250 | amigable |
| caliente | 0.7 | 300 | entusiasta, complice |
| cliente | 0.75 | 250 | familiar |
| ghosted | 0.6 | 150 | ligero, sin presion |

Adds ~200-400 chars of status-specific instructions to prompt. Controls sales intensity, question limits, and emoji ratio per lead status.

---

## SYSTEM 21: CALIBRATION LOADER

**File**: `services/calibration_loader.py`
**Verdict**: PARTIALLY WORKING

### Expected Format

```json
{
  "baseline": {
    "median_length": 25,
    "emoji_pct": 12.5,
    "exclamation_pct": 8.0,
    "question_frequency_pct": 15.0,
    "soft_max": 35
  },
  "few_shot_examples": [
    {"user_message": "...", "response": "...", "context": "..."}
  ],
  "context_soft_max": {"saludo": 22, "casual": 25},
  "response_pools": {...},
  "creator_vocabulary": [...]
}
```

### Why Missing for Iris

- File expected at: `calibrations/iris_bertran.json`
- **No auto-generation** — calibration files must be manually created
- Loading is silent: returns `None` if file not found (no error)
- Cache TTL: 300s (`CALIBRATION_CACHE_TTL`)

### Impact

Without calibration: no few-shot examples injected, no baseline statistics for response length control. The system degrades gracefully but loses quality signal.

---

## SYSTEM 22: PERSONALITY LOADER / Doc D

**File**: `core/personality_loader.py`, `services/creator_style_loader.py`
**Verdict**: WORKING

### Loading Priority Chain

1. **PersonalityDoc (Doc D)** — DB table `personality_docs`, replaces all legacy if present
2. **WritingPatterns** — DB model
3. **CreatorDMStyle** — Legacy DB table
4. **ToneProfile** — DB model

### DB Query with JOIN (recent fix)

```sql
SELECT pd.content FROM personality_docs pd
JOIN creators c ON c.id::text = pd.creator_id
WHERE (c.name = :creator_id OR pd.creator_id = :creator_id)
  AND pd.doc_type = 'doc_d'
LIMIT 1
```

Handles both slug and UUID resolution. Cache: 300s TTL, max 50 creators.

### Doc D Sections

- Section 4.1: SYSTEM PROMPT (code block with instructions)
- Section 4.2: BLACKLIST (phrases to avoid)
- Section 4.3: PARAMETROS (calibration overrides)
- Section 4.4: TEMPLATE POOL (response templates per category)
- Section 4.5: MULTI-BUBBLE (multi-message templates)

### Size Concern

Combined style prompt: ~21,495 chars. No truncation or optimization when Doc D exists alongside legacy sources. May consume excessive context window.

---

## SYSTEMS 23-25: KNOWLEDGE BASE + CITATION SERVICE + PROMPT BUILDER

### System 23: Knowledge Base — WORKING

**File**: `services/knowledge_base.py`
- JSON files in `knowledge_bases/{creator_id}.json`
- Keyword-based lookup (categories with keywords + content)
- Used for ~1-3% of messages needing factual data (prices, sessions)
- Lightweight, functional

### System 24: Citation Service — WORKING

**File**: `core/citation_service.py`
- Indexes creator posts into chunks
- Searches by keyword relevance
- Returns max 3 citations with min relevance 0.25
- Dual storage: PostgreSQL `rag_documents` + JSON fallback

### System 25: Prompt Builder — WORKING

**File**: `core/prompt_builder/orchestration.py`
- `build_system_prompt()` with 38 arguments
- Assembly order: Identity → Alerts → B2B → Frustration → Data → User → Actions → Conversion
- `custom_instructions` parameter receives the full `combined_context` from context.py
- Modular, well-structured

---

## TOP 5 CRITICAL FINDINGS

### 1. CONVERSATION STATE NEVER UPDATED (System 15)

**Severity**: CRITICAL
**Impact**: Sales funnel state machine is dead. Every conversation stays in INICIO forever.
**Root cause**: `StateManager.update_state()` exists but is never called from any pipeline phase.
**Fix**: Add `update_state()` call in post-processing phase after response generation.

### 2. MEMORY ENGINE DISABLED + TRUNCATED (System 16)

**Severity**: HIGH
**Impact**: 2,247 facts exist but are never used. `ENABLE_MEMORY_ENGINE=false` by default.
**Root cause**: Feature flag disabled + 1200-char budget truncates output to ~182 chars.
**Fix**: Enable flag in Railway env + increase char budget to 3000+.

### 3. RAG INGESTION NOT ACTIVE (System 17)

**Severity**: HIGH
**Impact**: Only 24 content chunks exist. RAG returns near-zero useful results.
**Root cause**: Ingestion pipelines (YouTube, Instagram) exist in code but are not connected to scheduler.
**Fix**: Activate ingestion pipeline to populate `content_chunks` table.

### 4. AUDIO SUMMARY NOT IN PROMPT (System 19)

**Severity**: HIGH
**Impact**: 4-layer audio pipeline generates summary but never injects it. LLM only gets structured metadata.
**Root cause**: context.py:300-318 extracts intent/entities/tone but skips clean_text, summary, topics.
**Fix**: Include `audio_intel["summary"]` or `audio_intel["clean_text"]` in audio_context block.

### 5. NO CATALAN DETECTION PATTERNS (Systems 8, 9)

**Severity**: MEDIUM
**Impact**: Catalan speakers in crisis ("vull morir") are not detected. Frustration in Catalan is ignored.
**Root cause**: All patterns are Spanish + English only.
**Fix**: Add Catalan equivalents for all critical detection patterns.

---

## SYSTEM HEALTH MATRIX

```
FULLY WORKING (no issues):
  [13] DB Fallback
  [14] Relationship DNA
  [18] Friend/Family Detection
  [20] Echo Relationship Adapter
  [23] Knowledge Base
  [24] Citation Service
  [25] Prompt Builder

WORKING (minor issues):
  [9]  Frustration Analyzer (no Catalan)
  [10] Pool Response Matching (edge case LLM bypass)
  [11] Intent Classifier (keyword-only, no semantic)
  [22] Personality Loader (size concern)

PARTIALLY WORKING (significant issues):
  [8]  Sensitive Detector (no Catalan detection)
  [12] MemoryStore JSON (ephemeral on Railway)
  [15] Conversation State (NEVER UPDATED - critical)
  [16] Memory Engine (disabled + truncated)
  [19] Audio Context (summary not in prompt)
  [21] Calibration Loader (missing for Iris)

BROKEN:
  [17] Semantic RAG (ingestion not active, only 24 chunks)
```

---

## RECOMMENDED FIX PRIORITY

| Priority | System | Fix | Effort | Impact |
|----------|--------|-----|--------|--------|
| P0 | 15 | Call `update_state()` in postprocessing | 1 hour | Unlocks entire sales funnel |
| P0 | 16 | Set `ENABLE_MEMORY_ENGINE=true` in Railway | 1 minute | Activates 2,247 facts |
| P1 | 16 | Increase `max_chars` from 1200 to 3000 | 5 minutes | 3x more memory context |
| P1 | 19 | Add `summary` to audio_context block | 30 minutes | Full audio meaning preserved |
| P1 | 17 | Activate content ingestion pipeline | 4 hours | Populates RAG with real content |
| P2 | 8,9 | Add Catalan detection patterns | 2 hours | Safety coverage for Catalan speakers |
| P2 | 21 | Create calibration file for Iris | 2 hours | Enables few-shot + length control |
| P3 | 22 | Truncate style prompt when Doc D exists | 1 hour | Saves ~10K tokens per call |
| P3 | 11 | Add confidence scoring to intent classifier | 4 hours | Better intent routing |
