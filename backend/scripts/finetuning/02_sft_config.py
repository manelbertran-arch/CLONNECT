# =========================================================================
# FASE 1 — SFT Gemma4-31B Dense sobre Iris
# Basado en notebook oficial Unsloth: kaggle.com/code/danielhanchen/gemma4-31b-unsloth
# Adaptado para Clonnect con dataset sft_combined_audited.jsonl (5,739 conversaciones)
# =========================================================================
#
# CELDA 1: Install
# -----------------
# !pip install -qU unsloth unsloth_zoo
# !pip install -qU trl datasets accelerate peft bitsandbytes
# !pip install -qU --no-deps "xformers<0.0.27" "torch>=2.4.0"
#
# CELDA 2: Config
# ================

from unsloth import FastModel
import torch

# ============ MODEL ============
MODEL_NAME = "unsloth/gemma-4-31B-it"   # Instruct version — o "unsloth/gemma-4-31B" si prefieres base
MAX_SEQ_LENGTH = 2048                    # Mensajes Iris son cortos, 2048 suficiente
LOAD_IN_4BIT = True                      # QLoRA — 22GB VRAM en A100
LOAD_IN_16BIT = False                    # True si tienes >40GB VRAM (mejor calidad)

model, tokenizer = FastModel.from_pretrained(
    model_name=MODEL_NAME,
    max_seq_length=MAX_SEQ_LENGTH,
    load_in_4bit=LOAD_IN_4BIT,
    load_in_16bit=LOAD_IN_16BIT,
    full_finetuning=False,
    dtype=None,   # None = auto detect (bfloat16 en A100)
    # token="YOUR_HF_TOKEN",  # Si el modelo está gated
)

# ============ LORA CONFIG (hiperparámetros 2026 investigados) ============
model = FastModel.get_peft_model(
    model,
    finetune_vision_layers=False,        # Solo texto
    finetune_language_layers=True,
    finetune_attention_modules=True,
    finetune_mlp_modules=True,

    r=16,                                # Rank — dataset estilístico, 16 suficiente
    lora_alpha=32,                       # alpha = 2*r (consensus 2026)
    lora_dropout=0.05,                   # Anti-overfit (NO 0 como plan marzo)
    bias="none",
    random_state=3407,

    use_rslora=False,                    # Experimental; default LoRA standard
    target_modules=[                     # All-linear para capturar style
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
)

# ============ CHAT TEMPLATE ============
# Gemma 4 usa "gemma-4-thinking" para 26B/31B
# Nuestro dataset NO tiene thinking blocks → responder con thinking OFF
from unsloth.chat_templates import get_chat_template
tokenizer = get_chat_template(
    tokenizer,
    chat_template="gemma-4-thinking",
)

# CELDA 3: Load dataset
# ======================

from datasets import load_dataset

# Opción A: subir sft_combined_audited.jsonl a Kaggle como Dataset
# Opción B: subir a HuggingFace privado
DATASET_PATH = "/kaggle/input/clonnect-iris-combined/sft_combined_audited.jsonl"

dataset = load_dataset("json", data_files=DATASET_PATH, split="train")
print(f"Dataset loaded: {len(dataset)} examples")
print(f"Sample: {dataset[0]}")

# ============ FORMAT DATASET ============
# Nuestro dataset ya está en formato ChatML: {"messages": [...]}
# standardize_data_formats asegura compat con Gemma 4
from unsloth.chat_templates import standardize_data_formats
dataset = standardize_data_formats(dataset)

def formatting_prompts_func(examples):
    convos = examples["conversations"] if "conversations" in examples else examples["messages"]
    texts = [
        tokenizer.apply_chat_template(
            convo,
            tokenize=False,
            add_generation_prompt=False,
            enable_thinking=False,       # CRÍTICO: sin thinking para persona DM
        ).removeprefix("<bos>")          # Processor añade <bos> automáticamente
        for convo in convos
    ]
    return {"text": texts}

dataset = dataset.map(formatting_prompts_func, batched=True)
print(f"\nFormatted sample text:\n{dataset[0]['text'][:500]}")

# CELDA 4: Training config
# =========================

from trl import SFTTrainer, SFTConfig

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    eval_dataset=None,
    args=SFTConfig(
        # Batch
        dataset_text_field="text",
        per_device_train_batch_size=2,   # Kaggle T4/L4/A100
        gradient_accumulation_steps=4,   # Effective batch = 8

        # Schedule
        warmup_ratio=0.05,
        num_train_epochs=1,              # 1 epoch — NO más (risk overfit)
        # max_steps=-1,                  # Usar num_train_epochs=1 en vez de max_steps
        learning_rate=2e-4,              # Unsloth default para Gemma 4
        lr_scheduler_type="cosine",

        # Optimización
        optim="adamw_8bit",
        weight_decay=0.01,
        max_grad_norm=0.3,

        # Logging
        logging_steps=10,
        save_strategy="steps",
        save_steps=500,
        save_total_limit=3,

        # Precision
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),

        # Reproducibility
        seed=3407,

        # Output
        output_dir="outputs/gemma31b-iris-sft",
        report_to="none",                # o "wandb" si tienes cuenta
    ),
)

# ============ TRAIN ON RESPONSES ONLY (CRÍTICO) ============
# Sin esto, el modelo aprende a imitar también al lead — catastrófico
from unsloth.chat_templates import train_on_responses_only
trainer = train_on_responses_only(
    trainer,
    instruction_part="<|turn>user\n",
    response_part="<|turn>model\n<|channel>thought\n<channel|>",
)

# Verify masking (opcional pero recomendado)
print("\n=== VERIFICATION: Masked training sample (should show only assistant text) ===")
sample_labels = trainer.train_dataset[0]["labels"]
decoded = tokenizer.decode([
    tokenizer.pad_token_id if x == -100 else x for x in sample_labels
]).replace(tokenizer.pad_token, " ")
print(decoded[:500])

# CELDA 5: Train
# ===============

print("\n🚀 Starting SFT training...")
trainer_stats = trainer.train()

print(f"\n✅ Training complete!")
print(f"Runtime: {trainer_stats.metrics['train_runtime']:.1f}s")
print(f"Train loss: {trainer_stats.metrics['train_loss']:.4f}")

# GUARDRAIL: si final loss < 0.2 → overfitting
if trainer_stats.metrics['train_loss'] < 0.2:
    print("⚠️  WARNING: train_loss < 0.2 indica overfitting. Considerar:")
    print("   - Reducir epochs (ya estamos en 1)")
    print("   - Aumentar lora_dropout a 0.1")
    print("   - Reducir learning_rate a 1e-4")

# CELDA 6: Save + Merge
# ======================

# Save LoRA adapter
model.save_pretrained("gemma31b-iris-sft-lora")
tokenizer.save_pretrained("gemma31b-iris-sft-lora")

# Merge to 16bit para deploy/evaluación
model.save_pretrained_merged(
    "gemma31b-iris-sft-merged",
    tokenizer,
    save_method="merged_16bit",
)

# OPCIONAL: push a HuggingFace privado
# model.push_to_hub("manelpujol/gemma31b-iris-sft", tokenizer, private=True, token="HF_TOKEN")

# OPCIONAL: GGUF para serving local
# model.save_pretrained_gguf("gemma31b-iris-sft-gguf", tokenizer, quantization_method="q4_k_m")

# CELDA 7: Smoke test inferencia
# ================================

messages = [
    {"role": "user", "content": "Hola! he visto tu reel, me encantaa"}
]
inputs = tokenizer.apply_chat_template(
    messages,
    add_generation_prompt=True,
    tokenize=True,
    return_dict=True,
    return_tensors="pt",
).to("cuda")

from transformers import TextStreamer
_ = model.generate(
    **inputs,
    max_new_tokens=100,
    use_cache=True,                      # CRÍTICO Gemma 4 (bug documentado con use_cache=False)
    temperature=1.0,                     # Gemma 4 recommended
    top_p=0.95,
    top_k=64,
    streamer=TextStreamer(tokenizer, skip_prompt=True),
)

# =========================================================================
# SIGUIENTE PASO:
# 1. Descargar gemma31b-iris-sft-merged
# 2. Servir en DeepInfra custom deployment O localmente con vLLM
# 3. Ejecutar 03_ccee_measurement.sh contra el nuevo endpoint
# 4. Gate 1 según composite v5 obtenido
# =========================================================================
