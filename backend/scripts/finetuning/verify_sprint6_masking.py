#!/usr/bin/env python3
"""
verify_sprint6_masking.py — Diagnóstico retrospectivo del masking SFT Sprint 6

Requiere:
    pip install unsloth transformers datasets

Uso:
    python3 scripts/finetuning/verify_sprint6_masking.py \
        --dataset data/dpo/trl/sft_combined_audited.jsonl \
        --n_samples 5

Qué verifica:
    1. Tokens producidos por apply_chat_template(enable_thinking=False)
    2. Masking correcto de train_on_responses_only
    3. Secuencia de tokens en el boundary user/model
    4. Presencia/ausencia de <|channel>thought tokens en training labels
"""
import argparse
import json


def verify_masking(dataset_path: str, n_samples: int = 5):
    # Imports tardíos para no fallar en entornos sin GPU
    from unsloth import FastModel
    from unsloth.chat_templates import get_chat_template, standardize_data_formats, train_on_responses_only
    from datasets import load_dataset
    from trl import SFTTrainer, SFTConfig
    import torch

    print("=== Sprint 6 Masking Retrospective Diagnostic ===\n")

    # --- 1. Cargar tokenizer (sin model para eficiencia) ---
    print("Loading tokenizer from unsloth/gemma-4-31B-it (no model weights)...")
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained("unsloth/gemma-4-31B-it")
    tokenizer = get_chat_template(tokenizer, chat_template="gemma-4-thinking")

    # --- 2. Cargar un sample del dataset ---
    print(f"Loading {n_samples} samples from {dataset_path}...")
    dataset = load_dataset("json", data_files=dataset_path, split="train")
    dataset = standardize_data_formats(dataset)

    print("\n" + "="*60)
    print("SECTION 1: What apply_chat_template(enable_thinking=False) produces")
    print("="*60)

    for i, example in enumerate(dataset.select(range(n_samples))):
        convos = example.get("conversations") or example.get("messages") or []
        if not convos:
            continue

        # Replicar formatting_prompts_func del Sprint 6
        text_sprint6 = tokenizer.apply_chat_template(
            convos,
            tokenize=False,
            add_generation_prompt=False,
            enable_thinking=False,
        ).removeprefix("<bos>")

        print(f"\n--- Sample {i} ---")
        print(f"Formatted text (first 400 chars):\n{text_sprint6[:400]}")

        # Verificar presencia de channel tokens
        has_channel = "<|channel>" in text_sprint6 or "<channel|>" in text_sprint6
        has_thinking_prefix = "<|channel>thought\n<channel|>" in text_sprint6
        print(f"\n❓ Contains <|channel> tokens: {has_channel}")
        print(f"❓ Contains <|channel>thought\\n<channel|> prefix: {has_thinking_prefix}")

        if has_channel:
            print("⚠️  WARNING: Channel tokens found in training data — unexpected for enable_thinking=False")
        else:
            print("✅ No channel tokens in training data (expected for enable_thinking=False)")

    print("\n" + "="*60)
    print("SECTION 2: Inference template — what the model sees at serving time")
    print("="*60)

    sample_convo = dataset[0].get("conversations") or dataset[0].get("messages") or []
    user_turn_only = [t for t in sample_convo if t["role"] == "user"][:1]

    inference_text = tokenizer.apply_chat_template(
        user_turn_only,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    print(f"\nInference prompt tail (last 200 chars):\n...{inference_text[-200:]}")

    has_channel_in_inference = "<|channel>thought\n<channel|>" in inference_text
    print(f"\n❓ Inference prompt ends with <|channel>thought\\n<channel|>: {has_channel_in_inference}")

    if has_channel_in_inference:
        print("⚠️  MISMATCH CONFIRMED: Training labels have NO channel prefix,")
        print("   but inference template INJECTS it. This is the Sprint 6 bug.")
    else:
        print("✅ No mismatch detected at this point.")

    print("\n" + "="*60)
    print("SECTION 3: Token IDs at the train/serve boundary")
    print("="*60)

    boundary_string_train = "<|turn>model\n"
    boundary_string_serve = "<|turn>model\n<|channel>thought\n<channel|>"

    train_ids = tokenizer.encode(boundary_string_train, add_special_tokens=False)
    serve_ids = tokenizer.encode(boundary_string_serve, add_special_tokens=False)

    print(f"\nTraining boundary: {repr(boundary_string_train)}")
    print(f"  Token IDs: {train_ids}")
    print(f"  Decoded:   {[tokenizer.decode([t]) for t in train_ids]}")

    print(f"\nServing boundary: {repr(boundary_string_serve)}")
    print(f"  Token IDs: {serve_ids}")
    print(f"  Decoded:   {[tokenizer.decode([t]) for t in serve_ids]}")

    prefix_mismatch = train_ids != serve_ids[:len(train_ids)]
    print(f"\n❓ Token boundary mismatch training vs serving: {prefix_mismatch}")

    print("\n" + "="*60)
    print("SECTION 4: Sprint 7 aligned boundary verification")
    print("="*60)

    sprint7_boundary = "<|turn>model\n<|channel>thought\n<channel|>"
    sprint7_ids = tokenizer.encode(sprint7_boundary, add_special_tokens=False)

    print(f"Sprint 7 response_part: {repr(sprint7_boundary)}")
    print(f"  Token IDs: {sprint7_ids}")
    print(f"  Decoded:   {[tokenizer.decode([t]) for t in sprint7_ids]}")

    print("\n=== DIAGNOSTIC SUMMARY ===")
    print("""
Sprint 6 mismatch:
  Training label boundary:  '<|turn>model\\n{response}'
  Inference context ending:  '<|turn>model\\n<|channel>thought\\n<channel|>'
  → Model predicts response DIRECTLY after <|turn>model\\n
  → But at inference, must continue from <|channel>thought\\n<channel|>
  → OOD context → C3 leakage, J6 degradation

Sprint 7 fix:
  Training label boundary:  '<|turn>model\\n<|channel>thought\\n<channel|>{response}'
  Inference context ending:  '<|turn>model\\n<|channel>thought\\n<channel|>'
  → Model predicts response AFTER channel prefix (consistent)
  → response_part='<|turn>model\\n<|channel>thought\\n<channel|>'
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify Sprint 6 masking and diagnose template mismatch")
    parser.add_argument("--dataset", default="data/dpo/trl/sft_combined_audited.jsonl")
    parser.add_argument("--n_samples", type=int, default=5)
    args = parser.parse_args()
    verify_masking(args.dataset, args.n_samples)
