#!/bin/bash
# Sprint 10 — Setup Vast.ai H200 80GB
# Run: bash setup_sprint10_h200.sh
# Requires env: HF_TOKEN, DATABASE_URL (Railway Postgres)
#
# VRAM requirements (max_seq_len=8192, Opción A):
#   Qwen3-32B bf16 weights:       ~64 GB
#   KV-cache at seq_len=8192:     ~8-12 GB (estimated)
#   Optimizer states (adamw_8bit): ~4 GB
#   Activations + gradient ckpt:  ~4 GB
#   TOTAL:                        ~80-88 GB  ← H200 80GB at limit
#
#   GPU options:
#     H200 80GB   → OK (per_device_batch_size=2, grad_accum=8)
#     A100 80GB   → OK (same, slightly slower than H200)
#     H100 80GB   → OK
#     4090 (24GB) → NOT viable at 8192 (would need 4-bit + seq_len=2048)
#
# Time estimates (H200 80GB, 2 epochs, 10K records, max_seq_len=8192):
#   SFT phase:  ~36-48h  (vs ~24h at seq_len=4096)
#   DPO phase:  ~8-12h   (vs ~4-6h at seq_len=4096)
#   TOTAL:      ~44-60h
#
# Note: doubled context window doubles VRAM for KV-cache and ~1.5x compute.

set -euo pipefail

echo "============================================================"
echo "  Sprint 10 — Vast.ai H200 Setup (max_seq_len=8192)"
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
    echo "ERROR: GPU has ${gpu_mem}MB VRAM — H200/A100/H100 80GB required"
    echo "  max_seq_len=8192 with Qwen3-32B needs ~80GB VRAM"
    echo "  See VRAM breakdown at top of this script"
    exit 1
fi
echo "GPU VRAM: ${gpu_mem}MB — OK"

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

# DB access for dataset regeneration
pip install psycopg2-binary sqlalchemy --quiet

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
    git pull origin sprint10/w2-sft-multiturn
else
    echo "Cloning repo"
    cd "$WORKSPACE"
    git clone https://github.com/manelbertran-arch/CLONNECT.git Clonnect
    cd Clonnect
    git checkout sprint10/w2-sft-multiturn
fi

BACKEND="$WORKSPACE/Clonnect/backend"
cd "$BACKEND"

# ---------------------------------------------------------------------------
# Railway DATABASE_URL connectivity check
# ---------------------------------------------------------------------------

echo ""
echo "=== Railway DB Connectivity Check ==="
if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERROR: DATABASE_URL not set"
    echo "Export Railway Postgres URL: export DATABASE_URL=postgresql://..."
    echo "Get from: railway variables | grep DATABASE_URL"
    exit 1
fi

echo "Testing connection to Railway Postgres..."
python3 -c "
import os
from sqlalchemy import create_engine, text
eng = create_engine(os.environ['DATABASE_URL'], connect_args={'connect_timeout': 10})
try:
    with eng.connect() as c:
        result = c.execute(text('SELECT COUNT(*) FROM messages LIMIT 1')).scalar()
    print(f'  Connection OK — messages table accessible')
except Exception as e:
    print(f'  FAIL: {e}')
    print('  Railway may block Vast.ai IPs. Try: railway run --environment production')
    print('  Workaround: generate dataset locally then scp to Vast.ai')
    exit(1)
"
DB_EXIT=$?
if [ "$DB_EXIT" -ne 0 ]; then
    echo "DB connection failed — see workaround above"
    exit 1
fi

# ---------------------------------------------------------------------------
# Dataset generation (requires Railway DB access)
# ---------------------------------------------------------------------------

echo ""
echo "=== Dataset Generation ==="

SFT_DATASET="$BACKEND/data/dpo/trl/sft_v4_multiturn.jsonl"
DPO_DATASET="$BACKEND/data/dpo/trl/dpo_iris_v3_clean.jsonl"

mkdir -p "$BACKEND/data/dpo/trl"

# SFT W2 dataset
if [ -f "$SFT_DATASET" ]; then
    lines=$(wc -l < "$SFT_DATASET")
    echo "[SKIP] SFT W2 dataset already exists: $lines records"
else
    echo "Regenerating SFT W2 dataset (max_seq_len=8192 filtered)..."
    python3 scripts/finetuning/build_sft_v4.py 2>&1
    if [ $? -ne 0 ]; then
        echo "ERROR: SFT dataset generation failed"
        exit 1
    fi
    lines=$(wc -l < "$SFT_DATASET")
    echo "[OK] SFT W2 dataset generated: $lines records"
fi

# DPO W1 dataset
if [ -f "$DPO_DATASET" ]; then
    lines=$(wc -l < "$DPO_DATASET")
    echo "[SKIP] DPO W1 dataset already exists: $lines records"
elif [ -f "data/dpo/trl/dpo_iris_v2.jsonl" ]; then
    echo "[FALLBACK] Using dpo_iris_v2.jsonl (run W1 for best results)"
else
    echo "ERROR: No DPO dataset found. Run W1 (scripts/finetuning/build_dpo_v3_clean.py) first."
    exit 1
fi

# ---------------------------------------------------------------------------
# Final dataset check
# ---------------------------------------------------------------------------

echo ""
echo "=== Final Dataset Check ==="
python3 -c "
import json

sft_path = 'data/dpo/trl/sft_v4_multiturn.jsonl'
dpo_paths = ['data/dpo/trl/dpo_iris_v3_clean.jsonl', 'data/dpo/trl/dpo_iris_v2.jsonl']

with open(sft_path) as f:
    records = [json.loads(l) for l in f]
mt = sum(1 for r in records if r.get('turn_type') == 'multi')
print(f'SFT: {len(records)} records, {mt/len(records)*100:.1f}% multi-turn')

# Check token budget
over = sum(
    1 for r in records
    if sum(len(m[\"content\"]) for m in r[\"messages\"]) > 8192 * 3.5 * 0.95
)
print(f'SFT: {over} records estimated >8192 tokens (should be 0)')

for p in dpo_paths:
    import os
    if os.path.exists(p):
        with open(p) as f:
            n = sum(1 for _ in f)
        print(f'DPO: {n} records ({p})')
        break
"

# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

LOG_DIR="$WORKSPACE/logs"
mkdir -p "$LOG_DIR"
mkdir -p output/sprint10/sft output/sprint10/dpo

echo ""
echo "============================================================"
echo "  PHASE 1: SFT Training (max_seq_len=8192)"
echo "  Estimated: 36-48h on H200 80GB"
echo "  Start: $(date)"
echo "============================================================"

python3 sprint10/01_train_sft.py 2>&1 | tee "$LOG_DIR/sft_$(date +%Y%m%d_%H%M).log"

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
echo "  PHASE 2: DPO Training (max_seq_len=8192, max_prompt=4096)"
echo "  Estimated: 8-12h on H200 80GB"
echo "  Start: $(date)"
echo "============================================================"

python3 sprint10/02_train_dpo.py 2>&1 | tee "$LOG_DIR/dpo_$(date +%Y%m%d_%H%M).log"

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
