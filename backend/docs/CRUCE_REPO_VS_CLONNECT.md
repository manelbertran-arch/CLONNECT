# Cruce Repo vs Clonnect — Pipeline Comparison

## 1. Prompt Structure

**Repo (DEEP_DIVE_CONTEXT_ENGINEERING.md:387–419):**
- System prompt assembled as array of strings (`systemPrompt: string[]`), passed via `QueryParams` (line 28).
- User context injected as separate user message via `prependUserContext()` (lines 389–400), which creates synthetic `<system-reminder>` tagged user message prepended to messages array.
- System context appended to system prompt array via `appendSystemContext()` (lines 405–418), which appends "key: value" entries to systemPrompt array.
- Attachments as separate user messages (lines 1580–1609 in getAttachmentMessages), each wrapped with `createAttachmentMessage()`.
- Conversation messages as their own array (line 338: `messages: Message[]`).
- Model receives: system prompt array → prependUserContext user message → conversation messages → attachment messages.

**Clonnect (DEEP_DIVE_CLONNECT_PIPELINE.md:204–225, 254–266):**
- Single system prompt string built via `PromptBuilder.build_system_prompt()` (services/prompt_service.py:51–125).
- All context concatenated into `combined_context` via `"\n\n".join(assembled)` (context.py:996), passed as `custom_instructions` embedded inside system prompt.
- No separate user context message; no system/user separation.
- No attachments as separate messages; no mechanism for per-turn attachment injection.
- History messages (up to last 10 turns) as `[{"role":"system",...}]` + history + `{"role":"user",...}` (generation.py:276–301).
- User message contains: `strategy_hint` + `_q_hint` + message text (generation.py:130–252).
- Model receives: system prompt string (with everything embedded) → history messages → user message with hints.

---

## 2. Injection Gating (How it Decides What to Include)

**Repo (DEEP_DIVE_CONTEXT_ENGINEERING.md:742–1003):**
- **Per-turn dynamic gates** via `getAttachments()` function; generates 0–60+ items based on current input turn.
- Attachment triggering conditions (lines 584–595):
  - Per-turn caps: MAX_MEMORY_BYTES = 4096 per file × 5 files.
  - Session-wide cap: RELEVANT_MEMORIES_CONFIG.MAX_SESSION_BYTES = 60KB.
  - Throttle intervals (plan mode every 5 turns, auto mode every 5 turns, todo/task reminders 10+ turns).
  - One-time events (date_change, plan_mode_exit, max_turns_reached).
  - Feature gates: BUDDY, TRANSCRIPT_CLASSIFIER, BG_SESSIONS, HISTORY_SNIP, KAIROS.
- No explicit per-message budget; attachments generated fresh each turn.
- `systemPromptSection()` with cache scoping (line 84).
- Feature flags eliminated at build time by bun:bundle (no runtime feature flag checks for many items).

**Clonnect (DEEP_DIVE_CLONNECT_PIPELINE.md:21–36, 397–427, 507–582):**
- **Static boolean flags** read at runtime via `os.getenv()` (context.py:21–36, 294, 371, 883). NOT per-turn gates.
- `MAX_CONTEXT_CHARS=8000` global budget with `_smart_truncate_context` (generation.py:245–250, context.py:936).
- `_sections` with ordinal priority (CRITICAL/HIGH/MEDIUM/FINAL) — listed lines 952–967.
- Selective truncation on overflow (context.py:980–989): skips sections in order until under budget.
- **Two adaptive gates**:
  - RAG: keyword signal gate + adaptive cosine similarity threshold (≥0.5 top 3, ≥0.40 top 1, <0.40 skip) (context.py:478–558).
  - Episodic memory: `len(_msg_stripped) >= 15 and len(_msg_words) >= 3` (context.py:316–318).

**Per-turn dynamic gates:**
- Repo: YES (getAttachments per-turn generation).
- Clonnect: NO (static env flags, global budget).

---

## 3. Static vs Dynamic Boundary

**Repo (DEEP_DIVE_CONTEXT_ENGINEERING.md:84, 448–450):**
- Explicit `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` separates cacheable from dynamic sections (referenced via `systemPromptSection()`, line 84).
- Cacheable (before boundary): intro, system rules, MCP instructions, tool descriptions.
- Dynamic (after boundary): session guidance, memory, env info, language, output style.
- Boundary enables server-side prompt caching benefit (repeated queries reuse cached system prompt).

**Clonnect (DEEP_DIVE_CLONNECT_PIPELINE.md:71–225, 951–967):**
- No explicit boundary declaration.
- Doc D (style_prompt, section 953): **static per-creator** — loaded once at agent init from DB/disk, same for all turns.
- Few-shots (section 954): **static per-creator** — loaded from calibration JSON, same for all messages.
- Friend context (section 956): **static** (always empty, 695).
- Recalling block (section 957): **dynamic per-message** — includes episodic memory (per-turn), DNA state (per-turn), conversation state (per-turn), relationship scoring (per-turn).
- Audio context (section 958): **dynamic per-message** — built from `metadata["audio_intel"]` (per-message).
- RAG context (section 960): **dynamic per-message** — search result varies per query signal and message content.
- All other sections: **dynamic per-turn** based on context assembly (recalling, DNA, state, etc.).
- All concatenated into single string with no cache distinction.

**Static per-creator sections in Clonnect:** style_prompt, few_shot_section, friend_context (3 sections).
**Dynamic per-message sections in Clonnect:** All others (recalling, audio, rag, kb, hierarchical, advanced, citation, etc.).

---

## 4. Post-Processing

**Repo (DEEP_DIVE_CONTEXT_ENGINEERING.md:129–145, 421–434):**
- Post-sampling hooks (query.ts:1000–1009): `executePostSamplingHooks()` fire-and-forget (not awaited).
- Hooks: extractMemory, skillImprovement, magicDocs.
- Stop hooks (query.ts:1267–1276): `handleStopHooks()` can prevent continuation but **do NOT modify content**.
- **Zero post-processing that mutates model output text.**
- Post-sampling hooks "do NOT modify the response" (line 144 explicit statement).

**Clonnect (DEEP_DIVE_CLONNECT_PIPELINE.md:310–342):**
- 27 steps in `phase_postprocessing` (postprocessing.py:26).

**Classification of 27 postprocessing steps:**

Mutate response text (11 steps):
- A2b [69–90] — repetition truncation (modify response)
- A2c [97–122] — sentence dedup (modify response)
- A3 [131–157] — echo detector Jaccard replacement (modify response)
- Question removal [200–217] (modify response)
- SBS [245–274] (can reemplaza response_content)
- PPA [277–298] (apply_ppa can replace)
- Guardrails [301–332] (validate_response can substitute corrected_response)
- Length control [335–340] (enforce_length modifies response)
- Style normalization [343–352] (normalize_style modifies response)
- Payment link injection [358–373] (append to response)
- Message splitting [498–507] (no direct modify of formatted_content)

Record metadata only (14 steps):
- A2 loop detect [47–63] (metadata["loop_detected"])
- Reflexion [220–236] (metadata only, no regenerate)
- CloneScore [379–390] (logging only)
- Lead score update [393] (sync, metadata)
- Conversation state [397–410] (async update, metadata)
- Email capture [413–425] (metadata, async)
- Background post-response [428–438] (fire-and-forget)
- Memory engine [442–464] (metadata, flag-gated)
- Commitment tracking [467–484] (fire-and-forget, flag-gated)
- Escalation [487–495] (fire-and-forget)
- Confidence scoring [518–530] (metadata only)
- Output validation [160–168] (logging via validate_links)
- Response fixes [171–180] (per docs apply_all_response_fixes, flag-gated)
- Blacklist replacement [185–195] (flag-gated, metadata)

Append content (2 steps):
- Payment link injection [358–373] (appends to response text)
- Message splitting [498–507] (stored in message_parts, not response text)

**Counts:** 11 mutate, 14 record metadata, 2 append. (Total 27)

---

## 5. Long-Context Management / Compaction

**Repo (DEEP_DIVE_CONTEXT_ENGINEERING.md:81–102, 164–177):**
- **Three strategies:**
  1. **microCompact** (line 413): Cleans tool results via `deps.microcompact()`, edits prompt cache with deferred boundary emission.
  2. **autoCompact** (line 453): Generates 9-section summary + `<analysis>` scratchpad via `deps.autocompact()`.
  3. **reactiveCompact** (line 1120): Recovers from prompt-too-long via `reactiveCompact.tryReactiveCompact()`.
- **Triggers:** `AUTOCOMPACT_BUFFER=13K tokens` (referenced line 724), `WARNING=20K tokens` (referenced line 637).
- **Circuit breaker:** `MAX_CONSECUTIVE_FAILURES=3` (referenced in state, line 54).
- **Post-compact session memory survives** and memories re-inject (line 100).

**Clonnect (DEEP_DIVE_CLONNECT_PIPELINE.md:254–266, 507–582, 557–575):**
- **No explicit compaction mechanism.**
- History limited to last N turns (generation.py:277–300, up to 10 turns).
- `MAX_CONTEXT_CHARS=8000` with truncation applied via `_smart_truncate_context` (generation.py:247–250).
- Individual messages truncated >600 chars (generation.py:298–299).
- No circuit breaker, no reactive recovery.
- No session memory that survives across conversation boundaries.

---

## 6. Persistent Memory (with Defaults)

**Repo (DEEP_DIVE_CONTEXT_ENGINEERING.md:587, 629–640):**
- **memdir/MEMORY.md** with `MAX_ENTRYPOINT_LINES=200`, `MAX_ENTRYPOINT_BYTES=25K` (NOT FOUND exact defaults in deep dive, inferred from query.ts references).
- **4 types:** user, feedback, project, reference (NOT FOUND detailed enumeration in deep dive).
- **extractMemories** auto-extraction post-sampling (line 144).
- **autoDream** consolidation every 24h + 5 sessions (NOT FOUND exact details in deep dive).
- **Session memory** with 9 sections, survives compaction (line 100).

**Clonnect (DEEP_DIVE_CLONNECT_PIPELINE.md:111–123, 173–176, 294, 362, 409–415):**
- `ENABLE_MEMORY_ENGINE` (default `false`, context.py:294) — OFF by default.
- `ENABLE_EPISODIC_MEMORY` (default `false`, context.py:32) — OFF by default.
- `ENABLE_HIERARCHICAL_MEMORY` (default `false`, context.py:31) — OFF by default.
- `ENABLE_COMMITMENT_TRACKING` (default `true`, context.py:371) — ON by default.
- DNA relational profile (ENABLE_DNA_AUTO_CREATE default true, ENABLE_DNA_AUTO_ANALYZE default true).
- `background_post_response` async extraction (postprocessing.py:428–438).

**Active by default in Repo:** Session memory, extractMemories (post-sampling hook, always fires).
**Active by default in Clonnect:** Commitment tracking, DNA auto-create, DNA auto-analyze. Memory systems OFF by default.

---

## 7. Error Recovery

**Repo (DEEP_DIVE_CONTEXT_ENGINEERING.md:164–177, 638–646, 712–741, 1070–1256):**
1. **Prompt-too-long** → context collapse drain → reactiveCompact (lines 1070–1182).
2. **Max-output-tokens** → 8K→64K escalation (lines 1195–1221) → multi-turn recovery (lines 1223–1252).
3. **Fallback model mid-stream** (lines 712–741): If streaming falls back, discard previous messages and retry.
4. **MAX_CONSECUTIVE_FAILURES=3** circuit breaker (referenced in state, line 54).

**Clonnect (DEEP_DIVE_CLONNECT_PIPELINE.md:281, 288, 350–352, 367–373):**
1. **General try/except in agent.py:367** → `error_response` (webhook.py implied, not detailed in deep dive).
2. **No mid-stream fallback;** emergency fallback only (generation.py:385–388, if `llm_result` is None).
3. **No max_output_tokens escalation.**
4. **No reactive compact.**
5. **Provider cascade:** Gemini Flash-Lite → GPT-4o-mini (generation.py:281, postprocessing line 281).

**Repo error recovery strategies:** 4 (context collapse drain, reactive compact, escalation, mid-stream fallback).
**Clonnect error recovery strategies:** 2 (general try/except, provider cascade).

---

## 8. Metadata Flow

**Repo (DEEP_DIVE_CONTEXT_ENGINEERING.md:387–419):**
- `userContext` dict → `prependUserContext()` → synthetic `<system-reminder>` user message (lines 389–400).
- `systemContext` dict → `appendSystemContext()` → appended to system prompt array (lines 405–418).
- Feature flags eliminated at build time by bun:bundle — no runtime flag checks.
- Metadata flows as function parameters (`QueryParams`, `ToolUseContext`, `ProcessUserInputContext`), not global dict.

**Repo metadata usage:** All metadata passed as params is consumed by decision logic (e.g., canUseTool, getAppState). No orphan fields documented.

**Clonnect (DEEP_DIVE_CLONNECT_PIPELINE.md:430–487):**
- `cognitive_metadata` dict with ~60 fields written across detection.py, context.py, generation.py, postprocessing.py, post_response.py.
- Fields written: 60+ (prompt_injection_attempt, intent_override, sensitive_detected, memory_chars, episodic_chars, hier_memory_*, commitments_pending, relationship_type, dna_seed_created, query_expanded, rag_routed, rag_confidence, rag_reranked, audio_enriched, length_hint_injected, question_hint_injected, relational_adapted, lead_warmth, context_skipped_*, response_strategy, preference_profile, gold_examples_injected, question_hint, prompt_truncated, max_tokens_category, length_hint, temperature_used, self_consistency_replaced, loop_detected, repetition_truncated, sentence_dedup, echo_detected, blacklist_replacement, reflexion_issues, reflexion_severity, sbs_*, ppa_*, guardrail_triggered, message_type, style_normalized, payment_link_injected, clone_score, dna_update_scheduled, nurturing_scheduled, email_captured, email_asked, etc.).
- Fields actually consumed for decisions: 6 (`question_context`, `question_confidence`, `_full_prompt`, `detected_language`, `best_of_n`, `relationship_category` per line 487).
- ~54 fields are orphans (written, never read for decisions; used only for logging/persistence per lines 484–485).
- Feature flags are env vars read at runtime (lines 397–427, no build-time elimination).

**Metadata fields written vs consumed:**
- Repo: All metadata consumed by decision logic (no orphans documented).
- Clonnect: 60+ written, 6 consumed, ~54 orphans.

---

## 9. Summary Difference Table

| Aspect | Repo | Clonnect | Potential impact |
|---|---|---|---|
| Prompt structure | System + separate user messages | Everything in single string | — |
| Injection gates | Per-turn dynamic (attachments) | Static flags + 2 adaptive gates | — |
| Static/dynamic boundary | Explicit (SYSTEM_PROMPT_DYNAMIC_BOUNDARY) | None | — |
| Post-processing | 0 steps mutate response | 11 steps mutate response | — |
| Compaction | 3 strategies | None (truncation + limited history) | — |
| Active memory (defaults) | Session memory + extractMemories | memory_engine OFF, episodic OFF, hier OFF | — |
| Error recovery | 4 strategies | try/except + provider cascade | — |
| Useful metadata | All flows to decisions | 6/60 fields consumed | — |

