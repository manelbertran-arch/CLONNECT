# RECUPERACIÓN DEL SISTEMA

## Si algo se rompe:

```bash
git fetch --tags
git checkout v1.0.1-stable
git push origin main --force
```

## Tags estables:

| Tag | Fecha | Qué funciona |
|-----|-------|--------------|
| v1.0.1-stable | 20/01/2026 | Todo: onboarding, productos, leads, mensajes, IngestionV2Pipeline |
| v1.0.0-stable | 20/01/2026 | Primera versión estable |

## Tests críticos que DEBEN pasar:

```bash
cd backend
pytest tests/test_ingestion_critical.py -v -m critical
```

### Qué testean:
- `test_pipeline_detects_products_from_website` - Detecta productos con precio (€22 Fitpack)
- `test_pipeline_creates_result_structure` - Estructura de resultado correcta
- `test_pipeline_without_db_does_not_crash` - No crashea sin DB (modo preview)
- `test_detector_finds_price_signals` - Extrae precios del texto
- `test_detector_identifies_cta_signals` - Detecta CTAs (Comprar, Reservar, etc.)

## Archivos críticos - NO tocar sin aprobación:

| Archivo | Por qué es crítico |
|---------|-------------------|
| `backend/api/routers/onboarding.py` | Flujo de creación de clones |
| `backend/ingestion/v2/pipeline.py` | Pipeline de detección de productos |
| `backend/ingestion/v2/product_detector.py` | Lógica de detección de señales |
| `backend/ingestion/v2/sanity_checker.py` | Validación anti-alucinaciones |

## Cómo verificar que todo funciona:

### 1. Health check
```bash
curl https://web-production-9f69.up.railway.app/health
```

### 2. Test de detección de productos (sin guardar)
```bash
curl -X POST "https://web-production-9f69.up.railway.app/ingestion/v2/preview" \
  -H "Content-Type: application/json" \
  -d '{"creator_id":"test","url":"https://www.stefanobonanno.com","max_pages":100}'
```

Debe devolver:
```json
{
  "products_detected": 1,
  "products": [{"name": "Fitpack Challenge...", "price": 22.0}]
}
```

### 3. Test completo de onboarding
1. Nuclear reset: `curl -X POST ".../admin/nuclear-reset?confirm=DELETE_EVERYTHING"`
2. Ir a `/register` y crear cuenta
3. Conectar Instagram + website
4. Verificar productos: `curl ".../creator/CREATOR_ID/products"`

## Contacto de emergencia

Si el sistema está caído y no puedes recuperar:
1. Verifica logs en Railway dashboard
2. Rollback al último tag estable
3. Revisa el último commit que rompió algo
