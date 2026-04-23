# Fase 6 — Plan de medición de `contextual_prefix`

> **MEDICIÓN DIFERIDA Q2 2026 — decisión CEO**
>
> Este documento especifica **cómo** se mediría el impacto de `contextual_prefix` cuando el golden dataset RAG esté construido. No se ejecuta en este ciclo. El entregable del PR actual es **dejar el sistema listo** (flag, config, métricas, refactor) para que la medición se pueda ejecutar sin tocar código.

**Branch:** `forensic/contextual-prefix-20260423`
**Fecha:** 2026-04-23
**Target de medición:** `core/contextual_prefix.py` (efecto sobre recall@k del retrieval RAG)

---

## 1. Tipo de evaluación

**Categoría**: RAG retrieval quality evaluation (offline, no CCEE directo).

**Métrica primaria**: **recall@k** (`k ∈ {5, 10, 20}`) sobre un golden dataset de (query, ground_truth_relevant_docs).

**Métricas secundarias**:
- **MRR (Mean Reciprocal Rank)**: útil para entender *cuán arriba* aparece el primer doc relevante.
- **nDCG@k**: si el golden dataset tiene grados de relevancia (no solo binario relevante/no).
- **Latencia indexación** (p50, p99): cuánto tarda embeddar 100 chunks con vs sin prefix.
- **Coste $ OpenAI**: tokens consumidos con vs sin prefix (el prefix añade ~35-40 tokens por chunk).

**Métricas CCEE indirectas observables post-eval** (si el eval RAG pasa gate):
- `J6` (Judge Q&A Accuracy): respuestas del DM que citan info del KB mejoran.
- `K1` (Knowledge Base Coverage): más chunks relevantes recuperados → más info disponible para el LLM.
- `K2` (Knowledge Accuracy / Context Usage): menos alucinación factual.

---

## 2. Harness requerido

### 2.1 Componentes que **ya existen** (listos para el eval)

- ✅ `core/rag/semantic.py::SemanticRAG.search` — retrieval pipeline completo.
- ✅ `core/embeddings.py` — embedding + store + pgvector search.
- ✅ `core/contextual_prefix.py` — sistema bajo eval.
- ✅ `ENABLE_CONTEXTUAL_PREFIX_EMBED` flag (este PR) — permite ablar on/off sin code change.
- ✅ Métricas Prometheus (este PR) — observabilidad durante el eval.
- ✅ `tests/test_contextual_prefix.py` — asegura correctitud funcional pre-eval.

### 2.2 Componentes que **faltan** (blocker para Q2)

| Componente | Estado | Blocker? | Esfuerzo estimado |
|------------|--------|----------|-------------------|
| **Golden dataset RAG Iris** | ❌ No existe | **SÍ** | 1-2 semanas ingeniero + revisión creator |
| **Golden dataset RAG Stefano** | ❌ No existe | **SÍ** | 1-2 semanas |
| Harness `scripts/rag_eval.py` | ❌ No existe | Sí | 2-3 días |
| Reindex script "baseline sin prefix" | ❌ Parcialmente (existe refresh, pero no con flag off) | Sí | 1 día |
| Script de comparación A/B de índices | ❌ No existe | Sí | 1 día |
| Dashboard Grafana de métricas prefix | ❌ No existe (métricas sí) | No (nice-to-have) | 0.5 día |

**Total**: ~3 semanas ingeniero + 2 semanas de curación con creators = **5 semanas elapsed**.

### 2.3 Especificación del golden dataset (blocker principal)

#### 2.3.1 Estructura

```yaml
# tests/eval_datasets/rag_golden_iris_bertran.yaml
version: 1
creator_id: iris_bertran
locale: es-CA
queries:
  - id: iris_001
    query: "¿Cuánto cuesta barre?"
    expected_docs:
      - chunk_id: "faq_price_barre"
        relevance: 2   # 2 = perfecto, 1 = parcial, 0 = irrelevante
      - chunk_id: "product_barre"
        relevance: 1
    intent: pricing
    notes: "Query exacta sobre precio de clase"

  - id: iris_002
    query: "puedo ir si estoy embarazada"
    expected_docs:
      - chunk_id: "faq_pregnancy"
        relevance: 2
    intent: restrictions
    notes: "Requiere entender el contexto de restricciones"

  # ... min 50 queries per creator
```

#### 2.3.2 Criterios de queries a incluir

| Categoría | Queries target | Por qué |
|-----------|----------------|---------|
| Intent `pricing` / `product_info` | 10-15 | Volumen alto en Iris, match exacto común |
| Intent `restrictions` / `health` | 5-10 | Semánticas, donde prefix contextual debería ayudar |
| Intent `scheduling` / `location` | 5-10 | Info factual simple |
| Short cryptic queries (<5 palabras) | 10 | Donde prefix horneado ayuda más (H1) |
| Code-switched ES/CA | 5 | Validar multilingual |
| Queries en idioma distinto del prefix | 3 | Test Bug 8 (Stefano IT) |
| Queries ambiguas (multi-intent) | 5 | Stress del retrieval |

#### 2.3.3 Proceso de construcción

1. **Sampling de mensajes reales**: query LLM histórico de `messages WHERE role='user' AND creator_id=iris_bertran LIMIT 500` → filtrar por calidad (no ruido tipo "hola", no mensajes vacíos).
2. **Curación por creator**: Iris/Stefano marcan qué chunks de `content_chunks` son realmente relevantes para cada query. Herramienta: UI simple (spreadsheet + doc viewer) o script en notebook.
3. **Validación inter-rater**: un segundo revisor (ingeniero) valida ≥20% del dataset para detectar sesgos del creator.
4. **Versionado**: dataset en `tests/eval_datasets/*.yaml` commiteado. Cambios requieren bump de `version`.

#### 2.3.4 Tamaño mínimo aceptable

- **50 queries por creator** (mínimo estadístico para delta > ±5% confiable).
- **~150 chunks ground-truth marcados** por creator.
- **200-500 chunks "distractores"** (el resto del índice del creator) necesarios para medir ranking.

---

## 3. Baseline requirement: reindex sin prefix

### 3.1 Por qué es necesario

La ganancia teórica del paper Anthropic (+35-49%) se mide **comparando el índice con prefix vs el índice sin prefix**. Necesitamos dos estados del `content_embeddings`:

- **Baseline A**: todos los chunks re-embedded **con** `ENABLE_CONTEXTUAL_PREFIX_EMBED=true` (estado actual en producción).
- **Baseline B**: todos los chunks re-embedded **con** `ENABLE_CONTEXTUAL_PREFIX_EMBED=false` (estado control).

### 3.2 Protocolo de comparación (no puede hacerse en prod)

**Prohibido mezclar A y B en la misma tabla** — el retrieval falla silenciosamente si la mitad de vectores tiene prefix y la otra no.

**Opciones**:

1. **Snapshot staging**: clonar `content_embeddings` en staging, flippear flag, re-embed. Medir ambos. **Preferido**.
2. **Tabla dual**: columna adicional `embedding_no_prefix vector(1536)` en `content_embeddings`. Duplica espacio pero permite A/B atómico. **Coste PG**: +1 GB por creator. No preferido por coste.
3. **Eval en jupyter offline**: cargar chunks en memoria, generar ambos embeddings ad-hoc, búsqueda manual. **Preferido para 1ª iteración**, no escala.

### 3.3 Coste estimado del reindex

Por creator, ~3000-8000 chunks (Iris+Stefano). Con `text-embedding-3-small` (128k tokens/min tier 1):
- Tokens por chunk: ~200 (texto) + ~40 (prefix) ≈ 240 con prefix, 200 sin prefix.
- 8000 chunks × 240 = ~2M tokens → ~15 min de API calls a $0.02/1M = **$0.04** por creator.
- x2 (con y sin prefix) = $0.08. **Despreciable**.

---

## 4. Gates de decisión

### 4.1 Gate KEEP — mantener prefix en producción

**Criterio de éxito** (ambas condiciones):
1. `recall@5` con prefix **≥** `recall@5` sin prefix **+ 10 puntos porcentuales relativos** (p.ej. 65% → 71.5%).
2. `recall@5` con prefix > `recall@5` sin prefix con `p < 0.05` (Wilcoxon signed-rank sobre las 50-100 queries).

**Interpretación**: si el prefix genera al menos +10% relativo con significancia, vale su coste (tokens OpenAI + cache RAM + drift de invalidation).

### 4.2 Gate REVERT — desactivar prefix

**Criterio**: `recall@5` con prefix **≤** `recall@5` sin prefix (o ganancia <2% sin significancia).

**Acción**:
1. Set `ENABLE_CONTEXTUAL_PREFIX_EMBED=false` en Railway.
2. Ejecutar reindex de todo `content_embeddings` con el flag apagado.
3. Documentar decisión en `docs/audit/contextual_prefix_eval_q2_2026.md`.
4. Archivar `contextual_prefix.py` como tech-debt a simplificar en otro ciclo.

### 4.3 Gate INCONCLUSO — ampliar muestra

**Criterio**: ganancia en rango 2-10% **sin significancia** (`p > 0.05`).

**Acción**:
1. Ampliar golden dataset a 150+ queries por creator.
2. Re-ejecutar eval.
3. Si sigue inconcluso: considerar que el beneficio es marginal, aplicar Gate REVERT.

### 4.4 Gate MULTILINGUAL REVISIT

**Condición especial**: si el eval para Stefano (IT) muestra ganancia <5% o negativa pero para Iris (ES) muestra ganancia >10%, entonces:
- El problema es Bug 8 (multilingual estructura ES hardcoded).
- Acción: **no desactivar** para Iris; trabajar en Q2+ el template por idioma antes de decidir en Stefano.

---

## 5. Diseño experimental (ABT — Ablation Binary Test)

### 5.1 Variantes a comparar

| Variante | Config | Propósito |
|----------|--------|-----------|
| **A — Baseline OFF** | `ENABLE_CONTEXTUAL_PREFIX_EMBED=false`, BM25 on, reranking on | Control |
| **B — Current ON** | `ENABLE_CONTEXTUAL_PREFIX_EMBED=true`, BM25 on (sin prefix), reranking on | Producción hoy |
| **C (opcional) — Prefix deterministic + BM25 contextual** | B + prefix inyectado también en índice BM25 | Captura gap identificado en Fase 4 |

C es un experimento **post-gate KEEP**: si B gana a A, entonces probamos si C gana a B. Si sí, abrir ticket Q3 para `core/rag/bm25.py`.

### 5.2 Protocolo step-by-step (cuando Q2 arranque)

```bash
# 1. Congelar golden dataset
git tag eval-golden-iris-v1

# 2. Clonar staging DB de content_embeddings
# (ops: coordinar con DBA, snapshot de Neon)

# 3. Reindex variante A en staging
export ENABLE_CONTEXTUAL_PREFIX_EMBED=false
python scripts/reindex_all_embeddings.py --creator iris_bertran --target staging

# 4. Ejecutar eval variante A
python scripts/rag_eval.py \
  --dataset tests/eval_datasets/rag_golden_iris_bertran.yaml \
  --target staging \
  --metric recall@5,recall@10,recall@20,mrr \
  > results/eval_iris_A.json

# 5. Reindex variante B en staging (replace)
export ENABLE_CONTEXTUAL_PREFIX_EMBED=true
python scripts/reindex_all_embeddings.py --creator iris_bertran --target staging

# 6. Ejecutar eval variante B
python scripts/rag_eval.py --dataset ... --target staging > results/eval_iris_B.json

# 7. Comparar
python scripts/rag_eval_compare.py results/eval_iris_A.json results/eval_iris_B.json
# emite delta por métrica, Wilcoxon p-value, gate recomendado
```

### 5.3 Estructura del script `scripts/rag_eval.py` (a escribir Q2)

```python
# Pseudocódigo
for query in dataset.queries:
    results = rag.search(query.text, top_k=20, creator_id=dataset.creator_id)
    retrieved_ids = [r["doc_id"] for r in results]
    for k in [5, 10, 20]:
        relevant_in_topk = len(set(retrieved_ids[:k]) & set(q.expected_doc_ids))
        recall_k = relevant_in_topk / len(q.expected_doc_ids)
        metrics[f"recall@{k}"].append(recall_k)
    # MRR
    for i, did in enumerate(retrieved_ids):
        if did in q.expected_doc_ids:
            metrics["rr"].append(1/(i+1))
            break
    else:
        metrics["rr"].append(0)
output {
    "recall@5": {"mean": ..., "std": ..., "n": 50},
    "recall@10": ..., "recall@20": ..., "mrr": ...,
}
```

### 5.4 Plan estadístico

- **N mínimo**: 50 queries por creator.
- **Test**: Wilcoxon signed-rank (pares A vs B por query) para `recall@5`.
- **Significancia**: `α = 0.05`.
- **Potencia esperada**: con N=50 y delta +10%, potencia ~80% (suficiente).

---

## 6. Riesgos del eval + mitigaciones

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| Golden dataset con sesgo del creator | Medición apunta a preferencias personales, no a calidad real | Inter-rater validation ≥20% |
| Queries demasiado fáciles (todas match exacto en texto) | `recall@5` satura al 100% en ambas variantes → delta invisible | Incluir categorías "short cryptic" y "semántica" (sección 2.3.2) |
| Reindex de staging diverge del pipeline prod | Medición no representativa | Reindex debe usar exactamente `api/routers/content.py::/embeddings/generate` (mismo path code) |
| OpenAI cambia silenciosamente el modelo `text-embedding-3-small` | Baseline A no reproducible | Anchorear eval con versión fija + snapshot de embeddings en staging |
| HNSW index bloat | Recall aproximado difiere de exacto | Ejecutar 10% del eval con `WHERE FALSE` forzando scan secuencial, validar que HNSW no degrada |

---

## 7. Timeline propuesto Q2 2026

| Semana | Tarea | Owner propuesto |
|--------|-------|-----------------|
| W1 | Construir golden dataset Iris (50 queries) | Ing + Iris |
| W2 | Construir golden dataset Stefano (50 queries) | Ing + Stefano |
| W3 | Escribir `scripts/rag_eval.py` + `rag_eval_compare.py` | Ing |
| W4 | Setup staging DB + scripts reindex | DBA + Ing |
| W5 | Ejecutar eval A/B para ambos creators, analizar | Ing |
| W6 | Decisión gate + writeup + comunicar CEO | Ing + CEO |

**Coste total estimado**: ~6 semanas elapsed, ~120 h ingeniero + 20 h de creators.

---

## 8. Qué observar **antes** de ejecutar el eval (desde hoy)

Este PR deja **observable en producción** sin necesitar el eval formal:

### 8.1 Cache hit rate (salud operativa)

```promql
sum(rate(contextual_prefix_cache_hits_total[5m])) /
(sum(rate(contextual_prefix_cache_hits_total[5m])) + sum(rate(contextual_prefix_cache_misses_total[5m])))
```

Esperado: >95% en régimen estable (pocos creators, caché calienta rápido).

### 8.2 Distribución de source

```promql
sum by (source) (rate(contextual_prefix_builds_total[1h]))
```

Esperado:
- `specialties`: ~70-90% (ambos Iris y Stefano tienen specialties definidas).
- `bio` / `products_fallback`: ~5-15%.
- `name_only` / `empty`: idealmente ~0% (alerta si sube — indica que `knowledge_about` está degradado).

### 8.3 Ratio empty prefix

```promql
sum(rate(contextual_prefix_builds_total{has_prefix="false"}[1h])) /
sum(rate(contextual_prefix_builds_total[1h]))
```

Esperado: <1%. Si sube a >5%, algo está fallando (schema mismatch, DB outage).

### 8.4 Errores por clase

```promql
sum by (error_class) (rate(contextual_prefix_errors_total[5m]))
```

Esperado: 0. Cualquier pico → alert.

### 8.5 Distribución de longitud

```promql
histogram_quantile(0.5, rate(contextual_prefix_length_chars_bucket[1h]))
histogram_quantile(0.99, rate(contextual_prefix_length_chars_bucket[1h]))
```

Esperado p50: 100-200. p99: <500 (cap). Si p99 toca 500 con frecuencia → `CONTEXTUAL_PREFIX_CAP_CHARS` debería subirse o los `MAX_*` reducirse.

### 8.6 Truncations

```promql
sum(rate(contextual_prefix_truncations_total[1h]))
```

Esperado: 0 en estado estable. Cualquier aparición → config miscalibrada.

---

## 8.7 Dependencia pre-merge: `scripts/bootstrap_tone_labels.py`

Tras el refactor DB-driven de labels (commit `5ed16c99`), el prefix ya no contiene diccionario de traducciones. Los creators existentes (Iris, Stefano) **no tienen** `dialect_label` / `formality_label` poblados en `tone_profile.profile_data`. Sin un bootstrap, el prefix post-merge emite el literal crudo del enum `dialect` (p.ej. `"Habla catalan_mixed"`), lo cual es funcionalmente correcto (degradación grácil) pero pobre en calidad humana.

**Script**: `backend/scripts/bootstrap_tone_labels.py` (incluido en este PR).

**Ejecución post-merge** (orden sugerido):
```bash
railway run python3 scripts/bootstrap_tone_labels.py --dry-run   # preview
railway run python3 scripts/bootstrap_tone_labels.py              # apply to all
railway run python3 scripts/bootstrap_tone_labels.py --creator iris_bertran   # single
```

**Idempotencia**: si `dialect_label` ya está poblado y no vacío, el script skipea. `--force` permite sobrescribir (para corrección manual).

**Mapping inicial** (editable en el script):
```python
"iris_bertran": {
    "dialect_label": "en catalán y castellano coloquial",
    "formality_label": "con tono cercano y desenfadado",
},
"stefano_bonanno": {
    "dialect_label": "in italiano colloquiale",
    "formality_label": "con tono professionale e diretto",
},
```

**Efecto**: tras correr el script y llamar `POST /admin/contextual-prefix/invalidate/{creator_id}`, los próximos builds de prefix usan las etiquetas humanas. Los vectores ya indexados siguen con el prefix viejo hasta que se invoque `POST /admin/ingestion/refresh-content/{creator_id}`.

**Si el script NO se ejecuta**: el sistema funciona (degradación grácil) pero Iris y Stefano reciben prefijos de calidad reducida. No afecta el eval Q2 (el eval compara con-prefix vs sin-prefix, ambos con la misma calidad del label).

---

## 9. Preparación del PR — lo que sí deja este ciclo

El PR actual (forensic/contextual-prefix-20260423) es **condición necesaria** para la medición Q2:

| Requisito del eval Q2 | ¿Lo aporta este PR? |
|------------------------|---------------------|
| Flag ablación on/off sin redeploy | ✅ `ENABLE_CONTEXTUAL_PREFIX_EMBED` |
| Métricas Prometheus para monitorizar eval en vivo | ✅ 6 métricas nuevas |
| Config tuneable para experimentos (cap, limits) | ✅ 8 env vars |
| `creator_id="unknown"` no ensucia la muestra | ✅ Bug 2 fix |
| Cross-creator contamination imposible | ✅ Bug 1 fix |
| Logs estructurados para post-mortem | ✅ Structured fields con `creator_id, source, error_class` |
| Cache invalidation endpoint | ✅ `POST /admin/contextual-prefix/invalidate` |
| Tests que validan correctitud pre-eval | ✅ 28 tests (antes 15) |

**Nada de lo anterior se puede construir en Q2 sin también tocar el código original** → hacerlo ahora evita acoplamiento temporal entre "preparar el sistema" y "medirlo".

---

## Resumen ejecutivo Fase 6

- **Medición diferida Q2 2026** por decisión CEO. Este doc especifica el protocolo para cuando Q2 arranque.
- **Blocker principal**: construcción del golden dataset RAG (50+ queries per creator, curadas con creator, inter-rater validadas). Estimación: 2 semanas/creator.
- **Tipo eval**: recall@{5,10,20} + MRR, A/B entre `ENABLE_CONTEXTUAL_PREFIX_EMBED=true` vs `=false`, requiere reindex completo por variante en staging.
- **Gates**:
  - KEEP: `+10%` relativo en recall@5 con `p<0.05`.
  - REVERT: `≤0%` o ganancia <2% sin significancia.
  - MULTILINGUAL REVISIT: ganancia asimétrica Iris-OK / Stefano-KO → arreglar Bug 8 antes de decidir.
- **Timeline**: 6 semanas elapsed, ~120 h ingeniero + ~20 h creators.
- **Este PR deja listo**: flag, config, métricas, structured logs, invalidation endpoint, tests extendidos. Cero código nuevo necesario Q2 fuera del harness del eval.
- **Observabilidad inmediata** en producción (Prometheus) valida operativamente el sistema incluso antes del eval formal.

**STOP Fase 6.** Procedo a Fase 7 (commit + PR).
