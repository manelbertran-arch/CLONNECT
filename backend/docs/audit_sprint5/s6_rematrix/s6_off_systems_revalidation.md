# S6 Re-Matriz — Fase 7: Revalidación Sistemas OFF

> **Scope:** 5 sistemas desactivados en CCEE. Evaluación causa (arquitectural vs intrínseca vs modelo-dependiente) y recomendación exclusiva por sistema.
> **Baseline:** W8 Fase C + Sprint 5 decision matrix (`docs/audit_sprint5/s5_off_components_decision_matrix.md`)
> **Branch:** `audit/s6-rematrix` | **Fecha:** 2026-04-21

---

## Resumen Ejecutivo

| Sistema | Flag | Δ Medido | Causa | Recomendación |
|---------|------|----------|-------|---------------|
| ECHO Engine | `ENABLE_ECHO` | -0.40 | **Intrínseca** (conflicto identidad con Doc D) | MANTENER OFF HASTA POST-FT |
| Gold Examples | `ENABLE_GOLD_EXAMPLES` | -0.70 | **Mixta** (bugs P1 + diseño sin exclusión mutua) | REVALIDAR TRAS FIX |
| Lead Categorizer v2 | `ENABLE_LEAD_CATEGORIZER` | -0.30 | **Intrínseca** (redundante con Conv State #9) | MANTENER OFF |
| SBS/PPA | `ENABLE_SCORE_BEFORE_SPEAK` + `ENABLE_PPA` | neutro | **Arquitectural** (T5.1 bypass enmascaró valor) | REVALIDAR TRAS FIX |
| Blacklist Replacement | `ENABLE_BLACKLIST_REPLACEMENT` | nunca medido | **Desconocida** (sin CCEE) | MANTENER OFF |

**Distribución de recomendaciones:** 2× REVALIDAR TRAS FIX, 1× MANTENER OFF HASTA POST-FT, 2× MANTENER OFF.

**Top hallazgo:** SBS/PPA es el candidato más prometedor para revalidación. T5.1 (bypass de M3+M4+M5, Δ combinado = -11.50) probablemente enmascaró su valor real. Coste de fix bajo, potencial alto.

---

## OFF.1 — ECHO Engine (Relationship Adapter behavioral mode)

### Qué es

ECHO NO es el Echo Detector (M5-alt, Jaccard similarity en postprocessing). ECHO = modo comportamental completo del Relationship Adapter:
- Temperature 0.6-0.8 por categoría de lead
- `max_tokens` 150-300 por categoría
- Tone/sales_push instrucciones textuales por lead (`RELATIONAL_PROFILES`)
- Prohibiciones por lead category

**Ubicación:** `services/relationship_adapter.py:69-180` (RELATIONAL_PROFILES), `:250-304` (adapt method)

### Estado actual

- **Flag:** `ENABLE_ECHO=false` en `config/env_ccee_gemma4.sh:45` y variantes
- **Δ medido:** -0.40 composite en CCEE Sprint 5
- **Mitigación existente:** `has_doc_d=True` activa data-only mode (`relationship_adapter.py:284-287`). En este modo, ECHO solo inyecta datos per-lead (nombre, memoria, commitments) — sin instrucciones de tono/estilo.

### Análisis de causa

**INTRÍNSECA con mitigación parcial existente.**

El conflicto fundamental: RELATIONAL_PROFILES define comportamiento por categoría de lead (tone "profesional-cercano", prohibitions, prompt_instructions con 50-100 tokens por perfil). Doc D define identidad del creator. Cuando ambos están activos, el modelo recibe instrucciones de tono contradictorias — ECHO dice "Sé profesional pero cercano" mientras Doc D dice "Habla como Iris habla". Esto es exactamente lo que CLAUDE.md prohíbe: reescribir señales de identidad.

El `has_doc_d` data-only mode ya mitiga el caso principal (creators con Doc D). Pero:
1. El mode switch es todo-o-nada — no hay granularidad entre "datos puros" y "instrucciones completas"
2. Los parámetros LLM (temperature, max_tokens) siguen aplicándose incluso en data-only mode
3. El Δ=-0.40 se midió con has_doc_d activado para Iris — es decir, incluso en data-only mode regresa

**¿Mitigable por ARC1/ARC2/ARC3?**
- ARC1 (BudgetOrchestrator): No resuelve. El conflicto no es de tokens sino de semántica — instrucciones contradictorias dentro del presupuesto asignado.
- ARC2 (anti-echo + normalization): No resuelve. ECHO opera pre-generation (inyecta en prompt), no post-generation.
- ARC3 (Doc D distillation): DEFERRED. Si Doc D se destila con parámetros de adaptación per-lead integrados, ECHO podría eliminarse. Pero ARC3 está pausado (Δ=-10.0 en H-Turing con distillation).

**¿Mitigable post-fine-tuning?**
Sí. Con fine-tuning, el modelo internaliza la identidad del creator. Las adaptaciones per-lead (temperatura, max_tokens, tone per lead category) dejan de competir con señales de identidad in-context. ECHO podría reactivarse con valor para adaptar la respuesta al tipo de lead sin confundir la voz del creator.

### Evidencia

```
services/relationship_adapter.py:69-91    — RELATIONAL_PROFILES["nuevo"] con prompt_instructions
services/relationship_adapter.py:284-287  — has_doc_d data-only mode
config/env_ccee_gemma4.sh:45              — ENABLE_ECHO=false
Fase 3 A.6 (s6_group_A_prompt_injection.md:326-336) — Doc D × ECHO downgraded to Tipo 3
```

### Recomendación: MANTENER OFF HASTA POST-FT

**Justificación:** Causa intrínseca — adaptación per-lead compite con identidad pre-FT. has_doc_d mitiga parcialmente pero Δ sigue negativo. Post-fine-tuning el conflicto desaparece porque el modelo ya no necesita señales de identidad in-context para mantener la voz.

---

## OFF.2 — Gold Examples (few-shot style injection)

### Qué es

Inyecta ejemplos de estilo del creator (few-shot) en el prompt de generación, seleccionados por pgvector similarity sobre la tabla `gold_examples`. Los ejemplos se filtran por intent, relationship_type, lead_stage, y language.

**Ubicación:** `core/dm/phases/generation.py:245-282` (injection point), `services/gold_examples_service.py` (retrieval)

### Estado actual

- **Flag:** `ENABLE_GOLD_EXAMPLES=false` en `config/env_ccee_gemma4.sh:118`
- **Δ medido:** -0.70 composite en CCEE Sprint 5
- **Bugs P1 corregidos post-medición:** (1) double-confidence multiplication en scoring, (2) ejemplos contaminados purgados de la tabla

### Análisis de causa

**MIXTA: bugs P1 + diseño sin exclusión mutua.**

**Componente bug (ya corregido):** Los dos bugs P1 explicaban parte de la regresión. El double-confidence scoring inflaba la similaridad de ejemplos irrelevantes, y los ejemplos contaminados (respuestas con tono chatbot, no del creator) inyectaban estilo incorrecto. Ambos fueron corregidos post-Sprint 5.

**Componente diseño (no corregido):** W8 finding 2.6 identificó que Gold Examples y Creator Style Loader (#25) inyectan estilo en paralelo sin exclusión mutua:
- Creator Style Loader: personality_docs → sección CRITICAL en prompt con Doc D completo
- Gold Examples: gold_examples → `=== EJEMPLOS DE ESTILO DEL CREATOR ===` sección separada

Ambos representan la voz del creator pero con fuentes distintas (Doc D descriptivo vs. ejemplos concretos). Sin guard de exclusión, el modelo recibe instrucciones duplicadas potencialmente incoherentes. Fase 6 (s6_group_DE_identity_scoring.md) documentó que StyleRetriever (#28, actualmente OFF) tiene la misma fuente (FeedbackCapture → gold_examples) — si ambos se activan simultáneamente, triple inyección.

**Cross-refs intra-S6:**
- Fase 6 D.2: PersonaCompiler → Creator Style Loader chain — Gold Examples operan en paralelo a esta chain
- Fase 3 A.12: Gold Examples inyectan en generation.py — no pasan por BudgetOrchestrator (ARC1 no los gestiona)
- CLAUDE.md identity preservation: los ejemplos son señales de identidad (few-shots) — no deben comprimirse ni reescribirse, pero SÍ necesitan deduplicación con Creator Style Loader

**¿Mitigable por ARC1/ARC2/ARC3?**
- ARC1: Parcialmente. Podría asignar budget compartido Style+Examples, pero el guard de exclusión mutua es lógica de negocio, no de presupuesto.
- ARC2: No relevante (pre-generation).
- ARC3: No resuelve directamente. Doc D distillation no afecta la tabla gold_examples.

**Fix necesario antes de revalidar:**
1. **Guard de exclusión mutua:** Si Creator Style Loader inyecta Doc D (has_doc_d=True), Gold Examples debe limitarse a ejemplos que complementen (no dupliquen) el estilo ya presente. Implementar como filtro: skip examples cuyo embedding sea >0.85 similar al Doc D existente.
2. **Verificar bugs P1 corregidos:** Confirmar que double-confidence y purga de contaminados están en prod.

### Evidencia

```
core/dm/phases/generation.py:245-282     — injection point con ENABLE_GOLD_EXAMPLES guard
config/env_ccee_gemma4.sh:118            — ENABLE_GOLD_EXAMPLES=false
Fase 6 D.2 (s6_group_DE_identity_scoring.md) — PersonaCompiler → Creator Style Loader chain
Fase 3 A.12 (s6_group_A_prompt_injection.md) — Gold Examples en generation, fuera de ARC1
W8 finding 2.6 — dual few-shot injection sin exclusión mutua
```

### Recomendación: REVALIDAR TRAS FIX

**Justificación:** Los bugs P1 ya están corregidos. Falta implementar guard de exclusión mutua (evitar dual injection con Creator Style Loader). Una vez implementado, re-medir con CCEE 50×3+MT. El valor teórico de few-shot concretos es alto — los bugs y el diseño sin guard explican el Δ=-0.70, no la técnica en sí.

**Prerrequisitos:**
1. Implementar guard exclusión mutua Gold Examples × Creator Style Loader
2. Confirmar bugs P1 en prod (double-confidence, purga)
3. CCEE 50×3+MT con guard activo

---

## OFF.3 — Lead Categorizer v2 (5-level funnel classification)

### Qué es

Clasifica cada lead en 5 categorías (NUEVO / INTERESADO / CALIENTE / CLIENTE / FANTASMA) basándose en los últimos 12 mensajes + estado de cliente. El resultado se inyecta como `lead_stage` en `core/dm/helpers.py:96-105`.

**Ubicación:** `core/dm/helpers.py:85-116` (injection + fallback), `core/lead_categorizer.py` (classifier)

### Estado actual

- **Flag:** `ENABLE_LEAD_CATEGORIZER=false` en `config/env_ccee_gemma4.sh:103`. Default `true` en feature_flags.
- **Δ medido:** -0.30 composite en CCEE Sprint 5
- **Fallback activo:** Cuando OFF, `get_lead_stage()` usa lógica simple basada en `purchase_intent_score` thresholds (líneas 109-116): ≥0.7 = CALIENTE, ≥0.4 = INTERESADO, else NUEVO.

### Análisis de causa

**INTRÍNSECA: redundancia funcional con Conv State #9.**

**Redundancia con Conv State (#9):** Conv State ya produce una clasificación de fase conversacional (presentación → interés → objeciones → cierre) que el modelo usa para decidir comportamiento. Lead Categorizer produce una segunda clasificación (NUEVO/INTERESADO/CALIENTE/CLIENTE/FANTASMA) que semánticamente solapa:
- Conv State "interés" ≈ Lead Categorizer "INTERESADO"
- Conv State "cierre" ≈ Lead Categorizer "CALIENTE"/"CLIENTE"
- Conv State "presentación" ≈ Lead Categorizer "NUEVO"

El modelo recibe dos señales de "dónde está este lead" con taxonomías distintas, sin arbitraje. Fase 5 (s6_group_C_detection.md) documentó que Conv State × Scorer (C.8) ya es un Tipo 1 cuando contradicen sell/don't-sell. Añadir Lead Categorizer crea una tercera señal de fase que amplifica la fragmentación.

**Componente arquitectural:** Sin gating condicional — Lead Categorizer se ejecuta siempre que está ON, sin importar si Conv State ya clasificó. ARC1 podría evitar redundancia si ambos compitieran por el mismo slot. Pero el fix es mínimo: si Conv State ya proporciona fase conversacional, Lead Categorizer no aporta información incremental significativa.

**¿Mitigable por ARC1/ARC2/ARC3?**
- ARC1: Podría limitar que solo uno de los dos (Conv State o Lead Categorizer) inyecte fase. Pero eso no resuelve la redundancia conceptual — simplemente la oculta.
- ARC2/ARC3: No relevantes.

**Valor incremental sobre fallback:** El fallback simple (purchase_intent_score thresholds) es funcional y no introduce señales contradictorias. El valor incremental del categorizer completo (12 mensajes + LLM) es bajo dado que Conv State ya cubre la necesidad.

### Evidencia

```
core/dm/helpers.py:85-116             — injection point + fallback logic
config/env_ccee_gemma4.sh:103         — ENABLE_LEAD_CATEGORIZER=false ("interfería −0.30")
Fase 5 C.8 (s6_group_C_detection.md) — Conv State × Scorer Tipo 1
core/feature_flags.py                 — default true (production ON, CCEE OFF)
```

### Recomendación: MANTENER OFF

**Justificación:** Causa intrínseca. Redundante con Conv State #9 — ambos clasifican fase del lead con taxonomías distintas, sin arbitraje. El fallback simple (purchase_intent_score thresholds) cubre la necesidad sin introducir señales contradictorias. El Δ=-0.30 refleja el coste real de la redundancia. No hay fix técnico que elimine la redundancia conceptual — tendría que reescribirse como extensión de Conv State, lo cual es un rediseño, no un fix.

**Nota:** En producción `ENABLE_LEAD_CATEGORIZER` defaults to `true` (feature_flags.py). Si se decide mantener OFF formalmente, cambiar default a `false` y confirmar que el fallback simple no regresa.

---

## OFF.4 — SBS/PPA (Score Before Speak + Post Persona Alignment)

### Qué es

Dos sistemas acoplados en `core/reasoning/ppa.py`:
1. **PPA (Post Persona Alignment):** Genera respuesta → recupera ejemplos similares de persona → refina si misaligned. 1 LLM call extra.
2. **SBS (Score Before Speak):** Extiende PPA — si alignment score < 0.7, regenera con retry. 2 LLM calls extra máximo.

Pipeline: score alignment → si ≥ 0.7 → done (0 calls). Si < 0.7 → PPA refine (1 call) → re-score. Si still < 0.7 → retry at different temperature (2 calls max).

**Ubicación:** `core/reasoning/ppa.py:1-50` (flags + constants), postprocessing step 7a4 (`core/dm/phases/postprocessing.py:276-329`)

### Estado actual

- **Flags:** `ENABLE_SCORE_BEFORE_SPEAK=false`, `ENABLE_PPA=false` en `config/env_ccee_gemma4.sh:120-121`
- **Δ medido:** neutro (0.00) en mediciones limitadas. **NUNCA medido con CCEE 50×3+MT completo.**
- **Tests:** Fallos conocidos en test suite (pre-existing)

### Análisis de causa

**ARQUITECTURAL: T5.1 probablemente enmascaró valor.**

**T5.1 — SBS bypass de M3+M4+M5 (Fase 4):** SBS regenera respuesta en step 7a4 (postprocessing.py:276-329), DESPUÉS de que anti-echo corrections (A2b, A2c, A3), output validator (7a), response fixes (7a2), blacklist replacement (7a2b3), y question removal (7a2c) ya se ejecutaron. La respuesta regenerada reemplaza `response_content` enteramente — los pasos protectivos NO se re-ejecutan.

Impacto: M3+M4+M5 son las 3 mutaciones más PROTECTIVAS del pipeline (Δ combinado = -11.50 si se desactivan, datos ARC4). SBS bypass significa que ~30% de respuestas (las que triggean retry) pierden estas protecciones. El resultado "neutro" probablemente refleja: valor de SBS alignment + daño de bypass protectivo ≈ 0.

**¿Mitigable por ARC?**
- **Sí, directamente por fix de ordering.** No requiere ARC1/ARC2/ARC3. El fix es reordenar la cadena:
  - **Current:** A2b → A2c → A3 → 7a → 7a2 → 7a2b3 → 7a2c → **SBS** → 7b → 7c → 7b2
  - **Proposed:** **SBS** → A2b → A2c → A3 → 7a → 7a2 → 7a2b3 → 7a2c → 7b → 7c → 7b2
  - Alternativa: mantener SBS donde está pero re-run A2b-7a2c después de regeneración.

**Valor teórico:** SBS/PPA alinean la respuesta con la persona del creator antes de enviar — exactamente lo que el pipeline necesita. El scoring de alignment es un quality gate natural. Con T5.1 corregido, el valor real debería ser positivo.

**Coste de fix:** Bajo. Es reordenamiento de steps en `postprocessing.py`, no rediseño. Los tests fallidos son un prerequisito adicional pero independiente.

### Evidencia

```
core/reasoning/ppa.py:1-26             — definición PPA/SBS, flags, threshold 0.7
core/dm/phases/postprocessing.py:276-329 — SBS step 7a4 (después de anti-echo chain)
Fase 4 T5.1 (s6_group_B_postprocessing.md:74-110) — SBS bypass analysis
config/env_ccee_gemma4.sh:120-121      — ENABLE_SCORE_BEFORE_SPEAK=false, ENABLE_PPA=false
```

### Recomendación: REVALIDAR TRAS FIX

**Justificación:** Causa arquitectural clara (T5.1 ordering bug). El valor teórico es alto — alignment scoring como quality gate es exactamente lo que falta en el pipeline. "Neutro" probablemente refleja valor + daño de bypass cancelándose. Con T5.1 corregido, debería medir positivo.

**Prerrequisitos (en orden):**
1. Fix T5.1: mover SBS antes de anti-echo chain O re-run protections después de SBS regeneration
2. Fix tests fallidos de SBS/PPA
3. CCEE 50×3+MT con ordering corregido

**Prioridad:** ALTA. Candidato más prometedor de los 5 OFF. Fix de bajo coste, potencial alto, valor teórico claro.

---

## OFF.5 — Blacklist Replacement (Doc D vocabulary enforcement)

### Qué es

Reemplaza palabras prohibidas y emojis prohibidos en la respuesta generada con equivalentes aprobados. Lee §4.2 del Doc D del creator para determinar blacklist y approved terms. Solo opera sobre address terms cortos (≤2 palabras) — frases largas de service-bot no se reemplazan (indicarían fallo de estilo más profundo).

**Ubicación:** `services/calibration_loader.py:208-280` (apply_blacklist_replacement), `core/dm/phases/postprocessing.py:234-245` (step 7a2b3)

### Estado actual

- **Flag:** `ENABLE_BLACKLIST_REPLACEMENT=false` en `config/env_ccee_gemma4.sh:127` (comentario: "unaudited")
- **Δ medido:** NUNCA. Sin medición CCEE ni de otro tipo.
- **En producción:** flag defaults to what feature_flags sets. El comentario "unaudited" indica que se desactivó por precaución, no por regresión medida.

### Análisis de causa

**DESCONOCIDA: nunca medido.**

No hay evidencia empírica de impacto positivo ni negativo. El sistema es conceptualmente sólido — reemplazar "compa" por "nena" si el Doc D del creator lo prohíbe es una corrección legítima de estilo. Pero:

1. **Riesgo bajo de daño:** Opera post-generation sobre tokens individuales (address terms, emojis). No modifica estructura ni contenido semántico.
2. **Riesgo de edge cases:** Regex sobre stems con elongación (`stem + tail + "+s?\b"`) podría matchear falsos positivos en idiomas con inflección. Ejemplo: si "bro" está en blacklist, ¿matchea "brother"? El `\b` boundary debería prevenirlo, pero no hay tests que lo confirmen.
3. **Dependencia de Doc D:** Si el creator no tiene Doc D o §4.2 está vacío, `_load_creator_vocab()` retorna vacío y es un no-op. Seguro por diseño.

**¿Mitigable por ARC?** No aplica — no hay regresión que mitigar. La pregunta es si vale la pena medir.

**Análisis coste-beneficio de medición:**
- Coste de CCEE 50×3+MT: ~2h setup + runtime
- Valor esperado: bajo. El sistema modifica 1-5 tokens por respuesta en el mejor caso. Impacto en métricas composite probablemente dentro del margen de error.
- Riesgo de activar sin medir: bajo. Es post-processing correctivo sobre vocabulary específica, no modifica comportamiento del modelo.

### Evidencia

```
services/calibration_loader.py:208-280   — apply_blacklist_replacement implementation
core/dm/phases/postprocessing.py:234-245 — step 7a2b3 injection point
config/env_ccee_gemma4.sh:127            — ENABLE_BLACKLIST_REPLACEMENT=false ("unaudited")
```

### Recomendación: MANTENER OFF

**Justificación:** Nunca medido, pero riesgo bajo. No vale CCEE 50×3+MT dedicado — el impacto esperado es marginal (1-5 tokens por respuesta). Si se decide medir en el futuro, puede incluirse como variable secundaria en otro CCEE run. Conservative default: OFF hasta que se incluya en un batch de mediciones.

**Alternativa considerada:** REVALIDAR TRAS FIX — pero no hay fix necesario (el código funciona). La razón del OFF es "unaudited", no "broken". Medir por medir consume recursos sin expectativa de impacto significativo.

---

## Matriz de Dependencias Cruzadas

```
                   ECHO   GoldEx   LeadCat   SBS/PPA   Blacklist
ECHO (OFF.1)         —      —        ↔ [1]      —          —
Gold Examples (OFF.2) —      —        —          —          —
Lead Categorizer (OFF.3) ↔ [1]  —      —         —          —
SBS/PPA (OFF.4)      —      ↔ [2]    —          —         ↔ [3]
Blacklist (OFF.5)    —      —        —         ↔ [3]       —
```

**[1] ECHO × Lead Categorizer:** ECHO usa lead_status (que viene de Lead Categorizer si ON, o fallback si OFF) para seleccionar RELATIONAL_PROFILE. Si ambos se reactivan simultáneamente, Lead Categorizer alimenta ECHO. Pero ambos están OFF y se recomiendan mantener OFF (ECHO hasta post-FT, Lead Categorizer permanente).

**[2] SBS/PPA × Gold Examples:** SBS alignment scoring evalúa si la respuesta matchea la persona del creator. Gold Examples inyectan few-shots que definen esa persona. Si Gold Examples mejoran la generation, SBS debería necesitar menos retries. **Recomendación: revalidar SBS primero (prerequisitos más claros), luego Gold Examples.**

**[3] SBS/PPA × Blacklist:** SBS regeneration bypass (T5.1) también bypasea Blacklist Replacement (step 7a2b3). Con T5.1 corregido, Blacklist se aplicaría a todas las respuestas incluyendo las regeneradas por SBS. Bajo impacto — Blacklist modifica pocos tokens.

---

## Comparación con W8 Baseline

| Sistema | W8 Status | Sprint 5 Status | S6 Status | Cambio |
|---------|-----------|-----------------|-----------|--------|
| ECHO | Reportado como "conflicto con Doc D" | OFF (Δ=-0.40) | OFF (causa intrínseca confirmada, post-FT) | Precisión +1 (causa clasificada) |
| Gold Examples | Reportado como "dual injection" (W8 2.6) | OFF (Δ=-0.70, bugs P1) | REVALIDAR (bugs fixed, falta guard) | Actionable |
| Lead Categorizer | No en scope W8 | OFF (Δ=-0.30) | OFF (causa intrínseca: redundancia Conv State) | Cerrado |
| SBS/PPA | No en scope W8 | OFF (neutro) | REVALIDAR (T5.1 bypass identificado Fase 4) | Actionable |
| Blacklist | No en scope W8 | OFF ("unaudited") | OFF (nunca medido, bajo impacto esperado) | Sin cambio |

**Valor agregado S6:** W8 solo cubría ECHO y Gold Examples. S6 añade análisis de causa para los 5 OFF, identifica T5.1 como enmascarador del valor de SBS/PPA, y establece prerrequisitos concretos para las 2 revalidaciones.

---

## Orden de Ejecución Recomendado

Si se decide actuar sobre las revalidaciones:

1. **SBS/PPA** — Fix T5.1 ordering → fix tests → CCEE 50×3+MT. Prioridad ALTA.
2. **Gold Examples** — Implementar guard exclusión mutua → confirmar bugs P1 → CCEE 50×3+MT. Prioridad MEDIA.
3. (Post-FT) **ECHO** — Revalidar cuando fine-tuning elimine dependencia de Doc D in-context.
4. **Lead Categorizer** — No revalidar. Redundante con Conv State.
5. **Blacklist** — Incluir como variable secundaria en próximo CCEE batch si hay oportunidad.

---

*Fase 7 completada. 5 sistemas OFF analizados: 2 REVALIDAR TRAS FIX (SBS/PPA alta prioridad, Gold Examples media), 1 MANTENER OFF HASTA POST-FT (ECHO), 2 MANTENER OFF (Lead Categorizer intrínseco, Blacklist sin medición). SBS/PPA es el candidato más prometedor — T5.1 bypass probablemente enmascaró valor real.*
