# CONTRATO: COPILOT

## Propósito
Modo de aprobación manual. Bot guarda respuestas como "pending"
hasta que creator las aprueba desde Dashboard.

## Entradas
- Mensaje de usuario
- Respuesta sugerida del bot
- Creator ID

## Salidas
- Mensaje enviado a usuario (tras aprobación)
- Status de mensaje (pending/sent/discarded)

## Endpoints expuestos
```
GET /copilot/{creator_id}/status
  Output: {copilot_enabled, pending_count, status}

GET /copilot/{creator_id}/pending
  Output: {pending_count, pending_responses: [...]}

POST /copilot/{creator_id}/approve/{message_id}
  Input: {edited_text?: string}
  Output: {success, message_id, platform_message_id}

POST /copilot/{creator_id}/discard/{message_id}
  Output: {success, message_id}
```

## Dependencias internas
- telegram_registry.py → Token para envío Telegram
- instagram.py → Token para envío Instagram
- DB: messages table

## Invariantes (NUNCA deben romperse)
1. Si copilot_mode=true → Mensajes se guardan como pending
2. Si copilot_mode=false → Mensajes se envían automáticamente
3. Aprobar mensaje → Se envía a la plataforma correcta
4. Mensaje aprobado → Status cambia a "sent"

## Tests de regresión
```bash
# Test 1: Status endpoint
curl https://...app/copilot/fitpack_global/status
# Esperado: tiene copilot_enabled

# Test 2: Pending endpoint
curl https://...app/copilot/fitpack_global/pending
# Esperado: pending_responses es array
```

## Flujo de datos
```
[Mensaje usuario]
    ↓
[dm_agent genera respuesta]
    ↓
[copilot_mode=true?]
    ├─ Sí → Guarda como pending → Dashboard muestra
    └─ No → Envía directo

[Creator aprueba]
    ↓
[_send_telegram_message() o _send_instagram_message()]
    ↓
[Actualiza status en DB]
```

---
*Última actualización: 2026-01-15*
