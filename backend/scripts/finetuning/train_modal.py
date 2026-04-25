"""
Modal script — SFT Gemma4-31B Dense sobre Iris (IG + WhatsApp)
"""
import modal

app = modal.App("clonnect-iris-sft")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("git")
    .pip_install(
        "torch==2.7.0",
        "torchvision==0.22.0",
        "xformers==0.0.30",
        extra_index_url="https://download.pytorch.org/whl/cu126",
    )
    .pip_install(
        "unsloth==2026.4.8",
        "unsloth_zoo==2026.4.9",
        "bitsandbytes==0.49.2",
        "accelerate==1.13.0",
        "peft==0.19.1",
        "transformers==5.5.0",
        "trl==0.24.0",
        "datasets==4.3.0",
        "huggingface_hub==1.12.0",
        "hf_transfer",
        "sentencepiece",
        "protobuf",
    )
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
    .add_local_file(
        "data/dpo/trl/sft_combined_audited.jsonl",
        remote_path="/data/sft_combined_audited.jsonl",
    )
)

volume = modal.Volume.from_name("clonnect-models", create_if_missing=True)


@app.function(
    image=image,
    gpu="A100-40GB",
    volumes={"/models": volume},
    timeout=60 * 60 * 6,
)
def train():
    import torch
    from unsloth import FastModel
    from unsloth.chat_templates import get_chat_template, standardize_data_formats, train_on_responses_only
    from datasets import load_dataset
    from trl import SFTTrainer, SFTConfig

    MODEL_NAME = "unsloth/gemma-4-31B-it"
    MAX_SEQ_LENGTH = 2048

    print(f"🚀 Loading {MODEL_NAME}...")
    model, tokenizer = FastModel.from_pretrained(
        model_name=MODEL_NAME,
        max_seq_length=MAX_SEQ_LENGTH,
        load_in_4bit=True,
        load_in_16bit=False,
        full_finetuning=False,
        dtype=None,
    )

    model = FastModel.get_peft_model(
        model,
        finetune_vision_layers=False,
        finetune_language_layers=True,
        finetune_attention_modules=True,
        finetune_mlp_modules=True,
        r=16,
        lora_alpha=32,
        lora_dropout=0.05,
        bias="none",
        random_state=3407,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )

    tokenizer = get_chat_template(tokenizer, chat_template="gemma-4-thinking")

    print("📂 Loading dataset...")
    dataset = load_dataset("json", data_files="/data/sft_combined_audited.jsonl", split="train")
    print(f"Dataset: {len(dataset)} examples")

    dataset = standardize_data_formats(dataset)

    def formatting_prompts_func(examples):
        convos = examples["conversations"] if "conversations" in examples else examples["messages"]
        texts = [
            tokenizer.apply_chat_template(convo, tokenize=False, add_generation_prompt=False, enable_thinking=False).removeprefix("<bos>")
            for convo in convos
        ]
        return {"text": texts}

    dataset = dataset.map(formatting_prompts_func, batched=True)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        eval_dataset=None,
        args=SFTConfig(
            dataset_text_field="text",
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            warmup_ratio=0.05,
            num_train_epochs=1,
            learning_rate=2e-4,
            lr_scheduler_type="cosine",
            optim="adamw_8bit",
            weight_decay=0.01,
            max_grad_norm=0.3,
            logging_steps=10,
            save_strategy="steps",
            save_steps=200,
            save_total_limit=3,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            seed=3407,
            output_dir="/models/gemma31b-iris-sft-checkpoints",
            report_to="none",
        ),
    )

    trainer = train_on_responses_only(
        trainer,
        instruction_part="<|turn>user\n",
        response_part="<|turn>model\n<|channel>thought\n<channel|>",
    )

    print("🔥 Starting SFT training...")
    stats = trainer.train()
    print(f"\n✅ Done. Runtime: {stats.metrics['train_runtime']:.1f}s, Loss: {stats.metrics['train_loss']:.4f}")

    print("💾 Saving LoRA adapter...")
    model.save_pretrained("/models/gemma31b-iris-sft-lora")
    tokenizer.save_pretrained("/models/gemma31b-iris-sft-lora")

    print("💾 Merging + saving 16bit...")
    model.save_pretrained_merged(
        "/models/gemma31b-iris-sft-merged",
        tokenizer,
        save_method="merged_16bit",
    )

    volume.commit()
    print("✅ Saved to Modal Volume 'clonnect-models'")


@app.local_entrypoint()
def main():
    train.remote()
