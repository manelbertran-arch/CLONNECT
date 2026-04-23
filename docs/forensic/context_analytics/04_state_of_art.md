# context_analytics — Estado del arte (breve)

## Contexto del search

Dos búsquedas ligeras:
1. "context window health monitoring LLM apps observability 2025 2026"
2. "prompt length observability Prometheus metrics LLM production token tracking"

---

## Hallazgos relevantes

### 1. Monitoreo de longitud de prompt — práctica estándar en producción

El patrón de `context_analytics` (medir tokens por sección del prompt y emitir alertas cuando se acerca al límite de contexto) está bien documentado en la literatura de LLM observability.

**Patrones identificados:**
- **Histograma de longitud de request**: herramientas como vLLM exponen `vllm:request_prompt_tokens_bucket` como Prometheus Histogram. El equivalent en Clonnect sería `context_tokens_total` (counter) o un Histogram.
- **Monitor average tokens per request**: "[Increases signal] prompt bloat or unnecessary context, which directly relates to context window efficiency." — práctica estándar según Braintrust/Maxim (2026).
- **Threshold alerting**: alertar cuando el uso supera 80/90% del context window es un patrón explícito en liteLLM Prometheus metrics y vLLM.

**Diferencia con `context_analytics`**: Los sistemas comerciales (Langfuse, Helicone, Braintrust) operan a nivel de proxy — interceptan la llamada API y miden la respuesta del proveedor. `context_analytics` opera más temprano (post-assembly, pre-llamada) y mide la **composición interna** del prompt, lo que es más útil para diagnóstico de secciones específicas.

### 2. Prometheus + OpenTelemetry como estándar

El stack estándar en producción (2026):
```
[app code] → Prometheus counters/histograms → [/metrics endpoint] → Grafana
```

vLLM, liteLLM, y TGI todos exponen `/metrics` scrapeables. La propuesta de Phase 5 (añadir `prometheus_client` counters en `context_analytics`) sigue exactamente este patrón.

**Métricas clave propuestas por el estado del arte para prompt health:**

| Métrica | Tipo Prometheus | Equivalente en context_analytics |
|---|---|---|
| `llm_request_prompt_tokens` | Histogram | `context_tokens_total` (a añadir) |
| `llm_context_usage_ratio` | Gauge | derivable de `usage_ratio` |
| `llm_context_health_warnings` | Counter{level} | `context_health_warnings_total{level}` (a añadir) |

### 3. Design principles — CHI 2025

Un estudio con 30 desarrolladores LLM (CHI 2025) identificó 4 principios para observabilidad efectiva:
1. **Awareness** — visibilizar el comportamiento del modelo
2. **Monitoring** — feedback en tiempo real
3. **Intervention** — capacidad de actuar al detectar el problema
4. **Operability** — mantenibilidad a largo plazo

`context_analytics` cubre (1) y (2). No cubre (3) — decisión correcta para un módulo SIN_EFECTO_RUNTIME. Cubre (4) parcialmente (buenos tests, env vars configurables).

---

## Repos de referencia

1. **vLLM metrics** (`vllm-project/vllm`, `vllm/engine/metrics.py`) — referencia para estructura de métricas Prometheus en LLM inference. Patrón: Histogram para latencias, Counter para tokens acumulados, Gauge para estado del sistema.

2. **liteLLM Prometheus plugin** (`BerriAI/litellm`, docs `/proxy/prometheus`) — expone `litellm_tokens_used_total{model, team_id}` como Counter, y `litellm_input_tokens` como Histogram. El pattern `Counter{label}` para `context_health_warnings_total{level="warning"}` es idéntico.

---

## Conclusión para context_analytics

El diseño actual (logging estructurado + thresholds configurables) es correcto y alineado con el estado del arte. La única brecha vs. el estándar de producción es la ausencia de métricas Prometheus (propuesta en Phase 5). El formato de los logs `[TokenAnalytics]` / `[ContextHealth]` es parseable por Loki/Datadog si se añade en el futuro.

---

**Fuentes consultadas:**
- [Monitor LLM Inference in Production (2026): Prometheus & Grafana](https://www.glukhov.org/observability/monitoring-llm-inference-prometheus-grafana/)
- [vLLM Metrics Design](https://docs.vllm.ai/en/stable/design/metrics/)
- [liteLLM Prometheus metrics](https://docs.litellm.ai/docs/proxy/prometheus)
- [OpenTelemetry LLM Observability intro](https://opentelemetry.io/blog/2024/llm-observability/)
- [Braintrust: best LLM monitoring tools 2026](https://www.braintrust.dev/articles/best-llm-monitoring-tools-2026)
