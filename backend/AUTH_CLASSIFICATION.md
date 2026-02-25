# Auth Classification: Routers Without Auth Middleware

All 38 routers confirmed to have no FastAPI `Depends()` auth middleware as of 2026-02-25.

---

## Category 1 — Intentionally Public

These endpoints must remain unauthenticated. They are called by external platforms (Meta, Stripe, Google, etc.), browser redirect flows, or infrastructure tooling (k8s, Prometheus). Adding auth would break them.

| Router File | Prefix | Reason |
|---|---|---|
| `api/routers/health.py` | `/health` | k8s liveness/readiness probes and monitoring must be reachable without credentials |
| `api/routers/static.py` | `/`, `/api`, `/privacy`, `/terms`, `/metrics` | Frontend HTML, legal pages, and Prometheus scrape endpoint — public by definition |
| `api/routers/instagram/webhook.py` | `/webhook` | Meta sends GET (hub.challenge verify_token) + POST (X-Hub-Signature-256) — must be reachable without bearer token |
| `api/routers/messaging_webhooks/__init__.py` | `/instagram`, `/whatsapp`, `/telegram`, `/evolution` | Platform-signed payloads from Meta, Twilio, Telegram Bot API, Evolution — signature is the auth mechanism |
| `api/routers/webhooks.py` | `/webhooks` | Stripe (Stripe-Signature), Hotmart (X-Hotmart-Hottok), PayPal, Calendly, Cal.com (X-Cal-Signature-256) — all use platform HMAC signatures |
| `api/routers/oauth/google.py` | `/oauth/google` | OAuth 2.0 start and callback redirect flow — browser must reach these without a token |
| `api/routers/oauth/instagram.py` | `/oauth/instagram`, `/oauth/meta` | Meta OAuth start and callback — same reason |
| `api/routers/booking.py` (public sub-routes only) | `/{creator_id}/public/{service_id}`, `/{creator_id}/public/{service_id}/available-dates`, `/{creator_id}/reserve` | Follower-facing public booking page and reservation — explicitly designed for unauthenticated followers |

---

## Category 2 — Creator-Facing (require_creator_access)

These endpoints are scoped to a specific `{creator_id}` and return or mutate that creator's private data. They should be protected with `require_creator_access`.

NOTE: Auth not added yet to avoid breaking frontend. Add `# TODO: add auth` comments to each endpoint.

| Router File | Prefix | What It Exposes |
|---|---|---|
| `api/routers/analytics.py` | `/analytics` | Sales stats and activity log per creator |
| `api/routers/audience.py` | `/audience` | Audience profiles, segment counts, aggregated follower metrics |
| `api/routers/audiencia.py` | `/audiencia` | "Tu Audiencia" tab data: topics, passions, frustrations, competition, trends, objections, perception |
| `api/routers/audio.py` | `/audio` | Whisper transcription for inbox audio messages |
| `api/routers/autolearning/analysis.py` | `/autolearning` | Trigger rule consolidation and pattern analysis per creator |
| `api/routers/autolearning/dashboard.py` | `/autolearning` | Gamified dashboard: XP, skills, achievements, gold examples, preference profile |
| `api/routers/autolearning/rules.py` | `/autolearning` | List, deactivate, and reactivate learning rules |
| `api/routers/booking.py` (creator sub-routes) | `/{creator_id}/availability`, `/{creator_id}/services`, `/{creator_id}/bookings` | Creator manages their own availability slots and services |
| `api/routers/citations.py` | `/citations` | Content citation index, search, and prompt generation |
| `api/routers/connections.py` | `/connections` | View and update integration credentials (Instagram token, Stripe key, etc.) — highly sensitive |
| `api/routers/dashboard.py` | `/dashboard` | Creator dashboard overview and bot pause/resume toggle |
| `api/routers/dm/conversations.py` | `/dm` | List, archive, mark-read, spam, delete, restore, reset, sync conversations |
| `api/routers/dm/debug.py` | `/dm` | DM message counts, DB diagnostics, and DM metrics per creator |
| `api/routers/dm/followers.py` | `/dm` | Follower detail with message history, update lead status |
| `api/routers/events.py` | `/events` | SSE real-time updates stream — already has inline `_verify_token_for_creator()` JWT check; needs middleware alignment |
| `api/routers/gdpr.py` | `/gdpr` | GDPR export, delete, anonymize, consent management, audit log per follower |
| `api/routers/insights.py` | `/insights` | Today's mission (hot leads, revenue), weekly insights, weekly metrics |
| `api/routers/instagram/icebreakers.py` | `/instagram` | Set/get/delete Instagram ice breaker quick-replies |
| `api/routers/instagram/menu.py` | `/instagram` | Set persistent menu, connect Instagram page, status |
| `api/routers/intelligence.py` | `/intelligence` | Business intelligence dashboard, predictions, recommendations, weekly report |
| `api/routers/knowledge.py` | `/creator/config` | FAQ CRUD and About Me knowledge base |
| `api/routers/messages.py` | `/dm` | Metrics, follower detail, send message, update status, conversation list |
| `api/routers/metrics.py` | `/metrics` | Bot performance metrics dashboard and health score |
| `api/routers/onboarding/clone.py` | `/onboarding` | Wizard onboarding: profile setup, products, bot configuration |
| `api/routers/onboarding/dm_sync.py` | `/onboarding` | Instagram DM history sync |
| `api/routers/onboarding/progress.py` | `/onboarding` | Onboarding checklist and progress tracking |
| `api/routers/payments.py` | `/payments` | Revenue stats, purchase list, customer history, attribute sale |
| `api/routers/preview.py` | `/preview` | Link preview / screenshot service (used in DM inbox UI) |
| `api/routers/tone.py` | `/tone` | ToneProfile CRUD, generate, prompt, refresh, dialect update |
| `api/routers/unified_leads.py` | `/leads` | List, get, merge, and unmerge unified leads |

---

## Category 3 — Admin-Only (require_admin)

These endpoints expose system internals, trigger batch operations, or manage infrastructure. They should be protected with `require_admin` (or equivalent).

NOTE: Auth not added yet to avoid breaking frontend. Add `# TODO: add auth` comments to each endpoint.

| Router File | Prefix | Why Admin-Only |
|---|---|---|
| `api/routers/content.py` | `/content` | RAG content add/search/reload/debug/bulk-load/clear/setup-pgvector/generate-embeddings — system-level pipeline control |
| `api/routers/debug.py` | `/debug` | Full system diagnostics: DB tables, creator data, env vars, system-prompt, agent-config — exposes raw system internals |
| `api/routers/maintenance.py` | `/maintenance` | Profile pic refresh, score recalculation, batch embed conversations, backfill personality, style analysis, echo engine — all batch system operations |
| `api/routers/ingestion_v2/debug.py` | `/ingestion` | Scraper step-by-step diagnostics and full content refresh trigger |
| `api/routers/ingestion_v2/instagram_ingest.py` | `/ingestion` | Trigger Instagram content ingestion pipeline |
| `api/routers/ingestion_v2/website.py` | `/ingestion` | Trigger website ingestion pipeline, preview, and verify |
| `api/routers/ingestion_v2/youtube.py` | `/ingestion` | Trigger YouTube ingestion pipeline |
| `api/routers/telegram.py` | `/telegram` | Register/unregister bots, fix webhooks, reload, diagnose, list all bots, test-message — bot infrastructure management |
| `api/routers/instagram/menu.py` (admin sub-routes) | `/instagram` | `list-creators` and `clear-cache` endpoints are admin-adjacent operations |

---

## Category 4 — Internal / Machine-to-Machine (API key header)

These endpoints are called by internal services, platform webhooks routing layer, or automated jobs — not by the browser frontend. They should require a shared internal API key passed in a header (e.g. `X-Internal-Key`).

NOTE: Auth not added yet to avoid breaking frontend. Add `# TODO: add auth` comments to each endpoint.

| Router File | Prefix | Caller |
|---|---|---|
| `api/routers/dm/processing.py` | `/dm` | `process_dm` is called by the webhook routing layer after signature verification; `send_manual_message` and `send_media_message` are triggered by the agent/job pipeline |
| `api/routers/bot.py` | `/bot` | Already has inline `require_creator_or_admin()` call per endpoint (not middleware `Depends()`); needs alignment to standard middleware pattern |

---

## Category 5 — Already Protected

These routers already have proper auth middleware via FastAPI `Depends()` and are listed here for completeness.

| Router File | Auth Mechanism |
|---|---|
| `api/routers/auth.py` | Public by design (login/register endpoints issue tokens) |
| Any router using `Depends(require_creator_access)` | Creator-scoped JWT validation |
| Any router using `Depends(require_admin)` | Admin API key validation |

---

## Summary Table

| Category | Count | Action Required |
|---|---|---|
| 1 — Intentionally Public | 8 router files (some split) | No change needed |
| 2 — Creator-Facing | 30 router files | Add `require_creator_access` dependency |
| 3 — Admin-Only | 9 router files | Add `require_admin` dependency |
| 4 — Internal / M2M | 2 router files | Add internal API key header validation |
| 5 — Already Protected | — | No change needed |

---

## Next Steps

1. Add `# TODO: add auth` comments to every endpoint in categories 2, 3, and 4.
2. Wire `Depends(require_creator_access)` into all category 2 routers.
3. Wire `Depends(require_admin)` into all category 3 routers.
4. Decide on internal API key strategy for category 4 and apply consistently.
5. For `bot.py` and `events.py`: refactor inline auth checks to use the standard `Depends()` middleware pattern.
6. For `booking.py`: split the router into a public sub-router (no auth) and a protected sub-router (creator auth) to avoid a mixed-auth file.
