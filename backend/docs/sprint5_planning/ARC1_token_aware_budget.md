# ARC1 — Token-aware Budget Orchestrator

**Sprint arquitectónico:** ARC1 (de 5 del plan W7 §9 Track 2).
**Duración estimada:** 4 semanas (1 para shadow + flag, 1 para staging/CCEE, 1 para A/B rollout, 1 para legacy removal).
**Fuentes input:** W7 §6 + §8.C + §9.ARC1, W3 completo (token analytics), W5 §0-§2 (gating dispatcher + `maybe()` wrapper), CRUCE §D10-D11.
**Dependencias:** Ninguna de entrada. Salida bloqueante para ARC3 (compaction triggers dependen del orchestrator).
**Estado del doc:** self-contained — un worker ejecutor puede leer este doc sin necesidad de W7.

---

## 0 · TL;DR ejecutivo

**Problema:** El budget de contexto de Clonnect (`MAX_CONTEXT_CHARS=8000`) está roto por **3 razones estructurales independientes** (W7 §8.C):

1. **Unidad incorrecta:** CHARS en lugar de TOKENS → ratio CHAR/TOKEN varía 2.5× entre ASCII y UTF-8 con tildes (W7 §D10, W3 §5).
2. **Sin cap per-section:** `style_prompt` puede consumir 66-77% del budget para Iris sin que el sistema lo limite (W3 §3).
3. **Sin orchestrator:** cada sección se añade y al final `_smart_truncate_context` hace skipping por ordinal (CRITICAL → HIGH → MEDIUM → FINAL), no por cost/value (W7 §D11).

**Solución:** reescribir `_assemble_context` como un **orchestrator con token-counter real + cap per-section + selección greedy por value/cost**, inspirado en el dispatcher paralelo de CC `getAttachments()` con su `maybe()` wrapper (W5 §0).

**Impacto esperado CCEE:** +3-5 puntos composite, recuperación de S1 Iris (>75), zero regresión en S3, L1, L3, K1 (métricas definidas en §4).

**Archivos afectados:** ~10 archivos Python (core + 6 nuevos), 1 migración ligera (schema `section_budgets` opcional), 0 DB breaking changes.

**Rollout:** 5 fases con feature flag `ENABLE_BUDGET_ORCHESTRATOR` (default OFF durante shadow, A/B 10%→50%→100%, luego legacy removal).

---

## 1 · Problema que resuelve (evidencia cuantitativa)

### 1.1 El trípode del budget roto (W7 Decisión C, §8.C)

Cada una de las 3 razones sobreviven aunque se fixen las otras dos — por eso es un **refactor arquitectónico**, no 3 bugs aislados.

**Razón 1 — CHARS vs TOKENS (B14, D10)**

`context.py:936` define `MAX_CONTEXT_CHARS=8000`. Ese número se compara contra `len(combined_context)`. Consecuencia (W3 §5.2):

| Sección | Estimación CROSS_SYSTEM (tokens) | Real medido (Iris) | Error |
|---------|----------------------------------|---------------------|-------|
| `style_prompt` | 325 | 1,383 | **+4.25× subestimado** |
| `history` (10 turns) | 600 | 87 | **−7× sobreestimado** |
| `few_shots` | 250 | 287 | 1.15× (OK) |
| `audio` | 120 | 180 | 1.5× |
| `rag` | 300 | 300 | 1.0× (OK) |

El error estructural es **asimétrico por sección**: `style` en español con tildes es sistemáticamente caro; `history` (mensajes cortos de DM) es sistemáticamente barato. Ninguna cantidad de ajuste manual al `MAX_CONTEXT_CHARS` resuelve esto — se necesita tokenizer real del provider.

**Razón 2 — No hay cap per-section (B13)**

Los 20 escenarios de W3 confirman:

| Creator | style (tokens) | % del total | Comportamiento |
|---------|----------------|-------------|-----------------|
| Iris Bertran | 1,383 | 66% (P95: 77%) | Style **SIEMPRE** >20% budget |
| Stefano Bonanno | 174 | 21% (P95: 30%) | Style **frecuentemente** >20%, pero fewshot también |

Para Iris S8 (worst case):

```
style:      5,535 chars (69.2% del char budget)
fewshot:      665 chars  (8.3%)
recalling:    ~980 chars (12.2%)
─────────────────────────────
Subtotal:   7,180 chars (89.8%)
RAG budget:   820 chars restantes → rag se trunca parcialmente
```

No hay mecanismo en el código actual para preguntar "¿puedo recortar style a 800 tokens si es necesario?" — el style se inyecta completo siempre.

**Razón 3 — No hay orchestrator (D11)**

`context.py:952-967` construye una lista `assembled` donde cada sección es un string ya materializado. Luego `_smart_truncate_context` (líneas 980-989) skipea secciones enteras en orden ordinal:

```
FINAL → MEDIUM → HIGH → CRITICAL
(citations, output_style) → (hier_memory, adv_memory) → (audio, rag) → (style, few_shots, recalling)
```

Problemas:
- Skipping binario: una sección se inyecta o se elimina, nunca se reduce parcialmente.
- Ranking ordinal: asume que "citations" < "rag" en valor, pero para un product-query explícito el rag puede ser la única señal útil.
- No conoce coste real: elimina `audio` (valor alto para intent purchase) antes de recortar `style` (valor estático per-creator).

### 1.2 Evidencia complementaria

**W3 §7:** "El context pressure real existe en el **char budget interno** (`MAX_CONTEXT_CHARS=8000`), NO en el context window del modelo (32K). El modelo tiene 7× más capacidad de la que se usa. El real bottleneck es el char budget." → confirma que el refactor es **per-section caps + token-counter**, no aumentar el window.

**W5 §0 (CC diseño):** `getAttachments()` es dispatcher paralelo con ~38 gates, cada uno en un `maybe()` wrapper con timeout 1s y fail-silent. Cap per-categoría hard-coded dentro de cada gate (`MAX_MEMORY_BYTES=4096`). Cap session-wide (`MAX_SESSION_BYTES=60KB`). → Clonnect no necesita 38 gates, pero sí la disciplina: **cap per-section + fail-silent + orchestrator-con-budget**.

**W5 §2.1 (relevant_memories gate):**
- `MAX_MEMORY_LINES=200`, `MAX_MEMORY_BYTES=4096`, 5 archivos máximo → 20KB/turn
- `MAX_SESSION_BYTES=60KB` acumulado
- Byte-counting via message scanning → compaction resetea automáticamente
→ Pattern transferible: cap **y** session-wide cap con auto-reset al compactar.

### 1.3 Por qué "arreglar `MAX_CONTEXT_CHARS`" no es suficiente

Tres contraejemplos:
1. Subir a 12,000 chars (recomendación W3 §7 rec 1) elimina truncation en Iris pero **no** resuelve Razón 1 (sigue en chars, no tokens).
2. Activar `USE_COMPRESSED_DOC_D` para Iris (W3 §7 rec 2) reduce style pero **QW2 ya probó** que pierde −10.5 CCEE composite (memoria del sistema persona_compiler).
3. Ambas juntas no resuelven Razón 3: el orchestrator sigue skipping por ordinal, no por value.

**Conclusión:** el refactor ARC1 es necesario para los 3 problemas; parches puntuales no bastan.

---

## 2 · Diseño técnico

### 2.1 Archivos afectados (inventario completo)

**A modificar:**

| Archivo | Cambio | Líneas aprox |
|---------|--------|--------------|
| `core/dm/phases/context.py` | Reemplazar `_assemble_context` (current ~100 LOC en 936-996) con llamada a orchestrator | −100 / +20 |
| `core/dm/phases/generation.py` | Ajustar `_assemble_user_prompt` para consumir `AssembledContext` object en vez de string | +30 |
| `core/dm/phases/postprocessing.py` | Consumir `context.sections_selected` para telemetry | +15 |
| `services/prompt_service.py::PromptBuilder.build_system_prompt` | Aceptar secciones ya budget-packed como input | +20 |
| `core/dm/phases/detection.py` | Emitir `budget_estimate_pre_llm` para observability | +10 |

**A crear:**

| Archivo | Propósito |
|---------|-----------|
| `core/dm/budget/orchestrator.py` | Clase `BudgetOrchestrator`, método `pack(sections, budget)` |
| `core/dm/budget/section.py` | Dataclass `Section` + `Priority` enum + helpers |
| `core/dm/budget/tokenizer.py` | Wrapper alrededor del tokenizer del provider activo |
| `core/dm/budget/gates/__init__.py` | Módulo de gates per-section (análogos a CC `maybe()`) |
| `core/dm/budget/gates/style.py` | Gate de style con cap per-creator |
| `core/dm/budget/gates/rag.py`, `.../memory.py`, `.../dna.py`, `.../audio.py`, `.../fewshots.py`, `.../history.py`, `.../commitments.py` | Un gate por sección existente |
| `core/dm/budget/metrics.py` | Emission helpers (Prometheus or logger) |
| `tests/budget/test_orchestrator.py` | Unit tests |
| `tests/budget/test_gates.py` | Gate tests |

**A no modificar (por contrato):**
- `api/database.py` (pool config protegida por CLAUDE.md).
- `core/providers/gemini_provider.py` (rate limits protegidos).
- Schemas de DB existentes (no hay cambios de datos).

### 2.2 Contract `Section` + `AssembledContext`

```python
# core/dm/budget/section.py
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Optional

class Priority(IntEnum):
    CRITICAL  = 4   # style, few_shots, system hardcoded rules
    HIGH      = 3   # rag, audio, memory_engine facts
    MEDIUM    = 2   # dna, commitments, frustration_note
    LOW       = 1   # hier_memory, advanced_section
    FINAL     = 0   # citations, output_style_note, kb

@dataclass(frozen=True)
class Section:
    name: str                      # 'style', 'rag', 'dna', ...
    content: str                   # texto ya materializado
    priority: Priority
    cap_tokens: int                # hard cap per-section
    value_score: float             # cost/benefit estimado (0-1)
    compressor: Optional[Callable[[str, int], str]] = None
    # compressor opcional: si token_count > cap, compressor(content, cap) → content_shorter
    metadata: dict = field(default_factory=dict)

@dataclass
class AssembledContext:
    combined: str                                 # string ensamblado (para backward compat)
    sections_selected: list[Section]              # qué se incluyó
    sections_dropped: list[Section]               # qué se eliminó (para telemetry)
    sections_compressed: list[tuple[Section, int]]# (section, new_tokens) si hubo compression
    total_tokens: int
    budget_tokens: int
    utilization: float                            # total_tokens / budget_tokens
```

### 2.3 Algoritmo `greedy_pack`

```python
# core/dm/budget/orchestrator.py
class BudgetOrchestrator:
    def __init__(self, tokenizer, budget_tokens: int, session_cap_tokens: int | None = None):
        self.tokenizer = tokenizer
        self.budget = budget_tokens
        self.session_cap = session_cap_tokens

    def pack(self, sections: list[Section]) -> AssembledContext:
        """
        Selecciona el subset de `sections` que maximiza
            sum(value_score * included)
        sujeto a:
            sum(min(tokens(s), s.cap_tokens) for s in included) <= budget

        Algoritmo: greedy por value/cost ratio, con restricción de Priority.
        CRITICAL se intenta siempre (comprimiendo si excede cap).
        El resto compite por budget restante.
        """
        tokenized = [(s, self.tokenizer.count(s.content)) for s in sections]

        # 1) CRITICAL obligatorio (con compression si excede cap)
        result: list[Section] = []
        dropped: list[Section] = []
        compressed: list[tuple[Section, int]] = []
        remaining = self.budget

        for section, tok in sorted(tokenized, key=lambda p: -p[0].priority):
            if section.priority != Priority.CRITICAL:
                break
            effective_tok = min(tok, section.cap_tokens)
            if tok > section.cap_tokens and section.compressor:
                new_content = section.compressor(section.content, section.cap_tokens)
                new_tok = self.tokenizer.count(new_content)
                section = Section(**{**section.__dict__, 'content': new_content})
                effective_tok = new_tok
                compressed.append((section, new_tok))
            if effective_tok > remaining:
                # CRITICAL no cabe ni comprimido — fallback: truncate hard
                section = Section(**{**section.__dict__,
                                      'content': self.tokenizer.truncate(section.content, remaining)})
                effective_tok = remaining
                compressed.append((section, effective_tok))
            result.append(section)
            remaining -= effective_tok

        # 2) Resto: greedy por value / cost
        rest = [(s, tok) for s, tok in tokenized if s.priority != Priority.CRITICAL]
        rest.sort(key=lambda p: -(p[0].value_score / max(p[1], 1)))

        for section, tok in rest:
            effective_tok = min(tok, section.cap_tokens)
            if effective_tok <= remaining:
                if tok > section.cap_tokens and section.compressor:
                    new_content = section.compressor(section.content, section.cap_tokens)
                    section = Section(**{**section.__dict__, 'content': new_content})
                    effective_tok = self.tokenizer.count(new_content)
                    compressed.append((section, effective_tok))
                result.append(section)
                remaining -= effective_tok
            else:
                dropped.append(section)

        combined = "\n\n".join(s.content for s in result)
        return AssembledContext(
            combined=combined,
            sections_selected=result,
            sections_dropped=dropped,
            sections_compressed=compressed,
            total_tokens=self.budget - remaining,
            budget_tokens=self.budget,
            utilization=(self.budget - remaining) / self.budget,
        )
```

**Justificación del greedy:** es NP-duro óptimo (knapsack 0/1), pero con ≤15 secciones y tiempos <2ms. No se necesita DP. El orden descendente por `value/cost` es la heurística estándar y mantiene la decisión trazable.

### 2.4 Tokenizer wrapper

```python
# core/dm/budget/tokenizer.py
class TokenCounter:
    """Wrapper agnóstico al provider. Prioridad:
       1. tiktoken (OpenAI compatible, GPT-4o/mini) con encoding 'cl100k_base'
       2. Gemini tokens_counter (google.generativeai) para gemini-*
       3. Aproximación 1:4 chars→tokens como fallback seguro
    """
    def __init__(self, provider: str, model: str):
        self.provider = provider
        self.model = model
        self._impl = self._resolve()

    def _resolve(self):
        if self.provider in ('openai', 'openrouter'):
            import tiktoken
            try:
                return tiktoken.encoding_for_model(self.model)
            except KeyError:
                return tiktoken.get_encoding('cl100k_base')
        if self.provider == 'gemini':
            # google.generativeai expone count_tokens
            import google.generativeai as genai
            return genai.GenerativeModel(self.model)
        return None  # fallback a chars//4

    def count(self, text: str) -> int:
        if not text:
            return 0
        if self._impl is None:
            return len(text) // 4  # fallback
        if self.provider in ('openai', 'openrouter'):
            return len(self._impl.encode(text))
        if self.provider == 'gemini':
            return self._impl.count_tokens(text).total_tokens
        return len(text) // 4

    def truncate(self, text: str, max_tokens: int) -> str:
        # Naive: convertir a tokens, cortar, decodificar
        if self._impl is None:
            return text[: max_tokens * 4]
        if self.provider in ('openai', 'openrouter'):
            tokens = self._impl.encode(text)
            return self._impl.decode(tokens[:max_tokens])
        if self.provider == 'gemini':
            # Gemini no expone decode — fallback por chars con ratio real
            ratio = len(text) / max(self.count(text), 1)
            return text[: int(max_tokens * ratio)]
        return text[: max_tokens * 4]
```

**Contrato de estabilidad:** el tokenizer **no es fuente de verdad** para facturación (esa es el provider). Es una estimación suficientemente precisa para budget (error esperado <3%).

### 2.5 Caps per-section propuestos

Tabla derivada de W3 medición real + W6 §5.3 propuesta A + W5 §2.1 pattern:

| Sección | `cap_tokens` | Justificación | Compressor |
|---------|--------------|---------------|------------|
| `style` | 800 | Media Iris=1383; Stefano=174. Cap a 800 cubre Stefano holgado, fuerza a Iris a compression (ver ARC3). | StyleDistillCache lookup |
| `few_shots` | 350 | Media 185; P95 261. Cap 350 permite hybrid + intent-matched. | Drop ejemplos mayores primero |
| `recalling` (dna+memory+state+frustration) | 400 | Media combined 179-290. Cap 400 holgado. | Drop state+frustration si exceeds |
| `audio` | 250 | P95=180. Cap 250 para casos extremos de transcription. | Truncate tail |
| `rag` | 350 | P95=137. Cap 350 permite top-5 chunks. | Drop chunks extras |
| `history` | 500 | Media 87; P95=160. Cap 500 para conversaciones activas. | Drop mensajes antiguos |
| `commitments` | 150 | Heurística (no medido en W3). | Drop commitments antiguos |
| `hier_memory` | 200 | Dormant; cap bajo por si se activa. | N/A |
| `kb` | 100 | Legacy (kb files excluidos de deploy). | N/A |
| `citations` | 50 | Final priority. | Drop entero |
| `friend_context` | 0 | Siempre "" runtime (context.py:691-694). | — |

**Total teórico:** 3,150 tokens. Con el resto (system hardcoded, base messages) ≈ 4,000 tokens budget total sugerido.

### 2.6 Value-score heuristic (cómo se calcula `s.value_score`)

Por sección, combinación de 3 señales (normalizadas 0-1):

```python
def compute_value_score(section_name: str, context: DmContext) -> float:
    base = {
        'style':       1.00,  # identity-critical
        'few_shots':   0.95,
        'recalling':   0.80,
        'audio':       0.70 if context.cognitive_metadata.get('audio_intel') else 0.0,
        'rag':         0.75 if context.cognitive_metadata.get('rag_signal') else 0.30,
        'history':     0.50,
        'commitments': 0.60 if context.cognitive_metadata.get('commitments_pending') else 0.0,
        'hier_memory': 0.40,
        'kb':          0.10,
        'citations':   0.20,
    }.get(section_name, 0.5)

    # Modificador por intent
    intent = context.cognitive_metadata.get('intent_category')
    if intent == 'purchase_intent' and section_name == 'rag':
        base *= 1.2
    if intent == 'casual' and section_name == 'rag':
        base *= 0.5
    return min(base, 1.0)
```

**Calibración:** los valores iniciales salen de evidence qualitative (W3 §6: "rag varies 0-137 tokens según signal"). Durante la Fase 3 (staging) se calibran contra CCEE.

### 2.7 Integración con `context.py`

Flujo propuesto:

```python
# core/dm/phases/context.py (refactor de _assemble_context)

async def _assemble_context(dm_ctx: DmContext) -> AssembledContext:
    if not os.getenv('ENABLE_BUDGET_ORCHESTRATOR', 'false') == 'true':
        return _assemble_context_legacy(dm_ctx)  # path antiguo

    # 1) Construir cada sección via gates (análogo a CC `maybe()`)
    sections: list[Section] = []
    for gate_name, gate_fn in [
        ('style',       gates.style.build),
        ('few_shots',   gates.fewshots.build),
        ('recalling',   gates.memory.build),
        ('audio',       gates.audio.build),
        ('rag',         gates.rag.build),
        ('history',     gates.history.build),
        ('commitments', gates.commitments.build),
    ]:
        try:
            section = await asyncio.wait_for(gate_fn(dm_ctx), timeout=0.5)
            if section is not None:
                sections.append(section)
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"gate {gate_name} failed: {e}")
            # fail-silent (pattern CC maybe)

    # 2) Pack con orchestrator
    tokenizer = TokenCounter(dm_ctx.provider, dm_ctx.model)
    orchestrator = BudgetOrchestrator(
        tokenizer=tokenizer,
        budget_tokens=int(os.getenv('BUDGET_ORCHESTRATOR_TOKENS', '4000'))
    )
    assembled = orchestrator.pack(sections)

    # 3) Emit telemetry (consumed by ARC5 observability)
    emit_budget_metrics(assembled, dm_ctx)

    return assembled
```

**Backward compat:** `_assemble_context_legacy` es el código actual renombrado. Durante Fase 1-3 vive en paralelo; durante Fase 5 se elimina.

### 2.8 Impacto en cache (importante para Sprint 4 boundary)

`core/dm/cache_boundary.py` (untracked, nuevo) asume que `style_prompt` + `few_shots` son el prefix cacheable. Con ARC1:

- `style_prompt` puede ser comprimido (si StyleDistillCache está ON en ARC3). **Hash diferente por creator** → invalida cache. No es regresión: hoy el cache se invalida igual al cambiar `MAX_CONTEXT_CHARS`.
- `few_shots` puede ser reordenado si greedy elige subset distinto por escenario.

**Mitigación:** el orchestrator marca sections con `cacheable=True` (style, few_shots hybrid) y las empaqueta primero, preservando orden consistente. Sections dinámicas (rag, audio, recalling) van al final.

**Monitoreo:** métrica `cache_hit_rate_pre_arc1` vs `cache_hit_rate_post_arc1`. Si degrada >10%, rollback.

---

## 3 · Plan de rollout (5 fases)

### Fase 1 — Implementación + shadow (Week 1)

**Objetivo:** código funcional en paralelo al actual, no invocado.

**Tareas:**
1. Crear archivos `core/dm/budget/*` (orchestrator, tokenizer, section, gates).
2. Implementar unit tests con cobertura ≥90% en `tests/budget/*`.
3. Añadir flag `ENABLE_BUDGET_ORCHESTRATOR` (default `false`).
4. Añadir "shadow mode": si `BUDGET_ORCHESTRATOR_SHADOW=true`, ejecuta orchestrator **en paralelo** al legacy y compara outputs, sin cambiar el prompt enviado.

**Deliverable:** PR mergeado, tests green, shadow mode ON en staging.

**Verificación:** logs muestran `budget_orchestrator_shadow_diff_tokens` por request sin drift del LLM.

### Fase 2 — Flag OFF en producción (Week 1 tail)

**Objetivo:** código desplegado, dormido.

**Tareas:**
1. Deploy a Railway main.
2. Verificar que `ENABLE_BUDGET_ORCHESTRATOR=false` en env prod.
3. Confirmar 24h sin errores de boot (import chain) ni regresión CCEE.

**Deliverable:** deploy verde, smoke tests pasan.

**Verificación:** `railway logs -n 500 | grep -i budget_orchestrator` muestra logs shadow pero 0 errors.

### Fase 3 — Staging + CCEE (Week 2)

**Objetivo:** activar en staging, medir CCEE full-suite.

**Tareas:**
1. En staging (`BUDGET_ORCHESTRATOR_STAGING=true`): activar flag para 1 creator piloto (Iris).
2. Run CCEE v5.3 26b + 31b para Iris sobre los 20 escenarios.
3. Comparar contra baseline actual (`ccee_v53_26b_sprint31_final.json`).
4. Calibrar `value_score` por sección si hay regresión en intent específicos (ej: audio).
5. Si composite ∆ > −2 puntos, iterar config; si ∆ < −2, rollback y debugging.

**Deliverable:** reporte `docs/audit_phase2/ARC1_staging_ccee.md` con comparación scenario-by-scenario.

**Verificación:** métricas clave:
- Composite Iris ≥ baseline + 0
- S1 Iris ≥ 75 (recovery esperado)
- S3, L1, L3, K1 estables (∆ ±2)

### Fase 4 — A/B rollout producción (Week 3)

**Objetivo:** rollout gradual con rollback automático.

**Tareas:**
1. Implementar A/B sampling por `lead_id` hash:
   ```python
   use_orchestrator = hash(lead_id) % 100 < os.getenv('BUDGET_ORCHESTRATOR_PCT', '0')
   ```
2. Rollout 10% → 50% → 100% en 3 ventanas de ~3 días cada una.
3. En cada ventana:
   - Monitor: error rate, latency p95, CCEE puntuales (1 scenario por creator).
   - Kill-switch: `BUDGET_ORCHESTRATOR_PCT=0` ante regresión.

**Deliverable:** `docs/audit_phase2/ARC1_rollout_report.md` con métricas por ventana.

**Verificación:** 
- Error rate ∆ < +0.5%
- Latency p95 ∆ < +100ms
- CCEE composite no-regresion (±1.0)

### Fase 5 — Legacy removal (Week 4)

**Objetivo:** eliminar `_assemble_context_legacy` y código muerto.

**Tareas:**
1. Cambiar default `ENABLE_BUDGET_ORCHESTRATOR=true` en env.
2. Después de 1 semana estable, borrar `_assemble_context_legacy` y eliminar el flag.
3. Remover env vars `MAX_CONTEXT_CHARS` si ya no se usan (o mantener como fallback tokenizer-failure).
4. Actualizar `docs/CROSS_SYSTEM_ARCHITECTURE.md` (aunque obsoleto, marcar section §4 como "superseded by ARC1").

**Deliverable:** PR `refactor: remove _assemble_context_legacy`, CI verde.

**Verificación:** smoke tests + 48h producción sin warnings de budget.

---

## 4 · Métricas de éxito

### 4.1 CCEE quantitative gates

| Métrica | Baseline (Sprint 31 final) | Target post-ARC1 | Kill-switch threshold |
|---------|----------------------------|------------------|-----------------------|
| Composite Iris | 70.0 | ≥ 73 | < 68 |
| Composite Stefano | 72.0 | ≥ 72 (estable) | < 70 |
| S1 Iris (greeting new) | ~68 | ≥ 75 | — |
| S3 (product query) | ~72 | ≥ 72 | < 70 |
| S8 worst case Iris | ~65 | ≥ 70 | < 63 |
| L1 persona consistency | ~74 | ≥ 74 | < 72 |
| L3 context retention | ~70 | ≥ 70 | < 68 |
| K1 relationship acuity | ~69 | ≥ 69 | < 67 |

### 4.2 Token budget observability

| Métrica | Fuente | Target |
|---------|--------|--------|
| `budget.utilization.mean` | `AssembledContext.utilization` | 0.70-0.85 típico |
| `budget.utilization.p95` | idem | <0.95 |
| `budget.sections_dropped.count` | `AssembledContext.sections_dropped` | <1 per request mean |
| `budget.sections_compressed.count` | idem | <1.5 per request mean |
| `tokens_actual_at_provider` | LLM response `usage.prompt_tokens` | Diferencia <5% con estimate |

### 4.3 Latency & cost

| Métrica | Baseline | Target |
|---------|----------|--------|
| `dm_phase_context.latency_p95` | ~120ms | ≤150ms |
| `tokens.in.mean` | ~2100 (Iris), ~870 (Stefano) | Estable o −10% |
| `cache_hit_rate_openai` | TBD (medir baseline) | ≥ baseline −10% |

### 4.4 Regresión guards

**Zero tolerance:** error rate `/webhook/instagram` stream. Cualquier ∆>0.5% tras rollout → rollback inmediato.

**Soft tolerance:** latency p99 `+200ms` aceptado si CCEE composite +3; si solo +1, rollback.

---

## 5 · Riesgos y mitigaciones

### R1 — Token counter mismatch entre providers

**Escenario:** tiktoken estima 1,400 para el style pero Gemini factura 1,550. El cap per-section se "salta" y el provider rechaza 413.

**Probabilidad:** media (los tokenizers no son bit-exact entre providers).

**Impacto:** alto (request muere por 413).

**Mitigación:**
- Buffer de seguridad: `budget_tokens_effective = budget_tokens × 0.92` (8% margin).
- Circuit breaker (coordinar con ARC3): si 413 en 3 requests consecutivas, bypass orchestrator 1h.
- Monitorear `tokens_actual_at_provider - tokens_estimated` por provider; ajustar margin si >8%.

### R2 — Value-score mal calibrado → peor que truncación uniforme

**Escenario:** `value_score['audio']=0.70` penaliza audio injustamente en intent `purchase_intent`, CCEE regresa en scenarios con audio.

**Probabilidad:** alta (la calibración inicial es heurística).

**Impacto:** medio (regresión en scenarios específicos).

**Mitigación:**
- Fase 3 obligatoria: medición CCEE en staging antes de producción.
- Intent-dependent modifiers (ver §2.6) calibrados scenario-by-scenario.
- Override per-creator vía tabla `creator_budget_config` (opcional, low priority).
- A/B con rollback automático si scenario específico regresa >3 puntos.

### R3 — Cache invalidation significativa (impacta Sprint 4 cache_boundary)

**Escenario:** el orchestrator reordena secciones o comprime style → hash del prefix cambia → cache miss en 80% de requests.

**Probabilidad:** media.

**Impacto:** alto (coste LLM +20-40%, latency +200ms).

**Mitigación:**
- Empaquetar secciones cacheables (`style`, `few_shots`) primero y en orden fijo.
- Sections dinámicas al final (ya lo hace el diseño greedy por priority).
- Monitor `cache_hit_rate_openai` pre/post; si ∆>10%, ajustar orden o rollback.
- Coordinar con `core/dm/cache_boundary.py` (untracked) el orden del prefix.

### R4 — Compression de CRITICAL sections degrada persona

**Escenario:** style excede cap 800 → compressor lo trunca → voice drift (QW2 ya demostró esto con compressed Doc D mecánico: −10.5 CCEE).

**Probabilidad:** alta si compressor es naive truncate.

**Impacto:** crítico (persona no reconocible).

**Mitigación:**
- **NUNCA** usar truncate naive para style. El `compressor` de style debe ser **StyleDistillCache lookup** (coordinado con ARC3).
- Si `StyleDistillCache` aún no existe (ARC3 posterior), fallback: deshabilitar cap de style en Fase 3-4 (`cap_tokens=9999`) y re-activar cuando ARC3 lande.
- Evidencia: QW2 report confirma pérdida. Memory `project_qw2_compressed_doc_d.md` recuerda: flag USE_COMPRESSED_DOC_D stays off hasta que el compressor sea LLM-distilled, no mecánico.

### R5 — Event loop blocking en tokenizer calls

**Escenario:** tiktoken.encode() en hot path async bloquea event loop → throughput cae.

**Probabilidad:** baja (tiktoken es C-rápido, ~0.1ms por 1k tokens).

**Impacto:** bajo-medio bajo carga.

**Mitigación:**
- Medir con `asyncio.get_event_loop().time()` antes/después en staging.
- Si >5ms en p99: wrap en `asyncio.to_thread()`.
- Para Gemini `count_tokens()`: ya es HTTP call → siempre en `to_thread`.

### R6 — Complejidad del greedy puede introducir non-determinism

**Escenario:** dos sections con mismo `value_score` se desempatan por orden dict iteration, produciendo outputs distintos entre runs.

**Probabilidad:** media.

**Impacto:** medio (tests flaky, CCEE ruidoso).

**Mitigación:**
- Tie-breaker determinista: `key=(- (value/cost), section.name)`.
- Unit tests con fixtures explícitos.

### R7 — Gate timeout 0.5s puede matar sections lentas (ej: DB query en commitments)

**Escenario:** commitments gate depende de `commitment_tracker.fetch()` que hace query DB. En carga, query >500ms → gate devuelve None → commitments missing.

**Probabilidad:** media.

**Impacto:** medio (silent feature degradation).

**Mitigación:**
- Timeouts per-gate configurables (no hardcoded 0.5s).
- Commitments gate: 1.5s (es DB-bound, aceptamos).
- Style gate: 0.1s (es memoria en objeto, debe ser instantáneo).
- Metric `gate.timeout.count` por gate para detectar patrones.

---

## 6 · Dependencias

### 6.1 Inputs (de qué depende ARC1)

- **Ninguno bloqueante.** Puede iniciarse de inmediato.
- **Preferible:** QW4 (metadata orphans cleanup) completado, reduce ruido en observability.
- **Sprint 4 cache_boundary:** no bloqueante pero debe coordinarse (el orchestrator afecta el cache prefix).

### 6.2 Outputs (qué depende de ARC1)

- **ARC3 (compaction):** el `compressor` de style requiere `StyleDistillCache`. ARC1 fija el contract `Section.compressor` que ARC3 implementa. Sin ARC3, el cap de style queda dormant (alto).
- **ARC5 (observability):** el orchestrator emite nuevas métricas tipadas (`budget.*`). ARC5 las consume para el dashboard.
- **ARC4 (mutations):** algunas mutations (e.g. A2c sentence dedup) se pueden eliminar si el orchestrator evita context pressure que las causa.

### 6.3 Secuencia recomendada

```
QW4 (orphans cleanup) → ARC1 Fase 1-5 → ARC3 compressors + Sprint 4 cache
                                      ↘ ARC5 observability
```

---

## 7 · Cronograma detallado

### Week 1 — Implementación + shadow

- **Day 1-2:** Scaffolding. Crear `core/dm/budget/*` con stubs + unit tests mínimos.
- **Day 3-4:** Implementar `TokenCounter` + 3 gates críticos (style, few_shots, rag).
- **Day 5:** Implementar `greedy_pack` + tests cobertura 90%.

**Deliverable:** `core/dm/budget/` completo, 4 gates funcionales, shadow mode instrumentado.

### Week 2 — Staging + CCEE

- **Day 1-2:** Deploy a staging con `ENABLE_BUDGET_ORCHESTRATOR=true` para Iris.
- **Day 3:** Run CCEE v5.3 26b (20 scenarios Iris).
- **Day 4:** Run CCEE v5.3 31b (20 scenarios Iris) + Stefano 20 scenarios 26b.
- **Day 5:** Calibración `value_score`; documento de reporte.

**Deliverable:** `docs/audit_phase2/ARC1_staging_ccee.md`.

**Gate para Week 3:** composite Iris ≥ 73 y no regresión >2 puntos en ningún scenario.

### Week 3 — A/B rollout

- **Day 1:** Rollout 10% (lead_id % 100 < 10). Monitor 24h.
- **Day 3:** Rollout 50%. Monitor 48h.
- **Day 5:** Rollout 100%. Monitor 72h.

**Deliverable:** `docs/audit_phase2/ARC1_rollout_report.md`.

**Gate para Week 4:** 72h a 100% sin regresión.

### Week 4 — Legacy removal

- **Day 1:** PR `refactor: remove _assemble_context_legacy`.
- **Day 3:** CI + smoke tests verde.
- **Day 5:** Merge + deploy + 48h observación.

**Deliverable:** ARC1 done, `DECISIONS.md` actualizado.

---

## 8 · Prompts de workers ejecutores

Cada prompt está ready-to-copy, XML-formatted, self-contained.

### Worker A1.1 — Implementar `budget_orchestrator.py` (Sonnet, 2 días)

```xml
<instructions>
<objetivo>
Implementar el módulo `core/dm/budget/` siguiendo el diseño en
`docs/sprint5_planning/ARC1_token_aware_budget.md` §2.
</objetivo>

<input_obligatorio>
Lee antes:
1. docs/sprint5_planning/ARC1_token_aware_budget.md §2 (Diseño técnico)
2. core/dm/phases/context.py:936-996 (_assemble_context actual)
3. core/dm/phases/generation.py:247-297 (flujo post-context)
</input_obligatorio>

<tareas>
1. Crear core/dm/budget/__init__.py vacío
2. Crear core/dm/budget/section.py con Section dataclass + Priority IntEnum
3. Crear core/dm/budget/tokenizer.py con TokenCounter (tiktoken + fallback)
4. Crear core/dm/budget/orchestrator.py con BudgetOrchestrator.pack()
5. Crear core/dm/budget/metrics.py con emit_budget_metrics()
6. Crear tests/budget/test_section.py + test_tokenizer.py + test_orchestrator.py
7. Cobertura objetivo 90% líneas
</tareas>

<reglas>
- NO modificar context.py aún (Worker A1.2)
- NO tocar postprocessing.py
- Todo en feature branch: feature/arc1-budget-orchestrator
- Python 3.11 compatible
- Type hints estrictos
- Tests usan pytest (seguir patrón en tests/test_persona_compiler.py)
- 4-phase workflow OBLIGATORIO (este worker modifica código)
</reglas>

<verificacion>
- pytest tests/budget/ -xvs → verde
- mypy core/dm/budget/ → 0 errores
- python3 -c "import ast; ast.parse(open('core/dm/budget/orchestrator.py').read())" → OK
</verificacion>
</instructions>
```

### Worker A1.2 — Integrar orchestrator en `context.py` (Sonnet, 1 día)

```xml
<instructions>
<objetivo>
Integrar BudgetOrchestrator en core/dm/phases/context.py via feature flag,
sin romper path legacy.
</objetivo>

<input_obligatorio>
1. docs/sprint5_planning/ARC1_token_aware_budget.md §2.7 (Integración context.py)
2. core/dm/phases/context.py completo
3. Output del Worker A1.1 (core/dm/budget/ ya existente)
</input_obligatorio>

<tareas>
1. Renombrar _assemble_context existente a _assemble_context_legacy
2. Crear nuevo _assemble_context que:
   - Lee flag os.getenv('ENABLE_BUDGET_ORCHESTRATOR', 'false')
   - Si OFF: delega a _assemble_context_legacy (zero-diff path)
   - Si ON: usa BudgetOrchestrator
3. Implementar 4 gates iniciales en core/dm/budget/gates/:
   - style.py (wraps style_prompt logic)
   - fewshots.py (wraps few_shot_section logic)
   - rag.py (wraps rag_context logic)
   - history.py (wraps history aggregation)
4. Añadir shadow mode: si BUDGET_ORCHESTRATOR_SHADOW=true, corre orchestrator
   en paralelo al legacy sin cambiar output real, loggea diff
5. Añadir unit tests de integration
</tareas>

<reglas>
- NO cambiar prompt output cuando flag OFF (backward compat total)
- Shadow mode debe loggear `budget_orchestrator_shadow: tokens_legacy=X tokens_new=Y diff=Z sections_dropped=[...]`
- Si shadow mode falla internamente, NO propagar exception al request
- 4-phase workflow OBLIGATORIO
</reglas>

<verificacion>
- pytest tests/ -xvs → verde (no regression)
- python3 tests/smoke_test_endpoints.py → todas pasan
- Deploy staging con shadow ON → logs muestran diffs pero request LLM unchanged
</verificacion>
</instructions>
```

### Worker A1.3 — Medir CCEE shadow vs legacy (Opus, 1 día)

```xml
<instructions>
<objetivo>
Medir CCEE v5.3 26b + 31b con ENABLE_BUDGET_ORCHESTRATOR=true vs baseline,
para los 20 scenarios Iris + 20 Stefano.
</objetivo>

<input_obligatorio>
1. docs/sprint5_planning/ARC1_token_aware_budget.md §4 (Métricas)
2. Últimos CCEE baselines en tests/ccee_results/iris_bertran/ccee_v53_26b_sprint31_final.json
3. Estructura de CCEE en scripts/run_ccee_v53.py
</input_obligatorio>

<tareas>
1. En staging: activar flag para Iris
2. Correr CCEE v5.3 26b Iris (20 scenarios)
3. Correr CCEE v5.3 31b Iris (20 scenarios)
4. Correr CCEE v5.3 26b Stefano (20 scenarios)
5. Comparar contra baselines Sprint 31 final:
   - Composite ∆
   - Por scenario (S1-S10)
   - Por métrica (L1/L3/K1/S*)
6. Producir tabla de regression/improvement
7. Si regression > 2 puntos en >3 scenarios: iterar value_score config
</tareas>

<output_esperado>
docs/audit_phase2/ARC1_staging_ccee.md con:
- Tabla comparativa baseline vs ARC1 por scenario
- Tabla por métrica composite
- Análisis de regresiones
- Recomendación: go/no-go para Fase 4 rollout
- JSON raw en tests/ccee_results/iris_bertran/ccee_v53_*_arc1.json
</output_esperado>

<reglas>
- NO tocar código producción
- NO cambiar flags de otros creators
- Si composite Iris < baseline − 2 → STOP y reportar
</reglas>
</instructions>
```

### Worker A1.4 — Implementar gates restantes (Sonnet, 2 días)

```xml
<instructions>
<objetivo>
Implementar los 4 gates restantes del orchestrator (recalling/memory, audio,
commitments, dna) para completar la cobertura de secciones.
</objetivo>

<input_obligatorio>
1. docs/sprint5_planning/ARC1_token_aware_budget.md §2.5 (Caps per-section)
2. core/dm/phases/context.py:263-330 (recalling_block, episodic, memory_engine)
3. core/dm/phases/context.py:724-767 (audio_context)
4. core/dm/phases/context.py:430 (commitments inject)
5. services/relationship_dna_service.py (dna_context builder)
</input_obligatorio>

<tareas>
1. Crear core/dm/budget/gates/memory.py (wraps recalling block + memory_engine + episodic)
2. Crear core/dm/budget/gates/audio.py
3. Crear core/dm/budget/gates/commitments.py
4. Crear core/dm/budget/gates/dna.py
5. Tests unitarios por cada gate con mocks del contexto
6. Integration test que corre pipeline completo con los 8 gates
</tareas>

<reglas>
- Cada gate debe ser timeout-configurable (default 0.5s, commitments 1.5s por DB query)
- fail-silent: si gate explota, returna None y loggea
- 4-phase workflow OBLIGATORIO
</reglas>
</instructions>
```

### Worker A1.5 — A/B rollout (Opus + bash, 3 días real-time)

```xml
<instructions>
<objetivo>
Ejecutar rollout gradual 10% → 50% → 100% del budget orchestrator en producción,
con kill-switch.
</objetivo>

<input_obligatorio>
1. docs/sprint5_planning/ARC1_token_aware_budget.md §3 Fase 4
2. Railway dashboard access (env vars management)
3. docs/audit_phase2/ARC1_staging_ccee.md (debe existir y estar green)
</input_obligatorio>

<tareas>
1. Day 1: set BUDGET_ORCHESTRATOR_PCT=10 en Railway prod. Monitor 24h:
   - error_rate_webhook_instagram
   - latency_p95
   - CCEE spot-check: 1 scenario Iris S1 via recorded webhook replay
2. Si green: Day 3 BUDGET_ORCHESTRATOR_PCT=50, monitor 48h
3. Si green: Day 5 BUDGET_ORCHESTRATOR_PCT=100, monitor 72h
4. Kill-switch: BUDGET_ORCHESTRATOR_PCT=0 si cualquier métrica excede threshold
5. Reporte por ventana: CCEE + latency + errors
</tareas>

<output_esperado>
docs/audit_phase2/ARC1_rollout_report.md con:
- Tabla 10%/50%/100% de métricas
- Incidents (si los hubo)
- Recomendación final: proceed to Fase 5 o mantener a 100% con monitoring
</output_esperado>

<reglas>
- NO subir % si la ventana anterior no terminó su periodo de observación
- Rollback automatico si error_rate ∆ > +0.5%
- Coordinate con user (Manel) antes de Day 5 rollout 100%
</reglas>
</instructions>
```

### Worker A1.6 — Legacy removal (Sonnet, 1 día)

```xml
<instructions>
<objetivo>
Eliminar _assemble_context_legacy después de 1 semana estable a 100%.
</objetivo>

<input_obligatorio>
1. docs/audit_phase2/ARC1_rollout_report.md debe mostrar 72h estable
2. Git log: confirmar ARC1 en main ≥ 7 días
</input_obligatorio>

<tareas>
1. Borrar función _assemble_context_legacy de context.py
2. Eliminar flag ENABLE_BUDGET_ORCHESTRATOR (hacer default ON implícito)
3. Eliminar shadow mode code si aún existe
4. Actualizar docstrings
5. Syntax check: python3 -c "import ast; ast.parse(open('core/dm/phases/context.py').read())"
6. Run smoke tests
7. PR "refactor: remove _assemble_context_legacy — ARC1 complete"
</tareas>

<reglas>
- Mantener BUDGET_ORCHESTRATOR_TOKENS como env var configurable (no hardcodear)
- NO tocar MAX_CONTEXT_CHARS (mantener como fallback emergency)
- 4-phase workflow OBLIGATORIO
</reglas>
</instructions>
```

---

## 9 · Open questions (decisiones pendientes)

### Q1 — ¿Budget tokens default = 4000 o 5000?

Argumentos 4000: mantiene margen ~25% respecto a 8K chars actual (≈2000 tokens en el peor caso Iris). Más conservador, menos coste.

Argumentos 5000: aprovecha que el modelo tiene 32K window; Iris P95 sin ajuste ya es 2367 tokens; 5000 da holgura para recalling + audio.

**Recomendación:** empezar en 4000 (seguro), calibrar en Fase 3 según CCEE.

### Q2 — ¿`value_score` hardcoded o en DB per-creator?

Argumentos hardcoded: simple, determinista, A/B testeable.

Argumentos DB: permite afinar por creator (Iris style=1.0 es irrenunciable, Stefano style=0.8 se puede recortar).

**Recomendación:** hardcoded en Fase 1-4; migrar a DB en ARC5 si se valida que afinación per-creator mejora >1 punto CCEE.

### Q3 — ¿Qué hacer cuando CRITICAL no cabe ni comprimido?

Opción A: truncate hard (puede romper persona).
Opción B: bypass budget (mandar al provider; si 413 → reactiveCompact en ARC3).
Opción C: fallback model (ej: GPT-4o-mini con más context).

**Recomendación:** Opción B. El provider rechaza limpio y ARC3 tiene reactiveCompact. Nunca mutilar style sin fallback.

### Q4 — ¿Compressor por gate o centralizado en orchestrator?

Argumentos per-gate: cada sección sabe mejor cómo comprimir su propio contenido (ej: few_shots drops ejemplos largos, rag drops chunks low-score).

Argumentos centralizado: fácil de mantener, testear.

**Recomendación:** per-gate (Section.compressor field), orquestado por orchestrator.

---

## 10 · Apéndice: comparativa con CC `getAttachments`

W5 §0-§2 documenta el dispatcher de CC. Diferencias clave con ARC1:

| Dimensión | CC `getAttachments` | ARC1 `BudgetOrchestrator` |
|-----------|---------------------|---------------------------|
| Gates paralelos | ~38 | ~8-10 |
| `maybe()` wrapper | fail-silent + 5% telemetry | fail-silent + 100% logging |
| Budget | per-cap hard-coded + MAX_SESSION_BYTES=60KB | greedy pack contra `budget_tokens` |
| Selection | ninguna (concat order) | greedy por value/cost |
| Compression | ninguna (drop entero) | per-section compressor opcional |
| Timeout | 1000ms global | 500ms per-gate configurable |
| Feature flags | GrowthBook runtime | env vars runtime |

**Diferencia filosófica:** CC no negocia entre gates (cada uno tiene su cap). ARC1 negocia (greedy). La razón: Clonnect tiene budget global total más apretado (≈4K vs 200K de CC), necesita priorización activa.

---

**Fin ARC1_token_aware_budget.md**
