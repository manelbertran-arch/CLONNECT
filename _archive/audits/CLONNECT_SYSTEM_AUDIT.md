# CLONNECT - Auditoría del Sistema

**Fecha:** 2025-12-28
**Versión:** Post-fusión Memory Engine + Reasoning Modules
**Tests:** 154 tests (143 passed, 11 skipped)

---

## 1. Visión General

### ¿Qué es CLONNECT?

CLONNECT es una plataforma de automatización de DMs (mensajes directos) para creadores de contenido. Permite a influencers, coaches y emprendedores digitales automatizar la atención de sus seguidores en Instagram, WhatsApp y Telegram, manteniendo un tono personalizado y humano.

### ¿Para quién?

- **Creadores de contenido** con alto volumen de DMs
- **Coaches y mentores** que venden cursos/servicios
- **Emprendedores digitales** con productos info

### ¿Qué problema resuelve?

1. **Escalabilidad:** Responder manualmente a cientos de DMs es insostenible
2. **Consistencia:** Mantener el mismo tono y calidad en cada respuesta
3. **Conversión:** Guiar leads hacia la compra sin perder calidez humana
4. **Disponibilidad:** Respuestas 24/7 sin contratar equipo

---

## 2. Arquitectura Técnica

### Diagrama de Módulos

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLONNECT SYSTEM                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐     │
│  │  Instagram  │   │  WhatsApp   │   │  Telegram   │   │   Web API   │     │
│  │   Webhook   │   │   Webhook   │   │   Webhook   │   │  Dashboard  │     │
│  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘     │
│         │                 │                 │                 │             │
│         └────────────────┬┴─────────────────┴─────────────────┘             │
│                          │                                                   │
│                          ▼                                                   │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         FastAPI (api/main.py)                          │  │
│  │                           153 endpoints                                │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                          │                                                   │
│         ┌────────────────┼────────────────┬───────────────┐                 │
│         ▼                ▼                ▼               ▼                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  DM Agent   │  │   Memory    │  │  Products   │  │  Nurturing  │        │
│  │  (2201 LOC) │  │   System    │  │   Catalog   │  │  Sequences  │        │
│  └──────┬──────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│         │                                                                    │
│         ▼                                                                    │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                        REASONING LAYER (NUEVO)                         │  │
│  ├─────────────────┬─────────────────┬─────────────────┬─────────────────┤  │
│  │ SelfConsistency │ ChainOfThought  │    Reflexion    │   Guardrails    │  │
│  │  (confianza)    │ (razonamiento)  │ (personalizar)  │  (seguridad)    │  │
│  └─────────────────┴─────────────────┴─────────────────┴─────────────────┘  │
│         │                                                                    │
│         ▼                                                                    │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                          RAG LAYER (MEJORADO)                          │  │
│  ├───────────────────────────────┬───────────────────────────────────────┤  │
│  │     Semantic Search (FAISS)   │       BM25 Lexical Search (NUEVO)     │  │
│  │     → Embeddings + similitud  │       → Keywords exactos              │  │
│  └───────────────────────────────┴───────────────────────────────────────┘  │
│         │                                                                    │
│         ▼                                                                    │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                            LLM PROVIDERS                               │  │
│  ├─────────────────┬─────────────────┬───────────────────────────────────┤  │
│  │      Groq       │     OpenAI      │           Anthropic               │  │
│  │  (Llama 3.3)    │   (GPT-4)       │         (Claude)                  │  │
│  └─────────────────┴─────────────────┴───────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Stack Tecnológico

| Capa | Tecnología |
|------|------------|
| **Backend** | Python 3.11+, FastAPI, SQLAlchemy |
| **Frontend** | React 18, TypeScript, Vite, Tailwind CSS |
| **Base de datos** | PostgreSQL (producción), JSON (desarrollo) |
| **LLM** | Groq (Llama 3.3 70B), OpenAI, Anthropic |
| **Embeddings** | sentence-transformers (MiniLM) |
| **Search** | FAISS + BM25 (híbrido) |

---

## 3. Módulos del Sistema

### 3.1 Core (backend/core/) - 13,023 líneas

| Archivo | Líneas | Descripción |
|---------|--------|-------------|
| `dm_agent.py` | 2,201 | Motor principal de procesamiento de DMs |
| `calendar.py` | 1,064 | Sistema de reservas y disponibilidad |
| `gdpr.py` | 859 | Cumplimiento GDPR (export, delete, anonymize) |
| `payments.py` | 819 | Integración Stripe/Hotmart para pagos |
| `whatsapp.py` | 770 | Conector WhatsApp Business API |
| `analytics.py` | 699 | Métricas y dashboards de rendimiento |
| `instagram_handler.py` | 557 | Handler de mensajes de Instagram |
| `telegram_adapter.py` | 550 | Adaptador para Telegram Bot API |
| `notifications.py` | 516 | Sistema de notificaciones push/email |
| `nurturing.py` | 479 | Secuencias de follow-up automatizadas |
| `instagram.py` | 461 | Conector Instagram Graph API |
| `products.py` | 451 | Catálogo de productos y objeciones |
| `i18n.py` | 432 | Internacionalización (ES/EN/PT) |
| `creator_config.py` | 409 | Configuración por creador |
| `metrics.py` | 390 | Métricas Prometheus (opcional) |
| `intent_classifier.py` | 379 | Clasificación de intenciones con LLM |
| `auth.py` | 337 | Autenticación por API keys |
| `alerts.py` | 325 | Sistema de alertas y escalado |
| `guardrails.py` | 264 | Validación de respuestas (NUEVO) |
| `memory.py` | 199 | Sistema de memoria por follower |
| `cache.py` | 190 | Cache de respuestas frecuentes |
| `query_expansion.py` | 174 | Expansión de queries para búsqueda |
| `sales_tracker.py` | 165 | Tracking de ventas y atribución (NUEVO) |
| `rate_limiter.py` | 145 | Rate limiting por follower |
| `llm.py` | 139 | Cliente multi-provider LLM |
| `telegram_sender.py` | 48 | Envío de mensajes Telegram |

### 3.2 Reasoning (backend/core/reasoning/) - NUEVO

| Archivo | Líneas | Descripción |
|---------|--------|-------------|
| `self_consistency.py` | 337 | Valida respuestas generando múltiples samples y midiendo consistencia. Si confidence < 0.6 → fallback seguro |
| `chain_of_thought.py` | 339 | Razonamiento paso a paso para queries complejas (salud, comparativas, >50 palabras) |
| `reflexion.py` | 325 | Mejora iterativa de mensajes via auto-crítica. Usado para personalizar nurturing |

### 3.3 RAG (backend/core/rag/) - MEJORADO

| Archivo | Líneas | Descripción |
|---------|--------|-------------|
| `semantic.py` | 335 | Búsqueda semántica con FAISS + embeddings |
| `bm25.py` | 348 | Búsqueda léxica BM25 con stopwords ES/EN (NUEVO) |
| `__init__.py` | 32 | Exports: SimpleRAG, HybridRAG, BM25Retriever |

**HybridRAG:** Combina 70% semántico + 30% BM25 para mejores resultados en nombres de productos y términos técnicos.

### 3.4 API (backend/api/) - 153 endpoints

#### Routers principales:

| Router | Endpoints | Propósito |
|--------|-----------|-----------|
| `main.py` | ~80 | Core: webhooks, DMs, conversations |
| `leads.py` | 15 | CRUD de leads, pipeline, scoring |
| `nurturing.py` | 12 | Secuencias, toggle, stats, enrollments |
| `payments.py` | 10 | Webhooks Stripe/Hotmart, purchases |
| `calendar.py` | 10 | Slots, bookings, availability |
| `products.py` | 8 | Catálogo, búsqueda, objections |
| `dashboard.py` | 5 | Overview, métricas, KPIs |
| `oauth.py` | 8 | OAuth Instagram/Meta (NUEVO) |
| `connections.py` | 6 | Gestión de conexiones IG/WA/TG (NUEVO) |
| `onboarding.py` | 5 | Flujo de onboarding (NUEVO) |
| `admin.py` | 8 | Panel administrativo (NUEVO) |
| `analytics.py` | 4 | Analytics avanzados (NUEVO) |

### 3.5 Frontend (frontend/src/) - 13,436 líneas

| Carpeta | Descripción |
|---------|-------------|
| `pages/` | Dashboard, Inbox, Leads, Revenue, Settings, Calendar, Nurturing |
| `components/` | Layout, Cards, Forms, Modals, Charts |
| `hooks/` | useApi, useAuth, useWebSocket |
| `services/` | API client, auth service |

---

## 4. Flujo de Procesamiento de DMs

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FLUJO DE PROCESAMIENTO DM                            │
└─────────────────────────────────────────────────────────────────────────────┘

1. ENTRADA
   │
   ▼
┌──────────────────┐
│ Webhook recibe   │ ← Instagram/WhatsApp/Telegram
│ mensaje          │
└────────┬─────────┘
         │
         ▼
2. RATE LIMITING
   │
   ▼
┌──────────────────┐
│ ¿Límite excedido?│ → Sí → Ignorar mensaje
└────────┬─────────┘
         │ No
         ▼
3. MEMORIA
   │
   ▼
┌──────────────────┐
│ Cargar historial │ ← memory.py
│ del follower     │
└────────┬─────────┘
         │
         ▼
4. CLASIFICACIÓN DE INTENT
   │
   ▼
┌──────────────────┐
│ intent_classifier│ → greeting, interest_soft, interest_strong,
│ + patterns       │   objection_price, question_product, support...
└────────┬─────────┘
         │
         ▼
5. CHAIN OF THOUGHT (NUEVO - si aplica)
   │
   ▼
┌──────────────────┐
│ ¿Query compleja? │ → Sí → Razonamiento paso a paso
│ (salud, >50 pal) │        con disclaimers apropiados
└────────┬─────────┘
         │ No
         ▼
6. GENERACIÓN DE RESPUESTA
   │
   ▼
┌──────────────────┐
│ LLM genera       │ ← System prompt + context + products
│ respuesta        │
└────────┬─────────┘
         │
         ▼
7. GUARDRAILS
   │
   ▼
┌──────────────────┐
│ Validar respuesta│ → Bloquear: info personal, claims médicos,
│                  │   competencia, contenido inapropiado
└────────┬─────────┘
         │
         ▼
8. SELF-CONSISTENCY (NUEVO)
   │
   ▼
┌──────────────────┐
│ ¿Confianza ≥0.6? │ → No → "Déjame confirmarlo con [creador]"
└────────┬─────────┘
         │ Sí
         ▼
9. TRADUCCIÓN (si necesario)
   │
   ▼
┌──────────────────┐
│ Detectar idioma  │ → ES/EN/PT auto-traducción
│ y adaptar        │
└────────┬─────────┘
         │
         ▼
10. ENVÍO
    │
    ▼
┌──────────────────┐
│ Enviar respuesta │ → Instagram/WhatsApp/Telegram API
│ + actualizar     │
│ memoria          │
└──────────────────┘
```

---

## 5. Capacidades Pre-Fusión vs Post-Fusión

| Capacidad | Antes | Ahora | Detalle |
|-----------|:-----:|:-----:|---------|
| **Respuestas automáticas** | ✅ | ✅ | DM → LLM → respuesta |
| **Multi-plataforma** | ✅ | ✅ | Instagram, WhatsApp, Telegram |
| **Clasificación de intent** | ✅ | ✅ | 20+ tipos de intención |
| **Productos y objeciones** | ✅ | ✅ | Catálogo + manejo de objeciones |
| **Nurturing sequences** | ✅ | ✅ | 12 tipos de secuencias |
| **Memoria de conversación** | ✅ | ✅ | Historial por follower |
| **GDPR compliance** | ✅ | ✅ | Export, delete, anonymize |
| **Pagos integrados** | ✅ | ✅ | Stripe + Hotmart |
| **Calendario/reservas** | ✅ | ✅ | Disponibilidad + booking |
| | | | |
| **Verificación de respuestas** | ❌ | ✅ | SelfConsistency: genera N samples, mide consistencia, fallback si baja confianza |
| **Razonamiento complejo** | ❌ | ✅ | ChainOfThought: paso a paso para queries de salud, comparativas |
| **Personalización nurturing** | ❌ | ✅ | Reflexion: auto-mejora de templates según contexto del follower |
| **Búsqueda híbrida** | ❌ | ✅ | BM25 + FAISS: mejor recall para nombres de productos |
| **Guardrails de seguridad** | ❌ | ✅ | Bloqueo de respuestas inseguras/inapropiadas |
| **Tracking de ventas** | ❌ | ✅ | SalesTracker: atribución de conversiones a conversaciones |
| **OAuth Instagram** | ❌ | ✅ | Conexión nativa sin tokens manuales |
| **Onboarding guiado** | ❌ | ✅ | Checklist para nuevos usuarios |

---

## 6. Estadísticas del Código

### Líneas de Código

| Componente | Líneas |
|------------|-------:|
| Backend total | 36,369 |
| Frontend total | 13,436 |
| **TOTAL** | **49,805** |

### Desglose Backend

| Carpeta | Líneas |
|---------|-------:|
| core/ | 13,023 |
| core/reasoning/ (NUEVO) | 1,001 |
| core/rag/ (NUEVO) | 715 |
| api/ | ~15,000 |
| tests/ | ~5,000 |

### Tests

| Métrica | Valor |
|---------|------:|
| Tests totales | 154 |
| Pasando | 143 |
| Skipped | 11 |
| Coverage estimado | ~75% |

### Módulos Nuevos (esta fusión)

| Módulo | Líneas | Propósito |
|--------|-------:|-----------|
| `reasoning/self_consistency.py` | 337 | Validación de confianza |
| `reasoning/chain_of_thought.py` | 339 | Razonamiento paso a paso |
| `reasoning/reflexion.py` | 325 | Mejora iterativa |
| `rag/bm25.py` | 348 | Búsqueda léxica |
| `guardrails.py` | 264 | Validación de seguridad |
| `sales_tracker.py` | 165 | Tracking de ventas |
| **TOTAL NUEVO** | **1,778** | |

---

## 7. Integraciones Externas

| Servicio | Propósito | Estado |
|----------|-----------|--------|
| Instagram Graph API | DMs de Instagram | ✅ Activo |
| WhatsApp Business API | DMs de WhatsApp | ✅ Activo |
| Telegram Bot API | DMs de Telegram | ✅ Activo |
| Groq API | LLM (Llama 3.3) | ✅ Primario |
| OpenAI API | LLM (fallback) | ✅ Opcional |
| Anthropic API | LLM (fallback) | ✅ Opcional |
| Stripe | Pagos | ✅ Activo |
| Hotmart | Pagos (LATAM) | ✅ Activo |
| Vercel | Frontend hosting | ✅ Activo |

---

## 8. Seguridad

### Guardrails Implementados

1. **Rate Limiting:** Máx 10 mensajes/minuto por follower
2. **Validación de respuestas:** Bloqueo de contenido inseguro
3. **GDPR:** Derecho al olvido, export de datos
4. **API Keys:** Autenticación por API key + creator_id
5. **Webhooks:** Verificación de firma (Instagram, Stripe)

### Contenido Bloqueado

- Información personal del creador (teléfono, dirección)
- Claims médicos sin disclaimer
- Menciones de competencia
- Contenido explícito/violento
- Promesas de resultados garantizados

---

## 9. Próximos Pasos Recomendados

1. **Monitoring:** Añadir Sentry para errores en producción
2. **Analytics:** Dashboard de métricas de reasoning modules
3. **A/B Testing:** Comparar respuestas con/sin SelfConsistency
4. **Cache:** Redis para cache distribuido en multi-instancia
5. **Embeddings:** Migrar a OpenAI embeddings para mejor calidad

---

*Documento generado automáticamente por Claude Code*
*Repositorio: CLONNECT*
*Commit: Post-merge Memory Engine + Reasoning Modules*
