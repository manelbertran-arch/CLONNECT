# context_analytics — Mejoras implementadas

## Criterios

Módulo SIN_EFECTO_RUNTIME → mejoras limitadas a:
1. Eliminar hardcodings menores
2. Mejorar visibilidad de errores en producción
3. Añadir métricas Prometheus (única upgrade funcional)

**No se toca**: lógica de thresholds, fórmula de tokens, estructura del dict analytics, firma de funciones públicas.

---

## Mejora 1: `_CHARS_PER_TOKEN` → env var `CONTEXT_CHARS_PER_TOKEN`

**Cambio** (`context_analytics.py:26`):
```python
# Antes
_CHARS_PER_TOKEN = 4

# Después
_CHARS_PER_TOKEN = int(os.getenv("CONTEXT_CHARS_PER_TOKEN", "4"))
```

**Por qué**: la heurística chars→tokens es dependiente del tokenizer del modelo. Gemini Flash-Lite, GPT-4o-mini, y modelos futuros pueden tener ratios distintos. Exponer como env var permite ajustar sin redeploy.

**Railway**: no requiere configuración — default=4 mantiene comportamiento idéntico al anterior.

---

## Mejora 2: `logger.debug` → `logger.warning` en except interno

**Cambio** (`context_analytics.py:141` → nueva línea equivalente):
```python
# Antes
except Exception as exc:
    logger.debug("[TokenAnalytics] analyze_token_distribution failed: %s", exc)

# Después
except Exception as exc:
    logger.warning("[TokenAnalytics] analyze_token_distribution failed: %s", exc)
```

**Por qué**: En Railway el nivel de log efectivo es INFO. `logger.debug` hace que un fallo en el módulo de observabilidad sea completamente invisible — la observabilidad fallaría en silencio.

---

## Mejora 3: `logger.debug` → `logger.warning` en callsite

**Cambio** (`generation.py:358`):
```python
# Antes
except Exception as _analytics_err:
    logger.debug("[TokenAnalytics] Skipped: %s", _analytics_err)

# Después
except Exception as _analytics_err:
    logger.warning("[TokenAnalytics] Skipped: %s", _analytics_err)
```

**Por qué**: mismo razonamiento que Mejora 2 — si el bloque falla (e.g., `ImportError` por renombrar el módulo), debe haber señal en los logs.

---

## Mejora 4: Métricas Prometheus

**Dos nuevos counters** en `context_analytics.py`:

```python
_CONTEXT_TOKENS_TOTAL = Counter(
    "context_tokens_total",
    "Cumulative estimated tokens measured by context_analytics",
)

_CONTEXT_HEALTH_WARNINGS_TOTAL = Counter(
    "context_health_warnings_total",
    "Number of context health warnings emitted",
    ["level"],
)
```

**Dónde se incrementan**:
- `_CONTEXT_TOKENS_TOTAL.inc(total_tokens)` — al final de `analyze_token_distribution()` si `total_tokens > 0`
- `_CONTEXT_HEALTH_WARNINGS_TOTAL.labels(level=w["level"]).inc()` — por cada warning en `check_context_health()`

**Import pattern**: `try/except Exception` con `_PROMETHEUS_AVAILABLE = False` como fallback — idéntico al patrón de `core/metrics.py`. Graceful no-op si `prometheus_client` no está disponible.

**Deduplicación en reload**: `_get_or_create_counter()` consulta `_REGISTRY._names_to_collectors` por base name antes de crear el counter, evitando `ValueError: Duplicated timeseries` en reloads de test.

**Labels de `context_health_warnings_total`**:
| Label `level` | Cuándo |
|---|---|
| `warning` | `usage_ratio` entre 0.80–0.90, o sección domina >40% |
| `critical` | `usage_ratio` ≥ 0.90 |

---

## Tests añadidos (20 total, antes 18)

Dos tests nuevos en `tests/test_context_analytics.py`:

1. **`test_prometheus_counter_increments_on_valid_analytics`**: verifica que `context_tokens_total` incrementa al llamar `analyze_token_distribution()` con datos válidos.

2. **`test_prometheus_warning_counter_increments`**: verifica que `context_health_warnings_total{level=warning}` incrementa al llamar `check_context_health()` con un analytics al 83% de uso.

Ambos tests usan `pytest.skip` si `_PROMETHEUS_AVAILABLE` es False (entorno sin `prometheus_client`).

---

## Resultado

```
Tests: 20/20 PASS
Syntax: context_analytics.py OK, generation.py OK
Comportamiento en Railway: IDÉNTICO (todos los defaults son iguales)
Nueva observabilidad: context_tokens_total, context_health_warnings_total{level}
```

**Ninguna mejora tiene efecto en el output del pipeline DM.** El módulo permanece SIN_EFECTO_RUNTIME.
