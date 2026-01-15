# CONTEXTO DE TRABAJO - CLONNECT

## METODOLOGÍA OBLIGATORIA
1. ANTES de cualquier cambio: Verificar qué funciona actualmente
2. UN problema a la vez: No tocar múltiples cosas simultáneamente
3. CHECKPOINT después de cada fix: git tag + push
4. VERIFICACIÓN MANUAL: Manel confirma, no confiar solo en curls
5. Si algo se rompe: Rollback con ./scripts/rollback.sh

## CHECKPOINTS DISPONIBLES
- telegram-creator-fix ← ACTUAL (15 ene 2026)
- instagram-verificado-ok
- precio-coaching-fix
- cache-productos-fix
- rag-anti-alucinacion-completa
- anti-alucinacion-completa
- sesion-15-ene-completa
- pre-bot-fix-toggle-ok

## URLS
- Backend: https://web-production-9f69.up.railway.app
- Frontend: https://frontend-wine-ten-57.vercel.app

## ESTADO ACTUAL (15 Ene 2026)

### Funciona
- Saludos del bot
- **TODOS los productos con precios correctos:**
  - Coaching 1:1: 77€ ✅
  - Taller de respiración: 75€ ✅
  - Challenge 11 Días: 22€ ✅
  - Sesión de Descubrimiento: GRATIS ✅
- Caché desactivado (TTL=0)
- Anti-alucinación (escala si no hay RAG)
- Toggle Copilot
- Dashboard en español
- RAG con 108 documentos
- Fast path para preguntas de precio (bypass LLM)
- Bot Instagram verificado con DM real ✅
- Bot Telegram usa mismo creator_id que Instagram (fitpack_global) ✅

### Pendientes
- [ ] Manel: Verificar Telegram con mensaje real

## PRODUCTOS EN DB
- Coaching 1:1: 77€
- Taller Respira, Siente y Conecta: 75€
- Sesión de Descubrimiento: 0€
- Challenge 11 Días: 22€

## FIX APLICADO: Coaching Fallback
El problema era que el LLM generaba respuestas incorrectas para "coaching" porque
el RAG tenía contenido sobre "COACHING CUÁNTICO" (diferente del producto "Coaching 1:1").
Solución: Fast path que responde directamente con el precio del producto cuando
el usuario pregunta "cuánto cuesta X" y el producto está identificado.
Archivo: `core/dm_agent.py` - búsqueda por "FAST PATH: Pregunta de precio"

## FIX APLICADO: Telegram creator_id
El problema era que Telegram usaba `creator_id: "stefano_auto"` en vez de `fitpack_global`.
- Instagram: fitpack_global (productos correctos)
- Telegram: stefano_auto (productos diferentes: 997€)

Solución: Cambiar creator_id del bot en el registry.
Comando: `PUT /telegram/bots/8485313235/creator?creator_id=fitpack_global`
Almacenamiento: `data/telegram/bots.json` (archivo JSON en servidor)
