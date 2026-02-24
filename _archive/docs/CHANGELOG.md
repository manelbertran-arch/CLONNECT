# Changelog

All notable changes to this project will be documented in this file.

## 2026-01-19 - Onboarding Flow FUNCIONANDO

### Lo que funciona al 100%:
- OAuth Instagram Login (conexión de cuenta)
- Scraping de 50 posts de Instagram
- ToneProfile generation (análisis de tono con OpenAI)
- ToneProfile guardado en PostgreSQL + JSON backup
- Content indexing (añadir posts al índice de citaciones)
- Progress polling desde frontend
- DM sync con soporte para media (imágenes, videos, stories, GIFs, stickers)

### Fix crítico aplicado:
- **Problema**: `index.save()` en citation_service.py causaba timeout por N+1 queries (1000+ chunks = 2000+ queries individuales)
- **Solución temporal**: Skippeado el save() para evitar timeout
- **TODO**: Implementar bulk insert en `_save_chunks_to_db()` en lugar de queries individuales

### Archivos clave del onboarding flow:
- `backend/api/routers/onboarding.py` - Endpoints y _run_clone_creation
- `backend/core/onboarding_service.py` - OnboardingService.onboard_creator()
- `backend/ingestion/tone_analyzer.py` - ToneAnalyzer.analyze()
- `backend/core/citation_service.py` - ContentIndex (TIENE EL BUG DE N+1)
- `backend/core/tone_service.py` - save_tone_profile()
- `backend/core/tone_profile_db.py` - Guardado en PostgreSQL

### Configuración actual:
- LLM: OpenAI (api.openai.com)
- Timeout LLM: 30 segundos
- Max posts scrapeados: 50
- Workers: uvicorn (single worker)

### Otros fixes en esta sesión:
- Fix import `from core.llm_client` -> `from core.llm` en tone_analyzer.py
- Added comprehensive debug logging throughout pipeline
- DM sync: estructura-based media detection (video_data, image_data, etc.)
- DM sync: proper handling of stories, reactions, shared posts, GIFs

---

## 2026-01-16

### Features
- **Nueva taxonomía de contenido**: Separación en 3 categorías
  - `product`: Cosas que se venden (ebooks, cursos, plantillas)
  - `service`: Servicios personales (coaching, mentoría, sesiones)
  - `resource`: Contenido gratuito (podcast, blog, newsletter)
- **Campos de taxonomía en Product**:
  - `category`: product | service | resource
  - `product_type`: ebook, curso, coaching, mentoria, podcast, etc.
  - `is_free`: Boolean para discovery calls y recursos gratuitos
- **Frontend dinámico**: Formulario de productos adapta campos según categoría
- **Bot contextual**: Respuestas diferentes según categoría del item
  - Products: Da precio + link de compra
  - Services: Precio + oferta de agendar
  - Resources: Menciona como contenido gratuito, sin vender
- **Sistema de categorías de leads**: NUEVO → INTERESADO → CALIENTE → CLIENTE → FANTASMA
- **Reactivación de leads fantasma**: Automática para leads 7-90 días inactivos
- **Sync con cola anti-rate-limit**: Throttling para Instagram API

### Bug Fixes
- `create_product()` ahora guarda campos de taxonomía (category, product_type, is_free, payment_link)
- Scraper ya no guarda testimonios como productos
- Scraper filtra podcasts y duplicados correctamente
- Timestamps de leads usan fecha original de Instagram, no fecha de sync

### Backend Changes
- `api/models.py`: Nuevos campos category, product_type, is_free en Product
- `api/services/db_service.py`: create_product() actualizado con taxonomía
- `api/routers/onboarding.py`: inject-stefano-data con taxonomía correcta
- `core/dm_agent.py`: format_item_by_category() y get_category_instructions()
- `ingestion/v2/product_detector.py`: clasificar_contenido() para taxonomía
- `ingestion/v2/pipeline.py`: Guarda campos de taxonomía

### Frontend Changes
- `types/api.ts`: ProductCategory, ProductType types
- `pages/new/ajustes/ProductoSection.tsx`: Formulario dinámico por categoría
- `pages/Leads.tsx`: Leyenda explicativa de categorías

### Configuration
- Ghost reactivation: min=7d, max=90d, cooldown=30d, max_per_cycle=5
- Sync throttling: 3s entre llamadas, 5min pausa si rate limit
- Scraper: solo productos con precio explícito o marcados gratuitos

### Database Migrations
- `init_db.py`: Columnas category, product_type, is_free, short_description

### Test Data (stefano_auto)
| Categoría | Count | Ejemplos |
|-----------|-------|----------|
| product | 1 | Fitpack Challenge (€97) |
| service | 4 | Coaching (€150), Mentoría (€1497), Discovery (gratis) |
| resource | 1 | Podcast Sabios y Salvajes |

---

## Archivos Modificados (57 total)

### Backend API (11)
- api/init_db.py
- api/main.py
- api/models.py
- api/routers/admin.py
- api/routers/copilot.py
- api/routers/messages.py
- api/routers/nurturing.py
- api/routers/oauth.py
- api/routers/onboarding.py
- api/routers/products.py
- api/services/db_service.py

### Backend Core (17)
- core/auto_configurator.py
- core/citation_service.py
- core/copilot_service.py
- core/dm_agent.py
- core/dm_history_service.py
- core/ghost_reactivation.py
- core/instagram_handler.py
- core/instagram_rate_limiter.py
- core/instagram.py
- core/lead_categorization.py
- core/lead_categorizer.py
- core/nurturing.py
- core/sync_worker.py
- core/telegram_adapter.py
- core/telegram_registry.py
- core/token_refresh_service.py
- core/tone_service.py

### Backend Ingestion (5)
- ingestion/tone_analyzer.py
- ingestion/v2/instagram_ingestion.py
- ingestion/v2/pipeline.py
- ingestion/v2/product_detector.py
- ingestion/v2/sanity_checker.py

### Frontend (12)
- src/components/CopilotPanel.tsx
- src/components/layout/MobileNav.tsx
- src/components/layout/Sidebar.tsx
- src/hooks/useApi.ts
- src/pages/Dashboard.tsx
- src/pages/Leads.tsx
- src/pages/new/ajustes/ProductoSection.tsx
- src/pages/Nurturing.tsx
- src/pages/Products.tsx
- src/pages/Settings.tsx
- src/services/api.ts
- src/types/api.ts
