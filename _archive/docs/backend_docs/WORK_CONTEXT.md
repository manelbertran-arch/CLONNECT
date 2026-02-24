# CONTEXTO DE TRABAJO - CLONNECT

## METODOLOGÍA OBLIGATORIA
1. ANTES de cualquier cambio: Verificar qué funciona actualmente
2. UN problema a la vez: No tocar múltiples cosas simultáneamente
3. CHECKPOINT después de cada fix: git tag + push
4. VERIFICACIÓN MANUAL: Manel confirma, no confiar solo en curls
5. Si algo se rompe: Rollback con ./scripts/rollback.sh

## CHECKPOINTS DISPONIBLES
- copilot-telegram-fix ← ACTUAL (15 ene 2026)
- telegram-creator-fix
- instagram-verificado-ok
- precio-coaching-fix
- cache-productos-fix
- rag-anti-alucinacion-completa
- anti-alucinacion-completa
- sesion-15-ene-completa
- pre-bot-fix-toggle-ok

## URLS
- Production: https://www.clonnectapp.com

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
- Bot Telegram verificado con mensaje real - 77€ correcto ✅
- Dashboard Copilot envía mensajes a Telegram ✅

### Pendientes
- Payment links vacíos en todos los productos
- Google Meet/Calendar no conectado

---

## CHECKLIST DE ESTABILIZACIÓN (15 Ene 2026)

### FASE 2: Verificación de Componentes Core
| # | Componente | Estado | Notas |
|---|------------|--------|-------|
| 2.1 | Backend Health | ✅ | Todos los checks pasados |
| 2.2 | API Leads | ✅ | 78 leads reales |
| 2.3 | API Products | ✅ | 4 productos con precios correctos |
| 2.4 | Webhook Instagram | ✅ | Bot responde, Copilot envía OK |
| 2.5 | RAG Search | ✅ | 108 docs, anti-alucinación funciona |
| 2.6 | Bot Response | ✅ | 77€ correcto en Instagram y Telegram |
| 2.7 | Copilot Mode | ✅ | Genera y envía mensajes OK |
| 2.8 | Config Bot | ✅ | Toggle copilot funciona |

### FASE 5: Problemas Reportados
| # | Problema | Estado | Notas |
|---|----------|--------|-------|
| 5.1 | Bot no responde DMs | ✅ RESUELTO | Funciona en ambas plataformas |
| 5.2 | Scraping genera datos fake | ✅ NO APLICA | RAG tiene contenido real (stefanobonanno.com) |
| 5.3 | Payment links vacíos | ⚠️ PENDIENTE | Los 4 productos tienen payment_link="" |
| 5.4 | Google Meet desconectado | ⚠️ PENDIENTE | google.connected: false |

### Resumen
- **FASE 2**: 8/8 verificados ✅
- **FASE 5**: 2/4 resueltos, 2 pendientes (no críticos para bot)

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

## FIX APLICADO: Copilot envío Telegram
El problema era que el Dashboard mostraba "no está conectado" al enviar mensajes.
- copilot_service.py buscaba `creator.telegram_bot_token` (tabla Creator)
- Pero el token está en `data/telegram/bots.json` (TelegramBotRegistry)

Solución: Modificar `_send_telegram_message()` para buscar primero en el registry.
Archivo: `core/copilot_service.py` - método `_send_telegram_message()`
