# DNA Engine Auto-Create — Forensic

**Date:** 2026-04-23

## Modules involved

| Path | Purpose | LOC |
|---|---|---|
| `backend/core/dm/phases/context.py:1034-1099` | Hot-path callsite (auto-create guard + limiter) | ~60 |
| `backend/services/relationship_dna_repository.py` | `create_relationship_dna()`, `get_relationship_dna()` — DB ops | 200+ |
| `backend/services/relationship_dna_service.py` | Service layer around the repo | N/A (read-only verified) |
| `backend/services/dna_update_triggers.py` | Subsequent DNA mutations (out of scope of "create") | N/A |
| `backend/core/relationship_type_detector.py` | Classifies turn pair → relationship type | N/A |
| `backend/services/dna_auto_create_limiter.py` | **NEW** — 4-layer rate-limiter | 135 |

## Callsite flow (post-sprint)

```
phase_memory_and_context
 └─ if ENABLE_DNA_AUTO_CREATE && !dna_context && follower.total_messages >= 2
      └─ if len(hist) >= 2
           └─ limiter.acquire(creator_id, sender_id)
                ├─ Layer 4: circuit breaker (per creator) — skip if open
                ├─ Layer 1: debounce (per lead) — skip if <60s since last attempt
                ├─ Layer 2: token bucket (per creator) — skip if empty
                └─ Layer 3: semaphore (global) — await slot
           └─ RelationshipTypeDetector().detect(hist)
           └─ asyncio.create_task(_create_seed_dna)
                ├─ _get_dna() → if exists: emit skipped + release
                ├─ create_relationship_dna()
                ├─ on success: emit triggered
                ├─ on exception: trip_circuit + emit circuit_tripped
                └─ finally: limiter.release()
```

## Git history snapshot (callsite block)

| Commit | Date | Change |
|---|---|---|
| (pre-sprint state) | varies | `asyncio.create_task(_create_seed_dna())` fire-and-forget, no cap |
| (this sprint) | 2026-04-23 | Wrap with `DnaAutoCreateLimiter`; add circuit-breaker on exception |

## Pre-sprint failure modes (flag was OFF in Railway for this reason)

1. **No per-lead debounce**: a chatty lead could trigger N concurrent create attempts for the same DNA row; the `if existing: return` guard inside `_create_seed_dna` was the only safeguard (post-hoc, not pre-flight).
2. **No token bucket per creator**: burst traffic for a single creator could fire >50 creates/minute, each doing a Gemini call via `RelationshipTypeDetector`.
3. **No global semaphore**: unbounded concurrent `asyncio.create_task` → SQL pool pressure at P99.
4. **No circuit breaker**: repeated Gemini 429s produced repeated retries without backoff.

## Post-sprint callsite state — line-by-line highlights

```python
# L1041 — limiter acquire (non-blocking False means skip)
_limiter = get_dna_auto_create_limiter()
_admitted = await _limiter.acquire(agent.creator_id, sender_id)
if not _admitted:
    emit_metric("dna_auto_create_cap_hit_total", ...)
else:
    # ... limiter-admitted work ...
```

```python
# Inside _create_seed_dna:
try:
    ...
    emit_metric("dna_auto_create_triggered_total", ...)
except Exception as e:
    _limiter.trip_circuit(agent.creator_id)
    emit_metric("dna_auto_create_circuit_tripped_total", ...)
finally:
    _limiter.release()
```

`release()` is in `finally` so the semaphore is always returned regardless of success/failure.

## Dependencies

- Reads: `follower.total_messages`, `dna_context`, `metadata["history"]`
- Writes: `relationship_dna` table (via repo)
- External calls: `RelationshipTypeDetector` (may hit Gemini)

## Observability

Four new Prometheus metrics (registered in `core/observability/metrics.py`):
- `dna_auto_create_triggered_total{creator_id, relationship_type}`
- `dna_auto_create_cap_hit_total{creator_id, reason}`
- `dna_auto_create_skipped_total{creator_id, reason}` (e.g. race → row already exists)
- `dna_auto_create_circuit_tripped_total{creator_id}`
