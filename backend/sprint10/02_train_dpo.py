"""
Sprint 10 DPO — cDPO + RPO over SFT adapter, all bug fixes applied
====================================================================

Bugs fixed vs Sprint 9:
  BUG-3:  All hyperparams (rpo_alpha=0.5, label_smoothing=0.1, cosine, weight_decay=0.01)
          Sprint 9 missing: rpo_alpha=0 → no NLL regularization
          Sprint 9 missing: label_smoothing=0 → brittle on noisy labels
          Sprint 9: linear LR → cosine (better for fine-tuning)
          Sprint 9: weight_decay=0 → cosine (prevents weight explosion)
  BUG-4:  dataset dpo_iris_v3_clean.jsonl (W1 output with deduplication + length filter)
  BUG-7:  Fresh LoRA adapter for DPO phase (not reusing SFT adapter weights directly)

Algorithm: cDPO (Conservative DPO) with RPO regularization
  - beta=0.05: low-margin → preserve style more than Sprint 9 (was 0.1)
  - rpo_alpha=0.5: adds SFT NLL term alongside DPO loss (Pang 2024 "crucial")
  - label_smoothing=0.1: cDPO noise robustness (assumes 10% label errors in human prefs)
  - loss_type="sigmoid": standard DPO (not ipo/hinge)

Dataset priority:
  1. data/dpo/trl/dpo_iris_v3_clean.jsonl  [W1 output — preferred]
  2. data/dpo/trl/dpo_iris_v2.jsonl         [fallback — 2499 pairs]

Hardware requirements (max_seq_len=8192):
  4090 24GB:  NOT viable
  A100 80GB:  viable — ~8-12h DPO
  H200 80GB:  viable — ~6-9h DPO

Usage:
  HF_TOKEN=<token> python sprint10/02_train_dpo.py [--dataset <path>] [--dry-run]
"""

import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sprint10.dpo")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_MODEL = "Qwen/Qwen3-32B"
SFT_ADAPTER = "manelbertranluque/clonnect-iris-sft-sprint10-qwen3-32b"
OUTPUT_DIR = "output/sprint10/dpo"
HF_REPO = "manelbertranluque/clonnect-iris-dpo-sprint10-qwen3-32b"

MAX_SEQ_LEN = 8192   # BUG-14 fix: match SFT context window (Doc D v1 = ~8.5K tokens)
MAX_PROMPT_LEN = 4096  # Half of MAX_SEQ_LEN — leaves room for chosen/rejected

# HF dataset (private, pre-uploaded via W1 pipeline)
HF_DATASET_DPO = "manelbertranluque/clonnect-iris-dpo-v3-clean"
# Local fallback paths
DATASET_LOCAL = "data/dpo/trl/dpo_iris_v3_clean.jsonl"
DATASET_FALLBACK = "data/dpo/trl/dpo_iris_v2.jsonl"

# DPO LoRA (smaller rank for refinement phase)
LORA_RANK = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.05
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj"]   # Attention only for DPO

# DPO algorithm config (BUG-3 fix — ALL hyperparams)
DPO_ALGO = dict(
    beta=0.05,              # cDPO low-margin — preserve style vs Sprint 9 (was 0.1)
    rpo_alpha=0.5,          # NLL regularization term (Pang 2024) — was 0 in Sprint 9
    label_smoothing=0.1,    # cDPO noise robustness — was 0 in Sprint 9
    loss_type="sigmoid",    # Standard DPO
)

TRAINING = dict(
    num_train_epochs=2,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,    # effective batch = 16
    learning_rate=5e-7,               # Standard DPO LR (10x lower than SFT)
    lr_scheduler_type="cosine",       # BUG-3 fix: was linear
    warmup_ratio=0.1,
    weight_decay=0.01,                # BUG-3 fix: was 0
    max_grad_norm=1.0,                # BUG-3 fix: was inf
    logging_steps=10,
    save_strategy="epoch",
    save_total_limit=2,
    bf16=True,
    optim="adamw_8bit",
    seed=3407,
    report_to="none",
)


# ---------------------------------------------------------------------------
# Dataset resolution
# ---------------------------------------------------------------------------

def load_dataset_smart(override: str | None):
    """Load DPO dataset from HF (preferred) or local fallback."""
    from datasets import load_dataset as hf_load_dataset

    if override:
        if Path(override).exists():
            return hf_load_dataset("json", data_files=override, split="train")
        else:
            hf_token = os.environ.get("HF_TOKEN")
            return hf_load_dataset(override, split="train", token=hf_token)

    hf_token = os.environ.get("HF_TOKEN")

    if hf_token:
        try:
            logger.info("Loading DPO dataset from HF: %s", HF_DATASET_DPO)
            ds = hf_load_dataset(HF_DATASET_DPO, split="train", token=hf_token)
            logger.info("HF dataset loaded: %d pairs", len(ds))
            return ds
        except Exception as e:
            logger.warning("HF dataset load failed (%s) — falling back to local", e)

    for local_path, label in [
        (DATASET_LOCAL, "W1 clean"),
        (DATASET_FALLBACK, "v2 fallback"),
    ]:
        if Path(local_path).exists():
            logger.info("Dataset: %s (%s)", local_path, label)
            return hf_load_dataset("json", data_files=local_path, split="train")

    logger.error("No DPO dataset found. Set HF_TOKEN or run W1 locally.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(dataset_override: str | None, dry_run: bool = False) -> None:
    import torch

    logger.info("Loading base model: %s", BASE_MODEL)
    logger.info("Loading SFT adapter: %s", SFT_ADAPTER)

    try:
        from unsloth import FastLanguageModel
    except ImportError:
        logger.error("unsloth not installed. Run: pip install unsloth[cu124-torch240]")
        sys.exit(1)

    from peft import PeftModel
    from trl import DPOTrainer, DPOConfig

    # Load base model
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LEN,
        dtype=torch.bfloat16,
        load_in_4bit=False,
    )

    # Load SFT adapter on top
    logger.info("Loading SFT LoRA adapter from: %s", SFT_ADAPTER)
    model = PeftModel.from_pretrained(model, SFT_ADAPTER, is_trainable=True)

    # BUG-7 fix: add fresh DPO LoRA on top of SFT adapter
    # This gives the DPO phase its own trainable params separate from SFT weights
    logger.info("BUG-7 fix: adding fresh DPO LoRA adapter on top of SFT weights")
    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_RANK,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=TARGET_MODULES,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=3407,
    )

    # Load dataset (BUG-4 fix: clean v3 with deduplication + length filter)
    dataset = load_dataset_smart(dataset_override)
    logger.info("Dataset size: %d pairs", len(dataset))

    # Validate dataset format
    required_cols = {"prompt", "chosen", "rejected"}
    if not required_cols.issubset(set(dataset.column_names)):
        logger.error(
            "Dataset missing columns: %s (have: %s)",
            required_cols - set(dataset.column_names),
            dataset.column_names,
        )
        sys.exit(1)

    if dry_run:
        logger.info("DRY RUN — showing first pair:")
        example = dataset[0]
        logger.info("  prompt:   %s", str(example["prompt"])[:200])
        logger.info("  chosen:   %s", str(example["chosen"])[:200])
        logger.info("  rejected: %s", str(example["rejected"])[:200])
        logger.info("DRY RUN complete. Exiting.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # DPO config with ALL hyperparams (BUG-3 fix)
    dpo_config = DPOConfig(
        output_dir=OUTPUT_DIR,
        max_length=MAX_SEQ_LEN,
        max_prompt_length=MAX_PROMPT_LEN,
        **DPO_ALGO,
        **TRAINING,
    )

    trainer = DPOTrainer(
        model=model,
        ref_model=None,         # PEFT with is_trainable handles reference internally
        args=dpo_config,
        train_dataset=dataset,
        tokenizer=tokenizer,
    )

    logger.info("Starting DPO training...")
    logger.info(
        "Config: beta=%.2f rpo_alpha=%.1f label_smoothing=%.1f",
        DPO_ALGO["beta"], DPO_ALGO["rpo_alpha"], DPO_ALGO["label_smoothing"],
    )
    trainer_stats = trainer.train()
    logger.info("Training complete. Stats: %s", trainer_stats)

    # Save locally
    final_dir = f"{OUTPUT_DIR}/final"
    model.save_pretrained(final_dir)
    tokenizer.save_pretrained(final_dir)
    logger.info("Saved to: %s", final_dir)

    # Push to HF
    hf_token = os.environ.get("HF_TOKEN")
    if hf_token:
        logger.info("Pushing to HF: %s", HF_REPO)
        model.push_to_hub(HF_REPO, token=hf_token)
        tokenizer.push_to_hub(HF_REPO, token=hf_token)
        logger.info("Pushed to HF: %s", HF_REPO)
    else:
        logger.warning("HF_TOKEN not set — skipping push to Hub")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Sprint 10 DPO Training")
    parser.add_argument("--dataset", type=str, default=None,
                        help="Override dataset path (default: auto-resolve W1 → fallback)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate dataset and show first pair, do not train")
    args = parser.parse_args()

    train(args.dataset, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
