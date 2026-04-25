# Dataset Quality Gate Report

**Generated:** 2026-04-26 00:45  
**Input:** `data/dpo/trl/sprint7/sft_sprint7.jsonl`  
**Records:** 2,585  
**Verdict:** ❌ FAIL

---

## Gate Results

| Gate | Criterio | Valor | Threshold | Severidad | Estado |
|---|---|---|---|---|---|
| G7.1 | messages array válido | 100.0% | 100% | BLOCKER | ✅ |
| G7.2 | role alternation correcto | 100.0% | 100% | BLOCKER | ✅ |
| G7.3 | tiene user + assistant | 100.0% | 100% | BLOCKER | ✅ |
| G7.4 | roles válidos | 100.0% | 100% | BLOCKER | ✅ |
| G7.5 | system prompt presente | 100.0% | 95% | WARNING | ✅ |
| G7.6 | no empty content | 100.0% | 100% | BLOCKER | ✅ |
| G1.1 | multi-turn ≥15% | 44.4% | 15% | BLOCKER | ✅ |
| G1.2 | persona Q&A ≥750 OR ≥7.5% | 91 (3.5%) | ≥750 OR ≥7.5% | BLOCKER | ❌ |
| G1.3 | adversarial ≥200 OR ≥2% (WARNING v1) | 11 (0.4%) | ≥200 OR ≥2% | WARNING | ⚠️ |
| G1.4 | DM single-turn ≤75% | 51.6% | 75% | WARNING | ✅ |
| G2.1 | error strings = 0 | 0 | 0 | BLOCKER | ✅ |
| G2.2 | solo-artifact = 0 | 0 | 0 | BLOCKER | ✅ |
| G2.3 | artifacts explícitos <2% | 18.5% | 2% | BLOCKER | ❌ |
| G2.4 | duplicados exactos <5% | 8.4% | 5% | WARNING | ⚠️ |
| G2.5 | respuestas <10chars <5% | 1.1% | 5% | WARNING | ✅ |
| G3.1 | Distinct-1 ≥0.20 | 12.8% | 20% | WARNING | ⚠️ |
| G3.2 | Distinct-2 ≥0.40 | 47.1% | 40% | WARNING | ✅ |
| G3.3 | Self-BLEU-4 ≤0.65 | 0.1% | 65% | WARNING | ✅ |
| G4.1 | categorías persona ≥5/6 | 6/6 | ≥5/6 | WARNING | ✅ |
| G4.2 | idioma ca+es ≥35% | 24.3% | 35% | WARNING | ⚠️ |
| G5.1 | coherencia ≥85% (heurística) | 94.0% | 85% | WARNING | ✅ |
| G6.2 | PII en assistant = 0 | 0 | 0 | BLOCKER | ✅ |
| G6.1 | overlap CCEE eval = 0 | 0 | 0 | BLOCKER | ✅ |
| G8.1 | N mínimo ≥2,000 | 2585 | 2000 | BLOCKER | ✅ |
| G8.2 | N máximo ≤30,000 | 2585 | 30000 | WARNING | ✅ |
| G8.3 | P99 tokens ≤2,048 (est: 3264) | 3264 | 2048 | WARNING | ⚠️ |
| G8.4 | records >1500 tokens <10% | 100.0% | 10% | WARNING | ⚠️ |

---

## Summary
- **Blockers fallados:** 2
- **Warnings fallados:** 6

### Blockers que requieren acción
- **G1.2** persona Q&A ≥750 OR ≥7.5%: `91 (3.5%)` (threshold: ≥750 OR ≥7.5%)
- **G2.3** artifacts explícitos <2%: `18.5%` (threshold: 2%)

### Warnings (training permitido pero documentar)
- **G1.3** adversarial ≥200 OR ≥2% (WARNING v1): `11 (0.4%)` (threshold: ≥200 OR ≥2%)
- **G2.4** duplicados exactos <5%: `8.4%` (threshold: 5%)
- **G3.1** Distinct-1 ≥0.20: `12.8%` (threshold: 20%)
- **G4.2** idioma ca+es ≥35%: `24.3%` (threshold: 35%)
- **G8.3** P99 tokens ≤2,048 (est: 3264): `3264` (threshold: 2048)
- **G8.4** records >1500 tokens <10%: `100.0%` (threshold: 10%)

---

## Stats detalladas

- **n_records:** 2585
- **parse_errors:** 0
- **n_multiturn:** 1148
- **n_persona_qa:** 91
- **n_adversarial:** 11
- **n_error_strings:** 0
- **n_artifact_only:** 0
- **artifact_rate:** 0.1853
- **distinct_1:** 0.1275
- **distinct_2:** 0.4710
- **self_bleu_4:** 0.0006
- **persona_categories_covered:** 6
- **lang_ca:** 537
- **lang_es:** 91
- **lang_other:** 1957
- **ccee_overlap:** 0
- **p99_tokens:** 3264
- **n_over_1500_tokens:** 2585

---

_Generado por `scripts/finetuning/09_dataset_quality_gate.py`_