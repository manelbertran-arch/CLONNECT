# BLOQUE: ONBOARDING
Estado: ✅ CONGELADO
Última verificación: 2026-01-15

## Qué hace
Flujo de registro de nuevo creator: slides explicativos, formulario
de datos, y trigger de creación del clon.

## Archivos principales
- backend/api/routers/onboarding.py (87KB) - Endpoints onboarding
- Frontend: pages/onboarding/

## Funcionalidades
- ✅ 11 slides explicativos
- ✅ Formulario: Instagram username + website
- ✅ Página de "creando tu clon"
- ✅ Trigger de Data Ingestion Pipeline

## Flujo
1. Usuario ve slides (11 pasos)
2. Ingresa @instagram y website
3. Sistema muestra "creando clon..."
4. Trigger a Data Ingestion Pipeline
5. Redirect a Dashboard cuando termina

## ⚠️ NO TOCAR SIN MOTIVO
Este bloque funciona. Cualquier cambio requiere re-testear todo.
