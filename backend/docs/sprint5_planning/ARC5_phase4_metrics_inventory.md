# ARC5 Phase 4 — Metrics Inventory

**Date:** 2026-04-19  
**Branch:** feature/arc5-phase4-grafana  
**Source of truth:** `core/observability/metrics.py` — `_METRIC_SPECS`

All metrics below are registered and emitted via `emit_metric()`.  
Dashboard queries only reference metrics in this inventory.

---

## Available Metrics (registered in _METRIC_SPECS)

### DM Generation

| Metric | Type | Labels | Dashboard |
|--------|------|--------|-----------|
| `generation_duration_ms` | Histogram | creator_id, model, status | Pipeline Overview |
| `scoring_duration_ms` | Histogram | creator_id, phase | Pipeline Overview |
| `detection_duration_ms` | Histogram | creator_id, intent | Pipeline Overview |

### ARC1 Budget Orchestrator

| Metric | Type | Labels | Dashboard |
|--------|------|--------|-----------|
| `budget_orchestrator_duration_ms` | Histogram | creator_id | ARC1 Budget |
| `budget_section_truncation_total` | Counter | section_name | ARC1 Budget |
| `dm_budget_utilization` | Histogram | creator_id | ARC1 Budget |
| `dm_budget_sections_selected` | Gauge | creator_id | ARC1 Budget |
| `dm_budget_sections_dropped_total` | Counter | creator_id, section_name | ARC1 Budget |
| `dm_budget_sections_compressed_total` | Counter | creator_id, section_name | ARC1 Budget |

### ARC2 Lead Memory

| Metric | Type | Labels | Dashboard |
|--------|------|--------|-----------|
| `memory_extraction_total` | Counter | creator_id, memory_type | ARC2 Memory |
| `lead_memories_read_total` | Counter | creator_id, source | ARC2 Memory |
| `lead_memories_read_duration_ms` | Histogram | creator_id | ARC2 Memory |
| `dual_write_success_total` | Counter | source | ARC2 Memory |
| `dual_write_failure_total` | Counter | source, error_type | ARC2 Memory |

### ARC3 Compactor / Distill

| Metric | Type | Labels | Dashboard |
|--------|------|--------|-----------|
| `compaction_applied_total` | Counter | creator_id, reason | ARC3 Compactor |
| `cache_hit_total` | Counter | cache_name | ARC3 Compactor |
| `cache_miss_total` | Counter | cache_name | ARC3 Compactor |

Note: `cache_name="distill"` and `cache_name="rag"` are the relevant values.

### LLM API

| Metric | Type | Labels | Dashboard |
|--------|------|--------|-----------|
| `llm_api_call_total` | Counter | provider, model, status | Pipeline Overview, Business |
| `llm_api_duration_ms` | Histogram | provider, model | Pipeline Overview |

### Webhooks

| Metric | Type | Labels | Dashboard |
|--------|------|--------|-----------|
| `webhook_received_total` | Counter | platform | Pipeline Overview |
| `webhook_processed_total` | Counter | platform, status | Pipeline Overview, Business |

### ARC4 Rules / Security

| Metric | Type | Labels | Dashboard |
|--------|------|--------|-----------|
| `rule_violation_total` | Counter | creator_id, rule_name | Pipeline Overview, Business |

### Active State

| Metric | Type | Labels | Dashboard |
|--------|------|--------|-----------|
| `active_conversations_gauge` | Gauge | creator_id | Pipeline Overview, Business |

---

## TODO — Metrics missing (not yet in registry)

These metrics are referenced in `ops/grafana/alerts.yaml` as commented-out rules.  
Add them by: (1) register in `_METRIC_SPECS`, (2) call `emit_metric()` at the right code point.

| Metric | Where to emit | Required by |
|--------|---------------|-------------|
| `circuit_breaker_tripped_total` | Circuit breaker trip path (ARC5 Phase 4, not started) | Alert: CircuitBreakerTrips |
| `llm_429_total` | Provider layer on HTTP 429 response | Alert: OpenRouterRateLimit |
| `dm_errors_total` | `core/dm/agent.py` top-level exception catch | Alert: HighErrorRate (semantic) |
| `distill_applied_total` | `services/creator_style_loader.py` when distill is applied | ARC3 Compactor dashboard panel |
| `whitelist_overflow_total` | `core/generation/compactor.py` whitelist overflow path | ARC3 Compactor dashboard panel |
| `compactor_shadow_decision_total` | `core/generation/compactor.py` shadow mode decision | ARC3 Compactor dashboard panel |
| `llm_cost_usd_total` | Provider layer, requires token count × price table | Business dashboard |

---

## Dashboard ↔ Metric Coverage

| Dashboard | Metrics covered | TODO panels |
|-----------|----------------|-------------|
| clonnect_pipeline_overview.json | 9 metrics | 0 |
| clonnect_arc1_budget.json | 6 metrics | 0 |
| clonnect_arc2_memory.json | 5 metrics | 0 |
| clonnect_arc3_compactor.json | 3 metrics | 4 (noted in text panel) |
| clonnect_business.json | 5 metrics | 3 (noted in text panel) |

**Total active alerts:** 7 (5 critical + 2 warning)  
**TODO alerts (commented out):** 2 (circuit breaker, 429)
