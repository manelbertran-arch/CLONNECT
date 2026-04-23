# Fase 2 — Forense línea a línea de `send_guard`

**Artefacto:** `backend/core/send_guard.py` (87 LOC)
**Fecha:** 2026-04-23
**Branch:** `forensic/send-guard-20260423`
**Método:** lectura línea a línea + `git blame` + auditoría de cada callsite + crosscheck de bypass paths.

---

## 1. Línea a línea de `send_guard.py`

### 1.1 Docstring del módulo (L1-L12)

```python
1:  """
2:  Safety Guard: Prevents bot messages from being sent without explicit approval.
3:
4:  LAST LINE OF DEFENSE against accidental auto-send.
5:  Every outbound bot message MUST pass through check_send_permission().
6:
7:  The ONLY ways a message can pass:
8:  1. approved=True (creator approved in dashboard, or creator manual send)
9:  2. Autopilot premium: copilot_mode=False AND autopilot_premium_enabled=True
10:
11: DO NOT REMOVE THIS MODULE.
12: """
```

**Observaciones:**
- L5 **contrato declarado**: "MUST pass through check_send_permission()". Pero el codebase **no tiene enforcement** (no hay test/CI que verifique que todas las rutas de envío la invocan). En Phase 2.4 identificamos **rutas que no la invocan**.
- L11 "DO NOT REMOVE THIS MODULE" es meta-comentario a futuros devs. No hay enforcement (no es un pre-commit hook ni un lint rule); si alguien elimina el archivo, solo los tests lo notarán — y solo hay **un test import-only** que lo cubriría.

### 1.2 Imports y logger (L14-L16)

```python
14: import logging
15:
16: logger = logging.getLogger(__name__)
```

Estándar. `__name__ == "core.send_guard"` (en prod) — el logger name es lo que Railway/Grafana buscaría para filtrar eventos del guard. OK.

### 1.3 Excepción (L19-L22)

```python
19: class SendBlocked(Exception):
20:     """Raised when a send is blocked by the safety guard."""
21:
22:     pass
```

**Observaciones:**
- Herencia directa de `Exception` (no de `RuntimeError`, `ValueError`, etc.). Semánticamente correcto.
- **No estructura de campos**: no tiene `reason`, `creator_id`, `caller` como atributos — solo el string pasado al constructor. Esto obliga a los callers a parsear strings o perder información.
- **Candidato Phase 5**: extender con dataclass-like fields (`reason: str`, `blocked_rule: "R2"|"R4"`, `creator_id`, `caller`). Mantiene compatibilidad si se usan kwargs.

### 1.4 Firma de `check_send_permission` (L25-L29)

```python
25: def check_send_permission(
26:     creator_id: str,
27:     approved: bool = False,
28:     caller: str = "unknown",
29: ) -> bool:
```

**Observaciones línea por línea:**
- L26 `creator_id: str` — sin `Optional`, pero no hay validación runtime. Acepta `""`, strings garbage, y `None` coerced via SQLAlchemy `filter_by(name=None)` (que devuelve None → R2 fail-closed). Protegido por fail-closed pero no por validación explícita.
- L27 `approved: bool = False` — **default fail-closed**. Correcto por diseño. Si alguien llama `check_send_permission(creator_id)` sin especificar approved, va por el path no-approved.
- L28 `caller: str = "unknown"` — **magic default** que oculta origen en logs. Si un dev añade un nuevo callsite y olvida `caller="..."`, el log sale con `caller=unknown` y ningún mecanismo lo detecta. **Bug candidato Phase 3**.
- L29 `-> bool`. **Pero en realidad nunca retorna False** — el path `False` se materializa vía `raise SendBlocked`. El tipo de retorno es engañoso: el valor `True` es la única posibilidad de retorno normal. Semánticamente `-> Literal[True]` o `-> None`.

### 1.5 Docstring de la función (L30-L43)

OK, completo. Menciona "Returns True if allowed" y "Raises SendBlocked if not allowed". Coincide con comportamiento real.

**Gap documental:** no menciona que `caller="unknown"` es un sentinel, que `approved=False` es el default fail-closed, ni que se abre una `SessionLocal` nueva por llamada.

### 1.6 R1 — Shortcut approved (L44-L46)

```python
44:     # Pre-approved messages always pass
45:     if approved:
46:         return True
```

**Observaciones:**
- L45 truthy-check de `approved`. Si `approved == 1` (int), `approved == "True"` (string), `approved == [1]` (lista no vacía) → pasa. Type hint `bool` no es runtime enforcement. Bajo riesgo en la práctica.
- **Ningún log** cuando pasa por R1. Un **80-90% de los envíos** en producción (copilot-approved) no emiten ningún rastro de que el guard se ejecutó. La única pista es `caller="..."` en logs cuando bloquea, que jamás ocurre para approved paths.
- Consecuencia para auditoría: si un regulador pregunta "demuéstrame que este mensaje pasó tu guard", no hay log. Solo hay rastro implícito en los logs del adapter (e.g. `[Copilot] Instagram API response: ...`).

### 1.7 Imports lazy (L49-L50)

```python
48:     # Not approved — check autopilot premium flags
49:     from api.database import SessionLocal
50:     from api.models import Creator
```

**Observaciones:**
- Lazy para evitar ciclos con `api.database` y `api.models` al importar `send_guard`. **Correcto** dado el grafo de dependencias de Clonnect.
- `from api.models import Creator` — el archivo real es `api/models/creator.py` pero hay un `api/models/__init__.py` que re-exporta `Creator`. OK.
- **Coste:** cada invocación re-resuelve el import (Python cachea módulos en `sys.modules`, coste casi nulo después del primero). No es un problema.

### 1.8 Sesión de DB (L52)

```python
52:     session = SessionLocal()
```

**Observaciones:**
- **Crea una sesión nueva** cada llamada; no reutiliza la sesión de la request HTTP. Implica:
  - +1 conexión efímera al pool (corta vida, get+release).
  - **Sin consistencia transaccional** con otras operaciones de la misma request. Si la request está en medio de una transacción que acaba de hacer UPDATE sobre `creators`, esta nueva sesión **no ve los cambios no committed** (aislamiento READ COMMITTED / nothing).
  - Razón: la request no tiene por qué haber tocado `creators`; el guard es idempotente y quiere lectura fresca. Correcto.
- **Gap:** no hay timeout explícito. Si el pool está exhausto, `SessionLocal()` bloquea hasta que haya conexión o hasta `pool_timeout`. Pool Clonnect = 5+7 (12 max), `pool_timeout` default SQLAlchemy = 30s. En un event loop async, esto **bloquea el loop 30s** si se llama desde contexto async sin `asyncio.to_thread`. En el prod code actual, `send_guard` se llama sincrónicamente desde métodos `async` — **posible hog del event loop** bajo pool pressure. Bug Phase 3.

### 1.9 Try/finally (L53, L79-L80)

```python
53:     try:
54:         creator = session.query(Creator).filter_by(name=creator_id).first()
...
79:     finally:
80:         session.close()
```

**Observaciones:**
- Try solo con `finally`, sin `except`. Cualquier excepción dentro (DB disconnect, timeout, constraint, etc.) **propaga hacia arriba** después de ejecutar `session.close()`. OK para cleanup.
- No hay `rollback()` en el finally. Como la sesión es read-only (solo SELECT), `rollback()` es innecesario; `close()` implícitamente rolls back transactions abiertas en SQLAlchemy. Aceptable.

### 1.10 Query Creator (L54)

```python
54:         creator = session.query(Creator).filter_by(name=creator_id).first()
```

**Observaciones:**
- `filter_by(name=creator_id)`. `Creator.name` está **indexado** (verificado en `api/models/creator.py:33` — `index=True` con comentario "FIX P1: Added index for faster lookups"). O(log N) lookup. OK.
- **`name` no es UNIQUE** en el schema (solo `email` y `api_key` son unique, ver `api/models/creator.py:32,34`). Si dos creators comparten `name` (fixture/test pollution, seed duplicado), `first()` devuelve uno arbitrario — **potencial cross-tenant leak** si dos tenants acaban con el mismo slug. **Bug candidato Phase 3 (baja probabilidad, alto impacto).**
- `creator_id` del parámetro se interpreta como `Creator.name`. Confusión potencial: en el rest del sistema `creator_id` a veces es slug, a veces UUID. Aquí **siempre** es slug por contrato (ver MEMORY.md "creator_id es slug/nombre").

### 1.11 R2 — Creator not found (L55-L60)

```python
55:         if not creator:
56:             logger.critical(
57:                 f"[BLOCKED AUTO-SEND] creator={creator_id} caller={caller} — "
58:                 f"Creator not found"
59:             )
60:             raise SendBlocked(f"Creator {creator_id} not found")
```

**Observaciones:**
- `logger.critical(...)` + `raise`. Correcto fail-closed.
- **Log string-interpolado**: no hay JSON, no hay `extra={...}`. Si Railway/Grafana tiene configurado JSON structured logging, esto sale como blob texto. Dificulta filtrado por campos. **Bug Phase 3 (observabilidad).**
- El prefijo `[BLOCKED AUTO-SEND]` es el único marcador machine-greppable. Un regex `\[BLOCKED AUTO-SEND\]` sobre logs funciona, pero extraer `creator_id` y `caller` requiere parser adicional.
- `raise SendBlocked(f"Creator {creator_id} not found")` — el mensaje de la excepción incluye el `creator_id`, duplicando info del log. Si el caller captura y re-logga `str(e)`, aparece 2x. Pequeño duplicado.

### 1.12 R3 — Autopilot premium pass (L62-L68)

```python
62:         # Autopilot requires BOTH flags
63:         if not creator.copilot_mode and creator.autopilot_premium_enabled:
64:             logger.info(
65:                 f"[AUTOPILOT] Send allowed for {creator_id} caller={caller} "
66:                 f"(premium autopilot active)"
67:             )
68:             return True
```

**Observaciones:**
- L63 **truthy-and check**. Implicaciones de nullability:
  - `creator.copilot_mode`: default `True`, `nullable` **no especificado** en el modelo → SQLAlchemy default = nullable. Legacy rows podrían tener `None`. Si `None`: `not None == True` → primera condición pasa.
  - `creator.autopilot_premium_enabled`: `nullable=False` (verificado L93 del modelo), garantizado bool.
  - Si `copilot_mode=None ∧ autopilot_premium=True`, R3 pasa. **Esto es semánticamente raro** — una fila con `copilot_mode=None` no ha sido configurada explícitamente, pero el guard la trata como "no copilot" y permite autopilot. **Bug Phase 3 (medium)**: preferiría `is False` explícito.
- Log `info` (no `critical`) — el único path success que loggea. Bien para auditoría del autopilot (cada envío autopilot deja rastro).
- `logger.info` en vez de `logger.warning` — en Railway sale mezclado con ruido SCORING-V3 etc. Bajo visibilidad operacional.

### 1.13 R4 — Block default (L70-L78)

```python
70:         # BLOCK
71:         logger.critical(
72:             f"[BLOCKED AUTO-SEND] creator={creator_id} caller={caller} — "
73:             f"copilot_mode={creator.copilot_mode} "
74:             f"autopilot_premium={creator.autopilot_premium_enabled} — "
75:             f"Bot message not approved by creator. "
76:             f"Only dashboard toggle + premium flag can enable autopilot."
77:         )
78:         raise SendBlocked("Message blocked — not approved by creator")
```

**Observaciones:**
- Log `critical` con los 4 campos relevantes inline (creator, caller, copilot_mode, autopilot_premium). **Mejor que R2** (que solo tiene creator+caller) pero aún string-interpolado.
- `SendBlocked("Message blocked — not approved by creator")` es **mensaje genérico**: **pierde el motivo específico** (era cópilo activado? era premium off? era ambos?). El caller que hace `str(e)` recibe el mismo texto sin importar qué combinación de flags causó el bloqueo. Dificulta telemetría y auditoría. **Bug Phase 3.**
- **Ninguna métrica Prometheus emitida**. Ni counter `send_guard_blocked_total`, ni histogram, nada. Solo logs. **Gap Phase 5.**

### 1.14 Class wrapper (L83-L87)

```python
83: class SendGuard:
84:     """Class wrapper around check_send_permission for structured usage."""
85:
86:     def check(self, creator_id: str, approved: bool = False, caller: str = "unknown") -> bool:
87:         return check_send_permission(creator_id, approved=approved, caller=caller)
```

**Observaciones:**
- Añadido en commit `7d49b663b` (2026-03-01) en un PR "fix: resolve 17 bugs in conversational engine — security, intent, pipeline, quality".
- **No se usa en ningún lado de producción** (`grep SendGuard backend` devuelve solo:
  - `core/send_guard.py` — la definición
  - `tests/test_motor_audit.py:535-536` — un assert `SendGuard is not None` (import check, nada más)
  - `docs/CLONNECT_FUNCTIONAL_INVENTORY.md` — menciones en docs
  - ).
- **Dead code.** 5 LOC sin valor. Candidato a eliminar en Phase 5 o dejar si se quiere consolidar API orientada a objetos.

---

## 2. Git blame resumido

`git log --all --oneline -- backend/core/send_guard.py`:

```
7d49b663 fix: resolve 17 bugs in conversational engine — security, intent, pipeline, quality
e2713c6e fix: safety guard — autopilot only via dashboard + premium flag
```

**Solo 2 commits en toda la historia del archivo** (2026-02-19 y 2026-03-01).

| Commit | Fecha | LOC touched | Cambio |
|--------|-------|-------------|--------|
| `e2713c6e` | 2026-02-19 19:49 | L1-L80 (80 LOC) | **Creación del módulo**. `SendBlocked`, `check_send_permission` con reglas R1-R4 tal cual existen hoy. Autor: manel + Claude Opus 4.6. Commit message acknowledge: "Add check_send_permission() as last line of defense against accidental auto-send". |
| `7d49b663` | 2026-03-01 20:56 | L81-L87 (7 LOC) | **Añadido `SendGuard` class wrapper**, nunca usado. Parte de un PR colectivo de 17 fixes. No hay contexto de por qué se añadió ni qué lo usaría. |

**Insights:**
- **La lógica fail-closed es original al commit inicial y no ha cambiado en 63 días** (19-feb → 23-abr). Esto es **saludable**: la seguridad es estable. Pero también significa que **no se ha validado empíricamente** bajo carga ni con test suite.
- **No hay refactors, no hay tests añadidos, no hay métricas añadidas.** El módulo está congelado desde la versión inicial.
- **No hay menciones de send_guard en CLAUDE.md** (ni project ni user memory). El único comentario es `DO NOT REMOVE THIS MODULE` dentro del propio archivo.

---

## 3. Auditoría de los 6 callsites (simetría)

### 3.1 Tabla comparativa

| # | Adapter | Archivo:Línea | Retorno bloqueo | Retorno otra exc. | Creator resolution | Caller string |
|---|---------|---------------|------------------|-------------------|--------------------|---------------|
| C1 | Telegram | `core/telegram_adapter.py:568-573` | `return False` | N/A (no try outer) | `self.creator_id` (from `__init__`) | `"tg_adapter.send_message"` |
| C2 | Instagram | `core/instagram_modules/message_sender.py:29-34` | `return False` | `except Exception` → queue for retry → `return False` | `self.creator_id` (from `__init__`) | `"ig_handler.send_response"` |
| C3 | Copilot mux | `core/copilot/messaging.py:22-28` | `{"success": False, "error": str(e), "blocked": True}` | `except Exception` → `{"success": False, "error": str(e)}` (sin `blocked: True`) | `creator.name` (from Creator object in call) | `"copilot_service"` |
| C4 | WhatsApp Cloud | `core/whatsapp/handler.py:348-353` | `return False` | `except Exception` (network) → `return False` | `self.creator_id` (from `__init__`) | `"wa_handler.send_response"` |
| C5 | Evolution text | `services/evolution_api.py:56-62` | `{"error": "Message blocked...", "blocked": True}` | **NO exception handler** — propaga a caller | `_resolve_creator_from_instance(instance)` → `"unknown"` on miss | `"evolution_api"` |
| C6 | Evolution media | `services/evolution_api.py:174-180` | `{"error": "Message blocked...", "blocked": True}` | **NO exception handler** — propaga a caller | `_resolve_creator_from_instance(instance)` → `"unknown"` on miss | `"evolution_api.send_media"` |

### 3.2 Asimetrías críticas

**Asimetría A — Contrato de retorno (boolean vs dict):**
- C1, C2, C4 → `return False` boolean
- C3, C5, C6 → `return {"error": ..., "blocked": True}` dict

**Consecuencia:** el caller de C1/C2/C4 **no puede distinguir** un bloqueo por guard de un fallo network/auth/rate-limit. Todos son `False`. Para telemetría agregada ("¿cuántos mensajes bloqueados vs cuántos fallos técnicos?") hay que cruzar con logs (string search de `[BLOCKED AUTO-SEND]` + correlate temporalmente). **No escalable.**

**Asimetría B — Creator ID resolution:**
- C1, C2, C4 → `self.creator_id` (bound en `__init__`; si el constructor no validó, garbage entra aquí)
- C3 → `creator.name` (objeto Creator ya cargado en el caller; trusted)
- C5, C6 → `_resolve_creator_from_instance(instance)` que **devuelve `"unknown"`** si el instance no está en `EVOLUTION_INSTANCE_MAP` (línea 36 evolution_api.py) o si el import falla (línea 38).

**Consecuencia C5/C6:** si el `instance` es desconocido, `creator_id="unknown"` se pasa al guard. Dos sub-casos:
- R1: `approved=True` → pasa sin tocar DB, sin validar. **Potencial bypass**: un atacante que controla el instance name y sabe pasar `approved=True` puede enviar mensajes sin que el creator real sea identificado en logs.
- R2: `filter_by(name="unknown").first()` → si existe un creator con nombre "unknown" (plausible de un seed o test fixture), aplica sus flags al envío — **autoridad cruzada**. Si no existe, R2 bloquea. Fail-closed correcto.

**Asimetría C — Manejo de excepciones no-SendBlocked:**
- C1 (telegram): solo captura `SendBlocked`; cualquier otra exc. del guard (DB timeout, ImportError) propaga → caller de `send_message` (e.g. orchestrator) la recibe sin envolver. Potencial 500.
- C2 (IG): outer `except Exception` envuelve todo en queue-for-retry y `return False`. **Si el guard tira DB exception, el mensaje entra en retry queue con `approved=True` hardcoded** (línea 184 de `meta_retry_queue.py`) → en el segundo intento, R1 short-circuit → envío sin validar flags. **Bypass indirecto via retry**. **Bug Phase 3 HIGH.**
- C3 (copilot): outer `except Exception` → dict sin `blocked: True`. Distinguible de bloqueo.
- C4 (WA): outer `except Exception` en el cuerpo del connector (L370), pero **el guard call (L350-353) está fuera** de ese try → si el guard tira DB exc., propaga al caller con `return False` imposible de distinguir de otros fallos.
- C5, C6 (evolution): **ninguna captura de exceptions no-SendBlocked en la función**. DB disconnect → propaga. Caller (`_send_whatsapp_message` en `messaging.py:167`) captura `except Exception as evo_err` (L171) y loggea warning + cae a Cloud API fallback → **pero Cloud API fallback usa connector directo sin guard** (bypass B1/B2 abajo).

### 3.3 Simetría 1: lazy import consistente

Los 6 hacen `from core.send_guard import SendBlocked, check_send_permission` **dentro del método** (no top-level). Rompen ciclos. **Consistente**.

### 3.4 Simetría 2: doc-string "GUARDED by send_guard"

Los 6 docstrings mencionan "GUARDED by send_guard" (o "--GUARDED by..." en C4 por typo doble guión). Discoverable via grep "GUARDED". Funciona como self-documenting contract — frágil si alguien añade send method nuevo y olvida el docstring.

---

## 4. Rutas de bypass detectadas (mensajes enviados SIN guard)

Grep de `connector.send_message|connector.send_template|connector.send_media|connector.send_text` reveló **4 rutas productivas de bypass** + **1 caller de unguarded send method**:

### 4.1 Bypass B1 — `api/routers/dm/processing.py:173`

```python
170:     # Fall back to official WhatsApp Cloud API
171:     wa_handler = get_whatsapp_handler()
172:     if wa_handler and wa_handler.connector:
173:         result = await wa_handler.connector.send_message(phone, message_text)
174:         sent = "error" not in result
```

**Contexto:** handler de **manual send** (creator escribe en dashboard y envía). Path WhatsApp, fallback Cloud API cuando no hay Evolution instance. **Llama al connector directamente**, NO pasa por `wa_handler.send_response` (C4).

**Severidad: HIGH.**
- **Mitigación existente**: esta ruta se activa solo via endpoint manual-send autenticado; el creator está iniciando la acción, así que "es aprobado por diseño". El `approved=True` lógico está implícito.
- **Problema**: el guard es el safety net **precisamente** para casos donde la lógica upstream falla. Sin la invocación explícita, un bug en el endpoint (e.g. falta verificación de auth) podría disparar sends sin consent.
- **Fix Phase 5**: reemplazar `wa_handler.connector.send_message(...)` por `wa_handler.send_response(phone, message_text, approved=True)` → pasa por C4.

### 4.2 Bypass B2 — `api/routers/messaging_webhooks/whatsapp_webhook.py:200`

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
```

**Contexto:** webhook-driven autopilot path. Cuando un WhatsApp msg entra, si `copilot_enabled=False` (cache), entra en rama AUTOPILOT → crea connector ad-hoc → send directo. **NO pasa por C4 ni C5.**

**Severidad: CRITICAL.**
- El upstream check es `_get_copilot_mode_cached(creator_id)` (L148) — **solo verifica `copilot_mode`**, no `autopilot_premium_enabled`. Un creator con `copilot_mode=False ∧ autopilot_premium_enabled=False` tendría `copilot_enabled=False` → **cae en rama autopilot y envía sin haber pagado premium**.
- Esto es **exactamente la regla que el guard debería enforcer** (R3: autopilot requires BOTH flags) — y se está saltando entera.
- Además, un cache stale: si el creator acaba de cambiar `copilot_mode=True` en dashboard, pero el cache tiene TTL y no se ha invalidado, el webhook procesa con el valor viejo → envío no autorizado.
- **Fix Phase 5 OBLIGATORIO**: insertar `check_send_permission(creator_id, approved=False, caller="wa_webhook.autopilot")` antes del send. Si el creator no tiene premium, el guard bloqueará. Coste: 1 DB query adicional por webhook.

### 4.3 Bypass B3 — `core/whatsapp/handler.py:375` `send_template`

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

**Contexto:** método para enviar template messages (welcome, notifications). **No llama a `check_send_permission`**.

**Severidad: MEDIUM.**
- Semánticamente las templates son notificaciones del sistema, no DMs del bot. Pero se envían en nombre del número del creator y pueden violar consent si no están aprobadas por la plataforma (WA requiere templates pre-aprobadas por Meta).
- Crosscheck: `grep send_template` muestra que **no hay callers productivos** en el codebase (solo la definición y test importaciones). **Dead method + potencial bypass.**
- **Fix Phase 5**: (a) eliminar si nunca se usa, o (b) añadir guard con `approved` param.

### 4.4 Bypass B4 — `core/instagram_modules/message_sender.py:86` `send_message_with_buttons`

```python
86:     async def send_message_with_buttons(
87:         self, recipient_id: str, text: str, buttons: List[Dict[str, str]]
88:     ) -> bool:
...
109:             result = await self.connector.send_message_with_buttons(recipient_id, text, buttons)
```

**Contexto:** enviar IG DM con quick-reply buttons. **No llama a `check_send_permission`**.

**Severidad: MEDIUM.**
- **Un caller detectado**: `core/instagram_handler.py:316` (`return await self._sender.send_message_with_buttons(...)`) — buscar quién llama a ese wrapper para evaluar si alguna ruta autopilot lo usa.
- Si solo se llama desde paths ya aprobados (e.g. onboarding o dashboard-driven), riesgo bajo. Si lo llama cualquier path autopilot, bypass activo.
- **Fix Phase 5**: añadir guard por simetría; coste trivial.

### 4.5 Weakness W1 — `services/meta_retry_queue.py:184` (trust propagation)

```python
183:     handler = InstagramHandler(creator_id=item.creator_id)
184:     return await handler.send_response(item.recipient_id, item.message, approved=True)
```

**Contexto:** retry queue para IG sends fallidos. Hardcodea `approved=True` en el reintento.

**Severidad: LOW-MEDIUM.**
- El mensaje entró a la queue **porque falló** — asumimos que previamente pasó el guard. Esta asunción es razonable **SI** el failed-send originalmente pasó por el guard (cual fue el caso: IG's `send_response` C2 guarda).
- **Problema**: si el creator revoca consent (flags cambian) entre el fallo original y el retry, el retry envía igualmente. `approved=True` bypassa re-validación.
- **Fix Phase 5**: propagar el `approved` original a la queue item (campo nuevo en `QueuedMessage`), o pasar `approved=False` en el retry para que R3 re-valide flags actuales del creator.

### 4.6 Weakness W2 — `core/copilot/messaging.py:167` `approved=True` hardcoded

Ya mencionado en Phase 1. `send_evolution_message(..., approved=True)` hardcoded en el multiplexer. Convierte C5 en no-op para este path. Severidad LOW (el path siempre ha pasado C3 previamente) pero conceptualmente igual a W1.

---

## 5. Edge cases

### 5.1 `creator_id` inputs raros

| Input | R1 (approved=True) | R1 (approved=False) |
|-------|-------------------|---------------------|
| `""` (empty string) | pasa | `filter_by(name="").first()` → None → R2 block |
| `None` | pasa | `filter_by(name=None)` → query SQL `name IS NULL`; si no hay row con name=NULL → R2 block; si sí (seed bug) → usa sus flags |
| Unicode exótico | pasa | normal string compare; ok |
| Whitespace padding `" iris_bertran "` | pasa | `filter_by(name=" iris_bertran ")` → no match (case-sensitive, space-sensitive) → R2 block |
| Upper case `"IRIS_BERTRAN"` | pasa | exact match → R2 block unless exists |
| `"unknown"` (sentinel de evolution resolver) | pasa (approved-path) | query "unknown" → None → R2 block |

### 5.2 `approved` inputs raros

| Input | Behavior | Risk |
|-------|----------|------|
| `True` | R1 pass | OK |
| `False` | goes to R2/R3/R4 | OK |
| `None` | falsy → goes to R2/R3/R4 | OK |
| `1` (int) | truthy → R1 pass | type hint lie but safe |
| `"True"` (string) | truthy → R1 pass | **bug candidate**: someone passes string from env/query-param |
| `[]` | falsy → goes to flags check | OK |
| `object()` | truthy → R1 pass | unlikely in practice |

### 5.3 Creator row edge cases

| Estado row | R3 eval | Resultado |
|------------|---------|-----------|
| `copilot_mode=True, autopilot_premium_enabled=False` | `not True ∧ False = False` | R4 block |
| `copilot_mode=False, autopilot_premium_enabled=True` | `not False ∧ True = True` | R3 pass |
| `copilot_mode=False, autopilot_premium_enabled=False` | `not False ∧ False = False` | R4 block |
| `copilot_mode=True, autopilot_premium_enabled=True` | `not True ∧ True = False` | R4 block |
| `copilot_mode=None, autopilot_premium_enabled=True` (legacy) | `not None ∧ True = True ∧ True = True` | **R3 pass** — semantically ambiguous (not configured = allow autopilot?) |
| `copilot_mode=None, autopilot_premium_enabled=None` (legacy + invariant broken, `nullable=False` protects) | should never happen | `None ∧ True ∧ ...` → eventually falsy → R4 |
| Row deleted mid-request | transaction visibility depends; fresh SessionLocal reads committed state → R2 probably | fail-closed OK |
| Two creators with same `name` (non-unique) | `first()` picks one arbitrarily | cross-tenant risk LOW probability, HIGH impact |

### 5.4 DB failures

| Failure | Comportamiento |
|---------|---------------|
| Pool exhausted (12/12 used) | `SessionLocal()` blocks up to `pool_timeout` (30s default) → event loop hog → either eventual query or `TimeoutError` propagation |
| Connection dies mid-query | `filter_by().first()` raises `OperationalError` → propaga up, session.close() still runs. Caller handling inconsistent (§3.2). |
| Server restart mid-query | same as above |
| Network partition | same |
| Invalid SQL (shouldn't happen with filter_by) | raises, propagates |

### 5.5 Concurrent flag changes

Scenario: dashboard UI toggles `copilot_mode` from `False` to `True` mid-request.

- T0: webhook received, bot generates reply, copilot_service decides autopilot path.
- T1 (ms=10): creator toggles flag in dashboard (`autopilot_premium_enabled=False`). Commit applied to DB.
- T2 (ms=20): `check_send_permission` opens SessionLocal → reads committed state → sees new flag → R4 block.

**Resultado:** bloqueo correcto aunque el initial path era "iba a enviar autopilot". Safe.

Inverso: T1 flips `autopilot_premium=False` → `autopilot_premium=True`. At T2, `check_send_permission` reads `True` → R3 pass → envío. **Consent just-in-time** — acceptable semantically.

**Verdict:** race behavior es aceptablemente fail-closed-first.

### 5.6 Cross-platform creator_id mismatch

`self.creator_id` en C1/C2/C4 se setea en `__init__` del handler. Si el handler se inicializa con creator_id erróneo y luego se llama `send_response` sobre un lead de OTRO creator, el guard valida contra el handler's creator_id, **no** contra el lead's creator. **Bug latente**: un test fixture o bug de routing podría causar envío con flags del creator equivocado.

Mitigación: el handler suele ser único por creator (1 IG handler por cuenta). Pero multi-tenant futuro (single handler multiplex) expone este bug.

---

## 6. Observaciones de contexto cruzado

### 6.1 Tests — cobertura real

Grep exhaustivo de tests que toquen `send_guard`:

- `tests/test_motor_audit.py:535-536` — `from core.send_guard import SendGuard; assert SendGuard is not None`. Solo comprueba importabilidad.
- `mega_test_auto.py:677-689` — 3 asserts triviales:
  - `issubclass(SendBlocked, Exception)`
  - `check_send_permission("test_creator", approved=True, caller="test") == True`
  - `check_send_permission("nonexistent_creator_xyz", approved=False, caller="test")` raises SendBlocked or Exception

**Gap: 0 tests que verifiquen las reglas R2/R3/R4 sobre creators reales con flags específicos. 0 tests de simetría entre callsites. 0 tests de bypass paths.**

### 6.2 Documentación externa

- `backend/docs/CLONNECT_FUNCTIONAL_INVENTORY.md:308-310,326` — describe SendGuard como "barrera infranqueable" y "el módulo más crítico del sistema". Status ✅ "funciona". Sin detalles de cobertura ni métricas.
- CLAUDE.md (raíz) — 0 menciones.

### 6.3 MEMORY.md (memoria del proyecto)

0 menciones de `send_guard`, `SendBlocked`, `check_send_permission`, o "safety guard". El módulo no tiene contexto histórico en memoria, lo cual es consistente con que está congelado desde hace 63 días.

---

## Resumen ejecutivo Fase 2

- **Código estable, 2 commits, 63 días congelado.** Arquitectura R1-R4 intacta desde día 1.
- **Simetría 6 callsites incompleta**: 2 familias de retorno (bool vs dict); creator resolution inconsistente (self.creator_id vs `_resolve_creator_from_instance` que devuelve `"unknown"` en miss); manejo de non-SendBlocked exceptions inconsistente.
- **4 bypass paths productivos detectados:**
  - **B1** `dm/processing.py:173` — manual WA Cloud fallback, severidad HIGH
  - **B2** `whatsapp_webhook.py:200` — AUTOPILOT webhook path, severidad **CRITICAL** (no verifica autopilot_premium)
  - **B3** `whatsapp/handler.py:375` — `send_template` método sin guard, severidad MEDIUM
  - **B4** `instagram_modules/message_sender.py:86` — `send_message_with_buttons` sin guard, severidad MEDIUM
- **2 weakness de trust propagation:**
  - **W1** `meta_retry_queue.py:184` — `approved=True` hardcoded en retry
  - **W2** `copilot/messaging.py:167` — `approved=True` hardcoded en multiplexer downstream
- **Edge cases sin cobertura:** `copilot_mode=None` legacy, `name` no-unique cross-tenant, pool exhaustion hangeando event loop, `approved` truthiness con strings.
- **Observabilidad pobre**: 0 métricas Prometheus, logs string-interpolados, R1 sin log, `SendBlocked` pierde reason (mensaje genérico).
- **Dead code**: `SendGuard` class (L83-L87) nunca usada en producción.
- **Tests**: 3 asserts triviales + 1 import check. Cobertura real ~0%.

**STOP Fase 2.** Aguardo confirmación para proceder a Fase 3 (consolidar bugs con SHA, línea, severidad, reproducción, fix).
