# 🔍 AUDITORÍA: Clonnect-creators

**Fecha**: 2026-01-04
**Repositorio**: `Clonnect-creators`
**Ubicación**: `/home/user/CLONNECT/Clonnect-creators`
**Total de archivos de código**: ~68 archivos Python

---

## 📁 1. Estructura del Repositorio

```
Clonnect-creators/
├── admin/
│   ├── dashboard.py           # Dashboard principal Streamlit
│   └── pages/                 # Páginas adicionales del dashboard
│       ├── inbox.py
│       ├── leads.py
│       ├── nurturing.py
│       ├── revenue.py
│       ├── calendar.py
│       └── settings.py
├── api/
│   ├── main.py                # FastAPI application principal
│   ├── models.py              # Modelos SQLAlchemy
│   ├── database.py            # Configuración de DB
│   ├── routes/                # Endpoints REST
│   │   ├── creators.py
│   │   ├── leads.py
│   │   ├── messages.py
│   │   ├── products.py
│   │   ├── knowledge.py
│   │   └── webhooks.py
│   └── schemas/               # Pydantic schemas
├── core/
│   ├── dm_agent.py            # Agente principal de DMs
│   ├── intent_classifier.py   # Clasificador de intenciones
│   ├── rag.py                 # Sistema RAG con FAISS
│   ├── llm.py                 # Cliente multi-LLM
│   ├── memory.py              # Persistencia de memoria
│   ├── instagram.py           # Conector Instagram
│   ├── telegram_adapter.py    # Adaptador Telegram
│   ├── analytics.py           # Sistema de analytics
│   ├── nurturing.py           # Motor de nurturing
│   ├── payments.py            # Integración pagos (Stripe/Hotmart)
│   ├── calendar.py            # Integración calendarios
│   └── gdpr.py                # Cumplimiento GDPR
├── tests/                     # Tests unitarios
├── scripts/                   # Scripts de utilidad
├── requirements.txt           # Dependencias Python
├── Dockerfile                 # Containerización
└── docker-compose.yml         # Orquestación
```

---

## 📋 2. Inventario de Funcionalidades por Archivo

### 2.1 Core Modules

| Archivo | Propósito | Clases/Funciones Principales | Mapeo a Módulo | Estado | Calidad |
|---------|-----------|------------------------------|----------------|--------|---------|
| `core/dm_agent.py` | Agente principal que responde DMs | `DMAgent`, `respond_to_message()`, `build_context()` | Response Engine v2 | ✅ Funcional | ⭐⭐⭐⭐ |
| `core/intent_classifier.py` | Clasificación de intenciones con 17+ intents | `IntentClassifier`, `classify()`, `INTENTS` | Intent Classifier (Infra) | ✅ Funcional | ⭐⭐⭐⭐ |
| `core/rag.py` | Sistema RAG con FAISS embeddings | `RAGEngine`, `add_document()`, `search()`, `build_index()` | HybridRAG (Infra) | ✅ Funcional | ⭐⭐⭐⭐ |
| `core/llm.py` | Cliente multi-proveedor LLM | `LLMClient`, `generate()`, soporte Groq/OpenAI/Anthropic | Infra | ✅ Funcional | ⭐⭐⭐⭐⭐ |
| `core/memory.py` | Persistencia de memoria por follower | `MemoryStore`, `get_context()`, `save_interaction()` | Memory Engine (Infra) | ✅ Funcional | ⭐⭐⭐ |
| `core/instagram.py` | Conector Instagram Graph API | `InstagramConnector`, `send_message()`, `get_messages()` | Instagram Scraper (parcial) | ⚠️ Solo mensajería | ⭐⭐⭐ |
| `core/telegram_adapter.py` | Adaptador Telegram Bot API | `TelegramAdapter`, `handle_update()`, `send_message()` | N/A (extra) | ✅ Funcional | ⭐⭐⭐⭐ |
| `core/analytics.py` | Sistema de analytics y métricas | `AnalyticsEngine`, `track_event()`, `get_stats()` | Advanced Analytics (parcial) | ⚠️ Básico | ⭐⭐⭐ |
| `core/nurturing.py` | Motor de secuencias de seguimiento | `NurturingEngine`, `process_sequences()`, `trigger_step()` | Behavior Triggers (parcial) | ⚠️ Parcial | ⭐⭐⭐ |
| `core/payments.py` | Integración Stripe + Hotmart | `PaymentManager`, `process_stripe_webhook()`, `process_hotmart_webhook()` | Dynamic Offers (parcial) | ✅ Funcional | ⭐⭐⭐⭐⭐ |
| `core/calendar.py` | Integración Calendly + Cal.com | `CalendarManager`, `get_available_slots()`, `create_booking()` | N/A (extra valioso) | ✅ Funcional | ⭐⭐⭐⭐⭐ |
| `core/gdpr.py` | Cumplimiento GDPR completo | `GDPRManager`, `export_data()`, `delete_data()`, `anonymize()` | N/A (compliance) | ✅ Funcional | ⭐⭐⭐⭐⭐ |

### 2.2 API Layer

| Archivo | Propósito | Clases/Funciones Principales | Mapeo a Módulo | Estado | Calidad |
|---------|-----------|------------------------------|----------------|--------|---------|
| `api/main.py` | Aplicación FastAPI principal | `app`, middleware CORS, routers | Infra | ✅ Funcional | ⭐⭐⭐⭐ |
| `api/models.py` | Modelos SQLAlchemy | `Creator`, `Lead`, `Message`, `Product`, `NurturingSequence`, `KnowledgeBase` | Infra | ✅ Funcional | ⭐⭐⭐⭐ |
| `api/database.py` | Configuración PostgreSQL | `get_db()`, `Base`, `engine` | Infra | ✅ Funcional | ⭐⭐⭐⭐ |
| `api/routes/creators.py` | CRUD de creadores | Endpoints `/creators/*` | Infra | ✅ Funcional | ⭐⭐⭐⭐ |
| `api/routes/leads.py` | Gestión de leads | Endpoints `/leads/*` | Infra | ✅ Funcional | ⭐⭐⭐⭐ |
| `api/routes/webhooks.py` | Webhooks externos | Stripe, Hotmart, Instagram | Infra | ✅ Funcional | ⭐⭐⭐⭐ |

### 2.3 Admin Dashboard

| Archivo | Propósito | Clases/Funciones Principales | Mapeo a Módulo | Estado | Calidad |
|---------|-----------|------------------------------|----------------|--------|---------|
| `admin/dashboard.py` | Dashboard Streamlit principal | Autenticación, selector de creator, navegación | UI Base Conocimiento (parcial) | ✅ Funcional | ⭐⭐⭐⭐ |
| `admin/pages/inbox.py` | Vista de mensajes | Lista de conversaciones, respuestas | N/A | ✅ Funcional | ⭐⭐⭐ |
| `admin/pages/leads.py` | Gestión de leads | Tabla de leads, filtros, scoring | N/A | ✅ Funcional | ⭐⭐⭐ |
| `admin/pages/nurturing.py` | Editor de secuencias | Creador de secuencias de nurturing | Behavior Triggers (UI) | ✅ Funcional | ⭐⭐⭐ |
| `admin/pages/revenue.py` | Dashboard de ingresos | Métricas de ventas, gráficos | Advanced Analytics (UI) | ✅ Funcional | ⭐⭐⭐ |
| `admin/pages/calendar.py` | Vista de calendario | Reservas, disponibilidad | N/A | ✅ Funcional | ⭐⭐⭐ |
| `admin/pages/settings.py` | Configuración del creator | Clone settings, tokens, productos | N/A | ✅ Funcional | ⭐⭐⭐ |

---

## 🔧 3. Dependencias y Tecnologías

### 3.1 Dependencias Python (requirements.txt)

| Categoría | Paquete | Versión | Uso |
|-----------|---------|---------|-----|
| **Core** | fastapi | >=0.104.0 | Framework API REST |
| | uvicorn | >=0.24.0 | Servidor ASGI |
| | pydantic | >=2.0.0 | Validación de datos |
| | python-dotenv | >=1.0.0 | Variables de entorno |
| **LLM** | openai | >=1.0.0 | OpenAI GPT |
| | anthropic | >=0.7.0 | Claude API |
| | groq | >=0.4.0 | Groq LPU |
| **Embeddings** | numpy | >=1.24.0 | Operaciones vectoriales |
| | sentence-transformers | >=2.2.0 | Embeddings de texto |
| | faiss-cpu | >=1.7.4 | Búsqueda vectorial |
| **Dashboard** | streamlit | >=1.28.0 | Admin UI |
| **Database** | sqlalchemy | 2.0.23 | ORM |
| | psycopg2-binary | 2.9.9 | Driver PostgreSQL |
| **Messaging** | aiohttp | >=3.9.0 | HTTP async (Instagram) |
| | python-telegram-bot | >=20.0 | Telegram Bot API |
| **Testing** | pytest | >=7.4.0 | Testing framework |
| | pytest-asyncio | >=0.21.0 | Tests async |
| | httpx | >=0.25.0 | HTTP client tests |
| **Utils** | python-dateutil | >=2.8.0 | Manejo de fechas |
| | pytz | >=2023.3 | Zonas horarias |
| | psutil | >=5.9.0 | Métricas del sistema |
| | requests | >=2.31.0 | HTTP client |

### 3.2 APIs Externas

| Servicio | Uso | Archivo |
|----------|-----|---------|
| Instagram Graph API | Mensajería DMs | `core/instagram.py` |
| Telegram Bot API | Bot de Telegram | `core/telegram_adapter.py` |
| Stripe API | Pagos y webhooks | `core/payments.py` |
| Hotmart API | Pagos infoproductos | `core/payments.py` |
| Calendly API | Gestión de citas | `core/calendar.py` |
| Cal.com API | Gestión de citas | `core/calendar.py` |
| OpenAI API | Generación de respuestas | `core/llm.py` |
| Anthropic API | Generación de respuestas | `core/llm.py` |
| Groq API | Generación de respuestas (rápida) | `core/llm.py` |

### 3.3 Base de Datos

- **PostgreSQL**: Base de datos principal
- **FAISS**: Índice vectorial para RAG (en memoria/archivo)
- **JSON files**: Persistencia de memoria (legacy)

---

## 📊 4. Mapa de Cobertura de Módulos

| # | Módulo | Prioridad | Estado | Cobertura | Notas |
|---|--------|-----------|--------|-----------|-------|
| 1 | Instagram Scraper | 🔴 CRÍTICO | ⚠️ Parcial | 30% | Solo mensajería, falta scraping de contenido público |
| 2 | Content Indexer | 🔴 CRÍTICO | ❌ No existe | 0% | No hay indexación de contenido del creator |
| 3 | Tone Analyzer | 🔴 CRÍTICO | ❌ No existe | 0% | No hay análisis de tono/estilo |
| 4 | Content Citation | 🔴 CRÍTICO | ❌ No existe | 0% | No hay sistema de citas |
| 5 | Response Engine v2 | 🔴 CRÍTICO | ✅ Existe | 70% | `dm_agent.py` - funcional, mejorable |
| 6 | Transcriber (Whisper) | 🟡 ALTO | ❌ No existe | 0% | No hay transcripción |
| 7 | YouTube Connector | 🟡 ALTO | ❌ No existe | 0% | No implementado |
| 8 | Podcast Connector | 🟡 ALTO | ❌ No existe | 0% | No implementado |
| 9 | UI Base Conocimiento | 🟢 MEDIO | ⚠️ Parcial | 40% | Dashboard existe pero sin editor de KB visual |
| 10 | Import Wizard | 🟢 MEDIO | ❌ No existe | 0% | No hay wizard de importación |
| 11 | Behavior Triggers | 🟢 MEDIO | ⚠️ Parcial | 50% | `nurturing.py` tiene secuencias básicas |
| 12 | Dynamic Offers | 🟢 MEDIO | ⚠️ Parcial | 40% | Pagos OK, falta lógica de ofertas dinámicas |
| 13 | Content Recommender | 🟢 MEDIO | ❌ No existe | 0% | No hay recomendador de contenido |
| 14 | Advanced Analytics | 🟢 MEDIO | ⚠️ Parcial | 35% | `analytics.py` básico + dashboard revenue |

### Infraestructura (ya implementada en main repo - verificar duplicación)

| Módulo | Estado en este repo | Notas |
|--------|---------------------|-------|
| Memory Engine | ✅ Implementado | `core/memory.py` - JSON-based |
| Intent Classifier | ✅ Implementado | `core/intent_classifier.py` - 17 intents |
| HybridRAG | ✅ Implementado | `core/rag.py` - FAISS + sentence-transformers |
| LLM Client | ✅ Implementado | `core/llm.py` - Multi-provider |

---

## 💎 5. Código Destacado para Reutilizar

### 5.1 Sistema de Pagos Multi-Plataforma (`core/payments.py`)

```python
@dataclass
class Purchase:
    """Registro de compra con atribución al bot"""
    id: str
    creator_id: str
    lead_id: Optional[str]
    platform: str  # 'stripe' | 'hotmart'
    product_id: str
    product_name: str
    amount: float
    currency: str
    status: str
    bot_attributed: bool  # Si la venta vino del bot
    created_at: datetime

class PaymentManager:
    """Gestor unificado de pagos Stripe + Hotmart"""

    async def process_stripe_webhook(self, payload: dict, signature: str) -> Optional[Purchase]:
        """Procesa webhooks de Stripe con verificación de firma"""
        # Verifica firma HMAC
        # Extrae evento checkout.session.completed
        # Crea registro de Purchase con atribución

    async def process_hotmart_webhook(self, payload: dict) -> Optional[Purchase]:
        """Procesa webhooks de Hotmart"""
        # Soporta eventos: PURCHASE_COMPLETE, PURCHASE_CANCELED, etc.
        # Mapea estados de Hotmart a estados internos

    async def get_revenue_stats(self, creator_id: str, period: str = "month") -> dict:
        """Estadísticas de ingresos con atribución al bot"""
        return {
            "total_revenue": float,
            "bot_attributed_revenue": float,
            "conversion_rate": float,
            "top_products": list
        }
```

**Valor**: ⭐⭐⭐⭐⭐ - Sistema completo de pagos listo para producción.

### 5.2 Integración de Calendarios (`core/calendar.py`)

```python
@dataclass
class BookingLink:
    """Link de reserva con configuración"""
    id: str
    creator_id: str
    platform: str  # 'calendly' | 'calcom'
    name: str
    url: str
    duration_minutes: int
    price: Optional[float]

class CalendarManager:
    """Gestor unificado Calendly + Cal.com"""

    async def get_available_slots(
        self,
        creator_id: str,
        booking_link_id: str,
        start_date: date,
        end_date: date
    ) -> List[TimeSlot]:
        """Obtiene slots disponibles de cualquier plataforma"""

    async def create_booking(
        self,
        booking_link_id: str,
        lead_id: str,
        slot: TimeSlot,
        attendee_info: dict
    ) -> Booking:
        """Crea reserva en la plataforma correspondiente"""

    async def process_calendly_webhook(self, payload: dict) -> Optional[Booking]:
        """Procesa webhooks de Calendly"""

    async def process_calcom_webhook(self, payload: dict) -> Optional[Booking]:
        """Procesa webhooks de Cal.com"""
```

**Valor**: ⭐⭐⭐⭐⭐ - Abstracción elegante multi-calendario.

### 5.3 Sistema GDPR Completo (`core/gdpr.py`)

```python
class GDPRManager:
    """Cumplimiento GDPR completo"""

    async def export_user_data(self, platform_user_id: str) -> dict:
        """Right to Access - Exporta todos los datos del usuario"""
        return {
            "personal_info": {...},
            "messages": [...],
            "interactions": [...],
            "consents": [...],
            "export_date": datetime
        }

    async def delete_user_data(self, platform_user_id: str) -> bool:
        """Right to be Forgotten - Elimina todos los datos"""
        # Elimina de todas las tablas
        # Registra en audit log

    async def anonymize_user_data(self, platform_user_id: str) -> bool:
        """Anonimiza datos manteniendo estadísticas"""
        # Reemplaza PII con hashes
        # Mantiene datos agregados

    async def record_consent(
        self,
        platform_user_id: str,
        consent_type: str,
        granted: bool
    ) -> None:
        """Registra consentimiento con timestamp"""

    async def get_audit_log(self, platform_user_id: str) -> List[AuditEntry]:
        """Obtiene historial de acciones GDPR"""
```

**Valor**: ⭐⭐⭐⭐⭐ - Esencial para compliance en EU.

### 5.4 Cliente LLM Multi-Proveedor (`core/llm.py`)

```python
class LLMClient:
    """Cliente unificado para múltiples proveedores LLM"""

    PROVIDERS = {
        "groq": GroqProvider,      # Más rápido, económico
        "openai": OpenAIProvider,   # GPT-4, más capaz
        "anthropic": AnthropicProvider  # Claude, mejor razonamiento
    }

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        provider: str = "groq",
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 500
    ) -> str:
        """Genera respuesta usando el proveedor especificado"""

    async def generate_with_fallback(
        self,
        prompt: str,
        providers: List[str] = ["groq", "openai", "anthropic"]
    ) -> str:
        """Intenta proveedores en orden hasta éxito"""
```

**Valor**: ⭐⭐⭐⭐ - Flexibilidad y resiliencia en LLM.

### 5.5 Clasificador de Intenciones (`core/intent_classifier.py`)

```python
INTENTS = {
    "greeting": "Saludo inicial",
    "question_product": "Pregunta sobre producto",
    "question_price": "Consulta de precio",
    "question_availability": "Disponibilidad",
    "booking_request": "Quiere agendar",
    "purchase_intent": "Intención de compra",
    "objection_price": "Objeción por precio",
    "objection_time": "Objeción por tiempo",
    "complaint": "Queja o problema",
    "gratitude": "Agradecimiento",
    "farewell": "Despedida",
    "off_topic": "Fuera de tema",
    "spam": "Spam/promoción",
    "request_human": "Pide hablar con humano",
    "content_request": "Pide contenido específico",
    "testimonial": "Comparte testimonio",
    "referral": "Viene referido"
}

class IntentClassifier:
    async def classify(self, message: str, context: dict) -> Tuple[str, float]:
        """Clasifica intención con score de confianza"""
        return (intent, confidence)
```

**Valor**: ⭐⭐⭐⭐ - Taxonomía completa de intenciones para e-commerce.

---

## ⚠️ 6. Problemas y Technical Debt

### 6.1 Código Duplicado

| Problema | Ubicación | Severidad | Recomendación |
|----------|-----------|-----------|---------------|
| Intent Classifier duplicado | Existe en main repo y aquí | 🟡 Media | Consolidar en un solo lugar |
| RAG Engine duplicado | Existe en main repo y aquí | 🟡 Media | Usar versión de main como librería |
| Memory Engine duplicado | Existe en main repo y aquí | 🟡 Media | Consolidar |

### 6.2 Dependencias Desactualizadas

| Paquete | Versión Actual | Última Estable | Riesgo |
|---------|----------------|----------------|--------|
| anthropic | >=0.7.0 | 0.40+ | 🟡 Muchas versiones atrás |
| openai | >=1.0.0 | 1.50+ | 🟢 Bajo (semver) |
| pydantic | >=2.0.0 | 2.10+ | 🟢 Bajo |

### 6.3 Problemas de Arquitectura

| Problema | Descripción | Severidad | Recomendación |
|----------|-------------|-----------|---------------|
| Memory en JSON | `memory.py` usa archivos JSON, no escala | 🔴 Alta | Migrar a Redis o PostgreSQL |
| Sin rate limiting | APIs sin límites de requests | 🟡 Media | Agregar middleware de rate limit |
| Secrets en código | Algunos ejemplos con keys hardcodeadas | 🔴 Alta | Auditar y limpiar |
| Sin health checks | Falta endpoint `/health` robusto | 🟡 Media | Agregar health checks |
| Sin métricas | No hay Prometheus/OpenTelemetry | 🟡 Media | Agregar observabilidad |

### 6.4 Bugs Potenciales

| Bug | Ubicación | Descripción | Severidad |
|-----|-----------|-------------|-----------|
| Race condition | `memory.py` | Escritura concurrente a JSON | 🟡 Media |
| Sin retry | `instagram.py` | Falla silenciosa en errores de red | 🟡 Media |
| Timezone naive | Varios archivos | Uso de `datetime.now()` sin tz | 🟢 Baja |

### 6.5 Technical Debt

1. **Tests insuficientes**: Cobertura estimada <30%
2. **Documentación**: Sin docstrings en muchas funciones
3. **Type hints**: Inconsistentes a lo largo del código
4. **Logging**: Uso de `print()` en lugar de `logging`
5. **Config management**: Mezcla de env vars y hardcoding

---

## 📈 7. Resumen Ejecutivo

### 7.1 Estadísticas Generales

| Métrica | Valor |
|---------|-------|
| Total archivos Python | ~68 |
| Líneas de código estimadas | ~15,000 |
| Módulos del Magic Slice cubiertos | 1 de 5 (20%) |
| Módulos totales cubiertos | 5 de 14 parciales (36%) |
| Calidad promedio | ⭐⭐⭐⭐ (4/5) |
| Deuda técnica | Media-Alta |

### 7.2 Fortalezas

1. ✅ **Sistema de pagos robusto** - Stripe + Hotmart completamente funcional
2. ✅ **Integración de calendarios** - Calendly + Cal.com bien implementado
3. ✅ **GDPR compliance** - Sistema completo de privacidad
4. ✅ **Multi-LLM** - Flexibilidad entre Groq, OpenAI y Anthropic
5. ✅ **Intent classification** - 17 intenciones bien definidas
6. ✅ **Dashboard admin** - UI funcional con Streamlit

### 7.3 Debilidades

1. ❌ **Sin scraping de contenido** - No indexa contenido público del creator
2. ❌ **Sin análisis de tono** - No clona el estilo del creator
3. ❌ **Sin transcripción** - No procesa audio/video
4. ❌ **Sin conectores YouTube/Podcast** - Limitado a Instagram/Telegram
5. ❌ **Memory no escalable** - JSON files no sirven para producción

### 7.4 Recomendación Final

| Opción | Recomendación | Justificación |
|--------|---------------|---------------|
| **MERGE parcial** | ✅ **RECOMENDADO** | Fusionar módulos valiosos (payments, calendar, gdpr) al repo principal |
| Mantener separado | ⚠️ No recomendado | Duplicación de código genera deuda técnica |
| Deprecar | ❌ No recomendado | Hay código muy valioso que perder |

### 7.5 Plan de Acción Sugerido

1. **Fase 1 - Extracción** (inmediato):
   - Mover `payments.py`, `calendar.py`, `gdpr.py` al repo principal como módulos
   - Consolidar `intent_classifier.py` y `rag.py` (eliminar duplicados)

2. **Fase 2 - Migración** (corto plazo):
   - Migrar `memory.py` de JSON a Redis/PostgreSQL
   - Unificar modelos SQLAlchemy con el repo principal

3. **Fase 3 - Dashboard** (medio plazo):
   - Evaluar si mantener Streamlit o migrar a React (consistencia con frontend)
   - Las páginas del dashboard pueden ser referencia para features

4. **Fase 4 - Deprecación** (largo plazo):
   - Una vez migrado todo lo valioso, archivar este repo
   - Mantener como referencia histórica

---

## 📎 Anexo: Archivos Analizados

| Archivo | Líneas | Analizado |
|---------|--------|-----------|
| core/dm_agent.py | ~300 | ✅ |
| core/intent_classifier.py | ~200 | ✅ |
| core/rag.py | ~250 | ✅ |
| core/llm.py | ~180 | ✅ |
| core/memory.py | ~150 | ✅ |
| core/instagram.py | ~200 | ✅ |
| core/telegram_adapter.py | ~180 | ✅ |
| core/analytics.py | ~150 | ✅ |
| core/nurturing.py | ~200 | ✅ |
| core/payments.py | ~800 | ✅ |
| core/calendar.py | ~1065 | ✅ |
| core/gdpr.py | ~860 | ✅ |
| api/main.py | ~150 | ✅ |
| api/models.py | ~79 | ✅ |
| admin/dashboard.py | ~254 | ✅ |

---

*Auditoría generada automáticamente por Claude Code*
*Siguiente repo a auditar: `creator-s-connect-hub`*
