# CCEE Execution Plan — Clonnect Clone Quality Measurement
*Created: 2026-04-03 | Branch: main*

---

## Estado Actual del Sistema (Producción)

### Flags de Modelo y Contexto
| Flag | Valor |
|------|-------|
| `LLM_PRIMARY_PROVIDER` | deepinfra |
| `DEEPINFRA_MODEL` | Qwen/Qwen3-14B |
| `MAX_CONTEXT_CHARS` | 40,000 |
| `EMBEDDING_PROVIDER` | NOT SET → OpenAI (via OPENAI_API_KEY presente: sk-proj-...) |

### Flags de Sistema
| Flag | Estado Actual | Fase |
|------|-------------|------|
| `USE_COMPRESSED_DOC_D` | **ON** | Fase 3 |
| `ENABLE_STYLE_NORMALIZER` | **ON** | Fase 3 |
| `ENABLE_MEMORY_ENGINE` | **ON** | Fase 3 |
| `ENABLE_EPISODIC_MEMORY` | **ON** | Fase 3 |
| `ENABLE_RERANKING` | **ON** | Fase 3 |
| `ENABLE_RAG` | **ON** | Fase 3 |
| `ENABLE_DNA_AUTO_CREATE` | **OFF** | Fase 4 |
| `ENABLE_DNA_TRIGGERS` | **OFF** | Fase 4 |
| `ENABLE_DNA_AUTO_ANALYZE` | **NOT SET** (→ OFF) | Fase 4 |
| `ENABLE_QUESTION_REMOVAL` | **OFF** | Fase 4 |
| `ENABLE_EVALUATOR_FEEDBACK` | **NOT SET** (→ OFF) | Fase 4 |
| `ENABLE_GOLD_EXAMPLES` | **OFF** | Fase 5 |
| `ENABLE_LEARNING_RULES` | **OFF** | Fase 5 |
| `ENABLE_AUTOLEARNING` | **OFF** | Fase 5 |

---

## Datos Disponibles para Medición (Iris Bertran)

| Recurso | Cantidad | Tabla |
|---------|----------|-------|
| Mensajes de creadora (role=assistant) | 35,795 | `messages` |
| Leads únicos | 2,577 | `messages.lead_id` |
| DNA entries | 659 | `relationship_dna` |
| Gold examples | 8,352 | `gold_examples` |
| Preference pairs | 2,310 | `preference_pairs` |
| Learning rules | 1,163 | `learning_rules` |
| Lead memories | 8,035 | `lead_memories` |
| RAG chunks | 938 | `content_embeddings` |
| Evaluator feedback | **0** ⚠️ tabla vacía | `evaluator_feedback` |
| Style profiles | 2 | `style_profiles` |
| Personality docs (Doc D) | 6 | `personality_docs` |

---

## Test Set v2 Estratificado

**Archivo:** `tests/cpe_data/iris_bertran/test_set_v2_stratified.json`
**Clave JSON:** `conversations` (no `cases`)

| Métrica | Valor |
|---------|-------|
| Total conversaciones | 50 |
| **Válidas para CCEE (texto)** | **42** ← ÚNICA base para todas las mediciones |
| Excluidas (audio/sticker/imagen) | **8** ← EXCLUIDAS de TODAS las mediciones, sin excepción |

**Criterio de exclusión:** `ground_truth` contiene `[audio]`, `[sticker]` o `[image]`. Los scripts de medición DEBEN filtrar estos casos antes de calcular cualquier métrica.

### Distribución por Categoría (50 totales, incluyendo excluidos)
| Categoría | n | % sobre 50 | Incluida en CCEE |
|-----------|---|-----------|-----------------|
| casual | 30 | 60% | ✅ (mayoría) |
| short_response | 8 | 16% | ✅ (mayoría) |
| question | 3 | 6% | ✅ |
| booking | 2 | 4% | ✅ |
| emoji_reaction | 1 | 2% | ⚠️ verificar si es texto |
| greeting | 1 | 2% | ✅ |
| humor | 1 | 2% | ✅ |
| long_personal | 1 | 2% | ✅ |
| objection | 1 | 2% | ✅ |
| product_inquiry | 1 | 2% | ✅ |
| thanks | 1 | 2% | ✅ |

⚠️ **DESBALANCEO — Acción requerida antes de Fase 6:**
El test set actual tiene 60% casual. Esto sesga las métricas hacia respuestas cortas/informales.
**Antes de iniciar Fase 6 (calibración final):** regenerar test set con distribución uniforme por categoría (~5 casos por categoría × 10 categorías = 50 casos balanceados).

---

## Hoja de Ruta CCEE

### FASE 3 — SUBTRACTIVE (sistemas actualmente ON)
**Protocolo:** Partir del sistema completo actual. Desactivar UN flag a la vez. Medir delta sobre las **42 conversaciones texto**. Si el score cae → el sistema aporta → MANTENER ON.

| Orden | Sistema | Flag exacto | Valor para ablación | Hipótesis |
|-------|---------|-------------|---------------------|-----------|
| 3.1 | **RAG** | `ENABLE_RAG` | `false` | Sin RAG pierde conocimiento de contenido |
| 3.2 | **Reranking** | `ENABLE_RERANKING` | `false` (mantener `ENABLE_RAG=true`) | Sin reranking, RAG menos preciso |
| 3.3 | **Memory Engine** | `ENABLE_MEMORY_ENGINE` | `false` | Sin memoria, pierde contexto del lead |
| 3.4 | **Episodic Memory** | `ENABLE_EPISODIC_MEMORY` | `false` | Sin episodic, pierde histórico largo plazo |
| 3.5 | **Style Normalizer** | `ENABLE_STYLE_NORMALIZER` | `false` | Sin normalizer, estilo menos consistente |
| 3.6 | **Doc D comprimido** | `USE_COMPRESSED_DOC_D` | `false` | Sin Doc D, identidad degradada |

**Decisión por sistema:** `score_ON - score_OFF > +0.5pp BERTScore F1` → KEEP ON.

---

### FASE 4 — ADDITIVE (sistemas actualmente OFF)
**Protocolo:** Partir del sistema completo actual (todos los de Fase 3 en ON). Activar UN flag a la vez. Medir delta sobre las **42 conversaciones texto**. Si el score sube → KEEP ON en producción.

| Orden | Sistema | Flag exacto | Valor para activar | Dependencia | Datos disponibles |
|-------|---------|-------------|-------------------|-------------|-------------------|
| 4.1 | **DNA Auto Create** | `ENABLE_DNA_AUTO_CREATE` | `true` | — | 659 DNA entries |
| 4.2 | **DNA Triggers** | `ENABLE_DNA_TRIGGERS` | `true` | Requiere 4.1 ON | — |
| 4.3 | **DNA Auto Analyze** | `ENABLE_DNA_AUTO_ANALYZE` | `true` | Requiere 4.1+4.2 ON | — |
| 4.4 | **Question Removal** | `ENABLE_QUESTION_REMOVAL` | `true` | — | — |
| 4.5 | **Evaluator Feedback** | `ENABLE_EVALUATOR_FEEDBACK` | `true` | — | **0 registros** ⚠️ delta esperado ~0 |

**Decisión por sistema:** `score_ON - score_OFF > +0.5pp BERTScore F1` → activar en producción.
**Nota 4.5:** Medir igualmente para establecer baseline; repetir cuando `evaluator_feedback` tenga datos.

---

### FASE 5 — ADDITIVE (sistemas de aprendizaje, actualmente OFF)
**Protocolo:** Partir del resultado óptimo de Fase 4. Activar UN flag a la vez. Medir delta sobre las **42 conversaciones texto**.

| Orden | Sistema | Flag exacto | Valor para activar | Dependencia | Datos disponibles |
|-------|---------|-------------|-------------------|-------------|-------------------|
| 5.1 | **Gold Examples** | `ENABLE_GOLD_EXAMPLES` | `true` | — | 8,352 ejemplos ✅ |
| 5.2 | **Learning Rules** | `ENABLE_LEARNING_RULES` | `true` | — | 1,163 reglas ✅ |
| 5.3 | **Autolearning** | `ENABLE_AUTOLEARNING` | `true` | Requiere 5.1+5.2 ON | — |

**Decisión por sistema:** mismo umbral que Fases 3 y 4 (+0.5pp BERTScore F1).

---

## Protocolo de Medición (para cada sistema)

```
1. Configurar flag en Railway (variable de entorno)
2. Esperar restart del servicio
3. Ejecutar runner sobre las 42 conversaciones válidas del test set v2
4. Recoger métricas:
   - BERTScore F1 (métrica principal)
   - BLEU-4
   - Longitud media de respuesta (tokens)
   - % de respuestas válidas (no vacías / no errores)
5. Comparar vs configuración anterior
6. Decisión: KEEP / REVERT
7. Documentar resultado en tabla de resultados
```

---

## Resumen de Conteo de Mediciones

| Fase | Sistemas | Mediciones necesarias |
|------|----------|----------------------|
| Fase 3 | 6 (subtractive) | 7 (1 baseline + 6 ablaciones) |
| Fase 4 | 5 (additive) | 5 |
| Fase 5 | 3 (additive) | 3 |
| **Total** | **14** | **15 mediciones** |

---

## Notas Críticas

- **Tabla DNA en producción:** `relationship_dna` (no `lead_dna`)
- **Test set JSON key:** `conversations` (no `cases` ni `test_cases`)
- **EMBEDDING_PROVIDER NOT SET** → usa OpenAI por defecto (OPENAI_API_KEY presente y funcionando)
- **Evaluator feedback vacío** → medir de todas formas para tener baseline, delta esperado = 0
- **Desbalanceo test set** → 60% casual, no bloquea pero flag para regeneración futura
- **Riesgo ablaciones:** cambiar flags en Railway afecta producción real. Coordinar mediciones en horario de bajo tráfico o usar ambiente de staging.
- **Orden dentro de Fase 4:** DNA Auto Create → DNA Triggers → DNA Auto Analyze son secuenciales (cada uno requiere el anterior). Question Removal y Evaluator Feedback son independientes.
