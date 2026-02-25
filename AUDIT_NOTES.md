# Clonnect — Notes for Technical Review

## Recent Cleanup (February 2026)

### Security Fixes Applied
- All admin endpoints now require `CLONNECT_ADMIN_KEY` via `require_admin` dependency
- Demo user password moved from hardcoded to environment variable
- Obsolete Railway URL removed from CORS origins

### Code Organization
- Non-essential files (audits, reports, legacy code, data, screenshots) moved to `_archive/`
- 4 legacy DM agent versions archived (only `dm_agent_v2.py` active)
- Deprecated LLM provider (DeepInfra) archived
- Dead router (`dm_orchestrated`) removed from app
- Scout model references cleaned up

### Known Items for Review
1. **models.py (1,647 lines)** — 53 SQLAlchemy models in a single file. Works but should be split by domain for maintainability.
2. **instagram_handler.py (3,154 lines)** — Largest file in the codebase. Decomposition candidate.
3. **14 feature flags disabled** — Built but not activated. Some may never be needed. Review which to keep vs deprecate.
4. **Test coverage unknown** — 293 test files exist (~56K lines) but no coverage measurement configured.
5. **Single Uvicorn worker** — Sufficient for current load but needs scaling plan for 10+ creators.
6. **No penetration test** — Security audit not performed beyond code review.

### Architecture Decisions (Intentional)
- **Monolith**: Single service on Railway. Deliberate choice for solo developer.
- **JSON + DB dual storage**: PostgreSQL primary, JSON fallback for resilience. By design.
- **In-memory webhook dedup**: Speed optimization, backed by DB UniqueConstraint.
- **65 feature flags**: Gradual rollout mechanism. Some are permanent, some experimental.

### Active LLM Stack
- Primary: Gemini 2.5 Flash-Lite (`gemini_provider.py`)
- Fallback: GPT-4o-mini (via `llm_service.py`)
- Embeddings: OpenAI text-embedding-3-small (1536d, pgvector)
- Deprecated: DeepInfra, Scout, Together, Groq (all archived)

## Scaling Plan (When Needed)

### Current State (Feb 2026)
- Single Uvicorn worker on Railway
- Sufficient for 1-5 creators with moderate DM volume
- Background tasks run in-process via asyncio

### Phase 1: 5-20 Creators
- Increase to 2-4 Uvicorn workers: `uvicorn api.main:app --workers 4`
- Move background tasks to separate Railway service (worker process)
- Add Redis for shared state (rate limiters, circuit breakers, webhook dedup)
- Estimated cost: +$10-20/month (Redis) + worker service

### Phase 2: 20-100 Creators
- Dedicated worker service with Celery or ARQ for background jobs
- Read replicas for PostgreSQL
- CDN for media (already using Cloudinary)
- Consider splitting webhook ingestion into separate service
- Estimated cost: +$50-100/month

### Phase 3: 100+ Creators
- Kubernetes or Railway multi-service architecture
- Separate services: API, webhook ingestion, background workers, LLM proxy
- Connection pooling with PgBouncer
- Horizontal scaling of API pods
- Full observability stack (Prometheus + Grafana or Datadog)

### Triggers to Scale
- P95 response time > 3 seconds → add workers
- Memory usage > 80% → add workers or optimize caches
- DB connection pool exhaustion → add PgBouncer
- Background task queue backing up → separate worker service

## Security — Penetration Testing

### Not Yet Performed
A professional penetration test has not been conducted. The following has been done:
- Code-level security review (admin auth, prompt injection, CORS, secrets)
- All admin endpoints require CLONNECT_ADMIN_KEY
- JWT auth for user endpoints
- Rate limiting on API and webhooks
- No hardcoded secrets in codebase

### Recommended Before Public Launch
1. OWASP Top 10 assessment
2. Instagram OAuth flow security review
3. Webhook signature validation (Stripe, Hotmart)
4. API fuzzing with authenticated and unauthenticated requests
5. SQL injection testing (parameterized queries used throughout, but verify)

### Tools to Consider
- OWASP ZAP (free, automated scanning)
- Burp Suite (comprehensive manual testing)
- SQLMap (SQL injection verification)
