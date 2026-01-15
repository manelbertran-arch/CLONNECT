# BLOQUE: BOT_CORE
Estado: 🔨 EN TRABAJO (85%)
Última verificación: 2026-01-15

## Qué hace
Procesa mensajes entrantes de Instagram/Telegram, genera respuestas
usando RAG + ToneProfile, valida anti-alucinaciones, y envía respuesta.

## Archivos principales
- backend/core/dm_agent.py (216KB) - Core del bot
- backend/core/instagram_handler.py - Webhook handler Instagram
- backend/core/telegram_adapter.py - Webhook handler Telegram
- backend/core/guardrails.py - Anti-alucinaciones
- backend/core/citation_service.py - RAG search
- backend/core/tone_service.py - ToneProfile

## Flujo
1. Webhook recibe mensaje (instagram_handler.py)
2. Rate limiter verifica (rate_limiter.py)
3. dm_agent.py procesa mensaje
4. citation_service.py busca contexto en RAG
5. tone_service.py aplica personalidad
6. guardrails.py valida anti-alucinaciones
7. Envía respuesta via Instagram API
8. Guarda mensaje en DB
9. Actualiza lead score

## Qué funciona ✅
- Recibir webhooks Instagram/Telegram
- Buscar en RAG
- Aplicar ToneProfile
- Rate limiting
- Guardar mensajes en DB
- Actualizar lead score

## Qué falta ⚠️
- Anti-alucinaciones no siempre funciona
- A veces inventa precios cuando no encuentra en RAG

## Configuración necesaria
- LLM_PROVIDER=openai (NO groq)
- OPENAI_API_KEY válida
- bot_active=true
- copilot_mode=false (para auto-responder)

## Tests pendientes
- test_webhook_receives_message()
- test_rag_returns_relevant_chunks()
- test_response_uses_tone_profile()
- test_price_comes_from_products_db()
- test_no_hallucination()
