#!/bin/bash
# =========================================================================
# FASE 1/2/3 — Medición CCEE post-fine-tuning
# Script reproducible para comparar modelo FT vs baseline 69.5
# =========================================================================
#
# Uso:
#   bash 03_ccee_measurement.sh <fase> <endpoint_url> [num_runs]
#
# Ejemplos:
#   bash 03_ccee_measurement.sh sft https://my-sft-endpoint.deepinfra.com
#   bash 03_ccee_measurement.sh dpo http://localhost:8000 3
#   bash 03_ccee_measurement.sh grpo_v1 https://api.modal.run/... 3
#
# =========================================================================

set -euo pipefail

# ============ PARAMS ============
FASE="${1:-sft}"                                    # sft | dpo | grpo_v1 | grpo_v2 ...
ENDPOINT="${2:?ERROR: endpoint URL required}"
NUM_RUNS="${3:-3}"                                  # 3 runs mínimo para σ confiable

# Naming
DATE=$(date +%Y%m%d_%H%M)
OUTFILE="tests/ccee_results/iris_bertran/ft_${FASE}_${DATE}.json"
BASELINE_FILE="tests/ccee_results/iris_bertran/baseline_post_revert_fewshot_commitment_20260424.json"

# ============ PRE-FLIGHT ============
cd ~/Clonnect/backend

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║  CCEE Measurement — Fine-tuning Sprint                             ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo "Fase:         $FASE"
echo "Endpoint:     $ENDPOINT"
echo "Runs:         $NUM_RUNS"
echo "Output:       $OUTFILE"
echo "Baseline:     69.5 (σ=0.08) — $BASELINE_FILE"
echo ""

# Verificar baseline existe
if [ ! -f "$BASELINE_FILE" ]; then
    echo "⚠️  WARNING: Baseline file not found. Continuing anyway."
fi

# Verificar endpoint accesible
echo "🔍 Testing endpoint..."
if ! curl -s -m 10 -o /dev/null -w "%{http_code}" "$ENDPOINT" | grep -qE "^(200|404|405)"; then
    echo "❌ ERROR: Endpoint not reachable: $ENDPOINT"
    exit 1
fi
echo "✅ Endpoint reachable"
echo ""

# ============ CONFIG ENV ============
# Cargar env production mirror
if [ -f config/env_prod_mirror_20260422.sh ]; then
    source config/env_prod_mirror_20260422.sh
    echo "✅ Loaded config/env_prod_mirror_20260422.sh"
else
    echo "⚠️  env_prod_mirror_20260422.sh not found — usando defaults"
fi

# Override endpoint para apuntar al modelo FT
export LLM_ENDPOINT="$ENDPOINT"
export DEEPINFRA_BASE_URL="$ENDPOINT"
export DEEPINFRA_MODEL="gemma31b-iris-${FASE}"
export LLM_MODEL="gemma31b-iris-${FASE}"
export CCEE_NO_FALLBACK=1          # Fallar si LLM judge no disponible (no mock)

# Load .env
set -a && source .env && set +a

# ============ RUN CCEE ============
echo ""
echo "🚀 Starting CCEE measurement (${NUM_RUNS} runs)..."
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
    --save-as "ft_${FASE}_${DATE}" 2>&1 | tee "/tmp/ccee_${FASE}_${DATE}.log"

# ============ PARSE RESULTS ============
echo ""
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║  RESULTS                                                           ║"
echo "╚════════════════════════════════════════════════════════════════════╝"

python3.11 << PYEOF
import json
import statistics
from pathlib import Path

outfile = Path("$OUTFILE")
baseline_file = Path("$BASELINE_FILE")

if not outfile.exists():
    print(f"❌ Output file not found: {outfile}")
    exit(1)

data = json.load(open(outfile))
runs = data.get("runs", [data])

# Extract composite v5 per run
composites_v5 = []
dimensions = {"J6": [], "B2": [], "C3": [], "K": [], "L": [], "H": [], "B": []}

for run in runs:
    v5 = run.get("v5_composite")
    if v5 is not None:
        composites_v5.append(v5)

    # Collect dimension scores
    for dim in dimensions:
        val = run.get(dim) or run.get(f"{dim}_persona_consistency") or \
              run.get(f"{dim}_contextual_appropriateness")
        if isinstance(val, dict):
            val = val.get("score")
        if isinstance(val, (int, float)):
            dimensions[dim].append(val)

# Stats
mean_v5 = statistics.mean(composites_v5) if composites_v5 else None
sigma_v5 = statistics.stdev(composites_v5) if len(composites_v5) > 1 else 0

print(f"\n📊 COMPOSITE V5:")
print(f"   Runs: {composites_v5}")
print(f"   Mean: {mean_v5:.2f}")
print(f"   σ:    {sigma_v5:.2f}")

# Baseline comparison
BASELINE = 69.5
BASELINE_SIGMA = 0.08
if mean_v5:
    delta = mean_v5 - BASELINE
    print(f"\n📈 vs BASELINE (69.5, σ=0.08):")
    print(f"   Δ:    {delta:+.2f}")
    # Significance check: delta > 2σ?
    combined_sigma = (sigma_v5**2 + BASELINE_SIGMA**2)**0.5
    if abs(delta) > 2 * combined_sigma:
        print(f"   ✅ STATISTICALLY SIGNIFICANT (|Δ| > 2σ_combined={2*combined_sigma:.2f})")
    else:
        print(f"   ⚠️  NOT SIGNIFICANT (|Δ| < 2σ_combined={2*combined_sigma:.2f}) — correr más runs")

# Dimensions critical (J6, B2, C3 = known weak)
print(f"\n🎯 CRITICAL DIMENSIONS (weak baseline: J6=35, B2=28.5, C3=21):")
for dim in ["J6", "B2", "C3"]:
    vals = dimensions.get(dim, [])
    if vals:
        m = statistics.mean(vals)
        print(f"   {dim}: {m:.1f}")

# Gate decision
print(f"\n{'='*68}")
if mean_v5:
    print("🚦 GATE DECISION:")
    if mean_v5 >= 78:
        print(f"   ✅ OBJECTIVE ACHIEVED ({mean_v5:.1f} ≥ 78) — DEPLOY")
    elif mean_v5 >= 75:
        print(f"   ➡️  Close to objective ({mean_v5:.1f} ∈ [75,77.9]) — CONSIDER FASE 2 (DPO)")
    elif mean_v5 >= 73:
        print(f"   ➡️  Good improvement ({mean_v5:.1f} ∈ [73,74.9]) — FASE 2 DPO recommended")
    elif mean_v5 >= 70:
        print(f"   ⚠️  Marginal ({mean_v5:.1f} ∈ [70,72.9]) — FASE 3 GRPO recommended (pair-quality ceiling)")
    else:
        print(f"   🛑 REGRESSION ({mean_v5:.1f} < 70) — STOP, debug config/data BEFORE spending more")
print(f"{'='*68}\n")

# Save summary
summary = {
    "fase": "$FASE",
    "date": "$DATE",
    "composites_v5": composites_v5,
    "mean_v5": mean_v5,
    "sigma_v5": sigma_v5,
    "delta_baseline": mean_v5 - BASELINE if mean_v5 else None,
    "dimensions_critical": {d: statistics.mean(v) if v else None for d, v in dimensions.items() if d in ["J6", "B2", "C3"]},
}
summary_path = outfile.with_suffix(".summary.json")
json.dump(summary, open(summary_path, "w"), indent=2)
print(f"Summary saved: {summary_path}")

PYEOF

echo ""
echo "✅ Done. Update 00_HANDOFF log with results."
