# CLONNECT Repository Audit — Current State

## Date: 2026-02-25
## Branch: main (post all fixes and decompositions)

---

### Metrics

| Metric | Count |
|---|---|
| Python source files (excl tests, .venv) | 521 |
| Lines of Python code | 153,271 |
| API endpoints defined | 421 |
| Routers registered in main.py | 45 |
| Test files | 294 |
| Frontend files (TS/TSX) | 208 |
| Alembic migrations | 38 |

### Syntax

- **0 errors** out of 521 Python files checked
- All files parse cleanly via `ast.parse()`

### Import Safety

- **266 passed**, 2 failed (pre-existing)
- `api.core.auth` — stale reference in code (`api.core` doesn't exist, should be `core`)
- `core.multimodal` — module was never created (referenced but missing)

### Functional Audit (Production)

- **127/127 endpoint tests passed (100%)**
- **5/5 E2E flows passed (100%)**
- All tested against live production at `https://www.clonnectapp.com`

### Decomposition Status — All 20 Verified

All decomposed modules confirmed working as packages with `__init__.py` re-exports:

| Module | Type | Sub-modules |
|---|---|---|
| api/routers/admin | package | 17 sub-modules |
| api/routers/oauth | package | 6 sub-modules |
| api/routers/dm | package | 4 sub-modules |
| api/routers/nurturing | package | 3 sub-modules |
| api/routers/leads | package | 3 sub-modules |
| api/routers/instagram | package | 3 sub-modules |
| api/routers/ingestion_v2 | package | 4 sub-modules |
| api/routers/autolearning | package | 3 sub-modules |
| api/routers/copilot | package | 2 sub-modules |
| api/routers/messaging_webhooks | package | 4 sub-modules |
| api/startup | package | 2 sub-modules |
| api/services/db_service | re-export shim | 5 lines |
| core/payments | package | 2 sub-modules |
| core/calendar | package | 2 sub-modules |
| core/gdpr | package | 2 sub-modules |
| core/whatsapp | package | 3 sub-modules |
| core/context_detector | package | 3 sub-modules |
| core/nurturing | package | 3 sub-modules |
| core/prompt_builder | package | 3 sub-modules |
| core/message_reconciliation | package | 4 sub-modules |

### Monolith Status (Files >800 Lines)

14 files remain over 800 lines:

| Lines | File | Justification |
|---|---|---|
| 2,984 | core/dm_agent_v2.py | Deferred — most critical module, needs tests first (see TODO_DM_DECOMPOSITION.md) |
| 1,902 | core/instagram_handler.py | Single cohesive handler class |
| 1,520 | core/copilot_service.py | Single cohesive service class |
| 1,394 | api/routers/admin/sync_dm.py | Complex DM sync logic, tightly coupled |
| 1,362 | api/routers/oauth/instagram.py | Instagram OAuth flow, sequential |
| 1,196 | services/memory_engine.py | Single cohesive MemoryEngine class (SKIPPED) |
| 1,176 | api/routers/copilot/analytics.py | Single router, many related endpoints |
| 1,098 | core/payments/manager.py | Post-decomposition manager (was 1,400+) |
| 1,020 | services/clone_score_engine.py | Single cohesive CloneScoreEngine (SKIPPED) |
| 981 | api/startup/handlers.py | Nested closures sharing scope |
| 969 | core/calendar/manager.py | Post-decomposition manager (was 1,300+) |
| 873 | core/personality_extraction/bot_configurator.py | 5-phase pipeline |
| 860 | core/auto_configurator.py | Single cohesive 5-phase pipeline (SKIPPED) |
| 832 | services/whatsapp_onboarding_pipeline.py | Single cohesive 5-phase pipeline (SKIPPED) |

### Auth Coverage

| Category | Count | Details |
|---|---|---|
| **Fully protected** | 30 routers | All admin/*, leads/*, nurturing/*, copilot/*, calendar, config, products, clone_score, memory |
| **Partially protected** | 3 routers | admin/tokens (5 unprotected), creator (3 unprotected), onboarding/pipeline (7 unprotected) |
| **Intentionally public** | 16 routers | health, static, webhooks, oauth callbacks, booking (public), preview |
| **No auth (needs review)** | 38 routers | See details below |

#### Partially Protected — Details

| Router | Unprotected Endpoints | Risk |
|---|---|---|
| admin/tokens | 5/8 — refresh_all_tokens, refresh_token, exchange_token, set_token, set_page_token, fix_instagram_ids | **HIGH** — token operations should require admin |
| creator | 3/4 — POST config, GET list, DELETE reset | **MEDIUM** — creator management |
| onboarding/pipeline | 7/9 — magic-slice, whatsapp trigger, full-setup | **LOW** — onboarding flows typically pre-auth |

#### Unprotected Routers — Risk Assessment

| Risk | Routers | Rationale |
|---|---|---|
| **Should be protected** | dm/conversations (10), dm/processing (3), dm/followers (2), dm/debug (2) | DM data is sensitive |
| **Should be protected** | connections (8), content (12), maintenance (15) | Modification capabilities |
| **Low risk / read-only** | dashboard (2), analytics (4), intelligence (6), insights (3), audience (4), audiencia (8), metrics (2), knowledge (9), citations (5), tone (7), events (1) | Read-only creator data |
| **Functional / internal** | bot (3), audio (1), debug (8), messages (5), telegram (12), ingestion_v2 (10), autolearning (11), onboarding/* (11), unified_leads (4), payments (5), gdpr (7) | Mixed — some need auth |

### Dead Code

- **91 files** (>20 lines) are never imported by any other file
- Most are router sub-modules (imported via `__init__.py` `include_router()`, not direct import)
- Top candidates for actual dead code:
  - `ingestion/structured_extractor.py` (451 lines) — may be unused
  - `ingestion/content_store.py` (404 lines) — may be replaced by v2
  - Various alembic migration files (expected — run-once scripts)

### Vulnerabilities

| Category | Count | Severity | Details |
|---|---|---|---|
| Hardcoded secrets | **0** | — | All `Bearer` tokens are from variables/env, not hardcoded |
| SQL injection in production code | **0** | — | f-strings in SQL only found in scripts/ (not served) |
| Admin endpoints without auth | **8** | **HIGH** | admin/tokens.py (7 endpoints), admin/leads.py configure_ghost (1) |
| Raw exception exposure (`detail=str(e)`) | **10+** | **MEDIUM** | unified_leads, payments, config, maintenance — leaks internal errors |

### Overall Assessment

The Clonnect backend is in good structural health after 22 monolith decompositions and 3 endpoint fixes. All 521 Python files pass syntax checks, all 127 production endpoints return valid responses (100%), and all 20 decomposed modules maintain backward compatibility through re-export packages. The primary areas needing attention are: **(1)** 8 admin token endpoints missing auth protection (HIGH priority), **(2)** 38 routers with no authentication that should be reviewed for sensitive data exposure, **(3)** 10+ endpoints leaking raw exception details via `detail=str(e)`, and **(4)** the `dm_agent_v2.py` monolith (2,984 lines) which remains the largest file and is deferred pending test coverage. The 2 pre-existing import safety failures (`api.core.auth` and `core.multimodal`) are stale references that should be cleaned up.
