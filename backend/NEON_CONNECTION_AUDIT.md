# Neon PostgreSQL Connection Audit
**Date**: 2026-03-15
**Period analyzed**: 14 days
**Observed cost**: $9.89 compute (93.31 CU-hrs, 93.72 GB transfer)

---

## 1. Connection String Analysis

```
DATABASE_URL: postgresql://neondb_owner:***@ep-raspy-truth-agjtq3o5-pooler.c-2.eu-central-1.aws.neon.tech/neondb?sslmode=require
```

| Property | Value | Status |
|----------|-------|--------|
| Using pgbouncer pooler? | **YES** (`-pooler.` in hostname) | ✅ Correct |
| Branch endpoint | `ep-raspy-truth-agjtq3o5` | = "import-2026-01-10" branch |
| DB size | **2998 MB (3 GB)** | import-2026-01-10 branch has all real data |
| Neon main branch | ~30 MB, 0 CU-hrs | Schema only — no data |

**Branch situation is correct**: production correctly points to the branch with all data. The "import" branch name is misleading — this IS the production branch.

---

## 2. Current Connection State (snapshot)

```
state                | count | application
---------------------|-------|-------------------
idle in transaction  |   4   | pgbouncer
idle                 |   4   | pgbouncer
idle                 |   1   | neon_compute_sql_exporter  ← Neon internal
idle                 |   1   | postgres-exporter          ← Neon internal
idle                 |   1   | vm-monitor                 ← Neon internal
idle                 |   1   | compute_ctl:compute_monitor ← Neon internal
active               |   1   | pgbouncer (this audit)
None (background)    |   5   | pg_cron, TimescaleDB, etc.
```

### idle in transaction (4 connections at snapshot time):
| idle secs | last query |
|-----------|-----------|
| 14s | `SELECT messages.role, messages.content, messages.created_at...` |
| 0s  | `SELECT nurturing_followups.id...` |
| 0s  | `SELECT role, content, intent, created_at, msg_metadata->>'type' AS meta_type...` |
| 0s  | `SELECT leads.id AS leads_id, leads.creator_id...` |

These are **transient** — `idle_in_transaction_session_timeout = 5min` (already configured by Neon) kills them automatically. Not the compute-alive driver.

---

## 3. Why Compute NEVER Scales to Zero

### Root cause: SQLAlchemy QueuePool keeps 10 persistent connections

```python
# api/database.py
engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=10,      # ← 10 connections ALWAYS open
    max_overflow=10,   # ← 10 more on demand
    pool_recycle=1800, # ← recycle every 30 min (not close!)
    ...
)
```

**QueuePool never closes connections** — it recycles them (sends a new connection to the pooler), but always maintains `pool_size` live connections. Neon compute requires **zero connections** to scale to zero. With pool_size=10, this is impossible.

### Secondary: 23 cron jobs wake DB continuously

| Job | Interval | Keeps DB alive |
|-----|----------|----------------|
| reconciliation | every 30 min | YES — wakes DB every 30 min |
| token_refresh | every 6h | YES |
| post_context_refresh | every 12h | YES |
| pattern_analyzer | every 12h | YES |
| gold_examples | every 12h | YES |
| score_decay | every 24h | YES |
| ... (17 more) | daily/weekly | YES |

Even if the pool were NullPool, the 30-min reconciliation job alone would prevent Neon from sleeping longer than 30 minutes.

### Tertiary: Real traffic (Iris/Stefano WhatsApp + Instagram)

Active conversations prevent any meaningful idle window. The compute endpoint sees activity every few minutes.

### Internal Neon processes

`vm-monitor`, `neon_autoscaling_sql_exporter`, `postgres-exporter`, `compute_ctl:compute_monitor` run as Neon-internal connections that are NOT user connections. They don't prevent scale-to-zero but indicate active compute. Auto-suspend setting: `NULL` (configured at project level, likely 5 min from Neon dashboard).

---

## 4. Session Leak Analysis (368 suspect functions)

```
python3 audit: 368 functions open SessionLocal() WITHOUT try/finally
```

### Top offenders (high-traffic code paths):
| File | Function | Risk |
|------|----------|------|
| `core/instagram_modules/echo.py` | 3 separate opens | HIGH — per-webhook |
| `core/instagram_modules/message_store.py` | 2 separate opens | HIGH — per-webhook |
| `core/copilot/actions.py` | 3 opens | HIGH — per-message |
| `core/copilot/lifecycle.py` | per-message | HIGH |
| `core/copilot/service.py` | 3 opens | HIGH |
| `services/lead_scoring.py` | per-lead | MEDIUM |
| `core/embeddings.py` | 4 functions | MEDIUM |
| `core/webhook_routing.py` | per-webhook | HIGH |
| `core/send_guard.py` | per-send | HIGH |

### Why it matters:
If **any exception** is raised after `session = SessionLocal()` but before `session.close()`, the connection enters `idle in transaction` state. With `idle_in_transaction_session_timeout = 5min`, it self-heals — but during exception storms (e.g., LLM provider rate-limits causing cascading failures), 10-20 connections can pile up idle-in-transaction simultaneously, exhausting the pool for 5 minutes.

### Session pattern that leaks:
```python
# BAD — session leaks on exception
session = SessionLocal()
result = session.query(...)  # exception thrown here
session.close()  # never reached
```

### Correct pattern:
```python
# GOOD — always closes
session = SessionLocal()
try:
    result = session.query(...)
    session.commit()
finally:
    session.close()
```

---

## 5. Database Size & Network Transfer (93.72 GB in 14 days)

### Table sizes:
| Table | Total size | Rows |
|-------|-----------|------|
| `messages` | **1848 MB** | 59,260 |
| `conversation_embeddings` | **1073 MB** | 42,534 |
| `lead_memories` | 43 MB | 2,933 |
| `content_embeddings` | 4 MB | 452 |
| All others | < 2 MB each | — |

### The `messages` table breakdown:
| Component | Size |
|-----------|------|
| Table total | 1848 MB |
| `content` column (text) | 2.3 MB |
| `msg_metadata` column (JSONB) | **755 MB** |

### The thumbnail_base64 problem:
```
415 rows with thumbnail_base64 in msg_metadata = 751 MB out of 755 MB total metadata
Average metadata size: 13 KB per row
Maximum metadata size: 37 MB (one row!)
```

**415 messages contain base64-encoded images/thumbnails stored directly in JSONB** = 751 MB of binary data in the database. This is queried on EVERY read of `msg_metadata`, even when only the `type` field is needed.

### Why 93.72 GB transferred in 14 days (= 6.7 GB/day):

**Before the `extract_signals` fix (2026-03-14):**
- `batch_recalculate_scores` queried `Message.msg_metadata` for ALL 100 messages per lead
- 2,490 leads × 100 msgs/lead × avg 13KB msg_metadata = **3.24 GB per scoring run**
- Scoring ran daily = **3.24 GB/day** just from scoring

**Still happening:**
- `conversation_embeddings` 1073 MB queried for vector RAG on every DM response
- Any query that SELECTs `msg_metadata` without column filtering transfers full JSONB
- Follower detail endpoint was loading 50 messages × full metadata (now fixed with JSONB operator)

**Estimate post-fix daily transfer:**
- DM response RAG queries: ~250 msgs/day × some embedding lookups ≈ low MB
- Background jobs querying leads/messages: variable
- Should be <500 MB/day now that scoring is fixed

---

## 6. SQLAlchemy Pool Configuration

```python
# api/database.py — current config
pool_size=10       # 10 permanent connections always open
max_overflow=10    # 10 burst connections (max 20 total)
pool_timeout=10    # 10s before "pool exhausted" error
pool_recycle=1800  # recycle (not close) connections every 30 min
pool_pre_ping=True # test before use
keepalives=1       # TCP keepalive on
```

### Problem: `pool_size=10` for a serverless database is counterproductive

For Neon (serverless), the ideal is either:
- **NullPool** (no persistent connections — every query opens+closes) → enables scale-to-zero
- **pool_size=1 or 2** → minimum connections to keep compute alive, fast for single-worker

With pool_size=10, Railway's single uvicorn worker maintains 10 open DB connections at all times, guaranteeing compute never sleeps.

---

## 7. Timeout Settings

| Setting | Current value | Recommendation |
|---------|--------------|----------------|
| `idle_in_transaction_session_timeout` | **5min** | ✅ OK — kills leaked transactions |
| `lock_timeout` | 0 (unlimited) | Consider 30s to prevent deadlock hangs |
| `statement_timeout` | 0 (unlimited) | Consider 60s to kill runaway queries |

---

## 8. Recommendations (Prioritized)

### P0 — Reduce pool_size to reduce baseline compute cost
```python
# api/database.py
pool_size=2,       # was 10 — 2 is enough for single uvicorn worker
max_overflow=8,    # was 10 — still allows burst to 10
pool_recycle=300,  # was 1800 — recycle faster (5 min) to help pgbouncer
```
**Impact**: Reduces from 10 permanent connections to 2. Neon still won't scale to zero (real traffic + cron jobs prevent it), but reduces minimum compute footprint.

### P1 — Remove thumbnail_base64 from messages JSONB
415 rows with base64-encoded images in JSONB = 751 MB of binary data that gets transferred on every `msg_metadata` query.
```sql
-- Strip thumbnail_base64 from existing rows (migration)
UPDATE messages
SET msg_metadata = msg_metadata - 'thumbnail_base64'
WHERE msg_metadata ? 'thumbnail_base64';
-- Saves: ~751 MB of stored data, dramatically reduces query transfer
```
Already has a reference to `thumbnail_url` (Cloudinary URL) — no data loss.

### P2 — Add statement_timeout to prevent runaway queries
```sql
ALTER DATABASE neondb SET statement_timeout = '60s';
ALTER DATABASE neondb SET lock_timeout = '30s';
```

### P3 — Fix 368 session leaks (add try/finally)
Focus on high-traffic paths first:
- `core/instagram_modules/echo.py`
- `core/copilot/lifecycle.py`
- `core/copilot/actions.py`
- `core/webhook_routing.py`

### P4 — Reduce reconciliation interval
The 30-min reconciliation job is the most frequent DB waker. If it's not critical, increase to every 2-4h.

### P5 — Accept that compute always runs (it's correct)
With 2 active creators sending WA/IG messages throughout the day, compute SHOULD be running continuously. The $9.89/14 days ($0.71/day) is reasonable for an active production service. Scale-to-zero is only meaningful for staging/dev branches.

---

## 9. Quick Wins Already Done

| Fix | Date | Impact |
|-----|------|--------|
| `extract_signals` JSONB fix | 2026-03-14 | Stopped querying full 755MB metadata in scoring |
| Scoring paged batches (50/session) | 2026-03-14 | No more 30s monopolized DB sessions |
| follower_detail JSONB stripping | previous | No more 50×full-metadata per follower view |
| pool_size 5→10 with pool_timeout 30→10 | 2026-03-14 | More connections, faster failure |

---

## 10. Neon Dashboard Actions

1. **Increase auto-suspend timeout** to match your traffic pattern. If traffic stops at night (e.g. 2-8 AM UTC), set suspend after 10 min. Currently appears to be 5 min but compute never actually idles.
2. **Migrate to Neon Scale plan** if you want scale-to-zero with >100 connections (current Free/Launch plan limits apply).
3. **Consider deleting the `import-2026-01-10` branch** if it's just a historical artifact — keeping branches with 3 GB of data incurs storage costs even when not active.
4. **Set DB-level timeouts**:
   ```sql
   ALTER DATABASE neondb SET statement_timeout = '60s';
   ALTER DATABASE neondb SET lock_timeout = '30s';
   ```
