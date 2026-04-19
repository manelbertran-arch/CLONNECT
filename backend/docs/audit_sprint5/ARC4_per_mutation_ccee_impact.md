# ARC4 — Per-Mutation CCEE Impact

**Branch:** `feature/arc4-phase1-baseline-rules`
**Date:** 2026-04-19
**Status:** PENDING — CCEE runs not yet executed

---

## Baseline (todas las mutations activas)

| Run | Creator | Model | Composite v5 | K1 | S3 | J4 | L2 | J6 | Date |
|---|---|---|---|---|---|---|---|---|---|
| arc4_baseline_all_mutations_on | iris_bertran | gemma-4-31b (openrouter) | PENDING | — | — | — | — | — | — |

---

## Shadow Tests — Efecto por Mutation (DISABLE_M*=true)

| Mutation | Disabled env var | Baseline | Without | Delta composite | K1 delta | S3 delta | Interpretación |
|---|---|---|---|---|---|---|---|
| M3 dedupe_repetitions | `DISABLE_M3_DEDUPE_REPETITIONS=true` | PENDING | PENDING | PENDING | — | — | — |
| M4 dedupe_sentences | `DISABLE_M4_DEDUPE_SENTENCES=true` | PENDING | PENDING | PENDING | — | — | — |
| M5-alt echo_detector | `DISABLE_M5_ECHO_DETECTOR=true` | PENDING | PENDING | PENDING | — | — | — |
| M6 normalize_length | `DISABLE_M6_NORMALIZE_LENGTH=true` | PENDING | PENDING | PENDING | — | — | — |
| M7 normalize_emojis | `DISABLE_M7_NORMALIZE_EMOJIS=true` | PENDING | PENDING | PENDING | — | — | — |
| M8 normalize_punctuation | `DISABLE_M8_NORMALIZE_PUNCTUATION=true` | PENDING | PENDING | PENDING | — | — | — |
| M10 strip_question | `ENABLE_QUESTION_REMOVAL=false` | PENDING | PENDING | PENDING | — | — | — |

---

## Interpretación (template)

- Delta > +1: la mutation REGRESA el composite → eliminarla mejora calidad
- Delta ~ 0: la mutation no afecta composite → eliminar es seguro
- Delta < -1: la mutation PROTEGE el composite → eliminar requiere prompt rule sólida
- Delta < -2: NO eliminar sin prompt rule validada primero (criterio go/no-go)

---

## Comandos para Ejecutar

### Baseline (todas activas)

```bash
set -a && source .env && set +a
source config/env_ccee_gemma4_31b_openrouter.sh
export LLM_PRIMARY_PROVIDER=openrouter
export OPENROUTER_MODEL=google/gemma-4-31b-it
export ACTIVE_MODEL=gemma-4-31b-it
export DEEPINFRA_TIMEOUT=45
export CCEE_NO_FALLBACK=1

python3.11 -W ignore::FutureWarning -u scripts/run_ccee.py \
  --creator iris_bertran \
  --runs 1 --cases 30 \
  --v4-composite --v5 \
  --save-as arc4_baseline_all_mutations_on_$(date +%Y%m%d_%H%M) \
  2>&1 | tee /tmp/arc4_baseline.log
```

### Por mutation (repetir con cada DISABLE_M* flag)

```bash
# M3
export DISABLE_M3_DEDUPE_REPETITIONS=true
python3.11 -W ignore::FutureWarning -u scripts/run_ccee.py \
  --creator iris_bertran --runs 1 --cases 30 --v4-composite --v5 \
  --save-as arc4_without_m3_$(date +%Y%m%d_%H%M)
unset DISABLE_M3_DEDUPE_REPETITIONS

# M4
export DISABLE_M4_DEDUPE_SENTENCES=true
python3.11 -W ignore::FutureWarning -u scripts/run_ccee.py \
  --creator iris_bertran --runs 1 --cases 30 --v4-composite --v5 \
  --save-as arc4_without_m4_$(date +%Y%m%d_%H%M)
unset DISABLE_M4_DEDUPE_SENTENCES

# M5-alt
export DISABLE_M5_ECHO_DETECTOR=true
python3.11 -W ignore::FutureWarning -u scripts/run_ccee.py \
  --creator iris_bertran --runs 1 --cases 30 --v4-composite --v5 \
  --save-as arc4_without_m5_$(date +%Y%m%d_%H%M)
unset DISABLE_M5_ECHO_DETECTOR

# M6
export DISABLE_M6_NORMALIZE_LENGTH=true
python3.11 -W ignore::FutureWarning -u scripts/run_ccee.py \
  --creator iris_bertran --runs 1 --cases 30 --v4-composite --v5 \
  --save-as arc4_without_m6_$(date +%Y%m%d_%H%M)
unset DISABLE_M6_NORMALIZE_LENGTH

# M7
export DISABLE_M7_NORMALIZE_EMOJIS=true
python3.11 -W ignore::FutureWarning -u scripts/run_ccee.py \
  --creator iris_bertran --runs 1 --cases 30 --v4-composite --v5 \
  --save-as arc4_without_m7_$(date +%Y%m%d_%H%M)
unset DISABLE_M7_NORMALIZE_EMOJIS

# M8
export DISABLE_M8_NORMALIZE_PUNCTUATION=true
python3.11 -W ignore::FutureWarning -u scripts/run_ccee.py \
  --creator iris_bertran --runs 1 --cases 30 --v4-composite --v5 \
  --save-as arc4_without_m8_$(date +%Y%m%d_%H%M)
unset DISABLE_M8_NORMALIZE_PUNCTUATION

# M10
export ENABLE_QUESTION_REMOVAL=false
python3.11 -W ignore::FutureWarning -u scripts/run_ccee.py \
  --creator iris_bertran --runs 1 --cases 30 --v4-composite --v5 \
  --save-as arc4_without_m10_$(date +%Y%m%d_%H%M)
unset ENABLE_QUESTION_REMOVAL
```
