# ARC2 Migration Runbook — Legacy Memory → arc2_lead_memories

**Worker:** A2.3  
**Branch:** feature/arc2-migration-scripts  
**Target table:** arc2_lead_memories (migration 047)  
**Impact:** Zero until executed manually. Scripts are read-only (dry-run default).

---

## Pre-checks (MANDATORY before any run)

```bash
# 1. Snapshot the DB (Railway — execute from prod machine)
pg_dump $DATABASE_URL --no-owner --no-acl -Fc -f /tmp/arc2_pre_migration_$(date +%Y%m%d).dump

# 2. Verify arc2_lead_memories exists
psql $DATABASE_URL -c "\dt arc2_lead_memories"

# 3. Count current rows in all 3 legacy sources
psql $DATABASE_URL -c "SELECT COUNT(*) FROM follower_memories;"
psql $DATABASE_URL -c "SELECT COUNT(*) FROM lead_memories WHERE is_active = true;"
psql $DATABASE_URL -c "SELECT COUNT(*) FROM arc2_lead_memories;"

# 4. Disk space (for embedding data)
df -h

# 5. Verify Python env
.venv/bin/python3.11 -c "from api.database import SessionLocal; print('DB OK')"
```

---

## Recommended execution order

### Step 1 — Dry-run all scripts

```bash
# Source A: follower_memories table (~15K rows estimated)
.venv/bin/python3.11 -m scripts.migrate_conversation_memory --dry-run 2>&1 | tee /tmp/arc2_dry_conv.log
tail -5 /tmp/arc2_dry_conv.log

# Source B: FollowerMemory JSON files (~500 files in data/followers/)
.venv/bin/python3.11 -m scripts.migrate_follower_jsons --dry-run 2>&1 | tee /tmp/arc2_dry_json.log
tail -5 /tmp/arc2_dry_json.log

# Source C: legacy lead_memories table (currently ~0 rows, flag OFF)
.venv/bin/python3.11 -m scripts.migrate_legacy_lead_memories --dry-run 2>&1 | tee /tmp/arc2_dry_legacy.log
tail -5 /tmp/arc2_dry_legacy.log
```

Review estimated counts before proceeding.

---

### Step 2 — Run migrate_conversation_memory (follower_memories → arc2)

```bash
# Full run (default: batch_size=1000, sleep=2s)
.venv/bin/python3.11 -m scripts.migrate_conversation_memory \
    --batch-size 500 \
    --sleep-between-batches 3 \
    2>&1 | tee /tmp/arc2_run_conv.log

# Verify
psql $DATABASE_URL -c "
  SELECT last_writer, COUNT(*) 
  FROM arc2_lead_memories 
  WHERE last_writer = 'migration_conversation_memory'
  GROUP BY last_writer;
"
```

---

### Step 3 — Run migrate_follower_jsons (JSON files → arc2)

```bash
# Run with default base-path (data/followers/)
.venv/bin/python3.11 -m scripts.migrate_follower_jsons \
    2>&1 | tee /tmp/arc2_run_json.log

# Verify
psql $DATABASE_URL -c "
  SELECT last_writer, COUNT(*) 
  FROM arc2_lead_memories 
  WHERE last_writer = 'migration_follower_json'
  GROUP BY last_writer;
"
```

---

### Step 4 — Run migrate_legacy_lead_memories (lead_memories → arc2)

```bash
# Only run if lead_memories has rows (flag ENABLE_MEMORY_ENGINE was ever ON)
psql $DATABASE_URL -c "SELECT COUNT(*) FROM lead_memories WHERE is_active = true;"

# If count > 0:
.venv/bin/python3.11 -m scripts.migrate_legacy_lead_memories \
    --batch-size 200 \
    --sleep-between-batches 2 \
    2>&1 | tee /tmp/arc2_run_legacy.log
```

---

### Step 5 — Re-extraction (AFTER A2.2 MemoryExtractor is merged)

```bash
# Check how many low-confidence records need re-extraction
psql $DATABASE_URL -c "
  SELECT COUNT(*) 
  FROM arc2_lead_memories 
  WHERE last_writer LIKE 'migration%' AND confidence < 0.7;
"

# Dry-run first
.venv/bin/python3.11 -m scripts.reextract_low_confidence \
    --dry-run \
    --max-records 100 \
    2>&1 | tee /tmp/arc2_dry_reextract.log

# Full run (slow — LLM calls with 1s sleep)
.venv/bin/python3.11 -m scripts.reextract_low_confidence \
    --confidence-threshold 0.7 \
    --batch-size 50 \
    --sleep-between-calls 1.5 \
    2>&1 | tee /tmp/arc2_run_reextract.log
```

---

## Rollback

If anything goes wrong, delete all migrated records (safe — uses `last_writer` tag):

```sql
-- Review before deleting
SELECT last_writer, COUNT(*)
FROM arc2_lead_memories
GROUP BY last_writer
ORDER BY count DESC;

-- Rollback one source at a time
DELETE FROM arc2_lead_memories WHERE last_writer = 'migration_conversation_memory';
DELETE FROM arc2_lead_memories WHERE last_writer = 'migration_follower_json';
DELETE FROM arc2_lead_memories WHERE last_writer = 'migration_memory_engine';
DELETE FROM arc2_lead_memories WHERE last_writer = 'reextraction';

-- Or full rollback of all migration data
DELETE FROM arc2_lead_memories WHERE last_writer LIKE 'migration%' OR last_writer = 'reextraction';
```

---

## Post-migration verification queries

```sql
-- Total rows per writer
SELECT last_writer, COUNT(*) AS cnt
FROM arc2_lead_memories
WHERE deleted_at IS NULL
GROUP BY last_writer
ORDER BY cnt DESC;

-- Distribution by memory_type
SELECT memory_type, COUNT(*) AS cnt
FROM arc2_lead_memories
WHERE deleted_at IS NULL
GROUP BY memory_type
ORDER BY cnt DESC;

-- Confidence distribution
SELECT
  CASE
    WHEN confidence >= 0.9 THEN 'high (≥0.9)'
    WHEN confidence >= 0.7 THEN 'medium (0.7–0.9)'
    ELSE 'low (<0.7)'
  END AS band,
  COUNT(*) AS cnt
FROM arc2_lead_memories
WHERE deleted_at IS NULL
GROUP BY band;

-- Records pending re-extraction
SELECT COUNT(*)
FROM arc2_lead_memories
WHERE last_writer LIKE 'migration%' AND confidence < 0.7 AND deleted_at IS NULL;

-- Unique leads covered
SELECT COUNT(DISTINCT lead_id)
FROM arc2_lead_memories
WHERE deleted_at IS NULL;

-- Objections and relationship_state with missing why (should be 0)
SELECT COUNT(*)
FROM arc2_lead_memories
WHERE memory_type IN ('objection', 'relationship_state')
  AND (why IS NULL OR how_to_apply IS NULL)
  AND deleted_at IS NULL;
```

---

## Phase 2 — Dual-Write (A2.4)

Phase 2 activates the live dual-write bridge. Every legacy write to the 3 legacy systems
also writes to `arc2_lead_memories` in real time. **Fail-silent** — never blocks a request.

### Activate dual-write

```bash
# Set env var in Railway (or .env for local)
ENABLE_DUAL_WRITE_LEAD_MEMORIES=true

# Verify flag is ON after deploy
curl -s https://www.clonnectapp.com/health | python3 -m json.tool | grep dual_write
```

### Monitor dual-write health

```sql
-- Live writes by source (check after 30 min)
SELECT last_writer, COUNT(*) AS cnt, MAX(updated_at) AS last_seen
FROM arc2_lead_memories
WHERE last_writer LIKE 'dual_write_%' AND deleted_at IS NULL
GROUP BY last_writer ORDER BY last_seen DESC;

-- Recent drift: are writes flowing?
SELECT last_writer, COUNT(*) AS cnt
FROM arc2_lead_memories
WHERE last_writer LIKE 'dual_write_%'
  AND updated_at > NOW() - INTERVAL '1 hour'
  AND deleted_at IS NULL
GROUP BY last_writer;
```

Or run the drift report script:

```bash
.venv/bin/python3.11 -m scripts.dual_write_diff_report
# JSON output for monitoring:
.venv/bin/python3.11 -m scripts.dual_write_diff_report --json
```

### Kill switch (instant rollback)

```bash
# Turn off without deploy — Railway env var update takes effect on next request
ENABLE_DUAL_WRITE_LEAD_MEMORIES=false
```

To remove already dual-written data:

```sql
DELETE FROM arc2_lead_memories
WHERE last_writer LIKE 'dual_write_%';
```

### Criteria to advance to Phase 3 (read cutover)

- [ ] `dual_write_memory_extraction`, `dual_write_follower_memory`, `dual_write_conversation_memory` all have rows
- [ ] No spike in Railway error logs tagged `[DualWrite]`
- [ ] Drift report shows coverage ≥ 80%
- [ ] Soak period: minimum 7 days with flag ON in production

---

## Notes

- Scripts are **idempotent** — safe to re-run. ON CONFLICT DO NOTHING prevents duplicates.
- The `reextraction` step is optional for Phase 2; required before Phase 3 cutover.
- `last_writer` tag always starts with `migration_` — used for rollback targeting.
- Embeddings from `lead_memories` (vector 1536) are preserved as-is in arc2_lead_memories.
- The `follower_memories` table and `lead_memories` table are NOT modified — legacy systems continue to work.
