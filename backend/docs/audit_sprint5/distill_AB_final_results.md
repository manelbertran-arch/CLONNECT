# Distill A/B Final Results — iris_bertran

**Fecha:** 2026-04-20  
**Branch:** feature/sprint5-distill-AB-treatment  
**Protocolo:** 50×3+MT (estándar)  
**Commit baseline:** 885fe454 / 4657fd99

---

## Contexto y motivación

### Historia del experimento

| Worker | Protocolo | Flag | Composite | Fecha |
|--------|-----------|------|-----------|-------|
| Worker I (ARC3 Phase 1) | 20×1 | OFF vs ON | OFF=67.6, ON=66.7, Δ=-0.9 | 2026-04-19 |
| Worker AA (A25 repro) | 50×3+MT | OFF | 68.9 | 2026-04-20 (ambiguo) |
| **P1 (este experimento)** | **50×3+MT** | **OFF** | **66.4** | **2026-04-20** |
| **P2 (este experimento)** | **50×3+MT** | **ON** | **65.7** | **2026-04-20** |

### Varianza conocida (aprendida Worker AA)
Worker AA reveló varianza OpenRouter **±3-4 puntos** en diferentes sesiones con el mismo código y commit (72.6 → 68.9 → 66.4 en días distintos). Por tanto, un delta debe ser **≥4 puntos** para considerarse señal real.

### Flags experimentales
- `USE_DISTILLED_DOC_D=true` (ON) / `false` (OFF)
- `USE_COMPACTION=false` en ambos
- `LLM_PRIMARY_PROVIDER=openrouter`, `OPENROUTER_MODEL=google/gemma-4-31b-it`

---

## Resultados

### v5 Composite (métrica canónica)

| | P1 OFF | P2 ON | Δ |
|---|---|---|---|
| **v5 Composite** | **66.4** | **65.7** | **-0.7** |
| v4 Composite | 64.8 | 65.5 | +0.7 |
| v4.1 Composite | 66.6 | 66.9 | +0.3 |

### Per-run (raw runs antes de v5 ajuste)

| Run | P1 OFF | P2 ON |
|-----|--------|-------|
| R1 | 62.16 | 68.42 |
| R2 | 63.30 | 66.04 |
| R3 | 64.32 | 67.13 |
| **Media** | **63.26** | **67.20** |

> Nota: Los per-run raw muestran ON > OFF (+3.9 media), pero el composite v5 final invierte ligeramente (-0.7) por el peso de H (Indistinguishability) y B (Persona Fidelity) que regresionan con distill ON.

---

## Dimensiones (v5)

| Dimensión | OFF | ON | Δ | Señal |
|-----------|-----|----|---|-------|
| S1 Style Fidelity | 72.3 | 75.7 | **+3.4** | ✅ mejora |
| S2 Response Quality | 47.0 | 47.6 | +0.6 | ➖ |
| S3 Strategic Alignment | 64.6 | 62.1 | -2.5 | ❌ |
| S4 Adaptation | 66.9 | 60.1 | **-6.8** | ❌ regresión notable |
| K Context Retention | 72.5 | 71.5 | -1.0 | ➖ |
| H Indistinguishability | 72.0 | 62.0 | **-10.0** | ❌ regresión notable |
| B Persona Fidelity | 57.8 | 56.3 | -1.5 | ➖ |
| G5 Persona Robustness | 80.0 | 80.0 | 0.0 | ➖ |
| J_new (MT Coherence) | 72.6 | 72.3 | -0.3 | ➖ |
| J_old | 29.5 | 57.6 | +28.1 | ✅ (peso 0.03, impacto mínimo) |
| J6 QA Consistency | 100.0 | 100.0 | 0.0 | ➖ |
| L (Reasoning/Tone) | 68.2 | 65.5 | -2.7 | ❌ |

**Mejoradas (>+0.5):** 3 (S1, S2, J_old)  
**Empeoradas (<-0.5):** 6 (S3, S4, H, B, J_new, L)

---

## Multi-Turn (MT)

| Métrica | OFF | ON | Δ |
|---------|-----|----|---|
| **MT Composite** | **73.1** | **72.6** | **-0.5** |
| K1 Context Retention | 57.3 | 59.3 | +2.0 |
| K2 Style Retention | 95.4 | 89.8 | -5.6 |
| J3 Prompt-to-Line | 86.5 | 89.5 | +3.0 |
| J5 Belief Drift | 70.0 | 65.0 | -5.0 |
| G5 Persona Robustness | 80.0 | 80.0 | 0.0 |
| L1 Persona Tone | 79.5 | 84.0 | +4.5 |
| L3 Action Justification | 60.0 | 50.0 | -10.0 |

---

## Veredicto calibrado por varianza

```
Varianza OpenRouter conocida:  ±3-4 puntos (inter-sesión)
Varianza esperada intra-día:   ±1-2 puntos
Delta v5 observado:            -0.7

Umbral señal real:             ≥ +4 para APPROVE
```

### ⚪ INDISTINGUIBLE

El delta v5 de **-0.7** está completamente dentro del ruido de medición. No hay evidencia de que distill mejore o empeore el composite agregado.

**Sin embargo, hay dos regresiones específicas significativas:**

1. **H Indistinguishability: -10.0 puntos** (72.0 → 62.0)  
   El clone con distill ON es más fácilmente identificable como bot en el Turing Test. Hipótesis: el distill "limpia" el doc_d eliminando irregularidades lingüísticas naturales (typos, code-switching, ellipsis) que son precisamente las que hacen al clone indistinguible de un humano.

2. **S4 Adaptation: -6.8 puntos** (66.9 → 60.1)  
   El clone con distill ON responde de forma menos adaptada al contexto conversacional. Hipótesis: el distill over-homogeniza el estilo, reduciendo la varianza situacional que Iris muestra en real.

---

## Recomendación

### NO activar `USE_DISTILLED_DOC_D=true` en Railway en este estado.

El distill v1 no aporta mejora medible en composite y introduce regresiones reales en H (Turing) y S4 (Adaptation), que son dos de las dimensiones más críticas para la experiencia de usuario.

---

## Propuestas iterate prompt distill v2

### Problema raíz identificado
El prompt distill actual comprime el doc_d pero pierde:
- **Marcadores de naturalidad:** typos intencionales, code-switching ES/CA, truncations, audio/imagen replies
- **Varianza situacional:** cómo Iris adapta tono según contexto (INTIMATE vs MEDIA vs EDGE_CASE)
- **Ejemplos de frontera:** los casos que definen los límites de la persona (qué dice en situaciones extremas)

### v2 ideas

| # | Propuesta | Target dim | Esperado |
|---|-----------|------------|---------|
| v2a | Añadir instrucción explícita: "preserve all code-switching, typos, audio/image reply patterns" | H +5 | Recuperar naturalidad |
| v2b | Preservar ejemplos por situación (INTIMATE/MEDIA/EXTRA/EDGE_CASE) en lugar de comprimir uniformemente | S4 +4 | Recuperar adaptación |
| v2c | Two-pass distill: pass 1 = comprimir hechos, pass 2 = expandir marcadores de voz | H+S4 | Ambos |
| v2d | Usar distilled_short (1368 chars) como sufijo/contexto adicional al doc_d completo, no como reemplazo | H+S4 | Probar primero |

### Recomendación inmediata v2d
Antes de reescribir el prompt, probar `distilled_short` como **contexto adicional** concatenado al doc_d completo (doc_d + "\n\n## Resumen comprimido:\n" + distilled_short). Esto añade señal sin quitar la riqueza del doc_d original. Coste: 0 iteraciones de distill.

---

## Archivos de referencia

- P1 OFF: `tests/ccee_results/iris_bertran/distill_AB_OFF_20260419_2214.json`
- P2 ON: `tests/ccee_results/iris_bertran/distill_AB_ON_20260420_1155.json`
- ARC3 Phase 1 (Worker I, 20×1): `docs/audit_sprint5/ARC3_phase1_distill_ccee_validation_results.md`
