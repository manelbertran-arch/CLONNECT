# Cross-System Architecture Audit — Clonnect DM Pipeline

**Date**: 2026-04-07
**Auditor**: Claude Opus 4.6 (Architecture Agent)
**Scope**: 23 systems (10 P0 + 13 P1), full prompt assembly + post-processing chain

---

## 1. PROMPT SNAPSHOT

### Architecture Overview

The DM pipeline has **5 phases**:

```
Phase 1 (Detection)    → Input guards, pool fast-path
Phase 2-3 (Context)    → Intent, parallel DB/IO, context assembly, system prompt build
Phase 4 (Generation)   → Strategy, few-shots, question hints, LLM call
Phase 5 (Postprocess)  → Guardrails, style normalization, splitting
```

### Prompt Assembly Points

There are **TWO prompt assembly points** — this is a critical architectural fact:

1. **System Prompt** (`services/prompt_service.py:PromptBuilder.build_system_prompt`)
   - Called at `core/dm/phases/context.py:995`
   - Receives `products` + `custom_instructions` (the assembled context)
   - Adds personality knowledge, product list, safety rules

2. **User Prompt** (`core/dm/phases/generation.py:320-337`)
   - Built from: preference_profile + gold_examples + strategy_hint + question_hint + user_message
   - Passed as the `user` role message in the multi-turn conversation

### System Prompt Structure (assembled in context.py:950-990)

The `custom_instructions` string injected into PromptBuilder contains these sections in priority order:

```
[POSITION 1] style_prompt        — Doc D / compressed Doc D + ECHO data-driven style
[POSITION 2] few_shot_section    — Calibration few-shot examples (3-5 examples)
[POSITION 3] friend_context      — (currently always empty "")
[POSITION 4] recalling_block     — Consolidated per-lead context:
                                    ├── relational_block (ECHO Relationship Adapter)
                                    ├── dna_context (RelationshipDNA + lead profile)
                                    ├── state_context (Conversation State Machine)
                                    ├── episodic_context (Episodic Memory)
                                    ├── frustration_note
                                    ├── context_notes (question context, length/question hints)
                                    └── memory_context (Memory Engine facts)
[POSITION 5] audio_context       — Audio intelligence transcription
[POSITION 6] rag_context         — RAG retrieval results (last = high attention)
[POSITION 7] kb_context          — Knowledge Base lookup
[POSITION 8] hier_memory_context — Hierarchical Memory (IMPersona-style, OFF by default)
[POSITION 9] advanced_section    — Advanced prompt rules (OFF by default)
[POSITION 10] citation_context   — Citation references
[POSITION 11] prompt_override    — Manual override from metadata
```

After custom_instructions, PromptBuilder appends:
- Creator knowledge (website, bio, expertise, location)
- Product list with prices and links
- Safety guardrails ("IMPORTANTE" section)

### User Message Structure (generation.py:320-337)

```
[USER MSG 1] preference_profile_section  — (OFF by default, ENABLE_PREFERENCE_PROFILE)
[USER MSG 2] gold_examples_section       — (OFF by default, ENABLE_GOLD_EXAMPLES)
[USER MSG 3] strategy_hint               — Response strategy instruction
[USER MSG 4] question_hint               — "NO incluyas pregunta" (probabilistic)
[USER MSG 5] message                     — Actual user message (last = highest attention)
```

### Full LLM Messages Array (generation.py:388-416)

```
messages = [
  {"role": "system", "content": system_prompt},        # ~4-8K chars
  {"role": "user",   "content": history[0].content},   # last 10 msgs
  {"role": "assistant", "content": history[1].content},
  ...                                                   # alternating turns
  {"role": "user",   "content": full_prompt},           # strategy + message
]
```

### Token Estimate (Prompt Snapshot — cannot generate live without DB)

Cannot generate a live prompt without Railway DB access. Based on code analysis:

| Section | Estimated chars | Est. tokens (chars/4) |
|---------|---------------:|----------------------:|
| Doc D / style_prompt | 1,300 | 325 |
| Few-shot examples (5x) | 800 | 200 |
| Recalling block | 500-1,200 | 125-300 |
| RAG context (3 results) | 300-600 | 75-150 |
| Products + knowledge | 400-800 | 100-200 |
| Conversion instructions | 800 | 200 |
| Absolute rules | 400 | 100 |
| Safety section | 200 | 50 |
| History (10 msgs) | 1,500-3,000 | 375-750 |
| Strategy + user msg | 200-400 | 50-100 |
| **TOTAL** | **6,400-9,500** | **1,600-2,375** |

**Conclusion**: Within Gemini Flash-Lite's context window. For Gemma4-26B (8K effective), the prompt is borderline at ~2K tokens; the MAX_CONTEXT_CHARS=40000 env var provides the budget cap, and `_smart_truncate_context` handles overflow.

---

## 2. INJECTION MAP

### Pre-LLM Injection Systems

| # | System | Type | Position | Est. Tokens | Content |
|---|--------|------|----------|-------------|---------|
| 1 | **Doc D / Style Prompt** | inject | system[1] (custom_instructions top) | 325 | Personality: identity, BFI traits, style constraints, vocabulary, emoji/excl rates |
| 2 | **ECHO Style Analyzer** | inject | appended to style_prompt | 50-100 | Data-driven quantitative style metrics from StyleProfile DB |
| 3 | **Calibration Few-shots** | inject | system[2] (post-style) | 200 | 3-5 real creator responses, intent-stratified + semantic hybrid |
| 4 | **Gold Examples** (OFF) | inject | user msg (pre-message) | 0 (OFF) | DNA golden_examples from gold_examples_service |
| 5 | **Relationship Adapter** | inject | system[4] recalling.relational | 50-100 | ECHO relational instructions (warmth, tone modulation) |
| 6 | **DNA Engine** | inject | system[4] recalling.dna | 100-200 | RelationshipDNA + merged lead profile (unified context) |
| 7 | **Conversation State** | inject | system[4] recalling.state | 30-50 | Phase machine state (greeting, engaged, closing, etc.) |
| 8 | **Memory Engine** | inject | system[4] recalling.memory | 50-150 | Extracted facts from past conversations |
| 9 | **Episodic Memory** (OFF) | inject | system[4] recalling.episodic | 0 (OFF) | Raw conversation snippets via embedding search |
| 10 | **Hierarchical Memory** (OFF) | inject | system[8] | 0 (OFF) | IMPersona 3-level memory (L1+L2+L3) |
| 11 | **RAG Service** | inject | system[6] (last for attention) | 75-150 | Product/FAQ/content chunks from pgvector |
| 12 | **Knowledge Base** | inject | system[7] | 20-50 | In-memory keyword lookup results |
| 13 | **Context Detector** | inject | system[4] recalling.context_notes | 10-30 | B2B, sarcasm, question context signals |
| 14 | **Frustration Detector** | inject | system[4] recalling.frustration_note | 10-20 | Frustration level note |
| 15 | **Audio Intelligence** | inject | system[5] | 50-200 | Transcription, entities, emotional tone |
| 16 | **Response Strategy** | inject | user msg (pre-message) | 30-50 | Strategy instruction (help/personal/sales/reactivation) |
| 17 | **Question Hint** | inject | user msg (pre-message) | 5-10 | "NO incluyas pregunta" (probabilistic) |
| 18 | **Length Hint** | inject | system[4] recalling.context_notes | 10-15 | Data-driven length target from length_by_intent.json |
| 19 | **Citation Service** | inject | system[10] | 0-30 | Citation references from creator content |
| 20 | **Preference Profile** (OFF) | inject | user msg (first) | 0 (OFF) | Lead preference profile from DPO pairs |
| 21 | **Prompt Builder (core/)** | inject | NOT USED in DM pipeline | 0 | Only used via build_prompt_from_ids() convenience — NOT the DM path |

### Post-LLM Processing Systems

| # | System | Type | Position in chain | Content |
|---|--------|------|-------------------|---------|
| P1 | **Loop Detector (A2/A2b/A2c)** | postproc | Step 1 | Repetition detection (inter/intra-response), sentence dedup |
| P2 | **Anti-Echo (A3)** | postproc | Step 2 | Jaccard similarity check, replaces echoed content |
| P3 | **Output Validator** | postproc | Step 3 | Link validation against known URLs |
| P4 | **Response Fixes** | postproc | Step 4 | Price typos, broken links, identity fixes |
| P5 | **Blacklist Replacement** | postproc | Step 5 (OFF) | Doc D word/emoji replacement |
| P6 | **Question Remover** | postproc | Step 6 | Removes banned generic questions |
| P7 | **Reflexion** (OFF) | postproc | Step 7 | Quality analysis (legacy) |
| P8 | **Score Before Speak** (OFF) | postproc | Step 8 | PPA alignment scoring + retry |
| P9 | **Guardrails** | postproc | Step 9 | Price validation, URL whitelist |
| P10 | **Length Controller** | postproc | Step 10 | Enforce soft length by message type |
| P11 | **Style Normalizer** | postproc | Step 11 | Emoji/exclamation rate matching |
| P12 | **Message Splitter** | postproc | Step 12 | Multi-bubble splitting |

### Phase 1 Systems (Pre-pipeline)

| # | System | Type | Action |
|---|--------|------|--------|
| D1 | **Sensitive Detector** | gate | Crisis detection → early return with resources |
| D2 | **Pool Matching** | gate | Short message fast-path → skip LLM entirely |
| D3 | **Prompt Injection Detection** | flag | Observability only, no blocking |
| D4 | **Media Placeholder Detection** | flag | Flags platform placeholders for context |

---

## 3. OWNERSHIP VERIFICATION

### 3.1 Few-shots: DNA golden_examples vs Calibration few-shots

**Status: CUMPLE (by design separation — both OFF or non-conflicting)**

Evidence:
- **Calibration few-shots** (`ENABLE_FEW_SHOT=true`): Loaded at `context.py:705-720` via `get_few_shot_section()`. Max 5 examples (`max_examples=5`). Always active when calibration exists.
- **Gold examples** (`ENABLE_GOLD_EXAMPLES=false`): Loaded at `generation.py:278-315`. Feature-flagged OFF in production. When ON, injected in USER message (different position than calibration few-shots in SYSTEM prompt).
- **Simultaneous use**: If both are ON, they would both inject — calibration in system prompt, gold in user message. This is NOT prevented by code, but gold is OFF in production so no conflict.
- **No 5+ msg gate**: Gold examples do NOT check `lead.total_messages >= 5`. They select by intent, relationship_type, lead_stage, and language.

**Assessment**: No active violation. However, if gold examples are enabled in the future, both would inject simultaneously. **Recommendation**: Add mutual exclusion guard.

### 3.2 Length control: Style Normalizer as sole length manipulator

**Status: VIOLA**

Evidence of MULTIPLE length manipulation points:
1. **Length Controller** (`services/length_controller.py`): `enforce_length()` called at `postprocessing.py:337`. Detects message type, enforces soft_max with truncation.
2. **Style Normalizer** (`core/dm/style_normalizer.py`): `normalize_style()` called at `postprocessing.py:347`. Handles emoji/exclamation rate normalization — does NOT manipulate length directly.
3. **Calibration max_tokens** (`generation.py:450`): `_llm_max_tokens` from calibration baseline controls LLM output token limit.
4. **Length hints** injected into prompt at `context.py:852-863`: Data-driven target from `length_by_intent.json`.
5. **MAX_CONTEXT_CHARS** budget at `context.py:935`: Truncates context sections.

**Violation**: Style Normalizer does NOT own length. Length Controller (`services/length_controller.py`) is the actual post-processing length enforcer. Calibration provides CONFIG (max_tokens, soft_max) and length hints provide prompt guidance. **Three systems touch length**: hints (pre-LLM), max_tokens (generation), Length Controller (post-LLM).

**Assessment**: This is a distributed responsibility, not centralized in Style Normalizer. The current design is reasonable but violates the stated ownership.

### 3.3 Vocabulary: Doc D base + DNA additive

**Status: CUMPLE**

Evidence:
- **Doc D** (`compressed_doc_d.py:152-184`): `_get_characteristic_vocab()` extracts top_50 vocabulary + greeting openers from baseline metrics. Injected as part of style_prompt.
- **DNA context** (`dm_agent_context_integration.py:149-180`): `_format_dna_for_prompt()` includes `shared_vocabulary`, `recurring_topics`, and `preferred_topics` from the relationship DNA.
- **Single section**: Both are assembled into one system prompt. DNA extends vocabulary per-lead. Doc D provides the creator-wide base.
- **No conflict**: DNA vocabulary is additive — it includes lead-specific shared terms that complement the base.

### 3.4 Response pools: Calibration Loader as owner, Variator as consumer

**Status: VIOLA**

Evidence:
- **ResponseVariatorV2** (`services/response_variator_v2.py:112-182`): Has hardcoded `_setup_fallback_pools()` with 16 categories of generic responses. These are NOT from calibration — they are generic Spanish phrases.
- **Creator-specific pools**: Loaded lazily per-creator via `_load_extraction_pools(creator_id)` which reads from Doc D extraction or calibration JSON.
- **Fallback vs override**: The fallback pools are only used when no creator-specific pool exists for a category (`if cat not in self.pools or not self.pools[cat]`).
- **Echo fallbacks** in anti-echo (`postprocessing.py:148`): Hardcoded `_ECHO_FALLBACKS = ["ja", "vale", "uf", "ok", "entes", "vaja"]`.

**Violation**: ResponseVariatorV2 has 16 categories of hardcoded pools (158 total responses). While they serve as fallbacks for creators without calibration, they ARE hardcoded responses that bypass calibration ownership. The anti-echo also has 6 hardcoded fallbacks.

**Assessment**: The fallback pools are architecturally necessary for new creators without calibration data. The violation is the anti-echo hardcoded fallbacks — these should come from calibration or use a more neutral approach.

### 3.5 Blacklists: Three separate layers

**Status: CUMPLE**

Evidence:
- **Guardrails** (`core/guardrails.py`): Security layer — validates prices, URLs, product information against known data. Called at `postprocessing.py:301-332`.
- **Calibration blacklist** (`services/calibration_loader.py:42-184`): Style layer — `_load_creator_vocab()` extracts prohibited words/emojis/phrases from Doc D. Used for: (a) filtering few-shot examples via `_filter_blacklisted_examples()`, (b) post-processing replacement via `apply_blacklist_replacement()`.
- **Output Validator** (`core/output_validator.py`): Technical layer — validates links only (`validate_links()`). Checks URLs against whitelist.
- **Question Remover** (`services/question_remover.py`): Separate concern — removes banned generic questions.

**Assessment**: Three distinct blacklist concerns (security, style, technical) are properly separated.

### 3.6 Tone/voice: Doc D as sole personality prompt

**Status: CUMPLE (with caveat)**

Evidence:
- **Doc D** is the primary personality prompt, loaded via `services/creator_style_loader.py` as `style_prompt`. It is the FIRST section in the system prompt (highest priority).
- **PromptBuilder** (`services/prompt_service.py:68-69`): Uses `personality.tone` for tone config BUT only appends creator knowledge (website, bio) — does NOT inject a competing voice prompt.
- **ECHO Style Analyzer** (`agent.py:267-309`): APPENDS quantitative data to style_prompt — does not compete, extends.
- **Relationship Adapter** (`context.py:880-927`): Generates `relational_block` with warmth/tone modulation — this IS a potential competing voice, but it modulates rather than defines base voice.

**Caveat**: The calibration system does NOT have a separate `voice_prompt`. However, the Relationship Adapter's `prompt_instructions` can inject tone guidance that competes with Doc D when the adapter is enabled (`ENABLE_RELATIONSHIP_ADAPTER=false` in production — correctly disabled per MEMORY.md).

---

## 4. TOKEN BUDGET

### Current Budget (Gemini Flash-Lite, 1M context)

No token pressure on Gemini. The prompt averages ~2K tokens, well within limits.

### Hypothetical Gemma4-26B Budget (8K effective)

| Section | Tokens | Priority | Recency Position |
|---------|--------|----------|-----------------|
| Doc D / style | 325 | CRITICAL | Top (cacheable) |
| Few-shots | 200 | CRITICAL | Near top |
| History (10 msgs) | 375-750 | HIGH | Multi-turn messages |
| Recalling block | 125-300 | HIGH | Middle |
| Products | 100-200 | HIGH | After custom_instructions |
| RAG context | 75-150 | HIGH | End of custom_instructions |
| Conversion instructions | 200 | MEDIUM | After products |
| Absolute rules | 100 | MEDIUM | Last system section |
| Strategy + user msg | 50-100 | HIGH | User message (last) |
| **TOTAL** | **1,550-2,325** | | |

**Assessment**: Fits within 4K budget (Gemma4-26B half-window). If budget pressure occurs:

**Recort priority (Lost in the Middle — cut middle first)**:
1. **Cut FIRST**: Conversion instructions (200 tokens, middle position, generic)
2. **Cut SECOND**: Knowledge base context (20-50 tokens, low value unless hit)
3. **Cut THIRD**: Citation context (0-30 tokens, rarely relevant)
4. **Reduce**: Few-shots from 5 to 3 (save ~80 tokens)
5. **Reduce**: History from 10 to 6 messages (save ~200 tokens)

---

## 5. CONFLICT RESOLUTION

### Violation 3.2: Length Control Ownership

**Conflict**: Three systems manipulate length (hints, max_tokens, Length Controller). The ownership decision says Style Normalizer should be the sole manipulator.

**Resolution**: This is a DESIGN CLARIFICATION, not a code bug. The current distributed approach is correct:
- Length hints = pre-LLM guidance (soft, prompt-based)
- max_tokens = generation cap (hard, API-level)
- Length Controller = post-LLM enforcement (soft, truncation-based)
- Style Normalizer = metric matching (emoji/excl rate, NOT length)

**Decision needed**: Update ownership document to reflect reality: Length Controller owns post-LLM length enforcement, Calibration provides config, length hints provide pre-LLM guidance. Style Normalizer does NOT own length.

### Violation 3.4: Hardcoded Fallback Pools

**Conflict**: ResponseVariatorV2 has 158 hardcoded fallback responses across 16 categories.

**Resolution**: This is architecturally necessary for new creators. However, the anti-echo hardcoded fallbacks in postprocessing.py should be configurable.

**No code fix applied** — these fallbacks are the safety net for creators without calibration. Removing them would break the system for new creators. The correct fix is to ensure calibration is generated early in onboarding, making fallbacks rarely used.

---

## 6. EXECUTION ORDER AUDIT

### Expected Order
```
Style Normalizer -> Question Remover -> Anti-Echo -> Output Validator -> Message Splitting -> Guardrails
```

### Actual Order (from postprocessing.py)

```
Step 1:  Loop Detector A2  (exact duplicate check — LOG ONLY)        [L:41-63]
Step 2:  Loop Detector A2b (intra-response repetition — TRUNCATE)    [L:69-90]
Step 3:  Loop Detector A2c (sentence-level dedup)                    [L:97-122]
Step 4:  Anti-Echo A3      (Jaccard similarity → replace)            [L:131-157]
Step 5:  Output Validator  (link validation)                         [L:161-168]
Step 6:  Response Fixes    (price typos, broken links)               [L:171-179]
Step 7:  Blacklist Replace (Doc D word/emoji substitution, OFF)      [L:185-195]
Step 8:  Question Remover  (banned generic questions)                [L:200-217]
Step 9:  Reflexion         (quality analysis, OFF)                   [L:220-236]
Step 10: Score Before Speak / PPA (alignment scoring, OFF)           [L:245-298]
Step 11: Guardrails        (price/URL security validation)           [L:301-332]
Step 12: Length Controller  (enforce soft length by type)             [L:335-339]
Step 13: Style Normalizer  (emoji/excl rate matching)                [L:343-352]
Step 14: Instagram Format  (message formatting)                      [L:355]
Step 15: Payment Link Inject (purchase intent link)                  [L:358-372]
Step 16: Message Splitter  (multi-bubble splitting)                  [L:499-507]
```

### Comparison: Expected vs Actual

| Expected Position | Expected System | Actual Position | Actual System | Match? |
|:-:|:--|:-:|:--|:-:|
| 1 | Style Normalizer | 13 | Style Normalizer | NO |
| 2 | Question Remover | 8 | Question Remover | NO |
| 3 | Anti-Echo | 4 | Anti-Echo | YES (relative) |
| 4 | Output Validator | 5 | Output Validator | YES (relative) |
| 5 | Message Splitting | 16 | Message Splitter | YES (last) |
| 6 | Guardrails | 11 | Guardrails | NO |

### Order Divergences

1. **Style Normalizer at position 13 (expected 1)**: Currently runs AFTER guardrails and length controller. This is actually CORRECT — style normalization (emoji/excl stripping) should run AFTER content validation, not before. If it ran first, guardrails might flag a response that was about to be cleaned.

2. **Question Remover at position 8 (expected 2)**: Runs after response fixes and blacklist replacement. This is correct — question removal should operate on the cleaned response.

3. **Guardrails at position 11 (expected 6/last)**: Runs after question removal but before length/style. This means guardrails validate the content-clean response before cosmetic adjustments, which is correct.

### Assessment: Actual order is MORE CORRECT than expected

The actual order follows a logical pipeline:
```
Content Safety (loops, echoes) →
Technical Fixes (links, typos) →
Style Fixes (blacklist, questions) →
Quality Gates (reflexion, SBS) →
Security Validation (guardrails) →
Cosmetic Adjustments (length, style) →
Format & Split (Instagram format, multi-bubble)
```

This is the correct layering: security before cosmetics, content before format. **No correction needed.**

---

## 7. SYSTEM INVENTORY (23 Systems)

### P0 Systems (10 — Active in Production)

| # | System | File | Phase | Status |
|---|--------|------|-------|--------|
| 1 | Doc D / Compressed Doc D | `core/dm/compressed_doc_d.py` + `services/creator_style_loader.py` | inject | ON |
| 2 | Calibration Loader | `services/calibration_loader.py` | inject + config | ON |
| 3 | Response Variator V2 | `services/response_variator_v2.py` | Phase 1 gate | ON |
| 4 | RAG Service | `core/rag/semantic.py` | inject | ON (gated) |
| 5 | Memory Engine | `services/memory_engine.py` | inject + extract | ON |
| 6 | DNA Engine | `services/dm_agent_context_integration.py` | inject | ON |
| 7 | Conversation State | `core/conversation_state.py` | inject | ON |
| 8 | Style Normalizer | `core/dm/style_normalizer.py` | postproc | ON |
| 9 | Length Controller | `services/length_controller.py` | postproc | ON |
| 10 | Guardrails | `core/guardrails.py` | postproc | ON |

### P1 Systems (13 — Mixed ON/OFF)

| # | System | File | Phase | Status |
|---|--------|------|-------|--------|
| 11 | Context Detector | `core/context_detector/` | inject | ON |
| 12 | Frustration Detector | `core/frustration_detector.py` | inject | ON |
| 13 | Question Remover | `services/question_remover.py` | postproc | ON |
| 14 | Output Validator | `core/output_validator.py` | postproc | ON |
| 15 | Response Fixes | `core/response_fixes.py` | postproc | ON |
| 16 | Message Splitter | `services/message_splitter.py` | postproc | ON |
| 17 | Sensitive Detector | `core/sensitive_detector.py` | Phase 1 gate | ON |
| 18 | Relationship Scorer | `services/relationship_scorer.py` | inject (silent) | ON |
| 19 | ECHO Relationship Adapter | `services/relationship_adapter.py` | inject | OFF |
| 20 | Gold Examples | `services/style_retriever.py` | inject | OFF |
| 21 | Preference Profile | `services/preference_profile_service.py` | inject | OFF |
| 22 | Score Before Speak / PPA | `core/reasoning/ppa.py` | postproc | OFF |
| 23 | Blacklist Replacement | `services/calibration_loader.py:apply_blacklist_replacement` | postproc | OFF |

---

## 8. FIXES APPLIED

No code fixes were applied in this audit. All violations found are design-level clarifications, not code bugs:

1. **Length ownership (3.2)**: Requires ownership document update, not code change.
2. **Fallback pools (3.4)**: Architecturally necessary; removing would break new creator onboarding.
3. **Post-processing order (6)**: Actual order is more correct than expected; no change needed.

---

## 9. ISSUES REQUIRING HUMAN DECISION

### Issue 1: Gold Examples + Calibration Few-shots Mutual Exclusion
**When** ENABLE_GOLD_EXAMPLES is turned ON, both calibration few-shots (system prompt) AND gold examples (user message) would inject simultaneously. No code guard prevents this.
**Decision**: Should we add `if not gold_examples_section: inject calibration few-shots` guard? Or is dual injection intentional?

### Issue 2: Length Ownership Clarification
**Current state**: Three systems touch length (hints, max_tokens, Length Controller).
**Decision**: Update ownership spec to match reality, or refactor to centralize in one system?

### Issue 3: Anti-Echo Hardcoded Fallbacks
**Location**: `postprocessing.py:148` — `_ECHO_FALLBACKS = ["ja", "vale", "uf", "ok", "entes", "vaja"]`
**Decision**: Should these come from calibration? They are currently Catalan-biased ("entes" = "entendido" in Catalan), which would be wrong for Spanish-only creators.

### Issue 4: Relationship Adapter Re-enablement Risk
**Current state**: ENABLE_RELATIONSHIP_ADAPTER=false (correctly disabled). If re-enabled, its `prompt_instructions` would compete with Doc D personality.
**Decision**: If re-enabling, should Adapter's output be merged INTO Doc D section rather than injected as a separate relational_block?

### Issue 5: Prompt Builder Redundancy
**Observation**: `core/prompt_builder/` (orchestration.py with build_system_prompt) is NOT used in the DM pipeline. The DM pipeline uses `services/prompt_service.py:PromptBuilder` instead. The core prompt_builder is only used via `build_prompt_from_ids()` convenience function.
**Decision**: Deprecate/remove `core/prompt_builder/` or refactor DM pipeline to use it?
