"""
Fine-tune Llama 4 Scout 17B-16E on RunPod using Unsloth QLoRA.

Requirements (install on RunPod):
    pip install -qU "unsloth[flash-attn]" "bitsandbytes==0.43.0"
    pip install datasets huggingface_hub wandb

Usage:
    python finetune_scout.py \
        --dataset scout_training_data.jsonl \
        --hf-repo "manelbertran/stefano-scout-lora" \
        --epochs 3 \
        --lr 2e-4

Hardware: 1x H100 80GB or A100 80GB (~71GB VRAM used)
Estimated time: ~15-30 min for 857 examples, 3 epochs
Disk: 300GB+ recommended for model + checkpoints
"""

import argparse
import json
import os

# ─── Configuration ────────────────────────────────────────────────────────────

BASE_MODEL = "meta-llama/Llama-4-Scout-17B-16E-Instruct"
MAX_SEQ_LENGTH = 2048
LORA_RANK = 16
LORA_ALPHA = 32
LORA_DROPOUT = 0.0
# All linear layers including MoE gate/up/down projections
TARGET_MODULES = [
    "q_proj", "k_proj", "v_proj", "o_proj",
    "gate_proj", "up_proj", "down_proj",
]
LOAD_IN_4BIT = True  # QLoRA NF4


def main():
    parser = argparse.ArgumentParser(description="Fine-tune Llama 4 Scout with Unsloth QLoRA")
    parser.add_argument("--dataset", required=True, help="Path to scout_training_data.jsonl")
    parser.add_argument("--hf-repo", required=True, help="HuggingFace repo to push adapter (e.g. your-org/stefano-scout-lora)")
    parser.add_argument("--epochs", type=int, default=3, help="Training epochs")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    parser.add_argument("--batch-size", type=int, default=1, help="Per-device batch size")
    parser.add_argument("--grad-accum", type=int, default=16, help="Gradient accumulation steps")
    parser.add_argument("--output-dir", default="./scout_ft_output", help="Local output directory")
    parser.add_argument("--wandb-project", default=None, help="W&B project name (optional)")
    parser.add_argument("--hf-token", default=None, help="HuggingFace token (or set HF_TOKEN env)")
    args = parser.parse_args()

    hf_token = args.hf_token or os.getenv("HF_TOKEN")
    if not hf_token:
        print("WARNING: No HF_TOKEN set. Won't be able to push to HuggingFace Hub.")

    # ─── Step 1: Load model with Unsloth ──────────────────────────────────────
    print(f"Loading {BASE_MODEL} with 4-bit quantization...")

    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,  # Auto-detect (bf16 on H100)
        load_in_4bit=LOAD_IN_4BIT,
    )

    # ─── Step 2: Add LoRA adapters ────────────────────────────────────────────
    print("Adding QLoRA adapters...")

    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_RANK,
        target_modules=TARGET_MODULES,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
        max_seq_length=MAX_SEQ_LENGTH,
    )

    # Print trainable parameters
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"Trainable: {trainable:,} / {total:,} ({100*trainable/total:.2f}%)")

    # ─── Step 3: Load and format dataset ──────────────────────────────────────
    print(f"Loading dataset from {args.dataset}...")

    from datasets import Dataset

    examples = []
    with open(args.dataset, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            convs = data.get("conversations", [])
            # Format as chat template
            text = tokenizer.apply_chat_template(convs, tokenize=False, add_generation_prompt=False)
            examples.append({"text": text})

    dataset = Dataset.from_list(examples)
    print(f"Dataset: {len(dataset)} examples")

    # ─── Step 4: Training ─────────────────────────────────────────────────────
    print("Starting training...")

    from unsloth import SFTTrainer
    from transformers import TrainingArguments

    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_steps=5,
        weight_decay=0.01,
        optim="adamw_8bit",
        fp16=False,
        bf16=True,
        logging_steps=10,
        save_strategy="epoch",
        seed=42,
        report_to="wandb" if args.wandb_project else "none",
        run_name=f"scout-ft-{args.epochs}ep" if args.wandb_project else None,
    )

    if args.wandb_project:
        import wandb
        wandb.init(project=args.wandb_project)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=MAX_SEQ_LENGTH,
        args=training_args,
    )

    trainer.train()

    # ─── Step 5: Save locally ─────────────────────────────────────────────────
    print(f"Saving adapter to {args.output_dir}...")
    model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)

    # ─── Step 6: Push to HuggingFace Hub ──────────────────────────────────────
    if hf_token and args.hf_repo:
        print(f"Pushing adapter to {args.hf_repo}...")
        model.push_to_hub(args.hf_repo, token=hf_token)
        tokenizer.push_to_hub(args.hf_repo, token=hf_token)
        print(f"Adapter pushed to https://huggingface.co/{args.hf_repo}")
    else:
        print("Skipping HuggingFace push (no token or repo)")

    # ─── Step 7: Training summary ─────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("TRAINING COMPLETE")
    print("=" * 60)
    print(f"Base model:      {BASE_MODEL}")
    print("Method:          QLoRA 4-bit (NF4)")
    print(f"LoRA rank:       {LORA_RANK}")
    print(f"LoRA alpha:      {LORA_ALPHA}")
    print(f"Target modules:  {TARGET_MODULES}")
    print(f"Epochs:          {args.epochs}")
    print(f"Learning rate:   {args.lr}")
    print(f"Batch (eff):     {args.batch_size * args.grad_accum}")
    print(f"Dataset:         {len(dataset)} examples")
    print(f"Trainable params:{trainable:,} ({100*trainable/total:.2f}%)")
    print(f"Output:          {args.output_dir}")
    if hf_token and args.hf_repo:
        print(f"HuggingFace:     https://huggingface.co/{args.hf_repo}")
    print("=" * 60)


if __name__ == "__main__":
    main()
