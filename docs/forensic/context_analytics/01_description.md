# context_analytics — Descripción y declaración SIN_EFECTO_RUNTIME

## Sistema

| Campo | Valor |
|---|---|
| Archivo | `core/dm/context_analytics.py` |
| LOC | 212 |
| Funciones públicas | `analyze_token_distribution`, `check_context_health` |
| Capa pipeline | **OBSERVABILIDAD** (POST-ASSEMBLY) |
| Estado pipeline DM | **Excluido** — reclasificado en este PR (50 → 49) |

---

## Qué mide

`context_analytics` recibe el prompt ya ensamblado y calcula:

1. **Token distribution** (`analyze_token_distribution`): desglosa cuántos tokens ocupa cada sección del system prompt (`style`, `rag`, `memory`, `fewshot`, `dna`, `state`, `kb`, `advanced`) y el historial de conversación, expresando cada uno como porcentaje del total. Usa la heurística `chars / 4 = tokens` (la misma que el resto del pipeline).

2. **Context health warnings** (`check_context_health`): emite avisos cuando:
   - Uso global ≥ 80 % (`CONTEXT_WARNING_THRESHOLD`) → log `WARNING`
   - Uso global ≥ 90 % (`CONTEXT_CRITICAL_THRESHOLD`) → log `ERROR`
   - Una sección domina ≥ 40 % del presupuesto (`SECTION_WARNING_THRESHOLD`) → log `WARNING`

Todos los avisos se emiten exclusivamente como log entries con prefijo `[TokenAnalytics]` / `[ContextHealth]`.

---

## Valor

Observabilidad pura: permite detectar cuándo el prompt del clone se acerca a la ventana de contexto del modelo (`MODEL_CONTEXT_WINDOW`, default 32 768 tokens para Gemini Flash-Lite). Sin este módulo, un prompt que crece silenciosamente degradaría las respuestas sin ninguna señal en los logs.

No tiene lógica de negocio. No recorta el prompt. No cambia ninguna variable del pipeline.

---

## Declaración formal SIN_EFECTO_RUNTIME

```
SISTEMA: context_analytics
CLASIFICACIÓN: SIN_EFECTO_RUNTIME
FECHA: 2026-04-23
```

Verificación técnica punto por punto:

| Criterio | Evidencia | Resultado |
|---|---|---|
| 0 mutaciones del prompt | `system_prompt` recibido como argumento, nunca reasignado ni devuelto | ✅ CONFIRMADO |
| 0 mutaciones de `system_prompt` | Grep: ningún `system_prompt =` fuera del scope de `generation.py` antes de la llamada | ✅ CONFIRMADO |
| 0 output al usuario | No hay `return` que llegue al caller que afecte la generación; el loop `for _w in check_context_health(...)` sólo llama `logger.*` | ✅ CONFIRMADO |
| Sólo logger calls | `logger.info`, `logger.warning`, `logger.error` en `context_analytics.py`; `logger.debug` en el `except` del callsite | ✅ CONFIRMADO |
| Downstream = NINGUNO | Grep: ningún módulo importa `check_context_health` ni usa su valor de retorno para lógica | ✅ CONFIRMADO |
| Prometheus = NINGUNO (actual) | No hay `prometheus_client` ni contador Prometheus en la versión actual | ✅ CONFIRMADO (mejora propuesta en Phase 5) |
| Flag env | Ningún `ENABLE_CONTEXT_ANALYTICS` — activado incondicionalmente, pero dentro de `try/except` que lo hace inerte si falla | ✅ CONFIRMADO |

**Veredicto: el sistema `context_analytics` no tiene efecto en el output del pipeline DM en ninguna ruta de ejecución.**

---

## Fase pipeline

```
[Prompt assembly] → [system_prompt ensamblado]
                         ↓
              [context_analytics ← POST-ASSEMBLY]
                         ↓
              logger.info/warning/error solamente
                         ↓
              [LLM generation] ← NO AFECTADO
```

`context_analytics` se ejecuta en `generation.py:342-358`, después del ensamblado del prompt (`_section_sizes`, `system_prompt`) y antes de la llamada LLM. Sin embargo, al estar envuelto en `try/except Exception`, cualquier error en él es silenciado y la generación continúa sin interrupción.

---

## Recomendación

**SACAR de inventario pipeline DM.**

Mover a capa **Observabilidad** junto con:
- Futuras métricas Prometheus (`context_tokens_total`, `context_health_warnings_total{level}`)
- Otros módulos de logging estructurado que no participan en la generación

Pipeline DM actualizado: **50 → 49 sistemas**.

El módulo debe mantenerse activo en producción —tiene valor de observabilidad real— pero no debe contarse como parte del pipeline de generación DM.
