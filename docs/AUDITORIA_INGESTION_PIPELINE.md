# AUDITORÍA DEL PIPELINE DE INGESTION - CLONNECT

**Fecha:** 2026-01-25
**Versión:** 1.0
**Alcance:** Pipeline completo desde fuentes (Instagram, Website) hasta Dashboard + Bot RAG

---

## 1. RESUMEN EJECUTIVO

### 1.1 Arquitectura General del Pipeline

```
                          ┌─────────────────────────────────────────────────────────────┐
                          │                    FUENTES DE DATOS                         │
                          │                                                             │
                          │  ┌──────────────┐     ┌──────────────┐    ┌──────────────┐  │
                          │  │  Instagram   │     │   Website    │    │  Manual JSON │  │
                          │  │  Graph API   │     │  Scraping    │    │   Upload     │  │
                          │  └──────┬───────┘     └──────┬───────┘    └──────┬───────┘  │
                          └─────────┼──────────────────┼──────────────────┼────────────┘
                                    │                  │                  │
                                    ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              PIPELINES DE INGESTION                                      │
│                                                                                          │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐ │
│  │                           INGESTION V2 PIPELINE (Activo)                            │ │
│  │                                                                                     │ │
│  │  ┌─────────────┐   ┌─────────────────┐   ┌───────────────┐   ┌──────────────────┐  │ │
│  │  │ Deterministic│──▶│Product Detector │──▶│Sanity Checker │──▶│ DUAL-SAVE        │  │ │
│  │  │ Scraper     │   │(Signal-Based)   │   │(Validación)   │   │ Dashboard + Bot  │  │ │
│  │  └─────────────┘   └─────────────────┘   └───────────────┘   └──────────────────┘  │ │
│  │         │                                                                          │ │
│  │         ▼                                                                          │ │
│  │  ┌──────────────────────────────────────────────────────────────────────────────┐  │ │
│  │  │                        EXTRACTORS (LLM-Assisted)                             │  │ │
│  │  │                                                                              │  │ │
│  │  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐                    │  │ │
│  │  │  │ Bio Extractor │  │ FAQ Extractor │  │ Tone Detector │                    │  │ │
│  │  │  │ (LLM)         │  │ (Regex+LLM)   │  │ (LLM)         │                    │  │ │
│  │  │  └───────────────┘  └───────────────┘  └───────────────┘                    │  │ │
│  │  └──────────────────────────────────────────────────────────────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              ALMACENAMIENTO DUAL                                         │
│                                                                                          │
│  ┌──────────────────────────────────┐    ┌──────────────────────────────────────────┐   │
│  │        DASHBOARD (UI)            │    │              BOT (RAG)                   │   │
│  │                                  │    │                                          │   │
│  │  ┌──────────────────────────┐    │    │  ┌──────────────────────────────────┐    │   │
│  │  │ creators.knowledge_about │    │    │  │     rag_documents (PostgreSQL)   │    │   │
│  │  │ (JSON Field)             │    │    │  │     - doc_id, content, source_url│    │   │
│  │  │ - bio, specialties       │    │    │  │     - content_type, title        │    │   │
│  │  │ - experience, tone       │    │    │  └──────────────────────────────────┘    │   │
│  │  └──────────────────────────┘    │    │                  │                       │   │
│  │                                  │    │                  ▼                       │   │
│  │  ┌──────────────────────────┐    │    │  ┌──────────────────────────────────┐    │   │
│  │  │ knowledge_base (FAQs)    │    │    │  │  content_embeddings (pgvector)   │    │   │
│  │  │ - question, answer       │    │    │  │  - chunk_id, embedding           │    │   │
│  │  └──────────────────────────┘    │    │  │  - OpenAI text-embedding-3-small │    │   │
│  │                                  │    │  └──────────────────────────────────┘    │   │
│  │  ┌──────────────────────────┐    │    │                                          │   │
│  │  │ products (Catalog)       │    │    │                                          │   │
│  │  │ - name, price, type      │    │    │                                          │   │
│  │  │ - category, payment_link │    │    │                                          │   │
│  │  └──────────────────────────┘    │    │                                          │   │
│  └──────────────────────────────────┘    └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. AUDITORÍA DE INSTAGRAM INGESTION

### 2.1 Métodos de Ingestion Disponibles

**Archivo:** `backend/ingestion/instagram_scraper.py`

| Método | Clase | Estado | Descripción |
|--------|-------|--------|-------------|
| **Meta Graph API** | `MetaGraphAPIScraper` | RECOMENDADO | API oficial, requiere Business Account |
| **Instaloader** | `InstaloaderScraper` | RIESGO RATE LIMIT | Scraping no oficial, puede ser bloqueado |
| **Manual JSON** | `ManualJSONScraper` | MÁS CONFIABLE | Usuario exporta y sube sus datos |

### 2.2 Flujo de Meta Graph API

```python
# Línea 70-131 - instagram_scraper.py
BASE_URL = "https://graph.instagram.com/v21.0"
fields = "id,caption,permalink,timestamp,media_type,like_count,comments_count,media_url,thumbnail_url"

# Rate limits manejados en línea 110-114:
if response.status_code == 429:
    raise RateLimitError("Meta API rate limit alcanzado")
```

### 2.3 Datos Extraídos por Post

```python
@dataclass
class InstagramPost:
    post_id: str
    post_type: Literal['image', 'video', 'carousel', 'reel']
    caption: str
    permalink: str
    timestamp: datetime
    likes_count: Optional[int]
    comments_count: Optional[int]
    hashtags: List[str]  # Extraídos con regex r'#(\w+)'
    mentions: List[str]  # Extraídos con regex r'@(\w+)'
```

### 2.4 OBSERVACIONES CRÍTICAS

| Aspecto | Estado | Detalle |
|---------|--------|---------|
| **Rate Limiting** | PARCIAL | Instaloader tiene delay configurable (1.5s), pero no hay circuit breaker |
| **Retry Logic** | AUSENTE | No hay reintentos automáticos en errores de red |
| **Posts con Caption Corto** | FILTRADO | Solo posts con `len(caption) > 10` pasan el filtro `has_content` |
| **Almacenamiento en RAG** | NO DIRECTO | Posts van a `content_chunks` vía `citation_service.index_creator_posts()` |

### 2.5 RIESGO: N+1 Query en Indexación

**Archivo:** `backend/core/citation_service.py` líneas 631-638

```python
# TEMPORARY: Skip save to avoid N+1 query timeout (1000+ chunks = 2000+ DB queries)
# TODO: Fix _save_chunks_to_db to use bulk operations
logger.debug(f"[index_creator_posts] SKIPPING index.save()")
# index.save()  # DISABLED - causes worker timeout
```

**IMPACTO:** Los posts de Instagram NO se persisten a PostgreSQL actualmente.

---

## 3. AUDITORÍA DE WEBSITE SCRAPING

### 3.1 Componentes del Scraper

**Archivo:** `backend/ingestion/deterministic_scraper.py`

```
┌────────────────────────────────────────────────────────────────────────┐
│                    DeterministicScraper                                │
│                                                                        │
│  Principio: NO LLM, NO Hallucinations - Solo extracción determinista  │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Configuración                                                  │   │
│  │  - timeout: 15s                                                 │   │
│  │  - max_pages: 100 (configurable)                                │   │
│  │  - User-Agent: ClonnectBot/1.0                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  SKIP_PATTERNS (URLs a ignorar):                                │   │
│  │  /login, /signin, /cart, /checkout, /admin, /privacy            │   │
│  │  facebook.com, twitter.com, instagram.com, .pdf, .zip, .mp4     │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  NOISE_ELEMENTS (HTML a eliminar):                              │   │
│  │  script, style, nav, footer, header, aside, form                │   │
│  │  [class*="cookie"], [class*="popup"], [class*="modal"]          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Estructura de Página Scrapeada

```python
@dataclass
class ScrapedPage:
    url: str
    title: str
    main_content: str          # Texto limpio
    sections: List[Dict]       # [{heading, content, level}]
    links: List[str]           # Enlaces internos (max 30)
    metadata: Dict[str, Any]   # og:image, description
    scraped_at: datetime
```

### 3.3 Algoritmo de Extracción

1. **Fetch HTTP** con httpx (async, follow_redirects=True, verify=False)
2. **Parse HTML** con BeautifulSoup
3. **Extraer links** ANTES de modificar el DOM
4. **Eliminar ruido** (decompose() en noise elements)
5. **Extraer texto** con separador de espacios
6. **Preservar listas** con marcador ◆ → coma

### 3.4 OBSERVACIONES CRÍTICAS

| Aspecto | Estado | Detalle |
|---------|--------|---------|
| **SSL Verification** | DISABLED | `verify=False` - acepta certificados inválidos |
| **Content-Type Check** | PRESENTE | Solo procesa `text/html` |
| **Crawl Depth** | ILIMITADO | Solo limitado por `max_pages` |
| **Robots.txt** | IGNORADO | No respeta directivas de exclusión |
| **JavaScript Rendering** | AUSENTE | Solo HTML estático (no Playwright) |

---

## 4. AUDITORÍA DEL PRODUCT DETECTOR

### 4.1 Sistema de Señales

**Archivo:** `backend/ingestion/v2/product_detector.py`

```
┌────────────────────────────────────────────────────────────────────────┐
│                   SISTEMA DE SEÑALES (Mínimo 3 requeridas)             │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  DEDICATED_PAGE     URL contiene /servicio, /producto, /curso   │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  CTA_PRESENT        Regex: comprar, reservar, inscríbete, únete │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  PRICE_VISIBLE      Regex: €X, X€, $X (rango 0-50000)           │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  SUBSTANTIAL_DESC   > 100 palabras de contenido                 │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  PAYMENT_LINK       stripe, paypal, calendly, gumroad, etc.     │   │
│  ├─────────────────────────────────────────────────────────────────┤   │
│  │  CLEAR_TITLE        5 < len(title) < 100 caracteres             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│  REGLA PRINCIPAL: Solo es PRODUCTO si tiene PRECIO o es GRATUITO       │
│  MAX_PRODUCTS = 20 (si hay más, aborta con SuspiciousExtractionError)  │
└────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Taxonomía de Productos

```python
# Clasificación automática:
clasificar_contenido(name, description, url, tiene_precio, es_gratis)
→ {
    'category': 'product' | 'service' | 'resource',
    'type': 'ebook' | 'curso' | 'coaching' | 'mentoria' | 'podcast' | etc,
    'is_free': bool
}
```

### 4.3 Filtro Anti-Testimonios

**Líneas 360-398:** Patrones para detectar testimonios y NO confundirlos con productos:

```python
TESTIMONIAL_PATTERNS = [
    r'\bme ayud[óo]\b', r'\bgracias a\b', r'\brecomiendo\b',
    r'\bcambi[óo] mi vida\b', r'\btransform[óo]\b',
    # ... 20+ patrones más
]
```

### 4.4 OBSERVACIONES CRÍTICAS

| Aspecto | Estado | Detalle |
|---------|--------|---------|
| **Precios Inventados** | NUNCA | Solo se guarda precio si se detecta por regex |
| **Moneda Default** | EUR | Si no hay símbolo claro, asume EUR |
| **Deduplicación** | ACTIVA | Mantiene producto con más señales |
| **Recursos (Podcast)** | EXCLUIDOS | Detectados y marcados como `category='resource'` |

---

## 5. AUDITORÍA DE FAQ EXTRACTOR

### 5.1 Pipeline Híbrido (Regex + LLM)

**Archivo:** `backend/ingestion/v2/faq_extractor.py`

```
┌────────────────────────────────────────────────────────────────────────┐
│                      FAQ EXTRACTION PIPELINE                           │
│                                                                        │
│  PASO 1: REGEX EXTRACTION                                              │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Pattern: r"¿([^?]+)\?"                                         │   │
│  │  - Extrae pregunta literal                                      │   │
│  │  - Extrae respuesta hasta siguiente ¿ o +2000 chars             │   │
│  │  - Filtra preguntas < 10 chars                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                           │                                            │
│                           ▼                                            │
│  PASO 2: FILTROS REGEX (Anti-Ruido)                                    │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  EXCLUDE_URL_PATTERNS:                                          │   │
│  │  /blog/, /post/, /articulo/, /article/, /noticias/              │   │
│  │                                                                 │   │
│  │  EXCLUDE_QUESTION_PATTERNS (CTAs y Retóricas):                  │   │
│  │  "¿Te gustaría...?", "¿Listo para...?", "¿Y si...?"             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                           │                                            │
│                           ▼                                            │
│  PASO 3: LLM CLASSIFICATION (REAL vs SKIP)                             │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Batches de 30 FAQs → LLM clasifica cada una                    │   │
│  │  REAL = FAQ de producto/servicio                                │   │
│  │  SKIP = Pregunta de blog/retórica                               │   │
│  │  Fallback: Si LLM falla, incluir todas                          │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                           │                                            │
│                           ▼                                            │
│  PASO 4: LLM CATEGORIZATION (Sin reformular)                           │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  Categorías: pricing, process, benefits, eligibility,           │   │
│  │             getting_started, other                              │   │
│  │  Context: Nombre del producto al que pertenece                  │   │
│  │  REGLA: NO cambiar pregunta ni respuesta originales             │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Limpieza de Respuestas

**Stop Patterns** (líneas 438-473) que cortan la respuesta:
- "MÁS PREGUNTAS", "SOBRE EL AUTOR"
- Testimonios: "X personas que ya han..."
- CTAs: "inscríbete", "reserva tu"
- Timestamps: fechas

### 5.3 OBSERVACIONES CRÍTICAS

| Aspecto | Estado | Detalle |
|---------|--------|---------|
| **Fidelidad al Contenido** | ALTA | Preguntas y respuestas son literales |
| **LLM Timeout** | 60s | Puede fallar en batches grandes |
| **Max FAQs** | 100 | Límite configurable |
| **Deduplicación** | ACTIVA | Por pregunta normalizada (lowercase) |

---

## 6. AUDITORÍA DE BIO Y TONE EXTRACTORS

### 6.1 Bio Extractor

**Archivo:** `backend/ingestion/v2/bio_extractor.py`

```python
@dataclass
class ExtractedBio:
    name: Optional[str]           # Nombre del creador
    bio_summary: str              # Max 250 chars
    specialties: List[str]        # Max 5 keywords
    years_experience: Optional[int]
    target_audience: Optional[str]
    confidence: float
```

**Páginas detectadas automáticamente:**
- `/about`, `/sobre`, `/quien-soy`, `/bio`, `/me`, `/conoceme`, `/mi-historia`

### 6.2 Tone Detector

**Archivo:** `backend/ingestion/v2/tone_detector.py`

```python
@dataclass
class DetectedTone:
    style: str              # "cercano", "inspirador", "técnico", etc.
    formality: str          # "formal", "informal", "mixto"
    language: str           # "es", "en", "pt", etc.
    emoji_usage: str        # "none", "light", "heavy"
    personality_traits: List[str]  # 3-5 traits
    communication_summary: str     # 1 frase descriptiva
    suggested_bot_tone: str        # Instrucciones para el bot (max 200 chars)
```

### 6.3 Auto-Configuración del Bot

**Mapeo tone.style → clone_tone preset:**

```python
TONE_TO_PRESET = {
    "inspirador": "mentor",
    "cercano": "amigo",
    "directo": "vendedor",
    "técnico": "profesional",
    "empático": "amigo",
    "formal": "profesional",
    # ...
}
```

---

## 7. AUDITORÍA DE VECTORIZACIÓN Y STORAGE

### 7.1 Sistema de Embeddings

**Archivo:** `backend/core/embeddings.py`

```
┌────────────────────────────────────────────────────────────────────────┐
│                    SISTEMA DE EMBEDDINGS                               │
│                                                                        │
│  Modelo: OpenAI text-embedding-3-small                                 │
│  Dimensiones: 1536                                                     │
│  Max Tokens: ~7500 (30000 chars)                                       │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  generate_embedding(text)                                       │   │
│  │  → Trunca a 30000 chars si necesario                            │   │
│  │  → Retorna List[float] de 1536 dimensiones                      │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                           │                                            │
│                           ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  store_embedding(chunk_id, creator_id, content, embedding)      │   │
│  │  → UPSERT en content_embeddings                                 │   │
│  │  → Formato pgvector: '[0.1, 0.2, ...]'::vector                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                           │                                            │
│                           ▼                                            │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  search_similar(query_embedding, creator_id, top_k)             │   │
│  │  → Cosine similarity via pgvector: 1 - (embedding <=> query)    │   │
│  │  → JOIN con content_chunks para obtener source_url              │   │
│  │  → min_similarity default: 0.3                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Tablas de Almacenamiento

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       TABLAS POSTGRESQL                                 │
│                                                                         │
│  ┌───────────────────────┐    ┌───────────────────────┐                 │
│  │   content_embeddings  │    │    content_chunks     │                 │
│  │   (pgvector)          │    │                       │                 │
│  │   ─────────────────   │    │   ─────────────────   │                 │
│  │   chunk_id (PK)       │◄──►│   chunk_id (PK)       │                 │
│  │   creator_id          │    │   creator_id          │                 │
│  │   content_preview     │    │   content             │                 │
│  │   embedding (vector)  │    │   source_url          │                 │
│  │   updated_at          │    │   source_type         │                 │
│  └───────────────────────┘    │   title               │                 │
│                               └───────────────────────┘                 │
│                                                                         │
│  ┌───────────────────────┐    ┌───────────────────────┐                 │
│  │   rag_documents       │    │    products           │                 │
│  │   (Anti-Hallucination)│    │                       │                 │
│  │   ─────────────────   │    │   ─────────────────   │                 │
│  │   doc_id              │    │   id (UUID)           │                 │
│  │   creator_id (FK)     │    │   creator_id (FK)     │                 │
│  │   content             │    │   name                │                 │
│  │   source_url (MUST)   │    │   price               │                 │
│  │   source_type         │    │   price_verified      │                 │
│  │   content_type        │    │   source_url          │                 │
│  │   title               │    │   payment_link        │                 │
│  │   chunk_index         │    │   category            │                 │
│  │   extra_data (JSON)   │    │   product_type        │                 │
│  └───────────────────────┘    └───────────────────────┘                 │
└─────────────────────────────────────────────────────────────────────────┘
```

### 7.3 OBSERVACIONES CRÍTICAS

| Aspecto | Estado | Detalle |
|---------|--------|---------|
| **Persistencia Embeddings** | ACTIVA | Sobreviven redeploys |
| **Fallback sin OpenAI** | KEYWORD SEARCH | Si no hay API key, usa word overlap |
| **Min Similarity** | 0.3 | Threshold bajo, puede traer ruido |
| **Chunking** | 500 chars | Con 50 chars de overlap |

---

## 8. AUDITORÍA DE DUAL-SAVE (Dashboard ↔ Bot)

### 8.1 Mecanismo DUAL-SAVE

**Archivo:** `backend/ingestion/v2/pipeline.py` líneas 587-762

```
┌────────────────────────────────────────────────────────────────────────┐
│                          DUAL-SAVE SYSTEM                              │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    _save_creator_knowledge()                    │   │
│  │                                                                 │   │
│  │  ORIGEN             DESTINO UI              DESTINO BOT (RAG)   │   │
│  │  ────────          ───────────             ─────────────────    │   │
│  │  Bio            →  knowledge_about.bio  →  rag_documents        │   │
│  │                     .creator_name           content_type='bio'  │   │
│  │                     .specialties                                │   │
│  │                     .experience                                 │   │
│  │                                                                 │   │
│  │  FAQs           →  knowledge_base      →   rag_documents        │   │
│  │                     (tabla separada)        content_type='faq'  │   │
│  │                                                                 │   │
│  │  Tone           →  knowledge_about.tone    (no va a RAG)        │   │
│  │                     .style, .formality                          │   │
│  │                     .suggested_bot_tone                         │   │
│  │                                                                 │   │
│  │  Products       →  products (tabla)    →   rag_documents        │   │
│  │                                             content_type=       │   │
│  │                                             'product'           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Auto-Configuración del Clone

```python
def _auto_configure_clone(creator, bio, tone):
    # 1. Nombre del bot = nombre del creador
    if bio and bio.name:
        creator.clone_name = bio.name

    # 2. Preset de tono
    creator.clone_tone = TONE_TO_PRESET.get(tone.style.lower(), "amigo")

    # 3. Instrucciones del bot
    creator.clone_vocabulary = tone.suggested_bot_tone
```

### 8.3 OBSERVACIONES CRÍTICAS

| Aspecto | Estado | Detalle |
|---------|--------|---------|
| **flag_modified()** | REQUERIDO | Para que SQLAlchemy detecte cambios en JSON |
| **Rollback Safety** | AUTO-CONFIG INDEPENDIENTE | Si falla auto-config, datos principales ya guardados |
| **Sincronización** | UNIDIRECCIONAL | Ingestion → Dashboard, no al revés |

---

## 9. AUDITORÍA DE CITABILIDAD EN BOT

### 9.1 Sistema de Citaciones

**Archivo:** `backend/core/citation_service.py`

```
┌────────────────────────────────────────────────────────────────────────┐
│                     CITATION SYSTEM (BOT RAG)                          │
│                                                                        │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  find_relevant_citations(creator_id, query, max_results=3)      │   │
│  │                                                                 │   │
│  │  1. get_content_index(creator_id)                               │   │
│  │     → Carga desde PostgreSQL (rag_documents)                    │   │
│  │     → Fallback: JSON local                                      │   │
│  │                                                                 │   │
│  │  2. index.search(query, min_relevance=0.4)                      │   │
│  │     → Normaliza texto (quita acentos)                           │   │
│  │     → Busca por keywords (not semantic)                         │   │
│  │     → Score = matches / total_keywords                          │   │
│  │                                                                 │   │
│  │  3. Retorna CitationContext                                     │   │
│  │     → citations[]: {source_url, excerpt, relevance_score}       │   │
│  │     → to_prompt_context() para inyectar en system prompt        │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Integración con RAG Semántico

**Archivo:** `backend/core/rag/semantic.py`

```python
class SemanticRAG:
    def search(self, query: str, top_k: int = 5, creator_id: str = None):
        # 1. Generar embedding de la query
        query_embedding = generate_embedding(query)

        # 2. Buscar en pgvector
        results = search_similar(
            query_embedding=query_embedding,
            creator_id=creator_id,
            top_k=top_k,
            min_similarity=0.3
        )

        # 3. Retorna con source_url para citación
        return [{
            "doc_id": r["chunk_id"],
            "text": r["content"],
            "metadata": {
                "source_url": r.get("source_url"),  # CITABLE
                "title": r.get("title"),
                "type": r.get("source_type")
            },
            "score": r["similarity"]
        }]
```

### 9.3 Anti-Hallucination Garantías

| Garantía | Implementación |
|----------|---------------|
| **source_url obligatorio** | Columna NOT NULL en rag_documents |
| **price_verified** | Solo True si precio detectado por regex |
| **confidence scores** | Cada extracción tiene score 0-1 |
| **No LLM en extracción** | DeterministicScraper + ProductDetector = solo regex |

---

## 10. PUNTOS CRÍTICOS Y RECOMENDACIONES

### 10.1 BUGS ENCONTRADOS

| ID | Severidad | Descripción | Archivo:Línea |
|----|-----------|-------------|---------------|
| BUG-001 | ALTA | Posts de Instagram NO se persisten a DB (N+1 query) | citation_service.py:631 |
| BUG-002 | MEDIA | SSL verification disabled globalmente | deterministic_scraper.py:191 |
| BUG-003 | BAJA | Robots.txt ignorado | deterministic_scraper.py (ausente) |

### 10.2 MEJORAS RECOMENDADAS

#### Corto Plazo (Quick Wins)

1. **Bulk Insert para Posts Instagram**
   ```python
   # Cambiar de N+1:
   for chunk in chunks: db.add(chunk)
   # A bulk:
   db.bulk_save_objects(chunks)
   ```

2. **Retry con Backoff para Graph API**
   ```python
   @retry(wait=wait_exponential(multiplier=1, max=10))
   async def get_posts(self, limit: int):
       ...
   ```

3. **Subir min_similarity a 0.5**
   - Actualmente 0.3 trae mucho ruido

#### Mediano Plazo

4. **Añadir Playwright para JS-rendered sites**
   - Muchos sitios modernos requieren JS

5. **Implementar Incremental Ingestion**
   - Actualmente `clean_before=True` borra todo
   - Añadir lógica de diff/update

6. **Circuit Breaker para Rate Limits**
   ```python
   from circuitbreaker import circuit
   @circuit(failure_threshold=3, recovery_timeout=60)
   async def fetch_instagram_posts():
       ...
   ```

### 10.3 MÉTRICAS DE OBSERVABILIDAD SUGERIDAS

```python
# Métricas a añadir:
ingestion_pages_scraped_total
ingestion_products_detected_total
ingestion_faqs_extracted_total
ingestion_embeddings_generated_total
ingestion_duration_seconds
ingestion_errors_total{error_type}
```

---

## 11. FLUJO COMPLETO ONBOARDING

```
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│                           ONBOARDING FLOW (CLONE CREATION)                                 │
│                                                                                            │
│  POST /onboarding/clone-creation/start                                                     │
│  {creator_id, website_url}                                                                 │
│                                                                                            │
│       │                                                                                    │
│       ▼                                                                                    │
│  ┌──────────────────────────────────────────────────────────────────────────────────────┐  │
│  │  _run_clone_creation() [Background Task]                                             │  │
│  │                                                                                      │  │
│  │  Step 1: INSTAGRAM                                                                   │  │
│  │  ┌─────────────────────────────────────────────────────────────────────────────┐     │  │
│  │  │  - scrape_instagram_posts(creator_id)                                       │     │  │
│  │  │  - index_creator_posts() → content_chunks + embeddings                      │     │  │
│  │  │  - Progress: 0% → 25%                                                       │     │  │
│  │  └─────────────────────────────────────────────────────────────────────────────┘     │  │
│  │                                                                                      │  │
│  │  Step 2: WEBSITE (IngestionV2Pipeline)                                               │  │
│  │  ┌─────────────────────────────────────────────────────────────────────────────┐     │  │
│  │  │  - DeterministicScraper.scrape_website(url)                                 │     │  │
│  │  │  - ProductDetector.detect_products(pages)                                   │     │  │
│  │  │  - SanityChecker.verify(products)                                           │     │  │
│  │  │  - BioExtractor.extract(pages)                                              │     │  │
│  │  │  - FAQExtractor.extract(pages, products)                                    │     │  │
│  │  │  - ToneDetector.detect(pages, bio)                                          │     │  │
│  │  │  - DUAL-SAVE: products, rag_docs, knowledge_about, knowledge_base           │     │  │
│  │  │  - Progress: 30% → 60%                                                      │     │  │
│  │  └─────────────────────────────────────────────────────────────────────────────┘     │  │
│  │                                                                                      │  │
│  │  Step 3: POST-PROCESSING                                                             │  │
│  │  ┌─────────────────────────────────────────────────────────────────────────────┐     │  │
│  │  │  - _auto_configure_clone(creator, bio, tone)                                │     │  │
│  │  │  - Update creator.clone_name, clone_tone, clone_vocabulary                  │     │  │
│  │  │  - Progress: 60% → 100%                                                     │     │  │
│  │  └─────────────────────────────────────────────────────────────────────────────┘     │  │
│  └──────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                            │
│  RESULTADO:                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────────────────┐  │
│  │  Dashboard UI:                          Bot RAG:                                     │  │
│  │  - products (catálogo)                  - rag_documents (searchable)                 │  │
│  │  - knowledge_base (FAQs)                - content_embeddings (semantic search)       │  │
│  │  - knowledge_about (bio, tone)          - products también en RAG (product type)     │  │
│  │  - clone_name, clone_tone, vocabulary   - FAQs también en RAG (faq type)             │  │
│  └──────────────────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 12. CONCLUSIONES

### 12.1 Fortalezas del Sistema

1. **Anti-Hallucination by Design**: `source_url` obligatorio, precios solo de regex
2. **Dual-Save Robusto**: Dashboard y Bot siempre sincronizados
3. **Pipeline V2 Maduro**: Signal-based detection reduce falsos positivos
4. **LLM Usage Controlado**: Solo para categorización, no para extracción

### 12.2 Deuda Técnica

1. **N+1 Query en Instagram Posts** - CRÍTICO
2. **No hay Incremental Ingestion** - Solo full refresh
3. **SSL Verification Disabled** - Riesgo de seguridad
4. **Robots.txt Ignorado** - Riesgo legal

### 12.3 Próximos Pasos Recomendados

1. Arreglar bulk insert para posts Instagram
2. Implementar respeto a robots.txt
3. Añadir Playwright para sitios con JS
4. Incrementar min_similarity de 0.3 a 0.5
5. Añadir métricas de observabilidad

---

*Documento generado por Claude Code - Auditoría de Ingestion Pipeline*
