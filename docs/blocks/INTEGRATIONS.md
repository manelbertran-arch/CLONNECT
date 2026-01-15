# BLOQUE: INTEGRATIONS
Estado: 🔨 EN TRABAJO (60%)
Última verificación: 2026-01-15

## Qué hace
Integraciones externas: calendarios, pagos, videollamadas.

## Subcomponentes

### Calendly ✅ FUNCIONA
- backend/core/calendar.py
- backend/api/routers/booking.py
- Webhook para eventos de booking

### Google Meet ⚠️ PARCIAL
- Crear links de Meet
- PROBLEMA: Desconectado en dashboard

### Stripe ❓ NO VERIFICADO
- backend/core/payments.py
- Webhooks de pago

### PayPal ❓ NO VERIFICADO
- backend/core/payments.py

## Configuración necesaria
- CALENDLY_API_KEY
- STRIPE_SECRET_KEY
- STRIPE_WEBHOOK_SECRET
- GOOGLE_CLIENT_ID
- GOOGLE_CLIENT_SECRET
