# context_analytics — Plan de medición

## Tipo de medición

**OBSERVABILIDAD** — NO CCEE.

Confirmado SIN_EFECTO_RUNTIME: el módulo no produce output al usuario, no modifica el prompt, no afecta la generación LLM. No existe variante A/B ni experimento causal posible. No hay score de calidad que medir.

---

## Reclasificación formal

```
Pipeline DM: 50 → 49 sistemas
context_analytics eliminado del inventario de pipeline DM
Nuevo hogar: Capa Observabilidad
```

La capa Observabilidad agrupa módulos que leen el estado del pipeline y emiten señales de diagnóstico sin participar en la generación de respuestas.

---

## Métricas a verificar post-deploy

### Gate 1: Tests

```bash
python3 -m pytest tests/test_context_analytics.py -v
# Esperado: 20/20 PASS
```

### Gate 2: Logs en Railway

Verificar que los logs `[TokenAnalytics]` se emiten correctamente en cada request DM:

```bash
railway logs -n 200 2>&1 | grep "\[TokenAnalytics\]"
```

**Formato esperado**:
```
[TokenAnalytics] Distribution: rag=850(45%), style=600(32%), memory=200(11%), history=240(13%) | Total: 1890/32768 (6%) | Largest: rag(45%)
```

Si aparece `[TokenAnalytics] Skipped:` → hay un error en el módulo (ahora visible gracias a Mejora 3).

### Gate 3: Métricas Prometheus

Si Railway expone el endpoint `/metrics`:

```bash
curl -s https://www.clonnectapp.com/metrics | grep context_
```

**Esperado**:
```
# HELP context_tokens_total Cumulative estimated tokens measured by context_analytics
# TYPE context_tokens_total counter
context_tokens_total_total N

# HELP context_health_warnings_total Number of context health warnings emitted
# TYPE context_health_warnings_total counter
context_health_warnings_total_total{level="warning"} N
context_health_warnings_total_total{level="critical"} N
```

`N` debe incrementar con cada request. Si `context_health_warnings_total{level="critical"}` > 0 de forma sostenida, indica que el prompt está creciendo peligrosamente hacia el límite del modelo.

---

## Alertas recomendadas (futuro)

| Condición | Acción sugerida |
|---|---|
| `context_health_warnings_total{level="critical"}` > 5/hora | Investigar qué sección crece (ver logs `[ContextHealth] CRITICAL`) |
| `context_tokens_total` / request > 8000 tokens (~32K chars) | Review de truncation strategy en `generation.py:_smart_truncate_context` |
| `[TokenAnalytics] Skipped:` en logs | Bug en el módulo — activar DEBUG temporalmente |

---

## Gates KEEP

| Gate | Criterio | Estado |
|---|---|---|
| Tests 20/20 | `pytest tests/test_context_analytics.py` → 20 passed | ✅ PASS |
| Syntax | `ast.parse()` OK en ambos archivos modificados | ✅ PASS |
| Comportamiento Railway | Todos los defaults iguales → cero cambio en output DM | ✅ CONFIRMADO |
| Métricas emitidas | `_PROMETHEUS_AVAILABLE=True` en local, Railway tiene `prometheus_client>=0.19.0` | ✅ LISTO |

---

## Notas de reclasificación

La reclasificación de `context_analytics` de "pipeline DM" a "Observabilidad" NO implica:
- Eliminar el módulo (mantener activo en Railway)
- Deshabilitar el logging (mantener activo)
- Añadir flag `ENABLE_CONTEXT_ANALYTICS` (innecesario — el `try/except` ya lo hace inocuo si falla)

Implica únicamente:
- Excluir del conteo de sistemas del pipeline DM (50 → 49)
- Documentar en `docs/forensic/context_analytics/` como SIN_EFECTO_RUNTIME
- No incluir en futuras evaluaciones CCEE de calidad de respuesta
