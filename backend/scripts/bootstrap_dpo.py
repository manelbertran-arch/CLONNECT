#!/usr/bin/env python3
"""
Bootstrap DPO — On-policy preference pair generation (DICE, ICLR 2025).

Generates DPO training pairs by:
1. Sampling prompts from test sets, SFT data, and synthetic generators
2. Generating N response variations from the tuned model (temperature=0.9)
3. Scoring each variation with an LLM judge (GPT-4o-mini)
4. Creating chosen/rejected pairs from best/worst variations (delta > 1.5)

This implements the iterative DPO bootstrapping loop described in DICE and
used by Llama 3 (6 rounds). Each round uses the latest tuned model to
generate on-policy responses, which are then ranked and added to the
training set for the next round.

Usage:
    python scripts/bootstrap_dpo.py \\
        --provider together \\
        --model manelbertran/iris-bertran-v1 \\
        --num-prompts 300 \\
        --num-variations 4 \\
        --output data/dpo/trl/dpo_bootstrapped_iris.jsonl

    # Dry run (show prompts, don't call APIs):
    python scripts/bootstrap_dpo.py --dry-run --num-prompts 10

    # Merge with existing pairs:
    python scripts/bootstrap_dpo.py \\
        --provider together \\
        --model manelbertran/iris-bertran-v1 \\
        --merge-with data/dpo/trl/dpo_together_iris.jsonl \\
        --output data/dpo/trl/dpo_combined_iris.jsonl

Cost estimate (300 prompts × 4 variations):
    Tuned model:  1,200 calls × ~100 tokens out = 120K tokens ≈ $0.10-0.30
    LLM judge:    1,200 calls × ~200 tokens in+out = 240K tokens ≈ $0.04
    Total:        ~$0.15-0.35 per round
"""

import argparse
import json
import logging
import os
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("bootstrap_dpo")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

# System prompt for Iris (same as SFT training)
SYSTEM_PROMPT = (
    "Eres Iris Bertran. Monitora de fitness en Dinamic Sport Gym, Igualada (Barcelona). "
    "Bilingüe catalán-castellano, mensajes ultra-breves, directa, informal, tuteo siempre. "
    "NO eres asistente virtual. Respondes DMs como persona real entre clases."
)

# LLM judge prompt
JUDGE_SYSTEM = """You are an expert evaluator of AI chatbot voice cloning quality.
Score how well the response matches Iris Bertran's style:
- Bilingual Catalan/Spanish code-switching
- Ultra-brief messages (10-60 chars typical)
- Warm, direct, informal (cuca, nena, flor, amor)
- Heavy emoji user (😂🫠🩷❤️😘🥹)
- Never sounds like a customer service bot

Score 0-10. Respond with ONLY a JSON: {"score": N, "reason": "one sentence"}"""

JUDGE_USER = """Message: "{prompt}"
Response: "{response}"

Score the response 0-10 for how well it matches Iris Bertran's voice."""


# ═══════════════════════════════════════════════════════════════════════════════
# PROMPT SOURCES
# ═══════════════════════════════════════════════════════════════════════════════

def load_prompts_test_set(path: Path) -> List[str]:
    """Extract user messages from test_set_v2.json."""
    if not path.exists():
        logger.warning("Test set not found: %s", path)
        return []
    with open(path) as f:
        data = json.load(f)
    prompts = []
    for conv in data.get("conversations", []):
        msg = conv.get("test_input", "").strip()
        if msg and len(msg) >= 3:
            prompts.append(msg)
    logger.info("Loaded %d prompts from test set", len(prompts))
    return prompts


def load_prompts_sft(path: Path, max_prompts: int = 200) -> List[str]:
    """Extract user messages from SFT JSONL."""
    if not path.exists():
        logger.warning("SFT data not found: %s", path)
        return []
    prompts = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                messages = data.get("messages", [])
                for msg in messages:
                    if msg.get("role") == "user":
                        content = msg["content"].strip()
                        if content and len(content) >= 3:
                            prompts.append(content)
                            break  # Only first user message per conversation
            except (json.JSONDecodeError, KeyError):
                continue
    random.shuffle(prompts)
    prompts = prompts[:max_prompts]
    logger.info("Loaded %d prompts from SFT data", len(prompts))
    return prompts


def generate_synthetic_prompts(n: int = 50) -> List[str]:
    """Generate diverse synthetic prompts covering Iris's conversation types."""
    templates = {
        "saludo_es": [
            "Hola!", "Buenas!", "Hola guapa!", "Hey!",
            "Buenos días!", "Hola Iris!", "Que tal?",
        ],
        "saludo_ca": [
            "Bon dia!", "Ei!", "Holaa!", "Bon dia guapa!",
            "Que tal?", "Hola nena!",
        ],
        "precio": [
            "Cuanto cuesta una clase?", "Quin preu te?",
            "Precio de barre?", "Cuanto es la clase suelta?",
            "Es gratis la primera clase?", "Hay algun descuento?",
            "Quant costa una sessió de reformer?",
        ],
        "reserva": [
            "Me puedo apuntar?", "Hay plaza para mañana?",
            "Quiero reservar para el jueves",
            "Em pots apuntar a barre de dema?",
            "Puedo ir al Flow4U del jueves?",
        ],
        "objecion": [
            "No puedo venir mañana", "No puc dijous",
            "Estoy malita no iré", "Tengo trabajo no llego",
            "No arribo, lo siento!", "Estic constipada",
        ],
        "personal": [
            "Que tal el fin de semana?", "Com va tot?",
            "Que haces?", "Hoy ha sido un día largo...",
            "Me he comprado unas bambas nuevas!",
        ],
        "emoji_reaction": [
            "😂😂😂", "❤️", "🔥🔥", "💪💪💪",
            "Jajajaja", "Buaaa", "Ostiaaa",
        ],
        "audio": [
            "[audio]", "Sent a voice message",
            "[🎤 Audio]: Hola guapa que tal como estas?",
        ],
        "media": [
            "Sent an attachment", "Sent a photo",
            "Mentioned you in their story",
        ],
        "gratitud": [
            "Gracias por la clase!", "Gràcies nena!",
            "Mil gracias!", "La clase de hoy brutal!",
            "Me ha encantado la clase de barre!",
        ],
    }

    all_prompts = []
    for category, options in templates.items():
        all_prompts.extend(options)

    random.shuffle(all_prompts)
    result = all_prompts[:n]
    logger.info("Generated %d synthetic prompts", len(result))
    return result


def collect_prompts(num_prompts: int) -> List[str]:
    """Collect prompts from all sources, deduplicate, sample."""
    prompts = []

    # Source 1: Test set
    prompts.extend(load_prompts_test_set(REPO_ROOT / "tests" / "test_set_v2.json"))

    # Source 2: SFT data
    prompts.extend(load_prompts_sft(
        REPO_ROOT / "data" / "dpo" / "trl" / "sft_2000.jsonl",
        max_prompts=200,
    ))

    # Source 3: Synthetic
    prompts.extend(generate_synthetic_prompts(n=80))

    # Deduplicate (case-insensitive)
    seen = set()
    unique = []
    for p in prompts:
        key = p.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(p)

    random.shuffle(unique)
    result = unique[:num_prompts]
    logger.info("Collected %d unique prompts (requested %d)", len(result), num_prompts)
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL INFERENCE (pluggable providers)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_messages(prompt: str) -> List[Dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]


def generate_responses_together(
    model: str, prompt: str, n: int, temperature: float, api_key: str,
) -> List[str]:
    """Generate N responses using Together AI API."""
    import requests

    responses = []
    for _ in range(n):
        try:
            resp = requests.post(
                "https://api.together.xyz/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": _build_messages(prompt),
                    "temperature": temperature,
                    "max_tokens": 150,
                    "stop": ["\n\n"],
                },
                timeout=30,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            if content:
                responses.append(content)
        except Exception as e:
            logger.warning("Together API error: %s", e)
    return responses


def generate_responses_fireworks(
    model: str, prompt: str, n: int, temperature: float, api_key: str,
) -> List[str]:
    """Generate N responses using Fireworks AI API."""
    import requests

    responses = []
    for _ in range(n):
        try:
            resp = requests.post(
                "https://api.fireworks.ai/inference/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": _build_messages(prompt),
                    "temperature": temperature,
                    "max_tokens": 150,
                },
                timeout=30,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            if content:
                responses.append(content)
        except Exception as e:
            logger.warning("Fireworks API error: %s", e)
    return responses


def generate_responses_deepinfra(
    model: str, prompt: str, n: int, temperature: float, api_key: str,
) -> List[str]:
    """Generate N responses using DeepInfra API."""
    import requests

    responses = []
    for _ in range(n):
        try:
            resp = requests.post(
                "https://api.deepinfra.com/v1/openai/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": _build_messages(prompt),
                    "temperature": temperature,
                    "max_tokens": 150,
                },
                timeout=30,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            if content:
                responses.append(content)
        except Exception as e:
            logger.warning("DeepInfra API error: %s", e)
    return responses


PROVIDERS = {
    "together": generate_responses_together,
    "fireworks": generate_responses_fireworks,
    "deepinfra": generate_responses_deepinfra,
}


# ═══════════════════════════════════════════════════════════════════════════════
# LLM JUDGE
# ═══════════════════════════════════════════════════════════════════════════════

def judge_response(prompt: str, response: str, judge_client) -> float:
    """Score a single response using GPT-4o-mini as judge. Returns 0-10."""
    try:
        user_prompt = JUDGE_USER.format(prompt=prompt[:200], response=response[:300])
        result = judge_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=100,
        )
        raw = result.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        data = json.loads(raw)
        return max(0.0, min(10.0, float(data.get("score", 0))))
    except Exception as e:
        logger.warning("Judge error: %s", e)
        return 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# DPO PAIR CREATION
# ═══════════════════════════════════════════════════════════════════════════════

def create_dpo_pair(
    prompt: str,
    responses: List[str],
    scores: List[float],
    min_delta: float = 1.5,
) -> Optional[Dict]:
    """Create a DPO pair from scored response variations.

    Returns Together DPO format or None if delta is too small.
    """
    if len(responses) < 2 or len(scores) < 2:
        return None

    paired = list(zip(scores, responses))
    paired.sort(key=lambda x: x[0], reverse=True)

    best_score, best_response = paired[0]
    worst_score, worst_response = paired[-1]
    delta = best_score - worst_score

    if delta < min_delta:
        return None

    return {
        "input": {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ]
        },
        "preferred_output": [{"role": "assistant", "content": best_response}],
        "non_preferred_output": [{"role": "assistant", "content": worst_response}],
        "_meta": {
            "best_score": best_score,
            "worst_score": worst_score,
            "delta": round(delta, 1),
            "n_variations": len(responses),
        },
    }


def convert_existing_pairs(path: Path) -> List[Dict]:
    """Convert existing DPO pairs (TRL format) to Together format."""
    if not path.exists():
        return []
    pairs = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            pairs.append({
                "input": {
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": data.get("prompt", "")},
                    ]
                },
                "preferred_output": [
                    {"role": "assistant", "content": data.get("chosen", "")}
                ],
                "non_preferred_output": [
                    {"role": "assistant", "content": data.get("rejected", "")}
                ],
            })
    logger.info("Converted %d existing pairs to Together format", len(pairs))
    return pairs


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Bootstrap DPO — On-policy preference pair generation (DICE-style)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full run with Together AI:
  python scripts/bootstrap_dpo.py \\
      --provider together --model manelbertran/iris-bertran-v1 \\
      --num-prompts 300 --num-variations 4

  # Dry run (show prompts, no API calls):
  python scripts/bootstrap_dpo.py --dry-run --num-prompts 10

  # Merge with existing pairs:
  python scripts/bootstrap_dpo.py \\
      --provider together --model manelbertran/iris-bertran-v1 \\
      --merge-with data/dpo/trl/dpo_together_iris.jsonl

Cost estimate (300 prompts × 4 variations):
  Tuned model:  1,200 calls × ~100 tok = 120K tokens ≈ $0.10-0.30
  LLM judge:    1,200 calls × ~200 tok = 240K tokens ≈ $0.04
  Total:        ~$0.15-0.35 per bootstrap round
        """,
    )
    parser.add_argument("--provider", choices=list(PROVIDERS.keys()), default="together",
                        help="Inference provider (default: together)")
    parser.add_argument("--model", type=str, default="manelbertran/iris-bertran-v1",
                        help="Model name on the provider")
    parser.add_argument("--num-prompts", type=int, default=300,
                        help="Number of prompts to sample (default: 300)")
    parser.add_argument("--num-variations", type=int, default=4,
                        help="Responses per prompt (default: 4)")
    parser.add_argument("--temperature", type=float, default=0.9,
                        help="Sampling temperature (default: 0.9)")
    parser.add_argument("--min-delta", type=float, default=1.5,
                        help="Minimum score delta to keep a pair (default: 1.5)")
    parser.add_argument("--output", "-o", type=str,
                        default="data/dpo/trl/dpo_bootstrapped_iris.jsonl",
                        help="Output path")
    parser.add_argument("--merge-with", type=str, default=None,
                        help="Merge with existing DPO pairs (Together format or TRL)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only collect prompts, don't call APIs")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)

    # 1. Collect prompts
    prompts = collect_prompts(args.num_prompts)
    logger.info("=" * 50)
    logger.info("Collected %d prompts", len(prompts))

    if args.dry_run:
        logger.info("\n--- DRY RUN: showing first 15 prompts ---")
        for i, p in enumerate(prompts[:15]):
            print(f"  [{i + 1}] {p[:80]}")
        total_calls = len(prompts) * args.num_variations
        logger.info(f"\nWould generate {total_calls} model calls + {total_calls} judge calls")
        logger.info(f"Estimated cost: ${total_calls * 0.0003:.2f}-${total_calls * 0.0005:.2f}")
        return

    # 2. Setup clients
    provider_fn = PROVIDERS[args.provider]
    api_key_env = {
        "together": "TOGETHER_API_KEY",
        "fireworks": "FIREWORKS_API_KEY",
        "deepinfra": "DEEPINFRA_API_KEY",
    }
    api_key = os.environ.get(api_key_env[args.provider], "")
    if not api_key:
        logger.error("Set %s environment variable", api_key_env[args.provider])
        sys.exit(1)

    from openai import OpenAI
    judge_client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

    # 3. Generate and judge
    pairs = []
    total_generated = 0
    total_judged = 0
    all_deltas = []
    all_best_scores = []

    for i, prompt in enumerate(prompts):
        logger.info("[%d/%d] Prompt: %s", i + 1, len(prompts), prompt[:60])

        # Generate variations
        responses = provider_fn(
            model=args.model,
            prompt=prompt,
            n=args.num_variations,
            temperature=args.temperature,
            api_key=api_key,
        )
        total_generated += len(responses)

        if len(responses) < 2:
            logger.warning("  Only %d responses, skipping", len(responses))
            continue

        # Judge each response
        scores = []
        for resp in responses:
            score = judge_response(prompt, resp, judge_client)
            scores.append(score)
            total_judged += 1

        # Create DPO pair
        pair = create_dpo_pair(prompt, responses, scores, min_delta=args.min_delta)
        if pair:
            pairs.append(pair)
            delta = pair["_meta"]["delta"]
            all_deltas.append(delta)
            all_best_scores.append(pair["_meta"]["best_score"])
            logger.info(
                "  ✓ Pair created: best=%.1f worst=%.1f delta=%.1f",
                pair["_meta"]["best_score"],
                pair["_meta"]["worst_score"],
                delta,
            )
        else:
            logger.info("  ✗ Filtered (delta < %.1f)", args.min_delta)

        # Rate limiting
        time.sleep(0.5)

    # 4. Merge with existing pairs if requested
    existing_pairs = []
    if args.merge_with:
        merge_path = Path(args.merge_with)
        if merge_path.suffix == ".jsonl":
            # Auto-detect format
            with open(merge_path) as f:
                first_line = json.loads(f.readline())
            if "input" in first_line:
                # Already Together format
                with open(merge_path) as f:
                    existing_pairs = [json.loads(l) for l in f if l.strip()]
            else:
                # TRL format, convert
                existing_pairs = convert_existing_pairs(merge_path)
        logger.info("Merged with %d existing pairs", len(existing_pairs))

    all_pairs = existing_pairs + pairs

    # 5. Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for pair in all_pairs:
            # Remove _meta for training output
            clean = {k: v for k, v in pair.items() if not k.startswith("_")}
            f.write(json.dumps(clean, ensure_ascii=False) + "\n")

    # 6. Stats
    logger.info("\n" + "=" * 50)
    logger.info("BOOTSTRAP DPO RESULTS")
    logger.info("=" * 50)
    logger.info("Prompts processed:   %d", len(prompts))
    logger.info("Responses generated: %d", total_generated)
    logger.info("Responses judged:    %d", total_judged)
    logger.info("Pairs created:       %d (from this run)", len(pairs))
    logger.info("Pairs filtered:      %d (delta < %.1f)", len(prompts) - len(pairs), args.min_delta)
    if existing_pairs:
        logger.info("Existing pairs:      %d (merged)", len(existing_pairs))
    logger.info("Total output pairs:  %d", len(all_pairs))

    if all_deltas:
        logger.info("Delta stats:  mean=%.1f  median=%.1f  min=%.1f  max=%.1f",
                     statistics.mean(all_deltas),
                     statistics.median(all_deltas),
                     min(all_deltas),
                     max(all_deltas))
    if all_best_scores:
        logger.info("Best scores:  mean=%.1f  median=%.1f",
                     statistics.mean(all_best_scores),
                     statistics.median(all_best_scores))

    logger.info("\nOutput: %s", output_path)
    logger.info("=" * 50)

    # Save metadata
    meta_path = output_path.with_suffix(".meta.json")
    meta = {
        "provider": args.provider,
        "model": args.model,
        "num_prompts": len(prompts),
        "num_variations": args.num_variations,
        "temperature": args.temperature,
        "min_delta": args.min_delta,
        "pairs_generated": len(pairs),
        "pairs_total": len(all_pairs),
        "delta_mean": round(statistics.mean(all_deltas), 1) if all_deltas else 0,
        "best_score_mean": round(statistics.mean(all_best_scores), 1) if all_best_scores else 0,
    }
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)


if __name__ == "__main__":
    main()
