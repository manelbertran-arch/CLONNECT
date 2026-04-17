# ARC5 — Observability & Typed Metadata

**Sprint:** 5 / Track 2 / ARC5
**Estimación realista:** 3 semanas (2 eng weeks + 1 rollout/tuning)
**Complejidad:** MEDIA
**Dependencias:** QW1 (orphans cleanup, ✅ done), QW3 (security alerting, ✅ done). ARC1-ARC4 emiten nuevas métricas que ARC5 consolida.
**Autor:** Arquitecto Clonnect (AI)
**Fecha:** 2026-04-16

---

## 0 · TL;DR

> **Problema:** W7 §3 mapeó 114 metadata fields en `messages.metadata`. De esos:
> - 65 **orphans** (escritos pero ningún lector) → QW1 eliminó 30 → restan **35 orphans**.
> - 49 con lectores → pero sin **tipado**, sin **alerting**, sin **dashboard**.
>
> No hay contrato: añadir un campo es escribir `metadata["x"] = ...` en cualquier punto. No hay garantía de schema, de consistencia cross-phase, ni de que alguien lo use downstream.
>
> **Solución:**
> 1. **Typed metadata via Pydantic** — cada fase (detection, scoring, generation, post) escribe un modelo tipado. La DB sigue guardando JSONB, pero el contrato se valida en código.
> 2. **`emit_metric` helper** — canal único para Prometheus. Cualquier field instrumentable se emite con una llamada obligatoria. Tests de contrato verifican que cada campo declarado emite métrica.
> 3. **Grafana dashboards** — 4 dashboards (generation pipeline, scoring, memory, compaction) que consumen las métricas.
> 4. **Orphan prevention** — CI check que bloquea PRs que añadan un `metadata["..."] = ...` sin emit_metric ni reader declarado.
>
> **Métrica objetivo:** 0 nuevos orphans post-ARC5. Los 35 restantes: cada uno **resuelto** (consumer added, deprecated, o promoted a metric). Full coverage Grafana > 90% de pipeline métricas.

---

## 1 · Problema que Resuelve

### 1.1 Evidencia W7 §3 — metadata flow

W7 §3 inventarió cada campo escrito a `messages.metadata`:

| Fase | Campos escritos | Con reader | Orphans iniciales | Post-QW1 |
|---|---|---|---|---|
| Detection | 18 | 11 | 7 | 4 |
| Scoring | 32 | 15 | 17 | 9 |
| Generation | 41 | 19 | 22 | 14 |
| Post-gen / mutations | 23 | 4 | 19 | 8 |
| **TOTAL** | **114** | **49** | **65** | **35** |

**Orphans = campos escritos pero nunca leídos, agregados, ni mostrados.** Son puro overhead:
- Ocupan espacio en JSONB (latencia DB).
- Aparentan señal pero no la transmiten.
- Nadie sabe si están "rotos" porque nadie los lee.

### 1.2 Evidencia W7 §9 — Decisión E

> **Decisión E — Observability:** *"Clonnect tiene metadata rica pero no tiene dashboards ni alerting estructurado. La metadata es `dict` sin schema. QW1 eliminó orphans; QW3 añadió alerting para security. Falta: tipado + dashboards + contrato de uso."*

### 1.3 Evidencia CC — observabilidad disciplinada

W4 + W5 documentaron que CC tiene:
- **`emit()` helper centralizado** — cualquier métrica pasa por un único punto.
- **Typed events** — cada evento es un TypeScript interface con schema.
- **StatsD/Prometheus integration** — todo evento es instrumentable.
- **Telemetry opt-in/out per-user.**

Clonnect no tiene equivalente.

### 1.4 Casos reales de daño

**Caso 1 — Scoring debug (2026-02-14):**
Manel reportó que scoring "tarda mucho en ciertos leads". No había métrica `scoring_duration_by_phase`. Hubo que añadir logging ad-hoc, redeployar, esperar 24h, analizar logs. **Tiempo diagnóstico: 3 días.** Con métrica preexistente: 10 minutos.

**Caso 2 — Compaction shadow (futuro ARC3):**
ARC3 Phase 2 dependerá de observabilidad. Si no existe cuando ARC3 arranca, el shadow mode no tendrá dónde loggear decisiones → retrasa ARC3.

**Caso 3 — Silent metadata growth:**
Sin contrato, cada PR añade 1-3 campos a metadata. En 6 meses, metadata crece 50% en tamaño, 0% en utilidad. DB storage + backup cost sube sin razón.

### 1.5 Síntesis del problema

- **Metadata es un "vertedero"** sin contrato.
- **35 orphans** siguen costando almacenamiento y confusión.
- **No hay dashboards** para pipeline metrics (solo para DB/infra).
- **Añadir un campo** no tiene checklist (reader + test + emit).
- **ARC1-ARC4 agregan campos nuevos** — sin ARC5, el ecosistema empeora.

---

## 2 · Diseño Técnico

### 2.1 Arquitectura de 3 capas

```
┌─────────────────────────────────────────────────────────────┐
│ LAYER 1 — Typed Metadata (code contract)                   │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Per-phase Pydantic models:                          │    │
│  │  - DetectionMetadata                                │    │
│  │  - ScoringMetadata                                  │    │
│  │  - GenerationMetadata                               │    │
│  │  - PostGenMetadata                                  │    │
│  │                                                     │    │
│  │ Message.metadata is a union of these                │    │
│  │ (persisted as JSONB, typed at boundary)             │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ LAYER 2 — emit_metric helper + contract                     │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ emit_metric(name, value, **labels)                  │    │
│  │  - Single source of truth for Prometheus            │    │
│  │  - Auto-labels: creator_id, lead_id (if present)    │    │
│  │  - Metric registry: declared up-front               │    │
│  │                                                     │    │
│  │ Contract: every typed metadata field must have:     │    │
│  │   (a) a reader function, OR                         │    │
│  │   (b) an emit_metric call, OR                       │    │
│  │   (c) explicit @deprecated marker                   │    │
│  │                                                     │    │
│  │ CI enforces: tests/test_metadata_contract.py        │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│ LAYER 3 — Grafana dashboards + alerts                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Dashboards:                                         │    │
│  │   1. Generation Pipeline (latency, error, tokens)   │    │
│  │   2. Scoring (batch progress, duration, errors)     │    │
│  │   3. Memory (ARC2 extraction, recall hit rate)      │    │
│  │   4. Compaction (ARC3 distill, compactor, breaker)  │    │
│  │                                                     │    │
│  │ Alerts:                                             │    │
│  │   - Latency P95 > 2.5s (warning)                    │    │
│  │   - Error rate > 2% (critical)                      │    │
│  │   - Circuit breaker trips > 0.5% (critical)         │    │
│  │   - CCEE composite drop > 3 points (warning, daily) │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Component 1 — Typed Metadata

#### 2.2.1 Pydantic models

```python
# core/metadata/models.py

from pydantic import BaseModel, Field
from typing import Literal, Optional
from uuid import UUID
from datetime import datetime

class DetectionMetadata(BaseModel):
    """Metadata emitted by core/dm/phases/detection.py."""
    detection_ts: datetime
    detection_duration_ms: int
    detected_intent: Literal["greeting", "question", "objection", "purchase", "other"]
    confidence: float = Field(..., ge=0.0, le=1.0)
    lang_detected: str
    matched_rules: list[str] = Field(default_factory=list)

    # Security (populated by QW3)
    security_flags: list[str] = Field(default_factory=list)
    security_severity: Optional[Literal["low", "medium", "high", "critical"]] = None

class ScoringMetadata(BaseModel):
    """Metadata emitted by services/lead_scoring.py."""
    scoring_ts: datetime
    scoring_duration_ms: int
    scoring_model: str
    score_before: float
    score_after: float
    score_delta: float

    # Sub-scores
    interest_score: float
    intent_score: float
    objection_score: float

    # Batch metadata
    batch_id: Optional[UUID] = None
    batch_position: Optional[int] = None

class GenerationMetadata(BaseModel):
    """Metadata emitted by services/generation.py."""
    generation_ts: datetime
    generation_duration_ms: int
    generation_model: str
    temperature: float

    # Tokens
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    # Context assembly (populated by ARC1/ARC3)
    compaction_applied: bool = False
    distill_cache_hit: bool = False
    sections_truncated: list[str] = Field(default_factory=list)
    context_budget_used_pct: float

    # Retries
    retry_count: int = 0
    circuit_breaker_tripped: bool = False

class PostGenMetadata(BaseModel):
    """Metadata emitted by services/safety_filter.py + post-processing."""
    post_gen_ts: datetime
    safety_status: Literal["OK", "BLOCK", "REGEN"]
    safety_reason: Optional[str] = None
    pii_redacted_types: list[str] = Field(default_factory=list)

    # Rule violations (ARC4 metrics)
    rule_violations: list[str] = Field(default_factory=list)  # e.g., ["emoji", "length"]
    length_regen_triggered: bool = False

class MessageMetadata(BaseModel):
    """Top-level container for all phase metadata."""
    detection: Optional[DetectionMetadata] = None
    scoring: Optional[ScoringMetadata] = None
    generation: Optional[GenerationMetadata] = None
    post_gen: Optional[PostGenMetadata] = None

    # Versioning (for migrations)
    schema_version: int = 1
```

#### 2.2.2 Boundary typing

La DB sigue guardando JSONB (no migration). El contrato se aplica al **escribir** y **leer**:

```python
# core/metadata/serdes.py

def write_metadata(message: Message, typed: MessageMetadata) -> None:
    """Write typed metadata to message.metadata (JSONB)."""
    message.metadata = typed.model_dump(mode="json", exclude_none=True)

def read_metadata(message: Message) -> MessageMetadata:
    """Read typed metadata from message.metadata (JSONB)."""
    if not message.metadata:
        return MessageMetadata()
    return MessageMetadata.model_validate(message.metadata)
```

#### 2.2.3 Partial updates (per-phase)

Las fases escriben su sub-modelo sin tocar las otras:

```python
# core/metadata/helpers.py

async def update_detection_metadata(
    session, message_id: UUID, detection: DetectionMetadata
):
    msg = await session.get(Message, message_id)
    current = read_metadata(msg)
    current.detection = detection
    write_metadata(msg, current)
    await session.commit()
```

Esto permite que **detection**, **scoring**, **generation**, **post-gen** escriban sin race conditions (cada fase toca una sola sub-sección).

#### 2.2.4 Migración de data existente

**No hacer migración masiva.** Los mensajes existentes siguen siendo `dict`. `read_metadata` maneja el caso:

```python
def read_metadata(message: Message) -> MessageMetadata:
    if not message.metadata:
        return MessageMetadata()
    try:
        return MessageMetadata.model_validate(message.metadata)
    except ValidationError:
        # Legacy message with pre-Pydantic fields — skip typing,
        # return empty. Don't crash, don't block the read.
        metrics.legacy_metadata_read.inc()
        return MessageMetadata()
```

Gradualmente, los mensajes nuevos son typed, los viejos son legacy. Tras 3 meses, legacy rate baja a ~0%.

---

### 2.3 Component 2 — emit_metric Helper

#### 2.3.1 API

```python
# core/observability/metrics.py

from prometheus_client import Counter, Histogram, Gauge
from typing import Any

# Metric registry (declared up-front, not dynamically)
_REGISTRY = {
    "generation_duration_ms": Histogram(
        "generation_duration_ms",
        "Generation duration in milliseconds",
        labelnames=["creator_id", "model", "status"],
        buckets=[50, 100, 200, 500, 1000, 2000, 5000, 10000],
    ),
    "scoring_duration_ms": Histogram(
        "scoring_duration_ms",
        "Scoring duration in milliseconds",
        labelnames=["creator_id", "phase"],
        buckets=[10, 50, 100, 500, 1000, 5000],
    ),
    "compaction_applied_total": Counter(
        "compaction_applied_total",
        "Compaction applied events",
        labelnames=["creator_id", "reason"],
    ),
    "rule_violation_total": Counter(
        "rule_violation_total",
        "Rule violation events (from ARC4)",
        labelnames=["creator_id", "rule_name"],
    ),
    # ... declared here, not inline
}


def emit_metric(name: str, value: Any = 1, **labels) -> None:
    """Emit a metric to Prometheus via the central registry.

    Usage:
        emit_metric("generation_duration_ms", 450, creator_id="iris", model="gemma-4-26b", status="ok")
    """
    metric = _REGISTRY.get(name)
    if metric is None:
        # Fail-open: log but don't crash
        logger.warning("emit_metric: unknown metric %s", name)
        return

    # Filter labels to only declared ones
    declared = metric._labelnames
    filtered = {k: v for k, v in labels.items() if k in declared}

    if isinstance(metric, Counter):
        metric.labels(**filtered).inc(value)
    elif isinstance(metric, Histogram):
        metric.labels(**filtered).observe(value)
    elif isinstance(metric, Gauge):
        metric.labels(**filtered).set(value)
    else:
        logger.error("emit_metric: unsupported type for %s", name)
```

#### 2.3.2 Auto-labels (context-aware)

Middleware en FastAPI para inyectar labels comunes:

```python
# core/observability/middleware.py

from contextvars import ContextVar

_current_creator_id: ContextVar[Optional[str]] = ContextVar("creator_id", default=None)
_current_lead_id: ContextVar[Optional[str]] = ContextVar("lead_id", default=None)

def set_context(creator_id: str, lead_id: str):
    _current_creator_id.set(creator_id)
    _current_lead_id.set(lead_id)

def get_context() -> dict:
    return {
        "creator_id": _current_creator_id.get(),
        "lead_id": _current_lead_id.get(),
    }
```

`emit_metric` puede auto-inyectar si no se pasan explícitos:

```python
def emit_metric(name: str, value: Any = 1, **labels) -> None:
    ctx = get_context()
    for k, v in ctx.items():
        if k not in labels and v is not None:
            labels[k] = v
    # ... rest
```

#### 2.3.3 Contract test

```python
# tests/test_metadata_contract.py

import ast
from pathlib import Path

ROOT = Path(__file__).parent.parent

def test_every_metadata_field_has_reader_or_metric():
    """Walk through typed metadata models; assert each field has either:
    - a function consuming it (grep "metadata.{field}" usage)
    - or an emit_metric call with field name
    - or @deprecated marker
    """
    from core.metadata.models import (
        DetectionMetadata, ScoringMetadata,
        GenerationMetadata, PostGenMetadata,
    )

    all_fields = []
    for model in [DetectionMetadata, ScoringMetadata, GenerationMetadata, PostGenMetadata]:
        for field_name in model.model_fields:
            all_fields.append((model.__name__, field_name))

    # Parse all .py files looking for usages
    all_src = ""
    for p in ROOT.glob("**/*.py"):
        if "test_" in str(p) or "__pycache__" in str(p):
            continue
        all_src += p.read_text() + "\n"

    orphans = []
    for model_name, field in all_fields:
        has_reader = f".{field}" in all_src
        has_metric = f'"{field}"' in all_src and "emit_metric" in all_src
        has_deprecated = f"# deprecated: {field}" in all_src
        if not (has_reader or has_metric or has_deprecated):
            orphans.append((model_name, field))

    assert not orphans, f"Orphan fields (no reader/metric/deprecated): {orphans}"
```

Este test **corre en CI** — bloquea PRs que añadan campos sin consumer.

---

### 2.4 Component 3 — Grafana Dashboards

#### 2.4.1 Dashboard 1 — Generation Pipeline

Paneles:
- Latency P50/P95/P99 (histogram `generation_duration_ms`)
- Error rate per creator (counter `generation_error_total` / `generation_total`)
- Tokens per turn (histogram `prompt_tokens`, `completion_tokens`)
- Retry rate (counter `generation_retry_total`)
- Circuit breaker trips (counter from ARC3)
- Rule violations (counter from ARC4)

#### 2.4.2 Dashboard 2 — Scoring

Paneles:
- Batch progress (gauge `scoring_batch_leads_processed`)
- Duration per phase (histogram `scoring_duration_ms`)
- Score delta distribution (histogram `scoring_score_delta`)
- Errors per batch (counter `scoring_error_total`)
- Scoring backlog depth (gauge `scoring_queue_depth`)

#### 2.4.3 Dashboard 3 — Memory (ARC2)

Paneles:
- Memory extraction rate (counter `memory_extracted_total` per type)
- Recall hit rate (counter `memory_recall_hit_total` / `memory_recall_total`)
- Memory table size (gauge `lead_memories_count_total`)
- Superseded chain depth distribution (histogram `memory_superseded_chain_depth`)
- Extraction latency (histogram `memory_extraction_duration_ms`)

#### 2.4.4 Dashboard 4 — Compaction (ARC3)

Paneles:
- Compaction applied rate (counter `compaction_applied_total` / `generation_total`)
- Distill cache hit rate (counter `distill_cache_hit_total` / `distill_cache_request_total`)
- Sections truncated (counter `section_truncated_total` per section)
- Circuit breaker state (gauge `circuit_breaker_tripped_total`)
- Doc D truncation rate (legacy vs new)

#### 2.4.5 Dashboard 5 — CCEE Quality (daily cron)

Paneles:
- CCEE composite per creator × model (gauge, daily)
- Top 3 metrics regresión (heatmap, K1-K10 + S1-S5)
- Scenario failures (table)

---

### 2.5 Component 4 — Alerting

Reutilizar la infraestructura de QW3 (`alert_security_event`). Nuevas alertas:

```yaml
# alerts/observability_rules.yml

groups:
  - name: generation_pipeline
    rules:
      - alert: GenerationLatencyHigh
        expr: histogram_quantile(0.95, rate(generation_duration_ms_bucket[5m])) > 2500
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Generation P95 > 2.5s sostenido"

      - alert: GenerationErrorRate
        expr: rate(generation_error_total[5m]) / rate(generation_total[5m]) > 0.02
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Error rate > 2%"

      - alert: CircuitBreakerTripsHigh
        expr: rate(circuit_breaker_tripped_total[10m]) / rate(generation_total[10m]) > 0.005
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "Circuit breaker trips > 0.5%"

  - name: ccee_quality
    rules:
      - alert: CCEERegresssion
        expr: ccee_composite_score - ccee_composite_score offset 7d < -3
        labels:
          severity: warning
        annotations:
          summary: "CCEE composite dropped > 3 points week-over-week"
```

Integrar con QW3 alerting channel (Slack + email Manel).

---

## 3 · Plan de Rollout (5 fases)

### Phase 1 — Typed Metadata Models (Semana 1)

**Objetivo:** Introducir Pydantic models sin cambiar comportamiento.

**Tasks:**
1. Crear `core/metadata/models.py` con los 5 Pydantic models.
2. `core/metadata/serdes.py` con `read_metadata` / `write_metadata`.
3. `core/metadata/helpers.py` con partial updates.
4. Tests unitarios: round-trip, validation, missing fields, legacy compat.
5. Deploy (models existen pero aún nada los usa).

**No-go:** Tests fallan.

**Output:** Código disponible, no integrado aún.

---

### Phase 2 — Integrate per-phase (Semana 1-2)

**Objetivo:** Reemplazar escrituras dict directas por sub-models.

**Tasks:**
1. En `core/dm/phases/detection.py`: reemplazar `metadata["x"] = ...` por `DetectionMetadata(...)` + `update_detection_metadata(...)`.
2. Mismo para scoring, generation, post-gen.
3. Tests de regresión: mensajes nuevos tienen schema correcto.
4. Deploy gradual con feature flag `USE_TYPED_METADATA`:
   - Semana 2 día 1: 10% tráfico.
   - Día 3: 50%.
   - Día 5: 100%.
5. Monitor `legacy_metadata_read` counter — debe subir a 0% en mensajes nuevos.

**No-go:** ValidationErrors en production.

**Output:** Escrituras typeadas. Lecturas pueden ser dict legacy o typed.

---

### Phase 3 — emit_metric Helper (Semana 2)

**Objetivo:** Canal único para Prometheus.

**Tasks:**
1. Crear `core/observability/metrics.py` con `emit_metric` y registry.
2. `core/observability/middleware.py` con context vars + middleware FastAPI.
3. Tests:
   - Registry declarations.
   - Context injection.
   - Unknown metric name (fail-open).
4. Reemplazar `prometheus_client.Counter(...)` directos scattered en código (~20 lugares) por `emit_metric(...)`.
5. Deploy.

**Validación:** Grafana explorer muestra métricas existentes con nuevas labels (creator_id injected).

---

### Phase 4 — Grafana Dashboards (Semana 2-3)

**Objetivo:** 5 dashboards operacionales.

**Tasks:**
1. Crear JSON de cada dashboard en `docs/observability/dashboards/`.
2. Deploy a Grafana via API/import.
3. Configurar alertas (observability_rules.yml) en Prometheus AlertManager.
4. Integrar alertas con canal QW3 (Slack).
5. Test end-to-end: forzar condición alert → verificar recepción.

**Gate:** Manel valida cada dashboard (utilidad, claridad).

---

### Phase 5 — Contract Enforcement + Orphan Cleanup (Semana 3)

**Objetivo:** CI check + eliminar 35 orphans restantes.

**Tasks:**
1. `tests/test_metadata_contract.py` implementación completa.
2. Correr en local: lista de orphans detectados.
3. Por cada orphan (35):
   - Decidir: add reader / add emit_metric / mark deprecated / delete field.
4. Añadir test a CI pipeline (bloquea merges).
5. Commit cleanup en fases (5 orphans/día = 1 semana).
6. Retrospective.

**No-go:** Si > 5 orphans son difíciles de resolver (e.g., requieren rediseño), escalar a nuevo sprint.

---

## 4 · Métricas de Éxito

### 4.1 Métricas Primarias

| Métrica | Baseline | Target | Método |
|---|---|---|---|
| Orphan fields | 35 | 0 | `test_metadata_contract` passing |
| Dashboards activos | 0 (custom) | 5 | Grafana |
| Metrics in `emit_metric` registry | ~8 ad-hoc | ≥ 30 | Registry count |
| CI check blocks orphans | No | Yes | CI config |
| Typed metadata coverage (new msgs) | 0% | ≥ 95% | `legacy_metadata_read` metric |

### 4.2 Métricas Operacionales

| Métrica | Target |
|---|---|
| Alert acknowledgment time | < 10 min |
| Dashboard load time | < 2s |
| Mean time to diagnose (MTTD) prod issue | < 30 min |

### 4.3 Métricas de adopción

- Nuevos ARCs (ARC1-ARC4) usan `emit_metric` al 100%.
- Zero PRs mergeados con metadata dict directo post-Phase 5.

---

## 5 · Riesgos y Mitigaciones

### R1 — Pydantic validation rompe writes en prod — 🔴 HIGH

**Descripción:** Cambiar de dict a Pydantic puede fallar en edge cases (campo con tipo inesperado, None donde no se esperaba).

**Mitigación:**
- Feature flag `USE_TYPED_METADATA` con rollout gradual.
- `read_metadata` con try/except + fallback a empty MessageMetadata.
- Tests extensive de edge cases (None, dict vacío, legacy).
- Monitor `typed_metadata_validation_error` counter — si sube, rollback inmediato.

### R2 — Performance hit de Pydantic serialization — 🟡 MEDIUM

**Descripción:** Pydantic v2 es rápido (~10μs por validation), pero sumado es overhead notable.

**Mitigación:**
- Benchmark pre/post con 1000 mensajes.
- Si overhead > 50ms per turn, considerar `TypedDict` + manual validation en hot path, Pydantic solo en slow path.
- Profiling antes de optimizar.

### R3 — Orphan cleanup rompe features "dormidas" — 🟡 MEDIUM

**Descripción:** Un campo orphan puede ser para un dashboard futuro que Manel tenía en mente pero no documentó.

**Mitigación:**
- Review cada orphan con Manel antes de borrar.
- Opciones por orphan: delete / mark @deprecated 3 months / add consumer.
- No mass delete — por fases.

### R4 — Grafana dashboard drift — 🟢 LOW

**Descripción:** Dashboards se divergen del código con el tiempo (métrica renombrada, panel roto).

**Mitigación:**
- Dashboards en repo (JSON versionado).
- PR template checkbox: "Updated Grafana dashboards?"
- Runbook quarterly review.

### R5 — emit_metric failures crashean endpoints — 🟡 MEDIUM

**Descripción:** Si Prometheus registry falla, no queremos tumbar generación.

**Mitigación:**
- `emit_metric` es **fail-open**: log warning + return, nunca raise.
- Tests que simulen Prometheus down.
- Circuit breaker global para Prometheus (al estilo ARC3).

### R6 — Labels explosion en Prometheus — 🟡 MEDIUM

**Descripción:** `creator_id` y `lead_id` como labels puede explotar cardinality (millones de leads).

**Mitigación:**
- `lead_id` NO se usa como label en métricas agregadas (solo para traces).
- `creator_id` sí (bajo cardinality: ~3-20 creators).
- Review de cada nueva métrica incluye cardinality estimate.

### R7 — ARC1-ARC4 emiten métricas inconsistentes — 🟢 LOW

**Descripción:** Si ARC3 usa `compaction_applied` pero ARC5 espera `compaction_applied_total`, no match.

**Mitigación:**
- ARC5 publica guía de naming antes del arranque de ARC1-ARC4 (o ASAP).
- Plantilla: `{subsystem}_{metric}_{type}` (e.g., `generation_duration_ms`, `scoring_batch_total`).
- Code review incluye check de naming.

---

## 6 · Dependencias

### 6.1 Dependencias técnicas

| Dependencia | Owner | Status | Blocking |
|---|---|---|---|
| QW1 (orphans QW1 cleanup) | Sprint 4 QW | ✅ done | No (ARC5 completa la limpieza) |
| QW3 (alerting infra) | Sprint 4 QW | ✅ done | No |
| Prometheus instance | Infra | ✅ existe | No |
| Grafana instance | Infra | ✅ existe | No |
| Pydantic v2 | Dep | ✅ instalado | No |

### 6.2 Dependencias con otros ARCs

- **ARC1, ARC2, ARC3, ARC4:** Todos emiten métricas nuevas que ARC5 consolida en dashboards.
- **Preferible:** ARC5 Phase 1-3 (modelos + helper) **antes** de ARC1-ARC4 — les da el canal de emit_metric.
- **Pragmático:** ARC5 puede ir en paralelo con los otros ARCs. Los otros ARCs usan `emit_metric` desde el principio (con registry declarado).

### 6.3 Orden recomendado

```
Semana 1-2: ARC5 Phase 1-3 (modelos + helper) en paralelo con ARC1 Phase 1.
Semana 3+: ARC5 Phase 4-5 (dashboards + cleanup) en paralelo con ARC2-ARC4.
```

ARC1-ARC4 consumen `emit_metric` desde el inicio → ARC5 dashboardea progresivamente.

---

## 7 · Cronograma (3 semanas realistas)

### Semana 1

| Día | Work | Owner | Output |
|---|---|---|---|
| Lun | Pydantic models + serdes | A5.1 | models.py + serdes.py + tests |
| Mar | Partial update helpers | A5.1 | helpers.py + tests |
| Mié | Feature flag + detection integration | A5.2 | Detection typed |
| Jue | Scoring + generation integration | A5.2 | Those phases typed |
| Vie | Post-gen integration + rollout 10% | A5.2 | Staging live |

### Semana 2

| Día | Work | Owner | Output |
|---|---|---|---|
| Lun | Rollout 50% typed metadata | A5.2 | Metrics OK |
| Mar | `emit_metric` helper + registry | A5.3 | metrics.py |
| Mié | Context middleware + auto-labels | A5.3 | Middleware live |
| Jue | Reemplazar 20 Counter directos | A5.3 | Migration done |
| Vie | Rollout 100% typed metadata | A5.2 | Full prod |

### Semana 3

| Día | Work | Owner | Output |
|---|---|---|---|
| Lun-Mar | Dashboard 1-2 (gen, scoring) | A5.4 | JSON + deployed |
| Mié | Dashboard 3-4 (memory, compaction) | A5.4 | JSON + deployed |
| Jue | Dashboard 5 (CCEE) + alerts | A5.4 | Alerting live |
| Vie | Contract test + orphan cleanup start | A5.5 | 10/35 orphans resolved |

**Buffer semana 4:** Para completar orphan cleanup si 35 son más de lo estimado.

---

## 8 · Worker Prompts (listos para copiar)

### Worker A5.1 — Typed Metadata Models

```xml
<instructions>
<role>
Eres un ingeniero backend Python senior, especialista en Pydantic v2 y schemas.
</role>

<context>
Sprint 5 ARC5 Phase 1. Crear Pydantic models para message.metadata.
Leer: docs/sprint5_planning/ARC5_observability.md §2.2 completo.
Leer: docs/audit_phase2/W7_FULL_CROSS_SYSTEM_60.md §3 (inventario 114 campos).
Leer: core/dm/phases/detection.py + services/lead_scoring.py + services/generation.py
      para ver qué campos se escriben actualmente.
</context>

<objetivo>
Producir Pydantic models que cubran los 49 campos con reader + los 35 orphans
restantes (marcados como `@deprecated` en Optional si no hay reader aún).
</objetivo>

<tareas>
1. `core/metadata/models.py`:
   - DetectionMetadata, ScoringMetadata, GenerationMetadata, PostGenMetadata.
   - MessageMetadata container.
   - Campos exactos según inventario W7 §3 (preservar naming backward-compat).
   - Campos deprecated marcados con Field(default=None, description="deprecated: ...").
2. `core/metadata/serdes.py`:
   - read_metadata, write_metadata.
   - Fallback para legacy dicts.
3. `core/metadata/helpers.py`:
   - update_detection_metadata, update_scoring_metadata, etc.
   - Cada uno lee el doc actual, actualiza sub-model, escribe.
4. Tests comprehensivos:
   - Round-trip (dict → Pydantic → dict).
   - Validation errors con mensajes claros.
   - Legacy dict compat (ValidationError capturado → empty model).
   - Partial updates (no sobrescribir otras fases).
5. Syntax check + run tests.
</tareas>

<reglas>
- Pydantic v2 (no v1).
- NO cambiar el schema JSONB en DB (sigue siendo dict).
- Tipos strict — usar Literal, NO str libre.
- Campos obligatorios solo si SIEMPRE están presentes. Else Optional.
- Tests coverage > 90%.
</reglas>

<deliverables>
- core/metadata/{models,serdes,helpers}.py
- tests/test_metadata_models.py, test_metadata_serdes.py
- Documentación inline: qué fase escribe cada campo
</deliverables>
</instructions>
```

---

### Worker A5.2 — Per-Phase Integration + Rollout

```xml
<instructions>
<role>
Eres un ingeniero backend de Clonnect, experto en refactor controlado.
</role>

<context>
Sprint 5 ARC5 Phase 2. Integrar typed metadata en las 4 fases existentes
(detection, scoring, generation, post-gen) con feature flag + rollout gradual.
Leer: docs/sprint5_planning/ARC5_observability.md §3 Phase 2.
Leer: core/metadata/* (output de A5.1).
</context>

<objetivo>
Reemplazar escrituras dict directas por Pydantic typed models, con rollout
controlado por feature flag.
</objetivo>

<tareas>
1. Feature flag `USE_TYPED_METADATA` en creator_runtime_config.
2. Por fase:
   - core/dm/phases/detection.py: reemplazar `msg.metadata["detection_ts"] = ...`
     por `update_detection_metadata(session, msg.id, DetectionMetadata(...))`.
   - services/lead_scoring.py: idem con ScoringMetadata.
   - services/generation.py: idem con GenerationMetadata.
   - services/safety_filter.py (post-ARC4): idem con PostGenMetadata.
3. Wrap con feature flag:
   ```python
   if should_use_typed_metadata(creator_id):
       await update_detection_metadata(...)
   else:
       msg.metadata["detection_ts"] = ...  # legacy path
   ```
4. Rollout schedule (por fase):
   - Detection día 1: 10% → día 3: 50% → día 5: 100%.
   - Scoring día 2: 10% → día 4: 50% → día 6: 100%.
   - Generation día 3: 10% → día 5: 50% → día 7: 100%.
   - Post-gen día 4: 10% → día 6: 50% → día 8: 100%.
5. Monitoring:
   - `typed_metadata_write_total` counter.
   - `typed_metadata_validation_error_total` counter (debe ser ~0).
   - Si validation errors > 0.1%: ROLLBACK esa fase, investigar.
6. Tras 100% stable 7 días: eliminar legacy path.
</tareas>

<reglas>
- NO modificar DB schema.
- NO eliminar legacy path hasta 7 días estable 100%.
- Syntax check obligatorio.
- Monitoring requerido antes de cada step de rollout.
- Si algún test de regresión falla, STOP rollout.
</reglas>

<deliverables>
- 4 fases con typed metadata writes.
- Feature flag + sticky hashing.
- Rollout logs día por día.
- Final report: docs/sprint5_planning/ARC5_phase2_rollout.md.
</deliverables>
</instructions>
```

---

### Worker A5.3 — emit_metric Helper + Context Middleware

```xml
<instructions>
<role>
Eres un ingeniero Python senior, experto en Prometheus y observability.
</role>

<context>
Sprint 5 ARC5 Phase 3. Crear canal único `emit_metric` y consolidar ~20
instancias de `prometheus_client.Counter(...)` scattered en código.
Leer: docs/sprint5_planning/ARC5_observability.md §2.3.
Grep: `grep -rn "prometheus_client" --include="*.py"` para encontrar usos actuales.
</context>

<objetivo>
Implementar `emit_metric` con registry declarado, context middleware para
auto-labels, y migrar todos los usos directos existentes.
</objetivo>

<tareas>
1. `core/observability/metrics.py`:
   - _REGISTRY dict con declaraciones up-front (~30 metrics conocidas).
   - emit_metric(name, value, **labels) fail-open.
   - Registry helpers para consulta.
2. `core/observability/middleware.py`:
   - ContextVar para creator_id, lead_id, turn_id.
   - FastAPI middleware que extrae estos del request/path y los setea.
   - get_context() helper.
3. Migrar ~20 usos directos:
   - `grep -rn "Counter(" --include="*.py"` identifica cada uno.
   - Añadir al _REGISTRY.
   - Reemplazar `counter.inc()` por `emit_metric("name", ...)`.
4. Tests:
   - Registry lookup.
   - Unknown metric → warning log, no crash.
   - Context injection via middleware.
   - Manual override de context vars.
5. Documentar en `docs/observability/emit_metric_guide.md`:
   - Cómo añadir una nueva métrica.
   - Naming convention.
   - Cardinality guidelines.
</tareas>

<reglas>
- emit_metric es FAIL-OPEN (nunca raise).
- Registry declarado up-front (no dynamic).
- Naming: `{subsystem}_{metric}_{type}` (e.g., `generation_duration_ms`).
- creator_id como label OK, lead_id NO (cardinality explosion).
- Tests comprensivos antes de deploy.
</reglas>

<deliverables>
- core/observability/metrics.py + tests
- core/observability/middleware.py + tests
- 20 usos directos migrados
- Guide docs/observability/emit_metric_guide.md
</deliverables>
</instructions>
```

---

### Worker A5.4 — Grafana Dashboards + Alerts

```xml
<instructions>
<role>
Eres un SRE de Clonnect, especialista en Grafana/Prometheus.
</role>

<context>
Sprint 5 ARC5 Phase 4. Crear 5 dashboards operacionales y alertas.
Leer: docs/sprint5_planning/ARC5_observability.md §2.4 y §2.5.
Leer: docs/observability/emit_metric_guide.md (output A5.3) para lista de métricas disponibles.
</context>

<objetivo>
5 dashboards + alertas Prometheus AlertManager integradas con QW3 alert channel.
</objetivo>

<tareas>
1. Para cada dashboard (gen, scoring, memory, compaction, ccee):
   - Crear JSON de Grafana en `docs/observability/dashboards/`.
   - Paneles según §2.4 (latency, error rate, rates, etc).
   - Variables de dashboard: creator_id (dropdown), time range.
   - Deploy vía Grafana API o import manual.
2. Alert rules: `alerts/observability_rules.yml`:
   - GenerationLatencyHigh (P95 > 2.5s).
   - GenerationErrorRate (> 2%).
   - CircuitBreakerTripsHigh (> 0.5%).
   - CCEERegression (composite drop > 3 points week-over-week).
   - ScoringBacklog (> 1000 leads pending).
   - TypedMetadataValidationErrors (> 0.1%).
3. Integrar AlertManager con QW3 channel (Slack webhook + email).
4. Test end-to-end:
   - Forzar latency spike → alert dispara → Slack recibe.
   - Forzar error rate → crítico → Manel email.
5. Runbook `docs/observability/alerts_playbook.md`:
   - Cada alerta con: severity, trigger, first-response action.
</tareas>

<reglas>
- Dashboards JSON versionados en repo.
- Alertas con severity explícita (warning/critical).
- NO silenciar alertas — si ruidosa, ajustar threshold o suprimir con rationale.
- Integrar con canal QW3 existente (no crear nuevo).
</reglas>

<deliverables>
- 5 dashboard JSONs en docs/observability/dashboards/
- alerts/observability_rules.yml
- docs/observability/alerts_playbook.md
- E2E test evidence (screenshots Slack notification)
</deliverables>
</instructions>
```

---

### Worker A5.5 — Contract Test + Orphan Cleanup

```xml
<instructions>
<role>
Eres un ingeniero senior de Clonnect con mindset de code quality.
</role>

<context>
Sprint 5 ARC5 Phase 5. Implementar test de contrato + eliminar 35 orphans.
Leer: docs/sprint5_planning/ARC5_observability.md §2.3.3 y §3 Phase 5.
Leer: docs/audit_phase2/W7_FULL_CROSS_SYSTEM_60.md §3 para lista de 35 orphans.
</context>

<objetivo>
1. Implementar `test_metadata_contract.py` que bloquee orphans en CI.
2. Eliminar los 35 orphans restantes (delete / add consumer / mark deprecated).
</objetivo>

<tareas>
1. Implementar tests/test_metadata_contract.py:
   - Walk Pydantic models → list all fields.
   - AST parse todo el repo → find reader/metric uses.
   - Fail si orphan found sin @deprecated.
2. Correr en local → obtener lista inicial de orphans.
3. Por cada orphan (35):
   - Hablar con Manel 1x para decidir acción.
   - Opción A: Añadir reader real (dashboard, log consumer, etc).
   - Opción B: Añadir emit_metric.
   - Opción C: Marcar @deprecated si aún sirve a legacy y eliminar en 3 meses.
   - Opción D: Delete field (más común).
4. Commits atómicos: 1 orphan por commit (facilita revert).
5. CI integration:
   - Añadir test a pipeline pytest.
   - PR que añada orphan → test rojo.
6. Documentar patrón en `docs/observability/adding_metadata_field.md`.
</tareas>

<reglas>
- NO bulk delete. Un orphan a la vez con justification.
- Si un orphan es ambiguo, Manel decide.
- @deprecated requiere fecha de eliminación explícita.
- CI check no bloquea hasta que los 35 estén resueltos.
</reglas>

<deliverables>
- tests/test_metadata_contract.py passing.
- 35 orphans resueltos (git log evidence).
- docs/observability/adding_metadata_field.md.
- CI check integrado en pipeline.
- Final count: 0 orphans, 100% declared fields con reader/metric.
</deliverables>
</instructions>
```

---

## 9 · Open Questions

### Q1 — ¿Pydantic v2 penaliza latencia crítica?

Estimación: ~10μs per validation × 4 phases = 40μs per turn. Sobre 2s de generation, es ruido. Pero habría que medir.

**Acción:** Benchmark en Phase 1. Si > 5% del budget, reconsiderar.

---

### Q2 — ¿Migrar data histórica?

**Actual:** Datos legacy siguen como dict. Reads son flexibles.

**Alternativa:** Script migration que procese todos los `messages.metadata` y los convierta a typed schema.

**Trade-off:** +2 semanas de trabajo vs. cleaner state. Suele no valer la pena — histórico pierde valor rápido.

**Recomendación tentativa:** No migrar. Legacy rate baja naturalmente < 5% en 3 meses.

---

### Q3 — ¿Dashboards per-creator o globales?

**Opción A:** Dashboard único con variable `creator_id` dropdown.
**Opción B:** Un dashboard per creator (manual management).

**Recomendación:** Opción A (más DRY). Si Manel quiere vistas personalizadas, crear con "Save as".

---

### Q4 — ¿Qué hacer con métricas de uso bajo?

Algunas métricas tienen 1-2 events/día (e.g., circuit_breaker_trips si todo va bien).

**Opciones:**
- Mantener (son útiles cuando el event pasa).
- Aggregar en un "health panel" única.

**Recomendación:** Mantener. El costo Prometheus es despreciable.

---

### Q5 — ¿Cómo versionar MessageMetadata schema?

Si añadimos campos en 6 meses, cómo manejamos compat?

**Respuesta:** Campo `schema_version: int = 1` en MessageMetadata. Bump on breaking change. read_metadata valida version y aplica migrators si necesario.

---

## 10 · Appendix

### 10.1 Glosario

- **Orphan field:** Campo en metadata escrito pero nunca leído, agregado ni visualizado.
- **Typed metadata:** Metadata validada via Pydantic al escribir y leer.
- **emit_metric:** Canal único de publicación de métricas a Prometheus.
- **Contract test:** Test automatizado que verifica que cada campo declarado tiene consumer o metric.
- **Label cardinality:** Número de valores distintos de una label — alto = Prometheus memory explosion.

### 10.2 Referencias

- W7 §3 (metadata flow 114 campos).
- W7 §9 Decisión E (observability gap).
- QW1 (orphans cleanup — 30 resolved).
- QW3 (security alerting — reused infra).

### 10.3 Post-ARC5 acceptance checklist

- [ ] 5 Pydantic models live + serdes + helpers.
- [ ] 4 fases con typed metadata writes al 100%.
- [ ] `emit_metric` helper con ≥ 30 metrics registered.
- [ ] Context middleware auto-injecting creator_id.
- [ ] 5 Grafana dashboards deployed.
- [ ] 6+ Prometheus alerts activas con integración Slack/email.
- [ ] test_metadata_contract passing en CI.
- [ ] 35 orphans resueltos (0 remaining).
- [ ] Runbooks: `emit_metric_guide.md`, `alerts_playbook.md`, `adding_metadata_field.md`.
- [ ] Retrospective `docs/sprint5_planning/ARC5_retrospective.md`.
