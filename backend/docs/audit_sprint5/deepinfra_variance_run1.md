# DeepInfra Variance Sesión 1 (Día 1) — Reporte Final

**Worker:** DI-VAR  
**Branch:** `worker/deepinfra-variance`  
**Fecha:** 2026-04-20  
**Estado:** ✅ COMPLETADO

---

## Config Sesión 1

| Parámetro | Valor |
|-----------|-------|
| Provider | `deepinfra` (directo) |
| Model | `google/gemma-4-31B-it` |
| Runs internos | 3 × 50 casos |
| Flags | `--multi-turn --v4-composite --v5` |
| Pipeline | P0+P1, 23 sistemas |
| Save-as | `di_variance_run1_20260420_1329` |
| Duración total | ~2.5h (13:29–16:00 aprox.) |

**Nomenclatura:** "Sesión 1" = este archivo. Los 3 "runs" son internos al script (repeticiones para estabilidad intra-sesión). La varianza inter-sesión se mide entre días (sesión 1 hoy, sesión 2 mañana, sesión 3 pasado mañana).

---

## Resultados Sesión 1

### v5_composite (métrica principal)

**v5_composite = 65.7**

| Dimensión | Score |
|-----------|-------|
| S1 Style Fidelity | 69.6 |
| S2 Response Quality | 46.5 |
| S3 Strategic Alignment | 55.9 |
| S4 Adaptation | 66.8 |
| J_new (Multi-turn) | 67.8 |
| J6 | 100.0 |
| K Context Retention | 80.2 |
| G5 | 85.0 |
| L | 65.5 |
| H Indistinguishability | 78.0 |
| B Persona Fidelity | 58.2 |

H1 Turing Test Rate: **64%** (32/50 casos superan el Turing test)

### v4 composites internos (3 runs)

| Run interno | Composite v4 | Pipeline time |
|-------------|-------------|--------------|
| 1/3 | 64.63 | 370.7s |
| 2/3 | 64.98 | 347.1s |
| 3/3 | 63.97 | 321.5s |
| **media** | **64.53** | 346.4s avg |
| **σ intra-sesión** | **0.419** | — |

### MT scoring (5 conversaciones)

| Conv | mt_score |
|------|---------|
| 1/5 | 67.3 |
| 2/5 | 75.1 |
| 3/5 | 72.9 |
| 4/5 | 76.5 |
| 5/5 | 69.6 |
| **media** | **72.3** |

---

## Calidad del run

### Errores de pipeline
**0 errores** (0/50 casos con `[ERROR` en bot_response). Run limpio.

### Latencia

| Fase | Latencia |
|------|---------|
| Pipeline (DI directo, net excl. 3s delay) | ~4.0s/call (mediana) |
| v5 judge (Qwen3-30B-A3B vía DI) | ~14.3s/case (714.3s / 50) |
| Conectividad inicial (test) | 1.19s |

Desglose latencia pipeline por run:
- Run 1: (370.7 - 49×3) / 50 = 4.47s/call
- Run 2: (347.1 - 49×3) / 50 = 4.00s/call
- Run 3: (321.5 - 49×3) / 50 = 3.49s/call
- Tendencia decreciente: posible warm-up de conexión en run 1.

---

## Comparación DeepInfra vs OpenRouter

| Métrica | DeepInfra (sesión 1) | OpenRouter (distill_AB_OFF) | Delta |
|---------|---------------------|----------------------------|-------|
| v5_composite | **65.7** | 66.4 | -0.7 |
| S1 | 69.6 | 72.3 | -2.7 |
| S2 | 46.5 | 47.0 | -0.5 |
| S3 | 55.9 | 64.6 | -8.7 |
| S4 | 66.8 | 66.9 | -0.1 |
| H | 78.0 | 72.0 | +6.0 |
| B | 58.2 | 57.8 | +0.4 |
| K | 80.2 | 72.5 | +7.7 |

**Nota:** S3 (Strategic Alignment) -8.7 es la divergencia más llamativa. Puede ser varianza normal o diferencia real entre proveedores. Necesita sesiones 2-3 para confirmar.

v5_composite delta de -0.7 está dentro del ruido conocido (±3-4 OpenRouter). **Indistinguible** en una sola sesión.

---

## Gate Decision

**σ_v4 intra-sesión = 0.419 < umbral 1.0 → GATE PASS**

DeepInfra es estable intra-sesión. El protocolo de 3 días puede continuar.

- **Sesión 2: 2026-04-21** — ver `deepinfra_variance_protocol.md`
- **Sesión 3: 2026-04-22** — ver `deepinfra_variance_protocol.md`

La conclusión inter-sesión (σ entre días) se calcula tras sesión 3.

---

## Datos técnicos

```json
{
  "provider": "deepinfra",
  "model": "google/gemma-4-31B-it",
  "v5_composite": 65.7,
  "v4_composites": [64.63, 64.98, 63.97],
  "v4_mean": 64.53,
  "sigma_v4_intra": 0.419,
  "mt_mean": 72.3,
  "h1_turing_rate": 64.0,
  "pipeline_errors": 0,
  "latency_pipeline_net_median_s": 4.0,
  "latency_v5judge_per_case_s": 14.3,
  "v5judge_model": "Qwen/Qwen3-30B-A3B"
}
```
