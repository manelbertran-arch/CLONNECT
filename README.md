# CLONNECT

**AI Sales Expert for Content Creators** — SaaS platform that creates AI-powered digital clones to automate DM conversations, qualify leads, and generate revenue.

Production: [www.clonnectapp.com](https://www.clonnectapp.com)

## What It Does

Clonnect learns a creator's voice, tone, knowledge, and sales style, then handles their DM conversations 24/7 — responding to inquiries, qualifying leads, handling objections, promoting products, and tracking every interaction.

## Architecture

Monolithic FastAPI backend + React frontend, deployed as a single service on Railway.

```
backend/
├── core/              # Business logic (DM agent, LLM, integrations)
│   ├── dm_agent_v2.py # Central orchestrator — 15-stage pipeline
│   ├── providers/     # LLM providers (Gemini Flash-Lite primary)
│   ├── rag/           # Hybrid search (BM25 + semantic + Cross-Encoder)
│   └── …            # Guardrails, memory, intent, scoring, etc.
├── api/               # FastAPI app (46 routers, auth, middleware)
├── services/          # Specialized services (lead scoring, nurturing, etc.)
├── ingestion/         # Content ingestion pipeline (IG, web, YouTube, podcast)
├── tests/             # Test suite (293 files)
├── alembic/           # DB migrations (37 versioned)
└── metrics/           # Prometheus collectors

frontend/
├── src/pages/         # Dashboard pages (Inbox, Leads, Products, etc.)
├── src/components/    # Reusable UI (shadcn/ui + TailwindCSS)
└── src/services/      # API client

_archive/              # Historical docs, legacy code, audit reports
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2.0, Pydantic |
| Frontend | React, TypeScript, Vite, TailwindCSS, shadcn/ui |
| Database | PostgreSQL 15 (Neon) + pgvector |
| Primary LLM | Gemini 2.5 Flash-Lite |
| Fallback LLM | GPT-4o-mini |
| Embeddings | OpenAI text-embedding-3-small (1536d) |
| Search | Hybrid RAG: 70% semantic + 30% BM25 + Cross-Encoder reranking |
| Hosting | Railway (single service) |
| Media | Cloudinary (persistent CDN) |
| Messaging | Instagram Graph API (primary), WhatsApp (Evolution API), Telegram |
| Payments | Stripe, Hotmart, PayPal |
| Monitoring | Sentry + Prometheus |

## Key Metrics

- **~246K lines** of code (210K Python + 36K TypeScript)
- **53 SQLAlchemy models**, 37 Alembic migrations
- **46 API routers**, 65 feature flags
- **18 operational subsystems** in production
- **15-stage DM processing pipeline** per message

## DM Agent Pipeline

Each incoming message passes through: Intent Classification → Frustration Detection → Sensitivity Detection → Context Analysis → Conversation State → Memory Recall → Query Expansion → Hybrid RAG Search → Prompt Construction → LLM Generation → Reflexion Self-Critique → Guardrails → Output Validation → Format Fixes → Lead Categorization.

## Running Locally

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn api.main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

Requires environment variables — see Railway config.

## Feature Flags

65 `ENABLE_*` flags control feature rollout. Key active flags: `ENABLE_RERANKING`, `ENABLE_BM25_HYBRID`, `ENABLE_GUARDRAILS`, `ENABLE_CHAIN_OF_THOUGHT`, `ENABLE_REFLEXION`.

## Status

**Phase:** Functional beta — MVP in production, preparing first paying customers.
