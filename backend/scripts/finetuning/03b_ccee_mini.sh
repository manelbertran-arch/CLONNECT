#!/bin/bash
# =========================================================================
# CCEE-Mini — subset 20 cases para gate intermedio entre fases Sprint 7
# =========================================================================
#
# Uso:
#   bash 03b_ccee_mini.sh <fase> <endpoint_url> [num_runs]
#
# Ejemplos:
#   bash 03b_ccee_mini.sh BL_pipeline https://my-bl-endpoint.deepinfra.com 1
#   bash 03b_ccee_mini.sh sft_fase1 https://my-sft-endpoint.modal.run 1
#
# CCEE-Mini = 20 cases × 1 run (~$0.10, ~10 min)
# CCEE Full  = 50 cases × 3 runs (~$1.50, ~30 min)
#
# Gate: si CCEE-Mini composite mejora >3pts → continuar a siguiente fase.
# =========================================================================

set -euo pipefail

FASE="${1:-mini_test}"
ENDPOINT="${2:?ERROR: endpoint URL required}"
NUM_RUNS="${3:-1}"  # Mini: 1 run es suficiente para señal rápida

DATE=$(date +%Y%m%d_%H%M)
OUTFILE="tests/ccee_results/iris_bertran/mini_${FASE}_${DATE}.json"
BASELINE_FILE="tests/ccee_results/iris_bertran/baseline_post_revert_fewshot_commitment_20260424.json"

cd ~/Clonnect/backend

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║  CCEE-Mini Measurement — 20 cases, Sprint 7 gate          ║"
echo "╚═══════════════════════════════════════════════════════════╝"
echo "Fase:       $FASE"
echo "Endpoint:   $ENDPOINT"
echo "Runs:       $NUM_RUNS (Mini: 1 run)"
echo "Cases:      20 (stratified, seed=3407)"
echo "Output:     $OUTFILE"
echo ""

# Preflight
echo "🔍 Testing endpoint..."
if ! curl -sL -m 10 -o /dev/null -w "%{http_code}" "${ENDPOINT}/models" | grep -qE "^(200|404|405)"; then
    echo "❌ ERROR: Endpoint not reachable: $ENDPOINT"
    exit 1
fi
echo "✅ Endpoint reachable"
echo ""

# Config env
if [ -f config/env_prod_mirror_20260422.sh ]; then
    source config/env_prod_mirror_20260422.sh
fi

export LLM_ENDPOINT="$ENDPOINT"
export DEEPINFRA_BASE_URL="$ENDPOINT"
export DEEPINFRA_MODEL="gemma31b-iris-${FASE}"
export LLM_MODEL="gemma31b-iris-${FASE}"
export CCEE_NO_FALLBACK=1
export DEEPINFRA_TIMEOUT=180
export CCEE_INTER_CASE_DELAY=1
export CCEE_SEED=3407  # Mini uses seed=3407 for reproducibility

set -a && source .env && set +a

echo "🚀 Starting CCEE-Mini (${NUM_RUNS} run × 20 cases)..."
echo ""

python3.11 -W ignore::FutureWarning -u scripts/run_ccee.py \
    --creator iris_bertran \
    --runs "$NUM_RUNS" \
    --cases 20 \
    --multi-turn \
    --mt-conversations 5 \
    --mt-turns 10 \
    --v4-composite \
    --v41-metrics \
    --v5 \
    --v52-fixes \
    --save-as "mini_${FASE}_${DATE}" 2>&1 | tee "/tmp/ccee_mini_${FASE}_${DATE}.log"

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║  CCEE-Mini RESULTS                                        ║"
echo "╚═══════════════════════════════════════════════════════════╝"

python3.11 << PYEOF
import json, statistics
from pathlib import Path

outfile = Path("$OUTFILE")
if not outfile.exists():
    print(f"❌ Output not found: {outfile}")
    exit(1)

data = json.load(open(outfile))
v5 = data.get("v5_composite", {})
score = v5.get("score") if isinstance(v5, dict) else v5
dims = v5.get("dimension_scores", {}) if isinstance(v5, dict) else {}

BASELINE_FULL = 67.7  # BL_pipeline_c0bcbd73 Full composite (3×50)

print(f"\n📊 CCEE-Mini composite: {score:.1f}")
print(f"   Δ vs BL Full (67.7): {score - BASELINE_FULL:+.1f}")
print()
for d, s in dims.items():
    print(f"   {d}: {s:.1f}")

print()
if score and score - BASELINE_FULL > 3:
    print("✅ Mini gate: PASS — continuar fase siguiente")
elif score and score - BASELINE_FULL > -2:
    print("🟡 Mini gate: MARGINAL — revisar antes de continuar")
else:
    print("🔴 Mini gate: FAIL — investigar antes de continuar")
PYEOF

echo ""
echo "✅ CCEE-Mini done. Compare with Full before committing to next phase."
