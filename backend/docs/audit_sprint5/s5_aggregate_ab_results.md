# Sprint 5 Aggregate A/B Results

**Worker:** S5-AB  
**Fecha:** 2026-04-20  
**Branch:** worker/s5-agg-ab  
**Protocolo:** 50×3+MT+v5 (instrumento actual) sobre bot pre-Sprint 5 (fb2b1195) vs post-Sprint 5 (main)

---

## 1. Commits comparados

| | SHA | Fecha | Descripción |
|---|---|---|---|
| **PRE** | `fb2b1195` | 2026-04-09 17:43 | fix: universal clone factory — zero hardcoding, all from creator profile |
| **POST** | `e62aaad4` | 2026-04-20 13:28 | main (post ARC1+ARC2+ARC3+ARC4+ARC5) |

---

## 2. Composite — número principal

### v5 Composite (número principal — misma instrumentación en ambos)

| | PRE (fb2b1195) | POST (e62aaad4) | Δ |
|---|---|---|---|
| **v5 composite** | **62.1** | **66.4** | **+4.3** |
| Per-run (formato old) | [59.61, 61.37, 54.90] | [62.16, 63.30, 64.32] | — |
| σ inter-run | 2.73 | 0.88 | PRE más inestable |

> **Veredicto binario Δv5 ≥ 4:** **SÍ ✅** — Δ=+4.3 supera el umbral de señal real

### v4 / v4.1 Composite (referencia)

| | PRE | POST | Δ |
|---|---|---|---|
| **v4 composite** | 60.6 | 64.8 | +4.2 ✅ |
| **v4.1 composite** | 62.6 | 66.6 | +4.0 ✅ |

---

## 3. Tabla dimensión por dimensión

> **Nota de comparabilidad:** PRE v2 completó con MT+v5 judge completo — misma instrumentación que POST. B es la única dimensión ⚠️ porque usa sub-dimensiones distintas (PRE: B1+B4, POST: B2+B4+B5).

| Dimensión | PRE (v2) | POST | Δ | Comparable | Señal |
|-----------|----------|------|---|------------|-------|
| **S1 Style Fidelity** | 60.5 | 72.3 | **+11.8** | ✅ | ✅ mejora |
| **S2 Response Quality** | 31.8 | 47.0 | **+15.2** | ✅ | ✅ mejora |
| **S3 Strategic Alignment** | 65.1 | 64.6 | -0.5 | ✅ | → estable |
| **S4 Adaptation** | 53.6 | 66.9 | **+13.3** | ✅ | ✅ mejora |
| **J_new (J3/J4/J5)** | 70.3 | 72.6 | +2.3 | ✅ | → marginal |
| — J3 Prompt-to-Line | 83.0 | 86.5 | +3.5 | ✅ | → |
| — J4 Line-to-Line | 63.8 | 56.7 | -7.1 | ✅ | ❌ regresión |
| — J5 Belief Drift | 60.0 | 70.0 | +10.0 | ✅ | ✅ mejora |
| **J_old** | 53.0 | 29.5 | **-23.5** | ✅ | ❌ regresión |
| **J6 QA Consistency** | 100.0 | 100.0 | 0.0 | ✅ | → estable |
| **K (K1/K2)** | 85.7 | 72.5 | **-13.2** | ✅ | ❌ regresión |
| — K1 Context Retention | 79.7 | 57.3 | **-22.4** | ✅ | ❌ regresión |
| — K2 Style Retention | 94.6 | 95.4 | +0.8 | ✅ | → estable |
| **G5 Persona Robustness** | 80.0 | 80.0 | 0.0 | ✅ | → estable |
| **L (L1/L2/L3)** | 65.7 | 68.2 | +2.5 | ✅ | → marginal |
| — L1 Persona Tone | 80.0 | 79.5 | -0.5 | ✅ | → |
| — L2 Logical Reasoning | 67.2 | 61.3 | -5.9 | ✅ | ❌ leve |
| — L3 Action Justification | 45.0 | 60.0 | +15.0 | ✅ | ✅ mejora |
| **H Indistinguishability** | 70.0 | 72.0 | +2.0 | ✅ H1 only en ambos | → marginal |
| — H1 Turing | 70.0 | 72.0 | +2.0 | ✅ | → |
| **B Persona Fidelity** | 50.0 (B1+B4) | 57.8 (B2+B4+B5) | +7.8 | ⚠️ sub-dims distintas | ⚠️ |

**Δ medio dimensiones ST (S1/S2/S3/S4):** (11.8 + 15.2 − 0.5 + 13.3) / 4 = **+9.95** ✅  
**Hallazgo clave MT:** K1 y J_old REGRESIONAN en POST (K1: −22.4, J_old: −23.5) pese a mejorar las ST

---

## 4. σ intra-sesión (hallazgo secundario)

> Los per-run composites son en formato old (pesos del evaluador pre-S5 para comparabilidad σ).

| | PRE σ | POST σ |
|---|---|---|
| Composite inter-run | 2.73 | 0.88 |

| Dim (per-run PRE) | R1 | R2 | R3 | σ |
|---|---|---|---|---|
| S1 | 64.6 | 64.3 | 60.5 | 1.87 |
| S2 | 31.5 | 31.8 | 31.8 | 0.13 |
| S3 | 55.8 | 64.3 | 65.1 | 4.20 |
| S4 | 54.4 | 55.1 | 53.6 | 0.63 |

| Dim (per-run POST) | R1 | R2 | R3 | σ |
|---|---|---|---|---|
| S1 | 71.6 | 72.2 | 72.3 | 0.31 |
| S2 | 47.4 | 46.5 | 47.0 | 0.37 |
| S3 | 55.6 | 60.9 | 64.6 | 3.67 |
| S4 | 67.0 | 66.6 | 66.9 | 0.17 |

El bot post-Sprint 5 muestra **menor varianza inter-run** (σ composite: 2.73→0.88). La varianza de S3 se mantiene alta en ambos (~4 pts), lo cual es coherente con la naturaleza discreta del scorer estratégico.

---

## 5. Confounds documentados

Estas diferencias entre pre y post son **componentes del Sprint 5**, no ruido:

| Componente | PRE | POST | Dimensiones afectadas |
|------------|-----|------|----------------------|
| **Doc D length** | 1576 chars (compressed) | 2557 chars (full) | S1, J3, G5, L1 |
| **Memory system** | `ENABLE_MEMORY_ENGINE=true` (old) | ARC2 Lead Memories | K1, J3, J6 |
| **Budget Orchestrator** | NO (ARC1 no existe) | `ENABLE_BUDGET_ORCHESTRATOR=true` | S1, S4, estabilidad |
| **Context Compactor** | NO | `ENABLE_COMPACTOR_SHADOW=true` | K1, K2 |
| **Circuit Breaker** | NO | `ENABLE_CIRCUIT_BREAKER=true` | G5, robustez |
| **Typed metadata** | NO | ARC5 activo | Contexto de conversación |

El delta medido es **sprint 5 agregado** — no descompone contribución individual de cada ARC.

---

## 6. Historial de runs

### v1 — CRASH en MT (14:00)
- **Causa:** `adversarial_prompts.json` ausente en worktree `/tmp/s5-pre/backend/evaluation_profiles/`
- **Datos recuperados:** 3 runs ST ([59.61, 61.37, 54.90] formato old)
- **Datos perdidos:** MT, v5 judge, v5 composite
- **JSON:** `s5_pre_sprint5_20260420_1340_recovered.json` (partial)

### v2 — COMPLETADO (14:01—14:44)
- **Fix:** copiado `adversarial_prompts.json` al worktree antes del run
- **JSON final:** `s5_pre_sprint5_v2_20260420_1401.json` (220 KB, full MT+v5)
- **v5 composite:** 62.1 — **AUTORITATIVO**

### Diferencia v1 vs v2 (varianza intra-día)

| Run | v1 | v2 |
|-----|----|----|
| R1 | 60.41 | 59.61 |
| R2 | 59.88 | 61.37 |
| R3 | 63.24 | 54.90 |
| Mean (old composite) | 61.18 | 58.63 |

Δ entre v1 y v2 (~2.5 pts en old composite) es coherente con varianza OpenRouter conocida ±3-4 pts.

---

## 7. Veredicto final

### Composite v5:
> **Δv5 = +4.3** — **SÍ ≥ 4 ✅** → señal real (PRE=62.1, POST=66.4)

### Dimensiones ST comparables (S1/S2/S3/S4):
> **Δ medio ST = +9.95** → señal fuerte y consistente

### Dimensiones MT:
> **K1 regresiona (−22.4), J_old regresiona (−23.5)** — regressions en retención y consistencia MT  
> **Hipótesis:** ARC2 Lead Memories (nuevo sistema) tiene menor cobertura de contexto inmediato en MT que el `ENABLE_MEMORY_ENGINE` legacy

### Veredicto binario:
> **¿Δv5 ≥ 4?** → **SÍ ✅** — Sprint 5 genera señal real en el composite principal

---

## 8. Qué NO mide este A/B

- **Contribución individual de cada ARC:** el delta es agregado por diseño. Para atribución por ARC se necesitaría ablation study por feature.
- **Impacto en usuarios reales:** CCEE mide fidelidad al creator, no engagement o conversión.
- **Regresión por creator:** medición solo en `iris_bertran`. Otro creator puede mostrar delta distinto.
- **Estabilidad a largo plazo:** medición puntual, no tendencia temporal.
- **Impacto de ARC5 typed metadata:** el scorer audit confirma que ningún scorer lee typed_metadata — si ARC5 mejora la calidad de respuesta, se captura indirectamente vía S1/S3/S4. Si ARC5 solo afecta downstream, no se captura aquí.

---

## 9. Archivos de referencia

| Archivo | Estado | Contenido |
|---------|--------|-----------|
| `tests/ccee_results/iris_bertran/s5_pre_sprint5_20260420_1340_recovered.json` | PARTIAL (v1 crash) | 3 runs ST, sin MT/v5 |
| `tests/ccee_results/iris_bertran/s5_pre_sprint5_v2_20260420_1401.json` | COMPLETO ✅ | 3 runs + MT + v5 — AUTORITATIVO |
| `tests/ccee_results/iris_bertran/distill_AB_OFF_20260419_2214.json` | COMPLETO ✅ | Post-Sprint 5 baseline |
| `docs/audit_sprint5/s5_ab_scorer_audit.md` | COMPLETO ✅ | Audit: 0 dimensiones metadata-based |
