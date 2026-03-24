#!/usr/bin/env bash
# =============================================================================
# Deploy fine-tuned Iris LoRA adapter to DeepInfra
# =============================================================================
#
# Two paths:
#   A) From Together.ai fine-tune job -> download adapter -> HF -> DeepInfra
#   B) From local training output -> merge or upload LoRA -> DeepInfra
#
# Prerequisites:
#   pip install together huggingface-hub
#   huggingface-cli login
#   together login  (if using path A)
#
# Usage:
#   bash scripts/deploy_to_deepinfra.sh                   # show help
#   bash scripts/deploy_to_deepinfra.sh together <job_id> # path A
#   bash scripts/deploy_to_deepinfra.sh local dpo         # path B
# =============================================================================

set -euo pipefail

HF_REPO="clonnect/iris-qwen32b-dpo-v1"
ADAPTER_DIR="./lora_adapter"

show_help() {
    echo "Usage:"
    echo "  $0 together <job_id>   Download from Together, upload to HF, deploy"
    echo "  $0 local <stage>       Use local /output/clonnect-iris-<stage>, deploy"
    echo ""
    echo "Get Together job_id from: together fine-tuning list"
    exit 0
}

# ── PATH A: Together.ai -> HuggingFace -> DeepInfra ──────────────────────

deploy_from_together() {
    local JOB_ID="$1"

    echo "=== Step 1: Download LoRA adapter from Together ==="
    mkdir -p "$ADAPTER_DIR"
    together fine-tuning download "$JOB_ID" --output "$ADAPTER_DIR"
    echo "Adapter downloaded to $ADAPTER_DIR"
    ls -la "$ADAPTER_DIR"

    echo ""
    echo "=== Step 2: Upload to HuggingFace ==="
    huggingface-cli upload "$HF_REPO" "$ADAPTER_DIR" --repo-type model
    echo "Uploaded to: https://huggingface.co/$HF_REPO"

    print_deepinfra_instructions
}

# ── PATH B: Local training output -> DeepInfra ───────────────────────────

deploy_from_local() {
    local STAGE="$1"
    local MODEL_DIR="/output/clonnect-iris-${STAGE}"

    if [ ! -d "$MODEL_DIR" ]; then
        echo "ERROR: $MODEL_DIR not found"
        echo "Run first: python scripts/run_finetune_qwen32b.py --stage $STAGE"
        exit 1
    fi

    echo "=== Step 1: Merge LoRA adapter ==="
    python3 -c "
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained('${MODEL_DIR}', load_in_4bit=False)
merged = '${MODEL_DIR}/merged'
model.save_pretrained_merged(merged, tokenizer, save_method='merged_16bit')
print(f'Merged to {merged}')
"

    echo ""
    echo "=== Step 2: Upload to HuggingFace ==="
    huggingface-cli upload "$HF_REPO" "${MODEL_DIR}/merged" --repo-type model
    echo "Uploaded to: https://huggingface.co/$HF_REPO"

    print_deepinfra_instructions
}

# ── DeepInfra deploy instructions (manual dashboard step) ────────────────

print_deepinfra_instructions() {
    echo ""
    echo "=============================================="
    echo " Step 3: Deploy on DeepInfra (MANUAL)"
    echo "=============================================="
    echo ""
    echo "  1. Go to: https://deepinfra.com/dash/deploy"
    echo "  2. Click 'Deploy a model'"
    echo "  3. Select 'Custom Model' -> 'LoRA Adapter'"
    echo "  4. Base model: Qwen/Qwen3-32B"
    echo "  5. Adapter: $HF_REPO"
    echo "  6. Click 'Deploy' -> wait for RUNNING"
    echo "  7. Copy endpoint URL"
    echo ""
    echo "  Pricing: ~\$0.27/M input, ~\$0.27/M output (serverless)"
    echo ""
    echo "=============================================="
    echo " Step 4: Configure Railway"
    echo "=============================================="
    echo ""
    echo "  railway variables set DEEPINFRA_MODEL=$HF_REPO"
    echo "  railway variables set LLM_PRIMARY_PROVIDER=deepinfra"
    echo ""
    echo "  # Rollback to Gemini:"
    echo "  railway variables set LLM_PRIMARY_PROVIDER=gemini"
    echo ""
    echo "=============================================="
    echo " Step 5: Verify"
    echo "=============================================="
    echo ""
    echo '  curl https://api.deepinfra.com/v1/openai/chat/completions \'
    echo '    -H "Authorization: Bearer $DEEPINFRA_API_KEY" \'
    echo '    -H "Content-Type: application/json" \'
    echo "    -d '{\"model\": \"$HF_REPO\", \"messages\": [{\"role\":\"user\",\"content\":\"Hola Iris!\"}]}'"
    echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────

case "${1:-help}" in
    together) deploy_from_together "${2:?missing job_id}" ;;
    local)    deploy_from_local "${2:-dpo}" ;;
    *)        show_help ;;
esac
