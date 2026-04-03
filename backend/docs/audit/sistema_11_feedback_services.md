# System #11 — Feedback Services (Preference Pairs + Learning Rules + Gold Examples)

**Date:** 2026-04-02  
**Auditor:** Forensic audit — every line read, every caller traced  
**Files:** `services/preference_pairs_service.py`, `services/learning_rules_service.py`, `services/gold_examples_service.py`  
**Models:** `api/models/learning.py` → `PreferencePair`, `LearningRule`, `GoldExample`

---

## 1. Architecture Overview

Three independent services capture feedback from copilot actions and inject corrections into the DM generation pipeline:

```
Creator uses Copilot UI
       │
       ├── approve → preference_pairs (chosen=suggested)
       ├── edit → preference_pairs (chosen=edited, rejected=suggested)
       │          → gold_examples (if minor edit)
       │          → autolearning_analyzer → learning_rules
       ├── discard → preference_pairs (rejected=suggested)
       │            → autolearning_analyzer → learning_rules
       ├── manual_override → preference_pairs + gold_examples
       └── resolved_externally → preference_pairs + gold_examples
                                  (creator replied from Instagram)
```

**Injection into prompts (generation.py):**
- Learning rules → line 149 (if `ENABLE_LEARNING_RULES=true`)
- Gold examples → line 221 (if `ENABLE_GOLD_EXAMPLES=true`)
- Preference pairs → NOT injected (export only for future DPO training)

---

## 2. Service-by-Service Analysis

### 2.1 Preference Pairs Service (387 lines)

**Purpose:** Collect (chosen, rejected) training data from copilot actions for future DPO/KTO fine-tuning.

**Feature flag:** `ENABLE_PREFERENCE_PAIRS=true` (ON by default)

**Functions:**
| Function | Type | Lines | Purpose |
|---|---|---|---|
| `create_pairs_from_action()` | async | 26-168 | Core: create pairs from 6 action types |
| `get_pairs_for_export()` | sync | 171-221 | Read pairs for DPO dataset export |
| `mark_exported()` | sync | 224-250 | Track exported pairs |
| `mine_historical_pairs()` | async | 253-352 | Backfill from historical IG messages |
| `curate_pairs()` | async | 355-387 | Background: mine if <10 pairs |

**Action type mapping:**
| Copilot Action | chosen | rejected | action_type |
|---|---|---|---|
| approved | suggested | None | approved |
| edited | final_text | suggested | edited |
| discarded | None | suggested | discarded |
| manual_override | manual_text | suggested | manual_override |
| resolved_externally | creator_reply | suggested | divergence |
| best_of_n | winner | each loser | best_of_n_ranking |

**Production callers (7):**
1. `core/copilot/actions.py:137` — `approve_response_impl()`
2. `core/copilot/actions.py:288` — `discard_response_impl()`
3. `core/copilot/actions.py:424` — `auto_discard_pending_for_lead_impl()`
4. `api/routers/copilot/actions.py:383` — `track_manual_response()`
5. `api/routers/copilot/actions.py:429` — `mark_pairs_exported()` endpoint
6. `api/routers/copilot/analytics.py:347` — `get_preference_pairs()` endpoint
7. `api/startup/handlers.py:546` — JOB 20 (12h curation)

**Scripts:** `turbo_onboarding.py`, `prepare_finetune_data.py`, `verify_db_layer.py`

**Quality:** Good. Clean action-type taxonomy. Export pipeline ready.

**Bugs:**
- **BUG-PP-01 (P2):** `create_pairs_from_action` is `async` but uses sync `SessionLocal()` at line 133. Should use `asyncio.to_thread()` for the DB block.
- **BUG-PP-02 (P3):** `mine_historical_pairs` does per-row query for preceding user message (line 312-323). N+1 pattern. Could batch with a window function.

---

### 2.2 Learning Rules Service (351 lines)

**Purpose:** CRUD for behavioral correction rules. When the bot makes recurring mistakes, rules are extracted ("NO uses 'a menudo'") and injected into future prompts.

**Feature flag:** `ENABLE_LEARNING_RULES=false` (OFF by default)

**Functions:**
| Function | Type | Lines | Purpose |
|---|---|---|---|
| `create_rule()` | sync | 32-103 | Create with dedup (same pattern+text → +0.05 confidence) |
| `get_applicable_rules()` | sync | 106-222 | Context-scored retrieval, 60s TTL cache |
| `update_rule_feedback()` | sync | 225-252 | Adjust confidence after application |
| `deactivate_rule()` | sync | 255-279 | Soft delete with supersession |
| `get_rules_count()` | sync | 282-301 | Count active rules |
| `get_all_active_rules()` | sync | 304-342 | For consolidation |
| `_invalidate_cache()` | sync | 345-351 | Cache invalidation |

**Context scoring algorithm:**
```
score = confidence × 0.1                    # Base
     + 3 × (intent/pattern match)           # Intent relevance
     + 2 × (relationship type match)        # Context match
     + 2 × (lead stage match)               # Funnel position
     + 1 × (universal rule, no context)     # Catch-all bonus
     × confidence                            # ← BUG: multiplied AGAIN
     + (times_helped / times_applied) × 1.5  # Effectiveness bonus
     + 1.0 × (source == "pattern_batch")     # LLM quality bonus
```

**Production callers (7):**
1. `core/dm/phases/generation.py:149` — prompt injection (conditional)
2. `services/autolearning_analyzer.py:114` — get + update rules
3. `services/autolearning_analyzer.py:318` — create rules from analysis
4. `services/learning_consolidator.py:55-59` — consolidation pipeline
5. `services/pattern_analyzer.py:136` — batch rule creation
6. `api/routers/autolearning/dashboard.py:9` — dashboard queries
7. `api/startup/handlers.py:464` — JOB 18 (24h consolidation)

**Bugs:**
- **BUG-LR-01 (P2):** All functions sync. Called from async contexts (`generation.py`, `autolearning_analyzer.py`). Should be wrapped with `asyncio.to_thread()`.
- **BUG-LR-02 (P1):** Double-confidence multiplication. Line 154: `score = rule.confidence * 0.1`. Line 185: `score *= rule.confidence`. This SQUARES the confidence. A rule with confidence=0.5 gets 0.5×0.1=0.05, then 0.05×0.5=0.025. A rule with confidence=1.0 gets 1.0×0.1=0.1, then 0.1×1.0=0.1. The 4:1 ratio should be 2:1. Low-confidence rules are over-penalized.

---

### 2.3 Gold Examples Service (459 lines)

**Purpose:** Curate high-quality (user_message, creator_response) pairs from copilot actions. Injected as few-shot examples in DM prompts.

**Feature flag:** `ENABLE_GOLD_EXAMPLES=false` (OFF by default)

**Quality scoring:**
| Source | Score |
|---|---|
| manual_override | 0.9 |
| approved | 0.8 |
| resolved_externally | 0.75 |
| minor_edit | 0.7 |
| historical | 0.6 |

**Functions:**
| Function | Type | Lines | Purpose |
|---|---|---|---|
| `create_gold_example()` | sync | 38-118 | Create with dedup (prefix or exact match) |
| `get_matching_examples()` | sync | 121-208 | Context-scored retrieval, 120s TTL cache |
| `mine_historical_examples()` | async | 211-295 | Backfill from historical IG |
| `curate_examples()` | async | 298-450 | Background: mine + expire + cap |
| `_invalidate_examples_cache()` | sync | 453-458 | Cache invalidation |

**Context scoring algorithm:**
```
score = quality_score × 0.1              # Base
     + 3 × (intent match)               # Intent relevance
     + 2 × (lead stage match)           # Funnel position
     + 1 × (relationship match)         # Context match
     + 0.5 × (universal, no context)    # Catch-all bonus
     × quality_score                      # ← BUG: multiplied AGAIN
```

**Production callers (5):**
1. `core/dm/phases/generation.py:221` — prompt injection (conditional)
2. `api/routers/autolearning/dashboard.py:587` — curate endpoint
3. `api/routers/autolearning/dashboard.py:9` — dashboard queries
4. `api/startup/handlers.py:537` — JOB 20 (12h curation)
5. `services/whatsapp_onboarding_pipeline.py:735` — WhatsApp onboarding

**Scripts:** `turbo_onboarding.py`, `purge_contaminated_gold_examples.py`

**Bugs:**
- **BUG-GE-01 (P1):** Same double-quality bug as LR-02. Line 162: `score = ex.quality_score * 0.1`. Line 183: `score *= ex.quality_score`. Squares quality_score.
- **BUG-GE-02 (P2):** `mine_historical_examples()` opens its own `SessionLocal()` (line 231) while called from `curate_examples()` which also has an open session (line 305). Two sessions from the same sync code block. Risk of connection pool exhaustion (pool_size=5).
- **BUG-GE-03 (P3):** `curate_examples` skips heavy edits (similarity_ratio < 0.8, line 353) — but heavy edits are often the MOST informative feedback signal. The creator rewrote the response significantly = strongest correction.

---

## 3. Overlap Analysis

### 3.1 Code Duplication

**Historical mining (80+ lines duplicated):**
Both `preference_pairs_service.mine_historical_pairs()` and `gold_examples_service.mine_historical_examples()` implement the SAME logic:
- Query: `Message.role=="assistant"`, `copilot_action IS NULL`, `15 <= length <= 250`
- Filter: 5 per lead max
- Lookup: preceding user message by `created_at < msg.created_at`
- Limit: 500 candidates

The only difference: one creates a `PreferencePair`, the other a `GoldExample`.

**Context-scored retrieval (40+ lines duplicated):**
Both `learning_rules_service.get_applicable_rules()` and `gold_examples_service.get_matching_examples()` implement:
- Same TTL cache pattern (dict + timestamp)
- Same weighted scoring (intent/stage/relationship)
- Same double-multiply bug
- Same `if _ > 0` filter on scores

### 3.2 Semantic Overlap

| What copilot "edit" produces | Preference Pair | Learning Rule | Gold Example |
|---|---|---|---|
| (edited_text, suggested_text) | chosen=edited, rejected=suggested | "When user says X, don't say Y, say Z" | (user_msg, edited_text) |

**The same edit event creates data in up to 3 tables.** The information is the same: "this response was wrong, this is the correction." Three different representations.

### 3.3 Injection Conflicts

At generation time (in `generation.py`):
- **Line 149:** Learning rules inject "NO: X, SI: Y" 
- **Line 221:** Gold examples inject "(user→creator_response)"
- **Calibration few-shot:** Separate injection from `calibration_loader.py`

These can contradict:
- Rule: "NO uses emojis" 
- Gold example (from older approved message): "Hola!! 😊😊"
- No conflict resolution mechanism exists.

---

## 4. Bug Summary

| ID | Service | Severity | Description |
|---|---|---|---|
| BUG-PP-01 | preference_pairs | P2 | Sync DB in async function |
| BUG-PP-02 | preference_pairs | P3 | N+1 query in mine_historical |
| BUG-LR-01 | learning_rules | P2 | All functions sync, called from async |
| BUG-LR-02 | learning_rules | **P1** | Double-confidence multiplication (squares score) |
| BUG-GE-01 | gold_examples | **P1** | Double-quality multiplication (squares score) |
| BUG-GE-02 | gold_examples | P2 | Nested SessionLocal risk |
| BUG-GE-03 | gold_examples | P3 | Skips heavy edits (most informative signal) |

---

## 5. Paper-Backed Architecture Recommendation

### What the research says (20 papers + 3 industry systems analyzed):

**Every production system uses ONE unified feedback store:**
- **PAHF (Feb 2026):** Single per-user memory with dual feedback channels
- **DEEPER (ACL 2025):** Single directed optimization from discrepancy signals
- **DPRF (Oct 2025):** Single refinement framework, inference-time
- **Character.ai:** All feedback types → ONE aggregated pipeline
- **Replika:** ONE Memory bank + ONE feedback pipeline
- **Delphi.ai:** Single "Clone Brain" knowledge graph

**No production system splits feedback into 3 separate services.**

### Recommendation: CONSOLIDATE

**Phase 1 (immediate):** Fix the 2 P1 bugs (double-multiply) in learning_rules and gold_examples. This is a 2-line fix each.

**Phase 2 (next sprint):** Create unified `FeedbackStore` service with:
- Single table with `feedback_type` field (preference_pair | learning_rule | gold_example | evaluator_correction)
- Single context-scored retrieval function (fix the bug once, not twice)
- Single historical mining function (deduplicate 80 lines)
- Multiple VIEWS for different consumption patterns:
  - DPO export view: WHERE ideal_response IS NOT NULL → (chosen, rejected)
  - Prompt injection view: WHERE quality >= 0.7 → few-shot examples
  - Anti-pattern view: WHERE error_tags IS NOT NULL → rules
  - Active learning view: WHERE needs_review = true → evaluator queue

**Phase 3:** Add evaluator feedback capture (the missing piece) into the same unified store.

**Justification:** One store, multiple views. Same pattern as PAHF's unified memory with dual consumption. Eliminates code duplication, resolves injection conflicts, and enables the human feedback system designed in `docs/research/HUMAN_FEEDBACK_SYSTEM.md`.

---

## 6. Hardcoding Check

| Check | Result |
|---|---|
| Creator-specific logic | NONE — all parameterized by `creator_db_id` |
| Hardcoded thresholds | Configurable via env vars (LEARNING_MAX_RULES_IN_PROMPT, GOLD_MAX_EXAMPLES_IN_PROMPT, etc.) |
| Language-specific logic | NONE |
| Platform-specific logic | NONE |

**All three services are universal.** Any creator_id works.

---

## 7. Test Coverage

| Service | Test File | Functions Tested |
|---|---|---|
| preference_pairs | `tests/cpe_shadow_comparison.py` | Indirect only |
| learning_rules | `tests/test_learning_rules_service.py` | Full CRUD + scoring |
| learning_rules | `tests/test_autolearning_analyzer.py` | Integration (9 patches) |
| learning_rules | `tests/test_learning_consolidator.py` | Consolidation flow |
| gold_examples | `tests/test_gold_examples_service.py` | Full CRUD + scoring |

**Gap:** `preference_pairs_service` has no dedicated unit test file. Only tested indirectly via shadow comparison.
