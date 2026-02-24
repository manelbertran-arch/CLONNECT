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
