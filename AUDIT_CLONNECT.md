# AUDITORÍA COMPLETA: CLONNECT CREATORS

**Generado:** 2025-12-27
**Repositorio:** clonnect-creators
**Líneas de código Backend:** ~34,275
**Líneas de código Frontend:** ~13,436
**Total:** ~47,700 líneas

---

## 1. RESUMEN EJECUTIVO

**Clonnect Creators** es una plataforma SaaS para automatizar DMs de creadores de contenido con IA. Permite a los creadores gestionar conversaciones automáticas con sus seguidores, clasificar leads, manejar objeciones y procesar ventas.

### Capacidades Principales:
- **Automatización de DMs** en Instagram, Telegram y WhatsApp
- **Clasificación de intents** con LLM (Groq/OpenAI/Anthropic)
- **Pipeline de leads** con scoring automático
- **Sistema de nurturing** con secuencias de follow-up
- **Personalidad del creador** configurable (tono, estilo, vocabulario)
- **Gestión de productos** con manejo de objeciones
- **Integraciones de pago** (Stripe, Hotmart)
- **Integraciones de calendario** (Calendly, Cal.com)
- **RAG básico** con embeddings para FAQ
- **GDPR compliance** (export, delete, anonymize)
- **Dashboard React** responsive

### Stack Tecnológico:
| Capa | Tecnologías |
|------|-------------|
| Backend | FastAPI, Python 3.11+, SQLAlchemy, PostgreSQL |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui |
| LLM | Groq (Llama 3.3 70B), OpenAI, Anthropic |
| Embeddings | sentence-transformers, FAISS |
| Mensajería | Meta Graph API (IG), python-telegram-bot, WhatsApp Cloud API |
| Pagos | Stripe, Hotmart webhooks |
| Deploy | Railway (backend), Vercel (frontend) |

---

## 2. ESTRUCTURA DEL PROYECTO

### 2.1 Archivos Python (Backend)

#### Core (Lógica de negocio)
```
backend/core/dm_agent.py          - Agente principal de procesamiento de DMs (~800 líneas)
backend/core/intent_classifier.py - Clasificador de intención con LLM (~380 líneas)
backend/core/llm.py               - Cliente LLM multi-provider (Groq/OpenAI/Anthropic) (~140 líneas)
backend/core/instagram.py         - Connector Instagram Meta Graph API
backend/core/instagram_handler.py - Handler de webhooks Instagram (~560 líneas)
backend/core/telegram_adapter.py  - Adapter Telegram Bot (~550 líneas)
backend/core/telegram_sender.py   - Envío de mensajes Telegram
backend/core/whatsapp.py          - Connector y Handler WhatsApp (~770 líneas)
backend/core/memory.py            - Sistema de memoria de followers (~200 líneas)
backend/core/products.py          - Gestión de productos y objeciones (~450 líneas)
backend/core/nurturing.py         - Sistema de follow-ups automáticos (~408 líneas)
backend/core/rag.py               - RAG simplificado con FAISS (~160 líneas)
backend/core/payments.py          - Integración Stripe/Hotmart (~800 líneas)
backend/core/calendar.py          - Integración Calendly/Cal.com (~500 líneas)
backend/core/gdpr.py              - GDPR compliance (export/delete) (~860 líneas)
backend/core/auth.py              - Sistema de API keys (~338 líneas)
backend/core/analytics.py         - Tracking de eventos y métricas
backend/core/alerts.py            - Sistema de alertas
backend/core/cache.py             - Cache de respuestas
backend/core/creator_config.py    - Configuración de creadores
backend/core/guardrails.py        - Guardrails de seguridad
backend/core/i18n.py              - Internacionalización (es/en/pt)
backend/core/metrics.py           - Métricas Prometheus
backend/core/notifications.py     - Notificaciones y escalación
backend/core/query_expansion.py   - Expansión de queries RAG
backend/core/rate_limiter.py      - Rate limiting
backend/core/sales_tracker.py     - Tracking de ventas
```

#### API (FastAPI Routers)
```
backend/api/main.py               - Entry point API (~2800 líneas)
backend/api/models.py             - Modelos SQLAlchemy (~90 líneas)
backend/api/database.py           - Configuración PostgreSQL
backend/api/db_service.py         - Servicio de base de datos
backend/api/routers/health.py     - Health checks
backend/api/routers/dashboard.py  - Dashboard overview
backend/api/routers/config.py     - Configuración creador
backend/api/routers/leads.py      - CRUD de leads
backend/api/routers/products.py   - CRUD de productos
backend/api/routers/messages.py   - Conversaciones y mensajes
backend/api/routers/nurturing.py  - Secuencias de nurturing
backend/api/routers/payments.py   - Revenue y compras
backend/api/routers/calendar.py   - Bookings y links
backend/api/routers/knowledge.py  - Knowledge base/FAQ
backend/api/routers/analytics.py  - Sales analytics
backend/api/routers/connections.py - Conexiones de canales
backend/api/routers/oauth.py      - OAuth flows (IG, Stripe, etc.)
backend/api/routers/onboarding.py - Onboarding wizard
backend/api/routers/admin.py      - Admin endpoints
```

#### Tests
```
backend/tests/test_full_flow.py        - Tests E2E completos (~18K líneas)
backend/tests/test_e2e_flow.py         - Tests de flujo E2E
backend/tests/test_nurturing.py        - Tests de nurturing
backend/tests/test_nurturing_runner.py - Tests del runner
backend/tests/test_intent.py           - Tests clasificación intent
backend/tests/test_instagram.py        - Tests Instagram handler
backend/tests/test_groq.py             - Tests cliente Groq
backend/tests/test_products.py         - Tests productos
backend/tests/test_leads_crud.py       - Tests CRUD leads
backend/tests/test_db_messages.py      - Tests mensajes DB
backend/tests/test_kanban_status.py    - Tests estados kanban
backend/tests/test_pipeline_scoring.py - Tests scoring leads
```

### 2.2 Archivos Frontend (React/TypeScript)

#### Páginas
```
frontend/src/pages/Dashboard.tsx   - Dashboard principal con métricas
frontend/src/pages/Inbox.tsx       - Bandeja de conversaciones
frontend/src/pages/Leads.tsx       - Kanban de leads
frontend/src/pages/Calendar.tsx    - Gestión de citas
frontend/src/pages/Nurturing.tsx   - Secuencias de nurturing
frontend/src/pages/Revenue.tsx     - Tracking de ingresos
frontend/src/pages/Settings.tsx    - Configuración (personalidad, productos, FAQ)
frontend/src/pages/Index.tsx       - Landing page
frontend/src/pages/Docs.tsx        - Documentación
```

#### Componentes
```
frontend/src/components/layout/DashboardLayout.tsx - Layout principal
frontend/src/components/layout/Sidebar.tsx         - Sidebar navegación
frontend/src/components/layout/MobileNav.tsx       - Navegación móvil
frontend/src/components/OnboardingChecklist.tsx    - Wizard onboarding
frontend/src/components/ui/*                       - Componentes shadcn/ui
```

#### Servicios
```
frontend/src/services/api.ts       - Cliente API
frontend/src/hooks/useApi.ts       - Hook para API calls
frontend/src/types/api.ts          - TypeScript types
```

### 2.3 Dependencias Principales

#### Backend (requirements.txt)
| Paquete | Uso | Costo |
|---------|-----|-------|
| fastapi | Framework API | FREE |
| uvicorn | ASGI server | FREE |
| pydantic | Validación datos | FREE |
| sqlalchemy | ORM | FREE |
| psycopg2-binary | PostgreSQL driver | FREE |
| openai | Cliente OpenAI | PAID ($) |
| anthropic | Cliente Anthropic | PAID ($$$) |
| groq | Cliente Groq (Llama) | FREE |
| aiohttp | HTTP async client | FREE |
| sentence-transformers | Embeddings | FREE |
| faiss-cpu | Vector search | FREE |
| python-telegram-bot | Telegram bot | FREE |
| streamlit | Dashboard admin | FREE |
| pytest | Testing | FREE |

#### Frontend (package.json)
| Paquete | Uso | Costo |
|---------|-----|-------|
| react | UI Framework | FREE |
| react-router-dom | Routing | FREE |
| @tanstack/react-query | Data fetching | FREE |
| tailwindcss | Styling | FREE |
| shadcn/ui (radix) | UI components | FREE |
| recharts | Charts | FREE |
| lucide-react | Icons | FREE |
| zod | Validation | FREE |
| react-hook-form | Forms | FREE |
| vitest | Testing | FREE |

### 2.4 Variables de Entorno

#### Obligatorias
```bash
DATABASE_URL=postgresql://... (Obligatoria - Conexión PostgreSQL)
GROQ_API_KEY=gsk_...         (Obligatoria - LLM por defecto)
```

#### Instagram (Obligatorias para IG)
```bash
INSTAGRAM_ACCESS_TOKEN=...    (Obligatoria - Token Meta Graph API)
INSTAGRAM_PAGE_ID=...         (Obligatoria - Facebook Page ID)
INSTAGRAM_USER_ID=...         (Obligatoria - IG Business Account ID)
INSTAGRAM_APP_SECRET=...      (Opcional - Verificación webhooks)
INSTAGRAM_VERIFY_TOKEN=...    (Opcional - Webhook verification)
```

#### Telegram (Opcional)
```bash
TELEGRAM_BOT_TOKEN=...        (Opcional - Bot token de BotFather)
TELEGRAM_WEBHOOK_URL=...      (Opcional - URL webhook producción)
```

#### WhatsApp (Opcional)
```bash
WHATSAPP_PHONE_NUMBER_ID=...  (Opcional - Phone number ID)
WHATSAPP_ACCESS_TOKEN=...     (Opcional - Access token)
WHATSAPP_APP_SECRET=...       (Opcional - App secret)
WHATSAPP_VERIFY_TOKEN=...     (Opcional - Webhook verify token)
```

#### Pagos (Opcional)
```bash
STRIPE_API_KEY=...            (Opcional - Stripe secret key)
STRIPE_WEBHOOK_SECRET=...     (Opcional - Webhook signing secret)
HOTMART_WEBHOOK_TOKEN=...     (Opcional - Hotmart hottok)
```

#### Calendario (Opcional)
```bash
CALENDLY_API_KEY=...          (Opcional - API key Calendly)
CALENDLY_WEBHOOK_SECRET=...   (Opcional - Webhook secret)
CALCOM_API_KEY=...            (Opcional - API key Cal.com)
```

#### LLM Alternativos (Opcional)
```bash
LLM_PROVIDER=groq             (Opcional - groq/openai/anthropic)
OPENAI_API_KEY=...            (Opcional - Si usas OpenAI)
ANTHROPIC_API_KEY=...         (Opcional - Si usas Anthropic)
```

#### Otras
```bash
CLONNECT_ADMIN_KEY=...        (Opcional - Admin API key)
FRONTEND_URL=...              (Opcional - URL frontend para redirects)
API_URL=...                   (Opcional - URL backend)
DATA_PATH=./data              (Opcional - Path para JSON storage)
REQUIRE_GDPR_CONSENT=false    (Opcional - Requerir consentimiento)
ENABLE_GUARDRAILS=true        (Opcional - Guardrails seguridad)
```

---

## 3. TABLA DE CAPACIDADES DEL SISTEMA

### 3.1 Canales de Mensajería

| Categoría | Feature | Estado | Archivo | Función/Clase | Dependencia | MVP |
|-----------|---------|--------|---------|---------------|-------------|-----|
| INSTAGRAM | Webhooks Meta | ✅ | core/instagram_handler.py | InstagramHandler.handle_webhook() | aiohttp | ✅ |
| INSTAGRAM | Envío de DMs | ✅ | core/instagram.py | InstagramConnector.send_message() | aiohttp | ✅ |
| INSTAGRAM | Auto-DM en comentarios | ✅ | core/instagram_handler.py | handle_comment() | aiohttp | ⏸️ |
| INSTAGRAM | Quick replies | ✅ | core/instagram.py | send_message_with_buttons() | aiohttp | ⏸️ |
| TELEGRAM | Bot polling | ✅ | core/telegram_adapter.py | TelegramAdapter.start() | python-telegram-bot | ✅ |
| TELEGRAM | Webhooks | ✅ | core/telegram_adapter.py | process_webhook_update() | python-telegram-bot | ✅ |
| TELEGRAM | Envío mensajes | ✅ | core/telegram_adapter.py | send_message() | python-telegram-bot | ✅ |
| WHATSAPP | Webhooks | ✅ | core/whatsapp.py | WhatsAppHandler.handle_webhook() | aiohttp | ⏸️ |
| WHATSAPP | Envío mensajes | ✅ | core/whatsapp.py | WhatsAppConnector.send_message() | aiohttp | ⏸️ |
| WHATSAPP | Templates | ✅ | core/whatsapp.py | send_template() | aiohttp | ⏸️ |
| WHATSAPP | Botones interactivos | ✅ | core/whatsapp.py | send_interactive_buttons() | aiohttp | ⏸️ |

### 3.2 LLM y Clasificación

| Categoría | Feature | Estado | Archivo | Función/Clase | Dependencia | MVP |
|-----------|---------|--------|---------|---------------|-------------|-----|
| LLM | Cliente Groq (Llama) | ✅ | core/llm.py | GroqClient | groq | ✅ |
| LLM | Cliente OpenAI | ✅ | core/llm.py | OpenAIClient | openai | ⏸️ |
| LLM | Cliente Anthropic | ✅ | core/llm.py | AnthropicClient | anthropic | ⏸️ |
| LLM | Factory multi-provider | ✅ | core/llm.py | get_llm_client() | - | ✅ |
| CLASIFICACIÓN | Intent classifier | ✅ | core/intent_classifier.py | IntentClassifier | LLM | ✅ |
| CLASIFICACIÓN | Quick patterns | ✅ | core/intent_classifier.py | _quick_classify() | - | ✅ |
| CLASIFICACIÓN | 12 tipos de intent | ✅ | core/intent_classifier.py | Intent(Enum) | - | ✅ |
| CLASIFICACIÓN | Conversation analyzer | ✅ | core/intent_classifier.py | ConversationAnalyzer | - | ⏸️ |

### 3.3 Personalidad y Respuestas

| Categoría | Feature | Estado | Archivo | Función/Clase | Dependencia | MVP |
|-----------|---------|--------|---------|---------------|-------------|-----|
| PERSONALIDAD | Tono configurable | ✅ | core/dm_agent.py | CreatorConfig.tone | - | ✅ |
| PERSONALIDAD | Estilo de escritura | ✅ | core/dm_agent.py | CreatorConfig.style | - | ✅ |
| PERSONALIDAD | Vocabulario custom | ✅ | core/dm_agent.py | CreatorConfig.vocabulary | - | ✅ |
| PERSONALIDAD | Welcome message | ✅ | core/dm_agent.py | CreatorConfig.welcome_message | - | ✅ |
| PERSONALIDAD | Multi-idioma (es/en/pt) | ✅ | core/i18n.py | detect_language() | - | ✅ |
| PERSONALIDAD | Variedad en saludos | ✅ | core/dm_agent.py | get_random_greeting() | - | ✅ |
| RESPUESTAS | Generación LLM | ✅ | core/dm_agent.py | _generate_response() | LLM | ✅ |
| RESPUESTAS | Cache de respuestas | ✅ | core/cache.py | ResponseCache | - | ⏸️ |
| RESPUESTAS | Guardrails | ✅ | core/guardrails.py | ResponseGuardrail | - | ⏸️ |

### 3.4 Productos y Objeciones

| Categoría | Feature | Estado | Archivo | Función/Clase | Dependencia | MVP |
|-----------|---------|--------|---------|---------------|-------------|-----|
| PRODUCTOS | CRUD productos | ✅ | core/products.py | ProductManager | - | ✅ |
| PRODUCTOS | Búsqueda por keywords | ✅ | core/products.py | search_products() | - | ✅ |
| PRODUCTOS | Recomendación | ✅ | core/products.py | recommend_product() | - | ✅ |
| PRODUCTOS | Payment links | ✅ | core/products.py | Product.payment_link | - | ✅ |
| OBJECIONES | Handlers por tipo | ✅ | core/products.py | get_objection_response() | - | ✅ |
| OBJECIONES | 8 tipos de objeción | ✅ | core/dm_agent.py | Intent.OBJECTION_* | - | ✅ |
| OBJECIONES | Respuestas dinámicas | ✅ | core/products.py | objection_handlers | - | ✅ |

### 3.5 Leads y Pipeline

| Categoría | Feature | Estado | Archivo | Función/Clase | Dependencia | MVP |
|-----------|---------|--------|---------|---------------|-------------|-----|
| LEADS | Modelo Lead DB | ✅ | api/models.py | Lead | SQLAlchemy | ✅ |
| LEADS | CRUD leads | ✅ | api/routers/leads.py | router | FastAPI | ✅ |
| LEADS | Estados Kanban | ✅ | api/routers/leads.py | status (new/engaged/etc) | - | ✅ |
| LEADS | Scoring automático | ✅ | core/memory.py | purchase_intent_score | - | ✅ |
| LEADS | Engagement score | ✅ | core/memory.py | engagement_score | - | ✅ |
| LEADS | Historial mensajes | ✅ | core/memory.py | last_messages | - | ✅ |
| LEADS | Intereses inferidos | ✅ | core/memory.py | interests[] | - | ⏸️ |
| PIPELINE | new → engaged → interested → hot_lead → customer | ✅ | api/routers/leads.py | status | - | ✅ |

### 3.6 Nurturing

| Categoría | Feature | Estado | Archivo | Función/Clase | Dependencia | MVP |
|-----------|---------|--------|---------|---------------|-------------|-----|
| NURTURING | Secuencias predefinidas | ✅ | core/nurturing.py | NURTURING_SEQUENCES | - | ✅ |
| NURTURING | 12 tipos de secuencia | ✅ | core/nurturing.py | SequenceType(Enum) | - | ✅ |
| NURTURING | Scheduler de envíos | ✅ | api/routers/nurturing.py | run_nurturing_now() | - | ✅ |
| NURTURING | Cancel en conversión | ✅ | core/payments.py | _cancel_nurturing_for_customer() | - | ✅ |
| NURTURING | Templates variables | ✅ | core/nurturing.py | render_template() | - | ✅ |
| NURTURING | Urgency/Scarcity | ✅ | core/nurturing.py | DISCOUNT_URGENCY, SPOTS_LIMITED | - | ⏸️ |

### 3.7 Escalación

| Categoría | Feature | Estado | Archivo | Función/Clase | Dependencia | MVP |
|-----------|---------|--------|---------|---------------|-------------|-----|
| ESCALACIÓN | Detección keywords | ✅ | core/intent_classifier.py | Intent.ESCALATION | - | ✅ |
| ESCALACIÓN | Pausar bot | ✅ | core/dm_agent.py | escalate_to_human | - | ✅ |
| ESCALACIÓN | Notificación Telegram | ✅ | core/notifications.py | send_escalation_notification() | python-telegram-bot | ✅ |
| ESCALACIÓN | Notificación Email | ⏸️ | core/notifications.py | (parcial) | - | ⏸️ |

### 3.8 Métricas y Analytics

| Categoría | Feature | Estado | Archivo | Función/Clase | Dependencia | MVP |
|-----------|---------|--------|---------|---------------|-------------|-----|
| MÉTRICAS | Dashboard overview | ✅ | api/routers/dashboard.py | get_overview() | - | ✅ |
| MÉTRICAS | Mensajes/día | ✅ | core/analytics.py | track_message() | - | ✅ |
| MÉTRICAS | Conversiones | ✅ | core/analytics.py | track_conversion() | - | ✅ |
| MÉTRICAS | Revenue tracking | ✅ | api/routers/payments.py | get_revenue_stats() | - | ✅ |
| MÉTRICAS | Bot attribution | ✅ | core/payments.py | _check_bot_attribution() | - | ✅ |
| MÉTRICAS | Prometheus export | ✅ | core/metrics.py | MetricsMiddleware | prometheus_client | ⏸️ |

### 3.9 Pagos

| Categoría | Feature | Estado | Archivo | Función/Clase | Dependencia | MVP |
|-----------|---------|--------|---------|---------------|-------------|-----|
| STRIPE | OAuth Connect | ✅ | api/routers/oauth.py | stripe_start/callback | httpx | ✅ |
| STRIPE | Webhooks | ✅ | core/payments.py | process_stripe_webhook() | - | ✅ |
| STRIPE | checkout.session.completed | ✅ | core/payments.py | _handle_stripe_checkout_completed() | - | ✅ |
| STRIPE | Refunds | ✅ | core/payments.py | _handle_stripe_refund() | - | ✅ |
| HOTMART | Webhooks | ✅ | core/payments.py | process_hotmart_webhook() | - | ⏸️ |
| HOTMART | PURCHASE_COMPLETE | ✅ | core/payments.py | _handle_hotmart_purchase() | - | ⏸️ |

### 3.10 Calendario

| Categoría | Feature | Estado | Archivo | Función/Clase | Dependencia | MVP |
|-----------|---------|--------|---------|---------------|-------------|-----|
| CALENDLY | OAuth | ✅ | api/routers/oauth.py | calendly_start/callback | httpx | ⏸️ |
| CALENDLY | Webhooks | ✅ | core/calendar.py | process_calendly_webhook() | - | ⏸️ |
| CALCOM | Webhooks | ✅ | core/calendar.py | process_calcom_webhook() | - | ⏸️ |
| BOOKING | Tracking | ✅ | core/calendar.py | Booking dataclass | - | ⏸️ |
| BOOKING | Links management | ✅ | api/routers/calendar.py | CRUD links | - | ⏸️ |

### 3.11 Auth y Seguridad

| Categoría | Feature | Estado | Archivo | Función/Clase | Dependencia | MVP |
|-----------|---------|--------|---------|---------------|-------------|-----|
| AUTH | API Keys | ✅ | core/auth.py | AuthManager | - | ✅ |
| AUTH | Generate/Revoke | ✅ | core/auth.py | generate_api_key(), revoke_api_key() | - | ✅ |
| AUTH | Admin key | ✅ | core/auth.py | is_admin_key() | - | ✅ |
| AUTH | Rate limiting | ✅ | core/rate_limiter.py | RateLimiter | - | ⏸️ |
| GDPR | Export data | ✅ | core/gdpr.py | export_user_data() | - | ✅ |
| GDPR | Delete data | ✅ | core/gdpr.py | delete_user_data() | - | ✅ |
| GDPR | Anonymize | ✅ | core/gdpr.py | anonymize_user_data() | - | ⏸️ |
| GDPR | Consent management | ✅ | core/gdpr.py | record_consent() | - | ⏸️ |
| GDPR | Audit log | ✅ | core/gdpr.py | log_access() | - | ✅ |

### 3.12 RAG y Knowledge Base

| Categoría | Feature | Estado | Archivo | Función/Clase | Dependencia | MVP |
|-----------|---------|--------|---------|---------------|-------------|-----|
| RAG | Embeddings | ✅ | core/rag.py | SimpleRAG | sentence-transformers | ⏸️ |
| RAG | Vector search | ✅ | core/rag.py | FAISS index | faiss-cpu | ⏸️ |
| RAG | Add documents | ✅ | core/rag.py | add_document() | - | ⏸️ |
| RAG | Search | ✅ | core/rag.py | search() | - | ⏸️ |
| KNOWLEDGE | FAQ CRUD | ✅ | api/routers/knowledge.py | CRUD endpoints | - | ✅ |

---

## 4. ARQUITECTURA DE PROCESAMIENTO DE DMs

```
MENSAJE ENTRANTE (Instagram/Telegram/WhatsApp)
        ↓
    1. WEBHOOK HANDLER
       - Verificar firma/token
       - Parsear payload
       - Extraer mensaje
        ↓
    2. PRE-PROCESAMIENTO
       - Detectar idioma
       - Cargar/crear memoria follower
       - Verificar rate limit
       - Check GDPR consent (si requerido)
        ↓
    3. CLASIFICACIÓN DE INTENT
       - Quick patterns (sin LLM)
       - Si no match → LLM classification
       - Resultado: Intent + confidence + entities
        ↓
    4. ACCIÓN SEGÚN INTENT
       ┌─────────────────────────────────────┐
       │ GREETING      → greet_and_discover  │
       │ QUESTION      → answer_from_rag     │
       │ INTEREST_SOFT → nurture_and_qualify │
       │ INTEREST_STRONG → close_sale        │
       │ OBJECTION     → handle_objection    │
       │ SUPPORT       → provide_support     │
       │ ESCALATION    → escalate_to_human   │
       │ SPAM          → ignore              │
       └─────────────────────────────────────┘
        ↓
    5. GENERACIÓN DE RESPUESTA
       - Cargar contexto (productos, config, historial)
       - Buscar en RAG si es pregunta
       - Construir prompt con personalidad
       - Llamar LLM
       - Aplicar guardrails
        ↓
    6. POST-PROCESAMIENTO
       - Actualizar memoria follower
       - Actualizar scores (purchase_intent, engagement)
       - Programar nurturing si aplica
       - Track analytics
        ↓
    7. ENVÍO DE RESPUESTA
       - Enviar via API del canal
       - Registrar mensaje enviado
        ↓
RESPUESTA ENVIADA
```

---

## 5. SISTEMA DE CLASIFICACIÓN DE INTENTS

```python
class Intent(Enum):
    # Saludos
    GREETING = "greeting"

    # Preguntas
    QUESTION_GENERAL = "question_general"
    QUESTION_PRODUCT = "question_product"

    # Interés
    INTEREST_SOFT = "interest_soft"
    INTEREST_STRONG = "interest_strong"

    # Objeciones
    OBJECTION = "objection"
    OBJECTION_PRICE = "objection_price"
    OBJECTION_TIME = "objection_time"
    OBJECTION_DOUBT = "objection_doubt"
    OBJECTION_LATER = "objection_later"
    OBJECTION_WORKS = "objection_works"
    OBJECTION_NOT_FOR_ME = "objection_not_for_me"
    OBJECTION_COMPLICATED = "objection_complicated"
    OBJECTION_ALREADY_HAVE = "objection_already_have"

    # Otros
    SUPPORT = "support"
    FEEDBACK_POSITIVE = "feedback_positive"
    FEEDBACK_NEGATIVE = "feedback_negative"
    ESCALATION = "escalation"
    LEAD_MAGNET = "lead_magnet"
    THANKS = "thanks"
    GOODBYE = "goodbye"
    SPAM = "spam"
    OTHER = "other"
```

### Patrones Quick (sin LLM)

| Intent | Patrones |
|--------|----------|
| GREETING | hola, buenas, hey, hi, qué tal, buenos días |
| FEEDBACK_POSITIVE | gracias, genial, increíble, perfecto, crack |
| INTEREST_STRONG | quiero comprar, cómo pago, precio, me apunto |
| INTEREST_SOFT | me interesa, cuéntame más, información |
| OBJECTION | es caro, no tengo tiempo, lo pienso |
| SUPPORT | no funciona, error, problema, ayuda |
| ESCALATION | hablar con persona, hablar con humano, agente real |

---

## 6. PIPELINE DE LEADS

### Estados del Lead

```
NEW → ENGAGED → INTERESTED → HOT_LEAD → CUSTOMER
 │                                          ↑
 └───────────────────────────────────────────┘
              (puede saltar estados)
```

| Estado | Descripción | Trigger |
|--------|-------------|---------|
| `new` | Primer contacto | Nuevo mensaje entrante |
| `engaged` | Conversación activa | 2+ mensajes intercambiados |
| `interested` | Mostró interés | Intent INTEREST_SOFT |
| `hot_lead` | Alta intención de compra | Intent INTEREST_STRONG |
| `customer` | Compró | Webhook de pago completado |

### Cálculo del Lead Score

```python
# En core/memory.py
if intent == "interest_strong":
    memory.purchase_intent_score += 0.3
elif intent == "interest_soft":
    memory.purchase_intent_score += 0.1
elif intent == "objection":
    memory.purchase_intent_score -= 0.05

# Engagement basado en mensajes
memory.engagement_score = min(1.0, total_messages / 20)
```

---

## 7. API ENDPOINTS

### Health & Status
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | /health/live | Liveness check |
| GET | /health/ready | Readiness check |

### Dashboard
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | /dashboard/{creator_id}/overview | Dashboard overview |
| PUT | /dashboard/{creator_id}/toggle | Toggle bot on/off |

### Configuración
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | /config/{creator_id} | Get creator config |
| PUT | /config/{creator_id} | Update config |

### Leads
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | /leads/{creator_id} | List all leads |
| GET | /leads/{creator_id}/{lead_id} | Get lead detail |
| POST | /leads/{creator_id} | Create lead |
| POST | /leads/{creator_id}/manual | Create manual lead |
| PUT | /leads/{creator_id}/{lead_id} | Update lead |
| DELETE | /leads/{creator_id}/{lead_id} | Delete lead |

### Mensajes
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | /messages/conversations/{creator_id} | List conversations |
| GET | /messages/follower/{creator_id}/{follower_id} | Get conversation |
| GET | /messages/metrics/{creator_id} | Message metrics |
| POST | /messages/send/{creator_id} | Send message |
| PUT | /messages/follower/{creator_id}/{follower_id}/status | Update status |

### Productos
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | /products/{creator_id}/products | List products |
| POST | /products/{creator_id}/products | Create product |
| PUT | /products/{creator_id}/products/{id} | Update product |
| DELETE | /products/{creator_id}/products/{id} | Delete product |

### Nurturing
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | /nurturing/{creator_id}/sequences | List sequences |
| GET | /nurturing/{creator_id}/followups | Get pending followups |
| GET | /nurturing/{creator_id}/stats | Nurturing stats |
| POST | /nurturing/{creator_id}/sequences/{type}/toggle | Toggle sequence |
| PUT | /nurturing/{creator_id}/sequences/{type} | Update sequence |
| POST | /nurturing/{creator_id}/run | Run nurturing now |
| DELETE | /nurturing/{creator_id}/cancel/{follower_id} | Cancel followups |

### Pagos
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | /payments/{creator_id}/revenue | Revenue stats |
| GET | /payments/{creator_id}/purchases | List purchases |
| POST | /payments/{creator_id}/purchases | Record purchase |

### Calendario
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | /calendar/{creator_id}/bookings | List bookings |
| GET | /calendar/{creator_id}/links | List booking links |
| POST | /calendar/{creator_id}/links | Create link |
| PUT | /calendar/{creator_id}/links/{id} | Update link |
| DELETE | /calendar/{creator_id}/links/{id} | Delete link |

### Knowledge Base
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | /knowledge/{creator_id}/knowledge | List FAQ |
| POST | /knowledge/{creator_id}/knowledge | Add FAQ |
| DELETE | /knowledge/{creator_id}/knowledge/{id} | Delete FAQ |

### Conexiones
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | /connections/{creator_id} | Get all connections |
| POST | /connections/{creator_id}/instagram | Connect IG |
| POST | /connections/{creator_id}/telegram | Connect TG |
| POST | /connections/{creator_id}/whatsapp | Connect WA |
| POST | /connections/{creator_id}/stripe | Connect Stripe |
| DELETE | /connections/{creator_id}/{platform} | Disconnect |

### OAuth
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | /oauth/instagram/start | Start IG OAuth |
| GET | /oauth/instagram/callback | IG OAuth callback |
| GET | /oauth/stripe/start | Start Stripe OAuth |
| GET | /oauth/stripe/callback | Stripe OAuth callback |
| GET | /oauth/calendly/start | Start Calendly OAuth |
| GET | /oauth/calendly/callback | Calendly callback |

### Webhooks
| Método | Ruta | Descripción |
|--------|------|-------------|
| GET/POST | /webhook/instagram | Instagram webhook |
| POST | /webhook/stripe | Stripe webhook |
| POST | /webhook/hotmart | Hotmart webhook |
| POST | /webhook/calendly | Calendly webhook |

---

## 8. TESTS

### Tests Existentes (133 tests)

```
tests/test_full_flow.py          - 50+ tests de flujo completo
tests/test_e2e_flow.py           - 6 tests E2E
tests/test_nurturing.py          - Tests nurturing
tests/test_nurturing_runner.py   - Tests runner
tests/test_intent.py             - Tests clasificación
tests/test_instagram.py          - Tests IG handler
tests/test_groq.py               - Tests cliente Groq
tests/test_products.py           - Tests productos
tests/test_leads_crud.py         - Tests CRUD leads
tests/test_db_messages.py        - Tests mensajes DB
tests/test_kanban_status.py      - Tests estados
tests/test_pipeline_scoring.py   - Tests scoring
tests/test_health.py             - Tests health
tests/test_config.py             - Tests config
tests/test_dashboard.py          - Tests dashboard
```

### Tests Faltantes Críticos
- [ ] Tests de WhatsApp handler
- [ ] Tests de GDPR compliance
- [ ] Tests de payments webhooks
- [ ] Tests de calendar integration
- [ ] Tests de rate limiting
- [ ] Tests de guardrails
- [ ] Tests de multi-idioma
- [ ] Tests frontend (solo estructura, pocos tests)

---

## 9. MODELOS DE BASE DE DATOS

```python
# api/models.py

class Creator(Base):
    id: UUID
    email: str (unique)
    name: str
    api_key: str (unique)
    bot_active: bool = False
    clone_tone: str = "friendly"
    clone_style: str
    clone_name: str
    clone_vocabulary: str
    welcome_message: str
    # Channels
    telegram_bot_token: str
    instagram_token: str
    instagram_page_id: str
    whatsapp_token: str
    whatsapp_phone_id: str
    # Payments
    stripe_api_key: str
    paypal_token: str
    hotmart_token: str
    # Calendar
    calendly_token: str
    created_at: datetime

class Lead(Base):
    id: UUID
    creator_id: UUID (FK)
    platform: str  # instagram, telegram, whatsapp
    platform_user_id: str
    username: str
    full_name: str
    status: str = "new"
    score: int = 0
    purchase_intent: float = 0.0
    context: JSON
    first_contact_at: datetime
    last_contact_at: datetime

class Message(Base):
    id: UUID
    lead_id: UUID (FK)
    role: str  # user, assistant
    content: str
    intent: str
    created_at: datetime

class Product(Base):
    id: UUID
    creator_id: UUID (FK)
    name: str
    description: str
    price: float
    currency: str = "EUR"
    is_active: bool = True
    created_at: datetime

class NurturingSequence(Base):
    id: UUID
    creator_id: UUID (FK)
    type: str
    name: str
    is_active: bool = True
    steps: JSON
    created_at: datetime

class KnowledgeBase(Base):
    id: UUID
    creator_id: UUID (FK)
    question: str
    answer: str
    created_at: datetime
```

---

## 10. CONCLUSIÓN

### Estado Actual: ~85% Completado

### Features Funcionando (MVP Ready):
- ✅ Procesamiento de DMs Instagram y Telegram
- ✅ Clasificación de intents con LLM
- ✅ Pipeline de leads con scoring
- ✅ Nurturing automático
- ✅ Gestión de productos y objeciones
- ✅ Dashboard React responsive
- ✅ OAuth Instagram y Stripe
- ✅ GDPR básico (export/delete)
- ✅ API Keys authentication
- ✅ 133 tests backend

### Features Pendientes:
- ⏸️ WhatsApp (implementado pero no probado)
- ⏸️ Calendario (Calendly/Cal.com)
- ⏸️ Hotmart webhooks
- ⏸️ RAG completo
- ⏸️ Multi-tenant completo
- ⏸️ Tests frontend

### Archivos Prioritarios para Review:
1. `core/dm_agent.py` - Lógica central del bot
2. `core/intent_classifier.py` - Clasificación de intents
3. `api/main.py` - Entry point y webhooks
4. `core/nurturing.py` - Sistema de follow-ups
5. `core/payments.py` - Integración pagos

### Recomendaciones para Beta:
1. **Priorizar Instagram** - Es el canal principal
2. **Probar nurturing** - Critical para conversiones
3. **Configurar Groq API** - LLM gratuito
4. **Activar GDPR** - Compliance obligatorio
5. **Monitorizar logs** - Para debugging rápido

---

*Documento generado automáticamente por Claude Code*
