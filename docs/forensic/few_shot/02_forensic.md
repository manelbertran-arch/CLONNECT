# Few-Shot Injection — Forensic line-by-line + git history

**Date:** 2026-04-23
**Modules audited:**
- `backend/services/calibration_loader.py` (699 LOC)
- `backend/core/dm/phases/context.py:1350-1380` (callsite)

## 1. Function map (`calibration_loader.py`)

| Line | Function | Purpose |
|---|---|---|
| 42 | `_load_creator_vocab` | Load `personality_docs.vocab_meta.content` (DB) for creator |
| 187 | `_load_creator_blacklist` | Extract blacklist_words from vocab_meta |
| 208 | `apply_blacklist_replacement` | Replace prohibited words in response (data-driven) |
| 282 | `_filter_blacklisted_examples` | Drop pool examples whose response contains blacklist |
| 315 | `load_calibration` | Read `calibrations/<creator>_unified.json` (or fallback `<creator>.json`), filter blacklist, cache 5 min |
| 368 | `_cosine_similarity` | Pure numpy vector math |
| 376 | `_select_examples_by_similarity` | Semantic top-k matching via stored embeddings |
| 432 | `detect_message_language` | ca/es fast-path markers + langdetect clause-level |
| 554 | `_select_stratified` | 3 intent-matched + 1-per-other-group + 2 semantic |
| 635 | `get_few_shot_section` | Public entrypoint: filter pool by lang, stratify, render block |
| 694 | `invalidate_cache` | Per-creator cache invalidation |

## 2. Callsite (`context.py:1350-1380`)

Post-sprint state:

```python
# Load few-shot examples from calibration (intent-stratified + semantic hybrid)
few_shot_section = ""
if ENABLE_FEW_SHOT and agent.calibration:      # ENABLE_FEW_SHOT = flags.few_shot
    _fs_examples_found = 0
    _fs_outcome = "empty"
    try:
        from services.calibration_loader import detect_message_language, get_few_shot_section
        detected_lang = detect_message_language(message)
        few_shot_section = get_few_shot_section(
            agent.calibration,
            max_examples=5,
            current_message=message,
            lead_language=detected_lang,
            detected_intent=intent_value,
        )
        if detected_lang:
            cognitive_metadata["detected_language"] = detected_lang
        if few_shot_section:
            _fs_examples_found = few_shot_section.count("\n- ") or 1
            _fs_outcome = "injected"
    except Exception as e:
        logger.debug(f"Few-shot loading failed: {e}")
        _fs_outcome = "error"
    emit_metric("few_shot_injection_total", creator_id=..., intent=..., outcome=_fs_outcome)
    if _fs_examples_found:
        emit_metric("few_shot_examples_count", _fs_examples_found, creator_id=...)
elif agent.calibration:
    emit_metric("few_shot_injection_total", creator_id=..., intent=..., outcome="disabled")
```

## 3. Git history summary (last 20 commits touching calibration_loader.py)

Relevant landmarks:
- `fd96f9ec feat: semantic few-shot selection (5 similar + 5 random) via embeddings` — semantic hybrid origin
- `6b369f99 feat: unify few-shot pool — 50→131 examples from calibration + gold_examples DB` — pool unification
- `151db324 fix: purge contaminated few-shot examples + universal blacklist filter` — blacklist filter
- `2266baa3 fix: PROHIBITED_CONTENT + language-filtered few-shot` — language filtering
- `5063a798 refactor: replace hardcoded ca/es language detection with universal langdetect` — de-hardcoding
- `8c53fc98 fix: detect ca-es code-switching, use full few-shot pool for mixed messages` — code-switching guard
- `afada377 feat: store vocabulary as vocab_meta in personality_docs for Railway production` — vocab moved to DB
- `d100c1ea feat: intent-stratified few-shot selection (universal)` — stratified selection

Trend: every historical change moved the system **away** from hardcoding and **towards** data-derived universal behaviour. Current state is the result of multiple de-hardcoding refactors.

## 4. Tests that already cover the module

- `backend/tests/test_calibration_loader.py` (pre-existing) — `get_few_shot_section` basic formatting, empty calibration, no examples branches.
- `backend/tests/test_sprint_top6_forensic_ligero.py` (new) — flag gate + metric emission.

## 5. Observations

- The selection pipeline is end-to-end data-derived per creator (calibration JSON + vocab_meta blacklist from DB).
- Zero Iris defaults, Stefano defaults, or any creator-baked literals in code.
- Three hardcoded literals remain and are flagged in `03_bugs.md` — all low severity.

## 6. Dependencies

Reads:
- `calibrations/<creator>_unified.json` (disk)
- `personality_docs` table (via `_load_creator_vocab`, `_load_creator_blacklist`)

Writes: none (read-only module).

Side effects: `_cache` dict TTL=300s.

Downstream consumers: `context.py:1350` is the ONLY hot-path consumer of `get_few_shot_section`. One test-path consumer in `mega_test_auto.py`.
