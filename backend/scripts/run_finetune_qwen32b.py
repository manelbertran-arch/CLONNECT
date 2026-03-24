"""
Fine-tune Qwen3-32B with QLoRA using TRL (CPT -> SFT -> DPO pipeline).

Usage:
    pip install unsloth trl transformers datasets peft bitsandbytes

    python scripts/run_finetune_qwen32b.py --stage cpt
    python scripts/run_finetune_qwen32b.py --stage sft
    python scripts/run_finetune_qwen32b.py --stage dpo
    python scripts/run_finetune_qwen32b.py --stage all
"""

import argparse
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "dpo")
OUTPUT_BASE = "/output"

MODEL_ID = "Qwen/Qwen3-32B"

# QLoRA config shared across stages
QLORA_CONFIG = {
    "r": 32,
    "lora_alpha": 64,
    "lora_dropout": 0.05,
    "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    "bias": "none",
    "task_type": "CAUSAL_LM",
}


def _get_model_and_tokenizer(stage: str, resume_from: str = None):
    """Load model with QLoRA quantization via Unsloth."""
    from unsloth import FastLanguageModel

    base = resume_from or MODEL_ID
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base,
        max_seq_length=2048,
        dtype=None,  # auto-detect
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=QLORA_CONFIG["r"],
        lora_alpha=QLORA_CONFIG["lora_alpha"],
        lora_dropout=QLORA_CONFIG["lora_dropout"],
        target_modules=QLORA_CONFIG["target_modules"],
        bias=QLORA_CONFIG["bias"],
    )

    return model, tokenizer


def _load_jsonl(path: str):
    """Load a JSONL file as a HuggingFace Dataset."""
    from datasets import load_dataset
    return load_dataset("json", data_files=path, split="train")


# ── CPT Stage ────────────────────────────────────────────────────────

def run_cpt():
    """Continued Pre-Training: causal LM on Iris's raw messages."""
    from trl import SFTTrainer, SFTConfig

    model, tokenizer = _get_model_and_tokenizer("cpt")
    dataset = _load_jsonl(os.path.join(DATA_DIR, "cpt_iris.jsonl"))
    output_dir = os.path.join(OUTPUT_BASE, "clonnect-iris-cpt")

    training_args = SFTConfig(
        output_dir=output_dir,
        num_train_epochs=1,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=8,
        learning_rate=2e-5,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        bf16=True,
        logging_steps=10,
        save_strategy="epoch",
        dataset_text_field="text",
        max_seq_length=512,
        packing=True,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=training_args,
    )

    trainer.train()
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"[CPT] Model saved to {output_dir}")
    return output_dir


# ── SFT Stage ────────────────────────────────────────────────────────

def run_sft(resume_from: str = None):
    """Supervised Fine-Tuning: chat format with system/user/assistant turns."""
    from trl import SFTTrainer, SFTConfig

    base = resume_from or MODEL_ID
    model, tokenizer = _get_model_and_tokenizer("sft", resume_from=base)
    dataset = _load_jsonl(os.path.join(DATA_DIR, "sft_iris.jsonl"))
    output_dir = os.path.join(OUTPUT_BASE, "clonnect-iris-sft")

    def format_chat(example):
        return {"text": tokenizer.apply_chat_template(
            example["messages"], tokenize=False, add_generation_prompt=False
        )}

    dataset = dataset.map(format_chat)

    training_args = SFTConfig(
        output_dir=output_dir,
        num_train_epochs=3,
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        learning_rate=2e-5,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        bf16=True,
        logging_steps=5,
        save_strategy="epoch",
        dataset_text_field="text",
        max_seq_length=1024,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=training_args,
    )

    trainer.train()
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"[SFT] Model saved to {output_dir}")
    return output_dir


# ── DPO Stage ────────────────────────────────────────────────────────

def run_dpo(resume_from: str = None):
    """Direct Preference Optimization: align to Iris's real responses."""
    from trl import DPOTrainer, DPOConfig

    base = resume_from or MODEL_ID
    model, tokenizer = _get_model_and_tokenizer("dpo", resume_from=base)
    dataset = _load_jsonl(os.path.join(DATA_DIR, "dpo_iris.jsonl"))
    output_dir = os.path.join(OUTPUT_BASE, "clonnect-iris-dpo")

    training_args = DPOConfig(
        output_dir=output_dir,
        num_train_epochs=1,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        learning_rate=5e-6,
        lr_scheduler_type="cosine",
        warmup_ratio=0.1,
        beta=0.1,
        bf16=True,
        logging_steps=10,
        save_strategy="epoch",
        max_length=1024,
        max_prompt_length=512,
    )

    trainer = DPOTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=training_args,
    )

    trainer.train()
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"[DPO] Model saved to {output_dir}")
    return output_dir


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fine-tune Qwen3-32B for Clonnect Iris clone")
    parser.add_argument("--stage", choices=["cpt", "sft", "dpo", "all"], required=True)
    args = parser.parse_args()

    if args.stage == "all":
        cpt_dir = run_cpt()
        sft_dir = run_sft(resume_from=cpt_dir)
        run_dpo(resume_from=sft_dir)
    elif args.stage == "cpt":
        run_cpt()
    elif args.stage == "sft":
        run_sft()
    elif args.stage == "dpo":
        run_dpo()


if __name__ == "__main__":
    main()
