# DECISIONS.md — Clonnect Backend

Architecture and implementation decisions, in reverse chronological order.

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
