# Fase 3 — Bugs detectados en `send_guard` y callsites

**Artefacto:** `backend/core/send_guard.py` y callsites productivos (6) + bypass paths (4)
**Fecha:** 2026-04-23
**Branch:** `forensic/send-guard-20260423`
**Método:** cross-check Fase 1 + Fase 2, `git blame` por SHA, severidad asignada por el usuario.

**Total bugs documentados:** 15 (2 CRÍTICOS, 4 ALTOS, 5 MEDIOS, 3 BAJOS, 1 MEJORA ESTRUCTURAL).

---

## Índice de severidad

| # | Bug | Severidad | Archivo | Línea | Commit origen |
|---|-----|-----------|---------|-------|---------------|
| BUG-01 | Autopilot WA webhook bypass (B2) | **CRÍTICA** | `api/routers/messaging_webhooks/whatsapp_webhook.py` | 194-210 | `970597d7` |
| BUG-02 | Creator.name no-unique cross-tenant risk (L54) | **CRÍTICA** | `core/send_guard.py` | 54 | `e2713c6e` |
| BUG-03 | Truthiness `copilot_mode=None` legacy (L63) | **ALTA** | `core/send_guard.py` | 63 | `e2713c6e` |
| BUG-04 | Sync-in-async pool exhaustion (L52) | **ALTA** | `core/send_guard.py` | 52 | `e2713c6e` |
| BUG-05 | Manual WA Cloud fallback bypass (B1) | **ALTA** | `api/routers/dm/processing.py` | 172-173 | `ee4aabe7` |
| BUG-06 | R1 approved-path sin log (L45) | **ALTA** | `core/send_guard.py` | 45-46 | `e2713c6e` |
| BUG-07 | `send_template` sin guard (B3) | MEDIA | `core/whatsapp/handler.py` | 375-397 | `27b8a7af` |
| BUG-08 | `send_message_with_buttons` sin guard (B4) | MEDIA | `core/instagram_modules/message_sender.py` | 86-122 | `199f85b3` |
| BUG-09 | Retry queue `approved=True` hardcoded (W1) | MEDIA | `services/meta_retry_queue.py` | 184 | `e2713c6e` |
| BUG-10 | Multiplex copilot `approved=True` trust propagation (W2) | MEDIA | `core/copilot/messaging.py` | 167 | `a941ee9f` |
| BUG-11 | 6 callsites con 2 familias de retorno | MEDIA | 6 archivos callsite | var. | var. |
| BUG-12 | Tests ~0% cobertura funcional | MEDIA | `tests/` | — | — |
| BUG-13 | `caller="unknown"` magic default (L28) | BAJA | `core/send_guard.py` | 28 | `e2713c6e` |
| BUG-14 | `-> bool` retorno engañoso (L29) | BAJA | `core/send_guard.py` | 29 | `e2713c6e` |
| BUG-15 | `SendGuard` class dead code (L83-L87) | BAJA | `core/send_guard.py` | 83-87 | `7d49b663` |

---

## BUG-01 — Autopilot WhatsApp webhook bypass (B2)

**Severidad:** 🔴 **CRÍTICA**
**Archivo:** `backend/api/routers/messaging_webhooks/whatsapp_webhook.py:194-210`
**Commit origen:** `970597d7` — manel bertran luque, 2026-02-25 11:39 (6 días después de crear `send_guard`, sin integrarlo aquí).
**Tipo:** Bypass de barrera fail-closed.

**Código afectado:**
```python
189:     else:
190:         # AUTOPILOT MODE - send response via WhatsApp
191:         logger.info("[WA] AUTOPILOT MODE - sending auto-reply")
192:         sent = False
193:
194:         if bot_reply and wa_token and wa_phone_id:
195:             try:
196:                 send_connector = WhatsAppConnector(
197:                     phone_number_id=wa_phone_id,
198:                     access_token=wa_token,
199:                 )
200:                 send_result = await send_connector.send_message(
201:                     message.sender_id, bot_reply
202:                 )
203:                 await send_connector.close()
204:                 ...
```

**Descripción:** El webhook handler de WhatsApp, cuando el modo copilot está OFF (`copilot_enabled=False` según `_get_copilot_mode_cached`, L148), entra en **rama AUTOPILOT** y crea un `WhatsAppConnector` ad-hoc, invocando `.send_message` **sin pasar por `check_send_permission`**. El único "gate" upstream es la función cacheada `_get_copilot_mode_cached` que **únicamente lee `copilot_mode`** y **NO verifica `autopilot_premium_enabled`**.

**Consecuencia (¿por qué es crítica?):**
- Un creator con `copilot_mode=False` pero `autopilot_premium_enabled=False` (i.e. no ha pagado el premium) **envía mensajes autopilot igualmente** por este path. La regla R3 del guard (`premium AND ¬copilot`) se está violando silenciosamente.
- Si la cache está stale (`copilot_mode` recién cambiado a `True` pero cache no invalidada), el mensaje sale antes de que la nueva preferencia se aplique.
- **Esto es exactamente el escenario de incidente legal que el guard fue creado para prevenir** (commit `e2713c6e` message: "safety guard — autopilot only via dashboard + premium flag"). Seis días después se añadió un path que lo elude.

**Pasos de reproducción:**
1. Crear creator `test_bypass` con `copilot_mode=False, autopilot_premium_enabled=False` en DB (`UPDATE creators SET copilot_mode=false, autopilot_premium_enabled=false WHERE name='test_bypass'`).
2. Configurar WhatsApp webhook para este creator (wa_token, wa_phone_id).
3. Enviar un mensaje WhatsApp inbound al número del creator (trigger el webhook).
4. Observar: el bot genera una respuesta y ejecuta L200 `send_connector.send_message(...)` → envío.
5. Buscar `[BLOCKED AUTO-SEND]` en logs → **no aparece** (guard no se invoca).
6. Confirmar: `grep AUTOPILOT MODE - sending auto-reply` ✅; `grep BLOCKED` ✗.

**Expected vs Actual:**
- Expected: R3 falla (premium=False) → `SendBlocked` → mensaje NO sale.
- Actual: mensaje sale sin comprobación.

**Fix propuesto (Phase 5):**
```python
# Insertar antes de L196 (creación del connector):
from core.send_guard import SendBlocked, check_send_permission

try:
    check_send_permission(
        creator_id,
        approved=False,
        caller="wa_webhook.autopilot",
    )
except SendBlocked as e:
    logger.critical(
        f"[WA] AUTOPILOT blocked by send_guard: {e}",
        extra={"creator_id": creator_id, "sender_id": message.sender_id},
    )
    results.append({
        "message_id": message.message_id,
        "sender_id": message.sender_id,
        "error": f"blocked: {e}",
        "blocked": True,
    })
    continue  # or equivalent loop-skip
```

**Coste:** +1 DB query por webhook autopilot (indexada, ~1ms). Rompe ningún contrato existente — solo añade check nuevo. Test de regresión trivial (mock creator sin premium → assert no send).

**Alternativa:** redirigir la rama autopilot a `wa_handler.send_response(recipient, text, approved=False)` (C4) que ya guarda — elimina duplicación de lógica. Coste: refactor más extenso.

---

## BUG-02 — `Creator.name` no-unique cross-tenant risk (L54)

**Severidad:** 🔴 **CRÍTICA** (probabilidad baja × impacto extremo)
**Archivo:** `backend/core/send_guard.py:54`
**Commit origen:** `e2713c6e` (creación del módulo, 2026-02-19)

**Código afectado:**
```python
54:         creator = session.query(Creator).filter_by(name=creator_id).first()
```

**Descripción:** El guard resuelve el creator por `Creator.name` (indexado pero **NO UNIQUE**, verificado en `api/models/creator.py:33`). Si dos rows de `creators` comparten `name` (colisión de slug, seed duplicado, bug de migración), `first()` devuelve **el primero arbitrario** (ORDER BY no especificado, comportamiento depende del planner PostgreSQL — típicamente ORDER BY `ctid` o `id`).

**Consecuencia:**
- **Evaluación de flags sobre el creator equivocado**: si creator A tiene `autopilot_premium=False` (bloqueado) pero otro row "homonymous" B tiene `autopilot_premium=True`, el `first()` devuelve B → R3 pasa → envío autorizado con flags de B **para un mensaje del lead de A**.
- **Cross-tenant consent leak**: un creator puede terminar enviando mensajes de otro creator sin su permiso.
- **Probabilidad**: baja en producción (slugs únicos por onboarding), pero NO cero: un seed script malo, un test fixture que sobrevive a migration, un merge de datos de dos entornos... → colisión.
- **Invariante no enforced**: no hay constraint DB ni check aplicativo que prevenga la colisión.

**Pasos de reproducción:**
1. Crear dos rows duplicadas: `INSERT INTO creators (name, copilot_mode, autopilot_premium_enabled) VALUES ('dup_creator', true, false), ('dup_creator', false, true);`
2. Llamar `check_send_permission("dup_creator", approved=False, caller="test")`.
3. Resultado: R3 pasa (por el row "dup_creator" con premium=True) → log `[AUTOPILOT] Send allowed` incluso si se pretendía enviar por el creator con premium=False.
4. Verificar: `select copilot_mode, autopilot_premium_enabled from creators where name='dup_creator'` — dos rows con distintos flags.

**Expected vs Actual:**
- Expected: fallo determinista o error (IntegrityError si UNIQUE, `MultipleResultsFound` si `.one()`, o explicit `raise`).
- Actual: evaluación silenciosa sobre row aleatorio → consent leak posible.

**Fix propuesto (Phase 5):**

Opción A — **Reparar schema + app**:
1. Migración Alembic: `ALTER TABLE creators ADD CONSTRAINT creators_name_key UNIQUE (name);` (si hay duplicados pre-existentes, la migración fallará y obliga a limpieza manual antes).
2. Cambiar `.first()` por `.one_or_none()` en L54; mantener R2 para el caso sin match.

Opción B — **Solo app** (si no se puede migrar DB):
1. Cambiar `.first()` por `.all()`; si `len(creators) > 1`: `logger.critical(f"[BUG-02] Duplicate creator.name={creator_id} — {len(creators)} rows")` → **raise SendBlocked** (fail-closed ante ambigüedad).

Recomendación: **Opción A** — el schema debe defender el invariante. Riesgo de migración: si hay legacy duplicates, bloquea el deploy hasta cleanup. Correcto.

**Coste:** migración + cleanup; estimated 1h.

---

## BUG-03 — Truthiness `copilot_mode=None` legacy (L63)

**Severidad:** 🟠 **ALTA**
**Archivo:** `backend/core/send_guard.py:63`
**Commit origen:** `e2713c6e` (creación del módulo, 2026-02-19)

**Código afectado:**
```python
62:         # Autopilot requires BOTH flags
63:         if not creator.copilot_mode and creator.autopilot_premium_enabled:
```

**Descripción:** La condición es truthy-based (`not x and y`). La columna `copilot_mode` tiene `default=True` pero **no tiene `nullable=False`** en el modelo (`api/models/creator.py:91`). Filas legacy anteriores a la añadidura de la columna pueden tener `copilot_mode=None`. La lógica `not None == True` → primera mitad del AND pasa; si `autopilot_premium_enabled=True`, R3 da PASS.

**Consecuencia:**
- Creators con `copilot_mode=None` (no configurado explícitamente) son tratados como "no-copilot" → si tienen `autopilot_premium_enabled=True`, envían autopilot automáticamente sin que el creator haya tomado la decisión.
- Semánticamente ambiguo: `None` != `False`. El creator puede haber nunca visto el toggle del dashboard y aún así el bot envía.
- **Invariante esperado violado**: R3 dice "copilot_mode=False AND autopilot_premium=True". En la práctica, el código acepta también `copilot_mode=None AND autopilot_premium=True`.

**Pasos de reproducción:**
1. Crear row legacy sin copilot_mode: `UPDATE creators SET copilot_mode=NULL, autopilot_premium_enabled=true WHERE name='legacy_test';` (simula pre-migration state).
2. Llamar `check_send_permission("legacy_test", approved=False, caller="test")`.
3. Resultado: R3 pasa → return True → log `[AUTOPILOT] Send allowed for legacy_test`.
4. Verificar: `select copilot_mode from creators where name='legacy_test'` → `NULL`.

**Expected vs Actual:**
- Expected: fallo explícito (R4 block) si `copilot_mode is None` porque el creator no ha configurado su modo.
- Actual: R3 pasa silenciosamente.

**Fix propuesto (Phase 5):**
```python
# En send_guard.py:63:
if creator.copilot_mode is False and creator.autopilot_premium_enabled is True:
```

Cambios:
- `not creator.copilot_mode` → `creator.copilot_mode is False` (explícito, rechaza None).
- `creator.autopilot_premium_enabled` → `creator.autopilot_premium_enabled is True` (defensivo aunque columna sea nullable=False).

Adicional: backfill migration para `UPDATE creators SET copilot_mode = COALESCE(copilot_mode, true) WHERE copilot_mode IS NULL;` + `ALTER TABLE creators ALTER COLUMN copilot_mode SET NOT NULL;`.

**Coste:** cambio de 1 línea + migración trivial. Test regresión: crear 3 rows (None/True/False × premium), assert comportamiento.

---

## BUG-04 — Sync-in-async pool exhaustion (L52)

**Severidad:** 🟠 **ALTA**
**Archivo:** `backend/core/send_guard.py:52-54, 79-80`
**Commit origen:** `e2713c6e` (creación del módulo, 2026-02-19)

**Código afectado:**
```python
52:     session = SessionLocal()
53:     try:
54:         creator = session.query(Creator).filter_by(name=creator_id).first()
...
79:     finally:
80:         session.close()
```

**Descripción:** `check_send_permission` es función **síncrona** que abre `SessionLocal()` y hace SELECT síncrono. Es llamada desde contextos `async` en **todos los 6 callsites** (`await` en la función caller async). Si el pool está exhausto (Neon+pgbouncer, 5 base + 7 overflow = 12 conexiones), `SessionLocal()` bloquea hasta `pool_timeout` (default SQLAlchemy = 30s). Durante ese bloqueo, **el event loop async se queda parado** porque la función no hace `await` ni `asyncio.to_thread`.

**Consecuencia:**
- Bajo carga (scoring batch runs at t+210s — documentado en MEMORY.md como causante histórico de pool exhaustion), un envío autopilot o copilot-approved puede hogear el loop hasta 30s.
- Cada envío que toca R3/R4 paths (no-approved) abre una nueva sesión → 6 callsites × N concurrent requests = presión sobre pool.
- **Ataque DoS**: muchas requests simultáneas forcing guard (e.g. burst de webhooks no-approved) pueden reventar el pool (tested históricamente en scoring batch).
- Degradación silenciosa: no hay alerta cuando el guard está bloqueando, solo timeouts en la request upstream.

**Pasos de reproducción:**
1. Reducir `pool_size=1, max_overflow=0` en `api/database.py` (solo para test).
2. Mantener una request que hold un connection (e.g. `select pg_sleep(60)` en otra sesión).
3. Ejecutar `await handler.send_response(recipient, text, approved=False)` (fuerza no-approved path).
4. Observar: la invocación a `check_send_permission` bloquea hasta `pool_timeout`; el event loop parado en ese intervalo.
5. Simultáneamente, otras corutinas del mismo proceso reciben delays medibles en sus `await`s.

**Expected vs Actual:**
- Expected: el guard no debería contender sobre recursos compartidos; idealmente usa `asyncio.to_thread(...)` o es nativamente async.
- Actual: sync DB en contexto async → blocking.

**Fix propuesto (Phase 5):**

Opción A — **Envolver en `asyncio.to_thread`** en cada callsite:
```python
from asyncio import to_thread
await to_thread(check_send_permission, creator_id, approved=approved, caller="...")
```
Problema: requiere cambiar los 6 callsites; propenso a omisiones. Patch.

Opción B — **Introducir `check_send_permission_async`** (recomendado):
```python
async def check_send_permission_async(
    creator_id: str, approved: bool = False, caller: str = "unknown"
) -> bool:
    from asyncio import to_thread
    return await to_thread(check_send_permission, creator_id, approved=approved, caller=caller)
```
Callsites async usan la versión async; callsites sync (si los hay en scripts/CLI) usan la sync. Documentar en docstring.

Opción C — **Refactor a async nativo** usando `async_session` de SQLAlchemy: mejor solución pero requiere cambios en `api/database.py` (async engine), fuera del scope forense simple.

**Recomendación:** Opción B (nueva función async, patch local, callsites migran progresivamente).

**Coste:** +10 LOC en send_guard; migración de 6 callsites a la versión async.

---

## BUG-05 — Manual WA Cloud fallback bypass (B1)

**Severidad:** 🟠 **ALTA**
**Archivo:** `backend/api/routers/dm/processing.py:170-173`
**Commit origen:** `ee4aabe7` — manel bertran luque, 2026-02-25 11:58 (6 días después del commit del guard, sin integrarlo).

**Código afectado:**
```python
170:     # Fall back to official WhatsApp Cloud API
171:     wa_handler = get_whatsapp_handler()
172:     if wa_handler and wa_handler.connector:
173:         result = await wa_handler.connector.send_message(phone, message_text)
174:         sent = "error" not in result
```

**Descripción:** En el endpoint **manual-send** del dashboard (creator escribe manualmente y envía), cuando el platform es WhatsApp y NO hay Evolution instance configurada, cae al fallback Cloud API. Este fallback **llama a `wa_handler.connector.send_message` directamente**, bypassando `wa_handler.send_response` (C4) que contiene el guard.

**Consecuencia:**
- El dashboard manual-send es creator-initiated (implícitamente approved), pero el guard es la red de seguridad **precisamente** para cuando lógica upstream falle (auth bug, session hijack, broken endpoint). Sin la llamada al guard, un bug en el endpoint podría disparar sends sin consent.
- Asimetría con el path Evolution (L165) que sí pasa `approved=True` a `send_evolution_message` (C5) — ese path sí está guardado.
- **Incentivo perverso**: la ausencia del guard comunica implícitamente "este path no necesita validación" → futuros devs copian el pattern.

**Pasos de reproducción:**
1. Creator `test_wa` con `whatsapp_token` y `whatsapp_phone_id` configurados, sin Evolution instance en `EVOLUTION_INSTANCE_MAP`.
2. Vía dashboard, POST `/dm/send_manual` con `follower_id="wa_34612345678"`.
3. Path ejecuta L151 (whatsapp) → no encuentra `evo_instance` → L172 Cloud API fallback → L173 connector directo.
4. Verificar logs: no aparece `[BLOCKED AUTO-SEND]` ni `[AUTOPILOT]` ni ningún rastro del guard.

**Expected vs Actual:**
- Expected: aunque el dashboard sea la fuente, el guard debería verificar (aunque pase trivialmente por R1 con `approved=True`) para mantener auditabilidad.
- Actual: la llamada no pasa por el guard en absoluto.

**Fix propuesto (Phase 5):**
```python
# Reemplazar L172-174 por:
from core.send_guard import SendBlocked, check_send_permission

if wa_handler and wa_handler.connector:
    try:
        check_send_permission(creator_id, approved=True, caller="dm.manual_send.wa_cloud_fallback")
    except SendBlocked as e:
        logger.error(f"Manual WA send blocked: {e}")
        return {"status": "error", "sent": False, "blocked": True}

    result = await wa_handler.connector.send_message(phone, message_text)
    sent = "error" not in result
```

Alternativa ideal (Phase 5 refactor): reemplazar `wa_handler.connector.send_message(...)` por `wa_handler.send_response(phone, message_text, approved=True)` → elimina duplicación y pasa por C4. Menos coste pero requiere verificar que `send_response` hace el mismo trabajo que el connector directo.

**Coste:** 5 LOC, sin cambios de contrato. Test: mock creator deleted → assert manual send returns blocked.

---

## BUG-06 — R1 approved-path sin log (80-90% invisible)

**Severidad:** 🟠 **ALTA**
**Archivo:** `backend/core/send_guard.py:45-46`
**Commit origen:** `e2713c6e` (creación del módulo, 2026-02-19)

**Código afectado:**
```python
44:     # Pre-approved messages always pass
45:     if approved:
46:         return True
```

**Descripción:** El path R1 (`approved=True`) es **silencioso** — no emite ningún log. En producción, **la mayoría de los envíos** (80-90% según el paradigma copilot por defecto) son approved (creator click "approve" pill en dashboard). Ninguno de estos deja rastro que el guard se ejecutó.

**Consecuencia:**
- **Auditoría pobre**: no hay forma de responder "demuéstrame que cada mensaje enviado pasó por el guard" sin correlacionar indirectamente logs del adapter. Para un compliance officer o un peritaje legal post-incidente, esto es un gap documental.
- **Telemetría ciega**: la métrica "tasa de uso del guard" no puede calcularse. Solo sabemos cuántos bloqueos hubo (via `[BLOCKED AUTO-SEND]` grep), no el denominador total.
- **Imposible detectar drift** en el tipo de paths: si alguien accidentalmente introduce un bypass y los counters de approved bajan 10%, no nos enteramos porque no los contamos.

**Pasos de reproducción:**
1. Configurar el log level en DEBUG.
2. Llamar `check_send_permission("iris_bertran", approved=True, caller="test")`.
3. Resultado: retorna True silenciosamente.
4. Verificar: `grep send_guard /var/log/clonnect` — vacío (para el approved path).

**Expected vs Actual:**
- Expected: cada decisión del guard deja rastro machine-greppable y/o incrementa métrica.
- Actual: solo los paths R3 (info) y R2/R4 (critical) logean. R1 es silencioso.

**Fix propuesto (Phase 5):**

Opción A — **Log `debug` en R1**:
```python
if approved:
    logger.debug(
        f"[SEND_ALLOWED] creator={creator_id} caller={caller} reason=approved"
    )
    return True
```
Usa nivel `debug` para no saturar Railway logs con el 80-90%. En prod se puede elevar a `info` para staging y a `debug` para prod. Trade-off coste de log vs completeness.

Opción B — **Prometheus counter (sin log)**:
```python
from prometheus_client import Counter
SEND_GUARD_ALLOWED = Counter(
    "send_guard_allowed_total",
    "Total sends allowed by send_guard",
    ["reason", "caller"]
)

if approved:
    SEND_GUARD_ALLOWED.labels(reason="approved", caller=caller).inc()
    return True
```
Coste marginal (in-memory counter), cero log spam. Permite dashboards.

Opción C — **Ambas (recomendado)**: counter siempre + log debug. Counter da telemetría; log ayuda forensics puntual.

**Coste:** +5 LOC en R1, +5 LOC en R3, +5 LOC en R2/R4. Grafana dashboard opcional.

---

## BUG-07 — `send_template` sin guard (B3)

**Severidad:** 🟡 **MEDIA**
**Archivo:** `backend/core/whatsapp/handler.py:375-397`
**Commit origen:** `27b8a7af` — 2025-12-21 (creación del módulo WhatsApp, **2 meses antes** de `send_guard`).
**Modificado:** `87ca2316` — 2026-02-07 (añadido `components` param).

**Código afectado:**
```python
375:     async def send_template(
376:         self,
377:         recipient: str,
378:         template_name: str,
379:         language_code: str = "es",
380:         components: List[dict] = None,
381:     ) -> bool:
382:         """Send a template message"""
383:         if not self.connector:
384:             return False
385:
386:         try:
387:             result = await self.connector.send_template(
388:                 recipient, template_name, language_code, components
389:             )
```

**Descripción:** `send_template` envía mensajes WhatsApp Business de tipo template (pre-aprobados por Meta, usados para notificaciones iniciales fuera de ventana de conversación). **No invoca `check_send_permission`**. Predates `send_guard.py` por 2 meses; nunca fue retrofitteado.

**Consecuencia:**
- Template messages son enviados en nombre del creator sin pasar por el guard.
- **Mitigación existente**: Meta pre-aprueba templates (contenido limitado). Pero el **acto de enviar** sigue requiriendo consent del creator.
- `grep send_template` no revela callers productivos (solo definición + test imports). Posible dead method — en tal caso, bajo impacto práctico.
- Si se re-activa (e.g. onboarding de nuevos creators envía template welcome), bypass vivo.

**Pasos de reproducción:**
1. Creator `test_tpl` con `copilot_mode=True, autopilot_premium_enabled=False`.
2. Invocar `wa_handler.send_template("34612345678", "welcome_template", "es", [])`.
3. Resultado: el template se envía (si Meta acepta) sin pasar por `check_send_permission`.
4. Verificar: no hay `[BLOCKED AUTO-SEND]` ni `[AUTOPILOT]` logs. El creator no necesita aprobar.

**Expected vs Actual:**
- Expected: paridad con `send_response` (C4) — si `send_response` guarda, `send_template` también debe.
- Actual: `send_template` bypass.

**Fix propuesto (Phase 5):**

Opción A — **Añadir guard** (simetría con C4):
```python
async def send_template(
    self,
    recipient: str,
    template_name: str,
    language_code: str = "es",
    components: List[dict] = None,
    approved: bool = False,
) -> bool:
    """Send a template message — GUARDED by send_guard."""
    from core.send_guard import SendBlocked, check_send_permission

    try:
        check_send_permission(self.creator_id, approved=approved, caller="wa_handler.send_template")
    except SendBlocked:
        return False

    if not self.connector:
        return False
    ...
```

Opción B — **Eliminar si dead code**: `grep send_template --include="*.py" backend | grep -v test | grep -v "def send_template"` para confirmar zero callers; si cero, eliminar.

**Recomendación:** A — mantener defensivo.

**Coste:** 5 LOC. Test: mock creator blocked → assert send_template returns False.

---

## BUG-08 — `send_message_with_buttons` sin guard (B4)

**Severidad:** 🟡 **MEDIA**
**Archivo:** `backend/core/instagram_modules/message_sender.py:86-122`
**Commit origen:** `199f85b3` — Claude, 2026-02-25 00:33 (6 días después del guard, sin integrarlo).

**Código afectado:**
```python
86:     async def send_message_with_buttons(
87:         self, recipient_id: str, text: str, buttons: List[Dict[str, str]]
88:     ) -> bool:
...
100:         if not self.connector:
101:             logger.error("Instagram connector not initialized")
102:             return False
...
108:         try:
109:             result = await self.connector.send_message_with_buttons(recipient_id, text, buttons)
```

**Descripción:** Método hermano de `send_response` (C2) para IG messages con quick-reply buttons. **No invoca `check_send_permission`**. Callsite conocido: `core/instagram_handler.py:316` (wrapper).

**Consecuencia:**
- Cualquier path que llame a este método envía mensajes IG con buttons sin paso por el guard.
- Probablemente se usa en flujos de quick actions (e.g. "¿Cita o info?" buttons) que podrían ser autopilot-driven sin aprobación.
- Simetría rota: `send_response` guarda; `send_message_with_buttons` no.

**Pasos de reproducción:**
1. Creator `test_btn` con `copilot_mode=True, autopilot_premium_enabled=False`.
2. Via upstream path (investigar cual), disparar `send_message_with_buttons`.
3. Resultado: IG message con buttons se envía sin guard.

**Expected vs Actual:**
- Expected: paridad con `send_response` (C2).
- Actual: bypass.

**Fix propuesto (Phase 5):**
```python
async def send_message_with_buttons(
    self, recipient_id: str, text: str, buttons: List[Dict[str, str]],
    approved: bool = False,
) -> bool:
    from core.send_guard import SendBlocked, check_send_permission

    try:
        check_send_permission(self.creator_id, approved=approved, caller="ig_handler.send_buttons")
    except SendBlocked:
        return False

    if not self.connector:
        ...
```

**Coste:** 5 LOC. Callers upstream (e.g. `instagram_handler.py:316`) deben propagar `approved` param — minor ripple.

---

## BUG-09 — Retry queue `approved=True` hardcoded (W1)

**Severidad:** 🟡 **MEDIA**
**Archivo:** `backend/services/meta_retry_queue.py:184`
**Commit origen:** `e2713c6e` — manel bertran luque, 2026-02-19 (**mismo commit** que crea `send_guard.py`: el autor modificó la retry queue en el momento de introducir el guard, hardcoding `approved=True` en el default retry path).

**Código afectado:**
```python
180:     try:
181:         from core.instagram_handler import InstagramHandler
182:
183:         handler = InstagramHandler(creator_id=item.creator_id)
184:         return await handler.send_response(item.recipient_id, item.message, approved=True)
185:     except Exception as e:
```

**Descripción:** En el fallback path del retry queue (cuando no hay `_send_fn` configurado), se crea un handler ad-hoc y se envía con `approved=True` hardcoded. El mensaje entró a la queue **porque falló un envío previo**; se asume que ese envío previo ya pasó el guard.

**Consecuencia:**
- **Trust propagation**: el retry confía en que el envío original estaba autorizado. Si flags del creator cambiaron entre el fallo y el retry (creator revocó consent), **el retry envía igualmente** — short-circuit R1.
- Además: **si el mensaje entró a la queue por una ruta que era un bypass** (BUG-01/05/07/08), el retry propaga el bypass → la queue se convierte en **backdoor** para mensajes no autorizados.
- Ventana de revocación: si creator toggled `copilot_mode=True` mientras un mensaje en queue espera retry (puede ser minutos/horas), el retry lo envía.

**Pasos de reproducción:**
1. Creator `test_retry` con `copilot_mode=False, autopilot_premium_enabled=True` — autopilot activo.
2. Triggerear envío IG que falle (ej. recipient deleted) → entra a retry queue.
3. Creator revoca: `UPDATE creators SET autopilot_premium_enabled=false WHERE name='test_retry';`.
4. Esperar retry cycle (o forzar `queue.process_queue()`).
5. Resultado: el retry invoca L184 con `approved=True` → R1 pasa → envío aunque creator ya no lo autoriza.

**Expected vs Actual:**
- Expected: retry re-evalúa flags; si ya no están autorizados, cancela y elimina de queue.
- Actual: retry pasa R1 siempre.

**Fix propuesto (Phase 5):**

Opción A — **Propagar `approved` original en el QueuedMessage**:
```python
@dataclass
class QueuedMessage:
    ...
    original_approved: bool = False  # NEW: carry through

# al encolar:
queue_failed_message(..., original_approved=was_approved)

# al reintentar (L184):
return await handler.send_response(
    item.recipient_id, item.message, approved=item.original_approved
)
```

Opción B — **Pass `approved=False` siempre en retry**: el guard re-evalúa flags del creator. Si siguen válidos → R3 pasa; si no → R4 block → retry se cancela (y el message quizás se mueve a una DLQ "cancelled_by_guard").

**Recomendación:** Opción B (más seguro — el guard siempre se re-ejecuta como control de consent actual).

**Coste:** 1 LOC en L184 (`approved=True` → `approved=False`) + handling de retornos False (drop del queue después de N intentos).

---

## BUG-10 — Multiplex copilot `approved=True` trust propagation (W2)

**Severidad:** 🟡 **MEDIA**
**Archivo:** `backend/core/copilot/messaging.py:167`
**Commit origen:** `a941ee9f` — Claude, 2026-02-25 14:43 (6 días después del guard).

**Código afectado:**
```python
165:         if evo_instance:
166:             logger.info(f"[Copilot] Sending WhatsApp via Evolution [{evo_instance}] to {recipient}")
167:             result = await send_evolution_message(evo_instance, recipient, text, approved=True)
168:             msg_id = result.get("key", {}).get("id", "")
```

**Descripción:** En el multiplexer `_send_whatsapp_message`, al bajar a `send_evolution_message` (C5), se pasa `approved=True` hardcoded. El approved real vino de C3 (`copilot_action in ("approved","edited")`) pero aquí se **hardcodea True** sin propagar el valor original.

**Consecuencia:**
- Convierte C5 en **no-op** para este path (R1 short-circuit sin validación).
- Trust propagation silenciosa: el multiplexer dice "confía en mí, ya validé arriba". Si hay bug en C3 (o un caller cambia la semántica), C5 no lo puede pillar.
- **Diseño más paranoico** (correcto para un safety guard): cada capa valida independientemente los flags en la DB.

**Pasos de reproducción:**
1. Verificar en código: `send_evolution_message(..., approved=True)` en L167 y `send_evolution_message(..., approved=approved)` no existe.
2. Si un test/mock cambia `check_send_permission` en C3 para retornar True para un creator sin flags → el envío pasa C3 → llega a L167 → C5 R1 trivial → envío.
3. En producción: un bug que force `approved=True` erróneamente en C3 se propaga sin red.

**Expected vs Actual:**
- Expected: `send_evolution_message(evo_instance, recipient, text, approved=approved_original)` — propagar valor real.
- Actual: hardcoded True.

**Fix propuesto (Phase 5):**
```python
# En messaging.py:142 send_message_impl reciba approved del caller:
async def send_message_impl(
    service, creator, lead, text: str, copilot_action: str = None
) -> Dict[str, Any]:
    approved = copilot_action in ("approved", "edited")
    try:
        check_send_permission(creator.name, approved=approved, caller="copilot_service")
    except SendBlocked as e:
        return {"success": False, "error": str(e), "blocked": True}

    # propagar approved en vez de hardcodear True
    if lead.platform == "whatsapp":
        return await _send_whatsapp_message(service, creator, lead, text, approved=approved)
    ...

async def _send_whatsapp_message(service, creator, lead, text: str, approved: bool = False):
    ...
    result = await send_evolution_message(evo_instance, recipient, text, approved=approved)  # propagado
    ...
```

**Coste:** 3 LOC + propagación por signature. Test: mock `check_send_permission` en C3 (returns True por side-effect) → test que C5 re-valida si approved=False se pasa down.

---

## BUG-11 — 6 callsites con 2 familias de retorno incompatibles

**Severidad:** 🟡 **MEDIA**
**Archivos:** los 6 callsites (ver tabla)
**Commit origen:** varios (cada callsite tiene su SHA).

**Descripción:** Los 6 callsites tienen **dos contratos de retorno** distintos ante un bloqueo del guard:

| Callsite | Retorno bloqueo | Familia |
|----------|-----------------|---------|
| C1 `tg_adapter.send_message:572` | `return False` | bool |
| C2 `ig_handler.send_response:33` | `return False` | bool |
| C3 `copilot_service.send_message_impl:27` | `{"success": False, "error": ..., "blocked": True}` | dict |
| C4 `wa_handler.send_response:352` | `return False` | bool |
| C5 `send_evolution_message:61` | `{"error": ..., "blocked": True}` | dict |
| C6 `send_evolution_media:179` | `{"error": ..., "blocked": True}` | dict |

**Consecuencia:**
- Caller de C1/C2/C4 ve `False` sin distinguir "bloqueado por guard" de "network error", "connector down", "rate limit". Para telemetría y alerting, hay que grep logs — no escalable.
- Caller de C3/C5/C6 puede distinguir vía `response["blocked"]`. Mejor, pero inconsistente.
- Tests del sistema tienen que implementar 2 patrones de assert (check bool vs check dict["blocked"]).

**Pasos de reproducción:**
1. Mock creator no existe. Ejecutar los 6 callsites.
2. Resultado: 3 retornan `False`, 3 retornan dicts. Mismo evento lógico, representaciones distintas.

**Fix propuesto (Phase 5):**

Opción A — **`SendDecision` dataclass** (canonical contract):
```python
@dataclass(frozen=True)
class SendDecision:
    sent: bool
    blocked: bool = False
    reason: Optional[str] = None
    message_id: Optional[str] = None

# Todos los callsites retornan SendDecision.
```

Opción B — **Estandarizar a dict**: todos retornan `{"sent": bool, "blocked": bool, "error": Optional[str], ...}`. Menos typing safety.

Opción C — **Mantener boolean pero añadir log extra en bloqueo explícito para distinguir**: peor que A/B.

**Recomendación:** A (dataclass frozen, typed, pickleable). Coste: migración de 6 callsites + actualización de sus callers upstream. Alto LOC pero cuantificable.

**Coste estimado:** 80-120 LOC total (dataclass + 6 callsite edits + tests).

---

## BUG-12 — Tests ~0% cobertura funcional

**Severidad:** 🟡 **MEDIA**
**Archivos:** `tests/test_motor_audit.py:535-536`, `mega_test_auto.py:677-689`
**Commit origen:** — (nunca han existido tests reales)

**Descripción:** Los únicos "tests" que tocan `send_guard` son:

1. `test_motor_audit.py:535-536`:
   ```python
   from core.send_guard import SendGuard
   assert SendGuard is not None
   ```
   **Import check. 0 asserts de lógica.**

2. `mega_test_auto.py:677-689`:
   ```python
   test("V1: SendBlocked is an Exception subclass", lambda: assert_true(issubclass(SendBlocked, Exception)))
   test("V2: check_send_permission approved=True → True", lambda: assert_true(check_send_permission("test_creator", approved=True, caller="test")))
   test("V3: check_send_permission approved=False → raises SendBlocked or returns True",
        ...)
   ```
   **3 asserts triviales:** isinstance check, R1 shortcut, R2/R3 "one of two things".

**Cobertura no cubierta:**
- R2 block por creator no-found (0 test).
- R3 pass por autopilot premium (0 test).
- R4 block por flags insuficientes (0 test).
- Edge case `copilot_mode=None` legacy (0 test).
- Simetría entre los 6 callsites (0 test).
- Bypass B1/B2/B3/B4 (0 test).
- Race conditions (0 test).
- Pool exhaustion behavior (0 test).

**Consecuencia:**
- Cualquier cambio al guard pasa sin red de seguridad. Los bugs BUG-01 a BUG-10 llegaron a producción y siguen allí porque no hay test que falle.
- Imposible garantizar que un refactor no rompe fail-closed.

**Fix propuesto (Phase 5):**

Test suite mínima:

1. **Unit tests `test_send_guard.py`** — 10+ tests:
   - R1 approved=True → returns True
   - R2 creator not in DB → raises SendBlocked
   - R3 copilot_mode=False + premium=True → returns True
   - R4 copilot_mode=True + premium=False → raises SendBlocked
   - R4 copilot_mode=False + premium=False → raises SendBlocked
   - R4 copilot_mode=True + premium=True → raises SendBlocked
   - Edge: copilot_mode=None → raises SendBlocked (post fix BUG-03)
   - Edge: creator_id="" → R2 raises
   - Edge: creator_id=None → R2 raises
   - Edge: caller default "unknown" emerge en logs (post fix BUG-13)
   - Logs: R2/R4 emit `critical`, R3 emits `info` (verify via `caplog`)
   - Métricas: counter increments (post fix BUG-06)

2. **Integration tests `test_send_guard_callsites.py`** — 6 tests:
   - C1-C6: uno por adapter, mock connector, assert que un bloqueo devuelve el retorno esperado (tras fix BUG-11 sería un `SendDecision`).
   - Simetría: assert los 6 devuelven el mismo tipo.

3. **Bypass tests** — 4 tests:
   - B1/B2/B3/B4: cada uno assert que la ruta ahora guarda (post-fix).

**Coste:** ~400 LOC de tests (unit + integ + bypass). 2-3 horas de dev.

---

## BUG-13 — `caller="unknown"` magic default (L28)

**Severidad:** 🟢 **BAJA**
**Archivo:** `backend/core/send_guard.py:28`
**Commit origen:** `e2713c6e` (creación del módulo, 2026-02-19)

**Código afectado:**
```python
25: def check_send_permission(
26:     creator_id: str,
27:     approved: bool = False,
28:     caller: str = "unknown",
29: ) -> bool:
```

**Descripción:** El parámetro `caller` tiene default `"unknown"`. Si un futuro callsite olvida pasar `caller=`, el log saldrá con `caller=unknown` y no se sabrá qué ruta lo invocó.

**Consecuencia:**
- Forensics pobres: "bloqueamos X envíos hoy, caller=unknown" → no accionable.
- Silencioso: ningún linter detecta la omisión. El default pasa.
- Actualmente los 6 callsites productivos pasan caller explícito — el bug está **latente**, no activo.

**Pasos de reproducción:**
1. `check_send_permission("test", approved=False)` (sin caller).
2. Resultado: si bloquea, log `[BLOCKED AUTO-SEND] creator=test caller=unknown`.

**Fix propuesto (Phase 5):**

Opción A — **Hacer obligatorio**:
```python
def check_send_permission(
    creator_id: str,
    *,  # kwargs-only
    approved: bool = False,
    caller: str,  # no default
) -> bool:
```

Opción B — **Validar runtime**:
```python
if caller == "unknown":
    logger.warning(f"[SEND_GUARD] caller not specified by stack: {traceback.extract_stack()[-2]}")
```

**Recomendación:** A (más estricto, falla rápido).

**Coste:** cambio de signature + update 6 callsites (ya pasan caller). Bajo riesgo.

---

## BUG-14 — `-> bool` retorno engañoso (L29)

**Severidad:** 🟢 **BAJA**
**Archivo:** `backend/core/send_guard.py:29`
**Commit origen:** `e2713c6e` (creación del módulo, 2026-02-19)

**Código afectado:**
```python
29: ) -> bool:
```

**Descripción:** La firma declara `-> bool`, sugiriendo que retorna `True` o `False`. **En realidad, nunca retorna `False`** — el path "no permitido" es siempre `raise SendBlocked`. Solo `True` es retorno normal.

**Consecuencia:**
- Developers que lean la firma pueden pensar "si False, no envío" → patrón anti-SendBlocked.
- Dos patrones incompatibles de consumo posibles:
  ```python
  if check_send_permission(...): ...  # ok para True
  ```
  vs
  ```python
  try:
      check_send_permission(...)
  except SendBlocked: ...
  ```
- Los callsites actuales usan el segundo patrón (correcto). Pero la firma invita al primero.

**Pasos de reproducción:**
Leer el type hint → no sugiere que nunca devuelve False.

**Fix propuesto (Phase 5):**
```python
from typing import Literal

def check_send_permission(
    creator_id: str,
    approved: bool = False,
    caller: str = "unknown",
) -> Literal[True]:
    """..."""
```

O mejor aún: `-> None` (el return value no se consume, la semántica es "raise or pass").

**Coste:** 1 LOC. Sin cambio de comportamiento. Type-checkers (mypy/pyright) validarán más fuerte.

---

## BUG-15 — `SendGuard` class dead code (L83-L87)

**Severidad:** 🟢 **BAJA**
**Archivo:** `backend/core/send_guard.py:83-87`
**Commit origen:** `7d49b663` — manel bertran luque, 2026-03-01 (añadido en PR "fix: resolve 17 bugs in conversational engine").

**Código afectado:**
```python
83: class SendGuard:
84:     """Class wrapper around check_send_permission for structured usage."""
85:
86:     def check(self, creator_id: str, approved: bool = False, caller: str = "unknown") -> bool:
87:         return check_send_permission(creator_id, approved=approved, caller=caller)
```

**Descripción:** Clase wrapper añadida 2 semanas después del commit inicial. **No se usa en ninguna ruta productiva** (verificado: `grep SendGuard backend --include="*.py" | grep -v send_guard.py | grep -v test` devuelve solo docs).

**Consecuencia:**
- 5 LOC de dead code.
- Potencial confusión: dos APIs (función + clase) para lo mismo, elegir cual usar.
- Señal de ruido: el PR de origen añadió 17 fixes y este wrapper es uno; nadie lo retomó.

**Pasos de reproducción:**
```bash
grep -rn "SendGuard" backend --include="*.py" | grep -v "send_guard.py" | grep -v test
```
Salida: solo docs.

**Fix propuesto (Phase 5):**
- Eliminar L81-L87 completamente, o
- Mantener y añadir test de uso para consolidar (si se decide que la API orientada a clase tiene valor para futuras expansiones — p.ej. inyección de dependencias en tests).

**Recomendación:** eliminar (5 LOC menos, cero pérdida funcional).

**Coste:** 1 delete.

---

## Resumen ejecutivo Fase 3

- **15 bugs categorizados**: 2 CRÍTICOS (BUG-01 autopilot WA bypass, BUG-02 name cross-tenant), 4 ALTOS (BUG-03..06), 5 MEDIOS (BUG-07..11, BUG-12), 3 BAJOS (BUG-13..15).
- **Patrón temporal**: todos los bypass (BUG-01, BUG-05, BUG-07, BUG-08) y weakness (BUG-09, BUG-10) **o bien preceden el guard** (BUG-07: 2 meses antes) **o bien fueron introducidos en los 6 días posteriores a crear el guard** (BUG-01, BUG-05, BUG-08, BUG-10). El guard se creó con la intención de ser universal pero nunca se completó la integración.
- **Mismo autor**: `manel bertran luque` (solo) o `manel bertran luque + Claude` en el 100% de commits afectados. Trabajo mayoritariamente AI-assistant-driven que introdujo el guard y paths paralelos sin reconciliar.
- **Cero commits de tests** para `send_guard` en 63 días de existencia.
- **Cero cambios al módulo** en 54 días desde el commit del class wrapper (que nunca se usó).
- **Prioridad de fix** (orden sugerido para Phase 5):
  1. **BUG-01** (CRÍTICO) — añadir guard en autopilot webhook WA (fix base sugerido por usuario).
  2. **BUG-02** (CRÍTICO) — UNIQUE constraint en `Creator.name` + `.one_or_none()`.
  3. **BUG-03** (ALTO) — `is False` explícito + backfill null.
  4. **BUG-04** (ALTO) — `check_send_permission_async` + migrar 6 callsites.
  5. **BUG-05** (ALTO) — guard en manual WA Cloud fallback.
  6. **BUG-06** (ALTO) — métricas Prometheus + log estructurado.
  7. **BUG-07/08** (MEDIO) — guards en `send_template` + `send_message_with_buttons`.
  8. **BUG-09/10** (MEDIO) — eliminar `approved=True` hardcoded en retry y multiplexer.
  9. **BUG-11** (MEDIO) — `SendDecision` dataclass uniforme.
  10. **BUG-12** (MEDIO) — test suite de 20+ tests.
  11. **BUG-13/14/15** (BAJO) — polish final.
- **Flag SEND_GUARD_AUDIT_ONLY**: constraint del task dice "si se añade flag, que sea SEND_GUARD_AUDIT_ONLY para logs-only sin bloqueo, default false". Se aplicará en Phase 5 como wrapper opcional para testing scoped.

**STOP Fase 3.** Aguardo confirmación para proceder a Fase 4 (papers + repos OSS 2024-2026 sobre fail-closed authz, message gating, consent management, audit logging).
