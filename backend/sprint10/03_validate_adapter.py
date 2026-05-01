"""
Sprint 10 — Post-training adapter validation
=============================================

Run after training completes to verify adapters load and produce coherent output.
Use on the Vast.ai instance or locally with the HF repo.

Usage:
  python sprint10/03_validate_adapter.py --phase sft
  python sprint10/03_validate_adapter.py --phase dpo
  python sprint10/03_validate_adapter.py --phase dpo --local output/sprint10/dpo/final
"""

import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("sprint10.validate")

SFT_REPO = "manelbertranluque/clonnect-iris-sft-sprint10-qwen3-32b"
DPO_REPO = "manelbertranluque/clonnect-iris-dpo-sprint10-qwen3-32b"
BASE_MODEL = "Qwen/Qwen3-32B"

# Canonical test messages covering main conversation types
TEST_MESSAGES = [
    "Hola Iris, cuánto cuestan tus clases?",
    "Ei guapa! Quina foto más bonica",
    "Me interesa apuntarme a barre, hay sitio?",
    "No sé si me va a gustar, es mi primera vez",
    "Gràcies per tot nena! 🩷",
    "🤣🤣🤣",
    "Oye y los horarios? Trabajo hasta las 6",
    "[audio message]",
]

SYSTEM_PROMPT = (
    "Eres Iris Bertran. Monitora de fitness en Dinamic Sport Gym, Igualada (Barcelona). "
    "Bilingüe catalán-castellano, mensajes ultra-breves, directa, informal, tuteo siempre. "
    "NO eres asistente virtual. Respondes DMs como persona real entre clases."
)

# Pass/fail heuristics for sanity check
def check_response(msg: str, response: str) -> tuple[bool, str]:
    """Basic sanity checks on generated response."""
    if not response or not response.strip():
        return False, "empty response"
    if len(response) > 300:
        return False, f"too long ({len(response)} chars) — Iris is ultra-brief"
    if any(phrase in response.lower() for phrase in [
        "como asistente", "como ia", "how can i help", "i'm an ai",
        "lo siento, no puedo", "no estoy segura de", "como modelo de lenguaje",
    ]):
        return False, "sounds like a bot/assistant"
    return True, "ok"


def validate(adapter_path: str) -> None:
    import torch
    from unsloth import FastLanguageModel

    logger.info("Loading base: %s", BASE_MODEL)
    logger.info("Loading adapter: %s", adapter_path)

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=4096,
        dtype=torch.bfloat16,
        load_in_4bit=False,
    )

    from peft import PeftModel
    model = PeftModel.from_pretrained(model, adapter_path)
    FastLanguageModel.for_inference(model)

    passed = 0
    failed = 0

    print("\n" + "=" * 60)
    print(f"Validation — {adapter_path}")
    print("=" * 60)

    for msg in TEST_MESSAGES:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": msg},
        ]
        input_ids = tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        ).to(model.device)

        with torch.no_grad():
            output_ids = model.generate(
                input_ids,
                max_new_tokens=100,
                temperature=0.7,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id,
            )

        response = tokenizer.decode(
            output_ids[0][input_ids.shape[1]:],
            skip_special_tokens=True,
        ).strip()

        ok, reason = check_response(msg, response)
        status = "[PASS]" if ok else "[FAIL]"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"\n{status} Q: {msg[:50]}")
        print(f"       A: {response[:150]}")
        if not ok:
            print(f"       ! {reason}")

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{len(TEST_MESSAGES)} passed")
    print("=" * 60)

    if failed > 0:
        logger.warning("%d checks failed — review responses above", failed)
        sys.exit(1)
    else:
        logger.info("All checks passed")


def main():
    parser = argparse.ArgumentParser(description="Sprint 10 Adapter Validation")
    parser.add_argument("--phase", choices=["sft", "dpo"], default="dpo",
                        help="Which adapter to validate")
    parser.add_argument("--local", type=str, default=None,
                        help="Local adapter path (default: HF repo)")
    args = parser.parse_args()

    if args.local:
        adapter_path = args.local
    elif args.phase == "sft":
        adapter_path = SFT_REPO
    else:
        adapter_path = DPO_REPO

    validate(adapter_path)


if __name__ == "__main__":
    main()
