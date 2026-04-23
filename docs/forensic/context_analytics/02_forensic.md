# context_analytics — Forense línea a línea

## Archivo: `core/dm/context_analytics.py` (212 LOC)

### Sección 1: Módulo docstring (L1–12)

```python
"""G3+G4: Token distribution analytics and context health warnings.
Observability-only module — reads prompt composition and emits structured
logs. Does NOT modify the prompt or the pipeline.
...
"""
```

El docstring declara explícitamente `observability-only`. Correcto y completo. Incluye ejemplo de uso.

---

### Sección 2: Thresholds + constante inline (L19–26)

```python
CONTEXT_WARNING_THRESHOLD  = float(os.getenv("CONTEXT_WARNING_THRESHOLD", "0.80"))
CONTEXT_CRITICAL_THRESHOLD = float(os.getenv("CONTEXT_CRITICAL_THRESHOLD", "0.90"))
SECTION_WARNING_THRESHOLD  = float(os.getenv("SECTION_WARNING_THRESHOLD", "0.40"))
DEFAULT_MODEL_CONTEXT_WINDOW = int(os.getenv("MODEL_CONTEXT_WINDOW", "32768"))

_CHARS_PER_TOKEN = 4  # ← hardcoded inline, no env var
```

**Env vars en Railway**: ninguna de estas 4 está configurada en Railway → corren con defaults del código.

| Variable | Default código | Valor Railway |
|---|---|---|
| `CONTEXT_WARNING_THRESHOLD` | 0.80 | no configurado → 0.80 |
| `CONTEXT_CRITICAL_THRESHOLD` | 0.90 | no configurado → 0.90 |
| `SECTION_WARNING_THRESHOLD` | 0.40 | no configurado → 0.40 |
| `MODEL_CONTEXT_WINDOW` | 32768 | no configurado → 32768 |
| `CONTEXT_CHARS_PER_TOKEN` | — (hardcoded=4) | no configurado |

`_CHARS_PER_TOKEN = 4` es un bug menor: debería ser configurable (ver 03_bugs.md). El valor 4 es la misma heurística usada en `generation.py:325` (`len(system_prompt) // 4`), por lo que es consistente con el resto del pipeline.

---

### Sección 3: `_chars_to_tokens` (L29–30)

```python
def _chars_to_tokens(chars: int) -> int:
    return max(0, chars // _CHARS_PER_TOKEN)
```

Simple y seguro. `max(0, ...)` previene negativos si `chars` es negativo (no debería ocurrir, pero es defensivo). Privada (`_`), no expuesta.

---

### Sección 4: `analyze_token_distribution` (L33–142)

**Flujo principal (L62–138):**

1. **L64–70**: Itera `section_sizes` dict, excluye secciones con `char_count <= 0`. No muta el dict original.
2. **L73–78**: Suma chars de todos los `history_messages["content"]`. Seguro con `isinstance(msg, dict)` y `.get("content", "")`.
3. **L81**: Calcula tokens del `system_prompt` completo (post-truncation — refleja el tamaño real que verá el LLM).
4. **L85**: `total_tokens = system_prompt_tokens + history_tokens`. El system_prompt ya incluye todas las secciones ensambladas, por lo que `section_tokens` son una sub-vista del mismo presupuesto.
5. **L88–92**: Calcula `pct_of_total` para cada sección y el historial.
6. **L95–98**: Identifica la sección más grande, incluyendo `history` como sección virtual.
7. **L100**: `usage_ratio = total_tokens / model_context_window`.
8. **L103–106**: `over_section_threshold`: True si cualquier sección >= `total * SECTION_WARNING_THRESHOLD`.
9. **L108–119**: Construye y retorna el dict `analytics`.
10. **L122–136**: Emite log `[TokenAnalytics] Distribution: ...` con el desglose compacto.
11. **L138**: `return analytics`.

**Observación crítica**: `system_prompt` es sólo leído por `len()`. No hay ningún `system_prompt = ...` dentro de la función. ✅

**Sección de error (L140–142):**
```python
except Exception as exc:
    logger.debug("[TokenAnalytics] analyze_token_distribution failed: %s", exc)
    return {}
```
Bug: `logger.debug` hace que los errores sean invisibles en producción (nivel por defecto es INFO). Ver 03_bugs.md.

---

### Sección 5: `check_context_health` (L145–212)

**Flujo:**

1. **L155**: Guard `if not analytics: return []` — seguro con `{}` vacío.
2. **L158–163**: Extrae campos del dict analytics.
3. **L166–175**: CRITICAL si `usage_ratio >= 0.90` → append warning con `level="critical"`.
4. **L177–186**: WARNING si `usage_ratio >= 0.80` (y no critical) → append con `level="warning"`.
5. **L189–210**: Section warning si `over_section_threshold` y no critical — encuentra qué secciones superan el umbral, incluye `history`.
6. **L212**: `return warnings`.

**Observación**: La función retorna una lista de dicts. El caller en `generation.py` itera esta lista y la convierte en logs. El valor de retorno no se asigna a ninguna variable que influya en el prompt o en la generación. ✅

---

## Callsite: `generation.py:341–358`

```python
# G3+G4: Token distribution analytics + context health warnings (observability only)
try:
    from core.dm.context_analytics import analyze_token_distribution, check_context_health
    _analytics = analyze_token_distribution(
        section_sizes=_section_sizes,
        system_prompt=system_prompt,
        history_messages=history,
    )
    for _w in check_context_health(_analytics):
        _lvl = _w["level"]
        if _lvl == "critical":
            logger.error("[ContextHealth] CRITICAL: %s", _w["message"])
        elif _lvl == "warning":
            logger.warning("[ContextHealth] WARNING: %s", _w["message"])
        else:
            logger.info("[ContextHealth] INFO: %s", _w["message"])
except Exception as _analytics_err:
    logger.debug("[TokenAnalytics] Skipped: %s", _analytics_err)
```

**Contexto pre-callsite (L295–339)**:

- `_section_sizes` se construye en L326–335 como `{k: len(v) for k, v in [...] if v}` — sólo chars, inmutable.
- `system_prompt` en L319 ya está truncado (`_smart_truncate_context` si supera `_MAX_CONTEXT_CHARS`).
- `history` viene del argumento de la función `generate_response`.

**Contexto post-callsite (L360+)**:

- L360–367: G5 Cache boundary metrics (otro módulo de observabilidad, sólo logs).
- L369+: LLM generation (`Flash-Lite → GPT-4o-mini`).

**`_analytics` no se usa después del bloque** — sólo dentro del loop de logging. ✅

---

## Verificación: el try/except NO oculta errores críticos

El `try/except Exception` en L342–358 envuelve **exclusivamente** el bloque de analytics. Los errores del ensamblado del prompt (anteriores a L341) y la llamada LLM (posteriores a L359) están fuera de este bloque y se propagan normalmente.

Sólo una excepción dentro de `analyze_token_distribution` o `check_context_health` quedaría silenciada. Dado que ambas funciones tienen sus propios `try/except` internos que retornan `{}` / `[]`, en la práctica el `except` exterior nunca se dispara salvo un `ImportError` del módulo.

**Riesgo**: Un `ImportError` (si el archivo fuera eliminado) sería silenciado con `logger.debug`. Esto es aceptable dado que el módulo es de observabilidad pura y no afecta el output.

---

## Flujo de datos completo

```
generation.py:326-335
  _section_sizes = {k: len(v) for k, v in [...] if v}
        ↓ (read-only)
context_analytics.py:analyze_token_distribution()
  ├── lee section_sizes (dict de ints) → no muta
  ├── lee system_prompt (string) → sólo len()
  ├── lee history_messages → sólo len(content)
  └── retorna analytics dict
        ↓
context_analytics.py:check_context_health()
  ├── lee analytics dict → no muta
  └── retorna list de warning dicts
        ↓
generation.py:349-356
  for _w in warnings → logger.error/warning/info solamente
        ↓
generation.py:369+
  LLM generation ← INALTERADO
```

**Ningún dato fluye desde `context_analytics` hacia el LLM.** ✅
