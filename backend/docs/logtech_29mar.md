# Logtech — Sesión 29 marzo 2026

**Fecha**: 2026-03-29 → 2026-03-30 00:30h
**Proyecto**: Clonnect Backend
**Branch**: `main`
**Commits**: 15 (f561819c → 6d15458a)
**Archivos nuevos**: 2,515 líneas en 7 módulos nuevos
**Archivos modificados**: 55 files changed, +20,005 lines

---

## 1. Resumen ejecutivo

Sesión dedicada a construir el **Clone Persona Evaluation (CPE)** framework completo y usarlo para recalibrar el sistema de generación. Resultado: la calidad de match cuantitativo de Iris pasó de **0.25 a 0.75** (3x mejora) mediante compresión del Doc D de 38K→1.3K caracteres y style normalization post-proceso.

Hallazgo clave: **el Doc D de 38K caracteres era el principal degradador de calidad** — el LLM ignoraba las instrucciones cuantitativas enterradas en texto largo. Un Doc D comprimido de 1.3K chars con métricas explícitas triplica el match score.

Se evaluaron 12 configuraciones distintas en un barrido sistemático. Few-shot examples resultaron neutros o negativos. Memory + RAG no mejoraron métricas cuantitativas. El estilo se controla mejor con Doc D comprimido + style normalizer post-proceso.

---

## 2. Tabla de configuraciones evaluadas

| Config | Descripción | Match | Emoji | Excl | Len (med) | Notas |
|--------|-------------|-------|-------|------|-----------|-------|
| **Target** | Iris real (baseline) | — | 22.6% | 2% | 68c | Ground truth |
| Config 1 | Qwen3-14B naked (sin Doc D) | 0.25 | ~96% | ~60% | ~120c | Chatbot genérico |
| Config 2 | + Doc D original (38K chars) | 0.25 | ~90% | ~55% | ~110c | Doc D ignorado |
| Config 2b | + Doc D comprimido (1.3K) | **0.75** | ~28% | ~8% | ~66c | **Breakthrough** |
| Config 2c | + frequency_penalty=0.5 | 0.75 | ~30% | ~10% | ~64c | Marginal |
| Config 3 | + few-shot (5 examples, plain) | 0.75 | ~32% | ~12% | ~70c | Neutro |
| Config 3b | + few-shot (multi-turn msgs[]) | 0.67 | ~35% | ~15% | ~72c | **Peor** (↓0.08) |
| Config 3c | Hybrid (3b + normalizer) | 0.67 | ~30% | ~10% | ~68c | Post-proc over-corrects |
| Config 4 | + strong Doc D | 0.75 | ~25% | ~6% | ~64c | Marginal mejora |
| Config 5 | + Doc D + normalizer | **0.75** | ~28% | ~8% | ~66c | Best combo |
| Config 5b | + normalizer keep_first | 0.71 | ~35% | ~8% | ~66c | Regresión keep_first |
| Config 5/RAG | + memory + RAG | 0.75 | ~30% | ~10% | ~68c | Neutro en L1 |
| Pipeline (Gemini) | Full pipeline Railway | 0.42 | — | — | — | DB read-only issue |
| Pipeline (DeepInfra) | Full pipeline Qwen3-14B | 0.33 | — | — | — | Worse than Gemini |

**Doc D Length Sweep** (50 casos × 4 variantes):

| Variante | Chars | Match | Emoji | Excl |
|----------|-------|-------|-------|------|
| A_500 | 500 | 0.29 | — | — |
| **B_1300** | 1,300 | **0.57** | 64% | 46% |
| C_2500 | 2,500 | 0.57 | 94% | 62% |
| D_5000 | 5,000 | 0.57 | 94% | 62% |

**Conclusión sweep**: B_1300 es óptimo. Más texto diluye las instrucciones cuantitativas → peor control de emoji/exclamaciones. No cambiar `build_compressed_doc_d()`.

---

## 3. CPE Framework — lo que se construyó

### 3.1 Fundamentos (23 papers)

El framework CPE se diseñó basándose en literatura de evaluación de personas conversacionales:

- **CharacterEval** (Tu et al., 2024) — 5 dimensiones de evaluación de personajes
- **PersonaGym** (Samuel et al., 2024) — benchmark de personas con métricas cuantitativas
- **Prometheus 2** (Kim et al., 2024) — formato ABSOLUTE_PROMPT con rubrics y reference answers
- **"A sentence is worth a thousand parameters"** — evidencia de que instrucciones cortas superan a documentos largos
- Papers sobre few-shot formatting, BFI personality modeling, style transfer evaluation

### 3.2 Niveles implementados

| Nivel | Qué mide | Costo | Estado |
|-------|----------|-------|--------|
| **Level 0** | Test set generation | $0 | ✅ Universal, auto-extrae de DB |
| **Level 1** | Métricas cuantitativas (emoji, longitud, vocab, excl, preguntas) | $0 | ✅ 50+ test cases, `--skip-pipeline` |
| **Level 2** | LLM-as-Judge multidimensional (5 dims, 1-5 scale) | ~$0.05/run | ✅ GPT-4o-mini + Prometheus rubrics |
| **Level 3** | A/B human eval | — | Pendiente |
| **Level 4** | Production metrics (engagement, response rate) | — | Pendiente |

### 3.3 Level 2 — Scores actuales (GPT-4o-mini judge)

| Dimensión | OpenAI format | Prometheus format |
|-----------|--------------|-------------------|
| Conversational Ability | 3.60 | 3.33 |
| Persona Fidelity | 3.00 | 2.67 |
| Knowledge Accuracy | 3.60 | 4.00 |
| Emotional Intelligence | 2.80 | 3.33 |
| Engagement | 3.20 | 3.33 |
| **Overall** | **3.24** (σ=0.64) | **3.33** (σ=0.42) |

Prometheus format produce scores más consistentes (σ menor) y ligeramente más altos. Persona Fidelity es la dimensión más débil — coherente con que el estilo cuantitativo aún no está al 100%.

### 3.4 Archivos creados

| Archivo | Líneas | Propósito |
|---------|--------|-----------|
| `tests/cpe_level1_quantitative.py` | 465 | Level 1: métricas cuantitativas sin LLM |
| `tests/cpe_level2_llm_judge.py` | 566 | Level 2: evaluación multidimensional con LLM judge |
| `core/dm/compressed_doc_d.py` | 245 | Builder de Doc D comprimido (38K→1.3K) |
| `core/dm/style_normalizer.py` | 135 | Post-proceso: normaliza emoji rate a target |
| `core/dm/text_utils.py` | 487 | Utilidades de texto para métricas |
| `services/creator_profile_service.py` | 153 | CRUD perfiles creador en DB |
| `services/creator_auto_provisioner.py` | 464 | Auto-provisioning en primer mensaje |

---

## 4. Descubrimientos críticos

### 4.1 Doc D de 38K caracteres era el problema principal

El personality document original (`personality_docs/iris_bertran.md`) tenía 38K caracteres. Incluía transcripciones de posts, análisis detallados, ejemplos extensos. El LLM simplemente **ignoraba las instrucciones cuantitativas** (emoji rate, longitud) enterradas en tanto texto.

**Evidencia**: Config 1 (sin Doc D) y Config 2 (con Doc D 38K) producían el **mismo score de 0.25**. El documento no añadía nada.

**Fix**: `compressed_doc_d.py` genera un Doc D de ~1.3K chars con:
- Personalidad BFI en 1 línea
- Métricas cuantitativas explícitas (mediana, percentiles, rates)
- Top emojis y palabras frecuentes
- Anti-patterns explícitos ("NUNCA respondas como asistente")

Score: 0.25 → 0.75 (3x mejora).

### 4.2 Few-shot examples son neutros o negativos

Contra la intuición (y contra algunos papers), los few-shot examples no mejoraron métricas cuantitativas:

- **Plain text** (5 examples seleccionados por intent): 0.75 (neutro)
- **Multi-turn messages[]** (formato paper): 0.67 (peor, ↓0.08)
- **Hybrid** (multi-turn + normalizer): 0.67 (normalizer no compensa)

**Hipótesis**: El Doc D comprimido ya captura el estilo cuantitativo. Los few-shot examples añaden ruido porque los ejemplos individuales no representan el *promedio* estadístico — pueden tener más emojis o ser más largos que la mediana.

### 4.3 Style normalizer funciona pero con límites

El `style_normalizer.py` reduce emoji rate de 96% → ~28% (target 22.6%). Funciona como post-proceso probabilístico: calcula `keep_prob = target_rate / model_rate` y stripea emojis con esa probabilidad.

- `keep_first=True` causó regresión (0.71 vs 0.75) — revertido
- Exclamation normalization planificada pero no implementada (regex fallaba)
- Integrado en producción vía `postprocessing.py`

### 4.4 Memory + RAG neutros en Level 1

Config 5 (memory + RAG) produce el mismo 0.75 que Config 2b (solo Doc D comprimido) en métricas cuantitativas. Esto es esperado: memory y RAG mejoran *contenido* (relevancia, conocimiento), no *estilo* (longitud, emoji). Se espera mejora visible en Level 2 (Knowledge Accuracy dimension).

### 4.5 Stefano no calibrado = 0.25

Al generar test set para `stefano_bonanno`, el score fue 0.25 — idéntico al Iris pre-calibración. Confirma que la calibración (Doc D comprimido + baseline metrics) es el factor determinante, no el modelo base.

### 4.6 Pipeline completo underperforms vs isolated

- Pipeline Gemini: 0.42 match (vs 0.75 isolated)
- Pipeline DeepInfra/Qwen: 0.33 match (vs 0.75 isolated)

Gap causado por: conversation state prompts (añaden preguntas), strategy hints (desalineados con contexto), DB read-only transaction issues. El pipeline inyecta instrucciones que compiten con el Doc D comprimido.

---

## 5. Estado de sistemas (52+ componentes)

### Nuevos sistemas añadidos esta sesión

| # | Sistema | Archivo | Estado |
|---|---------|---------|--------|
| 50 | CPE Level 1 — Quantitative | `tests/cpe_level1_quantitative.py` | ✅ ACTIVO |
| 51 | CPE Level 2 — LLM Judge | `tests/cpe_level2_llm_judge.py` | ✅ ACTIVO |
| 52 | Compressed Doc D Builder | `core/dm/compressed_doc_d.py` | ✅ ACTIVO |
| 53 | Style Normalizer | `core/dm/style_normalizer.py` | ✅ PRODUCCIÓN |
| 54 | Creator Profile Service | `services/creator_profile_service.py` | ✅ ACTIVO |
| 55 | Auto-Provisioner | `services/creator_auto_provisioner.py` | ✅ COMMIT (pendiente integración) |
| 56 | Text Utils (métricas) | `core/dm/text_utils.py` | ✅ ACTIVO |

### Feature flags actualizados

| Flag | Estado | Cambio |
|------|--------|--------|
| `ENABLE_STYLE_NORMALIZER` | `true` | **NUEVO** — post-proceso emoji normalization |
| `ENABLE_COMPRESSED_DOC_D` | `true` | **NUEVO** — usa Doc D 1.3K en vez de 38K |
| `STYLE_NORM_MODEL_EMOJI_RATE` | `0.55` | **NUEVO** — model baseline para normalización |

### DB migrations

| Migration | Descripción |
|-----------|-------------|
| 042 | `creator_profiles` table — almacena baseline metrics, BFI, Doc D comprimido por creador |

---

## 6. Gaps y problemas pendientes

### Críticos
1. **Pipeline gap**: 0.75 isolated → 0.42 pipeline. Conversation state y strategy prompts degradan el Doc D comprimido. Necesita: reducir/eliminar question injection en estados avanzados.
2. **Stefano sin calibrar**: Score 0.25. Necesita: extraer baseline metrics de sus datos reales y generar Doc D comprimido.
3. **Auto-provisioning no integrado**: `creator_auto_provisioner.py` existe pero no está conectado al flujo de primer mensaje.

### Importantes
4. **Level 2 scores bajos**: 3.24-3.33/5.0. Persona Fidelity (2.67-3.00) y Emotional Intelligence (2.80-3.33) son las más débiles.
5. **Exclamation normalizer no funciona**: Regex fallaba silently. Solo emoji normalization activa.
6. **real_011 sigue siendo peor caso**: Contexto empático recibe respuesta con "entusiasmo/curiosidad" por strategy hint RECURRENTE.

### Nice-to-have
7. **Few-shot selection**: Probar selección por embedding similarity en vez de intent matching.
8. **Level 3/4**: Human eval y production metrics aún no implementados.
9. **Prometheus model**: GPT-4o-mini como judge es subóptimo; Prometheus 2 no disponible en DeepInfra.

---

## 7. Commits de la sesión (cronológico)

```
f561819c fix(dm): RECURRENTE strategy + pool product guard removal
de7c319a bisect: disable 3 regression suspects
01e5b117 feat: universal CPE test set generator
7976252f feat: CPE baseline + BFI profile generators
356578a8 fix: universalize CPE rubrics
5aa5edaa feat: CPE Level 1 — quantitative style comparison
e42192db feat: compressed Doc D builder — 37K→1K chars, match 0.25→0.75
837c2679 feat: add frequency_penalty param to DeepInfra provider
1ccc68ca eval: Config 3 few-shot multi-turn — match 0.67
e9f824b9 CPE recalibration: style normalizer + strengthened Doc D
8a300c0b fix(style_normalizer): strip !!/!!! runs — regex failing
d6b1be67 feat: data-driven length hints
f77e177e feat: CPE Level 2 — LLM-as-Judge with Prometheus 2
53007638 feat: migrate CPE profiles from local JSON to DB
a21d8487 feat: add Prometheus 2 rubric backend to CPE Level 2
6d15458a feat: auto-provisioning of creator profiles on first message
```

---

## 8. Próximos pasos (prioridad)

1. **Cerrar pipeline gap** — Reducir question injection de conversation state para leads con `history_len > 4`. Objective: subir pipeline match de 0.42 → 0.65+.
2. **Calibrar Stefano** — Ejecutar CPE Level 0+1 para `stefano_bonanno`, generar Doc D comprimido, verificar mejora.
3. **Integrar auto-provisioner** — Conectar `creator_auto_provisioner.py` al webhook de primer mensaje.
4. **Fix exclamation normalizer** — Implementar regex correcto para `!!/!!!` stripping.
5. **Evaluar con Level 2 post-calibración** — Re-run Level 2 judge tras cerrar pipeline gap para medir mejora en Persona Fidelity.

---

## 9. Métricas clave

| Métrica | Antes (28-mar) | Después (29-mar) | Target |
|---------|----------------|-------------------|--------|
| Match score (isolated) | 0.25 | **0.75** | >0.80 |
| Match score (pipeline) | — | 0.42 | >0.70 |
| Emoji rate (bot) | ~96% | ~28% | 22.6% |
| Length median (bot) | ~120c | ~66c | 68c |
| Exclamation rate (bot) | ~60% | ~8% | 2% |
| Level 2 overall | — | 3.24/5.0 | >4.0 |
| Sistemas totales | 49 | **56** | — |
| Doc D size | 38K chars | 1.3K chars | — |

---

*Generado: 2026-03-30 10:30h*
*Sesión: ~8h de trabajo continuo*
*Modelo principal: Qwen3-14B (DeepInfra) para generación, GPT-4o-mini para evaluación*
