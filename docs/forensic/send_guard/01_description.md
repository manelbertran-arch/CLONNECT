# Fase 1 — Descripción y valor del sistema `send_guard`

**Artefacto:** `backend/core/send_guard.py` (87 LOC)
**Fecha:** 2026-04-23
**Branch:** `forensic/send-guard-20260423`
**Callsites productivos:** **6 reales** (el plan lista 5; evolution_api tiene 2 entradas simétricas: texto y media)
**Capa pipeline:** SEND-TIME — **última barrera** antes de cualquier POST a plataforma externa
**Flag env:** — (sin flag, hardcoded ON por diseño)
**Estado Railway:** ON **siempre** (safety-critical, apagarlo = incidente legal)
**Primer commit:** `e2713c6e` (2026-02-19) — "safety guard — autopilot only via dashboard + premium flag"
**Autor:** manel bertran luque + Claude Opus 4.6

---

## 1. Qué hace funcionalmente

`send_guard.py` expone **una única función pública** `check_send_permission(creator_id, approved, caller)` que se invoca **inmediatamente antes** de cualquier llamada a API externa de mensajería (Telegram, Instagram Graph, WhatsApp via Evolution, Meta graph). Decide, en tiempo de envío y con lectura fresca de DB, si el mensaje puede pasar o debe bloquearse.

Su filosofía es **fail-closed**: por defecto **niega**; solo habilita el envío si se cumple una de dos condiciones explícitas. Cualquier estado inesperado (creator no existe, excepción DB, flags `None`) resulta en **`raise SendBlocked`**, nunca en un envío silencioso.

No es un rate-limiter, no es un moderator de contenido, no es un filtro de toxicidad. Es un **authorization gate binario** sobre dos flags de producto: `copilot_mode` y `autopilot_premium_enabled`.

## 2. Reglas que enforce (árbol de decisión)

Orden de evaluación en `check_send_permission()`:

| # | Condición | Decisión | Log emitido |
|---|-----------|----------|-------------|
| R1 | `approved == True` | ✅ PASS (return True) | Ninguno |
| R2 | `creator not found` en DB (por `Creator.name`) | ❌ BLOCK (`raise SendBlocked`) | `logger.critical [BLOCKED AUTO-SEND] Creator not found` |
| R3 | `creator.copilot_mode == False ∧ creator.autopilot_premium_enabled == True` | ✅ PASS (return True) | `logger.info [AUTOPILOT] Send allowed` |
| R4 | cualquier otro caso | ❌ BLOCK (`raise SendBlocked`) | `logger.critical [BLOCKED AUTO-SEND]` con flags |

### 2.1 Significado de los flags

- **`approved=True`** (argumento al call): el mensaje fue aprobado explícitamente en dashboard (copilot pill `"approved"` o `"edited"`), o fue enviado por el creator en modo manual. Es la vía **humana**.
- **`copilot_mode=False`** (columna en tabla `creators`): el creator NO está en copilot review-mode; está en modo pasivo (no revisa cada mensaje).
- **`autopilot_premium_enabled=True`** (columna en tabla `creators`): el creator pagó el feature premium de autopilot total. Es la vía **automatizada**.

**Solo las dos vías pasan.** Cualquier combinación intermedia (`copilot_mode=True` pero sin aprobar; `autopilot_premium=False`; creator inexistente; DB caída → excepción arriba del finally) termina en `SendBlocked`.

### 2.2 Observación: `copilot_mode=True` siempre bloquea si `approved=False`

Esto es **intencional**. Si el creator está en copilot review-mode (`copilot_mode=True`), cada mensaje debe pasar por el dashboard y ser aprobado o editado antes de salir. No hay "atajo" premium que salte la revisión. El premium autopilot **requiere apagar el copilot** explícitamente (`copilot_mode=False`) para que el par AND active.

## 3. Valor aportado al producto

**V1 — Integridad legal:** previene que un mensaje generado por IA salga al teléfono/DM de un usuario final **sin consentimiento explícito** del creator. En jurisdicciones con regulación sobre automated messaging (GDPR, LOPDGDD, FTC Endorsement Guides, TCPA en EE.UU.), enviar en nombre de un creator sin su autorización es **suplantación** y **riesgo de sanción directa** (multas hasta 20M€ o 4% facturación global para GDPR; USD 500-1500 por mensaje TCPA).

**V2 — Confianza del producto:** un incidente de "el bot envió X sin que yo lo viese" destruye la relación comercial con el creator. Clonnect vende a influencers cuya reputación es su activo principal — un mensaje off-brand, prematuro o inapropiado enviado sin revisión puede liquidar la carrera del creator. El guard es la última línea antes de esa catástrofe.

**V3 — Defensa en profundidad:** en un sistema con 23+ scheduled jobs (handlers.py), múltiples paths async, retry queues, webhooks reentry, y tres modos de generación (pool responses, LLM, few-shot), existen **decenas** de maneras accidentales de disparar un envío. El guard es el **único punto único** que todas esas rutas atraviesan antes de tocar el network. Sin él, la correctitud del sistema depende de que cada path individual recuerde comprobar los flags — inviable.

**V4 — Auditabilidad (aspiracional):** cada bloqueo produce un log `critical` estructurado con `creator_id`, `caller`, y las dos flags. En principio permite reconstruir forensics de cualquier blocked-send event. En la práctica (ver Fase 3), la calidad del log es pobre (string interpolado, sin JSON, sin métrica) y la observabilidad es subdesarrollada.

## 4. Pipeline phase donde interviene

A diferencia del resto del sistema forense, SendGuard **no interviene en generación** (no toca el LLM, no toca el contenido, no toca el prompt). Opera en **SEND-TIME**, la última fase antes del POST a plataforma:

```
[webhook_receive] → [debounce] → [context_build] → [intent] → [llm_generation]
  → [guardrails] → [post_process]
  → [copilot_queue]           ← mensaje en dashboard, esperando pill "approve/edit/reject"
  → [send]
      ↓
  [check_send_permission]      ← SEND_GUARD AQUÍ, última barrera
      ↓ (OK)
  [platform_adapter.send]      ← POST a IG/TG/WA/Evolution
```

Si el call falla con `SendBlocked`, el adapter debe **abortar el send** y **no tocar el network**. La contracto convencional es: *el guard dice "no" → el adapter retorna False (o `{"blocked": True}`) sin retry*.

**No hay retry sobre SendGuard.** El bloqueo es definitivo para ese intento. Si cambia el estado (approved pasa a True, premium se activa), la próxima invocación puede pasar.

## 5. Los 6 callsites simétricos

El plan lista **5 callsites** pero un grep exhaustivo revela **6 reales**:

| # | Adapter | Archivo | Línea | `caller` string |
|---|---------|---------|-------|-----------------|
| C1 | Telegram | `core/telegram_adapter.py` | 568-572 | `"tg_adapter.send_message"` |
| C2 | Instagram | `core/instagram_modules/message_sender.py` | 29-33 | `"ig_handler.send_response"` |
| C3 | Copilot multiplex | `core/copilot/messaging.py` | 22-27 | `"copilot_service"` |
| C4 | WhatsApp (handler) | `core/whatsapp/handler.py` | 348-352 | `"wa_handler.send_response"` |
| C5 | Evolution API (**text**) | `services/evolution_api.py` | 56-61 | `"evolution_api"` |
| **C6** | **Evolution API (media)** | `services/evolution_api.py` | **174-179** | `"evolution_api.send_media"` |

### 5.1 Patrón de integración (casi) idéntico

Los 6 siguen un patrón muy similar: `import` lazy dentro del método para evitar ciclos, `try/except SendBlocked`, return neutral en caso de bloqueo. Pero hay **dos familias** de retorno:

| Familia | Callsites | Return en bloqueo |
|---------|-----------|-------------------|
| Boolean | C1, C2, C4 | `return False` (información perdida: por qué se bloqueó) |
| Dict estructurado | C3, C5, C6 | `return {"blocked": True, "error": str(e) or msg}` |

C3 y C5 incluyen `"blocked": True` explícito; C6 replica la forma de C5. C1/C2/C4 solo devuelven `False`, lo que es **indistinguible** de un fallo network/auth en el upstream.

### 5.2 Cadena Copilot → Evolution doble-guard (WhatsApp)

Caso real verificado: mensaje aprobado en copilot dashboard → `copilot_service` (C3) pasa el guard → `_send_whatsapp_message` (`copilot/messaging.py:142`) → llama a `send_evolution_message` (C5) con `approved=True` **hardcoded** en `messaging.py:167`. En este path el guard se ejecuta **2 veces** para el mismo mensaje.

**Importante: NO es C3→C4.** El camino copilot-→-WhatsApp nunca toca C4 (`wa_handler.send_response`). C4 solo se activa en el path webhook autopilot → handler. C3 despacha a sub-funciones propias (`_send_whatsapp_message`) que crean sus propios connectors o llaman directamente a `send_evolution_message`.

**Coste real del doble-guard en path approved:**
- **0 DB queries** — ambos guards cortocircuitan en R1 (`if approved: return True`) antes de abrir `SessionLocal()`. Mi estimación previa de "2x DB queries" era incorrecta.
- **0 logs útiles** — R1 no emite log (silent pass), así que en el path feliz no hay rastro ni en C3 ni en C5. Gap de observabilidad (ver Phase 3).

**Riesgos reales del doble-guard:**

1. **Veredicto: defense-in-depth intencional, con caveat.** El pattern "cada adapter entry-point tiene su guard" cubre callers no-copilot que llamen directo a `send_evolution_message` (scheduled jobs, nurturing retry, scripts). Para ellos C5 es meaningful.

2. **Caveat Phase 3 bug candidate:** `messaging.py:167` hardcodea `approved=True` en vez de propagar `copilot_action` real. Esto convierte C5 en **no-op** para el path C3→C5 — C5 confía ciegamente en lo que C3 ya validó. Un bug o mutación que force `approved=True` upstream pasaría C5 sin re-validar Creator flags. Alternativa más paranoica: propagar `copilot_action` downstream y re-computar `approved` en cada nivel, o re-verificar flags Creator independientemente en C5.

3. **Race window mínimo pero existente:** si creator revoca consentimiento entre C3 (t=0) y POST real (t≈100ms), C5 no re-valida — recibe `approved=True` fijo. Revocación no honrada en ese window. Bajo riesgo en práctica (llamadas síncronas/inline en el mismo async task).

4. **Lectura Creator fresh por guard (no cache):** cada `check_send_permission()` abre `SessionLocal()` propio. En path NO-approved (R3/R4), 2 SELECTs independientes sin consistency guarantee entre ellos. Si flags cambian entre C3 y C5 (race), una pasa y la otra bloquea → mensaje a mitad de camino.

## 6. Dimensiones impactadas

**NO CCEE.** SendGuard no cambia ninguna dimensión de CCEE v5 — no toca contenido, tono, estilo, persona. Está fuera del scope del eval conversacional.

**SÍ impacta compliance/safety metrics** (fuera del harness CCEE):

| Dim | Nombre | Mecanismo | Target |
|-----|--------|-----------|--------|
| **CMP-1** | Unauthorized send rate | % de mensajes enviados sin `approved∨premium` | **0** (debe ser exactamente cero) |
| **CMP-2** | Block → log coverage | % de bloqueos que generan log `critical` | 100% |
| **CMP-3** | Block → metric coverage | % de bloqueos que incrementan Prometheus counter | **0% hoy** → 100% post-Phase 5 |
| **CMP-4** | Callsite symmetry | Fraction of adapters con el mismo contrato de retorno | 3/6 → 6/6 |
| **CMP-5** | Auditability per incident | Tiempo para reconstruir forensics de un send inesperado | O(min) con métrica+logs estructurados; O(h) con logs string-interpolados |

### 6.1 Nota sobre el criterio de éxito

En los demás sistemas forensesos, éxito = subir score CCEE. En SendGuard, **éxito = cero falsos negativos** (ningún envío no autorizado pasa) y **mínimos falsos positivos** (bloqueo cuando el estado legítimamente permite enviar, p.ej. por race de flags). La asimetría de costes es extrema: un falso negativo = incidente legal; un falso positivo = mensaje no enviado (usuario reintenta o log se investiga). El sistema **debe priorizar bloquear de más**.

## 7. Inputs y outputs (interface)

**Signature:**

```python
def check_send_permission(
    creator_id: str,
    approved: bool = False,
    caller: str = "unknown",
) -> bool
```

**Inputs:**

| Parámetro | Tipo | Default | Validación | Origen |
|-----------|------|---------|------------|--------|
| `creator_id` | `str` | obligatorio | **ninguna** — acepta `""`, `None` coerced, strings inválidos | `self.creator_id` del adapter (C1/C2/C4), `creator.name` en C3, `_resolve_creator_from_instance(instance)` en C5/C6 |
| `approved` | `bool` | `False` (fail-closed) | ninguna — acepta `None` (falsy → False) | `copilot_action in ("approved","edited")` en C3; hardcoded false/true en los otros |
| `caller` | `str` | `"unknown"` | **ninguna** — magic default oculta origen | string literal por callsite |

**Output:**

- `True` si pasa (vía R1 o R3)
- `raise SendBlocked(str)` si bloquea (R2 o R4)
- **Nunca retorna False** — el bloqueo es siempre vía excepción

**Efectos secundarios:**

1. **DB query** (en ruta no-approved): `SELECT * FROM creators WHERE name = :creator_id LIMIT 1` con session fresca `SessionLocal()` (no pooleada con la request).
2. **Logs**:
   - `logger.critical` en R2 y R4 (bloqueo)
   - `logger.info` en R3 (paso por autopilot premium)
   - **Ningún log en R1** (approved silencioso) — pierde auditoría
3. **Ninguna métrica** emitida (gap a resolver en Phase 5).

## 8. Madurez operacional (snapshot hoy)

| Aspecto | Estado | Gap |
|---------|--------|-----|
| Tests | 1 test import-only en `mega_test_auto.py:677-689` (3 asserts triviales) | **No hay tests de reglas fail-closed, no hay tests de simetría entre callsites, no hay tests de race conditions** |
| Cobertura | 0% real (los 3 asserts solo comprueban importabilidad y return) | Necesario: 10+ unit + 6 integration (uno por callsite) |
| Métricas Prometheus | 0 | `send_guard_blocked_total{reason, adapter, caller}` + `send_guard_allowed_total{path, adapter}` |
| Logs estructurados | String interpolado `f"..."` sin JSON | JSON/extra{} con `creator_id`, `caller`, `reason`, `decision`, `copilot_mode`, `autopilot_premium` |
| Feature flag | ninguno (correcto: apagarlo = incidente) | Añadir `SEND_GUARD_AUDIT_ONLY=false` (default) para permitir test-harness scoped sin bloquear |
| Simetría callsites | 3/6 boolean, 3/6 dict | Unificar a un contrato (`SendDecision` dataclass) |
| Bypass paths | revisar si algún path envía sin importar `send_guard` | Phase 2 (forensic crosscheck) |
| Race conditions | DB read per call, sin caché; cambios mid-request posibles | Documentar, aceptar o mitigar |

## 9. Criticidad operativa

**Fail mode si el módulo se rompe:**
- **ImportError** al cargar `send_guard`: los 6 adapters no pueden hacer import lazy → `send_response` retorna `False` silencioso (o levanta) → **cero envíos** hasta el fix. Es un fail-closed global aceptable (outage de producto, no incidente legal).
- **DB caída** durante check: `session.query(...)` levanta → sale del `finally` sin capturar → propaga up → adapter captura o no (inconsistente entre callsites). **Riesgo**: si el adapter captura `Exception` genérico y retorna True por default → fail-open accidental. **Revisar en Phase 2**.
- **Creator row borrada** mientras running: R2 bloquea por `creator not found`. Correcto.
- **Flags cambiadas mid-request**: leído por primera vez aquí, con SessionLocal fresca. Cualquier commit que toca `copilot_mode` o `autopilot_premium_enabled` fuera de la transacción actual es visible. No hay lock. Aceptar.

---

## Resumen ejecutivo Fase 1

- `send_guard` es la **única barrera fail-closed** de autorización de envío en Clonnect. Última línea antes de POST a red.
- **6 callsites reales** (plan decía 5; evolution_api tiene send-text + send-media, ambos guardados).
- **2 vías de paso**: (i) `approved=True` desde dashboard/creator-manual, (ii) `copilot_mode=False ∧ autopilot_premium_enabled=True` desde flags del creator.
- **Todo lo demás bloquea**: creator not found, flags intermedios, default args — cualquier ambigüedad → `SendBlocked`.
- **Impacto**: no-CCEE (no toca contenido). Mueve métricas de **compliance/safety**: unauthorized-send rate, block log coverage, metric coverage, callsite symmetry, auditabilidad.
- **Criticidad legal**: alta. Un bypass = incidente GDPR/TCPA/reputacional potencialmente terminal. Apagar este módulo = incidente inmediato.
- **Madurez operacional baja**: 1 test import-only, 0 métricas, logs string, 2 familias de contrato de retorno entre callsites.
- **Criterio de éxito del branch forense**: cero falsos negativos (fail-closed intacto), mejor observabilidad (métrica + logs JSON), test suite que demuestre simetría y cobertura edge-cases.

**STOP Fase 1.** Aguardo confirmación para proceder a Fase 2.
