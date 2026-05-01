#!/usr/bin/env python3
"""
Blind A/B judge: evaluate Stefano-real vs bot responses without knowing which is which.

Single judge: GPT-4o-mini. Randomizes A/B order to prevent positional bias.

Usage:
    railway run python3.11 scripts/blind_judge.py --input results/backtest_full_XXX.json
    railway run python3.11 scripts/blind_judge.py --input results/backtest_full_XXX.json --sample 200

Cost estimate:
    - GPT-4o-mini: ~$0.02/pair
    - 200 pairs: ~$4
    - 2000 pairs: ~$40
"""
import sys
import json
import time
import asyncio
import argparse
import logging
import random
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Judge prompt
# ---------------------------------------------------------------------------

BLIND_JUDGE_PROMPT = """Eres un evaluador experto de mensajes de DM. Te doy el contexto de una conversacion y dos respuestas posibles (A y B). Una es de una persona real y otra de un bot de IA. NO sabes cual es cual.

## Contexto de la conversacion:
{conversation_context}

## Ultimo mensaje del usuario:
{lead_message}

## Respuesta A:
{response_a}

## Respuesta B:
{response_b}

## Evalua CADA respuesta en estas dimensiones (0-100):

1. **Naturalidad**: Suena como una persona real escribiendo por DM? (no como un bot)
2. **Relevancia**: Responde a lo que pregunto el usuario?
3. **Estilo**: Es consistente con el estilo de la conversacion previa?
4. **Efectividad**: Avanza la conversacion hacia un objetivo util?
5. **Personalidad**: Tiene personalidad propia o es generico?

## Despues responde:
- Cual crees que es la persona real? (A o B)
- Con que confianza? (baja/media/alta)
- Por que?

Responde SOLO en JSON valido (sin comentarios):
{{"response_a": {{"naturalidad": 0, "relevancia": 0, "estilo": 0, "efectividad": 0, "personalidad": 0}}, "response_b": {{"naturalidad": 0, "relevancia": 0, "estilo": 0, "efectividad": 0, "personalidad": 0}}, "guess_real": "A", "confidence": "media", "reasoning": "..."}}"""


# ---------------------------------------------------------------------------
# LLM Judge callers
# ---------------------------------------------------------------------------

async def call_judge_deepinfra(prompt: str) -> dict:
    """Call Qwen3-30B-A3B via DeepInfra as judge."""
    from scripts._shared.deepinfra_client import get_deepinfra_async_client, JUDGE_MODEL

    client = get_deepinfra_async_client()
    try:
        response = await client.chat.completions.create(
            model=JUDGE_MODEL,
            messages=[
                {"role": "system", "content": "You are an expert evaluator. Always respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=500,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        logger.warning(f"DeepInfra judge error: {e}")
        return {"error": str(e)}


DIMENSIONS = ["naturalidad", "relevancia", "estilo", "efectividad", "personalidad"]


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

async def evaluate_pair(
    pair: dict,
    judge_fn,
    judge_name: str,
) -> dict:
    """Evaluate a single pair with randomized A/B assignment."""
    # Randomize which is A and which is B
    stefano_is_a = random.random() < 0.5

    if stefano_is_a:
        response_a = pair["stefano_real"]
        response_b = pair["bot_response"]
    else:
        response_a = pair["bot_response"]
        response_b = pair["stefano_real"]

    # Build context string
    context_msgs = pair.get("conversation_context", [])
    context_str = ""
    if context_msgs:
        context_str = "\n".join(
            f"{'Usuario' if m['role'] == 'user' else 'Respuesta'}: {m['content']}"
            for m in context_msgs[-6:]
        )
    else:
        context_str = "(sin contexto previo)"

    # Format prompt
    prompt = BLIND_JUDGE_PROMPT.format(
        conversation_context=context_str,
        lead_message=pair["lead_message"],
        response_a=response_a,
        response_b=response_b,
    )

    # Call judge
    start_ms = time.monotonic()
    result = await judge_fn(prompt)
    elapsed_ms = int((time.monotonic() - start_ms) * 1000)

    if "error" in result:
        return {
            "conversation_id": pair["conversation_id"],
            "turn_index": pair["turn_index"],
            "judge": judge_name,
            "error": result["error"],
        }

    # Decode results back to stefano/bot
    scores_a = result.get("response_a", {})
    scores_b = result.get("response_b", {})
    guess = result.get("guess_real", "")
    confidence = result.get("confidence", "")
    reasoning = result.get("reasoning", "")

    if stefano_is_a:
        stefano_scores = scores_a
        bot_scores = scores_b
        judge_guessed_correctly = (guess.upper() == "A")
    else:
        stefano_scores = scores_b
        bot_scores = scores_a
        judge_guessed_correctly = (guess.upper() == "B")

    return {
        "conversation_id": pair["conversation_id"],
        "turn_index": pair["turn_index"],
        "judge": judge_name,
        "stefano_is_a": stefano_is_a,
        "stefano_scores": stefano_scores,
        "bot_scores": bot_scores,
        "judge_guessed_correctly": judge_guessed_correctly,
        "judge_confidence": confidence,
        "judge_reasoning": reasoning,
        "lead_category": pair.get("lead_category", ""),
        "topic": pair.get("topic", ""),
        "lead_message": pair["lead_message"],
        "stefano_real": pair["stefano_real"],
        "bot_response": pair["bot_response"],
        "latency_ms": elapsed_ms,
    }


async def run_blind_evaluation(
    pairs: list[dict],
    sample_size: int | None = None,
    max_concurrent: int = 10,
) -> dict:
    """Run blind A/B evaluation across all pairs using GPT-4o-mini."""
    # Sample if needed
    if sample_size and sample_size < len(pairs):
        pairs = random.sample(pairs, sample_size)
        logger.info(f"Sampled {len(pairs)} pairs")

    # Filter out error pairs
    pairs = [p for p in pairs if not p.get("bot_response", "").startswith("[ERROR")]

    semaphore = asyncio.Semaphore(max_concurrent)

    async def eval_one(pair):
        async with semaphore:
            return await evaluate_pair(pair, call_judge_deepinfra, "Qwen3-30B-A3B")

    print(f"\n  Running Qwen3-30B-A3B judge on {len(pairs)} pairs...")
    tasks = [eval_one(p) for p in pairs]
    results = await asyncio.gather(*tasks)

    # Compute metrics
    metrics = compute_metrics(results)

    return {
        "evaluations": results,
        "metrics": metrics,
        "config": {
            "judge": "Qwen3-30B-A3B",
            "total_pairs": len(pairs),
            "sample_size": sample_size,
        },
    }


def compute_metrics(results: list[dict]) -> dict:
    """Compute aggregate metrics from Qwen3-30B-A3B judge evaluations."""
    valid = [r for r in results if "error" not in r]
    if not valid:
        return {"Qwen3-30B-A3B": {"total_evaluated": 0, "errors": len(results)}}

    # Indistinguishability: % where judge got it WRONG
    correct_guesses = sum(1 for r in valid if r.get("judge_guessed_correctly"))
    indistinguishable = (1.0 - correct_guesses / len(valid)) * 100

    # Score gaps per dimension
    dim_gaps = defaultdict(list)
    dim_stefano = defaultdict(list)
    dim_bot = defaultdict(list)
    for r in valid:
        ss = r.get("stefano_scores", {})
        bs = r.get("bot_scores", {})
        for dim in DIMENSIONS:
            s_val = ss.get(dim, 50)
            b_val = bs.get(dim, 50)
            if isinstance(s_val, (int, float)) and isinstance(b_val, (int, float)):
                dim_gaps[dim].append(b_val - s_val)  # Positive = bot better
                dim_stefano[dim].append(s_val)
                dim_bot[dim].append(b_val)

    # Win rates (bot >= Stefano)
    win_rates = {}
    for dim in DIMENSIONS:
        gaps = dim_gaps[dim]
        if gaps:
            wins = sum(1 for g in gaps if g >= 0)
            win_rates[dim] = round(wins / len(gaps) * 100, 1)

    # Average scores
    avg_stefano = {dim: round(sum(v) / len(v), 1) for dim, v in dim_stefano.items() if v}
    avg_bot = {dim: round(sum(v) / len(v), 1) for dim, v in dim_bot.items() if v}
    avg_gap = {dim: round(sum(v) / len(v), 1) for dim, v in dim_gaps.items() if v}

    # By category
    by_category = defaultdict(lambda: {"correct": 0, "total": 0})
    for r in valid:
        cat = r.get("lead_category", "OTRO")
        by_category[cat]["total"] += 1
        if r.get("judge_guessed_correctly"):
            by_category[cat]["correct"] += 1

    cat_indistinguishable = {}
    for cat, counts in by_category.items():
        cat_indistinguishable[cat] = round(
            (1.0 - counts["correct"] / counts["total"]) * 100, 1
        ) if counts["total"] > 0 else 0

    # Confidence distribution
    conf_dist = Counter(r.get("judge_confidence", "") for r in valid)

    return {
        "Qwen3-30B-A3B": {
            "total_evaluated": len(valid),
            "errors": len(results) - len(valid),
            "indistinguishable_pct": round(indistinguishable, 1),
            "correct_guesses": correct_guesses,
            "avg_stefano_scores": avg_stefano,
            "avg_bot_scores": avg_bot,
            "avg_gap": avg_gap,
            "win_rates": win_rates,
            "by_category_indistinguishable": dict(cat_indistinguishable),
            "confidence_distribution": dict(conf_dist),
        },
    }


def print_judge_report(metrics: dict):
    """Print the blind judge evaluation report."""
    print(f"\n{'='*60}")
    print(f"  Blind A/B Judge Report (Qwen3-30B-A3B)")
    print(f"{'='*60}")

    m = metrics.get("Qwen3-30B-A3B", {})
    if not m:
        print("  No results.")
        return

    print(f"\n  Evaluated: {m['total_evaluated']} pairs ({m['errors']} errors)")
    print(f"\n  INDISTINGUISHABLE: {m['indistinguishable_pct']:.1f}%")
    print(f"  (Judge guessed correctly {m['correct_guesses']}/{m['total_evaluated']} times)")

    print(f"\n  Score comparison (Stefano vs Bot, gap):")
    print(f"  {'Dimension':20s} {'Stefano':>8s} {'Bot':>8s} {'Gap':>8s} {'Bot Win%':>8s}")
    print(f"  {'─'*52}")
    for dim in DIMENSIONS:
        s = m["avg_stefano_scores"].get(dim, 0)
        b = m["avg_bot_scores"].get(dim, 0)
        g = m["avg_gap"].get(dim, 0)
        w = m["win_rates"].get(dim, 0)
        marker = "" if abs(g) < 5 else (" <<<" if g < -5 else " >>>")
        print(f"  {dim:20s} {s:7.1f}  {b:7.1f}  {g:+7.1f}  {w:7.1f}%{marker}")

    if m.get("by_category_indistinguishable"):
        print(f"\n  Indistinguishable by category:")
        for cat, pct in sorted(m["by_category_indistinguishable"].items()):
            bar_len = int(pct / 5)
            bar = "█" * bar_len
            print(f"    {cat:20s} {pct:5.1f}% {bar}")

    if m.get("confidence_distribution"):
        print(f"\n  Judge confidence: {dict(m['confidence_distribution'])}")

    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Blind A/B Judge Evaluation")
    parser.add_argument("--input", required=True, help="Path to backtest results JSON")
    parser.add_argument("--sample", type=int, default=None, help="Sample N pairs")
    parser.add_argument("--max-concurrent", type=int, default=10, help="Max concurrent judge calls")
    parser.add_argument("--output", default=None, help="Output directory")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Load backtest results
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    pairs = data.get("pairs", [])
    if not pairs:
        print("Error: No pairs found in input file")
        sys.exit(1)

    print(f"  Loaded {len(pairs)} pairs from {input_path.name}")

    # Run evaluation
    result = asyncio.run(run_blind_evaluation(
        pairs,
        sample_size=args.sample,
        max_concurrent=args.max_concurrent,
    ))

    print_judge_report(result["metrics"])

    # Save results
    output_dir = Path(args.output) if args.output else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"judge_results_{timestamp}.json"

    output = {
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "input_file": str(input_path),
        "config": result["config"],
        "metrics": result["metrics"],
        "evaluations": result["evaluations"],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    print(f"  Saved to: {output_path}")
    print(f"\n  Next: Run failure clustering:")
    print(f"  python3.11 scripts/failure_clustering.py --input {output_path}")


if __name__ == "__main__":
    main()
