"""
Model comparison using 20 test conversations from test_set_v1.json.

Tests 3 models with the same prompt (Doc D distilled + few-shot + conversation history):
1. gemini-2.5-flash-lite (production primary)
2. Qwen/Qwen3-32B via DeepInfra (comparison)
3. gemini-2.5-flash (expensive, for comparison only)

Usage: DATABASE_URL=... GOOGLE_API_KEY=... DEEPINFRA_API_KEY=... python3 scripts/model_comparison_v1.py
"""

import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import httpx

# ── Config ──────────────────────────────────────────────────────────
MODELS = [
    {"id": "gemini-2.5-flash-lite", "provider": "gemini"},
    {"id": "Qwen/Qwen3-32B", "provider": "deepinfra"},
    {"id": "gemini-2.5-flash", "provider": "gemini"},
]

MAX_TOKENS = 150
TEMPERATURE = 0.7
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"

SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
TEST_SET_PATH = BACKEND_DIR / "tests" / "test_set_v1.json"
DOC_D_PATH = BACKEND_DIR / "data" / "personality_extractions" / "iris_bertran_v2_distilled.md"
CALIBRATION_PATH = BACKEND_DIR / "calibrations" / "iris_bertran.json"
OUTPUT_PATH = BACKEND_DIR / "tests" / "model_comparison_v1.json"


# ── LLM Calls ──────────────────────────────────────────────────────

async def call_gemini(model: str, system_prompt: str, user_message: str) -> dict:
    api_key = os.environ["GOOGLE_API_KEY"]
    url = f"{GEMINI_API_URL}/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": user_message}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {"maxOutputTokens": MAX_TOKENS, "temperature": TEMPERATURE},
    }
    start = time.monotonic()
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


async def call_deepinfra(model: str, system_prompt: str, user_message: str) -> dict:
    from openai import AsyncOpenAI
    api_key = os.environ["DEEPINFRA_API_KEY"]
    client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepinfra.com/v1/openai")
    start = time.monotonic()
    response = await asyncio.wait_for(
        client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        ),
        timeout=20.0,
    )
    latency_ms = int((time.monotonic() - start) * 1000)
    content = (response.choices[0].message.content or "").strip()
    usage = response.usage
    return {
        "content": content,
        "latency_ms": latency_ms,
        "tokens_in": usage.prompt_tokens if usage else 0,
        "tokens_out": usage.completion_tokens if usage else 0,
    }


async def call_model(model_id: str, provider: str, system_prompt: str, user_msg: str) -> dict:
    try:
        if provider == "gemini":
            return await call_gemini(model_id, system_prompt, user_msg)
        elif provider == "deepinfra":
            return await call_deepinfra(model_id, system_prompt, user_msg)
        else:
            return {"content": f"[ERROR: unknown provider {provider}]", "latency_ms": 0, "tokens_in": 0, "tokens_out": 0}
    except Exception as e:
        return {"content": f"[ERROR: {e}]", "latency_ms": 0, "tokens_in": 0, "tokens_out": 0}


# ── Prompt Building ────────────────────────────────────────────────

def load_system_prompt() -> str:
    """Load Doc D distilled system prompt."""
    content = DOC_D_PATH.read_text(encoding="utf-8")
    # Extract the system prompt between first ``` and closing ```
    import re
    match = re.search(r"## 4\.1 SYSTEM PROMPT[^\n]*\n```\n(.*?)```", content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return content


def load_few_shot(max_examples: int = 10) -> str:
    """Load few-shot examples from calibration file."""
    if not CALIBRATION_PATH.exists():
        return ""
    cal = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
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


def build_user_prompt(conv: dict) -> str:
    """Build user prompt from conversation turns (history + last message)."""
    turns = conv["turns"]

    # Find the ground truth timestamp — everything before that is context
    gt_ts = conv.get("ground_truth_timestamp", "")

    # Build history from all turns before ground_truth
    history_lines = []
    last_lead_msg = ""
    for turn in turns:
        ts = turn.get("timestamp", "")
        if gt_ts and ts >= gt_ts:
            break
        role_label = "Iris" if turn["role"] == "iris" else "Follower"
        history_lines.append(f"{role_label}: {turn['content']}")
        if turn["role"] == "lead":
            last_lead_msg = turn["content"]

    if not last_lead_msg:
        # Fallback: use last lead message in turns
        for turn in reversed(turns):
            if turn["role"] == "lead":
                last_lead_msg = turn["content"]
                break

    parts = []
    if history_lines:
        parts.append("Conversacion reciente:\n" + "\n".join(history_lines[-10:]))
    parts.append(f"Mensaje actual:\n<user_message>\n{last_lead_msg}\n</user_message>")
    return "\n\n".join(parts)


# ── Scoring ─────────────────────────────────────────────────────────

def score_response(generated: str, ground_truth: str) -> float:
    """SequenceMatcher similarity between generated and ground truth."""
    return SequenceMatcher(None, generated.lower(), ground_truth.lower()).ratio()


# ── Main ────────────────────────────────────────────────────────────

async def main():
    # Load test data
    test_data = json.loads(TEST_SET_PATH.read_text(encoding="utf-8"))
    conversations = test_data["conversations"]
    print(f"Loaded {len(conversations)} conversations from test_set_v1.json")

    # Load prompts
    system_prompt_base = load_system_prompt()
    few_shot = load_few_shot(max_examples=10)
    system_prompt = system_prompt_base
    if few_shot:
        system_prompt = system_prompt_base + "\n\n" + few_shot
    print(f"System prompt: {len(system_prompt)} chars (~{len(system_prompt)//4} tokens)")

    results = {
        "version": "v1",
        "created_at": datetime.now().isoformat(),
        "models": [m["id"] for m in MODELS],
        "test_set": "test_set_v1.json",
        "system_prompt_chars": len(system_prompt),
        "few_shot_examples": 10,
        "conversations": [],
    }

    # Per-model aggregates
    model_scores = {m["id"]: [] for m in MODELS}
    model_latencies = {m["id"]: [] for m in MODELS}

    for i, conv in enumerate(conversations):
        conv_id = conv["id"]
        ground_truth = conv["ground_truth"]
        user_prompt = build_user_prompt(conv)

        print(f"\n[{i+1}/{len(conversations)}] {conv_id} ({conv['type']}, {conv['language']})")
        print(f"  GT: {ground_truth[:80]}...")

        conv_result = {
            "id": conv_id,
            "type": conv["type"],
            "language": conv["language"],
            "ground_truth": ground_truth,
            "models": {},
        }

        for model_cfg in MODELS:
            mid = model_cfg["id"]
            provider = model_cfg["provider"]

            result = await call_model(mid, provider, system_prompt, user_prompt)
            sc = score_response(result["content"], ground_truth)

            conv_result["models"][mid] = {
                "response": result["content"],
                "score": round(sc, 4),
                "latency_ms": result["latency_ms"],
                "tokens_in": result["tokens_in"],
                "tokens_out": result["tokens_out"],
            }

            model_scores[mid].append(sc)
            model_latencies[mid].append(result["latency_ms"])

            status = "OK" if "[ERROR" not in result["content"] else "ERR"
            print(f"  {mid:25s} | {sc:.1%} | {result['latency_ms']:4d}ms | {status} | {result['content'][:60]}")

            # Small delay between calls to avoid rate limits
            await asyncio.sleep(0.3)

        results["conversations"].append(conv_result)

    # Summary
    print("\n" + "=" * 70)
    print(f"{'Model':25s} | {'Score':>6s} | {'Latency':>8s} | {'Min':>5s} | {'Max':>5s}")
    print("-" * 70)

    summary = {}
    for model_cfg in MODELS:
        mid = model_cfg["id"]
        scores = model_scores[mid]
        latencies = model_latencies[mid]
        avg_score = sum(scores) / len(scores) if scores else 0
        avg_lat = sum(latencies) / len(latencies) if latencies else 0
        min_sc = min(scores) if scores else 0
        max_sc = max(scores) if scores else 0

        print(f"{mid:25s} | {avg_score:5.1%} | {avg_lat:6.0f}ms | {min_sc:4.1%} | {max_sc:4.1%}")

        summary[mid] = {
            "avg_score": round(avg_score, 4),
            "avg_latency_ms": round(avg_lat),
            "min_score": round(min_sc, 4),
            "max_score": round(max_sc, 4),
            "total_conversations": len(scores),
        }

    print("=" * 70)

    results["summary"] = summary

    # Save
    OUTPUT_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
