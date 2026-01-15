# BLOQUE: INTEGRATIONS
Estado: 🔨 EN TRABAJO (40%)
Última verificación: 2026-01-15 15:30 UTC

## Qué hace
Integraciones externas: calendarios, pagos, videollamadas.

## Estado por componente

### Instagram ✅ FUNCIONA
- Webhook configurado y funcionando
- Bot responde DMs correctamente
- Copilot envía mensajes OK

### Telegram ✅ FUNCIONA
- Bot registrado en TelegramBotRegistry
- Webhook funcionando
- Copilot envía mensajes OK
- creator_id: fitpack_global

### Calendly ❓ NO VERIFICADO
- backend/core/calendar.py
- backend/api/routers/booking.py

### Google Meet ⚠️ NO CONECTADO
- google.connected: false (verificado 15 ene)
- Requiere OAuth de Google Calendar
- backend/api/routers/calendar.py

### Stripe ❓ NO VERIFICADO
- backend/core/payments.py
- stripe.connected: false

### PayPal ❓ NO VERIFICADO
- backend/core/payments.py
- paypal.connected: false

## Pendientes inmediatos
1. **Payment links vacíos**: Productos sin link de pago
2. **Google Calendar**: Conectar OAuth

## Configuración necesaria
```env
# Ya configurados
INSTAGRAM_ACCESS_TOKEN=***
TELEGRAM_BOT_TOKEN=*** (en bots.json)

# Pendientes de configurar
STRIPE_SECRET_KEY=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
CALENDLY_API_KEY=
```
