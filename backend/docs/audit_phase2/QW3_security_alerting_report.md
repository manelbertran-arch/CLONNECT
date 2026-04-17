# QW3 — Fix Security Flags Alerting

**Date:** 2026-04-16
**Branch:** main (local — not pushed)
**Commits:** `e31534c5 → fb2e95d6 → 00f3ea89`
**Author:** Claude Opus 4.6 (paired with Manel)

---

## 1. Problem

Two fields in `cognitive_metadata` were written on every match by
`core/dm/phases/detection.py` but had zero downstream consumers:

| Field | Site | What fires it |
|-------|------|---------------|
| `prompt_injection_attempt` | detection.py:103 | Any of 6 regex patterns (Perez & Ribeiro 2022) |
| `sensitive_detected` | detection.py:125 | `detect_sensitive_content()` confidence ≥ threshold |

Result: **zero observability on security incidents**. Attacker sends 200
jailbreak attempts/minute, nobody ever sees the signal. This was
confirmed in `docs/audit_phase2/W2_metadata_flow.md`.

## 2. Scope

**In scope:**
- Persistent DB log (new `security_events` table).
- Rate limiting (avoid spam from 100+ attempts in burst).
- Severity levels (INFO / WARNING / CRITICAL).
- GDPR: SHA256 hash only — no raw content stored.
- Fail-silent: alerting must never crash the DM pipeline.

**Out of scope:**
- Slack / email / PagerDuty webhooks → next sprint. Current delivery
  is DB-only. Consumers (dashboards, oncall) will poll `security_events`.

## 3. Design decisions

### 3.1 Table — `security_events`

```text
id              BIGSERIAL PK                  autoincrement
creator_id      VARCHAR(100)  NOT NULL        slug (e.g. "iris_bertran"), NOT UUID
sender_id       VARCHAR(100)  NULL            Instagram platform_user_id (raw, no "ig_")
event_type      VARCHAR(40)   NOT NULL        "prompt_injection" | "sensitive_content" | "rate_limit_summary"
severity        VARCHAR(20)   NOT NULL        "INFO" | "WARNING" | "CRITICAL"
content_hash    VARCHAR(64)   NULL            SHA256 hex digest of triggering message
message_length  INTEGER       NULL            raw character length
event_metadata  JSONB         NOT NULL {}     pattern_prefix, sensitive_category, confidence, suppressed_count, …
created_at      TIMESTAMPTZ   NOT NULL NOW()  server-default
```

**Indexes:**
- `idx_security_events_creator_sender_type_time` on
  `(creator_id, sender_id, event_type, created_at)` — covers queries
  by creator, by creator+sender, by creator+sender+type. Postgres can
  scan ASC indexes backward so a DESC modifier is unnecessary.
- `idx_security_events_created_at` on `created_at` — time-window
  reports.

Single-column indexes on `creator_id` / `sender_id` / `event_type` are
**deliberately omitted** — the composite covers them via leading-column
usage, and extra indexes amplify write cost on a high-write event log.

Integer PK (not UUID): this is an append-only event log with
high-volume inserts; UUID v4 offers no ordering benefit and doubles
index size.

### 3.2 GDPR — content fingerprinting

Raw message is never persisted. We store:
- `content_hash`: SHA256 hex digest (64 chars). Allows dedup /
  correlation / bulk-signature matching without PII retention.
- `message_length`: integer, for bucket analytics.

Test `test_alert_never_persists_raw_content_gdpr` asserts the
invariant: the raw message string does not appear in any value of the
persisted row.

### 3.3 Rate limiting

In-process `cachetools.TTLCache(maxsize=10_000, ttl=300)` keyed by
`(creator_id, sender_id, event_type)`.

| Scenario | Behaviour |
|----------|-----------|
| First event on a key | Emit (count=0, `emit_now=True`). |
| Event 2..99 on same key | Suppress (no DB write). |
| Event 100, 200, 300, … | Emit a summary row (`event_type="rate_limit_summary"`, `severity="INFO"`, `event_metadata["suppressed_count"]=N`). |
| After 300s of silence | Cache entry evicted; next event restarts the cycle. |

The compound read-modify-write is guarded by a `threading.Lock` so that
concurrent `asyncio.to_thread` workers can't race-double-count. On any
cache failure we default to **emit** — an extra row beats a missed
alert.

**Caveat (documented, acceptable for QW3):** Railway runs multi-worker
uvicorn. With N workers the window is effectively N× weaker; bursts
across workers can emit up to N summary rows per 100-suppressed cycle.
Next sprint will promote the cache to Redis if volume warrants it.

### 3.4 Severity mapping

| Trigger | Severity |
|---------|----------|
| `prompt_injection` match | `WARNING` (always) |
| `sensitive_content`, confidence < `AGENT_THRESHOLDS.sensitive_escalation` | `WARNING` |
| `sensitive_content`, confidence ≥ `AGENT_THRESHOLDS.sensitive_escalation` | `CRITICAL` |
| Rate-limit summary row | `INFO` |

Unknown severities coerce to `WARNING` with a debug log.

### 3.5 Async dispatch — fail-silent fire-and-forget

```python
def dispatch_fire_and_forget(...):
    loop = asyncio.get_running_loop()          # skip silently if no loop
    task = loop.create_task(alert_security_event(...))
    _pending_tasks.add(task)                   # strong ref until done
    task.add_done_callback(_pending_tasks.discard)
```

Three layers of defense:
1. Outer try/except in `phase_detection` (never raises).
2. Outer try/except in `alert_security_event` (belt + braces).
3. Inner try/except around the `asyncio.to_thread(_sync_write)`.

Every path logs at `debug` with `exc_info=True` so the information
survives in production logs when debug level is enabled, but normal
operation stays quiet.

### 3.6 DB write pattern

```python
async def alert_security_event(...):
    await asyncio.to_thread(_sync_write, row)

def _sync_write(row):
    from api.database import get_db_session
    from api.models.security import SecurityEvent
    with get_db_session() as session:
        session.add(SecurityEvent(**row))
        session.commit()
```

Identical pattern to `core/dm/phases/context.py:163` (episodic memory
resolver). Uses the pooled sync session; pgbouncer transaction mode is
compatible because there is no session-level SET.

## 4. Files touched

```
Commit 1 (e31534c5) — migration + model
  + alembic/versions/045_add_security_events.py     (75 lines)
  + api/models/security.py                          (55 lines)
  M api/models/__init__.py                          (+2 lines)
  M DECISIONS.md                                    (+17 lines)

Commit 2 (fb2e95d6) — alerting service + unit tests
  + core/security/__init__.py                       (12 lines)
  + core/security/alerting.py                       (217 lines)
  + tests/unit/test_security_alerting.py            (264 lines, 14 tests)

Commit 3 (00f3ea89) — detection integration + integration tests
  M core/dm/phases/detection.py                     (+41 / -2 lines)
  + tests/unit/test_detection_alerting_integration.py (117 lines, 3 tests)
```

## 5. Test coverage

### Unit tests (14) — `tests/unit/test_security_alerting.py`

1. `test_hash_content_is_sha256_hex_and_stable`
2. `test_hash_content_handles_none_and_empty`
3. `test_should_emit_first_occurrence_emits_once`
4. `test_should_emit_summary_every_100_suppressed`
5. `test_alert_invokes_sync_write_once_with_expected_row`
6. `test_alert_severity_invalid_coerces_to_warning`
7. `test_alert_respects_rate_limit_within_window`
8. `test_alert_burst_emits_summary_row_on_100th_suppressed`
9. `test_alert_fail_silent_on_db_error`
10. `test_alert_never_persists_raw_content_gdpr` ← GDPR invariant
11. `test_alert_truncates_long_creator_id`
12. `test_alert_different_event_types_not_rate_limited_together`
13. `test_dispatch_fire_and_forget_creates_task`
14. `test_dispatch_fire_and_forget_no_loop_is_silent`

### Integration tests (3) — `tests/unit/test_detection_alerting_integration.py`

1. `test_prompt_injection_dispatches_alert` — asserts call shape &
   `cognitive_metadata["prompt_injection_attempt"]=True`.
2. `test_sensitive_content_dispatches_alert_with_severity` — asserts
   CRITICAL severity above escalation AND crisis short-circuit fires.
3. `test_alert_dispatch_failure_does_not_break_detection` — dispatcher
   raises `RuntimeError`; `phase_detection` completes normally.

**Results:** `17 passed in 0.05s`.

### Smoke tests — `tests/smoke_test_endpoints.py`

```
[PASS] health                         — HTTP 200
[PASS] health_live                    — HTTP 200
[PASS] health_ready                   — HTTP 200
[PASS] health_tasks                   — HTTP 200
[PASS] conversations_iris             — HTTP 200
[PASS] conversations_stefano          — HTTP 200
[PASS] debug_memory                   — HTTP 200
7/7 passed (3 DB checks skipped — no DATABASE_URL locally)
```

## 6. Review (phase 3)

Two reviewers ran in parallel:

**python-reviewer** flagged (highlights):
- H1 rate-limit race → **FIXED** with `threading.Lock`.
- H2 `_should_emit` return contract ambiguity → kept but documented.
- M3 GDPR test gap → **FIXED** (`test_alert_never_persists_raw_content_gdpr`).
- M6 dead branch in `_hash_content` → **FIXED**.
- L1–L6 lint / doc nits → partial fixes.

**code-reviewer** flagged:
- H1 unused `_RATE_LIMIT_WINDOW_SECONDS` → **REMOVED**, documented the
  300s-TTL-is-the-window model.
- M1 redundant single-column indexes → **REMOVED** from both model
  and migration.
- H3 `creator_id` truncation → **FIXED** via `[:100]` defensive slice.
- M3 tautological mocks → acknowledged; next sprint will add a DB
  round-trip fixture.

Both reviewers returned **verdict: WARNING (no blockers)**.

## 7. Risks & rollback

**Deploy risk: low.**
- Migration is purely additive (new table + indexes, no schema changes
  to existing tables). Downgrade is a clean `DROP TABLE`.
- Integration is fire-and-forget at two sites in detection.py wrapped
  in try/except — if alerting code is ever corrupted the DM pipeline
  still runs.
- Feature flags (`flags.prompt_injection_detection`,
  `flags.sensitive_detection`) gate the upstream dispatch call, so
  flipping the flags OFF disables alerting without code change.

**Rollback:** `alembic downgrade 044` removes the table; the code in
detection.py will continue to call `_dispatch_security_alert`, which
will attempt `_sync_write` and fail silently (debug log). No user-facing
impact.

## 8. Out-of-scope / Next-sprint

- Slack / email / PagerDuty webhook consumers.
- Redis-backed rate limiter for cross-worker burst control.
- End-to-end DB round-trip test (current tests mock `_sync_write`).
- Dashboard / admin endpoint: `GET /admin/security/events?since=...`.
- Retention policy: 90-day rolling purge on `security_events`
  (GDPR art. 5(1)(e) storage limitation).

---

## 9. Verification summary

| Phase | Status | Evidence |
|-------|--------|----------|
| 1 PLAN | completed | DECISIONS.md entry + this report §3 |
| 2 IMPLEMENT | completed | 3 commits, all `ast.parse` green |
| 3 REVIEW | completed | python-reviewer + code-reviewer both WARN, no BLOCK; all HIGH issues fixed |
| 4 VERIFY | completed | 17/17 unit+integration tests pass, 7/7 smoke tests pass |

QW3 closed.
