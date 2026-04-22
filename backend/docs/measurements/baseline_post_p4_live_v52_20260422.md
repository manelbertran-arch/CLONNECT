# Baseline CCEE v5.3 — Post-P4 LIVE — 2026-04-22/23 (con v52-fixes)

**Fecha:** 2026-04-22 23:13 → 2026-04-23 00:11  
**Branch:** measure/baseline-post-p4 (commit 5f641cf5)  
**Includes:** PR #77 (intent canonical) + PR #78 (ARC1 truncation) + PR #79 (SalesIntentResolver) + PR #80 (P4 integration LIVE)  
**Flags:** `--v4-composite --v41-metrics --v5 --v52-fixes`  
**Config:** 3 runs × 50 cases + 5 MT conv × 10 turns  
**Railway:** USE_COMPRESSED_DOC_D=false | ENABLE_SELL_ARBITER_LIVE=true | ENABLE_RERANKING=true | USE_COMPACTION=true  
**JSON:** `tests/ccee_results/iris_bertran/baseline_post_p4_live_v52_20260422.json`

---

## Composites

| Protocolo | Este baseline (v52-fixes ON) | Sprint2 ON (12-abr) | Variance 20-22 abr (sin v52-fixes) | pre-Sprint2 |
|-----------|------------------------------|---------------------|-------------------------------------|-------------|
| v4-style  | **68.0**                     | 60.9                | ~67–69                              | 57.4        |
| v4.1      | **66.7**                     | —                   | —                                   | —           |
| v5        | **67.7**                     | 65.2                | —                                   | —           |

σ_intra (std 3 runs): **0.43** — medición estable

Per-run composites (v4): run1=69.41 | run2=70.26 | run3=69.98

---

## Dimensiones v4 (Single-Turn)

| Dimensión | Score | Peso |
|-----------|-------|------|
| S1 Style Fidelity | 64.1 | 0.20 |
| S2 Response Quality | 67.2 | 0.15 |
| S3 Strategic Alignment | 76.2 | 0.20 |
| S4 Adaptation | 63.3 | 0.12 |
| J_old (J1+J2) | 51.4 | 0.05 |
| J_new (J3+J4+J5) | 72.4 | 0.13 |
| K (K1+K2) | 75.4 | 0.08 |
| G5 Persona Robustness | 60.0 | 0.07 |

### S1 Sub-params (A1–A9, promedio 3 runs)

| Param | run1 | run2 | run3 |
|-------|------|------|------|
| A1 Length | 99.26 | 99.97 | 99.70 |
| A2 Emoji | 96.92 | 92.29 | 92.29 |
| A2 Contextual | 58.33 | 60.76 | 60.04 |
| A3 Exclamations | 50.09 | 42.09 | 42.09 |
| A4 Questions | 87.73 | 91.73 | 87.73 |
| A5 Vocabulary | 16.0 | 28.0 | 20.0 |
| A6 Language | 22.69 | 18.08 | 20.29 |
| A7 Fragmentation | 100.0 | 100.0 | 100.0 |
| A8 Formality | 99.12 | 99.12 | 99.12 |
| A9 Catchphrases | 0.0 | 20.0 | 20.0 |

### S2–S4 per run

| Dim | run1 | run2 | run3 | mean |
|-----|------|------|------|------|
| S1 | 63.01 | 65.20 | 64.13 | 64.1 |
| S2 | 67.40 | 66.17 | 67.23 | 67.2 |
| S3 | 74.47 | 76.34 | 76.21 | 76.2 |
| S4 | 62.84 | 63.62 | 63.30 | 63.3 |

---

## Dimensiones v4.1 — Multi-Turn (5 conv × 10 turns)

| Dimensión | Score |
|-----------|-------|
| J3 Prompt-to-Line | 82.5 |
| J4 Line-to-Line | 64.0 |
| J5 Belief Drift | 67.5 |
| J6 Q&A Consistency | **35.0** |
| K1 Context Retention | 68.1 |
| K2 Style Retention | 86.4 |
| G5 Persona Robustness | 60.0 |
| L1 Persona Tone | 84.5 |
| L2 Logical Reasoning | 62.1 |
| L3 Action Justification | 52.0 |

Notas: J6=35.0 bajo — pocas Q&A cross-session probes activas en los 5 MT convs. K2=86.4 sólido (10 turns suficientes). G5=60.0 moderado (2/5 convs con G5=0 indica fallos de resistencia en algunos escenarios).

---

## Dimensiones v5 — Indistinguishability + Persona Fidelity

### H1 Turing Test

| Contexto | Score | Detalle |
|----------|-------|---------|
| MT (DB-backed) | **82.0%** | 41/50 comparisons fooled, 5 conv × 10 turns |
| ST (Qwen3 judge) | **78.0%** | single-turn rate |

### B Persona Fidelity (Qwen3-30B-A3B, 50 casos)

| Dimensión | Score |
|-----------|-------|
| B2 Persona Consistency | **28.5** |
| B4 Persona Boundaries | 100.0 |
| B5 Emotional Signature | 49.0 |
| C2 Naturalness | 61.5 |
| C3 Contextual Appropriateness | **21.0** |

Notas: B2=28.5 y C3=21.0 son los puntos más débiles. B4=100 indica que el bot nunca revela su naturaleza de bot. B5=49 moderado.

---

## Análisis Cualitativo

### Casos Tipo 1 (DNA=FAMILIA, frustration≥2)
No identificados en per_case_records (campos dna_type/frustration_level no presentes en la estructura de salida actual — están en el test set generation, no en los case records exportados).

### Observaciones generales
- G5=60 indica que ~2/5 conversaciones fallaron robustez de persona bajo pressure social (conv 2 y conv 3 con G5=0 en MT scoring)
- J4=64 (line-to-line consistency) moderado — coherencia inter-turno mejorable
- J6=35 — baja Q&A cross-session: las convs generadas no activaron suficientes probes de Q&A
- B2=28.5 y C3=21.0 son señales de áreas de mejora para Sprint 7

---

## Varianza y Estabilidad

| Métrica | Valor |
|---------|-------|
| σ_intra (3 runs) | **0.43** |
| Rango runs | 69.41–70.26 |
| CV (coef. variación) | 0.006 |

Medición muy estable. σ=0.43 es la más baja registrada hasta ahora.

---

## Comparación vs Histórico

| Sistema | v4-style | Δ vs pre-S2 | Δ vs S2-ON | Δ vs variance |
|---------|----------|-------------|------------|---------------|
| pre-Sprint2 (12-abr, rescored) | 57.4 | baseline | — | — |
| Sprint2 ON (12-abr) | 60.9 | +3.5 | — | — |
| Variance 20-22 abr (sin v52-fixes) | ~68.0 | +10.6 | +7.1 | — |
| **Este baseline (v52-fixes ON)** | **68.0** | **+10.6** | **+7.1** | **±0.0** |

v52-fixes NO introduce regresión respecto a las variance sessions sin v52-fixes.

---

## Conclusión

**v4-style=68.0, σ=0.43 — estable.** v52-fixes no regresiona vs variance sessions (v4~67-69); +7.1 pts sobre Sprint2 ON confirma progreso real acumulado. H1 Turing 82% (MT) sólido. Áreas de atención para S7: J6=35, B2=28.5, C3=21.0, G5=60.

---

## Baseline oficial post-P4 LIVE — 2026-04-22

Composites: v4-style=68.0, v5=67.7, σ_intra=0.43
Flags: --v4-composite --v41-metrics --v5 --v52-fixes
Environment: Railway corregido (USE_COMPRESSED_DOC_D=false, ENABLE_SELL_ARBITER_LIVE=true)

### Fortalezas
- H1 Turing: 82% MT, 78% ST (bot indistinguible de Iris en mayoría de casos)
- S3 Strategic: 76.2 (post-P4, jerarquía sell/don't-sell funcional)
- K2 Style Retention: 86.4
- L1 Persona Tone: 84.5

### Áreas críticas (hallazgos v52-fixes que scorer sin fixes ocultaba)
- J6 Q&A Consistency: 35 → memoria episódica / creator profile débil en preguntas factuales
- B2 Persona Fidelity: 28.5 → rubric creator-specific expone gap de personalidad
- C3 Contextual Reasoning: 21 → uso de contexto largo débil

### Plan de ataque priorizado
Los 3 hallazgos críticos sugieren orden óptimo de optimización T1 CONSERVAR-OPTIMIZAR:
1. #5 Semantic Memory PGVector + #6 Memory Consolidator + #7 LLM Consolidation — ataca J6/C3
2. #4 Episodic Memory — ataca J6 contexto previo
3. #67 Creator Profile Service — ataca B2
4. #93 Copilot — tangencial
5. #94 Commitment Tracker — tangencial

### Referencia para activaciones futuras
Todas las mediciones subsiguientes usan mismo protocolo:
- 3 runs × 50 ST + 5 MT × 10 turns
- --v4-composite --v41-metrics --v5 --v52-fixes
- CCEE_NO_FALLBACK=1
- Railway vars del env_prod_mirror_20260422.sh

Gates para KEEP/REVERT:
- KEEP si composite v5 ≥ +1.5 sin regresión >2 en dimensión crítica
- REVERT si composite v5 ≤ -1.5 o regresión >3 en dimensión crítica
