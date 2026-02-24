# BLOQUE: COPILOT
Estado: ✅ CONGELADO
Última verificación: 2026-01-15 15:30 UTC
Verificado por: Manel (envío mensaje Telegram desde Dashboard)

## Qué hace
Modo de aprobación manual. Bot genera respuesta sugerida,
creator la aprueba/rechaza desde el Dashboard antes de enviar.

## Archivos principales
- backend/core/copilot_service.py - Lógica copilot
- backend/api/routers/copilot.py - Endpoints API

## Funcionalidades verificadas ✅
- ✅ Guardar mensajes como "pending_approval"
- ✅ Listar mensajes pendientes
- ✅ Aprobar mensaje → envía a Instagram
- ✅ Aprobar mensaje → envía a Telegram
- ✅ Rechazar mensaje (descarta)
- ✅ Toggle copilot_mode desde Dashboard

## Endpoints
- GET /copilot/{creator_id}/status
- GET /copilot/{creator_id}/pending
- POST /copilot/{creator_id}/approve/{message_id}
- POST /copilot/{creator_id}/discard/{message_id}

## Fix aplicado (15 Ene 2026)
**Telegram envío usaba tabla incorrecta**
- Problema: Buscaba token en Creator.telegram_bot_token
- Realidad: Token está en data/telegram/bots.json (TelegramBotRegistry)
- Solución: copilot_service.py ahora busca primero en registry
- Archivo: core/copilot_service.py método `_send_telegram_message()`

## Configuración
- copilot_mode=true → Bot guarda como pending
- copilot_mode=false → Bot envía automáticamente

## ⚠️ NO TOCAR SIN MOTIVO
Este bloque funciona. Cualquier cambio requiere verificación manual.
