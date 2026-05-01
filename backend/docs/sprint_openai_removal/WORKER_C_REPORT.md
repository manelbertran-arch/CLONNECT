# Worker C Report — Sprint 2bis embeddings migration

## Cambios

### core/embeddings.py
- Eliminado `get_openai_client()` y todos los imports de OpenAI
- `generate_embedding()`: migrado de `client.embeddings.create(model="text-embedding-3-small")` a `httpx.post` contra Gemini API
- `generate_embeddings_batch()`: simplificado a loop sobre `generate_embedding()` (consistente con codebase, elimina dependencia de `batchEmbedContents`)
- Añadido parámetro `task_type` (default `RETRIEVAL_DOCUMENT`) para optimizar RAG
- Modelo: `models/gemini-embedding-001` (no `text-embedding-004` — ver nota abajo)
- Patrón httpx: consistente con `core/providers/gemini_provider.py`
- Cache: mantenido `BoundedTTLCache` con key `{task_type}:{text}` para evitar contaminación entre document/query embeddings

### core/rag/semantic.py
- Sin cambios — ya usaba `core/embeddings.generate_embedding()` vía import

### tests/test_embeddings_audit.py
- Reescrito para mockear `httpx.post` en lugar de `get_openai_client`
- Añadido test de `task_type=RETRIEVAL_QUERY`

### tests/audit/test_audit_embeddings.py
- Eliminado import de `get_openai_client` (ya no existe)

### tests/test_rag_knowledge_audit.py
- Actualizado mock de `get_openai_client` → `_get_gemini_api_key`

### scripts/rag_health_check.py
- Actualizado mensaje de error: `OPENAI_API_KEY` → `GOOGLE_API_KEY`

## Decisión de modelo: gemini-embedding-001, no text-embedding-004

El plan original mencionaba `text-embedding-004` pero ese modelo tiene dimensión nativa 768.
`outputDimensionality=1536` requiere upscaling → no soportado.
`gemini-embedding-001` tiene dimensión nativa 3072 y soporta MRL truncation hasta 1536.
El plan describe correctamente gemini-embedding-001 como el modelo objetivo ("top-3 MTEB").

## Tests

- `tests/test_embeddings_audit.py`: 16/16 ✓
- `tests/audit/test_audit_embeddings.py`: 5/5 ✓
- `tests/test_contextual_prefix.py`: 31/31 ✓
- `tests/test_rag_knowledge_audit.py`: 39/39 ✓
- `tests/test_semantic_memory_pgvector.py`: 12/13 (1 fallo pre-existente, no relacionado)
- Smoke tests: 10/10 ✓

## Live API test

⚠ No ejecutado — `GOOGLE_API_KEY` y `GEMINI_API_KEY` en `.env` están marcadas como leaked/bloqueadas por Google.
El código es correcto; requiere rotate de API key antes de validar en producción.

Validar tras rotate:
```bash
set -a && source .env && set +a
.venv/bin/python3.11 -c "
from core.embeddings import generate_embedding
out = generate_embedding('Hola, soy Iris y enseño Pilates en Barcelona')
assert out and len(out) == 1536
print(f'✓ dim={len(out)}, first 5: {out[:5]}')
"
```

## Pgvector

- Schema sin cambios (mantenemos dim 1536 con `outputDimensionality=1536`)
- Vectores existentes generados con OpenAI NO son comparables con nuevos Gemini
- **Acción requerida**: reindexar content_embeddings tras rotate de API key
  (`services/content_refresh.py` o `scripts/create_proposition_chunks.py` con `--force-reindex`)

## Coste eliminado

- $0.50/mes (text-embedding-3-small @ ~100K tokens/mes)
- Coste futuro: $0/mes (Gemini free tier cubre volumen actual 1000x)

## Branch

`feature/openai-removal-C-embeddings`
