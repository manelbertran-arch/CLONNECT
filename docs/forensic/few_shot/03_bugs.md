# Few-Shot Injection — Bug Catalog

**Date:** 2026-04-23
**Scope:** findings identified during sprint forensic. No CRITICAL bugs blocking activation.

| ID | Severity | Description | Reproduction | Status |
|---|---|---|---|---|
| FS-01 | **LOW** | `get_few_shot_section` uses two Spanish hardcoded strings in the output template: the opening frame `=== EJEMPLOS REALES DE COMO RESPONDES ===` (L681) and the closing directive `"Responde de forma breve y natural, como en los ejemplos."` (L689). For non-ES creators the frame and directive remain in Spanish. | `get_few_shot_section({"few_shot_examples": [...]}, max_examples=1, lead_language="en")` — header is still Spanish. | **DEFER-Q2** — parametrise via vocab_meta `few_shot_frame_texts` per creator. Not blocking activation for current hispanohablante creators (Iris, Stefano). |
| FS-02 | **LOW** | `detect_message_language` hardcodes ca/es keyword markers in `_CA_RE` / `_ES_RE` (L456-467). This is a technical workaround because `langdetect` cannot distinguish Catalan from Spanish on short strings. Other language pairs use universal `langdetect`. | Any short message in Catalan + Spanish mix triggers the hardcoded regex. | **KEEP-AS-IS** — documented justification in the docstring; replacing with a learned classifier is out of sprint scope. Revisit post-FT with a distilled lang-detector. |
| FS-03 | **LOW** | `_select_stratified` selects 3 intent-matched + 1 per other group + 2 semantic → can exceed `max_examples` when many intents are present. The cap is soft (by truncation after). | `_select_stratified(pool_with_10_intents, intent="VENTA", msg="hola", max_examples=5)` — may return more than 5 before truncation. | **KEEP-AS-IS** — truncation at render time caps the final count. Verified by new test `test_few_shot_k_equals_5_cap`. No correctness impact. |
| FS-04 | **INFO** | `load_calibration` uses `time.time()` for cache TTL; process restarts flush the cache. No hot-reload mechanism when calibration JSON changes on disk. | Edit `calibrations/iris_bertran_unified.json` mid-flight → change is not visible until next process start or manual `invalidate_cache`. | **KEEP-AS-IS** — calibration packs are rebuilt offline and deployed. No runtime mutation expected. |
| FS-05 | **INFO** | `cognitive_metadata["detected_language"]` is set only when `detect_message_language` returns non-None. For short strings (<10 chars), it is `None` and the key is absent. Downstream logs may miss language attribution for short turns. | `is_short_affirmation("sí")` path → no language in metadata. | **KEEP-AS-IS** — consistent with the "short strings are language-agnostic" design. |

## Summary by severity

| Severity | Count | Blocker for activation? |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 0 | — |
| MEDIUM | 0 | — |
| LOW | 3 | No |
| INFO | 2 | No |

## Creator-specific hardcoding audit (user-requested deep dive)

Explicit search for Iris/Stefano/creator-specific literals:

| Pattern searched | Found? | Location | Verdict |
|---|---|---|---|
| `iris` (case-insensitive) in code strings | No | — | Clean |
| `stefan` in code strings | No | — | Clean |
| Hardcoded apelativos (`nena`, `tia`, `cuca`, `flor`, `reina`) | Only in docstring comment (L48) | `calibration_loader.py:48` "'SÍ usa: nena, tia, cuca...'" | Documentation only; not executed code |
| Hardcoded few-shot example content | No | — | Clean — examples come from JSON per creator |
| Default fallback responses | No | — | Clean — empty string is the fallback |

**Verdict:** No creator-specific hardcoding. The module is universal per-creator.

## Activation blocker decision

**NONE.** All LOW/INFO findings are either deferred to Q2 with rationale or kept-as-is with justification. Flag can flip safely post-CCEE gate.
