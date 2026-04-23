# DNA Engine Auto-Create — Bug Catalog

**Date:** 2026-04-23
**Scope:** issues uncovered during sprint forensic. Severity reflects state AT sprint start (pre-fix).

| ID | Severity | Title | State pre-sprint | State post-sprint |
|---|---|---|---|---|
| DNA-01 | **HIGH** | No per-lead debounce — race condition allows multiple concurrent create attempts for the same DNA row. Saved only by `if existing: return` inside the async task, which is a post-hoc guard (already fired Gemini call + DB read + write attempt). | Unfixed; flag OFF in Railway as compensating control. | **Fixed** — Layer-1 debounce 60s in `DnaAutoCreateLimiter.acquire()`. |
| DNA-02 | **HIGH** | No token-bucket cap per creator — burst traffic could trigger >50 creates/min for a single creator, each doing a Gemini relationship-detector call. | Unfixed; flag OFF. | **Fixed** — Layer-2 token bucket (20/h/creator) in `DnaAutoCreateLimiter`. |
| DNA-03 | **MEDIUM** | No global concurrency cap — unbounded `asyncio.create_task` under bursty load → pool pressure on 5+7=12 SQLAlchemy pool. | Unfixed. | **Fixed** — Layer-3 global `asyncio.Semaphore(3)`. |
| DNA-04 | **MEDIUM** | No circuit breaker — Gemini 429/timeouts caused cascading retries without backoff. | Unfixed. | **Fixed** — Layer-4 300s circuit breaker per creator, tripped on any downstream exception. |
| DNA-05 | **LOW** | `_SEED_TRUST` map hardcoded in the callsite (relationship_type → trust float). Not creator-specific and not data-derived. | Present. | **Unchanged** — KEEP-AS-IS for this sprint; DEFER-Q2 (move to `vocab_meta.seed_trust_by_type` per creator). |
| DNA-06 | **LOW** | `cognitive_metadata["dna_seed_created"] = True` is set even when the limiter denies admission (not this sprint — **fixed** by moving the metadata assignment inside the `else` branch). | Unfixed. | **Fixed** — metadata only set when admitted. |
| DNA-07 | **INFO** | `RelationshipTypeDetector().detect()` is a fresh instance per call; if the detector has significant construction cost (embeddings loaded), this is wasteful. | Present. | **DEFER-Q2** — move to module-level singleton. |
| DNA-08 | **INFO** | Logging uses f-strings for `[DNA-SEED]` logs; logs may contain PII (sender_id). | Present. | **DEFER-Q2** — consistent with the rest of the pipeline; holistic PII audit is out of scope. |

## Summary by severity (pre-sprint)

| Severity | Count | Status after sprint |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 2 | **Both fixed** |
| MEDIUM | 2 | **Both fixed** |
| LOW | 2 | 1 fixed, 1 deferred |
| INFO | 2 | Both deferred |

## Activation criterion

HIGH findings fixed, MEDIUM findings fixed → **activation unblocked** per sprint gate.

Flag-flip instruction: see `05_optimization.md` §Activation.
