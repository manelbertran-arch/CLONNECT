#!/bin/bash
# ============================================================================
# RunPod Fine-Tuning Launch Script for Llama 4 Scout
# ============================================================================
#
# Run this on a RunPod H100/A100 80GB pod.
#
# BEFORE running, set these environment variables:
#   export HF_TOKEN="hf_your_token_here"
#   export HF_REPO="manelbertran/stefano-scout-lora"
#
# Usage:
#   chmod +x runpod_train.sh && ./runpod_train.sh
#
# ============================================================================

set -euo pipefail

echo "============================================"
echo "  Llama 4 Scout QLoRA Fine-Tuning (Unsloth)"
echo "============================================"
echo ""

# ─── Validate environment ─────────────────────────────────────────────────────
if [ -z "${HF_TOKEN:-}" ]; then
    echo "ERROR: HF_TOKEN not set. Run: export HF_TOKEN=hf_..."
    exit 1
fi

HF_REPO="${HF_REPO:-manelbertran/stefano-scout-lora}"
EPOCHS="${EPOCHS:-3}"
LR="${LR:-2e-4}"

echo "HF_REPO:  $HF_REPO"
echo "EPOCHS:   $EPOCHS"
echo "LR:       $LR"
echo ""

# ─── Step 1: Install dependencies ─────────────────────────────────────────────
echo "[1/5] Installing dependencies..."
pip install -qU "unsloth[flash-attn]" "bitsandbytes==0.43.0"
pip install -qU datasets huggingface_hub
echo "Dependencies installed."
echo ""

# ─── Step 2: Login to HuggingFace ─────────────────────────────────────────────
echo "[2/5] Logging into HuggingFace..."
huggingface-cli login --token "$HF_TOKEN"
echo ""

# ─── Step 3: Verify dataset ───────────────────────────────────────────────────
DATASET_FILE="scout_training_data.jsonl"
if [ ! -f "$DATASET_FILE" ]; then
    echo "ERROR: Dataset file not found: $DATASET_FILE"
    echo "Upload it to the pod first:"
    echo "  runpodctl send $DATASET_FILE"
    echo "  OR scp from local: scp scout_training_data.jsonl root@<pod-ip>:~/"
    exit 1
fi

LINES=$(wc -l < "$DATASET_FILE")
echo "[3/5] Dataset: $DATASET_FILE ($LINES examples)"
echo ""

# ─── Step 4: Check GPU ────────────────────────────────────────────────────────
echo "[4/5] GPU info:"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null || echo "  nvidia-smi not available"
echo ""

# ─── Step 5: Run training ─────────────────────────────────────────────────────
echo "[5/5] Starting training..."
echo "  Model:    meta-llama/Llama-4-Scout-17B-16E-Instruct"
echo "  Method:   QLoRA 4-bit (Unsloth)"
echo "  Modules:  q,k,v,o + gate,up,down"
echo "  Rank:     16, Alpha: 32"
echo "  Epochs:   $EPOCHS, LR: $LR"
echo "  Batch:    1 x 16 grad_accum = 16 effective"
echo ""

python finetune_scout.py \
    --dataset "$DATASET_FILE" \
    --hf-repo "$HF_REPO" \
    --epochs "$EPOCHS" \
    --lr "$LR" \
    --hf-token "$HF_TOKEN"

echo ""
echo "============================================"
echo "  DONE! Adapter pushed to:"
echo "  https://huggingface.co/$HF_REPO"
echo "============================================"
