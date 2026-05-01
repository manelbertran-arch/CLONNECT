# Worker A Report — Sprint 1 drain Railway

**Fecha**: 2026-05-01
**Branch**: `feature/openai-removal-A-drain`

## Cambios realizados

### `core/providers/gemini_provider.py`

- **Eliminada** función `_call_openai_mini()` completa (~55 líneas)
- **Eliminadas** funciones helpers `_add_fallback_guard()` y constante `_FALLBACK_GUARD` (~20 líneas)
- **3 callers actualizados** a `return None` directamente:
  - `generate_simple()` línea ~406: ya no llama a OpenAI
  - path config-driven línea ~698: ya no llama a OpenAI
  - path legacy cascade línea ~774: ya no llama a OpenAI
- **Docstrings y comentarios actualizados** para reflejar la nueva arquitectura

### `core/dm/history_compactor.py`

- **Eliminado** bloque OpenAI completo (~18 líneas):
  ```python
  if not model or "openai" in model.lower() or "gpt" in model.lower():
      # ... openai.OpenAI(...).chat.completions.create() ...
  ```
- Si Gemini falla: `RuntimeError` propagado al caller
- El caller `_build_llm_summary()` ya captura la excepción (línea 375) y hace fallback a template summary → comportamiento correcto

## Tests

- `pytest tests/unit/test_gemini_provider.py` → **5/5 passed ✓**
- `pytest tests/unit/test_deepinfra_provider.py` → **passed ✓**
- `pytest tests/unit/test_openrouter_provider.py` → **passed ✓**
- Syntax check `gemini_provider.py` → **✓**
- Syntax check `history_compactor.py` → **✓**
- Import check ambos módulos → **✓**
- `_call_summary_llm` raises `RuntimeError` correctamente → **✓**

## Tests pre-existentes fallando (no relacionados con estos cambios)

- `test_dm_history_filters.py::test_status_assignment_logic` — búsqueda de string en código
- `test_dm_agent_advanced_prompts.py::test_flag_exists` — flag eliminada en sprint previo
- `test_fireworks_provider.py/test_together_provider.py` — network live tests

## Coste eliminado

- `_call_openai_mini`: ~120 calls/día × $0.0003/call = **$0.60/mes eliminado**
- Historia compactor: eliminado fallback (contribuía al mismo pool de ~120 calls/día)
- **Total billing Railway post-deploy: ~$0/mes**

## Hallazgo: cambios pre-existentes en working tree

Los siguientes archivos ya estaban modificados antes de este sprint (probablemente de sesión anterior):
- `core/embeddings.py` — migrado a Gemini text-embedding-004
- `services/llm_judge.py` — actualizado para DeepInfra
- `ingestion/transcriber.py` — Whisper-1 tier-2 eliminado
- `core/personality_extraction/llm_client.py` — migrado a Gemini
- `core/llm.py` — OpenAIClient eliminado

Estos NO se incluyen en este commit. Necesitan su propia verificación y commit.

## Branch

`feature/openai-removal-A-drain` → listo para revisión
