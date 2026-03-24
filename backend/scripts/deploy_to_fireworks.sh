#!/usr/bin/env bash
# =============================================================================
# Deploy fine-tuned Iris LoRA adapter to Fireworks.ai
# =============================================================================
#
# Fireworks supports serverless LoRA on top of base models (Qwen3-8B/32B).
# The adapter is uploaded directly — no merging needed.
#
# Prerequisites:
#   pip install fireworks-ai
#   fireworks login
#
# Usage:
#   bash scripts/deploy_to_fireworks.sh <adapter_dir>
#   bash scripts/deploy_to_fireworks.sh ./lora_adapter
#   bash scripts/deploy_to_fireworks.sh /output/clonnect-iris-dpo
# =============================================================================

set -euo pipefail

ADAPTER_DIR="${1:-}"
ACCOUNT="clonnect"
MODEL_NAME="iris-qwen32b-dpo-v1"
BASE_MODEL="accounts/fireworks/models/qwen3-32b"

if [ -z "$ADAPTER_DIR" ]; then
    echo "Usage: $0 <adapter_directory>"
    echo ""
    echo "The adapter directory should contain:"
    echo "  - adapter_config.json"
    echo "  - adapter_model.safetensors (or .bin)"
    echo ""
    echo "Steps:"
    echo "  1. Upload LoRA adapter to Fireworks"
    echo "  2. Deploy as serverless LoRA (no dedicated GPU needed)"
    echo "  3. Configure Railway env vars"
    exit 1
fi

if [ ! -d "$ADAPTER_DIR" ]; then
    echo "ERROR: Directory not found: $ADAPTER_DIR"
    exit 1
fi

echo "=============================================="
echo " Step 1: Create model on Fireworks"
echo "=============================================="
echo ""
echo "Running: fireworks models create $MODEL_NAME"
fireworks models create \
    --display-name "Iris Bertran DPO v1" \
    --description "QLoRA adapter for Iris voice clone (Qwen3-32B base)" \
    "accounts/${ACCOUNT}/models/${MODEL_NAME}" 2>/dev/null || echo "(model may already exist)"

echo ""
echo "=============================================="
echo " Step 2: Upload LoRA adapter"
echo "=============================================="
echo ""
echo "Uploading from: $ADAPTER_DIR"
fireworks models upload \
    "accounts/${ACCOUNT}/models/${MODEL_NAME}" \
    "$ADAPTER_DIR" \
    --base-model "$BASE_MODEL" \
    --lora

echo ""
echo "=============================================="
echo " Step 3: Deploy (serverless LoRA)"
echo "=============================================="
echo ""
echo "Fireworks deploys LoRA adapters serverlessly — no dedicated GPU needed."
echo "The adapter is loaded on-demand on top of the base model."
echo ""
fireworks models deploy "accounts/${ACCOUNT}/models/${MODEL_NAME}" 2>/dev/null || echo "(may auto-deploy)"
echo ""
echo "Model endpoint: accounts/${ACCOUNT}/models/${MODEL_NAME}"
echo "Pricing: ~\$0.20/M input, ~\$0.20/M output (serverless LoRA)"

echo ""
echo "=============================================="
echo " Step 4: Configure Railway"
echo "=============================================="
echo ""
echo "  # Set Fireworks API key (if not already set)"
echo "  railway variables set FIREWORKS_API_KEY=<your_key>"
echo ""
echo "  # Set the model identifier"
echo "  railway variables set FIREWORKS_MODEL=accounts/${ACCOUNT}/models/${MODEL_NAME}"
echo ""
echo "  # Switch primary provider to Fireworks"
echo "  railway variables set LLM_PRIMARY_PROVIDER=fireworks"
echo ""
echo "  # Rollback to Gemini:"
echo "  railway variables set LLM_PRIMARY_PROVIDER=gemini"

echo ""
echo "=============================================="
echo " Step 5: Verify"
echo "=============================================="
echo ""
echo '  curl https://api.fireworks.ai/inference/v1/chat/completions \'
echo '    -H "Authorization: Bearer $FIREWORKS_API_KEY" \'
echo '    -H "Content-Type: application/json" \'
echo "    -d '{\"model\": \"accounts/${ACCOUNT}/models/${MODEL_NAME}\", \"messages\": [{\"role\":\"user\",\"content\":\"Hola Iris!\"}]}'"
echo ""
echo "=============================================="
echo " DONE"
echo "=============================================="
