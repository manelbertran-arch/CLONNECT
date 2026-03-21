"""
Model comparison test: run 20 test conversations against multiple LLMs
using the same optimized prompt (Doc D distilled + 10 few-shot examples).

Usage: cd backend && python3 tests/model_comparison_v1.py
Requires: GOOGLE_API_KEY, OPENAI_API_KEY in .env
"""

import asyncio
import json
import os
import random
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

# Fixed seed for deterministic few-shot sampling across test runs.
# Production code (calibration_loader.py) uses unseeded random for variety.
random.seed(42)

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ---------------------------------------------------------------------------
# Load test set + calibration + Doc D
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent.parent

with open(BASE / "tests" / "test_set_v1.json") as f:
    TEST_SET = json.load(f)

with open(BASE / "calibrations" / "iris_bertran.json") as f:
    CALIBRATION = json.load(f)

with open(BASE / "data" / "personality_extractions" / "iris_bertran_v2_distilled.md") as f:
    DOC_D = f.read()

# ---------------------------------------------------------------------------
# Build few-shot section (same logic as calibration_loader.get_few_shot_section)
# ---------------------------------------------------------------------------
def build_few_shot(cal: dict, max_examples: int = 10) -> str:
    examples = cal.get("few_shot_examples", [])
    if not examples:
        return ""
    k = min(max_examples, len(examples))
    selected = random.sample(examples, k)
    lines = ["=== EJEMPLOS REALES DE COMO RESPONDES ==="]
    for ex in selected:
        user_msg = ex.get("user_message", "")
        response = ex.get("response", "")
        if user_msg and response:
            lines.append(f"Follower: {user_msg}")
            lines.append(f"Tu: {response}")
            lines.append("")
    lines.append("Responde de forma breve y natural, como en los ejemplos.")
    lines.append("=== FIN EJEMPLOS ===")
    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Build prompt for a conversation
# ---------------------------------------------------------------------------
def build_prompt(conv: dict) -> tuple[str, str]:
    """Returns (system_prompt, user_message)."""
    few_shot = build_few_shot(CALIBRATION, max_examples=10)

    # Build conversation history
    turns = conv["turns"]
    history_lines = []
    for t in turns[:-1]:  # all but last (last is the lead message we respond to)
        role_label = "Iris" if t["role"] == "iris" else "Follower"
        history_lines.append(f"{role_label}: {t['content']}")

    last_turn = turns[-1]
    user_message = last_turn["content"]

    # Context info
    lead_name = conv.get("lead_name", "Follower")
    lead_status = conv.get("lead_status", "unknown")
    conv_type = conv.get("type", "casual")
    language = conv.get("language", "es")

    system_prompt = f"""{DOC_D}

{few_shot}

=== CONTEXTO DE LA CONVERSACION ===
Lead: {lead_name}
Estado: {lead_status}
Tipo: {conv_type}
Idioma detectado: {language}

Historial reciente:
{chr(10).join(history_lines)}
=== FIN CONTEXTO ===

Responde al ultimo mensaje del follower como Iris. Un solo mensaje corto."""

    return system_prompt, user_message

# ---------------------------------------------------------------------------
# Model callers
# ---------------------------------------------------------------------------

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"

async def call_gemini(model: str, system_prompt: str, user_message: str) -> dict:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_API_KEY not set"}

    url = f"{GEMINI_API_URL}/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": user_message}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "maxOutputTokens": 150,
            "temperature": 0.7,
        },
    }

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload)
            latency_ms = int((time.monotonic() - start) * 1000)
            resp.raise_for_status()
            data = resp.json()

            content = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            usage = data.get("usageMetadata", {})
            return {
                "content": content,
                "latency_ms": latency_ms,
                "tokens_in": usage.get("promptTokenCount", 0),
                "tokens_out": usage.get("candidatesTokenCount", 0),
            }
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {"error": str(e), "latency_ms": latency_ms}


async def call_openai(model: str, system_prompt: str, user_message: str) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"error": "OPENAI_API_KEY not set"}

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 150,
        "temperature": 0.7,
    }

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            latency_ms = int((time.monotonic() - start) * 1000)
            resp.raise_for_status()
            data = resp.json()

            content = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {})
            return {
                "content": content,
                "latency_ms": latency_ms,
                "tokens_in": usage.get("prompt_tokens", 0),
                "tokens_out": usage.get("completion_tokens", 0),
            }
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {"error": str(e), "latency_ms": latency_ms}


async def call_deepseek(system_prompt: str, user_message: str) -> dict:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return {"error": "DEEPSEEK_API_KEY not set"}

    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 150,
        "temperature": 0.7,
    }

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            latency_ms = int((time.monotonic() - start) * 1000)
            resp.raise_for_status()
            data = resp.json()

            content = data["choices"][0]["message"]["content"].strip()
            usage = data.get("usage", {})
            return {
                "content": content,
                "latency_ms": latency_ms,
                "tokens_in": usage.get("prompt_tokens", 0),
                "tokens_out": usage.get("completion_tokens", 0),
            }
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {"error": str(e), "latency_ms": latency_ms}


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------
MODELS = {
    "gemini-2.5-flash-lite": lambda sp, um: call_gemini("gemini-2.5-flash-lite", sp, um),
    "gemini-2.5-flash": lambda sp, um: call_gemini("gemini-2.5-flash", sp, um),
    "gpt-4o-mini": lambda sp, um: call_openai("gpt-4o-mini", sp, um),
    "deepseek-v3.2": lambda sp, um: call_deepseek(sp, um),
}

# Pricing per 1M tokens (input, output) in USD
PRICING = {
    "gemini-2.5-flash-lite": (0.075, 0.30),
    "gemini-2.5-flash": (0.15, 0.60),
    "gpt-4o-mini": (0.15, 0.60),
    "deepseek-v3.2": (0.27, 1.10),
}

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def score_response(generated: str, ground_truth: str) -> float:
    return SequenceMatcher(None, generated.lower(), ground_truth.lower()).ratio()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def run_comparison():
    conversations = TEST_SET["conversations"]
    results = {
        "date": "2026-03-21",
        "prompt_version": "doc_d_v2_distilled + 10_fewshot + calibration_v1",
        "models": {},
        "conversations": [],
    }

    # Check which models are available
    available_models = {}
    for name, caller in MODELS.items():
        if name.startswith("gemini") and not os.getenv("GOOGLE_API_KEY"):
            print(f"  SKIP {name}: no GOOGLE_API_KEY")
            continue
        if name == "gpt-4o-mini" and not os.getenv("OPENAI_API_KEY"):
            print(f"  SKIP {name}: no OPENAI_API_KEY")
            continue
        if name == "deepseek-v3.2" and not os.getenv("DEEPSEEK_API_KEY"):
            print(f"  SKIP {name}: no DEEPSEEK_API_KEY")
            continue
        available_models[name] = caller

    print(f"Models: {list(available_models.keys())}")
    print(f"Conversations: {len(conversations)}")
    print()

    for i, conv in enumerate(conversations):
        conv_id = conv["id"]
        ground_truth = conv.get("ground_truth", "")
        system_prompt, user_message = build_prompt(conv)

        conv_result = {
            "id": conv_id,
            "type": conv.get("type"),
            "language": conv.get("language"),
            "ground_truth": ground_truth,
            "user_message": user_message,
            "responses": {},
        }

        # Call all models in parallel for this conversation
        tasks = {}
        for model_name, caller in available_models.items():
            tasks[model_name] = caller(system_prompt, user_message)

        model_results = {}
        for model_name, coro in tasks.items():
            model_results[model_name] = await coro

        for model_name, result in model_results.items():
            if "error" in result:
                conv_result["responses"][model_name] = {
                    "error": result["error"],
                    "latency_ms": result.get("latency_ms", 0),
                }
                status = f"ERR: {result['error'][:40]}"
            else:
                sc = score_response(result["content"], ground_truth)
                conv_result["responses"][model_name] = {
                    "response": result["content"],
                    "score": round(sc, 4),
                    "latency_ms": result["latency_ms"],
                    "tokens_in": result.get("tokens_in", 0),
                    "tokens_out": result.get("tokens_out", 0),
                }
                status = f"score={sc:.1%} lat={result['latency_ms']}ms"

            print(f"  [{conv_id}] {model_name:25s} {status}")

        results["conversations"].append(conv_result)
        print(f"  [{conv_id}] done ({i+1}/{len(conversations)})")

        # Small delay to avoid rate limits between conversations
        if i < len(conversations) - 1:
            await asyncio.sleep(0.5)

    # ---------------------------------------------------------------------------
    # Aggregate stats
    # ---------------------------------------------------------------------------
    for model_name in available_models:
        scores = []
        latencies = []
        total_tokens_in = 0
        total_tokens_out = 0
        by_type = {}
        by_language = {}
        errors = 0

        for conv_res in results["conversations"]:
            resp = conv_res["responses"].get(model_name, {})
            if "error" in resp:
                errors += 1
                continue

            sc = resp["score"]
            lat = resp["latency_ms"]
            scores.append(sc)
            latencies.append(lat)
            total_tokens_in += resp.get("tokens_in", 0)
            total_tokens_out += resp.get("tokens_out", 0)

            ctype = conv_res["type"]
            clang = conv_res["language"]
            by_type.setdefault(ctype, []).append(sc)
            by_language.setdefault(clang, []).append(sc)

        avg_score = sum(scores) / len(scores) if scores else 0
        avg_latency = int(sum(latencies) / len(latencies)) if latencies else 0
        n = len(scores)

        # Cost calculation
        price_in, price_out = PRICING.get(model_name, (0, 0))
        total_cost = (total_tokens_in * price_in + total_tokens_out * price_out) / 1_000_000
        cost_per_msg = total_cost / n if n > 0 else 0

        results["models"][model_name] = {
            "overall_score": round(avg_score, 4),
            "avg_latency_ms": avg_latency,
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out,
            "total_cost_usd": round(total_cost, 6),
            "cost_per_msg_usd": round(cost_per_msg, 6),
            "n_success": n,
            "n_errors": errors,
            "by_type": {k: round(sum(v)/len(v), 4) for k, v in sorted(by_type.items())},
            "by_language": {k: round(sum(v)/len(v), 4) for k, v in sorted(by_language.items())},
        }

    # Save results
    out_path = BASE / "tests" / "model_comparison_v1.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {out_path}")

    # ---------------------------------------------------------------------------
    # Print summary table
    # ---------------------------------------------------------------------------
    print("\n" + "=" * 72)
    print(f"{'Model':<25s} | {'Score':>6s} | {'Latency':>8s} | {'Cost/msg':>10s} | {'N':>3s}")
    print("-" * 72)
    for model_name in available_models:
        m = results["models"].get(model_name, {})
        sc = m.get("overall_score", 0)
        lat = m.get("avg_latency_ms", 0)
        cost = m.get("cost_per_msg_usd", 0)
        n = m.get("n_success", 0)
        print(f"{model_name:<25s} | {sc:5.1%} | {lat:6d}ms | ${cost:.5f} | {n:>3d}")
    print("=" * 72)

    # By type breakdown
    print(f"\n{'Type':<18s}", end="")
    for mn in available_models:
        print(f" | {mn:>12s}", end="")
    print()
    print("-" * (18 + 15 * len(available_models)))
    all_types = sorted(set(c["type"] for c in results["conversations"]))
    for t in all_types:
        print(f"{t:<18s}", end="")
        for mn in available_models:
            bt = results["models"].get(mn, {}).get("by_type", {})
            val = bt.get(t, 0)
            print(f" | {val:11.1%}", end="")
        print()

    # By language breakdown
    print(f"\n{'Language':<18s}", end="")
    for mn in available_models:
        print(f" | {mn:>12s}", end="")
    print()
    print("-" * (18 + 15 * len(available_models)))
    all_langs = sorted(set(c["language"] for c in results["conversations"]))
    for lang in all_langs:
        print(f"{lang:<18s}", end="")
        for mn in available_models:
            bl = results["models"].get(mn, {}).get("by_language", {})
            val = bl.get(lang, 0)
            print(f" | {val:11.1%}", end="")
        print()


if __name__ == "__main__":
    asyncio.run(run_comparison())
