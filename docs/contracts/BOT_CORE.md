# CONTRATO: BOT_CORE

## Propósito
Procesar mensajes de Instagram/Telegram y generar respuestas usando RAG.

## Entradas
- Mensaje de usuario (texto)
- Creator ID
- Platform (instagram/telegram)
- Sender ID

## Salidas
- Respuesta de texto
- Intent detectado
- Producto mencionado (si aplica)
- Action taken

## Endpoints expuestos
```
POST /dm/process
  Input: {creator_id, sender_id, message, platform}
  Output: {response_text, intent, product_mentioned, action_taken}

GET /dm/leads/{creator_id}
  Output: [{lead_id, name, platform, status, score}]

POST /webhook/instagram
  Input: Meta webhook payload
  Output: 200 OK

POST /webhook/telegram
  Input: Telegram update payload
  Output: 200 OK
```

## Dependencias internas
- citation_service.py → Buscar en RAG
- guardrails.py → Validar respuesta
- telegram_registry.py → Tokens de Telegram

## Invariantes (NUNCA deben romperse)
1. Preguntas de precio → Devuelve precio de DB, NO inventa
2. Si no hay match en RAG → Escala a humano
3. Mensajes guardados en DB con timestamp
4. Lead score actualizado después de cada mensaje

## Tests de regresión
```bash
# Test 1: Health check
curl https://...app/health
# Esperado: status=healthy

# Test 2: Precio coaching
curl -X POST https://...app/dm/process \
  -d '{"creator_id":"fitpack_global","sender_id":"test","message":"cuanto cuesta coaching"}'
# Esperado: response contiene "77€"

# Test 3: RAG funciona
curl "https://...app/content/search?creator_id=fitpack_global&query=coaching"
# Esperado: count > 0
```

## Métricas de salud
- Tiempo respuesta < 3s
- Error rate < 1%
- Fallback rate < 10%

---
*Última actualización: 2026-01-15*
