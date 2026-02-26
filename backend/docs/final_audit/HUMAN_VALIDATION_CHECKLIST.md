# HUMAN VALIDATION CHECKLIST — Beta con Stefano Bonanno
**Capa 7: Human in the Loop**
**Fecha**: 2026-02-26 | **Tester**: Stefano Bonanno | **Env**: producción

---

## OVERVIEW

Este checklist guía el testing manual completo de Clonnect con Stefano como beta tester real. Cubre todos los sistemas identificados en `CLONNECT_SYSTEM_AUDIT.md`. Cada test tiene:
- **Acción**: qué hacer exactamente
- **Resultado esperado**: qué debe pasar
- **Verificación**: cómo confirmarlo (dashboard / DB / logs)
- **Prioridad**: P0 = bloqueante, P1 = importante, P2 = nice-to-have

---

## SECCIÓN 1: TESTS FUNCIONALES POR SISTEMA

### A. DM PIPELINE

| ID | Prioridad | Acción | Resultado Esperado | Verificación |
|----|-----------|--------|-------------------|--------------|
| DM-01 | P0 | Enviar DM de texto simple ("Hola") desde cuenta test a Stefano | Bot responde en <15s con saludo en tono Stefano | Dashboard → Leads → ver mensaje + respuesta. Logs: `[DM] pipeline success` |
| DM-02 | P0 | Enviar DM con intención de compra ("¿Cuánto cuesta tu curso?") | Respuesta con precio real del producto (de knowledge base), sin inventar | Verificar que el precio coincide con `products` table. RAG citation visible en logs |
| DM-03 | P0 | Enviar DM con frustración ("llevo semanas esperando y nada") | Respuesta empática, tono más suave, sin prometer lo que no puede cumplir | Logs: `frustration_level > 0.5`. Respuesta no agresiva |
| DM-04 | P1 | Enviar solo emojis ("🔥🔥🔥") | Bot responde (no crashea), respuesta corta informal | HTTP 200, respuesta >0 chars |
| DM-05 | P1 | Enviar mensaje de 500+ caracteres (párrafo largo) | Bot responde sin timeout, respuesta proporcional en longitud | HTTP 200 en <20s, respuesta coherente |
| DM-06 | P1 | Enviar audio/nota de voz | Bot detecta audio, responde textualmente o pide repetición | Sin crash. Logs: `media_type=audio` handled |
| DM-07 | P1 | Enviar imagen | Bot detecta imagen, responde contextualmente | Sin crash. Logs: `media_type=image` |
| DM-08 | P2 | Enviar story reply | Bot procesa como DM normal | Sin crash, lead creado |
| DM-09 | P0 | Conversación de 5+ mensajes seguidos (same thread) | Bot mantiene contexto, no repite presentaciones, recuerda info previa | Respuesta en msg5 referencia info de msg1-2 |
| DM-10 | P1 | Cambio de tema mid-conversation ("Ok, olvida lo del curso. ¿Hacés colaboraciones?") | Bot detecta cambio de intent, categoriza lead como `colaborador` | Lead status updated en DB. Nueva categoría visible en dashboard |

---

### B. COPILOT SYSTEM

| ID | Prioridad | Acción | Resultado Esperado | Verificación |
|----|-----------|--------|-------------------|--------------|
| CP-01 | P0 | Verificar que copilot_mode=true para Stefano | Sugerencias aparecen en `/copilot/stefano_bonanno/pending` | `GET /copilot/stefano_bonanno/pending` → pending_count ≥ 0 (no 500) |
| CP-02 | P0 | Stefano aprueba sugerencia sin editar | Mensaje se envía a Instagram exactamente como fue sugerido | Dashboard → Copilot → Approve. Luego ver DM en Instagram. `Message.status='sent'`, `copilot_action='approved'` |
| CP-03 | P0 | Stefano edita sugerencia y aprueba | Mensaje editado se envía; autolearning se dispara | Ver DM en Instagram con texto editado. Logs: `[AutoLearning] edit analyzed`. `learning_rules` table nueva regla |
| CP-04 | P0 | Stefano descarta sugerencia | Sugerencia marcada discarded, DM no se envía | `Message.status='discarded'`. No llega DM a follower |
| CP-05 | P1 | Stefano escribe respuesta manual (override) | Override registrado, bot suggestion descartada, manual response enviada | `copilot_action='manual_override'` en DB. GoldExample creado |
| CP-06 | P1 | Verificar debounce: DM llega mientras Stefano está viendo otra sugerencia | Sistema espera 2s antes de crear nueva pending (no duplica) | Solo 1 pending por lead en DB |
| CP-07 | P2 | Aprobar múltiples sugerencias en orden (5 pendientes) | Todas se envían en orden correcto, sin mezclar threads | Verificar en Instagram que cada respuesta llega a su conversación correcta |
| CP-08 | P1 | Descartar todas las pendientes (`POST /copilot/stefano_bonanno/discard-all`) | Todas descartadas, count=0 | `GET /copilot/pending` → pending_count=0 |

---

### C. LEAD SCORING & LIFECYCLE

| ID | Prioridad | Acción | Resultado Esperado | Verificación |
|----|-----------|--------|-------------------|--------------|
| LS-01 | P0 | Verificar leads de Stefano en dashboard | Lista de leads con status y score visible | `GET /dm/leads/stefano_bonanno` → 200, lista con items |
| LS-02 | P0 | Lead nuevo envía DM de compra → verificar clasificación | Lead categorizado como `caliente`, score 45-85 | DB: `leads.status='caliente'`, `leads.score` en rango |
| LS-03 | P1 | Lead existente cambia de `nuevo` a `caliente` en conversación | Score actualizado en tiempo real | Refresh dashboard → lead en columna caliente |
| LS-04 | P1 | Trigger rescore manual (`POST /admin/dm/leads/rescore/stefano_bonanno`) | Todos los leads rescoreados, respuesta con totales | HTTP 200, `{total, updated, by_status: {...}}` |
| LS-05 | P2 | Lead inactivo 14+ días → verificar `frío` | Lead marcado frío en próximo rescore | `leads.status='frío'` tras scheduler daily |
| LS-06 | P1 | Lead marca `cliente` (viene pago de Stripe) | Status 'cliente' preservado, score 75-100, no baja | Lead status=cliente tras webhook payment |

---

### D. RAG / KNOWLEDGE BASE

| ID | Prioridad | Acción | Resultado Esperado | Verificación |
|----|-----------|--------|-------------------|--------------|
| RAG-01 | P0 | DM pregunta por info específica de Stefano (ej. precio de curso) | Respuesta cita el precio real extraído de su web | Precio en respuesta = precio en `products` table. Sin inventar |
| RAG-02 | P0 | DM pregunta algo que NO está en knowledge base | Respuesta honesta ("no tengo info sobre eso") o redirige sin inventar | No hallucination. Respuesta coherente sin datos inventados |
| RAG-03 | P1 | Verificar documentos indexados | Knowledge base tiene docs de Stefano | `GET /creator/config/stefano_bonanno/knowledge` → documentos presentes |
| RAG-04 | P1 | Trigger re-indexación (`POST /admin/ingestion/refresh/stefano_bonanno`) | Nuevos documentos indexados | `rag_documents` count aumenta o se mantiene. Logs: `indexed N docs` |
| RAG-05 | P2 | DM con pregunta del FAQ de Stefano | Respuesta usa el FAQ exacto | Respuesta incluye info del FAQ. Citation en logs |

---

### E. ONBOARDING & CONFIGURACIÓN

| ID | Prioridad | Acción | Resultado Esperado | Verificación |
|----|-----------|--------|-------------------|--------------|
| OB-01 | P0 | Verificar que Stefano tiene `onboarding_completed=true` | Config completa en DB | `GET /creator/config/stefano_bonanno` → `onboarding_completed: true` |
| OB-02 | P0 | Verificar ToneProfile de Stefano | Perfil de tono con dialect, voz, vocabulario | `GET /tone/stefano_bonanno` → profile con datos reales |
| OB-03 | P1 | Verificar productos indexados | Productos de Stefano en DB | `GET /creator/stefano_bonanno/products` → lista de productos |
| OB-04 | P1 | Verificar instagram_token activo | Token no expirado, bot activo | `GET /admin/oauth/status/stefano_bonanno` → `token_valid: true` |
| OB-05 | P0 | Verificar bot activo | `bot_active=true` en Creator | `GET /bot/stefano_bonanno/status` → 200, `active: true` |

---

### F. INSTAGRAM SYNC

| ID | Prioridad | Acción | Resultado Esperado | Verificación |
|----|-----------|--------|-------------------|--------------|
| SY-01 | P0 | Verificar sync histórico completado | Conversaciones previas de Instagram en DB | `GET /dm/conversations/stefano_bonanno` → lista con items |
| SY-02 | P1 | Trigger sync manual (`POST /admin/sync-dm/stefano_bonanno`) | Nuevas conversaciones sincronizadas | `sync_state` updated, `messages` count aumenta |
| SY-03 | P1 | Verificar que DM enviado aparece en thread de Instagram | After approve → DM visible en IG app | Abrir Instagram → verificar DM llegó al follower |
| SY-04 | P2 | Lead que ya tenía conversación previa → sync correcto | No duplicados, historial correcto | `messages` table sin duplicados por `platform_message_id` |

---

### G. NURTURING ENGINE

| ID | Prioridad | Acción | Resultado Esperado | Verificación |
|----|-----------|--------|-------------------|--------------|
| NU-01 | P1 | Verificar secuencias configuradas para Stefano | Sequences en DB | `GET /nurturing/stefano_bonanno/sequences` → lista |
| NU-02 | P1 | Lead caliente sin respuesta 3+ días → nurturing trigger | Follower recibe follow-up DM automático | `nurturing_followups` table, DM enviado |
| NU-03 | P2 | Ghost reactivation (lead inactivo 7+ días) | Reactivation DM enviado por scheduler | Logs: `[Ghost] reactivation sent to {lead_id}` |

---

### H. ANALYTICS & DASHBOARD

| ID | Prioridad | Acción | Resultado Esperado | Verificación |
|----|-----------|--------|-------------------|--------------|
| AN-01 | P0 | Stefano carga dashboard | Página carga sin errores, métricas visibles | HTTP 200, sin errores JS en consola |
| AN-02 | P0 | Ver overview de leads | Leads categorizados con totales por status | Dashboard → Leads → columnas caliente/cliente/nuevo/frío |
| AN-03 | P1 | Ver historial de conversación de un lead | Timeline de mensajes con timestamps | Click en lead → ver mensajes ordenados |
| AN-04 | P1 | Ver analytics de ventas | Revenue, conversiones del período | `GET /analytics/stefano_bonanno/sales` → datos reales |
| AN-05 | P2 | Clone score | Score visible | `GET /clone-score/stefano_bonanno` → score numérico |

---

### I. PAYMENTS (si aplica)

| ID | Prioridad | Acción | Resultado Esperado | Verificación |
|----|-----------|--------|-------------------|--------------|
| PAY-01 | P1 | Verificar webhook Stripe configurado para Stefano | Webhook activo | Stripe Dashboard → Webhooks → events recibidos |
| PAY-02 | P1 | Pago de prueba (Stripe test mode) | PaymentRecord creado, lead→cliente | `payment_records` table, lead status=cliente |

---

## SECCIÓN 2: PROTOCOLO DÍA A DÍA CON STEFANO

### DÍA 1 — Conexión & Verificación de Base

**Objetivo**: Confirmar que la infraestructura de Stefano está correctamente configurada.

```
09:00 — Pre-flight check (Manel)
  □ curl GET /bot/stefano_bonanno/status → 200, active=true
  □ curl GET /oauth/status/stefano_bonanno → token_valid=true
  □ curl GET /copilot/stefano_bonanno/pending → 200 (no 500)
  □ curl GET /tone/stefano_bonanno → profile con dialect
  □ curl GET /creator/stefano_bonanno/products → N productos
  □ curl GET /dm/conversations/stefano_bonanno → conversaciones

10:00 — Con Stefano
  □ Stefano abre el dashboard en su navegador → carga sin errores (AN-01)
  □ Stefano ve sus leads categorizados (AN-02)
  □ Stefano verifica que su tone profile es correcto (OB-02)
    → "¿Reconoces tu forma de hablar aquí?"
  □ Stefano verifica sus productos indexados (OB-03)
    → "¿Están todos tus productos con precios correctos?"
  □ Si faltan productos → trigger refresh ingestion (RAG-04)

11:00 — Verificación knowledge base
  □ Stefano hace 3 preguntas sobre su contenido (ej. precios, temas de posts)
  □ Verificar que las respuestas del bot son precisas (RAG-01, RAG-02)
  □ Si RAG no responde bien → reindexar

Criterio de éxito Día 1:
  ✓ Dashboard carga sin errores
  ✓ Token Instagram activo
  ✓ Tone profile reconocido por Stefano como suyo
  ✓ ≥80% de productos correctamente indexados
```

---

### DÍA 2 — DM Pipeline Real

**Objetivo**: Validar que el bot responde correctamente a DMs reales.

**Setup**: Necesitas una cuenta Instagram de prueba (no la de Stefano).

```
10:00 — Tests básicos (DM desde cuenta test)
  □ Enviar "Hola!" → verificar respuesta en <15s (DM-01)
  □ Enviar pregunta de precio → verificar precio correcto (DM-02, RAG-01)
  □ Enviar mensaje largo (150+ palabras) → verificar respuesta coherente (DM-05)
  □ Enviar solo emojis → verificar que no crashea (DM-04)

11:00 — Tests de copilot con Stefano
  □ Stefano ve sugerencias en dashboard (CP-01)
  □ Stefano aprueba 1 sugerencia → verificar que llega al follower (CP-02)
  □ Stefano edita 1 sugerencia → verificar envío + autolearning (CP-03)
  □ Stefano descarta 1 sugerencia → verificar que no se envía (CP-04)

14:00 — Edge cases
  □ Enviar audio (nota de voz) desde cuenta test (DM-06)
  □ Enviar imagen (DM-07)
  □ Enviar mensaje de frustración (DM-03)
  □ Enviar pregunta que NO está en knowledge base (RAG-02)

Criterio de éxito Día 2:
  ✓ Bot responde en <15s al 95% de mensajes
  ✓ 0 crashes/500 errors
  ✓ Precio citado = precio real en DB (no alucinación)
  ✓ Stefano puede aprobar/editar/descartar desde dashboard
  ✓ DMs aprobados llegan a Instagram
```

---

### DÍA 3 — Copilot Intensivo & Dashboard

**Objetivo**: Stefano usa el product completo como lo usaría en producción.

```
10:00 — Simular bandeja de entrada real
  □ 5+ DMs simultáneos desde diferentes cuentas test
  □ Stefano gestiona todas desde dashboard (aprobar/editar/descartar)
  □ Verificar que cada respuesta llega a su thread correcto (CP-07)
  □ Medir: % aprobadas sin editar (target >40%), tiempo de revisión

11:00 — Lead management
  □ Stefano ve lead que preguntó por precio → categoría caliente (LS-02)
  □ Stefano añade nota manual a un lead (LeadActivity)
  □ Stefano cambia status de lead manualmente
  □ Stefano verifica historial completo de conversación de un lead (AN-03)

14:00 — Nurturing & automation
  □ Verificar secuencias de follow-up (NU-01)
  □ Revisar analytics del período (AN-04)
  □ Verificar clone score (AN-05)

Criterio de éxito Día 3:
  ✓ Stefano puede gestionar 5+ conversaciones simultáneas desde dashboard
  ✓ Leads correctamente categorizados
  ✓ Dashboard responsive y sin errores
  ✓ Stefano da feedback cualitativo positivo sobre calidad de sugerencias
```

---

### DÍA 4+ — Stress & Edge Cases

**Objetivo**: Confirmar resiliencia del sistema bajo carga y casos extremos.

```
Tests de stress:
  □ 10 DMs simultáneos → verificar que todos se procesan
  □ Conversación de 10+ mensajes en el mismo thread (DM-09)
  □ Lead que vuelve después de 7 días de silencio → contexto correcto
  □ Lead que cambia de tema 3 veces (DM-10)
  □ Ghost reactivation (si hay leads inactivos 7+ días) (NU-03)

Tests de resiliencia:
  □ Reiniciar app (railway redeploy) → verificar que no hay pérdida de datos
  □ Token Instagram casi expirado → verificar refresh automático
  □ RAG con query muy larga (500+ chars) → no timeout

Opcionales (si aplica a Stefano):
  □ Booking flow: follower pide sesión 1:1 → BookingLink → Calendly → CalendarBooking
  □ Pago Stripe test: follower compra → lead→cliente automáticamente
```

---

## SECCIÓN 3: CRITERIOS DE ÉXITO — GO / NO-GO

### P0 — Bloqueantes (deben cumplirse 100%)

| Criterio | Target | Medir |
|---------|--------|-------|
| 0 crashes (HTTP 500) durante el test | 0 errores | Logs en Railway |
| DMs aprobados llegan a Instagram | 100% | Verificar en IG app |
| Bot no alucina precios ni información | 0 alucinaciones | Verificar vs products table |
| Dashboard carga sin errores JS | 0 errors | Browser console |
| Copilot pending endpoint → 200 siempre | 100% | HTTP monitoring |
| Leads se crean automáticamente por DM | 100% de nuevos contactos | DB: leads table |

### P1 — Importantes (deben cumplirse >80%)

| Criterio | Target | Medir |
|---------|--------|-------|
| Tiempo de respuesta DM (webhook → pending) | <10s p95 | Railway logs timestamp |
| % DMs con respuesta coherente al contexto | >90% | Revisión manual Stefano |
| % sugerencias que Stefano aprueba sin editar | >40% | `copilot_action='approved'` count |
| Lead scoring correcto (caliente/cliente/nuevo) | >85% accuracy | Revisión manual 20 leads |
| RAG cita info real (no inventada) | 100% | Verificar precios/info vs fuente |

### P2 — Nice-to-have (mejoran la beta pero no la bloquean)

| Criterio | Target |
|---------|--------|
| Clone score ≥ 7.0/10 | Aspiracional |
| Nurturing sequences activas | Al menos 1 secuencia corriendo |
| Analytics con datos del período | Métricas visibles para Stefano |

### DECISION FINAL

```
GO   ← Si todos los P0 cumplen al 100% y los P1 cumplen al >80%
NO-GO ← Si cualquier P0 falla o los P1 <70%
CONDICIONAL ← P0 al 100%, P1 entre 70-80% (lista de fixes antes de siguiente creador)
```

---

## SECCIÓN 4: BUG TRACKING TEMPLATE

Para cada bug encontrado durante el testing, crear un entry en `bugs_beta.md`:

```markdown
## BUG-[ID]

**Fecha**: YYYY-MM-DD HH:MM
**Severidad**: P0 / P1 / P2
**Sistema afectado**: DM Pipeline / Copilot / Lead Scoring / RAG / Dashboard / Sync / Payments / Nurturing / Otro

### Pasos para reproducir
1.
2.
3.

### Resultado esperado
[Qué debería haber pasado]

### Resultado real
[Qué pasó realmente]

### Evidencia
- [ ] Screenshot: [adjuntar]
- [ ] Log: [pegar fragmento relevante]
- [ ] HTTP response: [status code + body]
- [ ] DB state: [query result si aplica]

### Hipótesis de causa raíz
[Archivo/función sospechosa]

### Estado
- [ ] OPEN — encontrado, no asignado
- [ ] IN PROGRESS — siendo investigado
- [ ] FIXED — fix implementado, pendiente verificación
- [ ] VERIFIED — fix verificado en producción
- [ ] WONT-FIX — no se arreglará (documentar razón)

### Fix aplicado
[Commit hash si está fixed]
```

---

## APÉNDICE — COMANDOS ÚTILES PARA TESTING

```bash
# Health check rápido
curl -s https://www.clonnectapp.com/health | python3 -m json.tool

# Verificar estado de Stefano
curl -s -H "X-API-Key: clonnect_admin_secret_2024" \
  https://www.clonnectapp.com/bot/stefano_bonanno/status

# Ver pending copilot
curl -s -H "X-API-Key: clonnect_admin_secret_2024" \
  "https://www.clonnectapp.com/copilot/stefano_bonanno/pending?limit=10"

# Enviar DM de prueba (dry-run, no envía a IG)
curl -s -X POST -H "Content-Type: application/json" \
  -H "X-API-Key: clonnect_admin_secret_2024" \
  -d '{"sender_id":"test_user_123","message":"Hola! ¿Cuánto cuesta tu curso?"}' \
  "https://www.clonnectapp.com/dm/stefano_bonanno"

# Ver leads
curl -s -H "X-API-Key: clonnect_admin_secret_2024" \
  "https://www.clonnectapp.com/dm/leads/stefano_bonanno?limit=20"

# Rescore leads
curl -s -X POST -H "X-API-Key: clonnect_admin_secret_2024" \
  "https://www.clonnectapp.com/admin/dm/leads/rescore/stefano_bonanno"

# Ver logs en tiempo real
cd ~/Clonnect && railway logs --tail 50

# Run massive test (producción)
cd ~/Clonnect/backend && python3 massive_test.py
```

---

## REGISTRO DE TESTS EJECUTADOS

| Fecha | Tester | Tests | PASS | FAIL | Notas |
|-------|--------|-------|------|------|-------|
| 2026-02-26 | Manel (auto) | 366 | 366 | 0 | Pre-beta automated |
| — | Stefano | — | — | — | Día 1 pendiente |
| — | Stefano | — | — | — | Día 2 pendiente |
| — | Stefano | — | — | — | Día 3 pendiente |
| — | Stefano | — | — | — | Stress tests pendiente |
