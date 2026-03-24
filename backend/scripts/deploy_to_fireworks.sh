#!/usr/bin/env bash
# =============================================================================
# Deploy fine-tuned Iris LoRA adapter to Fireworks.ai
# =============================================================================
#
# Fireworks supports serverless LoRA on top of base models (Qwen3-8B/32B).
# The adapter is uploaded directly — no merging needed.
#
# Two variants:
#   8B  — Cheaper, faster, recommended for production
#   32B — Higher quality, more expensive
#
# Prerequisites:
#   pip install firectl together    (firectl = Fireworks CLI)
#   firectl signin
#   together login                  (if downloading from Together)
#
# Usage:
#   bash scripts/deploy_to_fireworks.sh 8b  <adapter_dir>
#   bash scripts/deploy_to_fireworks.sh 32b <adapter_dir>
#   bash scripts/deploy_to_fireworks.sh 8b  together <together_job_id>
#
# =============================================================================
#
# COMPLETE WORKFLOW: Together SFT/DPO -> Fireworks Serverless LoRA
#
# --- STEP 0: Know your Together job IDs ---
# SFT-8B:  ft-b2b5feea-584e  -> manelbertran_c647/Qwen3-8B-iris-sft-8b-v1-877e513f
# SFT-32B: ft-89ee8dcf-01de  -> manelbertran_c647/Qwen3-32B-iris-sft-32b-v1-61ee8d5b
# DPO-8B:  (pending — launch from SFT-8B checkpoint)
# DPO-32B: (pending — launch from SFT-32B checkpoint)
#
# --- STEP 1: Download adapter from Together ---
# together fine-tuning download ft-XXXXX --output ./lora_8b_dpo/
#
# The download creates a directory with:
#   adapter_config.json
#   adapter_model.safetensors
#   (plus tokenizer files inherited from base)
#
# --- STEP 2: Upload to Fireworks ---
# firectl create model accounts/clonnect/models/iris-8b-dpo-v1 \
#   --display-name "Iris 8B DPO v1" \
#   --description "Voice clone for Iris Bertran (Qwen3-8B + LoRA)"
#
# firectl deploy accounts/clonnect/models/iris-8b-dpo-v1 \
#   --base-model accounts/fireworks/models/qwen3-8b \
#   --adapter-path ./lora_8b_dpo/ \
#   --min-replica 0  (scale to zero = serverless, no idle cost)
#
# --- STEP 3: Configure Railway ---
# railway variables set FIREWORKS_MODEL=accounts/clonnect/models/iris-8b-dpo-v1
# railway variables set LLM_PRIMARY_PROVIDER=fireworks
#
# --- STEP 4: Verify ---
# curl https://api.fireworks.ai/inference/v1/chat/completions \
#   -H "Authorization: Bearer $FIREWORKS_API_KEY" \
#   -H "Content-Type: application/json" \
#   -d '{"model":"accounts/clonnect/models/iris-8b-dpo-v1",
#        "messages":[{"role":"user","content":"Hola Iris!"}]}'
#
# --- ROLLBACK ---
# railway variables set LLM_PRIMARY_PROVIDER=gemini
#
# =============================================================================

set -euo pipefail

VARIANT="${1:-}"
SOURCE="${2:-}"
TOGETHER_JOB="${3:-}"

ACCOUNT="clonnect"

case "$VARIANT" in
    8b)
        MODEL_NAME="iris-8b-dpo-v1"
        BASE_MODEL="accounts/fireworks/models/qwen3-8b"
        DISPLAY="Iris 8B DPO v1"
        DESC="Voice clone for Iris Bertran (Qwen3-8B + QLoRA)"
        ;;
    32b)
        MODEL_NAME="iris-32b-dpo-v1"
        BASE_MODEL="accounts/fireworks/models/qwen3-32b"
        DISPLAY="Iris 32B DPO v1"
        DESC="Voice clone for Iris Bertran (Qwen3-32B + QLoRA)"
        ;;
    *)
        echo "Usage:"
        echo "  $0 8b  <adapter_dir>                 Deploy local 8B adapter"
        echo "  $0 32b <adapter_dir>                 Deploy local 32B adapter"
        echo "  $0 8b  together <together_job_id>    Download from Together + deploy 8B"
        echo "  $0 32b together <together_job_id>    Download from Together + deploy 32B"
        echo ""
        echo "Known Together jobs:"
        echo "  SFT-8B:  ft-b2b5feea-584e"
        echo "  SFT-32B: ft-89ee8dcf-01de"
        echo "  DPO-8B:  (pending)"
        echo "  DPO-32B: (pending)"
        echo ""
        echo "Recommended: 8B for production (cheaper, faster, serverless LoRA)"
        exit 0
        ;;
esac

ADAPTER_DIR="$SOURCE"

# ── If source is "together", download first ──────────────────────────────

if [ "$SOURCE" = "together" ]; then
    if [ -z "$TOGETHER_JOB" ]; then
        echo "ERROR: missing Together job ID"
        echo "Usage: $0 $VARIANT together <job_id>"
        exit 1
    fi
    ADAPTER_DIR="./lora_${VARIANT}_$(echo "$TOGETHER_JOB" | tail -c 8)"

    echo "=============================================="
    echo " Step 0: Download adapter from Together"
    echo "=============================================="
    echo ""
    mkdir -p "$ADAPTER_DIR"
    together fine-tuning download "$TOGETHER_JOB" --output "$ADAPTER_DIR"
    echo "Downloaded to: $ADAPTER_DIR"
    ls -la "$ADAPTER_DIR"
    echo ""
fi

if [ ! -d "$ADAPTER_DIR" ]; then
    echo "ERROR: Directory not found: $ADAPTER_DIR"
    exit 1
fi

# ── Step 1: Create model on Fireworks ────────────────────────────────────

echo "=============================================="
echo " Step 1: Create model on Fireworks"
echo "=============================================="
echo ""
echo "Model: accounts/${ACCOUNT}/models/${MODEL_NAME}"
firectl create model "accounts/${ACCOUNT}/models/${MODEL_NAME}" \
    --display-name "$DISPLAY" \
    --description "$DESC" 2>/dev/null || echo "(model may already exist)"

# ── Step 2: Deploy with LoRA adapter ─────────────────────────────────────

echo ""
echo "=============================================="
echo " Step 2: Deploy serverless LoRA"
echo "=============================================="
echo ""
echo "Base model: $BASE_MODEL"
echo "Adapter:    $ADAPTER_DIR"
echo ""
firectl deploy "accounts/${ACCOUNT}/models/${MODEL_NAME}" \
    --base-model "$BASE_MODEL" \
    --adapter-path "$ADAPTER_DIR" \
    --min-replica 0
echo ""
echo "Deployed: accounts/${ACCOUNT}/models/${MODEL_NAME}"
echo "Mode: serverless (min-replica=0, scales to zero when idle)"
echo "Pricing: ~\$0.20/M input, ~\$0.20/M output"

# ── Step 3: Railway config ───────────────────────────────────────────────

echo ""
echo "=============================================="
echo " Step 3: Configure Railway"
echo "=============================================="
echo ""
echo "  railway variables set FIREWORKS_MODEL=accounts/${ACCOUNT}/models/${MODEL_NAME}"
echo "  railway variables set LLM_PRIMARY_PROVIDER=fireworks"
echo ""
echo "  # Rollback to Gemini:"
echo "  railway variables set LLM_PRIMARY_PROVIDER=gemini"

# ── Step 4: Verify ───────────────────────────────────────────────────────

echo ""
echo "=============================================="
echo " Step 4: Verify"
echo "=============================================="
echo ""
echo '  curl https://api.fireworks.ai/inference/v1/chat/completions \'
echo '    -H "Authorization: Bearer $FIREWORKS_API_KEY" \'
echo '    -H "Content-Type: application/json" \'
echo "    -d '{\"model\": \"accounts/${ACCOUNT}/models/${MODEL_NAME}\","
echo "         \"messages\": [{\"role\":\"user\",\"content\":\"Hola Iris!\"}]}'"
echo ""
echo "=============================================="
echo " DONE — $VARIANT deployed to Fireworks"
echo "=============================================="
