# BLOQUE: DATA_INGESTION
Estado: ✅ CONGELADO (para fitpack_global)
Última verificación: 2026-01-15 15:30 UTC

## Qué hace
Pipeline que indexa contenido del creator en RAG para que el bot
pueda responder con información real.

## Estado actual - fitpack_global
- **RAG Documents**: 108 documentos indexados ✅
- **Content Chunks**: 53 chunks en DB ✅
- **Instagram Posts**: 51 posts indexados ✅
- **Fuente principal**: stefanobonanno.com (10 páginas)

## Archivos principales
- backend/ingestion/v2/pipeline.py - Pipeline principal
- backend/core/citation_service.py - Búsqueda RAG
- backend/api/routers/content.py - Endpoints de contenido

## Subcomponentes
1. **Website Scraper** → Páginas web a chunks ✅
2. **RAG Indexer** → Embeddings para búsqueda ✅
3. **Product Detector** → Productos y precios ✅

## Endpoints verificados
- GET /content/search?creator_id=X&query=Y → Funciona ✅
- POST /content/add → Funciona ✅
- GET /citations/{creator_id}/stats → Funciona ✅

## Lo que funciona ✅
- Búsqueda RAG devuelve contenido real
- Bot usa contenido de stefanobonanno.com
- Anti-alucinación escala si no hay RAG match

## Problemas conocidos
- `/ingestion/website` hace timeout con muchas páginas
- Solución: usar `/content/add` para chunks individuales

## ⚠️ NO RE-INDEXAR SIN MOTIVO
El RAG de fitpack_global tiene 108 docs funcionando.
Re-indexar podría romper el contenido actual.

---

## ProductDetector (v0.3.0) - 2026-01-20

**Estado**: ✅ IMPLEMENTADO Y FUNCIONANDO

**Descripción**: Sistema de detección de productos basado en señales que extrae productos reales de websites sin alucinaciones.

### Señales de detección (requiere mínimo 2):

| Señal | Descripción |
|-------|-------------|
| `DEDICATED_PAGE` | URL contiene /servicio, /producto, /curso, etc. |
| `CTA_PRESENT` | Tiene "comprar", "reservar", "apúntate", etc. |
| `PRICE_VISIBLE` | Precio encontrado via regex (€XX, XX€, $XX) |
| `SUBSTANTIAL_DESCRIPTION` | >50 caracteres de descripción |
| `CLEAR_TITLE` | Título entre 5-100 caracteres |
| `PAYMENT_LINK` | Link a Stripe, Calendly, PayPal, etc. |

### Archivos principales
- `backend/ingestion/v2/pipeline.py` - Pipeline IngestionV2
- `backend/ingestion/v2/product_detector.py` - Detector de productos
- `backend/ingestion/v2/sanity_checker.py` - Verificación anti-alucinación

### Endpoints
- `POST /ingestion/v2/website` - Detectar y guardar productos
- `POST /ingestion/v2/preview` - Preview sin guardar
- `GET /ingestion/v2/verify/{creator_id}` - Verificar productos guardados

### Integración con Onboarding
El ProductDetector se ejecuta automáticamente durante el flujo de creación de clon:
1. Usuario conecta Instagram y proporciona website
2. Se scrapea el website para RAG
3. **ProductDetector analiza el website y guarda productos verificados**
4. Productos aparecen en el dashboard del creator

### Ejemplo de resultado exitoso
```json
{
  "products_detected": 1,
  "products_verified": 1,
  "products_saved": 1,
  "products": [{
    "name": "Fitpack Challenge de 11 días",
    "price": 22.0,
    "currency": "EUR",
    "confidence": 0.83,
    "signals_matched": ["dedicated_page", "cta_present", "price_visible", "substantial_description", "clear_title"]
  }]
}
```

### Sanity Checks (todos deben pasar)
1. `product_count` - Máximo 20 productos (evita CTAs como productos)
2. `source_urls` - Todos tienen source_url
3. `same_domain` - URLs del mismo dominio
4. `reasonable_prices` - Precios entre €0-€50,000
5. `minimum_confidence` - Confidence >= 0.5
6. `re_verification` - Re-fetch de URLs confirma producto
