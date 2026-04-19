# ARC4 Phase 1 — Rollout Plan

**Sprint:** 5 / ARC4
**Date:** 2026-04-19
**Branch:** `feature/arc4-phase1-baseline-rules`

---

## Estado Post-Phase 1

### Mutations confirmadas en código (7 activas)

| ID | Nombre | File | Flag |
|---|---|---|---|
| M1 | guardrails | `core/guardrails.py` | `ENABLE_GUARDRAILS` — KEEP |
| M3 | intra_repetition (A2b) | `postprocessing.py:108-131` | `DISABLE_M3_DEDUPE_REPETITIONS` ← nuevo |
| M4 | sentence_dedupe (A2c) | `postprocessing.py:133-163` | `DISABLE_M4_DEDUPE_SENTENCES` ← nuevo |
| M5-alt | echo_detector (A3) | `postprocessing.py:164-203` | `DISABLE_M5_ECHO_DETECTOR` ← nuevo |
| M6 | normalize_length | `services/length_controller.py` | `DISABLE_M6_NORMALIZE_LENGTH` ← nuevo |
| M7 | normalize_emojis | `style_normalizer.py` | `DISABLE_M7_NORMALIZE_EMOJIS` ← nuevo |
| M8 | normalize_punctuation | `style_normalizer.py` | `DISABLE_M8_NORMALIZE_PUNCTUATION` ← nuevo |
| M10 | strip_question | `services/question_remover.py` | `ENABLE_QUESTION_REMOVAL` (existente) |

### Mutations del design doc que NO existen

M2 (pii_redactor), M9 (casing), M11 (signature_tic) → Solo diseñar prompt rules.

---

## Phase 2 — Shadow Validation (Semana 2)

**Objetivo:** Confirmar qué % de turnos cada mutation modifica el output.
Target: `changed_rate < 5%` antes de eliminar.

**Implementación:**
- Shadow logging: comparar `pre_mutation_text` vs `post_mutation_text` por turn.
- Log a `mutation_shadow_log` table o archivo temporal.
- 5,000+ turnos de tráfico real (~3 días).

**Criterio GO/NO-GO:**
- `changed_rate < 5%` → la prompt rule ya funciona → proceder a eliminación
- `changed_rate 5-20%` → iterar prompt rule → nuevo shadow 3 días
- `changed_rate > 20%` → prompt rule no funciona → STOP, rediseñar antes de continuar

**Mutations a shadow primero (LOW risk):**
- M3, M4, M7, M8

---

## Phase 3 — Eliminate LOW Risk (Semana 2-3)

**Orden de eliminación (más seguro primero):**

### Paso 3.1 — M3 + M4 (dedupe_repetitions + dedupe_sentences)

**Pre-requisito:** Añadir prompt rules M3+M4 al Doc D de iris_bertran + stefano_bonanno.

**Validación:**
```bash
export DISABLE_M3_DEDUPE_REPETITIONS=true
export DISABLE_M4_DEDUPE_SENTENCES=true
python3.11 scripts/run_ccee.py --creator iris_bertran --runs 1 --cases 30 --v5 \
  --save-as arc4_phase3_without_m3m4_$(date +%Y%m%d_%H%M)
```

**GO criteria:** ΔCCEE composite > -2 puntos.
**Kill switch:** `DISABLE_M3_DEDUPE_REPETITIONS=false` (default) revierte inmediatamente.

### Paso 3.2 — M7 + M8 (normalize_emojis + normalize_punctuation)

**Pre-requisito:** `_tone_config.punctuation_style` + `emoji_rate_pct` en Doc D.

**Validación:**
```bash
export DISABLE_M7_NORMALIZE_EMOJIS=true
export DISABLE_M8_NORMALIZE_PUNCTUATION=true
python3.11 scripts/run_ccee.py --creator iris_bertran --runs 1 --cases 30 --v5 \
  --save-as arc4_phase3_without_m7m8_$(date +%Y%m%d_%H%M)
```

**GO criteria:** ΔCCEE composite > -2 puntos.

### Paso 3.3 — M5-alt echo detector (RECONSIDER)

**Decisión previa necesaria:** ¿REPLACE o KEEP?
- Si REPLACE: añadir prompt rule "no parafrasees el mensaje del lead".
- Si KEEP: mantener pero hacer observable (log `echo_rate` metric).

---

## Phase 4 — Eliminate MEDIUM Risk (Semana 3)

### Paso 4.1 — M10 (strip_question_when_not_asked)

**Ya tiene flag:** `ENABLE_QUESTION_REMOVAL=false`

**Pre-requisito:** Añadir `question_cadence` + `question_rate_pct` a `_tone_config`.

**Validación:**
```bash
export ENABLE_QUESTION_REMOVAL=false
python3.11 scripts/run_ccee.py --creator iris_bertran --runs 1 --cases 30 --v5 \
  --save-as arc4_phase4_without_m10_$(date +%Y%m%d_%H%M)
```

**Métrica extra:** `consecutive_questions_rate` (bot + lead ambos hacen pregunta).
Target: < 5% (baseline ~8%).

**GO criteria:** ΔCCEE > -2 AND consecutive_questions_rate < 8%.

### Paso 4.2 — M6 (normalize_length)

**Antes de eliminar M6:**
1. Implementar `LengthRegenFallback` (ARC4 §3 Phase 4).
2. Shadow test 1 semana (regen_trigger_rate target < 3%).
3. Entonces eliminar M6.

**Validación:**
```bash
export DISABLE_M6_NORMALIZE_LENGTH=true
python3.11 scripts/run_ccee.py --creator iris_bertran --runs 1 --cases 30 --v5 \
  --save-as arc4_phase4_without_m6_$(date +%Y%m%d_%H%M)
```

---

## Phase 5 — M1+M2 SafetyFilter (Semana 4)

- M1 guardrails: KEEP, refactor a `services/safety_filter.py`.
- M2 pii_redactor: NO EXISTE en código — implementar como parte de SafetyFilter (deuda).

---

## Rollout por Riesgo (Orden Recomendado)

```
Week 2:
  Day 1: Prompt rules M3+M4 en Doc D → CCEE shadow
  Day 3: Eliminar M3+M4 si shadow OK
  Day 4: Prompt rules M7+M8 en tone_config → CCEE shadow
  Day 5: Eliminar M7+M8 si shadow OK

Week 3:
  Day 1: Prompt rules M10 en tone_config → CCEE shadow
  Day 2: Implementar LengthRegenFallback
  Day 3: Eliminar M10 si shadow OK
  Day 4: Shadow M6 con regen fallback
  Day 5: Eliminar M6 si shadow OK + regen_rate < 3%
  Day 5: Decisión M5-alt (KEEP vs REPLACE)

Week 4:
  Day 1-3: SafetyFilter refactor (M1+M2)
  Day 4-5: Final CCEE + retrospective
```

---

## Criterios GO/NO-GO por Phase

| Phase | Criterio GO | Kill switch |
|---|---|---|
| 3.1 (M3+M4) | ΔCCEE > -2 | `DISABLE_M3=false && DISABLE_M4=false` |
| 3.2 (M7+M8) | ΔCCEE > -2 | `DISABLE_M7=false && DISABLE_M8=false` |
| 3.3 (M5-alt) | Decisión explícita Manel | `DISABLE_M5_ECHO_DETECTOR=false` |
| 4.1 (M10) | ΔCCEE > -2, consec_q < 8% | `ENABLE_QUESTION_REMOVAL=true` |
| 4.2 (M6) | ΔCCEE > -2, regen_rate < 3% | `DISABLE_M6=false` |

---

## Tracking de Progreso

Actualizar este documento tras cada phase con:
- Fecha de eliminación
- CCEE composite pre/post
- Issues encontrados
