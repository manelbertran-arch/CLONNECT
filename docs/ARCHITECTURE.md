# CLONNECT - Arquitectura del Sistema

## 1. Visión General

**CLONNECT** es un SaaS para automatizar respuestas a DMs (mensajes directos) de creadores de contenido usando IA. El sistema permite a creadores de contenido "clonar" su voz y estilo para responder automáticamente a sus seguidores en Instagram, Telegram y WhatsApp.

### Características Principales
- **DM Automation**: Respuestas automáticas personalizadas usando LLM
- **Multi-plataforma**: Instagram, Telegram, WhatsApp
- **Magic Slice**: Sistema de análisis de tono y citación de contenido
- **Ventas Automatizadas**: Detección de intención de compra y gestión de pagos
- **Nurturing**: Secuencias de seguimiento automático
- **Calendar/Booking**: Integración con Calendly, Cal.com, Zoom, Google Meet
- **GDPR Compliance**: Gestión de consentimiento y datos personales

---

## 2. Stack Tecnológico

| Componente | Tecnología |
|------------|------------|
| **Backend** | FastAPI (Python 3.11) |
| **Base de Datos** | PostgreSQL + JSON fallback |
| **LLM** | Groq (Llama 3.3 70B), OpenAI (GPT-4o-mini), Anthropic (Claude) |
| **Dashboard** | Streamlit |
| **Frontend** | React + Vite + TypeScript |
| **Deploy Backend** | Railway (Docker) |
| **Deploy Frontend** | Vercel |
| **Mensajería** | Instagram Graph API, Telegram Bot API, WhatsApp Cloud API |
| **Pagos** | Stripe, PayPal, Hotmart |
| **Calendario** | Calendly, Cal.com |

---

## 3. Estructura de Directorios

```
CLONNECT/
├── backend/
│   ├── api/                    # FastAPI application
│   │   ├── main.py             # Entry point, todos los endpoints
│   │   ├── models.py           # SQLAlchemy models
│   │   ├── database.py         # DB connection
│   │   ├── config.py           # Configuration
│   │   ├── routers/            # API routers modulares
│   │   │   ├── health.py       # Health checks
│   │   │   ├── leads.py        # Lead management
│   │   │   ├── products.py     # Product CRUD
│   │   │   ├── oauth.py        # OAuth flows (Meta, Stripe, PayPal, Google)
│   │   │   ├── booking.py      # Calendar booking
│   │   │   ├── nurturing.py    # Follow-up sequences
│   │   │   ├── citations.py    # Content citations
│   │   │   └── tone.py         # Tone profiles
│   │   ├── schemas/            # Pydantic schemas
│   │   └── services/           # Business logic services
│   │
│   ├── core/                   # Core business logic
│   │   ├── dm_agent.py         # 🔑 Main DM responder agent
│   │   ├── llm.py              # LLM client factory (Groq/OpenAI/Anthropic)
│   │   ├── intent_classifier.py # Intent classification
│   │   ├── memory.py           # Conversation memory
│   │   ├── creator_config.py   # Creator configuration
│   │   ├── products.py         # Product management
│   │   ├── nurturing.py        # Nurturing sequences
│   │   ├── payments.py         # Payment processing
│   │   ├── calendar.py         # Calendar integration
│   │   ├── instagram.py        # Instagram webhook handler
│   │   ├── instagram_handler.py # Instagram message processing
│   │   ├── telegram_adapter.py # Telegram bot adapter
│   │   ├── whatsapp.py         # WhatsApp Cloud API
│   │   ├── gdpr.py             # GDPR compliance
│   │   ├── alerts.py           # Alert system
│   │   ├── notifications.py    # Escalation notifications
│   │   ├── guardrails.py       # Response safety guardrails
│   │   ├── tone_service.py     # Magic Slice: Tone integration
│   │   ├── citation_service.py # Magic Slice: Citation integration
│   │   ├── onboarding_service.py # Creator onboarding pipeline
│   │   ├── analytics/          # Analytics tracking
│   │   ├── rag/                # RAG: BM25 + semantic search
│   │   └── reasoning/          # Advanced reasoning (CoT, self-consistency)
│   │
│   ├── ingestion/              # 🔮 Magic Slice module
│   │   ├── __init__.py         # Module exports
│   │   ├── content_indexer.py  # Content chunking
│   │   ├── instagram_scraper.py # Instagram scraping
│   │   ├── tone_analyzer.py    # Tone/voice analysis
│   │   ├── content_citation.py # Content citation engine
│   │   ├── response_engine_v2.py # Enhanced response generation
│   │   ├── transcriber.py      # Audio transcription (Whisper)
│   │   ├── youtube_connector.py # YouTube import
│   │   ├── podcast_connector.py # Podcast import
│   │   └── pdf_extractor.py    # PDF text extraction
│   │
│   ├── dashboard/              # Streamlit dashboards
│   │   ├── app.py              # User dashboard
│   │   └── admin.py            # Admin dashboard
│   │
│   ├── admin/                  # Admin UI components
│   │   ├── dashboard.py
│   │   ├── pages/
│   │   └── components/
│   │
│   ├── tests/                  # Test suite (406 tests)
│   ├── scripts/                # Utility scripts
│   └── data/                   # JSON storage (fallback)
│
├── frontend/                   # React frontend
│   ├── src/
│   └── dist/
│
├── cloudflare-telegram-proxy/  # Telegram proxy worker
│
├── DEPLOY.md                   # Deployment guide
└── docs/
    └── ARCHITECTURE.md         # This file
```

---

## 4. Módulos Principales

### 4.1 Core - DM Agent (`backend/core/dm_agent.py`)

El corazón del sistema. Procesa mensajes entrantes y genera respuestas.

```python
class DMResponderAgent:
    """Agent principal para responder DMs"""

    async def process_dm(
        self,
        sender_id: str,
        message_text: str,
        message_id: str,
        platform: str = "instagram"
    ) -> DMResponse:
        """Procesa un DM y genera respuesta"""
```

**Flujo de procesamiento:**
1. Verificar GDPR consent (si está habilitado)
2. Clasificar intent del mensaje
3. Cargar contexto de conversación (memory)
4. Generar respuesta usando LLM
5. Aplicar tone matching (Magic Slice)
6. Añadir citations si aplica
7. Aplicar guardrails de seguridad
8. Programar nurturing si corresponde
9. Trackear analytics

**Intents soportados:**
| Intent | Descripción |
|--------|-------------|
| `GREETING` | Saludo inicial |
| `INTEREST_SOFT` | Interés leve |
| `INTEREST_STRONG` | Intención de compra |
| `OBJECTION_PRICE` | Objeción de precio |
| `OBJECTION_TIME` | "No tengo tiempo" |
| `QUESTION_PRODUCT` | Pregunta sobre producto |
| `BOOKING` | Quiere agendar llamada |
| `ESCALATION` | Requiere humano |
| `SUPPORT` | Soporte técnico |

### 4.2 LLM Client (`backend/core/llm.py`)

Factory pattern para múltiples proveedores LLM:

```python
def get_llm_client(provider: str = None) -> LLMClient:
    """
    Providers:
    - groq (default): Llama 3.3 70B - GRATIS
    - openai: GPT-4o-mini
    - anthropic: Claude 3 Haiku
    """
```

### 4.3 Magic Slice (`backend/ingestion/`)

Sistema de análisis y citación de contenido del creador.

#### Phase 1: Core Components

| Módulo | Función |
|--------|---------|
| `tone_analyzer.py` | Analiza posts para extraer ToneProfile |
| `content_citation.py` | Indexa contenido y genera citas |
| `content_indexer.py` | Chunking de contenido |
| `instagram_scraper.py` | Scraping de posts de Instagram |
| `response_engine_v2.py` | Generación mejorada de respuestas |

#### Phase 2: Media Connectors

| Módulo | Función |
|--------|---------|
| `transcriber.py` | Transcripción audio → texto (Whisper) |
| `youtube_connector.py` | Importar videos de YouTube |
| `podcast_connector.py` | Importar episodios de podcast |
| `pdf_extractor.py` | Extraer texto de PDFs |

**ToneProfile estructura:**
```python
@dataclass
class ToneProfile:
    formality: float        # 0-1 (informal → formal)
    enthusiasm: float       # 0-1
    empathy: float          # 0-1
    directness: float       # 0-1
    humor: float            # 0-1
    vocabulary: List[str]   # Palabras frecuentes
    expressions: List[str]  # Expresiones típicas
    emoji_usage: float      # 0-1
    avg_message_length: int
```

### 4.4 API Routers (`backend/api/routers/`)

| Router | Prefix | Función |
|--------|--------|---------|
| `health.py` | `/health` | Health checks |
| `leads.py` | `/leads` | CRUD de leads |
| `products.py` | `/products` | CRUD de productos |
| `oauth.py` | `/oauth` | OAuth flows |
| `booking.py` | `/booking` | Calendar booking |
| `nurturing.py` | `/nurturing` | Follow-up sequences |
| `citations.py` | `/citations` | Content citations API |
| `tone.py` | `/tone` | Tone profiles API |
| `onboarding.py` | `/onboarding` | Creator onboarding |

---

## 5. Endpoints API

### Health & Status
| Method | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/health/live` | Liveness probe |
| GET | `/health/ready` | Readiness probe |
| GET | `/health` | Full health status |

### Webhooks (Messaging Platforms)
| Method | Endpoint | Descripción |
|--------|----------|-------------|
| GET/POST | `/webhook/instagram` | Instagram webhook |
| GET/POST | `/webhook/whatsapp` | WhatsApp webhook |
| POST | `/webhook/telegram` | Telegram webhook |
| POST | `/webhook/instagram/comments` | Instagram comments |

### DM Processing
| Method | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/dm/process` | Procesar mensaje DM |
| GET | `/dm/conversations/{creator_id}` | Listar conversaciones |
| GET | `/dm/follower/{creator_id}/{follower_id}` | Info de follower |
| PUT | `/dm/follower/{creator_id}/{follower_id}/status` | Actualizar status |

### Creator Management
| Method | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/creator/config` | Crear config |
| GET | `/creator/config/{creator_id}` | Obtener config |
| PUT | `/creator/config/{creator_id}` | Actualizar config |
| GET | `/creator/list` | Listar creadores |
| POST | `/bot/{creator_id}/pause` | Pausar bot |
| POST | `/bot/{creator_id}/resume` | Reanudar bot |

### Products
| Method | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/creator/{creator_id}/products` | Crear producto |
| GET | `/creator/{creator_id}/products` | Listar productos |
| PUT | `/creator/{creator_id}/products/{id}` | Actualizar |
| DELETE | `/creator/{creator_id}/products/{id}` | Eliminar |

### Calendar & Booking
| Method | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/calendar/{creator_id}/bookings` | Listar bookings |
| POST | `/calendar/{creator_id}/links` | Crear booking link |
| GET | `/calendar/{creator_id}/links` | Listar links |
| POST | `/webhook/calendly` | Calendly webhook |
| POST | `/webhook/calcom` | Cal.com webhook |

### Payments
| Method | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/webhook/stripe` | Stripe webhook |
| POST | `/webhook/paypal` | PayPal webhook |
| POST | `/webhook/hotmart` | Hotmart webhook |
| GET | `/payments/{creator_id}/revenue` | Revenue stats |

### GDPR
| Method | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/gdpr/{creator_id}/export/{follower_id}` | Exportar datos |
| DELETE | `/gdpr/{creator_id}/delete/{follower_id}` | Eliminar datos |
| POST | `/gdpr/{creator_id}/consent/{follower_id}` | Registrar consent |

### OAuth
| Method | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/oauth/instagram/start` | Iniciar OAuth Instagram |
| GET | `/oauth/instagram/callback` | Callback |
| GET | `/oauth/stripe/connect` | Stripe Connect |
| GET | `/oauth/paypal/start` | PayPal OAuth |
| GET | `/oauth/google/start` | Google OAuth |

---

## 6. Flujos de Negocio

### 6.1 Flujo de Mensaje Entrante (DM)

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Instagram  │────▶│   Webhook    │────▶│  DMAgent    │
│  /Telegram  │     │  /webhook/*  │     │ process_dm()│
│  /WhatsApp  │     └──────────────┘     └──────┬──────┘
└─────────────┘                                  │
                                                 ▼
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Response   │◀────│   LLM        │◀────│  Intent     │
│  to User    │     │  (Groq)      │     │  Classify   │
└─────────────┘     └──────────────┘     └─────────────┘
                           │
                           ▼
            ┌──────────────────────────┐
            │     Magic Slice          │
            │  - Tone matching         │
            │  - Content citations     │
            │  - Guardrails            │
            └──────────────────────────┘
```

1. **Webhook recibe mensaje** (`/webhook/instagram`, `/webhook/telegram`, `/webhook/whatsapp`)
2. **Valida signature** y extrae datos del mensaje
3. **DMAgent.process_dm()** procesa el mensaje:
   - Verifica GDPR consent si está habilitado
   - Clasifica intent del mensaje
   - Carga historial de conversación (memory)
   - Construye prompt con contexto
4. **LLM genera respuesta** (Groq/OpenAI/Anthropic)
5. **Magic Slice** aplica:
   - Tone matching (ajusta al estilo del creador)
   - Content citations (cita contenido relevante)
   - Guardrails (filtra respuestas inapropiadas)
6. **Envía respuesta** a la plataforma original
7. **Post-processing**:
   - Actualiza lead score
   - Programa nurturing si aplica
   - Trackea analytics

### 6.2 Flujo de Onboarding de Creador

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Frontend   │────▶│  /onboarding │────▶│ Onboarding  │
│  Wizard     │     │  /start      │     │ Service     │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                 │
                    ┌────────────────────────────┼────────────────────────────┐
                    ▼                            ▼                            ▼
            ┌──────────────┐            ┌──────────────┐            ┌──────────────┐
            │  Instagram   │            │    Tone      │            │   Content    │
            │  Scraper     │            │   Analyzer   │            │   Indexer    │
            └──────────────┘            └──────────────┘            └──────────────┘
                    │                            │                            │
                    ▼                            ▼                            ▼
            ┌──────────────┐            ┌──────────────┐            ┌──────────────┐
            │    Posts     │            │ ToneProfile  │            │   Content    │
            │    JSON      │            │    JSON      │            │    Index     │
            └──────────────┘            └──────────────┘            └──────────────┘
```

1. **Creador inicia onboarding** vía frontend
2. **Conecta Instagram** (OAuth o JSON manual)
3. **Instagram Scraper** obtiene posts recientes
4. **Tone Analyzer** analiza posts → genera ToneProfile
5. **Content Indexer** indexa contenido para citations
6. **Guarda configuración** (products, rules, etc.)
7. **Marca onboarding_completed = True**

### 6.3 Flujo Magic Slice

```
┌─────────────────────────────────────────────────────────────┐
│                      MAGIC SLICE                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐   │
│  │   Scraper   │────▶│    Tone     │────▶│ ToneProfile │   │
│  │  Instagram  │     │  Analyzer   │     │   (.json)   │   │
│  └─────────────┘     └─────────────┘     └─────────────┘   │
│                                                  │          │
│  ┌─────────────┐     ┌─────────────┐            │          │
│  │   Content   │────▶│   Content   │────────────┘          │
│  │   Indexer   │     │    Index    │                       │
│  └─────────────┘     └─────────────┘                       │
│         │                   │                              │
│         ▼                   ▼                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Response Engine V2                      │   │
│  │  - Aplica ToneProfile al prompt                     │   │
│  │  - Busca y cita contenido relevante                 │   │
│  │  - Genera respuesta personalizada                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 6.4 Flujo de Ventas

```
Mensaje con interés
        │
        ▼
┌───────────────┐
│ Intent:       │
│ INTEREST_*    │────┐
└───────────────┘    │
                     ▼
            ┌───────────────┐
            │ Update Lead   │
            │ purchase_intent│
            │ status: hot   │
            └───────┬───────┘
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
┌───────────┐ ┌───────────┐ ┌───────────┐
│  Payment  │ │  Booking  │ │  Nurture  │
│   Link    │ │   Link    │ │ Sequence  │
└───────────┘ └───────────┘ └───────────┘
```

### 6.5 Flujo de Nurturing

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Scheduler  │────▶│  Nurturing   │────▶│   Send      │
│  (5 min)    │     │  Manager     │     │  Follow-up  │
└─────────────┘     └──────────────┘     └─────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  Check:      │
                    │  - Last msg  │
                    │  - Lead temp │
                    │  - Sequence  │
                    └──────────────┘
```

---

## 7. Integraciones Externas

### LLM Providers
| Servicio | Uso | Configuración |
|----------|-----|---------------|
| **Groq** | LLM principal (Llama 3.3 70B) | `GROQ_API_KEY` |
| **OpenAI** | LLM alternativo, Whisper | `OPENAI_API_KEY` |
| **Anthropic** | LLM alternativo | `ANTHROPIC_API_KEY` |
| **xAI** | Knowledge generation | `XAI_API_KEY` |

### Messaging Platforms
| Servicio | Uso | Variables |
|----------|-----|-----------|
| **Instagram** | DMs, Comments | `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_PAGE_ID` |
| **Telegram** | Bot messaging | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_PROXY_URL` |
| **WhatsApp** | Cloud API | `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` |

### Payments
| Servicio | Uso | Variables |
|----------|-----|-----------|
| **Stripe** | Pagos, Connect | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` |
| **PayPal** | Pagos alternativos | `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` |
| **Hotmart** | Infoproductos | `HOTMART_WEBHOOK_TOKEN` |

### Calendar
| Servicio | Uso | Variables |
|----------|-----|-----------|
| **Calendly** | Booking links | `CALENDLY_API_KEY` |
| **Cal.com** | Booking alternativo | `CALCOM_API_KEY` |
| **Zoom** | Video calls | `ZOOM_ACCESS_TOKEN` |
| **Google** | Google Meet | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |

### Other
| Servicio | Uso | Variables |
|----------|-----|-----------|
| **Resend** | Email notifications | `RESEND_API_KEY` |
| **Meta** | OAuth, Embedded Signup | `META_APP_ID`, `META_APP_SECRET` |

---

## 8. Base de Datos

### PostgreSQL Schema (SQLAlchemy Models)

#### Creator
```sql
CREATE TABLE creators (
    id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE,
    name VARCHAR(255) NOT NULL,
    api_key VARCHAR(64) UNIQUE,
    bot_active BOOLEAN DEFAULT FALSE,
    clone_tone VARCHAR(50),
    clone_style TEXT,
    clone_name VARCHAR(255),
    -- Channel connections
    telegram_bot_token VARCHAR(255),
    instagram_token TEXT,
    whatsapp_token TEXT,
    -- Payment connections
    stripe_api_key TEXT,
    paypal_token TEXT,
    -- Calendar connections
    calendly_token TEXT,
    google_access_token TEXT,
    -- Knowledge
    knowledge_about JSON,
    onboarding_completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### Lead
```sql
CREATE TABLE leads (
    id UUID PRIMARY KEY,
    creator_id UUID REFERENCES creators(id),
    platform VARCHAR(20) NOT NULL,
    platform_user_id VARCHAR(255) NOT NULL,
    username VARCHAR(255),
    status VARCHAR(50) DEFAULT 'new',
    score INTEGER DEFAULT 0,
    purchase_intent FLOAT DEFAULT 0.0,
    context JSON,
    first_contact_at TIMESTAMPTZ,
    last_contact_at TIMESTAMPTZ
);
```

#### Message
```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY,
    lead_id UUID REFERENCES leads(id),
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    intent VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### Product
```sql
CREATE TABLE products (
    id UUID PRIMARY KEY,
    creator_id UUID REFERENCES creators(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    price FLOAT,
    currency VARCHAR(3) DEFAULT 'EUR',
    payment_link VARCHAR(500),
    is_active BOOLEAN DEFAULT TRUE
);
```

#### BookingLink
```sql
CREATE TABLE booking_links (
    id UUID PRIMARY KEY,
    creator_id VARCHAR(255) NOT NULL,
    meeting_type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    duration_minutes INTEGER DEFAULT 30,
    platform VARCHAR(50) DEFAULT 'manual',
    url TEXT,
    price INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE
);
```

### JSON Storage (Fallback)

Cuando `DATABASE_URL` no está configurado, el sistema usa archivos JSON:

```
data/
├── followers/{creator_id}/          # Lead data
│   ├── {follower_id}.json           # Individual follower
│   └── {follower_id}_messages.json  # Message history
├── products/{creator_id}_products.json
├── creators/{creator_id}_config.json
├── analytics/{creator_id}_events.json
├── nurturing/{creator_id}_followups.json
├── tone_profiles/{creator_id}_tone.json
└── content_index/{creator_id}_index.json
```

---

## 9. Configuración

### Variables de Entorno Requeridas

| Variable | Descripción | Default |
|----------|-------------|---------|
| `LLM_PROVIDER` | Provider LLM (groq/openai/anthropic) | `groq` |
| `GROQ_API_KEY` | API key de Groq | - |
| `CLONNECT_ADMIN_KEY` | Admin authentication | - |

### Variables Opcionales

#### Database
| Variable | Descripción | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | (JSON fallback) |
| `ENABLE_JSON_FALLBACK` | Usar JSON si no hay DB | `false` |

#### Application
| Variable | Descripción | Default |
|----------|-------------|---------|
| `DATA_PATH` | Directorio de datos | `./data` |
| `LOG_LEVEL` | Nivel de logging | `INFO` |
| `DEBUG` | Modo debug | `false` |
| `DEFAULT_CREATOR_ID` | Creator por defecto | `manel` |
| `FRONTEND_URL` | URL del frontend | `https://clonnect.vercel.app` |
| `API_URL` | URL del backend | `https://www.clonnectapp.com` |

#### Messaging
| Variable | Descripción |
|----------|-------------|
| `INSTAGRAM_ACCESS_TOKEN` | Token de Instagram |
| `INSTAGRAM_PAGE_ID` | Page ID de Facebook |
| `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram |
| `TELEGRAM_PROXY_URL` | Cloudflare Worker proxy |
| `WHATSAPP_ACCESS_TOKEN` | Token de WhatsApp |
| `WHATSAPP_PHONE_NUMBER_ID` | Phone number ID |

#### Payments
| Variable | Descripción |
|----------|-------------|
| `STRIPE_SECRET_KEY` | Stripe secret key |
| `PAYPAL_CLIENT_ID` | PayPal client ID |
| `PAYPAL_CLIENT_SECRET` | PayPal client secret |

---

## 10. Testing

### Test Suite Overview

```
Total: 423 tests
├── Passed: 406
├── Skipped: 17 (API keys not configured)
└── Failed: 0
```

### Magic Slice Tests: 85/85 ✓

### Ejecutar Tests

```bash
cd backend
PYTHONPATH=/path/to/CLONNECT python -m pytest tests/ -v

# Solo tests rápidos
pytest tests/ -v -m "not slow"

# Con coverage
pytest tests/ --cov=. --cov-report=html
```

### Archivos de Test Principales

| Archivo | Tests |
|---------|-------|
| `test_full_flow.py` | Flow completo de DM |
| `test_tone_analyzer.py` | Magic Slice tone |
| `test_content_citation.py` | Magic Slice citations |
| `test_media_connectors.py` | YouTube, Podcast, PDF |
| `test_onboarding_service.py` | Onboarding pipeline |
| `test_leads.py` | Lead management |
| `test_products.py` | Product CRUD |
| `test_nurturing.py` | Nurturing sequences |

---

## 11. Deployment

### Railway (Backend)

```bash
# Configuración en railway.json
{
  "build": { "builder": "DOCKERFILE" },
  "deploy": {
    "healthcheckPath": "/health/live",
    "restartPolicyType": "ON_FAILURE"
  }
}
```

### Vercel (Frontend)

```bash
# Build command
npm run build

# Output directory
dist
```

### URLs de Producción

| Servicio | URL |
|----------|-----|
| Production | https://www.clonnectapp.com |

### Health Checks

```bash
# Liveness
curl https://www.clonnectapp.com/health/live

# Readiness
curl https://www.clonnectapp.com/health/ready
```

---

## 12. Changelog / Magic Slice

### Phase 1 (Completed)
- ✅ ToneProfile analysis
- ✅ Content citation engine
- ✅ Instagram scraping
- ✅ Onboarding pipeline

### Phase 2 (Completed)
- ✅ Audio transcription (Whisper)
- ✅ YouTube connector
- ✅ Podcast connector
- ✅ PDF extractor

### Phase 3 - Instagram Multi-Creator (Completed - 2026-01-12)
- ✅ Multi-Creator Routing (page_id → creator_id)
- ✅ Dedicated Instagram Router
- ✅ Ice Breakers configuration
- ✅ Persistent Menu support
- ✅ Stories Reply/Mention Handler
- ✅ E2E Tests for Instagram

---

## 13. Métricas del Proyecto

```
┌─────────────────────────────────────────────────────────────────┐
│                    PROJECT METRICS (2026-01-12)                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  CODEBASE:                                                      │
│  ├── Archivos Python:            186                           │
│  ├── Archivos TypeScript/React:  80+                           │
│  ├── Líneas Python (backend):    ~75,000                       │
│  ├── Líneas TS/React (frontend): ~22,000                       │
│  └── Tests pasando:              422                           │
│                                                                 │
│  API:                                                           │
│  ├── Endpoints totales:          281                           │
│  ├── Routers:                    23                            │
│  └── Modelos de datos:           19                            │
│                                                                 │
│  FRONTEND:                                                      │
│  ├── Páginas:                    35                            │
│  ├── Servicios core:             37                            │
│  └── Tests frontend:             31                            │
│                                                                 │
│  PERFORMANCE:                                                   │
│  ├── DM response time:           2-5 segundos                  │
│  ├── Dashboard load:             <2 segundos                   │
│  └── Webhook processing:         <1 segundo                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

*Documento generado el 2026-01-05*
*Última actualización: 2026-01-12*
*Versión: 1.1*
