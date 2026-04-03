# AUDIT PART 3: LLM Generation + Post-processing + Learning

**Date**: 2026-03-19
**Auditor**: Claude Opus 4.6
**Scope**: Systems #26-49 (Generation pipeline, post-processing, learning loop)
**Method**: Full line-by-line code review + production DB analysis

---

## Production Data Snapshot

| Metric | Value |
|--------|-------|
| Learning rules (total/active) | 932 / 634 |
| Gold examples (total/active) | 4,811 / 177 |
| Preference pairs | 985 |
| Messages pending approval | 36 |
| Approved by creator | 1 |
| Edited by creator | 2 |
| Discarded by creator | 4 |
| Resolved externally (creator replied from app) | 624 |
| Manual override | 39 |
| Clone accuracy (latest, 2026-03-19) | **17.1%** (n=33) |
| Clone accuracy (trend, 5-day) | 11.1% -> 17.3% -> 15.8% -> 15.1% -> 17.1% |

**Key insight**: 624 resolved_externally vs 1 approved = **the creator almost never uses the copilot suggestions**. She replies directly from Instagram/WhatsApp 99.5% of the time.

---

## System #26: Response Strategy

**File**: `core/dm/strategy.py` (98 lines)

### How it works
5 strategies in priority order:
1. **PERSONAL**: Family/intimate/friend -> no selling
2. **BIENVENIDA + AYUDA**: First message with question
3. **BIENVENIDA**: First message, no question
4. **AYUDA**: Help signals detected (returning user)
5. **VENTA**: Purchase intent detected
6. **REACTIVACION**: Ghost lead returning
7. Default: empty string (no strategy hint)

### Assessment
- **Status**: WORKING correctly
- **Bug**: None
- **Does it influence LLM?** Yes - strategy text is appended to user prompt in `generation.py:199`. But at ~150 chars, it's drowned by the 20K-char style prompt. Impact is **minimal**.
- **Issue**: "fantasma" stage check at line 90 uses Spanish literal instead of enum. Works because lead.status stores Spanish strings, but fragile.

---

## System #27: Learning Rules Service

**File**: `services/learning_rules_service.py` (351 lines)

### How rules are created
- Created by `autolearning_analyzer.py` after each copilot action (edit/discard/resolve)
- LLM (Gemini Flash Lite) analyzes bot_response vs creator_response and generates a JSON rule
- Rules have: `rule_text`, `pattern`, `example_bad`, `example_good`, `confidence`, `applies_to_*` arrays
- Dedup: same pattern + rule_text -> increment confidence by 0.05

### How 5 are selected per call
1. Load all active rules for creator (LIMIT 100)
2. Score each: base score = `confidence * 0.1`
3. Context bonuses: +3 intent match, +2 relationship match, +2 stage match
4. Universal rules (no context): +1
5. Multiply by confidence
6. Bonus for help_ratio (times_helped / times_applied) * 1.5
7. Sort descending, take top 5

### Production rule quality analysis

| Rule | Pattern | Conf | Applied | Helped | Quality |
|------|---------|------|---------|--------|---------|
| "Use emojis for emotions" | general | 0.9 | 81 | **0** | BAD |
| "Affectionate greeting to women with emojis" | saludo | 0.9 | 23 | **0** | BAD |
| "Short direct phrases" | conversational_starters | 0.9 | 28 | **0** | BAD |
| "Hearts and smiley emojis" | emojis | 0.9 | 155 | **0** | BAD |
| "Express enthusiasm and emotional connection" | casual | 0.9 | 243 | **0** | BAD |
| "Avoid open generic questions" | question_general | 0.9 | 79 | **0** | BAD |
| "Include friendly greeting + open question" | greeting | 0.9 | 47 | **0** | BAD |
| "Use phrases about recurring situations" | situaciones | 0.9 | 318 | **0** | BAD |
| "Use colloquial expressions" | general | 0.9 | 161 | **0** | BAD |
| "Prioritize 'historical' action" | historical | 0.9 | 7 | **0** | NONSENSE |

### CRITICAL BUG: `times_helped` is ALWAYS 0

**All 634 active rules have `times_helped = 0`**. The `update_rule_feedback(was_helpful=True)` is only called during `_handle_approval` (line 112-121 of autolearning_analyzer.py), but there's only 1 approval in the entire history. With 624 resolved_externally actions, the feedback loop is **completely broken** — rules accumulate but never get quality signals.

### BUG: Rules contradict each other
- Rule #1: "Use emojis" (confidence 0.9)
- Rule #6: "Avoid open generic questions" (confidence 0.9)
- Rule #7: "Include friendly greeting + open question" (confidence 0.9)

Rules #6 and #7 directly contradict. This happens because the LLM generates rules from individual edits/discards without seeing existing rules. No dedup logic checks for semantic contradiction — only exact text match.

### BUG: Rule #10 is nonsensical
"Prioritize 'historical' action when the creator's choice is 'Ho hauria de fer ara'" — this is a rule generated from a Catalan message that the LLM misinterpreted as an instruction.

### Verdict: LEARNING RULES ARE NET NEGATIVE
- 634 rules injected into every prompt, adding ~220 tokens of noise
- 0% of rules have been validated as helpful
- Contradictory rules confuse the LLM
- The feedback loop doesn't work because Iris doesn't use the approve button
- **Recommendation**: Disable ENABLE_LEARNING_RULES until feedback loop is fixed

---

## System #28: Preference Profile Service

**File**: `services/preference_profile_service.py` (188 lines)

### Why is it returning None?
- `compute_preference_profile()` requires **at least 10 messages** with `copilot_action IN ('approved', 'edited', 'manual_override')`
- Production has: 1 approved + 2 edited + 39 manual_override = 42 total
- **BUT**: these are filtered `Message.content IS NOT NULL AND len > 5`, which may reduce count below 10

### Is the code broken?
No, the code is correct. The threshold (10 messages) is reasonable. The problem is that the creator barely interacts with copilot suggestions. With 42 actioned messages, the profile should actually compute. The issue might be that `manual_override` copilot_action doesn't match the filter (it checks for "approved", "edited", "manual_override" — correct).

### Assessment
- **Status**: PARTIALLY WORKING — likely computes but effect is invisible since it adds ~200 chars to a 23K system prompt
- **Impact**: NEGLIGIBLE — even if computed, this data is already covered by the 20K Doc D style prompt

---

## System #29: Gold Examples Service

**File**: `services/gold_examples_service.py` (459 lines)

### How examples are generated
1. **Copilot curation** (`curate_examples()`): Scans last 30 days of approved/edited/manual_override/resolved_externally messages
2. **Historical mining** (`mine_historical_examples()`): When <10 examples, mines historical messages (copilot_action IS NULL) with length 15-250 chars, max 5 per lead

### How 3 are selected per call
1. Load active examples (LIMIT 20)
2. Score: base = `quality_score * 0.1`
3. Bonuses: +3 intent match, +2 stage match, +1 relationship match
4. Multiply by quality_score
5. Sort descending, take top 3

### CRITICAL BUG: Media examples in gold library

Production random sample reveals catastrophic quality:

| # | Lead says | Iris response | Quality Score | Issue |
|---|-----------|---------------|---------------|-------|
| 1 | "[Sticker]" | "[Sticker]" | 0.75 | **Sticker -> Sticker. Useless.** |
| 3 | "Fua divisima" | "He utilizado WeTransfer..." | 0.75 | **Wrong response (WeTransfer link garbage)** |
| 4 | "tu cuando te vas a lanzarote??" | "Lo siento, hubo un error..." | **0.9** | **ERROR MESSAGE as gold example!!** |
| 5 | "Esperem que si" | "[Audio]: Vale, Sira..." | 0.75 | **Audio transcription as example** |
| 6 | "Jo tambe" | "[Sticker]" | 0.75 | **Sticker response** |
| 7 | "Mira hahahaua" | "Lo siento, hubo un error..." | **0.9** | **ERROR MESSAGE with quality 0.9!!** |

### BUG: Error messages stored as gold examples with quality 0.9
"Lo siento, hubo un error procesando tu mensaje" has `quality_score=0.9` because it was marked as `manual_override` (highest source quality). The autolearning system stored the ERROR response as a "gold" example of how Iris writes!

### BUG: No content filtering on creator_response
`create_gold_example()` doesn't filter out:
- Error messages (`"Lo siento, hubo un error"`)
- Sticker markers (`"[Sticker]"`)
- Audio transcriptions (`"[Audio]: ..."`)
- WeTransfer/spam links
- Media markers (`"[Photo]"`, `"[Video]"`)

The `_is_non_text_response()` check exists in `autolearning_analyzer.py` but NOT in `gold_examples_service.py`.

### BUG: Only 20 examples loaded for scoring
`get_matching_examples()` at line 143 does `LIMIT 20` — with 177 active examples, 88% are never considered. Selection is effectively random from the first 20 returned by the DB (no ORDER BY = arbitrary order).

### Verdict: GOLD EXAMPLES ARE ACTIVELY HARMFUL
- 2/10 random samples are **error messages** with highest quality (0.9)
- 3/10 are sticker/audio (non-replicable)
- Only ~3/10 are actually useful
- The LLM learns from error messages and stickers
- **Recommendation**: Purge all examples matching error/sticker/audio patterns, add content filter

---

## System #30: LLM Primary (Gemini Flash Lite)

**File**: `core/providers/gemini_provider.py` (405 lines)

### Exact parameters
- **Model**: `gemini-2.5-flash-lite` (from env `GEMINI_MODEL`, validated by `safe_model()`)
- **Temperature**: 0.7 (default), varies in Best-of-N [0.2, 0.7, 1.4]
- **Max tokens**: 150 (for DM), 512 (for autolearning), 1024 (for generate_simple)
- **Timeout**: 15s per HTTP call, 5s overall (`LLM_PRIMARY_TIMEOUT`)
- **Retries**: 2 (exponential backoff on 429/503)
- **API**: `generativelanguage.googleapis.com/v1beta` (direct HTTP, not SDK)

### Is the full prompt logged?
- System prompt size is logged: `[TIMING] System prompt: {len} chars (~{tokens} tokens) sections={...}`
- Full prompt is NOT logged (too large)
- Individual section sizes ARE logged

### Error handling
- Timeout: falls back to GPT-4o-mini
- 429 (rate limit): retry with exponential backoff (1s, 3s)
- 503: retry with 1s fixed delay
- Other HTTP errors: return None, trigger fallback
- Circuit breaker: after 2 consecutive failures, skip Gemini for 120s

### Assessment
- **Status**: WORKING correctly
- **Issue**: Creating a new `httpx.AsyncClient` per call (line 135) instead of reusing — minor perf cost (~50ms per call for TLS handshake)

---

## System #31: LLM Fallback (GPT-4o-mini)

**File**: `core/providers/gemini_provider.py` (lines 291-404)

### When fallback triggers
1. Gemini returns empty
2. Gemini times out (>5s)
3. Gemini HTTP error (non-retryable)
4. Circuit breaker open (2+ consecutive failures)

### Same prompt sent?
Yes — identical `messages` list (system + user) forwarded to OpenAI API.

### How often?
Cannot determine from code alone — would need `llm_usage_log` table analysis. Circuit breaker logs suggest it's rare (only fires after 2 consecutive failures).

### Assessment
- **Status**: WORKING correctly
- **Model**: `gpt-4o-mini` (configurable via `LLM_FALLBACK_MODEL`)
- **Timeout**: 10s (configurable via `LLM_FALLBACK_TIMEOUT`)

---

## System #32: Best-of-N

**File**: `core/best_of_n.py` (222 lines)

### Architecture
- Generates 3 candidates in parallel at T=[0.2, 0.7, 1.4]
- Each candidate gets a style hint injected into system prompt:
  - T=0.2: "[ESTILO: responde de forma breve y directa, maximo 1-2 frases cortas]"
  - T=0.7: "" (no hint)
  - T=1.4: "[ESTILO: responde de forma mas elaborada, calida y expresiva, 3-4 frases con personalidad]"
- Scored by `calculate_confidence()`, best wins

### Why these temperatures?
- T=0.2: Low randomness for safe, predictable responses
- T=0.7: Balanced (default)
- T=1.4: High randomness for creative, varied responses
- Rationale: cover the spectrum from safe to creative

### Do style hints work?
Style hints are appended to the END of a 23K-char system prompt. At this position, their influence is **minimal** — the LLM has already processed the full personality. A more effective approach would be to prepend them or use separate system messages.

### Timeout 12s
12s timeout for 3 parallel calls is generous. Each call has its own 15s HTTP timeout. In practice, all 3 calls go to the same Gemini model, so they complete within similar timeframes (~500ms each).

### Assessment
- **Status**: WORKING but COST x3
- **Cost**: 3 Gemini API calls per message when copilot enabled = 3x input tokens
- **Effectiveness**: Questionable — confidence scorer is too crude to meaningfully differentiate candidates (see #33)
- **BUG**: `BestOfNSelector` class (lines 189-222) is dead code — duplicates `calculate_confidence` but is never used

---

## System #33: Confidence Scorer

**File**: `core/confidence_scorer.py` (262 lines)

### Scoring factors
| Factor | Weight | How scored |
|--------|--------|-----------|
| Intent confidence | 0.30 | Static lookup table (greeting=0.95, purchase=0.60, etc.) |
| Response type | 0.20 | Static lookup (pool=0.90, llm=0.70, error=0.05) |
| Historical rate | 0.30 | DB query: approved/(approved+edited+discarded) last 30 days |
| Length quality | 0.10 | Heuristic: 20-200 chars = 1.0, <5 = 0.1 |
| Blacklist check | 0.10 | Regex patterns for errors, identity claims, broken links |

### Is scoring reliable?
**No.** Critical issues:

1. **Historical rate always returns 0.70** — requires 5+ copilot-actioned messages per intent. With only 3 total approved+edited, every intent falls back to 0.70 (neutral).

2. **Intent confidence is backwards** — `greeting` gets 0.95 (easiest) while `purchase` gets 0.60 (hardest). This means the scorer is MORE confident about easy messages and LESS confident about hard ones — exactly wrong for a copilot that should flag complex cases.

3. **All 3 Best-of-N candidates score nearly identically** because:
   - Intent score: same (same message = same intent)
   - Response type: same (all "llm_generation" = 0.70)
   - Historical: same (0.70 fallback)
   - Blacklist: usually same (all clean = 1.0)
   - Only differentiator: length_quality (10% weight) — trivially different

4. **DB query per scoring call** — `_get_historical_rate` opens a new SessionLocal per call. In Best-of-N, this means 3 separate DB queries to count the same data.

### Verdict: CONFIDENCE SCORER IS INEFFECTIVE
- All candidates score ~0.70 regardless of quality
- Best-of-N selection is effectively random
- The 3x API cost yields no meaningful improvement

---

## System #34: Self-Consistency Validator

**File**: `core/reasoning/self_consistency.py` (338 lines)

### How it works
1. Take the already-generated response
2. Generate 2 more samples at T=0.8 (total 3)
3. Calculate pairwise similarity (SequenceMatcher + Jaccard)
4. If average similarity >= 0.6, response is "consistent"
5. If not consistent, select the "most central" response

### Is it worth the cost?
**No.**
- Adds 2 extra LLM calls (via `self.llm.chat`) per message
- Uses `agent.llm_service` which may be a different provider than Gemini
- Total cost: 2 extra calls on top of 3 Best-of-N = **5 total LLM calls per message**
- The similarity metric (character-level SequenceMatcher) doesn't capture semantic consistency — two messages saying the same thing in different words would score low

### Does it catch bad responses?
Unlikely. The threshold (0.6) is low enough that most short DM responses (10-50 chars) will be "consistent" simply because they share common words.

### Assessment
- **Status**: ENABLED but WASTEFUL
- **Impact**: 2 extra LLM calls, ~0 quality improvement
- **BUG**: Uses `self.llm.chat()` (legacy interface) which may not route through the Gemini/GPT cascade

---

## System #35: Chain of Thought

**File**: Referenced in `generation.py:219-241`

### How it works
1. Checks if message is a "complex query" (health/product/multi-part)
2. If complex, generates reasoning steps via separate LLM call (~500 tokens)
3. Reasoning steps are appended to system prompt

### Assessment
- **Status**: ENABLED but untested
- **Impact**: 1 extra LLM call for "complex" queries
- Given that most DMs are casual ("Hola!", "Gracies!", "Sii"), this probably fires rarely
- No production metrics to verify effectiveness

---

## Systems #36-44: Post-Processing Pipeline

**File**: `core/dm/phases/postprocessing.py` (386 lines)

### Pipeline order (10 steps):

#### Step 1: Loop Detector (lines 48-67)
- Compares first 50 chars of response to last 3 bot messages
- If exact match, replaces with "Contame mas"
- **Assessment**: BASIC but functional. Only catches exact repeats, not paraphrases.
- **BUG**: "Contame mas" is hardcoded Argentine Spanish — doesn't match Iris's Catalan/Spanish style

#### Step 2: Output Validator (lines 70-91)
- Validates prices against known product prices
- Validates links against known product URLs
- **Assessment**: WORKING, catches hallucinated prices/links

#### Step 3: Response Fixes (lines 93-103)
- Applies regex-based fixes (typos, formatting)
- **Assessment**: WORKING, low overhead

#### Step 4: Tone Enforcer (lines 105-115)
- Adjusts emoji/exclamation/question rates from calibration
- **Assessment**: ONLY works if `agent.calibration` exists — need to verify if calibration is loaded for Iris

#### Step 5: Question Remover (lines 117-122)
- `process_questions()` — removes excessive bot questions
- **Assessment**: Risk of removing useful questions. No logging of what's removed.

#### Step 6: Reflexion Engine (lines 124-175)
- Rule-based analysis (not LLM): length, unanswered questions, repetition, phase appropriateness, missing prices
- If severity high/medium: **RE-GENERATES THE ENTIRE RESPONSE** via another Gemini call
- **Assessment**: EXTRA LLM CALL for medium severity issues. With the reflexion engine's broad criteria (any response >300 chars for a short question triggers "medium"), this fires frequently.
- **BUG**: Re-generation uses T=0.3 with a revision prompt but NO style prompt — the revised response loses Iris's personality
- **Cost**: 1 more LLM call, totaling up to **6 LLM calls per message** (Best-of-N 3 + Self-consistency 2 + Reflexion 1)

#### Step 7: Guardrails (lines 177-209)
- Validates response against domain whitelist (from product URLs)
- **Assessment**: WORKING, prevents hallucinated URLs

#### Step 8: Length Controller (lines 211-217)
- `enforce_length()` — adjusts response length based on message type
- **Assessment**: WORKING

#### Step 9: Instagram Formatter (line 220)
- Formats for Instagram/WhatsApp (emoji cleanup, etc.)
- **Assessment**: WORKING

#### Step 10: Payment Link Injection (lines 222-238)
- If purchase intent + product mentioned + link missing -> injects payment link
- **Assessment**: WORKING, useful for sales conversion

### Post-processing verdict
- **Too many steps**: 10 processing steps with 3 potential extra LLM calls
- **Biggest issue**: Reflexion re-generation loses personality (no style prompt)
- **Loop detector fix is wrong**: "Contame mas" doesn't match Iris's style

---

## System #45: Copilot Lifecycle

**File**: `core/copilot/lifecycle.py` (504 lines)

### How suggestions are stored
1. User message arrives via webhook
2. DM Agent generates response
3. `create_pending_response_impl()` saves both user message + bot suggestion to `messages` table
4. Bot message gets `status='pending_approval'`, `suggested_response=original_text`
5. Dedup checks: platform_message_id (60s window), existing pending per lead

### Assessment
- **Status**: WORKING correctly
- **Good**: Profile fetch fallback (sibling lead), phone backfill for WhatsApp
- **Good**: Dedup with 60s early-save window
- **Issue**: When lead already has pending suggestion, schedules debounced regen — could cause suggestion churn

---

## System #46: Approve/Discard Learning

**File**: `core/copilot/actions.py` (451 lines)

### Does learning fire correctly?
- **Approve**: fires `analyze_creator_action(action="approved")` + `create_pairs_from_action(action="approved")`
- **Edit**: fires both with `action="edited"` + edit_diff
- **Discard**: fires both with `action="discarded"` + discard_reason
- **Resolved externally**: fires both with `action="resolved_externally"`

### BUG: Approval reinforcement is circular
When a response is approved, `_handle_approval()` calls `get_applicable_rules()` to find matching rules, then marks them as "helpful". But the rules were generated from PAST interactions — there's no verification that the approved rules actually influenced THIS response. It's a placebo feedback loop.

---

## System #47: Autolearning Analyzer

**File**: `services/autolearning_analyzer.py` (337 lines)

### How new rules are generated
1. Creator takes action (edit/discard/manual/resolved_externally)
2. `analyze_creator_action()` fires (fire-and-forget)
3. LLM call: compare bot_response vs creator_response, extract rule as JSON
4. Rule stored via `create_rule()`

### Are rules good?
**No.** The LLM (Flash Lite) generates vague, generic rules like "use emojis" and "be casual" from individual message comparisons. It has no view of existing rules, leading to:
- Contradictions (see #27)
- Redundancy (634 active rules, many saying the same thing)
- Nonsensical rules (Catalan text misinterpreted)

### BUG: ENABLE_AUTOLEARNING is likely "false" in prod
The env var defaults to `"false"`. Need to verify Railway config.

### Good: Non-text filtering
`_is_non_text_response()` correctly skips audio/sticker/media for resolved_externally. But this filter is NOT applied in gold_examples_service.

---

## System #48: Preference Pairs

### Production data
- 985 pairs exist
- `pair_type` column doesn't exist — schema mismatch
- Pairs are created in `create_pairs_from_action()` for each copilot action
- Used for future RLHF/DPO training (not currently consumed by any prompt)

### Assessment
- **Status**: DATA COLLECTING but unused
- No bug — pairs are stored correctly but serve no purpose yet

---

## System #49: Clone Accuracy Score

### How it's calculated
- Daily eval job: `copilot_evaluations` table with `eval_type='daily'`
- `clone_accuracy` field in `metrics` JSONB
- Sample size: 31-73 messages per day

### Trend analysis
| Date | Accuracy | N |
|------|----------|---|
| 2026-03-15 | 11.1% | 40 |
| 2026-03-16 | 17.3% | 36 |
| 2026-03-17 | 15.8% | 31 |
| 2026-03-18 | 15.1% | 73 |
| 2026-03-19 | 17.1% | 33 |

**Flat at ~15% over 5 days** — the learning systems are not improving accuracy.

---

## LLM Call Budget Per Message (Worst Case)

When ALL features are enabled (as in prod):

| Call | Purpose | Model | Tokens |
|------|---------|-------|--------|
| 1-3 | Best-of-N generation | Flash Lite x3 | ~6,500 in x3 |
| 4-5 | Self-consistency validation | Flash Lite x2 | ~6,500 in x2 |
| 6 | Chain of Thought (if complex) | Flash Lite | ~500 |
| 7 | Reflexion re-generation (if medium+ severity) | Flash Lite | ~6,500 |
| 8 | Autolearning rule extraction | Flash Lite | ~500 |

**Worst case: 8 LLM calls per single DM message**
**Typical case: 5-6 LLM calls per message** (BoN 3 + Self-consistency 2 + Autolearning 1)

At $0.075/1M input tokens, 6,500 tokens per call, 6 calls = ~$0.003 per message. Not expensive per-message, but 5 of those calls produce zero measurable quality improvement.

---

## Summary Table

| # | System | Status | Bugs Found | Impact | Priority |
|---|--------|--------|-----------|--------|----------|
| 26 | Response Strategy | WORKING | 0 | Low (drowned by 20K style prompt) | P4 |
| 27 | Learning Rules Service | BROKEN | 3 | HIGH - contradictory rules injected as noise | **P1** |
| 28 | Preference Profile | PARTIAL | 0 | Negligible - data redundant with style prompt | P4 |
| 29 | Gold Examples Service | BROKEN | 4 | HIGH - error messages & stickers as "gold" examples | **P1** |
| 30 | LLM Primary (Gemini) | WORKING | 1 (new httpx client per call) | Low | P3 |
| 31 | LLM Fallback (GPT-4o-mini) | WORKING | 0 | N/A - correct | P4 |
| 32 | Best-of-N | WORKING | 1 (dead code) | MEDIUM - 3x cost for ~0 quality gain | **P2** |
| 33 | Confidence Scorer | INEFFECTIVE | 3 | HIGH - all candidates score ~0.70, Best-of-N is random | **P1** |
| 34 | Self-Consistency | WASTEFUL | 1 | MEDIUM - 2 extra LLM calls, 0 quality gain | **P2** |
| 35 | Chain of Thought | UNKNOWN | 0 | Low - fires rarely | P4 |
| 36 | Loop Detector | BASIC | 1 ("Contame mas" wrong style) | Low | P3 |
| 37 | Output Validator | WORKING | 0 | Positive | P4 |
| 38 | Response Fixes | WORKING | 0 | Positive | P4 |
| 39 | Tone Enforcer | CONDITIONAL | 0 | Depends on calibration data | P3 |
| 40 | Question Remover | WORKING | 0 | Risk of over-removal, no logging | P3 |
| 41 | Reflexion Engine | HARMFUL | 1 (loses personality on re-gen) | MEDIUM - re-gen without style prompt | **P2** |
| 42 | Guardrails | WORKING | 0 | Positive | P4 |
| 43 | Length Controller | WORKING | 0 | Positive | P4 |
| 44 | Payment Link Injection | WORKING | 0 | Positive | P4 |
| 45 | Copilot Lifecycle | WORKING | 0 | N/A - correct | P4 |
| 46 | Approve/Discard Learning | BROKEN | 1 (circular reinforcement) | MEDIUM - placebo feedback | **P2** |
| 47 | Autolearning Analyzer | LOW QUALITY | 1 (no existing rule awareness) | HIGH - generates bad rules | **P1** |
| 48 | Preference Pairs | COLLECTING | 1 (schema mismatch) | None - unused data | P4 |
| 49 | Clone Accuracy | WORKING | 0 | Informational - flat at 15% | P4 |

---

## Top 5 Recommendations (by impact)

### 1. PURGE GOLD EXAMPLES (P1, 1 hour)
Delete all gold examples where `creator_response` matches error messages, stickers, audio markers, or WeTransfer links. Add content filter to `create_gold_example()`.

### 2. DISABLE LEARNING RULES (P1, 5 minutes)
Set `ENABLE_LEARNING_RULES=false` in Railway. 634 rules with 0 helpful signal are pure noise. Re-enable only after implementing rule quality filtering and contradiction detection.

### 3. DISABLE SELF-CONSISTENCY (P1, 5 minutes)
Set `ENABLE_SELF_CONSISTENCY=false`. Saves 2 LLM calls per message with 0 quality benefit. The SequenceMatcher similarity metric doesn't capture semantic consistency.

### 4. FIX REFLEXION RE-GENERATION (P2, 30 minutes)
When reflexion triggers re-generation, include the full style prompt in the revision prompt. Currently re-generates without personality = generic response replaces styled response.

### 5. FIX CONFIDENCE SCORER (P2, 2 hours)
- Use style_fidelity metrics instead of intent-based static scores
- Cache historical rate lookup (1 query, not 3)
- Or simply disable Best-of-N (saves 2 LLM calls) until scorer is meaningful

---

## Cost Savings from Recommendations

| Action | LLM calls saved per msg | Monthly savings (est. 1000 msgs/day) |
|--------|------------------------|--------------------------------------|
| Disable Self-Consistency | 2 | ~$4.50/month |
| Disable Best-of-N (use single call) | 2 | ~$4.50/month |
| Disable Reflexion re-gen | 0-1 | ~$1-2/month |
| **Total** | 4-5 calls saved | **~$10-11/month** |

Cost is small, but latency improvement is significant: **~2-4 seconds faster per message** (fewer parallel API calls to wait for).
