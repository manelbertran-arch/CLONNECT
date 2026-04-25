# Auditoría Forense del Dataset — SFT Iris
**Fecha:** 2026-04-25  
**Dataset:** `data/dpo/trl/sft_combined_audited.jsonl`  
**Rama:** feat/sft-postmortem-analysis

---

## 2.1 Auditoría Estructural

| Métrica | Valor | Severity |
|---|---|---|
| Total samples | 9.272 | — |
| Formato `messages` | 9.272 (100%) | — |
| Formato `conversations` | 0 (0%) | — |
| **Single-turn** | **9.272 (100%)** | 🔴 HIGH |
| Multi-turn | 0 (0%) | 🔴 HIGH |
| **Con system prompt** | **4.266 (46%)** | 🟡 MEDIUM |
| Sin system prompt | 5.006 (54%) | — |
| Empty content turns | 0 | ✅ |
| Role errors | 0 | ✅ |

### Distribución por fuente y system prompt

| Fuente | Samples | Con system prompt | Contenido del system prompt |
|---|---|---|---|
| **Instagram** | 4.266 | **4.266 (100%)** | 510 chars — "⚠️ REGLAS CRITICAS — APLICA SIEMPRE: 1. IDIOMA..." |
| **WhatsApp** | 5.006 | **0 (0%)** | Sin system prompt |

**Finding crítico:** El dataset está heterogéneamente dividido. Las muestras de Instagram incluyen un system prompt corto con reglas de idioma y comportamiento, mientras que las de WhatsApp no tienen system prompt. Esto crea dos distribuciones de entrada distintas durante el training:
- 46% del training: `[system_510chars] + [user] → [assistant]`
- 54% del training: `[user] → [assistant]`

Ninguna de estas distribuciones coincide con el formato de producción: `[system_~8093tokens] + [history] + [user] → [assistant]`.

### System prompt de Instagram (snippet)

```
⚠️ REGLAS CRITICAS — APLICA SIEMPRE:
1. IDIOMA: Responde SIEMPRE en el idioma del lead. Si escribe español → español. 
   Si catalán → catalán. Si mezcla → mezcla. NUNCA respondas en catalán a un 
   mensaje en español.
2. PROHIBIDO: "Que et porta per aquí?"
[... ~510 chars total]
```

Este system prompt es un prototipo antiguo del pipeline — NO contiene Doc D, ni persona description, ni few-shots. Está desactualizado respecto al pipeline de producción.

---

## 2.2 Distribución de Longitudes

### Respuestas (assistant turn, chars)

| Percentil | Chars |
|---|---|
| P5 | 8 |
| P25 | 22 |
| P50 (mediana) | 47 |
| P75 | 95 |
| P95 | 250 |
| P99 | 423 |
| Media | 75.7 |
| Std | 82.8 |
| Máximo | 500 |
| Mínimo | 3 |

La distribución es altamente asimétrica (media 75 >> mediana 47). El P75 = 95 chars significa que el 75% de las respuestas son mensajes muy cortos, coherente con el estilo DM de Iris.

**Implicación para el training:** El modelo aprendió que las respuestas "correctas" son cortas (mediana 47 chars). Esto explica el win en A1 length matching (+80.4 en naked mode) y el J3 prompt-to-line (+61). El model aprendió la longitud de Iris sin necesitar el system prompt.

---

## 2.3 Categorización de Contenido (200 muestras, seed=42)

| Categoría | Count | % | Descripción |
|---|---|---|---|
| other | 119 | 59% | Conversación informal no categorizable |
| question | 52 | 26% | Contiene `?` (Iris pregunta o responde pregunta) |
| plan_action | 15 | 7% | Planes, horarios, acciones futuras |
| persona_fact | 9 | 4% | Iris menciona fact sobre sí misma |
| reaction_pos | 3 | 1% | Reacción positiva explícita |
| emotional | 2 | 1% | Expresión emocional directa |

**Observación:** El 59% "other" es conversación informal típica de DM (reacciones, comentarios, respuestas sociales). La categoría dominante `question` refleja que Iris hace muchas preguntas en sus respuestas (coherente con su estilo extrovertido).

---

## 2.4 Auditoría de Calidad Crítica

| Issue | Count | % | Severity |
|---|---|---|---|
| **Error string "Lo siento, hubo un error"** | **22** | **0.24%** | 🔴 HIGH |
| Respuestas ≤5 chars | 253 | 2.7% | 🟡 MEDIUM |
| Respuestas <10 chars | 719 | 7.8% | 🟡 MEDIUM |
| Media/sticker en respuesta | 441 | 4.8% | 🟡 MEDIUM |
| Solo sticker (`[🏷️ Sticker]`) | ~100 | ~1% | 🟡 MEDIUM |

### Error string contamination (CRÍTICO)

**22 muestras contienen el fallback de error del pipeline como respuesta de training.** El modelo aprendió que `"Lo siento, hubo un error procesando tu mensaje. Por favor intenta de nuevo."` es una respuesta válida de Iris. Ejemplos:

```
user: "nena et volia dir t'agrada aixo per gravar"
resp: "Lo siento, hubo un error procesando tu mensaje. Por favor intenta de nuevo."

user: "OMG Es paran tots al segon 3 o aixiii O solo a mi?"  
resp: "Lo siento, hubo un error procesando tu mensaje. Por favor intenta de nuevo. Rein..."
```

Esto ocurre en el dataset de WhatsApp, donde el pipeline de producción generó errores en lugar de respuestas reales y las conversaciones fueron incluidas en el dataset de training sin filtrado.

### Respuestas ultra-cortas (muestras)

```
"Oka", "Fet❤️", "13:40", "Voy", "Mati", "Sii", "Okaaa", "Vaaaa", "Como?", "Siii"
```

Estas respuestas son válidas en el contexto de DM pero contribuyen a la varianza alta de longitud y reducen la signal de calidad del dataset.

### Duplicados exactos

| Respuesta | Ocurrencias |
|---|---|
| `[🏷️ Sticker] [🏷️ Sticker]` | 63 |
| `[🏷️ Sticker]` | 32 |
| `Oka` | 17 |
| `Lo siento, hubo un error...` | 15 |
| `[video]` | 15 |
| `[📷 Photo]` | 10 |

**Total duplicados exactos:** 1.352 samples (14.6% del dataset).

El 14.6% de samples son respuestas exactamente iguales. Esto no es intrínsecamente malo (Iris dice "Oka" muchas veces) pero infla la distribución de responses cortas y genera over-representation de ciertos patrones.

---

## 2.5 Diversidad del Dataset

Calculado sobre 1.000 muestras aleatorias (seed=42):

| Métrica | Valor | Benchmark chat (referencia) | Interpretación |
|---|---|---|---|
| Distinct-1 | 0.191 | 0.20-0.35 típico | Bajo pero aceptable para DM |
| Distinct-2 | 0.668 | 0.60-0.85 típico | Razonable |
| Duplicados exactos | 14.6% | <5% best practice | 🔴 Alto |

**Top-20 unigrams más frecuentes:**
`que(563), a(496), no(421), la(327), de(254), si(250), el(245), i(204), ja(155), es(145), tu(140), me(128), les(122), ho(114), te(110), amb(106), et(103), y(102), ok(101), va(98)`

La presencia dominante de `ja` (catalán para "ya") y tokens bilíngües (cat/es) confirma la naturaleza multilingüe del dataset. El Distinct-1 bajo (0.191) es esperado para conversaciones DM cortas — no indica falta de diversidad temática, sino vocabulario limitado por naturaleza del dominio.

---

## 2.6 Cobertura de Q&A Persona

| Métrica | Valor | Severity |
|---|---|---|
| User hace pregunta sobre Iris | 164 (1.8%) | 🔴 HIGH |
| Respuesta contiene fact de persona | 10 (0.1%) | 🔴 HIGH |

**Solo 10 de 9.272 ejemplos (0.1%) contienen una respuesta de Iris con un hecho factual sobre su persona.**

Esta es la causa raíz más directa del problema J6. El modelo nunca aprendió a responder preguntas sobre sí mismo de forma consistente porque prácticamente no hay datos de entrenamiento que muestren cómo Iris responde a esas preguntas.

**¿Qué necesitaría para J6 ≥ 80 en pipeline?**  
Estimación basada en LIMA (Zhou 2023) y literatura de persona modeling: mínimo 200-500 ejemplos Q&A persona-consistentes con la misma respuesta a preguntas equivalentes (como seed para aprender la invarianza).

---

## 2.7 Contaminación y Leakage

### Contaminación dataset-evaluation (CRÍTICO)

No se ha hecho cross-check programático entre los 9.272 samples de training y los test cases CCEE. Sin embargo, dado que los test cases se generan con `SELECT ... ORDER BY RANDOM()` sobre las mismas conversaciones de producción, existe riesgo de overlap.

**Acción necesaria:** Implementar deduplicación exacta y semántica entre train set y eval test cases antes del próximo sprint.

### Artefactos de scraping

Los samples contienen artefactos de mensajes de la app de mensajería:
- `[🏷️ Sticker]` — Iris mandó un sticker (no texto recuperable)
- `[video]`, `[📷 Photo]` — medios no recuperables
- `[🎤 Audio]: ...` — transcripción de audio (variable calidad)
- `[contact]` — contacto compartido (no textual)

441 de 9.272 samples (4.8%) contienen alguno de estos artefactos en la respuesta. El modelo aprendió a emitir `[🏷️ Sticker]` y `[📷 Photo]` como respuestas válidas (visible en CCEE: `Bot: [🏷️ Sticker] [🏷️ Sticker]`).

---

## Resumen de Issues

| ID | Issue | Severity | Impacto estimado |
|---|---|---|---|
| D-01 | **0% multi-turn samples** | 🔴 HIGH | J5, J6, K1 en pipeline |
| D-02 | **22 error-string samples** | 🔴 HIGH | Potencial regresión safety + calidad |
| D-03 | **0.1% persona Q&A responses** | 🔴 HIGH | J6 cross_session = 0 con pipeline |
| D-04 | **Heterogeneous system prompts** (46% corto vs 54% ninguno) | 🔴 HIGH | Distribution shift serving |
| D-05 | **1.352 duplicados exactos (14.6%)** | 🟡 MEDIUM | Over-representation de patterns cortos |
| D-06 | **441 media/sticker responses** | 🟡 MEDIUM | Modelo aprende artefactos |
| D-07 | **Sin validation split** | 🟡 MEDIUM | No hay signal de overfitting |
| D-08 | **Sin dedup train↔eval** | 🟡 MEDIUM | Riesgo de contaminación |
| D-09 | **System prompt training ≠ production** | 🔴 HIGH | Distribution shift J6, H1 |
