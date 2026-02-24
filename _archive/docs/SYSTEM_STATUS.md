# CLONNECT - Estado Real del Sistema

**Fecha:** 2026-01-04
**Commit:** e57983ce (refactor(onboarding): split into Desktop and Mobile components)
**Rama:** claude/clonnect-onboarding-integration-RjjH6

---

## RESUMEN EJECUTIVO

| Estado | Cantidad | Descripción |
|--------|----------|-------------|
| ✅ Funciona | 18 | Componentes listos para producción |
| ⚠️ Parcial | 8 | Funcionan pero requieren config externa (API keys) |
| ❌ No funciona | 2 | Requieren implementación adicional |

---

## BACKEND

### Estructura
```
backend/
├── api/           # FastAPI endpoints (16 routers)
├── core/          # Lógica de negocio (DM Agent, LLM, integraciones)
├── admin/         # Dashboard admin (Streamlit - legacy)
├── scripts/       # Scripts de utilidad
└── tests/         # Tests automatizados
```

### Endpoints API

| Router | Endpoints | Estado | Notas |
|--------|-----------|--------|-------|
| `/health` | GET /health, /live, /ready | ✅ | Health checks funcionando |
| `/dashboard` | GET /{creator_id}/overview | ✅ | Métricas en tiempo real |
| `/config` | GET/POST /{creator_id}/config | ✅ | Configuración del clon |
| `/leads` | GET/POST/PUT/DELETE | ✅ | CRUD completo de leads |
| `/products` | GET/POST/PUT/DELETE | ✅ | CRUD completo de productos |
| `/messages` | GET/POST conversaciones | ✅ | Chat y mensajería |
| `/payments` | GET revenue, POST webhook | ⚠️ | Requiere Stripe/PayPal keys |
| `/calendar` | GET bookings, stats | ⚠️ | Requiere Calendly token |
| `/nurturing` | GET/POST secuencias | ✅ | Secuencias de follow-up |
| `/knowledge` | GET/POST FAQs, about | ✅ | Knowledge base RAG |
| `/analytics` | GET métricas | ✅ | Analytics del bot |
| `/onboarding` | GET status, POST complete | ✅ | Onboarding visual |
| `/admin` | Endpoints admin | ✅ | Panel de administración |
| `/connections` | GET/POST plataformas | ✅ | Estado de conexiones |
| `/oauth` | OAuth flows | ⚠️ | Requiere app credentials |
| `/booking` | Booking links | ✅ | Links de reserva |

### Servicios Core

| Servicio | Archivo | Estado | Notas |
|----------|---------|--------|-------|
| DM Agent | `core/dm_agent.py` | ✅ | Agente de respuestas automáticas |
| Intent Classifier | `core/intent_classifier.py` | ✅ | 12 intents detectables vía LLM |
| LLM Client | `core/llm.py` | ⚠️ | Soporta Groq/OpenAI/Anthropic - requiere API key |
| RAG | `core/rag/` | ✅ | BM25 + Semantic search |
| Memory Store | `core/memory.py` | ✅ | Memoria de conversaciones |
| Nurturing | `core/nurturing.py` | ✅ | 11 tipos de secuencias |
| Payments | `core/payments.py` | ⚠️ | Stripe/Hotmart/PayPal - requiere keys |
| Calendar | `core/calendar.py` | ⚠️ | Calendly/Zoom/Google - requiere tokens |
| Guardrails | `core/guardrails.py` | ✅ | Validación de respuestas |
| Reasoning | `core/reasoning/` | ✅ | Chain-of-thought, Reflexion, Self-consistency |

---

## FRONTEND

### Estructura
```
frontend/src/
├── components/    # UI components + Onboarding
├── pages/         # Páginas del dashboard
├── hooks/         # React Query hooks (useApi.ts)
├── services/      # API client (api.ts)
└── types/         # TypeScript types
```

### Páginas Dashboard

| Página | Ruta | Conectada a API | Formularios | Estado | Notas |
|--------|------|-----------------|-------------|--------|-------|
| Dashboard | `/` | ✅ useDashboard | N/A | ✅ | Métricas en tiempo real |
| Inbox | `/inbox` | ✅ useConversations | ✅ Enviar mensaje | ✅ | Chat unificado multicanal |
| Leads | `/leads` | ✅ useConversations | ✅ CRUD leads | ✅ | Kanban visual |
| Nurturing | `/nurturing` | ✅ useNurturingSequences | ✅ Toggle/Edit | ✅ | Gestión de secuencias |
| Products | `/products` | ✅ useProducts | ✅ CRUD productos | ✅ | Catálogo de productos |
| Bookings | `/bookings` | ✅ useBookings | ✅ Crear/Cancelar | ✅ | Calendario de citas |
| Settings | `/settings` | ✅ useCreatorConfig | ✅ Guardar config | ✅ | Configuración completa |

### Componentes Especiales

| Componente | Estado | Notas |
|------------|--------|-------|
| Onboarding (Desktop) | ✅ | 12 slides, animaciones, tour del dashboard |
| Onboarding (Mobile) | ✅ | Versión simplificada táctil |
| Sidebar | ✅ | Navegación desktop |
| MobileNav | ✅ | Navegación móvil |

---

## INTEGRACIONES

| Integración | Código | Configurada | Funcionando | Notas |
|-------------|--------|-------------|-------------|-------|
| **Instagram** | `core/instagram.py` | ⚠️ | ⚠️ | Requiere: `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_PAGE_ID`, `INSTAGRAM_APP_SECRET` |
| **Telegram** | `core/telegram_adapter.py` | ⚠️ | ⚠️ | Requiere: `TELEGRAM_BOT_TOKEN`. Soporta polling y webhook |
| **WhatsApp** | `core/whatsapp.py` | ⚠️ | ⚠️ | Requiere: `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` |
| **Groq (LLM)** | `core/llm.py` | ⚠️ | ⚠️ | Requiere: `GROQ_API_KEY`. Default provider (Llama 3.3 70B gratis) |
| **OpenAI** | `core/llm.py` | ⚠️ | ⚠️ | Requiere: `OPENAI_API_KEY`. Opcional, GPT-4o-mini |
| **Anthropic** | `core/llm.py` | ⚠️ | ⚠️ | Requiere: `ANTHROPIC_API_KEY`. Opcional, Claude 3 |
| **Stripe** | `core/payments.py` | ⚠️ | ⚠️ | Requiere: `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET` |
| **PayPal** | `core/payments.py` | ⚠️ | ⚠️ | Requiere: `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET` |
| **Hotmart** | `core/payments.py` | ⚠️ | ⚠️ | Requiere: `HOTMART_TOKEN`, `HOTMART_WEBHOOK_SECRET` |
| **Calendly** | `core/calendar.py` | ⚠️ | ⚠️ | Requiere: OAuth flow o `CALENDLY_API_KEY` |
| **Zoom** | `core/calendar.py` | ⚠️ | ⚠️ | Requiere: OAuth flow |
| **Google Meet** | `core/calendar.py` | ⚠️ | ⚠️ | Requiere: OAuth flow |

---

## BASE DE DATOS

| Aspecto | Estado | Notas |
|---------|--------|-------|
| **Tipo** | PostgreSQL + JSON fallback | Híbrido |
| **Conexión** | ✅ | `DATABASE_URL` env var |
| **ORM** | SQLAlchemy | Models definidos en `api/models.py` |
| **Migraciones** | ⚠️ | `init_db.py` crea tablas, no hay Alembic |

### Tablas/Modelos

| Modelo | Campos principales | Estado |
|--------|-------------------|--------|
| `Creator` | id, email, name, bot_active, tokens, onboarding_completed | ✅ |
| `Lead` | id, creator_id, platform, username, status, score | ✅ |
| `Message` | id, lead_id, role, content, intent | ✅ |
| `Product` | id, creator_id, name, price, payment_link | ✅ |
| `NurturingSequence` | id, creator_id, type, is_active, steps | ✅ |
| `KnowledgeBase` | id, creator_id, question, answer | ✅ |
| `BookingLink` | id, creator_id, meeting_type, url, price | ✅ |
| `CalendarBooking` | id, creator_id, follower_id, scheduled_at | ✅ |
| `CreatorAvailability` | id, creator_id, day_of_week, slots | ✅ |

---

## BOT / IA

### DM Agent
- **Archivo:** `core/dm_agent.py`
- **Estado:** ✅ Funciona
- **Intents detectados:** 16 tipos (greeting, interest_soft, interest_strong, objection_*, question_*, etc.)
- **RAG:** BM25 + Semantic search para knowledge base
- **Memoria:** Contexto de conversación persistente
- **Guardrails:** Validación de respuestas antes de enviar

### Intent Classifier
- **Archivo:** `core/intent_classifier.py`
- **Estado:** ✅ Funciona
- **Método:** LLM con prompt estructurado
- **Quick patterns:** Patrones regex para respuestas rápidas sin LLM

### Nurturing Scheduler
- **Archivo:** `core/nurturing.py`
- **Estado:** ✅ Funciona
- **Secuencias:** 11 tipos (abandoned, interest_cold, re_engagement, post_purchase, etc.)
- **Ejecución:** Script `scripts/process_nurturing.py` o via API

---

## CONCLUSIÓN

### ✅ READY PARA BETA (18 componentes)

**Backend:**
- API completa con 16 routers funcionando
- DM Agent con intent classification
- RAG para knowledge base
- Nurturing sequences
- CRUD completo (leads, products, messages, bookings)
- Onboarding visual (desktop + mobile)

**Frontend:**
- Dashboard completo con 7 páginas
- Chat unificado multicanal
- Kanban de leads
- Gestión de productos
- Configuración de personalidad
- Onboarding interactivo

### ⚠️ FUNCIONA PARCIALMENTE (8 componentes)

Todos estos funcionan pero **requieren configuración de API keys/tokens:**

1. **LLM (Groq/OpenAI/Anthropic)** - Necesita al menos `GROQ_API_KEY`
2. **Instagram** - Necesita tokens y app credentials
3. **Telegram** - Necesita `TELEGRAM_BOT_TOKEN`
4. **WhatsApp** - Necesita tokens de Meta
5. **Stripe** - Necesita API key y webhook secret
6. **PayPal** - Necesita client ID y secret
7. **Calendly** - Necesita OAuth o API key
8. **Zoom/Google Meet** - Necesita OAuth

### ❌ NO FUNCIONA / PENDIENTE (2 items)

1. **Migraciones DB** - Solo `init_db.py`, falta Alembic para versiones
2. **Tests E2E automatizados** - Existen pero no están en CI/CD

---

## 🎯 PARA LANZAR BETA NECESITAMOS:

### Crítico (Bloquea lanzamiento)
1. **Configurar GROQ_API_KEY** - Para que el bot genere respuestas
2. **Conectar al menos 1 canal** - Instagram, Telegram o WhatsApp
3. **Configurar DATABASE_URL** - PostgreSQL en Railway/Supabase
4. **Deploy en Vercel** - Merge PR #4 a main

### Importante (Primera semana post-lanzamiento)
5. **Configurar Stripe/PayPal** - Para procesar pagos
6. **Configurar Calendly** - Para bookings
7. **Configurar alertas** - Slack/Discord para notificaciones

### Nice to have
8. **Alembic migrations** - Para cambios de schema
9. **Tests en CI/CD** - GitHub Actions
10. **Monitoring** - Prometheus/Grafana

---

## VARIABLES DE ENTORNO REQUERIDAS

```bash
# Base de datos (CRÍTICO)
DATABASE_URL=postgresql://user:pass@host:5432/clonnect

# LLM (CRÍTICO - al menos uno)
GROQ_API_KEY=gsk_...          # Recomendado (gratis)
# OPENAI_API_KEY=sk-...       # Opcional
# ANTHROPIC_API_KEY=sk-...    # Opcional

# Mensajería (al menos uno para beta)
TELEGRAM_BOT_TOKEN=123456:ABC...
# INSTAGRAM_ACCESS_TOKEN=...
# WHATSAPP_ACCESS_TOKEN=...
# WHATSAPP_PHONE_NUMBER_ID=...

# Pagos (opcional para beta)
# STRIPE_API_KEY=sk_...
# STRIPE_WEBHOOK_SECRET=whsec_...

# Calendario (opcional)
# CALENDLY_API_KEY=...
```

---

*Generado automáticamente por Claude Code - 2026-01-04*
