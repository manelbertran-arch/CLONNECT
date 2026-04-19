# ARC5 Phase 3 — emit_metric Helper + Context Middleware

**Worker:** ARC5 Phase 3  
**Branch:** feature/arc5-phase3-emit-metric  
**Design ref:** docs/sprint5_planning/ARC5_observability.md §2.3 + §3

---

## Summary

Phase 3 creates a single Prometheus channel for all Clonnect metrics.

**Before:** ~24 prometheus_client objects scattered across `core/metrics.py` (20), `core/dm/budget/metrics.py` (4). Each file declares its own `Counter`/`Histogram`/`Gauge` inline, with no shared label conventions or registry governance.

**After:** `core/observability/metrics.py` holds a declarative `_REGISTRY` of all metrics. Any code calls `emit_metric("name", value, **labels)` instead of importing prometheus objects directly. A FastAPI middleware auto-injects `creator_id`/`lead_id` from the request context into every `emit_metric` call.

**Why unify:**
- Single place to add/remove/rename metrics (no grep hunts)
- Consistent label naming across all metrics (creator_id always lowercase, never `creator`, `cid`, etc.)
- Fail-open: emit_metric never raises — unknown metric name → warning log, prometheus failure → error log, always continues
- Middleware auto-injection eliminates boilerplate in hot paths

---

## Metric Registry

| Name | Type | Labels | Buckets |
|------|------|--------|---------|
| `generation_duration_ms` | Histogram | creator_id, model, status | 50–10000ms |
| `scoring_duration_ms` | Histogram | creator_id, phase | 10–5000ms |
| `detection_duration_ms` | Histogram | creator_id, intent | 5–500ms |
| `compaction_applied_total` | Counter | creator_id, reason | — |
| `memory_extraction_total` | Counter | creator_id, memory_type | — |
| `lead_memories_read_total` | Counter | creator_id, source | — |
| `lead_memories_read_duration_ms` | Histogram | creator_id | 1–500ms |
| `dual_write_success_total` | Counter | source | — |
| `dual_write_failure_total` | Counter | source, error_type | — |
| `llm_api_call_total` | Counter | provider, model, status | — |
| `llm_api_duration_ms` | Histogram | provider, model | 100–30000ms |
| `cache_hit_total` | Counter | cache_name | — |
| `cache_miss_total` | Counter | cache_name | — |
| `webhook_received_total` | Counter | platform | — |
| `webhook_processed_total` | Counter | platform, status | — |
| `budget_orchestrator_duration_ms` | Histogram | creator_id | 1–100ms |
| `budget_section_truncation_total` | Counter | section_name | — |
| `dm_budget_utilization` | Histogram | creator_id | 0.1–1.1 |
| `dm_budget_sections_selected` | Gauge | creator_id | — |
| `dm_budget_sections_dropped_total` | Counter | creator_id, section_name | — |
| `dm_budget_sections_compressed_total` | Counter | creator_id, section_name | — |
| `rule_violation_total` | Counter | creator_id, rule_name | — |
| `active_conversations_gauge` | Gauge | creator_id | — |

**Total: 23 metrics declared**

---

## Migration Log

### Migrated in this worker

| File | Before | After |
|------|--------|-------|
| `core/dm/budget/metrics.py` | 4 direct prometheus_client declarations + inline calls | `emit_metric()` calls; declarations moved to `_REGISTRY` |

### Pending migration (gradual — legacy path still works)

| File | Metrics count | Notes |
|------|--------------|-------|
| `core/metrics.py` | 20 (7 Counter, 3 Histogram, 5 Gauge + 5 ingestion) | `clonnect_*` prefix; used by MetricsMiddleware + helper functions. Safe to migrate in Phase 4 without breaking `/metrics` endpoint. |

The `core/metrics.py` metrics export via `/metrics` endpoint via `MetricsMiddleware`. They continue to work untouched. Migration to `emit_metric` is planned for Phase 4 alongside Grafana dashboard wiring.

---

## Usage Examples

### Basic emit

```python
from core.observability.metrics import emit_metric

# Counter
emit_metric("dual_write_success_total", source="dual_write_memory_extraction")

# Histogram (ms value)
emit_metric("generation_duration_ms", 450, creator_id="iris", model="gemma-4-31b", status="ok")

# Gauge
emit_metric("active_conversations_gauge", 5, creator_id="iris")
```

### With context auto-injection

```python
from core.observability.middleware import set_context
from core.observability.metrics import emit_metric

# Set context at start of DM turn (or use middleware — it's automatic for HTTP requests)
set_context(creator_id="iris_bertran", lead_id="1234567890")

# creator_id is injected automatically — no need to pass it
emit_metric("rule_violation_total", rule_name="no_price_leak")
emit_metric("cache_hit_total", cache_name="rag")
```

### Fail-open demo

```python
# All of these are safe — never raise
emit_metric("unknown_metric_name")              # → warning log, no crash
emit_metric("generation_duration_ms", "bad")   # → error log, no crash
emit_metric("cache_hit_total", bad_label="x")  # → label filtered out, still emits
```

### Adding a new metric

1. Add entry to `_METRIC_SPECS` in `core/observability/metrics.py`:

```python
("my_new_counter", Counter if _PROMETHEUS_AVAILABLE else None,
 "Description of what this counts",
 ["creator_id", "category"], {}),
```

2. Call it anywhere:

```python
emit_metric("my_new_counter", creator_id="iris", category="sales")
```

3. Add a test in `tests/observability/test_metrics.py` verifying it appears in `get_declared_metric_names()`.

---

## Middleware: How creator_id / lead_id are injected

`CreatorContextMiddleware` wraps every HTTP request:

1. Reads `X-Creator-ID` header → sets `creator_id` in ContextVar
2. Falls back to URL path extraction: `/dm/{creator_id}/...`, `/creators/{creator_id}/...`
3. Reads `X-Lead-ID` header → sets `lead_id` in ContextVar
4. Generates `request_id` (UUID4) if `X-Request-ID` not present
5. Calls `set_context(creator_id, lead_id, request_id)` before route handler
6. Calls `clear_context()` in `finally` — no leakage between requests

`emit_metric` reads the context and injects declared labels automatically. Labels already passed explicitly take precedence over context values.

---

## Next Steps: Phase 4 Grafana Dashboards

Phase 4 (planned next sprint) will:
1. Create 5 Grafana dashboard JSONs in `docs/observability/dashboards/`
2. Wire `generation_duration_ms` P50/P95/P99 per creator
3. Wire `dual_write_*` counters for ARC2 monitoring
4. Wire `dm_budget_utilization` histogram for ARC1 monitoring
5. Requires: Railway → Grafana Cloud push gateway configured (Prometheus remote write)

Grafana explorer validation:
```bash
# After Railway deploy, verify metrics appear:
curl -s http://localhost:8000/metrics | grep generation_duration_ms
curl -s http://localhost:8000/metrics | grep dm_budget_utilization
```
