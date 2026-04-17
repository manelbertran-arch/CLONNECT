# ARC4 — Eliminate Response Mutations

**Sprint:** 5 / Track 2 / ARC4
**Estimación realista:** 4 semanas (3 eng weeks + 1 buffer validación)
**Complejidad:** MEDIA
**Dependencias:** Ninguna (independiente de ARC1/ARC2/ARC3/ARC5)
**Autor:** Arquitecto Clonnect (AI)
**Fecha:** 2026-04-16

---

## 0 · TL;DR

> **Problema:** Clonnect aplica **11 mutaciones post-generación** al output del LLM (regex replace, deduplicación, longitud, puntuación, etc). Claude Code aplica **0 mutaciones** — toda su forma la define el system prompt. Las mutations de Clonnect:
>
> 1. **Ocultan señal de entrenamiento:** si el LLM genera "mal", lo reescribimos silenciosamente → nunca sabemos cuál prompt funciona realmente.
> 2. **Generan divergencia creador↔bot:** la voz del creador no es la que el LLM produce ni la que el creador escribe — es una **tercera voz** post-mutated.
> 3. **Multiplican código:** cada mutation es ~50-150 líneas + tests + monitoring. Total: ~1,200 LOC de mutaciones.
> 4. **Comen tiempo de review:** cada bug de estilo abre la duda "¿fue el prompt o la mutation?".
>
> **Solución:** Eliminar 9 de 11 mutations, sustituyéndolas por **reglas prompt-time** (system prompt rules + few-shots que demuestren el comportamiento). Mantener 2 (guardrails de seguridad, redacción PII). Validar cada eliminación con CCEE v5.3.
>
> **Métrica objetivo:** 9 mutations eliminadas, CCEE composite sin regresión > -2 puntos, ~1,000 LOC removidos.

---

## 1 · Problema que Resuelve

### 1.1 Evidencia W7 — Decisión D (§9)

> **Decisión D — Mutaciones post-gen:** *"Clonnect tiene 11 mutations. CC tiene 0 — su output es lo que el LLM genera. Cada mutation es una regla aplicada sin visibilidad del prompt. Debería ser prompt-time."*

### 1.2 Inventario completo — CRUCE §4

Del documento `docs/CRUCE_REPO_VS_CLONNECT.md §4` (cruzado con `W7 §4.S5-S8`):

| # | Nombre | Dónde | Qué hace | LOC | Riesgo al eliminar |
|---|---|---|---|---|---|
| **M1** | `apply_guardrails` | `services/guardrails.py` | Bloquea PII leak, profanity, unsafe content | ~180 | 🔴 HIGH — security |
| **M2** | `redact_pii` | `services/pii_redactor.py` | Reemplaza emails, phones, card numbers | ~95 | 🟡 MEDIUM — compliance |
| **M3** | `dedupe_repetitions_a2b` | `services/response_post.py::_a2b` | Colapsa "jajajaja" → "jaja", "sisisisi" → "si" | ~60 | 🟢 LOW |
| **M4** | `dedupe_sentences_a2c` | `services/response_post.py::_a2c` | Elimina frases repetidas consecutivas | ~85 | 🟢 LOW |
| **M5** | `remove_meta_questions_a3` | `services/response_post.py::_a3` | Quita "¿Te cuento más?" repetitivo | ~70 | 🟢 LOW |
| **M6** | `normalize_length` | `services/response_post.py::_length` | Trunca si > max, expande si < min | ~120 | 🟡 MEDIUM — UX |
| **M7** | `normalize_emojis` | `services/response_post.py::_emoji` | Aplica emoji_rule (0-2 per response) | ~90 | 🟢 LOW |
| **M8** | `normalize_punctuation` | `services/response_post.py::_punct` | Arregla "!!!" → "!", "..." → "." | ~55 | 🟢 LOW |
| **M9** | `normalize_casing` | `services/response_post.py::_casing` | "HOLA" → "hola" si creator lowercase | ~40 | 🟢 LOW |
| **M10** | `strip_question_when_not_asked` | `services/response_post.py::_noask` | Quita "?" cuando lead no preguntó | ~65 | 🟡 MEDIUM — conversational flow |
| **M11** | `insert_signature_tic` | `services/response_post.py::_tic` | Añade tic verbal del creador si falta | ~75 | 🟡 MEDIUM — voice fidelity |

**Total:** ~935 LOC solo en mutations (+ ~280 LOC de tests, + monitoring).

### 1.3 Evidencia de daño — casos reales

**Caso 1 — Iris scoring batch (2026-03-20):**
```
LLM output: "Fins demà! ;)"
M9 normalize_casing: no aplica (ya lowercase)
M7 normalize_emojis: elimina ";)" porque Iris emoji_rule=0
Output final: "Fins demà!"
```

La voz de Iris usa `;)` como tic característico. La mutation **eliminó el tic**. El prompt debería haber dicho "emojis: solo carita guiñando para cerrar".

**Caso 2 — Stefano warm lead (2026-04-02):**
```
LLM output: "Ciao bella, grazie mille per il messaggio! Come posso aiutarti?
             Fammi sapere se vuoi parlare di qualcosa in particolare. A presto!"
M6 normalize_length: max=150 chars → trunca a "Ciao bella, grazie mille per il
             messaggio! Come posso aiutarti? Fammi sapere se vuoi parlare"
Output final: frase incompleta, sin cierre natural.
```

La mutation **cortó a mitad de frase**. El prompt debería haber dicho "máximo 150 chars, termina con una pregunta o cierre".

### 1.4 Evidencia CC — 0 mutations

W7 §2.CC-D: *"Claude Code no aplica ninguna mutation post-generación. Todo el control de forma está en el system prompt + tool descriptions. Output = LLM output (verbatim)."*

Fundamento arquitectónico: **el LLM es el escritor, no el regex.**

### 1.5 Síntesis del problema

- **9 de 11 mutations son cosmetic/structural** → son "band-aids" para prompts mal escritos.
- **2 de 11 mutations son legítimas** (security + compliance) → deben quedarse.
- Cada mutation oculta el comportamiento real del LLM → dificulta debugging.
- Cada mutation añade latencia (~5-15ms por mutation × 11 = ~80-150ms total).
- Cada bug de estilo obliga a debuggear si el bug está en el prompt o en la mutation.

---

## 2 · Diseño Técnico

### 2.1 Clasificación de mutations

Cada mutation cae en 1 de 3 categorías:

| Categoría | Decisión | Cuántas |
|---|---|---|
| **KEEP** — función crítica no expresable por prompt | Mantener | 2 (M1, M2) |
| **REPLACE** — función replicable con regla de prompt | Eliminar + añadir regla prompt-time | 8 (M3-M9, M11) |
| **RECONSIDER** — función útil pero mal implementada | Rediseñar + evaluar | 1 (M10) |

### 2.2 Per-mutation plan

#### M1 · `apply_guardrails` — **KEEP**

**Función:** Bloquea output que filtra PII del creador, profanity high-severity, o unsafe content.

**Por qué keep:**
- Seguridad no negociable. Un prompt bien escrito puede fallar en 0.1% de casos adversariales.
- CC también tiene guardrails equivalentes en su API layer.
- Regla legal: "no liberar datos personales de otros creators o leads".

**Mejoras dentro del keep:**
- Hacer guardrail **observable** (loggea qué bloqueó y por qué).
- Separar "hard block" (seguridad) de "soft warn" (estilo → se reenvía a prompt regen).

**LOC cambio:** 0 (mantener).

---

#### M2 · `redact_pii` — **KEEP con refactor**

**Función:** Reemplaza emails, teléfonos, tarjetas de crédito en el output.

**Por qué keep:**
- Compliance (GDPR, PCI). No se puede confiar solo en prompt.
- Caso real: lead pregunta "¿tu email?" — LLM puede responder con `creator_email@gmail.com` aunque el prompt diga no.

**Refactor:**
- Integrar con `M1.apply_guardrails` (un solo paso "safety filter").
- En lugar de redact silenciosamente, **reject + regenerate** (alert Manel).
- Añadir regla prompt-time explícita: "nunca incluyas email, teléfono, tarjetas".

**LOC cambio:** -95 (fusionar con M1).

---

#### M3 · `dedupe_repetitions_a2b` — **REPLACE**

**Función:** Colapsa repeticiones onomatopéyicas ("jajajaja" → "jaja").

**Por qué replace:**
- El LLM genera "jajajaja" cuando el prompt no especifica qué grado de onomatopeya es natural.
- Solución prompt-time: añadir al Doc D:
  > "Onomatopeyas: máximo 4 caracteres repetidos. Ej: 'jaja', 'siii', nunca 'jajajaja'."

**Validación:**
- CCEE v5.3 pre/post con 20 scenarios que inducen risa.
- Si > 5% de outputs exceden "jaja" limit, iterar prompt.

**LOC cambio:** -60.

---

#### M4 · `dedupe_sentences_a2c` — **REPLACE**

**Función:** Elimina frases repetidas consecutivas ("Claro que sí. Claro que sí.").

**Por qué replace:**
- Un LLM bien promptado no repite frases.
- Cuando repite, es señal de prompt defectuoso (temperatura alta, instrucciones contradictorias).
- Mutation oculta el bug real.

**Solución prompt-time:**
- Añadir al system prompt global:
  > "No repitas frases idénticas consecutivas. Cada oración debe aportar información nueva."
- Validar con CCEE (si repetición > 2%, hay un bug de prompt → arreglarlo).

**LOC cambio:** -85.

---

#### M5 · `remove_meta_questions_a3` — **REPLACE**

**Función:** Elimina "¿Te cuento más?", "¿Quieres saber más?" al final de cada respuesta.

**Por qué replace:**
- Es un tic del LLM mal promptado. Con el prompt correcto, no ocurre.
- Mutation hace invisible el patrón → Manel no sabe que el prompt es el problema.

**Solución prompt-time:**
- Doc D de cada creador:
  > "No cierres con 'te cuento más?' o similares. Si quieres invitar a continuar, hazlo con afirmación ('a ver qué más me cuentas') o con pregunta relevante al tema."

**Validación:** CCEE v5.3 pre/post, validar que tasa de meta-preguntas < 5%.

**LOC cambio:** -70.

---

#### M6 · `normalize_length` — **REPLACE con fallback**

**Función:** Trunca si output > max_chars, expande si < min_chars.

**Por qué replace:**
- Es la mutation que más daño hace (truncar a mitad de frase).
- LLMs son capaces de respetar límites de longitud si el prompt es específico.

**Solución prompt-time:**
- Doc D:
  > "Longitud típica: 80-150 caracteres. Si tu respuesta excede, reformúlala. Termina siempre en frase completa."
- Few-shots con ejemplos corto/medio/largo.

**Fallback (no mutation):**
- Si output > max × 1.3 (exceso severo): **rechazar y regenerar** con temperatura -0.1.
- Si output < min × 0.7 (déficit severo): regenerar.
- Máximo 1 regeneración (CircuitBreaker de ARC3 cubre loops).

**Validación:**
- CCEE v5.3 mide distribución de longitud.
- Si > 10% excede max × 1.3, prompt mal.

**LOC cambio:** -120 (removida) + 40 (regen fallback) = **-80 neto**.

---

#### M7 · `normalize_emojis` — **REPLACE**

**Función:** Aplica `emoji_rule` del creador (0-2 emojis por respuesta, tipo permitido).

**Por qué replace:**
- QW6 ya wire-eó `_tone_config.emoji_rule` en el system prompt (commit `a54fb28b`).
- La mutation es redundante si el prompt está bien.

**Solución prompt-time (ya done):**
- QW6: `tone_directive` en system prompt incluye `emoji_rule`.
- Validar con CCEE que compliance > 95%.

**Mantener mínimo:**
- Métrica `emoji_rule_violation_rate` para detectar degradación futura.
- NO mutation; solo logging.

**LOC cambio:** -90.

---

#### M8 · `normalize_punctuation` — **REPLACE**

**Función:** Arregla "!!!" → "!", "..." → "."

**Por qué replace:**
- LLMs modernos (Gemma-4, Claude) ya generan puntuación natural.
- Creators que usan "!!!" deliberadamente (Stefano) pierden ese tic con la mutation.

**Solución prompt-time:**
- Per-creator: `_tone_config.punctuation_style` con opciones:
  - `standard` (default): puntuación natural estándar.
  - `expressive`: permite "!!!" y "..." como énfasis.
  - `minimal`: un solo signo por frase.
- Inyectar en system prompt.

**LOC cambio:** -55 + 15 (config schema) = **-40 neto**.

---

#### M9 · `normalize_casing` — **REPLACE**

**Función:** "HOLA" → "hola" si creator usa lowercase, "hola" → "Hola" si usa capitalize.

**Por qué replace:**
- Es un comportamiento expresable en una línea de prompt:
  > "Escribe todo en minúsculas, sin mayúscula inicial de frase." (Iris)
  > "Mayúscula solo al inicio de frase, no ALL CAPS." (Stefano)

**LOC cambio:** -40.

---

#### M10 · `strip_question_when_not_asked` — **RECONSIDER**

**Función:** Elimina "?" cuando el lead no hizo pregunta (anti-loop).

**Por qué reconsider:**
- Es sutil — la función es evitar conversaciones donde cada mensaje del bot termina con pregunta.
- Eliminarla via prompt es posible pero frágil.

**Opciones:**

**Opción A — Prompt-time:**
```
Reglas de pregunta:
- Si el lead HIZO una pregunta → tu respuesta no necesita terminar con pregunta.
- Si el lead NO hizo pregunta → termina con afirmación o invitación (no pregunta directa).
- Una pregunta cada 3-4 mensajes como máximo.
```

**Opción B — Keep mutation pero observable:**
- Log `question_stripped` metric.
- No trimmear silenciosamente — regenerar sin pregunta.

**Recomendación:** Opción A + shadow mode durante 2 semanas. Si falla, fallback a B.

**LOC cambio (si A succeeds):** -65.

---

#### M11 · `insert_signature_tic` — **REPLACE**

**Función:** Inserta un tic verbal del creador si el LLM no lo usó en N respuestas consecutivas.

**Por qué replace:**
- Es una "proxy metric" de personalización — si el bot no usa tics del creador, es señal de que la distilled voice está mal.
- Mutation es pegar el tic sintéticamente → el creador escribe "posaaa" de forma orgánica, la mutation lo pega al final sin contexto.

**Solución prompt-time:**
- Doc D debería enseñar **cuándo** usar tic, no solo **que** el tic existe.
- Few-shots con ejemplos del tic en contexto (inicio vs cierre vs respuesta a emoción).
- Métrica: `tic_usage_rate` — si < target, iterar prompt.

**LOC cambio:** -75.

### 2.3 Resumen de cambios

| Mutation | Decisión | LOC delta | Prompt-time rule |
|---|---|---|---|
| M1 guardrails | KEEP | 0 | — |
| M2 redact_pii | KEEP + fusionar con M1 | -95 (-40 + -55 fusión) | "nunca incluyas email/teléfono" |
| M3 dedupe_repetitions | REPLACE | -60 | "onomatopeyas max 4 chars" |
| M4 dedupe_sentences | REPLACE | -85 | "no repitas frases idénticas" |
| M5 remove_meta_questions | REPLACE | -70 | "no cierres con 'te cuento más'" |
| M6 normalize_length | REPLACE + regen fallback | -80 | "80-150 chars, frase completa" |
| M7 normalize_emojis | REPLACE (done QW6) | -90 | `tone_directive.emoji_rule` |
| M8 normalize_punctuation | REPLACE + config schema | -40 | `_tone_config.punctuation_style` |
| M9 normalize_casing | REPLACE | -40 | "todo minúsculas / capitalize" |
| M10 strip_question | RECONSIDER → REPLACE if validated | -65 | "pregunta 1 de cada 3-4 mensajes" |
| M11 insert_signature_tic | REPLACE | -75 | Doc D + few-shots enseñan uso |
| **TOTAL** |  | **-700 LOC net** | 10 nuevas reglas en prompt |

### 2.4 Arquitectura post-ARC4

```
┌────────────────────────────────────────────────────┐
│ Pre-generation                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ System prompt incluye:                       │  │
│  │  - emoji_rule (QW6)                          │  │
│  │  - length_guidance ("80-150 chars")          │  │
│  │  - punctuation_style                         │  │
│  │  - casing_rule                               │  │
│  │  - question_cadence ("1/3-4 messages")       │  │
│  │  - onomatopoeia_limit ("max 4 chars")        │  │
│  │  - meta_question_ban                         │  │
│  │  - pii_ban                                   │  │
│  └──────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────┐  │
│  │ Few-shots demuestran cada regla              │  │
│  │ (tic usage, length, emoji, casing, ...)      │  │
│  └──────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────┐
│ LLM generation                                     │
└────────────────────────────────────────────────────┘
                         │
                         ▼
┌────────────────────────────────────────────────────┐
│ Post-generation (único paso restante)              │
│  ┌──────────────────────────────────────────────┐  │
│  │ SafetyFilter (M1 + M2 fusionados)            │  │
│  │  - Hard block: PII leak, unsafe content      │  │
│  │  - On block: regenerate (max 1) or fallback  │  │
│  │  - Log all blocks                            │  │
│  └──────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────┐  │
│  │ LengthRegenFallback (nuevo, reemplaza M6)    │  │
│  │  - If len > max × 1.3 or < min × 0.7:        │  │
│  │    regenerate with temp -0.1                 │  │
│  │  - Max 1 retry (CircuitBreaker covers loops) │  │
│  └──────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────┘
                         │
                         ▼
                 Response to lead
```

**Total post-processing LOC:** ~280 (solo SafetyFilter + LengthRegen) vs actual ~1,200.

---

## 3 · Plan de Rollout (5 fases)

### Phase 1 — Baseline + Prompt Rules (Semana 1)

**Objetivo:** Documentar baseline actual y preparar prompt-time rules para todas las mutations.

**Tasks:**
1. Correr CCEE v5.3 baseline (Iris + Stefano × 26B + 31B) **con mutations activas**.
2. Para cada mutation M3-M11:
   - Diseñar la prompt-time rule equivalente.
   - Añadir al `_tone_config` schema si aplica.
   - Escribir few-shots que la demuestren.
3. Producir `docs/sprint5_planning/ARC4_phase1_prompt_rules.md` con:
   - Baseline CCEE results.
   - 10 prompt-time rules en formato copy-paste al Doc D.
   - Nuevos campos de `_tone_config` per-creator.

**No-go criteria:** Ninguno (esto es doc work).

---

### Phase 2 — Shadow Validation (Semana 2)

**Objetivo:** Antes de eliminar cada mutation, validar que el output pre-mutation ya cumple la regla (gracias al prompt-time rule).

**Tasks:**
1. Implementar `services/response_post.py::shadow_mode(mutation_name)`:
   - Ejecuta mutation.
   - Compara pre-mutation output vs post-mutation output.
   - Log a `mutation_shadow_log` table: `(mutation, pre_len, post_len, changed, diff_text)`.
2. Activar shadow para M3-M11 simultáneamente (no aplica lógica — mutations siguen activas).
3. Después de 5,000 turnos (~3 días de tráfico):
   - Por mutation: calcular `changed_rate` (% de turnos donde la mutation modificó el output).
   - Target: `changed_rate < 5%` → el prompt ya funciona sin la mutation.
4. Producir `docs/sprint5_planning/ARC4_phase2_shadow_analysis.md` con:
   - Tabla `mutation × changed_rate`.
   - Recomendación per-mutation: "safe to remove" / "needs prompt iteration" / "keep".

**No-go criteria:**
- Si 3+ mutations tienen `changed_rate > 20%` → iterar prompts antes de continuar.

---

### Phase 3 — Eliminate Low-Risk (Semana 2-3)

**Objetivo:** Eliminar mutations con `changed_rate < 5%` y `risk = LOW`.

**Candidatos** (según tabla §2.3):
- M3 dedupe_repetitions
- M4 dedupe_sentences
- M5 remove_meta_questions
- M7 normalize_emojis (ya validado QW6)
- M8 normalize_punctuation
- M9 normalize_casing

**Rollout por mutation:**
1. **Feature flag:** `DISABLE_MUTATION_M{N}` en `creator_runtime_config`.
2. Rollout 10% → 50% → 100% por creator en 3 días.
3. CCEE v5.3 comparativo tras cada step.
4. Si ΔCCEE composite > -2 puntos: rollback esa mutation, iterar prompt.

**Paralelización:** 2-3 mutations a la vez (no las 6 de golpe — aisla la causa si hay regresión).

---

### Phase 4 — Eliminate Medium-Risk (Semana 3)

**Objetivo:** Eliminar M6, M10, M11 (los 3 de mayor riesgo UX).

**Tratamiento especial:**

#### M6 — normalize_length
- Implementar `LengthRegenFallback` antes de eliminar.
- Shadow mode 1 semana.
- Validar que regen fallback trigger-rate < 3%.
- Entonces eliminar M6.

#### M10 — strip_question
- Opción A (prompt-time) rollout 10% Stefano.
- Medir "consecutive-questions rate" (turnos donde bot y lead ambos hacen preguntas).
- Si < 5% (actualmente ~8%), proceed.
- Si > 8%, fallback a keep-mutation-but-observable.

#### M11 — insert_signature_tic
- Medir `tic_usage_rate` con la mutation (baseline).
- Rollout 10% sin mutation.
- Medir nuevo `tic_usage_rate`.
- Si cae > 20% (e.g., 80% → 64%), iterar Doc D con más few-shots de tic.
- Si cae < 20%, proceed.

---

### Phase 5 — Refactor M1+M2 into SafetyFilter (Semana 4)

**Objetivo:** Consolidar las 2 mutations que se mantienen en un solo componente observable.

**Tasks:**
1. Crear `services/safety_filter.py`:
   - `apply_safety(response)` → {status: OK|BLOCK|REGEN, reason, ...}
   - Integra guardrails (M1) + PII (M2).
   - Emite eventos a `security_events` (QW3 already live).
2. Deprecar `services/guardrails.py` y `services/pii_redactor.py`.
3. Tests de regresión — todos los casos adversariales conocidos.
4. Deploy + monitor 48h.

**LOC final:** ~280 (SafetyFilter + LengthRegen + métricas).

---

## 4 · Métricas de Éxito

### 4.1 Métricas Primarias

| Métrica | Baseline | Target | Método |
|---|---|---|---|
| **Mutations eliminadas** | 11 | ≤ 2 (solo safety) | Count de archivos en services/response_post/ |
| **LOC removidos** | 0 | ≥ 700 | git diff |
| **CCEE composite Iris** | 70.2 | ≥ 68.0 (aceptar -2) | CCEE v5.3 × 26B/31B × 20 scenarios |
| **CCEE composite Stefano** | 68.5 | ≥ 66.5 (aceptar -2) | CCEE v5.3 × 26B/31B × 20 scenarios |
| **Post-gen latency P95** | ~120ms | ≤ 40ms | Trace span en generation pipeline |

### 4.2 Métricas per-mutation (Quality)

Por cada mutation eliminada, debe cumplirse:

| Criterio | Threshold |
|---|---|
| `changed_rate` en shadow (pre-elimination) | < 5% |
| ΔCCEE composite post-elimination | > -2 puntos |
| `rule_violation_rate` (e.g., emoji count > max) | < 5% |
| User-perception score (Manel 10 turnos review) | ≥ 4/5 |

### 4.3 Métricas secundarias

| Métrica | Target |
|---|---|
| `safety_filter_block_rate` | < 0.5% |
| `length_regen_fallback_rate` | < 3% |
| Post-gen latency mean | < 20ms |

---

## 5 · Riesgos y Mitigaciones

### R1 — Eliminar mutation sin prompt equivalente rompe UX — 🔴 HIGH

**Descripción:** Si la prompt-time rule no es efectiva, el output del LLM no cumple el estilo y el lead percibe el cambio.

**Mitigación:**
- Shadow mode obligatorio antes de eliminar (Phase 2).
- Rollout gradual (10→50→100).
- CCEE v5.3 pre/post per-mutation.
- Feature flag para rollback inmediato.
- Review humano (Manel) de 10 turnos pre/post.

### R2 — Iteración de prompt es costosa — 🟡 MEDIUM

**Descripción:** Si una mutation no se puede reemplazar al primer intento, iterar el prompt puede tomar 2-3 ciclos × 4h cada uno.

**Mitigación:**
- Buffer semana 4 en el cronograma.
- Trabajo paralelo: mientras se itera M6, se elimina M3/M4/M5.
- Documentar patrones exitosos — reutilizar entre creadores.

### R3 — Pérdida de observabilidad temporal — 🟡 MEDIUM

**Descripción:** Durante Phase 2 (shadow), tenemos info doble. Tras Phase 3, perdemos el log "qué estaba haciendo la mutation" — si aparece un bug, no sabemos si era un escenario que la mutation cubría.

**Mitigación:**
- Log `mutation_shadow_log` retenido 90 días post-elimination.
- Métricas de post-processing en Grafana (ARC5).
- Alert: si `safety_filter_block_rate` sube > 2x baseline → investigar.

### R4 — Creadores diferentes necesitan rules diferentes — 🟡 MEDIUM

**Descripción:** Lo que funciona para Iris (lowercase todo) no aplica a Stefano (sentence case).

**Mitigación:**
- Todas las reglas son **per-creator** en `_tone_config`.
- Onboarding de nuevo creador incluye definir `_tone_config` completo.
- Default conservador (e.g., sentence case) si el creator no lo especifica.

### R5 — Mutations interactúan — 🟢 LOW

**Descripción:** M4 y M5 pueden solaparse (frase repetida = meta-pregunta repetida).

**Mitigación:**
- Eliminar en orden: M5 primero (más específica) → M4 (más general).
- Tests cubren edge case "frase repetida + meta-pregunta".

### R6 — Degradación post-6-meses — 🟢 LOW

**Descripción:** A largo plazo, modelo base puede cambiar y empezar a violar reglas.

**Mitigación:**
- Métrica continua `rule_violation_rate` per-rule.
- Alert si cruza 5% sostenido.
- Playbook: "si violation-rate sube, iterar prompt (no reintroducir mutation)".

### R7 — M11 (tic) es difícil de replicar via prompt — 🟡 MEDIUM

**Descripción:** El tic característico no es una regla sino una ejecución. Puede requerir muchos few-shots.

**Mitigación:**
- Validación específica: `tic_usage_rate` medido pre/post.
- Fallback: keep-as-observable-mutation (log only, no insert) si prompt falla.

---

## 6 · Dependencias

### 6.1 Dependencias técnicas

| Dependencia | Owner | Status | Blocking |
|---|---|---|---|
| QW6 emoji_rule wiring | Sprint 4 QW | ✅ done | No |
| QW3 alerting | Sprint 4 QW | ✅ done | No |
| CCEE v5.3 harness | Sprint 4 CCEE | ✅ done | No |
| Feature flag infra (ARC1) | Sprint 5 ARC1 | in_progress | No |
| `_tone_config` schema | Persona compiler | ✅ existe | No |

### 6.2 Dependencias con otros ARCs

- **ARC1 (Budget):** Independiente. No se tocan los mismos archivos.
- **ARC2 (Memory):** Independiente.
- **ARC3 (Compaction):** Independiente. Compactor opera sobre prompt pre-gen; mutations operaban sobre response post-gen.
- **ARC5 (Observability):** ARC4 emite métricas nuevas (`rule_violation_rate`, `mutation_changed_rate`) que ARC5 dashboardea.

### 6.3 Orden recomendado con otros ARCs

Ejecutar **en paralelo con ARC1 y ARC2**. No bloquea ni es bloqueado.

---

## 7 · Cronograma (4 semanas realistas)

### Semana 1 — Prompt Rules Design

| Día | Work | Owner | Output |
|---|---|---|---|
| Lun | CCEE baseline Iris + Stefano | A4.1 (CCEE) | Baseline results archived |
| Mar | Design 10 prompt-time rules | A4.2 (prompt eng) | Rules doc draft |
| Mié | Few-shots per rule | A4.2 | Few-shot library |
| Jue | `_tone_config` schema extension | A4.3 (dev) | Schema + migración |
| Vie | Phase 1 review con Manel | A4.2 + Manel | Approved rules |

### Semana 2 — Shadow Validation

| Día | Work | Owner | Output |
|---|---|---|---|
| Lun | `shadow_mode()` implementation | A4.3 | Shadow code |
| Mar | Deploy shadow + `mutation_shadow_log` table | A4.3 | Live shadow |
| Mié-Jue | Collect 5,000+ turnos data | (tráfico natural) | Logs |
| Vie | Phase 2 analysis + recommendations | A4.1 | Go/no-go per mutation |

### Semana 3 — Eliminate

| Día | Work | Owner | Output |
|---|---|---|---|
| Lun | Eliminate M3 + M8 (low-risk) | A4.3 + A4.1 | 10→50→100 rollout |
| Mar | Eliminate M4 + M9 | A4.3 + A4.1 | 10→100 |
| Mié | Eliminate M5 + M7 | A4.3 + A4.1 | 10→100 |
| Jue | Implement LengthRegenFallback (pre M6) | A4.3 | Regen in staging |
| Vie | Eliminate M6 (with regen backing) | A4.3 + A4.1 | 10→50 |

### Semana 4 — Medium-Risk + SafetyFilter

| Día | Work | Owner | Output |
|---|---|---|---|
| Lun | M6 rollout 100% + monitor | A4.1 | Metrics check |
| Mar | Eliminate M10 (with fallback plan) | A4.3 | 10→100 |
| Mié | Eliminate M11 + validate tic_usage_rate | A4.1 | Tic metric OK |
| Jue | Refactor M1+M2 → SafetyFilter | A4.4 (refactor) | SafetyFilter live |
| Vie | Retrospective + final CCEE | A4.1 | Sprint completion |

**Buffer:** 3-5 días adicionales si:
- M10 o M11 requieren iteración de prompt.
- CCEE regresa > -2 puntos en una mutation.

---

## 8 · Worker Prompts (listos para copiar)

### Worker A4.1 — CCEE Baseline + Per-Mutation Validation

```xml
<instructions>
<role>
Eres un ML engineer de Clonnect, especialista en evaluación CCEE.
</role>

<context>
Sprint 5 ARC4. Eliminaremos 9 mutations post-generación. Tu rol: establecer
baseline CCEE y validar cada eliminación con CCEE v5.3.
Leer: docs/sprint5_planning/ARC4_eliminate_mutations.md §4 completo.
Leer: tests/run_ccee.py para entender el harness.
</context>

<objetivo>
1. Producir baseline CCEE pre-ARC4 (Iris + Stefano × 26B + 31B).
2. Tras cada eliminación de mutation, correr CCEE comparativo.
3. Reportar regresiones > -2 puntos → gate de rollback.
</objetivo>

<tareas>
Fase 1 (Semana 1):
1. Correr CCEE v5.3 × 4 configs (Iris/Stefano × 26B/31B) con mutations ACTIVAS.
2. Guardar en tests/ccee_results/{creator}/arc4_baseline_{model}.json.
3. Publicar tabla comparativa en docs/sprint5_planning/ARC4_baseline.md.

Fase 3-4 (Semana 3-4, per mutation):
4. Tras cada mutation eliminada (M3, M4, M5, M7, M8, M9, M6, M10, M11):
   - Correr CCEE mismo harness.
   - Comparar composite + per-metric con baseline.
   - Si Δcomposite > -2: OK, proceed a siguiente.
   - Si Δcomposite ≤ -2: STOP, comunicar a eng para iterar prompt.
5. Documentar cada paso en docs/sprint5_planning/ARC4_per_mutation_results.md.
</tareas>

<reglas>
- CCEE v5.3 obligatorio (no variantes).
- 20 scenarios × 2 modelos × 2 creators = 80 generaciones por run.
- NO aprobar eliminación sin Δcomposite > -2.
- Report per-metric: si K1 o S3 regresan > -3 puntos, flag aunque composite OK.
</reglas>

<deliverables>
- Baseline JSON × 4 + markdown summary.
- Per-mutation validation JSON + markdown summaries (9 mutations).
- Final roll-up: ARC4_final_ccee_report.md.
</deliverables>
</instructions>
```

---

### Worker A4.2 — Prompt Rules Design

```xml
<instructions>
<role>
Eres un prompt engineer senior de Clonnect. Tu experiencia es diseñar
system prompts y few-shots que induzcan comportamiento específico del LLM.
</role>

<context>
Sprint 5 ARC4. Reemplazaremos 9 mutations con prompt-time rules.
Leer: docs/sprint5_planning/ARC4_eliminate_mutations.md §2.2 completo
(descripción per-mutation con "Solución prompt-time").
Leer: services/prompt_service.py para entender cómo se compone el prompt.
Leer: Docs D actuales de Iris y Stefano en DB.
</context>

<objetivo>
Diseñar 10 prompt-time rules + few-shots que reemplacen las mutations M3-M11.
Cada rule debe ser copy-paste al Doc D (o al system prompt global, según aplique).
</objetivo>

<tareas>
1. Para cada mutation M3-M11 + M2 (PII rule):
   - Escribir la rule textual en español.
   - Escribir 2-3 few-shots demostrando el comportamiento correcto.
   - Indicar si va en Doc D (per-creator) o system prompt (global) o `_tone_config`.
2. Específicos:
   - M6 length: diseñar rule adaptable per-creator (80-150 Iris, 60-120 Stefano).
   - M10 question cadence: rule clara + 3 few-shots mostrando cuándo SÍ preguntar.
   - M11 tic: NO es una rule, son few-shots — seleccionar 5 ejemplos del corpus real del creador.
3. Producir docs/sprint5_planning/ARC4_phase1_prompt_rules.md con:
   - Tabla mutation × rule × location (Doc D / system / tone_config).
   - Rules en formato copy-paste (literal).
   - Few-shots con source (corpus real si disponible, o sintético marcado).
4. Ampliar `_tone_config` schema con nuevos campos:
   - `punctuation_style`: Literal["standard", "expressive", "minimal"]
   - `casing_rule`: Literal["lowercase", "sentence", "title"]
   - `length_range`: tuple[int, int]  # (min, max)
   - `question_cadence`: int  # max 1 pregunta cada N turnos
   - `onomatopoeia_limit`: int  # max chars de repetición
5. Tests de persona_compiler asegurando que los nuevos campos se inyectan en el prompt.
</tareas>

<reglas>
- Rules en español natural, no jerga técnica.
- Few-shots deben ser REALISTAS (corpus del creador si existe).
- NO duplicar reglas que ya existen en el Doc D actual.
- Gate: Manel review obligatorio antes de Phase 2.
</reglas>

<deliverables>
- docs/sprint5_planning/ARC4_phase1_prompt_rules.md completo.
- Esquema _tone_config ampliado en core/personas/compiler.py.
- Tests pasando en test_persona_compiler.py.
- Per-creator tone_config actualizado en DB (seed script).
</deliverables>
</instructions>
```

---

### Worker A4.3 — Shadow Mode + Mutation Elimination

```xml
<instructions>
<role>
Eres un ingeniero backend Python de Clonnect, especialista en refactor
controlado y feature flags.
</role>

<context>
Sprint 5 ARC4 Phase 2-4. Implementar shadow mode, luego eliminar mutations
una a una con feature flags y rollout gradual.
Leer: docs/sprint5_planning/ARC4_eliminate_mutations.md §2.3, §3 Phase 2-4.
Leer: services/response_post.py completo (las 11 mutations viven aquí).
</context>

<objetivo>
1. Implementar shadow mode para medir changed_rate de cada mutation.
2. Eliminar M3-M11 progresivamente con feature flags + rollout.
3. Implementar LengthRegenFallback antes de eliminar M6.
</objetivo>

<tareas>
Phase 2 (Semana 2):
1. Implementar `services/response_post.py::shadow_wrapper(mutation_fn)`:
   - Decorador que envuelve cada mutation existente.
   - Calcula diff pre/post.
   - Log a tabla `mutation_shadow_log` (id, mutation_name, pre_text, post_text, changed, turn_id, created_at).
2. Migración alembic para `mutation_shadow_log`.
3. Deploy a producción (shadow = no afecta output).
4. Después de 5,000+ turnos, query agregado: changed_rate per mutation.

Phase 3 (Semana 3):
5. Feature flag `DISABLE_MUTATION_{M}` en `creator_runtime_config`.
6. Modificar `response_post.py` para respetar el flag:
   ```python
   if should_apply(mutation="m3", creator_id=ctx.creator_id):
       text = _a2b(text)
   ```
7. Rollout 10% → 50% → 100% per creator per mutation:
   - M3, M8 día 1
   - M4, M9 día 2
   - M5, M7 día 3

Phase 4 (Semana 4):
8. Implementar LengthRegenFallback:
   ```python
   async def generate_with_length_check(...):
       resp = await llm.generate(...)
       if not length_in_range(resp, tone_config.length_range):
           resp = await llm.generate(..., temperature=temp - 0.1)
       return resp  # Accept even if second fails
   ```
9. Eliminar M6 (con fallback activo).
10. Eliminar M10 (con shadow extra validation: consecutive_questions_rate).
11. Eliminar M11 (con tic_usage_rate validation pre/post).

Después:
12. Métrica per-rule: `rule_violation_rate`:
    - emoji_violation_rate
    - length_violation_rate
    - punctuation_violation_rate
    - etc.
</tareas>

<reglas>
- Shadow mode NO modifica output real.
- Feature flag per-mutation per-creator (granular rollback).
- NO eliminar código de la mutation hasta que rollout = 100% estable 7 días.
- Test coverage obligatorio: cada eliminación debe tener test que valide el comportamiento prompt-time.
- Syntax check .py modificados.
</reglas>

<deliverables>
- core/generation/shadow_wrapper.py
- Migración mutation_shadow_log
- Feature flags implementados
- LengthRegenFallback en services/generation.py
- 9 mutations eliminadas (código borrado tras validación 7 días)
- rule_violation_rate metrics en Prometheus
</deliverables>
</instructions>
```

---

### Worker A4.4 — SafetyFilter Refactor (Consolidate M1+M2)

```xml
<instructions>
<role>
Eres un ingeniero backend de Clonnect, enfocado en security/compliance.
</role>

<context>
Sprint 5 ARC4 Phase 5. M1 (guardrails) + M2 (PII redact) son las únicas 2
mutations que se quedan. Consolidarlas en un solo componente observable.
Leer: docs/sprint5_planning/ARC4_eliminate_mutations.md §2.2 M1 + M2, §3 Phase 5.
Leer: services/guardrails.py + services/pii_redactor.py completos.
Leer: core/security/alerting.py (QW3 already live).
</context>

<objetivo>
Consolidar M1 + M2 en `services/safety_filter.py` con:
- API unificada
- Observabilidad (log qué bloquea, por qué)
- Regenerate-on-block (no silent redact)
- Integración con QW3 alerting
</objetivo>

<tareas>
1. Crear `services/safety_filter.py`:
   ```python
   @dataclass
   class SafetyResult:
       status: Literal["OK", "BLOCK", "REGEN"]
       reason: str | None = None
       sanitized_text: str | None = None
       metadata: dict = field(default_factory=dict)

   async def apply_safety(
       text: str,
       creator_id: UUID,
       lead_id: UUID,
   ) -> SafetyResult:
       # 1. Hard block checks (PII leak of creator's own data)
       # 2. Content policy checks (profanity, unsafe)
       # 3. Regen if soft violation detected
       # 4. Log all blocks to security_events (QW3)
       ...
   ```
2. Port logic from guardrails.py + pii_redactor.py (NO lógica nueva, solo reorganización).
3. Integración en `services/generation.py`:
   ```python
   resp = await llm.generate(...)
   safety = await apply_safety(resp, creator_id, lead_id)
   if safety.status == "BLOCK":
       return await get_fallback_response(...)  # ARC3 fallback
   if safety.status == "REGEN":
       resp = await llm.generate(..., adjusted_prompt=...)
       safety = await apply_safety(resp, ...)  # second try
       if safety.status != "OK":
           return fallback
   return safety.sanitized_text or resp
   ```
4. Emit alert via alert_security_event para cada block.
5. Tests de regresión:
   - Todos los casos de guardrails_tests.py deben pasar.
   - Todos los casos de pii_redactor_tests.py deben pasar.
   - Nuevos tests: regen flow, alert emission, metadata.
6. Deprecar `services/guardrails.py` y `services/pii_redactor.py` (mark as deprecated, eliminar tras 2 semanas).
</tareas>

<reglas>
- NO cambiar los thresholds de guardrails ni las regex de PII sin approval.
- Regen-on-block es CRÍTICO: no hacer silent redact.
- Alert obligatorio por cada BLOCK (QW3 ya está live).
- Tests de adversarial scenarios: 100% passing.
- Syntax check + smoke tests obligatorios.
</reglas>

<deliverables>
- services/safety_filter.py + tests
- Integración en services/generation.py
- Files deprecated: guardrails.py, pii_redactor.py (tombstones)
- security_events populated con nuevos eventos
- Documentación: docs/runbooks/safety_filter.md
</deliverables>
</instructions>
```

---

## 9 · Open Questions

### Q1 — ¿Todas las mutations se eliminan al mismo tiempo o secuencialmente?

**Respuesta tentativa:** Secuencialmente (Phase 3-4 ya lo define) para aislar regresiones. Eliminar todas de golpe haría imposible debugear.

---

### Q2 — ¿Cómo manejar el caso "rule prompt funciona en 95% pero falla en edge case específico"?

Ejemplo: M3 (onomatopeyas) funciona 95% pero un lead con "JAJAJAJAJA" en mayúsculas induce regresión.

**Opciones:**
- A: Add specific few-shot para el edge case.
- B: Keep mutation específicamente para este case.
- C: Accept 5% error rate (humanos también se equivocan).

**Recomendación tentativa:** A primero, B como último recurso. Documentar el caso en rule library.

---

### Q3 — ¿Qué pasa con tests que dependían de las mutations?

Hay tests en `tests/test_response_post.py` que específicamente validan "after M5 runs, output no tiene '?'". Al eliminar M5, esos tests dejan de tener sentido.

**Respuesta:** Se reemplazan por tests prompt-time: "LLM output con este prompt no contiene '?'". Test unitarios → integration tests con LLM mock o real.

---

### Q4 — ¿Mantenemos capacidad de "hot-enable" una mutation si se detecta regresión en prod?

**Propuesta:** Feature flag `DISABLE_MUTATION_{M}` se mantiene como kill-switch por **3 meses post-elimination**. Código de mutation se archiva en `services/response_post_deprecated.py` durante ese periodo. Tras 3 meses sin rollback, borrar.

---

### Q5 — ¿El costo de tokens aumenta?

Sí, los prompts se hacen más largos (~300-500 tokens más) por las rules + few-shots.

**Estimación:** +5-8% costos per-turn. Aceptable si a cambio:
- -700 LOC de mutations
- Mejor debugeabilidad
- Posibilidad de mejorar prompt sin deploy (runtime config)

**Métrica a monitorear:** `avg_tokens_per_generation` pre/post ARC4.

---

## 10 · Appendix

### 10.1 Glosario

- **Mutation:** Modificación post-generación del output del LLM mediante regex/reglas Python.
- **Prompt-time rule:** Instrucción en el system prompt o Doc D que induce el comportamiento deseado directamente en el LLM.
- **Shadow mode:** Ejecutar lógica en paralelo al pipeline real, solo logging.
- **SafetyFilter:** Componente consolidado post-ARC4 que reemplaza guardrails + pii_redactor.
- **Regen fallback:** Estrategia de regeneración con temperatura ajustada cuando el output no cumple constraints duros.

### 10.2 Referencias

- W7 §9 Decisión D: mutations gap.
- CRUCE §4: inventario inicial de 11 mutations.
- QW6 (commit a54fb28b): emoji_rule wiring (precedente de éxito).
- CC arch: 0 post-gen mutations, todo prompt-time.

### 10.3 Lista completa de mutations eliminadas (post-ARC4)

- ✅ M3 `dedupe_repetitions_a2b`
- ✅ M4 `dedupe_sentences_a2c`
- ✅ M5 `remove_meta_questions_a3`
- ✅ M6 `normalize_length` (reemplazada por LengthRegenFallback)
- ✅ M7 `normalize_emojis` (ya vía QW6)
- ✅ M8 `normalize_punctuation`
- ✅ M9 `normalize_casing`
- ✅ M10 `strip_question_when_not_asked` (if shadow OK, else RECONSIDER)
- ✅ M11 `insert_signature_tic`

### 10.4 Post-ARC4 acceptance checklist

- [ ] 9 mutations eliminadas (código borrado del trunk).
- [ ] 10 prompt-time rules integradas en Doc D / system / tone_config.
- [ ] Few-shot library per creador actualizada.
- [ ] SafetyFilter live (reemplaza M1+M2).
- [ ] LengthRegenFallback live (reemplaza M6).
- [ ] CCEE composite Iris ≥ 68.0 y Stefano ≥ 66.5.
- [ ] `rule_violation_rate` dashboards live.
- [ ] Runbook `safety_filter.md` publicado.
- [ ] Retrospective docs/sprint5_planning/ARC4_retrospective.md.
- [ ] ~700 LOC removidos (git diff evidence).
