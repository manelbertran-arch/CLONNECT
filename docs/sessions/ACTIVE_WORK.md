# TRABAJO ACTIVO

## Estado: ✅ SISTEMA ESTABLE

## Última sesión: 2026-01-15 15:30 UTC

### Qué se verificó hoy
- ✅ Bot Instagram responde (DM real)
- ✅ Bot Telegram responde (precio 77€)
- ✅ Copilot envía mensajes Telegram
- ✅ RAG funciona (108 docs)
- ✅ Dashboard toggle copilot OK

### Fixes aplicados
1. **precio-coaching-fix**: Fast-path precios sin LLM
2. **telegram-creator-fix**: creator_id correcto
3. **copilot-telegram-fix**: Usa TelegramBotRegistry

### Checkpoints disponibles
- `copilot-telegram-fix` ← ACTUAL
- `telegram-creator-fix`
- `instagram-verificado-ok`
- `precio-coaching-fix`

---

## BLOQUES CONGELADOS (NO TOCAR)

| Bloque | Verificado |
|--------|-----------|
| BOT_CORE | ✅ 15 ene |
| COPILOT | ✅ 15 ene |
| DASHBOARD | ✅ 15 ene |
| DATA_INGESTION | ✅ 15 ene |

---

## Pendientes (no críticos)

| Tarea | Prioridad |
|-------|-----------|
| Payment links en productos | Media |
| Google Calendar OAuth | Baja |
| WhatsApp verificar | Baja |

---

## Para próxima sesión

Antes de empezar cualquier tarea:
1. Leer `docs/CURRENT_STATE.md`
2. Leer `docs/blocks/` del bloque a tocar
3. Ejecutar `python scripts/verify_integration.py`
4. Si todo OK → Proceder con tarea
5. Si falla → Investigar primero

### Metodología
1. UN problema a la vez
2. Verificar que funciona ANTES de tocar
3. Checkpoint después de cada fix
4. Manel confirma manualmente
