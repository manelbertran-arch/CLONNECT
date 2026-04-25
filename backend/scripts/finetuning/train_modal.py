"""
Modal script — SFT Gemma4-31B Dense sobre Iris (IG + WhatsApp)

Modes:
  modal run scripts/finetuning/train_modal.py              # full training
  modal run scripts/finetuning/train_modal.py --smoke      # 100-step smoke test
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
        "data/dpo/trl/sprint7/sft_sprint7.jsonl",
        remote_path="/data/sft_sprint7.jsonl",
    )
)

volume = modal.Volume.from_name("clonnect-models", create_if_missing=True)


# ─── Loss alert thresholds (S5 + S6 research) ─────────────────────────────────
LOSS_ALERTS = {
    #  step: (ok_low, ok_high, alert_threshold, abort_threshold)
    1:    (1.0,  3.0,  None, 12.0),
    10:   (1.5,  2.5,  4.0,  None),
    50:   (1.0,  2.0,  5.0,  None),
    100:  (0.8,  1.8,  None, 8.0),
}


def make_loss_callback():
    from transformers import TrainerCallback

    class LossAlertCallback(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kwargs):
            if not logs or "loss" not in logs:
                return
            step = state.global_step
            loss = float(logs["loss"])
            if step in LOSS_ALERTS:
                ok_low, ok_high, alert, abort = LOSS_ALERTS[step]
                status = "OK" if ok_low <= loss <= ok_high else "WARN"
                if abort is not None and loss > abort:
                    print(f"🚨 ABORT triggered at step {step}: loss={loss:.4f} > abort={abort}")
                    control.should_training_stop = True
                elif alert is not None and loss > alert:
                    print(f"⚠️  ALERT at step {step}: loss={loss:.4f} > alert={alert}")
                print(f"📊 Step {step}: loss={loss:.4f} [{status}]  ok=[{ok_low},{ok_high}]")

    return LossAlertCallback()


@app.function(
    image=image,
    gpu="A100-40GB",
    volumes={"/models": volume},
    timeout=60 * 60 * 6,
)
def train(smoke: bool = False):
    import torch
    from unsloth import FastModel
    from unsloth.chat_templates import get_chat_template, standardize_data_formats, train_on_responses_only
    from datasets import load_dataset
    from trl import SFTTrainer, SFTConfig

    MODEL_NAME = "unsloth/gemma-4-31B-it"
    MAX_SEQ_LENGTH = 2048

    print(f"🚀 Loading {MODEL_NAME}... (smoke={smoke})")
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
    # Manual load: normalize columns (adversarial records have extra 'type'/'topic' fields
    # that cause DatasetGenerationCastError with load_dataset — keep only 'messages')
    import json as _json
    raw_records = []
    with open("/data/sft_sprint7.jsonl") as _f:
        for _line in _f:
            _r = _json.loads(_line)
            raw_records.append({"messages": _r["messages"]})
    from datasets import Dataset as _Dataset
    dataset = _Dataset.from_list(raw_records)
    print(f"Dataset: {len(dataset)} examples")

    dataset = standardize_data_formats(dataset)

    def formatting_prompts_func(examples):
        convos = examples["conversations"] if "conversations" in examples else examples["messages"]
        texts = [
            tokenizer.apply_chat_template(
                convo, tokenize=False, add_generation_prompt=False, enable_thinking=False
            ).removeprefix("<bos>")
            for convo in convos
        ]
        return {"text": texts}

    dataset = dataset.map(formatting_prompts_func, batched=True)

    # 90/5/5 train/val/test split
    splits = dataset.train_test_split(test_size=0.10, seed=3407)
    train_dataset = splits["train"]
    temp = splits["test"].train_test_split(test_size=0.50, seed=3407)
    val_dataset = temp["train"]
    test_dataset = temp["test"]
    print(f"Split: {len(train_dataset)} train / {len(val_dataset)} val / {len(test_dataset)} test")

    # ── Smoke params vs full params ────────────────────────────────────────────
    if smoke:
        max_steps       = 100
        num_epochs      = None        # overridden by max_steps
        save_steps      = 50
        output_dir      = "/models/gemma31b-iris-sft-smoke"
        print(f"🔬 SMOKE MODE: max_steps={max_steps}, save_steps={save_steps}")
    else:
        max_steps       = -1          # full epoch
        num_epochs      = 1
        save_steps      = 200
        output_dir      = "/models/gemma31b-iris-sft-checkpoints"

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        args=SFTConfig(
            dataset_text_field="text",
            per_device_train_batch_size=2,
            gradient_accumulation_steps=4,
            warmup_ratio=0.05,
            num_train_epochs=num_epochs if num_epochs else 1,
            max_steps=max_steps,
            learning_rate=2e-4,
            lr_scheduler_type="cosine",
            optim="adamw_8bit",
            weight_decay=0.01,
            max_grad_norm=0.3,
            logging_steps=10,
            eval_strategy="steps",
            eval_steps=100,
            save_strategy="steps",
            save_steps=save_steps,
            save_total_limit=3,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            seed=3407,
            output_dir=output_dir,
            report_to="none",
        ),
        callbacks=[make_loss_callback()],
    )

    trainer = train_on_responses_only(
        trainer,
        instruction_part="<|turn>user\n",
        response_part="<|turn>model\n<|channel>thought\n<channel|>",
    )

    # ── Masking verification (PASO 5) ──────────────────────────────────────────
    print("\n🔍 Masking verification (pre-training)...")
    sample = trainer.train_dataset[0]
    if "labels" in sample:
        labels = sample["labels"]
        unmasked = sum(1 for l in labels if l != -100)
        total = len(labels)
        pct = unmasked / total * 100 if total > 0 else 0
        status = "✅" if 5 <= pct <= 60 else "⚠️ "
        print(f"  {status} Labels: {unmasked}/{total} unmasked ({pct:.1f}%)")
        print(f"     Expected: 5–60% unmasked (assistant tokens only)")
        # Decode to verify only assistant visible
        decoded_preview = tokenizer.decode(
            [tokenizer.pad_token_id if x == -100 else x for x in labels[:200]],
            skip_special_tokens=False,
        ).replace(tokenizer.pad_token or "<pad>", "·")
        print(f"  Labels preview (first 200 tokens): {decoded_preview[:300]!r}")
    else:
        print("  ⚠️  No 'labels' key found in dataset — masking check skipped")

    print(f"\n🔥 Starting {'SMOKE' if smoke else 'FULL'} training...")
    stats = trainer.train()
    print(f"\n✅ Done. Runtime: {stats.metrics['train_runtime']:.1f}s, Loss: {stats.metrics['train_loss']:.4f}")

    if smoke:
        print("\n📋 Smoke test summary:")
        for k, v in stats.metrics.items():
            print(f"  {k}: {v}")
        print("💾 Saving smoke checkpoint...")
        model.save_pretrained(output_dir + "-lora")
        tokenizer.save_pretrained(output_dir + "-lora")
    else:
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
    print(f"✅ Saved to Modal Volume 'clonnect-models' ({'smoke' if smoke else 'full'})")


@app.local_entrypoint()
def main(smoke: bool = False):
    train.remote(smoke=smoke)
