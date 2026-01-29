# CLONNECT

SaaS platform for content creators to automate Instagram/Telegram/WhatsApp DMs with AI.

## Features

- **AI-Powered DM Responses**: Automatically respond to DMs with personalized messages using your voice/tone
- **Multi-Channel Support**: Instagram, Telegram, WhatsApp integration
- **Lead Management**: Track and score leads through the sales funnel (new -> warm -> hot -> customer)
- **Nurturing Sequences**: Automated follow-up sequences for different lead stages
- **Product Catalog**: Manage products with pricing and payment links
- **Analytics Dashboard**: Real-time metrics on conversations, conversions, and revenue
- **Booking Integration**: Calendar integration for scheduling calls (Calendly, Cal.com)
- **Payment Processing**: Stripe, Hotmart, PayPal integration with revenue tracking
- **GDPR Compliance**: Built-in data export, anonymization, and consent management

## Tech Stack

- **Backend**: FastAPI (Python 3.11+)
- **Frontend**: React + TypeScript + Vite + TailwindCSS + shadcn/ui
- **Database**: PostgreSQL (with SQLAlchemy ORM)
- **LLM**: Groq (Llama 3.3 70B), OpenAI, Anthropic with fallback
- **Deployment**: Railway (all services)

## Project Structure

```
CLONNECT/
├── backend/
│   ├── api/                 # FastAPI application
│   │   ├── main.py          # Main API entry point
│   │   ├── models.py        # SQLAlchemy models
│   │   ├── routers/         # API route handlers
│   │   └── middleware/      # Rate limiting, etc.
│   ├── core/                # Business logic
│   │   ├── dm_agent.py      # AI response generation
│   │   ├── llm.py           # LLM provider abstraction
│   │   ├── payments.py      # Payment processing
│   │   ├── nurturing.py     # Nurturing sequences
│   │   └── ...
│   ├── alembic/             # Database migrations
│   ├── scripts/             # Utility scripts
│   └── tests/               # Backend tests
├── frontend/
│   ├── src/
│   │   ├── components/      # React components
│   │   ├── pages/           # Page components
│   │   ├── hooks/           # Custom hooks
│   │   └── lib/             # Utilities
│   ├── e2e/                 # Playwright E2E tests
│   └── ...
└── .github/workflows/       # CI/CD pipelines
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- PostgreSQL 15+
- Git

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment variables
cp .env.example .env
# Edit .env with your API keys

# Run database migrations (if DATABASE_URL is set)
alembic upgrade head

# Start the server
uvicorn api.main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Install Playwright browsers (for E2E tests)
npx playwright install

# Start development server
npm run dev
```

## Environment Variables

### Required

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Groq API key for LLM |
| `DATABASE_URL` | PostgreSQL connection string |
| `CLONNECT_ADMIN_KEY` | Admin authentication key |

### Optional

| Variable | Description |
|----------|-------------|
| `SENTRY_DSN` | Sentry error tracking DSN |
| `STRIPE_SECRET_KEY` | Stripe API key |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram Graph API token |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |

See `backend/.env.example` for full list.

## API Documentation

Once the backend is running, access the interactive API docs at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Testing

### Backend Tests

```bash
cd backend
pytest -v
```

### Frontend Tests

```bash
cd frontend

# Unit tests
npm run test

# E2E tests
npm run test:e2e

# E2E with UI
npm run test:e2e:ui
```

## Deployment

### Railway (Backend)

1. Connect your GitHub repo to Railway
2. Set environment variables in Railway dashboard
3. Railway auto-deploys on push to `main`

## Database Migrations

```bash
cd backend

# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

## Monitoring

- **Error Tracking**: Sentry (configure `SENTRY_DSN`)
- **Metrics**: Prometheus metrics at `/metrics`
- **Health Check**: `/health` endpoint

## Backup

Run the backup script:

```bash
cd backend
./scripts/backup.sh
```

Requires `DATABASE_URL` and optionally `S3_BUCKET` + AWS credentials for cloud backup.

## Contributing

1. Create a feature branch
2. Make changes
3. Run tests
4. Submit PR

## License

Private - All rights reserved
