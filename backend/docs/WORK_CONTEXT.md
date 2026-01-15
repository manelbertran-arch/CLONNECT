# CONTEXTO DE TRABAJO - CLONNECT

## METODOLOGÍA OBLIGATORIA
1. ANTES de cualquier cambio: Verificar qué funciona actualmente
2. UN problema a la vez: No tocar múltiples cosas simultáneamente
3. CHECKPOINT después de cada fix: git tag + push
4. VERIFICACIÓN MANUAL: Manel confirma, no confiar solo en curls
5. Si algo se rompe: Rollback con ./scripts/rollback.sh

## CHECKPOINTS DISPONIBLES
- cache-productos-fix ← ACTUAL (15 ene 2026)
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
- Taller de respiración (75€)
- Caché desactivado (TTL=0)
- Anti-alucinación (escala si no hay RAG)
- Toggle Copilot
- Dashboard en español
- RAG con 108 documentos

### Pendientes
- [ ] Coaching da fallback en vez de precio (77€ en DB)
- [ ] Verificar bot con DM real en Instagram

## PRODUCTOS EN DB
- Coaching 1:1: 77€
- Taller Respira, Siente y Conecta: 75€
- Sesión de Descubrimiento: 0€
- Challenge 11 Días: 22€
