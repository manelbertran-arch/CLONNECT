# Clonnect — AI Clone Platform for Content Creators

## 4-Phase Development Workflow (MANDATORY)

YOU MUST follow all 4 phases for every non-trivial change. YOU MUST NOT push if smoke tests fail.

### Phase 1: PLAN
- Use the planner agent (`.claude/agents/planner.md`)
- Identify affected files, dependencies, and blast radius
- Log decisions in `DECISIONS.md`

### Phase 2: IMPLEMENT
- Use the tdd-guide agent (`.claude/agents/tdd-guide.md`)
- Write/update tests before or alongside implementation
- Syntax-check every modified `.py` file: `python3 -c "import ast; ast.parse(open('FILE').read())"`

### Phase 3: REVIEW
- Use the code-reviewer agent (`.claude/agents/code-reviewer.md`)
- Use the python-reviewer agent (`.claude/agents/python-reviewer.md`) for Python files
- Check for regressions against existing patterns

### Phase 4: VERIFY
- Run smoke tests: `python3 tests/smoke_test_endpoints.py`
- All tests MUST pass before commit/push
- If any test fails, fix the issue and re-run before proceeding

## Stack
FastAPI + uvicorn, PostgreSQL (Neon + pgbouncer), pgvector, SQLAlchemy, Python 3.11
Deploy: Railway (auto-deploy on push to `main`). Procfile: `alembic upgrade head && uvicorn ...`
Frontend: separate repo. Backend entry: `api/main.py`

## Critical Rules

IMPORTANT: `creator_id` is a **slug** (e.g. `"iris_bertran"`), NOT a UUID. The DB column `creator_id` in `leads`/`messages` IS a UUID — use `Creator.name` to resolve.

IMPORTANT: Two OAuth flows coexist. IGAAT tokens use `graph.instagram.com`. EAA tokens use `graph.facebook.com`. Never mix them. Check token prefix: `IGAAT*` vs `EAA*`.

YOU MUST NOT change these values without explicit user approval:
- `pool_size`, `max_overflow` in `api/database.py` (currently 5+7=12)
- `DEBOUNCE_SECONDS` in `core/copilot/models.py` (currently 15s)
- `batch_size` or `sleep` in `services/lead_scoring.py`
- Rate limits or timeouts in `core/providers/gemini_provider.py`
- Any `connect_args` in `api/database.py` — pgbouncer rejects unsupported params

YOU MUST NOT modify OAuth token handling (`api/routers/oauth/instagram.py`), webhook signature verification (`core/instagram_modules/webhook.py`), or scheduler timing (`core/task_scheduler.py`) without understanding the full flow first. Read before changing.

IMPORTANT: Do NOT compress, summarize, reorder by importance, or rewrite identity-defining signals (Doc D persona, creator few-shots, mined style patterns, vocabulary profiles) while the model is not fine-tuned on creator data. Two independent experiments showed identical failure mode: Sprint 2 importance scoring of history messages removed style examples → S1 Style Fidelity -10.9; Sprint 5 Doc D distillation (70% compression) → H Turing -10.0, S4 Adaptation -6.8. Root cause: base models treat identity signals as literal in-context information — lossy compression destroys subtleties the model cannot reconstruct without fine-tuning. Exception: conversational history (transient context, not identity) may be compacted. Revisit post-fine-tuning. Reference: `docs/audit_sprint5/s5_off_components_decision_matrix.md`.

## Verification — Before Every Change

1. Read the file(s) you intend to modify FIRST
2. Check if the function is called from multiple places (`grep -rn "function_name"`)
3. Verify `python3 -c "import ast; ast.parse(open('file.py').read())"` passes for every modified file

## Verification — After Every Change

1. Syntax check all modified files (ast.parse)
2. If touching DB models: verify alembic chain (`alembic heads`)
3. If touching webhooks/OAuth: check Railway logs post-deploy for errors
4. If touching scoring/scheduler: monitor `railway logs -n 200` for pool exhaustion

## Never Modify Without Authorization

- `api/database.py` — pool config, connect_args, sslmode
- `Procfile` — deploy command
- `alembic/env.py` — migration config
- Any `*_APP_SECRET`, `*_APP_ID` env var references
- `BLOCKED_MODELS` list in `core/config/llm_models.py`

## Conventions

- Lead `platform_user_id`: raw numeric ID, NO `ig_` prefix. Always check both formats when querying.
- All lead creation paths MUST fetch profile (username, profile_pic) from Instagram API.
- Webhook handlers: never swallow errors silently. Use `JSONResponse(4xx)` not `HTTPException` inside `try/except`.
- Background jobs: always use `asyncio.to_thread()` for sync DB operations in async context.
- Scoring batch: runs at t+210s after deploy, uses paged queries with sleep between batches.
- CDN URLs (scontent.cdninstagram.com) expire in 24h — upload to Cloudinary for permanent storage.

## Quick Commands
```bash
python3 -m pytest tests/ -x -q                    # Unit tests
curl -s https://www.clonnectapp.com/health         # Health check
railway logs -n 200 2>&1 | grep -v "SCORING-V3"   # Logs (filter noise)
```
