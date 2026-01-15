# CONTEXTO DE TRABAJO - CLONNECT

## METODOLOGÍA OBLIGATORIA
1. ANTES de cualquier cambio: Verificar qué funciona actualmente
2. UN problema a la vez: No tocar múltiples cosas simultáneamente
3. CHECKPOINT después de cada fix: git tag + push
4. VERIFICACIÓN MANUAL: Manel confirma, no confiar solo en curls
5. Si algo se rompe: Rollback con ./scripts/rollback.sh

## CHECKPOINT ACTUAL
sesion-15-enero-completa (15 ene 2026)

## CHECKPOINTS DISPONIBLES
- sesion-15-enero-completa ← ACTUAL
- rate-limiter-preventivo
- instagram-verificado-ok
- precio-coaching-fix
- cache-productos-fix

## URLs
- Backend: https://web-production-9f69.up.railway.app
- Dashboard: https://clonnect.vercel.app

## COMPLETADO HOY (15 ene 2026)
- [x] 128 tests pasando
- [x] Rate limiter Instagram preventivo
- [x] Lead scoring funcionando (3 HOT, 33 NEW)
- [x] Sync DMs con batching
- [x] Token auto-refresh (cron diario)
- [x] 8 productos de Stefano
- [x] 361 docs en RAG
- [x] Anti-alucinación verificada

## PENDIENTE
- [ ] Sync incremental (solo mensajes nuevos)
- [ ] Verificar sync cuando Meta resetee rate limit
