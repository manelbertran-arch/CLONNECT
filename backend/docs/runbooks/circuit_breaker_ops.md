# Runbook: CircuitBreaker Operations

**ARC3 Phase 4 — Operational Runbook**
**Última actualización:** 2026-04-19
**Feature flag:** `ENABLE_CIRCUIT_BREAKER` (default: **ON**)
**Código:** `core/generation/circuit_breaker.py`
**Integración:** `core/dm/phases/generation.py:477-503`

---

## Arquitectura en una línea

El CircuitBreaker opera **por conversación** (`creator_id` + `lead_id`). Tras 3 fallos consecutivos, bloquea generación LLM durante 60s y devuelve una respuesta fallback en lenguaje natural. El estado vive en `TTLCache` en memoria (no Redis) — expira automáticamente a los 5 minutos.

```
LLM call intento
      │
      ▼
 breaker.check()
      │
 ┌────┴────┐
 │tripped? │──yes──→ return fallback response + log WARNING
 └────┬────┘
      │ no
      ▼
 LLM generation
      │
  ┌───┴───┐
  │ error? │──yes──→ record_failure() → si failures=3 → TRIP + alert
  └───┬───┘
      │ no
      ▼
 record_success() → reset state
```

**Constantes clave:**
```python
MAX_CONSECUTIVE_FAILURES = 3    # fallos antes del trip
RESET_WINDOW_SECONDS     = 300  # 5 min — auto-reset si no hay actividad
TRIP_COOLDOWN_SECONDS    = 60   # tras trip, esperar 60s antes de reintento
```

---

## 1. Cuándo intervenir

### Señales de alerta

| Señal | Dónde verla | Urgencia |
|-------|-------------|----------|
| `[CircuitBreaker] TRIP` en logs | `railway logs` | Alta — revisar en < 15 min |
| `circuit_breaker_tripped=True` en metadata | Grafana / logs | Media |
| `model="circuit_breaker_fallback"` en respuestas | Grafana panel model distribution | Media |
| Alerta Grafana `CircuitBreakerTrips` disparada | Grafana Alerting | Alta |
| Leads recibiendo "Ey, te respondo en un rato" múltiples veces | Feedback de creator | Alta |

### Verificar estado actual

```bash
# Logs de trips en las últimas 2 horas
railway logs -n 500 | grep -E "CircuitBreaker|circuit_breaker" | grep -v "check\|success\|failure recorded"

# Ver todos los trips con creator + lead
railway logs -n 1000 | grep "TRIP creator="

# Contar fallos por creator
railway logs -n 500 | grep "CircuitBreaker.*failure recorded" | grep -oP "creator=\S+" | sort | uniq -c | sort -rn
```

---

## 2. Diagnóstico

### Leer logs filtrando por creator_id y lead_id

```bash
# Sustituir con UUIDs reales
CREATOR_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
LEAD_ID="yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"

railway logs -n 1000 | grep -E "creator=${CREATOR_ID}.*lead=${LEAD_ID}|lead=${LEAD_ID}.*creator=${CREATOR_ID}"
```

### Secuencia típica de un trip

```
[INFO]  [CircuitBreaker] failure recorded creator=abc lead=123 failures=1/3 reason=llm_timeout
[INFO]  [CircuitBreaker] failure recorded creator=abc lead=123 failures=2/3 reason=llm_timeout
[WARNING] [CircuitBreaker] TRIP creator=abc lead=123 reason=llm_timeout failures=3
[WARNING] [CircuitBreaker] BLOCKED creator=abc lead=123 (45.0s remaining)
```

### Entender el tipo de fallo

Los logs incluyen el `reason` del FailureType:

| reason en log | Tipo | Siguiente paso |
|---------------|------|----------------|
| `llm_timeout` | HARD | Revisar OpenRouter status / red |
| `llm_5xx` | HARD | Revisar quota OpenRouter o status del modelo |
| `content_filter` | HARD | Revisar el mensaje del lead — posible violación de policy |
| `json_parse_error` | HARD | Revisar prompt de sistema — posible corrupción |
| `empty_response` | SOFT | Revisar si el modelo está devolviendo vacío (quota?) |
| `response_too_short` | SOFT | Revisar system prompt, posible truncación |
| `loop_detected` | SOFT | Similar-response detection — revisar historial |

### Estado del breaker en memoria (no persistente)

El TTLCache no tiene endpoint de inspección directo. Para inferir el estado:

```bash
# Si hay "BLOCKED" en logs → está tripped
railway logs -n 100 | grep "BLOCKED creator="

# Si hay "TRIP" reciente (< 5 min) → estado activo en memoria
# Si el último "TRIP" fue hace > 5 min → TTLCache expiró → auto-reset

# Timestamp del último trip
railway logs -n 1000 | grep "TRIP creator=" | tail -5
```

---

## 3. Reset manual

### Opción A — Esperar el cooldown (recomendado)

El breaker se resetea automáticamente de dos formas:
1. **Cooldown (60s):** Tras el trip, después de 60s permite un "probe" (un intento de generación). Si tiene éxito, el estado se limpia.
2. **TTL (5 min):** Si la conversación está inactiva 5 minutos, el estado expira del TTLCache.

**En la mayoría de casos, no hay que hacer nada** — el breaker se auto-recupera.

### Opción B — Resetear forzando un restart (si está atascado)

El estado vive en memoria del proceso Railway. Un restart limpia todos los estados:

```bash
# Hacer un deploy vacío para reiniciar el proceso (resetea TODOS los breakers)
# AVISO: esto causa ~30s de downtime durante el re-deploy
git commit --allow-empty -m "ops: force restart to clear circuit breaker states"
git push origin main
```

**Usar solo si hay múltiples conversaciones bloqueadas que no se recuperan solas tras > 10 minutos.**

### Opción C — Desactivar el breaker temporalmente

Si hay falsos positivos sostenidos (ej. el proveedor LLM tuvo downtime y ahora está OK pero el breaker sigue):

```bash
# Desactivar CircuitBreaker (emergency only)
railway variables --set ENABLE_CIRCUIT_BREAKER=false
# Efecto tras el siguiente request, no requiere restart

# Restaurar cuando el sistema esté estable
railway variables --set ENABLE_CIRCUIT_BREAKER=true
```

**NUNCA dejar `ENABLE_CIRCUIT_BREAKER=false` más de 1 hora** sin resolver la causa raíz.

---

## 4. Failure taxonomy — acción por tipo

### HARD failures (siempre cuentan para el trip)

#### `LLM_TIMEOUT`
**Cuándo ocurre:** OpenRouter tarda > 90s en responder.

**Investigar:**
```bash
# Estado OpenRouter
# Ir a: https://status.openrouter.ai

# Ver si hay patrón en el modelo usado
railway logs -n 200 | grep -E "llm_timeout|timeout.*model"
```

**Acción:**
1. Si OpenRouter está down → esperar. Los breakers se auto-recuperarán cuando el proveedor vuelva.
2. Si timeout es de un modelo específico → considerar cambiar `OPENROUTER_MODEL` env var.
3. Si persiste > 30 min → escalar a Manel.

---

#### `LLM_5XX`
**Cuándo ocurre:** Error 500/502/503 de OpenRouter.

**Investigar:**
```bash
railway logs -n 200 | grep -E "5xx|LLM_5XX|HTTP 5"
```

**Acción:**
1. Verificar quota en OpenRouter dashboard.
2. Si es rate limit → esperar, el breaker tiene cooldown de 60s que ayuda.
3. Si es error sistémico → revisar si el modelo fue deprecado o está en maintenance.

---

#### `CONTENT_FILTER`
**Cuándo ocurre:** El modelo rechazó el prompt por policy violation.

**Investigar:** El mensaje del lead probablemente contiene contenido que el modelo no acepta.

```bash
# Buscar en logs el lead_id asociado al content_filter
railway logs -n 200 | grep "content_filter" | grep -oP "lead=\S+"
```

**Acción:**
1. Revisar el mensaje del lead (en DB: `SELECT content FROM messages WHERE id=<lead_id>`).
2. Si es intento de jailbreak → marcar lead como blockeado, NO resetear el breaker.
3. Si es falso positivo del modelo → revisar guardrails en system prompt.

---

#### `JSON_PARSE_ERROR`
**Cuándo ocurre:** El modelo devolvió un JSON inválido (solo relevante en llamadas structured output).

**Investigar:**
```bash
railway logs -n 200 | grep "json_parse_error\|JSONDecodeError"
```

**Acción:**
1. Verificar que el system prompt no fue modificado recientemente.
2. Revisar si el modelo fue cambiado y el nuevo modelo tiene comportamiento diferente.
3. Si es intermitente → temperatura alta puede causar esto; verificar settings del provider.

---

### SOFT failures (cuentan, pero indican patrón más sutil)

#### `EMPTY_RESPONSE`
**Cuándo ocurre:** El modelo devolvió string vacío o None.

**Acción:** Verificar quota de tokens. Con OpenRouter, una respuesta vacía a veces indica crédito agotado.

---

#### `RESPONSE_TOO_SHORT`
**Cuándo ocurre:** Respuesta < 3 caracteres (pero no vacía).

**Acción:** Revisar `tone_directive` en system prompt — puede haber restricción de longitud muy estricta que el modelo está intentando cumplir con contenido vacío.

---

#### `LOOP_DETECTED`
**Cuándo ocurre:** La respuesta generada es idéntica (o muy similar) al mensaje anterior del creador en esa conversación.

**Acción:** Revisar el historial de esa conversación. Si hay repetición de contexto en el prompt → puede ser un bug en `core/dm/phases/context.py`.

---

### No son failures (aunque parezcan)

- Respuesta con emoji "incorrecto" → las mutations lo corrigen post-generación
- Longitud fuera de rango → los mutations de longitud lo normalizan
- Respuesta en idioma diferente → no es un failure del LLM, es un error de calibración del prompt

---

## 5. Tuning de MAX_CONSECUTIVE_FAILURES

### Valor actual y por qué

`MAX_CONSECUTIVE_FAILURES = 3` — alineado con `createGeneration.js:442` de Claude Code (referencia ARC3 §2.4.1).

**3 es conservador-protector:** permite 2 errores transitorios (ej. flakiness del proveedor) pero bloquea en el tercero. Coincide con el patrón estándar de la industria para circuit breakers en LLM pipelines.

### Cuándo bajar (más protector)

Bajar a `MAX_CONSECUTIVE_FAILURES = 2` si:
- Los falsos positivos son raros (el proveedor es muy estable)
- Los retry-loops observados en W5 §4.3 causan impacto en cost/latency visible
- Manel prefiere respuesta fallback rápida antes que 3 intentos

```python
# core/generation/circuit_breaker.py:47
MAX_CONSECUTIVE_FAILURES = 2  # cambiar aquí
```

### Cuándo subir (menos conservador)

Subir a `MAX_CONSECUTIVE_FAILURES = 5` si:
- El proveedor LLM tiene mucha flakiness transient (3 fallos son frecuentes sin haber problema real)
- Las respuestas fallback están causando confusión en leads reales

**Procedimiento para cambiar el valor:**
1. Modificar la constante en `core/generation/circuit_breaker.py`
2. Syntax check: `python3.11 -c "import ast; ast.parse(open('core/generation/circuit_breaker.py').read())"`
3. Correr tests: `.venv/bin/python3.11 -m pytest tests/circuit_breaker/ -q`
4. Commit + deploy

---

## Respuestas fallback disponibles

Cuando el breaker está tripped, el lead recibe una de estas respuestas (según idioma detectado):

| Key | Texto |
|-----|-------|
| `default` (español) | "Ey, te respondo en un rato que ando liado/a 🙏" |
| `es_long` | "Mil perdones, se me está liando el día — te escribo ahorita con calma" |
| `en` | "hey! i'll get back to you in a bit, bear with me 🙏" |

La detección de idioma actual es best-effort y defaultea a `default` (español).

---

## Referencias

- Diseño ARC3: `docs/sprint5_planning/ARC3_compaction.md` §2.4
- Design doc CircuitBreaker: `docs/sprint5_planning/ARC3_phase4_circuit_breaker.md`
- Código: `core/generation/circuit_breaker.py`
- Integración: `core/dm/phases/generation.py:477-503`
- Feature flag: `core/feature_flags.py:116-123` (`ENABLE_CIRCUIT_BREAKER`)
