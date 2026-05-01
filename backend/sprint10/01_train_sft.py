"""
Sprint 10 SFT — Qwen3-32B from scratch, all bug fixes applied
==============================================================

Bugs fixed vs Sprint 9:
  BUG-2:  train_on_responses_only ACTIVATED (was missing → loss on prompt tokens)
  BUG-7:  get_peft_model fresh — no CPT adapter reuse
  BUG-12: dataset multi-turn 60/40 (W2 output expected)
  BUG-13: filtered records (max 200 chars response)
  BUG-14: 4 system prompt variants
  BUG-15: SKIP CPT — start from Qwen3-32B raw base

DECISION BUG-15 rationale:
  139K tokens sub-minimum (recipes need 10M+), ratio 13000:1 → overfit guaranteed.
  Creator-clone recipes (Edward Donner, WhatsApp-Llama) never use CPT.

Pipeline: Qwen3-32B base → SFT (this) → DPO (02_train_dpo.py)

Dataset priority:
  1. data/dpo/trl/sft_v4_multiturn.jsonl  [W2 output — preferred]
  2. data/dpo/trl/sft_v3_clean.jsonl       [fallback if W2 not ready]

Hardware requirements (max_seq_len=8192):
  4090 24GB:  NOT viable (KV-cache alone exceeds VRAM at 8192)
  A100 80GB:  viable — ~36-48h SFT, ~$120-160 Vast.ai
  H200 80GB:  viable — ~24-36h SFT, ~$120-160 Vast.ai (faster memory bandwidth)
  Note: doubled context vs 4096 adds ~50% compute and ~8GB KV-cache

Usage:
  HF_TOKEN=<token> python sprint10/01_train_sft.py [--dataset <path>] [--dry-run]
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
logger = logging.getLogger("sprint10.sft")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_MODEL = "Qwen/Qwen3-32B"
OUTPUT_DIR = "output/sprint10/sft"
MAX_SEQ_LEN = 8192   # BUG-14 fix needs Doc D v1 íntegro 30K chars = ~8.5K tokens
HF_REPO = "manelbertranluque/clonnect-iris-sft-sprint10-qwen3-32b"

# HF dataset (private, pre-uploaded via sprint10/sanitize_sft_v4.py)
HF_DATASET_SFT = "manelbertranluque/clonnect-iris-sft-v4-multiturn"
# Local fallback paths (for development only — not available on Vast.ai)
DATASET_LOCAL_FILTERED = "data/dpo/trl/sft_v4_multiturn_filtered.jsonl"
DATASET_LOCAL_RAW = "data/dpo/trl/sft_v4_multiturn.jsonl"
DATASET_FALLBACK = "data/dpo/trl/sft_v3_clean.jsonl"

LORA_RANK = 32
LORA_ALPHA = 64        # 2x rank (Unsloth recommended)
LORA_DROPOUT = 0.05
TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]

TRAINING = dict(
    num_train_epochs=2,                # Not 3 — 32B overfits fast
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,    # effective batch = 16
    learning_rate=5e-6,               # conservative for stacked training
    lr_scheduler_type="cosine",       # was linear in Sprint 9
    warmup_ratio=0.05,
    weight_decay=0.01,                # was 0 in Sprint 9
    max_grad_norm=1.0,
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
    """
    Load SFT dataset. Priority:
    1. --dataset override (path or HF repo)
    2. HF private repo (Vast.ai standard path)
    3. Local filtered JSONL
    4. Local raw JSONL
    5. Local fallback v3
    """
    from datasets import load_dataset as hf_load_dataset

    if override:
        # Can be a local path or HF repo id
        if Path(override).exists():
            logger.info("Dataset: %s (override local)", override)
            return hf_load_dataset("json", data_files=override, split="train")
        else:
            logger.info("Dataset: %s (override HF)", override)
            hf_token = os.environ.get("HF_TOKEN")
            return hf_load_dataset(override, split="train", token=hf_token)

    hf_token = os.environ.get("HF_TOKEN")

    # Try HF first (preferred on Vast.ai — datasets not in git)
    if hf_token:
        try:
            logger.info("Loading dataset from HF: %s", HF_DATASET_SFT)
            ds = hf_load_dataset(HF_DATASET_SFT, split="train", token=hf_token)
            logger.info("HF dataset loaded: %d examples", len(ds))
            return ds
        except Exception as e:
            logger.warning("HF dataset load failed (%s) — falling back to local", e)

    # Local fallbacks
    for local_path, label in [
        (DATASET_LOCAL_FILTERED, "W2 filtered (token-safe)"),
        (DATASET_LOCAL_RAW, "W2 raw"),
        (DATASET_FALLBACK, "v3 fallback"),
    ]:
        if Path(local_path).exists():
            logger.info("Dataset: %s (%s)", local_path, label)
            return hf_load_dataset("json", data_files=local_path, split="train")

    logger.error("No dataset found. Set HF_TOKEN or run W2 locally.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(dataset_override: str | None, dry_run: bool = False) -> None:
    # --- Dry-run: validate config + dataset access without GPU/unsloth ---
    if dry_run:
        import json
        logger.info("=== DRY RUN MODE (no GPU required) ===")
        logger.info("Config: BASE_MODEL=%s  MAX_SEQ_LEN=%d  LORA_RANK=%d  HF_REPO=%s",
                    BASE_MODEL, MAX_SEQ_LEN, LORA_RANK, HF_REPO)
        logger.info("Hyperparams: %s", TRAINING)

        # Validate dataset file accessible (local path check, no datasets lib needed)
        found = None
        for p in [dataset_override, DATASET_LOCAL_FILTERED, DATASET_LOCAL_RAW, DATASET_FALLBACK]:
            if p and Path(p).exists():
                found = p
                break
        if found:
            with open(found) as f:
                records = [json.loads(l) for l in f if l.strip()]
            sample = records[0]
            mt = sum(1 for r in records if r.get("turn_type") == "multi")
            logger.info("Dataset: %s — %d records, %.1f%% multi-turn", found, len(records), mt/len(records)*100)
            logger.info("Sample keys: %s", list(sample.keys()))
            if "messages" in sample:
                logger.info("Sample messages[0]: %s", str(sample["messages"][0])[:200])
        elif os.environ.get("HF_TOKEN"):
            logger.info("Local dataset not found — HF token present, will download on Vast.ai")
            logger.info("HF_DATASET_SFT: %s", HF_DATASET_SFT)
        else:
            logger.error("No local dataset and no HF_TOKEN — training will fail on Vast.ai")
            sys.exit(1)

        logger.info("DRY RUN complete. All checks passed.")
        return

    # --- Full training path (requires GPU + unsloth) ---
    import torch

    logger.info("Loading base model: %s", BASE_MODEL)
    logger.info("BUG-7 fix: fresh get_peft_model (no CPT adapter reuse)")
    logger.info("BUG-15 fix: starting from raw Qwen3-32B (no CPT phase)")

    try:
        from unsloth import FastLanguageModel
        from unsloth.chat_templates import train_on_responses_only
    except ImportError:
        logger.error("unsloth not installed. Run: pip install unsloth[cu124-torch240]")
        sys.exit(1)

    from trl import SFTTrainer, SFTConfig

    # BUG-7 fix: load base model fresh, no adapter carryover
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LEN,
        dtype=torch.bfloat16,
        load_in_4bit=False,     # bf16 full precision for max quality
    )

    # BUG-7 fix: apply LoRA fresh
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

    # Load dataset (HF preferred, local fallback)
    dataset = load_dataset_smart(dataset_override)
    logger.info("Dataset size: %d examples", len(dataset))

    # Format with ChatML template (Qwen3 native)
    def format_chatml(example):
        return {
            "text": tokenizer.apply_chat_template(
                example["messages"],
                tokenize=False,
                add_generation_prompt=False,
            )
        }

    dataset = dataset.map(format_chatml, batched=False, desc="Applying chat template")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    training_args = SFTConfig(
        output_dir=OUTPUT_DIR,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LEN,
        **TRAINING,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=training_args,
    )

    # BUG-2 CRITICAL FIX: mask system + user tokens, only compute loss on assistant
    # Without this: model was learning to predict system prompt and user messages too
    # This explains style drift in Sprint 8/9 — base model pattern dominated
    logger.info("BUG-2 fix: applying train_on_responses_only")
    trainer = train_on_responses_only(
        trainer,
        instruction_part="<|im_start|>user\n",
        response_part="<|im_start|>assistant\n",
    )

    logger.info("Starting SFT training...")
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
    parser = argparse.ArgumentParser(description="Sprint 10 SFT Training")
    parser.add_argument("--dataset", type=str, default=None,
                        help="Override dataset path (default: auto-resolve W2 → W1 fallback)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate dataset and show first example, do not train")
    args = parser.parse_args()

    train(args.dataset, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
