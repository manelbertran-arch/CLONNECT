# BLOQUE: BOT_CORE
Estado: ✅ CONGELADO
Última verificación: 2026-01-15 15:30 UTC
Verificado por: Manel (DM real Instagram + Telegram)

## Qué hace
Procesa mensajes entrantes de Instagram/Telegram, genera respuestas
usando RAG + productos, aplica fast-path para precios, y envía respuesta.

## Archivos principales
- backend/core/dm_agent.py - Core del bot
- backend/api/routers/instagram.py - Webhook handler Instagram
- backend/core/telegram_adapter.py - Webhook handler Telegram
- backend/core/telegram_registry.py - Registry de bots Telegram
- backend/core/guardrails.py - Anti-alucinaciones
- backend/core/citation_service.py - RAG search

## Flujo verificado
1. Webhook recibe mensaje (instagram.py o telegram_adapter.py)
2. Identifica creator_id por page_id o bot_id
3. dm_agent.py procesa mensaje
4. Fast-path para preguntas de precio → responde directo sin LLM
5. citation_service.py busca contexto en RAG
6. guardrails.py valida anti-alucinaciones
7. Envía respuesta via Instagram/Telegram API
8. Guarda mensaje en DB
9. Actualiza lead score

## Verificado funcionando ✅
- Recibir webhooks Instagram ✅
- Recibir webhooks Telegram ✅
- Fast-path precios (77€ Coaching) ✅
- Buscar en RAG (108 docs) ✅
- Anti-alucinación (escala si no hay RAG) ✅
- Guardar mensajes en DB ✅
- Actualizar lead score ✅

## Fixes aplicados (15 Ene 2026)
1. **Fast-path precios**: Bypass LLM para "cuánto cuesta X"
   - Archivo: dm_agent.py línea ~3386
   - Buscar: "FAST PATH: Pregunta de precio"

2. **Telegram creator_id**: Bot usa fitpack_global (no stefano_auto)
   - Archivo: data/telegram/bots.json
   - Endpoint: PUT /telegram/bots/{bot_id}/creator

## Configuración necesaria
- LLM_PROVIDER=openai
- OPENAI_API_KEY válida
- bot_active=true
- copilot_mode=false (para auto-responder)

## ⚠️ NO TOCAR SIN MOTIVO
Este bloque funciona correctamente en producción.
Cualquier cambio requiere verificación manual por Manel.
