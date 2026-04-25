# CCEE-Mini Correlación Validation

**Fecha:** 2026-04-25
**Branch:** validation/ccee-mini-correlation
**Método:** retrospective bootstrap sobre per-case data existente

---

## Pregunta

¿Puede CCEE-Mini (20 cases × 1 run, ~$0.10) servir como gate intermedio entre
fases de curriculum en Sprint 7, si tiene correlación Pearson r ≥ 0.8 con CCEE Full
(50 cases × 3 runs, ~$1.50)?

---

## Setup

| Parámetro | Valor |
|---|---|
| CCEE-Mini | 20 cases × 1 run |
| CCEE Full | 50 cases × 3 runs |
| Conditions | BL_pipeline_c0bcbd73 (S11=67.7) + FT_sprint6 (66.4) |
| Dimensiones analizadas | S1, S2, S3, S4, J_old, J_new, J6, K, G5, L, H, B, Composite |
| Seed Mini | 3407 |
| Bootstrap N | 1000 subsets |

**Método:** Las dimensiones "variables" (S1-S4, B) se computan como promedio de
N per-case scores (50 para Full, 20 para Mini). Las dimensiones "fijas" (J6, K, L,
H, G5, J_old, J_new) provienen de 5 MT conversations — son **idénticas** entre
Mini y Full independientemente del `--cases N`.

Los datos provienen de las mediciones reales existentes (per_case_records de los
archivos JSON CCEE), no de datos sintéticos.

---

## Resultados

### Pearson Correlation

| Métrica | Valor | p-value | N puntos |
|---|---|---|---|
| r (todas las dims) | **0.959** | p<0.001 | 26 |
| r (solo dims variables) | **0.574** | p=0.083 | 10 |
| Bootstrap mean r (var. dims) | **0.571** | — | — |
| Bootstrap CI 95% (var. dims) | **[0.396, 0.734]** | — | 1000 muestras |

> **Nota:** r=0.959 está artificialmente inflado porque 7 de 12 dimensiones son
> "fijas" (idénticas entre Mini y Full). El número honesto es r=0.574.

### Por dimensión (seed=3407)

| Dimensión | BL Mini | BL Full | FT Mini | FT Full | Δ BL | Δ FT | Tipo |
|---|---|---|---|---|---|---|---|
| S1 | 56.6 | 60.5 | 65.7 | 82.9 | -3.9 | **-17.2** | variable |
| S2 | 63.7 | 65.2 | 66.3 | 65.9 | -1.5 | +0.4 | variable |
| S3 | 64.8 | 72.3 | 50.4 | 62.0 | -7.6 | **-11.6** | variable |
| S4 | 62.3 | 63.5 | 65.2 | 62.4 | -1.2 | +2.8 | variable |
| B | 60.8 | 63.0 | 56.3 | 53.3 | -2.2 | +3.0 | variable |
| J_old | 52.5 | 52.5 | 55.5 | 55.5 | ±0 | ±0 | **fija** |
| J_new | 65.6 | 65.6 | 61.1 | 61.1 | ±0 | ±0 | **fija** |
| J6 | 45.0 | 45.0 | 25.0 | 25.0 | ±0 | ±0 | **fija** |
| K | 77.7 | 77.7 | 60.6 | 60.6 | ±0 | ±0 | **fija** |
| G5 | 100.0 | 100.0 | 100.0 | 100.0 | ±0 | ±0 | **fija** |
| L | 61.9 | 61.9 | 63.6 | 63.6 | ±0 | ±0 | **fija** |
| H | 82.0 | 82.0 | 68.0 | 68.0 | ±0 | ±0 | **fija** |
| **Composite** | **65.5** | **67.7** | **62.2** | **66.4** | -2.2 | -4.2 | variable |

### Bootstrap (1000 subsets, dims variables)

| Estadístico | Valor |
|---|---|
| Mean r | 0.571 |
| Median r | 0.580 |
| CI 95% | [0.396, 0.734] |
| % muestras con r ≥ 0.8 | **0.2%** |
| % muestras con r ≥ 0.6 | 39.4% |

---

## Análisis de Causa Raíz

La baja correlación en dims variables se debe principalmente a **S1 (style fidelity)**:

- `S1 FT_mini = 65.7` vs `S1 FT_full = 82.9` → error de **-17.2 puntos**
- S1 es la dimensión más variable per-case porque depende del estilo léxico de cada
  conversación seleccionada.
- Con N=20 hay alta probabilidad de que el subset no sea representativo de la
  distribución real de S1 scores.

Secundariamente, **S3 (coherencia lógica)** también tiene alta varianza:
- `S3 FT_mini = 50.4` vs `S3 FT_full = 62.0` → error de **-11.6 puntos**

S2, S4, B tienen error bajo (<3 puntos) y son confiables a N=20.

---

## Veredicto

```
r (dims variables, seed=3407) = 0.574 < 0.6
Bootstrap CI 95%: [0.396, 0.734]
% samples ≥ 0.8: 0.2%
```

🔴 **CCEE-Mini NO VÁLIDO como gate entre fases Sprint 7.**

El threshold de r ≥ 0.8 requerido para "gate" NO se alcanza en ninguno de los
1000 bootstrap samples (solo 0.2%). El r mediano (~0.58) es apenas significativo
(p=0.08 para N=10 puntos).

La causa fundamental: CCEE-Mini cambia solo las dims `--cases N` (S1-S4, B) pero
no cambia las dims de MT conversations (J6, K, L, H). Con N=20 per-case, S1 y S3
tienen demasiado ruido de muestreo para ser confiables como gate.

---

## Implicaciones Sprint 7

**Recomendación:** Eliminar el concepto de "CCEE-Mini gate" del plan Sprint 7.

**Opciones concretas:**

| Opción | Descripción | Coste | Señal |
|---|---|---|---|
| A | CCEE Full única vez al final de cada fase ($1.50) | $1.50×3 = $4.50 | ✅ Fiable |
| B | CCEE Full 1-run como señal rápida ($0.50) + Full 3-run al final | +$0.50 por fase | 🟡 Marginal |
| C | Eliminar intermediate gates, solo medir al final del curriculum | $1.50 total | ✅ Más económico |

> Recomendación: Opción A o C. CCEE-Mini no ofrece una señal estadísticamente
> fiable para tomar decisiones de go/no-go entre fases.

**El script `03b_ccee_mini.sh` se mantiene** para uso exploratorio (debugging
direccional, verificar si una run fue catastrófica), pero no debe usarse para
decisiones de gate.

---

## Datos brutos

- `measurements/validation/ccee_mini_correlation/raw_correlation.json`
- BL source: `tests/ccee_results/iris_bertran/bl_pipeline_doc_d_c0bcbd73_20260425_1729.json`
- FT source: `tests/ccee_results/iris_bertran/ft_sft_20260425_0130.json`
