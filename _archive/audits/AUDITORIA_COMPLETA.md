# AUDITORÍA COMPLETA - CLONNECT

**Fecha:** 2026-01-06
**Versión:** 1.0
**Rama:** claude/audit-clonnect-repo-F69mK

---

## RESUMEN EJECUTIVO

CLONNECT es una **plataforma SaaS de automatización de DMs con IA** para creadores de contenido. Permite crear "clones" de IA que responden mensajes directos en Instagram, Telegram y WhatsApp, gestionan leads, procesan pagos y programan reuniones.

| Métrica | Valor |
|---------|-------|
| **Endpoints API** | 114 |
| **Servicios Core** | 40+ |
| **Componentes Frontend** | 58+ |
| **Archivos de Test** | 30 (419 test functions) |
| **Integraciones** | 15+ |
| **Líneas de código (estimado)** | ~50,000+ |

---

## 1. ESTRUCTURA DEL PROYECTO

### Árbol de Directorios Principal

```
/home/user/CLONNECT/
├── .github/
│   └── workflows/
│       └── auto-merge-claude.yml      # CI/CD auto-merge
├── backend/                            # API FastAPI (Python 3.11)
│   ├── api/                           # Aplicación principal
│   │   ├── main.py                   # 184 KB - Entry point
│   │   ├── models.py                 # SQLAlchemy ORM
│   │   ├── routers/                  # 19 routers
│   │   ├── schemas/                  # Pydantic schemas
│   │   ├── services/                 # Servicios de BD
│   │   └── utils/
│   ├── core/                          # Lógica de negocio (40+ módulos)
│   │   ├── dm_agent.py               # 146 KB - Motor IA principal
│   │   ├── reasoning/                # CoT, Reflexion, Self-Consistency
│   │   ├── rag/                      # BM25 + Semantic search
│   │   └── analytics/
│   ├── data/                          # Almacenamiento JSON
│   │   ├── followers/
│   │   ├── products/
│   │   ├── creators/
│   │   ├── tone_profiles/
│   │   ├── content_index/
│   │   ├── payments/
│   │   ├── calendar/
│   │   ├── nurturing/
│   │   ├── escalations/
│   │   ├── gdpr/
│   │   └── analytics/
│   ├── tests/                         # 30 archivos de test
│   ├── scripts/                       # Utilidades
│   ├── admin/                         # Panel admin (Streamlit)
│   ├── dashboard/                     # Dashboard (Streamlit)
│   ├── docs/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── railway.json
│   ├── render.yaml
│   ├── requirements.txt
│   └── .env.example
├── frontend/                           # React + Vite + TypeScript
│   ├── src/
│   │   ├── components/               # 58+ componentes UI
│   │   ├── pages/                    # 20+ páginas
│   │   ├── services/                 # API client
│   │   ├── hooks/                    # React Query hooks
│   │   ├── types/
│   │   └── test/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   └── vercel.json
├── cloudflare-telegram-proxy/          # Proxy Telegram
├── data/                               # Datos root (mirror)
├── docs/                               # Documentación
└── screenshots/
```

### Archivos Clave

| Archivo | Tamaño | Propósito |
|---------|--------|-----------|
| `backend/api/main.py` | 184 KB | FastAPI app principal |
| `backend/core/dm_agent.py` | 146 KB | Motor de respuestas IA |
| `backend/api/services/db_service.py` | 48 KB | Operaciones PostgreSQL |
| `backend/api/routers/oauth.py` | 41 KB | Flujos OAuth |
| `backend/core/payments.py` | 41 KB | Gestión de pagos |
| `backend/core/calendar.py` | 37 KB | Integraciones calendario |
| `frontend/src/services/api.ts` | 1106 líneas | Cliente API |
| `frontend/src/hooks/useApi.ts` | 886 líneas | React Query hooks |

---

## 2. BACKEND

### 2.1 Endpoints Disponibles (114 total)

#### Health & Status
```
GET  /health/live              # Health check
GET  /health/ready             # Readiness probe
```

#### Dashboard
```
GET  /dashboard/{creator_id}/overview    # Métricas overview
PUT  /dashboard/{creator_id}/toggle      # Toggle bot on/off
```

#### Mensajes y Conversaciones
```
GET  /dm/metrics/{creator_id}                      # Métricas de mensajes
GET  /dm/follower/{creator_id}/{follower_id}       # Detalle conversación
GET  /dm/conversations/{creator_id}                # Lista conversaciones
POST /dm/send/{creator_id}                         # Enviar mensaje
POST /dm/conversations/{id}/archive                # Archivar
POST /dm/conversations/{id}/spam                   # Marcar spam
```

#### Leads
```
GET    /dm/leads/{creator_id}              # Listar leads
POST   /dm/leads/{creator_id}              # Crear lead
PUT    /dm/leads/{creator_id}/{lead_id}    # Actualizar lead
DELETE /dm/leads/{creator_id}/{lead_id}    # Eliminar lead
```

#### Productos
```
GET    /creator/{id}/products              # Listar productos
POST   /creator/{id}/products              # Crear producto
PUT    /creator/{id}/products/{pid}        # Actualizar
DELETE /creator/{id}/products/{pid}        # Eliminar
```

#### Pagos
```
GET  /payments/{id}/revenue                # Estadísticas ingresos
GET  /payments/{id}/purchases              # Historial compras
POST /payments/{id}/purchases              # Registrar compra
POST /payments/webhook/stripe              # Webhook Stripe
POST /payments/webhook/hotmart             # Webhook Hotmart
```

#### Calendario & Booking
```
GET  /calendar/{id}/bookings               # Listar bookings
GET  /calendar/{id}/stats                  # Estadísticas
GET  /booking/availability/{id}            # Disponibilidad
POST /booking/{id}/links                   # Crear link booking
POST /booking/{id}/slots                   # Crear slots
POST /booking/{id}/slots/{sid}/book        # Reservar slot
```

#### Nurturing
```
GET  /nurturing/{id}                       # Obtener secuencias
POST /nurturing/{id}/enable                # Activar secuencia
POST /nurturing/{id}/schedule              # Programar follow-ups
GET  /nurturing/scheduler/status           # Estado scheduler
```

#### Knowledge Base
```
GET    /creator/config/{id}/knowledge/faqs        # Obtener FAQs
POST   /creator/config/{id}/knowledge/faqs        # Agregar FAQ
PUT    /creator/config/{id}/knowledge/faqs/{fid}  # Actualizar
DELETE /creator/config/{id}/knowledge/faqs/{fid}  # Eliminar
GET    /creator/config/{id}/knowledge/about       # About Me
PUT    /creator/config/{id}/knowledge/about       # Actualizar About
```

#### Analytics
```
GET  /analytics/{id}/sales                 # Stats ventas
GET  /analytics/{id}/sales/activity        # Actividad reciente
GET  /analytics/{id}/sales/follower/{fid}  # Journey conversión
POST /analytics/{id}/sales/click           # Registrar click
```

#### OAuth
```
GET  /oauth/instagram/start                # Iniciar OAuth Instagram
GET  /oauth/instagram/callback             # Callback Instagram
GET  /oauth/telegram/start                 # Iniciar OAuth Telegram
GET  /oauth/google/start                   # Iniciar OAuth Google
GET  /oauth/calendly/start                 # Iniciar OAuth Calendly
POST /oauth/telegram/bot/{token}/start     # Registrar bot Telegram
```

#### Connections
```
GET /connections/{id}                      # Estado integraciones
```

#### Onboarding & Tone
```
GET  /onboarding/{id}/status               # Estado onboarding
POST /onboarding/{id}/quick                # Onboarding rápido
POST /onboarding/{id}/full                 # Onboarding completo
GET  /tone/{id}                            # ToneProfile
POST /tone/generate                        # Generar ToneProfile
```

#### Citations
```
POST /citations/index                      # Indexar posts
GET  /citations/{id}/stats                 # Stats índice
POST /citations/search                     # Buscar contenido
```

#### Admin
```
POST /admin/reset-db                       # Reset BD (demo)
```

---

### 2.2 Servicios Core

| Servicio | Archivo | Descripción |
|----------|---------|-------------|
| **DMResponderAgent** | `dm_agent.py` | Motor principal de respuestas IA (16 tipos de intención) |
| **CitationService** | `citation_service.py` | Indexación y citación de contenido |
| **ToneService** | `tone_service.py` | Análisis de tono de voz |
| **IntentClassifier** | `intent_classifier.py` | Clasificación de intención (LLM) |
| **NurturingManager** | `nurturing.py` | Secuencias de follow-up automáticas (9 tipos) |
| **SalesTracker** | `sales_tracker.py` | Tracking de conversiones y attribution |
| **PaymentManager** | `payments.py` | Gestión de pagos multi-plataforma |
| **CalendarManager** | `calendar.py` | Integraciones de calendario |
| **ProductManager** | `products.py` | CRUD de productos |
| **CreatorConfigManager** | `creator_config.py` | Configuración de creadores |
| **MemoryStore** | `memory.py` | Contexto de conversación |
| **ResponseCache** | `cache.py` | Caché de respuestas LLM |
| **ResponseGuardrail** | `guardrails.py` | Validación de seguridad |
| **GDPRManager** | `gdpr.py` | Cumplimiento GDPR |
| **AlertManager** | `alerts.py` | Sistema de alertas |
| **NotificationService** | `notifications.py` | Notificaciones multi-canal |
| **RateLimiter** | `rate_limiter.py` | Control de rate limiting |
| **MetricsMiddleware** | `metrics.py` | Prometheus metrics |

#### Reasoning Engine
| Módulo | Archivo | Descripción |
|--------|---------|-------------|
| Chain of Thought | `reasoning/chain_of_thought.py` | Razonamiento paso a paso |
| Self-Consistency | `reasoning/self_consistency.py` | Validación de consistencia |
| Reflexion | `reasoning/reflexion.py` | Mejora iterativa |

#### RAG (Retrieval Augmented Generation)
| Módulo | Archivo | Descripción |
|--------|---------|-------------|
| BM25 | `rag/bm25.py` | Búsqueda sparse |
| Semantic | `rag/semantic.py` | Búsqueda con embeddings (FAISS) |

---

### 2.3 Modelos de Datos

```python
# CREATOR
- id: UUID
- email, name, api_key
- bot_active: bool
- clone_tone, clone_style, clone_name, clone_vocabulary
- instagram_token, telegram_bot_token, whatsapp_token
- stripe_api_key, paypal_token, hotmart_token
- calendly_token, zoom_tokens, google_tokens
- knowledge_about: JSON

# LEAD
- id: UUID
- creator_id: FK
- platform, platform_user_id, username
- status: "new" | "active" | "hot" | "customer"
- score, purchase_intent
- first_contact_at, last_contact_at

# MESSAGE
- id: UUID
- lead_id: FK
- role: "user" | "assistant"
- content, intent, created_at

# PRODUCT
- id: UUID
- creator_id: FK
- name, description, price, currency
- payment_link, is_active

# CALENDAR_BOOKING
- id: UUID
- creator_id, follower_id
- meeting_type, platform, status
- scheduled_at, duration_minutes
- guest_name, guest_email, meeting_url

# PURCHASE
- purchase_id, creator_id, follower_id, product_id
- amount, currency, platform, status
- attributed_to_bot: bool
```

---

## 3. FRONTEND

### 3.1 Stack Tecnológico

| Tecnología | Versión | Uso |
|------------|---------|-----|
| React | 18.3.1 | Framework UI |
| TypeScript | 5.8.3 | Lenguaje |
| Vite | 5.4.19 | Build tool |
| Tailwind CSS | 3.4.17 | Estilos |
| Radix UI | 27+ paquetes | Componentes base |
| shadcn/ui | - | Componentes estilizados |
| TanStack Query | 5.83.0 | Estado y caché |
| React Router | 6.30.1 | Routing |
| React Hook Form | 7.61.1 | Formularios |
| Recharts | 2.15.4 | Gráficos |
| Vitest | 4.0.16 | Testing |
| Playwright | 1.57.0 | E2E Testing |

### 3.2 Páginas Disponibles

#### Dashboard Original (`/dashboard`, `/inbox`, etc.)
| Ruta | Componente | Líneas | Descripción |
|------|------------|--------|-------------|
| `/dashboard` | Dashboard.tsx | 363 | Métricas, bot toggle, hot leads |
| `/inbox` | Inbox.tsx | 590 | Conversaciones |
| `/leads` | Leads.tsx | 771 | Pipeline de leads (drag & drop) |
| `/nurturing` | Nurturing.tsx | 608 | Secuencias de follow-up |
| `/products` | Products.tsx | 544 | CRUD productos |
| `/bookings` | Bookings.tsx | 807 | Calendario y reservas |
| `/settings` | Settings.tsx | 1687 | Configuración completa |

#### Nueva Interfaz (`/new/*`)
| Ruta | Componente | Descripción |
|------|------------|-------------|
| `/new/inicio` | Inicio.tsx | Dashboard simplificado (español) |
| `/new/mensajes` | Mensajes.tsx | Chat interface |
| `/new/clientes` | Clientes.tsx | Lista de leads |
| `/new/ajustes` | Ajustes.tsx | Configuración modular |

#### Rutas Especiales
| Ruta | Componente | Descripción |
|------|------------|-------------|
| `/onboarding` | Onboarding.tsx | Setup inicial |
| `/book/:creatorId/:serviceId` | BookService.tsx | Booking público |

### 3.3 Componentes UI (58+)

**Componentes Radix/shadcn:**
- Button, Card, Input, Label, Dialog, Drawer
- Form, Toast, Select, Switch, Tabs, Badge
- Calendar, Carousel, Chart, Progress
- Dropdown, Popover, Tooltip, etc.

**Componentes de Dominio:**
- ProductoSection, PagosSection, ConexionesSection
- CalendarioSection, AutomatizacionesSection, TuClonSection
- Onboarding (Desktop + Mobile)

### 3.4 Estado y Datos

**Gestión:** TanStack React Query (NO Redux)

**Hooks principales:**
| Hook | Refetch | Descripción |
|------|---------|-------------|
| `useDashboard()` | 5s | Datos dashboard |
| `useConversations()` | 5s | Lista conversaciones |
| `useFollowerDetail()` | 5s | Detalle conversación |
| `useLeads()` | 10s | Lista leads |
| `useRevenue()` | 60s | Estadísticas ingresos |
| `useProducts()` | 60s | Lista productos |
| `useBookings()` | 30s | Reservas |
| `useNurturingSequences()` | 60s | Secuencias nurturing |

---

## 4. SISTEMA DE DATOS

### 4.1 Almacenamiento

| Tipo | Tecnología | Ubicación |
|------|------------|-----------|
| **BD Principal** | PostgreSQL | Railway.app |
| **Fallback** | JSON | `/backend/data/` |
| **ORM** | SQLAlchemy | - |
| **Sincronización** | Bidireccional | `data_sync.py` |

### 4.2 Estructura de Datos

```
backend/data/
├── tone_profiles/{creator_id}.json      # Perfiles de tono
├── content_index/{creator_id}/          # Índice de contenido
│   ├── posts.json
│   └── chunks.json
├── creators/{creator_id}_config.json    # Config creadores
├── products/{creator_id}_products.json  # Catálogo
├── followers/{creator_id}/{fid}.json    # Conversaciones
├── escalations/{creator_id}.jsonl       # Escalaciones (JSON Lines)
├── analytics/{creator_id}_events.json   # Eventos
├── nurturing/{creator_id}_followups.json # Follow-ups
├── payments/{creator_id}_purchases.json # Compras
├── calendar/{creator_id}_*.json         # Booking data
└── gdpr/{creator_id}_*.json             # Consentimientos
```

### 4.3 Formato de Datos Principales

**ToneProfile:**
```json
{
  "creator_id": "string",
  "formality": "informal|formal|mixto",
  "energy": "baja|media|alta",
  "warmth": "cálido|neutro|distante",
  "signature_phrases": ["array"],
  "common_greetings": ["array"],
  "emoji_frequency": "baja|media|alta",
  "confidence_score": 0.0-1.0
}
```

**Follower/Conversation:**
```json
{
  "follower_id": "string",
  "username": "string",
  "purchase_intent_score": 0.0-1.0,
  "is_customer": boolean,
  "products_discussed": ["array"],
  "last_messages": [
    {"role": "user|assistant", "content": "string", "intent": "string"}
  ]
}
```

**Purchase:**
```json
{
  "purchase_id": "pur_xxx",
  "amount": 99.99,
  "currency": "EUR",
  "platform": "stripe|hotmart|paypal|manual",
  "attributed_to_bot": boolean
}
```

### 4.4 Backups

- **Script:** `/backend/scripts/backup.py`
- **Formato:** tar.gz
- **Ubicación:** `/backend/backups/`
- **Retención:** 7 días

---

## 5. INTEGRACIONES

### 5.1 Instagram

| Componente | Archivo | Estado |
|------------|---------|--------|
| OAuth | `oauth.py` | ✅ Implementado |
| Graph API v21.0 | `instagram.py` | ✅ Implementado |
| Webhooks | `instagram_handler.py` | ✅ Implementado |
| DM Send/Receive | `instagram.py` | ✅ Implementado |
| Scraper Captions | `instagram_scraper.py` | ✅ Implementado |

**Variables:**
```
META_APP_ID, META_APP_SECRET
INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_PAGE_ID
INSTAGRAM_APP_SECRET, INSTAGRAM_VERIFY_TOKEN
```

### 5.2 Telegram

| Componente | Archivo | Estado |
|------------|---------|--------|
| Bot Integration | `telegram_adapter.py` | ✅ Implementado |
| Polling Mode | `telegram_adapter.py` | ✅ Implementado |
| Webhook Mode | `telegram_adapter.py` | ✅ Implementado |
| Message Sender | `telegram_sender.py` | ✅ Implementado |
| Alerts | `alerts.py` | ✅ Implementado |

**Variables:**
```
TELEGRAM_BOT_TOKEN
TELEGRAM_WEBHOOK_URL
TELEGRAM_PROXY_URL, TELEGRAM_PROXY_SECRET
```

### 5.3 WhatsApp Business

| Componente | Archivo | Estado |
|------------|---------|--------|
| Cloud API | `whatsapp.py` | ✅ Implementado |
| Send/Receive | `whatsapp.py` | ✅ Implementado |
| Webhooks | `whatsapp.py` | ✅ Implementado |
| Templates | - | ⚠️ Parcial |

**Variables:**
```
WHATSAPP_PHONE_NUMBER_ID
WHATSAPP_ACCESS_TOKEN
WHATSAPP_VERIFY_TOKEN
```

### 5.4 Pagos

| Plataforma | Estado | Webhooks |
|------------|--------|----------|
| **Stripe** | ✅ Completo | checkout.session.completed, payment_intent.succeeded |
| **Hotmart** | ✅ Completo | PURCHASE_COMPLETE, PURCHASE_APPROVED |
| **PayPal** | ⚠️ Básico | payment completion |
| **Bizum** | ✅ Manual | N/A (registro manual) |
| **Transferencia** | ✅ Manual | N/A |

**Variables:**
```
STRIPE_SECRET_KEY
PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET
HOTMART_WEBHOOK_TOKEN
```

### 5.5 Calendarios

| Plataforma | Estado | Webhooks |
|------------|--------|----------|
| **Calendly** | ✅ Completo | invitee.created, invitee.canceled |
| **Cal.com** | ✅ Completo | BOOKING_CREATED, BOOKING_CANCELLED |
| **Google Meet** | ✅ OAuth | Via Calendar API |
| **Zoom** | ✅ OAuth | Meeting creation |
| **Manual** | ✅ Interno | Sistema propio de slots |

**Variables:**
```
CALENDLY_API_KEY
CALCOM_API_KEY
GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
ZOOM_CLIENT_ID, ZOOM_CLIENT_SECRET
```

---

## 6. TESTS

### 6.1 Configuración

- **Framework:** pytest 7.4.0+
- **Async:** pytest-asyncio (auto mode)
- **HTTP:** httpx
- **Ubicación:** `/backend/tests/`

### 6.2 Archivos de Test (30)

| Archivo | Cobertura |
|---------|-----------|
| `test_instagram.py` | Instagram API |
| `test_paypal.py` | PayPal integration |
| `test_content_citation.py` | Citation service |
| `test_reasoning.py` | AI reasoning engine |
| `test_leads_conversations.py` | Lead flow |
| `test_integration.py` | Integration tests |
| `test_rag_bm25.py` | BM25 RAG |
| `test_media_connectors.py` | YouTube, RSS, PDF |
| `test_response_engine_v2.py` | Response generation |
| `test_leads_crud.py` | Lead CRUD |
| `test_nurturing_runner.py` | Nurturing automation |
| `test_pipeline_scoring.py` | Lead scoring |
| `test_products.py` | Product management |
| `test_e2e_flow.py` | End-to-end |
| `test_groq.py` | Groq LLM |
| `test_tone_analyzer.py` | Tone analysis |
| `test_nurturing.py` | Nurturing campaigns |
| `test_dashboard.py` | Dashboard |
| `test_full_flow.py` | Full flow |
| `test_content_indexer.py` | Content indexing |
| `test_health.py` | Health endpoints |
| `test_intent.py` | Intent classification |
| `test_leads.py` | Lead management |
| `test_onboarding_service.py` | Onboarding |

### 6.3 Estadísticas

| Métrica | Valor |
|---------|-------|
| Total archivos | 30 |
| Total funciones test | 419 |
| Líneas de código test | 6,715 |
| Cobertura estimada | 60-80% |

### 6.4 Frontend Tests

- Vitest para unit tests
- Playwright para E2E
- Archivos: Dashboard.test.tsx, Leads.test.tsx, etc.

---

## 7. DEPLOYMENT

### 7.1 Docker

**Dockerfile (multi-stage):**
```dockerfile
# Builder stage
FROM python:3.11-slim AS builder
# ... virtual environment, dependencies

# Runtime stage
FROM python:3.11-slim AS runtime
# Non-root user: clonnect
# Port: 8000
# Healthcheck: /health/live
# Entry: /app/scripts/start.sh
```

### 7.2 Railway

**railway.json:**
```json
{
  "build": {"builder": "DOCKERFILE"},
  "deploy": {
    "healthcheckPath": "/health/live",
    "healthcheckTimeout": 30,
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 3
  }
}
```

### 7.3 Render

**render.yaml:**
- API Web Service (clonnect-creators-api)
- Dashboard (clonnect-dashboard) - Streamlit
- Admin (clonnect-admin) - Streamlit
- Telegram Worker (clonnect-telegram-bot)

### 7.4 Variables de Entorno Requeridas

```env
# REQUERIDAS
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_xxx
CLONNECT_ADMIN_KEY=xxx

# DATABASE
DATABASE_URL=postgresql://...
ENABLE_JSON_FALLBACK=true

# INTEGRACIONES (según uso)
INSTAGRAM_ACCESS_TOKEN=xxx
TELEGRAM_BOT_TOKEN=xxx
STRIPE_SECRET_KEY=xxx
CALENDLY_API_KEY=xxx

# FEATURE FLAGS
ENABLE_GUARDRAILS=true
ENABLE_DEMO_RESET=true
REQUIRE_GDPR_CONSENT=true
```

### 7.5 CI/CD

**GitHub Actions:**
- `auto-merge-claude.yml`: Auto-merge ramas `claude/**` a main
- **Gap:** No hay workflow de tests automáticos

---

## 8. GAPS Y DEUDA TÉCNICA

### 8.1 Código Incompleto

| Área | Issue | Prioridad |
|------|-------|-----------|
| **WhatsApp Templates** | Soporte parcial de message templates | Media |
| **PayPal OAuth** | Integración básica, falta refresh token | Media |
| **Email Notifications** | RESEND_API_KEY configurado pero poco usado | Baja |
| **Zoom Webhooks** | Solo OAuth, no webhooks de meeting events | Baja |

### 8.2 Mejoras Necesarias

| Área | Issue | Prioridad |
|------|-------|-----------|
| **CI/CD Tests** | No hay workflow para ejecutar pytest antes de merge | Alta |
| **Coverage Reports** | No hay pytest-cov ni reportes de cobertura | Alta |
| **API Rate Limiting** | RateLimiter existe pero no está aplicado globalmente | Media |
| **Error Monitoring** | No hay Sentry ni similar configurado | Media |
| **Logging Centralizado** | Logs solo en stdout, no hay agregación | Media |
| **API Versioning** | No hay versionado de API (/v1/, /v2/) | Baja |
| **OpenAPI Docs** | Swagger UI disponible pero sin ejemplos completos | Baja |

### 8.3 Hardcodeado

| Elemento | Ubicación | Descripción |
|----------|-----------|-------------|
| `DEFAULT_CREATOR_ID="manel"` | Múltiples archivos | ID de demo hardcodeado |
| `FRONTEND_URL` | `.env.example` | URL de producción hardcodeada |
| `API_URL` en frontend | `.env.production` | URL Railway hardcodeada |
| Textos UI | Páginas `/new/*` | Textos en español sin i18n |
| `50 leads goal` | Dashboard.tsx | Meta hardcodeada |

### 8.4 Seguridad

| Issue | Estado | Prioridad |
|-------|--------|-----------|
| CORS `allow_origins: *` | ⚠️ Abierto | Alta (producción) |
| API keys en JSON | ⚠️ Sin encriptar en disco | Media |
| HMAC verification | ✅ Implementado | - |
| JWT tokens | ✅ Implementado | - |
| Rate limiting | ⚠️ Parcial | Media |

### 8.5 Escalabilidad

| Issue | Estado | Recomendación |
|-------|--------|---------------|
| JSON fallback | En uso | Migrar 100% a PostgreSQL |
| Sync bidireccional | Complejo | Eliminar duplicación |
| Single replica | Railway | Configurar auto-scaling |
| No Redis | - | Agregar para cache/sessions |
| No queue | - | Agregar Celery/RQ para async |

### 8.6 Testing

| Gap | Recomendación |
|-----|---------------|
| No CI tests | Agregar workflow pytest |
| No coverage | Agregar pytest-cov |
| No load tests | Agregar Locust |
| Frontend E2E | Expandir Playwright tests |

---

## 9. ARQUITECTURA RECOMENDADA

### Diagrama de Flujo Actual

```
┌─────────────────────────────────────────────────────────┐
│                    EXTERNAL CHANNELS                     │
├─────────────────────────────────────────────────────────┤
│   Instagram DM   │   Telegram   │   WhatsApp   │  API   │
└────────┬─────────────────┬──────────────┬────────┬──────┘
         │                 │              │        │
         └─────────────────┴──────────────┴────────┘
                           │
                    WEBHOOKS/POLLING
                           │
         ┌─────────────────▼─────────────────┐
         │         FastAPI Application       │
         │         (19 routers, 114 endpoints)│
         └─────────────────┬─────────────────┘
                           │
         ┌─────────────────▼─────────────────┐
         │           Core Services           │
         │  ┌─────────────────────────────┐  │
         │  │ DMResponderAgent (LLM)      │  │
         │  │ IntentClassifier            │  │
         │  │ CitationService (RAG)       │  │
         │  │ ToneService                 │  │
         │  │ Guardrails                  │  │
         │  └─────────────────────────────┘  │
         └─────────────────┬─────────────────┘
                           │
         ┌────────┬────────┴────────┬────────┐
         │        │                 │        │
    ┌────▼───┐ ┌──▼───┐ ┌──────────▼──────┐ │
    │PostgreSQL│ │JSON │ │External Services│ │
    │(Railway) │ │Files│ │ (LLM, OAuth)   │ │
    └──────────┘ └─────┘ └─────────────────┘ │
```

---

## 10. PRÓXIMOS PASOS RECOMENDADOS

### Prioridad Alta
1. [ ] Agregar workflow CI/CD para tests antes de merge
2. [ ] Restringir CORS en producción
3. [ ] Implementar pytest-cov para coverage reports
4. [ ] Eliminar DEFAULT_CREATOR_ID hardcodeado

### Prioridad Media
1. [ ] Agregar Sentry para error monitoring
2. [ ] Implementar Redis para cache
3. [ ] Completar integración PayPal OAuth
4. [ ] Agregar rate limiting global

### Prioridad Baja
1. [ ] Internacionalización (i18n) del frontend
2. [ ] Versionado de API
3. [ ] Documentación OpenAPI completa
4. [ ] Load testing con Locust

---

## CONCLUSIÓN

CLONNECT es una **plataforma madura y funcional** con:
- Arquitectura sólida (FastAPI + React + PostgreSQL)
- Múltiples integraciones operativas
- Sistema de IA avanzado con reasoning
- Cobertura de tests moderada-buena

Los principales gaps son de **operaciones/DevOps** (CI/CD, monitoring) más que de funcionalidad. El sistema está listo para producción con mejoras incrementales.

---

*Documento generado automáticamente por Claude Code*
*Última actualización: 2026-01-06*
