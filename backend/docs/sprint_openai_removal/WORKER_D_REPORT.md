# Worker D Report — Sprint 3 cleanup

## Dead code eliminado

### `core/llm.py`
- Eliminated `OpenAIClient` class (~27 lines)
- Removed `DEFAULT_OPENAI_MODEL` constant
- Changed `DEFAULT_PROVIDER` from `"openai"` → `"groq"`
- Removed `elif provider == "openai"` branch from `get_llm_client()`
- **Note**: File retained (used by 8+ production modules via `get_llm_client()`)

### `services/llm_service.py`
- Changed default provider from `LLMProvider.OPENAI` → `LLMProvider.GEMINI`
- Removed `LLMProvider.OPENAI` from `DEFAULT_MODELS` and `AVAILABLE_MODELS`
- Removed `elif self.provider == LLMProvider.OPENAI` branch in `_call_provider` (~10 lines)
- Removed `LLMProvider.OPENAI` from `failover_order` in `_try_failover`
- Removed `elif provider == LLMProvider.OPENAI` branch in `_try_failover` (~10 lines)
- Removed `_parse_openai_response` method (~15 lines)
- Removed `LLMProvider.OPENAI: "OPENAI_API_KEY"` from `_get_api_key_from_env`
- **Kept**: `LLMProvider.OPENAI = "openai"` in enum (backward compat for tests)
- **Note**: File retained (used in production by `core/dm/agent.py`, `metrics/collectors/consistency_judge.py`)

### `ingestion/response_engine_v2.py`
- Changed `default_model` from `"gpt-4o-mini"` → `"llama-3.3-70b-versatile"`
- File retained (re-exported from `ingestion/__init__.py`; has test coverage)

## Scripts sustituidos

| Script | Action | New provider |
|--------|--------|-------------|
| `scripts/blind_judge.py` | SUSTITUIR | DeepInfra Qwen3-30B-A3B (async) |
| `scripts/bootstrap_dpo.py` | SUSTITUIR | DeepInfra Qwen3-30B-A3B (sync judge_client) |
| `scripts/cpe_generate_bfi_profile.py` | SUSTITUIR | DeepInfra Qwen3-32B |
| `scripts/eval_baselines.py` | ADD provider | DeepInfra Qwen3-32B (added to PROVIDERS dict) |
| `scripts/model_comparison_v1.py` | SUSTITUIR | Replaced `call_openai` + `gpt-4o-mini` → `call_deepinfra` + `Qwen/Qwen3-32B` |
| `scripts/compare_models.py` | SUSTITUIR | Removed `call_openai` from PROVIDER_FNS + API_KEY_ENVS |
| `scripts/fill_knowledge_gaps.py` | PARTIAL | Embedding function marked TODO(Worker-C); no generation calls to migrate |

## Scripts eliminados

| Script | Reason |
|--------|--------|
| `scripts/deepseek_comparison.py` | Historical DeepSeek comparison, no longer relevant |

## Helper creado

`scripts/_shared/deepinfra_client.py` — centralized factory:
- `get_deepinfra_client()` → sync `OpenAI` client
- `get_deepinfra_async_client()` → async `AsyncOpenAI` client
- Constants: `JUDGE_MODEL = "Qwen/Qwen3-30B-A3B"`, `GEN_MODEL = "Qwen/Qwen3-32B"`

## Verificación final

```
grep "OPENAI_API_KEY" producción → SOLO en embedding/RAG code (Worker C scope):
  - api/config.py
  - api/routers/content.py
  - core/rag/semantic.py
  - scripts/fill_knowledge_gaps.py (embedding function only)
```

- Import check: ✓ (all production imports OK)
- Syntax check: ✓ (11 files, 0 errors)
- Smoke tests: ✓ (7/7 passed)
- Script --help: ✓ (blind_judge, bootstrap_dpo, compare_models, cpe_generate_bfi_profile)

## Branch

`feature/openai-removal-D-cleanup`
