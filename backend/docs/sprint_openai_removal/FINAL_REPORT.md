# OpenAI Removal — Final Report

## Branch
`feature/openai-removal-FINAL` (consolidado desde workers A, B, C, D)

## Commits
```
af9ec8a2 refactor: cleanup OpenAI dead code + migrate scripts to DeepInfra  [Worker D]
5e89d916 refactor(C): migrate embeddings from OpenAI to Gemini gemini-embedding-001  [Worker C]
be5c0f19 refactor(B): replace OpenAI in prod secondary services  [Worker B]
6d14153a refactor: remove OpenAI fallbacks in production DM path  [Worker A]
```

## Resumen
- **29 archivos modificados**
- **794 líneas eliminadas, 587 insertadas** (neto: -207)
- Referencias activas OPENAI_API_KEY en producción: **1 residual** (`core/rag/semantic.py`)
- Referencias en scripts: 2 pendientes (ver sección "Pendientes")

## Cambios por worker

### Worker A — Producción crítica
- `core/providers/gemini_provider.py`: eliminado fallback `_call_openai_mini` (-140 líneas)
- `core/dm/history_compactor.py`: eliminado branch OpenAI en compactación de historial

### Worker B — Producción secundaria
- `services/llm_judge.py`: GPT-4o-mini → DeepInfra Qwen3-30B-A3B (OPENAI_API_KEY → DEEPINFRA_API_KEY)
- `core/personality_extraction/llm_client.py`: fallback OpenAI → delegate a Gemini Flash
- `ingestion/transcriber.py`: eliminado Whisper-1 tier-2 (-85 líneas), cascade Groq → Gemini → `""`

### Worker C — Embeddings
- `core/embeddings.py`: text-embedding-3-small → gemini-embedding-001 (dim 1536 via MRL)
- task_type RETRIEVAL_DOCUMENT/RETRIEVAL_QUERY para RAG correcto
- Tests actualizados, REINDEX_PROCEDURE documentado
- `scripts/deepseek_comparison.py`: eliminado

### Worker D — Dead code + scripts
- `core/llm.py`: eliminada clase OpenAIClient
- `services/llm_service.py`: eliminado branch OpenAI, `_parse_openai_response`, default → GEMINI
- `ingestion/response_engine_v2.py`: default gpt-4o-mini → llama-3.3-70b-versatile
- 6 scripts migrados a DeepInfra Qwen3: `blind_judge.py`, `bootstrap_dpo.py`, `cpe_generate_bfi_profile.py`, `eval_baselines.py`, `model_comparison_v1.py`, `compare_models.py`
- `scripts/_shared/deepinfra_client.py`: nuevo cliente DeepInfra centralizado

## Referencias OPENAI_API_KEY residuales (pendientes de PR separado)

| Archivo | Tipo | Impacto | Acción |
|---|---|---|---|
| `core/rag/semantic.py:79` | **Producción** | RAG semantic search (site #7) | Migrar a `core/embeddings.generate_embedding()` |
| `scripts/fill_knowledge_gaps.py:145` | Script | Seeding knowledge base | TODO(Worker-C) — migrar a Gemini embeddings |
| `scripts/seed_products_rag.py:21,134` | Script | One-off seeding | Migrar a Gemini embeddings post-reindex |
| `api/routers/content.py:176,327` | Router | Mensaje de error en diagnóstico | Actualizar string error message |
| `api/config.py:28` | Config | Campo Optional[str] | Mantener hasta confirmar $0 billing 7 días |

**Crítico**: `core/rag/semantic.py` es la única referencia activa en el path de producción. Si la key se elimina de Railway y hay queries RAG activas → semantic search degradado silenciosamente (no crash, solo warning + skip).

## Acciones manuales pendientes (en orden)

### 1. Rotar GOOGLE_API_KEY (URGENTE)
Las keys actuales en `.env` están expuestas. Ver REINDEX_PROCEDURE.md.
- Ir a https://aistudio.google.com/app/apikey
- Revocar keys antiguas, crear key nueva
- Actualizar `.env` local + Railway env vars

### 2. Reindex content_embeddings (después de rotar key)
- Ejecutar procedimiento en `docs/sprint_openai_removal/REINDEX_PROCEDURE.md`
- ETA: ~2h dependiendo del volumen

### 3. Migrar `core/rag/semantic.py` a Gemini embeddings (PR separado)
- Cambiar `api_key = os.getenv("OPENAI_API_KEY")` → usar `generate_embedding()` de `core/embeddings.py`
- Esta es la única referencia productiva residual post-este-PR

### 4. Variable Railway (opcional, default ya en código)
```
CLONE_SCORE_JUDGE_MODEL=Qwen/Qwen3-30B-A3B
```

### 5. Después de 7 días con dashboard $0
- Eliminar `OPENAI_API_KEY` de Railway
- Cancelar tarjeta en https://platform.openai.com/account/billing
- Eliminar referencias restantes en `api/config.py`, `verify_config.py`, `deploy_check.py`

## Coste futuro estimado
| Concepto | Antes | Después |
|---|---|---|
| GPT-4o-mini (DM path fallback) | ~$30/mes | $0 |
| GPT-4o-mini (CloneScore judge) | ~$14/mes potencial | $0 |
| OpenAI Whisper-1 (audio fallback) | ~$2/mes potencial | $0 |
| OpenAI embeddings | ~$5/mes | $0 |
| DeepInfra judge (nuevo) | $0 → ~$13/mes si CloneScore activo | ~$13/mes |
| **Total** | **~$45-51/mes** | **~$0-13/mes** |
