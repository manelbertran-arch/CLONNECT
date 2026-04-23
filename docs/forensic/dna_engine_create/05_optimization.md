# DNA Engine Auto-Create — Optimization (Sprint top-6)

**Date:** 2026-04-23
**Verdict:** ADAPT-NOW per `04_state_of_art.md`. 4-layer in-process limiter, no Redis, ~135 LOC.

## 1. Changes applied this sprint

### A. New module: `services/dna_auto_create_limiter.py` (135 LOC)

`DnaAutoCreateLimiter` — 4-layer guard:
1. **Per-lead debounce** (`DEBOUNCE_SECONDS = 60`) — reject same `(creator_id, follower_id)` within 60s.
2. **Token bucket per creator** (`TOKEN_BUCKET_CAPACITY = 20`, `TOKEN_BUCKET_WINDOW_SECONDS = 3600`) — refill-on-read; max 20 tokens/hour/creator.
3. **Global concurrency semaphore** (`asyncio.Semaphore(3)`) — max 3 concurrent in-flight creates.
4. **Circuit breaker per creator** (`CIRCUIT_OPEN_SECONDS = 300`) — tripped by `trip_circuit(creator_id)` after a downstream exception; blocks acquires for 5 min.

Module singleton via `get_dna_auto_create_limiter()` (lazy).

### B. Callsite rewrite: `core/dm/phases/context.py:1034-1099`

- Wrapped the existing `asyncio.create_task(_create_seed_dna())` with `limiter.acquire(...)`.
- On limiter denial → emit `dna_auto_create_cap_hit_total{reason="limiter_denied"}` and skip.
- On admission → run detector + create_task; inside the task:
  - `existing` row → emit `dna_auto_create_skipped_total{reason="already_exists"}` + release.
  - Success → emit `dna_auto_create_triggered_total{relationship_type=...}`.
  - Exception → `limiter.trip_circuit(creator_id)` + emit `dna_auto_create_circuit_tripped_total` + release.
- `cognitive_metadata["dna_seed_created"]` is set ONLY on admission (fixes DNA-06).

### C. Prometheus metrics (new, in central registry)

```python
("dna_auto_create_triggered_total",       Counter, "...", ["creator_id", "relationship_type"], {}),
("dna_auto_create_cap_hit_total",          Counter, "...", ["creator_id", "reason"], {}),
("dna_auto_create_skipped_total",          Counter, "...", ["creator_id", "reason"], {}),
("dna_auto_create_circuit_tripped_total",  Counter, "...", ["creator_id"], {}),
```

### D. Tests: 9 new in `backend/tests/test_sprint_top6_dna_create.py`

1. `test_dna_limiter_fresh_acquire_returns_true` — happy path
2. `test_dna_limiter_debounce_blocks_second_attempt` — Layer 1
3. `test_dna_limiter_token_bucket_caps_per_creator` — Layer 2 (fast-fire 25 in 25s → ≤21 admits, ≥4 denials)
4. `test_dna_limiter_global_semaphore_caps_concurrency` — Layer 3 (4th acquire blocks with asyncio.wait_for timeout)
5. `test_dna_limiter_circuit_breaker_blocks_until_window_expires` — Layer 4 (300s)
6. `test_dna_limiter_debounce_releases_after_window` — idempotence after 61s
7. `test_dna_limiter_double_release_is_safe` — defensive release
8. `test_dna_limiter_different_leads_same_creator_independent` — debounce key isolation
9. `test_dna_limiter_separate_creators_separate_buckets` — bucket isolation

All 9 pass (`pytest tests/test_sprint_top6_dna_create.py`).

## 2. Deferred (DEFER-Q2)

| Item | Source | Reason |
|---|---|---|
| `_SEED_TRUST` → `vocab_meta.seed_trust_by_type` per creator | DNA-05 | Data-derivation is orthogonal to activation; fix cap first, data-derive later |
| `RelationshipTypeDetector` module-level singleton | DNA-07 | Performance micro-opt; measure first |
| PII redaction in `[DNA-SEED]` logs | DNA-08 | Holistic audit out of scope |
| Redis distributed coordination | `04_state_of_art.md` §5 | Overkill for single-node deployment |
| Prometheus gauge for token bucket fill level | ― | Counters cover usage; gauge is DX nicety |

## 3. Activation

Railway command (CEO executes):

```bash
railway variables set ENABLE_DNA_AUTO_CREATE=true --service web
```

Observability to watch post-activation (first 1h):

| Metric | Expected |
|---|---|
| `dna_auto_create_triggered_total` | Steady rate, ≤ `#new_leads_per_hour` |
| `dna_auto_create_cap_hit_total{reason="limiter_denied"}` | Low (<10% of attempts); non-zero indicates the limiter is doing its job |
| `dna_auto_create_skipped_total{reason="already_exists"}` | Near-zero post-debounce (was the pre-sprint symptom) |
| `dna_auto_create_circuit_tripped_total` | 0 in healthy operation; >0 indicates downstream (Gemini) failure |

## 4. Rollback

```bash
railway variables set ENABLE_DNA_AUTO_CREATE=false --service web
```
Zero code rollback required.

## 5. Activation readiness

- [x] Layer-1 debounce implemented
- [x] Layer-2 token bucket implemented
- [x] Layer-3 global semaphore implemented
- [x] Layer-4 circuit breaker implemented
- [x] 4 observability counters
- [x] 9 tests passing
- [x] State-of-the-art verdict: ADAPT-NOW confirmed by literature + repos (`04_state_of_art.md`)
- [x] Bug catalog: 2 HIGH + 2 MEDIUM fixed; 2 LOW/INFO deferred
- [ ] CCEE measurement (see `06_measurement_plan.md`)
