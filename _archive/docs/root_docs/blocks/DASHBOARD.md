# BLOQUE: DASHBOARD
Estado: ✅ CONGELADO
Última verificación: 2026-01-15 15:30 UTC
Verificado por: Manel

## Qué hace
Frontend React para que creators gestionen su bot, vean leads,
aprueben mensajes (Copilot), y configuren productos.

## Ubicación
- Repo: creator-s-connect-hub
- URL: https://www.clonnectapp.com
- Deploy: Railway

## Funcionalidades verificadas ✅
- ✅ Login de creator
- ✅ Ver lista de leads (78 leads)
- ✅ Ver conversaciones
- ✅ Toggle bot activo/inactivo
- ✅ Toggle copilot mode
- ✅ Aprobar/rechazar mensajes pendientes
- ✅ Ver productos con precios correctos
- ✅ Interfaz en español

## Endpoints que consume
- GET /dm/leads/{creator_id}
- GET /creator/{creator_id}/products
- GET /copilot/{creator_id}/pending
- POST /copilot/{creator_id}/approve/{id}
- GET /bot/{creator_id}/status
- PUT /bot/{creator_id}/toggle

## Configuración
- VITE_API_URL=https://www.clonnectapp.com

## ⚠️ NO TOCAR SIN MOTIVO
El Dashboard funciona. Cambios en frontend requieren
verificar que no rompen la comunicación con el backend.
