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

## Fix 2026-01-20: Productos no se guardaban en DB

**Problema**: AutoConfigurator se instanciaba sin db_session
**Causa**: `configurator = AutoConfigurator()` → self.db = None
**Efecto**: Productos detectados pero nunca guardados (self.db check fallaba)
**Solución**: Pasar db_session al constructor: `AutoConfigurator(db_session=db)`
**Archivos modificados**: backend/api/routers/onboarding.py
**Fecha**: 2026-01-20
