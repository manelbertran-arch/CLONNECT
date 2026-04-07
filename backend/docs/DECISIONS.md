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
