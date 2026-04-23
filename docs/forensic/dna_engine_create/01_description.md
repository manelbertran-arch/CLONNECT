# DNA Engine Auto-Create — Description

**Date:** 2026-04-23
**Flag:** `flags.dna_auto_create` (env: `ENABLE_DNA_AUTO_CREATE`, Railway: `false` pre-sprint)

## Value proposition

On a lead's 2nd message (or later, when no prior DNA exists), the system auto-builds a *seed* Relationship DNA row: a per-(creator, follower) persona record capturing relationship type (e.g. `CLIENTE`, `AMISTAD_CASUAL`), initial trust score, and depth level. Downstream phases (tone selection, product gating, style modulation) consume this DNA to personalise responses.

Without auto-create, leads fall through with no DNA → downstream uses generic defaults → persona fidelity degrades.

## Why it matters for CCEE

| Dimension | Rationale | Expected Δ |
|---|---|---|
| **B2 (baseline adherence)** | DNA drives relationship-aware tone; absence defaults to generic. | +2 to +4 |
| **L1 (length calibration)** | Different relationship types warrant different message lengths. | +1 to +2 |
| **K1 (context coherence)** | Relationship continuity across turns. | +1 to +3 |
| **S4 (adaptation)** | Per-lead personalisation. | +1 to +2 |

## Callsite (hot path, post-sprint)

`backend/core/dm/phases/context.py:1034-1099` (updated):

```python
if ENABLE_DNA_AUTO_CREATE and not dna_context and follower.total_messages >= 2:
    if len(hist) >= 2:
        _limiter = get_dna_auto_create_limiter()
        _admitted = await _limiter.acquire(agent.creator_id, sender_id)
        if not _admitted:
            emit_metric("dna_auto_create_cap_hit_total", ...)
        else:
            # ... RelationshipTypeDetector → asyncio.create_task(_create_seed_dna())
            # _create_seed_dna() calls _limiter.trip_circuit + release on exception;
            # release always in finally.
```

## Why a 4-layer cap is needed (pre-sprint problem)

Pre-sprint, the callsite did `asyncio.create_task(_create_seed_dna())` with no rate-limit. Observed issues:
- Burst traffic per creator (10+ new leads arriving simultaneously) triggered 10+ concurrent DB writes and Gemini calls for relationship detection.
- No cooldown per lead: race conditions caused multiple attempts for the same lead.
- No global concurrency cap: pool pressure against the 5+7=12 SQLAlchemy connection pool under P99 load.
- No circuit breaker for LLM-fallback failures (e.g. Gemini 429s): cascade failures caused by repeated retries.

The 4-layer limiter (see `05_optimization.md`) addresses all four failure modes in-process, single-node, with ~60 LOC and zero new infrastructure.

## Non-goals

- Redis / distributed coordination (single-node Railway deployment — overkill).
- Full DNA profile (just the seed; enrichment lives in `dna_update_triggers.py`).
- Eager bootstrap for existing leads (on-demand only to avoid batch load).
