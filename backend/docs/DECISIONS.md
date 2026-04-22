# Architectural Decisions Log

This file logs non-trivial architectural decisions made during development. Each entry: date, context, decision, rationale, alternatives considered, blast radius.

---

## 2026-04-07 — Model Hyperparameter Adapter Unification (Option A)

**Context:** Migration from Qwen3-14B (DeepInfra) to Gemma4-26B (Google AI Studio) is blocked because model hyperparameters (`temperature`, `top_p`, `max_tokens`, chat-template tokens, safety, etc.) are scattered across:
- Function arg defaults in 5 of 6 provider files
- Per-provider Railway env vars (`DEEPINFRA_MODEL`, `GEMINI_MODEL`, `GEMINI_PRESENCE_PENALTY`, …)
- Per-creator calibration JSON overrides
- Hardcoded literals in call sites (SBS retry @ temp=0.5, dm_agent_v2 max_tokens=150, etc.)

Only `core/providers/google_provider.py` already loads from `config/models/{model_id}.json` via `_load_model_config()`. The other 5 providers (gemini, deepinfra, together, fireworks, openrouter) are config-blind.

**Decision:** Extend the existing `google_provider` config-driven pattern to ALL providers via a new shared loader module, with one new env var (`LLM_MODEL_NAME`) selecting the active model config file. Schema is the existing nested schema (`provider.*`, `sampling.*`, `chat_template.*`, `thinking.*`, `system_prompt.*`) plus minimal additive extensions (`runtime.*`, `safety.*`, `sampling.frequency_penalty`/`presence_penalty`/`seed`, `thinking.no_think_suffix`).

**Confirmed Railway production state (2026-04-07):**
- `LLM_PRIMARY_PROVIDER=deepinfra`
- `DEEPINFRA_MODEL=Qwen/Qwen3-14B`  ← prod model is **14B**, code default `Qwen/Qwen3-32B` is misleading
- `DEEPINFRA_TIMEOUT=30`
- `DEEPINFRA_INCLUDE_REASONING=false`
- `DEEPINFRA_NO_FALLBACK=false`
- `GEMINI_MODEL=gemini-2.5-flash-lite`
- `GEMINI_PRESENCE_PENALTY=0.0`
- `GEMINI_FREQUENCY_PENALTY=0.0`
- `LLM_MODEL=gpt-4o-mini`, `LLM_PROVIDER=openai` (legacy fallback path)

**Resolved questions (decisions made before implementation):**

| # | Question | Decision | Rationale |
|---|---|---|---|
| 1 | Production model: 14B vs 32B | **Qwen3-14B** (Railway truth) | Code default `Qwen3-32B` is wrong; will be deleted in cleanup PR |
| 2 | Config dir: `config/models/` vs `config/model_configs/` | **`config/models/`** wins; delete `config/model_configs/` entirely | `config/models/` is what `google_provider._load_model_config` reads today; `config/model_configs/` contains 2 stale flat-schema dead files that nothing reads |
| 3 | Active-model env var name | **`LLM_MODEL_NAME`** | Planner default, no bikeshed |
| 4 | Deprecation timeline for `LLM_PRIMARY_PROVIDER` + per-provider env vars | **One release cycle** — keep as fallback, remove in separate cleanup PR after Gemma4 cutover proven | Avoid one-shot deploy risk |
| 5 | Safety settings location | **Per-model `safety.*` config** with `BLOCK_ONLY_HIGH` default when absent | Future-proof: a model that needs different safety doesn't require a code change |
| 6 | Circuit-breaker scope | **Per-provider** (env vars, NOT per-model config) | CB protects against provider outages, not model issues; if DeepInfra is down it doesn't matter which model you call |
| 7 | Delete `config/model_configs/gemma4_31b.json` | **YES** — entire directory gets removed | Stale flat-schema duplicate |

**Schema (final, minimal-additive):**

```jsonc
{
  "model_id": "string  // REQUIRED, must match filename",
  "model_name": "string",
  "architecture": "dense | moe",

  "provider": {
    "name": "google_ai_studio | gemini | deepinfra | together | fireworks | openrouter | openai",  // REQUIRED
    "api_key_env": "string  // REQUIRED",
    "model_string": "string  // REQUIRED",
    "base_url": "string  // optional, OpenAI-compat providers"
  },

  "sampling": {
    "temperature": "float  // REQUIRED",
    "top_p": "float  // default 1.0",
    "top_k": "int  // google only",
    "max_tokens": "int  // REQUIRED",
    "stop_sequences": "list[string]",
    "frequency_penalty": "float  // NEW; default 0.0",
    "presence_penalty": "float  // NEW; default 0.0",
    "seed": "int | null  // NEW"
  },

  "thinking": {
    "enabled": "bool",
    "token": "string",
    "filter_from_history": "bool",
    "no_think_suffix": "string  // NEW; e.g. /no_think for Qwen3"
  },

  "chat_template": {
    "filter_thought_blocks": "bool",
    "strip_thinking_artifacts": "bool  // NEW"
  },

  "system_prompt": {
    "system_prompt_mode": "system_instruction | user_message",
    "max_length_chars": "int"
  },

  "runtime": {
    "timeout_seconds": "int  // NEW; default 15",
    "max_retries": "int  // NEW; default 2"
  },

  "safety": {  // NEW; Gemini only; default BLOCK_ONLY_HIGH when absent
    "harassment": "BLOCK_NONE | BLOCK_ONLY_HIGH | BLOCK_MEDIUM_AND_ABOVE | BLOCK_LOW_AND_ABOVE",
    "hate_speech": "...",
    "sexually_explicit": "...",
    "dangerous_content": "..."
  }
}
```

**Fields explicitly NOT added (YAGNI):** `repetition_penalty`, `n`, `logprobs`, `stream`, Together `safety_model`, Fireworks LoRA selector (handled via `model_string`), per-model CB threshold/cooldown (stays per-provider env var per decision #6).

**Override semantics preserved:** Every provider keeps `temperature: Optional[float] = None` and `max_tokens: Optional[int] = None`. Caller wins when set; otherwise read from active config. SBS retry @ temp=0.5, PPA refinement, calibration-derived per-creator max_tokens — all unchanged.

**Order of operations (11 steps, smoke gate after each):**

1. **Pure extraction** — `core/providers/model_config.py` (loader copied from `google_provider.py`, zero behavior change)
2. **Schema additions** — additive optional fields on existing JSONs + `config/models/default_config.json`
3. **Legacy snapshots** — `qwen3_14b.json` (PROD), `gemini_flash_lite.json` (Gemini default)
4. **Delete stale dir** — `config/model_configs/` entirely
5. **Refactor OpenRouter** (lowest blast radius — untracked file)
6. **Refactor Fireworks + Together**
7. **Refactor DeepInfra** ⚠️ point of no return for prod-on-Qwen3-14B
8. **Refactor Gemini** ⚠️ point of no return for prod-on-default
9. **Staging activation test**: `LLM_MODEL_NAME=qwen3_14b` should be byte-identical to current prod
10. **Flip primary**: `LLM_MODEL_NAME=gemma4_26b_a4b` (true cutover, separate deploy)
11. **Docs + `.env.example`**

**Diff size estimate:** ~1,380 lines added / ~295 modified / ~35 deleted across 22 files. NOT a megacommit — one commit per step minimum, smoke test between each.

**Files NOT changing** (verified by planner): `core/dm_agent_v2.py`, `core/dm/phases/generation.py`, `core/reasoning/ppa.py`, `services/memory_engine.py`, `core/best_of_n.py`, all CCEE scripts, all `tests/cpe_*.py`. They pass explicit overrides which still work.

**Rollback plan:**
- Steps 1–6: trivial revert (no prod path touched)
- Step 7 (DeepInfra): revert single commit; with `LLM_MODEL_NAME` unset, behavior is byte-identical to today
- Step 8 (Gemini): same — `LLM_MODEL_NAME` unset = current behavior
- Step 10 (Gemma4 cutover): `railway variables unset LLM_MODEL_NAME` → instant rollback to Gemini default, no redeploy needed

**Phase 4 evidence:**
- Smoke test BEFORE refactor (2026-04-07 11:21): **7/7 PASS** (3 skipped — no DATABASE_URL locally)
- Each step gates on `python3 tests/smoke_test_endpoints.py` PASS before proceeding

---

## 2026-04-07 — Step 5: OpenRouter provider config-driven refactor

**Context:** Batch 2 of the model-config refactor begins with OpenRouter — lowest blast radius (file was untracked, not on prod path) so it's the safe place to establish the per-provider refactor pattern that DeepInfra and Gemini will copy in Steps 7–8.

**Decision:** Refactor `call_openrouter()` to accept an optional `model_id: Optional[str] = None` kwarg. When set, sampling/runtime/provider info are loaded from `config/models/{model_id}.json` via the shared `core.providers.model_config` accessor helpers. When unset, behavior is byte-identical to today (env var + arg defaults). Caller-supplied `temperature` / `max_tokens` always win over config values. Circuit breaker stays per-provider env-var per DECISIONS.md #6 (not in config).

**Schema additions actually consumed by this provider:**
- `provider.api_key_env`, `provider.model_string`, `provider.base_url`
- `sampling.temperature`, `sampling.max_tokens`, `sampling.frequency_penalty`, `sampling.presence_penalty` (penalties only included in payload when > 0)
- `runtime.timeout_seconds`

**Files added/modified:**
- `core/providers/openrouter_provider.py` — refactored (was untracked, pre-existing WIP)
- `config/models/openrouter_default.json` — placeholder snapshot capturing today's arg defaults (max_tokens=78, temp=0.7, timeout=120s, model_string=google/gemma-4-31b-it)
- `tests/unit/test_openrouter_provider.py` — new file, 13 tests covering legacy path, config-driven path, caller-override semantics, fallback to default_config.json, missing API key, circuit breaker

**Rationale for `max_tokens`/`temperature` default change to `Optional[int]`/`Optional[float]`:** the old hardcoded defaults (78/0.7) move into the legacy fallback branch (`cfg_sampling.get(..., 78)` etc.), so legacy callers passing positional values are unaffected and callers passing nothing now get config values when `model_id` is set. `_try_openrouter()` in `gemini_provider.py` always passes positional `max_tokens, temperature` from its caller, so no breakage.

**Verification:**
- Smoke test 7/7 PASS after refactor
- Unit tests: 13/13 new + 12/12 existing model_config = 25/25 PASS
- Public signature: only additive (`model_id` kwarg added, `max_tokens`/`temperature` types widened to Optional with same legacy default behavior)

**Blast radius:** Zero. File was untracked WIP, not imported on prod path. `_try_openrouter()` in gemini_provider.py still works because it passes positional args.

---

## 2026-04-07 — Step 6: Fireworks + Together provider config-driven refactor

**Context:** Step 6 applies the OpenRouter pattern (Step 5) to the next two providers in the cascade. Neither is on the Railway prod path (`LLM_PRIMARY_PROVIDER=deepinfra`), so blast radius remains low.

**Decision:** Add `model_id: Optional[str] = None` kwarg to both `call_fireworks()` and `call_together()`. When set, sampling/runtime/provider info loads from `config/models/{model_id}.json` via the shared accessor helpers. Caller-supplied `temperature`/`max_tokens` always win. Circuit breaker stays per-provider env vars.

**Files added/modified:**
- `core/providers/fireworks_provider.py` — refactored
- `core/providers/together_provider.py` — refactored
- `config/models/fireworks_default.json` — placeholder snapshot (max_tokens=60, temp=0.7, timeout=15s, model_string=accounts/fireworks/models/qwen3-8b)
- `config/models/together_default.json` — placeholder snapshot (max_tokens=60, temp=0.7, timeout=15s, model_string=Qwen/Qwen3-32B)
- `tests/unit/test_fireworks_provider.py` — extended with 5 config-driven tests
- `tests/unit/test_together_provider.py` — extended with 5 config-driven tests

**Public signature change:** `max_tokens: int = 60` → `max_tokens: Optional[int] = None` and `temperature: float = 0.7` → `temperature: Optional[float] = None`. Legacy callers passing positional ints/floats are unaffected; passing nothing now uses the same 60/0.7 values via the legacy fallback branch (`cfg_sampling.get(..., 60)` etc.). `_try_fireworks` and `_try_together` in `gemini_provider.py` always pass positional values.

**Verification:**
- Smoke test 7/7 PASS
- Unit tests: 55/55 PASS (2 live-API skipped) across model_config + openrouter + fireworks + together

**Blast radius:** Zero on prod path. Both providers are non-primary in Railway today.

---

## 2026-04-07 — Step 7: DeepInfra provider config-driven refactor (PROD path)

**Context:** Step 7 is the point of no return for production-on-Qwen3-14B. DeepInfra is the current primary provider in Railway (`LLM_PRIMARY_PROVIDER=deepinfra`, `DEEPINFRA_MODEL=Qwen/Qwen3-14B`). Behavior must remain byte-identical when `LLM_MODEL_NAME` is unset.

**Decision:** Add `model_id: Optional[str] = None` kwarg to `call_deepinfra()`. The refactor preserves three subtle behaviors:

1. **`/no_think` suffix injection** — moved under config control via `thinking.no_think_suffix`. When `model_id` provided AND suffix non-empty → inject. When `model_id` provided with empty suffix → no injection. When `model_id` is None (legacy) → keep the existing hardcoded `"Qwen3" in model` substring detection.
2. **`strip_thinking_artifacts` post-processing** — moved under config control via `chat_template.strip_thinking_artifacts`. Legacy path (model_id=None) always strips (preserves prod behavior). Config path follows the config flag (default true via `qwen3_14b.json`).
3. **`frequency_penalty`** — caller arg > config > env var (`DEEPINFRA_FREQUENCY_PENALTY`) > 0.0. Config path uses `cfg.sampling.frequency_penalty`.

**Caller-override semantics preserved:** explicit `temperature=0.5` (SBS retry), `max_tokens=150` (calibration-derived), `frequency_penalty=...` all win over config when not None.

**Public signature change:** `max_tokens: int = 400` → `Optional[int] = None`, `temperature: float = 0.7` → `Optional[float] = None`. Legacy callers passing positional ints/floats are unaffected. The single internal caller (`_try_deepinfra` in `gemini_provider.py`) passes positional values.

**Files added/modified:**
- `core/providers/deepinfra_provider.py` — refactored
- `tests/unit/test_deepinfra_provider.py` — new file, 10 tests covering legacy path, config-driven path, /no_think behavior (both legacy substring + config-driven via no_think_suffix + empty suffix skipping injection), caller override, model_string from config overriding env var, missing API key

**Verification:**
- Smoke test 7/7 PASS
- Unit tests: 96/98 PASS (2 pre-existing failures in `tests/test_score_before_speak.py::test_bad_response_triggers_refinement` and `::test_failed_refinement_triggers_retry`. Both were verified failing at HEAD before this commit via `git stash`. Not introduced by Step 7.)
- New deepinfra tests: 10/10 PASS

**Pre-existing failures noted:** `tests/test_score_before_speak.py` has 2 failing tests at HEAD (`assert 1 >= 2` on `total_llm_calls`). Verified pre-existing via `git stash` round-trip on the working tree minus Step 7. Not blocking Step 7 commit; will report under OPEN ISSUES.

**Blast radius:** Affects current PROD path. With `LLM_MODEL_NAME` unset, every code path through `call_deepinfra()` flows through the legacy branch which is functionally identical to pre-refactor (same /no_think substring detection, same `strip_thinking_artifacts` always-on, same env-var-driven freq_pen and timeout). The only difference is the function default values for `max_tokens`/`temperature` are now `None` and resolved to `400`/`0.7` in the legacy branch — equal to the prior literal defaults.

---

## 2026-04-07 — Step 8: Gemini provider config-driven + LLM_MODEL_NAME routing

**Context:** Final batch-2 step. Activates `LLM_MODEL_NAME` as the unified active-model selector, with `generate_dm_response()` dispatching based on the active config's `provider.name`.

**Decision:**

1. **`core/config/llm_models.py`** — added `LLM_MODEL_NAME: Optional[str] = os.getenv("LLM_MODEL_NAME")` and `get_active_model_config()` helper that loads `config/models/{LLM_MODEL_NAME}.json` via the shared loader (returns None if env var unset). `log_model_config()` now logs the active model when set. The helper re-reads `os.environ["LLM_MODEL_NAME"]` on each call so tests can monkeypatch without re-import.

2. **`core/providers/gemini_provider.py::_call_gemini`** — added `model_id: Optional[str] = None`. When set, `frequency_penalty`/`presence_penalty` come from `cfg.sampling.*` and safety thresholds come from `cfg.safety.*`. Legacy path (model_id=None) preserves the existing `GEMINI_*_PENALTY` env-var reads and the `BLOCK_ONLY_HIGH` defaults.

3. **`generate_response_gemini`** — added `model_id` kwarg. When set, reads `provider.api_key_env` and `provider.model_string` from config. Forwards `model_id` to `_call_gemini`.

4. **`generate_dm_response`** — added a "step 0" dispatch at the top: if `get_active_model_config()` returns a config, route based on `cfg.provider.name` to the matching `_try_*` (deepinfra/together/openrouter/gemini/google_ai_studio) passing `model_id`. On failure of the active provider, falls through to the GPT-4o-mini fallback (NOT through the legacy LLM_PRIMARY_PROVIDER cascade). When `LLM_MODEL_NAME` is unset, the legacy cascade runs unchanged. The public signature of `generate_dm_response` is unchanged — only optional internal kwargs were added to the underlying `_try_*` helpers.

5. **`_try_deepinfra` / `_try_together` / `_try_openrouter`** — added optional `model_id` kwarg, forwarded to the respective `call_*` function.

6. **`.env.example`** — added a documented `LLM_MODEL_NAME` section explaining the available config names.

**Public signature guarantee:** `generate_dm_response(messages, max_tokens=60, temperature=0.7)` — unchanged. The patch targets in `tests/test_score_before_speak.py`, `tests/unit/test_ppa.py`, `tests/test_battery_realista.py`, `tests/test_e2e_pipeline.py` continue to mock the function as a whole and remain compatible.

**Files added/modified:**
- `core/config/llm_models.py` — added `LLM_MODEL_NAME`, `get_active_model_config()`, updated `log_model_config()` (incorporates pre-existing google_ai_studio additions in working tree)
- `core/providers/gemini_provider.py` — `_call_gemini` config-driven, `generate_response_gemini` config-driven, `generate_dm_response` LLM_MODEL_NAME dispatch, `_try_*` helpers accept `model_id` (incorporates pre-existing google_ai_studio + openrouter routing additions in working tree)
- `.env.example` — added LLM_MODEL_NAME section (incorporates pre-existing edits in working tree)
- `tests/unit/test_gemini_provider.py` — new file, 5 tests covering: legacy unset cascade, qwen3_14b → deepinfra dispatch, gemini_flash_lite → gemini dispatch, _call_gemini env-var penalties (legacy), _call_gemini config penalties + safety overrides

**Verification:**
- Smoke test 7/7 PASS
- Unit tests: 101/103 PASS across model_config + 4 refactored providers + new gemini tests + ppa
- Pre-existing failures (2 in test_score_before_speak) UNCHANGED — verified at HEAD before Step 7 commit
- Public `generate_dm_response` signature unchanged — `tests/unit/test_ppa.py` (which patches it) passes

**Pre-existing modifications in working tree:** The `gemini_provider.py`, `llm_models.py`, and `.env.example` files were already modified in the working tree from earlier google_ai_studio + openrouter routing work (not yet committed). Step 8 changes layer ON TOP of those pre-existing edits in a single commit, since both sets of changes converge on the same code paths and are functionally complementary.

**Blast radius:** With `LLM_MODEL_NAME` unset (current Railway state), behavior is byte-identical to today: `_call_gemini` reads `GEMINI_PRESENCE_PENALTY`/`GEMINI_FREQUENCY_PENALTY` env vars (both 0.0 in prod), uses BLOCK_ONLY_HIGH safety, and `generate_dm_response` runs the existing `LLM_PRIMARY_PROVIDER` cascade (deepinfra → gemini → openai-fallback). Activation of `LLM_MODEL_NAME=qwen3_14b` in staging is the next gate (Step 9).

---

---
DATE: 2026-04-19
ARC: ARC4
DECISION: ARC4 Phase 3-5 APLAZADA a post-fine-tuning
CONTEXT: Worker B completó 8 mediciones shadow (baseline + 7 mutations). 6/7 mutations son PROTECTIVE (Δ composite -2.2 a -4.7, ΔK1 -16 a -43). Solo M10 strip_question es NEUTRAL (+0.3 composite).
RATIONALE: Plan original (eliminar 9-11 mutations para +3/+6 composite) INCORRECTO con Gemma-4-31B base. Las mutations NO son band-aids — son red de seguridad necesaria. K1 (memory continuity) colapsa -30/-40 puntos al eliminar M3/M7/M8 aunque composite solo baja -3. Eliminar M10 ganaría +0.3 (despreciable vs coste de iteración).
NEXT: Re-medir las 7 mutations con modelo FINE-TUNED cuando FT esté listo (Sprint 6-7). Modelo FT probablemente no genere "jajajaja" ni echo espontáneo → mutations podrían eliminarse en bloque. Decisión más eficiente 1 vez con todas que 7 veces con el modelo base.
STATUS: DEFERRED TO POST-FINE-TUNING
---

---
DATE: 2026-04-20
ARC: MEDICIÓN / VARIANCE
DECISION: Variance OpenRouter confirmada: ±3-4 puntos en composite, ±20-23 en dimensiones específicas
CONTEXT: Triangulación de mediciones mismo código (commit 885fe454):
- A2.5 POST (19-abr mediodía): S2=70.0, composite=72.6
- AA repro (20-abr mañana): S2=46.4, composite=68.9
- Diferencia: -23.6 S2 y -3.7 composite con CÓDIGO IDÉNTICO
RATIONALE: La varianza OpenRouter es MUY grande en dimensiones específicas (S2, K). Worker R investigó si sentence_transformers missing era causa del drop S2 -23, pero está ausente en las 3 mediciones → no puede explicar diferencia. Conclusión: es ruido del provider, no regresión de código.
NEXT: Para decisiones A/B fiables requiere delta ≥ 4 en composite. Considerar migrar a DeepInfra directo para mediciones futuras (provider menos variable).
STATUS: LESSON LEARNED - mediciones futuras calibradas por variance conocida
---

---
DATE: 2026-04-20
ARC: ARC3 Phase 1
DECISION: Distill Doc D NO activado en producción (aplazado post-fine-tuning)
CONTEXT: Worker I (20×1 cases, 19-abr noche) dio veredicto APPROVE con delta composite -0.9 y K +12.3. Worker P2 con protocolo estándar 50×3+MT (20-abr mediodía) dio resultado distinto: composite -0.7, H -10, S4 -6.8, K -1.0.
RATIONALE: Con protocolo estadísticamente serio distill NO aporta mejora. H Turing -10 y S4 Adaptation -6.8 son regresiones reales fuera del ruido. El APPROVE inicial de Worker I resultó ser artefacto del sample pequeño (20×1). El prompt distill v1 pierde señal crítica del Doc D para tareas Turing-like.
NEXT: Aplazar distill a post-fine-tuning. Cuando modelo FT esté listo (Sprint 6+): (a) re-medir prompt v1 con modelo FT, (b) si sigue no aportando, considerar prompt v2 como contexto adicional (no reemplazo del Doc D), como propuso Worker P2.
STATUS: DEFERRED TO POST-FINE-TUNING
---

---
DATE: 2026-04-20
ARC: Sprint 5 cierre
DECISION: Sprint 5 validado agregadamente con evidencia medible — cerrado 100%
CONTEXT: Worker S5-AB ejecutó A/B pre-Sprint 5 (commit fb2b1195, 9-abr) vs post-Sprint 5 (commit e62aaad4, 20-abr) con protocolo estándar 50×3+MT. Audit scorers confirmó CCEE v4 es instrumento válido para comparaciones arquitectónicas (cero dimensiones metadata-based → composite naive = composite fair).
RATIONALE:
- v5 pre = 62.1 (σ=2.73)
- v5 post = 66.4 (σ=0.88)
- Δv5 = +4.3 (supera umbral variance ±4)
- Δ dimensiones S1-S4 agregado = +5.4 (fidelidad estilística, foco diseño del sprint)
- σ reducción 3× (2.73→0.88) = beneficio colateral (output más predecible, menos outliers)
- Primer run v1 crasheó por adversarial_prompts.json ausente en worktree fb2b1195; fix: copiado desde main (recurso instrumento CCEE, no sujeto); re-run v2 limpio
CAVEATS: A/B mide impacto AGREGADO. NO mide contribución individual de cada ARC (requeriría 5 A/Bs separados, bloqueado por variance OpenRouter).
NEXT: Sprint 5 cerrado. Próximo foco: fine-tuning (Sprint 6). A2.6 legacy removal sigue pendiente gate 26-abr. Sesiones 2-3 DeepInfra variance pendientes 21-22 abril.
STATUS: CLOSED — Sprint 5 generó valor composite medible Y pagó tech debt simultáneamente
---

---
DATE: 2026-04-20
ARC: MEDICIÓN / PROTOCOLO
DECISION: DeepInfra intra-sesión confirmado 2× más estable que OpenRouter — gate PASS sesiones 2-3
CONTEXT: Worker DI-VAR ejecutó sesión 1/3 con DeepInfra directo (google/gemma-4-31b-it). σ_intra=0.419 vs OpenRouter σ_intra≈0.88.
RATIONALE: v5 DeepInfra = 65.7 vs v5 OpenRouter = 66.4 (delta -0.7 indistinguible → providers producen bots equivalentes, solo varían en ruido). 0 errores 50 casos. Latencia ~4s/call comparable. σ < 1.0 gate PASS.
NEXT: Sesiones 2 (21-abr) y 3 (22-abr) DeepInfra mismo SHA + comando. Tras 3 sesiones: calcular σ_inter-sesión DeepInfra vs OpenRouter ±3-4 conocido. Si DeepInfra inter-sesión también estable → migrar protocolo A/B oficial a DeepInfra. Si similar a OpenRouter → varianza es del modelo Gemma mismo, considerar otras estrategias.
STATUS: SESSION 1/3 COMPLETED — pendiente sesiones 2-3 Manel
---

---
DATE: 2026-04-21
ARC: MEDICIÓN / VARIANCE
DECISION: DeepInfra variance sesión 2/3 completada — σ_inter-sesión significativo (+3.0 puntos vs 1/3)
CONTEXT: Sesión 2/3 ejecutada con mismo protocolo que 1/3 (DeepInfra Gemma4-31B, Qwen3 judge, 3 runs × 50 cases + MT). Pipeline idéntico (solo docs mergeados entre sesiones).
RATIONALE:
- v5 sesión 2/3 = 68.7 ± 0.94 (runs: 68.50, 70.69, 68.98)
- v5 sesión 1/3 = 65.7 ± 0.42
- Delta inter-sesión: +3.0 puntos
- Gate intra-sesión PASS (σ<1 en ambas)
- Incidentes: 1 DeepInfra timeout Run 2 recuperado, 1 case skipped Run 3
- Warning: style context budget 43-45% (umbral 40%)
CAVEATS: Con 2 sesiones NO se puede calcular σ_inter fiable. Hypothesis en pendiente hasta sesión 3/3.
NEXT: Sesión 3/3 mañana 22-abr. Si converge a ~68 → nuevo baseline DeepInfra. Si vuelve a ~65 → σ_inter alto, sesión 2/3 outlier.
STATUS: SESSION 2/3 COMPLETED — pendiente sesión 3/3 para calcular σ_inter final
---

---
DATE: 2026-04-22
ARC: INTENT / ARQUITECTURA
DECISION: Establecer services.IntentClassifier como clasificador canónico único — deprecar classify_intent_simple()
CONTEXT: Dos clasificadores de intent corrían en paralelo sin coordinarse: classify_intent_simple() (7-string legacy) en core/context_detector/orchestration.py y services.IntentClassifier (32 valores) en dm/phases/context.py. Divergencia ~31% en muestra de 100 mensajes.
RATIONALE: services.IntentClassifier tiene 32 valores granulares (8 sub-tipos objección), es la fuente que alimenta routing y estrategia real. classify_intent_simple() solo alimentaba DetectedContext.context_notes (informativo). Migración de orchestration.py a canonico es de bajo riesgo. dm_history_service.py bloqueado hasta fix CASUAL short-message bug (len<15 catch-all convierte "ayuda", "error", "no funciona" en CASUAL en vez de support).
CAMBIOS: core/context_detector/intent_mapping.py (nuevo — Tabla A + Tabla B), orchestration.py migrado a canonical, classify_intent_simple() marcado deprecated (logging.warning una vez por proceso), bug documentado en docs/bugs/intent_classifier_casual_short_msg.md.
BEHAVIOR CHANGES: (1) ESCALATION: ctx.intent era OTHER, ahora ESCALATION — solo afecta context_notes. (2) "cuéntame más": interest_level era soft, ahora strong (semánticamente correcto).
NEXT: fix/intent-classifier-casual-short (fix bug len<15 CASUAL), luego fix/dm-history-service-canonical-intent (migrar dm_history_service.py + hacer classify_intent_simple delegate a canonical).
STATUS: OPEN — dm_history_service.py pendiente CASUAL fix
---

---
DATE: 2026-04-22
ARC: BUDGET / BUG
DECISION: Fix ARC1-TRUNCATION — non-CRITICAL sections con tok > cap concatenaban contenido completo mientras descontaban solo cap del remaining
CONTEXT: Detectado en auditoría jerarquización (commit d5616c68, rama audit/jerarquizacion-gap). orchestrator.py._fit() solo aplicaba hard-truncate a secciones CRITICAL (force=True). Non-CRITICAL con tok>cap y compressor=None devolvían content completo pero effective_tok=cap → prompt sobre-presupuesto 5-15% típico, 25% peor caso (recalling cap=400 con 500-1000 tokens reales).
RATIONALE: Fix mínimo (Opción A, elif quirúrgico). elif tok > cap and not force: trunca a cap usando tokenizer.truncate() existente. CRITICAL path intacto. Parámetro allow_truncate_non_critical descartado — 1 único caller (context.py:585), sería dead code.
CAMBIOS: core/dm/budget/orchestrator.py:106-117 (elif nuevo), import logging + emit_metric añadidos. Métrica budget_section_truncation_total pre-registrada en registry, ahora emitida.
NEXT: Monitorizar budget_section_truncation_total en dashboard post-deploy para cuantificar frecuencia real de truncaciones.
STATUS: FIXED — fix/arc1-truncation, PR #78
---
