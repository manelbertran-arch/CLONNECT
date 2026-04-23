# Fase 1 — Descripción y valor del sistema `contextual_prefix`

**Artefacto:** `backend/core/contextual_prefix.py` (182 LOC)
**Fecha:** 2026-04-23
**Branch:** `forensic/contextual-prefix-20260423`
**Callsites productivos:** 3 (`core/rag/semantic.py:101-105`, `api/routers/content.py:384-427`, `services/content_refresh.py:185-190`)
**Callsites scripts:** 2 (`scripts/_rag_gen_embeddings.py`, `scripts/create_proposition_chunks.py`) — fuera del pipeline de runtime
**Capa pipeline:** COLD PATH — **indexación / refresh de embeddings**, NO en hot path DM
**Flag env:** — (sin flag dedicado; gating indirecto por `OPENAI_API_KEY` presente + `ENABLE_RAG=true` para que los embeddings se consulten downstream)
**Estado Railway:** ON (corre en cualquier ingestión o refresh que invoque `rag.add_document`, `/content/embeddings/generate` o `ensure_embeddings_for_creator`)
**Creación:** commit único `dae541df` (2026-04-02) dentro del squash "audit: 14 systems optimized, 80+ bugs fixed, ..., RAG contextual prefix, ..." — 21 días en producción al momento de este forense

---

## 1. Qué hace funcionalmente

`contextual_prefix.py` expone **tres funciones públicas** que **prependen una breve descripción contextual del creador** al texto antes de generar su embedding OpenAI (`text-embedding-3-small`, 1536 dim). La descripción se compone **en tiempo de indexación** a partir del perfil del creador en BD y se **hornea en el vector almacenado** (pgvector), nunca aparece en el texto visible que se devuelve al usuario ni se inyecta en el prompt del LLM del DM.

API pública:
- `build_contextual_prefix(creator_id: str) → str`: devuelve la cadena prefijada (o `""` si no hay datos suficientes). Usa caché propio `BoundedTTLCache(50, 300s)`.
- `generate_embedding_with_context(text, creator_id) → List[float] | None`: wrapper de `embeddings.generate_embedding` que antepone el prefijo antes de llamar a OpenAI. **Solo para documentos, NO queries**.
- `generate_embeddings_batch_with_context(texts, creator_id) → List[embeddings]`: variante batch del wrapper.

Es un **pre-processor de embeddings** que implementa la técnica "Contextual Retrieval" de Anthropic (2024): enriquecer cada chunk con un resumen corto del dominio para que el vector codifique *quién + dominio + ubicación + idioma* además del contenido crudo del chunk. El objetivo declarado es **subir el recall@k del retrieval** cuando los chunks son ambiguos o demasiado cortos para auto-contextualizarse.

Ejemplo de prefijo generado para `iris_bertran` (con knowledge_about pobladísimo):
```
Iris (@iraais5) ofrece instructora de fitness, barre, zumba en Barcelona. Habla castellano y catalán mezclados. Estilo muy informal y cercano.

```

## 2. Estructura del prefijo y precedencia de fuentes

La función `_build_prefix_from_db` compone hasta **5 partes** con una cadena de fallbacks explícita sobre los campos del `CreatorData`:

| # | Parte | Fuente primaria | Fallback 1 | Fallback 2 | Emitida cuando |
|---|-------|-----------------|------------|------------|----------------|
| 1 | Identidad | `profile.clone_name` ∨ `profile.name` | — | — | siempre que exista `profile.name` |
| 1b | Handle | `knowledge_about.instagram_username` | — | — | si presente |
| 2 | Dominio | `knowledge_about.specialties` (máx 3) | `knowledge_about.bio` (primera frase, min 10 chars) | `[p.name for p in products[:5]]` | si alguna fuente tiene datos |
| 3 | Ubicación | `knowledge_about.location` | — | — | si presente |
| 4 | Idioma/dialecto | `tone_profile.dialect` (map `_DIALECT_LABELS` 7 entradas) | literal `dialect` | — | si ≠ `"neutral"` |
| 5 | Estilo formal | `tone_profile.formality` ∈ {`formal`, `casual`} | — | — | si ∈ el set |
| 6 | FAQ hint | `faqs[:3].question` unidos por `"; "` | — | — | **solo si** `len(parts)==1` (solo nombre) |

Orden de montaje en el string final (`_build_prefix_from_db:143`): `". ".join(parts) + ".\n\n"`.

**Cap duro**: `len(prefix) > 500 → prefix[:497] + ".\n\n"` (`contextual_prefix.py:146-147`).

## 3. Los tres callsites productivos y su rol en el pipeline

| Callsite | Función llamada | Contexto | Trigger productivo |
|----------|-----------------|----------|--------------------|
| `core/rag/semantic.py:101-105` | `generate_embedding_with_context(text, creator_id)` | Dentro de `SemanticRAG.add_document`, ejecutado al insertar cada documento en el índice in-memory + pgvector | Cualquier código que llame `rag.add_document(...)` — hoy: carga inicial de RAG y rehidratación desde DB |
| `api/routers/content.py:384-427` | `generate_embeddings_batch_with_context(texts, creator_id)` | Endpoint `POST /content/embeddings/generate` — backfill batch de chunks sin embedding | Llamada manual del admin o del endpoint de bulk re-indexado |
| `services/content_refresh.py:185-190` | `generate_embedding_with_context(row.content, creator_id)` | Servicio `_ensure_embeddings_for_creator`, llamado dentro de `refresh_creator_content` | Jobs de refresh de contenido (cron / manual refresh) |

**Scripts (no productivos en runtime DM)**:
- `scripts/_rag_gen_embeddings.py:30`: utility one-shot para generar embeddings de chunks.
- `scripts/create_proposition_chunks.py:57-58`: generación de propositional chunks con prefijo.

**Ausencia deliberada en hot path**: `SemanticRAG._semantic_search` (query path del DM) llama `generate_embedding(query)` directamente, **sin prefijo** — y un test explícito lo verifica (`tests/test_contextual_prefix.py:272-281`). Esto es correcto por la asimetría de la técnica Anthropic: el prefijo se hornea en el vector del documento para enriquecer su representación, pero las queries no lo llevan para no sesgar el espacio de similitud.

## 4. Inputs que lo disparan

`_build_prefix_from_db` depende de `get_creator_data(creator_id, use_cache=True)` y lee 4 ramas del objeto `CreatorData`:

| # | Campo leído | Origen BD | Default si ausente |
|---|-------------|-----------|--------------------|
| 1 | `profile.name`, `profile.clone_name` | tabla `creators` | `""` → early return `""` |
| 2 | `profile.knowledge_about` (dict) | `creators.knowledge_about` JSONB | `{}` |
| 2a | `ka.get("specialties")` | sub-clave JSONB | `[]` |
| 2b | `ka.get("bio")` | sub-clave JSONB | `""` |
| 2c | `ka.get("instagram_username")` | sub-clave JSONB | `""` |
| 2d | `ka.get("location")` | sub-clave JSONB | `""` |
| 3 | `tone_profile.dialect` | `tone_profiles.profile_data.dialect` | `"neutral"` |
| 4 | `tone_profile.formality` | `tone_profiles.profile_data.formality` | `"informal"` |
| 5 | `products[:5].name` | tabla `products` | `[]` |
| 6 | `faqs[:3].question` | tabla `faqs` | `[]` |

Los tres callsites pasan `creator_id` desde:
- `rag/semantic.py`: `metadata.get("creator_id", "unknown")` (viene del documento indexado)
- `api/routers/content.py`: `creator_id` del body del request
- `services/content_refresh.py`: `creator_id` argumento de la función

## 5. Outputs y efectos

### 5.1 Output directo
- `build_contextual_prefix` → string de 0 a 500 chars terminado en `.\n\n` (o `""`).
- `generate_embedding_with_context` → `List[float]` 1536-dim (OpenAI `text-embedding-3-small`) o `None` si falla.
- `generate_embeddings_batch_with_context` → `List[List[float] | None]` alineado por índice con `texts`.

### 5.2 Efectos de lado
1. **Caché en proceso**: `_prefix_cache.set(creator_id, prefix)` — dict bounded (50 creators, TTL 300 s) en memoria del worker uvicorn.
2. **Persistencia indirecta**: el vector de 1536-dim con el prefijo baked-in se guarda en `content_embeddings` (pgvector) vía `store_embedding(doc_id, creator_id, text, embedding)`. El texto plano **sin prefijo** se guarda en `content_chunks.content`. El prefijo solo sobrevive como perturbación del vector.
3. **Log**: `logger.info("[CONTEXTUAL-PREFIX] Built prefix for %s: %d chars", ...)` una vez por miss de caché.
4. **Log de warning on fail**: `logger.warning("[CONTEXTUAL-PREFIX] Failed to build for %s: %s", ...)` sobre excepción en construcción (fail-open: devuelve `""`).

### 5.3 Implicación crítica: el prefijo viaja dentro del vector, no en el texto
El retrieval compara queries (vector **sin prefijo**) contra documentos (vector **con prefijo horneado**). Esto significa que:
- **Rollback requiere reindex**: desactivar el flag no limpia los vectores actuales. Para comparar baseline hay que re-embeddar todo `content_chunks` sin prefijo.
- **Rollforward asimétrico**: activar el flag tras la desactivación requiere re-embeddar toda la base nueva.
- **Bug de regresión silenciosa**: un cambio en `_DIALECT_LABELS` o en `knowledge_about` cambia el vector de chunks futuros pero NO los viejos, creando una flota de vectores heterogéneos dentro del mismo índice.

## 6. Fase pipeline donde interviene

Pipeline DM V2 (`DMResponderAgentV2`):

```
Hot path (DM turn):
[phase_intent] → [phase_detection] → [phase_context]
                                       └─ RAG search (query SIN prefijo) ← hot path
                                            └─ pgvector cosine similarity con vectores YA indexados
[phase_llm_generation] → ...

Cold path (indexación — contextual_prefix AQUÍ):
[SemanticRAG.add_document] ─┐
[POST /content/embeddings/generate] ─┼─→ build_contextual_prefix → OpenAI embeddings API → store_embedding → content_embeddings (pgvector)
[services/content_refresh]  ─┘
```

**Momento de ejecución**: solo durante operaciones de escritura al índice (ingestión inicial, backfill masivo, refresh periódico). **Cero impacto en latencia DM runtime** porque la caché del `_prefix_cache` ni siquiera se toca en el query path.

**Latencia añadida en indexación**: una resolución `get_creator_data` cacheada + concatenación de strings + logging. <1 ms. La llamada OpenAI que sigue es el coste real (50-200 ms por chunk batch).

## 7. Hipótesis de valor aportado al pipeline

**H1 — El prefijo sube recall@k para queries ambiguas o cortas**. Sin prefijo, un chunk como *"cuesta 5€ por clase"* embebe como genérico "precios"; con prefijo horneado *"Iris (@iraais5) ofrece barre, zumba en Barcelona. Habla castellano y catalán. [chunk]"*, el vector se acerca a queries *"¿cuánto sale barre en Barcelona?"* aunque las palabras literales del chunk no lo digan. Este es el mecanismo reportado por Anthropic con ganancia +35-49% recall@5 (2024, entorno general).

**H2 — En sistemas multi-creator con vocabulario solapado, el prefijo desambigua**. El índice `content_embeddings` es compartido entre creators y se filtra por `creator_id` al query time (`SemanticRAG.search` pasa `creator_id` al filtro pgvector). El prefijo añade un hint adicional en el espacio vectorial para dominios vecinos: *"fitness en Barcelona"* vs *"business coach en Milano"* → menos ruido cross-creator aunque el filtro falle o el operador relaje la cláusula.

**H3 — Útil en multilingual leve (ES/CA/EN/IT)**. Al horneear "Habla catalán" en el vector, queries mezcladas ES/CA hacen cosine más alto. Sin evaluación local; depende del comportamiento de `text-embedding-3-small` con prefijos en español ante texto en catalán — **no medido**.

**H4 — Dependencia oculta en calidad de `knowledge_about`**. Si el creador tiene `knowledge_about` vacío o solo con campos irrelevantes, el prefijo degrada a fallbacks (products, faqs) o a `""` (solo nombre sin nada más). La ganancia teórica +49% se evapora cuando `knowledge_about` no es denso; y **el sistema actual no instrumenta qué fuente ganó**, ni cuántos chunks fueron indexados con prefijo vacío.

**H5 — Riesgo de contaminación temporal**. Dado que `knowledge_about` puede cambiarse por el admin (UI de perfil) sin disparar reindex, en una base estable conviven vectores generados con `knowledge_about` antiguo y nuevo. Silenciosamente, el retrieval estará "optimizado" para un perfil que ya no existe. No hay alerta ni hook de invalidación.

## 8. Dimensiones CCEE v5 potencialmente impactadas (indirectas)

`contextual_prefix` NO toca el prompt del DM ni el estilo de generación. Su influencia sobre CCEE llega **vía top-k retrieval**: si mejora el recall@k, los chunks que llegan al LLM son más relevantes → la respuesta usa información mejor alineada con la intención del usuario.

| Dim CCEE v5 | Nombre | Mecanismo de impacto | Signo esperado |
|-------------|--------|----------------------|----------------|
| **J6** | Judge Q&A Accuracy | Mejor retrieval → menos alucinación factual, más respuestas "sabe la respuesta" | **+** si H1 se cumple |
| **C3** | Contextual Reasoning | Razonamiento correcto requiere evidencia en contexto → mejor recall → más evidencia | **+/0** |
| **K1** | Knowledge Base Coverage | Chunks con prefijo embebido son más "encontrables" para queries temáticas | **+** |
| **K2** | Knowledge Accuracy / Context Usage | Mejor retrieval → el LLM cita información concreta del KB en vez de inventar | **+** |
| **H1** | Turing Test (global) | No esperado — el prefijo no cambia estilo | **0** |
| **S1** | Style Fidelity | No esperado — los chunks hornean dominio, no estilo creador | **0** |
| **B2** | Persona Fidelity | Marginal — si el prefijo fuga "habla castellano y catalán" via contexto recuperado, el LLM podría imitar | **0/+** débil |

**Nota crítica**: NO hay medición interna de ninguna de estas hipótesis en Clonnect. El +49% es un dato externo sobre corpora genéricos de Anthropic, no validado sobre `creator.iris_bertran` ni `creator.stefano_bonanno`. El **eval formal queda diferido Q2 2026** por decisión CEO (construcción de golden dataset RAG es un proyecto en sí).

## 9. Madurez técnica observada

| Señal | Estado |
|-------|--------|
| Tests unitarios | 15 tests pass (`tests/test_contextual_prefix.py`), cubren happy path, fallbacks, cache, cap, dialect, error handling |
| Docstring | Excelente (Anthropic reference, ejemplos, asimetría query/doc explicada) |
| Logs productivos | 1 `logger.info` por build (cache miss) + 1 `logger.warning` por fallo — sin `creator_id` estructurado, sin `prefix_len` estructurado salvo en mensaje, sin métrica de `cache_hit_rate` |
| Métricas Prometheus | 0 (no hay contador de builds, no hay histograma de longitud, no hay counter de fuente ganadora specialties/bio/products/faq) |
| Flag de control | — (ni `ENABLE_CONTEXTUAL_PREFIX_EMBED` ni equivalente → ablación en vivo imposible sin code change) |
| Hardcoding crítico | `max_size=50`, `ttl_seconds=300`, cap `500` chars, tabla `_DIALECT_LABELS` (7 entradas inline), `specialties[:3]`, `products[:5]`, `faqs[:3]`, bio min 10 chars |
| Invalidation hooks | 0 — cambio en `knowledge_about` no invalida ni el caché de `_prefix_cache` ni los vectores ya indexados |
| Observabilidad caché | 0 — `BoundedTTLCache` no tiene `.hits`/`.misses`; es visible vía adding instrumentación |
| Configurabilidad runtime | 0 — todo hardcoded |

## 10. Upstream / Downstream resumido

```
creator_data_loader.get_creator_data (5 min cache) ─┐
BoundedTTLCache _prefix_cache (50/300s)            ─┼─→ build_contextual_prefix
_DIALECT_LABELS (inline dict 7 items)              ─┘         │
                                                              ▼
                                   prefix ("Iris (@iraais5) ofrece ... en Barcelona. Habla ... \n\n")
                                                              │
                                                              ▼
                                         str concatenation: prefix + chunk_text
                                                              │
                              ┌───────────────────────────────┼───────────────────────────────┐
                              ▼                               ▼                               ▼
              embeddings.generate_embedding    embeddings.generate_embeddings_batch           (none)
                       (OpenAI API)                    (OpenAI API)
                              │                               │
                              └───────────────┬───────────────┘
                                              ▼
                                 store_embedding(doc_id, creator_id, text, embedding)
                                              ▼
                          pgvector table `content_embeddings` (1536-dim)
                                              ▼
                           consumed by SemanticRAG._semantic_search (hot path DM)
                                              ▼
                           top_k chunks → phase_context.user_context → LLM prompt (hot path DM)
```

Downstream crítico:
- **`content_embeddings`**: tabla pgvector donde viven los vectores con prefijo horneado. Cada `UPDATE` de `creators.knowledge_about` deja la tabla en estado inconsistente hasta que se ejecute manualmente `content_refresh` o `_ensure_embeddings_for_creator`.
- **HNSW index** (migration 038): indexa esos vectores para búsqueda aproximada. No distingue "con prefijo" / "sin prefijo", todos van al mismo espacio.

---

## Resumen ejecutivo Fase 1

- `contextual_prefix` es un **pre-processor cold-path** que añade 1-3 frases de contexto del creador antes de embeddar cada chunk en pgvector. Implementa la técnica Anthropic "Contextual Retrieval" (2024, +35-49% recall reportado en sus benchmarks).
- Solo se ejecuta en **indexación / refresh**, nunca en el hot path DM. El **query embedding NO lleva prefijo** — asimetría deliberada verificada por test.
- Hay **3 callsites productivos** (`rag/semantic.add_document`, `content.py` bulk endpoint, `content_refresh` service) y 2 scripts. Todos terminan en `store_embedding → content_embeddings` pgvector.
- **Valor teórico**: +35-49% recall@k según Anthropic. **Valor medido en Clonnect: 0 puntos** — sin benchmark local, sin golden dataset, sin gate A/B. CCEE v5 potencialmente impactado en **J6, C3, K1, K2**, con magnitud no caracterizada.
- **Hardcoding detectado**: `max_size=50`, `ttl_seconds=300`, cap `500`, `_DIALECT_LABELS` (7 entradas inline), `specialties[:3]`, `products[:5]`, `faqs[:3]`. Sin env vars de control. Sin métrica Prometheus. Sin flag para ablación.
- **Riesgo mayor (H5)**: vectores indexados con `knowledge_about` antiguo siguen vivos cuando el admin actualiza el perfil del creador. Sin hook de invalidación ni alerta de drift.
- **Decisión CEO aplicada**: NO se construye golden dataset RAG en esta iteración. El entregable de este worker es el PR listo (extracción de hardcoding + flag + métricas + tests) con la medición formal marcada como tech-debt **Q2 2026**.

**STOP Fase 1.** Procedo a Fase 2 (forense línea a línea).
