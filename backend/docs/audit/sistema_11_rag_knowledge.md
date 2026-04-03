# Auditoría Forense — Sistema #11: RAG Knowledge Engine

**Fecha:** 2026-04-02
**Auditor:** Claude Opus 4.6
**Estado:** COMPLETADA

---

## 1. Inventario de Archivos

| # | Archivo | LOC | Función |
|---|---------|-----|---------|
| 1 | `core/rag/semantic.py` | 555 | **SemanticRAG** — Motor principal. Embeddings OpenAI + pgvector + BM25 hybrid + reranking |
| 2 | `core/rag/reranker.py` | 229 | Cross-encoder reranking (local multilingual + Cohere skeleton) |
| 3 | `core/rag/bm25.py` | 367 | BM25 lexical retriever, per-creator singleton |
| 4 | `core/embeddings.py` | ~320 | OpenAI `text-embedding-3-small` (1536d) + pgvector store/search |
| 5 | `core/semantic_memory_pgvector.py` | 526 | Episodic conversation memory — semantic search over `conversation_embeddings` |
| 6 | `core/dm/phases/context.py` | ~1150 | RAG integration point — adaptive retrieval gating, source routing, budget |
| 7 | `core/dm/helpers.py:16` | 54 | `format_rag_context()` — source-aware formatting for prompt |
| 8 | `core/dm/phases/generation.py` | ~300 | Consumes `rag_context` in final prompt assembly |
| 9 | `services/knowledge_base.py` | 113 | Simple keyword-based KB lookup (JSON file, no embeddings) |
| 10 | `core/creator_data_loader.py` | 753 | `get_rag_context()` bridge + FAQ/product loading |
| 11 | `api/services/db/knowledge.py` | 203 | CRUD for `knowledge_base` table (FAQ management) |
| 12 | `api/models/content.py` | 215 | DB models: `ContentChunk`, `RAGDocument`, `KnowledgeBase` |
| 13 | `scripts/create_proposition_chunks.py` | ~350 | **HARDCODED IRIS** — chunk creation script |
| 14 | `ingestion/v2/pipeline.py` | ~300 | Website scraping → product detection → RAG indexing |
| 15 | `core/auto_configurator.py` | ~200 | Orchestrates onboarding + RAG indexing |

---

## 2. Arquitectura del Sistema

```
                    ┌─────────────────────────────────┐
                    │    Ingestion (Onboarding)         │
                    │  website scraper → product detect  │
                    │  IG scraper → post captions        │
                    │  create_proposition_chunks.py      │
                    └──────────┬──────────────────────────┘
                               │ content_chunks + content_embeddings (pgvector)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    RAG Search Pipeline                                │
│                                                                      │
│  1. Adaptive Gate (context.py)                                       │
│     - Product keywords → retrieve                                    │
│     - Content ref markers → retrieve                                 │
│     - Casual message → SKIP (zero retrieval)                         │
│                                                                      │
│  2. Query Expansion (optional)                                       │
│                                                                      │
│  3. Semantic Search (OpenAI embedding + pgvector cosine)             │
│     content_embeddings JOIN content_chunks                            │
│                                                                      │
│  4. BM25 Hybrid Fusion (RRF, 0.7 semantic + 0.3 BM25)              │
│                                                                      │
│  5. Cross-Encoder Reranking (mmarco-mMiniLMv2-L12 multilingual)     │
│                                                                      │
│  6. Source-Type Boost (+15% product_catalog, +10% faq)               │
│                                                                      │
│  7. Adaptive Threshold (top ≥0.5→3 results, ≥0.4→1, <0.4→skip)     │
│                                                                      │
│  8. Source Routing (product query→product chunks only)               │
│                                                                      │
│  9. Format (max 3 results, 300-500 chars each, source tags)          │
└──────────────┬───────────────────────────────────────────────────────┘
               │ rag_context (string, ~900-1500 chars)
               ▼
┌──────────────────────────────────────────────────────────────────────┐
│           Context Orchestration (context.py)                          │
│  Priority: style > fewshot > recalling > audio > RAG > KB > ...      │
│  Budget: MAX_CONTEXT_CHARS = 8000 (env configurable)                 │
│  RAG placed LAST for highest LLM attention (Liu et al. 2023)         │
└──────────────────────────────────────────────────────────────────────┘
```

### Parallel Systems (Episodic Memory ≠ RAG)
- **RAG** searches `content_chunks` / `content_embeddings` → creator's factual knowledge
- **Episodic Memory** searches `conversation_embeddings` → past conversation history per lead
- Both use pgvector but serve different purposes and have separate gating

---

## 3. Descripción Detallada por Componente

### 3.1 SemanticRAG (`core/rag/semantic.py`)
- Singleton via `get_semantic_rag()`
- `load_from_db(creator_id)`: Loads `content_chunks` into in-memory `_documents` dict (max 500)
- `search()`: 4-step pipeline — semantic → BM25 → rerank → source boost
- Cache: `BoundedTTLCache(200, 300s)` keyed by `creator_id:query`
- Intent gating: Skips search for `greeting/farewell/thanks` intents
- Fallback: keyword overlap search if OpenAI unavailable

### 3.2 Reranker (`core/rag/reranker.py`)
- Default: local `nreimers/mmarco-mMiniLMv2-L12-H384-v1` (multilingual CA/ES/EN/IT)
- Lazy-loaded with 30s retry cooldown on failure
- Cohere skeleton (not activated, needs `COHERE_API_KEY`)
- Warmup function for cold start

### 3.3 BM25 (`core/rag/bm25.py`)
- Pure Python BM25 implementation (no external deps)
- Multilingual stopwords: ES + EN + CA + IT
- Per-creator singleton via `get_bm25_retriever(creator_id)`
- Pre-built on `load_from_db()` to avoid first-search penalty

### 3.4 Embeddings (`core/embeddings.py`)
- OpenAI `text-embedding-3-small` (1536 dims)
- Cache: `BoundedTTLCache(200, 600s)` — avoids repeated API calls
- `search_similar()`: pgvector cosine distance on `content_embeddings` JOIN `content_chunks`
- Min similarity: 0.35 (env `RAG_MIN_SIMILARITY`), adaptive threshold in context.py

### 3.5 Adaptive Retrieval Gating (`context.py:468-534`)
- **Product signal**: intent is purchase-related OR message contains product keywords
- **Content ref**: message contains "tu post", "tu reel", etc.
- **Dynamic keywords**: extracted from `content_chunks` per creator (cached per process)
- **Universal keywords**: hardcoded set of 30+ ES/CA/EN terms
- **No signal → ZERO retrieval** (casual messages get no RAG overhead)

### 3.6 Knowledge Base (`services/knowledge_base.py`)
- Simple JSON file-based keyword lookup (fallback for ~1-3% of messages)
- NOT the same as `knowledge_base` table — this is a separate `knowledge_bases/{creator_id}.json`
- In context.py, KB is checked independently of RAG after RAG returns

---

## 4. Diagnóstico Profundo

### A) UNIVERSALIDAD — ¿Hardcoded para Iris?

| Componente | Universal? | Detalle |
|-----------|-----------|---------|
| `SemanticRAG` | ✅ YES | Filters by `creator_id`, loads per-creator |
| `reranker.py` | ✅ YES | No creator references |
| `bm25.py` | ✅ YES | Per-creator singletons |
| `embeddings.py` | ✅ YES | `search_similar(creator_id=)` |
| `context.py` gating | ✅ YES | Dynamic keywords per creator from DB |
| `knowledge_base.py` | ✅ YES | Per-creator JSON files |
| **`create_proposition_chunks.py`** | **🔴 BUG-RAG-01: HARDCODED IRIS** | Lines 39-48: `IRIS_CONTEXT_PREFIX`, `IRIS_CREATOR_ID_SLUG`, `IRIS_CREATOR_ID_UUID`. All expertise/objection/values/policies chunks are Iris-specific content. This script CANNOT create chunks for any other creator. |
| `ingestion/v2/pipeline.py` | ✅ YES | Generic website scraping per creator |

### B) INTERACCIÓN — Token Budget Calculation

**RAG context injection (typical):**
- Format: header (65 chars) + 3 results × (~300-500 chars) = **~1000-1600 chars** (250-400 tokens)

**Total context budget with all systems active:**
| Section | Typical Chars | Priority |
|---------|-------------|----------|
| Doc D (style_prompt) | 3000-5000 | CRITICAL |
| Few-shot examples | 800-1500 | CRITICAL |
| Recalling block (DNA+memory+state+episodic) | 500-2000 | HIGH |
| Audio context | 0-500 | HIGH |
| **RAG context** | **900-1600** | **HIGH** |
| KB context | 0-200 | HIGH |
| Hierarchical memory | 0-400 | MEDIUM |
| Advanced prompts | 0-300 | MEDIUM |
| Citation context | 0-200 | MEDIUM |
| **TOTAL** | **5200-11700** | Budget: 8000 |

**Conflict risk**: When Doc D is large (5000 chars) + few-shot (1500) + recalling (2000), that's already 8500 → RAG gets truncated or skipped entirely (line 963-969: only `style`, `recalling`, `rag` are truncated; rest are dropped).

### C) CONSUMO — DB Queries & Latency

| Operation | DB Queries | Latency |
|-----------|-----------|---------|
| `_get_creator_product_keywords()` | 1 (cached per process) | ~50ms first call, 0ms after |
| `generate_embedding()` | 0 (OpenAI API call) | ~100-300ms |
| `search_similar()` (pgvector) | 1 (cosine similarity) | ~50-150ms |
| BM25 search | 0 (in-memory) | ~5-20ms |
| Reranking (local cross-encoder) | 0 (CPU inference) | ~100-200ms |
| **Total RAG pipeline** | **1 DB + 1 API** | **~300-700ms** |

**Cold start**: `load_from_db()` loads up to 500 chunks + builds BM25 indexes. ~500ms-2s.

### D) EDGE CASES

| Case | Behavior | Verdict |
|------|----------|---------|
| 0 chunks for creator | `search()` returns `[]`, cache stores empty, no error | ✅ OK |
| Empty knowledge_base | `kb.lookup()` returns `None` | ✅ OK |
| Query in wrong language | Multilingual embedding (text-embedding-3-small) handles cross-lingual well; BM25 has ES/CA/EN/IT stopwords; reranker is multilingual | ✅ OK |
| OpenAI API down | Falls through to `_fallback_search()` (keyword overlap) | ✅ OK |
| pgvector not available | `search_similar()` returns `[]`, logged as error | ✅ OK |
| Very long query | Truncated at 30000 chars in `generate_embedding()` | ✅ OK |
| No OPENAI_API_KEY | `_embeddings_available = False`, all semantic search returns empty | ⚠️ Silent degradation |

### E) SEGURIDAD — Prompt Injection via RAG Chunks

| Risk | Assessment |
|------|-----------|
| RAG chunks containing instructions | **⚠️ BUG-RAG-02: MEDIUM RISK** — Chunks from scraped websites/IG posts could contain injected instructions. No sanitization of chunk content before prompt injection. `format_rag_context()` blindly inserts `content[:500]` into prompt. |
| SQL injection via embeddings | ✅ SAFE — `CAST(:query AS vector)` uses parameterized queries |
| Embedding string construction | ✅ SAFE — `validated_floats` in `store_embedding()` validates all values |

### F) ASYNC — Blocking Calls

| Call | Blocking? | Fix Needed? |
|------|----------|-------------|
| `agent.semantic_rag.search()` in context.py | **🔴 BUG-RAG-03: YES** — Called synchronously at line 519. Contains `generate_embedding()` (OpenAI API, 100-300ms), `search_similar()` (DB query), reranking (CPU inference). All blocking the event loop. |
| `kb.lookup()` in context.py | ✅ OK — In-memory after first load |
| `_episodic_search()` | ✅ OK — Wrapped in `asyncio.to_thread()` |
| `_get_creator_product_keywords()` | ⚠️ First call is blocking DB query, but cached after |

### G) ERROR HANDLING

| Scenario | Handling | Verdict |
|----------|---------|---------|
| DB down during search | try/except returns `[]` | ✅ OK |
| OpenAI API error | try/except → fallback search | ✅ OK |
| Reranker model load failure | 30s retry cooldown, returns docs as-is | ✅ OK |
| Cohere API failure | Falls back to local reranker | ✅ OK |
| BM25 failure | Returns semantic results only | ✅ OK |
| pgvector not installed | search returns `[]` | ✅ OK |

---

## 5. Bugs Encontrados

### BUG-RAG-01 (P1): `create_proposition_chunks.py` Hardcoded for Iris
**Severity:** P1 — Blocks multi-creator
**File:** `scripts/create_proposition_chunks.py:39-48`
**Issue:** Entire script is hardcoded with Iris context prefix, UUID, and all expertise/objection/values/policies content is Iris-specific. Cannot create chunks for Stefano or any future creator.
**Fix:** Refactor to load creator data from DB and generate contextual prefix dynamically. OR — mark script as deprecated since `ingestion/v2/pipeline.py` + `auto_configurator.py` handle generic chunk creation.

### BUG-RAG-02 (P2): No RAG Chunk Sanitization Against Prompt Injection
**Severity:** P2 — Security
**File:** `core/dm/helpers.py:52`
**Issue:** `format_rag_context()` inserts chunk content directly into prompt with no sanitization. Scraped website content could contain "Ignore all previous instructions..." or similar injection attempts.
**Fix:** Strip common injection patterns from RAG chunks before prompt injection. At minimum, truncate lines that look like instructions (start with "You are", "Ignore", "System:", etc.).

### BUG-RAG-03 (P2): RAG Search is Synchronous in Async Context
**Severity:** P2 — Performance
**File:** `core/dm/phases/context.py:519`
**Issue:** `agent.semantic_rag.search()` runs synchronously in an async function. This includes OpenAI API call (100-300ms) + pgvector DB query + CPU-bound reranking. Blocks the event loop.
**Fix:** Wrap in `asyncio.to_thread()`:
```python
rag_results = await asyncio.to_thread(
    agent.semantic_rag.search,
    rag_query, top_k=agent.config.rag_top_k, creator_id=agent.creator_id
)
```

### BUG-RAG-04 (P3): `_creator_kw_cache` is Unbounded
**Severity:** P3 — Memory leak
**File:** `core/dm/phases/context.py:71`
**Issue:** `_creator_kw_cache: Dict[str, Set[str]] = {}` grows unboundedly. With many creators, each entry holds a set of potentially thousands of keywords.
**Fix:** Use `BoundedTTLCache` like other caches in the codebase.

### BUG-RAG-05 (P3): BM25 `_retrievers` Dict is Unbounded
**Severity:** P3 — Memory leak
**File:** `core/rag/bm25.py:347`
**Issue:** `_retrievers: Dict[str, BM25Retriever] = {}` grows without bound. Each retriever holds the full corpus in memory.
**Fix:** Use `BoundedTTLCache` or limit to N creators.

### BUG-RAG-06 (P3): SemanticRAG Singleton Loads ALL Creators
**Severity:** P3 — Performance/Memory
**File:** `core/rag/semantic.py:456-516`
**Issue:** `load_from_db(creator_id)` is called per search via `get_rag_context()`, but the singleton `_rag_instance` accumulates documents from all creators in `_documents` dict (up to 500 total, not per creator). For many creators, early-loaded creators get evicted.
**Fix:** Already capped at 500, but could be improved with per-creator document tracking.

### BUG-RAG-07 (P3): `get_context_for_response()` Hardcoded Spanish
**Severity:** P3 — i18n
**File:** `core/semantic_memory_pgvector.py:334`
**Issue:** `"CONTEXTO HISTORICO RELEVANTE:"` and `"Usuario"/"Tu"` are hardcoded in Spanish. For English/Italian creators, this is wrong.
**Fix:** Use language-neutral labels or detect language from creator config.

### BUG-RAG-08 (P4): `SessionLocal()` Without Context Manager in Multiple Places
**Severity:** P4 — Robustness
**Files:** `core/rag/semantic.py:469`, `core/embeddings.py:258`, `core/creator_data_loader.py:405`
**Issue:** Uses `SessionLocal()` with manual `try/finally/close()` pattern instead of `get_db_session()` context manager. Risk of session leak on unexpected exceptions.
**Fix:** Replace with `with get_db_session() as db:` pattern.

---

## 6. Investigación Académica (Papers 2024-2026)

### Key Papers & Findings

1. **"Lost in the Middle" (Liu et al., 2023/2024)** — LLMs attend most to start and end of context. RAG chunks placed LAST get highest attention. ✅ Clonnect already does this.

2. **CRAG - Corrective RAG (Yan et al., 2024)** — Self-corrective retrieval: if retrieved docs are irrelevant, triggers web search or generates without retrieval. **Gap:** Clonnect has adaptive threshold but no corrective re-retrieval.

3. **Self-RAG (Asai et al., 2024)** — Model decides when to retrieve, what to retrieve, and whether to use results. **Gap:** Clonnect uses keyword gating (simpler, faster) instead of model-based gating.

4. **Proposition Chunking (Chen et al., 2024)** — Atomic proposition chunks (self-contained facts) outperform fixed-size chunks for QA. ✅ Clonnect implements this via `create_proposition_chunks.py`.

5. **Contextual Retrieval (Anthropic, 2024)** — Prepending document context to chunks before embedding improves retrieval by 35-49%. ✅ **IMPLEMENTED**: Universal `build_contextual_prefix()` in `core/contextual_prefix.py` replaces hardcoded `IRIS_CONTEXT_PREFIX`. Auto-generates prefix from any creator's DB profile.

6. **Hybrid Search (RRF)** — Multiple papers confirm semantic+BM25 with RRF fusion outperforms either alone for multilingual queries. ✅ Clonnect implements this.

7. **Cross-Encoder Reranking** — Consistently improves precision by 5-15% at cost of 100-200ms. Multilingual models (mmarco) essential for non-English. ✅ Clonnect uses multilingual reranker.

8. **Adaptive Retrieval Gating** — Papers show 30-50% of conversational turns don't need retrieval (greetings, acknowledgments). Gating saves latency and avoids noise injection. ✅ Clonnect implements intent-based + keyword-based gating.

9. **RAG for Persona-based Chatbots (RoleLLM, ACL 2024)** — RAG can help maintain character consistency by retrieving persona-relevant facts, but over-retrieval dilutes character voice. ⚠️ Clonnect should monitor RAG's effect on persona fidelity.

10. **Temporal Decay in Retrieval** — Freshness boosting prevents stale information from dominating. ✅ Implemented in `semantic_memory_pgvector.py` for episodic memory (0.7 + 0.3 * recency over 90 days). Not implemented for content RAG (content chunks don't have temporal relevance).

---

## 7. Gap Analysis vs Papers/Repos

| Feature | Papers Recommend | Clonnect Status | Priority |
|---------|-----------------|----------------|----------|
| Adaptive retrieval gating | ✅ Essential | ✅ Implemented (keyword + intent) | Done |
| Hybrid search (semantic + BM25) | ✅ Essential | ✅ Implemented (RRF 0.7/0.3) | Done |
| Cross-encoder reranking | ✅ Beneficial (+5-15% precision) | ✅ Implemented (multilingual) | Done |
| Proposition chunking | ✅ Best practice | ⚠️ Only for Iris | P1 |
| Contextual embedding (Anthropic) | ✅ +35-49% retrieval quality | ✅ **IMPLEMENTED** universal prefix | Done |
| Corrective RAG (re-retrieval) | 🔬 Advanced | ❌ Not implemented | P4 |
| Self-RAG (model-based gating) | 🔬 Advanced, expensive | ❌ Keyword-based instead | P4 (OK as-is) |
| Source-type routing | ✅ Essential for multi-source | ✅ Implemented | Done |
| Token budget management | ✅ Essential | ✅ 8000 char budget + priority truncation | Done |
| RAG chunk sanitization | ✅ Security essential | ✅ **FIXED** `_sanitize_rag_content()` | Done |
| Async RAG pipeline | ✅ Performance essential | ✅ **FIXED** `asyncio.to_thread()` | Done |
| Per-creator contextual prefix | ✅ +35-49% quality | ✅ **IMPLEMENTED** `build_contextual_prefix()` | Done |

---

## 8. Resumen de Calidad

| Dimensión | Score | Notas |
|-----------|-------|-------|
| Arquitectura | 8/10 | Excelente pipeline de 4 pasos (semantic → BM25 → rerank → boost). Bien diseñado. |
| Universalidad | 6/10 | Pipeline runtime es universal, pero ingestion de chunks (proposition) es solo Iris |
| Rendimiento | 7/10 | Cache agresivo, adaptive gating bueno. BUG: blocking async |
| Seguridad | 6/10 | SQL injection safe. RAG content injection risk (P2) |
| Robustez | 8/10 | Graceful degradation everywhere. Fallbacks for each component |
| Escalabilidad | 7/10 | Per-creator isolation. Memory leaks in caches (P3) |
| TOTAL | **7.0/10** | Muy buen sistema con gaps claros: universalidad de chunks y async |

---

## 9. Plan de Fixes

### P1 — Critical
- [ ] **BUG-RAG-01**: Universalizar `create_proposition_chunks.py` o marcar como deprecated en favor de `ingestion/v2/pipeline.py` que ya es universal

### P2 — Important
- [ ] **BUG-RAG-02**: Sanitizar RAG chunks contra prompt injection
- [ ] **BUG-RAG-03**: Envolver RAG search en `asyncio.to_thread()`

### P3 — Maintenance
- [ ] **BUG-RAG-04**: Reemplazar `_creator_kw_cache` con `BoundedTTLCache`
- [ ] **BUG-RAG-05**: Reemplazar `_retrievers` dict con bounded cache
- [ ] **BUG-RAG-07**: Internacionalizar labels de episodic memory

### P4 — Nice to have
- [ ] **BUG-RAG-06**: Tracking per-creator de documentos en SemanticRAG
- [ ] **BUG-RAG-08**: Migrar `SessionLocal()` a `get_db_session()` context manager
