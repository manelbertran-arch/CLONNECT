# Railway vs Env Script Flag Diff — 2026-04-22

Audit de 4 fases: inventario código → estado Railway → invocación pipeline → tabla final.
Para contexto y decisiones, ver commits referenciados.

---

## Tabla final: veredicto por flag

| Flag | Railway | Env Script | Código Default | Veredicto | Causa Railway |
|------|---------|------------|----------------|-----------|---------------|
| `USE_COMPRESSED_DOC_D` | **true** | true | false | ⚠️ **DRIFT** — Railway debería ser false | Activado manualmente en algún punto post-QW2. Commit `83a1104d` ya advierte contra este flag. Memoria project_qw2: -10.69 regression con Gemma-4-31B |
| `ENABLE_FEW_SHOT` | false | true | true | ✓ Railway intencional | `dbf0cd11` (2026-04-03): "turn OFF 16 unaudited systems pending forensic audit". Auditado en `8fed3b10` (W8-B2a) pero no reactivado |
| `ENABLE_LENGTH_HINTS` | false | true | true | ✓ Railway intencional | `dbf0cd11` OFF list + `de7c319a` bisect: "disable 3 regression suspects — length hints, temp dual, loop detector" |
| `ENABLE_RERANKING` | true | **false** | true | ✓ Railway correcto — env script erróneo | Env script desactivó reranking para algún ablation run y nunca se corrigió |
| `ENABLE_CITATIONS` | false | true | true | ✓ Railway intencional | `dbf0cd11` OFF list como "citations" |
| `ENABLE_OUTPUT_VALIDATION` | false | true | true | ✓ Railway intencional | `1b3bc213`: "clean 655 lines dead code from output_validator.py — keep only validate_links()". Sistema vaciado |
| `ENABLE_RESPONSE_FIXES` | false | true | true | ✓ Railway intencional | `dbf0cd11` OFF list como "response_fixes" |
| `ENABLE_MESSAGE_SPLITTING` | false | true | true | ✓ Railway intencional | Misma ronda de auditoría W8 |
| `ENABLE_BLACKLIST_REPLACEMENT` | false | true | **false** | ✓ Railway = código default | `dbf0cd11`: flag creado con default false. Env script lo activa sin justificación |
| `ENABLE_STYLE_ANCHOR` | *(no var)* = false | true | false | ✗ **DISCREPANCIA** — env script activa, Railway no tiene la var | `generation.py:307` usa `os.environ.get() == "true"` → Railway = desactivado. Env script lo activa. Efecto real en prod: OFF |

---

## Flags en env script ausentes de Railway (sin discrepancia real)

| Flag | Env Script | Railway | Veredicto |
|------|-----------|---------|-----------|
| `USE_TEMPLATE_SYSTEM` | true | *(no var)* | Dead flag — no encontrado en Python. Sin efecto |
| `ENABLE_POOL_MATCHING` | true | *(no var)* | Code default = true (`feature_flags.py:36`). Railway usa default → ambos true. Sin discrepancia |
| `ENABLE_INTENT_CONFIDENCE_SCORE` | true | *(no var)* | Dead flag — no encontrado en Python. Sin efecto |
| `ENABLE_ECHO` | false | *(no var)* | Probablemente dead flag |

---

## Resumen ejecutivo

**Env script (`env_ccee_gemma4_31b_full.sh`) fue creado antes de la audit W8 (2026-04-03).** Desde entonces, 7 sistemas fueron desactivados en Railway via `dbf0cd11` y siguen OFF. El env script nunca se actualizó.

**Para CCEE baseline que matchee prod exacto, aplicar estos overrides sobre el env script:**

```bash
# Corregir derive env script → Railway
export USE_COMPRESSED_DOC_D=false          # drift en Railway; memoria: stays off
export ENABLE_FEW_SHOT=false               # intentional OFF desde dbf0cd11
export ENABLE_LENGTH_HINTS=false           # bisect regression + dbf0cd11
export ENABLE_RERANKING=true               # Railway=true; env script tenía false (ablation artifact)
export ENABLE_CITATIONS=false              # dbf0cd11
export ENABLE_OUTPUT_VALIDATION=false      # sistema vaciado (1b3bc213)
export ENABLE_RESPONSE_FIXES=false         # dbf0cd11
export ENABLE_MESSAGE_SPLITTING=false      # W8 audit
export ENABLE_BLACKLIST_REPLACEMENT=false  # default false = Railway
export ENABLE_STYLE_ANCHOR=false           # Railway no tiene la var → efectivamente false
export ENABLE_SELL_ARBITER_LIVE=true       # PR #80 — no está en env script pero sí en Railway
```

**Acción pendiente en Railway:** `USE_COMPRESSED_DOC_D=true` en Railway es drift. Debe corregirse a `false` independientemente del CCEE run.

---

## Comando CCEE baseline prod-fiel

```bash
cd /Users/manelbertranluque/Clonnect/backend

# 1. Cargar env base
source config/env_ccee_gemma4_31b_full.sh
export $(grep -v '^#' .env | grep DEEPINFRA_API_KEY | xargs)

# 2. Overrides prod-match (Railway state 2026-04-22)
export USE_COMPRESSED_DOC_D=false
export ENABLE_FEW_SHOT=false
export ENABLE_LENGTH_HINTS=false
export ENABLE_RERANKING=true
export ENABLE_CITATIONS=false
export ENABLE_OUTPUT_VALIDATION=false
export ENABLE_RESPONSE_FIXES=false
export ENABLE_MESSAGE_SPLITTING=false
export ENABLE_BLACKLIST_REPLACEMENT=false
export ENABLE_STYLE_ANCHOR=false
export ENABLE_SELL_ARBITER_LIVE=true

# 3. Run
nohup .venv/bin/python3 -W ignore::FutureWarning -u scripts/run_ccee.py \
    --creator iris_bertran \
    --runs 3 --cases 50 \
    --multi-turn --v4-composite --v5 \
    --save-as "baseline_post_p4_live_20260422" \
    > /tmp/baseline_post_p4.log 2>&1 &
echo "PID: $!"
```
