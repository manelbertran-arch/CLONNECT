# Forensic Ligero: Commitment Tracker

**Date:** 2026-04-23
**Scope:** ligero (activation + zero-hardcoding migration; full forensic deferred to Q2 post-FT).
**Flag:** `flags.commitment_tracking` (env: `ENABLE_COMMITMENT_TRACKING`, Railway: `false` pre-sprint).
**State of the art:** see `commitment_tracker_state_of_art.md` (verdict: **ADAPT-NOW Path A**).

## 1. What the system does

Detects bot-commitments in generated responses (e.g. *"te envío el link mañana"*), persists them in the `commitments` table, and re-injects pending commitments into the prompt on later turns via `RelationshipAdapter`.

Two callsites in the hot path:
- `core/dm/phases/postprocessing.py:655` — after LLM generation, run `detect_commitments_regex(response_content, sender="assistant", creator_id=agent.creator_id)` and persist.
- `core/dm/phases/context.py:1016` — during context assembly, `tracker.get_pending_text(sender_id)` returns pending commitments block.

Persistence: sync SQLAlchemy via `SessionLocal`; tests reference singleton `get_commitment_tracker()`.

## 2. Pre-sprint findings

| Finding | Severity | Status |
|---|---|---|
| Hardcoded Spanish regex `COMMITMENT_PATTERNS` (11 entries, delivery/info_request/meeting/follow_up/promise) and `TEMPORAL_PATTERNS` (7 entries) embedded in `commitment_tracker.py:38-66`. | **CRITICAL** (violates zero-hardcoding policy) | **Fixed this sprint** — moved to cold-start fallback + vocab_meta override. |
| Flag read inline via `os.getenv("ENABLE_COMMITMENT_TRACKING", ...)` at `context.py:1016` AND `commitment_tracker.py:28`, duplicated. | Medium (drift risk; inconsistent with registry pattern) | **Fixed this sprint** — both read `flags.commitment_tracking`. |
| Zero Prometheus observability (pattern source, detection counts). | Medium | **Fixed this sprint** — added `commitment_detected_total`, `commitment_tracker_patterns_source`. |
| No LLM fallback when regex misses future-tense commitments without exact pattern match (FnCTOD ACL 2024 recommends zero-shot DST as fallback). | Medium | **DEFER-Q2** — separate sub-flag per SotA doc. |

## 3. Fix applied this sprint (ADAPT-NOW Path A)

`backend/services/commitment_tracker.py`:

1. Renamed `COMMITMENT_PATTERNS` / `TEMPORAL_PATTERNS` → `_FALLBACK_COMMITMENT_PATTERNS` / `_FALLBACK_TEMPORAL_PATTERNS` (kept legacy aliases for backward compat).
2. Added `_load_creator_patterns(creator_id)` → `(compiled_patterns, compiled_temporal, source)` where `source ∈ {"mined", "hardcoded_fallback"}`.
   - Reads `personality_docs.vocab_meta.content.commitment_patterns` (list of `{"pattern": <regex>, "type": <str>}`) + `.temporal_patterns`.
   - If key missing or parse fails → cold-start fallback.
3. `detect_commitments_regex(message, sender, creator_id=None)` now accepts `creator_id`; per-creator override when present.
4. Emits `commitment_tracker_patterns_source{creator_id, source}` once per turn + `commitment_detected_total{creator_id, commitment_type, source}` per detection.
5. Module-level flag alias: `ENABLE_COMMITMENT_TRACKING = flags.commitment_tracking` (proxy to registry).

Context.py callsite (`line 1016`): `os.getenv(...)` → `flags.commitment_tracking`.

## 4. Metrics

| Metric | Labels | Expected signal |
|---|---|---|
| `commitment_tracker_patterns_source` | creator_id, source | Post-bootstrap: `mined` > `hardcoded_fallback` for Iris |
| `commitment_detected_total` | creator_id, commitment_type, source | Turn-level detections by type (delivery/follow_up/promise/meeting/info_request) |

## 5. Tests (3/3 passing)

`backend/tests/test_sprint_top6_forensic_ligero.py`:
- `test_commitment_tracker_flag_off_returns_empty` — flag gate
- `test_commitment_tracker_hardcoded_fallback_source` — cold-start path + metric
- `test_commitment_tracker_user_message_returns_empty` — sender filter

## 6. Bootstrap dependency

Consolidated bootstrap (`scripts/bootstrap_sprint_top6_activations.py`) will seed `personality_docs.vocab_meta.commitment_patterns` for `iris_bertran` with the current Spanish fallback. Post-bootstrap, the metric `commitment_tracker_patterns_source{creator_id="iris_bertran", source="mined"}` should be dominant.

## 7. Measurement plan snapshot

- Flag: `ENABLE_COMMITMENT_TRACKING=true` for arm B.
- Expected Δ dimensions: J2 (dialogue state coherence) +2, S2 (consistency) +1.
- Gate KEEP: ΔJ2 ≥ +2 AND ΔS2 ≥ +1.
- Gate REVERT: Δ regression > 3 on J-family (dialogue state) OR new `error` outcomes > 5% of turns.

## 8. Out-of-scope (explicit)

- FnCTOD-style LLM fallback behind sub-flag (post-regex miss). **DEFER-Q2**.
- Multi-language support beyond Spanish (add vocab_meta entries per language). **DEFER-Q2**.
- DST-graph persistence (LangGraph-style commitment DAG). **DEFER-Q2**.
- Commitment completion detection (bot says "te envío X" → user later says "gracias!" → mark complete). **DEFER-Q2**.
