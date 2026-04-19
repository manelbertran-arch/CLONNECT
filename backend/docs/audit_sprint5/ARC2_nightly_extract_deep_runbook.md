# ARC2 Nightly extract_deep — Operational Runbook

**Branch:** `feature/arc2-extract-deep-scheduler`
**Status:** READY — not yet activated in prod (ENABLE_NIGHTLY_EXTRACT_DEEP=false)
**Blocker resolved:** This job resolves the A2.6 blocker found in the ARC2 implementation audit.

---

## 1. What is this job and why?

`extract_deep` is the LLM-based branch of the ARC2 hybrid memory extractor (`services/memory_extractor.py`, §2.5 Opción C).

The regex sync path (`extract_from_message`) only covers `identity` and `intent_signal` — because those can be detected per-turn in under 200ms.

The remaining 3 types require multi-turn conversation context and LLM reasoning:
- `objection` — price resistance, doubts, blockers
- `interest` — topic/product interest inferred from conversation arc
- `relationship_state` — lead status transitions (new → warm → customer → cold/ghost → reactivation)

**Without this job, those 3 types only get populated via legacy dual-write (A2.4).**
A2.6 (legacy removal) CANNOT run until this job has been validated for 7 consecutive days in prod.

---

## 2. How the job activates

### Via TaskScheduler (preferred — no external dependency)

The job is registered in `api/startup/handlers.py` as `"nightly_extract_deep"`, running every 86400s (24h), with initial delay 720s.

To enable in prod:
```bash
# Railway env vars (or .env for local)
ENABLE_NIGHTLY_EXTRACT_DEEP=true
```

After setting the env var, the next Railway deploy will pick it up. The job fires 720s (~12 min) after app start, then every 24h.

### Via standalone script (Railway scheduled job or local)

```bash
# Dry-run: count candidates without calling LLM
python3 scripts/nightly_extract_deep.py --dry-run --max-leads 100

# Full run (all creators, up to 1000 leads)
python3 scripts/nightly_extract_deep.py

# Limit to one creator (useful for validation)
python3 scripts/nightly_extract_deep.py --creator-id <CREATOR_UUID>

# With Railway exec
railway run python3 scripts/nightly_extract_deep.py --dry-run
```

### Railway Scheduled Job (external cron — if not using TaskScheduler)

In Railway project settings → Cron Jobs:
```
Schedule: 0 3 * * *   (03:00 UTC daily)
Command:  python3 scripts/nightly_extract_deep.py --max-leads 1000
```

---

## 3. How to monitor

### Check memories populated by nightly job

```sql
-- Count memories by type, last 7 days
SELECT
  memory_type,
  COUNT(*) as cnt,
  AVG(confidence) as avg_confidence
FROM arc2_lead_memories
WHERE last_writer = 'extract_deep_nightly'
  AND created_at > NOW() - INTERVAL '7 days'
  AND deleted_at IS NULL
GROUP BY memory_type
ORDER BY cnt DESC;

-- Daily extraction trend
SELECT
  DATE(created_at) as day,
  memory_type,
  COUNT(*) as memories_created
FROM arc2_lead_memories
WHERE last_writer = 'extract_deep_nightly'
  AND deleted_at IS NULL
GROUP BY day, memory_type
ORDER BY day DESC, memories_created DESC;

-- Check last run (scheduler health)
-- Use: GET /health → task_scheduler section → "nightly_extract_deep"
```

### Scheduler health endpoint

```bash
curl https://www.clonnectapp.com/health | python3 -m json.tool | grep -A 10 nightly_extract_deep
```

Expected output when healthy:
```json
"nightly_extract_deep": {
  "is_running": false,
  "run_count": 7,
  "error_count": 0,
  "last_run": "2026-04-26T03:12:00.000Z",
  "interval_seconds": 86400
}
```

### Railway logs

```bash
railway logs --tail 100 2>&1 | grep "NIGHTLY_EXTRACT_DEEP\|nightly_extract_deep"
```

---

## 4. Expected LLM cost per nightly run

**Assumptions:**
- 200 active leads per night (last 48h window)
- 20 turns per conversation = ~600 tokens input context
- Extractor prompt template: ~400 tokens
- Total input per lead: ~1000 tokens
- Output per lead: ~200 tokens (XML response)
- Model: `google/gemma-4-31b-it` via OpenRouter
- Price: ~$0.04/M input, ~$0.04/M output (Gemma 4 31B on OpenRouter as of Apr 2026)

**Calculation:**
- Input: 200 leads × 1000 tokens = 200K tokens → $0.008
- Output: 200 leads × 200 tokens = 40K tokens → $0.0016
- **Total: ~$0.01/night** (< $0.30/month)

Rate limiting: 1s sleep between leads → job takes ~3-4 min for 200 leads.

If active leads grow to 2000:
- Total: ~$0.10/night → ~$3/month (still negligible)

---

## 5. Kill-switch

To immediately stop the job:

```bash
# Option A: env var (immediate effect after deploy)
railway variables set ENABLE_NIGHTLY_EXTRACT_DEEP=false

# Option B: if running as standalone cron, remove from Railway Cron Jobs settings
```

The job is fail-silent per lead — a single LLM failure never crashes the job. If the LLM provider has an outage, the job logs warnings and moves on.

---

## 6. Criteria for A2.6 legacy removal unblocked

All three conditions must be met before running A2.6 (legacy removal):

| Condition | Measurement | Target |
|-----------|-------------|--------|
| **Consecutive days running** | scheduler `run_count` ≥ 7, `error_count` = 0 | 7 days clean |
| **Memory coverage** | `SELECT COUNT(*) FROM arc2_lead_memories WHERE last_writer = 'extract_deep_nightly' AND memory_type IN ('objection','interest','relationship_state')` | ≥ 50 memories |
| **Dual-write drift** | Run `python3 scripts/dual_write_diff_report.py` | < 5% gap |

Once all three are satisfied, proceed with A2.6 per the runbook in `ARC2_migration_runbook.md`.

---

## 7. Debugging common issues

### Job registers but never runs

Check `initial_delay_seconds=720` — the job fires 12 min after app start. If the app restarts frequently, it may not reach the job.

### "DATABASE_URL not configured" error

The standalone script requires `DATABASE_URL` env var. Set it via `railway run` or `.env`.

### LLM timeouts

OpenRouter has a 120s default timeout. The extractor prompt is ~1400 tokens — should respond in < 5s. If timeouts spike:
1. Check OpenRouter status
2. Reduce `--max-leads` to reduce job duration
3. The job will resume normally next night

### Memories not appearing

Check:
1. `ENABLE_NIGHTLY_EXTRACT_DEEP=true` is set
2. There are active leads in the last 48h: `SELECT COUNT(DISTINCT lead_id) FROM messages WHERE created_at > NOW() - INTERVAL '48 hours'`
3. `extract_deep` returns results: try `--dry-run` first, then a single creator run

---

## 8. Files

| File | Purpose |
|------|---------|
| `scripts/nightly_extract_deep.py` | Standalone CLI script + `run_nightly()` callable |
| `api/startup/handlers.py` | Scheduler registration (JOB N, ENABLE_NIGHTLY_EXTRACT_DEEP=false) |
| `tests/memory/test_nightly_extract_deep.py` | Unit tests (10 cases, 85%+ coverage) |
| `services/memory_extractor.py` | `extract_deep()` — the LLM function being called |
| `services/lead_memory_service.py` | `upsert()` — writes to arc2_lead_memories |
