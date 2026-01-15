# CLONNECT - Estado Actual del Sistema

**Fecha de verificación:** 2026-01-15 15:30 UTC
**Verificado por:** Manel (DM real Instagram + Telegram)
**Ambiente:** Producción (Railway)

---

## URLs de Producción
- **Backend**: https://web-production-9f69.up.railway.app
- **Frontend**: https://frontend-wine-ten-57.vercel.app

---

## BLOQUES - Estado

### ✅ CONGELADOS (NO TOCAR)
| Bloque | Estado | Verificación |
|--------|--------|--------------|
| BOT_CORE | ✅ Funciona | DM real Instagram + Telegram |
| COPILOT | ✅ Funciona | Envío mensaje desde Dashboard |
| DASHBOARD | ✅ Funciona | Toggle copilot, ver leads |
| DATA_INGESTION | ✅ Funciona | 108 docs RAG indexados |

### 🔨 EN TRABAJO
| Bloque | Estado | Pendiente |
|--------|--------|-----------|
| INTEGRATIONS | 40% | Payment links, Google Meet |
| AUTH | Básico | Solo API keys |
| ONBOARDING | Manual | Script semi-automático |
| NURTURING | 60% | Secuencias básicas |

---

## CHECKLIST DE ESTABILIZACIÓN

### FASE 2: Componentes Core (8/8 ✅)
| # | Componente | Estado |
|---|------------|--------|
| 2.1 | Backend Health | ✅ OK |
| 2.2 | API Leads | ✅ 78 leads |
| 2.3 | API Products | ✅ 4 productos |
| 2.4 | Webhook Instagram | ✅ Bot responde OK |
| 2.5 | RAG Search | ✅ 108 docs |
| 2.6 | Bot Response | ✅ 77€ correcto |
| 2.7 | Copilot Mode | ✅ Genera y envía |
| 2.8 | Config Bot | ✅ Toggle funciona |

### FASE 5: Problemas Reportados
| # | Problema | Estado |
|---|----------|--------|
| 5.1 | Bot no responde DMs | ✅ RESUELTO |
| 5.2 | Scraping datos fake | ✅ NO APLICA |
| 5.3 | Payment links vacíos | ⚠️ PENDIENTE |
| 5.4 | Google Meet | ⚠️ PENDIENTE |

---

## Productos en DB (fitpack_global)

| Producto | Precio | Payment Link |
|----------|--------|--------------|
| Coaching 1:1 | 77€ | ⚠️ Vacío |
| Taller Respira, Siente y Conecta | 75€ | ⚠️ Vacío |
| Challenge 11 Días | 22€ | ⚠️ Vacío |
| Sesión de Descubrimiento | GRATIS | N/A |

---

## Conexiones (fitpack_global)

| Servicio | Estado |
|----------|--------|
| Instagram | ✅ Conectado |
| Telegram | ✅ Conectado (via bots.json) |
| Google | ❌ No conectado |
| Stripe | ❌ No conectado |
| Calendly | ❌ No conectado |

---

## QUÉ NO TOCAR

### Archivos críticos (congelados)
- `backend/core/dm_agent.py` - Core del bot
- `backend/core/copilot_service.py` - Lógica copilot
- `backend/core/citation_service.py` - RAG search
- `backend/core/telegram_registry.py` - Registry bots
- `backend/api/routers/instagram.py` - Webhook IG

### Datos críticos
- `data/telegram/bots.json` - Tokens de Telegram
- DB: tabla `rag_documents` - 108 docs indexados
- DB: tabla `products` - Precios correctos

---

## Pendientes Inmediatos (No críticos para bot)

1. **Payment links**: Añadir links de pago a productos
2. **Google Calendar**: Conectar OAuth
3. **WhatsApp**: No verificado

---

## Últimos Fixes (15 Ene 2026)

1. **precio-coaching-fix**: Fast-path para preguntas de precio
2. **telegram-creator-fix**: Bot usa fitpack_global
3. **copilot-telegram-fix**: Envío usa TelegramBotRegistry

---

*Última actualización: 2026-01-15 15:30 UTC*
