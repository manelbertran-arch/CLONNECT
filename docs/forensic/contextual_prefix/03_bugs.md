# Fase 3 — Bugs detectados en `contextual_prefix` + callsites

**Artefacto base:** `backend/core/contextual_prefix.py` + 3 callsites productivos
**Fecha:** 2026-04-23
**Severidad**: rating interno (BLOCKING / HIGH / MED / LOW) con justificación de impacto medido sobre indexación + retrieval + CCEE indirectos.

---

## Bug 1 — Cross-creator embedding contamination en `/content/embeddings/generate` (HIGH)

**Archivo**: `backend/api/routers/content.py:384-432`

**Descripción**:
El endpoint `POST /content/embeddings/generate` acepta `creator_id` como parámetro del body y lo usa para construir el prefijo:

```python
L427: embeddings = generate_embeddings_batch_with_context(texts, creator_id)  # <- creator_id del request
```

Pero **guarda** los embeddings con `row.creator_id` (el `creator_id` de la fila `content_chunks` en BD):

```python
L432: if store_embedding(row.chunk_id, row.creator_id, row.content, embedding):  # <- row.creator_id de la BD
```

**Escenario de reproducción**:
1. Admin ejecuta `POST /content/embeddings/generate` con `creator_id="iris_bertran"`, `batch_size=10`.
2. Backend filtra `content_chunks WHERE creator_id = 'iris_bertran' AND embedding IS NULL` (L401).
3. Hasta aquí OK — solo chunks de Iris.
4. **Pero**: si la migración o ingesta dejó chunks con `creator_id` corrupto/mezclado (improbable hoy, posible si el admin resetea el filtro SQL en un fix rápido), la línea L427 usa el `creator_id` del request para el prefix (= Iris) pero guarda con `row.creator_id` (= cualquier cosa). Resultado: vector de Iris-flavored prefix guardado bajo otro creator.

**Más realista — en el flujo actual**:
- El filtro SQL garantiza consistencia, por lo que el bug es **latente** hoy. Pero:
- Es una **mina arquitectónica**: cualquier persona que modifique el SQL en el futuro (p.ej. añadir `OR creator_id IS NULL` para backfill) dispara el bug.
- **No hay assert** validando `row.creator_id == creator_id` antes de `store_embedding`. Fallo silencioso.

**Impacto**:
- Vectores con prefijo del creator X almacenados bajo creator Y → retrieval de queries del creator Y devolverá esos chunks enriquecidos contextualmente "por Iris". Recall puede incluso subir por casualidad, pero la información horneada es errónea.
- **Difícil de detectar** porque los chunks textuales sí pertenecen al creator correcto; solo el vector está "envenenado".

**Fix recomendado**:
```python
# En content.py L427-432
for row, embedding in zip(batch, embeddings):
    if row.creator_id != creator_id:
        logger.error("[EMBED] creator_id mismatch: %s vs %s", row.creator_id, creator_id)
        continue
    if embedding and store_embedding(row.chunk_id, row.creator_id, row.content, embedding):
        generated += 1
```
Y mejor aún: eliminar `creator_id` del body del endpoint y derivarlo desde las rows (único source of truth).

---

## Bug 2 — `creator_id="unknown"` en `SemanticRAG.add_document` crea basura en pgvector (HIGH)

**Archivo**: `backend/core/rag/semantic.py:100-110`

**Descripción**:
```python
L104: creator_id = metadata.get("creator_id", "unknown") if metadata else "unknown"
L105: embedding = generate_embedding_with_context(text, creator_id)
L106: if embedding:
L107:     store_embedding(doc_id, creator_id, text, embedding)
```

Si el caller olvida pasar `creator_id` en `metadata`, el documento se indexa con `creator_id="unknown"`:
- El prefix para `"unknown"` vuelve `""` (no hay tal creator en BD).
- El embedding se genera sin contexto.
- Se guarda una fila en `content_embeddings` con `creator_id="unknown"`.

**Escenario de reproducción**:
```python
rag = get_semantic_rag()
rag.add_document("doc_xyz", "Some orphan text")  # olvidé metadata
# → content_embeddings gana una fila con creator_id='unknown'
```

**Impacto**:
- **Filas huérfanas en pgvector** que nunca son retrievables (las búsquedas filtran por un `creator_id` válido).
- Hinchan el índice HNSW innecesariamente (migration 038), degradando rendimiento de búsqueda aproximada.
- Tabla `content_embeddings` tiene una clave foránea implícita pero **no FK real** a `creators.name`, por lo que `"unknown"` no explota en tiempo de insert.
- No hay job de limpieza de filas con `creator_id="unknown"`.

**Rastros en producción (verificación requiere Railway, no ejecutable aquí)**:
```sql
SELECT COUNT(*) FROM content_embeddings WHERE creator_id = 'unknown';
```

**Fix recomendado**:
```python
# En semantic.py L104
if not metadata or not metadata.get("creator_id"):
    logger.error("[RAG] add_document called without creator_id, skipping embed for %s", doc_id)
    return  # NO embebar sin creator_id válido
creator_id = metadata["creator_id"]
```

---

## Bug 3 — Iteración 1-a-1 en `content_refresh._embed_new_chunks` (MED — perf/cost)

**Archivo**: `backend/services/content_refresh.py:185-193`

**Descripción**:
```python
L189: for row in rows:  # rows puede tener hasta 100 chunks
L190:     embedding = generate_embedding_with_context(row.content, creator_id)
L191:     if embedding:
L192:         store_embedding(row.chunk_id, creator_id, row.content, embedding)
```

Cada chunk es una llamada a OpenAI API separada. Existe la variante batch `generate_embeddings_batch_with_context` que comprime ~100 chunks en 1-2 calls.

**Impacto medido (estimación)**:
- Latencia: 100 chunks × ~80 ms OpenAI latency ≈ **8 s** por creator por refresh vs ~1 s con batch.
- Coste OpenAI: misma cantidad de tokens (OpenAI cobra por tokens, no por llamada), pero **rate limit hits** más probables con 100 calls/min que con 2. `text-embedding-3-small` tiene limit ~3000 RPM; en un cluster de workers refrescando, se llega.
- Refresh es cada 24h, 2 creators hoy → no urgente, pero escala mal.

**Fix recomendado**:
```python
# services/content_refresh.py L185-193
from core.contextual_prefix import generate_embeddings_batch_with_context

texts = [row.content for row in rows]
embeddings = generate_embeddings_batch_with_context(texts, creator_id)
for row, emb in zip(rows, embeddings):
    if emb and store_embedding(row.chunk_id, creator_id, row.content, emb):
        stored += 1
```
Drop-in replacement. Mismos `store_embedding` calls. Ahorra ~7s por refresh.

---

## Bug 4 — Cap 500 chars rompe mid-word (LOW — estético, impacto semántico marginal)

**Archivo**: `backend/core/contextual_prefix.py:146-147`

**Descripción**:
```python
L146: if len(prefix) > 500:
L147:     prefix = prefix[:497] + ".\n\n"
```

Si el prefix es `"Iris (@iraais5) ofrece instr... [...497 chars]"` y el char 497 cae a mitad de palabra (`"instruct"` cortado), el resultado es `"instruct.\n\n"`. Palabra cortada + punto falso.

**Impacto**:
- Para `text-embedding-3-small`, una palabra cortada genera BPE tokens extraños (sub-word) — puede contaminar el vector ligeramente. En la práctica es ruido <0.5% del vector total.
- Nunca se alcanza el cap en datos reales de Iris/Stefano (prefix típico ~140 chars). Activable solo si `knowledge_about.specialties` es una lista larga — poco probable.
- **Latente, no vivo hoy**.

**Fix recomendado**:
```python
# En contextual_prefix.py L146-147
if len(prefix) > 500:
    # Cut at last space before 497
    truncated = prefix[:497]
    last_space = truncated.rfind(" ")
    if last_space > 300:  # avoid too aggressive cuts
        truncated = truncated[:last_space]
    prefix = truncated + ".\n\n"
```

---

## Bug 5 — `formality == "casual"` nunca matchea en producción (MED — feature muerta)

**Archivo**: `backend/core/contextual_prefix.py:126-130`

**Descripción**:
```python
L126: if formality == "formal":
L127:     parts.append("Estilo formal y profesional")
L128: elif formality == "casual":
L129:     parts.append("Estilo muy informal y cercano")
```

Pero el dataclass `ToneProfileInfo` documenta los valores posibles como `"formal"`, `"informal"`, `"mixed"` (`creator_data_loader.py:192`). **Ningún creator en producción tiene `formality="casual"`** — ese valor nunca entra al código.

Iris y Stefano tienen `formality="informal"` (default). La rama L128-129 **nunca se ejecuta**.

**Impacto**:
- Iris y Stefano pierden el hint "Estilo muy informal y cercano" → el prefix queda sin Parte 5. Impacto marginal (ya hay 4 partes con señal suficiente).
- **Feature muerta desde creación**. 21 días en producción sin hacer nada.

**Fix recomendado** (decidir dirección):
- **Opción A**: cambiar `"casual"` → `"informal"` para que la rama matchee (pero entonces TODOS los creators con default disparan la etiqueta → prefix más largo, puede no ser deseado).
- **Opción B**: pasar la lista de formalities a un `dict` configurable tipo `_FORMALITY_LABELS = {"formal": "Estilo formal y profesional", "informal": "Estilo cercano e informal", "mixed": "Estilo mixto"}` y loopearla como `_DIALECT_LABELS`.
- **Recomendación**: Opción B. Sale gratis como parte del refactor de Fase 5.

---

## Bug 6 — Cache invalidation inexistente tras cambio en `knowledge_about` (HIGH — silencioso/acumulativo)

**Archivo**: `backend/core/contextual_prefix.py:30` + ausencia de hooks en ruta admin

**Descripción**:
El caché `_prefix_cache` tiene TTL 5 min. El caché de `get_creator_data` (upstream) tiene TTL 5 min. Pero **cambios en `creators.knowledge_about` no invalidan ningún caché** ni disparan re-indexación de los vectores ya almacenados.

**Flujo del bug**:
1. Admin actualiza `knowledge_about` de Iris vía UI (añade "pilates" a specialties).
2. Durante 5 min, el próximo `build_contextual_prefix("iris_bertran")` retorna el prefix **viejo** (cache hit).
3. Tras 5 min, el caché expira → nuevo prefix con "pilates" incluido.
4. **Pero los vectores existentes en `content_embeddings` siguen hornados con el prefix viejo**. El cambio solo afecta chunks indexados a partir del paso 3.
5. Sin un `refresh_creator_content` explícito (manual) o espera al cron diario, la base queda **mezclada** — unos vectores con "pilates", otros sin.
6. Retrieval para queries sobre pilates estará parcialmente degradado indefinidamente.

**Impacto**:
- **Acumulativo silencioso**: cada edit de perfil del admin va generando drift entre vectores viejos y nuevos.
- **Invisibilidad**: no hay métrica que diga "% de vectores indexados con versión X del prefix".
- **Railway logs no ayudan**: el log solo se emite en miss, no dice qué versión del prefix se usó.

**Fix recomendado (parcial, deuda Q2 2026)**:
- Corto plazo (en este PR): añadir un endpoint `POST /admin/contextual-prefix/invalidate/{creator_id}` que haga `_prefix_cache.pop(creator_id)`. No resuelve los vectores viejos, pero al menos detiene la propagación del viejo prefix a nuevos chunks en la ventana de 5 min tras el edit.
- Medio plazo (Q2): hook en UI de edit de `knowledge_about` → enqueue job `refresh_creator_content(creator_id)` post-save.
- Largo plazo (Q2+): versionar el prefix dentro de `content_embeddings` (nueva columna `prefix_version` — BLOCKING: requiere migration alembic 040) y exponer `% stale` en dashboard.

---

## Bug 7 — Dialectos no mapeados producen mezcla ES/EN (LOW)

**Archivo**: `backend/core/contextual_prefix.py:122`

**Descripción**:
```python
L122: lang_label = _DIALECT_LABELS.get(dialect, dialect)
L123: parts.append(f"Habla {lang_label}")
```

Si `dialect` es un valor no mapeado (p.ej. `"portuguese"`, `"french"`, `"galician"`, `"basque"`), el fallback es el literal crudo:
- `dialect="portuguese"` → `"Habla portuguese"` (palabra EN en frase ES).
- `dialect=""` → skipea por L111 (correcto).

**Impacto**:
- Hoy ningún creator tiene dialect fuera de los 7 mapeados → **bug latente**.
- Si el producto escala a creators portugueses, brasileños, etc., cada nuevo idioma entra como mezcla hasta que el dev añada manualmente a `_DIALECT_LABELS`.

**Fix recomendado** (parte del refactor en Fase 5): mover `_DIALECT_LABELS` a `core/config/dialect_labels.py` (o tabla `vocab_meta` si existe) para que añadir nuevos dialectos no requiera tocar `contextual_prefix.py`.

---

## Bug 8 — Conectivos españoles hardcoded rompen multilingual estructural (MED)

**Archivo**: `backend/core/contextual_prefix.py:94, 108, 123, 128, 137`

**Descripción**:
Las palabras conectivas del prefijo están todas en español:
- `"ofrece"` (L94)
- `"en"` (L108)
- `"Habla"` (L123)
- `"Estilo formal y profesional"` / `"Estilo muy informal y cercano"` (L128, L130)
- `"Temas frecuentes"` (L137)

Para un creator italiano (Stefano), el prefix resulta:
```
Stefano Bonanno ofrece business coach en Milano. Habla italiano. Estilo formal y profesional.
```

**Mezcla ES-estructura + IT-nombre/dialect**. Un query italiano (`"quanto costa il coaching?"`) tiene que superar dos layers de mismatch lingüístico para recuperar el chunk.

**Impacto**:
- Para Stefano específicamente, el beneficio +49% de Anthropic queda mitigado. OpenAI `text-embedding-3-small` es multilingual pero no inmune a mezclas asimétricas.
- Imposible medir sin golden dataset (deferred Q2).
- El fix natural es switch por `dialect` → template idiomático.

**Fix recomendado** (parcial en Fase 5, completo Q2):
- Añadir `_TEMPLATES = {"es": {...}, "it": {...}, "en": {...}}` con las strings traducidas.
- Derivar `template_lang` desde `dialect` (mapping: `italian` → `it`, `english` → `en`, resto → `es`).
- Compose con f-strings usando el template.

---

## Bug 9 — BoundedTTLCache no es thread-safe (LOW hoy, HIGH si uvicorn escala)

**Archivo**: `backend/core/cache.py:193-253` (upstream, fuera de scope de este PR)

**Descripción**:
`BoundedTTLCache.get/set/pop/_evict` no usa locks. Bajo uvicorn single-worker no hay concurrencia real (Python GIL + async single event loop). Pero si se activa `--workers N`, o si se añade un hilo de background que toque el caché, existe race:
- Thread A lee `_data` en `get()` → key existe, lee age.
- Thread B ejecuta `_evict()` → borra key.
- Thread A retorna valor borrado (no explota, pero retorna stale).

**Impacto**:
- Cero hoy (`uvicorn` 1-worker en Railway).
- Si se escalan workers: inconsistencia del caché, sin corrupción de BD (no escribe).
- Si se añade cleanup async: posible RuntimeError al mutar dict durante iter.

**Fix recomendado**: fuera de scope — parche en `core/cache.py` con `threading.RLock`. No tocar en este PR.

---

## Bug 10 — Fail-open sin métrica de degradación (MED — observabilidad)

**Archivo**: `backend/core/contextual_prefix.py:155-157`

**Descripción**:
```python
L155: except Exception as e:
L156:     logger.warning("[CONTEXTUAL-PREFIX] Failed to build for %s: %s", creator_id, e)
L157:     return ""
```

Cualquier fallo (BD down, schema mismatch, attribute error por cambio en `CreatorData`) → `""` → chunks embebidos sin prefix. **Silencioso**. Sin:
- Métrica Prometheus (`contextual_prefix_failures_total{creator_id, error_type}`).
- Alerta.
- Contador de "ratio_chunks_with_empty_prefix" en una ventana.

**Escenario real**:
- Migración alembic introduce cambio breaking en `creators.knowledge_about` (p.ej. cambia de `JSONB` a `JSON[]`).
- `get_creator_data` carga con error silencioso — campo queda `{}`.
- `_build_prefix_from_db` sigue funcionando pero todo creator tiene `ka={}` → fallback a products/faqs.
- Tras deploy: durante 24 h, el cron de content_refresh re-indexa todo → vectores en producción quedan con prefix degradado.
- Retrieval baja silenciosamente. Nadie se entera hasta que un user reporta respuestas pobres.

**Fix recomendado (Fase 5)**:
- Counter Prometheus `contextual_prefix_builds_total{creator_id, source, has_prefix}` donde:
  - `source ∈ {specialties, bio, products_fallback, faq_fallback, name_only}`.
  - `has_prefix ∈ {true, false}`.
- Counter Prometheus `contextual_prefix_errors_total{creator_id, error_class}`.
- Histograma `contextual_prefix_length_bytes`.
- Log estructurado JSON con los mismos fields (compatible con log aggregators).

---

## Hardcoding inventario completo (referencia rápida)

| # | Símbolo | Valor | Línea | Justificación del valor (si existe) | Propuesta env var |
|---|---------|-------|-------|--------------------------------------|-------------------|
| 1 | `max_size` en `_prefix_cache` | 50 | L30 | — | `CONTEXTUAL_PREFIX_CACHE_SIZE=50` |
| 2 | `ttl_seconds` en `_prefix_cache` | 300 | L30 | alinear con `get_creator_data` cache | `CONTEXTUAL_PREFIX_CACHE_TTL=300` |
| 3 | `specialties[:3]` | 3 | L91 | — | `CONTEXTUAL_PREFIX_MAX_SPECIALTIES=3` |
| 4 | `data.products[:5]` | 5 | L81 | — | `CONTEXTUAL_PREFIX_MAX_PRODUCTS=5` |
| 5 | `data.faqs[:3]` | 3 | L135 | — | `CONTEXTUAL_PREFIX_MAX_FAQS=3` |
| 6 | `len(first_sentence) > 10` | 10 | L98 | filtro bios basura | `CONTEXTUAL_PREFIX_MIN_BIO_LEN=10` |
| 7 | Cap final | 500 | L146 | ~12% de 4000 chars chunk típico | `CONTEXTUAL_PREFIX_CAP_CHARS=500` |
| 8 | Truncate size | 497 | L147 | 500 − 3 (`.\n\n`) | derivar de #7 |
| 9 | `_DIALECT_LABELS` inline | 7 entries | L113-121 | — | extraer a `core/config/dialect_labels.py` |
| 10 | Conectivos ES | `ofrece`, `en`, `Habla`, `Estilo...`, `Temas frecuentes` | L94, L108, L123, L128, L130, L138 | — | template dict por idioma (opción futura Q2) |

---

## Ranking consolidado por severidad y prioridad del fix

| # | Bug | Severidad | Fix en este PR (Fase 5)? | Blocker para medición Q2? |
|---|-----|-----------|--------------------------|----------------------------|
| 6 | Cache invalidation ausente | HIGH | Parcial (endpoint invalidate) | Sí — sin esto, eval contra prefix drift-ed |
| 1 | Cross-creator contamination (content.py) | HIGH | Sí (assert + drop creator_id del body) | Sí — contamina baseline |
| 2 | creator_id="unknown" orphans | HIGH | Sí (early return) | No — pero es limpieza pre-medición |
| 10 | Fail-open sin métrica | MED | Sí (métricas + structured logs) | Sí — sin métrica no se puede observar degradación |
| 3 | 1-a-1 vs batch en content_refresh | MED | Sí (drop-in batch) | No — solo coste |
| 8 | Conectivos ES hardcoded multilingual | MED | **No** — requiere template dict, fuera de scope del audit actual (mencionar Q2) | Parcial para Stefano |
| 5 | formality=="casual" dead branch | MED | Sí (template dict por formality) | No |
| 7 | Dialectos no mapeados mezclan ES/EN | LOW | Sí (extraer a config) | No |
| 4 | Cap 500 rompe mid-word | LOW | Sí (respect last space) | No |
| 9 | BoundedTTLCache no thread-safe | LOW | **No** — upstream | No (uvicorn 1-worker) |

---

## Resumen ejecutivo Fase 3

- **10 bugs identificados**, 3 HIGH (cross-creator, unknown-orphans, cache-invalidation), 4 MED (perf, multilingual, dead branch, observabilidad), 3 LOW (cap, dialectos, thread-safety).
- **Blocker para medición Q2**: Bug 6 (cache invalidation) + Bug 1 (cross-creator) deben arreglarse antes de construir el golden dataset, o la baseline quedará contaminada.
- **En este PR (Fase 5)** se arreglan 8 de 10 (todos excepto Bug 8 multilingual templates y Bug 9 thread-safety upstream).
- **Hardcoding a extraer a env vars**: 7 constantes numéricas + `_DIALECT_LABELS` a módulo de config.
- **Deuda documentada para Q2**: multilingual templates, versionado de prefix en pgvector, invalidation automática por hook admin.

**STOP Fase 3.** Procedo a Fase 4 (papers y repos).
