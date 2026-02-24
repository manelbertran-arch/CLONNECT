# BLOQUE: NURTURING
Estado: 🔨 EN TRABAJO (70%)
Última verificación: 2026-01-15

## Qué hace
Secuencias automáticas de follow-up. Envía mensajes programados
basados en comportamiento del lead.

## Archivos principales
- backend/core/nurturing.py - NurturingManager
- backend/api/routers/nurturing.py - Endpoints

## Secuencias disponibles (12)
- interest_cold: [24h, 72h, 168h]
- abandoned: [1h, 24h]
- objection_price, objection_time
- post_purchase, re_engagement
- booking_reminder, booking_followup
- scarcity, urgency, social_proof, fomo

## Qué funciona ✅
- Scheduler existe y corre cada 5 min
- Secuencias se activan por defecto para nuevos creators
- Endpoints para activar/desactivar

## Qué falta ⚠️
- No testeado en producción
- Creators existentes no tienen secuencias activas

## Endpoints
- GET /nurturing/{creator_id}/sequences
- POST /nurturing/{creator_id}/sequences/{type}/toggle
- POST /nurturing/{creator_id}/run
