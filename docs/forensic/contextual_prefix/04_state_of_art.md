# Fase 4 — Estado del arte (papers, repos, consenso 2024-2026)

**Artefacto objetivo:** `backend/core/contextual_prefix.py`
**Fecha revisión:** 2026-04-23
**Scope:** papers + repos + práctica industrial sobre contextual retrieval, contextual embeddings, late chunking, hybrid search y adaptación multilingüe.

---

## 1. Paper fundacional — Anthropic "Contextual Retrieval" (2024-09)

**Fuente primaria**: [Contextual Retrieval — Anthropic (2024-09-19)](https://www.anthropic.com/news/contextual-retrieval)

### 1.1 Técnica

Anthropic propone dos modificaciones al pipeline RAG estándar:
1. **Contextual Embeddings**: antes de embeddar cada chunk, prepender un resumen generado por un LLM que explique **dónde encaja ese chunk en el documento completo**. El LLM recibe el documento entero + el chunk concreto, y emite 50-100 tokens de contexto específico.
2. **Contextual BM25**: el mismo prefix contextual se inyecta en el índice BM25 (keyword-based) para que la búsqueda léxica también se beneficie.

Ambas técnicas se combinan típicamente con **reranking** (cross-encoder sobre top-K resultados) para obtener el stack completo.

### 1.2 Resultados reportados (métrica: 1 − recall@20)

| Config | Failure rate | Delta vs baseline |
|--------|--------------|-------------------|
| Baseline (embeddings sin contexto) | 5.7% | — |
| + Contextual Embeddings | 3.7% | **−35.1%** (relativo) |
| + Contextual Embeddings + Contextual BM25 | 2.9% | **−49.1%** (relativo) |
| + Contextual BM25 + CE + Reranking (stack completo) | 1.9% | **−67%** |

**Nota crítica**: el benchmark de Anthropic usa corpora de **documentos completos** (PDFs técnicos, codebases) donde cada chunk tiene un "documento padre" rico en contexto. Aplicar esto a chunks de **social media posts + FAQs** (el caso Clonnect) no es automáticamente transferible — un post de Instagram de 200 chars no tiene "contexto de documento mayor" equiparable.

### 1.3 Diferencias clave vs implementación de Clonnect

| Aspecto | Anthropic (paper) | Clonnect (`contextual_prefix.py`) |
|---------|-------------------|-----------------------------------|
| Quién genera el contexto | LLM (Claude) por chunk | Composición determinista desde BD |
| Coste de generación | 1 LLM call por chunk (caro, pero cacheable) | 1 string concat por creator (gratis) |
| Granularidad | Per-chunk, custom al contenido | Per-creator, mismo prefix para TODOS los chunks del creator |
| Contenido del prefix | Contextualiza el chunk dentro del documento | Contextualiza al creator en bruto |
| Hybrid BM25 contextual | Sí, prefix inyectado en BM25 también | **No** — Clonnect tiene BM25 (ENABLE_BM25_HYBRID) pero opera sobre texto plano sin prefix |
| Reranking | Recomendado | Activo (ENABLE_RERANKING cross-encoder) |
| Medición | Eval formal con 1−recall@20 | **0 eval local** |

**Implicación**: la implementación de Clonnect captura **la parte más barata y menos efectiva** del paper (prefix determinista a nivel creator, no a nivel chunk). La ganancia +35-49% del paper asume el modo expensive (LLM per-chunk). Clonnect está probablemente recuperando un subconjunto de ese beneficio — **quizás +5-15% recall, quizás 0, sin medir no se sabe**.

---

## 2. Paper relacionado — "Late Chunking" (arXiv 2409.04701, Jina AI 2024-2025)

**Fuente primaria**: [Late Chunking: Contextual Chunk Embeddings Using Long-Context Embedding Models (arXiv:2409.04701v3, Jul 2025)](https://arxiv.org/abs/2409.04701)

### 2.1 Técnica

Propuesta alternativa a "prefix antes de embed": usar un modelo de embedding de **contexto largo** (8k-128k tokens), pasar el documento completo por el transformer, y **solo al final** hacer mean-pooling por segmentos (chunks). Resultado: cada chunk embedding captura contexto global del documento porque los token-level embeddings ya atendieron al documento entero.

### 2.2 Comparación con contextual prefix

| Propiedad | Contextual Prefix (Anthropic) | Late Chunking (Jina) |
|-----------|-------------------------------|----------------------|
| Requiere LLM adicional | Sí (para generar prefix per-chunk) | No |
| Requiere long-context embedding model | No | **Sí** (jina-embeddings-v2-small-en o v3) |
| Coste runtime | Alto (1 LLM call/chunk en indexado) | Medio (1 forward pass/document, pero chunk-level embeddings) |
| Transferibilidad a text-embedding-3-small | ✅ | ❌ — OpenAI model no expone token-level outputs |
| Performance vs baseline | +35% recall (reportado) | +5-12% recall (reportado en subset de MTEB) |

**Implicación para Clonnect**: Late chunking no aplica directamente hoy porque Clonnect usa `text-embedding-3-small` (OpenAI) que no expone token-level embeddings. **Migrar a Jina v3** o similar abriría esta opción — un ticket Q3 2026, fuera de scope del audit actual.

---

## 3. Hybrid search + reranking como stack productivo (consenso 2025-2026)

**Fuentes**:
- [Optimizing RAG with Hybrid Search & Reranking — Superlinked](https://superlinked.com/vectorhub/articles/optimizing-rag-with-hybrid-search-reranking)
- [Building Contextual RAG Systems with Hybrid Search and Reranking — Analytics Vidhya (2024-12)](https://www.analyticsvidhya.com/blog/2024/12/contextual-rag-systems-with-hybrid-search-and-reranking/)
- [Hybrid Search — Perivitta Rajendran blog (2026-03)](https://pr-peri.github.io/blogpost/2026/03/05/blogpost-hybrid-search.html)

### 3.1 Consenso industrial

El stack **dense (semantic) + sparse (BM25) + cross-encoder reranking** es la receta probada en producción 2026. Cada capa cubre un modo de fallo distinto:
- **Dense**: captura similitud semántica, tolerante a sinónimos. Falla con query exacta (nombres de producto, precios literales).
- **Sparse/BM25**: captura match léxico exacto. Falla con paráfrasis.
- **Cross-encoder**: relaciona query y chunk bidireccionalmente (no factorizado como dot product) → alta precisión.

### 3.2 Estado en Clonnect

| Componente | Estado actual |
|------------|---------------|
| Dense semantic (OpenAI) | ✅ Activo |
| BM25 hybrid (`ENABLE_BM25_HYBRID=true`) | ✅ Activo |
| Cross-encoder reranking (`ENABLE_RERANKING=true`) | ✅ Activo |
| **Contextual prefix inyectado en dense** | ✅ Activo (vía `contextual_prefix.py`) |
| **Contextual prefix inyectado en BM25** | ❌ **NO** (BM25 indexa texto plano de `content_chunks.content`) |
| Fine-tuned embedding | ❌ No (OpenAI off-the-shelf) |

**Gap identificado**: Clonnect aplica el prefix al embedding dense pero **no al índice BM25**. En Anthropic paper, el salto de 35% (solo dense contextual) a 49% (dense + BM25 contextual) vino precisamente del BM25. **Porcentaje del valor potencial capturado hoy: ~71%** (si la técnica fuera directamente transferible, cosa no garantizada).

Este gap **NO se cubre en este PR** (requiere refactor de `core/rag/bm25.py` que está fuera del scope de auditar `contextual_prefix.py`). Se documenta en `06_measurement_plan.md` como deuda Q2+.

---

## 4. Multilingüe — embeddings para ES/CA/IT/EN

### 4.1 Consenso de benchmarks (MTEB Multilingual v2, 2025-2026)

**Fuentes**:
- [MTEB Multilingual v2 leaderboard (Hugging Face)](https://huggingface.co/spaces/mteb/leaderboard) — referenciado en varias reviews 2026
- [Harrier-OSS-v1: SOTA Multilingual Embeddings (2026-03-30)](https://kiadev.net/news/2026-03-30-harrier-oss-v1-multilingual-embeddings)
- [Best Embedding Models for RAG in 2026 — StackAI](https://www.stackai.com/insights/best-embedding-models-for-rag-in-2026-a-comparison-guide)

Top multilingual models 2026:
| Modelo | Idiomas | MTEB Multi v2 | Self-host | Notas |
|--------|---------|---------------|-----------|-------|
| Qwen3-Embedding-8B | 100+ | 70.58 | ✅ | Líder en junio 2025 |
| BGE-M3 (BAAI) | 100+ | 68-69 | ✅ MIT | Dense + sparse + multi-vector |
| Cohere embed-v3 | 100+ | ~69 | ❌ API | Enterprise-focused |
| Harrier-OSS-v1 | 50+ | SOTA | ✅ | 2026-03 release |
| OpenAI text-embedding-3-large | 100+ | ~67 | ❌ API | **Clonnect usa el `-small` (1536d, 3072d less), peor aún** |
| OpenAI text-embedding-3-small | 100+ | ~62-64 | ❌ API | **Clonnect usa este** |

### 4.2 Implicaciones para Clonnect

El modelo actual (`text-embedding-3-small`) no es mal multilingüe, pero está **6-8 puntos de MTEB-Multi por debajo** de los líderes. Para la casuística Clonnect (ES con trazas CA, IT):
- **ES/CA**: bien cubierto. OpenAI multilingual trata ES-CA con cierta cercanía por cercanía léxica + share de training data.
- **IT (Stefano)**: cubierto, pero la estructura del prefix hardcoded en ES debilita la señal (ver Bug 8 en Fase 3).

### 4.3 Paper específico ES/IT

**Fuente**: [A Comprehensive Evaluation of Embedding Models and LLMs for IR and QA Across English and Italian — MDPI (2025)](https://www.mdpi.com/2504-2289/9/5/141)

Hallazgo relevante: modelos multilingual off-the-shelf tienen degradación de 10-20 puntos en recall cuando el query está en idioma-X y el documento en idioma-Y, **especialmente si el prefix/contexto mezcla idiomas**. Esto valida directamente Bug 8 de Fase 3.

**Recomendación aplicable ahora**: mantener el prefix en el idioma dominante del creator, usando `dialect` como switch. En este PR se introduce la infraestructura (envs, config) pero el switch por idioma se difiere a Q2.

---

## 5. Repos y librerías de referencia

### 5.1 LlamaIndex — SemanticSplitterNodeParser

**Repo**: [run-llama/llama_index](https://github.com/run-llama/llama_index)

LlamaIndex ofrece `SemanticSplitterNodeParser` (split semántico por embeddings) + un patrón opcional **MetadataReplacementNodePostProcessor** que inyecta metadata en el chunk durante retrieval. Útil para el caso Clonnect: el contexto "quién es el creator" **podría** inyectarse post-retrieval en vez de pre-embedding, evitando el problema de cache invalidation del vector.

**Implicación arquitectónica**: hay una alternativa "contextual post-retrieval" que evita hornear contexto en el vector:
- Pros: cambios en `knowledge_about` NO requieren reindex.
- Cons: pierdes el beneficio sobre recall (el vector sigue siendo genérico) — solo ayudas al reranker/LLM downstream.

No reemplaza a `contextual_prefix.py` hoy, pero es una ruta posible de migración si la deuda de invalidation pesa.

### 5.2 Haystack — v2 DocumentStore + ContextualRetriever

**Repo**: [deepset-ai/haystack](https://github.com/deepset-ai/haystack)

Haystack v2 incluye abstracciones para pipelines RAG modulares. La comunidad ha publicado integraciones de "contextual retrieval" Anthropic-style:
- [haystack-experimental](https://github.com/deepset-ai/haystack-experimental) tiene `ContextualChunkEnricher`.
- Patrón: genera el contexto con LLM al indexar, no con composición determinista. Más caro pero más potente.

### 5.3 `NeuralVulture/contextual-retrieval-by-anthropic` (reference impl)

**Repo**: [RionDsilvaCS/contextual-retrieval-by-anthropic](https://github.com/RionDsilvaCS/contextual-retrieval-by-anthropic)

Implementación directa del paper Anthropic con Python. Usa Claude Haiku para generar prefix per-chunk. Buen referente para la variante "expensive" si Clonnect quisiera subir la apuesta.

### 5.4 Jina AI — Late Chunking

**Repo**: [jina-ai/late-chunking](https://github.com/jina-ai/late-chunking)

Implementación oficial del paper de late chunking. Requiere jina-embeddings-v2-small-en o v3. Código pequeño (~400 LOC), puede evaluarse en local sin mucha fricción.

### 5.5 Instructor — Async contextual retrieval

**Fuente**: [Implementing Anthropic's Contextual Retrieval with Async Processing — Instructor (2024-09)](https://python.useinstructor.com/blog/2024/09/26/implementing-anthropics-contextual-retrieval-with-async-processing/)

Patrón práctico: procesar batches de chunks en paralelo con asyncio al indexar. Clonnect hoy ni siquiera usa el batch endpoint en `content_refresh.py` (Bug 3 en Fase 3) — hay espacio de mejora 10-100x.

### 5.6 Unstructured — Contextual Chunking en platform

**Fuente**: [Contextual Chunking — Unstructured (2024-2025)](https://unstructured.io/blog/contextual-chunking-in-unstructured-platform-boost-your-rag-retrieval-accuracy)

Unstructured lo integró nativamente en su plataforma gestionada. Señal de que el patrón está maduro y adoptado por vendors enterprise.

---

## 6. Estado del arte 2026 — ¿qué harían hoy?

Si diseñas desde cero un sistema tipo Clonnect en abril 2026 con el estado del arte, el stack recomendado sería:

```
Ingestión → Chunking semántico (LlamaIndex/Haystack)
         → Contextual enrichment per-chunk (LLM Haiku/Flash, cacheable)
         → Dense embedding (BGE-M3 ó Qwen3-Embedding-8B multilingual, self-hosted)
         → BM25 index (con prefix inyectado también)
         → pgvector HNSW

Retrieval → Hybrid dense + sparse (RRF / weighted fusion)
         → Cross-encoder reranking (bge-reranker-v2-m3)
         → LLM con citations
```

**Deltas respecto a Clonnect hoy**:
| Componente | Clonnect hoy | Estado del arte 2026 | Criticidad |
|------------|--------------|----------------------|------------|
| Chunking | Custom (content_chunks) | LlamaIndex SemanticSplitter | MED (mejorable) |
| Contextual enrichment | Determinista per-creator | LLM per-chunk | HIGH (más capturable con eval) |
| Dense model | text-embedding-3-small (OpenAI) | BGE-M3 / Qwen3 | MED (mejorable) |
| BM25 contextual | No | Sí | HIGH (capturable, directamente accionable) |
| Reranking | Activo | Activo | OK |

**Decisión CEO**: no mover a LLM per-chunk ni cambiar modelo de embedding en Q2. El salto debería validarse con un eval formal (golden dataset) que no existe hoy. Este worker cubre solo el refactor del sistema actual.

---

## 7. Lo que dicen los papers más recientes (2025-2026)

### 7.1 "Beyond Chunk-Then-Embed" (arXiv:2602.16974, 2026)

**Fuente**: [Beyond Chunk-Then-Embed: A Comprehensive Taxonomy and Evaluation of Document Chunking Strategies for Information Retrieval](https://arxiv.org/html/2602.16974v1)

Paper taxonómico 2026. Clasifica las estrategias:
- **Pre-chunk enrichment** (← Clonnect aquí): prepend context antes de embed.
- **Post-chunk enrichment**: LLM per-chunk context (Anthropic).
- **Late chunking** (Jina).
- **Hierarchical chunking** (parent-child).

Conclusión del paper: "post-chunk enrichment" sigue siendo el más efectivo medido, pero "pre-chunk" con metadata estructurada del dominio es el **mejor ratio coste/beneficio cuando el dominio es muy específico y cerrado** (caso Clonnect).

**Validación del diseño actual**: pre-chunk deterministic prefix es una elección defendible para Clonnect. El valor añadido del LLM per-chunk sería +10-20% sobre el pre-chunk, no +49% sobre cero.

### 7.2 Documentation chunking 2025 practical guide

**Fuente**: [Document Chunking for RAG: 9 Strategies Tested (70% Accuracy Boost 2025) — LangCopilot](https://langcopilot.com/posts/2025-10-11-document-chunking-for-rag-practical-guide)

Blog post muy aplicado. Resumen:
- Boost acumulado de ~70% llegando al stack completo.
- Contextual prefix aporta **10-20% del boost** en dominios específicos (ranges 5-25% con alta varianza por dominio).
- Invisibilidad del prefix al usuario es considerada "best practice" — Clonnect ya lo hace (prefix en vector, no en texto visible).

---

## 8. Consenso sobre observabilidad RAG (práctica 2026)

**Fuentes**:
- [Production RAG System with pgvector — Markaicode](https://markaicode.com/pgvector-rag-production/)
- [HNSW Indexes with Postgres and pgvector — Crunchy Data](https://www.crunchydata.com/blog/hnsw-indexes-with-postgres-and-pgvector)

### 8.1 Métricas mínimas esperadas en producción

| Métrica | Por qué | Estado Clonnect |
|---------|---------|-----------------|
| `recall@k` sobre golden dataset | Gate principal de salud del retrieval | ❌ Sin eval (blocker Q2) |
| `cache_hit_rate` (prefix cache, retrieval cache) | Detectar desalineación cache/TTL | ❌ Sin métrica |
| `contextual_prefix_builds_total` + source | Saber qué rama genera el prefix | ❌ Sin métrica |
| `prefix_length_bytes` histograma | Detectar caps anómalos | ❌ Sin métrica |
| `embedding_generation_errors_total` | Fallos OpenAI / BD | ❌ Sin métrica |
| `index_reindex_lag_seconds` | Drift entre edits y vectores | ❌ Sin métrica |

El refactor de Fase 5 cubre las **4 métricas in-process** (cache, builds, length, errors). Las otras dos (recall y reindex lag) requieren infra externa → Q2.

### 8.2 Práctica de evaluación continua

**Fuente**: [Crunchy Data HNSW blog (2025)](https://www.crunchydata.com/blog/hnsw-indexes-with-postgres-and-pgvector)

> "Set up alerting on recall by periodically running an exact KNN search versus your approximate HNSW search on a sample set."

Clonnect no hace esto. Sin eval baseline, no hay forma de saber si HNSW (migration 038) mantiene recall equivalente al KNN exacto — ni si el prefix está ayudando o perjudicando.

Es el mismo problema que `contextual_prefix`: sin golden dataset no hay baseline.

---

## 9. Gap analysis: Clonnect vs state-of-the-art

| Dimensión | Clonnect 2026-04 | State of art 2026 | Gap | Prioridad |
|-----------|------------------|-------------------|-----|-----------|
| Pre-chunk prefix | Determinista, per-creator | Anthropic LLM per-chunk | HIGH (expected +10-20% adicional) | Q3 2026 |
| BM25 contextual | No | Sí | HIGH (expected +10% adicional) | Q2 2026 |
| Reranking | ✅ (bge o similar) | ✅ | 0 | — |
| Eval pipeline | Ninguno | recall@k continuo | **BLOCKER** | Q2 2026 |
| Métricas in-process | Cero | Prometheus stack | MED | **Este PR** |
| Cache invalidation | Manual implícita | Hook-driven | MED | Parcial en este PR |
| Multilingual structure | ES hardcoded | Template por idioma | LOW-MED | Q2 2026 |

**Prioridad de este PR**: cubrir los gaps accionables **sin medición formal** (métricas in-process, hardcoding extraction, cache invalidation endpoint, config externalization) para dejar el sistema listo y observable cuando Q2 se construya el golden dataset.

---

## Sources

- [Contextual Retrieval in AI Systems — Anthropic (2024-09)](https://www.anthropic.com/news/contextual-retrieval)
- [Contextual retrieval with Amazon Bedrock — AWS (2024)](https://aws.amazon.com/blogs/machine-learning/contextual-retrieval-in-anthropic-using-amazon-bedrock-knowledge-bases/)
- [Anthropic's Contextual Retrieval: Guide — DataCamp](https://www.datacamp.com/tutorial/contextual-retrieval-anthropic)
- [Anthropic's Contextual Retrieval — Michael Ruminer / Medium](https://m-ruminer.medium.com/anthropics-contextual-retrieval-11dbd16841b4)
- [Late Chunking — arXiv:2409.04701v3 (Jul 2025)](https://arxiv.org/abs/2409.04701)
- [Late Chunking — Jina AI blog](https://jina.ai/news/late-chunking-in-long-context-embedding-models/)
- [jina-ai/late-chunking — GitHub](https://github.com/jina-ai/late-chunking)
- [RionDsilvaCS/contextual-retrieval-by-anthropic — GitHub](https://github.com/RionDsilvaCS/contextual-retrieval-by-anthropic)
- [Instructor — async contextual retrieval (2024-09)](https://python.useinstructor.com/blog/2024/09/26/implementing-anthropics-contextual-retrieval-with-async-processing/)
- [Beyond Chunk-Then-Embed — arXiv:2602.16974 (2026)](https://arxiv.org/html/2602.16974v1)
- [Best Embedding Models for RAG 2026 — StackAI](https://www.stackai.com/insights/best-embedding-models-for-rag-in-2026-a-comparison-guide)
- [Harrier-OSS-v1 multilingual (2026-03)](https://kiadev.net/news/2026-03-30-harrier-oss-v1-multilingual-embeddings)
- [Comprehensive Evaluation Embeddings EN/IT — MDPI (2025)](https://www.mdpi.com/2504-2289/9/5/141)
- [Contextual Chunking — Unstructured](https://unstructured.io/blog/contextual-chunking-in-unstructured-platform-boost-your-rag-retrieval-accuracy)
- [Optimizing RAG Hybrid + Reranking — Superlinked](https://superlinked.com/vectorhub/articles/optimizing-rag-with-hybrid-search-reranking)
- [Hybrid Search — Perivitta Rajendran (2026-03)](https://pr-peri.github.io/blogpost/2026/03/05/blogpost-hybrid-search.html)
- [HNSW Indexes pgvector — Crunchy Data](https://www.crunchydata.com/blog/hnsw-indexes-with-postgres-and-pgvector)
- [Production RAG with pgvector — Markaicode](https://markaicode.com/pgvector-rag-production/)
- [Document Chunking RAG Guide (2025-10) — LangCopilot](https://langcopilot.com/posts/2025-10-11-document-chunking-for-rag-practical-guide)

---

## Resumen ejecutivo Fase 4

- **Paper fundacional**: Anthropic (2024-09) propone contextual embeddings con +35% recall@20 (solo dense) y +49% (dense + BM25 contextual). Clonnect implementa solo la mitad dense y de forma determinista (no LLM per-chunk).
- **Estimación realista de ganancia capturable hoy**: **5-20% sobre baseline sin prefix**, dada la naturaleza determinista del prefix y la ausencia del leg BM25 contextual. El +49% teórico no es realmente alcanzable con la arquitectura actual.
- **Competencia técnica**: late chunking (Jina), hybrid search + reranking (consenso), modelos multilingual de nueva generación (Qwen3, BGE-M3). Todos son upgrades relevantes pero fuera del scope de este PR.
- **Validación del diseño deterministic**: papers 2026 consideran pre-chunk enrichment con metadata estructurada un "mejor ratio coste/beneficio" para dominios específicos cerrados — defendible para Clonnect.
- **Gap mayor capturable en Q2 2026**: extender el prefix al índice BM25 (fuera del archivo `contextual_prefix.py`, requiere tocar `core/rag/bm25.py`). Expected +10% adicional.
- **Blocker transversal (papers + práctica)**: sin eval pipeline recall@k continuo, ningún ajuste se puede medir. Decisión CEO: construir golden dataset Q2 2026; este PR prepara la infraestructura (métricas, flags, config).

**STOP Fase 4.** Procedo a Fase 5 (optimización — aplicar cambios al código).
