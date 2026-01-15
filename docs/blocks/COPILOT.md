# BLOQUE: COPILOT
Estado: ✅ CONGELADO
Última verificación: 2026-01-15

## Qué hace
Modo de aprobación manual. Bot genera respuesta sugerida,
creator la aprueba/rechaza antes de enviar.

## Archivos principales
- backend/core/copilot_service.py - Lógica copilot
- backend/api/routers/copilot.py - Endpoints

## Funcionalidades
- ✅ Guardar mensajes como "pending_approval"
- ✅ Listar mensajes pendientes
- ✅ Aprobar mensaje (envía)
- ✅ Rechazar mensaje (descarta)
- ✅ Aprobar todos los pendientes

## Endpoints
- GET /copilot/{creator_id}/pending
- POST /copilot/{creator_id}/approve/{message_id}
- POST /copilot/{creator_id}/discard/{message_id}
- POST /copilot/{creator_id}/approve-all

## Configuración
- copilot_mode=true → Bot guarda como pending
- copilot_mode=false → Bot envía automáticamente

## ⚠️ NO TOCAR SIN MOTIVO
Este bloque funciona. Cualquier cambio requiere re-testear todo.
