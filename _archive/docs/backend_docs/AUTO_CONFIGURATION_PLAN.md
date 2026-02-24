# Auto-Configuration System - Plan Detallado

## Objetivo
Crear un clon de IA del usuario (Stefano Bonanno) que pueda:
- Conversar con seguidores sobre su contenido **sin alucinaciones**
- **Citar** contenido real del creador
- Ofrecer productos con precios verificados
- Agendar llamadas
- Asesorar basándose en contenido real
- Responder como el creador respondería (ToneProfile)

---

## Tecnología Disponible (Inventario Completo)

### 1. Sistema V2 Anti-Alucinaciones
**Ubicación:** `backend/ingestion/v2/`

#### ProductDetector (`product_detector.py`)
- **6 señales** para detectar productos reales:
  1. `DEDICATED_PAGE` - URL contiene /servicio, /producto, /curso
  2. `CTA_PRESENT` - "comprar", "reservar", "apúntate"
  3. `PRICE_VISIBLE` - Precio con regex (€X, X€, X EUR)
  4. `SUBSTANTIAL_DESCRIPTION` - >100 palabras
  5. `PAYMENT_LINK` - Stripe, Calendly, PayPal, etc.
  6. `CLEAR_TITLE` - Título 5-100 chars
- **Requiere 3+ señales** para considerar algo un producto
- **Aborta si >20 productos** (indica error de detección)
- **Precio NUNCA inventado** - solo regex extraction con `price_source_text`

#### SanityChecker (`sanity_checker.py`)
- 6 checks progresivos que abortan si algo es sospechoso:
  1. Product count (máx 20)
  2. Source URLs presentes
  3. Same domain check
  4. Price ranges (0-50000€)
  5. Confidence scores
  6. URL re-verification (fetch live)

#### IngestionPipeline (`pipeline.py`)
```
1. LIMPIAR datos anteriores
2. SCRAPEAR website
3. DETECTAR productos (señales)
4. SANITY CHECKS
5. GUARDAR solo si TODO pasa
```

#### InstagramIngestion (`instagram_ingestion.py`)
- 4 sanity checks por post:
  1. Caption >10 chars
  2. Fecha válida (no futura, <3 años)
  3. No duplicados
  4. Contenido útil (no solo hashtags)
- Guarda posts + content_chunks para RAG

### 2. Transcriber (Whisper)
**Ubicación:** `backend/ingestion/transcriber.py`

- **Soporta**: mp3, wav, m4a, ogg, webm, mp4, mov, avi
- **Límite**: 25MB por archivo
- **Output**: `Transcript` con `segments` (timestamp start/end)
- **Uso**: Transcribir reels/videos de Instagram

### 3. Citation Service
**Ubicación:** `backend/core/citation_service.py`

- **ContentChunk**: Fragmentos de contenido indexados
- **Search**: Keyword matching con normalización (sin acentos)
- **CitationContext**: Inyectable en prompts del bot
- **Persistencia**: PostgreSQL (principal) + JSON (backup)

### 4. ToneProfile
**Ubicación:** `backend/core/tone_profile_db.py`

- Analiza captions de posts para extraer:
  - Vocabulario frecuente
  - Emojis preferidos
  - Longitud de mensajes
  - Estilo (formal/casual)
  - Temas recurrentes
- Guardado en PostgreSQL con `confidence_score`

### 5. Guardrails
**Ubicación:** `backend/core/guardrails.py`

- **Validación de precios**: Solo precios conocidos de productos
- **URLs autorizadas**: Whitelist de dominios
- **Detección de alucinaciones**: Patrones como "te llamo en X minutos"
- **Fallback responses**: Si algo falla, respuesta segura

### 6. Modelos de Base de Datos
**Ubicación:** `backend/api/models.py`

```sql
-- Creator
- name, email, api_key
- bot_active, clone_tone, clone_style
- instagram_connected, instagram_username
- website_url, business_description
- onboarding_completed

-- Product
- name, description, price, currency
- payment_link, source_url
- price_verified, confidence

-- ContentChunk (RAG)
- chunk_id, content, source_type
- source_id, source_url, title

-- InstagramPost
- post_id, caption, permalink
- media_type, media_url
- likes_count, comments_count

-- ToneProfile
- creator_id, profile_data (JSON)
- analyzed_posts_count, confidence_score
```

---

## Pipeline de Auto-Configuración

### Fase 1: Recopilación de Datos

#### 1.1 Scraping Instagram (50 posts)
```python
# Usar InstaloaderScraper existente
from ingestion.instagram_scraper import InstaloaderScraper
from ingestion.v2.instagram_ingestion import ingest_instagram_v2

result = await ingest_instagram_v2(
    creator_id="stefano_bonanno",
    instagram_username="stefanobonanno",
    max_posts=50,
    clean_before=True
)

# Output:
# - posts_scraped: 50
# - posts_passed_sanity: ~45 (los que pasan validación)
# - rag_chunks_created: ~45 (para el sistema de citas)
```

#### 1.2 Transcripción de Videos (Reels)
```python
from ingestion.transcriber import get_transcriber

transcriber = get_transcriber()

for post in posts_with_video:
    if post.media_type in ['VIDEO', 'REEL']:
        transcript = await transcriber.transcribe_url(
            url=post.media_url,
            language="es",
            include_timestamps=True
        )
        # Agregar transcripción como content chunk adicional
        # source_type = 'instagram_reel_transcript'
```

#### 1.3 Scraping Website
```python
from ingestion.v2.pipeline import ingest_website_v2

result = await ingest_website_v2(
    creator_id="stefano_bonanno",
    website_url="https://stefanobonanno.com",
    max_pages=10,
    clean_before=True,
    re_verify=True
)

# Output:
# - pages_scraped: 10
# - products_detected: 3-5 (verificados con señales)
# - sanity_checks: [✓ product_count, ✓ urls, ✓ prices...]
```

#### 1.4 Ingesta de DMs (50 conversaciones)
```python
# Los DMs se obtienen via webhook (ya configurado)
# O desde Instagram Graph API:
# GET /{page-id}/conversations?fields=messages{...}

# Cada DM se convierte en content_chunk:
# - source_type = 'dm_conversation'
# - source_id = conversation_id
# - content = "Pregunta: X\nRespuesta de Stefano: Y"
```

### Fase 2: Procesamiento y Análisis

#### 2.1 Generación de ToneProfile
```python
from ingestion.tone_analyzer import ToneAnalyzer

analyzer = ToneAnalyzer()
profile = analyzer.analyze_content([
    post.caption for post in posts
    if len(post.caption) > 20
])

# Output ToneProfile:
# {
#   "vocabulary": ["abundancia", "plenitud", "energía"...],
#   "emoji_style": ["🙌", "✨", "💪"...],
#   "avg_message_length": 180,
#   "formality": 0.3,  # 0=casual, 1=formal
#   "recurring_topics": ["fitness", "mindset", "nutrición"],
#   "signature_phrases": ["para eso estamos", "vamos a por ello"]
# }

await save_tone_profile_db(creator_id, profile.to_dict())
```

#### 2.2 Indexación RAG con Embeddings
```python
from core.citation_service import index_creator_posts

# Ya se hace automáticamente en instagram_ingestion
# Pero podemos enriquecer con más fuentes:

await index_creator_posts(
    creator_id="stefano_bonanno",
    posts=[
        # Posts de Instagram
        {"post_id": "abc", "caption": "...", "url": "..."},
        # Transcripciones de videos
        {"post_id": "video_123", "caption": transcript.full_text,
         "post_type": "instagram_reel_transcript"},
        # Contenido de website
        {"post_id": f"web_{page.url}", "caption": page.content,
         "post_type": "website_page"}
    ]
)
```

#### 2.3 Detección y Verificación de Productos
```python
# Ya incluido en ingest_website_v2, pero resumen:

products = [
    {
        "name": "Fitpack 90",
        "description": "Programa de 90 días...",
        "price": 297.0,  # Extraído con regex, verificado
        "source_url": "https://stefanobonanno.com/fitpack",
        "signals_matched": ["dedicated_page", "cta", "price_visible"],
        "confidence": 0.83
    }
]

# Cada producto tiene:
# - price_source_text: "297€ - Pago único" (literal del HTML)
# - source_url: URL donde se encontró
# - price_verified: True (pasó sanity checks)
```

### Fase 3: Configuración del Bot

#### 3.1 Actualización del Creator
```python
# Actualizar campos del creator en DB:
creator = {
    "name": "stefano_bonanno",
    "clone_name": "Stefano",
    "clone_tone": "friendly",  # Del ToneProfile
    "clone_style": "Respondo de forma cercana y motivacional...",
    "business_description": "Coach de fitness y mindset...",
    "website_url": "https://stefanobonanno.com",
    "instagram_username": "stefanobonanno",
    "bot_active": True,
    "onboarding_completed": True
}
```

#### 3.2 Productos en Dashboard
```python
# Los productos detectados se guardan automáticamente
# con source_url para trazabilidad:

for product in verified_products:
    Product.create(
        creator_id=creator.id,
        name=product.name,
        description=product.description,
        price=product.price,
        currency=product.currency,
        source_url=product.source_url,
        price_verified=True,
        confidence=product.confidence
    )
```

### Fase 4: Sistema de Respuesta del Bot

#### 4.1 Flujo de Respuesta
```
1. Usuario envía mensaje
2. Buscar contenido relevante (RAG)
3. Inyectar citations en prompt
4. Generar respuesta con LLM
5. Validar con Guardrails
6. Enviar respuesta
```

#### 4.2 Prompt con Citations
```python
from core.citation_service import get_citation_prompt_section

citation_section = get_citation_prompt_section(
    creator_id="stefano_bonanno",
    query="¿Cuánto cuesta el Fitpack?",
    min_relevance=0.25
)

# Output:
# """
# CONTENIDO RELEVANTE DEL CREADOR:
#
# [Instagram Post - 15 Nov 2024]
# "El Fitpack 90 es mi programa estrella..."
# URL: https://instagram.com/p/xxx
#
# [Website - Fitpack]
# "Programa de transformación de 90 días..."
# Precio verificado: 297€
# URL: https://stefanobonanno.com/fitpack
# """
```

#### 4.3 Validación con Guardrails
```python
from core.guardrails import get_response_guardrail

guardrail = get_response_guardrail()
validation = guardrail.validate_response(
    query="¿Cuánto cuesta el programa?",
    response="El Fitpack cuesta 297€, puedes...",
    context={
        "products": products,  # Para validar precios
        "allowed_urls": ["stefanobonanno.com", "stripe.com"]
    }
)

if not validation["valid"]:
    # Usar fallback o corregir
    response = guardrail.get_safe_response(...)
```

---

## Estructura del Endpoint

### `/onboarding/full-auto-setup`

```python
@router.post("/full-auto-setup")
async def full_auto_setup(request: FullAutoSetupRequest):
    """
    Configuración automática completa del clon.

    Input:
    - instagram_username: str
    - website_url: Optional[str]
    - creator_id: str

    Output:
    - creator: Creator actualizado
    - products: Lista de productos detectados
    - content_indexed: Estadísticas de indexación
    - tone_profile: Perfil de tono generado
    - status: 'success' | 'partial' | 'failed'
    """

    result = {
        "creator_id": request.creator_id,
        "steps_completed": [],
        "errors": []
    }

    # PASO 1: Scrapear Instagram (50 posts)
    instagram_result = await ingest_instagram_v2(
        creator_id=request.creator_id,
        instagram_username=request.instagram_username,
        max_posts=50
    )
    result["instagram"] = instagram_result.to_dict()
    result["steps_completed"].append("instagram_scraping")

    # PASO 2: Transcribir videos (si hay)
    transcription_results = []
    for post in get_video_posts(request.creator_id):
        try:
            transcript = await transcribe_post_video(post)
            await save_transcript_as_chunk(request.creator_id, post, transcript)
            transcription_results.append({"post_id": post.post_id, "success": True})
        except Exception as e:
            transcription_results.append({"post_id": post.post_id, "error": str(e)})
    result["transcriptions"] = transcription_results
    result["steps_completed"].append("video_transcription")

    # PASO 3: Scrapear website (productos)
    if request.website_url:
        website_result = await ingest_website_v2(
            creator_id=request.creator_id,
            website_url=request.website_url,
            max_pages=10
        )
        result["website"] = website_result.to_dict()
        result["steps_completed"].append("website_scraping")

    # PASO 4: Generar ToneProfile
    tone_profile = await generate_tone_profile(request.creator_id)
    await save_tone_profile_db(request.creator_id, tone_profile)
    result["tone_profile"] = tone_profile
    result["steps_completed"].append("tone_profile")

    # PASO 5: Actualizar Creator con datos extraídos
    await update_creator_from_analysis(
        creator_id=request.creator_id,
        instagram_data=instagram_result,
        website_data=website_result,
        tone_profile=tone_profile
    )
    result["steps_completed"].append("creator_update")

    # PASO 6: Activar bot
    await activate_bot(request.creator_id)
    result["steps_completed"].append("bot_activated")

    return result
```

---

## Auto-Fill Dashboard

### Campos que se auto-rellenan:

| Campo | Fuente | Método |
|-------|--------|--------|
| `clone_name` | Instagram profile | Nombre antes de apellido |
| `clone_tone` | ToneProfile | Análisis de captions |
| `business_description` | Website | Meta description + análisis |
| `products` | Website | ProductDetector V2 |
| `website_url` | Input usuario | Directo |
| `instagram_username` | Input usuario | Directo |
| `recent_posts` | Instagram API | 50 más recientes |
| `FAQs` | DMs + Website | Extracción de preguntas frecuentes |
| `availability` | Manual | Usuario configura horarios |

---

## Flujo Completo del Usuario

```
1. Usuario entra a /register
2. Crea cuenta (email, password)
3. Redirect a /onboarding
4. Introduce Instagram + Website
5. Click "Crear mi clon"
6. [10 segundos de loading visual]
   - Backend ejecuta full-auto-setup:
     a. Scrapea 50 posts Instagram
     b. Transcribe videos/reels
     c. Scrapea website
     d. Detecta productos
     e. Genera ToneProfile
     f. Indexa contenido para RAG
     g. Actualiza Creator en DB
7. Pantalla de éxito (5 segundos)
8. Redirect a /dashboard
9. Dashboard muestra:
   - Posts indexados: 50
   - Productos detectados: 3
   - Bot: Activo
   - Últimas conversaciones
   - Analytics
```

---

## Consideraciones Técnicas

### Timeouts
- Instagram scraping: ~150 segundos (50 posts × 3s delay)
- Website scraping: ~30 segundos (10 páginas)
- Transcription: ~10-30 segundos por video
- **Total**: 3-5 minutos

### Solución para UX
1. **Background job**: Ejecutar en celery/background task
2. **Polling**: Frontend hace polling cada 5s
3. **WebSocket**: Notificar progreso en tiempo real
4. **Quick-setup primero**: Crear clon básico, enriquecer después

### Arquitectura Recomendada
```
[Frontend]
    |
    v
[/onboarding/quick-setup] → Crea clon básico (2s)
    |
    v
[Redirect a Dashboard]
    |
    v
[Background: full-auto-setup] → Enriquece datos (3-5min)
    |
    v
[WebSocket/Polling] → Actualiza dashboard cuando termine
```

---

## Archivos a Modificar/Crear

1. **`api/routers/onboarding.py`**
   - Añadir `/full-auto-setup` endpoint
   - Añadir `/setup-status/{creator_id}` para polling

2. **`core/auto_configurator.py`** (NUEVO)
   - Orquestador que une todas las piezas
   - Manejo de errores parciales
   - Logging detallado

3. **`ingestion/instagram_scraper.py`**
   - Asegurar que extrae `media_type` y `media_url` para videos

4. **`frontend/src/pages/Onboarding.tsx`**
   - Añadir polling de estado
   - Mostrar progreso detallado

---

## Métricas de Éxito

- [ ] 50 posts de Instagram indexados
- [ ] Videos transcritos con Whisper
- [ ] 3-5 productos detectados del website
- [ ] ToneProfile con confidence >0.7
- [ ] Bot responde citando contenido real
- [ ] Guardrails bloquean precios inventados
- [ ] Dashboard muestra datos reales
