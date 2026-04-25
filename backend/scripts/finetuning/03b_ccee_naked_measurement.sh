#!/bin/bash
# =========================================================================
# NAKED MODE — Medición CCEE sin pipeline de producción
# Aísla la variable modelo del pipeline para diagnóstico de distribution shift.
#
# Diferencia vs 03_ccee_measurement.sh:
#   - --naked-mode: el LLM recibe solo {"role":"user","content":"<case>"}
#   - Sin system prompt, sin Doc D, sin RAG, sin few-shots
#   - Output con prefijo "naked_" en el filename JSON
#
# Uso:
#   bash 03b_ccee_naked_measurement.sh <label> <endpoint_url> [num_runs]
#
# Ejemplos:
#   bash 03b_ccee_naked_measurement.sh ft_naked \
#     https://manelbertran-arch--clonnect-iris-serve-serve.modal.run/v1 3
#
#   bash 03b_ccee_naked_measurement.sh baseline_naked \
#     https://api.deepinfra.com/v1/openai 3
# =========================================================================

set -euo pipefail

# ============ PARAMS ============
LABEL="${1:-ft_naked}"
ENDPOINT="${2:?ERROR: endpoint URL required}"
NUM_RUNS="${3:-3}"

DATE=$(date +%Y%m%d_%H%M)
OUTFILE="tests/ccee_results/iris_bertran/naked_${LABEL}_${DATE}.json"
BASELINE_FILE="tests/ccee_results/iris_bertran/baseline_post_revert_fewshot_commitment_20260424.json"

# ============ PRE-FLIGHT ============
cd ~/Clonnect/backend

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║  CCEE Naked Measurement — Distribution Shift Diagnostic            ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo "Label:        $LABEL"
echo "Endpoint:     $ENDPOINT"
echo "Runs:         $NUM_RUNS"
echo "Output:       $OUTFILE"
echo "Mode:         NAKED (no system prompt, no Doc D, no RAG)"
echo ""

if [ ! -f "$BASELINE_FILE" ]; then
    echo "⚠️  WARNING: Baseline file not found. Continuing anyway."
fi

echo "🔍 Testing endpoint..."
if ! curl -sL -m 15 -o /dev/null -w "%{http_code}" "${ENDPOINT}/models" | grep -qE "^(200|404|405)"; then
    echo "❌ ERROR: Endpoint not reachable: $ENDPOINT"
    exit 1
fi
echo "✅ Endpoint reachable"
echo ""

# ============ CONFIG ENV ============
if [ -f config/env_prod_mirror_20260422.sh ]; then
    source config/env_prod_mirror_20260422.sh
    echo "✅ Loaded config/env_prod_mirror_20260422.sh"
else
    echo "⚠️  env_prod_mirror_20260422.sh not found — usando defaults"
fi

export LLM_ENDPOINT="$ENDPOINT"
export DEEPINFRA_BASE_URL="$ENDPOINT"
export DEEPINFRA_TIMEOUT=180
export CCEE_NO_FALLBACK=1
export CCEE_INTER_CASE_DELAY=1

# Naked: model name must match what the endpoint serves
# For FT endpoint: gemma31b-iris-sft
# For baseline DeepInfra: google/gemma-4-31B-it
if [[ "$LABEL" == *"baseline"* ]]; then
    export DEEPINFRA_MODEL="google/gemma-4-31B-it"
    export LLM_MODEL="google/gemma-4-31B-it"
    echo "✅ Model: google/gemma-4-31B-it (baseline)"
else
    export DEEPINFRA_MODEL="gemma31b-iris-sft"
    export LLM_MODEL="gemma31b-iris-sft"
    echo "✅ Model: gemma31b-iris-sft (FT)"
fi

set -a && source .env && set +a

# ============ RUN CCEE — NAKED MODE ============
echo ""
echo "🚀 Starting CCEE naked measurement (${NUM_RUNS} runs)..."
echo ""

python3.11 -W ignore::FutureWarning -u scripts/run_ccee.py \
    --creator iris_bertran \
    --runs "$NUM_RUNS" \
    --cases 50 \
    --multi-turn \
    --mt-conversations 5 \
    --mt-turns 10 \
    --v4-composite \
    --v41-metrics \
    --v5 \
    --v52-fixes \
    --naked-mode \
    --save-as "naked_${LABEL}_${DATE}" 2>&1 | tee "/tmp/ccee_naked_${LABEL}_${DATE}.log"

# ============ PARSE RESULTS ============
echo ""
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║  RESULTS                                                           ║"
echo "╚════════════════════════════════════════════════════════════════════╝"

python3.11 << PYEOF
import json, statistics
from pathlib import Path

outfile = Path("$OUTFILE")
if not outfile.exists():
    # Try partial
    partial = outfile.with_suffix("").with_suffix("").parent / f"naked_${LABEL}_${DATE}_partial.json"
    if partial.exists():
        outfile = partial
        print(f"⚠️  Using partial: {partial}")
    else:
        print(f"❌ Output not found: {outfile}")
        exit(1)

data = json.load(open(outfile))
v5 = data.get('v5_composite', {})
score = v5.get('score') if isinstance(v5, dict) else None
dims = v5.get('dimension_scores', {}) if isinstance(v5, dict) else {}

print(f"\n📊 NAKED v5_composite: {score}")
print(f"\n🎯 Dimensions:")
for d, v in sorted(dims.items()):
    print(f"   {d:6s}: {v:.1f}")

BASELINE = 69.5
if score:
    delta = score - BASELINE
    print(f"\n📈 vs pipeline baseline (69.5): {delta:+.1f}")

    pipeline_ft = 66.4
    delta_ft = score - pipeline_ft
    print(f"📈 vs pipeline FT (66.4):      {delta_ft:+.1f}")

print(f"\n{'='*68}")
print(f"Pipeline: metadata.pipeline_version = {data.get('metadata',{}).get('pipeline_version','?')}")
print(f"naked_mode: {data.get('metadata',{}).get('flags',{}).get('naked_mode','?')}")
print(f"{'='*68}")
PYEOF

echo ""
echo "✅ Done. Log: /tmp/ccee_naked_${LABEL}_${DATE}.log"
