# BLOQUE: DATA_INGESTION
Estado: 🔨 EN TRABAJO (80%)
Última verificación: 2026-01-15

## Qué hace
Pipeline que "absorbe" datos del creator: scraping Instagram,
scraping web, importar DMs, detectar productos, generar ToneProfile.

## Archivos principales
- backend/ingestion/v2/pipeline.py - Pipeline principal
- backend/ingestion/instagram_scraper.py - Scraper IG
- backend/ingestion/website_scraper.py - Scraper web
- backend/ingestion/v2/product_detector.py - Detectar productos
- backend/core/tone_service.py - Generar ToneProfile

## Subcomponentes
1. Instagram Scraper → Posts, bio, followers
2. Website Scraper → Páginas web a chunks
3. DM Importer → Historial de conversaciones
4. Product Detector → Productos y precios
5. Tone Analyzer → Personalidad del creator
6. RAG Indexer → Embeddings para búsqueda

## Qué funciona ✅
- Scraping web (5 páginas)
- Product detection (determinístico, no LLM)
- RAG indexing
- ToneProfile generation

## Qué falta ⚠️
- Instagram scraping limitado por API
- A veces genera datos fake (bug en onboarding.py - YA ARREGLADO)

## Output esperado
- 20-50 posts de Instagram
- 50+ chunks de website en RAG
- 4+ productos detectados
- ToneProfile con confianza > 80%
