#!/bin/bash
# Sprint 10 — Setup Vast.ai H200 80GB
# Run: bash setup_sprint10_h200.sh
# Requires env: HF_TOKEN

set -euo pipefail

echo "============================================================"
echo "  Sprint 10 — Vast.ai H200 Setup"
echo "  $(date)"
echo "============================================================"

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

echo ""
echo "=== GPU Check ==="
nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader
gpu_mem=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
if [ "$gpu_mem" -lt 75000 ]; then
    echo "WARNING: GPU has ${gpu_mem}MB VRAM — need 80GB for 32B+bf16"
    echo "Minimum: H200 80GB or A100 80GB"
    echo "Continue? (Ctrl-C to abort)"
    sleep 5
fi

echo ""
echo "=== Disk Check ==="
df -h /workspace 2>/dev/null || df -h /
free_disk=$(df / | tail -1 | awk '{print $4}')
echo "Free disk: ${free_disk} KB"

echo ""
echo "=== RAM Check ==="
free -h

echo ""
echo "=== Python Check ==="
python3 --version
which python3

# ---------------------------------------------------------------------------
# Install dependencies
# ---------------------------------------------------------------------------

echo ""
echo "=== Installing dependencies ==="

pip install --upgrade pip --quiet

# Unsloth with CUDA 12.4 + PyTorch 2.4 (H200 compatible)
pip install "unsloth[cu124-torch240] @ git+https://github.com/unslothai/unsloth.git" --quiet

# Training stack
pip install \
    "transformers>=4.51.0" \
    "trl>=0.9.6" \
    "datasets>=2.20.0" \
    "huggingface_hub>=0.24.0" \
    "accelerate>=0.30.0" \
    "bitsandbytes>=0.43.0" \
    "peft>=0.11.0" \
    --quiet

# Verify imports
python3 -c "
import torch, unsloth, transformers, trl, datasets, peft
print(f'torch: {torch.__version__} (CUDA: {torch.cuda.is_available()})')
print(f'unsloth: ok')
print(f'transformers: {transformers.__version__}')
print(f'trl: {trl.__version__}')
print(f'peft: {peft.__version__}')
print(f'GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB')
"

echo ""
echo "=== HF Login ==="
if [ -z "${HF_TOKEN:-}" ]; then
    echo "ERROR: HF_TOKEN not set"
    echo "Export with: export HF_TOKEN=hf_..."
    exit 1
fi
huggingface-cli login --token "$HF_TOKEN"

# ---------------------------------------------------------------------------
# Clone/sync repo
# ---------------------------------------------------------------------------

echo ""
echo "=== Syncing repo ==="
WORKSPACE="${WORKSPACE:-/workspace}"

if [ -d "$WORKSPACE/Clonnect" ]; then
    echo "Repo exists — pulling latest"
    cd "$WORKSPACE/Clonnect"
    git pull origin sprint10/w3-training-pipeline
else
    echo "Cloning repo"
    cd "$WORKSPACE"
    git clone https://github.com/manelbertran-arch/CLONNECT.git Clonnect
    cd Clonnect
    git checkout sprint10/w3-training-pipeline
fi

BACKEND="$WORKSPACE/Clonnect/backend"
cd "$BACKEND"

# ---------------------------------------------------------------------------
# Dataset checks
# ---------------------------------------------------------------------------

echo ""
echo "=== Dataset Status ==="

if [ -f "data/dpo/trl/sft_v4_multiturn.jsonl" ]; then
    lines=$(wc -l < data/dpo/trl/sft_v4_multiturn.jsonl)
    echo "[OK] SFT W2 dataset: sft_v4_multiturn.jsonl ($lines lines)"
elif [ -f "data/dpo/trl/sft_v3_clean.jsonl" ]; then
    lines=$(wc -l < data/dpo/trl/sft_v3_clean.jsonl)
    echo "[FALLBACK] SFT W1 dataset: sft_v3_clean.jsonl ($lines lines)"
else
    echo "[ERROR] No SFT dataset found!"
    exit 1
fi

if [ -f "data/dpo/trl/dpo_iris_v3_clean.jsonl" ]; then
    lines=$(wc -l < data/dpo/trl/dpo_iris_v3_clean.jsonl)
    echo "[OK] DPO W1 dataset: dpo_iris_v3_clean.jsonl ($lines lines)"
elif [ -f "data/dpo/trl/dpo_iris_v2.jsonl" ]; then
    lines=$(wc -l < data/dpo/trl/dpo_iris_v2.jsonl)
    echo "[FALLBACK] DPO dataset: dpo_iris_v2.jsonl ($lines lines)"
else
    echo "[ERROR] No DPO dataset found!"
    exit 1
fi

# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

LOG_DIR="$WORKSPACE/logs"
mkdir -p "$LOG_DIR"
mkdir -p output/sprint10/sft output/sprint10/dpo

echo ""
echo "============================================================"
echo "  PHASE 1: SFT Training"
echo "  Start: $(date)"
echo "============================================================"

python sprint10/01_train_sft.py 2>&1 | tee "$LOG_DIR/sft_$(date +%Y%m%d_%H%M).log"

SFT_EXIT=${PIPESTATUS[0]}
if [ "$SFT_EXIT" -ne 0 ]; then
    echo "ERROR: SFT training failed (exit $SFT_EXIT)"
    exit "$SFT_EXIT"
fi

echo ""
echo "=== SFT Complete: $(date) ==="
echo "Adapter pushed to: manelbertranluque/clonnect-iris-sft-sprint10-qwen3-32b"

echo ""
echo "============================================================"
echo "  PHASE 2: DPO Training"
echo "  Start: $(date)"
echo "============================================================"

python sprint10/02_train_dpo.py 2>&1 | tee "$LOG_DIR/dpo_$(date +%Y%m%d_%H%M).log"

DPO_EXIT=${PIPESTATUS[0]}
if [ "$DPO_EXIT" -ne 0 ]; then
    echo "ERROR: DPO training failed (exit $DPO_EXIT)"
    exit "$DPO_EXIT"
fi

echo ""
echo "============================================================"
echo "  Sprint 10 Training COMPLETE"
echo "  End: $(date)"
echo "============================================================"
echo ""
echo "Adapters in HF:"
echo "  SFT: manelbertranluque/clonnect-iris-sft-sprint10-qwen3-32b"
echo "  DPO: manelbertranluque/clonnect-iris-dpo-sprint10-qwen3-32b"
echo ""
echo "Next: run CCEE evaluation with sprint10 adapter"
