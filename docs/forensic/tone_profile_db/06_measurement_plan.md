# Phase 6 — Measurement plan (Test coverage + BC + Migration integrity)

> Branch: `forensic/tone-profile-db-20260423`
> Type: **NOT CCEE** — structural refactor of the data layer. `tone_profile_db` is not an ablation unit (confirmed scout). Measurement is test coverage + backward-compat + migration smoke.

---

## A. Measurement type

- ✅ Test coverage per repo (unit + integration-mock).
- ✅ Backward-compat verification (AST diff + signature parity + 9 importer boot).
- ✅ Migration integrity (golden master invariants I1–I11 preserved).
- ❌ CCEE — not applicable (no ablatable flag, no DM-response-quality impact).
- ❌ Load testing / stampede — deferred (DECISIONS.md, single-worker invariant).
- ❌ Prometheus metrics — deferred (DECISIONS.md, non-BC follow-up).

---

## B. Harness

### B.1 Unit / integration (pytest, mock DB)

```bash
# New repo tests (target: 32 green)
python3 -m pytest tests/test_tone_profile_repo.py \
                  tests/test_content_chunks_repo.py \
                  tests/test_instagram_posts_repo.py \
                  -v --tb=short

# Adjacent regression check (must not be affected)
python3 -m pytest tests/test_tone_service.py \
                  tests/test_auto_configurator_audit.py \
                  tests/test_ingestion_v2_router_audit.py \
                  -q --tb=line
```

Baseline captured (2026-04-23, this worktree):
- Repo tests: **32 passed, 0 failed**
- Adjacent: **67 passed, 1 failed** — the 1 failure (`test_ingest_website_propagates_pipeline_error`, HTTP 503 vs 500) is **pre-existing** and reproduces on the untouched tree. Not a regression.

### B.2 Backward-compat (Python)

```bash
# All 9 productive importers must import cleanly
python3 - <<'EOF'
import importlib
for mod in [
    "core.tone_service", "core.auto_configurator",
    "ingestion.v2.instagram_ingestion", "ingestion.v2.youtube_ingestion",
    "services.feed_webhook_handler",
    "api.routers.ingestion_v2.instagram_ingest",
    "api.routers.ingestion_v2.youtube",
    "api.routers.onboarding.setup",
    "api.routers.admin.debug",
]:
    importlib.import_module(mod)
    print("OK", mod)
EOF

# 13 signatures identical (parameter-level, ignoring PEP-563 string annotations)
python3 - <<'EOF'
import inspect
from core.tone_profile_db import (
    save_tone_profile_db, get_tone_profile_db, get_tone_profile_db_sync,
    delete_tone_profile_db, list_profiles_db, clear_cache,
    save_content_chunks_db, get_content_chunks_db, delete_content_chunks_db,
    save_instagram_posts_db, get_instagram_posts_db,
    delete_instagram_posts_db, get_instagram_posts_count_db,
)
# (full assertion block as executed in Phase 5 — 13/13 must match)
EOF

# AST syntax check every touched file
for f in backend/core/tone_profile_db.py backend/core/data/*.py \
         backend/api/routers/admin/debug.py \
         backend/tests/test_{tone_profile,content_chunks,instagram_posts}_repo.py; do
  python3 -c "import ast; ast.parse(open('$f').read())" && echo "OK  $f"
done
```

### B.3 Staging smoke (post-merge, before prod)

```bash
# 1. Bootstrap — DMAgentV2 must initialise with a populated personality dict
railway run --environment=staging python3 - <<'EOF'
from core.dm.agent import DMResponderAgentV2
agent = DMResponderAgentV2("iris_bertran")
p = agent.personality
assert isinstance(p, dict) and p, "personality empty — bootstrap broken"
print("bootstrap OK — personality keys:", sorted(p.keys())[:5])
EOF

# 2. Ingestion v2 / Instagram — single post round-trip
railway run --environment=staging python3 - <<'EOF'
import asyncio
from core.data.instagram_posts_repo import (
    save_instagram_posts_db, get_instagram_posts_count_db,
)
async def go():
    n = await save_instagram_posts_db("iris_bertran", [{
        "id": "smoke_p1", "caption": "smoke #test @bot",
        "timestamp": "2026-04-23T12:00:00Z",
    }])
    count_after = get_instagram_posts_count_db("iris_bertran")
    print("save ok:", n, "count:", count_after)
asyncio.run(go())
EOF

# 3. Ingestion v2 / YouTube — chunk round-trip
railway run --environment=staging python3 - <<'EOF'
import asyncio
from core.data.content_chunks_repo import save_content_chunks_db, get_content_chunks_db
async def go():
    n = await save_content_chunks_db("iris_bertran", [{
        "id": "smoke_c1", "content": "yt smoke", "source_type": "youtube",
    }])
    rows = await get_content_chunks_db("iris_bertran")
    print("save ok:", n, "reloaded rows:", len(rows))
asyncio.run(go())
EOF

# 4. Admin/debug — new public accessor must populate the panel
curl -s -H "X-API-Key: $ADMIN_KEY" https://staging.clonnectapp.com/admin/debug/memory \
  | python3 -c "import sys,json; d=json.load(sys.stdin); \
    tc=d.get('caches',{}).get('tone_cache',{}); \
    assert isinstance(tc, dict) and 'size' in tc and 'max_size' in tc and 'ttl_seconds' in tc, tc; \
    print('admin tone_cache stats OK:', tc)"
```

---

## C. Gates KEEP (ALL must hold)

| # | Gate | Evidence needed | Baseline captured |
|---|---|---|---|
| K1 | 32/32 repo tests pass | pytest short summary `32 passed` | ✅ (2026-04-23, this branch) |
| K2 | 67/67 adjacent tests pass (excluding the 1 pre-existing website-route failure) | pytest short summary | ✅ (confirmed pre-existing via `git stash`) |
| K3 | 9/9 productive importers import cleanly | import loop OK, no ImportError | ✅ |
| K4 | 13/13 signature parameter lists identical pre/post refactor | Parameter-level diff script | ✅ |
| K5 | Cache instance identity preserved (no split-brain) | `legacy_tone_cache is new_tone_cache` | ✅ |
| K6 | Zero regression in adjacent suites | Delta test-pass count unchanged | ✅ |
| K7 | Golden master invariants I1–I11 preserved | Outputs match `golden_master_baseline.txt` | ✅ (baseline itself is the reference) |
| K8 | Staging smoke — DMAgentV2 bootstrap populates personality | Step F.10 output | ⏳ (post-merge) |
| K9 | Staging smoke — Instagram ingestion round-trip | Step F.11 output | ⏳ (post-merge) |
| K10 | Staging smoke — YouTube chunk round-trip | Step F.11 output | ⏳ (post-merge) |
| K11 | Staging smoke — `get_tone_cache_stats()` returns dict with `size/max_size/ttl_seconds` | Step F.12 output | ⏳ (post-merge) |
| K12 | Staging 1 h post-deploy: zero `ImportError` / `AttributeError` / `TypeError` referencing `tone_profile_db` or `core.data` | Railway logs grep | ⏳ (post-merge) |
| K13 | Prod 24 h post-deploy: zero errors + no regression in bootstrap latency | Railway logs + Grafana bootstrap panel | ⏳ (post-merge) |

**K1–K7 already green** in this worktree. K8–K13 only observable after merge to `main`; rehearsal on staging is mandatory before prod.

---

## D. Gates REVERT (ANY triggers rollback)

| # | Revert trigger | Detection | Action |
|---|---|---|---|
| R1 | Any of the 9 importers fails to import post-merge | `ImportError` in Railway startup log within 60 s of deploy | `git revert <merge-sha>` + push immediately |
| R2 | `DMResponderAgentV2` bootstrap raises or returns empty personality | Staging smoke step F.10 fails, OR prod error rate on `/dm/*` spikes | Revert merge |
| R3 | Ingestion v2 (IG or YT) fails to persist | Staging smoke steps F.11 fail, OR feed-webhook 5xx in prod logs | Revert merge |
| R4 | AST signature drift against baseline | CI parameter-diff script fails | Do not merge until reconciled |
| R5 | Repo tests < 32 pass OR adjacent suite regresses | `pytest` non-zero exit beyond the known pre-existing failure | Block merge |
| R6 | `get_tone_cache_stats()` missing from admin/debug response | Step F.12 curl check fails | Revert merge + fix accessor |
| R7 | Any `TypeError: 'BoundedTTLCache' object is not subscriptable` reappears | Railway log grep | Revert — B-01 regression |

---

## E. Pre-merge sequence (local worktree → PR)

```
  STEP    ACTION                                                        STATUS (baseline)
 ──────  ─────────────────────────────────────────────────────────────  ─────────────────
  1      Capture golden master baseline (11 invariants I1–I11).         ✅ done Phase 5
  2      pytest tests/test_tone_profile_repo.py -v                      ✅ 13 passed
  3      pytest tests/test_content_chunks_repo.py -v                    ✅  9 passed
  4      pytest tests/test_instagram_posts_repo.py -v                   ✅ 10 passed
  5      pytest tests/test_tone_service.py tests/test_auto_…audit.py    ✅ 67 passed,
           tests/test_ingestion_v2_router_audit.py                         1 pre-existing fail
  6      Run AST + signature + BC-import scripts (section B.2)          ✅ all green
  7      git add / git commit -m "refactor(data): split …"              ⏳ Phase 5→6 hand-off
  8      git push origin forensic/tone-profile-db-20260423              ⏳ Phase 7
  9      gh pr create --base main --draft (NO merge)                    ⏳ Phase 7
```

**Do not merge** until the PR review loop completes. Per constraint, no merge in this branch.

---

## F. Post-merge sequence (staging → prod)

```
  STEP  ACTION                                                          OWNER     GATE
 ───── ─────────────────────────────────────────────────────────────── ────────  ─────
  10   Merge PR on GitHub (main).                                        CEO     —
  11   Railway auto-deploys to prod (single env today — see §F.note).    Railway —
  12   Within 60 s: tail `railway logs -n 200 | grep -Ei \
         "ImportError|AttributeError|TypeError|tone_profile_db"`.        Eng    K12
  13   Run B.3 smoke 1 (DMAgentV2 bootstrap).                            Eng    K8
  14   Run B.3 smoke 2 (Instagram post round-trip).                      Eng    K9
  15   Run B.3 smoke 3 (YouTube chunk round-trip).                       Eng    K10
  16   Run B.3 smoke 4 (admin/debug tone_cache panel).                   Eng    K11
  17   Monitor 1 h: any R1–R7 → immediate revert (§G rollback).          Eng    K12
  18   Monitor 24 h: Grafana bootstrap latency panel flat ±5 %.          Eng    K13
```

### F.note — Staging caveat

Clonnect today runs a **single Railway environment** (prod). The task constraint "**NO modificar Railway**" combined with "NO mergear" means steps 11–18 are **not executed in this branch**. They are rehearsed here so that when the CEO decides to merge (post-review), the team has the script.

If a `staging` environment is stood up before merge, substitute `--environment=staging` in the Railway smoke commands and run steps 12–17 against staging first; only proceed to prod after K8–K12 are all green in staging.

---

## G. Observability & rollback procedure

### G.1 Log patterns to watch (first 1 h, then 24 h)

```bash
# Deploy-window errors
railway logs -n 500 2>&1 | grep -Ei "ImportError.*(tone_profile_db|core\.data)"
railway logs -n 500 2>&1 | grep -Ei "AttributeError.*_tone_cache"
railway logs -n 500 2>&1 | grep -Ei "TypeError.*BoundedTTLCache"   # B-01 regression signature

# Silent-degradation patterns
railway logs -n 500 2>&1 | grep -Ei "Error (loading|saving) ToneProfile"
railway logs -n 500 2>&1 | grep -Ei "Error (loading|saving) content chunks"
railway logs -n 500 2>&1 | grep -Ei "Error (loading|saving) Instagram posts"
```

DeprecationWarnings from the shim are NOT rollback triggers — they are informational, used to prioritise Q2 migration of the 9 importers off the shim.

### G.2 Rollback procedure (explicit)

```bash
# 1. Identify the merge commit
git log --oneline --merges main | head -1
# expected form: <SHA>  Merge pull request #NNN from forensic/tone-profile-db-20260423

# 2. Revert (creates a new commit on main that undoes the merge)
git checkout main && git pull
git revert -m 1 <merge-sha> --no-edit
git push origin main

# 3. Railway redeploys automatically on push; verify the shim file is gone
#    and the original 540-LOC file is restored
railway run python3 -c "import core.tone_profile_db, os; \
  print(os.path.getsize(core.tone_profile_db.__file__))"
# expected: close to pre-refactor size (~18 KB), not the 1.8 KB shim

# 4. Confirm the reverted prod is healthy
curl -s https://www.clonnectapp.com/health
railway logs -n 200 2>&1 | grep -Ei "error|traceback" | head -10

# 5. Re-open the PR with the specific failure noted; fix forward, never re-merge
#    the same SHA.
```

**Time budget:** detection ≤ 60 s post-deploy; revert push ≤ 5 min; Railway redeploy ≤ 3 min; back-to-green ≤ 10 min total.

### G.3 Non-rollback signals

- `DeprecationWarning` emitted from shim access → log, collect, migrate in Q2 (scheduling doc, not this PR).
- Pre-existing `test_ingest_website_propagates_pipeline_error` failure → documented in golden master baseline; ignore unless its failure mode changes.

---

## H. Inventory reclassification after KEEP

Applied as soon as all KEEP gates close (not before).

| Bucket | Before this PR | After this PR | Delta |
|---|---|---|---|
| Pipeline-DM, no-optimized-ON | 49 (incl. "Tone Profile DB" as a single entity, 3 domains glued) | 49 (incl. "tone_profile_repo" — tracks only Domain A) | **0** (internal cleanup) |
| Data / Ingestion layer | N | N + 2 (`content_chunks_repo`, `instagram_posts_repo`) | **+2** |
| Deprecated entities | 0 | 1 (`tone_profile_db.py` shim — scheduled for removal once 9 importers migrate) | +1 |

**Clarifications:**

1. `tone_profile_repo` stays in the pipeline-DM inventory because it is read at `DMResponderAgentV2.__init__` to build Doc D. It does **NOT** move to "optimized ON" in this PR — no CCEE metric exists to certify optimisation. That is a separate, future initiative.
2. `content_chunks_repo` and `instagram_posts_repo` are pure ingestion/batch. They leave the DM inventory; they are tracked in the Data/Ingestion layer with their own ownership.
3. The legacy entity "Tone Profile DB" is **dissolved** as a single-unit inventory row and replaced by the three domain-scoped entities.
4. The shim `core/tone_profile_db.py` is an inventory row too, but tagged "deprecated, zero-LOC behavioural content, remove once callers migrate". Not counted in pipeline-DM.

---

## I. Go / no-go checklists

### I.1 Go / no-go — staging (pre-prod rehearsal)

- [ ] K1 — 32/32 repo tests pass in CI
- [ ] K2 — 67/67 adjacent tests pass (excluding known pre-existing failure)
- [ ] K3 — 9/9 importers boot
- [ ] K4 — 13/13 signature diff green
- [ ] K5 — Cache instance identity preserved (`is` check)
- [ ] K7 — Golden master invariants I1–I11 preserved
- [ ] K8 — `DMResponderAgentV2("iris_bertran").personality` non-empty dict
- [ ] K9 — Instagram post save returns expected count, row visible via `get_instagram_posts_count_db`
- [ ] K10 — Content chunk save returns expected count, row visible via `get_content_chunks_db`
- [ ] K11 — Admin endpoint `caches.tone_cache` dict has `size`, `max_size`, `ttl_seconds`
- [ ] K12 — 1 h post-deploy, zero matches of R1/R2/R3/R7 log patterns

**ALL boxes checked → go to prod.** Any unchecked → investigate and do not promote.

### I.2 Go / no-go — prod (post-staging)

- [ ] All staging boxes above checked
- [ ] Bootstrap latency (p50/p95/p99) within ±5 % of pre-deploy baseline — Grafana panel
- [ ] DM response 5xx rate unchanged — Grafana `/dm/*` panel
- [ ] Feed-webhook ingestion 5xx rate unchanged — Grafana `/webhook/instagram` panel
- [ ] Admin/debug endpoint responds 200 with new `tone_cache` panel populated
- [ ] K13 — 24 h post-deploy, no new error categories in `railway logs` for `tone_profile`/`content_chunks`/`instagram_posts`
- [ ] PR comments addressed (code review + any reviewer-requested smoke steps)

**ALL boxes checked → close PR as merged and update inventory (§H).**

---

## J. Explicit out-of-scope (re-stated)

- **CCEE** — not an ablation unit. No S1–S6 axes change.
- **Load testing / stampede** — single-worker invariant; documented DECISIONS entry `2026-04-23 — Tone cache stampede protection`.
- **Prometheus metrics** — documented DECISIONS entry `2026-04-23 — Prometheus metrics for new repos`.
- **SQLAlchemy 2.x imperative migration** — separate initiative.
- **Migrating the 9 importers off the shim** — Q2 follow-up, not this PR.

---

## STOP — End of Phase 6.
