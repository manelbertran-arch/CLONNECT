# BLOQUE: DASHBOARD
Estado: ✅ CONGELADO
Última verificación: 2026-01-15

## Qué hace
Panel de control del creator: ve leads, mensajes, productos, analytics.

## Archivos principales
- backend/api/routers/leads.py - CRUD leads
- backend/api/routers/messages.py - CRUD mensajes
- backend/api/routers/products.py - CRUD productos
- Frontend: pages/dashboard/

## Funcionalidades
- ✅ Lista de leads (nombre, status, score)
- ✅ Ver conversación de cada lead
- ✅ Filtrar por status (hot/warm/cold)
- ✅ Ver productos configurados
- ✅ Configuración de bot (on/off, copilot)

## Endpoints principales
- GET /api/leads?creator_id=X
- GET /api/messages?lead_id=X
- GET /api/products?creator_id=X
- PATCH /api/leads/{id}/status

## ⚠️ NO TOCAR SIN MOTIVO
Este bloque funciona. Cualquier cambio requiere re-testear todo.
