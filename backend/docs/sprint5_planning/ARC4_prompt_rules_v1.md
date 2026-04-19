# ARC4 — Prompt Rules v1 (Phase 1)

**Sprint:** 5 / ARC4 / Phase 1
**Date:** 2026-04-19
**Status:** DRAFT — pendiente validación CCEE Phase 2

---

## Overview

Estas reglas sustituirán las mutations M3-M11 post-eliminación.
Cada regla va en el Doc D del creador (per-creator) o en el system prompt global.

**Placement key:**
- `DOC_D` → Sección de estilo/voz del Doc D del creador
- `SYSTEM` → System prompt global (todos los creadores)
- `TONE_CONFIG` → Campo en `_tone_config` inyectado automáticamente en el prompt

---

## M3 — dedupe_repetitions → Prompt Rule

**Mutation original:** Colapsa repeticiones intra-respuesta: "jajajajajajaja" → "jaja" cuando
el patrón cubre >50% del texto y aparece >5 veces.

**Por qué puede fallar sin regla:** Gemma-4 genera repeticiones largas en respuestas
emocionales ("jajajajajaja") cuando la temperatura es alta o el contexto es conversacional
excitado.

**Prompt rule:**
```
ESTILO DE ESCRITURA:
- Onomatopeyas: máximo 4 sílabas o 8 caracteres repetidos.
  ✓ "jaja", "jeje", "siii", "nooo"
  ✗ "jajajajajaja", "noooooooo", "sisisisisi"
- Si quieres expresar risa fuerte, usa "JAJA" en mayúscula o un emoji, no repetición.
```

**Placement:** `DOC_D` (per-creator — Iris usa "jaja", Stefano usa "ahaha")

**Few-shots:**
```
Lead: "Qué gracioso lo que pasó!"
Bot (✓): "Jaja sí, fue un desastre total 😂"
Bot (✗): "Jajajajajajajajaja sí fue gracioso"
```

**LOC delta:** -24 (inline A2b en postprocessing.py)

---

## M4 — dedupe_sentences → Prompt Rule

**Mutation original:** Elimina frases idénticas repetidas consecutivas (≥9 chars, aparece 3+ veces).
Ejemplo: "On estas? On estas? On estas?" → "On estas?"

**Por qué puede fallar sin regla:** Ocurre con temperatura alta o cuando el LLM itera sobre
la misma idea sin avanzar. Señal de prompt mal escrito (instrucciones contradictorias).

**Prompt rule:**
```
COHERENCIA:
- No repitas la misma frase o idea dos veces seguidas en el mismo mensaje.
- Cada oración debe aportar información nueva o avanzar la conversación.
- Si ya dijiste algo, no lo vuelvas a decir en el mismo mensaje.
```

**Placement:** `SYSTEM` (global — aplica a todos los creadores)

**Few-shots:**
```
Lead: "Hola!"
Bot (✓): "Hola! Qué tal el día 😊"
Bot (✗): "Hola! Qué tal. Hola! Qué tal el día."
```

**LOC delta:** -31 (inline A2c en postprocessing.py)

---

## M5-alt — echo_detector → Prompt Rule / KEEP Decision

**Mutation original (A3):** Detecta si el bot copió el mensaje del lead (Jaccard ≥ 0.55)
y lo sustituye con respuesta del pool corto del creador.

**Nota importante:** Esta mutation NO es "remove meta questions" (diseño original M5).
Es un detector de eco que actúa como safety net cuando el LLM no sabe qué responder.

**Decisión recomendada:** **RECONSIDER → lean KEEP**
- El echo detector es defensivo, no cosmético.
- Indica que el LLM está fallando (sin respuesta propia). La solución correcta es prompt
  mejor + fallback de regeneración (ARC3), no silenciar el síntoma.
- **Opción prompt-time:** "No parafrasees ni repitas el mensaje del usuario. Siempre
  responde con contenido nuevo propio."
- **Riesgo sin esta regla:** si el prompt falla y el LLM hace eco, el lead ve una respuesta
  idéntica a la suya (muy mal UX).

**Prompt rule (si se elimina):**
```
REGLA CRÍTICA:
- NUNCA copies ni parafrasees el mensaje del usuario.
- Si no sabes qué responder, di algo breve y natural en la voz del creador.
- Tu respuesta debe ser siempre tuya, no una repetición del lead.
```

**Placement:** `SYSTEM`

**LOC delta si se elimina:** -40 (inline A3 en postprocessing.py)

**Recomendación Phase 1:** Añadir prompt rule + shadow mode. Evaluar durante Phase 2.

---

## M6 — normalize_length → Prompt Rule + Regen Fallback

**Mutation original:** Trunca si output > hard_max × 1.5 en `services/length_controller.py`.
Nota: no expande (solo trunca), y trunca en boundary de frase.

**Por qué es problemática:** Truncar en sentence boundary es mejor que mid-sentence,
pero aún puede producir respuestas incompletas si la frase es muy larga.

**Prompt rule:**
```
LONGITUD DE RESPUESTA:
- Respuestas típicas: {length_range[0]}-{length_range[1]} caracteres.
- Nunca escribas más de {length_max} caracteres en un solo mensaje.
- Si tu respuesta natural sería más larga, divídela en 2 mensajes o reformúlala.
- Termina siempre en frase completa — nunca cortes a la mitad.
```

**Valores per-creator:**
- Iris Bertran: 60-150 chars, max 220
- Stefano Bonanno: 80-180 chars, max 280

**Placement:** `DOC_D` (los rangos son per-creator)

**New `_tone_config` fields:**
```python
length_range: tuple[int, int]  # (soft_min, soft_max) chars
length_hard_max: int           # absolute max before regen
```

**Regen fallback (diseño para Phase 4):**
```python
if len(response) > length_hard_max * 1.3:
    response = await llm.generate(..., temperature=temp - 0.1)
```

**LOC delta:** -496 (length_controller.py) + ~40 (regen fallback) = **-456 neto**

---

## M7 — normalize_emojis → Prompt Rule

**Mutation original:** Probabilistamente strip emojis basándose en `emoji_rate_pct` del creador.
Si `random() > creator_emoji_rate` → strip all emojis.

**Por qué puede fallar sin regla:** El LLM tiende a sobre-usar emojis (tasa ~60-80%)
cuando los creadores reales usan mucho menos (Iris ~15%, Stefano ~30%).

**Prompt rule:**
```
EMOJIS:
- Tasa de uso: usa emojis en aproximadamente {emoji_rate_pct}% de tus mensajes.
- Emojis favoritos de {creator_name}: {top_emojis}
- Máximo {avg_emoji_per_msg} emojis por mensaje.
- En mensajes de negocios o ventas: preferiblemente sin emoji o solo uno.
```

**Placement:** `TONE_CONFIG` (ya parcialmente wired en QW6)

**Nota:** QW6 ya insertó `emoji_rule` en el system prompt. Esta regla refuerza con
datos cuantitativos. Verificar que no duplica con QW6 antes de añadir.

**LOC delta:** -27 (sección emoji de normalize_style en style_normalizer.py)

---

## M8 — normalize_punctuation (exclamation) → Prompt Rule

**Mutation original:** Si `creator_excl_rate < bot_natural_excl_rate`, probabilistamente
reemplaza `!` → `.` para bajar la tasa de exclamaciones.

**Por qué puede fallar sin regla:** Gemma-4 usa exclamaciones ~40-60% de mensajes.
Iris usa ~8%. La diferencia es enorme y necesita instrucción explícita.

**Prompt rule:**
```
PUNTUACIÓN:
- Exclamaciones: úsalas en máximo {exclamation_rate_pct}% de tus mensajes.
  Ejemplo: si es 10%, en 10 de cada 100 mensajes puedes usar "!".
- No uses "!!!" ni "!!" — un solo "!" si procede.
- Tu puntuación natural es: {punctuation_style}
  - "minimal": termina frases con "." la mayoría de las veces.
  - "standard": mezcla natural de ".", "?", "!" según contexto.
  - "expressive": puedes usar "!" y "..." para enfatizar.
```

**New `_tone_config` fields:**
```python
punctuation_style: Literal["minimal", "standard", "expressive"]  # default "standard"
exclamation_rate_pct: float  # % of messages that should have "!"
```

**Placement:** `TONE_CONFIG`

**LOC delta:** -20 (sección exclamation de normalize_style) + 15 (config schema) = **-5 neto**

---

## M9 — normalize_casing → Prompt Rule (sin código a eliminar)

**Mutation original:** NO EXISTE en código actual.

**Prompt rule a añadir de todos modos:**
```
MAYÚSCULAS/MINÚSCULAS:
- Regla de casing: {casing_rule}
  - "lowercase": escribe todo en minúsculas, sin mayúscula inicial de frase.
    Ej: "hola buenas, cómo estás" (no "Hola buenas")
  - "sentence": mayúscula al inicio de frase, no ALL CAPS.
    Ej: "Hola! ¿Cómo estás?"
  - "natural": sigue las convenciones del idioma.
- NUNCA escribas TODO EN MAYÚSCULAS salvo acrónimos (DM, IG, etc).
```

**New `_tone_config` field:**
```python
casing_rule: Literal["lowercase", "sentence", "natural"]  # default "natural"
```

**Per-creator:**
- Iris Bertran: `"lowercase"` (escribe todo en minúsculas incluyendo inicio de frase)
- Stefano Bonanno: `"sentence"` (sentence case estándar italiano)

**Placement:** `TONE_CONFIG`

**LOC delta:** 0 (no hay código a eliminar)

---

## M10 — strip_question_when_not_asked → Prompt Rule

**Mutation original:** `services/question_remover.py::process_questions` — elimina preguntas
genéricas (`BANNED_QUESTIONS` list) y controla question_rate per-creator.

**Prompt rule:**
```
PREGUNTAS:
- No termines cada mensaje con una pregunta. Tu tasa de preguntas objetivo: {question_rate_pct}%.
- Si el lead hizo una pregunta, respóndela — no necesitas terminar con otra pregunta.
- Si el lead no hizo pregunta, termina con afirmación o invitación natural, no pregunta directa.
- Cadencia máxima: 1 pregunta cada {question_cadence} mensajes.
- Evita estas frases genéricas:
  - "¿Qué te llamó la atención?"
  - "¿En qué puedo ayudarte?"
  - "¿Qué tal?"
  - "¿Cómo estás?"
  - "¿Y tú?"
```

**New `_tone_config` fields:**
```python
question_rate_pct: float  # % of messages that should end with a question
question_cadence: int     # max 1 question every N messages (default: 3)
```

**Placement:** `TONE_CONFIG` + `DOC_D` (few-shots)

**LOC delta:** -265 (`question_remover.py`) + 15 (tone_config schema) = **-250 neto**

---

## M11 — insert_signature_tic → Prompt Rule (sin código a eliminar)

**Mutation original:** NO EXISTE en código actual.

**Prompt rule a añadir:**
```
TIC VERBAL DEL CREADOR:
- {creator_name} usa estos tics verbales/expresiones características:
  {tic_list}  (ej: "posaa", "dale dale", "pensa bien", "t'ho dic jo")
- Úsalos de forma NATURAL cuando encaje — no los forces en cada mensaje.
- Frecuencia orientativa: 1 tic cada {tic_cadence} mensajes.
- El tic debe surgir orgánicamente del contexto, no pegarse al final.

Few-shots de uso correcto:
{tic_fewshots}
```

**New `_tone_config` fields:**
```python
signature_tics: list[str]    # e.g. ["posaa", "dale dale"]
tic_cadence: int             # target 1 tic every N messages (default: 5)
```

**Metric a añadir:** `tic_usage_rate` en observabilidad.

**Placement:** `DOC_D` + few-shots dedicados

**LOC delta:** 0 (no hay código a eliminar)

---

## Resumen — Prompt Rules por Location

| Mutation | Regla en | LOC delta | Estado |
|---|---|---|---|
| M3 dedupe_repetitions | DOC_D | -24 | Draft |
| M4 dedupe_sentences | SYSTEM | -31 | Draft |
| M5-alt echo | SYSTEM | -40 (si REPLACE) | RECONSIDER |
| M6 normalize_length | DOC_D + TONE_CONFIG | -456 neto | Draft |
| M7 normalize_emojis | TONE_CONFIG | -27 | Draft (QW6 parcial) |
| M8 normalize_punctuation | TONE_CONFIG | -5 neto | Draft |
| M9 normalize_casing | TONE_CONFIG | 0 | Draft (sin código) |
| M10 strip_question | TONE_CONFIG + DOC_D | -250 neto | Draft |
| M11 signature_tic | DOC_D + few-shots | 0 | Draft (sin código) |

**LOC total a eliminar si todo REPLACE:** ~833 LOC
**Nota:** Este documento es v1 — las reglas deben validarse con CCEE Phase 2 antes de usar.
