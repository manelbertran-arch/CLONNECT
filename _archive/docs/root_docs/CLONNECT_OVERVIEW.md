# CLONNECT - Auditoría Técnica Completa

> **Resumen Ejecutivo**: Clonnect es una plataforma SaaS que permite a **creadores de contenido** automatizar la atención de mensajes directos (DMs) en Instagram, WhatsApp y Telegram mediante un **clon de IA personalizado** que responde en su tono y estilo, gestiona leads, programa citas y cierra ventas de sus productos/servicios digitales.

---

## Tabla de Contenidos

1. [Arquitectura General](#arquitectura-general)
2. [Stack Tecnológico](#stack-tecnológico)
3. [Módulos del Backend](#módulos-del-backend)
4. [Frontend (Dashboard)](#frontend-dashboard)
5. [APIs y Endpoints](#apis-y-endpoints)
6. [Flujo Completo del Usuario](#flujo-completo-del-usuario)
7. [Integraciones Externas](#integraciones-externas)
8. [Base de Datos](#base-de-datos)
9. [Estado de Producción](#estado-de-producción)

---

## Arquitectura General

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CLONNECT ARCHITECTURE                              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                 │
│   │  Instagram   │    │   WhatsApp   │    │   Telegram   │                 │
│   │   Webhook    │    │   Webhook    │    │   Webhook    │                 │
│   └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                 │
│          │                   │                   │                          │
│          └───────────────────┼───────────────────┘                          │
│                              ▼                                               │
│                    ┌──────────────────┐                                     │
│                    │   FastAPI App    │                                     │
│                    │    (main.py)     │                                     │
│                    └────────┬─────────┘                                     │
│                             │                                               │
│          ┌──────────────────┼──────────────────┐                           │
│          ▼                  ▼                  ▼                            │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                      │
│   │ DM Agent    │   │   RAG       │   │  Copilot    │                      │
│   │ (LLM Core)  │   │ (Knowledge) │   │  Service    │                      │
│   └─────────────┘   └─────────────┘   └─────────────┘                      │
│          │                  │                  │                            │
│          ▼                  ▼                  ▼                            │
│   ┌─────────────────────────────────────────────────┐                      │
│   │              PostgreSQL Database                 │                      │
│   │  (Creators, Leads, Messages, Products, etc.)    │                      │
│   └─────────────────────────────────────────────────┘                      │
│                                                                              │
│   ┌─────────────────────────────────────────────────┐                      │
│   │              React Dashboard (SPA)               │                      │
│   │  - Inbox    - Leads    - Settings   - Analytics │                      │
│   └─────────────────────────────────────────────────┘                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Stack Tecnológico

### Backend
| Componente | Tecnología |
|------------|------------|
| Framework | FastAPI (Python 3.11+) |
| Base de datos | PostgreSQL |
| ORM | SQLAlchemy |
| LLM | Groq (llama3-70b-8192, llama3-8b-8192) |
| RAG | Sentence Transformers + FAISS |
| Cache | In-memory (con opción Redis) |
| Métricas | Prometheus (opcional) |
| Deploy | Railway / Render |

### Frontend
| Componente | Tecnología |
|------------|------------|
| Framework | React 18 + TypeScript |
| Build Tool | Vite |
| Styling | Tailwind CSS + shadcn/ui |
| State | React Query (TanStack Query) |
| Router | React Router v6 |
| Testing | Vitest |

---

## Módulos del Backend

### 1. DM Agent (`core/dm_agent.py`)
**El corazón del sistema** - Agente de IA que responde mensajes directos.

**Funcionalidades:**
- Clasificación de intención (Intent Classification)
- Generación de respuestas personalizadas con LLM
- Manejo de objeciones de venta
- Detección de idioma y voseo argentino
- Respuestas basadas en contexto RAG
- Rate limiting para evitar spam
- Escalación a humano cuando necesario

**Intenciones soportadas:**
```python
class Intent(Enum):
    GREETING = "greeting"
    INTEREST_SOFT = "interest_soft"
    INTEREST_STRONG = "interest_strong"
    OBJECTION_PRICE = "objection_price"
    OBJECTION_TIME = "objection_time"
    OBJECTION_DOUBT = "objection_doubt"
    QUESTION_PRODUCT = "question_product"
    QUESTION_GENERAL = "question_general"
    BOOKING = "booking"
    SUPPORT = "support"
    ESCALATION = "escalation"
    # ... más
```

### 2. RAG System (`core/rag/`)
Sistema de Retrieval-Augmented Generation para respuestas basadas en conocimiento.

**Componentes:**
- `semantic.py` - SimpleRAG con embeddings (sentence-transformers)
- `bm25.py` - BM25RAG para búsqueda por keywords
- HybridRAG - Combina semántico + BM25

**Uso:**
- Indexa posts de Instagram del creador
- Indexa páginas web del creador
- Indexa FAQs personalizadas
- Proporciona contexto relevante al LLM

### 3. Copilot Service (`core/copilot_service.py`)
Modo de aprobación humana antes de enviar respuestas.

**Funcionalidades:**
- Guardar respuestas como "pending_approval"
- Panel para aprobar/editar/descartar
- Notificaciones de mensajes pendientes
- Calcular purchase_intent del lead

### 4. Nurturing System (`core/nurturing.py`)
Follow-ups automáticos para leads que no convirtieron.

**Secuencias:**
- `INTEREST_COLD` - Interés sin conversión
- `OBJECTION_PRICE` - Objeción de precio
- `OBJECTION_TIME` - Objeción de tiempo
- `ABANDONED` - Carrito abandonado
- `RE_ENGAGEMENT` - Sin actividad en X días
- `POST_PURCHASE` - Después de compra

### 5. Tone Service (`core/tone_service.py`)
Perfiles de tono personalizados por creador.

**Funcionalidades:**
- Analiza posts de Instagram para extraer estilo
- Genera ToneProfile con vocabulario, muletillas, emojis
- Soporta dialectos (español neutro, voseo argentino)
- Guía al LLM para responder en el tono del creador

### 6. Calendar/Booking (`core/calendar.py`)
Sistema de reservas de citas.

**Funcionalidades:**
- Crear links de booking (discovery, coaching, etc.)
- Gestión de disponibilidad semanal
- Integración con Calendly, Google Calendar
- Envío automático de Google Meet links

### 7. Payments (`core/payments.py`)
Gestión de pagos y tracking de ventas.

**Integraciones:**
- Stripe
- PayPal
- Hotmart
- Métodos alternativos (Bizum, transferencia)

### 8. Intent Classifier (`core/intent_classifier.py`)
Clasificador de intención usando LLM o patrones rápidos.

**Salidas:**
```python
@dataclass
class IntentResult:
    intent: Intent
    confidence: float
    sub_intent: str
    entities: List[str]
    suggested_action: str
```

### 9. Instagram Handler (`core/instagram_handler.py`)
Maneja webhooks de Instagram Graph API.

**Funcionalidades:**
- Recibe mensajes de Instagram DMs
- Envía respuestas via API
- Verifica firma de webhooks

### 10. WhatsApp Handler (`core/whatsapp.py`)
Maneja webhooks de WhatsApp Business API.

### 11. Telegram Adapter (`core/telegram_adapter.py`)
Integración con Telegram Bot API.

### 12. GDPR Manager (`core/gdpr.py`)
Cumplimiento de normativa europea.

**Funcionalidades:**
- Gestión de consentimientos
- Exportación de datos del usuario
- Eliminación de datos (derecho al olvido)

### 13. Analytics (`core/analytics/`)
Sistema de métricas y tracking.

**Métricas:**
- Mensajes procesados por día
- Tasa de conversión
- Revenue por follower
- Tiempo de respuesta

### 14. Ingestion V2 (`ingestion/v2/`)
Sistema de extracción de productos **zero hallucinations**.

**Componentes:**
- `ProductDetector` - Detección por señales (3+ requeridas)
- `SanityChecker` - Verificación de resultados
- `Pipeline` - Orquestador principal

**Principio:** Si no puede PROBAR que es real, NO EXISTE.

---

## Frontend (Dashboard)

### Páginas Principales

| Página | Ruta | Descripción |
|--------|------|-------------|
| Login | `/login` | Autenticación de usuarios |
| Onboarding | `/onboarding` | Setup inicial del creador |
| Dashboard | `/dashboard` | Vista general, métricas |
| Inbox | `/inbox` | Bandeja de mensajes |
| Leads | `/leads` | Gestión de leads/contactos |
| Products | `/products` | Catálogo de productos |
| Nurturing | `/nurturing` | Secuencias de follow-up |
| Bookings | `/bookings` | Calendario de citas |
| Settings | `/settings` | Configuración del bot |
| Copilot | `/copilot` | Panel de aprobación |

### Componentes Principales

```
frontend/src/
├── pages/
│   ├── Login.tsx
│   ├── Onboarding.tsx
│   ├── Dashboard.tsx
│   ├── Inbox.tsx
│   ├── Leads.tsx
│   ├── Products.tsx
│   ├── Nurturing.tsx
│   ├── Bookings.tsx
│   ├── Settings.tsx
│   └── new/           # Nueva UI
├── components/
│   ├── layout/
│   ├── ui/            # shadcn components
│   └── CopilotPanel.tsx
├── services/
│   └── api.ts         # API client
└── context/
    └── AuthContext.tsx
```

---

## APIs y Endpoints

### Autenticación (`/auth`)
```
POST /auth/register      - Registrar usuario
POST /auth/login         - Login y obtener token
GET  /auth/me            - Info del usuario actual
POST /auth/link-creator  - Vincular creador al usuario
```

### Dashboard (`/dashboard`)
```
GET  /{creator_id}/overview   - Métricas generales
PUT  /{creator_id}/toggle     - Activar/desactivar bot
```

### Leads (`/leads`)
```
GET  /{creator_id}            - Listar leads
GET  /{creator_id}/{lead_id}  - Detalle de lead
POST /{creator_id}            - Crear lead
POST /{creator_id}/manual     - Crear lead manual
PUT  /{creator_id}/{lead_id}  - Actualizar lead
DELETE /{creator_id}/{lead_id} - Eliminar lead
```

### Mensajes (`/messages`)
```
GET  /metrics/{creator_id}                    - Métricas de mensajes
GET  /follower/{creator_id}/{follower_id}     - Historial de conversación
POST /send/{creator_id}                       - Enviar mensaje
GET  /conversations/{creator_id}              - Lista de conversaciones
```

### Productos (`/products`)
```
GET    /{creator_id}/products              - Listar productos
POST   /{creator_id}/products              - Crear producto
PUT    /{creator_id}/products/{product_id} - Actualizar producto
DELETE /{creator_id}/products/{product_id} - Eliminar producto
```

### Nurturing (`/nurturing`)
```
GET  /{creator_id}/sequences                    - Listar secuencias
GET  /{creator_id}/followups                    - Follow-ups pendientes
GET  /{creator_id}/stats                        - Estadísticas
POST /{creator_id}/sequences/{type}/toggle      - Activar/desactivar
PUT  /{creator_id}/sequences/{type}             - Configurar secuencia
POST /{creator_id}/run                          - Ejecutar nurturing
```

### Calendar/Booking (`/calendar`, `/booking`)
```
GET  /{creator_id}/bookings       - Listar reservas
GET  /{creator_id}/links          - Links de booking
POST /{creator_id}/links          - Crear link de booking
GET  /availability/{creator_id}   - Disponibilidad
POST /{creator_id}/reserve        - Reservar cita
```

### Onboarding (`/onboarding`)
```
GET  /{creator_id}/status         - Estado del onboarding
GET  /{creator_id}/visual-status  - Estado visual
POST /{creator_id}/complete       - Marcar completado
POST /manual-setup                - Setup manual (scrapea Instagram)
POST /scrape-instagram            - Scrapear posts
```

### Copilot (`/copilot`)
```
GET  /{creator_id}/pending        - Mensajes pendientes
POST /{creator_id}/approve/{id}   - Aprobar mensaje
POST /{creator_id}/discard/{id}   - Descartar mensaje
GET  /{creator_id}/status         - Estado del copilot
PUT  /{creator_id}/toggle         - Activar/desactivar modo copilot
```

### Tone (`/tone`)
```
GET  /profiles               - Listar perfiles de tono
GET  /{creator_id}           - Obtener perfil de tono
POST /generate               - Generar perfil desde posts
GET  /{creator_id}/prompt    - Obtener prompt de tono
```

### Knowledge (`/knowledge`)
```
GET  /{creator_id}/knowledge        - Base de conocimiento
GET  /{creator_id}/knowledge/faqs   - FAQs
POST /{creator_id}/knowledge/faqs   - Crear FAQ
GET  /{creator_id}/knowledge/about  - Info "Sobre mí"
```

### OAuth (`/oauth`)
```
GET /instagram/start    - Iniciar OAuth Instagram
GET /instagram/callback - Callback Instagram
GET /whatsapp/start     - Iniciar OAuth WhatsApp
GET /stripe/start       - Iniciar OAuth Stripe
GET /google/start       - Iniciar OAuth Google
GET /status/{creator_id} - Estado de conexiones
```

### Ingestion V2 (`/ingestion/v2`)
```
POST /website             - Ingestar productos desde web
GET  /test/{creator_id}   - Test de ingestion
DELETE /clear/{creator_id} - Limpiar productos
```

### Webhooks
```
POST /webhook/instagram   - Webhook de Instagram
POST /webhook/whatsapp    - Webhook de WhatsApp
POST /webhook/telegram    - Webhook de Telegram
POST /webhook/stripe      - Webhook de Stripe
POST /webhook/calendly    - Webhook de Calendly
```

---

## Flujo Completo del Usuario

### 1. Registro y Onboarding del Creador

```
┌─────────────────────────────────────────────────────────────────┐
│                     ONBOARDING FLOW                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Usuario visita /login                                        │
│     ↓                                                            │
│  2. Login con email/password                                     │
│     ↓                                                            │
│  3. Si onboarding_completed=false → /onboarding                  │
│     ↓                                                            │
│  4. Introduce Instagram username + website (opcional)            │
│     ↓                                                            │
│  5. POST /onboarding/manual-setup                                │
│     │                                                            │
│     ├── Scrapea 50 posts de Instagram                           │
│     ├── Genera ToneProfile (análisis de estilo)                 │
│     ├── Indexa posts en RAG                                     │
│     └── Scrapea website para productos                          │
│     ↓                                                            │
│  6. onboarding_completed = true                                  │
│     ↓                                                            │
│  7. Redirige a /dashboard                                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Conexión de Instagram

```
1. Creador va a Settings → Conexiones → Instagram
2. Click "Conectar Instagram"
3. OAuth flow con Meta (Facebook Login)
4. Callback guarda token en creators.instagram_token
5. Bot puede recibir/enviar DMs
```

### 3. Flujo de un Mensaje Entrante

```
┌─────────────────────────────────────────────────────────────────┐
│                     MESSAGE FLOW                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Follower envía DM en Instagram                               │
│     ↓                                                            │
│  2. Instagram envía webhook a /webhook/instagram                 │
│     ↓                                                            │
│  3. InstagramHandler parsea el mensaje                           │
│     ↓                                                            │
│  4. Se crea/actualiza Lead en DB                                 │
│     ↓                                                            │
│  5. DMResponderAgent procesa el mensaje:                         │
│     │                                                            │
│     ├── a) Clasifica intención (greeting, interest, etc.)        │
│     │                                                            │
│     ├── b) Busca contexto en RAG (posts, FAQs, productos)        │
│     │                                                            │
│     ├── c) Genera respuesta con LLM (Groq)                       │
│     │      - Usa ToneProfile del creador                         │
│     │      - Incluye productos relevantes                        │
│     │      - Maneja objeciones                                   │
│     │                                                            │
│     └── d) Aplica guardrails (no dar teléfono, etc.)             │
│     ↓                                                            │
│  6. Si copilot_mode = true:                                      │
│     │                                                            │
│     ├── Guarda como "pending_approval"                           │
│     └── Notifica al creador en dashboard                         │
│     ↓                                                            │
│  7. Si copilot_mode = false O creador aprueba:                   │
│     │                                                            │
│     └── Envía respuesta via Instagram API                        │
│     ↓                                                            │
│  8. Guarda mensaje en DB                                         │
│     ↓                                                            │
│  9. Actualiza métricas (analytics)                               │
│     ↓                                                            │
│  10. Si aplica, programa nurturing follow-up                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4. Flujo de Venta

```
1. Follower pregunta por producto
2. Bot detecta INTEREST_STRONG
3. Bot responde con info del producto + link de pago
4. Follower compra (Stripe/PayPal)
5. Webhook de pago confirma compra
6. Lead se actualiza a status="customer"
7. Se programa secuencia POST_PURCHASE
```

### 5. Flujo de Booking

```
1. Follower quiere agendar llamada
2. Bot detecta intent BOOKING
3. Bot envía link de Calendly/Google Calendar
4. Follower elige fecha/hora
5. Webhook confirma reserva
6. Se crea CalendarBooking en DB
7. Se envía confirmación + link de Google Meet
```

---

## Integraciones Externas

### Canales de Comunicación

| Plataforma | API | Estado |
|------------|-----|--------|
| Instagram | Graph API (Meta) | ✅ Producción |
| WhatsApp | Business API (Meta) | ✅ Producción |
| Telegram | Bot API | ✅ Producción |

### Pagos

| Plataforma | Tipo | Estado |
|------------|------|--------|
| Stripe | OAuth + Webhooks | ✅ Producción |
| PayPal | OAuth + IPN | ✅ Producción |
| Hotmart | Webhooks | ✅ Producción |

### Calendario

| Plataforma | Tipo | Estado |
|------------|------|--------|
| Calendly | OAuth + Webhooks | ✅ Producción |
| Google Calendar | OAuth | ✅ Producción |
| Cal.com | Webhooks | 🔄 Parcial |

### LLM

| Proveedor | Modelo | Uso |
|-----------|--------|-----|
| Groq | llama3-70b-8192 | Respuestas principales |
| Groq | llama3-8b-8192 | Clasificación de intención |

---

## Base de Datos

### Tablas Principales

```sql
-- Usuarios del sistema (creadores)
users (id, email, password_hash, name, is_active, is_admin)

-- Creadores (cuentas de negocio)
creators (
    id, name, email, api_key,
    bot_active, copilot_mode, onboarding_completed,
    -- Configuración del clon
    clone_tone, clone_style, clone_name, welcome_message,
    -- Conexiones de canales
    instagram_token, instagram_page_id,
    whatsapp_token, whatsapp_phone_id,
    telegram_bot_token,
    -- Conexiones de pago
    stripe_api_key, paypal_token, hotmart_token,
    -- Conexiones de calendario
    calendly_token, google_access_token,
    -- Extras
    knowledge_about, email_capture_config
)

-- Relación Users <-> Creators
user_creators (id, user_id, creator_id, role)

-- Leads (contactos/followers)
leads (
    id, creator_id, platform, platform_user_id,
    username, full_name, status, score, purchase_intent,
    context, first_contact_at, last_contact_at
)

-- Mensajes
messages (
    id, lead_id, role, content, intent,
    status, suggested_response, approved_at, approved_by
)

-- Productos
products (
    id, creator_id, name, description,
    price, currency, payment_link, is_active
)

-- Secuencias de nurturing
nurturing_sequences (id, creator_id, type, name, is_active, steps)

-- Follow-ups programados
nurturing_followups (
    id, creator_id, follower_id, sequence_type,
    step, scheduled_at, message_template, status
)

-- Base de conocimiento (FAQs)
knowledge_base (id, creator_id, question, answer)

-- Links de booking
booking_links (
    id, creator_id, meeting_type, title, description,
    duration_minutes, platform, url, price, is_active
)

-- Reservas de calendario
calendar_bookings (
    id, creator_id, follower_id, meeting_type,
    platform, status, scheduled_at, duration_minutes,
    guest_name, guest_email, meeting_url
)

-- Disponibilidad del creador
creator_availability (
    id, creator_id, day_of_week,
    start_time, end_time, is_active
)

-- Tone profiles
tone_profiles (id, creator_id, tone_data, created_at)
```

---

## Estado de Producción

### Módulos en Producción ✅

| Módulo | Estado | Notas |
|--------|--------|-------|
| DM Agent | ✅ Producción | Core funcional |
| RAG System | ✅ Producción | Semantic + BM25 |
| Copilot Mode | ✅ Producción | Aprobación humana |
| Nurturing | ✅ Producción | Follow-ups automáticos |
| Instagram Handler | ✅ Producción | DMs funcionando |
| WhatsApp Handler | ✅ Producción | Mensajes funcionando |
| Telegram Handler | ✅ Producción | Bot funcionando |
| Stripe Integration | ✅ Producción | Pagos funcionando |
| Calendly Integration | ✅ Producción | Bookings funcionando |
| Frontend Dashboard | ✅ Producción | React SPA |
| Onboarding Flow | ✅ Producción | Setup manual |
| Ingestion V2 | ✅ Nuevo | Zero hallucinations |

### Módulos en Desarrollo 🔄

| Módulo | Estado | Notas |
|--------|--------|-------|
| Google Calendar | 🔄 Parcial | OAuth funciona, Meet parcial |
| Cal.com | 🔄 Parcial | Webhooks básicos |
| Email Capture | 🔄 Parcial | Flujo básico implementado |
| Analytics Dashboard | 🔄 Parcial | Métricas básicas |

### Pendientes 📋

| Módulo | Prioridad |
|--------|-----------|
| Multi-idioma dashboard | Media |
| App móvil | Baja |
| Facturación/Suscripciones | Alta |
| Dashboard de métricas avanzado | Media |

---

## Configuración de Entorno

### Variables de Entorno Requeridas

```bash
# Base de datos
DATABASE_URL=postgresql://...

# LLM
GROQ_API_KEY=gsk_...

# Instagram/Meta
META_APP_ID=...
META_APP_SECRET=...
INSTAGRAM_VERIFY_TOKEN=...

# WhatsApp
WHATSAPP_VERIFY_TOKEN=...

# Stripe
STRIPE_API_KEY=sk_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Calendly
CALENDLY_CLIENT_ID=...
CALENDLY_CLIENT_SECRET=...

# Google (Calendar/Meet)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# JWT
JWT_SECRET=...

# Frontend
VITE_API_URL=https://api.clonnect.io
```

---

## Cómo Ejecutar

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
cd backend
pytest tests/ -v
```

---

## Métricas Clave

- **Mensajes procesados/día**: ~500-1000 por creador activo
- **Tiempo de respuesta LLM**: ~1-2 segundos
- **Tasa de conversión**: Variable por creador (~5-15%)
- **Uptime**: 99.5% (Railway)

---

## Conclusión

Clonnect es una plataforma completa de automatización de DMs para creadores de contenido que incluye:

1. **Bot de IA personalizado** que responde en el tono del creador
2. **Sistema RAG** para respuestas basadas en contenido real
3. **Gestión de leads** con scoring automático
4. **Nurturing automatizado** para follow-ups
5. **Integraciones de pago** (Stripe, PayPal, Hotmart)
6. **Sistema de booking** (Calendly, Google Calendar)
7. **Modo Copilot** para aprobación humana
8. **Dashboard completo** para gestión

El sistema está en producción y es utilizado por creadores de contenido para automatizar su atención al cliente y ventas.

---

*Documento generado el 9 de Enero de 2026*
*Versión: API Main V7*
