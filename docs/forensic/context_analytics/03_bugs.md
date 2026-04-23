# context_analytics — Bugs detectados

Severidad: todos **BAJA** (módulo de observabilidad, sin efecto en output).

---

## Bug 1: `_CHARS_PER_TOKEN = 4` hardcoded (L26)

**Archivo**: `core/dm/context_analytics.py:26`

```python
_CHARS_PER_TOKEN = 4  # ← no es configurable
```

**Problema**: La heurística chars→tokens es configurable en otros módulos de observabilidad (e.g., `titoken` usa modelos distintos). Si el modelo cambia (Flash-Lite tiene tokenizer diferente a GPT-4o), el valor 4 puede sobreestimar o subestimar el uso real.

**Severidad**: Baja — la misma heurística `// 4` se usa en `generation.py:325`, por lo que es internamente consistente.

**Fix propuesto**: Exponer como env var `CONTEXT_CHARS_PER_TOKEN` (default 4). Ver 05_optimization.md.

---

## Bug 2: `try/except` demasiado amplio en el callsite (generation.py:342–358)

**Archivo**: `core/dm/phases/generation.py:342–358`

```python
try:
    from core.dm.context_analytics import ...
    ...
except Exception as _analytics_err:
    logger.debug("[TokenAnalytics] Skipped: %s", _analytics_err)
```

**Problema**: El `except Exception` captura todo, incluyendo `ImportError`, `MemoryError`, `KeyboardInterrupt` (parcialmente). En la práctica esto es aceptable porque el módulo es observabilidad pura, pero dificulta el diagnóstico si el módulo falla por un bug real.

**Severidad**: Baja — por diseño intencional (no debe bloquear la generación). El riesgo real es que un `ImportError` se silencie completamente.

**Fix propuesto**: Acotar a `except (ImportError, Exception)` con `logger.warning` en lugar de `logger.debug`. Ver 05_optimization.md.

---

## Bug 3: `logger.debug` en el `except` del callsite (generation.py:358)

**Archivo**: `core/dm/phases/generation.py:358`

```python
except Exception as _analytics_err:
    logger.debug("[TokenAnalytics] Skipped: %s", _analytics_err)  # ← debug, invisible en prod
```

**Problema**: En Railway, el nivel de log efectivo es INFO (no DEBUG). Si `context_analytics` falla (por un bug de import o runtime), el error quedará completamente silenciado. No habrá señal en los logs de que el módulo de observabilidad está roto.

**Severidad**: Baja-media — el módulo es observabilidad, pero si falla siempre deberíamos saberlo.

**Fix propuesto**: Cambiar a `logger.warning`. Ver 05_optimization.md.

---

## Bug 4: `logger.debug` en el `except` interno de `analyze_token_distribution` (context_analytics.py:141)

**Archivo**: `core/dm/context_analytics.py:141`

```python
except Exception as exc:
    logger.debug("[TokenAnalytics] analyze_token_distribution failed: %s", exc)
    return {}
```

**Problema**: Mismo patrón — un error interno en la función de análisis (e.g., un `ZeroDivisionError` no previsto, un cambio de interfaz del dict) quedaría invisible en producción.

**Severidad**: Baja — el módulo es observabilidad, pero un fallo silencioso elimina el valor de la observabilidad.

**Fix propuesto**: Cambiar a `logger.warning`. Ver 05_optimization.md.

---

## Resumen

| # | Ubicación | Tipo | Severidad | Fix |
|---|---|---|---|---|
| 1 | `context_analytics.py:26` | Hardcoding inline | Baja | Env var `CONTEXT_CHARS_PER_TOKEN` |
| 2 | `generation.py:342-358` | `except` demasiado amplio | Baja | Mantener `except Exception`, cambiar log level |
| 3 | `generation.py:358` | `logger.debug` invisible en prod | Baja-media | `logger.warning` |
| 4 | `context_analytics.py:141` | `logger.debug` invisible en prod | Baja-media | `logger.warning` |

**Ningún bug afecta el output del pipeline DM.** Todos son de visibilidad de diagnóstico.
