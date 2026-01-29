# CLONNECT - Deployment Guide

## Overview

CLONNECT is a SaaS platform for automating content creator DMs with AI. The system consists of:

| Service | Technology | Platform |
|---------|------------|----------|
| Backend API | FastAPI + Python 3.11 | Railway/Docker |
| Dashboard | Streamlit | Railway/Render |
| Admin Panel | Streamlit | Railway/Render |
| Frontend | React + Vite | Vercel |
| Telegram Bot | Python Worker | Railway (optional) |

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (optional)
- Railway CLI or Render account
- Vercel account (for frontend)

### Local Development

```bash
cd backend
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

### Docker

```bash
cd backend
docker-compose up -d
```

Services available at:
- API: http://localhost:8000
- Dashboard: http://localhost:8501

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `LLM_PROVIDER` | LLM provider to use | `groq` or `openai` |
| `GROQ_API_KEY` | Groq API key (if using Groq) | `gsk_...` |
| `OPENAI_API_KEY` | OpenAI API key (if using OpenAI) | `sk-...` |
| `CLONNECT_ADMIN_KEY` | Admin authentication key | `your-secure-key` |

### Database (Optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | (uses JSON fallback) |
| `ENABLE_JSON_FALLBACK` | Use JSON files if no DB | `false` |

### Instagram Integration

| Variable | Description |
|----------|-------------|
| `INSTAGRAM_ACCESS_TOKEN` | Meta Graph API token |
| `INSTAGRAM_PAGE_ID` | Facebook Page ID |
| `INSTAGRAM_USER_ID` | Instagram Business Account ID |
| `INSTAGRAM_APP_SECRET` | Meta App secret |
| `INSTAGRAM_VERIFY_TOKEN` | Webhook verification token |

### WhatsApp Integration

| Variable | Description |
|----------|-------------|
| `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp Business phone ID |
| `WHATSAPP_ACCESS_TOKEN` | WhatsApp API token |
| `WHATSAPP_VERIFY_TOKEN` | Webhook verification token |
| `WHATSAPP_APP_SECRET` | Meta App secret |

### Telegram Bot

| Variable | Description |
|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token |
| `TELEGRAM_WEBHOOK_URL` | Webhook URL for updates |
| `TELEGRAM_PROXY_URL` | Cloudflare Worker proxy URL |
| `TELEGRAM_PROXY_SECRET` | Proxy authentication secret |

### Payment Integrations

| Variable | Description |
|----------|-------------|
| `STRIPE_SECRET_KEY` | Stripe secret key |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `PAYPAL_CLIENT_ID` | PayPal OAuth client ID |
| `PAYPAL_CLIENT_SECRET` | PayPal OAuth client secret |
| `PAYPAL_MODE` | `sandbox` or `live` |

### Calendar Integrations

| Variable | Description |
|----------|-------------|
| `CALENDLY_API_KEY` | Calendly API key |
| `CALCOM_API_KEY` | Cal.com API key |

### Alerts & Notifications

| Variable | Description |
|----------|-------------|
| `TELEGRAM_ALERTS_ENABLED` | Enable Telegram alerts |
| `TELEGRAM_ALERTS_BOT_TOKEN` | Alerts bot token |
| `TELEGRAM_ALERTS_CHAT_ID` | Chat ID for alerts |
| `RESEND_API_KEY` | Resend email API key |

### Application Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `DATA_PATH` | Data storage directory | `./data` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `DEBUG` | Enable debug mode | `false` |
| `DEFAULT_CREATOR_ID` | Default creator | `manel` |
| `FRONTEND_URL` | Frontend app URL | `https://www.clonnectapp.com` |
| `API_URL` | Backend API URL | `https://www.clonnectapp.com` |

## Deployment Platforms

### Railway (Recommended for Backend)

1. Connect GitHub repository
2. Configure environment variables in Railway dashboard
3. Railway will auto-detect `railway.json` and use Dockerfile
4. Health check endpoint: `/health/live`

**railway.json** configuration:
```json
{
  "build": { "builder": "DOCKERFILE" },
  "deploy": {
    "healthcheckPath": "/health/live",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

### Render

Uses `render.yaml` blueprint for multi-service deployment:
- clonnect-creators-api (Web Service)
- clonnect-dashboard (Web Service)
- clonnect-admin (Web Service)
- clonnect-telegram-bot (Worker - optional)

## Health Checks

| Endpoint | Description |
|----------|-------------|
| `GET /health/live` | Liveness probe |
| `GET /health/ready` | Readiness probe |
| `GET /health` | Full health status |

## Pre-Deploy Checklist

```bash
cd backend
python scripts/deploy_check.py
```

- [ ] All required environment variables set
- [ ] `requirements.txt` dependencies installed
- [ ] Syntax check passes
- [ ] API health endpoints responding
- [ ] Data directories created

## Security Checklist

- [x] `.env` in `.gitignore`
- [x] No hardcoded secrets in code
- [x] Non-root user in Docker (clonnect)
- [ ] HTTPS enforced (via platform)
- [ ] API keys in environment variables only
- [ ] CORS configured for production frontend

## Troubleshooting

### API not starting

1. Check `LOG_LEVEL=DEBUG` for detailed logs
2. Verify all required env vars are set
3. Check `/health/live` endpoint

### LLM errors

1. Verify `LLM_PROVIDER` matches your API key
2. Check API key is valid and has credits
3. Look for rate limiting errors in logs

### Database connection

1. Verify `DATABASE_URL` format: `postgresql://user:pass@host:port/db`
2. Check network connectivity to database
3. Set `ENABLE_JSON_FALLBACK=true` for file-based storage

### Webhook issues

1. Verify webhook URLs are publicly accessible
2. Check verify tokens match configuration
3. Review webhook logs in platform dashboard

## URLs

| Environment | Backend | Frontend |
|-------------|---------|----------|
| Production | https://www.clonnectapp.com | https://www.clonnectapp.com |
| Local | http://localhost:8000 | http://localhost:5173 |

## Useful Commands

```bash
# Run deploy check
python scripts/deploy_check.py

# Run tests
PYTHONPATH=/path/to/CLONNECT python -m pytest backend/tests/ -v

# Local development
uvicorn api.main:app --reload --port 8000

# Docker build
docker build -t clonnect-api .

# Docker run
docker run -p 8000:8000 --env-file .env clonnect-api
```
