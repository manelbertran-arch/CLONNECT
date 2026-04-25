# Review Sesión 5 — Validation methodology + surrogate metrics (I5+I7)

**Fecha review:** 2026-04-25
**Documento revisado:** 05_validation_methodology.md
**Branch original:** research/eval-methodology
**Veredicto:** ✅ APROBADO POST-CORRECCIONES (5 correcciones aplicadas)

---

## Errores críticos detectados pre-corrección

### EC-1: Loss inicial Gemma-4 mal calculada (CRITICAL)

Worker decía:
> "log(256000) = 12.45, esperable para gemma-4-31B-it preentrenado"

**Esto es entropía RANDOM, NO de modelo preentrenado.**

Verificación matemática:
- log(256000) = 12.45 → loss de modelo random uniforme sobre 256k vocab
- gemma-4-31B-it preentrenado: loss típica para chat completion = 1-3
- Sprint 6 (10.64) NO era "casi normal" — era **masking COMPLETAMENTE ROTO**

Implicación: alertas tempranas de Sprint 6 estaban mal calibradas. Si la alerta era "loss > 11.0 → revisar", **nunca se habría disparado** aunque el masking estuviera roto al 90%.

### EC-2: "4,852 ejemplos" sin justificación

Worker presentaba "4,852 ejemplos esperados Sprint 7" como número derivado pero sin trazabilidad.

Cálculo correcto: sft_full.jsonl (5,739) − duplicados (~1,352) − error strings (22) − media artifacts (441) ≈ **3,900-4,400 registros**.

Número definitivo: definirse post-Sesión 8 (dataset quality gate ejecutado).

### EC-3: Sin coordinación con curriculum learning (Sesión 4)

Sesión 4 propone curriculum: persona Q&A 1 epoch → multi-turn 2-3 → adversarial 2-3.

Si early stopping aplica durante transición Q&A→multi-turn, puede confundirse con overfitting (la val loss subirá temporalmente).

Worker no consideraba esto.

### EC-4: CCEE-Mini sin validación empírica

Worker proponía CCEE-Mini (20 cases, $0.15) como gate Sprint 7 sin verificar correlación con CCEE Full.

Riesgo: gate puede ser ruido. Si CCEE-Mini no correlaciona >0.8 con CCEE Full, no es válido como decision tool.

### EC-5: Alertas tempranas mal calibradas

Worker proponía:
- Step 50: loss > 11.0 → ALERTA
- Final: loss < 0.2 → warning overfit

Calibración problemática: loss > 11.0 step 50 solo se da si modelo es prácticamente random. Pasaría desapercibido un masking 70% roto (loss ~4-7).

---

## Correcciones aplicadas (5)

| # | Corrección | Status |
|---|---|---|
| 1 | Tabla loss inicial 5 niveles (1-3 OK, 10-12 = masking roto) | ✅ Aplicada |
| 2 | "4,852" → "3,900-4,400 estimación, definitivo post-S8" | ✅ Aplicada |
| 3 | curriculum_phase_steps=150, early stopping desactivado durante Q&A | ✅ Aplicada |
| 4 | CCEE-Mini correlación empírica obligatoria antes de usarla como gate | ✅ Aplicada |
| 5 | Alertas refinadas: step 50 > 5.0 ALERTA, step 100 > 8.0 ABORT | ✅ Aplicada |

---

## Hallazgos validados post-corrección

- ✅ Split 90/5/5 sobre dataset Sprint 7 (post-S8)
- ✅ eval_steps=100 (5-6 checkpoints/epoch)
- ✅ Alerta divergencia val/train > 1.5
- ✅ Patience=3 (desactivado durante curriculum Q&A)
- ✅ Surrogates Tier 1: L1 + chrF++ ($0, <2s)
- ✅ Surrogates Tier 2: BERTScore XLM-R ($0, ~8s/50 cases)
- ✅ CCEE-Mini 20 cases ($0.15) — sólo si correlación > 0.8 verificada

---

## Coherencia cross-sesión

- ✅ Coherente con S4 (curriculum learning) post-corrección 3
- ✅ Coherente con S6 (loss inicial 1.5-2.5) post-corrección 1
- ✅ Coherente con S8 (dataset quality gate como pre-flight)

---

## Acciones bloqueantes para Sprint 7

1. Ejecutar CCEE-Mini correlación empírica ($0.30) antes de Sprint 7 training
2. Implementar SFTDivergenceCallback con curriculum_phase_steps=150
3. Confirmar número final dataset post-Sesión 8 (resolver "3,900-4,400 estimación")

---

## Severity final

🟢 HIGH value post-corrección.
🟡 MED risk si correlación CCEE-Mini ↔ Full no se valida antes de Sprint 7.
