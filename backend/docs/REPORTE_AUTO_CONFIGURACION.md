# Reporte: Sistema de Auto-Configuración de Clones V2

**Fecha:** 14 Enero 2026
**Proyecto:** Clonnect
**Objetivo:** Crear un sistema que auto-configure clones de IA con zero-hallucination, contenido citable, y datos 100% reales

---

## 1. Contexto y Objetivo

El usuario necesitaba un sistema que, cuando alguien se registra y entra a la página de onboarding "Creando tu clon", el backend ejecute automáticamente:

1. Scraping de 50 posts de Instagram
2. Transcripción de videos/reels (opcional)
3. Scraping del website + detección de productos
4. Generación de ToneProfile
5. Indexación de contenido para RAG (citable)
6. Auto-rellenado del dashboard

Todo usando la tecnología **V2 anti-alucinaciones** ya existente en el repositorio.

---

## 2. Análisis de Tecnología Existente

### 2.1 Sistema V2 de Ingestion (Ya existía)

**Ubicación:** `/backend/ingestion/v2/`

| Archivo | Función |
|---------|---------|
| `pipeline.py` | Pipeline de 5 pasos: limpiar → scrapear → detectar → verificar → guardar |
| `product_detector.py` | Detecta productos con 6 señales (requiere 3+) |
| `sanity_checker.py` | 6 checks que abortan si algo es sospechoso |
| `instagram_ingestion.py` | Ingesta de posts con 4 sanity checks |

**Señales de Producto (ProductDetector):**
1. `DEDICATED_PAGE` - URL contiene /servicio, /producto, /curso
2. `CTA_PRESENT` - "comprar", "reservar", "apúntate"
3. `PRICE_VISIBLE` - Precio extraído con regex (€X, X€)
4. `SUBSTANTIAL_DESCRIPTION` - >100 palabras
5. `PAYMENT_LINK` - Stripe, Calendly, PayPal
6. `CLEAR_TITLE` - Título 5-100 chars

**Sanity Checks de Instagram:**
1. Caption >10 chars
2. Fecha válida (no futura, <3 años)
3. No duplicados
4. Contenido útil (no solo hashtags)

### 2.2 Transcriber (Ya existía)

**Ubicación:** `/backend/ingestion/transcriber.py`

- Usa Whisper API de OpenAI
- Soporta: mp3, wav, m4a, ogg, webm, mp4, mov, avi
- Límite: 25MB por archivo
- Output: `Transcript` con segments (start/end timestamps)

### 2.3 Citation Service (Ya existía)

**Ubicación:** `/backend/core/citation_service.py`

- `ContentChunk`: Fragmentos indexados con `source_url`
- `CreatorContentIndex`: Búsqueda por keywords
- Persistencia: PostgreSQL + JSON backup
- Inyección en prompts del bot

### 2.4 ToneProfile (Ya existía)

**Ubicación:** `/backend/core/tone_profile_db.py`

- Analiza captions para extraer estilo
- Guarda en PostgreSQL
- Campos: formality, energy, emoji_style, frequent_words

### 2.5 Guardrails (Ya existía)

**Ubicación:** `/backend/core/guardrails.py`

- Valida precios contra productos conocidos
- Whitelist de URLs
- Detecta patrones de alucinación
- Fallback responses si algo falla

---

## 3. Archivos Creados

### 3.1 Plan Detallado

**Archivo:** `/backend/docs/AUTO_CONFIGURATION_PLAN.md`

Documento de 400+ líneas que incluye:
- Inventario completo de tecnología disponible
- Pipeline de auto-configuración paso a paso
- Estructura del endpoint `/onboarding/full-auto-setup`
- Campos del dashboard que se auto-rellenan
- Flujo completo del usuario
- Consideraciones de timeouts y UX
- Arquitectura recomendada (background jobs)

### 3.2 Auto Configurator (Orquestador Principal)

**Archivo:** `/backend/core/auto_configurator.py`

```python
class AutoConfigurator:
    """
    Orquestador que combina todas las tecnologías V2.

    Pipeline:
    1. _scrape_instagram() → ingest_instagram_v2 (50 posts, sanity checks)
    2. _transcribe_videos() → Whisper API para reels
    3. _scrape_website() → ingest_website_v2 (productos V2)
    4. _generate_tone_profile() → Análisis de estilo
    5. _update_creator() → Actualiza DB y activa bot
    """
```

**Características:**
- `AutoConfigResult`: Dataclass con estadísticas completas
- Manejo de errores parciales (continúa si un paso falla)
- Status: 'success', 'partial', 'failed'
- Logging detallado en cada paso
- Función de conveniencia: `auto_configure_clone()`

### 3.3 Nuevos Endpoints en Onboarding Router

**Archivo:** `/backend/api/routers/onboarding.py`

**Endpoints añadidos:**

```python
# Request model
class FullAutoSetupRequest(BaseModel):
    creator_id: str
    instagram_username: str
    website_url: Optional[str] = None
    max_posts: int = 50
    transcribe_videos: bool = False

# Endpoint síncrono (espera a que termine)
@router.post("/full-auto-setup")
async def full_auto_setup(request: FullAutoSetupRequest):
    """Ejecuta todo el pipeline V2 y retorna resultado."""

# Endpoint en background (retorna inmediatamente)
@router.post("/full-auto-setup-background")
async def full_auto_setup_background(request, background_tasks):
    """Inicia proceso en background, retorna ID para polling."""

# Status del proceso en background
@router.get("/full-auto-setup/{creator_id}/status")
async def get_full_auto_setup_status(creator_id: str):
    """Retorna progreso del auto-setup en background."""
```

---

## 4. Archivos Modificados

### 4.1 Frontend Onboarding

**Archivo:** `/frontend/src/pages/Onboarding.tsx`

**Cambio:** El flujo de submit ahora:

```typescript
// ANTES: Solo quick-setup
await api.post('/onboarding/quick-setup', {...});

// DESPUÉS: Quick-setup + Full auto-setup en background
// 1. Quick setup para respuesta inmediata
await api.post('/onboarding/quick-setup', {...});

// 2. Full auto-setup en background (V2 zero-hallucination)
await api.post('/onboarding/full-auto-setup-background', {
    creator_id: creatorId,
    instagram_username: instagram.replace('@', ''),
    website_url: website || null,
    max_posts: 50,
    transcribe_videos: false
});
```

**Flujo UX:**
1. Usuario introduce Instagram + Website
2. Click "Crear mi clon"
3. Animación de loading 10 segundos
4. Pantalla de éxito 5 segundos
5. Redirect a Dashboard
6. (Background: full-auto-setup continúa procesando)

---

## 5. Flujo Completo del Sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                      USUARIO EN FRONTEND                         │
├─────────────────────────────────────────────────────────────────┤
│  /register → /onboarding → Introduce @instagram + website        │
│                    ↓                                              │
│              Click "Crear mi clon"                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                       FRONTEND (10s)                              │
├─────────────────────────────────────────────────────────────────┤
│  1. POST /onboarding/quick-setup                                  │
│     → Crea Creator básico en DB                                   │
│     → Marca onboarding_completed = true                           │
│     → Activa bot_active = true                                    │
│                                                                   │
│  2. POST /onboarding/full-auto-setup-background                   │
│     → Inicia proceso V2 en background                             │
│                                                                   │
│  3. Muestra animación de loading 10 segundos                      │
│  4. Muestra pantalla de éxito 5 segundos                          │
│  5. Redirect a /dashboard                                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   BACKEND (Background, 3-5 min)                   │
├─────────────────────────────────────────────────────────────────┤
│  AutoConfigurator.run():                                          │
│                                                                   │
│  PASO 1: Instagram Scraping V2                                    │
│  ├── InstaloaderScraper.get_posts(limit=50)                       │
│  ├── InstagramPostSanityChecker.check_post()                      │
│  │   ├── caption_not_empty (>10 chars)                            │
│  │   ├── valid_date (no futura, <3 años)                          │
│  │   ├── not_duplicate                                            │
│  │   └── useful_content (no solo hashtags)                        │
│  ├── save_instagram_posts_db()                                    │
│  └── save_content_chunks_db() → RAG indexing                      │
│                                                                   │
│  PASO 2: Video Transcription (opcional)                           │
│  ├── get_instagram_posts_db() → filter VIDEO/REELS                │
│  ├── Transcriber.transcribe_url()                                 │
│  └── CreatorContentIndex.add_post() → chunks RAG                  │
│                                                                   │
│  PASO 3: Website Scraping V2                                      │
│  ├── DeterministicScraper.scrape_website()                        │
│  ├── ProductDetector.detect_products()                            │
│  │   ├── _identify_service_pages()                                │
│  │   ├── _analyze_page() → 6 señales                              │
│  │   └── Requiere 3+ señales para ser producto                    │
│  ├── SanityChecker.verify()                                       │
│  │   ├── product_count (<20)                                      │
│  │   ├── source_urls present                                      │
│  │   ├── same_domain check                                        │
│  │   ├── price_ranges (0-50000€)                                  │
│  │   ├── confidence scores                                        │
│  │   └── URL re-verification (fetch live)                         │
│  ├── _save_products() → Product table                             │
│  └── _save_product_rag_docs() → RAG indexing                      │
│                                                                   │
│  PASO 4: ToneProfile Generation                                   │
│  ├── get_instagram_posts_db()                                     │
│  ├── _analyze_tone()                                              │
│  │   ├── emoji extraction                                         │
│  │   ├── avg message length                                       │
│  │   ├── formality score                                          │
│  │   ├── frequent words                                           │
│  │   └── topic detection                                          │
│  └── save_tone_profile_db()                                       │
│                                                                   │
│  PASO 5: Creator Update                                           │
│  ├── Update Creator in DB                                         │
│  │   ├── instagram_username                                       │
│  │   ├── website_url                                              │
│  │   ├── onboarding_completed = True                              │
│  │   └── bot_active = True (si confidence >= 0.5)                 │
│  └── Log completion                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     RESULTADO EN DB                               │
├─────────────────────────────────────────────────────────────────┤
│  creators:                                                        │
│  ├── name, instagram_username, website_url                        │
│  ├── bot_active = true                                            │
│  └── onboarding_completed = true                                  │
│                                                                   │
│  products: (detectados del website)                               │
│  ├── name, description, price, currency                           │
│  ├── source_url (trazabilidad)                                    │
│  ├── price_verified = true                                        │
│  └── confidence score                                             │
│                                                                   │
│  instagram_posts: (50 posts scrapeados)                           │
│  ├── caption, permalink, media_type                               │
│  ├── likes_count, comments_count                                  │
│  └── hashtags, mentions                                           │
│                                                                   │
│  content_chunks: (RAG para citations)                             │
│  ├── content, source_type, source_url                             │
│  └── chunk_index, title                                           │
│                                                                   │
│  tone_profiles:                                                   │
│  ├── profile_data (JSON)                                          │
│  ├── analyzed_posts_count                                         │
│  └── confidence_score                                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Cómo Funciona el Bot Después

Cuando un seguidor envía un mensaje al bot:

```
1. Recibe mensaje del usuario
        ↓
2. get_citation_prompt_section(creator_id, query)
   → Busca contenido relevante en content_chunks
   → Retorna contexto citable para inyectar en prompt
        ↓
3. LLM genera respuesta usando:
   - ToneProfile (estilo del creador)
   - Citations (contenido real con source_url)
   - Products (precios verificados)
        ↓
4. ResponseGuardrail.validate_response()
   - Valida precios contra productos conocidos
   - Valida URLs contra whitelist
   - Detecta patrones de alucinación
        ↓
5. Si válido → Envía respuesta
   Si inválido → Usa fallback response
```

---

## 7. Endpoints Disponibles

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/onboarding/quick-setup` | Setup rápido sin scraping (testing/demos) |
| POST | `/onboarding/full-auto-setup` | Auto-config completa V2 (síncrono) |
| POST | `/onboarding/full-auto-setup-background` | Auto-config en background |
| GET | `/onboarding/full-auto-setup/{id}/status` | Estado del proceso background |
| POST | `/onboarding/manual-setup` | Setup manual con scraping |
| GET | `/onboarding/{id}/status` | Checklist de onboarding |

---

## 8. Ejemplo de Request/Response

### Request: Full Auto Setup
```json
POST /onboarding/full-auto-setup
{
    "creator_id": "stefano_bonanno",
    "instagram_username": "stefanobonanno",
    "website_url": "https://stefanobonanno.com",
    "max_posts": 50,
    "transcribe_videos": false
}
```

### Response: AutoConfigResult
```json
{
    "success": true,
    "creator_id": "stefano_bonanno",
    "status": "success",
    "steps_completed": [
        "instagram_scraping",
        "website_scraping",
        "product_detection",
        "tone_profile",
        "creator_updated"
    ],
    "instagram": {
        "posts_scraped": 50,
        "posts_indexed": 47,
        "sanity_passed": 47
    },
    "transcription": {
        "videos_found": 15,
        "videos_transcribed": 0,
        "errors": []
    },
    "website": {
        "pages_scraped": 8,
        "products_detected": 4,
        "products_verified": 3
    },
    "tone_profile": {
        "generated": true,
        "confidence": 0.83
    },
    "rag": {
        "chunks_created": 52
    },
    "errors": [],
    "warnings": [],
    "duration_seconds": 145.3
}
```

---

## 9. Archivos Clave del Proyecto

```
backend/
├── core/
│   ├── auto_configurator.py      # NUEVO - Orquestador principal
│   ├── citation_service.py       # RAG + citations
│   ├── tone_profile_db.py        # ToneProfile persistence
│   └── guardrails.py             # Validación de respuestas
│
├── ingestion/
│   ├── v2/
│   │   ├── pipeline.py           # Pipeline V2 website
│   │   ├── product_detector.py   # 6 señales de producto
│   │   ├── sanity_checker.py     # Verificación anti-hallucination
│   │   └── instagram_ingestion.py # Instagram V2 con sanity
│   ├── instagram_scraper.py      # InstaloaderScraper
│   └── transcriber.py            # Whisper API
│
├── api/
│   ├── routers/
│   │   └── onboarding.py         # MODIFICADO - Nuevos endpoints
│   └── models.py                 # Creator, Product, ContentChunk, etc.
│
└── docs/
    ├── AUTO_CONFIGURATION_PLAN.md     # NUEVO - Plan detallado
    └── REPORTE_AUTO_CONFIGURACION.md  # NUEVO - Este reporte

frontend/
└── src/
    └── pages/
        └── Onboarding.tsx        # MODIFICADO - Usa full-auto-setup
```

---

## 10. Próximos Pasos Sugeridos

1. **Testing del Pipeline Completo**
   - Probar con cuenta de Stefano Bonanno real
   - Verificar que productos se detectan correctamente
   - Comprobar que ToneProfile refleja su estilo

2. **Optimización de Timeouts**
   - Instagram scraping puede tardar 2-3 min (50 posts × 3s delay)
   - Considerar aumentar workers/paralelismo

3. **Dashboard Auto-Fill**
   - Mostrar indicador "Procesando..." si background job activo
   - Refrescar datos cuando background job termine

4. **Transcripción de Videos**
   - Habilitar `transcribe_videos: true` para casos de uso específicos
   - Añadir UI para seleccionar videos a transcribir

5. **Monitoreo**
   - Añadir métricas de éxito/fallo del pipeline
   - Alertas si sanity checks fallan consistentemente

---

## 11. Conclusión

Se ha implementado un sistema completo de auto-configuración que:

- **Usa toda la tecnología V2 existente** (zero-hallucination)
- **Procesa automáticamente** 50 posts de Instagram
- **Detecta productos** con sistema de 6 señales
- **Genera ToneProfile** del creador
- **Indexa contenido** para citations (RAG)
- **Mantiene UX fluida** (10s loading visual, resto en background)
- **Es extensible** para añadir transcripción de videos

El clon resultante puede conversar con seguidores sin inventar información, citando contenido real del creador con URLs verificables.
