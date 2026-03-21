"""
DeepSeek V3.2 comparison against 20 test conversations.
Reuses same prompt structure as model_comparison_v1.py.

Usage: python3 scripts/deepseek_comparison.py
"""

import json
import os
import random
import re
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from openai import OpenAI

SCRIPT_DIR = Path(__file__).parent
BACKEND_DIR = SCRIPT_DIR.parent
TEST_SET_PATH = BACKEND_DIR / "tests" / "test_set_v1.json"
DOC_D_PATH = BACKEND_DIR / "data" / "personality_extractions" / "iris_bertran_v2_distilled.md"
CALIBRATION_PATH = BACKEND_DIR / "calibrations" / "iris_bertran.json"
OUTPUT_PATH = BACKEND_DIR / "tests" / "deepseek_comparison.json"

DEEPSEEK_API_KEY = "sk-64dec7b4a2c9424e91f63e942bad971c"
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

MAX_TOKENS = 150
TEMPERATURE = 0.7


def load_system_prompt() -> str:
    content = DOC_D_PATH.read_text(encoding="utf-8")
    match = re.search(r"## 4\.1 SYSTEM PROMPT[^\n]*\n```\n(.*?)```", content, re.DOTALL)
    return match.group(1).strip() if match else content


def load_few_shot(max_examples: int = 10) -> str:
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
    turns = conv["turns"]
    gt_ts = conv.get("ground_truth_timestamp", "")
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
        for turn in reversed(turns):
            if turn["role"] == "lead":
                last_lead_msg = turn["content"]
                break
    parts = []
    if history_lines:
        parts.append("Conversacion reciente:\n" + "\n".join(history_lines[-10:]))
    parts.append(f"Mensaje actual:\n<user_message>\n{last_lead_msg}\n</user_message>")
    return "\n\n".join(parts)


def score_response(generated: str, ground_truth: str) -> float:
    return SequenceMatcher(None, generated.lower(), ground_truth.lower()).ratio()


def main():
    test_data = json.loads(TEST_SET_PATH.read_text(encoding="utf-8"))
    conversations = test_data["conversations"]
    print(f"Loaded {len(conversations)} conversations")

    system_prompt_base = load_system_prompt()
    few_shot = load_few_shot(max_examples=10)
    system_prompt = system_prompt_base + "\n\n" + few_shot if few_shot else system_prompt_base
    print(f"System prompt: {len(system_prompt)} chars (~{len(system_prompt)//4} tokens)")

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

    results = {
        "version": "v1",
        "created_at": datetime.now().isoformat(),
        "model": DEEPSEEK_MODEL,
        "baselines": {
            "gpt-4o-mini": {"avg_score": 0.289, "avg_latency_ms": 1124},
            "gemini-2.5-flash-lite": {"avg_score": 0.233, "avg_latency_ms": 604},
            "gemini-2.5-flash": {"avg_score": 0.221, "avg_latency_ms": 1202},
        },
        "system_prompt_chars": len(system_prompt),
        "few_shot_examples": 10,
        "conversations": [],
    }

    scores = []
    latencies = []

    for i, conv in enumerate(conversations):
        conv_id = conv["id"]
        ground_truth = conv["ground_truth"]
        user_prompt = build_user_prompt(conv)

        print(f"\n[{i+1}/{len(conversations)}] {conv_id} ({conv['type']}, {conv['language']})")
        print(f"  GT: {ground_truth[:80]}...")

        start = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=MAX_TOKENS,
                temperature=TEMPERATURE,
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            content = (response.choices[0].message.content or "").strip()
            usage = response.usage
            tokens_in = usage.prompt_tokens if usage else 0
            tokens_out = usage.completion_tokens if usage else 0
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            content = f"[ERROR: {e}]"
            tokens_in = tokens_out = 0

        sc = score_response(content, ground_truth)
        scores.append(sc)
        latencies.append(latency_ms)

        results["conversations"].append({
            "id": conv_id,
            "type": conv["type"],
            "language": conv["language"],
            "ground_truth": ground_truth,
            "response": content,
            "score": round(sc, 4),
            "latency_ms": latency_ms,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
        })

        status = "OK" if "[ERROR" not in content else "ERR"
        print(f"  {DEEPSEEK_MODEL:25s} | {sc:.1%} | {latency_ms:4d}ms | {status} | {content[:70]}")

    avg_score = sum(scores) / len(scores) if scores else 0
    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    min_sc = min(scores) if scores else 0
    max_sc = max(scores) if scores else 0

    results["summary"] = {
        "avg_score": round(avg_score, 4),
        "avg_latency_ms": round(avg_lat),
        "min_score": round(min_sc, 4),
        "max_score": round(max_sc, 4),
        "total_conversations": len(scores),
    }

    print("\n" + "=" * 70)
    print(f"{'Model':25s} | {'Score':>6s} | {'Latency':>8s} | {'Min':>5s} | {'Max':>5s}")
    print("-" * 70)
    print(f"{'gpt-4o-mini':25s} | {28.9:5.1f}% | {'1124ms':>8s} |       |      ")
    print(f"{'gemini-2.5-flash-lite':25s} | {23.3:5.1f}% | {'604ms':>8s} |       |      ")
    print(f"{'gemini-2.5-flash':25s} | {22.1:5.1f}% | {'1202ms':>8s} |       |      ")
    print(f"{DEEPSEEK_MODEL:25s} | {avg_score*100:5.1f}% | {f'{avg_lat:.0f}ms':>8s} | {min_sc*100:4.1f}% | {max_sc*100:4.1f}%")
    print("=" * 70)

    OUTPUT_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nResults saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
