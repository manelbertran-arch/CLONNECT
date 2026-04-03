# Learning Systems Consolidation: 7→3 Architecture Spec

**Date:** 2026-04-03
**Author:** Claude (architect) for Manel
**Status:** Design complete — ready for implementation

---

## STEP 1: INVENTORY — Every function classified

### 1. FeedbackStore (`services/feedback_store.py`) → **A: FeedbackCapture**

| Function | Lines | Classification | Destination | Reason |
|----------|-------|---------------|-------------|--------|
| `capture()` | 53-174 | **REUSE** | A | Clean routing facade, well-tested, handles all 8 signal types |
| `_compute_quality()` | 177-182 | **REUSE** | A | Simple BeeS heuristic, works correctly |
| `QUALITY_SCORES` dict | 28-37 | **REUSE** | A | Well-calibrated constants |
| `_COPILOT_ACTION_MAP` | 40-46 | **REUSE** | A | Clean mapping |
| `save_feedback()` | 189-323 | **REUSE** | A | Core evaluator save, dedup works, single-transaction derivatives |
| `get_feedback()` | 326-378 | **REUSE** | A | Standard query with filters |
| `get_feedback_stats()` | 381-439 | **REWRITE** | A | Good but queries LearningRule/GoldExample counts — update refs after consolidation |
| `_auto_create_preference_pair()` | 446-473 | **REUSE** | A | Clean, uses caller session correctly |
| `_auto_create_gold_example()` | 476-532 | **REUSE** | A | Clean dedup, quality gate, uses caller session |

### 2. PreferencePairsService (`services/preference_pairs_service.py`) → **A: FeedbackCapture**

| Function | Lines | Classification | Destination | Reason |
|----------|-------|---------------|-------------|--------|
| `_fetch_context_and_save_sync()` | 30-111 | **REUSE** | A | Session-bounded context fetch + batch save, well-designed |
| `create_pairs_from_action()` | 114-230 | **REUSE** | A | All 6 action types handled, BUG-6 dedup guard, clean |
| `get_pairs_for_export()` | 233-284 | **REUSE** | A | Standard query |
| `mark_exported()` | 287-313 | **REUSE** | A | Bulk update, clean |
| `mine_historical_pairs()` | 316-469 | **REUSE** | A | Batch-optimized (no N+1), session boundary, per-lead cap |
| `curate_pairs()` | 472-503 | **REUSE** | A | Thin wrapper for scheduler |

### 3. AutolearningAnalyzer (`services/autolearning_analyzer.py`) → **B: PersonaCompiler**

| Function | Lines | Classification | Destination | Reason |
|----------|-------|---------------|-------------|--------|
| `analyze_creator_action()` | 63-110 | **REWRITE** | B | Good router but stores individual rules — should batch patterns instead |
| `_handle_approval()` | 113-124 | **ELIMINATE** | — | Reinforces individual rules; rules system going away from runtime |
| `_handle_edit()` | 127-161 | **REWRITE** | B | LLM extraction is good; but output should feed pattern accumulator, not individual rules |
| `_handle_discard()` | 164-194 | **REWRITE** | B | Same — good extraction, wrong destination |
| `_handle_resolved_externally()` | 197-229 | **REWRITE** | B | Same |
| `_handle_manual_override()` | 232-263 | **REWRITE** | B | Same |
| `_llm_extract_rule()` | 266-299 | **REWRITE** | B | Core LLM call — reuse but change output format from individual rule to pattern observation |
| `_parse_llm_response()` | 302-332 | **REUSE** | B | JSON parsing + injection sanitization is solid |
| `_store_rule()` | 335-359 | **ELIMINATE** | — | Stores to learning_rules; replaced by pattern accumulation in B |
| `_ANALYSIS_PROMPT_TEMPLATE` | 40-60 | **REWRITE** | B | Prompt targets single rule extraction; B needs pattern observation format |
| `_is_non_text_response()` | 28-32 | **REUSE** | B | Media filter, universally useful |

### 4. AutolearningEvaluator (`core/autolearning_evaluator.py`) → **B: PersonaCompiler**

| Function | Lines | Classification | Destination | Reason |
|----------|-------|---------------|-------------|--------|
| `run_daily_evaluation()` | 22-172 | **REUSE** | B | Solid daily metrics aggregation (approval rate, clone accuracy, edit patterns) |
| `_detect_daily_patterns()` | 175-245 | **REUSE** | B | Pattern detection from edit diffs (shortening, question removal, rewrite, emoji) |
| `run_weekly_recalibration()` | 248-361 | **REWRITE** | B | Good trend analysis; add Doc D update trigger (TextGrad) |
| `_generate_weekly_recommendations()` | 364-444 | **REWRITE** | B | Generates recommendations as data — should generate Doc D patch instructions instead |

### 5. PatternAnalyzer (`services/pattern_analyzer.py`) → **B: PersonaCompiler**

| Function | Lines | Classification | Destination | Reason |
|----------|-------|---------------|-------------|--------|
| `run_pattern_analysis()` | 98-206 | **REWRITE** | B | Core batch logic is good; change output from rules → pattern observations for Doc D compiler |
| `_build_judge_prompt()` | 46-66 | **REWRITE** | B | Good prompt structure; output should be "Doc D section update" not "learning rules" |
| `_format_pair()` | 32-43 | **REUSE** | B | Clean pair formatting |
| `_call_judge()` | 209-231 | **REUSE** | B | LLM call + JSON parse, generic enough |
| `_persist_run_sync()` / `_persist_run()` | 69-95 | **REUSE** | B | Audit trail, keep |
| `run_pattern_analysis_all()` | 234-259 | **REUSE** | B | All-creators iterator, keep |

### 6. LearningConsolidator (`services/learning_consolidator.py`) → **B: PersonaCompiler**

| Function | Lines | Classification | Destination | Reason |
|----------|-------|---------------|-------------|--------|
| `consolidate_rules_for_creator()` | 49-128 | **ELIMINATE** | — | Consolidates rules into... more rules. TextGrad says compile into Doc D directly |
| `_consolidate_group()` | 131-164 | **REWRITE** | B | LLM merging logic is good; redirect to produce Doc D section text, not new rules |
| `_parse_consolidation_response()` | 167-193 | **REUSE** | B | JSON parsing, reusable |

### 7. LearningRulesService (`services/learning_rules_service.py`) → **B: PersonaCompiler (data source)**

| Function | Lines | Classification | Destination | Reason |
|----------|-------|---------------|-------------|--------|
| `create_rule()` | 107-182 | **KEEP** (transitional) | B data | Still needed during transition; B reads rules table as input data |
| `get_applicable_rules()` | 185-315 | **ELIMINATE** | — | Runtime injection removed (already commented out in generation.py L144) |
| `update_rule_feedback()` | 318-345 | **ELIMINATE** | — | Feedback loop on individual rules is dead path |
| `deactivate_rule()` | 348-372 | **KEEP** | B | Used by consolidation |
| `get_rules_count()` | 375-394 | **KEEP** | B | Used for threshold checks |
| `get_all_active_rules()` | 397-435 | **KEEP** | B | Used by PersonaCompiler as input |
| `sanitize_rule_text()` | 65-72 | **REUSE** | B | Injection protection, universal |
| `filter_contradictions()` | 75-104 | **REUSE** | B | Useful for contradiction detection in Doc D compilation |
| `_CONTRADICTION_PAIRS` | 51-62 | **REUSE** | B | ES/CA keyword pairs for contradiction detection |

### 8. GoldExamplesService (`services/gold_examples_service.py`) → **C: StyleRetriever**

| Function | Lines | Classification | Destination | Reason |
|----------|-------|---------------|-------------|--------|
| `create_gold_example()` | 81-170 | **REUSE** | C | Dedup, quality scoring, non-text filter, truncation — all solid |
| `get_matching_examples()` | 173-284 | **REWRITE** | C | Works but uses keyword scoring; upgrade to embedding similarity (DITTO paper) |
| `detect_language()` | 52-61 | **REUSE** | C | CA/ES/EN heuristic, lightweight |
| `_is_non_text()` | 65-69 | **REUSE** | C | Media filter |
| `_SOURCE_QUALITY` | 72-78 | **REUSE** | C | Quality scores by source |
| `mine_historical_examples()` | 298-382 | **REUSE** | C (via A) | Historical mining path for new creators |
| `curate_examples()` | 385-537 | **REUSE** | C | Background curation (expiry, cap, historical mining) |
| `_invalidate_examples_cache()` | 540-546 | **REUSE** | C | Thread-safe cache invalidation |
| LRU cache system | 27-30, 287-295 | **REWRITE** | C | Replace with embedding-based retrieval |

---

## STEP 2: RESEARCH SYNTHESIS

### System A: FeedbackCapture — Research patterns

| Paper | Pattern | What changes vs current |
|-------|---------|----------------------|
| **OAIF** (2024) | Online preference scoring — capture quality signal at the moment of action, not deferred | Already implemented. `QUALITY_SCORES` dict and `_compute_quality()` are online. **No change needed.** |
| **Self-Rewarding LMs** | Model judges own output as improvement signal | Not yet implemented. Add optional self-eval score in `capture()` metadata. **Minor addition.** |
| **SOLID** (2024) | Session-bounded context prevents catastrophic forgetting | Already implemented. `_SESSION_GAP_HOURS = 4` in preference_pairs_service. **No change needed.** |
| **PersonaGym/CharacterEval** | Calibrate with human eval before trusting automated metrics | Already implemented via EvaluatorFeedback (human scores). **No change needed.** |

**Conclusion for A:** Current code is well-aligned with research. Minimal changes — mainly consolidate the two files into one module.

### System B: PersonaCompiler — Research patterns

| Paper | Pattern | What changes vs current |
|-------|---------|----------------------|
| **TextGrad** (Nature'24) | Optimize prompts directly with feedback gradient — rules compile INTO persona description | **Major change.** Currently rules are stored as separate entities and were injected at runtime (now disabled). B must compile patterns into Doc D text sections. |
| **RBR** (Anthropic) | Rules compile into constitution/persona, not runtime injection | Aligns with TextGrad. Rules → Doc D compilation, not separate bullet injection. **Already direction-of-travel** (generation.py L144 comment confirms rules removed from runtime). |
| **SOLID** (2024) | Continual learning with session-bounded context | B should version Doc D updates and maintain a "change log" to prevent forgetting previous good patterns when adding new ones. |
| **OAIF** (2024) | Online feedback beats offline DPO | B should weight recent feedback higher. Use time-decay when aggregating pattern evidence. |

**Concrete pattern for B:**
1. Read accumulated LearningRules + PreferencePairs + EvaluatorFeedback + CopilotEvaluations
2. Group by pattern category (tone, length, emoji, questions, CTA, structure)
3. For each category with 3+ evidence items, LLM-generate a Doc D section paragraph
4. Diff against current Doc D — only update sections with new evidence
5. Version control: store Doc D snapshot before/after, enable rollback

### System C: StyleRetriever — Research patterns

| Paper | Pattern | What changes vs current |
|-------|---------|----------------------|
| **DITTO** (2024) | Few-shot persona examples selected by embedding similarity outperform random selection | **Major change.** Replace keyword-scoring (`get_matching_examples`) with embedding-based retrieval. |
| **PersonaGym** | Calibrate example quality with human eval | Already done — quality_score from evaluator. **No change.** |
| **Self-Rewarding LMs** | Model-generated quality scores for curation | Optional: auto-score examples not yet evaluated by humans. **Nice-to-have.** |

**Concrete pattern for C:**
1. Store embeddings for each gold_example.creator_response (OpenAI `text-embedding-3-small`, already used in project for RAG)
2. At inference time: embed the user_message, cosine similarity search top-N
3. Filter: quality_score >= 0.6, language match, not expired
4. Inject top 3 as few-shot examples (existing prompt template works)

---

## STEP 3: UNIFIED DESIGN

### Data Flow Diagram

```
SIGNAL SOURCES                    A) FeedbackCapture              DB TABLES
─────────────                     ──────────────────              ─────────
Copilot approve ──┐                                              
Copilot edit ─────┤               ┌──────────────┐              evaluator_feedback
Copilot discard ──┤──────────────►│   capture()   │──────────────►preference_pairs
Copilot manual ───┤               │               │              gold_examples
Copilot resolved ─┤               │ Routes signal │              
Human eval ───────┤               │ to handler    │              
Historical mine ──┤               │               │              
Best-of-N ────────┘               └──────────────┘              

DB TABLES                         B) PersonaCompiler              Doc D (creators.doc_d)
─────────                         ──────────────────              ─────────────────────
preference_pairs ──┐              ┌──────────────────┐           
evaluator_feedback ┤──(weekly)───►│ analyze_patterns()│           
copilot_evaluations┤              │ compile_doc_d()   │──────────►Updated Doc D text
learning_rules ────┘              │ version_snapshot() │          doc_d_versions (new)
                                  └──────────────────┘           

DB TABLES                         C) StyleRetriever               Prompt injection
─────────                         ─────────────────               ───────────────
gold_examples ─────(inference)───►│ retrieve()        │──────────►Few-shot examples
  + embeddings                    │ embed + cosine    │           in generation prompt
                                  └─────────────────┘           
```

### A) FeedbackCapture — Detailed Design

**Location:** `services/feedback_capture.py` (rename from `feedback_store.py`)

**Public API:**
```python
async def capture(
    signal_type: str,          # evaluator_score|copilot_*|historical_mine|best_of_n
    creator_db_id: UUID,
    lead_id: Optional[UUID] = None,
    user_message: Optional[str] = None,
    bot_response: Optional[str] = None,
    creator_response: Optional[str] = None,
    conversation_context: Optional[list] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]
```
*Unchanged from current `feedback_store.capture()`. This is the single entry point.*

**Signal types handled (8):**
1. `evaluator_score` → EvaluatorFeedback + auto-derivatives
2. `copilot_approve` → PreferencePair (chosen=suggested)
3. `copilot_edit` → PreferencePair (chosen=final, rejected=suggested)
4. `copilot_discard` → PreferencePair (rejected=suggested)
5. `copilot_manual` → PreferencePair (chosen=final, rejected=suggested)
6. `copilot_resolved` → PreferencePair (chosen=final, rejected=suggested)
7. `historical_mine` → PreferencePairs mined from history
8. `best_of_n` → PreferencePairs from ranked candidates

**Quality scoring algorithm:** Unchanged BeeS heuristic:
- Static scores per signal type (`QUALITY_SCORES` dict)
- Dynamic for evaluator: `lo_enviarias / 5.0`

**Output format:** Returns `Dict[str, Any]` with `status`, `quality_score`, `signal_type`, handler-specific fields.

**DB schema:** No changes. Reuses existing tables:
- `evaluator_feedback` — human scores & corrections
- `preference_pairs` — chosen/rejected pairs
- `gold_examples` — high-quality examples (auto-created from evaluator corrections with lo_enviarias >= 4)

**Connection to B:** PersonaCompiler reads `preference_pairs`, `evaluator_feedback`, `copilot_evaluations` periodically (weekly batch). No direct API call between A→B.

**Connection to C:** `capture()` auto-creates gold_examples when evaluator provides ideal_response with lo_enviarias >= 4. StyleRetriever reads `gold_examples` table at inference time.

**Existing code REUSED verbatim:**
- `capture()`, `_compute_quality()`, `QUALITY_SCORES`, `_COPILOT_ACTION_MAP` from `feedback_store.py`
- `save_feedback()`, `get_feedback()`, `_auto_create_preference_pair()`, `_auto_create_gold_example()` from `feedback_store.py`
- `create_pairs_from_action()`, `_fetch_context_and_save_sync()`, `mine_historical_pairs()`, `curate_pairs()` from `preference_pairs_service.py`
- `get_pairs_for_export()`, `mark_exported()` from `preference_pairs_service.py`

**What is NEW:** Nothing functionally new. This is a file consolidation — `feedback_store.py` + `preference_pairs_service.py` → `feedback_capture.py`. All function signatures preserved for backward compatibility.

---

### B) PersonaCompiler — Detailed Design

**Location:** `services/persona_compiler.py` (new file, absorbs logic from 4 systems)

**Trigger:** Weekly cron (via `api/startup/handlers.py`), or manual via API endpoint.
Also runs after accumulating N new feedback items (configurable, default 50).

**Input (reads from DB):**
1. `preference_pairs` WHERE `batch_analyzed_at IS NULL` — unprocessed pairs
2. `evaluator_feedback` — human scores for quality calibration
3. `copilot_evaluations` — daily/weekly metrics (approval rate, clone accuracy, patterns)
4. `learning_rules` WHERE `is_active = TRUE` — existing accumulated rules
5. `creators.doc_d` — current persona description text

**Processing pipeline (5 steps):**

```
Step 1: COLLECT — Read all unprocessed signals since last run
    → preference_pairs (new), evaluator_feedback (recent), copilot_evaluations (last 7d)

Step 2: CATEGORIZE — Group signals by behavioral dimension
    Categories: tone, length, emoji, questions, CTA, structure, personalization, greetings, language_mix
    Each category gets: evidence_count, avg_quality_score, direction (more/less/change)

Step 3: COMPILE — For each category with 3+ evidence items, LLM generates Doc D paragraph
    Input: categorized evidence + current Doc D section for that category
    Output: updated paragraph that reflects BOTH old + new patterns (no forgetting)
    Model: gemini-2.5-flash (cost-efficient, structured output)

Step 4: DIFF — Compare compiled Doc D against current version
    Only update sections where evidence warrants change
    Apply contradiction filter (reuse `filter_contradictions()` logic)
    Log what changed and why

Step 5: PERSIST — Atomic update
    Snapshot current Doc D to doc_d_versions table (new)
    Update creators.doc_d with new text
    Mark processed preference_pairs.batch_analyzed_at = now()
    Log compilation run to pattern_analysis_runs table
```

**LLM calls:**
- One call per behavioral category with evidence (typically 3-6 categories)
- Prompt: "Given these N observed patterns from creator corrections, update this Doc D section"
- Model: `gemini-2.5-flash` (cheapest, structured output, ~500 input + 200 output tokens per call)
- Cost per weekly run: ~6 calls × $0.001 = $0.006 per creator per week
- Temperature: 0.1 (deterministic)

**Compilation prompt template:**
```
Current Doc D section for "{category}":
---
{current_section_text}
---

New evidence from {evidence_count} creator corrections:
{formatted_evidence}

Generate an UPDATED section that:
1. Preserves valid existing instructions
2. Integrates new patterns naturally
3. Resolves contradictions (newer evidence wins if evidence_count >= 3)
4. Writes in the SAME LANGUAGE as the creator's responses
5. Max 150 words
6. Imperative mood ("Responde brevemente", not "El bot debería...")

Output ONLY the updated section text, no JSON or markdown.
```

**How it handles contradictions:**
- Contradiction detection reuses `_CONTRADICTION_PAIRS` from learning_rules_service.py
- When old Doc D says "use emojis" but 5+ recent corrections remove emojis → new evidence wins
- Logs contradiction resolution for audit

**How it handles multi-language (CA/ES/EN):**
- Detects dominant language from evidence (reuses `detect_language()` from gold_examples_service)
- Compiles Doc D section in the dominant language of the evidence
- If mixed (CA/ES), compiles in both: "En català: ... / En castellano: ..."

**Doc D update format:**
Doc D is already a text field on `creators.doc_d`. PersonaCompiler appends/replaces tagged sections:

```
[PERSONA_COMPILER:tone]
Responde siempre de forma cercana y directa, sin emojis...
[/PERSONA_COMPILER:tone]

[PERSONA_COMPILER:length]
Mantén las respuestas entre 1-3 frases máximo...
[/PERSONA_COMPILER:length]
```

Sections outside `[PERSONA_COMPILER:*]` tags are untouched (human-authored parts of Doc D).

**Version control:**
- New table `doc_d_versions` stores snapshots before each update
- Enables rollback via API: `POST /autolearning/{creator}/rollback-doc-d/{version_id}`

**Existing code REUSED:**
- `_detect_daily_patterns()` from `autolearning_evaluator.py` — edit diff pattern detection
- `run_daily_evaluation()` from `autolearning_evaluator.py` — daily metrics aggregation
- `run_weekly_recalibration()` from `autolearning_evaluator.py` — weekly trend analysis (rewrite output)
- `_format_pair()` from `pattern_analyzer.py` — pair formatting for LLM
- `_call_judge()` from `pattern_analyzer.py` — generic LLM call + JSON parse
- `_persist_run_sync()` / `_persist_run()` from `pattern_analyzer.py` — audit trail
- `_parse_llm_response()` from `autolearning_analyzer.py` — JSON parsing + injection sanitization
- `sanitize_rule_text()` from `learning_rules_service.py` — injection protection
- `filter_contradictions()` / `_CONTRADICTION_PAIRS` from `learning_rules_service.py`
- `detect_language()` from `gold_examples_service.py`

**What is NEW:**
- `compile_doc_d()` — main orchestrator: collect → categorize → compile → diff → persist
- `_categorize_evidence()` — groups signals by behavioral dimension
- `_compile_section()` — LLM call to generate Doc D section from evidence
- `_diff_and_apply()` — compares old/new Doc D, applies changes atomically
- `_snapshot_doc_d()` — saves current Doc D to `doc_d_versions` before update
- Doc D tagged section format (`[PERSONA_COMPILER:category]`)

---

### C) StyleRetriever — Detailed Design

**Location:** `services/style_retriever.py` (rename/rewrite from `gold_examples_service.py`)

**Runtime API:**
```python
async def retrieve(
    creator_db_id: UUID,
    user_message: str,
    intent: Optional[str] = None,
    lead_stage: Optional[str] = None,
    language: Optional[str] = None,
    max_examples: int = 3,
) -> List[Dict[str, str]]
```
*Returns list of `{"creator_response": str, "intent": str, "quality_score": float}`*

**Embedding model:** `text-embedding-3-small` (OpenAI, 1536 dims)
- Already used in project for RAG (confirmed in codebase)
- Stored in `gold_examples.embedding` column (new, pgvector `vector(1536)`)

**Selection algorithm:**
1. Embed `user_message` → query vector
2. Cosine similarity search on `gold_examples` WHERE `creator_id = X AND is_active = TRUE AND quality_score >= 0.6`
3. Language filter: exclude examples where `detect_language(creator_response)` doesn't match
4. Return top N by similarity score

**Injection format:** Unchanged from current generation.py L209-214:
```
=== EJEMPLOS DE ESTILO DEL CREATOR (referencia de tono y formato, NO copies literalmente) ===
- "response text" [intent_tag]
- "response text" [intent_tag]
```

**Quality gate:** `quality_score >= 0.6` (excludes low-confidence historical examples at 0.5)

**Language filtering:** Reuses `detect_language()` from gold_examples_service.py. Unknown/mixto always pass.

**Privacy:** Only `creator_response` is returned/injected. `user_message` from other leads is never exposed in the prompt.

**Token budget:** Max 3 examples × 500 chars = 1500 chars (~375 tokens). Fits within the existing prompt budget alongside Doc D.

**Existing code REUSED:**
- `create_gold_example()` — dedup, quality scoring, non-text filter
- `detect_language()` — CA/ES/EN heuristic
- `_is_non_text()` — media filter
- `_SOURCE_QUALITY` — quality scores by source
- `mine_historical_examples()` — historical mining
- `curate_examples()` — background curation (expiry, cap, mining)
- Cache invalidation logic

**What is NEW:**
- `retrieve()` — embedding-based retrieval replaces `get_matching_examples()`
- Embedding storage: new column `gold_examples.embedding vector(1536)`
- `_embed_text()` — calls OpenAI embedding API (reuse existing project utility)
- `_ensure_embeddings()` — backfill embeddings for existing gold examples
- Embedding computed on `create_gold_example()` — add embedding call after save

---

### Interface Contract

```
A produces:
  → evaluator_feedback rows (human scores, ideal_response, error_tags)
  → preference_pairs rows (chosen, rejected, action_type, conversation_context)
  → gold_examples rows (user_message, creator_response, quality_score, intent)

B reads:
  ← preference_pairs WHERE batch_analyzed_at IS NULL
  ← evaluator_feedback (recent, for quality calibration)
  ← copilot_evaluations (daily/weekly metrics and patterns)
  ← learning_rules WHERE is_active = TRUE (existing rule accumulation)
  ← creators.doc_d (current persona text)
B writes:
  → creators.doc_d (updated persona text with [PERSONA_COMPILER:*] sections)
  → doc_d_versions (snapshot before update)
  → preference_pairs.batch_analyzed_at = now() (mark processed)
  → pattern_analysis_runs (audit trail)

C reads:
  ← gold_examples WHERE is_active = TRUE AND quality_score >= 0.6
  ← gold_examples.embedding (pgvector cosine similarity)
C injects:
  → Top 3 examples as few-shot in generation prompt (creator_response only)
```

---

## STEP 4: IMPLEMENTATION SPEC

### System A: FeedbackCapture

**1. Filename:** `services/feedback_capture.py`

**2. Imports:**
```python
import asyncio, logging, os, uuid, re, threading, time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from collections import defaultdict, OrderedDict
```

**3-4. Class/function skeleton:**
```python
# === Constants (from feedback_store.py + preference_pairs_service.py) ===
QUALITY_SCORES = {...}  # from feedback_store.py L28-37
_COPILOT_ACTION_MAP = {...}  # from feedback_store.py L40-46
_SESSION_GAP_HOURS = 4  # from preference_pairs_service.py L27

# === CAPTURE (entry point) ===
async def capture(signal_type: str, creator_db_id, ...) -> Dict[str, Any]
    # Copy from feedback_store.py L53-174 VERBATIM

def _compute_quality(signal_type: str, metadata: dict) -> float
    # Copy from feedback_store.py L177-182 VERBATIM

# === EVALUATOR FEEDBACK ===
def save_feedback(creator_db_id, evaluator_id: str, ...) -> Dict[str, Any]
    # Copy from feedback_store.py L189-323 VERBATIM

def get_feedback(creator_db_id, ...) -> List[Dict]
    # Copy from feedback_store.py L326-378 VERBATIM

def get_feedback_stats(creator_db_id) -> Dict[str, Any]
    # Copy from feedback_store.py L381-439, update to reference new module names

# === PREFERENCE PAIRS ===
async def create_pairs_from_action(action: str, creator_db_id, ...) -> int
    # Copy from preference_pairs_service.py L114-230 VERBATIM

def _fetch_context_and_save_sync(creator_db_id, ...) -> int
    # Copy from preference_pairs_service.py L30-111 VERBATIM

def get_pairs_for_export(creator_db_id, ...) -> List[Dict]
    # Copy from preference_pairs_service.py L233-284 VERBATIM

def mark_exported(pair_ids: List[str]) -> int
    # Copy from preference_pairs_service.py L287-313 VERBATIM

async def mine_historical_pairs(creator_id: str, creator_db_id, limit: int = 500) -> int
    # Copy from preference_pairs_service.py L316-469 VERBATIM

async def curate_pairs(creator_id: str, creator_db_id) -> Dict[str, Any]
    # Copy from preference_pairs_service.py L472-503 VERBATIM

# === AUTO-CREATION HELPERS ===
def _auto_create_preference_pair(session, ...) -> bool
    # Copy from feedback_store.py L446-473 VERBATIM

def _auto_create_gold_example(session, ...) -> bool
    # Copy from feedback_store.py L476-532 VERBATIM
```

**5. Existing functions to copy:**
- `feedback_store.py` L28-532: ALL functions (entire file)
- `preference_pairs_service.py` L24-503: ALL functions (entire file)

**6. New functions:** None. Pure consolidation.

**7. DB migrations:** None. Reuses existing tables.

**8. Tests required:**
- `test_capture_evaluator_score` — evaluator signal routes correctly, saves feedback + derivatives
- `test_capture_copilot_actions` — each of 5 copilot actions creates correct preference pairs
- `test_capture_best_of_n` — ranked candidates produce N-1 pairs
- `test_capture_historical_mine` — historical mining with session boundary + per-lead cap
- `test_dedup_evaluator_feedback` — duplicate source_message_id updates instead of creating
- `test_quality_scoring` — verify all 8 signal types produce correct quality scores
- `test_auto_create_gold_from_evaluator` — lo_enviarias >= 4 creates gold example
- `test_backward_compat_imports` — `from services.feedback_store import capture` still works via re-export

**9. Files to DELETE after migration:**
- `services/feedback_store.py` → replaced by `services/feedback_capture.py`
- `services/preference_pairs_service.py` → merged into `services/feedback_capture.py`

**10. Files to MODIFY:**
- `services/feedback_store.py` → convert to re-export shim: `from services.feedback_capture import *`
- `services/preference_pairs_service.py` → convert to re-export shim
- `core/copilot/actions.py` L118,137,280,303,439,455 → update imports
- `api/routers/copilot/actions.py` L362,383,439 → update imports
- `api/routers/feedback.py` L101,106,111 → update imports
- `api/routers/copilot/analytics.py` L347 → update import
- `api/startup/handlers.py` L546 → update import

---

### System B: PersonaCompiler

**1. Filename:** `services/persona_compiler.py`

**2. Imports:**
```python
import asyncio, json, logging, os, re
from collections import defaultdict
from datetime import datetime, date, timedelta, timezone
from typing import Any, Dict, List, Optional
```

**3-4. Class/function skeleton:**
```python
# === CONSTANTS ===
PERSONA_COMPILER_MIN_EVIDENCE = int(os.getenv("PERSONA_COMPILER_MIN_EVIDENCE", "3"))
PERSONA_COMPILER_MAX_EVIDENCE_PER_CATEGORY = 10
_BEHAVIORAL_CATEGORIES = [
    "tone", "length", "emoji", "questions", "cta",
    "structure", "personalization", "greetings", "language_mix",
]

# Tag format for Doc D sections
_TAG_PATTERN = re.compile(r'\[PERSONA_COMPILER:(\w+)\](.*?)\[/PERSONA_COMPILER:\1\]', re.DOTALL)

# === MAIN ENTRY POINT ===
async def compile_persona(creator_id: str, creator_db_id: UUID) -> Dict[str, Any]:
    """Weekly batch: analyze signals → compile Doc D updates.
    Returns {status, categories_updated, doc_d_version_id}."""
    # Step 1: collect_signals()
    # Step 2: categorize_evidence()
    # Step 3: for each category with enough evidence → compile_section()
    # Step 4: diff_and_apply()
    # Step 5: persist + mark processed

# === DAILY/WEEKLY EVALUATION (reused from autolearning_evaluator.py) ===
async def run_daily_evaluation(creator_id: str, creator_db_id, eval_date: Optional[date] = None):
    # Copy from autolearning_evaluator.py L22-172 VERBATIM

def _detect_daily_patterns(session, creator_db_id, since, until) -> list:
    # Copy from autolearning_evaluator.py L175-245 VERBATIM

async def run_weekly_recalibration(creator_id: str, creator_db_id, week_end: Optional[date] = None):
    # Copy from autolearning_evaluator.py L248-361
    # MODIFY: After storing weekly eval, trigger compile_persona() if recommendations exist

def _generate_weekly_recommendations(daily_evals, metrics: dict) -> list:
    # Copy from autolearning_evaluator.py L364-444 VERBATIM

# === SIGNAL COLLECTION ===
def _collect_signals(session, creator_db_id, since: datetime) -> Dict[str, List]:
    """Read unprocessed preference_pairs + recent evaluator_feedback + copilot_evaluations."""
    # NEW: Query preference_pairs WHERE batch_analyzed_at IS NULL
    # NEW: Query evaluator_feedback WHERE created_at >= since
    # NEW: Query copilot_evaluations WHERE eval_date >= since.date()
    # Returns {"pairs": [...], "feedback": [...], "evaluations": [...]}

# === EVIDENCE CATEGORIZATION ===
def _categorize_evidence(signals: Dict[str, List]) -> Dict[str, List[Dict]]:
    """Group signals by behavioral dimension.
    
    Returns: {"tone": [evidence_items], "length": [...], ...}
    Each evidence_item: {"text": str, "direction": str, "quality": float, "source": str}
    """
    # NEW: Analyze preference pair diffs → categorize
    # REUSE: edit_diff categories from _detect_daily_patterns()
    # REUSE: _CONTRADICTION_PAIRS for grouping

# === DOC D COMPILATION ===
async def _compile_section(
    category: str, 
    evidence: List[Dict], 
    current_section: str,
) -> Optional[str]:
    """LLM call to generate updated Doc D section from evidence.
    Returns updated section text or None if no meaningful change."""
    # NEW: Build prompt with evidence + current section
    # REUSE: _call_judge() pattern from pattern_analyzer.py
    # REUSE: sanitize_rule_text() for output validation

def _extract_current_sections(doc_d: str) -> Dict[str, str]:
    """Parse [PERSONA_COMPILER:*] sections from Doc D text."""
    # NEW

def _apply_sections(doc_d: str, updates: Dict[str, str]) -> str:
    """Replace [PERSONA_COMPILER:*] sections in Doc D. Add new sections at end."""
    # NEW

# === VERSION CONTROL ===
def _snapshot_doc_d(session, creator_db_id, doc_d_text: str, trigger: str) -> UUID:
    """Save current Doc D to doc_d_versions table before update."""
    # NEW

async def rollback_doc_d(creator_db_id: UUID, version_id: UUID) -> Dict:
    """Restore Doc D from a previous version snapshot."""
    # NEW

# === AUDIT ===
async def _persist_run(creator_db_id, result: Dict[str, Any]) -> None:
    # REUSE from pattern_analyzer.py L90-95

# === ALL CREATORS ===
async def compile_persona_all() -> Dict[str, Any]:
    """Run persona compilation for all active creators. Used by background job."""
    # REUSE pattern from pattern_analyzer.run_pattern_analysis_all()

# === UTILITIES (reused) ===
def sanitize_rule_text(text: str) -> str:  # from learning_rules_service.py
def filter_contradictions(rules: List[Dict]) -> List[Dict]:  # from learning_rules_service.py
def detect_language(text: str) -> str:  # from gold_examples_service.py
```

**5. Existing functions to copy:**
- `autolearning_evaluator.py` L22-444: `run_daily_evaluation`, `_detect_daily_patterns`, `run_weekly_recalibration`, `_generate_weekly_recommendations`
- `pattern_analyzer.py` L32-43, 90-95, 209-231: `_format_pair`, `_persist_run`, `_call_judge`
- `autolearning_analyzer.py` L302-332: `_parse_llm_response`
- `learning_rules_service.py` L65-104: `sanitize_rule_text`, `filter_contradictions`, `_CONTRADICTION_PAIRS`
- `gold_examples_service.py` L52-61: `detect_language`

**6. New functions (with pseudocode):**

```python
async def compile_persona(creator_id, creator_db_id):
    session = SessionLocal()
    try:
        # 1. Collect signals since last compilation
        last_run = query pattern_analysis_runs ORDER BY ran_at DESC LIMIT 1
        since = last_run.ran_at if last_run else 30_days_ago
        signals = _collect_signals(session, creator_db_id, since)
        
        if total_evidence(signals) < PERSONA_COMPILER_MIN_EVIDENCE:
            return {"status": "skipped", "reason": "insufficient_evidence"}
        
        # 2. Categorize
        categories = _categorize_evidence(signals)
        
        # 3. Get current Doc D
        creator = session.query(Creator).filter_by(id=creator_db_id).first()
        current_doc_d = creator.doc_d or ""
        current_sections = _extract_current_sections(current_doc_d)
        
        # 4. Compile each category with enough evidence
        updates = {}
        for cat, evidence in categories.items():
            if len(evidence) >= PERSONA_COMPILER_MIN_EVIDENCE:
                new_section = await _compile_section(cat, evidence, current_sections.get(cat, ""))
                if new_section:
                    updates[cat] = new_section
        
        if not updates:
            return {"status": "no_updates"}
        
        # 5. Snapshot + apply + persist
        _snapshot_doc_d(session, creator_db_id, current_doc_d, "weekly_compilation")
        new_doc_d = _apply_sections(current_doc_d, updates)
        creator.doc_d = new_doc_d
        
        # Mark pairs as analyzed
        mark preference_pairs.batch_analyzed_at = now() for all collected pairs
        
        session.commit()
        await _persist_run(creator_db_id, {"status": "done", "categories_updated": list(updates.keys())})
        return {"status": "done", "categories_updated": list(updates.keys())}
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

**7. DB migrations needed:**

```sql
-- New table: Doc D version history
CREATE TABLE doc_d_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL REFERENCES creators(id),
    doc_d_text TEXT NOT NULL,
    trigger VARCHAR(50) NOT NULL,  -- 'weekly_compilation', 'manual_edit', 'rollback'
    categories_updated JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_doc_d_versions_creator ON doc_d_versions(creator_id);
CREATE INDEX idx_doc_d_versions_created ON doc_d_versions(created_at);
```

**8. Tests required:**
- `test_compile_persona_basic` — with 5+ preference pairs, produces Doc D update
- `test_compile_skips_insufficient_evidence` — < 3 items → skipped
- `test_categorize_evidence` — pairs with edit_diff categorize correctly
- `test_section_extraction` — parse [PERSONA_COMPILER:*] tags from Doc D
- `test_section_application` — correctly replace/add sections without touching human content
- `test_contradiction_resolution` — newer evidence overrides conflicting old section
- `test_doc_d_versioning` — snapshot created before update, rollback works
- `test_multi_language_compilation` — mixed CA/ES evidence produces bilingual section
- `test_daily_evaluation_unchanged` — daily eval still works as before (regression)
- `test_weekly_triggers_compilation` — weekly recalibration triggers compile_persona

**9. Files to DELETE after migration:**
- `services/autolearning_analyzer.py` → absorbed into `persona_compiler.py`
- `core/autolearning_evaluator.py` → absorbed into `persona_compiler.py`
- `services/pattern_analyzer.py` → absorbed into `persona_compiler.py`
- `services/learning_consolidator.py` → absorbed into `persona_compiler.py`

**10. Files to MODIFY:**
- `api/startup/handlers.py` L402-502 → update imports to `persona_compiler`
- `api/routers/autolearning/analysis.py` L23,47 → update imports
- `core/copilot/actions.py` L118,280,439 → remove `autolearning_analyzer` calls; B is batch-only now
- `api/routers/copilot/actions.py` L362 → remove `autolearning_analyzer` call
- `services/learning_rules_service.py` → keep as data-access layer (B reads from it), remove runtime injection functions (`get_applicable_rules` is dead code but `create_rule` still used transitionally)

---

### System C: StyleRetriever

**1. Filename:** `services/style_retriever.py`

**2. Imports:**
```python
import asyncio, logging, os, re, threading, time
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
```

**3-4. Class/function skeleton:**
```python
# === CONSTANTS (from gold_examples_service.py) ===
STYLE_MAX_EXAMPLES = int(os.getenv("GOLD_MAX_EXAMPLES_IN_PROMPT", "3"))
STYLE_MAX_CHARS = int(os.getenv("GOLD_MAX_CHARS_PER_EXAMPLE", "500"))
STYLE_MIN_QUALITY = 0.6
_NON_TEXT_PREFIXES = (...)  # from gold_examples_service.py
_SOURCE_QUALITY = {...}  # from gold_examples_service.py

# === RETRIEVAL (main API) ===
async def retrieve(
    creator_db_id: UUID,
    user_message: str,
    intent: Optional[str] = None,
    lead_stage: Optional[str] = None,
    language: Optional[str] = None,
    max_examples: int = 3,
) -> List[Dict[str, str]]:
    """Embedding-based retrieval of style examples for few-shot injection.
    Returns [{"creator_response": str, "intent": str, "quality_score": float}]"""
    # NEW: embed user_message → cosine similarity search on gold_examples

# === FALLBACK (keyword scoring, for when embeddings not ready) ===
def get_matching_examples(creator_db_id, ...) -> List[Dict]:
    # COPY from gold_examples_service.py L173-284 (transitional fallback)

# === CURATION ===
def create_gold_example(creator_db_id, ...) -> Optional[Dict]:
    # COPY from gold_examples_service.py L81-170
    # MODIFY: After save, compute + store embedding

async def mine_historical_examples(creator_id, creator_db_id, limit=500) -> int:
    # COPY from gold_examples_service.py L298-382 VERBATIM

async def curate_examples(creator_id, creator_db_id) -> Dict[str, Any]:
    # COPY from gold_examples_service.py L385-537 VERBATIM

# === EMBEDDING ===
async def _embed_text(text: str) -> List[float]:
    """Compute embedding using text-embedding-3-small."""
    # NEW: Call OpenAI API (reuse existing embedding utility in project)

async def ensure_embeddings(creator_db_id: UUID) -> int:
    """Backfill embeddings for gold examples missing them. Returns count updated."""
    # NEW

# === UTILITIES (reused) ===
def detect_language(text: str) -> str  # from gold_examples_service.py
def _is_non_text(text: str) -> bool  # from gold_examples_service.py
def _invalidate_examples_cache(creator_db_id_str: str)  # from gold_examples_service.py

# Cache system (same OrderedDict LRU as current)
```

**5. Existing functions to copy:**
- `gold_examples_service.py` L27-547: ALL functions (entire file)

**6. New functions (with pseudocode):**

```python
async def retrieve(creator_db_id, user_message, intent=None, lead_stage=None, language=None, max_examples=3):
    # Check if embeddings are available
    from api.database import SessionLocal
    from api.models import GoldExample
    
    session = SessionLocal()
    try:
        # Count examples with embeddings
        has_embeddings = session.query(GoldExample).filter(
            GoldExample.creator_id == creator_db_id,
            GoldExample.is_active.is_(True),
            GoldExample.embedding.isnot(None),
        ).count()
        
        if has_embeddings < 3:
            # Fallback to keyword scoring
            return get_matching_examples(
                creator_db_id, intent=intent, lead_stage=lead_stage, language=language
            )
        
        # Embed user message
        query_embedding = await _embed_text(user_message)
        
        # pgvector cosine similarity search
        results = session.query(
            GoldExample,
            GoldExample.embedding.cosine_distance(query_embedding).label("distance")
        ).filter(
            GoldExample.creator_id == creator_db_id,
            GoldExample.is_active.is_(True),
            GoldExample.quality_score >= STYLE_MIN_QUALITY,
            GoldExample.embedding.isnot(None),
        ).order_by("distance").limit(max_examples * 2).all()
        
        # Language filter + format
        output = []
        for ex, dist in results:
            if language:
                ex_lang = detect_language(ex.creator_response)
                if ex_lang not in (language, "mixto", "unknown"):
                    continue
            output.append({
                "creator_response": ex.creator_response[:STYLE_MAX_CHARS],
                "intent": ex.intent,
                "quality_score": ex.quality_score,
            })
            if len(output) >= max_examples:
                break
        
        return output
    finally:
        session.close()
```

**7. DB migrations needed:**

```sql
-- Enable pgvector (already enabled in project)
-- Add embedding column to gold_examples
ALTER TABLE gold_examples ADD COLUMN embedding vector(1536);
CREATE INDEX idx_gold_examples_embedding ON gold_examples 
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10);
```

**8. Tests required:**
- `test_retrieve_with_embeddings` — returns examples ranked by similarity
- `test_retrieve_fallback_no_embeddings` — falls back to keyword scoring
- `test_retrieve_quality_gate` — examples below 0.6 excluded
- `test_retrieve_language_filter` — wrong-language examples excluded
- `test_create_gold_example_with_embedding` — embedding computed on create
- `test_ensure_embeddings_backfill` — fills missing embeddings
- `test_curate_examples_unchanged` — background curation still works (regression)
- `test_backward_compat_imports` — `from services.gold_examples_service import ...` still works

**9. Files to DELETE after migration:**
- `services/gold_examples_service.py` → replaced by `services/style_retriever.py`

**10. Files to MODIFY:**
- `services/gold_examples_service.py` → convert to re-export shim
- `core/dm/phases/generation.py` L185 → update import to `style_retriever.retrieve`
- `api/routers/autolearning/dashboard.py` L510,576,587 → update imports
- `services/whatsapp_onboarding_pipeline.py` L735 → update import

---

### MIGRATION ORDER

**Phase 1: System A (FeedbackCapture)** — Week 1
- Lowest risk: pure file consolidation, no logic changes
- All callers work via re-export shims immediately
- Prerequisite for nothing, blocks nothing

**Phase 2: System C (StyleRetriever)** — Week 2
- Medium risk: adds embedding column + new retrieval path
- Fallback to keyword scoring means no regression risk
- Independent of B (reads same gold_examples table)

**Phase 3: System B (PersonaCompiler)** — Week 3-4
- Highest complexity: new LLM compilation pipeline, Doc D mutations
- Requires careful testing with real creator data
- Depends on A being stable (reads A's output tables)
- Remove real-time autolearning_analyzer calls from copilot actions (biggest behavioral change)

### ROLLBACK PLAN

| System | Rollback strategy |
|--------|------------------|
| A (FeedbackCapture) | Re-export shims mean old imports still work. Delete `feedback_capture.py`, restore original files. Zero downtime. |
| B (PersonaCompiler) | `doc_d_versions` table enables one-click rollback of Doc D. Re-enable autolearning_analyzer imports in copilot/actions.py. Feature flag `ENABLE_PERSONA_COMPILER=false` disables batch compilation. |
| C (StyleRetriever) | Fallback to keyword scoring is built-in (< 3 embeddings → old path). Drop embedding column is safe (nullable). Re-export shim keeps old imports working. |

### RISK ASSESSMENT

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| **PersonaCompiler LLM generates bad Doc D section** | Medium | High (bad bot responses) | Doc D versioning + rollback API. Manual review for first 2 weeks. |
| **Embedding column migration locks gold_examples table** | Low | Medium (brief downtime) | Use `ALTER TABLE ... ADD COLUMN` (no lock on nullable column). Backfill embeddings async. |
| **Removing real-time autolearning_analyzer reduces learning speed** | Medium | Low | B runs weekly, not real-time. But accumulated evidence quality is higher than individual rule extraction. Monitor clone_accuracy for regression. |
| **Import path breakage during migration** | Low | High (crashes) | Re-export shims for ALL old module paths. Keep shims for 30 days post-migration. |
| **LLM cost increase from B's compilation calls** | Low | Low | ~$0.006/creator/week. 10 creators = $0.06/week. Negligible. |
| **Contradiction resolution removes valid Doc D content** | Medium | Medium | Log all changes with before/after. Require evidence_count >= 3 for any change. |

---

## VERIFICATION CHECKLIST

- [x] Step 1: ALL 7+1 files read (8 files), EVERY function classified (REUSE/REWRITE/ELIMINATE)
- [x] Step 2: Research patterns mapped to each of our 3 systems (7 papers applied)
- [x] Step 3: All 3 systems designed with interfaces, DB schema, data flow
- [x] Step 3: Interface contract between A→B→C documented
- [x] Step 4: Implementation spec for each system (10 items per system)
- [x] Step 4: Migration order + rollback + risk documented
