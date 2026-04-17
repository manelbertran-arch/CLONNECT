# ARC3 — Compaction Strategies

**Sprint:** 5 / Track 2 / ARC3
**Estimación realista:** 3 semanas (2 eng weeks + 1 buffer)
**Complejidad:** MEDIA
**Dependencias:** ARC1 (Token-Aware Budget) — preferible pero no bloqueante
**Autor:** Arquitecto Clonnect (AI)
**Fecha:** 2026-04-16

---

## 0 · TL;DR

> **Problema:** Clonnect no tiene ninguna estrategia de compactación del prompt. Claude Code tiene **3 activas** (microCompact, SessionMemoryCompact, autoCompact) + 1 reactiva. Cuando el context budget se excede, nuestra única estrategia es **truncar Doc D mecánicamente**, lo cual QW2 demostró que causa **-10.5 puntos CCEE** (pérdida irrecuperable de señal de estilo).
>
> **Solución:** Construir 3 mecanismos complementarios:
>
> 1. **StyleDistillCache** — Versión LLM-destilada del Doc D (offline, precomputada, cache por hash). Reemplaza la truncación mecánica con distillation semántica. Objetivo: Iris Doc D 5,535 → ~1,500 chars con pérdida CCEE ≤ -2 puntos.
> 2. **PromptSliceCompactor** — Orquestador de budget proporcional por componente con whitelist de secciones intocables. Decide qué truncar y cómo cuando se excede el budget total.
> 3. **CircuitBreaker** — `MAX_CONSECUTIVE_FAILURES=3` (como CC) para evitar retry-loops en edge cases de generación.
>
> **Métrica objetivo:** S3 recovery ≥ 65 (actualmente 54.8), Doc D Iris truncation rate ≤ 2% (actualmente ~8% en scoring batch).

---

## 1 · Problema que Resuelve

### 1.1 Evidencia W7 — Decisión C (§9)

> **Decisión C — Compaction:** *"Clonnect no tiene compaction. Cuando el prompt excede MAX_CONTEXT_CHARS=8000, la única estrategia es truncar Doc D a MAX_STYLE_CHARS (variable). Esto pierde señal de estilo crítica."*

### 1.2 Evidencia W6 — CC tiene 3+1 estrategias

| Estrategia CC | Trigger | Target |
|---|---|---|
| **microCompact** | Cada turno de herramienta | Output de tool calls largas |
| **SessionMemoryCompact** | Cada 10 turnos | Mensajes antiguos |
| **autoCompact** | 92% del context window | Todo el conversation history |
| **reactiveCompact** | Token overflow detectado | Fallback de emergencia |

**Clonnect actualmente:** 0 estrategias activas. Solo `len(doc_d)[:MAX]` (truncación naïve).

### 1.3 Evidencia W3 — Iris Doc D es el cuello de botella

| Componente | Chars promedio (Iris) | % del prompt |
|---|---|---|
| Doc D (style_prompt) | **5,535** | **66% mean, 77% P95** |
| Doc M (message_history) | 680 | 8% |
| Doc R (recalling_memories) | 310 | 4% |
| Doc F (few_shots) | 1,180 | 14% |
| System + otros | 695 | 8% |
| **TOTAL** | **8,400** | **105% de MAX_CONTEXT_CHARS=8000** |

**Consecuencia actual:** Scoring batch Iris trunca Doc D ~8% de las veces cuando el prompt incluye reply_hint largo o RAG hits > 3.

### 1.4 Evidencia QW2 — Truncación mecánica mata la señal

QW2 experimentó con `USE_COMPRESSED_DOC_D=true` (mecanical top-K sentences por TF-IDF).

**Resultado:**
```
Iris Gemma-4-31B baseline:          CCEE composite 70.2
Iris Gemma-4-31B compressed Doc D:  CCEE composite 59.7  (-10.5)
```

**Decisión registrada en `MEMORY.md`:** *"flag USE_COMPRESSED_DOC_D regresses composite -10.69 for Iris on Gemma-4-31B → stays off"*.

**Root cause** (W7 §2.QW2): mecanismo TF-IDF top-K pierde orden narrativo, rompe sub-párrafos de estilo (bullets con contexto), y descarta ejemplos concretos en favor de generalidades abstractas. **La señal de estilo está en los detalles, no en las frases más frecuentes.**

### 1.5 Síntesis del problema

- Doc D no cabe en el budget para ~8% de turnos de Iris → truncation rate alto.
- Truncación mecánica pierde señal → regresión -10.5 CCEE.
- Sin circuit breaker → retry-loops pueden generar 3-5x tokens en edge cases (observado en W5 §4.3 trace).
- Sin whitelist → el algoritmo puede truncar secciones core (guardrails, persona) antes que secciones opcionales (RAG, few_shots).

---

## 2 · Diseño Técnico

### 2.1 Arquitectura de 3 capas

```
┌─────────────────────────────────────────────────────────────┐
│ LAYER 1 — Offline Preparation (batch, 1/día o on-change)   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ StyleDistillBatchJob                                │    │
│  │  - Per creator, per doc_d version_hash              │    │
│  │  - LLM: Claude Sonnet 4.6                           │    │
│  │  - Target: 1,500 chars preservando voz + ejemplos   │    │
│  │  - Store: creator_style_distill (hash → distilled)  │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ LAYER 2 — Runtime Budget Decision (per turn, <1ms)          │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ PromptSliceCompactor.pack(sections, budget)         │    │
│  │  1. Count tokens for each section                   │    │
│  │  2. If total ≤ budget → return as-is                │    │
│  │  3. Else:                                           │    │
│  │     a) If style_prompt > 40% budget AND             │    │
│  │        StyleDistillCache has hit → replace with     │    │
│  │        distilled (saves 60-70% tokens)              │    │
│  │     b) Apply ratio caps per component               │    │
│  │     c) Truncate non-whitelisted from lowest         │    │
│  │        priority upward                              │    │
│  │     d) NEVER truncate whitelist: guardrails,        │    │
│  │        persona_identity, current_user_msg           │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ LAYER 3 — Generation Failure Protection (on generate)       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ CircuitBreaker.check(creator_id, lead_id)           │    │
│  │  - Tracks consecutive failures in last 5 min        │    │
│  │  - MAX_CONSECUTIVE_FAILURES=3                       │    │
│  │  - On trip: skip generation, return fallback        │    │
│  │    message ("let me get back to you"), alert        │    │
│  │  - Reset on 1 successful generation                 │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Component 1 — StyleDistillCache

#### 2.2.1 Problem statement

Iris Doc D (`style_prompt`) ≈ 5,535 chars ≈ 1,380 tokens. Es el 66% del budget. Cuando se trunca, se pierde:
- Ejemplos concretos ("yo digo X cuando me preguntan Y")
- Lista de tics verbales con contexto
- Tono per-situation (cold vs warm vs hot lead)

**Mechanical truncation** (TF-IDF, first-N, last-N) — QW2 probó que pierde -10.5 CCEE.

**LLM-distilled** — hipótesis: preserva señal semántica compactando forma.

#### 2.2.2 Esquema de datos

```sql
CREATE TABLE creator_style_distill (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,

    -- Versioning
    doc_d_hash TEXT NOT NULL,        -- SHA256 del style_prompt original
    doc_d_chars INT NOT NULL,        -- Tamaño original
    doc_d_version INT NOT NULL,      -- Incremental per creator

    -- Distilled outputs
    distilled_short TEXT NOT NULL,   -- Target ~1,500 chars (60% compression)
    distilled_med TEXT,              -- Target ~3,000 chars (40% compression, opcional)

    -- Meta
    distilled_chars INT NOT NULL,    -- len(distilled_short)
    distill_model TEXT NOT NULL,     -- 'claude-sonnet-4-6'
    distill_prompt_version INT NOT NULL,  -- Para re-generar si cambia el prompt

    -- Quality scoring (populated on validation)
    quality_score FLOAT,             -- CCEE comparativo, 0-100
    human_validated BOOL DEFAULT false,

    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),

    UNIQUE(creator_id, doc_d_hash, distill_prompt_version)
);

CREATE INDEX idx_style_distill_creator_hash
    ON creator_style_distill(creator_id, doc_d_hash);
```

#### 2.2.3 Distillation prompt (v1)

```python
DISTILL_PROMPT_V1 = """
Eres un experto en preservar la voz y el estilo comunicativo de un creador de contenido.

A continuación tienes el "Doc D" completo de un creador (su style_prompt). Tu tarea es
producir una versión DESTILADA que preserve:

1. La VOZ única (tics verbales, expresiones características, tono)
2. Los EJEMPLOS concretos más representativos (al menos 3-5)
3. Las reglas de tono según situación (cold/warm/hot lead si existen)
4. Las restricciones de forma (longitud, emojis, puntuación si existen)

Debes ELIMINAR:
- Frases genéricas sobre "ser auténtico" o "conectar con el lead"
- Redundancias (misma idea dicha 2+ veces)
- Meta-comentarios sobre el estilo (decir "mi estilo es X" en lugar de demostrarlo)
- Ejemplos menos informativos si hay varios similares

TARGET: {target_chars} caracteres (±15%).

FORMATO DE SALIDA: Solo el texto destilado, sin meta-explicaciones ni preámbulo.

DOC D ORIGINAL:
---
{doc_d}
---

VERSIÓN DESTILADA:
"""
```

#### 2.2.4 Batch job

```python
# scripts/distill_style_prompts.py

async def distill_all_creators():
    creators = await db.creators.find_all()
    for creator in creators:
        prompt_obj = await prompt_service.get_for_creator(creator.id)
        doc_d = prompt_obj.style_prompt

        doc_d_hash = hashlib.sha256(doc_d.encode()).hexdigest()[:16]

        # Check cache
        existing = await db.creator_style_distill.find_one(
            creator_id=creator.id,
            doc_d_hash=doc_d_hash,
            distill_prompt_version=DISTILL_PROMPT_VERSION,
        )
        if existing:
            continue  # Already distilled

        # Distill
        target_chars = 1500
        distilled = await llm.distill(
            prompt=DISTILL_PROMPT_V1.format(doc_d=doc_d, target_chars=target_chars),
            model="claude-sonnet-4-6",
            max_tokens=800,
        )

        # Validate length (retry if too long/short)
        if not (1200 <= len(distilled) <= 1800):
            distilled = await llm.distill(..., retry=True)

        # Store
        await db.creator_style_distill.insert(
            creator_id=creator.id,
            doc_d_hash=doc_d_hash,
            doc_d_chars=len(doc_d),
            doc_d_version=prompt_obj.version,
            distilled_short=distilled,
            distilled_chars=len(distilled),
            distill_model="claude-sonnet-4-6",
            distill_prompt_version=DISTILL_PROMPT_VERSION,
        )
```

#### 2.2.5 Invalidación

- Cada vez que `style_prompt` cambia, el hash cambia → nuevo row.
- Cron diario elimina distillations cuyo `doc_d_version` < `creator.current_version - 3`.
- Si `distill_prompt_version` cambia (mejora de prompt), **re-distill all** (batch job).

#### 2.2.6 Fallback behavior

```python
def get_doc_d_for_turn(creator_id: UUID, budget_pressure: bool) -> str:
    doc_d_full = await prompt_service.get_style_prompt(creator_id)

    if not budget_pressure:
        return doc_d_full

    # Budget pressure → try distilled
    doc_d_hash = sha256(doc_d_full)[:16]
    distilled = await cache.get_distilled(creator_id, doc_d_hash)

    if distilled is None:
        # No cache hit → must use full (accept budget overrun or let
        # PromptSliceCompactor truncate other sections)
        metrics.distill_cache_miss.inc(creator_id=creator_id)
        return doc_d_full

    metrics.distill_cache_hit.inc(creator_id=creator_id)
    return distilled.distilled_short
```

**Clave:** Nunca devolver truncación mecánica si no hay distilled. Es mejor exceder budget 10% que perder -10.5 CCEE.

#### 2.2.7 Quality validation

Antes de activar en prod, por creador:
1. Correr CCEE v5.3 en 20 scenarios con `doc_d_full`.
2. Correr CCEE v5.3 en los mismos 20 scenarios con `distilled_short`.
3. Reportar delta por métrica (K1-K10, S1-S5).
4. **Gate de activación:** ΔCCEE_composite ≥ -3 puntos (aceptamos pérdida pequeña; no aceptamos -10.5).
5. Si falla → ajustar `DISTILL_PROMPT_V1` o `target_chars`, re-destilar, re-validar.

---

### 2.3 Component 2 — PromptSliceCompactor

#### 2.3.1 Relación con ARC1

**ARC1** (BudgetOrchestrator) decide **cuánto presupuesto** asigna a cada sección. **ARC3** (PromptSliceCompactor) decide **cómo truncar** una sección individual que excede su cap, y cuándo invocar `StyleDistillCache`.

Son complementarios:
- Si ARC1 está en prod: PromptSliceCompactor es el "truncator" que ARC1 invoca para cada sección.
- Si ARC1 NO está: PromptSliceCompactor opera con ratios hard-coded por creador.

**Por eso ARC3 puede shippear antes que ARC1**, pero la integración limpia requiere ARC1 primero.

#### 2.3.2 Budget ratios (W6 propuesta A)

```python
# Default ratios (override per creator via creator_runtime_config)
DEFAULT_RATIOS = {
    "style_prompt": 0.35,    # Doc D
    "lead_facts": 0.15,       # Nombre, intereses conocidos
    "lead_memories": 0.20,    # Memory recall (ARC2)
    "rag_hits": 0.15,         # Retrieval semántico
    "message_history": 0.10,  # Últimos N turnos
    "few_shots": 0.05,        # Ejemplos canónicos
}

# Total = 1.00
```

**Context budget total:** 8,000 chars (MAX_CONTEXT_CHARS actual).

Ejemplo Iris con budget 8,000:
- style_prompt cap: 2,800
- lead_facts cap: 1,200
- lead_memories cap: 1,600
- rag_hits cap: 1,200
- message_history cap: 800
- few_shots cap: 400

Pero `style_prompt_full` = 5,535 > cap 2,800 → trigger StyleDistillCache → usa distilled 1,500.

#### 2.3.3 Preserve whitelist

Secciones **intocables** (nunca truncadas):

```python
PROMPT_WHITELIST = {
    "system_instructions",     # Prompt system base (~200 chars)
    "guardrails",              # Reglas de seguridad (~150 chars)
    "persona_identity",        # "Eres [creator_name]..." (~100 chars)
    "current_user_msg",        # El mensaje actual del lead (variable)
    "tone_directive",          # Emoji rule, length rule (~80 chars)
}
```

Si el prompt sin whitelist ya excede budget → ALERT + usar fallback (respuesta genérica), no truncar whitelist.

#### 2.3.4 Algoritmo de compactación

```python
@dataclass
class SectionSpec:
    name: str
    content: str
    priority: int         # 1 (highest) to 10 (lowest)
    is_whitelist: bool
    ratio_cap: float      # 0.0-1.0, relative to total budget

class PromptSliceCompactor:
    def __init__(self, budget_chars: int, ratios: dict):
        self.budget = budget_chars
        self.ratios = ratios

    def pack(self, sections: List[SectionSpec]) -> PackResult:
        # Step 1: Compute whitelist cost
        whitelist_cost = sum(len(s.content) for s in sections if s.is_whitelist)

        if whitelist_cost > self.budget:
            # Pathological: whitelist alone exceeds budget
            metrics.whitelist_overflow.inc()
            return PackResult(
                packed={},
                status="CIRCUIT_BREAK",
                reason="whitelist_overflow",
            )

        # Step 2: Budget for non-whitelist
        remaining = self.budget - whitelist_cost

        # Step 3: Try as-is (no compaction needed)
        non_wl = [s for s in sections if not s.is_whitelist]
        current_cost = sum(len(s.content) for s in non_wl)

        if current_cost <= remaining:
            return PackResult(
                packed={s.name: s.content for s in sections},
                status="OK",
                compaction_applied=False,
            )

        # Step 4: Apply StyleDistillCache if style_prompt is the issue
        style_section = next((s for s in non_wl if s.name == "style_prompt"), None)
        if style_section and len(style_section.content) > remaining * 0.4:
            distilled = await distill_cache.get(
                creator_id=context.creator_id,
                doc_d=style_section.content,
            )
            if distilled:
                style_section.content = distilled
                current_cost = sum(len(s.content) for s in non_wl)
                metrics.distill_applied.inc()

        # Step 5: If still over budget, apply ratio caps
        if current_cost > remaining:
            for s in non_wl:
                cap_chars = int(self.ratios[s.name] * remaining)
                if len(s.content) > cap_chars:
                    s.content = truncate_preserving_structure(s.content, cap_chars)
                    metrics.section_truncated.inc(section=s.name)

            current_cost = sum(len(s.content) for s in non_wl)

        # Step 6: If STILL over budget, truncate by reverse priority
        if current_cost > remaining:
            for s in sorted(non_wl, key=lambda x: -x.priority):  # lowest first
                if current_cost <= remaining:
                    break
                needed_reduction = current_cost - remaining
                new_len = max(0, len(s.content) - needed_reduction)
                s.content = s.content[:new_len]
                current_cost = sum(len(x.content) for x in non_wl)
                metrics.section_aggressive_truncate.inc(section=s.name)

        # Step 7: Assemble
        result = {s.name: s.content for s in sections}
        return PackResult(
            packed=result,
            status="OK",
            compaction_applied=True,
            final_chars=whitelist_cost + current_cost,
        )


def truncate_preserving_structure(text: str, max_chars: int) -> str:
    """
    Intenta truncar en límites de párrafo/frase, no a mitad de palabra.
    """
    if len(text) <= max_chars:
        return text

    # Try paragraph boundary
    truncated = text[:max_chars]
    last_paragraph = truncated.rfind("\n\n")
    if last_paragraph > max_chars * 0.8:
        return truncated[:last_paragraph]

    # Try sentence boundary
    last_period = truncated.rfind(". ")
    if last_period > max_chars * 0.85:
        return truncated[:last_period + 1]

    # Fallback: word boundary
    last_space = truncated.rfind(" ")
    if last_space > max_chars * 0.9:
        return truncated[:last_space]

    # Last resort: hard cut
    return truncated
```

#### 2.3.5 Integración con injection

```python
# services/context.py (actualizado)

async def build_context(
    creator_id: UUID,
    lead_id: UUID,
    user_msg: str,
) -> str:
    # Fetch all sections (async parallel)
    sections = await gather_sections(creator_id, lead_id)

    # Pack with compactor
    compactor = PromptSliceCompactor(
        budget_chars=get_runtime_config(creator_id).max_context_chars,
        ratios=get_runtime_config(creator_id).compaction_ratios or DEFAULT_RATIOS,
    )

    result = await compactor.pack(sections)

    if result.status == "CIRCUIT_BREAK":
        return None  # Caller should use CircuitBreaker fallback

    return assemble_prompt(result.packed, user_msg)
```

---

### 2.4 Component 3 — CircuitBreaker

#### 2.4.1 Motivación

W5 §4.3 trace mostró un edge case donde un prompt malformado causó 5 retries consecutivos, cada uno con más tokens (el retry añade el error anterior al prompt). Resultado: 3x cost, 3x latency, output final incorrecto.

CC implementa `MAX_CONSECUTIVE_FAILURES=3` en `createGeneration.js:442` — tras 3 fallos consecutivos, **skip generation** y devolver fallback.

#### 2.4.2 Diseño

```python
# core/generation/circuit_breaker.py

@dataclass
class BreakerState:
    creator_id: UUID
    lead_id: UUID
    consecutive_failures: int
    last_failure_at: datetime | None
    tripped_at: datetime | None

class CircuitBreaker:
    MAX_CONSECUTIVE_FAILURES = 3
    RESET_WINDOW_SECONDS = 300  # 5 min
    TRIP_COOLDOWN_SECONDS = 60  # Después de trip, esperar 60s antes de re-intentar

    async def check(self, creator_id: UUID, lead_id: UUID) -> bool:
        """Returns True if generation allowed, False if circuit tripped."""
        state = await redis.get_state(creator_id, lead_id)

        if state is None:
            return True

        # Auto-reset si ha pasado el window
        if state.last_failure_at and (now() - state.last_failure_at).seconds > self.RESET_WINDOW_SECONDS:
            await redis.reset_state(creator_id, lead_id)
            return True

        # Si está tripped, check cooldown
        if state.tripped_at:
            if (now() - state.tripped_at).seconds < self.TRIP_COOLDOWN_SECONDS:
                metrics.circuit_breaker_rejection.inc(creator_id=creator_id)
                return False
            # Cooldown over → allow retry (but don't reset state until success)
            return True

        return state.consecutive_failures < self.MAX_CONSECUTIVE_FAILURES

    async def record_failure(self, creator_id: UUID, lead_id: UUID, reason: str):
        state = await redis.get_state(creator_id, lead_id) or BreakerState(
            creator_id=creator_id,
            lead_id=lead_id,
            consecutive_failures=0,
            last_failure_at=None,
            tripped_at=None,
        )

        state.consecutive_failures += 1
        state.last_failure_at = now()

        if state.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
            state.tripped_at = now()
            metrics.circuit_breaker_tripped.inc(
                creator_id=creator_id,
                reason=reason,
            )
            await alerting.send_alert(
                severity="warning",
                event_type="generation_circuit_tripped",
                creator_id=creator_id,
                lead_id=lead_id,
                reason=reason,
            )

        await redis.set_state(creator_id, lead_id, state, ttl=self.RESET_WINDOW_SECONDS)

    async def record_success(self, creator_id: UUID, lead_id: UUID):
        await redis.reset_state(creator_id, lead_id)
```

#### 2.4.3 Fallback responses

Cuando breaker está tripped:

```python
FALLBACK_RESPONSES = {
    "default": "Ey, te respondo en un rato que ando liado/a 🙏",
    "es_long": "Mil perdones, se me está liando el día — te escribo ahorita con calma",
    "en": "hey! i'll get back to you in a bit, bear with me 🙏",
}

async def get_fallback_response(creator_id: UUID, lead_id: UUID) -> str:
    creator = await db.creators.get(creator_id)
    lang = creator.default_language or "es_long"
    return FALLBACK_RESPONSES.get(lang, FALLBACK_RESPONSES["default"])
```

#### 2.4.4 Failure taxonomy

Qué constituye un "failure":
- **HARD failures** (cuentan siempre): LLM timeout, 5xx, content filter trip, JSON parse error en structured output.
- **SOFT failures** (solo si reincide): respuesta vacía, respuesta < 3 chars, respuesta idéntica al mensaje anterior (loop).
- **NO failures** (aunque parezcan): respuesta con emoji "incorrecto", longitud fuera de rango (mutations las corrigen).

```python
class FailureType(Enum):
    LLM_TIMEOUT = "llm_timeout"
    LLM_5XX = "llm_5xx"
    CONTENT_FILTER = "content_filter"
    JSON_PARSE_ERROR = "json_parse_error"
    EMPTY_RESPONSE = "empty_response"
    RESPONSE_TOO_SHORT = "response_too_short"
    LOOP_DETECTED = "loop_detected"
```

---

## 3 · Plan de Rollout (5 fases)

### Phase 1 — Shadow StyleDistillCache (Semana 1)

**Objetivo:** Generar distillations para los 3 creators activos, validar calidad vía CCEE.

**Tasks:**
1. Crear tabla `creator_style_distill` (migración alembic).
2. Implementar `scripts/distill_style_prompts.py`.
3. Correr batch para 3 creators.
4. Por creator: CCEE v5.3 con full Doc D vs distilled Doc D (20 scenarios × 2 modelos).
5. Reportar delta CCEE composite + per-metric.
6. Si ΔCCEE_composite ≥ -3 puntos → approve; else iterate prompt.

**No-go criteria:** Si 2+ creators tienen regresión > -3 puntos, revisar `DISTILL_PROMPT_V1`.

**Output:** `docs/sprint5_planning/ARC3_phase1_distill_validation.md`

---

### Phase 2 — Shadow PromptSliceCompactor (Semana 1-2, paralelo)

**Objetivo:** Implementar compactor en modo shadow (log decisions, don't apply).

**Tasks:**
1. Implementar `core/generation/compactor.py`.
2. En `services/context.py`, llamar `compactor.pack()` y **comparar con assembly actual**.
3. Log divergencias a `context_compactor_shadow_log` table.
4. Analizar 1,000 turnos de shadow data:
   - % de turnos que hubieran activado compaction
   - Secciones más truncadas
   - Pérdida de información estimada

**Gate:** Compaction activada en < 15% de turnos (si más, ratios están mal calibrados).

**Output:** Tabla `context_compactor_shadow_log` + análisis.

---

### Phase 3 — Live Compactor + Distill Cache (Semana 2-3)

**Objetivo:** Activar compactor + distill en producción, bajo feature flag, ramp-up gradual.

**Rollout:**
- Día 1: 10% de turnos para Stefano (creador con menor Doc D, menor riesgo).
- Día 2: 25% Stefano si métricas OK.
- Día 3: 50% Stefano + 10% Iris.
- Día 5: 100% Stefano + 50% Iris si OK.
- Día 7: 100% todos los creators.

**Sticky hashing:** `hash(lead_id) % 100 < rollout_pct` (mismo lead siempre mismo grupo).

**Kill switch:** `USE_COMPACTION=false` revierte a comportamiento actual.

**Métricas por día:**
- Doc D truncation rate (actual baseline: 8% Iris)
- CCEE composite (correr subset de 20 scenarios/día)
- Latencia P95
- Error rate

**No-go (rollback):**
- CCEE composite regresa > -5 puntos
- Error rate > 2x baseline
- Latencia P95 > +200ms

---

### Phase 4 — CircuitBreaker (Semana 3)

**Objetivo:** Añadir circuit breaker como última línea de defensa.

**Tasks:**
1. Implementar `core/generation/circuit_breaker.py`.
2. Integrar en `services/generation.py` entry point.
3. Redis backend para state (TTL 5 min).
4. Fallback responses per language.
5. Alerting integration (QW3 ya implementado).

**Validation:**
- Simular 3 failures consecutivos en staging → verificar trip + alert.
- Verificar reset después de success.
- Verificar cooldown correcto.

**Deploy:** Full rollout (sin A/B, es protección).

---

### Phase 5 — Tuning + Runbook (Semana 3)

**Objetivo:** Dejar el sistema operable.

**Tasks:**
1. Runbook `docs/runbooks/compaction_tuning.md`:
   - Cómo ajustar ratios per-creator
   - Cómo re-distill cuando cambia Doc D
   - Cómo interpretar circuit breaker alerts
2. Dashboards Grafana:
   - `compaction_applied_rate` per creator
   - `distill_cache_hit_rate`
   - `circuit_breaker_trips` rolling 24h
   - `doc_d_truncation_rate` (legacy vs new)
3. Alertas:
   - Distill cache miss > 5% sostenido
   - Circuit breaker trip rate > 0.5% sostenido
   - Compaction applied > 30% sostenido (indica budget insuficiente)

---

## 4 · Métricas de Éxito

### 4.1 Métricas Primarias (Gate de éxito del sprint)

| Métrica | Baseline | Target | Método |
|---|---|---|---|
| **Iris Doc D truncation rate** | 8% | ≤ 2% | Log post-compactor, count `compaction_applied=true` con `style_prompt=distilled` |
| **S3 recovery CCEE** | 54.8 | ≥ 65 | Correr CCEE v5.3 con escenarios S3-specific (scoring-batch pressure) |
| **Iris CCEE composite overall** | 70.2 | ≥ 70.0 | No regresión vs baseline (empate es aceptable dado que compaction ahorra tokens) |
| **Latency P95 generation** | 1,800ms | ≤ 1,900ms | DataDog trace, percentile |

### 4.2 Métricas Secundarias

| Métrica | Target |
|---|---|
| Distill cache hit rate | > 95% |
| Circuit breaker trip rate | < 0.1% |
| Compaction applied rate | 5-15% |
| Whitelist overflow rate | 0% |

### 4.3 Métricas de Calidad (Quality)

| Métrica | Método |
|---|---|
| Distill validation score (per creator) | CCEE composite ≥ -3 puntos vs full Doc D |
| Human perception (Manel) | Review 10 turnos pre/post compaction, rate 1-5 |

---

## 5 · Riesgos y Mitigaciones

### R1 — Distillation pierde señal (repitiendo QW2) — 🔴 HIGH

**Descripción:** LLM-distilled también podría perder señal crítica si el prompt está mal diseñado.

**Mitigación:**
- Validación CCEE v5.3 **antes** de activar cada distilled version.
- Gate: ΔCCEE_composite ≥ -3 puntos.
- Iteración del `DISTILL_PROMPT_V1` si falla, con versioning (`distill_prompt_version`).
- Human-in-the-loop: Manel revisa la distilled version antes de approve.
- Fallback a full Doc D si la distilled falla validación.

### R2 — Distill batch latency alto — 🟡 MEDIUM

**Descripción:** LLM calls para distilled toman 3-5s/creador. Con 3 creators → 15s/batch. No crítico (es offline), pero escala mal a 100+ creators.

**Mitigación:**
- Batch paralelizable (3-5 concurrent).
- Cron diario, no en hot path.
- Si hay 100+ creators en el futuro, considerar Gemini Flash para distillation (más barato, suficiente).

### R3 — Compactor rompe sub-párrafos — 🟡 MEDIUM

**Descripción:** `truncate_preserving_structure` intenta cortar en límites de párrafo/frase, pero puede fallar en contenido sin estructura clara.

**Mitigación:**
- Fallback: word boundary (ya en algoritmo).
- Métrica `section_aggressive_truncate` — si > 1%/día, ajustar ratios.
- Shadow mode antes de activar detecta casos patológicos.

### R4 — CircuitBreaker false positives — 🟡 MEDIUM

**Descripción:** 3 failures consecutivos pueden ser coincidencia (LLM provider downtime) y no un bug real. Trip bloquea generación aunque el sistema funcione.

**Mitigación:**
- Failure taxonomy: solo HARD failures cuentan siempre. SOFT failures necesitan patrón (2+ del mismo tipo).
- TRIP_COOLDOWN_SECONDS=60 es corto → recuperación rápida.
- Alerting integrado (QW3) → Manel ve el trip en minutos.
- Si LLM provider está down, CircuitBreaker es *correcto* (fallback es mejor que timeouts en cadena).

### R5 — Ratios hard-coded no generalizan — 🟢 LOW

**Descripción:** DEFAULT_RATIOS están optimizados para Iris/Stefano. Nuevo creador puede necesitar distribución diferente.

**Mitigación:**
- Config per-creator en `creator_runtime_config.compaction_ratios`.
- Onboarding de nuevo creador incluye step: correr CCEE, ajustar ratios.
- Runbook documenta el proceso.

### R6 — Cache invalidation complexity — 🟢 LOW

**Descripción:** Si Doc D se actualiza via hot-reload, distilled version quedaría stale.

**Mitigación:**
- Hash-based lookup (`doc_d_hash` = SHA256) → cambio de Doc D → miss → regeneración.
- Miss path no falla, usa Doc D full (posible budget overrun, pero seguro).
- Cron diario elimina orphaned distillations.

### R7 — Distilled version no refleja tono actualizado — 🟡 MEDIUM

**Descripción:** Si creator actualiza su style_prompt el lunes, distilled sigue con versión vieja hasta el martes (cron diario).

**Mitigación:**
- Trigger manual: `POST /api/admin/creators/{id}/distill` (immediate regeneration).
- Hot reload: cuando `prompt_service` carga nuevo Doc D, encolar job de distillation.
- UI dashboard muestra "distill freshness: 2h" → Manel sabe cuándo fue generada.

---

## 6 · Dependencias

### 6.1 Dependencias técnicas

| Dependencia | Owner | Status | Blocking |
|---|---|---|---|
| ARC1 (BudgetOrchestrator) | Sprint 5 ARC1 | in_progress | **Preferible, no bloqueante** — ARC3 puede shippear standalone con hard-coded budget 8000 |
| Redis instance | Infra | ✅ existe | No |
| Alerting (QW3) | QW3 sprint 4 | ✅ completed | No |
| LLM budget (distillation) | Financial | ✅ aprobado ($10/mes estimado) | No |
| CCEE v5.3 harness | Sprint 4 CCEE | ✅ completed | No |

### 6.2 Dependencias de conocimiento

- W3 (token analytics) — ✅ disponible.
- W6 (compaction deep dive) — ✅ disponible.
- QW2 (compressed Doc D validation) — ✅ disponible (documentado en MEMORY).

### 6.3 Dependencias con otros ARCs

- **ARC1 (Budget):** Preferible para integración limpia. ARC3 puede funcionar standalone, pero si ARC1 llega primero, integración es 1 día menos.
- **ARC2 (Memory):** No bloquea. ARC3 trata `lead_memories` como cualquier otra sección.
- **ARC4 (Eliminate mutations):** Independiente.
- **ARC5 (Observability):** ARC3 emite métricas nuevas que ARC5 dashboardea.

---

## 7 · Cronograma (3 semanas realistas)

### Semana 1

| Día | Work | Owner | Output |
|---|---|---|---|
| Lun | DDL + migración `creator_style_distill` | A3.1 (dev) | Tabla creada, alembic up |
| Lun-Mar | `scripts/distill_style_prompts.py` + run para 3 creators | A3.1 | 3 distilled versions stored |
| Mar | CCEE v5.3 validation (Iris) | A3.2 (CCEE) | Report ΔCCEE per metric |
| Mié | CCEE v5.3 validation (Stefano) | A3.2 | Report + approve/reject |
| Jue-Vie | Iterar prompt si failure + re-validate | A3.1 + A3.2 | Aprovación gate Phase 1 |
| Vie | Shadow mode implementation (compactor.py) | A3.3 | Compactor en shadow |

### Semana 2

| Día | Work | Owner | Output |
|---|---|---|---|
| Lun-Mar | Analizar shadow data (1,000 turnos) | A3.3 | Shadow analysis report |
| Mar | Feature flag + sticky hash infrastructure | A3.4 | Flag plumbing |
| Mié | Rollout 10% Stefano | A3.4 | Metrics baseline |
| Jue | Rollout 25% Stefano + 10% Iris | A3.4 | Metrics check |
| Vie | Rollout 50% Stefano + 25% Iris | A3.4 | Go/no-go meeting |

### Semana 3

| Día | Work | Owner | Output |
|---|---|---|---|
| Lun | Rollout 100% (si OK) | A3.4 | Full prod |
| Mar | `circuit_breaker.py` implementation | A3.5 | Breaker live |
| Mié | Breaker integration + staging tests | A3.5 | Breaker validated |
| Jue | Dashboards Grafana + runbook | A3.6 | Operational |
| Vie | Retrospective + final validation CCEE | A3.2 | Sprint completion report |

**Buffer:** Semana 4 está reservada pero no asignada. Usar si:
- Distillation validation falla en 2+ iteraciones.
- Rollout detecta regresión > -5 CCEE y requiere rollback + fix.

---

## 8 · Worker Prompts (listos para copiar)

### Worker A3.1 — StyleDistillCache: Schema + Batch Job

```xml
<instructions>
<role>
Eres un ingeniero senior de Clonnect (FastAPI + PostgreSQL + SQLAlchemy + alembic).
</role>

<context>
Sprint 5 ARC3 Phase 1. Implementar StyleDistillCache offline batch.
Leer: docs/sprint5_planning/ARC3_compaction.md §2.2 completo.
Leer: docs/audit_phase2/W6_cc_compaction_deep_dive.md §5.3 propuesta B.
Leer: scripts existentes en scripts/ para ver el patrón de batch jobs.
</context>

<objetivo>
Crear la tabla `creator_style_distill` y el batch script para generar
distilled versions del Doc D por creador, usando Claude Sonnet 4.6 via
el provider existente (core/providers/anthropic_provider.py).
</objetivo>

<tareas>
1. Migración alembic: crear tabla `creator_style_distill` con el schema
   exacto de ARC3 §2.2.2.
2. Modelo SQLAlchemy: `core/creator_style/models.py::CreatorStyleDistill`.
3. Servicio: `core/creator_style/distill_service.py`:
   - `get_distilled(creator_id, doc_d_hash)` — cache lookup
   - `store_distilled(...)` — insert row
   - `invalidate_old_versions(creator_id, keep_last=3)` — cleanup
4. Batch script: `scripts/distill_style_prompts.py`:
   - CLI args: `--creator-id` (optional, default all), `--force` (regenerate)
   - Usa `DISTILL_PROMPT_V1` de §2.2.3
   - Valida longitud (1200-1800 chars), retry 1 vez
   - Stores via distill_service
5. Tests unitarios para distill_service (mock LLM).
6. Test de integración: run script contra DB local con 1 creator seed.
</tareas>

<reglas>
- NO modificar api/database.py (pool config).
- NO ejecutar el batch en producción sin approval.
- Usar `asyncio.to_thread()` para operaciones DB en async context.
- Respetar convenciones existentes de servicios (ver services/prompt_service.py).
- Logger `core.creator_style` con structured logging.
- Syntax check cada .py modificado: `python3 -c "import ast; ast.parse(open('FILE').read())"`.
</reglas>

<deliverables>
- Migración: alembic/versions/XXX_add_creator_style_distill.py
- Modelo + servicio + script
- Tests pasando: `python3 -m pytest tests/test_distill_service.py -v`
- Local run logs en logs/distill_run_YYYY-MM-DD.log
</deliverables>
</instructions>
```

---

### Worker A3.2 — CCEE Validation for Distilled Doc D

```xml
<instructions>
<role>
Eres un ML engineer de Clonnect, especialista en evaluación CCEE.
</role>

<context>
Sprint 5 ARC3 Phase 1 validation gate. QW2 estableció que truncación
mecánica del Doc D regresa CCEE composite -10.5. Validar que la
LLM-distilled version NO regrese más de -3 puntos.
Leer: docs/sprint5_planning/ARC3_compaction.md §2.2.7 y §4.
Leer: tests/run_ccee.py y tests/ccee_results/ para formato.
</context>

<objetivo>
Ejecutar CCEE v5.3 comparando full Doc D vs distilled Doc D para 2 creators
(Iris, Stefano) en 2 modelos (Gemma-4-26B, Gemma-4-31B). Producir report.
</objetivo>

<tareas>
1. Verificar que creator_style_distill tiene rows para Iris + Stefano
   (dependency on A3.1 output).
2. Implementar flag `USE_DISTILLED_DOC_D=true/false` en services/prompt_service.py
   (similar a flag actual USE_COMPRESSED_DOC_D pero leyendo de creator_style_distill).
3. Correr CCEE v5.3 x 4 configuraciones:
   - Iris + 26B + full Doc D (baseline)
   - Iris + 26B + distilled Doc D
   - Iris + 31B + full Doc D
   - Iris + 31B + distilled Doc D
   - Repetir 4 configs para Stefano
4. Producir `docs/sprint5_planning/ARC3_phase1_distill_validation.md`:
   - Tabla comparativa por métrica (K1-K10, S1-S5, composite)
   - Delta por creator × modelo
   - Recomendación: approve / iterate / reject
</tareas>

<reglas>
- Usar CCEE v5.3 (último harness validado).
- NO modificar el flag USE_COMPRESSED_DOC_D existente (es independiente).
- Guardar outputs en tests/ccee_results/{creator}/ccee_v53_{model}_distilled_v1.json.
- Decision gate: composite delta ≥ -3 puntos per creator × model → approve.
  Si falla, NO aprobar y crear ticket para iterar DISTILL_PROMPT_V1.
</reglas>

<deliverables>
- Flag USE_DISTILLED_DOC_D implementado
- 4 archivos JSON de resultados CCEE
- Report MD con recomendación go/no-go
- Si no-go: document specific failure modes (qué se pierde)
</deliverables>
</instructions>
```

---

### Worker A3.3 — PromptSliceCompactor (Shadow Mode)

```xml
<instructions>
<role>
Eres un ingeniero senior de Clonnect, especialista en sistemas de contexto.
</role>

<context>
Sprint 5 ARC3 Phase 2. Implementar PromptSliceCompactor en shadow mode
(no aplica en prod, solo log). Objetivo: validar calibración antes de activar.
Leer: docs/sprint5_planning/ARC3_compaction.md §2.3 completo.
Leer: services/context.py actual para entender el injection point.
Si ARC1 está done, leer también core/prompt/budget_orchestrator.py para
integración limpia.
</context>

<objetivo>
Implementar PromptSliceCompactor + shadow logging para analizar 1,000+ turnos
de datos reales antes de activación.
</objetivo>

<tareas>
1. Implementar `core/generation/compactor.py`:
   - SectionSpec dataclass
   - PromptSliceCompactor clase con método pack()
   - truncate_preserving_structure helper
   - DEFAULT_RATIOS constants
2. Tabla shadow log: `context_compactor_shadow_log` con campos:
   (id, creator_id, lead_id, turn_id, total_chars_before, total_chars_after,
    compaction_applied, sections_truncated JSONB, distill_used BOOL, created_at)
3. Integración en services/context.py:
   - Después de build actual del prompt, llamar compactor.pack() en shadow
   - Diff con prompt actual → log a tabla shadow
   - NO reemplazar el prompt (aún)
4. Métricas Prometheus:
   - compaction_shadow_applied_total (counter)
   - compaction_section_truncated_shadow (counter con label section_name)
5. Tests unitarios para compactor (todos los casos: under-budget, over-budget,
   whitelist-only, ratio-cap, aggressive-truncate).
6. Después de 48h en staging con tráfico real, analizar logs y producir
   `docs/sprint5_planning/ARC3_phase2_shadow_analysis.md`.
</tareas>

<reglas>
- Shadow = NO afecta al prompt real. Si hay bug, no impacta generación.
- Logs a tabla separada (no a messages.metadata).
- Syntax check + tests obligatorios.
- NO activar feature flag aún — esto es solo observación.
</reglas>

<deliverables>
- core/generation/compactor.py + tests
- Migración para context_compactor_shadow_log
- Integración en context.py
- Después de 48h: análisis con decisión go/no-go para Phase 3
</deliverables>
</instructions>
```

---

### Worker A3.4 — Live Rollout with Feature Flag

```xml
<instructions>
<role>
Eres un ingeniero de Clonnect especializado en rollouts progresivos.
</role>

<context>
Sprint 5 ARC3 Phase 3. PromptSliceCompactor + StyleDistillCache ya están
shadowed y validados. Ahora rollout a producción con sticky hashing.
Leer: docs/sprint5_planning/ARC3_compaction.md §3 Phase 3 completo.
Leer: docs/sprint5_planning/ARC3_phase1_distill_validation.md (validation gate).
Leer: docs/sprint5_planning/ARC3_phase2_shadow_analysis.md (shadow gate).
</context>

<objetivo>
Activar compactor + distill cache en producción de forma gradual, con
kill switch y monitoring en tiempo real.
</objetivo>

<tareas>
1. Feature flag: `USE_COMPACTION` en creator_runtime_config (per-creator
   rollout_pct field).
2. Sticky hashing:
   ```python
   def is_in_rollout(lead_id: UUID, creator_id: UUID) -> bool:
       pct = get_creator_config(creator_id).compaction_rollout_pct
       hash_val = int(hashlib.md5(f"{lead_id}".encode()).hexdigest(), 16) % 100
       return hash_val < pct
   ```
3. En services/context.py: si is_in_rollout → usar compactor.pack() real
   (reemplazar prompt); else → legacy assembly.
4. Dashboard de rollout: `railway run python scripts/compaction_rollout_status.py`
   → muestra rollout_pct per creator + metrics.
5. Rollout schedule:
   - Día 1 (Lun): Stefano 10%
   - Día 2: Stefano 25%
   - Día 3: Stefano 50% + Iris 10%
   - Día 5: Stefano 100% + Iris 50%
   - Día 7: Iris 100%
6. Monitoring continuo:
   - CCEE composite (20 scenarios/día por creator activo)
   - Latency P95
   - Error rate
   - Doc D truncation rate comparativa
7. Kill switch: `railway run python scripts/disable_compaction.py --creator all`
   → setea rollout_pct=0 para todos.
</tareas>

<reglas>
- NO activar sin validación Phase 1 + Phase 2 OK.
- ROLLBACK AUTOMÁTICO si CCEE composite regresa > -5 puntos vs baseline.
- Comunicar a Manel cada rollout step antes de ejecutar.
- Mantener legacy code path durante 4 semanas post-100% rollout (revertir si needed).
</reglas>

<deliverables>
- Feature flag implementado + tests
- Sticky hash en prod
- Rollout logs día por día en docs/sprint5_planning/ARC3_phase3_rollout_log.md
- Final report con CCEE comparativa 100% pre vs post
</deliverables>
</instructions>
```

---

### Worker A3.5 — CircuitBreaker Implementation

```xml
<instructions>
<role>
Eres un ingeniero backend Python, especialista en resilience patterns.
</role>

<context>
Sprint 5 ARC3 Phase 4. Añadir CircuitBreaker como última línea de defensa
contra retry loops y LLM failures sostenidos.
Leer: docs/sprint5_planning/ARC3_compaction.md §2.4 completo.
Leer: core/providers/anthropic_provider.py y gemini_provider.py para entender
entry points actuales.
Leer: docs/audit_phase2/W5_cc_gating_deep_dive.md §4.3 para trace del edge case.
</context>

<objetivo>
Implementar CircuitBreaker Python con Redis backend, integrarlo en el pipeline
de generación, validar comportamiento en staging.
</objetivo>

<tareas>
1. Implementar `core/generation/circuit_breaker.py`:
   - BreakerState dataclass
   - CircuitBreaker clase con check/record_failure/record_success
   - FailureType enum (HARD vs SOFT)
   - Redis backend (usar instancia existente)
2. Fallback responses: `core/generation/fallback_responses.py` con diccionario
   FALLBACK_RESPONSES por language.
3. Integración en services/generation.py:
   ```python
   if not await breaker.check(creator_id, lead_id):
       return await get_fallback_response(creator_id, lead_id)
   try:
       response = await llm.generate(...)
       if is_soft_failure(response):
           await breaker.record_failure(creator_id, lead_id, "soft_...")
       else:
           await breaker.record_success(creator_id, lead_id)
   except LLMTimeoutError:
       await breaker.record_failure(creator_id, lead_id, FailureType.LLM_TIMEOUT)
       return fallback
   ```
4. Alerting: on trip → alert_security_event (reutilizar QW3).
5. Tests:
   - Unit: state transitions (healthy → tripped → cooldown → healthy).
   - Integration: simular 3 failures → verificar trip + alert.
   - Load test: 100 req/s con 10% failure rate, verificar estabilidad.
6. Staging validation:
   - Forzar 3 timeouts via mock → verificar trip + fallback response.
   - Verificar reset después de success.
</tareas>

<reglas>
- FailureType taxonomy estricta — solo HARD failures cuentan siempre.
- TRIP_COOLDOWN_SECONDS=60, MAX_CONSECUTIVE_FAILURES=3 (valores CC-alineados).
- NO fallback si el error es del usuario (e.g., content filter por policy violation del lead).
- Redis keys con TTL para evitar leaks (RESET_WINDOW_SECONDS=300).
</reglas>

<deliverables>
- core/generation/circuit_breaker.py + tests
- core/generation/fallback_responses.py
- Integración en services/generation.py
- Staging test report
- Deploy a prod (no requiere rollout gradual — es protección)
</deliverables>
</instructions>
```

---

### Worker A3.6 — Runbook + Observability

```xml
<instructions>
<role>
Eres un SRE de Clonnect, responsable de operabilidad.
</role>

<context>
Sprint 5 ARC3 Phase 5. El sistema de compactación ya está en producción.
Dejarlo operable: runbook, dashboards, alertas.
Leer: docs/sprint5_planning/ARC3_compaction.md §3 Phase 5 + §4 métricas.
Leer: docs/runbooks/ para ver el formato de otros runbooks.
</context>

<objetivo>
Producir documentación operacional para que cualquier eng pueda:
- Ajustar ratios per-creator
- Re-generar distillations
- Interpretar alertas
- Debuggear trips del circuit breaker
</objetivo>

<tareas>
1. Runbook `docs/runbooks/compaction_tuning.md`:
   - Cómo revisar si un creador necesita distillation.
   - Cómo cambiar compaction_ratios via creator_runtime_config.
   - Cómo forzar re-distillation (comando + validación post).
   - Troubleshooting común (distill cache miss sostenido, trip rate alto, etc).
2. Dashboards Grafana (crear dashboard JSON en docs/observability/):
   - Panel 1: `compaction_applied_rate` time-series per creator.
   - Panel 2: `distill_cache_hit_rate` gauge.
   - Panel 3: `circuit_breaker_trips` rolling 24h.
   - Panel 4: `doc_d_truncation_rate` legacy vs new comparative.
   - Panel 5: CCEE composite rolling 7d.
3. Alertas (Prometheus AlertManager rules):
   - Distill cache miss > 5% sostenido 30 min → warning.
   - Circuit breaker trip rate > 0.5% sostenido 10 min → critical.
   - Compaction applied > 30% sostenido 1h → warning (budget insuficiente).
   - Whitelist overflow > 0 → critical (patológico).
4. Incident response playbook para cada alerta.
</tareas>

<reglas>
- Runbooks en español (convención del repo).
- Comandos copy-paste con `railway run ...` exactos.
- Dashboard JSON debe importar sin errores en Grafana 10+.
- Alertas con severity correcta (warning vs critical).
</reglas>

<deliverables>
- docs/runbooks/compaction_tuning.md
- docs/observability/compaction_dashboard.json
- alerts/compaction_rules.yml (Prometheus AlertManager)
- Playbook integrado en runbook principal
</deliverables>
</instructions>
```

---

## 9 · Open Questions

### Q1 — ¿Distilled version se regenera on-change automáticamente?

**Opción A:** Hook en prompt update → encola job → regenera en < 5 min.
**Opción B:** Cron nocturno, latencia de 0-24h hasta nueva versión.
**Opción C:** Regeneración manual trigger.

**Impacto:** Opción A añade complejidad operacional (queue, retries). Opción B simple pero "tono lunes" puede servirse todo lunes con distilled del domingo.

**Recomendación tentativa:** B + C (cron + trigger manual). Re-evaluar post-100% rollout.

---

### Q2 — ¿Distilled para ES + CA + EN?

Iris escribe 80% ES, 15% CA, 5% EN. ¿Distillation per-idioma o única?

**Opción A:** Una distillation que preserve multilingual character.
**Opción B:** 3 distillations separadas, switch per-turn según lang del lead.

**Impacto:** B triplica cost + complexity. A es riesgo si la compression pierde señal CA/EN en favor del ES dominante.

**Recomendación tentativa:** A con validación CCEE específica para CA y EN subsets.

---

### Q3 — ¿CircuitBreaker per-lead o per-creator?

**Actual:** `state(creator_id, lead_id)` → per-conversación.

**Alternativa:** `state(creator_id)` → per-creator (si LLM provider tiene problema, todos los leads ven fallback).

**Consideración:** Per-lead puede dejar pasar fallos sistémicos. Per-creator puede ser demasiado agresivo.

**Recomendación tentativa:** Dual breaker: per-lead (3 failures) AND per-creator (20 failures en 5 min) — lo que dispare primero.

---

### Q4 — ¿Qué hacer si ambos CCEE (full vs distilled) bajan?

Edge case: el propio CCEE v5.3 puede tener ruido ±2 puntos. Si el delta es -3 pero ambos bajan, no sabemos si es ruido o regresión real.

**Mitigación:** Correr 3x el CCEE (60 scenarios totales), reportar variance. Si variance > 2 puntos, el gate -3 es insuficiente.

---

### Q5 — ¿Compaction interactúa bien con ARC2 (memory)?

**Escenario:** ARC2 emite `lead_memories` con 20 memories de 100 chars c/u = 2000 chars. Compactor con ratio 0.20 sobre budget 8000 = cap 1600 chars → 4 memories eliminadas.

**Pregunta:** ¿Qué 4? ¿La más antigua? ¿La de menor similarity?

**Recomendación tentativa:** ARC2 expone memories ya rankeadas por relevance. Compactor trunca desde el final (menos relevantes primero).

---

## 10 · Appendix

### 10.1 Glosario

- **Doc D:** Alias interno del `style_prompt` de un creador (voz, tono, ejemplos).
- **Distillation:** Compresión semántica via LLM (vs truncación mecánica).
- **Whitelist:** Conjunto de secciones del prompt que nunca se truncan.
- **Circuit breaker:** Patrón de resilience — detiene operaciones cuando fallan consecutivamente.
- **Shadow mode:** Ejecutar lógica en paralelo sin aplicarla, solo logging.
- **Sticky hash:** Hash determinístico sobre lead_id para que el mismo lead siempre vea la misma versión (A/B).

### 10.2 Referencias

- W6 §5.3 (propuestas A, B, D): strategies a implementar.
- W7 §9 Decisión C: compaction gap.
- QW2 outcome: mechanical truncation validation (-10.5 CCEE).
- CC source: `createAutoCompact`, `microCompact`, `reactiveCompact` en claude-code v4.

### 10.3 Post-sprint acceptance checklist

- [ ] 3 creators con distilled version validada (ΔCCEE ≥ -3).
- [ ] PromptSliceCompactor en prod al 100% de leads.
- [ ] CircuitBreaker deployed y validado en staging.
- [ ] Doc D truncation rate ≤ 2% (medido 7 días post-rollout).
- [ ] S3 recovery ≥ 65 (medido vía CCEE v5.3 en scoring-batch scenarios).
- [ ] Iris CCEE composite ≥ 70 (no regresión).
- [ ] Dashboards + alertas en producción.
- [ ] Runbook publicado.
- [ ] Retrospective documentada en `docs/sprint5_planning/ARC3_retrospective.md`.
