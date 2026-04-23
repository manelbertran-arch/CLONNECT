# Fase 2 — Forense línea a línea de `dm_strategy`

**Archivo principal:** `backend/core/dm/strategy.py` (117 LOC, LOC útiles ~85 excluyendo docstring)
**Callsite único:** `backend/core/dm/phases/generation.py:194-203` (invocación) + `:292-293` (inyección prompt)
**Autor único de los 7 commits claves:** Manel Bertran Luque (con coautoría Claude Sonnet/Opus 4.6 en algunos)
**Fecha creación:** 2026-02-25
**Fecha último cambio funcional:** 2026-04-03 (learning_rules cleanup, no toca strategy.py)

---

## 1. Historia del archivo — 7 commits clave

Cronología de cambios funcionales en `strategy.py` y en su callsite de `generation.py`:

| SHA | Fecha | Autor | Cambio | Archivos tocados |
|-----|-------|-------|--------|------------------|
| `81467a92e` | 2026-02-25 14:11 | Manel | **Refactor inicial**: extrae `_determine_response_strategy` de `core/dm_agent_v2.py` a `core/dm/strategy.py`. 71/71 tests pass. | `core/dm/strategy.py` (new) |
| `cd33367cf` | 2026-02-25 16:06 | Manel | Callsite creado en `generation.py` (extracción de fase `phase_llm_generation`) | `generation.py:193-206` |
| `7d49b663b` | 2026-03-01 20:56 | Manel | **BUG-12**: first_message check pasa ANTES de help_signals (evita colisión "Hola, necesito ayuda"). **BUG-07**: añade `purchase_intent`, `product_question`, `pricing` al VENTA check. Agrega comentarios "Priority 2/3/4/5". | `strategy.py:56,63,64,93-107` |
| `5b1a2fbe1` | 2026-03-21 21:47 | Manel | **Hardening P1/P2** basado en LLM-judge analysis de 6 conversaciones reales: añade "5-30 chars", "directness", "compartir detalles", "no reacciones genéricas" a FAMILIA y AMIGO. | `strategy.py:41-46,51-53` + 6 few-shot examples nuevos |
| `a1ee5cd6e` | 2026-03-26 13:25 | Manel | Rework prompt building: elimina XML wrapper, mensaje puro último, `prompt_parts = []` inicialización explícita. | `generation.py:284-294` |
| **`9752df768`** | **2026-03-27 20:13** | Manel | **🔴 COMMIT CRÍTICO — desactivación P1/P2**: `_rel_type=""` en `context.py:1222`, hardcoding `relationship_type=""` y `is_friend=False` en `generation.py:197,199`. Justificación: "elimina conflicto con Context Detection". **NO acompañado de CCEE pre/post.** | `context.py:8l`, `generation.py:4l` |
| `de7c319a1` | 2026-03-29 10:26 | Manel | Bisect — disable length_hints/temp_dual/loop_detector. Cambia `is_first_message` a `(follower.total_messages ≤ 1) and not history`. | `generation.py:198,202` |
| `f561819c4` | 2026-03-29 10:47 | Manel | **P4 RECURRENTE**: añade Priority 2b (`history_len ≥ 4 ∧ ¬is_first_message`) para prevenir "¿Qué te llamó la atención?" en leads con historial. Añade `history_len` al signature. Mide 7.67 → 8.17 en Railway (σ=0.40). | `strategy.py:21,78-91` |

**Observaciones arqueológicas:**
- El eje "calidad personal" (P1 FAMILIA, P2 AMIGO) fue reforzado con cuidado en `5b1a2fbe1` (evidencia: 6 conversaciones reales judged) y desactivado 6 días después en `9752df768` sin medición.
- Tras `9752df768`, el único refuerzo de estilo conversacional en el sistema fue la rama **P4 RECURRENTE** añadida en `f561819c4`, y solo aplica a leads con historial, no a familia/amigos.
- El commit `9752df768` acompañaba un cambio en `context.py` que **restringe** `is_friend` a `score > 0.8` (antes era `>= 0.6`). Es decir, hizo dos cambios en paralelo: endurecer la definición de "friend" Y desactivar la rama. Solo uno de los dos habría sido necesario para eliminar el "conflicto con Context Detection".

---

## 2. strategy.py — forense sección por sección

### 2.1 Docstring y signature (LL1-22)

```python
"""
Response strategy determination for DM Agent V2.

Determines HOW the LLM should approach a response based on:
- Relationship type (family, friend, follower)
- Help signals in the message
- Purchase intent
- First message vs returning
- Ghost/reactivation
"""


def _determine_response_strategy(
    message: str,
    intent_value: str,
    relationship_type: str,
    is_first_message: bool,
    is_friend: bool,
    follower_interests: list,
    lead_stage: str,
    history_len: int = 0,
) -> str:
```

- **Autor:** `81467a92e` (2026-02-25) para LL1-20.
- **Cambio posterior:** `f561819c4` (2026-03-29) añadió `history_len: int = 0` (L21).
- **Convenio de tipado**: `list` sin genérico (no `list[str]`). **Smell**: `follower_interests: list` sin constraint, y **nunca se lee** dentro de la función → parámetro dead.

### 2.2 Normalización (LL36)

```python
msg_lower = message.lower().strip()
```

- Única normalización. No se normalizan acentos (importante: `help_signals` incluye "cómo" y "como hago" por eso) ni se tokeniza. Detección por substring exacta sobre `msg_lower`.

### 2.3 Rama P1 — PERSONAL-FAMILIA (LL38-47)

```python
# Priority 1: Family/close friends -> personal mode, never sell
if relationship_type in ("FAMILIA", "INTIMA"):
    return (
        "ESTRATEGIA: PERSONAL-FAMILIA. Esta persona es cercana (familia/íntimo). "
        "REGLAS: 1) NUNCA vendas ni ofrezcas productos/servicios. "
        "2) Responde al CONTENIDO concreto del mensaje, no con reacciones genéricas. "
        "3) Comparte detalles reales de tu vida si vienen al caso. "
        "4) Ultra-breve: 5-30 chars máximo. "
        "5) Si preguntan algo, responde directamente sin florituras."
    )
```

- **Disparo:** `relationship_type ∈ {"FAMILIA", "INTIMA"}`
- **Hoy:** **MUERTA** — `generation.py:197` pasa `relationship_type=""`.
- **Comentario CCEE relevante:** 5 reglas en el hint, 4 de ellas son de **estilo/brevedad** (2, 3, 4, 5). Una sola (regla 1) es política de venta.
- **Origen de las reglas:** LLM-judge analysis de 6 conversaciones personales reales (commit `5b1a2fbe1`: "bot says 'tranqui' instead of addressing actual content like lost shoes", "over-effusive emoji spam with close people — real Iris is ultra-brief", "missing context-awareness").

### 2.4 Rama P2 — PERSONAL-AMIGO (LL49-54)

```python
if is_friend:
    return (
        "ESTRATEGIA: PERSONAL-AMIGO. Esta persona es amigo/a. "
        "REGLAS: 1) No vendas. 2) Responde al contenido concreto, no genérico. "
        "3) Ultra-breve. 4) Comparte detalles si vienen al caso."
    )
```

- **Disparo:** `is_friend == True`
- **Hoy:** **MUERTA** — `generation.py:199` pasa `is_friend=False`.
- **Peculiaridad:** aunque `context.py:1221` calcula correctamente `is_friend = _rel_score.suppress_products` (True solo si score ≥ 0.8), el valor **nunca llega** a strategy porque el callsite lo sobrescribe a `False` manualmente.
- **4 reglas**, todas de estilo (brevedad, concreción, compartir) salvo la política "no vendas".

### 2.5 Vocab inline — help_signals (LL56-61)

```python
# Shared help signals used in Priority 2 and Priority 4
help_signals = [
    "ayuda", "problema", "no funciona", "no puedo", "error",
    "cómo", "como hago", "necesito", "urgente", "no me deja",
    "no entiendo", "explícame", "explicame", "qué hago", "que hago",
]
```

- **14 strings en español**, definidos inline dentro de la función (no a nivel de módulo → se re-crea la lista en cada llamada, coste trivial pero denso).
- **Bug potencial BUG-03:** 14 strings hardcoded. No cubren catalán, inglés, portugués (Iris = ES-CA, Stefano = IT). Mensajes como "help!", "ajuda", "non riesco", "ajuda-me" NO matchean.
- **Bug potencial BUG-04:** duplicado `explícame`/`explicame` y `qué hago`/`que hago` (manual accent-stripping) revela que la lógica sabe que acentos importan, pero la solución ad-hoc no escala.

### 2.6 Rama P3 — BIENVENIDA (LL63-76)

```python
# Priority 2: BUG-12 fix — First message takes priority over generic help signals
# so "Hola, necesito ayuda" gives BIENVENIDA + AYUDA, not just AYUDA
if is_first_message:
    # Check if first message contains a question or help need
    if "?" in message or any(s in msg_lower for s in help_signals):
        return (
            "ESTRATEGIA: BIENVENIDA + AYUDA. Es el primer mensaje y contiene una pregunta. "
            "Saluda brevemente y responde a su necesidad en la misma respuesta."
        )
    return (
        "ESTRATEGIA: BIENVENIDA. Primer mensaje del usuario. "
        "Saluda brevemente y pregunta en qué puedes ayudar. "
        "NO hagas un saludo genérico largo."
    )
```

- **Origen BUG-12:** commit `7d49b663b` reorganizó el orden de prioridades tras observar que "Hola, necesito ayuda" caía en AYUDA sin saludar.
- **Variante nested:** `BIENVENIDA + AYUDA` si hay `?` o `help_signals`; `BIENVENIDA` puro en otro caso.
- **Detección de pregunta robusta a ES/CA/IT** por el símbolo `"?"` (bien). Pero `help_signals` = solo español.

### 2.7 Rama P4 — RECURRENTE (LL78-91)

```python
# Priority 2b: Returning user with conversation history — prevent new-lead openers
# This fires when history is substantial enough to confirm a prior relationship.
# Prohibits "¿Que te llamó la atención?" / "Que t'ha cridat l'atenció?" patterns
# that the model uses by default for leads tagged as "nuevo" in the prompt.
if history_len >= 4 and not is_first_message:
    return (
        "ESTRATEGIA: RECURRENTE. Esta persona ya te conoce y tiene historial contigo. "
        "REGLAS CRÍTICAS: "
        "1) NO preguntes '¿Que te llamó la atención?' ni '¿Que t'ha cridat l'atenció?' ni variantes — NUNCA. "
        "2) NO saludes como si fuera la primera vez. "
        "3) Responde con naturalidad y espontaneidad usando el contexto de la conversación. "
        "4) Muestra energía y personalidad de Iris: reacciona con entusiasmo o curiosidad según el contexto, "
        "usa apelativos (nena, tia, flor, cuca, reina) — NUNCA la palabra 'flower'."
    )
```

- **Origen:** commit `f561819c4` (2026-03-29). Añadido tras observar que el modelo seguía usando cold-lead openers aunque el lead tuviera historial (porque el campo `lead.stage` estaba mal etiquetado).
- **Threshold:** `history_len >= 4` — hardcoded, no data-derived.
- **Regla 4** referencia a Iris explícitamente ("nena, tia, flor, cuca, reina" — los apelativos del calibrations/iris_bertran.json) → **viola principio de universalidad** (strategy.py debería ser agnóstico de creador).
- **Patrón anti-bug:** "NUNCA la palabra 'flower'" — evidencia que el modelo ha inventado "flower" como apelativo calcado del inglés; Iris nunca usa esa palabra.

### 2.8 Rama P5 — AYUDA (LL93-99)

```python
# Priority 3: Detect concrete help requests (returning users)
if any(signal in msg_lower for signal in help_signals):
    return (
        "ESTRATEGIA: AYUDA. El usuario tiene una necesidad concreta. "
        "Responde DIRECTAMENTE a lo que necesita. NO saludes genéricamente. "
        "Si no sabes la respuesta exacta, pregunta detalles específicos."
    )
```

- Re-usa `help_signals` de LL57.
- **Overlap con P4**: si `history_len≥4` y mensaje contiene "ayuda", P4 RECURRENTE gana (orden). Esto significa que usuarios con historial pidiendo ayuda reciben guidance de RECURRENTE, no de AYUDA. **Posible brecha**: RECURRENTE no dice "responde directamente a lo que necesita".

### 2.9 Rama P6 — VENTA (LL101-107)

```python
# Priority 4: Product interest -> sales mode
if intent_value in ("purchase", "pricing", "product_info", "purchase_intent", "product_question"):
    return (
        "ESTRATEGIA: VENTA. El usuario muestra interés en productos/servicios. "
        "Da la información concreta que pide (precio, contenido, duración). "
        "Añade un CTA suave al final."
    )
```

- **Origen del set de intents:** commit `7d49b663b` BUG-07 los añadió. Combinación de nombres legacy (`purchase`, `pricing`) y nuevos del IntentClassifier refactor (`purchase_intent`, `product_question`).
- **Duplicación semántica:** `purchase` vs `purchase_intent` y `product_info` vs `product_question` parecen sinónimos. Probable deuda de naming.
- **Overlap con resolver S6 (ArbitrationLayer):** la decisión `SELL` vs `NO_SELL` del resolver se toma en otra fase, pero el hint VENTA preexiste y dice "añade CTA". Si el resolver decide `NO_SELL` pero strategy dice VENTA, hay conflicto.

### 2.10 Rama P7 — REACTIVACIÓN (LL109-114)

```python
# Priority 5: Ghost/reactivation
if lead_stage in ("fantasma",):
    return (
        "ESTRATEGIA: REACTIVACIÓN. El usuario vuelve después de mucho tiempo. "
        "Muestra que te alegra verle. No seas agresivo con la venta."
    )
```

- **Disparo:** `lead_stage == "fantasma"` (único valor matcheado; la tupla de un solo elemento sugiere planificación futura de otros stages).
- **Precedencia:** por debajo de VENTA → si un ghost vuelve preguntando precio, gana VENTA (razonable).

### 2.11 Default (LL116-117)

```python
# Default: natural conversation
return ""
```

- Retorna vacío → `generation.py:204 if strategy_hint:` no añade nada al prompt.

---

## 3. Control flow y distribución en producción

### 3.1 Árbol de decisión (precedencia estricta de arriba abajo)

```
┌─ relationship_type ∈ {FAMILIA, INTIMA}  ──→ P1 PERSONAL-FAMILIA  [MUERTA en prod]
├─ is_friend                             ──→ P2 PERSONAL-AMIGO    [MUERTA en prod]
├─ is_first_message
│    ├─ "?" ∈ msg ∨ help_signals ∈ msg   ──→ P3a BIENVENIDA+AYUDA
│    └─ (resto)                          ──→ P3b BIENVENIDA
├─ history_len ≥ 4 ∧ ¬is_first_message   ──→ P4 RECURRENTE
├─ help_signals ∈ msg                    ──→ P5 AYUDA
├─ intent_value ∈ {purchase, pricing,...}──→ P6 VENTA
├─ lead_stage == "fantasma"              ──→ P7 REACTIVACIÓN
└─ default                               ──→ "" (no hint)
```

### 3.2 Distribución medida en dataset `iris_bertran/test_set_v2_stratified.json` (n=50)

Reproducción: `python3 -c "..."` aplicando `_determine_response_strategy` con `relationship_type=""` e `is_friend=False` (simulación fiel al callsite de prod):

| Rama | Casos | % | Comentario |
|------|-------|---|------------|
| **P4 RECURRENTE** | 45 | **90.0%** | Dominante absoluto. El dataset es conversacional multi-turn. |
| Default (sin hint) | 4 | 8.0% | Mensajes cortos con `history_len<4` y sin help/intent signals (ej: "Si") |
| P6 VENTA | 1 | 2.0% | Detección heurística por keywords "plan"/"clase" (sin acceso al IntentClassifier real) |
| P1 FAMILIA | 0 | 0% | Hardcoded `""` |
| P2 AMIGO | 0 | 0% | Hardcoded `False` |
| P3 BIENVENIDA | 0 | 0% | Ningún caso con `is_first_message=True` en este bucket |
| P5 AYUDA | 0 | 0% | Ninguno contiene help_signals (bucket de Iris, informal) |
| P7 REACTIVACIÓN | 0 | 0% | No hay `lead_stage=="fantasma"` en metadata |

**Hallazgo clave:** el sistema está de facto **monopolizado por P4 RECURRENTE** en el eval de Iris. Las otras ramas son contribución marginal en este dataset. El impacto CCEE del hint depende mayoritariamente de la calidad del texto P4. Una regresión en P4 se amplifica 10x. Esto también implica que **cualquier mejora en P1/P2 es invisible al CCEE si el dataset no tiene conversaciones familia/amigo** — habrá que verificar si el bucket incluye este tipo.

**Nota sobre validez:** esta estimación se hizo sin IntentClassifier activo (por eso solo 1 caso VENTA). En prod, IntentClassifier probablemente clasificaría ~10-20% como `pricing`/`purchase_intent`, desviando parte de los 45 casos RECURRENTE hacia VENTA (pero VENTA está debajo de RECURRENTE en precedencia, por lo que no hay movimiento: RECURRENTE sigue ganando).

### 3.3 Acceso a logs prod

- `railway logs` requiere credenciales y no está accesible desde worktree aislado.
- Alternativa: el campo `cognitive_metadata["response_strategy"]` se graba en DB en cada respuesta via `api/routers/dm/processing.py`. Consulta SQL para obtener distribución real de últimos 7 días:
  ```sql
  SELECT cognitive_metadata->>'response_strategy' AS branch, COUNT(*)
  FROM messages
  WHERE role='assistant' AND created_at >= NOW() - INTERVAL '7 days'
  GROUP BY 1 ORDER BY 2 DESC;
  ```
  Esta consulta queda documentada en `06_measurement_plan.md` como validación pre-corrida.

---

## 4. Upstream — Trazabilidad de los 8 parámetros

El callsite (`generation.py:194-203`) extrae valores del `ContextBundle` construido en `phase_context` y los pasa a `_determine_response_strategy`. Tabla completa:

| # | Param → Callsite (gen.py:L) | Valor pasado | Origen real (context.py:L) | Hardcoded? |
|---|----------------------------|--------------|----------------------------|------------|
| 1 | `message` (L195) | argumento de `phase_llm_generation` | — | no |
| 2 | `intent_value` (L196) | `context.intent_value` (L173) | `phase_intent` → `IntentClassifier.classify()` | no |
| 3 | `relationship_type` (L197) | **`""` literal** | _Ignora_ `context.rel_type` (L1690) que a su vez es `""` por política (L1222) | **sí** (doblemente) |
| 4 | `is_first_message` (L198) | `(follower.total_messages ≤ 1) and not history` | `follower.total_messages` (IG API / DB) y `history` (conv_state) | no (derivación en línea) |
| 5 | `is_friend` (L199) | **`False` literal** | _Ignora_ `context.is_friend` (L1689) que viene de `_rel_score.suppress_products` (L1221) | **sí** |
| 6 | `follower_interests` (L200) | `follower.interests` | `Follower.interests` (DB, probablemente JSON array) | no (pero **dead param**, nunca se lee dentro de la función) |
| 7 | `lead_stage` (L201) | `current_stage` (L177) | `phase_context` → `_get_lead_stage(follower, metadata)` → `leads.stage` | no |
| 8 | `history_len` (L202) | `len(history)` | `context.history` → mensajes previos lead/bot | no |

### 4.1 Nota sobre la doble capa de hardcoding

- **Capa 1** (`context.py:1222`): `_rel_type = ""` — política explícita documentada en comentario.
- **Capa 2** (`generation.py:197`): `relationship_type=""` — **redundante** porque `_rel_type` ya es `""`.
- **Consecuencia:** cualquier intento de re-activar P1/P2 requiere **dos cambios coordinados**. Esto es defense-in-depth intencional (el autor aseguró la desactivación).
- **Para la decisión CEO (Fase 5)**: mantener ambas capas tal cual (no restaurar) y resolver el problema portando guidelines al resolver S6.

---

## 5. Downstream — Efectos del output

Output de la función (`str`, vacío o con contenido) se usa en tres puntos:

### 5.1 Metadata (`generation.py:205`)

```python
cognitive_metadata["response_strategy"] = strategy_hint.split(".")[0]
```

- Graba el **primer fragmento** (antes del primer punto) como token de estrategia.
- Ejemplo: `"ESTRATEGIA: RECURRENTE"` se almacena; el resto del texto (reglas) **NO**.
- Este metadata se persiste en `messages.cognitive_metadata` (JSONB) en DB.

### 5.2 Log estructurado (`generation.py:206`)

```python
logger.info(f"[STRATEGY] {strategy_hint.split('.')[0]}")
```

- Observabilidad básica. No usa `extra={}` dict (no estructurado en el sentido Datadog/structured-logging), solo stdout formateado.
- **Smell:** formato f-string sin campos keyed para Prometheus / OpenTelemetry.

### 5.3 Inyección al prompt final (`generation.py:292-293`)

```python
if strategy_hint:
    prompt_parts.append(strategy_hint)
```

- Añade el texto **completo** (todas las reglas) al `prompt_parts`.
- Orden de `prompt_parts` (LL287-303):
  1. `preference_profile_section` (opcional, flag OFF por default)
  2. `gold_examples_section` (opcional, flag OFF por default)
  3. **`strategy_hint`** ← aquí
  4. `_q_hint` (question suppression, probabilístico)
  5. `message` (literal del usuario)
- Concatenación: `full_prompt = "\n\n".join(prompt_parts)`
- `full_prompt` se pasa al LLM junto con `system_prompt` (construido aparte por `build_system_prompt` en `phase_context`).

**Observación clave:** strategy_hint NO forma parte del system_prompt. El LLM lo ve como parte del mensaje user-turn, precediendo al mensaje real del usuario. Esto significa que **Gemini/Claude interpretan el hint como "instrucción contextual de esta vuelta"**, no como política persistente.

---

## 6. Hallazgos del forense

### 6.1 Hallazgos de diseño

1. **Single-author, single-day creation**: `81467a92e` es pura extracción de `dm_agent_v2.py`. La lógica ha evolucionado mayoritariamente en 7 commits del mismo autor sin PRs multi-autor → cero code review externa formal al archivo.
2. **Dead parameter**: `follower_interests` nunca se lee. Deuda acumulada desde creación.
3. **Hardcoded threshold**: `history_len >= 4` no es data-derived. Debería computarse del creator profile (ej: p75 de length of first 4 exchanges para cada creator).
4. **Vocab inline ES-only**: 14 `help_signals` en español cortan la universalidad (Stefano=italiano, otros creadores futuros).
5. **Creator-specific hint embebido**: regla 4 de P4 menciona "nena, tia, flor, cuca, reina" → solo vale para Iris. Debería venir de `calibrations/{creator}.json` vocab_profile.
6. **Char limit texto-libre**: "5-30 chars" en P1 es string libre, no reglas data-derived del creator baseline.

### 6.2 Hallazgos funcionales

7. **Doble hardcoding redundante** (`context.py:1222` + `generation.py:197,199`): defense-in-depth contra reactivación accidental.
8. **27 días sin CCEE**: desde `9752df768` (2026-03-27) hasta hoy (2026-04-23), el eje estilo FAMILIA/AMIGO quedó huérfano sin cobertura. Posible regresión silenciosa en B2 persona fidelity.
9. **90% de mensajes caen en P4 RECURRENTE** en el eval dataset → cualquier cambio de wording de RECURRENTE tiene impacto amplificado.
10. **Overlap de lógica con resolver S6**: VENTA vs NO_SELL puede chocar. Si resolver decide NO_SELL pero intent es `pricing`, strategy dice "añade CTA suave" → contradicción.

### 6.3 Hallazgos de observabilidad

11. **Sin métricas Prometheus**: no hay `dm_strategy_branch_total{branch=...}` ni contador de inyección. Única señal es log stdout + metadata en DB (requiere query SQL para auditoría).
12. **Metadata solo guarda el primer fragmento**: no se persiste qué reglas específicas se inyectaron → imposible A/B testar wording sin re-ejecutar.

### 6.4 Hallazgos de tests

13. Tests existentes (`tests/test_dm_agent_v2.py:521+`, `tests/test_motor_audit.py:312,480`, `tests/test_e2e_pipeline.py:9`) están **distribuidos en 3 archivos** y usan el símbolo re-exportado desde `core/dm_agent_v2.py` (línea 28, `noqa: F401`). Deuda: el módulo antiguo sigue re-exportando por backward-compat de tests.
14. No hay test explícito que verifique que P1/P2 **nunca** se disparen (defense-in-depth → convertir en test de regresión).

---

## 7. Resumen ejecutivo Fase 2

- **Historia**: 7 commits clave, autor único Manel Bertran, creación 2026-02-25, último cambio funcional 2026-03-29 (P4 RECURRENTE).
- **Control flow**: 7 ramas `if` top-level + 1 nested + default, evaluación con precedencia estricta, `return` temprano en cada rama.
- **Distribución medida**: **P4 RECURRENTE absorbe 90% de casos** en `iris_bertran/test_set_v2_stratified.json` (n=50). P1/P2 muertas (0%). P3/P5/P7 = 0% en este dataset (no hay first_messages, help_signals explícitos ni fantasmas). Default = 8%, VENTA heurístico = 2%.
- **Upstream**: 8 parámetros; **2 hardcoded** (`relationship_type=""`, `is_friend=False`); **1 dead** (`follower_interests` nunca leído).
- **Downstream**: metadata + log + inyección en user prompt (no system_prompt). Solo el primer fragmento se guarda como metadata.
- **Deuda crítica**: 27 días sin CCEE tras desactivación P1/P2. ¿Regresión silenciosa en B2?
- **Sin métricas ni gate**: strategy está ON always, sin flag, sin Prometheus, sin guard.

**STOP Fase 2.** Aguardo confirmación para proceder a Fase 3 (bugs detectados con tabla SHA/línea/severidad/reproducción/fix).
