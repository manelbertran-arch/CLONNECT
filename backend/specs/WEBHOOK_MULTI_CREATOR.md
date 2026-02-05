# SPEC: Sistema de Webhooks Multi-Creator

## Objetivo
Sistema robusto y escalable para recibir webhooks de Instagram y rutearlos al creator correcto, independientemente del formato de ID que Meta envíe.

## Problema Actual
- Webhooks llegan con ID `17841400506734756`
- DB tiene `instagram_page_id = NULL` para stefano_bonanno
- No hay fallback ni búsqueda en IDs adicionales
- Webhooks se pierden silenciosamente

## Solución

### 1. Modelo de Datos

#### 1.1 Modificar tabla `creators`
```sql
-- Añadir índices para búsquedas rápidas
CREATE INDEX IF NOT EXISTS ix_creators_instagram_page_id ON creators(instagram_page_id);
CREATE INDEX IF NOT EXISTS ix_creators_instagram_user_id ON creators(instagram_user_id);

-- Añadir campo para IDs adicionales (legacy, secundarios)
ALTER TABLE creators ADD COLUMN IF NOT EXISTS instagram_additional_ids JSONB DEFAULT '[]';

-- Añadir tracking de webhooks
ALTER TABLE creators ADD COLUMN IF NOT EXISTS webhook_last_received TIMESTAMPTZ;
ALTER TABLE creators ADD COLUMN IF NOT EXISTS webhook_count INTEGER DEFAULT 0;
```

#### 1.2 Nueva tabla `unmatched_webhooks`
```sql
CREATE TABLE IF NOT EXISTS unmatched_webhooks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    received_at TIMESTAMPTZ DEFAULT NOW(),
    instagram_ids JSONB NOT NULL,  -- Todos los IDs extraídos del payload
    payload_summary JSONB,          -- Resumen del payload (no completo por privacidad)
    resolved BOOLEAN DEFAULT FALSE,
    resolved_to_creator_id UUID REFERENCES creators(id),
    resolved_at TIMESTAMPTZ,
    notes TEXT
);

CREATE INDEX ix_unmatched_webhooks_resolved ON unmatched_webhooks(resolved) WHERE NOT resolved;
CREATE INDEX ix_unmatched_webhooks_instagram_ids ON unmatched_webhooks USING GIN(instagram_ids);
```

### 2. Funciones Core

#### 2.1 `extract_all_instagram_ids(payload: dict) -> List[str]`
```python
"""
Extrae TODOS los posibles IDs de Instagram del payload del webhook.

Input: Payload completo del webhook de Meta
Output: Lista de IDs únicos encontrados

Ubicaciones a buscar:
- entry[].id
- entry[].messaging[].recipient.id
- entry[].messaging[].sender.id
- entry[].changes[].value.from.id
- entry[].changes[].value.to.id
"""
```

#### 2.2 `get_creator_by_any_instagram_id(instagram_id: str) -> Optional[Dict]`
```python
"""
Busca creator por CUALQUIER tipo de Instagram ID.

Orden de búsqueda (con índices):
1. instagram_page_id (exacto) - más común
2. instagram_user_id (exacto) - fallback
3. instagram_additional_ids (contiene) - legacy/secundarios

Returns: Dict con info del creator si encuentra, None si no
"""
```

#### 2.3 `find_creator_for_webhook(instagram_ids: List[str]) -> Tuple[Optional[Dict], Optional[str]]`
```python
"""
Intenta encontrar creator probando todos los IDs extraídos.

Input: Lista de IDs del payload
Output: (creator_info, matched_id) o (None, None)

Itera sobre todos los IDs y retorna el primer match.
"""
```

#### 2.4 `save_unmatched_webhook(instagram_ids: List[str], payload: dict) -> str`
```python
"""
Guarda webhook que no encontró creator para debug posterior.

Guarda:
- Todos los IDs encontrados
- Resumen del payload (sin datos sensibles)
- Timestamp

Returns: ID del registro creado (UUID como string)
"""
```

### 3. Webhook Handler

```python
@router.post("/webhook/instagram")
async def instagram_webhook_receive(request: Request):
    """
    Handler principal de webhooks de Instagram.

    Flujo:
    1. Parsear payload
    2. Extraer TODOS los IDs posibles
    3. Buscar creator con cualquier ID
    4. Si no encuentra → guardar en unmatched_webhooks
    5. Si encuentra → procesar normalmente + actualizar stats
    """
```

### 4. Migración de Datos

```sql
-- Migrar datos de Stefano
UPDATE creators
SET
    instagram_user_id = '25734915742865411',
    instagram_page_id = '25734915742865411',
    instagram_additional_ids = '["17841400506734756"]'
WHERE name = 'stefano_bonanno';
```

### 5. Onboarding Mejorado

Durante OAuth/onboarding de nuevo creator:
1. Llamar a GET /me?fields=id,instagram_business_account
2. Extraer todos los IDs disponibles
3. Guardar en instagram_user_id, instagram_page_id
4. Guardar cualquier ID adicional en instagram_additional_ids

### 6. Tests Requeridos

#### 6.1 Unit Tests
- `test_extract_all_instagram_ids` - extrae IDs de payloads de ejemplo
- `test_get_creator_by_page_id` - encuentra por page_id
- `test_get_creator_by_user_id` - encuentra por user_id
- `test_get_creator_by_additional_id` - encuentra por ID en array
- `test_get_creator_not_found` - retorna None si no existe
- `test_save_unmatched_webhook` - guarda correctamente

#### 6.2 Integration Tests
- `test_webhook_finds_creator_by_page_id`
- `test_webhook_finds_creator_by_legacy_id`
- `test_webhook_saves_unmatched`
- `test_webhook_updates_stats`

### 7. Archivos a Modificar/Crear

| Archivo | Acción | Descripción |
|---------|--------|-------------|
| `api/models.py` | MODIFICAR | Añadir campos a Creator y modelo UnmatchedWebhook |
| `core/webhook_routing.py` | CREAR | Funciones de routing |
| `api/routers/messaging_webhooks.py` | MODIFICAR | Usar nuevo routing |
| `alembic/versions/011_webhook_multi_creator.py` | CREAR | Migración |
| `tests/test_webhook_routing.py` | CREAR | Tests |

### 8. Criterios de Aceptación

- [ ] Webhook con ID actual (25734915742865411) → encuentra stefano_bonanno
- [ ] Webhook con ID legacy (17841400506734756) → encuentra stefano_bonanno
- [ ] Webhook con ID desconocido → guarda en unmatched_webhooks
- [ ] Búsquedas usan índices (no full table scan)
- [ ] Onboarding de nuevo creator captura todos los IDs
- [ ] Tests pasan al 100%
- [ ] Tiempo de lookup < 10ms

### 9. Rollback Plan

Si algo falla:
1. Las funciones nuevas son aditivas, no rompen el flujo existente
2. La migración SQL es reversible (DROP COLUMN, DROP TABLE)
3. El código antiguo sigue funcionando en paralelo hasta validar

### 10. Diagrama de Flujo

```
                         WEBHOOK POST /webhook/instagram
                                      │
                                      ▼
                        ┌─────────────────────────────┐
                        │  extract_all_instagram_ids  │
                        │  payload → ["id1","id2"...] │
                        └─────────────────────────────┘
                                      │
                                      ▼
                        ┌─────────────────────────────┐
                        │  find_creator_for_webhook   │
                        │  Itera IDs buscando match   │
                        └─────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    ▼                                   ▼
              ENCONTRADO                          NO ENCONTRADO
                    │                                   │
                    ▼                                   ▼
        ┌───────────────────┐              ┌───────────────────┐
        │ Update stats:     │              │ save_unmatched_   │
        │ - webhook_count++ │              │ webhook()         │
        │ - last_received   │              │                   │
        └───────────────────┘              └───────────────────┘
                    │                                   │
                    ▼                                   ▼
        ┌───────────────────┐              ┌───────────────────┐
        │ get_handler_for_  │              │ Return 200 OK     │
        │ creator()         │              │ + warning log     │
        └───────────────────┘              └───────────────────┘
                    │
                    ▼
        ┌───────────────────┐
        │ handler.handle_   │
        │ webhook(payload)  │
        └───────────────────┘
                    │
                    ▼
              ✅ Respuesta
```
