# CLONNECT INFRASTRUCTURE MAP

**Generated**: 2026-03-15
**Environment**: Production (Railway)
**Domain**: api.clonnectapp.com / www.clonnectapp.com

---

## HOSTING & COMPUTE

### 1. Railway (Application Hosting)
- **What**: FastAPI backend + Evolution API (WhatsApp)
- **Plan**: Pro ($5/month base + usage)
- **Services**: 2 (backend, Evolution API)
- **Volume**: 1 (persistent storage for media/logs)
- **Domain**: api.clonnectapp.com (custom domain)
- **Auto-deploy**: Push to `main` → automatic deploy
- **Env vars**: `RAILWAY_*` (auto-injected)
- **Cost**: ~$10-15/month (compute + bandwidth)
- **Status**: PAID

### 2. Neon (PostgreSQL Database)
- **What**: Serverless PostgreSQL with pgvector extension
- **Host**: `ep-raspy-truth-agjtq3o5-pooler.c-2.eu-central-1.aws.neon.tech`
- **Database**: `neondb`
- **Plan**: Scale (pay-as-you-go)
- **Features**: Scale-to-zero, connection pooling (PgBouncer), pgvector
- **Env var**: `DATABASE_URL`
- **Size**: 1.18 GB (after cleanup, was 2.57 GB)
- **Cost**: ~$19-25/month (storage + compute hours + data transfer)
- **Status**: PAID
- **Note**: Data transfer was 93 GB/14 days due to thumbnail_base64 bloat — now fixed

---

## LLM / AI PROVIDERS

### 3. Google AI (Gemini)
- **What**: PRIMARY LLM for DM responses + extraction + background tasks
- **Models used**: `gemini-2.0-flash-lite` (DM + extraction), `gemini-2.0-flash` (audio transcription)
- **API**: `https://generativelanguage.googleapis.com/v1beta/models`
- **Env var**: `GOOGLE_API_KEY`
- **Cost**: ~$2/month (245 msgs/day at current volume)
- **Status**: PAID (pay-per-token)
- **Critical**: Yes — primary DM generation engine

### 4. OpenAI
- **What**: Fallback LLM + embeddings + intent classification
- **Models used**: `gpt-4o-mini` (fallback DM, intent, judge), `text-embedding-3-small` (RAG)
- **Env var**: `OPENAI_API_KEY`
- **Cost**: ~$1/month (fallback + embeddings + intent classification)
- **Status**: PAID (pay-per-token)
- **Critical**: Yes — fallback when Gemini fails, embeddings for RAG

### 5. Groq
- **What**: Audio transcription (Whisper) — Tier 0, FREE
- **Models used**: `whisper-large-v3-turbo`
- **Env var**: `GROQ_API_KEY`
- **Cost**: $0 (free tier)
- **Status**: FREE TIER
- **Critical**: Low — only for audio messages (~5% of traffic)

### 6. Anthropic
- **What**: SDK installed but NOT actively used in production
- **Env var**: None configured in Railway
- **Cost**: $0
- **Status**: UNUSED (SDK in requirements.txt for LLMService compatibility)

### 7. xAI (Grok)
- **What**: AI assistant for dashboard "Copilot AI" feature
- **Models used**: `grok-beta`
- **API**: `https://api.x.ai/v1/chat/completions`
- **Env var**: `XAI_API_KEY`
- **Used in**: `api/routers/ai.py` (3 endpoints: rules generation, product extraction, general AI)
- **Cost**: ~$0-2/month (on-demand dashboard usage only)
- **Status**: PAID (pay-per-token)
- **Critical**: No — dashboard feature only, not in DM pipeline

### 8. DeepInfra
- **What**: Env vars configured but NO code usage found in production
- **Env var**: `DEEPINFRA_API_KEY`, `DEEPINFRA_TIMEOUT`, etc.
- **Cost**: $0 (not used)
- **Status**: UNUSED — can remove env vars

---

## MESSAGING PLATFORMS

### 9. Meta / Instagram Graph API
- **What**: Instagram DM webhook + message sending + profile data
- **APIs**: Graph API v21.0, Instagram Business Login, Facebook Login
- **Apps**: 2 Meta apps
  - Instagram Business Login: App ID `1394912658890530` (secret: `INSTAGRAM_APP_SECRET`)
  - Clonnect Bot (Facebook Login): App ID `892717189846426` (secret: `META_APP_SECRET`)
- **Env vars**: `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET`, `INSTAGRAM_PAGE_ID`, `IG_USER_ID`, `META_APP_ID`, `META_APP_SECRET`, `META_REDIRECT_URI`, `FACEBOOK_PAGE_ID`
- **Cost**: $0 (free API, requires approved app)
- **Status**: FREE
- **Critical**: YES — core messaging channel

### 10. Meta / WhatsApp Business API (via Evolution API)
- **What**: WhatsApp messaging via Evolution API (self-hosted on Railway)
- **Evolution API**: Self-hosted instance at `EVOLUTION_API_URL`
- **Meta WhatsApp app**: App ID `767210019781160`
- **Env vars**: `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_BUSINESS_ACCOUNT_ID`, `WHATSAPP_APP_SECRET`, `WHATSAPP_META_APP_ID`, `EVOLUTION_API_URL`, `EVOLUTION_API_KEY`
- **Cost**: ~$0-5/month (Evolution API on Railway, WhatsApp API free for business-initiated)
- **Status**: SELF-HOSTED (Evolution API) + FREE (Meta WhatsApp API)
- **Critical**: Yes — second messaging channel

### 11. Telegram Bot API
- **What**: Telegram messaging channel
- **Proxy**: Cloudflare Worker at `TELEGRAM_PROXY_URL` (*.workers.dev)
- **Env vars**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_PROXY_URL`, `TELEGRAM_WEBHOOK_SECRET`
- **Cost**: $0 (Telegram API free, Cloudflare Worker free tier)
- **Status**: FREE
- **Critical**: Medium — third messaging channel

---

## MEDIA & STORAGE

### 12. Cloudinary
- **What**: Image/video CDN and permanent storage for DM media
- **Env var**: `CLOUDINARY_URL` (contains cloud name, API key, secret)
- **Cloud name**: `dvekr3sut`
- **Used for**: Uploading Instagram CDN media before expiry, permanent_url storage
- **Cost**: Free tier (25 credits/month = ~25K transformations or 25 GB storage)
- **Status**: FREE TIER (may need upgrade at scale)
- **Critical**: Medium — media permanence for DM previews

### 13. Microlink API
- **What**: URL preview / link unfurling (fallback for screenshots)
- **API**: `https://api.microlink.io`
- **Env var**: None (no API key, uses free tier)
- **Used in**: `api/services/screenshot_service.py`
- **Cost**: $0 (free tier, 50 req/day)
- **Status**: FREE TIER
- **Critical**: Low — fallback for URL previews when Playwright unavailable

---

## PAYMENT PROVIDERS

### 14. Stripe
- **What**: Payment processing for creator products
- **Env vars**: `STRIPE_SECRET_KEY` (test mode: `sk_test_*`), `STRIPE_CLIENT_ID`
- **Used in**: `core/payments/stripe_handler.py`, `api/routers/oauth/stripe.py`
- **Cost**: 2.9% + $0.30 per transaction (only when payments processed)
- **Status**: PAID (per-transaction, currently in TEST MODE)
- **Critical**: Low (not yet in production)

### 15. PayPal
- **What**: Alternative payment processing
- **Env vars**: `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_MODE`
- **Cost**: 2.9% + $0.30 per transaction
- **Status**: CONFIGURED (not actively processing)
- **Critical**: Low

---

## SCHEDULING & INTEGRATIONS

### 16. Calendly
- **What**: Meeting scheduling integration for creators
- **Env vars**: `CALENDLY_API_KEY`, `CALENDLY_CLIENT_ID`, `CALENDLY_CLIENT_SECRET`, `CALENDLY_REDIRECT_URI`, `CALENDLY_WEBHOOK_SECRET`
- **Cost**: Depends on creator's Calendly plan (Clonnect uses OAuth, no direct cost)
- **Status**: CONFIGURED
- **Critical**: Low — optional creator integration

### 17. Zoom
- **What**: Video meeting integration
- **Env vars**: `ZOOM_CLIENT_ID`, `ZOOM_CLIENT_SECRET`, `ZOOM_REDIRECT_URI`
- **Cost**: $0 (OAuth integration, no API fees)
- **Status**: CONFIGURED
- **Critical**: Low — optional creator integration

### 18. Google OAuth
- **What**: Google Calendar / Meet integration
- **Env vars**: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`
- **Cost**: $0 (OAuth integration)
- **Status**: CONFIGURED
- **Critical**: Low — optional creator integration

---

## EMAIL & NOTIFICATIONS

### 19. Resend
- **What**: Transactional email service
- **API**: `https://api.resend.com/emails`
- **Env var**: `RESEND_API_KEY`
- **Used in**: `core/notifications.py` (2 call sites)
- **Cost**: Free tier (100 emails/day, 3,000/month)
- **Status**: FREE TIER
- **Critical**: Low — notification emails only

---

## MONITORING

### 20. Sentry
- **What**: Error tracking and performance monitoring
- **Env var**: `SENTRY_DSN` (NOT currently set in Railway)
- **SDK**: `sentry-sdk[fastapi]` in requirements.txt
- **Used in**: `api/main.py` (init), `core/link_preview.py` (capture_exception)
- **Cost**: Free tier (5K errors/month)
- **Status**: NOT ACTIVE (SENTRY_DSN not configured)
- **Critical**: Should be enabled for production monitoring

### 21. Prometheus (metrics)
- **What**: Metrics collection
- **SDK**: `prometheus_client` in requirements.txt
- **Status**: INCLUDED (library only, no external service)

---

## CONTENT INGESTION

### 22. Playwright
- **What**: Headless browser for screenshots and web scraping
- **SDK**: `playwright>=1.40.0` in requirements.txt
- **Used in**: `api/services/screenshot_service.py`, ingestion pipeline
- **Cost**: $0 (self-hosted, runs on Railway)
- **Status**: SELF-HOSTED
- **Critical**: Low — screenshot generation for link previews

### 23. YouTube (yt-dlp + Transcript API)
- **What**: YouTube video content ingestion
- **SDKs**: `yt-dlp`, `youtube-transcript-api`
- **Cost**: $0 (no API key needed)
- **Status**: FREE
- **Critical**: Low — content ingestion only

---

## SECURITY

### 24. JWT Authentication
- **What**: User authentication tokens
- **Env var**: `JWT_SECRET`
- **SDK**: `PyJWT`
- **Cost**: $0 (self-implemented)
- **Status**: SELF-HOSTED

---

## COST SUMMARY

### Monthly Fixed Costs

| Service | Monthly Cost | Category |
|---------|-------------|----------|
| Railway (compute) | ~$10-15 | Hosting |
| Neon (PostgreSQL) | ~$19-25 | Database |
| **Subtotal fixed** | **~$29-40** | |

### Monthly Variable Costs (at 245 msgs/day, 2 creators)

| Service | Monthly Cost | Category |
|---------|-------------|----------|
| Google AI (Gemini) | ~$2 | LLM |
| OpenAI (fallback + embeddings) | ~$1 | LLM |
| xAI (Grok, dashboard) | ~$0-2 | LLM |
| Stripe/PayPal | $0 (test mode) | Payments |
| **Subtotal variable** | **~$3-5** | |

### Free Services

| Service | Limit | Status |
|---------|-------|--------|
| Groq (Whisper) | Generous free tier | Active |
| Instagram/Meta API | Unlimited (approved app) | Active |
| WhatsApp API | Business-initiated free | Active |
| Telegram API | Unlimited | Active |
| Cloudinary | 25 credits/month | Active |
| Resend | 3,000 emails/month | Active |
| Microlink | 50 req/day | Active |
| Sentry | 5K errors/month | NOT configured |
| Cloudflare Workers | 100K req/day | Active (Telegram proxy) |

### TOTAL ESTIMATED MONTHLY COST: ~$32-45

---

## UNUSED / CAN REMOVE

| Env Var | Service | Reason |
|---------|---------|--------|
| `DEEPINFRA_API_KEY` | DeepInfra | No code references in production |
| `DEEPINFRA_INCLUDE_REASONING` | DeepInfra | Same |
| `DEEPINFRA_NO_FALLBACK` | DeepInfra | Same |
| `DEEPINFRA_TIMEOUT` | DeepInfra | Same |
| `SENTRY_DSN` | Sentry | Not set (should be configured, not removed) |
| `anthropic` (requirements.txt) | Anthropic | SDK installed but no API key configured |

---

## SECURITY WARNINGS

1. **Hardcoded DB credentials in scripts/**: 4 files contain full Neon connection string with password:
   - `scripts/backfill_profile_pics.py:24`
   - `scripts/import_ig_history.py:30`
   - `scripts/import_iris_ig_history.py:27`
   - `scripts/restore_messages_from_json.py:17`
   - **Action**: Replace with `os.getenv("DATABASE_URL")` or remove scripts

2. **Admin key is weak**: `CLONNECT_ADMIN_KEY = clonnect_admin_secret_2024` — should be rotated to a random string

3. **Stripe in test mode**: `sk_test_*` — switch to live keys when ready for payments

---

## ARCHITECTURE DIAGRAM

```
                    ┌─────────────────────┐
                    │   www.clonnectapp.com│
                    │   (Frontend - Vercel?)│
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │  api.clonnectapp.com │
                    │  Railway (FastAPI)   │
                    └──┬──┬──┬──┬──┬──┬───┘
                       │  │  │  │  │  │
         ┌─────────────┘  │  │  │  │  └──────────────┐
         │                │  │  │  │                  │
    ┌────▼────┐    ┌─────▼──▼──▼──▼─────┐    ┌──────▼──────┐
    │  Neon   │    │    LLM Providers    │    │  Messaging  │
    │PostgreSQL│    │ Gemini│OpenAI│Groq │    │ IG│WA│TG    │
    │pgvector │    │ xAI   │      │     │    │             │
    └─────────┘    └────────────────────┘    └─────────────┘
         │                                         │
    ┌────▼────┐                              ┌─────▼──────┐
    │Cloudinary│                              │Evolution API│
    │  (CDN)  │                              │(WA, Railway)│
    └─────────┘                              └────────────┘
```

---

*Document generated 2026-03-15 by Claude Code.*
