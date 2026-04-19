# ARC2 Extractor Evaluation — A2.2

**Date:** 2026-04-19  
**Worker:** A2.2 (`services/memory_extractor.py`)  
**Branch:** `feature/arc2-extractor-unified`

---

## 1. Legacy Extractor Mapping

| Dimension | Legacy 1: `memory_extraction.py` | Legacy 2: `memory_engine.py` | Legacy 3: `models/conversation_memory.py` |
|-----------|-----------------------------------|-------------------------------|-------------------------------------------|
| **Types** | preference, commitment, topic, objection, personal_info, purchase_history (6) | Delegates to Legacy 1 | PRICE_GIVEN, LINK_SHARED, PRODUCT_EXPLAINED, QUESTION_ASKED, QUESTION_ANSWERED, APPOINTMENT_MENTIONED, NAME_USED, OBJECTION_RAISED, INTEREST_EXPRESSED (9) |
| **Method** | LLM (Gemini/GPT, English prompt) | LLM via Legacy 1 + pgvector storage + decay | Dataclass model — consumers call manually |
| **Language** | Any (prompt in English, facts in any lang) | Any | ES hardcoded regex + manually set by bot |
| **Paradigm** | Lead-side (what LEAD revealed) | Lead-side + compression | **Bot-side** (what BOT did — fundamentally different) |
| **LLM calls/turn** | 1 | 1 (via Legacy 1) | 0 (no LLM) |
| **Guards** | Overlap, throttle, manifest, cursor | Via Legacy 1 | None |
| **Status** | ENABLE_MEMORY_ENGINE=false (prod OFF) | ENABLE_MEMORY_ENGINE=false (prod OFF) | Active in some phases |

---

## 2. New Extractor Coverage Map

| ARC2 type | Sync (regex) | Deep (LLM) | Legacy 1 equivalent | Legacy 3 equivalent |
|-----------|:---:|:---:|---|---|
| `identity` | ✅ age, name, location | ✅ full | `personal_info` | `NAME_USED` |
| `intent_signal` | ✅ strong/medium/abandon | ✅ full | `preference` + `purchase_history` (partial) | `INTEREST_EXPRESSED` (partial) |
| `interest` | ❌ (needs multi-turn context) | ✅ full | `preference` | `INTEREST_EXPRESSED` |
| `objection` | ❌ (needs multi-turn context) | ✅ full | `objection` | `OBJECTION_RAISED` |
| `relationship_state` | ❌ (structural inference) | ✅ full | ❌ **not in Legacy 1** | ❌ **not in Legacy 3** |

---

## 3. Per-Fixture Comparison (10 Fixtures)

| Fixture | New Sync | New Deep | Legacy 1 (estimated) | Legacy 3 (estimated) | Delta |
|---------|----------|----------|----------------------|----------------------|-------|
| fx_01 — age + strong intent | identity, intent_signal | identity, intent_signal | personal_info, preference | NAME_USED? (manual), — | **+intent_signal structured** |
| fx_02 — name only | identity | identity, interest | personal_info, topic | — | **+interest from deep** |
| fx_03 — strong purchase | intent_signal | intent_signal | purchase_history? | — | **+structured signal_strength** |
| fx_04 — medium intent | intent_signal | intent_signal | preference? | — | **+actionable how_to_apply** |
| fx_05 — greeting (no signal) | [] | [] | [] | [] | Same (no noise) |
| fx_06 — location | identity | identity | personal_info | — | Equivalent |
| fx_07 — price objection | intent_signal | intent_signal + objection | objection | OBJECTION_RAISED | **+how_to_apply mandatory** |
| fx_08 — Catalan age + intent | identity, intent_signal | identity, intent_signal | personal_info (EN only) | — | **+Catalan support** |
| fx_09 — English strong intent | intent_signal | intent_signal + interest | preference, purchase_history | — | **+multilingual** |
| fx_10 — multi-signal | identity + intent_signal | identity + interest + intent_signal | personal_info, preference | NAME_USED (partial) | **+composite body_structure** |

---

## 4. Redundancy Analysis

### New Extractor vs Legacy 1+2
- **~65% overlap** in types detected: identity ≈ personal_info, objection = objection, interest ≈ preference
- **New unique**: `relationship_state` (not in Legacy 1), multilingual regex (sync), XML body_structure with `why`+`how_to_apply` mandatory
- **Legacy 1 unique**: `commitment` (explicit lead promises), `topic` (recurring themes), `purchase_history` (past transactions confirmed)
- **Risk**: `commitment` type is NOT in ARC2 schema — intentional. CC's commitment type is bot-tracked; ARC2 uses `relationship_state` for status transitions

### New Extractor vs Legacy 3
- **~15% overlap**: only `INTEREST_EXPRESSED` → interest/intent_signal, `OBJECTION_RAISED` → objection
- **Legacy 3 is fundamentally different paradigm**: tracks what the BOT did (PRICE_GIVEN, LINK_SHARED, etc.), not lead revelations
- These bot-centric facts are NOT being replaced — they serve a different purpose (avoiding repetition in bot responses)

---

## 5. Elimination Recommendation (Phase 5)

| Priority | Extractor | Rationale |
|----------|-----------|-----------|
| 🟥 **First to eliminate** | `models/conversation_memory.py` (Legacy 3) | Wrong paradigm (bot-side vs lead-side), ES-only hardcoded regex, types don't map to ARC2 schema. Replace its bot-avoidance feature with `context.py` rewrite |
| 🟧 **Second** | `services/memory_extraction.py` (Legacy 1) | Types overlap ~65% after mapping. Can eliminate after A2.4 dual-write validates coverage parity over 2 weeks of production traffic |
| 🟨 **Last** | `services/memory_engine.py` (Legacy 2) | Delegates to Legacy 1 + has pgvector storage, recall, compression, decay. Eliminate after `LeadMemoryService` (A2.1) fully replaces its DB operations |

**Condition for Legacy 1+2 elimination:** CCEE K1 Context Retention must not regress (baseline ~69). Run CCEE comparison before cutover.

---

## 6. Sync Latency Measurement

From `test_extract_from_message_latency_below_200ms` (50 iterations avg):

| Scenario | Measured (avg) | Budget |
|----------|---------------|--------|
| Multi-signal message (age + name + location + intent) | < 1ms | 200ms |
| No-signal message (pre-filter exits early) | < 0.1ms | 200ms |

Regex path is ~200-2000x within budget. The 200ms limit is not a risk for this extractor.

---

## 7. Types Covered by Each Path

| Path | Types | Triggers |
|------|-------|---------|
| `extract_from_message` (sync) | `identity`, `intent_signal` | Per-turn, post-webhook |
| `extract_deep` (LLM nightly) | `identity`, `interest`, `objection`, `intent_signal`, `relationship_state` | Nightly job or manual trigger |

---

## 8. Next Steps

- **A2.3** (if needed): Migration script `scripts/migrate_conversation_memory.py` to backfill ~15K rows
- **A2.4**: Dual-write — call `memory_extractor.extract_from_message` in the webhook post-turn hook and persist via `LeadMemoryService` (A2.1)
- **Phase 5**: Legacy elimination in priority order (see §5)
