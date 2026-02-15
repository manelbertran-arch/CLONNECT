"""
Test inference with fine-tuned Llama 4 Scout LoRA adapter.

Loads base model + LoRA adapter from HuggingFace, generates sample responses.
Use this to verify the fine-tuning worked before integrating into production.

Requirements:
    pip install --no-deps "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"
    pip install --no-deps trl peft accelerate bitsandbytes xformers

Usage:
    python inference_scout_ft.py --adapter "your-org/stefano-scout-lora"
"""

import argparse

BASE_MODEL = "meta-llama/Llama-4-Scout-17B-16E-Instruct"
MAX_SEQ_LENGTH = 2048

# Real Stefano DM inputs for testing
TEST_INPUTS = [
    {
        "system": "Eres Stefano Bonanno respondiendo DMs de Instagram. Longitud mediana: 18 caracteres. Usas emoji en ~23% de mensajes. Responde de forma breve y natural.",
        "user": "Hola Stefano! Me encanta tu contenido 🔥",
        "expected_style": "Short greeting, possibly with emoji",
    },
    {
        "system": "Eres Stefano Bonanno respondiendo DMs de Instagram. Longitud mediana: 18 caracteres. Usas emoji en ~23% de mensajes. Responde de forma breve y natural.",
        "user": "Cuanto cuesta tu curso?",
        "expected_style": "Brief product mention, redirect to link",
    },
    {
        "system": "Eres Stefano Bonanno respondiendo DMs de Instagram. Longitud mediana: 18 caracteres. Usas emoji en ~23% de mensajes. Responde de forma breve y natural.",
        "user": "Jajaja eso estuvo muy bueno",
        "expected_style": "Short humor response, casual",
    },
    {
        "system": "Eres Stefano Bonanno respondiendo DMs de Instagram. Longitud mediana: 18 caracteres. Usas emoji en ~23% de mensajes. Responde de forma breve y natural.",
        "user": "Gracias por responder! Sos un crack",
        "expected_style": "Brief gratitude acknowledgment",
    },
    {
        "system": "Eres Stefano Bonanno respondiendo DMs de Instagram. Longitud mediana: 18 caracteres. Usas emoji en ~23% de mensajes. Responde de forma breve y natural.",
        "user": "Que opinas de invertir en crypto ahora?",
        "expected_style": "Brief opinion, Stefano's voice",
    },
]


def main():
    parser = argparse.ArgumentParser(description="Test Scout fine-tuned model inference")
    parser.add_argument("--adapter", required=True, help="HuggingFace adapter repo or local path")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--max-tokens", type=int, default=60)
    parser.add_argument("--hf-token", default=None, help="HuggingFace token (or set HF_TOKEN env)")
    args = parser.parse_args()

    print(f"Loading base model: {BASE_MODEL}")
    print(f"Loading adapter: {args.adapter}")

    from unsloth import FastLanguageModel

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.adapter,
        max_seq_length=MAX_SEQ_LENGTH,
        dtype=None,
        load_in_4bit=True,
    )

    # Enable fast inference mode
    FastLanguageModel.for_inference(model)

    print("\n" + "=" * 70)
    print("INFERENCE TEST — Fine-Tuned Scout")
    print("=" * 70)

    for i, test in enumerate(TEST_INPUTS, 1):
        messages = [
            {"role": "system", "content": test["system"]},
            {"role": "user", "content": test["user"]},
        ]

        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

        outputs = model.generate(
            **inputs,
            max_new_tokens=args.max_tokens,
            temperature=args.temperature,
            do_sample=True,
            top_p=0.9,
        )

        # Decode only the new tokens
        new_tokens = outputs[0][inputs["input_ids"].shape[1]:]
        response = tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

        print(f"\n--- Test {i}/5 ---")
        print(f"  User:     {test['user']}")
        print(f"  Response: {response}")
        print(f"  Length:   {len(response)} chars")
        print(f"  Expected: {test['expected_style']}")

    print("\n" + "=" * 70)
    print("INFERENCE TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
