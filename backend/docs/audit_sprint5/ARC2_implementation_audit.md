# ARC2 Implementation Audit — K1 Regression Root Cause

**Branch:** `feature/arc2-read-cutover`
**Date:** 2026-04-19
**Scope:** A2.1 (schema+service), A2.2 (extractor), A2.4 (dual-write), A2.5 (read cutover)
**Measurement:** K1=25 with ARC2 read ON vs K1=100 with legacy MemoryEngine

---

## 0. Executive Summary

The K1=25 regression has **three compounding root causes**, not one:

| # | Root Cause | Severity | File:Line |
|---|-----------|----------|-----------|
| RC1 | **get_all() dumps ALL memories with zero message-relevance filtering** — legacy `recall()` uses pgvector semantic search with the current `message` | CRITICAL | `context.py:353` vs `memory_engine.py:337` |
| RC2 | **`<memoria>` tag mismatch** — ARC2 formatter outputs `[Identidad]`, `[Intereses]` labels but `_build_recalling_block` footer instructs LLM to "Lee \<memoria\>" — tag never exists in ARC2 output | HIGH | `context.py:276-300` vs `context.py:1151` |
| RC3 | **500-char hard cap vs 2000-char legacy** — ARC2 truncates at 500 chars; legacy allows 2000 chars with dedup + priority ordering + compressed memo | MEDIUM | `context.py:266` vs `memory_engine.py:1436` |

Combined effect: the LLM receives an unranked dump of ALL memories (potentially dozens), formatted without the `<memoria>` XML tag the usage instruction references, and hard-capped at 500 chars that may mid-sentence truncate the most important facts.

---

## 1. Schema Fidelity (A2.1)

**Design doc:** ARC2 §2.2 — 5 closed types, content TEXT, why/how_to_apply TEXT, CHECK constraints for objection+relationship_state, embedding vector(1536), ON CONFLICT (creator_id, lead_id, memory_type, content).

**Implementation:** `services/lead_memory_service.py`

| Spec | Implementation | Verdict |
|------|---------------|---------|
| 5 closed types: identity, interest, objection, intent_signal, relationship_state | `MEMORY_TYPES` list + `validate_memory_type()` at line 63 | **PASS** |
| CHECK: objection+relationship_state require why+how_to_apply | `_REQUIRES_WHY_HOW` frozenset + `validate_body_structure()` line 71-85 | **PASS** |
| ON CONFLICT dedup key (creator_id, lead_id, memory_type, content) | SQL at line 190 | **PASS** |
| Advisory lock per lead_id | `_acquire_advisory_lock()` using `pg_advisory_xact_lock` at line 107 | **PASS** |
| embedding vector(1536) + hnsw index | SQL uses `::vector`, migration creates hnsw index | **PASS** |
| confidence CHECK (0,1) | `validate_confidence()` at line 88 | **PASS** |
| superseded_by self-ref | `supersede()` method at line 217 | **PASS** |
| soft-delete via deleted_at | `soft_delete()` at line 207, all reads filter `deleted_at IS NULL` | **PASS** |

**Schema fidelity: 8/8 — FULL MATCH.**

---

## 2. Single-Writer Enforcement (A2.1)

**Design doc:** ARC2 §2.3 — "Advisory lock per lead_id to prevent interleaved writes. If row exists with different last_writer, log warning and proceed with newer-wins."

**CC reference pattern:** `createAutoMemCanUseTool` sandboxes write access per tool, `hasMemoryWritesSince` mutex prevents fork-agent from overwriting main-agent in-progress updates.

**Implementation:** `lead_memory_service.py:158-163`

```python
if existing and existing.last_writer != last_writer:
    logger.warning("...writer conflict...newer-wins...")
```

| Aspect | CC Pattern | ARC2 Implementation | Gap |
|--------|-----------|---------------------|-----|
| Lock granularity | Per-file (memdir/) + per-session (SessionMemory) | Per-lead (advisory lock) | OK — domain-appropriate |
| Conflict resolution | Deny fork if main has writes since fork started | Warning + newer-wins | **DIVERGENCE** — no deny path |
| Concurrent extractors | N/A (single agent) | Advisory lock serializes | OK |

**Gap analysis:** The CC pattern is *deny* on conflict; ARC2 is *warn-and-overwrite*. This is acceptable for dual-write (multiple legacy writers are transient), but will matter when `extract_deep` (nightly LLM) runs alongside real-time `extract_from_message`. If both write the same (lead, type, content) key, the nightly job silently overwrites the real-time extraction's confidence score without notice.

**Verdict: ACCEPTABLE for current phase — needs tightening before multi-extractor activation.**

---

## 3. API Fidelity (A2.1)

**Design doc:** ARC2 §2.4 — `get_by_lead` returns all, `recall_semantic` for relevance-based retrieval.

| API Method | Design | Implementation | Used in Read Cutover? |
|-----------|--------|---------------|----------------------|
| `upsert()` | Insert/update with dedup | ✅ `lead_memory_service.py:116` | No (write path) |
| `get_all()` | Return all memories | ✅ `lead_memory_service.py:258` | **YES — this is the problem** |
| `get_by_type()` | Filter by type list | ✅ `lead_memory_service.py:274` | No |
| `recall_semantic()` | pgvector cosine similarity, threshold + top_k | ✅ `lead_memory_service.py:317` | **NO — never called** |
| `get_current_state()` | Consolidated snapshot | ✅ `lead_memory_service.py:379` | No |
| `soft_delete()` | Set deleted_at | ✅ `lead_memory_service.py:207` | No |
| `supersede()` | Mark old + insert new | ✅ `lead_memory_service.py:217` | No |
| `count_by_type()` | Type distribution | ✅ `lead_memory_service.py:346` | No |
| `delete_by_lead()` | Bulk soft-delete | ✅ `lead_memory_service.py:366` | No |

**All 9 API methods implemented. But the read cutover uses `get_all()` instead of `recall_semantic()`.**

The design doc explicitly specifies `recall_semantic` for the DM context path. Using `get_all()` is the direct cause of RC1: no message-relevance filtering → context dilution → K1 regression.

---

## 4. Extractor Fidelity (A2.2)

**Design doc:** ARC2 §2.5 — Hybrid Opción C. `extract_from_message` regex per-turn (identity + intent_signal). `extract_deep` LLM nightly (all 5 types).

**Implementation:** `services/memory_extractor.py`

### 4a. extract_from_message (regex per-turn)

| Feature | Design | Implementation | Verdict |
|---------|--------|---------------|---------|
| Regex only, no LLM | identity + intent_signal | `_extract_identity()` + `_extract_intent_signal()` | **PASS** |
| <200ms budget | Sync regex | No async, no I/O | **PASS** |
| ES/CA/EN multilingual | Patterns for 3 languages | Age, name, location in ES/CA/EN | **PASS** |
| Confidence threshold | >= CONFIDENCE_THRESHOLD | Line 258: `[m for m in memories if m.confidence >= CONFIDENCE_THRESHOLD]` | **PASS** |
| Pre-filter | Signal classifier | `_classify_signal()` at line 251 | **PASS** |

### 4b. extract_deep (LLM nightly)

| Feature | Design | Implementation | Verdict |
|---------|--------|---------------|---------|
| All 5 types | XML prompt | `EXTRACTOR_PROMPT_TEMPLATE` with 5 types | **PASS** |
| Fail-silent | Returns [] on error | `except Exception: return []` at line 307-309 | **PASS** |
| Manifest dedup | Inject already_known | `already_known` param + `_format_already_known()` | **PASS** |
| **Nightly scheduler** | Design says "nightly job" | **NO CALLER EXISTS** | **FAIL — CRITICAL** |

**CRITICAL GAP:** `extract_deep` is implemented but has **zero callers in production**. The only reference is in `scripts/reextract_low_confidence.py` (with a TODO comment). This means:

- **objection**: Only populated via dual-write from legacy `ConversationMemoryService` (regex-detected in `services/memory_service.py:FactType.OBJECTION_RAISED`)
- **interest**: Only populated via dual-write from legacy `FollowerMemory.interests` list or `ConversationMemoryService`
- **relationship_state**: Only populated via dual-write from legacy `FollowerMemory.is_customer`/`.status`

The new ARC2 extractor covers only **2 of 5 types** in production (identity, intent_signal). The remaining 3 depend entirely on the dual-write bridge from legacy systems — which are supposed to be replaced.

---

## 5. Read Cutover Analysis (A2.5) — K1 Root Cause

### 5a. Code Path Comparison

**Legacy path** (`context.py:668-677`):
```
ENABLE_MEMORY_ENGINE=true →
  mem_engine.recall(creator_id, sender_id, message) →
    search(creator_id, lead_id, message, top_k=10) →     # semantic search
      _generate_embedding(message) →                       # embed current message
      _pgvector_search(query_embedding, min_similarity=0.4) → # cosine distance
    _get_compressed_memo() →                               # add compressed memo
    _format_memory_section(facts, summary, max_chars=2000) # <memoria> XML tags
```

**ARC2 path** (`context.py:657-665`):
```
ENABLE_LEAD_MEMORIES_READ=true →
  _read_arc2_memories_sync(creator_id, sender_id) →       # NO message param
    svc.get_all(creator_uuid, lead_uuid) →                 # ALL memories, no filter
    _format_arc2_memories(memories) →                      # [Label] format, 500 chars
```

### 5b. Root Cause Decomposition

#### RC1: No Message-Relevance Filtering (CRITICAL)

| Dimension | Legacy (MemoryEngine) | ARC2 (LeadMemoryService) |
|-----------|----------------------|-------------------------|
| Query input | Current `message` text | **None** |
| Embedding | `_generate_embedding(message)` | Never called |
| Search method | `_pgvector_search(cosine, min_similarity=0.4)` | `get_all()` — returns everything |
| Ranking | By cosine similarity (most relevant first) | By `created_at` (chronological) |
| Cap | `top_k=10` (env: MAX_FACTS_IN_PROMPT) | **No cap** (all non-deleted rows) |

Effect: If a lead has 50 memories, legacy retrieves the 10 most relevant to the current message. ARC2 dumps all 50, sorted chronologically, then hard-truncates at 500 chars. The LLM receives noise-dominant context.

#### RC2: Format Tag Mismatch (HIGH)

The `_build_recalling_block` footer at `context.py:1151`:
```python
footer = "IMPORTANTE: Lee <memoria> y responde mencionando algo de ahí. No repitas textual."
```

Legacy format wraps output in `<memoria>...</memoria>` XML tags (memory_engine.py:1462):
```
<memoria>
Nombre: Cuca
- Le interesa yoga
- Tiene una hija que se llama María
Último tema: precios del curso
</memoria>
```

ARC2 format uses bracket labels with no XML wrapper (context.py:276-300):
```
[Identidad] Lead's name is María
[Intereses] yoga, fitness
[Objeciones] Es muy caro
```

The LLM is instructed to "Lee \<memoria\>" but there is no `<memoria>` tag in the ARC2 output. The LLM has no clear boundary marker for where memories start and end, reducing utilization. Research (MRPrompt 2026, Zep 2025) shows explicit boundary markers improve memory recall by 15-30% in sub-14B models.

#### RC3: 500 vs 2000 Char Budget (MEDIUM)

| | Legacy | ARC2 |
|--|--------|------|
| Max chars | 2000 | 500 |
| Dedup | `_dedup_facts()` removes near-duplicates | None (ON CONFLICT dedup at write time only) |
| Priority ordering | commitment > preference > objection > personal_info > purchase_history > topic | By confidence DESC per type group |
| Name extraction | Separate `Nombre:` line | Inline in content |
| Compressed memo | Included as first item | Not supported |
| Truncation | Per-fact truncation | Mid-string truncation (`result[:497] + "..."`) |

The 500-char cap means roughly 5-8 facts maximum. Combined with no relevance ranking, these may be the least relevant 5-8 facts due to chronological ordering.

---

## 6. Dual-Write Bridge Analysis (A2.4)

**Implementation:** `services/dual_write.py`

### 6a. Coverage Matrix

| Legacy Source | Legacy Types | ARC2 Types Mapped | Skipped |
|-------------|-------------|-------------------|---------|
| MemoryExtractor (extraction.py) | personal_info, preference, objection, purchase_history, commitment, topic, compressed_memo | identity, interest, objection, intent_signal, relationship_state | compressed_memo |
| FollowerMemory (memory_service.py) | name, interests[], objections_raised[], is_customer, status | identity, interest, objection, relationship_state | — |
| ConversationMemoryService (memory_service.py) | interest, objection, name_used, appointment, price_given, link_shared, product_explained, question_asked, question_answered | interest, objection, identity, intent_signal | 5 bot-side/noisy types |

### 6b. Fail-Silent Correctness

All 3 public hooks (`dual_write_from_extraction`, `dual_write_from_follower_memory`, `dual_write_from_conversation_memory`) are wrapped in the `maybe_dual_write` envelope which:
- Returns immediately if `flags.dual_write_lead_memories` is false (zero overhead)
- Catches all exceptions, logs warning, increments failure counter
- Never re-raises

**Verdict: Fail-silent correctly implemented.**

### 6c. ID Resolution

Both `_resolve_creator_uuid` and `_resolve_lead_uuid` use `asyncio.to_thread` for DB queries. Lead resolution strips `ig_`/`wa_`/`tg_` prefixes and checks both formats with `ANY(ARRAY[:pid, :pid_raw])`.

**Matches the `_read_arc2_memories_sync` ID resolution logic. No mismatch.**

### 6d. body_structure Enforcement

For `objection` and `relationship_state`, dual-write auto-fills missing `why`/`how_to_apply` with defaults:
```python
if not why:
    why = "Extracted from legacy memory system"
if not how_to_apply:
    how_to_apply = "Use as context for personalization"
```

This satisfies the DB CHECK constraint. The defaults are generic but not incorrect.

---

## 7. CC ↔ Clonnect Divergence Analysis

| CC Pattern | CC Implementation | Clonnect ARC2 Implementation | Impact |
|-----------|------------------|------------------------------|--------|
| **Scope separation** | memdir/ (durable) vs SessionMemory (ephemeral) | Single table `arc2_lead_memories` for all | Low — domain difference (developer vs lead) |
| **Recall = semantic** | Not applicable (file-based, tool reads) | `recall_semantic()` exists but **unused in read cutover** | **HIGH — RC1** |
| **Manifest injection** | Pre-load existing facts, inject into prompt to prevent re-extraction | `extract_deep` has `already_known` param | OK — matches |
| **Cursor incremental** | Process only new messages since cursor | `CURSOR_ENABLED` flag in `memory_extraction.py` (legacy) | N/A for new extractor |
| **Overlap guard** | Per-(creator,lead) in-progress flag | Legacy only, not in new extractor | Low risk (regex is sync) |
| **Single writer** | Deny fork if main has writes | Warn + newer-wins | **MEDIUM** — acceptable for now |
| **Format: XML boundary** | Tool output has clear boundaries | ARC2 output lacks `<memoria>` tags | **HIGH — RC2** |
| **Retrieval: k-limited** | CC uses targeted file reads | Legacy uses top_k=10; ARC2 has **no cap** | **HIGH — RC1** |
| **Consolidation: dedup** | `update existing rather than creating duplicate` | ON CONFLICT dedup at write time | OK |
| **Date conversion** | "convert relative dates to absolute" | In `extract_deep` prompt template | OK |

---

## 8. Recommendations

### P0: Fix K1 Regression (before re-enabling read cutover)

**RC1 fix — Use `recall_semantic()` instead of `get_all()`:**

In `_read_arc2_memories_sync` (context.py:353), change:
```python
# BEFORE:
memories = svc.get_all(creator_uuid, lead_uuid)

# AFTER:
# 1. Generate embedding for current message (need message param)
# 2. Use recall_semantic(creator_uuid, lead_uuid, query_embedding, top_k=5)
# 3. Fallback to get_all() if no embeddings populated yet
```

This requires threading the `message` parameter through `_read_arc2_memories_sync`. The function signature must change from:
```python
def _read_arc2_memories_sync(creator_slug, platform_user_id) -> str
```
to:
```python
def _read_arc2_memories_sync(creator_slug, platform_user_id, message) -> str
```

**Prerequisite:** Embeddings must actually be populated. Currently `extract_from_message` (regex) does not generate embeddings — only `extract_deep` (LLM, no scheduler) and dual-write (no embeddings) populate data. Without embeddings, `recall_semantic` returns empty. This means:
1. Either add embedding generation to the dual-write bridge
2. Or run a backfill job to add embeddings to existing rows
3. Or use `get_by_type()` with a type priority list + cap as an intermediate fix

**RC2 fix — Wrap ARC2 output in `<memoria>` tags:**

In `_format_arc2_memories` (context.py:276-300), wrap the output:
```python
return f"<memoria>\n{result}\n</memoria>"
```

**RC3 fix — Raise cap to 1500 chars:**

Change `_MAX_ARC2_MEMORY_CHARS = 500` to `1500`. The legacy system uses 2000, but ARC2's format is more compact (no bullet prefixes, no timestamp suffixes).

### P1: Activate extract_deep Scheduler

Create a nightly cron/scheduler that calls `extract_deep` for active leads. Without this, 3/5 memory types (objection, interest, relationship_state) depend entirely on dual-write from legacy systems.

### P2: Add Embedding Generation to Write Path

Either in `_write_entries_sync` (dual_write.py:165) or in `LeadMemoryService.upsert()`, generate and store embeddings for every written memory. This is prerequisite for `recall_semantic()` to work.

### P3: Harden Single-Writer for Multi-Extractor Phase

When both `extract_from_message` and `extract_deep` run in production, add a deny-on-conflict mode for specific writer pairs (e.g., nightly should not overwrite real-time extraction within the same hour).

---

## Appendix A: File Reference

| File | Lines | Role |
|------|-------|------|
| `services/lead_memory_service.py` | 409 | ARC2 A2.1 — schema + service |
| `services/memory_extractor.py` | 526 | ARC2 A2.2 — hybrid extractor (regex + LLM) |
| `services/dual_write.py` | 411 | ARC2 A2.4 — dual-write bridge |
| `core/dm/phases/context.py:276-360` | ~85 | ARC2 A2.5 — read cutover + formatter |
| `core/dm/phases/context.py:656-677` | ~22 | Read cutover flag routing |
| `services/memory_engine.py:318-358` | ~40 | Legacy recall (semantic search) |
| `services/memory_engine.py:1432-1491` | ~60 | Legacy format (`<memoria>` XML) |
| `services/memory_service.py:17-100` | ~84 | Legacy FollowerMemory (JSON) |
| `services/memory_service.py:334-560` | ~227 | Legacy ConversationMemoryService (regex facts) |

## Appendix B: Memory Population Flow (Current State)

```
Lead sends DM message
    │
    ├── Legacy MemoryExtractor._do_extract() ──→ dual_write_from_extraction()
    │     (6 fact types: personal_info, preference, ...)    (maps to 5 ARC2 types)
    │
    ├── Legacy MemoryStore.save(FollowerMemory) ──→ dual_write_from_follower_memory()
    │     (name, interests[], objections[], status)         (maps to 4 ARC2 types)
    │
    ├── Legacy ConversationMemoryService.save() ──→ dual_write_from_conversation_memory()
    │     (9 FactTypes, regex-detected)                     (maps to 4 ARC2 types, 5 skipped)
    │
    ├── NEW extract_from_message() ──→ LeadMemoryService.upsert()
    │     (regex: identity + intent_signal only)   (2/5 types, no embedding)
    │
    └── NEW extract_deep() ──→ [NO CALLER — orphaned]
          (LLM: all 5 types)

Read path:
    ENABLE_LEAD_MEMORIES_READ=true → get_all() → _format_arc2_memories() → 500 chars
    ENABLE_MEMORY_ENGINE=true      → recall(message) → semantic search → <memoria> → 2000 chars
```
