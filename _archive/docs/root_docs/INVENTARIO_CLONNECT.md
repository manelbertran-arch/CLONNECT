# INVENTARIO CLONNECT (Repositorio Principal)

> Generado: 2026-01-18
> Propósito: Comparativa con Memory Engine para planificar migración

---

## Estadísticas Generales

| Métrica | Valor |
|---------|-------|
| **Archivos Python** | 221 |
| **Archivos TypeScript/JavaScript** | 136 |
| **Tests Backend (Python)** | 47 |
| **Tests Frontend** | 17 |
| **Líneas Backend (Python)** | ~86,137 |
| **Líneas Frontend (TS/TSX)** | ~26,363 |
| **Total líneas código** | ~112,500 |
| **API Endpoints** | ~195 |
| **API Routers** | 24 |

---

## Estructura del Proyecto

```
CLONNECT/
├── backend/                    # FastAPI Backend
│   ├── api/                    # FastAPI app + routers
│   │   ├── main.py            # Main API (6,745 lines)
│   │   ├── models.py          # SQLAlchemy ORM models
│   │   ├── routers/           # 24 routers, ~195 endpoints
│   │   ├── services/          # Business services
│   │   ├── schemas/           # Pydantic schemas
│   │   └── middleware/        # Rate limiting, CORS
│   ├── core/                   # Core business logic (46 modules)
│   │   ├── dm_agent.py        # Main DM responder (5,097 lines)
│   │   ├── reasoning/         # CoT, SelfConsistency, Reflexion
│   │   ├── rag/               # BM25 + Semantic search
│   │   └── analytics/         # Analytics manager
│   ├── ingestion/             # Content ingestion pipeline
│   │   ├── transcriber.py     # Whisper transcription
│   │   ├── youtube_connector.py
│   │   ├── podcast_connector.py
│   │   ├── pdf_extractor.py
│   │   ├── tone_analyzer.py
│   │   └── v2/                # V2 ingestion (product detector)
│   ├── tests/                  # 47 test files
│   │   ├── performance/       # RAG performance tests
│   │   └── contracts/         # API contract tests
│   └── data/                   # JSON persistent storage
├── frontend/                   # React + TypeScript
│   ├── src/
│   │   ├── pages/             # 20+ pages
│   │   ├── components/        # Reusable components
│   │   └── hooks/             # Custom React hooks
│   └── e2e/                    # Playwright E2E tests
├── docs/                       # Documentation
└── scripts/                    # Utility scripts
```

---

## Módulos por Categoría

### Core Business Logic (`backend/core/`)

| Archivo | Líneas | Descripción | Estado |
|---------|--------|-------------|--------|
| `dm_agent.py` | 5,097 | DM Agent principal con generación de respuestas | ✅ Completo |
| `payments.py` | 1,129 | Integración Stripe/Hotmart/PayPal | ✅ Completo |
| `calendar.py` | 1,064 | Integración calendarios (Calendly, Cal.com) | ✅ Completo |
| `auto_configurator.py` | 944 | Auto-configuración de creadores | ✅ Completo |
| `gdpr.py` | 859 | Cumplimiento GDPR | ✅ Completo |
| `whatsapp.py` | 770 | Integración WhatsApp Business API | ✅ Completo |
| `citation_service.py` | 705 | Servicio de citaciones de contenido | ✅ Completo |
| `nurturing.py` | 699 | Motor de secuencias nurturing | ✅ Completo |
| `telegram_adapter.py` | 673 | Integración Telegram Bot API | ✅ Completo |
| `instagram_handler.py` | 630 | Manejador de Instagram DMs | ✅ Completo |
| `tone_profile_db.py` | 528 | Persistencia perfiles de tono | ✅ Completo |
| `copilot_service.py` | 489 | Modo copilot con aprobación humana | ✅ Completo |
| `intent_classifier.py` | 469 | Clasificación de intenciones | ✅ Completo |
| `products.py` | 456 | Gestión de productos | ✅ Completo |
| `guardrails.py` | 283 | Validación anti-hallucination | ✅ Completo |
| `query_expansion.py` | - | Expansión de queries | ✅ Existe |

### Reasoning Modules (`backend/core/reasoning/`)

| Archivo | Líneas | Descripción | Estado |
|---------|--------|-------------|--------|
| `chain_of_thought.py` | 339 | Razonamiento paso a paso | ✅ Completo |
| `self_consistency.py` | 337 | Validación por consistencia múltiple | ✅ Completo |
| `reflexion.py` | 325 | Mejora iterativa de respuestas | ✅ Completo |

### RAG Modules (`backend/core/rag/`)

| Archivo | Líneas | Descripción | Estado |
|---------|--------|-------------|--------|
| `bm25.py` | 348 | BM25 lexical search | ✅ Completo |
| `semantic.py` | 280 | OpenAI Embeddings + pgvector | ✅ Completo |
| `__init__.py` | 40 | HybridRAG export | ✅ Completo |

### Ingestion Pipeline (`backend/ingestion/`)

| Archivo | Líneas | Descripción | Estado |
|---------|--------|-------------|--------|
| `tone_analyzer.py` | 709 | Análisis de tono del creador | ✅ Completo |
| `instagram_scraper.py` | 499 | Scraping de posts Instagram | ✅ Completo |
| `content_citation.py` | 473 | Magic Slice content citations | ✅ Completo |
| `podcast_connector.py` | 414 | RSS + transcripción podcasts | ✅ Completo |
| `youtube_connector.py` | 347 | yt-dlp + transcripts YouTube | ✅ Completo |
| `pdf_extractor.py` | 345 | Extracción de texto PDF (pypdf) | ✅ Completo |
| `transcriber.py` | 231 | Whisper transcription | ✅ Completo |
| `content_indexer.py` | 139 | Indexación de contenido | ✅ Completo |

### Ingestion V2 (`backend/ingestion/v2/`)

| Archivo | Líneas | Descripción | Estado |
|---------|--------|-------------|--------|
| `product_detector.py` | 875 | Detección automática de productos | ✅ Completo |
| `instagram_ingestion.py` | 476 | Ingestion Instagram mejorado | ✅ Completo |
| `pipeline.py` | 421 | Pipeline V2 completo | ✅ Completo |
| `sanity_checker.py` | 366 | Validación de datos | ✅ Completo |

---

## API Routers (Endpoints)

| Router | Endpoints | Líneas | Descripción |
|--------|-----------|--------|-------------|
| `onboarding.py` | 24 | 4,190 | Setup wizard completo |
| `admin.py` | 29 | 2,847 | Panel administración |
| `oauth.py` | 15 | 1,646 | OAuth Instagram/Meta |
| `leads.py` | 17 | 1,093 | CRUD leads + pipeline |
| `instagram.py` | 10 | 976 | Webhooks + sync |
| `booking.py` | 7 | 761 | Reservas calendario |
| `calendar.py` | 12 | 651 | Gestión calendario |
| `nurturing.py` | 12 | 714 | Secuencias nurturing |
| `messages.py` | 5 | 639 | DM processing |
| `copilot.py` | 7 | 364 | AI suggestions |
| `ingestion.py` | 6 | 337 | Content ingestion |
| `ingestion_v2.py` | 5 | 354 | V2 ingestion |
| `connections.py` | 8 | 368 | Gestión conexiones |
| `config.py` | 7 | 257 | Config creador |
| `knowledge.py` | 9 | 178 | Knowledge base |
| `tone.py` | 7 | 149 | Tone profile |
| `citations.py` | 5 | 123 | Content citations |
| `preview.py` | 5 | 187 | Link previews |
| `products.py` | 4 | 101 | CRUD productos |
| `payments.py` | 3 | 105 | Webhooks pagos |
| `analytics.py` | 4 | 48 | Métricas |
| `dashboard.py` | 2 | 83 | Dashboard data |
| `health.py` | 2 | 16 | Health checks |

---

## Comparativa con Memory Engine

### Funcionalidades YA EXISTENTES en CLONNECT

| Funcionalidad | Archivo Clonnect | Estado | Notas |
|---------------|------------------|--------|-------|
| **Whisper Transcription** | `ingestion/transcriber.py` | ✅ | OpenAI Whisper API |
| **YouTube Connector** | `ingestion/youtube_connector.py` | ✅ | yt-dlp + transcripts |
| **Podcast Connector** | `ingestion/podcast_connector.py` | ✅ | feedparser + whisper |
| **PDF Extractor** | `ingestion/pdf_extractor.py` | ✅ | pypdf |
| **Tone Profile** | `ingestion/tone_analyzer.py` | ✅ | Análisis completo |
| **Content Citations** | `ingestion/content_citation.py` | ✅ | Magic Slice |
| **Intent Detection** | `core/intent_classifier.py` | ✅ | Multi-intent |
| **Lead Scoring** | `api/services/signals.py` | ✅ | Purchase intent |
| **Nurturing Sequences** | `core/nurturing.py` | ✅ | 8 tipos |
| **BM25 Search** | `core/rag/bm25.py` | ✅ | Lexical search |
| **Semantic RAG** | `core/rag/semantic.py` | ✅ | OpenAI + pgvector |
| **Chain of Thought** | `core/reasoning/chain_of_thought.py` | ✅ | Implementado |
| **Self-Consistency** | `core/reasoning/self_consistency.py` | ✅ | Implementado |
| **Reflexion** | `core/reasoning/reflexion.py` | ✅ | Implementado |
| **Query Cache** | `core/cache.py` | ✅ | TTL cache |
| **Guardrails** | `core/guardrails.py` | ✅ | Anti-hallucination |
| **Query Expansion** | `core/query_expansion.py` | ✅ | Existe |
| **Instagram** | `core/instagram_handler.py` | ✅ | DM completo |
| **Telegram** | `core/telegram_adapter.py` | ✅ | Bot completo |
| **WhatsApp** | `core/whatsapp.py` | ✅ | Business API |
| **Stripe/PayPal/Hotmart** | `core/payments.py` | ✅ | Webhooks |

### Funcionalidades que FALTAN (de Memory Engine)

| Funcionalidad | Memory Engine | Clonnect | Prioridad | Acción |
|---------------|---------------|----------|-----------|--------|
| **Cross-Encoder Reranking** | ✅ `core/adapter.py` | ❌ No tiene | 🔴 ALTA | Migrar |
| **HybridRAG completo** | ✅ BM25 + Semantic + Rerank | ⚠️ Parcial (sin rerank) | 🔴 ALTA | Mejorar |
| **ChromaDB** | ✅ | ❌ Usa pgvector | 🟢 BAJA | No necesario |
| **LangChain Agents** | ✅ | ❌ No tiene | 🟡 MEDIA | Futuro |
| **Tree of Thoughts** | ✅ | ❌ No tiene | 🟢 BAJA | No prioritario |
| **Fine-tuning pipeline** | ✅ | ❌ No tiene | 🟢 BAJA | No necesario |

---

## Resumen de Migración Recomendada

### CRÍTICO - Migrar de Memory Engine:

1. **Cross-Encoder Reranking** (`ms-marco-MiniLM-L-6-v2`)
   - Mejora significativa en calidad de búsqueda
   - Integrar en `core/rag/` como nuevo módulo `reranker.py`

### IMPORTANTE - Mejorar en Clonnect:

1. **HybridRAG con Reranking**
   - Ya tiene BM25 + Semantic
   - Añadir fase de reranking con cross-encoder

2. **Query Cache mejorado**
   - Ya existe `core/cache.py`
   - Considerar Redis para producción

### NO NECESARIO migrar:

| Funcionalidad | Razón |
|---------------|-------|
| ChromaDB | pgvector es suficiente y más integrado con PostgreSQL |
| LangChain | Arquitectura propia funciona bien |
| Tree of Thoughts | Overkill para casos de uso actuales |
| Fine-tuning | Costos vs beneficio no justificados |
| Whisper local | OpenAI API es más simple |

---

## Tests Existentes

### Backend (47 archivos, ~8,500 líneas)

| Test File | Líneas | Cobertura |
|-----------|--------|-----------|
| `test_scraping_pipeline_integration.py` | 704 | Scraping E2E |
| `test_media_connectors.py` | 649 | YouTube/Podcast/PDF |
| `test_response_engine_v2.py` | 601 | Response generation |
| `test_content_citation.py` | 420 | Citations |
| `test_signals.py` | 397 | Signal detection |
| `test_reasoning.py` | - | CoT, SelfConsistency, Reflexion |
| `test_rag_bm25.py` | 200 | BM25 + HybridRAG |

### Frontend (17 archivos)

- Unit tests: Vitest + Testing Library
- E2E tests: Playwright
- Accessibility tests: axe-core
- Snapshot tests: para regresiones UI

---

## Tecnologías Confirmadas

### Backend
- **Framework**: FastAPI + Uvicorn
- **ORM**: SQLAlchemy 2.0
- **DB**: PostgreSQL 15+ con pgvector
- **LLM**: Groq (Llama 3.3), OpenAI, Anthropic
- **Embeddings**: OpenAI text-embedding-3-small
- **Search**: BM25 + Semantic (pgvector)

### Frontend
- **Framework**: React 18.3 + TypeScript
- **Build**: Vite
- **UI**: TailwindCSS + shadcn/ui + Radix UI
- **State**: TanStack Query
- **Forms**: React Hook Form + Zod

### Infraestructura
- **Backend**: Railway
- **Frontend**: Vercel
- **CI/CD**: GitHub Actions
- **Monitoring**: Sentry

---

## Conclusión

**CLONNECT ya tiene implementado el 90% de las funcionalidades de Memory Engine.**

Solo falta migrar:
1. Cross-Encoder Reranking (prioridad alta)
2. Mejoras menores al HybridRAG

El resto de funcionalidades de Memory Engine o ya existen en Clonnect con implementaciones equivalentes, o no son necesarias para el caso de uso actual.
