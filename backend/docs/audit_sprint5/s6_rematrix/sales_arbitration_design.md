# Sales Arbitration — Diseño Arquitectónico (Fase 2)

**Branch de trabajo:** main (documento solo, sin código)
**Fecha:** 2026-04-21
**Contexto previo:** s6_rematrix_decisions.md — 3 contradicciones Tipo 1 activas (R.4, R.5, C.8)

---

## 0. Problema a resolver

Cuatro sistemas independientes emiten directivas de venta sin arbitraje:

| Sistema | Mecanismo | Posición en recalling | Activo cuando |
|---------|-----------|----------------------|---------------|
| DNA Engine | Texto: "NUNCA vender" | Posición 2 | `relationship_type = FAMILIA / INTIMA` |
| Conv State | Texto: "Menciona el producto / Da el link" | Posición 3 | `phase = PROPUESTA / CIERRE` |
| Frustration | Texto: "No vendas ahora" | Posición 5 | `frustration_level ≥ 2` |
| Scorer | Bool: elimina productos del prompt | No en recalling (data-level) | `score > 0.8` |

El assembly en `context.py:1353` es concatenación pura — ningún sistema tiene conocimiento de los demás. El LLM resuelve ad-hoc conflictos que deberían ser invariantes del sistema.

---

## 1. Pregunta 1 — Scope del árbitro

### Las tres opciones

**Opción A — Solo prompt (minimal)**
El árbitro reescribe los parámetros de texto inyectados (`state_context`, `frustration_note`). Conv State sigue avanzando fases de forma independiente.

- Esfuerzo: 1 día
- Blast radius: solo `context.py` (capa assembly)
- Problema crítico: **Conv State stall**. Para un lead FAMILIA en fase PROPUESTA, el árbitro suprime la instrucción de venta pero Conv State sigue en PROPUESTA. `_determine_transition()` (línea 403 de `conversation_state.py`) avanza a CIERRE solo cuando detecta `intent=interest_strong` o keywords "link/comprar". Si el bot nunca menciona productos (por el árbitro), Conv State nunca avanza → PROPUESTA infinita. El árbitro vence la incoherencia textual pero crea una incoherencia de estado persistida en DB.
- Veredicto: **insuficiente como solución final**, válido como MVP de emergencia.

**Opción B — Prompt + transiciones**
El árbitro bloquea la transición a PROPUESTA para leads FAMILIA/INTIMA. `_determine_transition()` en `conversation_state.py` consulta al árbitro.

- Esfuerzo: 3–4 días
- Blast radius: `context.py` + `conversation_state.py` (transiciones, tests de máquina de estado)
- Problema: Conv State también gestiona comportamientos no-venta (CUALIFICACION, DESCUBRIMIENTO). Tocarlo introduce riesgo en flujos que actualmente funcionan. La función `_determine_transition()` no recibe signals de DNA ni Frustration — habría que pasarlos, cambiando la signatura de múltiples funciones.
- Veredicto: **arquitectónicamente correcto pero blast radius alto** para v1.

**Opción C — "Estado efectivo" desacoplado**
El árbitro emite un `SellDirective` que se usa para:
1. Reemplazar la instrucción de Conv State en el prompt (como Opción A)
2. Emitir `effective_sell_mode` a `cognitive_metadata` y observabilidad

Conv State nominal sigue avanzando (PROPUESTA, CIERRE), pero su instrucción de venta se reemplaza en el texto. La telemetría registra tanto `conv_state_phase` (nominal) como `sell_directive` (efectivo). Esto expone la divergencia de forma medible sin tocar la máquina de estado.

- Esfuerzo: 1.5–2 días
- Blast radius: solo `context.py`
- Ventaja sobre A: la divergencia es visible en métricas. Cuando en prod se vea `conv_state_phase=PROPUESTA + sell_directive=NO_SELL` con frecuencia alta para FAMILIA leads, tendremos evidencia cuantificada para justificar Opción B en una iteración futura.
- El stall de PROPUESTA sigue existiendo, pero es **ahora medible y acotado** (FAMILIA + INTIMA son una minoría del volumen de conversaciones).

### Recomendación: **Opción C**

Justificación con evidencia del código:

1. Todas las contradicciones activas (R.4, R.5, C.8) son fallos de la capa de prompt, no de la máquina de estado. El LLM recibe instrucciones contradictorias. La Opción C elimina la contradicción textual.

2. El stall de PROPUESTA (limitación de Opción A/C vs B) afecta solo a leads donde `relationship_type ∈ {FAMILIA, INTIMA}`. Estos leads NO deberían estar recibiendo sales funnel tracking en absoluto — Conv State fue diseñado para leads de venta. El fix correcto es excluirlos del tracking en una iteración futura (bajo riesgo, alcance limitado).

3. La Opción B requiere pasar signals de DNA y Frustration a `_determine_transition()`, cambiando la firma de `update()` en `StateManager`. Eso crea una dependencia circular: `conversation_state.py` dependería de sistemas que actualmente son agnósticos al estado de Conv State.

---

## 2. Pregunta 2 — Inputs completos del árbitro

### Inputs de la propuesta inicial (revisados)

| Input propuesto | Fuente en código | Tipo real | Corrección |
|----------------|-----------------|-----------|------------|
| `dna_relationship_type` | `dm_agent_context_integration.py:167` | `str` (enum semántico) | Taxon: FAMILIA, INTIMA, AMISTAD_CERCANA, AMISTAD_CASUAL, CLIENTE, COLABORADOR, DESCONOCIDO |
| `conv_phase` | `conversation_state.py:24–32` | `ConversationPhase` enum | Fases reales: INICIO, CUALIFICACION, DESCUBRIMIENTO, PROPUESTA, OBJECIONES, CIERRE, ESCALAR |
| `frustration_level` | `frustration_detector.py:390–397` | `int` 0–3 | Correcto |
| `relationship_score` | `relationship_scorer.py:89–137` | `float` 0.0–1.0 | Correcto |
| `suppress_products` | `relationship_scorer.py:135` | `bool` (`score > 0.8`) | Correcto, but see P7 |

### Inputs adicionales identificados en la auditoría

**`soft_suppress` (bool, score entre 0.6 y 0.8):**
`relationship_scorer.py:136`: `soft_suppress=(0.6 < total <= 0.8)`. Actualmente ignorado por el pipeline. Necesario para inferir el estado SOFT_MENTION de forma determinista en vez de depender del LLM.

**`sensitive_action_required` (str | None):**
Los casos de `SensitiveDetector` que NO hacen hard-exit del pipeline son relevantes para el árbitro:
- `action_required="no_pressure_sale"` (MINOR): no venta de presión, pero conversación sigue
- `action_required="empathetic_response"` (EATING_DISORDER, ECONOMIC_DISTRESS): foco en empatía, no venta

Los casos `escalate_immediate`, `block_response`, `no_response` salen del pipeline ANTES de que el árbitro corra — no llegan nunca al arbiter. Este input reemplaza el `sensitive_detected: bool` de la propuesta original, que era demasiado impreciso (no distingue severidad).

**`has_pending_sales_commitment` (bool):**
Commitment Tracker (`commitment_tracker.py:247–301`) rastrea promesas pendientes del bot. Si el bot prometió "te paso el link del curso" y ahora `frustration_level = 2`, el árbitro necesita saber que hay un compromiso de venta pendiente para no violarlo silenciosamente. Fuente: `commitment_text` en `context.py:946–956`. Para el árbitro, extraer el bool `any("link" in c or "curso" in c for c in pending_commitments)`.

**`intent_type` (str) — RECOMENDADO pero no bloqueante para v1:**
El clasificador simple de `intent_classifier.py` ya corre en Phase 1. Señales como `OBJECTION` o `EXIT_INTENT` deberían inhibir `SELL_ACTIVELY`. Sin embargo, Conv State ya maneja transiciones basadas en intent — añadir intent al árbitro podría crear doble-lógica. Dejarlo para v2.

### Inputs finales del árbitro v1

```python
@dataclass
class SellArbiterInputs:
    dna_relationship_type: str           # "FAMILIA", "INTIMA", "AMISTAD_CERCANA", etc.
    conv_phase: str                      # "PROPUESTA", "CIERRE", "CUALIFICACION", etc.
    frustration_level: int               # 0, 1, 2, 3
    relationship_score: float            # 0.0–1.0
    suppress_products: bool              # score > 0.8
    soft_suppress: bool                  # 0.6 < score ≤ 0.8
    sensitive_action_required: str | None  # "no_pressure_sale", "empathetic_response", None
    has_pending_sales_commitment: bool   # compromiso de venta pendiente
```

---

## 3. Pregunta 3 — Jerarquía de precedencia

### Jerarquía propuesta y análisis de casos incorrectos

```
P1. sensitive_action_required in ("no_pressure_sale", "empathetic_response")  →  NO_SELL
P2. frustration_level >= 2                                                      →  NO_SELL
P3. dna_relationship_type in ("FAMILIA", "INTIMA")                             →  NO_SELL
P4. suppress_products = True  AND  dna NOT in NO_SELL set                      →  REDIRECT
P5. soft_suppress = True  OR  dna_relationship_type = "AMISTAD_CERCANA"        →  SOFT_MENTION
P6. conv_phase in ("PROPUESTA", "CIERRE")  AND  ningún bloqueante anterior      →  SELL_ACTIVELY
P7. default                                                                     →  SOFT_MENTION
```

**¿Por qué P2 (frustración) puede ser ≥ P3 (DNA)?**
Evidencia: frustration_level=2 indica que el lead está activamente molesto EN ESTE MOMENTO. Un CLIENTE (no FAMILIA) frustrado que recibe una mención de producto tiene una experiencia peor que un FAMILIA que no la recibe. La frustración es señal del estado emocional actual; DNA es señal de tipo de relación histórica. Ambas a P2/P3 en la jerarquía es correcto — en la práctica, un FAMILIA con frustration=2 activa P3 (más restrictivo gana), y un CLIENTE con frustration=2 activa P2.

**Caso donde la jerarquía original sería incorrecta:**

*Caso A: FAMILIA lead + frustration=1 (leve)*
- Jerarquía original: frustración no llega al umbral, pero DNA FAMILIA sí → NO_SELL (P3 gana). Correcto.

*Caso B: CLIENTE + PROPUESTA + frustration=2 + has_pending_sales_commitment=True*
- P2 gana → NO_SELL. Pero el árbitro emite NO_SELL puro, y el bot puede ignorar el compromiso de venta pendiente.
- Solución: cuando `has_pending_sales_commitment=True` + `NO_SELL`, añadir texto al frustration_note: "Tienes un compromiso pendiente. Menciona que lo enviarás cuando sea buen momento, sin presionar ahora."
- Este es el caso R.9. No requiere un nuevo estado del árbitro, solo una modificación del texto de ayuda emitido con NO_SELL.

*Caso C: AMISTAD_CERCANA + PROPUESTA + frustration=0 + suppress_products=False + soft_suppress=False*
- P3 no aplica (AMISTAD_CERCANA no está en el NO_SELL set)
- P4 no aplica (suppress=False)
- P5 aplica (AMISTAD_CERCANA) → SOFT_MENTION
- ¿Es correcto? Sí: con un buen amigo, mencionas la solución con naturalidad, no vendes agresivamente con link de compra.

*Caso D: CLIENTE + CIERRE + score=0.85 (suppress_products=True)*
- Contradicción C.8: Conv State dice "Da el link" pero no hay productos en el prompt.
- Jerarquía: P4 activa → REDIRECT. El árbitro suprime la instrucción de CIERRE y reemplaza con "Redirige la conversación naturalmente hacia otro valor".
- Sin árbitro: LLM recibe "Da el link" pero no tiene datos de productos → puede alucinar un link, decir "no tengo info", o actuar de forma inconsistente. **REDIRECT es el estado que resuelve C.8 explícitamente.**

**Corrección a jerarquía original:**
La propuesta del usuario ponía `Sensitive` en P1 de forma correcta en intención, pero los casos hard-sensitive (SELF_HARM, THREAT, PHISHING, SPAM) salen del pipeline *antes* de que el árbitro corra. El árbitro solo ve los casos soft-sensitive (MINOR → `no_pressure_sale`, EATING_DISORDER / ECONOMIC_DISTRESS → `empathetic_response`). La jerarquía corregida lo refleja.

---

## 4. Pregunta 4 — Output space del árbitro

### Enum final

```python
class SellDirective(Enum):
    SELL_ACTIVELY    = "SELL_ACTIVELY"   # Presenta producto + link. Máxima intención de venta.
    SOFT_MENTION     = "SOFT_MENTION"    # Menciona la solución sin presión. Sin link si no solicita.
    NO_SELL          = "NO_SELL"         # Foco en empatía/ayuda. No hay referencia a producto.
    REDIRECT         = "REDIRECT"        # Conv State dice vender, pero no hay productos. Pivota.
```

### ¿Hace falta WAIT?

**No para v1.** El estado WAIT requeriría persistencia entre turnos ("no vendas en este turno, reintenta en el siguiente"). Esto crea estado adicional en DB y lógica de retry que no existe actualmente. El comportamiento "esperar un turno" emerge naturalmente:

- Turno N: frustration=2 → NO_SELL. El bot no menciona productos.
- Turno N+1: el lead responde positivamente → frustration probablemente cae a 0 o 1. Conv State puede avanzar. Árbitro re-evalúa y puede emitir SOFT_MENTION o SELL_ACTIVELY.

La naturaleza stateless del árbitro (re-evalúa cada turno desde cero) produce el comportamiento de WAIT de forma orgánica.

**Caso de `has_pending_sales_commitment`:** No requiere WAIT como estado, sino un modifier de texto dentro de NO_SELL (ver Pregunta 3, Caso B).

---

## 5. Pregunta 5 — Modelo de integración

### Las tres opciones formalizadas

**Pull model:**
```python
# Cada sistema consulta al árbitro
if arbiter.should_inject_sell(inputs) == SELL_ACTIVELY:
    state_context = state_manager.build_enhanced_prompt(...)
else:
    state_context = ""  # o versión sin instrucción de venta
```
- Pro: lógica de cada sistema no cambia
- Con: árbitro llamado N veces (4+), posibles inconsistencias si inputs cambian entre llamadas (improbable pero posible)

**Push model:**
```python
# Árbitro produce todo el texto final
sell_block = arbiter.produce_sell_instruction(inputs)
# ... reemplaza state_context, frustration_note
```
- Pro: control centralizado total
- Con: arbiter debe conocer el formato de output de cada sistema (acoplamiento alto). Si DNA cambia su formato, el arbiter se rompe.

**Opción recomendada — Pre-assembly interception (variante del Hybrid):**
```python
# En _assemble_context_legacy(), antes de _build_recalling_block():
_directive = resolve_sell_intent(SellArbiterInputs(...))

# Modificar parámetros según directiva, antes de pasar a _build_recalling_block()
_state_for_recalling = _apply_directive_to_state(state_context, _directive)
_frustration_for_recalling = _apply_directive_to_frustration(frustration_note, _directive, _directive_aux_text)

# Los demás parámetros no cambian: dna, memory, context_notes
recalling = _build_recalling_block(
    ...,
    state=_state_for_recalling,
    frustration_note=_frustration_for_recalling,
    ...
)
```

**Por qué este modelo:**
1. `_build_recalling_block()` no cambia. Ni su firma ni su lógica interna.
2. Árbitro se llama una sola vez con todos los inputs disponibles.
3. Solo dos variables son modificadas por el árbitro (`state` y `frustration_note`) — el resto del recalling (DNA, Memory, Context Notes) es read-only para el árbitro.
4. DNA no es modificado intencionalmente: el texto "NUNCA vender" de DNA sirve como redundancia útil que refuerza el NO_SELL. Duplicar no daña.
5. Si flag=OFF, el bloque de intercepción se salta completamente — rollback exacto.

El modelo pull añade complejidad sin necesidad (el árbitro ya tiene todos los inputs en un solo punto). El push crea acoplamiento con el formato interno de cada sistema. La intercepción pre-assembly es el sweet spot.

---

## 6. Pregunta 6 — Feature flag strategy

### Análisis de las opciones

**Opción (a) — Global ON/OFF:**
- `ENABLE_SALES_ARBITRATION=true`
- Pro: simplicidad, observabilidad clara, rollback en segundos
- Con: no permite A/B por creator

**Opción (b) — Por creator:**
- `ARBITRATION_CREATORS=iris_bertran,stefano_bonanno`
- Pro: A/B testing por creator type (Iris = personal/social, Stefano = más business)
- Con: complejidad de configuración, Railway no tiene gestión granular de env vars por creator

**Opción (c) — Solo cuando detecta conflicto:**
- Activar árbitro solo cuando ≥2 sistemas divergen
- Pro: mide impacto incremental exactamente en casos problemáticos
- Con: requiere un pre-detector ligero de conflicto antes de invocar el árbitro completo. En la práctica, ese pre-detector es un árbitro simplificado — complejidad duplicada.

### Recomendación: **Opción (a) global, con rollout en dos fases**

Fase 3a (lanzamiento): `ENABLE_SALES_ARBITRATION=false` por defecto. Activar en staging via Railway, monitor 24h, luego activar en prod.

Fase 3b (steady state): `ENABLE_SALES_ARBITRATION=true` como default. Railway env var solo para emergencia OFF.

La opción (c) es intelectualmente elegante pero sobre-ingenierizada para v1. El árbitro tiene costo computacional mínimo (pure Python, sin LLM, sin DB en el hot path) — correrlo en cada turno es negligible. Si en el futuro hay evidencia de que Iris y Stefano necesitan comportamientos distintos, añadir per-creator en v2.

---

## 7. Pregunta 7 — Threshold 0.8 del Scorer

### Análisis

`relationship_scorer.py:135`:
```python
suppress_products=(total > 0.8),
soft_suppress=(0.6 < total <= 0.8),
```

Los thresholds 0.8 y 0.6 son magic numbers sin calibración empírica documentada. No hay tests de decisión que los validen contra datos reales de conversaciones.

### Tres opciones

**Opción (a) — Heredar el magic number:**
- El árbitro usa `suppress_products` y `soft_suppress` como booleans (ya calculados)
- No toca los thresholds
- Pro: zero blast radius adicional
- Con: deuda técnica heredada. Si los thresholds están mal calibrados, el árbitro los propaga.

**Opción (b) — Configurable por creator via env var:**
- `SCORER_SUPPRESS_THRESHOLD=0.8`, `SCORER_SOFT_THRESHOLD=0.6` en Railway
- Pro: permite ajuste operacional sin deploy
- Con: más env vars, calibración manual sin datos

**Opción (c) — Eliminar threshold y usar score continuo:**
- El árbitro recibe `relationship_score: float` y aplica sus propias reglas
- Permite umbrales más sofisticados (ej: AMISTAD_CERCANA + score > 0.5 = NO_SELL, pero CLIENTE + score > 0.5 = SOFT_MENTION)
- Pro: más expesivo, potencialmente más preciso
- Con: reinventa lógica del Scorer. Duplica responsabilidad.

### Recomendación: **Opción (a) con nota técnica + Opción (b) como configuración mínima**

Los booleans `suppress_products` y `soft_suppress` son abstracciones válidas. El árbitro no debería re-implementar la lógica de scoring. Sin embargo, los thresholds deberían ser expuestos como env vars para poder ajustarlos basándose en datos de observabilidad post-deploy.

Acción concreta: en `relationship_scorer.py`, reemplazar los literales 0.8 y 0.6 con `float(os.getenv("SCORER_SUPPRESS_THRESHOLD", "0.8"))` y `float(os.getenv("SCORER_SOFT_THRESHOLD", "0.6"))`. Esto es una línea de código, no es el scope del árbitro pero debe hacerse en paralelo.

**Una nota sobre la deuda X.2:** El scorer extrae `memory_facts` desde `memory_context` via regex de line-splitting que no entiende el formato XML `<memoria tipo="...">` de ARC2. Cuando ARC2 cambie su formato, el scorer perderá esa señal silenciosamente. Esto es independiente del árbitro pero debe estar en el backlog.

---

## 8. Pregunta 8 — Observabilidad

### Métricas requeridas por decisión del árbitro

```python
# Emitir a cognitive_metadata (persiste en DB via ARC5 TypedMetadata cuando esté activo)
# Y via emit_metric() para dashboards en tiempo real

cognitive_metadata["arbitration"] = {
    # La directiva emitida
    "sell_directive": directive.value,       # "SELL_ACTIVELY", "NO_SELL", etc.

    # Señal que causó la decisión (la más restrictiva que ganó)
    "blocking_signal": "dna_familia",        # "frustration_2", "scorer_suppress", etc. None si SELL_ACTIVELY

    # Inputs que el árbitro vio
    "inputs": {
        "dna_type": dna_relationship_type,
        "conv_phase": conv_phase,
        "frustration_level": frustration_level,
        "rel_score": round(relationship_score, 2),
        "suppress": suppress_products,
        "soft_suppress": soft_suppress,
        "sensitive": sensitive_action_required,
        "pending_commit": has_pending_sales_commitment,
    },

    # ¿Había conflicto entre sistemas?
    "conflict_detected": bool,               # True si ≥2 sistemas divergían
    "conflict_signals": list[str],           # Ej: ["conv_state_sell", "dna_no_sell"]

    # ¿Qué habrían inyectado los 4 sistemas sin árbitro?
    "counterfactual": {
        "conv_state_would": "SELL",          # "SELL" | "NO_SELL" | "NEUTRAL"
        "dna_would": "NO_SELL",
        "frustration_would": "NO_SELL",
        "scorer_would": "NEUTRAL",
    }
}
```

### Por qué `counterfactual` es crítico

El counterfactual permite calcular, post-deploy, cuántos turnos habría habido una contradicción sin el árbitro. Si en una semana el árbitro resuelve 200 conflictos donde `conv_state_would=SELL + dna_would=NO_SELL`, eso es 200 oportunidades de alucinación evitadas. Esta métrica justifica el árbitro con datos propios.

También permite el A/B test sin necesidad de dos deployments: con flag ON, se puede simular qué habría pasado con flag OFF observando el counterfactual.

---

## 9. Pregunta 9 — Testabilidad

### Plan de testing

**Nivel 1 — Tests unitarios (tabla de decisión completa)**

`tests/compactor/` → `tests/arbitration/test_sell_arbiter_decisions.py`

```python
@pytest.mark.parametrize("inputs,expected_directive,expected_blocking_signal", [
    # P1: Sensitive soft cases
    (SellArbiterInputs(sensitive_action_required="no_pressure_sale", conv_phase="PROPUESTA", ...), NO_SELL, "sensitive_no_pressure"),
    (SellArbiterInputs(sensitive_action_required="empathetic_response", conv_phase="PROPUESTA", ...), NO_SELL, "sensitive_empathetic"),
    # P2: Frustration
    (SellArbiterInputs(frustration_level=2, conv_phase="PROPUESTA", dna_relationship_type="CLIENTE", ...), NO_SELL, "frustration_2"),
    (SellArbiterInputs(frustration_level=3, conv_phase="PROPUESTA", dna_relationship_type="CLIENTE", ...), NO_SELL, "frustration_3"),
    (SellArbiterInputs(frustration_level=1, conv_phase="PROPUESTA", dna_relationship_type="CLIENTE", suppress_products=False, soft_suppress=False, ...), SELL_ACTIVELY, None),
    # P3: DNA no-sell
    (SellArbiterInputs(dna_relationship_type="FAMILIA", conv_phase="PROPUESTA", frustration_level=0, ...), NO_SELL, "dna_familia"),
    (SellArbiterInputs(dna_relationship_type="INTIMA", conv_phase="PROPUESTA", frustration_level=0, ...), NO_SELL, "dna_intima"),
    # P4: Redirect
    (SellArbiterInputs(suppress_products=True, conv_phase="PROPUESTA", dna_relationship_type="CLIENTE", frustration_level=0, ...), REDIRECT, "scorer_suppress"),
    (SellArbiterInputs(suppress_products=True, conv_phase="CIERRE", dna_relationship_type="CLIENTE", frustration_level=0, ...), REDIRECT, "scorer_suppress"),
    # P5: Soft mention
    (SellArbiterInputs(soft_suppress=True, conv_phase="PROPUESTA", dna_relationship_type="CLIENTE", frustration_level=0, suppress_products=False, ...), SOFT_MENTION, None),
    (SellArbiterInputs(dna_relationship_type="AMISTAD_CERCANA", conv_phase="PROPUESTA", frustration_level=0, suppress_products=False, soft_suppress=False, ...), SOFT_MENTION, None),
    # P6: Sell actively
    (SellArbiterInputs(conv_phase="PROPUESTA", dna_relationship_type="DESCONOCIDO", frustration_level=0, suppress_products=False, soft_suppress=False, sensitive_action_required=None, ...), SELL_ACTIVELY, None),
    (SellArbiterInputs(conv_phase="CIERRE", dna_relationship_type="CLIENTE", frustration_level=0, suppress_products=False, soft_suppress=False, sensitive_action_required=None, ...), SELL_ACTIVELY, None),
    # P7: Default (no-sell phase)
    (SellArbiterInputs(conv_phase="CUALIFICACION", dna_relationship_type="DESCONOCIDO", frustration_level=0, suppress_products=False, soft_suppress=False, sensitive_action_required=None, ...), SOFT_MENTION, None),
    # Triple conflict: todos los blockers activos → más restrictivo gana
    (SellArbiterInputs(dna_relationship_type="FAMILIA", frustration_level=3, suppress_products=True, conv_phase="PROPUESTA", ...), NO_SELL, "dna_familia"),  # P3 > P4
    # Commitment + NO_SELL: verifica aux_text
    (SellArbiterInputs(frustration_level=2, has_pending_sales_commitment=True, conv_phase="PROPUESTA", dna_relationship_type="CLIENTE", ...), NO_SELL, "frustration_2"),  # + check aux_text
])
def test_arbiter_decision_table(inputs, expected_directive, expected_blocking_signal):
    result = resolve_sell_intent(inputs)
    assert result.directive == expected_directive
    assert result.blocking_signal == expected_blocking_signal
```

**Nivel 2 — Tests de integración (prompt assembly)**

`tests/arbitration/test_arbitration_prompt_integration.py`

Escenarios reales de los 3 conflictos Tipo 1:

- R.4: FAMILIA + PROPUESTA → verificar que `state_context` en recalling NO contiene "Menciona el producto"
- R.5: Frustration=2 + PROPUESTA → verificar que `state_context` no contiene sell instructions
- C.8: score=0.9 + PROPUESTA → verificar REDIRECT (instrucción de pivote presente, no "Da el link")
- Triple conflict: FAMILIA + frustration=2 + score=0.9 → NO_SELL limpio

Usar mocks para DB (igual que `tests/compactor/test_shadow_log_uuid_resolution.py`).

**Nivel 3 — Regression flag test**

`tests/arbitration/test_arbitration_flag_off.py`

Con `ENABLE_SALES_ARBITRATION=false`, el recalling ensamblado debe ser byte-identical al actual. Capturar output actual (golden file), activar flag=true, comparar con golden. Si hay diferencia con flag=false, el rollback no es limpio.

**Nivel 4 — CCEE comparativo (post-deploy)**

- Baseline: 50 casos × 3 runs con flag=false (uso del current main)
- Treatment: 50 casos × 3 runs con flag=true
- Métricas a vigilar: S3 Strategic Alignment (principal afectado), H Turing Test, v5 composite
- Threshold de regresión: treatment_composite < baseline_composite - 2.0 (2σ del σ_intra=0.42 de DeepInfra)
- Expectativa: S3 mejora (menos conflictos sell/no-sell); H estable o mejora; v5 neutral o +

---

## 10. Pregunta 10 — Migración y rollback

### ¿Flag OFF revierte exactamente al comportamiento actual?

**Sí, si el diseño es correcto.** La intercepción pre-assembly se estructura como:

```python
if flags.enable_sales_arbitration:
    _state_for_recalling, _frustration_for_recalling = _apply_sell_directive(
        state_context, frustration_note, resolve_sell_intent(inputs)
    )
else:
    _state_for_recalling = state_context
    _frustration_for_recalling = frustration_note
```

El árbitro no escribe nada a DB (stateless). El único efecto es la modificación de dos strings en memoria que se pasan a `_build_recalling_block()`. Flag=false → cero diferencia.

**Tests de regresión de flag:** El Nivel 3 del plan de testing valida esto formalmente antes del deploy.

### Plan para datos "corruptos"

El árbitro v1 es puramente stateless — lee signals de DB pero no escribe. El único registro es en `cognitive_metadata` (campo nuevo `"arbitration"` dentro del JSON existente). Al hacer rollback (flag=false), el campo `cognitive_metadata["arbitration"]` sigue apareciendo en datos históricos pero no afecta comportamiento. No hay plan de limpieza necesario — los campos adicionales en JSON son backwards-compatible.

Si en el futuro el árbitro escribe estado (ej: "este lead está en FAMILY_MODE, saltarse Conv State PROPUESTA"), ese estado requeriría migración. Para v1: prohibir escrituras de estado desde el árbitro.

### Cómo distinguir ruido de regresión real

De la evidencia del Variance Study (commit 0c3fbd6f): σ_intra DeepInfra ≈ 0.42 puntos. Una variación de ±1.0 en composite sobre 3 runs = ruido estadístico normal.

**Protocolo de regresión:**
1. Si treatment_composite < baseline_composite - 1.5: **amarillo** — segunda ronda de 3 runs antes de decidir
2. Si treatment_composite < baseline_composite - 2.5: **rojo** — `ENABLE_SALES_ARBITRATION=false` inmediato, análisis de causa
3. Si S3 cae > 5 puntos: **rojo** independientemente del composite (S3 = Strategic Alignment es el proxy directo de la calidad de la señal de venta)
4. Si H Turing cae > 8 puntos: **rojo** (precedente: distill H -10 fue regresión real)

Tiempo mínimo de observación antes de marcar verde: 48h + ≥ 500 conversaciones con el flag activo.

---

## 11. Comparación de las tres opciones de diseño

### Opción 0: Status quo (baseline)

| Dimensión | Valor |
|-----------|-------|
| Contradicciones activas | 3 Tipo 1 (R.4, R.5, C.8) |
| LLM resuelve conflictos | Sí, ad-hoc, no determinista |
| Coherencia estado Conv State | Sí (Conv State avanza con datos reales) |
| Alucinación de productos en C.8 | Posible (LLM recibe "Da el link" sin datos de producto) |
| Esfuerzo | 0 días |
| Blast radius | 0 |
| Observable | No (conflictos son invisibles) |
| **Cuándo elegir** | Si CCEE demuestra que los conflictos no tienen impacto medible |

**Veredicto:** La alucinación potencial en C.8 (Conv State CIERRE + Scorer suppress) es un riesgo de reputación: el bot inventa o cita links incorrectos. Esto no requiere CCEE para ser un problema — es correcto por construcción. Status quo no es viable.

---

### Opción 1: Árbitro de prompt mínimo (Opción A + C parcial)

- Prompt-only override, sin emitir `effective_sell_mode`, sin observabilidad del conflicto
- 1 día de implementación
- Resuelve las 3 contradicciones textualmente
- No registra qué habría pasado sin el árbitro
- Conv State stall no medible (no se sabe cuántas veces FAMILIA lleva N turnos en PROPUESTA)

**Cuándo elegir:** Si tiempo es crítico y se puede iterar rápido.

---

### Opción 2: Árbitro con effective_sell_mode + observabilidad **(RECOMENDADO)**

- Pre-assembly interception con `SellDirective` enum completo
- Emite `cognitive_metadata["arbitration"]` con counterfactual
- `emit_metric("arbitration_decision", ...)` para dashboards
- 2 días de implementación
- Resuelve las 3 contradicciones
- Mide cuántos conflictos se resuelven por turno (justifica el feature con datos propios)
- Habilitado por `ENABLE_SALES_ARBITRATION=false` por defecto en primer deploy

---

### Opción 3: Árbitro coherente con transiciones Conv State (Opción B)

- Bloquea PROPUESTA para FAMILIA/INTIMA en `_determine_transition()`
- Resuelve el stall de PROPUESTA
- 4–6 días de implementación
- Blast radius alto (Conv State usada en todo el pipeline)
- Requiere tests extensos de máquina de estado
- **Cuándo elegir:** Después de que Opción 2 esté en prod y los datos confirmen que el stall de PROPUESTA para FAMILIA es frecuente (> 5% de conversaciones activas). Eso convierte el problema en prioritario con evidencia.

---

### Tabla comparativa

| Criterio | Status quo | Opción 1 (minimal) | Opción 2 (effective_mode) | Opción 3 (full coherence) |
|----------|-----------|-------------------|--------------------------|--------------------------|
| Resuelve R.4/R.5/C.8 | ✗ | ✓ | ✓ | ✓ |
| Elimina alucinación C.8 | ✗ | ✓ | ✓ | ✓ |
| Conv State stall FAMILIA | N/A | ✗ presente | ✗ presente pero medible | ✓ |
| Observabilidad conflictos | ✗ | ✗ | ✓ counterfactual | ✓ |
| Rollback limpio | N/A | ✓ | ✓ | ⚠️ (estado en DB) |
| Esfuerzo | 0 | 1d | 2d | 4–6d |
| Blast radius | 0 | bajo | bajo | medio-alto |
| Tests necesarios | 0 | 20 | 50+ | 80+ |
| Iterable hacia Opción 3 | - | sí | **sí, base natural** | - |

---

## 12. Tabla de decisión completa (matriz inputs → output)

```
sensitive_action_required    frustration  dna_type         suppress  soft_suppress  conv_phase         → DIRECTIVE          blocker
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
"no_pressure_sale"           any          any              any       any            any                → NO_SELL            sensitive_soft
"empathetic_response"        any          any              any       any            any                → NO_SELL            sensitive_empathetic
None                         2 or 3       any              any       any            any                → NO_SELL            frustration_2+
None                         0 or 1       FAMILIA/INTIMA   any       any            any                → NO_SELL            dna_no_sell
None                         0 or 1       other            True      any            any                → REDIRECT           scorer_suppress
None                         0 or 1       other            False     True           any                → SOFT_MENTION       scorer_soft
None                         0 or 1       AMISTAD_CERCANA  False     False          any                → SOFT_MENTION       dna_soft
None                         0 or 1       other            False     False          PROPUESTA/CIERRE   → SELL_ACTIVELY      —
None                         0 or 1       other            False     False          other              → SOFT_MENTION       —
```

### Casos compuestos críticos

| Escenario | Inputs activos | Resultado | Por qué |
|-----------|---------------|-----------|---------|
| R.4 — FAMILIA+PROPUESTA | DNA=FAMILIA, phase=PROPUESTA | NO_SELL | P3 > P6 |
| R.5 — Frustration+PROPUESTA | frustration=2, phase=PROPUESTA | NO_SELL | P2 > P6 |
| C.8 — Scorer+PROPUESTA | suppress=True, phase=PROPUESTA | REDIRECT | P4 > P6 |
| Triple | DNA=FAMILIA, frustration=3, suppress=True | NO_SELL | P3 win (P3 ≥ P4) |
| R.9 — Pending commit+Frustration | frustration=2, pending_commit=True | NO_SELL + aux_text | P2 win, commitment aux |
| Happy path | Desconocido, phase=PROPUESTA, frustration=0 | SELL_ACTIVELY | P6 |
| Amigo cercano no frustrado | AMISTAD_CERCANA, phase=PROPUESTA, frustration=0 | SOFT_MENTION | P5 |
| CLIENTE en fase temprana | CLIENTE, phase=CUALIFICACION, frustration=0 | SOFT_MENTION | P7 default |
| Menor en PROPUESTA | sensitive=no_pressure_sale, phase=PROPUESTA | NO_SELL | P1 |

---

## 13. Diseño recomendado detallado (Opción 2)

### Interfaces públicas

```python
# core/generation/sell_arbiter.py  (archivo nuevo)

@dataclass(frozen=True)
class SellArbiterInputs:
    dna_relationship_type: str
    conv_phase: str
    frustration_level: int
    relationship_score: float
    suppress_products: bool
    soft_suppress: bool
    sensitive_action_required: str | None
    has_pending_sales_commitment: bool

@dataclass(frozen=True)
class SellArbiterResult:
    directive: SellDirective
    blocking_signal: str | None           # None cuando SELL_ACTIVELY
    conflict_detected: bool
    conflict_signals: list[str]
    counterfactual: dict[str, str]
    aux_text: str | None                  # Texto adicional para frustration_note en casos R.9

def resolve_sell_intent(inputs: SellArbiterInputs) -> SellArbiterResult:
    """Pure function, no DB access, no side effects. O(1)."""
    ...
```

### Punto de integración en context.py

```python
# core/dm/phases/context.py, en _assemble_context_new() o _assemble_context_legacy()
# Después de calcular state_context, frustration_note, _rel_score:

if flags.enable_sales_arbitration:
    _arb_inputs = SellArbiterInputs(
        dna_relationship_type=_dna_type or "DESCONOCIDO",
        conv_phase=_conv_phase_str,
        frustration_level=_fl,
        relationship_score=_rel_score.score if _rel_score else 0.0,
        suppress_products=_rel_score.suppress_products if _rel_score else False,
        soft_suppress=_rel_score.soft_suppress if _rel_score else False,
        sensitive_action_required=_sensitive_action if _sensitive_triggered_soft else None,
        has_pending_sales_commitment=_has_pending_sales_commit,
    )
    _arb_result = resolve_sell_intent(_arb_inputs)
    state_context = _suppress_sell_in_state(state_context, _arb_result.directive)
    frustration_note = _merge_arb_into_frustration(frustration_note, _arb_result)
    inp.cognitive_metadata["arbitration"] = _arb_result_to_dict(_arb_result)
    emit_metric("arbitration_decision", inp.cognitive_metadata["arbitration"])
```

### Invariantes del árbitro

1. **Stateless**: no escribe a DB, no tiene side effects observables fuera del valor de retorno
2. **Pure function**: mismos inputs → mismo output (determinista)
3. **No-op when disabled**: `if not flags.enable_sales_arbitration: return` antes del bloque de integración
4. **Fail-silent**: si el árbitro lanza excepción (shouldn't happen dado que es pure), catch + log WARNING, usar estado sin árbitro
5. **No toca DNA, Memory, Context Notes**: solo `state_context` y `frustration_note`

---

## 14. Estimación de esfuerzo Fase 3

| Tarea | Esfuerzo | Riesgo |
|-------|---------|--------|
| `core/generation/sell_arbiter.py` (pure function + dataclasses) | 3h | bajo |
| Tabla de decisión como código (jerarquía P1→P7) | 1h | bajo |
| Integración en `context.py` (7 nuevas líneas aprox.) | 1h | bajo (bien delimitado) |
| `_suppress_sell_in_state()` helper | 1h | bajo |
| Observabilidad: `_arb_result_to_dict()` + `emit_metric()` | 1h | bajo |
| Tests unitarios (tabla de decisión, ~50 casos parametrizados) | 3h | bajo |
| Tests de integración prompt assembly (R.4, R.5, C.8, triple) | 2h | bajo-medio |
| Test de regression con flag=false (golden file) | 1h | bajo |
| CCEE baseline + treatment (50×3) | 2h activo + 3h wall clock | bajo |
| **Total** | **~15h (~2 días)** | **bajo** |

### Pre-requisito no bloqueante

El fix del Scorer (exponer thresholds como env vars) puede hacerse en paralelo en 30 minutos. No bloquea la implementación del árbitro — el árbitro consume los booleans `suppress_products` y `soft_suppress`, no los thresholds directamente.

### Secuencia de implementación recomendada

1. Crear `core/generation/sell_arbiter.py` + tests unitarios (tabla completa en verde)
2. Integrar en `context.py` (7 líneas) + test flag=false (golden file)
3. Tests de integración (prompt assembly R.4, R.5, C.8)
4. Deploy con `ENABLE_SALES_ARBITRATION=false` → verificar zero diff en staging
5. Activar `ENABLE_SALES_ARBITRATION=true` → CCEE 50×3 en staging
6. Si CCEE green → activar en prod + monitor 48h
