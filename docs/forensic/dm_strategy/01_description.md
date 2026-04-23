# Fase 1 — Descripción y valor del sistema `dm_strategy`

**Artefacto:** `backend/core/dm/strategy.py` (117 LOC)
**Fecha:** 2026-04-23
**Branch:** `forensic/dm-strategy-20260423`
**Callsite productivo:** `backend/core/dm/phases/generation.py:194-203` (único)
**Capa pipeline:** PRE-LLM hot path, **Step 5b** de `phase_llm_generation` (Phase 4 del pipeline DM)
**Flag env:** — (sin flag, hardcoded ON)
**Estado Railway:** ON (sin gate)

---

## 1. Qué hace funcionalmente

`strategy.py` expone una única función pública `_determine_response_strategy(...)` que **clasifica la conversación entrante en una estrategia conversacional** y devuelve un string de instrucción al LLM (un "hint" de ~1-3 oraciones) que se **inyecta como parte del prompt final** antes del mensaje del usuario.

El hint NO le dice al LLM *qué decir*, sino *cómo aproximar la respuesta*: qué tono tomar, qué reglas seguir, qué patrones evitar (ej. "no vendas", "no preguntes X", "ultra-breve", "saluda brevemente").

Es un **router de política conversacional** (dialogue policy) basado en reglas deterministas sobre 8 señales heterogéneas (message text, intent, relationship, first-message flag, friend flag, interests, lead stage, history length).

## 2. Las estrategias y cuándo se disparan (orden de precedencia)

La función implementa un **decision tree por prioridades estrictas**: la primera rama que matchea gana y retorna; todas las demás se ignoran. Precedencia de arriba hacia abajo:

| # | Estrategia (token en hint) | Condición disparo | Reglas inyectadas al LLM |
|---|----------------------------|-------------------|--------------------------|
| P1 | `PERSONAL-FAMILIA` | `relationship_type ∈ {"FAMILIA","INTIMA"}` | NO vender, responder al contenido concreto, compartir detalles reales, ultra-breve 5-30 chars, directness |
| P2 | `PERSONAL-AMIGO` | `is_friend == True` | No vender, responder concreto, ultra-breve, compartir detalles |
| P3 | `BIENVENIDA + AYUDA` | `is_first_message ∧ ("?" ∈ msg ∨ help_signals ∈ msg)` | Saludar breve + responder la necesidad en la misma respuesta |
| P3b | `BIENVENIDA` | `is_first_message` (sin ayuda) | Saludo breve + pregunta en qué puedes ayudar, NO saludo largo |
| P4 | `RECURRENTE` | `history_len ≥ 4 ∧ ¬is_first_message` | NO saludar como primera vez, NO "¿qué te llamó la atención?", apelativos (nena/tia/flor/cuca/reina), NUNCA "flower" |
| P5 | `AYUDA` | `help_signals ∈ msg` (returning user) | Responder directo, no saludo genérico, preguntar detalles si no sabes |
| P6 | `VENTA` | `intent_value ∈ {purchase, pricing, product_info, purchase_intent, product_question}` | Info concreta (precio/contenido/duración) + CTA suave al final |
| P7 | `REACTIVACIÓN` | `lead_stage == "fantasma"` | Alegrarse de verle, no agresivo con la venta |
| — | `default` | ninguna match | Retorna `""` (sin hint, conversación natural) |

Nota: el plan de usuario y el scout previo hablan de "6 estrategias P1-P6". Verificado por `grep ^    if` sobre `strategy.py`, el código real expone **7 `if` top-level + 1 `if` nested (L67) + default** = 7 ramas activables + default:

```
L39   if relationship_type in ("FAMILIA","INTIMA")                 → P1 PERSONAL-FAMILIA
L49   if is_friend                                                  → P2 PERSONAL-AMIGO
L65   if is_first_message                                           → P3 BIENVENIDA (L67 nested: "?" | help_signals → BIENVENIDA+AYUDA)
L82   if history_len >= 4 and not is_first_message                  → P4 RECURRENTE
L94   if any(signal in msg_lower for signal in help_signals)        → P5 AYUDA
L102  if intent_value in ("purchase","pricing","product_info",
                          "purchase_intent","product_question")     → P6 VENTA
L110  if lead_stage in ("fantasma",)                                → P7 REACTIVACIÓN
L117  return ""                                                     → default
```

Scout anterior numeró P1-P6 omitiendo **P7 REACTIVACIÓN**. Numeración definitiva para el resto del forense: **7 ramas + default**, indexadas P1…P7.

### 2.1 Ramas muertas en producción

Desde commit `9752df768` (2026-03-27), el callsite (`generation.py:197,199`) **hardcodea** `relationship_type=""` y `is_friend=False`. Esto **deshabilita P1 FAMILIA y P2 AMIGO** de forma permanente aunque `context.py` sí calcula correctamente ambos upstream (`context.py:1221-1222`).

**Estrategias vivas hoy:** P3 BIENVENIDA, P4 RECURRENTE, P5 AYUDA, P6 VENTA, P7 REACTIVACIÓN.
**Estrategias muertas:** P1 PERSONAL-FAMILIA, P2 PERSONAL-AMIGO.

El commit fue deliberado (ver `context.py:1220`: "_rel_type kept empty so strategy.py receives no relationship signal") con motivación "limpiar conflicto con Context Detection", pero **nunca se midió en CCEE pre/post**. El eje estilo de las ramas PERSONAL (brevedad 5-30, concreción, directness, compartir detalles — 4 de 6 reglas) quedó **huérfano 27 días** sin cobertura equivalente en ningún otro lugar del pipeline.

## 3. Valor aportado al pipeline (hipótesis)

**H1 — El hint de estrategia reduce doom loops y modos-off-brand**: sin hint, el LLM tiende a saludos genéricos largos ("¡Hola! Gracias por escribirme..."), preguntas de cold-lead ("¿Qué te llamó la atención?"), o modo-venta reflejo ante cualquier señal comercial. El hint inserta un *prior* que acota el espacio de respuestas plausibles.

**H2 — P4 RECURRENTE es la rama de mayor volumen y mayor valor**: la mayoría de mensajes en Iris vienen de leads con historial (`history_len ≥ 4`). Sin la rama RECURRENTE, el modelo re-abriría conversaciones como si fuera nuevas (observado pre-`f561819c`).

**H3 — P3 BIENVENIDA previene sobrevender en el primer mensaje**: sin guía, el LLM ofrece producto en la bienvenida, comportamiento no-humano.

**H4 — P1/P2 (si estuvieran vivas) moverían B2 Persona Fidelity y S1 Style en leads clasificados como FAMILIA/AMIGO**: las 4 reglas de estilo (brevedad, concreción, directness, compartir) son las que más diferencian a Iris (creadora) del modo genérico de Gemini. Al estar muertas, el sistema depende de Doc D + few-shots para transportar ese estilo, lo que funciona peor en mensajes cortos y casuales.

**H5 — Inyección post-`prompt_parts` puede interferir con few-shots**: el hint se concatena *después* de `preference_profile_section` + `gold_examples_section` y *antes* del mensaje del usuario (`generation.py:292-303`). Su peso relativo depende del tamaño de Doc D.

## 4. Inputs que lo disparan

El callsite le pasa **8 parámetros** extraídos del `ContextBundle` ya construido por `phase_context`:

| # | Parámetro | Origen real en `ContextBundle` | Valor pasado hoy |
|---|-----------|--------------------------------|------------------|
| 1 | `message` | `phase_llm_generation(... message ...)` argumento | ✅ literal del usuario |
| 2 | `intent_value` | `context.intent_value` | ✅ clasificado por Intent Classifier |
| 3 | `relationship_type` | Debería venir de `context.rel_type` | ❌ **hardcoded `""`** |
| 4 | `is_first_message` | `follower.total_messages ≤ 1 ∧ ¬history` | ✅ derivado en línea |
| 5 | `is_friend` | Debería venir de `context.is_friend` | ❌ **hardcoded `False`** |
| 6 | `follower_interests` | `follower.interests` | ✅ (no usado en función) |
| 7 | `lead_stage` | `current_stage` (de `context.current_stage`) | ✅ |
| 8 | `history_len` | `len(history)` | ✅ |

`follower_interests` se recibe pero **nunca se lee** dentro de la función → parámetro dead-weight.

## 5. Outputs y efectos

`_determine_response_strategy(...)` → `str` (vacío o con contenido).

Si no vacío:
1. **Metadata cognitiva** (`generation.py:205`): `cognitive_metadata["response_strategy"] = strategy_hint.split(".")[0]` — primer fragmento hasta el primer punto (token descriptivo de la estrategia, ej. "ESTRATEGIA: RECURRENTE").
2. **Log estructurado** (`generation.py:206`): `logger.info(f"[STRATEGY] {strategy_hint.split('.')[0]}")`.
3. **Inyección en prompt final** (`generation.py:292-293`): `prompt_parts.append(strategy_hint)` dentro del bloque de construcción de prompt, antes del mensaje del usuario y después de `preference_profile` y `gold_examples`.

**Efecto secundario:** el string íntegro (no solo el token) pasa al LLM como guía de comportamiento.

## 6. Fase pipeline donde interviene

Pipeline DM V2 (`DMResponderAgentV2`), secuencia real ejecutada por `phase_llm_generation` (`generation.py:163-314`):

```
[phase_intent]       → intent_value
[phase_detection]    → frustration_level, sensitive_action flags
[phase_context]      → ContextBundle (rel_type, is_friend, history, user_context, ...)
[phase_llm_generation]
    Step 5a: alias context fields
    Step 5b: _determine_response_strategy()  ← strategy.py AQUÍ
    Step 5c: (learning_rules ya removido)
    Step 5d: preference_profile
    Step 5e: gold_examples (few-shot)
    Step 6:  build full_prompt = [profile, examples, strategy_hint, q_hint, message]
    Step 7:  LLM call (Gemini / fallback chain)
[phase_guardrails]
[phase_post_process]
```

**Strategy se ejecuta PRE-LLM**, después de todo el contexto y justo antes de construir el prompt final. No hay retry loop sobre su output.

## 7. Dimensiones CCEE v5 que podría mover

| Dim CCEE v5 | Nombre | Mecanismo de impacto | Signo esperado |
|-------------|--------|----------------------|----------------|
| **B2** | Persona Fidelity | Reglas P4 (apelativos, prohibir "flower", no pregunta cold-lead); P1/P2 dormidas bloquean fidelity en leads FAMILIA | **+** si se re-activa P1/P2 o se porta al resolver |
| **S1** | Style Fidelity | Brevedad "5-30 chars" (P1/P2 muertas); directness en P5 AYUDA | **+** con portado estilo al ArbitrationLayer |
| **S3** | Strategic Alignment | Router explícito = alinea estrategia elegida con intent/stage | **+/0** (ya activo parcialmente) |
| **L1** | Persona Tone | Apelativos P4 ("nena/tia/flor/cuca/reina"); prohibir "flower" | **+** |
| **H1** | Turing Test (global) | Composite de B2+S1+L1 → el usuario nota lo robótico cuando faltan P1/P2 | **+** modesto con re-activación |
| **J6** | Judge Overall (composite) | Si B2/S1/L1 suben, J6 sube | **+** |
| **K2** | Knowledge Accuracy / Context Usage | P5 AYUDA y P6 VENTA fuerzan responder a la necesidad concreta | **0/+** (ya cubierto por intent) |

Nota: la **decisión CEO** (portar 4 guidelines estilo al directive del resolver S6 ArbitrationLayer cuando `directive==NO_SELL ∧ relationship_type ∈ {FAMILY, FRIEND, INTIMATE}`) es el vector principal para recuperar el impacto de P1/P2 sin restaurar el hardcoding en el callsite. Esto deja a `dm_strategy` cubriendo las 5 ramas vivas (P3-P7) y al `sell_arbitration/arbitration_layer` cubriendo el eje estilo de relaciones cercanas — cero solapamiento funcional.

---

## Resumen ejecutivo Fase 1

- `dm_strategy` es un **router de política conversacional** pre-LLM con **7 ramas** (el plan las llama "P1-P6" agrupando BIENVENIDA).
- **5 ramas vivas** en prod hoy (P3-P7). **2 ramas muertas** (P1 FAMILIA, P2 AMIGO) por hardcoding `""` / `False` desde 2026-03-27.
- El hint se **inyecta en el prompt final** entre `gold_examples` y `message`, con peso dependiente del tamaño de Doc D.
- **Impacto esperado en CCEE v5**: principalmente **B2** (persona fidelity, baseline 28.5) y **S1** (style), secundariamente **L1** y **S3**. Vía portado de guidelines estilo al ArbitrationLayer del resolver S6 (decisión CEO, evita restaurar hardcoding del callsite).
- **Baseline medición:** `tests/ccee_results/iris_bertran/baseline_post_p4_live_v52_20260422.json` — composite v5 = 67.7.
- **Riesgo arqueológico:** el commit `9752df768` desactivó dos ramas sin CCEE pre/post; la deuda ha sido **27 días sin medir**.

**STOP Fase 1.** Aguardo confirmación para proceder a Fase 2.
