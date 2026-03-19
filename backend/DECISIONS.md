# DECISIONS.md — Clonnect Backend

Architecture and implementation decisions, in reverse chronological order.

---

## 2026-03-19 — Enforced methodology hooks (advisory → blocking gates)

**Problem:** CLAUDE.md rules are advisory — workers can skip the planner, code reviewer, DECISIONS.md, and smoke tests without consequence. Hooks make them enforced gates.

**3 new hooks added to `.claude/settings.json`:**

1. **Stop (agent):** Spawns a subagent that checks git diff for .py changes. If found, verifies DECISIONS.md was updated, smoke tests were run, and code review was done. Blocks Claude from finishing if any are missing. Only fires when `.py` files were actually modified.

2. **PreToolUse (command) — `pre-commit-decisions.sh`:** Intercepts `git commit`/`git push`. If `.py` files are staged but DECISIONS.md is not, blocks with `permissionDecision: deny`. Uses same `hookSpecificOutput` pattern as existing `pre-commit-syntax.sh`.

3. **Stop (command) — `stop-smoke-tests.sh`:** When Claude finishes and `.py` files have uncommitted changes, auto-runs `python3 tests/smoke_test_endpoints.py`. Blocks with `{"decision": "block"}` if tests fail. Checks `stop_hook_active` to prevent infinite loops.

**Blast radius:** Config-only change. No .py files modified. Existing hooks preserved (methodology-reminder, session-start-baseline, superpowers, pre-commit-syntax, post-deploy-health).

---

## 2026-03-19 — DB fallback: status filter excluded all messages (NULL status)

**Bug:** `get_history_from_db` queried `Message.status.in_(("sent", "edited"))` but messages in DB have `status=None` (NULL). Zero messages were returned, fallback silently did nothing.

**Fix:** Changed filter to `Message.status != "discarded"` — excludes only rejected copilot suggestions; allows NULL and all real message statuses.

**Verified:** `/dm/follower/iris_bertran/wa_120363386411664374` returns 38 messages all with `status=None`.

---

## 2026-03-19 — DB fallback for conversation history (zero-history bug)

**Bug:** The DM agent generates copilot suggestions with ZERO conversation history. The agent reads from JSON files at `data/followers/{creator_slug}/{follower_id}.json` via `MemoryStore.get_or_create()`. These files don't exist on Railway for any WA lead or Iris IG leads. Result: `follower.last_messages = []` → `history = []` → LLM prompt has no `=== HISTORIAL DE CONVERSACION ===` section. Every response is generated as if it's the first message ever.

**Impact:** All copilot suggestions and auto-replies for all WhatsApp leads (both creators) and all Instagram leads (Iris). The DB has 61K+ messages but the agent never reads them.

**Root cause:** `MemoryStore` is JSON-file-backed. Files only exist for:
- `data/followers/{creator_uuid}/` — 910 files for Stefano (old IG code path, UUID-based)
- `data/followers/stefano_bonanno/` — 84 files (current slug-based path)
- `data/followers/iris_bertran/` — DOES NOT EXIST

The DM agent passes `creator_id=slug` + `follower_id=wa_XXXXX`, so the UUID-based files are never found.

**Fix (Option A — surgical DB fallback):**
- In `core/dm/helpers.py`: add `get_history_from_db(creator_id, follower_id, limit=20)` that queries the `messages` table via `Lead.platform_user_id` join.
- In `core/dm/phases/context.py` line 399: after `history = agent._get_history_from_follower(follower)`, if `not history`, call the DB fallback.
- Also backfill `metadata["history"]` so earlier code (question context, relationship detection, DNA seed) benefits.

**Why Option A over full migration:**
- Lowest risk: only adds a fallback path, never changes existing behavior when JSON files exist
- Zero schema changes, zero new dependencies
- The 84 Stefano slug-based files continue working as before
- Can migrate fully to DB later; this unblocks quality immediately

**Blast radius:** `context.py` (one new call site), `helpers.py` (one new function). No changes to MemoryStore, prompt_service, or any other module.

---

## 2026-03-19 — Audio intelligence: summaries must respect source language

**Bug:** Audio summary generated in Spanish even when audio was in Catalan.

**Root causes (3):**
1. `CLEAN_PROMPT`: no language instruction → LLM could translate Catalan to Spanish while "cleaning"
2. `EXTRACT_PROMPT`: prompt in Spanish, no language instruction → `intent`, `emotional_tone`, `topics` returned in Spanish
3. `SUMMARY_PROMPT`: rule 4 said "mismo idioma" but it was rule 4 of 7, surrounded by Spanish extracted fields; LLM defaulted to Spanish

**Fix** (`services/audio_intelligence.py`):
- Added `_LANGUAGE_NAMES` dict and `_language_name(code)` helper
- All three prompts now start with `"IDIOMA OBLIGATORIO: ... en {lang_name}"` as first line
- System prompts for each layer also include language instruction
- `language` parameter propagated to `_clean()` and `_extract()`
- Fallback values changed from Spanish words ("ninguna", "neutro") to "-" (language-neutral)

**Smoke tests:** 7/7 pass before and after.

---

## 2026-03-19 — Copilot: stop skipping audio messages

**Context:**
Audio messages from Evolution webhook arrive in two forms:
- With transcription: `"[🎤 Audio]: <transcribed text>"` — always passed through copilot (was never in skip list)
- Without transcription: `"[🎤 Audio message]"` — was in `_EMOJI_MEDIA_PREFIXES` skip list → copilot silently skipped it

**Decision:**
Remove `"[🎤 Audio message]"` from `_EMOJI_MEDIA_PREFIXES`. Copilot should generate a suggestion for audio messages even without transcription, instructing the LLM to ask the lead to re-send as text.

**Changes:**
- `core/copilot/models.py`: Removed `"[🎤 Audio message]"` from skip list. Moved `_EMOJI_MEDIA_PREFIXES` to module level (was re-allocated on every call).
- `services/prompt_service.py`: Added explicit REGLAS CRÍTICAS rule: if message is `[🎤 Audio message]`, ask lead to re-send as text.

**Blast radius:** Confined to `create_pending_response_impl` in `core/copilot/lifecycle.py`. `autolearning_analyzer.py` and `preference_pairs_service.py` have separate audio guards for outgoing creator responses — unaffected.

**Smoke tests:** 7/7 pass before and after.
