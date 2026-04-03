# Audit — Fase 2: Context Systems (#6–#12)

**Date:** 2026-04-01
**Status:** Audit complete — NO measurements yet (pending anti-echo fix)
**Orchestrator:** `core/dm/phases/context.py` (973 lines)

## Overview

All 7 context systems feed into a single orchestrator (`phase_memory_and_context`) which assembles sections with a **priority-based budget** of `MAX_CONTEXT_CHARS=8000`. Sections are added in priority order; lower-priority sections are skipped if over budget.

```
Priority order (first = highest):
  style → fewshot → friend → recalling → audio → rag → kb → hier_memory → advanced → citation → override

Critical sections (style, recalling, rag) are TRUNCATED rather than skipped.
```

Feature flags at top of context.py:
```python
ENABLE_QUESTION_CONTEXT     = true
ENABLE_CONVERSATION_STATE   = true
ENABLE_DNA_AUTO_CREATE      = true
ENABLE_QUERY_EXPANSION      = true
ENABLE_RAG                  = true
ENABLE_HIERARCHICAL_MEMORY  = true
ENABLE_EPISODIC_MEMORY      = true
ENABLE_FEW_SHOT             = true
ENABLE_LENGTH_HINTS         = true
ENABLE_QUESTION_HINTS       = true
```

---

## System #6: Conversation State Loader

**File:** `core/conversation_state.py` (463 lines)
**Called from:** `context.py:249` via `_load_conv_state()`

### What it does
Sales funnel state machine with 7 phases: INICIO → CUALIFICACION → DESCUBRIMIENTO → PROPUESTA → OBJECIONES → CIERRE → ESCALAR.

For each message:
1. Loads state from PostgreSQL (or in-memory fallback)
2. Extracts context from user message (regex: goals, constraints, personal info)
3. Determines phase transition based on intent + message keywords
4. Builds enhanced prompt with phase-specific instructions

### Prompt injection
Injects via `build_enhanced_prompt()` → into the "recalling" block:
```
=== ESTADO CONVERSACION ===
Fase actual: PROPUESTA
Mensajes intercambiados: 5

FASE: PROPUESTA - Tu objetivo es presentar el producto ADAPTADO.
- Menciona el producto que encaja con SU situacion
- Incluye precio claro con euro
...

=== CONTEXTO USUARIO ===
Nombre: Maria
Objetivo: bajar de peso
Limitaciones: poco tiempo

=== RECORDATORIOS ===
Ya mencionaste el precio, no lo repitas a menos que te pregunten
```

### Size estimate
~300–600 chars depending on accumulated context.

### Universal?
**YES** — fully universal. No hardcoded creator data. Uses `creator_id` + `follower_id` as keys. Phase instructions are in Spanish only.

### Bugs

| ID | Severity | Description |
|----|----------|-------------|
| B1 | Medium | **Spanish-only phase instructions** — "Tu objetivo es saludar y despertar curiosidad" for all creators regardless of language. Italian creators (Stefano) get Spanish sales instructions. |
| B2 | Medium | **Keyword extraction is ES-only** — `_extract_context()` uses Spanish keywords: "hijo", "trabajo", "bajar", "dinero". Won't detect Italian/Catalan/English equivalents. |
| B3 | Low | **Aggressive phase transitions** — After 1 message → CUALIFICACION, after 3 → DESCUBRIMIENTO, after 4 → PROPUESTA. Very short casual conversations get pushed through sales funnel too fast. |
| B4 | Low | **`_determine_transition` uses "si" as purchase affirmation** — "si" (Catalan for "yes"), "vale", "ok" all trigger OBJECIONES→CIERRE. Could misfire on casual "si" in non-purchase context. |

### Paper support
No direct paper reference. Standard sales funnel pattern. The phase-specific instructions follow the "structured task decomposition" principle from prompt engineering literature.

---

## System #7: User Context Builder

**File:** `core/user_context_loader.py` (666 lines)
**Called from:** `context.py:243` via `asyncio.gather(get_user_context(...))`

### What it does
Loads complete user profile from 3 sources:
1. **FollowerMemory (JSON files)** — conversation history, scores, interests
2. **UserProfile (JSON files)** — preferences, weighted interests, objections
3. **Lead table (PostgreSQL)** — CRM data (status, tags, full_name)

Produces a `UserContext` dataclass with: identity, preferences (language, tone, style), interests, products discussed, objections, scores (purchase_intent, engagement), CRM status, conversation history, computed flags (is_first_message, is_returning_user, days_since_last_contact).

### Prompt injection
Via `format_user_context_for_prompt()`:
```
=== CONTEXTO DEL USUARIO ===
- Nombre: Maria
- Idioma preferido: ca
- Intereses: nutricion, fitness
- Productos que le interesan: curso 8 semanas
- Estado: LEAD CALIENTE
- Usuario que vuelve despues de 14 dias
```

This goes into the `follower` object passed to `phase_memory_and_context`, then used in the `recalling` block assembly.

### Size estimate
~100–400 chars. Only non-default fields are included.

### Universal?
**YES** — fully universal. Uses `creator_id` as directory key, `follower_id` as file key. No hardcoded data.

### Bugs

| ID | Severity | Description |
|----|----------|-------------|
| B5 | Medium | **Labels in Spanish only** — "CONTEXTO DEL USUARIO", "Nombre", "Intereses", "LEAD CALIENTE", "PRIMER MENSAJE - Dar bienvenida". Italian/English creators get Spanish metadata labels. |
| B6 | Low | **Sync file I/O in `_load_from_follower_memory`** — reads JSON with `open()` synchronously. On Railway (where JSON files may not exist), this is a no-op. But on local dev with many leads, could block event loop. |
| B7 | Low | **60s cache TTL** — `BoundedTTLCache(max_size=200, ttl_seconds=60)`. If a lead sends rapid follow-ups, context may be stale for up to 60s (won't reflect newest message). |
| B8 | Info | **`get_display_name()` defaults to "amigo"** — Spanish default for unknown users. Should be language-aware. |

### Paper support
No direct paper. Standard CRM context injection pattern.

---

## System #8: DNA Engine (Relationship DNA)

**File:** `services/relationship_dna_service.py` (279 lines)
**Supporting:** `services/bot_instructions_generator.py` (BASE_INSTRUCTIONS per type)
**Called from:** `context.py:248,252` via `_get_raw_dna()` → `_build_ctx()`

### What it does
Per-lead relationship type classification with vocabulary guidance. Each lead gets a DNA record with:
- `relationship_type`: FAMILIA, INTIMA, AMISTAD_CERCANA, CONOCIDO, FAN_ACTIVO, LEAD_FRIO, DESCONOCIDO
- `uses_words`: vocabulary the creator uses WITH this specific lead
- `avoids_words`: vocabulary to avoid
- Auto-seeds when lead has 2+ messages (via `RelationshipTypeDetector`)

### Prompt injection
Via `get_prompt_instructions()` → formatted as relationship context:
```
TIPO DE RELACION: AMISTAD_CERCANA
Usa este vocabulario con esta persona: [specific words]
Evita: [specific words]
[BASE_INSTRUCTIONS for AMISTAD_CERCANA]
```

BASE_INSTRUCTIONS examples (from `bot_instructions_generator.py`):
- FAMILIA: "Habla con cariño y cercanía, como si fuera de tu familia..."
- INTIMA: "Es alguien muy cercano. Habla con total confianza..."
- LEAD_FRIO: "Es un contacto nuevo. Se amable pero profesional..."

### Size estimate
~200–500 chars (type + uses/avoids + base instructions).

### Universal?
**MOSTLY** — relationship types and detection are universal. But:

| ID | Severity | Description |
|----|----------|-------------|
| B9 | Medium | **BASE_INSTRUCTIONS all in Spanish** — "Habla con cariño y cercanía" for Italian/English creators. |
| B10 | Medium | **`uses_words`/`avoids_words` populated by LLM analysis** — quality depends on conversation history. New leads with 2 messages get minimal DNA from `RelationshipTypeDetector` which is rule-based (checks for emoji frequency, informal markers). |
| B11 | Low | **DB cache with 300s TTL** — DNA refreshes every 5 min. If relationship evolves mid-conversation, stale DNA persists. |
| B12 | Low | **Auto-create threshold too low** — Seeds DNA at 2 messages. Two messages is barely enough to detect relationship type. Could misclassify. |

### Paper support
Inspired by PersonaGym's relationship-aware response adaptation. The vocabulary uses/avoids pattern follows RoleLLM's speaking style capture approach.

---

## System #9: Memory Engine (Per-Lead Facts)

**File:** `services/memory_engine.py` (~650 lines)
**Called from:** `context.py:257-266` (if `ENABLE_MEMORY_ENGINE=true`)

### What it does
LLM-based fact extraction and semantic recall:
1. **add()**: Sends conversation to LLM with `FACT_EXTRACTION_PROMPT` → extracts facts (preference, commitment, topic, objection, personal_info, purchase_history)
2. **search()**: pgvector semantic search with `min_similarity=0.4`
3. **recall()**: Combines semantic search + compressed memo + summary → formatted for prompt
4. **resolve_conflict()**: Two-pass dedup: Jaccard text similarity (>0.85 = skip) → embedding cosine via pgvector (distance <0.15 = skip)
5. **compress_lead_memory()**: COMEDY-inspired narrative memo when >8 facts accumulated
6. **decay_memories()**: Ebbinghaus eviction with configurable half-life (30 days default)

### Prompt injection
Via `recall()` → formatted facts:
```
Lo que recuerdas de esta persona:
- [preference] Le interesa el curso de nutricion (conf: 0.9)
- [personal_info] Vive en Barcelona, tiene 2 hijos (conf: 0.85)
- [commitment] Prometio venir el jueves (conf: 0.8)

Resumen: Maria es una seguidora interesada en nutricion que...
```

### Size estimate
~200–800 chars depending on fact count (max 10 facts in prompt).

### Universal?
**YES** — fully universal. Creator ID resolved via slug→UUID. Fact extraction prompt is in Spanish but works across languages (LLM handles multilingual input).

### Bugs

| ID | Severity | Description |
|----|----------|-------------|
| B13 | **Critical** | **`ENABLE_MEMORY_ENGINE=false` by default** — This entire system is OFF in production. All the infrastructure exists but produces zero value. |
| B14 | High | **LLM extraction cost** — Each `add()` call invokes the LLM to extract facts. For high-volume creators (Iris: ~50 DMs/day), this adds 50 LLM calls/day just for memory. Cost not measured. |
| B15 | Medium | **Fact extraction prompt is ES-only** — "Analiza esta conversacion de DMs entre un creador y un lead." Italian/English leads get Spanish extraction instructions (LLM handles it, but extraction quality may suffer). |
| B16 | Medium | **`ENABLE_MEMORY_DECAY=false` by default** — Ebbinghaus decay is also OFF. If memory engine is turned on, facts accumulate forever without eviction. |
| B17 | Low | **60s recall cache** — Same staleness issue as user context. |
| B18 | Low | **Temporal fact detection only covers ES/CA/EN** — Missing Italian temporal markers ("domani", "oggi", "prossimo"). |

### Paper support
- **COMEDY (COLING 2025)**: Narrative memo compression for long-context leads. Implemented as `compress_lead_memory()`.
- **Ebbinghaus decay**: Standard forgetting curve with configurable half-life.
- **Embedding dedup**: pgvector cosine similarity for semantic deduplication.

---

## System #10: Episodic Memory (Conversation Embeddings)

**File:** `core/dm/phases/context.py:127-177` (`_episodic_search()`)
**Backend:** `core/semantic_memory_pgvector.py` (SemanticMemoryPgvector)
**Called from:** `context.py:272-281` (if `ENABLE_EPISODIC_MEMORY=true` AND message >= 15 chars)

### What it does
pgvector semantic search over `conversation_embeddings` table. For each incoming message:
1. Embeds the message
2. Searches for past messages (from this lead with this creator) with similarity >= 0.45
3. Returns top 3 matches
4. Handles ID resolution: tries slug+platform_id first, then UUID+lead_uuid via DB lookup

### Prompt injection
Formatted in the Recalling block:
```
Conversaciones pasadas relevantes:
- lead: "Me interesaba el curso de 8 semanas pero no se si me da tiempo"
- tú: "Tranqui, muchas alumnas lo combinan con trabajo..."
- lead: "Vale, me lo pienso y te digo"
```

### Size estimate
~150–500 chars (3 results × ~50-150 chars each).

### Universal?
**YES** — uses creator_id + follower_id as keys. No hardcoded data.

### Bugs

| ID | Severity | Description |
|----|----------|-------------|
| B19 | Medium | **15-char minimum gate** — Messages like "precio?" (7 chars) or "cuanto?" (7 chars) skip episodic search entirely. These are exactly the messages that benefit most from past context (what product were they asking about?). |
| B20 | Medium | **No role filtering** — Returns both user and bot messages. Past bot messages may contain hallucinated info that gets re-injected as "context". |
| B21 | Low | **Double DB query for UUID resolution** — When slug+platform_id fails, does a second query with UUID+lead_uuid. This means 2 DB round-trips for the common case (Railway UUID pattern). |
| B22 | Low | **Fixed k=3, min_similarity=0.45** — Not configurable via env vars. May need tuning per creator. |

### Paper support
Standard RAG over conversation history. Similar to MemoryBank (Zhong et al., 2024) which uses embedding search over past conversations.

---

## System #11: RAG Knowledge Engine

**File:** `core/rag/semantic.py` (555 lines)
**Supporting:** `core/rag/bm25.py` (369 lines)
**Called from:** `context.py:382-490`

### What it does
3-stage retrieval pipeline over creator's knowledge base (`content_chunks` table):

**Stage 1: Signal Gating (Conversational Adaptive RAG)**
- Only retrieves when product signal detected:
  - `_PRODUCT_INTENTS`: question_product, question_price, interest_strong, purchase_intent, objection_price
  - `_UNIVERSAL_PRODUCT_KEYWORDS`: curso, programa, precio, comprar, pagar, etc. (40+ ES/CA/EN/IT keywords)
  - `_CONTENT_REF_MARKERS`: "tu post", "tu reel", "what you said", etc.
  - `_dynamic_kw`: creator-specific keywords extracted from DB content_chunks titles
- Casual messages → ZERO retrieval (saves latency + prevents noise)

**Stage 2: Hybrid Search (Semantic + BM25)**
- OpenAI `text-embedding-3-small` for semantic search via pgvector
- BM25 lexical search with multilingual stopwords (ES/CA/EN/IT)
- Weighted Reciprocal Rank Fusion: 0.7 semantic + 0.3 BM25
- Source-type boosting: product_catalog +0.15, faq +0.10, objection_handling +0.10, expertise +0.08

**Stage 3: Adaptive Threshold**
- top score >= 0.5 → inject top 3 results (high confidence)
- top score >= 0.4 → inject top 1 result (medium)
- top score < 0.4 → skip injection (low confidence, LLM knows enough)

**Stage 4: Source-Type Routing**
- Product signals → prefer: product_catalog, faq, knowledge_base, expertise, objection_handling, policies
- Content ref signals → prefer: instagram_post, video, carousel, website
- If no matching source type → drop (prevents IG caption noise for product queries)

### Prompt injection
Via `agent._format_rag_context()`:
```
Informacion relevante de tu base de conocimiento:
- [product_catalog] Curso 8 semanas: programa de entrenamiento... (score: 0.72)
- [faq] Precio del curso: 197€ con acceso ilimitado... (score: 0.65)
```

### Size estimate
~200–800 chars (1-3 results × ~100-250 chars each). Zero for casual messages.

### Universal?
**MOSTLY** — the retrieval pipeline is universal. But:

| ID | Severity | Description |
|----|----------|-------------|
| B23 | Medium | **Universal keywords are ES/CA/EN/IT only** — `_UNIVERSAL_PRODUCT_KEYWORDS` and `_CONTENT_REF_MARKERS` don't cover Portuguese, French, or other languages. New language = missed product signals. |
| B24 | Medium | **BM25 stopwords missing languages** — Has ES/CA/EN/IT. No Portuguese. Adding a PT creator would get noisy BM25 results. |
| B25 | Low | **Dynamic keywords cached globally** — `_get_creator_product_keywords()` uses a module-level dict. If content_chunks are updated, stale keywords persist until process restart. |
| B26 | Low | **Query expansion not measured** — `ENABLE_QUERY_EXPANSION=true` but no A/B test showing it helps. May add noise. |
| B27 | Info | **500 chunk limit in `load_from_db()`** — `query.limit(500)`. If a creator has >500 chunks, only first 500 are loaded. Not an issue today but could be for content-heavy creators. |

### Paper support
- **Reciprocal Rank Fusion (Cormack et al., 2009)**: Standard fusion method for hybrid search.
- **Product signal gating**: Inspired by Conversational AI retrieval patterns — "retrieve only when the user expresses information need" (Gao et al., 2023).
- **Adaptive threshold**: Similar to confidence-based retrieval filtering in RAG literature.

---

## System #12: Reranker (Cross-Encoder)

**File:** `core/rag/reranker.py` (~100 lines)
**Called from:** `core/rag/semantic.py:350-372` (if `ENABLE_RERANKING=true`)

### What it does
Cross-encoder reranking using `nreimers/mmarco-mMiniLMv2-L12-H384-v1`:
1. Takes query + candidate documents from hybrid search
2. Evaluates each (query, document) pair together (not separately like bi-encoder)
3. Re-scores and re-sorts results
4. Returns top_k reranked results

Key implementation details:
- **Lazy loading**: model loaded on first call, not at import time
- **30s retry cooldown**: if model fails to load, won't retry for 30 seconds
- **Cohere reranker skeleton**: code exists but not activated (would use Cohere API)

### Prompt injection
None directly — modifies the ordering of RAG results before they're formatted.

### Size estimate
0 chars added (reranker changes result ORDER, not content).

### Universal?
**YES** — `mmarco-mMiniLMv2` is multilingual (trained on MS MARCO in multiple languages). No hardcoded data.

### Bugs

| ID | Severity | Description |
|----|----------|-------------|
| B28 | Medium | **Model loaded in-process** — Cross-encoder model loaded into the FastAPI process. Adds ~200MB RAM + first-call latency (~2-5s). No separate inference service. |
| B29 | Low | **Silent fallback** — If reranking fails, silently returns un-reranked results. No logging of failure frequency. Could be failing constantly without anyone knowing. |
| B30 | Info | **Cohere skeleton dead code** — Cohere reranker class exists but is never instantiated. Dead code. |

### Paper support
- **Cross-encoder reranking (Nogueira & Cho, 2019)**: Standard two-stage retrieval (bi-encoder → cross-encoder).
- **mMARCO (Bonifacio et al., 2021)**: Multilingual MS MARCO dataset for cross-encoder training.

---

## System #10.5: Hierarchical Memory (IMPersona)

**File:** `core/hierarchical_memory/hierarchical_memory.py` (175 lines)
**Called from:** `context.py:285-317` (if `ENABLE_HIERARCHICAL_MEMORY=true`)

### What it does
3-level memory system inspired by IMPersona (Princeton, 2025):
- **L1 (Episodic)**: Per-conversation summaries with topics. Source: `memories_level1.jsonl`
- **L2 (Semantic)**: Patterns grouped by topic across conversations. Aggregated from L1.
- **L3 (Abstract)**: Generalizations about creator's behavior. Distilled from L2.

Retrieval strategy:
1. **Always**: top-3 L3 (abstract generalizations, sorted by confidence)
2. **Keyword search**: top-3 L2 (patterns relevant to message by word overlap)
3. **Per-lead name**: top-3 L1 (episodic memories for this specific lead)

Storage: JSONL files in `data/persona/{creator_id}/memories_level{N}.jsonl`

### Prompt injection
```
[Comportamiento habitual]
- Iris suele responder con mensajes cortos y directos
- Usa mucho el catalan mezclado con castellano
- Cuando alguien pregunta por precio, da el link directamente

[Patrones recientes]
- En marzo, muchas conversaciones sobre el curso de 8 semanas
- Tendencia a usar "flower" como muletilla

[Historial con Tania]
- 2026-03-15: Tania pregunto por el curso y Iris le envio link
- 2026-03-20: Tania volvio para preguntar sobre horarios
```

### Size estimate
~200–700 chars (max_tokens=300 → ~1050 chars max, but usually less).

### Universal?
**YES** — JSONL per creator_id. No hardcoded data.

### Bugs

| ID | Severity | Description |
|----|----------|-------------|
| B31 | **Critical** | **JSONL files must be pre-built** — Requires running `scripts/build_memories.py` to populate JSONL. If not run, all 3 levels are empty arrays → system does nothing. No auto-generation from DB. |
| B32 | High | **L2 keyword scoring is naive** — `_score_l2_relevance()` uses raw word overlap between message and memory text. No TF-IDF, no embedding, no stopword filtering. Common words match everything. |
| B33 | Medium | **L1 search by `lead_name` only** — Searches L1 by name string match: `search_term in m.get("lead_name", "").lower()`. If JSONL has "tania_garcia" but metadata passes "Tania", it works. But if username vs display name differs, misses. No `lead_id` fallback implemented (code accepts `lead_id` param but never uses it). |
| B34 | Medium | **No L2/L3 auto-refresh** — Once built, JSONL files are static. New conversations don't update L2/L3 until `build_memories.py` is re-run. Memory drifts from reality over time. |
| B35 | Low | **Instantiated per-request** — `HierarchicalMemoryManager(agent.creator_id)` is created fresh each time, re-reading all JSONL files from disk. No caching/singleton. |

### Paper support
- **IMPersona (Princeton, 2025)**: Hierarchical memory adds +19 pts to human pass rate. 3-level architecture: episodic → semantic → abstract.

---

## Cross-System Analysis

### Total prompt budget usage (estimated)

| System | Chars (typical) | Chars (max) | Priority |
|--------|-----------------|-------------|----------|
| #14 Doc D (style) | 1,700 | 2,000 | CRITICAL |
| Few-shot examples | 500 | 1,000 | CRITICAL |
| #6 Conv State | 300 | 600 | HIGH (in recalling) |
| #7 User Context | 200 | 400 | HIGH (in recalling) |
| #8 DNA Engine | 300 | 500 | HIGH (in recalling) |
| #9 Memory Engine | 0 (OFF) | 800 | HIGH (in recalling) |
| #10 Episodic | 200 | 500 | HIGH (in recalling) |
| #11 RAG | 300 | 800 | HIGH |
| #12 Reranker | 0 | 0 | N/A (reorders) |
| #10.5 Hier Memory | 300 | 700 | MEDIUM |
| **TOTAL** | **~3,800** | **~7,300** | 8000 budget |

### Systems that are OFF or degraded

| System | Status | Impact |
|--------|--------|--------|
| #9 Memory Engine | `ENABLE_MEMORY_ENGINE=false` | Zero per-lead fact recall |
| #9 Memory Decay | `ENABLE_MEMORY_DECAY=false` | No eviction (moot while engine OFF) |
| #10.5 Hier Memory | ON but likely empty JSONL | Zero hierarchical context |

### Universality summary

| System | Universal? | Language issue? |
|--------|-----------|----------------|
| #6 Conv State | Yes | Phase instructions ES-only, keyword extraction ES-only |
| #7 User Context | Yes | Labels ES-only, "amigo" default |
| #8 DNA Engine | Mostly | BASE_INSTRUCTIONS ES-only |
| #9 Memory Engine | Yes | Extraction prompt ES-only, temporal markers missing IT |
| #10 Episodic | Yes | None |
| #11 RAG | Mostly | Keywords missing PT+, BM25 stopwords missing PT+ |
| #12 Reranker | Yes | None (multilingual model) |
| #10.5 Hier Memory | Yes | None (but may have empty data) |

### Bug priority ranking

| Priority | Count | Key bugs |
|----------|-------|----------|
| Critical | 2 | B13 (Memory Engine OFF), B31 (Hier Memory needs manual build) |
| High | 3 | B14 (LLM cost for memory), B32 (naive L2 scoring), B34 (no L2/L3 auto-refresh) |
| Medium | 10 | B1,B2,B5,B9,B10,B15,B19,B20,B23,B24 |
| Low | 10 | B3,B4,B6,B7,B8,B11,B12,B17,B18,B21,B22,B25,B26,B29,B33,B35 |
| Info | 3 | B27, B28, B30 |

### Top 5 bugs to fix (highest ROI)

1. **B13: Turn on Memory Engine** — All infrastructure exists. Flip `ENABLE_MEMORY_ENGINE=true` and measure impact. This is the #1 lever for solving "falta contexto".
2. **B19: Lower episodic search gate** — Change 15-char minimum to 5 or remove entirely. Short messages like "precio?" are exactly the ones that need context.
3. **B31: Auto-build hierarchical memory** — Add a cron/trigger that rebuilds JSONL from DB instead of requiring manual `build_memories.py`. Or disable the flag until auto-generation exists.
4. **B1+B5+B9: Internationalize system prompts** — All phase instructions, user context labels, and DNA instructions are Spanish-only. Create a language map per creator.
5. **B20: Filter bot messages from episodic recall** — Only return `role=user` messages to prevent re-injecting hallucinated bot content as "context".
