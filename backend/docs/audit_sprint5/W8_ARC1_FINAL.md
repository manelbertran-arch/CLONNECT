# ARC1 — Medición Final Estado 6370ce82
**Date:** 2026-04-19  
**Run file:** `arc1_final_6370ce82_iris_20260419_0127.json`  
**Protocol:** CCEE v5.3 — 3×50 ST + 5×10 MT, Gemma-4-31B (OpenRouter), Qwen3-30B-A3B judge (DeepInfra)  
**Estado medido:** 8 gates (A1.4) + S4-proximity fix + rag ×1.4 (A1.5) + recalling=400 (revert A1.5-bis)

---

## 1. Tabla Comparativa Completa

| Métrica | Baseline | A1.3 (4 gates) | A1.5-bis (fallido) | **FINAL (6370ce82)** | Δ vs A1.3 |
|---------|----------|----------------|--------------------|----------------------|-----------|
| **v5 composite** | **69.5** | **70.6** | **66.9** | **67.3** | **-3.3** ❌ |
| S1 style fidelity | 69.4 | 72.4 | 69.0 | 69.2 | -3.2 |
| S2 response quality | 47.5 | 66.9 | 47.3 | 67.6 | +0.7 |
| S3 strategic alignment | 66.5 | 65.7 | 56.6 | 56.0 | **-9.7** |
| S4 adaptation | 60.6 | 58.1 | 57.3 | 57.6 | -0.5 |
| J_old (J1 recall) | 56.3 | 54.8 | 30.6 | 29.9 | -24.9 |
| J_new | 71.8 | 72.5 | 73.3 | 74.2 | +1.7 |
| J6 | 100.0 | 100.0 | 100.0 | 90.0 | -10.0 |
| K (K1+K2) | 86.9 | 76.4 | 85.6 | 68.0 | -8.4 |
| G5 persona robustness | 80.0 | 100.0 | 100.0 | 100.0 | 0.0 |
| L (language) | 74.5 | 65.6 | 66.1 | 63.9 | -1.7 |
| H (Turing) | 92.0 | 78.0 | 90.0 | 82.0 | +4.0 |
| B (persona fidelity) | 61.3 | 63.0 | 62.0 | 61.7 | -1.3 |

### Sub-dimensiones MT

| Métrica | Baseline | A1.3 | A1.5-bis | **FINAL** | Δ vs A1.3 |
|---------|----------|------|----------|-----------|-----------|
| **K1** context retention | 83.48 | 64.86 | 78.66 | **51.74** | **-13.1** ❌ |
| K2 style retention | 91.98 | 93.69 | 96.02 | 92.4 | -1.3 |
| J3 prompt-to-line | 86.5 | 86.0 | 86.0 | 89.5 | +3.5 |
| J4 line-to-line | 59.16 | 61.88 | 62.08 | 65.42 | +3.5 |
| J5 belief drift | 65.0 | 65.0 | 67.5 | 62.5 | -2.5 |
| H1 Turing pass% | 92.0 | 78.0 | 90.0 | 82.0 | +4.0 |
| L1 language | 88.5 | 81.5 | 85.5 | 86.0 | +4.5 |
| L2 register | 68.78 | 59.88 | 63.8 | 55.84 | -4.0 |
| L3 intimacy | 61.66 | 50.0 | 42.5 | 42.5 | -7.5 |
| B2 persona depth | — | 43.0 | 38.5 | 39.5 | -3.5 |
| B5 persona consistency | — | 46.0 | 47.5 | 45.5 | -0.5 |
| **MT composite** | 76.18 | 75.98 | 78.82 | **74.96** | -1.0 |

### Per-run ST composites (v4)

| | Baseline | A1.3 | A1.5-bis | **FINAL** |
|-|----------|------|----------|-----------|
| Run 1 | 62.40 | 70.14 | 62.21 | 64.84 |
| Run 2 | 62.64 | 69.39 | 61.93 | 64.73 |
| Run 3 | 62.16 | 69.43 | 60.88 | 63.99 |
| **Mean ± σ** | **62.4 ± 0.2** | **69.65 ± 0.4** | **61.67 ± 0.7** | **64.52 ± 0.46** |

---

## 2. Análisis

### ¿Los 8 gates + S4-fix + rag ×1.4 suman valor vs A1.3 (4 gates)?

**No.** El estado FINAL (v5=67.3) es -3.3 puntos peor que A1.3 (70.6) y -2.2 puntos peor que baseline (69.5).

### Regresiones identificadas

**S3 strategic alignment: -9.7 puntos (65.7 → 56.0)**  
Regresión persistente en TODOS los checkpoints con 8 gates (A1.5-bis: 56.6, FINAL: 56.0). No es la recalling cap — esa fue revertida a 400. El origen es la arquitectura de 8 gates: los 4 gates adicionales (memory, audio, commitments, dna) añaden señal que produce derive estratégico en turno único. Esta regresión es real y estructural.

**K1 context retention: -13.1 puntos (64.86 → 51.74)**  
Con recalling=400 y 8 gates activos, K1 cae a 51.74 — peor que A1.3 (64.86) y peor que baseline (83.48). El presupuesto de tokens que antes iba a "recalling" ahora se comparte con 4 gates adicionales, reduciendo el contexto conversacional disponible. A1.5-bis (recalling=700) tenía K1=78.66, confirmando que K1 es directamente función del cap de recalling, pero ese cap a 700 destruía S3. Trade-off no resuelto.

**J6: -10.0 puntos (100.0 → 90.0)**  
Pequeña regresión en coherencia de cierre. Sin impacto significativo (peso 0.03 → -0.30 pts).

### ¿Qué mejora el FINAL vs A1.3?

| Dimensión | A1.3 | FINAL | Δ | Interpretación |
|-----------|------|-------|---|----------------|
| H1 Turing | 78.0 | 82.0 | +4.0 | S4-proximity fix ayuda |
| J_new | 72.5 | 74.2 | +1.7 | Leve mejora MT coherencia |
| S2 | 66.9 | 67.6 | +0.7 | Case-variance (no significativo) |

La S4-proximity fix aporta +4 en H1 (Turing pass rate), aunque S4 en sí no se recuperó vs baseline.

---

## 3. Veredicto

**v5 FINAL = 67.3 < 70.0 → Regla de cierre: revertir a estado A1.3.**

| Condición | Umbral | Resultado |
|-----------|--------|-----------|
| v5 ≥ 70.6 | FINAL > A1.3, cerrar en FINAL | ❌ 67.3 |
| 70.0 ≤ v5 < 70.6 | FINAL ≈ A1.3, conservar arquitectura | ❌ 67.3 |
| v5 < 70.0 | Revertir a A1.3 como punto de cierre | ✅ **67.3** |

### ARC1 cierra en A1.3: v5 = 70.6 (+1.1% vs baseline 69.5)

**Los 8 gates en su estado actual degradan la calidad** respecto al sistema de 4 gates de A1.3. El problema central es S3 (strategic alignment) que cae -9.7 puntos con la arquitectura de 8 gates, independientemente del cap de recalling. El código de los 8 gates queda en `feature/arc1-budget-orchestrator` como infraestructura para ARC2, pero el flag `ENABLE_BUDGET_ORCHESTRATOR` no debe activarse en producción hasta resolver S3.

---

## 4. Plan ARC2

| Objetivo | Métrica diana | Desde | Brecha |
|----------|---------------|-------|--------|
| Recuperar S3 | ≥ 65.0 | 56.0 (FINAL) | -9.0 |
| Recuperar K1 | ≥ 80.0 | 51.74 (FINAL) | -28.3 |
| Recuperar S4 | ≥ 60.0 | 57.6 (FINAL) | -2.4 |
| v5 objetivo | ≥ 72.0 | 67.3 (FINAL) | -4.7 |

**Hipótesis ARC2**: La S3 regresión viene de que los gates adicionales inyectan secciones con señal conflictiva para intent estratégico. Posibles palancas: (a) priority re-weighting para gates MEDIUM (dna, commitments), (b) compresión agresiva de memory/dna antes de inyectar, (c) separar recalling en sub-bloques con caps distintos.
