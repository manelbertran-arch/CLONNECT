# Auditoría Forense — Sistema #9: Memory Engine

**Fecha:** 2026-04-01
**Archivos auditados:**
- `services/memory_engine.py` (1651 líneas) — Motor principal (MemoryEngine)
- `services/memory_service.py` (570 líneas) — Servicio legacy (MemoryStore + ConversationMemoryService)
- `services/context_memory_service.py` (219 líneas) — Contexto básico (ContextMemoryService)
- `services/bot_orchestrator.py` — Integra ConversationMemoryService
- `core/dm/phases/context.py:257-280` — Punto de inyección recall()
- `core/dm/phases/postprocessing.py:425-443` — Punto de extracción add()
- `core/cache.py:193-252` — BoundedTTLCache

---

## 1. ARQUITECTURA

### Tres sistemas de memoria coexisten:

| Sistema | Archivo | Storage | Estado |
|---------|---------|---------|--------|
| **MemoryEngine** (Sistema #9) | `services/memory_engine.py` | PostgreSQL + pgvector (`lead_memories`, `conversation_summaries`) | Feature-flagged (`ENABLE_MEMORY_ENGINE`), OFF por defecto |
| **ConversationMemoryService** (legacy) | `services/memory_service.py` | JSON files (`data/conversation_memory/`) | Activo via BotOrchestrator |
| **ContextMemoryService** | `services/context_memory_service.py` | Reads from DB (messages table) | Activo, read-only |

### MemoryEngine — Flujo completo:

```
WRITE PATH (postprocessing.py:431-443):
  Message pair (user + assistant) → asyncio.create_task(mem_engine.add())
    → _extract_facts_via_llm() [Gemini Flash-Lite]
    → _generate_embeddings_batch() [OpenAI embeddings]
    → resolve_conflict() [Jaccard + pgvector dedup]
    → _store_fact() [INSERT lead_memories]
    → summarize_conversation() [INSERT conversation_summaries]

READ PATH (context.py:257-266):
  recall(creator_id, sender_id, message)
    → BoundedTTLCache check (500 entries, 60s TTL)
    → search() [pgvector cosine similarity, top 10]
    → _get_compressed_memo() [COMEDY narrative memo]
    → _get_latest_summary()
    → _format_memory_section() [max 3000 chars]
    → Injected into prompt as "=== MEMORIA DEL LEAD ==="
```

### Qué recuerda:
- **Facts** (6 tipos): preference, commitment, topic, objection, personal_info, purchase_history
- **Conversation summaries**: resumen + key_topics + commitments + sentiment
- **Compressed memo** (COMEDY-style): narrative summary of all facts when count > 8

### Cómo se almacena:
- **PostgreSQL** table `lead_memories` with `pgvector` extension
- Columns: id, creator_id, lead_id, fact_type, fact_text, fact_embedding (vector), confidence, source_type, times_accessed, last_accessed_at, is_active, superseded_by
- `conversation_summaries` table: summary_text, key_topics (jsonb), commitments_made (jsonb), sentiment

### Cómo se recupera:
- **Semantic search**: pgvector cosine similarity (`1 - (embedding <=> query)`) with min_similarity=0.4
- **Fallback**: recency-based (most recent active facts)
- **Compressed memo**: separate query, prepended to results

### Tokens inyectados:
- Max ~750 tokens (3000 chars) via `_format_memory_section(max_chars=3000)`
- With compressed memo: memo text + up to 3 pending commitments
- Without memo: sorted facts by priority (commitment > preference > objection > personal_info > purchase_history > topic)

---

## 2. BUGS ENCONTRADOS

### BUG-MEM-01: `_recall_cache_ts` — NameError en forget_lead() [SEVERITY: HIGH]

**Archivo:** `services/memory_engine.py:696`

```python
_recall_cache.pop(cache_key, None)
_recall_cache_ts.pop(cache_key, None)  # ← NameError: _recall_cache_ts is not defined
```

`_recall_cache_ts` es un vestigio del cache antiguo (pre-BoundedTTLCache). La migración a BoundedTTLCache (session 31-Mar) eliminó el dict `_recall_cache_ts` pero olvidó esta referencia en `forget_lead()`.

**Impacto:** GDPR forget_lead() falla con NameError, no puede borrar memorias.

**Fix:** Eliminar la línea 696 (`_recall_cache_ts.pop(cache_key, None)`).

### BUG-MEM-02: sync DB in async context — _resolve_creator_uuid / _resolve_lead_uuid [SEVERITY: MEDIUM]

**Archivo:** `services/memory_engine.py:188-250`

Both resolution methods use `SessionLocal()` synchronously inside async coroutines (`add()`, `recall()`, `search()`). This blocks the event loop during DB queries.

**Impacto:** Latency spike on every memory operation. In high-concurrency scenarios, could starve the event loop.

**Fix:** Use `asyncio.to_thread()` or make them async with `await asyncio.to_thread(self._resolve_creator_uuid, creator_id)`.

### BUG-MEM-03: All DB operations are sync inside async methods [SEVERITY: MEDIUM]

**Archivo:** `services/memory_engine.py` — every `_store_fact()`, `_pgvector_search()`, `_get_existing_active_facts()`, `_update_access_counters()`, etc.

All use `SessionLocal()` synchronously. The entire MemoryEngine blocks the event loop on every DB call.

**Fix:** Wrap all DB calls in `asyncio.to_thread()` or use async SQLAlchemy sessions.

### BUG-MEM-04: Memory extraction uses only LAST 2 messages [SEVERITY: LOW]

**Archivo:** `services/memory_engine.py` / `core/dm/phases/postprocessing.py:435-441`

```python
conversation_msgs = [
    {"role": "user", "content": message},
    {"role": "assistant", "content": formatted_content},
]
asyncio.create_task(mem_engine.add(agent.creator_id, sender_id, conversation_msgs))
```

Only the current message pair is sent for extraction. The LLM sees 2 messages, making it hard to extract multi-turn context. The extraction prompt says "conversación" but gets 1 exchange.

**Impacto:** Facts that require multi-turn context are missed. E.g., "me interesa el retiro" (msg 1) → "el de Bali?" (msg 2) → "sí, ese" (msg 3) — only msg 3 + response sent.

**Recommendation:** Send last 6-10 messages from conversation history, not just the current pair.

### BUG-MEM-05: ContextMemoryService has hardcoded location/activity patterns [SEVERITY: LOW]

**Archivo:** `services/context_memory_service.py:146-173`

```python
patterns = {
    "location_mentioned": ["barcelona", "madrid", "argentina", "españa", "brazil", "italia"],
    "activity_mentioned": ["yoga", "gym", "entrenar", "clase", "sesión", "evento", "retiro"],
    ...
}
```

Hardcoded to iris_bertran's domain. Not universal for other creators.

### BUG-MEM-06: ConversationMemoryService uses JSON files, not DB [SEVERITY: INFO]

**Archivo:** `services/memory_service.py:162-192`

`MemoryStore` persists to `data/followers/` as JSON files. On Railway (ephemeral filesystem), these files are lost on every deploy. The BotOrchestrator still uses this.

**Impacto:** BotOrchestrator's memory (interests, objections, purchase_intent_score) is lost on deploy. The MemoryEngine (pgvector) survives deploys because it uses PostgreSQL.

### BUG-MEM-07: MemoryStore cache is unbounded [SEVERITY: LOW]

**Archivo:** `services/memory_service.py:179`

```python
self._cache: Dict[str, FollowerMemory] = {}
```

Unlike MemoryEngine which uses BoundedTTLCache, MemoryStore uses a plain dict. With many leads, this grows without bound.

### BUG-MEM-08: decay_memories() counter bug [SEVERITY: LOW]

**Archivo:** `services/memory_engine.py:730,778`

```python
deactivated = temporal_expired  # initialized from temporal
...
if ids_to_deactivate:
    ...
    deactivated = len(ids_to_deactivate)  # ← OVERWRITES temporal_expired instead of adding
```

Should be `deactivated += len(ids_to_deactivate)`.

---

## 3. BoundedTTLCache fix — VERIFIED

**Session 31-Mar fix applied correctly:**
- `services/memory_engine.py:48-51`: Uses `BoundedTTLCache(max_size=500, ttl_seconds=60)` ✅
- Old unbounded dict cache eliminated ✅
- Configurable via env vars: `MEMORY_RECALL_CACHE_MAX_SIZE`, `MEMORY_RECALL_CACHE_TTL` ✅

---

## 4. UUID cast failures — VERIFIED

**Session 29-Mar fix applied:**
- `_resolve_creator_uuid()` (line 188): tries UUID parse first, falls back to slug lookup ✅
- `_resolve_lead_uuid()` (line 215): tries UUID parse first, falls back to platform_user_id with prefix variants (ig_, wa_, tg_) ✅
- Both methods have try/except with fallback ✅

---

## 5. PAPERS & REPOS — LITERATURE REVIEW

### 5.1 COMEDY: COMpressivE Memory for Dialogue sYstems (COLING 2025)

**Architecture:** Per-session summaries capturing events + user/bot portraits → compressed into a single cross-session memory capped at 500 words containing user profile, relationship dynamics, and condensed event timeline.

**Compression trigger:** After 15+ sessions accumulate for a user-bot pair. Uses GPT-4-Turbo (temp=0.9, 3x generations for diversity). Then trains a single model via mixed-task SFT (LR 1e-5, batch 32, 2 epochs) + DPO (beta=0.1).

**Retrieval:** No explicit retrieval — compressed memory is concatenated directly into the prompt. Avoids retrieval failures but limits total memory to ~500 words.

**Result:** Outperformed RAG-based baselines (top-k=3 retrieval) on Dolphin benchmark. "One model does everything" approach was key.

**Our implementation:** `compress_lead_memory()` creates narrative memos via LLM. Gap: was never auto-triggered. **Now fixed:** auto-triggers in `add()` when fact_count >= 8.

### 5.2 MemGPT / Letta (NeurIPS 2023 Workshop) — 12K+ stars

**Tiered memory:**
1. **Core memory** — Named editable text blocks (`human`, `persona`), 5000-char limit each, always in system prompt. Updated via `core_memory_append`/`core_memory_replace`.
2. **Recall storage** — Full conversation history (out-of-context DB), searchable via `conversation_search()` with date/role filters.
3. **Archival storage** — Persistent knowledge base, embedding-indexed, via `archival_memory_insert()`/`archival_memory_search()`.

**Key design:** The LLM itself decides when to save/retrieve memories via tool calls. System prompt instructs it about limited context. FIFO eviction on conversation buffer; running summary maintained in-context.

**Our mapping:** prompt injection (3000 chars) ≈ core memory, `lead_memories` table ≈ archival, pgvector search ≈ archival_memory_search. **Gap:** Our LLM can't explicitly request/save memories — it's passive.

### 5.3 mem0 (25K+ stars)

**Two-pass extraction pipeline:**
1. LLM extracts atomic facts (`FACT_RETRIEVAL_PROMPT`, 7 categories)
2. Vector-search top-5 existing memories per fact
3. Second LLM call classifies each as **ADD / UPDATE / DELETE / NONE** (`DEFAULT_UPDATE_MEMORY_PROMPT`)

**Storage:** Dual — vector store (Qdrant/pgvector, 1536-dim) + optional Neo4j graph (entity-relationship triples). Graph uses BM25 reranking, not vector search.

**Conflict resolution:** LLM compares new vs existing, uses integer IDs (mapped from UUIDs to prevent hallucination). Rule: "if same fact, keep the one with more information."

**No decay/eviction** — memories persist until LLM explicitly DELETEs them.

**Our comparison:** We do 1-pass extraction (cheaper). Our dedup uses Jaccard + embedding (no second LLM call). mem0's approach is more accurate but 2x the LLM cost per extraction. For our volume (~1K msgs/day), our approach is sufficient.

### 5.4 Episodic vs Semantic Memory (2024-2025)

**Recommended split:** Episodic stores raw interaction contexts. Semantic stores extracted facts/preferences.

**Consolidation approaches:**
- SimpleMem (2026): recursive consolidation — related episodic units merged into higher-level abstractions (inspired by biological sleep consolidation)
- MemRL (2026): stores intent-experience-utility triplets, RL learns which episodes to retain/compress
- Practical heuristic: track memory "strength" (recency × access frequency) + "importance" (LLM-scored salience)

**Our coverage:** MemoryEngine = semantic memory, `_episodic_search` = episodic memory. Both implemented behind separate flags. Key gap: no automatic consolidation from episodic → semantic (would require a batch job).

### 5.5 Memory-Augmented Persona Agents (2024-2025)

**Key insight (MindMemory 2025, O-Mem):** Keep persona immutable in core memory, update user knowledge in a separate mutable store. Systems that mix persona + user facts show drift.

**Our implementation:** Persona = Compressed Doc D (immutable system prompt). User facts = MemoryEngine (mutable per-lead). This matches the recommended architecture.

---

## 6. COMPARISON TABLE — Our System vs State of the Art

| Aspect | Our MemoryEngine | mem0 | MemGPT/Letta | COMEDY |
|--------|-----------------|------|--------------|--------|
| Extraction | 1-pass LLM (6 types) | 2-pass LLM (extract → reconcile) | Agent tool calls | Mixed-task SFT |
| Storage | pgvector (facts + embeddings) | Vector + Neo4j graph | PostgreSQL + pgvector (tiered) | In-context only (500w) |
| Retrieval | Cosine similarity (min 0.4) | Vector + BM25 reranking | Hybrid search + date filters | No retrieval (concat all) |
| Compression | COMEDY-style memo (**now auto-triggered**) | None (append-only) | Context overflow → summarize | After 15+ sessions |
| Decay | Ebbinghaus (30d half-life, access-scaled) | None | FIFO eviction | None |
| Dedup | Jaccard + embedding (2-pass) | LLM ADD/UPDATE/DELETE | Agent str_replace | None |
| Persona separation | Doc D (immutable) + facts (mutable) | N/A | Core blocks + archival | Compressive memory |
| GDPR | `forget_lead()` deletes all | Manual delete | N/A | N/A |
| Temporal facts | 7-day TTL with multilingual markers | None | None | None |
| Cost per message | 1 LLM call (extraction) | 2 LLM calls (extract + reconcile) | 0 extra (agent decides) | 0 (pre-trained model) |

### Ebbinghaus Decay Calibration Analysis

Our formula: `effective_confidence = confidence * exp(-0.693 * days / (30 * (1 + times_accessed)))`

| Scenario | Half-life | Days to deactivation (conf < 0.1) |
|----------|-----------|-----------------------------------|
| Fact accessed 0 times (conf=0.7) | 30 days | ~87 days |
| Fact accessed 3 times (conf=0.7) | 120 days | ~347 days |
| Fact accessed 10 times (conf=0.9) | 330 days | ~1070 days |
| Commitment (conf=0.8, 0 access) | 30 days | ~90 days |

**Assessment:** Well-calibrated for our use case. Unaccessed facts fade in ~3 months. Frequently accessed facts (e.g., "Le interesa yoga") persist for years. Temporal facts expire independently via TTL (7 days). No change needed.

---

## 7. OPTIMIZATIONS IMPLEMENTED

### OPT-1: Auto-trigger COMEDY compression (**IMPLEMENTED**)
After `add()` stores new facts, automatically checks total active fact count. If >= MEMO_COMPRESSION_THRESHOLD (8), fires `compress_lead_memory()` as `asyncio.create_task()` (non-blocking).

**Location:** `services/memory_engine.py`, inside `add()`, after cache invalidation.

### OPT-2: Multi-turn extraction (**IMPLEMENTED** — BUG-MEM-04)
Fact extraction now receives last 3 messages from conversation history + current pair (5 messages total), instead of only the current pair (2 messages).

### OPT-3: Async DB operations (**IMPLEMENTED** — BUG-MEM-03)
19 sync DB methods wrapped in `asyncio.to_thread()`. Estimated latency reduction: 20-50ms per operation.

### Decided NOT to implement:

| Opportunity | Reason |
|-------------|--------|
| mem0-style 2-pass reconciliation | 2x LLM cost per message. Our Jaccard + embedding dedup is sufficient for current volume. |
| MemGPT-style agent-controlled memory | Would require exposing memory tools to Qwen3-14B. Risk of hallucinated memory ops. Not worth the complexity. |
| Graph memory (Neo4j entities) | Adds infrastructure dependency. Entity relationships are captured adequately in fact text. |
| UUID resolution caching | Adds ~10ms. Fast path already skips DB for valid UUIDs. Not worth the complexity. |

---

## 8. FUNCTIONAL TESTS (10/10)

All tests in `tests/test_memory_engine_bugs.py`:

| # | Test | Bug/Feature | Result |
|---|------|-------------|--------|
| 1 | `_resolve_creator_uuid` is async | BUG-MEM-02 | PASS |
| 2 | `_resolve_lead_uuid` is async | BUG-MEM-02 | PASS |
| 3 | All DB methods use `asyncio.to_thread` (19 found) | BUG-MEM-03 | PASS |
| 4 | Postprocessing passes history to extraction | BUG-MEM-04 | PASS |
| 5 | `context_memory_service.py` deleted (no hardcoded patterns) | BUG-MEM-05 | PASS |
| 6 | ConversationMemoryService persists to DB | BUG-MEM-06 | PASS |
| 7 | MemoryStore uses BoundedTTLCache | BUG-MEM-07 | PASS |
| 8 | `_recall_cache_ts` fully removed | BUG-MEM-01 | PASS |
| 9 | Decay counter uses `+=` | BUG-MEM-08 | PASS |
| 10 | UUID resolution fast-paths for valid UUIDs | BUG-MEM-02 | PASS |

---

## 9. SUMMARY — ALL FIXES

| Priority | Bug | Impact | Effort | Status |
|----------|-----|--------|--------|--------|
| 🔴 P0 | BUG-MEM-01: `_recall_cache_ts` NameError | GDPR forget fails | 1 line delete | **FIXED** (session 1) |
| 🟡 P1 | BUG-MEM-03: Sync DB in async context | Event loop blocking | Medium (wrap in to_thread) | **FIXED** — 19 methods wrapped |
| 🟡 P1 | BUG-MEM-04: Only 2 messages for extraction | Poor fact quality | Small (pass history) | **FIXED** — passes last 3 from history + current pair |
| 🟢 P2 | BUG-MEM-08: decay counter overwrites | Incorrect decay stats | 1 line fix | **FIXED** (session 1) |
| 🟢 P2 | BUG-MEM-02: Sync UUID resolution | Latency spike | Small | **FIXED** — both resolve methods now async |
| ⚪ P3 | BUG-MEM-05: Hardcoded patterns | Not universal | Remove or make dynamic | **RESOLVED** — file deleted |
| ⚪ P3 | BUG-MEM-06: JSON persistence on Railway | Data loss on deploy | Migrate to DB | **FIXED** — DB-first with JSON fallback |
| ⚪ P3 | BUG-MEM-07: Unbounded MemoryStore cache | Memory growth | Use BoundedTTLCache | **FIXED** — BoundedTTLCache(500, 600s) |

---

## 10. MEMORY INJECTION REDESIGN v3 (2026-04-02)

### Problem
L1 metric 6/6/6 but human evaluation 1.4/5 ("¿enviarías esta respuesta?"). Model received 600-863 chars of memory but IGNORED it in 5/5 test cases.

### Root Causes
1. **Prose format** (3000 chars max, `=== MEMORIA DEL LEAD ===` markers) — unparseable by 14B model
2. **No explicit usage instruction** — only "usa esta info naturalmente"
3. **Memory in MIDDLE** of 8000-char prompt — Lost in the Middle effect (Liu 2023)
4. **Anti-echo accent bug** — Catalan accented text bypassed Jaccard (0.6 instead of 1.0)
5. **Echo threshold too high** (0.70) — semantic echoes (rephrased) scored 0.64 and passed

### Research Base (18 papers, 6 repos)

**Papers:**
| Paper | Year | Venue | Key Finding for Memory Format |
|-------|------|-------|-------------------------------|
| COMEDY | 2025 | COLING | Compressive memory > retrieval. Single model pipeline eliminates ignore problem |
| SeCom | 2025 | ICLR | Segment-level + compression-as-denoising. Turn-level too noisy, session too coarse |
| RMM | 2025 | ACL | RL-based retrieval + citation requirements. Model must cite what it uses |
| MRPrompt | 2026 | arXiv | Explicit 4-stage protocol required. "Card format alone does not reliably improve" |
| Mem0 | 2025 | arXiv | k≤2 memories optimal, k>2 HURTS. Bulleted list format |
| Zep/Graphiti | 2025 | arXiv | XML-tagged facts with timestamps. 18.5% accuracy improvement |
| MemGPT/Letta | 2024 | ICLR | XML blocks `<persona>`, `<human>`. Self-editing via function calls |
| MemoryBank | 2024 | AAAI | Ebbinghaus decay. Only reinforced memories surface |
| A-MEM | 2025 | NeurIPS | Zettelkasten-style notes with keywords, tags, embeddings |
| LIGHT | 2025 | arXiv | Scratchpad compressed to 15k tokens. Full context NOT the answer |
| LOCOMO | 2024 | ACL | LLMs struggle with 600-turn conversations. RAG + long-context both lag humans |
| Lost in the Middle | 2024 | TACL | U-shaped attention. Begin/end positions >> middle. 30%+ accuracy drop in middle |
| Context Rot | 2025 | Chroma | Focused 300 tokens >> unfocused 113K tokens. Degradation at ALL lengths |
| LongLLMLingua | 2024 | ACL | 4x compression → 21.4% BOOST. Less tokens = better performance |
| CoALA | 2024 | TMLR | Memory must be actively managed, not passively injected |
| Caffeine | 2024 | EACL | Commonsense expansion + contradiction resolution > raw accumulation |
| Persona Drift | 2024 | COLM | Persona drift measurable in 8 turns. Split-softmax attention fix |
| Fixed-Persona SLMs | 2025 | arXiv | Fine-tune style into weights, inject only facts at runtime |

**Repos:**
| Repo | Stars | Memory Format | Key Technique |
|------|-------|---------------|---------------|
| mem0ai/mem0 | 25K | `- fact` bulleted list | k≤2 retrieval, explicit "leverage memories" instruction |
| letta-ai/letta | 22K | XML `<persona>`, `<human>` blocks, 20K char limits | Self-editing via tools, "immerse in persona" |
| getzep/zep | 2K | `<FACTS>...</FACTS>` + `<ENTITIES>...</ENTITIES>` | Temporal metadata, step-by-step analysis instructions |
| langchain | 100K | `Context: {entities}` section | EntityMemory: proper noun extraction + summarization |
| llama_index | 40K | `----context----` separator | ChatMemoryBuffer: 3K token default |
| long-memory-character-chat | 25 | 3-tier (short/mid/long-term) | **Style exemplar**: first response stored as voice reference |

### Changes Implemented (v3)

| # | Change | Research Basis | File |
|---|--------|---------------|------|
| 1 | `<memoria>...</memoria>` XML tags + `- fact` bullets | mem0, Zep, Letta | `services/memory_engine.py` |
| 2 | `Nombre: X` line via universal regex name extraction | LangChain EntityMemory | `services/memory_engine.py` |
| 3 | `Instrucción: Responde usando la info de <memoria>.` | MRPrompt, Zep | `services/memory_engine.py` |
| 4 | Memory at END of recalling block | Lost in the Middle, Context Rot | `core/dm/phases/context.py` |
| 5 | Max 600 chars, 5 facts (was 3000, 10) | Mem0: k>2 hurts. Chroma: focused wins | `services/memory_engine.py` |
| 6 | Echo threshold 0.55 (was 0.70), env-configurable | Semantic echo at 0.64 missed | `core/dm/phases/postprocessing.py` |
| 7 | Accent normalization `unicodedata.normalize('NFD')` | Catalan text bypass fix | `core/dm/phases/postprocessing.py` |

### Example Output (v3)
```
<memoria>
Nombre: Marta
- Marta, una clienta interesada en asistir a la clase de hoy, busca coordinar una cita
- El lead confirmó su asistencia para mañana. [PENDIENTE]
- El lead dijo que vendra a las 13:30 [PENDIENTE]
</memoria>
Instrucción: Responde usando la info de <memoria>. No la repitas textual.
```

### 5-Case Comparison

| Case | v0 (original) | v3 (new) | Iris Real | Improved? |
|------|--------------|----------|-----------|-----------|
| 1: Frustrated cuñado | "Tramposa 😂" (OFFENSIVE) | "Crec que el crack ho solucionarà 😊" | "Iñaki pot agafar un taxi" | YES — not offensive, uses "crack" from memory |
| 2: Si scheduling | "Ja, què?" (IGNORES memory) | "Ens veiem demà a les 13:30?" | "A les 13h ens veiem! 🙌" | YES — uses time+name from memory |
| 3: Echo | Verbatim echo (MISSED) | Caught by 0.55 threshold (J=0.636) | "Exacte, sense compromís" | YES — echo now detected |
| 4: Cuca intimate | "Ja, gràcies" (NONSENSICAL) | "Descansa i beu aigua" | "Prenet un ibuprofè 💊" | YES — empathetic, relevant |
| 5: Audio | "Ja va ser?" (MEANINGLESS) | "Ah, crack! Què tal?" | "No he pogut escoltar l'àudio!" | PARTIAL — audio handling is separate bug |

### Remaining Gaps

1. **Audio transcription** — Case 5 needs separate audio handling (not a memory problem)
2. **Style exemplar** — long-memory-character-chat pattern (store first response as voice reference) could further reduce vocabulary drift
3. **Semantic echo detection** — Papers recommend BERTScore (0.829 balanced acc) over Jaccard (0.711). Current 0.55 threshold is interim fix. Potential false positives on short agreeing messages.
4. **Persona drift** — Li et al. (COLM 2024) measures drift in 8 turns. Split-softmax attention fix or periodic style re-anchoring could help.

### Tests
- 37/37 `test_memory_engine.py` pass (including new `test_name_extraction`)
- 7/7 smoke tests pass
- `test_echo_sprint4.py` assertion updated for new format
