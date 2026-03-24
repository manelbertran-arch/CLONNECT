#!/usr/bin/env bash
# Deploy fine-tuned Qwen3-32B to DeepInfra
#
# Prerequisites:
#   pip install deepinfra
#   deepinfra auth login
#
# Usage:
#   bash scripts/deploy_to_deepinfra.sh [stage]
#   bash scripts/deploy_to_deepinfra.sh dpo       # deploy DPO checkpoint
#   bash scripts/deploy_to_deepinfra.sh sft       # deploy SFT checkpoint

set -euo pipefail

STAGE="${1:-dpo}"
MODEL_DIR="/output/clonnect-iris-${STAGE}"
MODEL_NAME="clonnect-iris-${STAGE}"

if [ ! -d "$MODEL_DIR" ]; then
    echo "ERROR: Model directory not found: $MODEL_DIR"
    echo "Run the fine-tuning first: python scripts/run_finetune_qwen32b.py --stage $STAGE"
    exit 1
fi

echo "=== Step 1: Merge LoRA adapter into base model ==="
python3 -c "
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained('${MODEL_DIR}', load_in_4bit=False)
merged_dir = '${MODEL_DIR}/merged'
model.save_pretrained_merged(merged_dir, tokenizer, save_method='merged_16bit')
print(f'Merged model saved to {merged_dir}')
"

MERGED_DIR="${MODEL_DIR}/merged"

echo ""
echo "=== Step 2: Upload to DeepInfra ==="
echo ""
echo "Option A — CLI upload:"
echo "  deepinfra model create ${MODEL_NAME}"
echo "  deepinfra model upload ${MODEL_NAME} ${MERGED_DIR}"
echo "  deepinfra model deploy ${MODEL_NAME}"
echo ""
echo "Option B — HuggingFace Hub + DeepInfra import:"
echo "  1. Push to HF:  huggingface-cli upload clonnect/${MODEL_NAME} ${MERGED_DIR}"
echo "  2. In DeepInfra dashboard: Import from HuggingFace -> clonnect/${MODEL_NAME}"
echo ""
echo "Option C — Upload GGUF (quantized, cheaper inference):"
echo "  python3 -c \""
echo "    from unsloth import FastLanguageModel"
echo "    model, tokenizer = FastLanguageModel.from_pretrained('${MODEL_DIR}', load_in_4bit=False)"
echo "    model.save_pretrained_gguf('${MODEL_DIR}/gguf', tokenizer, quantization_method='q4_k_m')"
echo "  \""
echo "  deepinfra model create ${MODEL_NAME}-gguf"
echo "  deepinfra model upload ${MODEL_NAME}-gguf ${MODEL_DIR}/gguf"
echo ""
echo "=== Step 3: Test endpoint ==="
echo ""
echo "  curl https://api.deepinfra.com/v1/openai/chat/completions \\"
echo "    -H 'Authorization: Bearer \$DEEPINFRA_API_KEY' \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{"
echo "      \"model\": \"clonnect/${MODEL_NAME}\","
echo "      \"messages\": [{\"role\":\"user\",\"content\":\"Hola Iris, que tal?\"}]"
echo "    }'"
echo ""
echo "=== Done ==="
