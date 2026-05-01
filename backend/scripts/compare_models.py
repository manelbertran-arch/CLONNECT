#!/usr/bin/env python3
"""
Compare model responses side-by-side for 10 canonical messages.

Generates responses from multiple models/providers for the same prompts,
outputs a markdown table for visual comparison + JSON for analysis.

Uses the production system prompt (Doc D v2 + few-shot examples).

Usage:
    # Compare SFT 8B vs 32B on Together:
    python scripts/compare_models.py \\
        --providers together,together \\
        --models manelbertran_c647/Qwen3-8B-iris-sft-8b-v1-877e513f,manelbertran_c647/Qwen3-32B-iris-sft-32b-v1-61ee8d5b \\
        --labels 8B-SFT,32B-SFT

    # Compare tuned vs Gemini baseline:
    python scripts/compare_models.py \\
        --providers together,gemini \\
        --models manelbertran_c647/Qwen3-8B-iris-sft-8b-v1-877e513f,gemini-2.0-flash-lite \\
        --labels Qwen3-8B-tuned,Gemini-flash

    # Single model quick test:
    python scripts/compare_models.py \\
        --providers together \\
        --models manelbertran_c647/Qwen3-8B-iris-sft-8b-v1-877e513f
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("compare_models")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

# ═══════════════════════════════════════════════════════════════════════════════
# 10 CANONICAL TEST MESSAGES
# ═══════════════════════════════════════════════════════════════════════════════

CANONICAL_MESSAGES = [
    "Hola! Me interesaría saber los precios de las clases",
    "Ei quina foto mes bonica",
    "No sé, es un poco caro para mí",
    "Bon dia Iris!! Avui tens classe?",
    "🤣🤣",
    "Hola guapa! Quiero apuntarme a barre",
    "Gràcies per tot, ets la millor!",
    "Oye y los horarios? Trabajo hasta las 6",
    "[audio message]",
    "Ya pero es que no sé si me va a gustar",
]


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT (production — Doc D v2 + few-shot)
# ═══════════════════════════════════════════════════════════════════════════════

def build_system_prompt(message: str) -> str:
    """Build production system prompt with Doc D + few-shot examples."""
    parts = []

    # Load Doc D v2
    doc_d_path = REPO_ROOT / "data" / "personality_extractions" / "iris_bertran_v2_distilled.md"
    if doc_d_path.exists():
        with open(doc_d_path, encoding="utf-8") as f:
            content = f.read()
        # Extract content between ``` markers (the system prompt section)
        if "```" in content:
            blocks = content.split("```")
            if len(blocks) >= 2:
                parts.append(blocks[1].strip())
            # Also include blacklist section if present
            for block in blocks[2:]:
                if "BLACKLIST" in block or "PROHIBIDAS" in block or "PARAMETROS" in block:
                    parts.append(block.strip())
        else:
            parts.append(content)
    else:
        # Fallback minimal prompt
        parts.append(
            "Eres Iris Bertran. Monitora de fitness en Dinamic Sport Gym, Igualada (Barcelona). "
            "Bilingue catalan-castellano, mensajes ultra-breves, directa, informal, tuteo siempre. "
            "NO eres asistente virtual. Respondes DMs como persona real entre clases."
        )

    # Load few-shot examples from calibration
    try:
        from services.calibration_loader import get_few_shot_section, load_calibration, _cache
        _cache.clear()
        cal = load_calibration("iris_bertran")
        if cal:
            fewshot = get_few_shot_section(cal, max_examples=5, current_message=message)
            if fewshot:
                parts.append(fewshot)
    except Exception as e:
        logger.debug("Could not load few-shot: %s", e)

    return "\n\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# PROVIDERS
# ═══════════════════════════════════════════════════════════════════════════════

def call_together(model: str, system_prompt: str, message: str, api_key: str) -> str:
    """Call Together AI API."""
    import requests

    # Append /no-think for Qwen3 models
    sp = system_prompt
    if "qwen" in model.lower() or "Qwen" in model:
        sp = sp + "\n\n/no-think"

    resp = requests.post(
        "https://api.together.xyz/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": sp},
                {"role": "user", "content": message},
            ],
            "temperature": 0.7,
            "max_tokens": 150,
            "stop": ["\n\n"],
        },
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    # Strip <think>...</think> blocks from Qwen3 if /no-think didn't work
    if "<think>" in content:
        import re
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return content


def call_fireworks(model: str, system_prompt: str, message: str, api_key: str) -> str:
    """Call Fireworks AI API."""
    import requests

    sp = system_prompt
    if "qwen" in model.lower():
        sp = sp + "\n\n/no-think"

    resp = requests.post(
        "https://api.fireworks.ai/inference/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": sp},
                {"role": "user", "content": message},
            ],
            "temperature": 0.7,
            "max_tokens": 150,
        },
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if "<think>" in content:
        import re
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return content


def call_deepinfra(model: str, system_prompt: str, message: str, api_key: str) -> str:
    """Call DeepInfra API."""
    import requests

    sp = system_prompt
    if "qwen" in model.lower():
        sp = sp + "\n\n/no-think"

    resp = requests.post(
        "https://api.deepinfra.com/v1/openai/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": sp},
                {"role": "user", "content": message},
            ],
            "temperature": 0.7,
            "max_tokens": 150,
        },
        timeout=30,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"].strip()
    if "<think>" in content:
        import re
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return content


def call_gemini(model: str, system_prompt: str, message: str, api_key: str) -> str:
    """Call Google Gemini API."""
    import requests

    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        json={
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"parts": [{"text": message}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 150},
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    candidates = data.get("candidates", [])
    if candidates:
        parts = candidates[0].get("content", {}).get("parts", [])
        if parts:
            return parts[0].get("text", "").strip()
    return "[empty response]"


PROVIDER_FNS = {
    "together": call_together,
    "fireworks": call_fireworks,
    "deepinfra": call_deepinfra,
    "gemini": call_gemini,
}

API_KEY_ENVS = {
    "together": "TOGETHER_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "deepinfra": "DEEPINFRA_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT
# ═══════════════════════════════════════════════════════════════════════════════

def format_markdown_table(messages: List[str], labels: List[str], results: dict) -> str:
    """Format results as a markdown table."""
    lines = []

    # Header
    header = "| # | Mensaje | " + " | ".join(labels) + " |"
    separator = "|---|---|" + "|".join(["---"] * len(labels)) + "|"
    lines.append(header)
    lines.append(separator)

    # Rows
    for i, msg in enumerate(messages):
        msg_short = msg[:40] + ("..." if len(msg) > 40 else "")
        cells = []
        for label in labels:
            resp = results.get((i, label), "[error]")
            resp_clean = resp.replace("|", "\\|").replace("\n", " ")[:60]
            cells.append(resp_clean)
        row = f"| {i + 1} | {msg_short} | " + " | ".join(cells) + " |"
        lines.append(row)

    return "\n".join(lines)


def format_detailed_output(messages: List[str], labels: List[str], results: dict) -> str:
    """Format results as detailed per-message comparison."""
    lines = []
    for i, msg in enumerate(messages):
        lines.append(f"\n{'=' * 60}")
        lines.append(f"MSG {i + 1}: {msg}")
        lines.append("=" * 60)
        for label in labels:
            resp = results.get((i, label), "[error]")
            lines.append(f"  {label:20s} → {resp}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    from dotenv import load_dotenv
    load_dotenv(REPO_ROOT / ".env")

    parser = argparse.ArgumentParser(
        description="Compare model responses side-by-side for canonical messages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Compare SFT 8B vs 32B:
  python scripts/compare_models.py \\
      --providers together,together \\
      --models Qwen3-8B-...,Qwen3-32B-... \\
      --labels 8B-SFT,32B-SFT

  # Compare tuned model vs Gemini baseline:
  python scripts/compare_models.py \\
      --providers together,gemini \\
      --models manelbertran_c647/Qwen3-8B-...,gemini-2.0-flash-lite \\
      --labels Tuned-8B,Gemini-baseline

  # Single model test:
  python scripts/compare_models.py \\
      --providers gemini \\
      --models gemini-2.0-flash-lite \\
      --labels Gemini
        """,
    )
    parser.add_argument("--providers", required=True,
                        help="Comma-separated providers: together,fireworks,deepinfra,gemini")
    parser.add_argument("--models", required=True,
                        help="Comma-separated model IDs (one per provider)")
    parser.add_argument("--labels", default=None,
                        help="Comma-separated display labels (default: model names)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output JSON path (default: tests/compare_<timestamp>.json)")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--runs", type=int, default=1,
                        help="Number of runs per message per model (default: 1)")
    args = parser.parse_args()

    providers = args.providers.split(",")
    models = args.models.split(",")
    labels = args.labels.split(",") if args.labels else [m.split("/")[-1][:25] for m in models]

    if len(providers) != len(models):
        logger.error("Number of providers (%d) must match models (%d)", len(providers), len(models))
        sys.exit(1)
    if len(labels) != len(models):
        logger.error("Number of labels (%d) must match models (%d)", len(labels), len(models))
        sys.exit(1)

    # Validate providers
    for p in providers:
        if p not in PROVIDER_FNS:
            logger.error("Unknown provider: %s (valid: %s)", p, ", ".join(PROVIDER_FNS))
            sys.exit(1)

    # Check API keys
    api_keys = {}
    for p in set(providers):
        env_var = API_KEY_ENVS[p]
        key = os.environ.get(env_var, "")
        if not key:
            logger.error("Missing %s environment variable", env_var)
            sys.exit(1)
        api_keys[p] = key

    logger.info("Comparing %d models across %d messages", len(models), len(CANONICAL_MESSAGES))
    for label, provider, model in zip(labels, providers, models):
        logger.info("  %s: %s/%s", label, provider, model.split("/")[-1][:40])

    # Generate responses
    results = {}  # (msg_idx, label) -> response
    all_responses = []  # For JSON output

    for i, msg in enumerate(CANONICAL_MESSAGES):
        logger.info("\n[%d/%d] %s", i + 1, len(CANONICAL_MESSAGES), msg[:50])
        system_prompt = build_system_prompt(msg)

        for label, provider, model in zip(labels, providers, models):
            fn = PROVIDER_FNS[provider]
            key = api_keys[provider]

            responses_for_runs = []
            for run in range(args.runs):
                try:
                    resp = fn(model, system_prompt, msg, key)
                    responses_for_runs.append(resp)
                    logger.info("  %s → %s", label, resp[:60])
                except Exception as e:
                    resp = f"[ERROR: {e}]"
                    responses_for_runs.append(resp)
                    logger.warning("  %s → ERROR: %s", label, e)
                time.sleep(0.3)

            # Use first run for table, store all for JSON
            results[(i, label)] = responses_for_runs[0]
            all_responses.append({
                "message_idx": i,
                "message": msg,
                "label": label,
                "provider": provider,
                "model": model,
                "responses": responses_for_runs,
                "response_lengths": [len(r) for r in responses_for_runs],
            })

    # Output markdown table
    table = format_markdown_table(CANONICAL_MESSAGES, labels, results)
    detailed = format_detailed_output(CANONICAL_MESSAGES, labels, results)

    print("\n" + table)
    print(detailed)

    # Save JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_path = args.output or f"tests/compare_{timestamp}.json"
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "models": [
            {"label": l, "provider": p, "model": m}
            for l, p, m in zip(labels, providers, models)
        ],
        "messages": CANONICAL_MESSAGES,
        "responses": all_responses,
        "markdown_table": table,
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    logger.info("\nSaved to %s", output_path)

    # Summary stats
    print("\n" + "=" * 60)
    print("RESPONSE LENGTH STATS")
    print("=" * 60)
    for label in labels:
        lengths = [len(results.get((i, label), "")) for i in range(len(CANONICAL_MESSAGES))]
        avg_len = sum(lengths) / max(len(lengths), 1)
        print(f"  {label:20s}  avg={avg_len:.0f} chars  min={min(lengths)}  max={max(lengths)}")


if __name__ == "__main__":
    main()
