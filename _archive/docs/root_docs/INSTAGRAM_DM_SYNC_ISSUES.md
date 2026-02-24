# Instagram DM Sync - Fallos Conocidos y Soluciones

## Resumen Ejecutivo

Este documento documenta TODOS los problemas encontrados con la ingesta de DMs de Instagram y sus soluciones para evitar regresiones.

---

## Tabla Resumen de Problemas

| # | Problema | Causa | Solución | Archivo:Línea | Estado |
|---|----------|-------|----------|---------------|--------|
| 1 | Rate limit 429/4/17 | Demasiadas llamadas API | Backoff exponencial + throttling 3s | `sync_worker.py:139-140` | ✅ |
| 2 | Rate limit subcode 1349210 | Límite específico de DMs | Detectar y pausar 5 min | `sync_worker.py:139` | ✅ |
| 3 | Timestamps incorrectos (fantasma) | Usaba fecha sync, no fecha original | Parsear `created_time` de mensajes | `sync_worker.py:177-198` | ✅ |
| 4 | Fantasma detectaba mal | `last_contact_at` incluía mensajes del bot | Solo usar mensajes del USER | `sync_worker.py:195-197` | ✅ |
| 5 | Duplicados de mensajes | Sin verificar existencia | Check `platform_message_id` | `sync_worker.py:236-241` | ✅ |
| 6 | Follower ID no encontrado | Solo miraba campo "from" | También buscar en "to.data[]" | `sync_worker.py:163-171` | ✅ |
| 7 | Sync bloqueante | Proceso sincrónico | Cola async + background worker | `sync_worker.py:402-494` | ✅ |
| 8 | Sin progreso visible | No había tracking | SyncState + SyncQueue tables | `sync_worker.py:38-47` | ✅ |
| 9 | Rate limit sin recovery | Quedaba bloqueado | Estado `rate_limit_until` + auto-resume | `sync_worker.py:303-311` | ✅ |
| 10 | Muchas llamadas simultáneas | Sin throttling | Límites 10/min, 150/h, 3000/día | `instagram_rate_limiter.py:57-59` | ✅ |
| 11 | Errores sin backoff | Retry inmediato | Backoff exponencial 5s→300s | `instagram_rate_limiter.py:62-64` | ✅ |
| 12 | Token no configurado | Falta validación | Check explícito antes de sync | `sync_worker.py:315-317` | ✅ |
| 13 | Leads sin `first_contact_at` | No se guardaba | Parsear min(timestamps) | `sync_worker.py:194,213` | ✅ |

---

## Detalle de Problemas Solucionados

### 1. Rate Limit (Error codes 4, 17, 429)

**Síntoma:** API devuelve error después de muchas llamadas
```json
{"error": {"code": 4, "message": "Rate limit exceeded"}}
```

**Causa:** Meta limita ~200 calls/hora por token

**Solución:**
```python
# sync_worker.py:139-140
if error_code in [4, 17] or error_data.get("error_subcode") == 1349210:
    raise RateLimitError(error_data.get("message", "Rate limit"))
```

**Prevención:**
```python
# instagram_rate_limiter.py:57-59
CALLS_PER_MINUTE = 10   # Muy conservador
CALLS_PER_HOUR = 150    # Meta permite ~200
CALLS_PER_DAY = 3000    # Meta permite ~4800
```

---

### 2. Timestamps Incorrectos para Detección de Fantasma

**Síntoma:** Leads marcados como fantasma incorrectamente (todos tenían mismo timestamp)

**Causa:** Se usaba la fecha del sync, no la fecha original del mensaje de Instagram

**Solución:**
```python
# sync_worker.py:177-198
# Parse timestamps - separar mensajes de usuario vs creator
all_msg_timestamps = []
user_msg_timestamps = []

for msg in messages:
    if msg.get("created_time"):
        ts = datetime.fromisoformat(msg["created_time"].replace("+0000", "+00:00"))
        all_msg_timestamps.append(ts)

        # Solo contar mensajes del follower (no del creator)
        from_id = msg.get("from", {}).get("id")
        if from_id and from_id != ig_user_id:
            user_msg_timestamps.append(ts)

# IMPORTANTE: last_contact_at debe ser el último mensaje del USUARIO
last_user_msg_time = max(user_msg_timestamps) if user_msg_timestamps else None
```

---

### 3. Fantasma Detectaba Mensajes del Bot

**Síntoma:** Lead marcado como fantasma aunque acababa de escribir

**Causa:** `last_contact_at` incluía mensajes del bot (role=assistant)

**Solución:**
```python
# sync_worker.py:214-226
if not lead:
    lead = Lead(
        # IMPORTANTE: usar último mensaje del USUARIO para fantasma
        last_contact_at=last_user_msg_time or first_msg_time
    )
else:
    # IMPORTANTE: solo actualizar si hay mensaje del USUARIO más reciente
    if last_user_msg_time and (not lead.last_contact_at or last_user_msg_time > lead.last_contact_at):
        lead.last_contact_at = last_user_msg_time
```

---

### 4. Follower ID No Encontrado

**Síntoma:** Conversaciones ignoradas, mensajes no guardados

**Causa:** Solo buscaba follower en campo "from", pero a veces está en "to"

**Solución:**
```python
# sync_worker.py:150-171
# Find the follower (non-creator participant)
follower_id = None

# Primero buscar en "from"
for msg in messages:
    from_data = msg.get("from", {})
    from_id = from_data.get("id")
    if from_id and from_id != ig_user_id:
        follower_id = from_id
        break

# Si no se encontró, buscar en "to.data[]"
if not follower_id:
    for msg in messages:
        to_data = msg.get("to", {}).get("data", [])
        for recipient in to_data:
            if recipient.get("id") != ig_user_id:
                follower_id = recipient.get("id")
                break
```

---

### 5. Sync Bloqueante

**Síntoma:** Endpoint timeout, UI congelada

**Causa:** Proceso síncrono esperaba todas las conversaciones

**Solución:** Sistema de cola con background worker
```python
# sync_worker.py - SyncQueue + SyncState tables
# 1. start_sync() añade conversaciones a cola
# 2. Background worker procesa 1 por 1
# 3. /sync-status muestra progreso en tiempo real
```

---

## Problemas Pendientes / Edge Cases

| # | Problema | Estado | Prioridad |
|---|----------|--------|-----------|
| 1 | Token refresh automático | 🟡 Implementado pero no probado en producción | Media |
| 2 | Paginación de conversaciones (>50) | 🟡 No implementado | Baja |
| 3 | Webhooks para sync incremental | 🟡 Configurado pero no activo | Alta |
| 4 | Retry de jobs fallidos | ✅ Implementado (max_retries=3) | - |
| 5 | Notificación de rate limit al usuario | 🟡 Solo logs, no UI | Baja |

---

## Archivos Críticos

```
backend/core/sync_worker.py          # Cola y procesamiento
backend/core/instagram_rate_limiter.py   # Rate limiting preventivo
backend/api/routers/admin.py         # Endpoints /start-sync, /sync-status
backend/api/routers/onboarding.py    # /sync-instagram-dms (legacy)
backend/api/models.py                # SyncState, SyncQueue tables
```

---

## Configuración Actual

```python
# sync_worker.py:21-27
SYNC_CONFIG = SyncConfig(
    delay_between_calls=3,    # 3s entre llamadas
    rate_limit_pause=300,     # 5 min pausa si rate limit
    max_retries=3,            # 3 reintentos por conversación
    batch_size=10,            # 10 convs, luego pausa
    batch_pause=30            # 30s entre batches
)

# instagram_rate_limiter.py:57-64
CALLS_PER_MINUTE = 10
CALLS_PER_HOUR = 150
CALLS_PER_DAY = 3000
INITIAL_BACKOFF_SECONDS = 5
MAX_BACKOFF_SECONDS = 300
```

---

## Cómo Evitar Regresiones

1. **NUNCA** modificar la lógica de `last_contact_at` sin entender FANTASMA
2. **SIEMPRE** usar `platform_message_id` para deduplicación
3. **NUNCA** hacer sync síncrono (usar cola)
4. **SIEMPRE** parsear `created_time` de los mensajes, no usar `datetime.now()`
5. **SIEMPRE** buscar follower en AMBOS campos: `from` y `to.data[]`

---

## Tests Recomendados

```bash
# Verificar sync funciona
curl -X POST http://localhost:8000/admin/start-sync/fitpack_global

# Ver progreso
curl http://localhost:8000/admin/sync-status/fitpack_global

# Verificar rate limiter
curl http://localhost:8000/admin/rate-limit-stats
```

---

*Documento creado: 2026-01-16*
*Última actualización: 2026-01-16*
