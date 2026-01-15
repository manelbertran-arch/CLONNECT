# Estado Actual del Sistema - CLONNECT

**Última actualización:** 15 Enero 2026

## URLs de Producción

| Servicio | URL | Notas |
|----------|-----|-------|
| Backend (Railway) | https://web-production-9f69.up.railway.app | API principal |
| Frontend NUEVO (Vercel) | https://frontend-wine-ten-57.vercel.app | Dashboard actualizado |
| Frontend VIEJO (Vercel) | https://clonnect.vercel.app | Proyecto anterior, sin cambios recientes |

## Estado de Componentes

### Backend API ✅ Funcionando

- **Health:** OK
- **Endpoints probados:**
  - `/health` - OK
  - `/dm/process` - OK (bot responde)
  - `/webhook/instagram` - OK (verificación funciona)
  - `/copilot/*` - OK (toggle funciona)
  - `/leads/*` - OK
  - `/products/*` - OK

### Base de Datos ✅ Funcionando

- **Leads:** 22 leads reales de fitpack_global
- **Productos:** 4 productos reales:
  - Coaching 1:1 - €150
  - Taller Grupal - €75
  - Sesión Descubrimiento - €0 (gratis)
  - Challenge 21 días - €22
- **Mensajes:** Historial de conversaciones guardado

### RAG (Retrieval Augmented Generation) ✅ Funcionando

- **Documentos indexados:** 108 para fitpack_global
- **Fuentes:** Productos, testimonios, FAQs, contenido del creador
- **Estado:** Indexado y funcionando

### Bot de DM ✅ Funcionando

- Responde con contenido del RAG
- Detecta intents correctamente
- Modo Copilot funciona (aprobación manual)
- Modo Automático funciona (respuesta directa)

### Dashboard ✅ Funcionando

- Traducido completamente a español
- Toggle de modo Copilot rediseñado con cards
- Métricas funcionando
- Gestión de leads funcionando

## Bugs Arreglados (15 Enero 2026)

1. **RAG vacío** → Indexados 108 documentos
2. **Productos fake** → 4 productos reales
3. **Toggle Copilot roto** → Funciona correctamente (fix: leer directo de DB)
4. **Dashboard en inglés** → Traducido a español

## Pendiente

- [ ] Anti-alucinación: Bot solo debe responder con contenido del RAG
- [ ] Tests de regresión automáticos
- [ ] Verificar bot en Instagram real con mensajes de usuarios
- [ ] Migrar dominio clonnect.vercel.app al proyecto nuevo

## Git Tags (Checkpoints)

- `pre-bot-fix-toggle-ok` - Estado estable con toggle arreglado
