# BLOQUE: AUTH
Estado: ✅ CONGELADO
Última verificación: 2026-01-15

## Qué hace
Maneja autenticación de usuarios y OAuth con Instagram/Meta.

## Archivos principales
- backend/api/routers/oauth.py (57KB) - Flujo OAuth completo
- backend/api/routers/auth.py - Login/registro básico
- backend/core/auth.py - Utilidades de autenticación

## Funcionalidades
- ✅ Registro de nuevos creators
- ✅ Login con email/password
- ✅ OAuth Instagram (conectar cuenta)
- ✅ Refresh de tokens Instagram
- ✅ Logout

## Configuración necesaria
- INSTAGRAM_APP_ID
- INSTAGRAM_APP_SECRET
- JWT_SECRET

## Endpoints
- POST /auth/register
- POST /auth/login
- GET /oauth/instagram/authorize
- GET /oauth/instagram/callback
- POST /oauth/instagram/refresh

## Tests
- tests/regression/test_auth.py (pendiente crear)

## ⚠️ NO TOCAR SIN MOTIVO
Este bloque funciona. Cualquier cambio requiere re-testear todo.
