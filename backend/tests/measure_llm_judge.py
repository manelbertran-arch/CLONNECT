"""
LLM-as-Judge Measurement Script — Primary Clone Quality Metric

Runs the production DM pipeline (or an external provider) on test conversations,
then evaluates each response with GPT-4o-mini as judge across 6 dimensions.

SequenceMatcher is included for backward-compatible tracking but LLM-Judge
is the primary metric (SM has a ~30% ceiling and penalizes synonyms).

Usage:
    # Default: production pipeline (gemini)
    railway run python3 tests/measure_llm_judge.py
    railway run python3 tests/measure_llm_judge.py --output tests/my_run.json
    railway run python3 tests/measure_llm_judge.py --test-set tests/test_set_v2.json

    # External provider: Together AI, Fireworks, DeepInfra
    python3 tests/measure_llm_judge.py \\
      --provider together --model Qwen/Qwen3-32B \\
      --test-set tests/test_set_v2.json -o tests/score_qwen32b_v1.json

    python3 tests/measure_llm_judge.py \\
      --provider deepinfra --model Qwen/Qwen3-32B \\
      -o tests/score_deepinfra.json

    # Judge-only: re-evaluate existing results
    python3 tests/measure_llm_judge.py --judge-only tests/baseline_v3_final.json

The --provider flag selects the model provider (gemini, together, fireworks, deepinfra).
The --model flag specifies the exact model ID for external providers.
The --limit flag restricts the number of conversations to evaluate.
The --judge-only flag skips the pipeline run and evaluates an existing
baseline file (must contain conversations[].bot_response).
"""

import asyncio
import json
import logging
import os
import random
import re
import statistics
import sys
import time
from datetime import date

# Fixed seed for deterministic few-shot sampling across test runs.
# Production code (calibration_loader.py) uses unseeded random for variety.
random.seed(42)

from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add repo root to path so imports resolve correctly
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("measure_llm_judge")
logger.setLevel(logging.INFO)

CREATOR_ID = "iris_bertran"
TEST_SET_PATH = REPO_ROOT / "tests" / "test_set_v2.json"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "tests" / "llm_judge_latest.json"

# Reference scores for delta reporting
BASELINE_V1_SM = 28.9
BASELINE_V1_JUDGE = 3.5
BASELINE_V3_SM = 34.2
BASELINE_V3_JUDGE = 5.7

JUDGE_MODEL = "gpt-4o-mini"

JUDGE_SYSTEM_PROMPT = """You are an expert evaluator of AI chatbot voice cloning quality.

You evaluate how well a BOT response mimics a specific creator's voice and style,
compared to the creator's REAL response to the same message.

The creator is Iris Bertran, a fitness instructor in Barcelona. Key traits:
- Bilingual: mixes Catalan and Spanish naturally (code-switching mid-sentence)
- Very warm: uses "carino", "amor", "nena", "reina", "xurri" constantly
- Direct and energetic: exclamations, CAPS for emphasis
- Heavy emoji user: clusters like "jajajaja", hearts, laughing faces
- Informal: abbreviations (xk, pq, q, tb, dispo), no formal register
- Professional warmth: mixes class scheduling with personal affection

Score each dimension 0-10 (integers). Be strict but fair."""

JUDGE_USER_PROMPT = """Evaluate this bot response against the creator's real response.

Type: {conv_type}
Expected language: {language}
Lead message: {lead_message}
REAL Iris response: {ground_truth}
BOT response: {bot_response}

Score these 6 dimensions (0-10 each):

1. TONO: Does it sound like Iris? (warm, direct, informal, energetic)
2. CONTENIDO: Is the response relevant and correct for the context?
3. IDIOMA: Does it use the correct language? (if Iris responds in ES, bot should too)
4. LONGITUD: Is the length appropriate? (similar to what Iris would write)
5. NATURALIDAD: Does it feel like a real person or a generic bot?
6. UTILIDAD: Would this response actually work in the conversation?

Respond with ONLY valid JSON (no markdown, no backticks, no extra text):
{{"tono": N, "contenido": N, "idioma": N, "longitud": N, "naturalidad": N, "utilidad": N, "overall": N.N, "comentario": "one sentence"}}

The "overall" field should be your holistic score (0-10, one decimal), not just the average."""


# =========================================================================
# PIPELINE RUNNER (reused from measure_baseline_v1.py)
# =========================================================================

def compute_sm_score(bot_response: str, ground_truth: str) -> float:
    if not bot_response or not ground_truth:
        return 0.0
    ratio = SequenceMatcher(None, bot_response.lower(), ground_truth.lower()).ratio()
    return round(ratio * 100, 1)


def get_platform_user_id(lead_id: str) -> Optional[str]:
    try:
        from api.database import SessionLocal
        from api.models import Lead
        session = SessionLocal()
        try:
            row = session.query(Lead.platform_user_id).filter_by(id=lead_id).first()
            return row[0] if row and row[0] else None
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"Could not resolve lead_id={lead_id}: {e}")
    return None


def build_history_metadata(turns: List[Dict], test_input: str) -> Dict:
    history = []
    for turn in turns:
        role = turn.get("role", "")
        content = turn.get("content", "")
        if not content:
            continue
        if role == "iris":
            history.append({"role": "assistant", "content": content})
        elif role == "lead":
            history.append({"role": "user", "content": content})
    if history and history[-1].get("role") == "user" and history[-1].get("content") == test_input:
        history = history[:-1]
    return {"history": history}


async def run_pipeline(conversations: List[Dict]) -> List[Dict]:
    """Run the production DM pipeline on all test conversations."""
    logger.info(f"Initializing DMResponderAgent for creator_id='{CREATOR_ID}'...")
    t_init = time.monotonic()
    try:
        from core.dm_agent_v2 import DMResponderAgent
        agent = DMResponderAgent(creator_id=CREATOR_ID)
        logger.info(f"Agent initialized in {int((time.monotonic() - t_init) * 1000)}ms")
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}", exc_info=True)
        sys.exit(1)

    results = []
    for i, conv in enumerate(conversations, 1):
        conv_id = conv["id"]
        test_input = conv.get("test_input", "")
        ground_truth = conv.get("ground_truth", "")
        conv_type = conv.get("type", "unknown")
        language = conv.get("language", "es")
        lead_id = conv.get("lead_id", "")
        lead_name = conv.get("lead_name", "")

        logger.info(f"[{i}/{len(conversations)}] {conv_id}: {conv_type}/{language}")

        sender_id = get_platform_user_id(lead_id) or lead_id
        turns = conv.get("turns", [])
        metadata = build_history_metadata(turns, test_input)
        metadata["username"] = lead_name or sender_id
        metadata["message_id"] = f"judge_test_{conv_id}"

        t0 = time.monotonic()
        try:
            dm_response = await agent.process_dm(
                message=test_input, sender_id=sender_id, metadata=metadata,
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            bot_response = dm_response.content if dm_response else ""
        except Exception as e:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.error(f"[{conv_id}] FAILED: {e}")
            bot_response = ""

        sm_score = compute_sm_score(bot_response, ground_truth)
        logger.info(f"  -> SM={sm_score}% | {elapsed_ms}ms | '{bot_response[:50]}...'")

        results.append({
            "id": conv_id,
            "type": conv_type,
            "language": language,
            "test_input": test_input,
            "bot_response": bot_response,
            "ground_truth": ground_truth,
            "sm_score": sm_score,
            "elapsed_ms": elapsed_ms,
        })

    return results


# =========================================================================
# EXTERNAL PROVIDER PIPELINE (Together, Fireworks, DeepInfra)
# =========================================================================

PROVIDER_CONFIGS = {
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "env_key": "TOGETHER_API_KEY",
    },
    "fireworks": {
        "base_url": "https://api.fireworks.ai/inference/v1",
        "env_key": "FIREWORKS_API_KEY",
    },
    "deepinfra": {
        "base_url": "https://api.deepinfra.com/v1/openai",
        "env_key": "DEEPINFRA_API_KEY",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
    },
}


def _load_system_prompt() -> str:
    """Load Doc D distilled as system prompt for external providers."""
    doc_d_path = REPO_ROOT / "data" / "personality_extractions" / "iris_bertran_v2_distilled.md"
    if doc_d_path.exists():
        return doc_d_path.read_text(encoding="utf-8")
    logger.warning("Doc D not found, using minimal system prompt")
    return "Eres Iris Bertran. Responde como ella: breve, informal, con emojis."


def _load_few_shot() -> str:
    """Load few-shot examples from calibration file."""
    cal_path = REPO_ROOT / "calibrations" / f"{CREATOR_ID}.json"
    if not cal_path.exists():
        return ""
    try:
        with open(cal_path) as f:
            cal = json.load(f)
        examples = cal.get("few_shot_examples", [])
        if not examples:
            return ""
        selected = random.sample(examples, min(10, len(examples)))
        lines = ["=== EJEMPLOS REALES DE CÓMO RESPONDES ==="]
        for ex in selected:
            lines.append(f"Follower: {ex.get('user_message', '')}")
            lines.append(f"Tú: {ex.get('response', '')}")
            lines.append("")
        lines.append("Responde de forma breve y natural, como en los ejemplos.")
        lines.append("=== FIN EJEMPLOS ===")
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Could not load calibration: {e}")
        return ""


def _load_hierarchical_memory() -> str:
    """Load hierarchical memory context if ENABLE_HIERARCHICAL_MEMORY=true."""
    if os.getenv("ENABLE_HIERARCHICAL_MEMORY", "false").lower() != "true":
        return ""
    try:
        from core.hierarchical_memory.hierarchical_memory import HierarchicalMemoryManager
        hmm = HierarchicalMemoryManager(CREATOR_ID)
        ctx = hmm.get_context_for_message(message="", max_tokens=500)
        if ctx:
            logger.warning(f"[HierMem] Injecting {len(ctx)} chars of hierarchical memory")
        return ctx
    except Exception as e:
        logger.warning(f"[HierMem] Failed to load: {e}")
        return ""


def _get_provider_client(provider: str):
    """Create an OpenAI-compatible client for the given provider."""
    from openai import OpenAI
    config = PROVIDER_CONFIGS[provider]
    api_key = os.environ.get(config["env_key"])
    if not api_key:
        logger.error(f"{config['env_key']} not set")
        sys.exit(1)
    return OpenAI(api_key=api_key, base_url=config["base_url"])


async def run_provider_pipeline(
    conversations: List[Dict], provider: str, model: str
) -> List[Dict]:
    """Run an external provider model on all test conversations."""
    client = _get_provider_client(provider)
    system_prompt = _load_system_prompt()
    few_shot = _load_few_shot()
    hier_memory = _load_hierarchical_memory()
    parts = [system_prompt]
    if hier_memory:
        parts.append(f"\n=== MEMORIA DEL CREATOR ===\n{hier_memory}\n=== FIN MEMORIA ===")
    if few_shot:
        parts.append(few_shot)
    full_system = "\n\n".join(parts)

    # Disable thinking mode for Qwen3 and similar models
    if "qwen3" in model.lower() or "deepseek" in model.lower():
        full_system = "/no_think\n\n" + full_system

    logger.info(f"External provider: {provider} / {model}")
    logger.info(f"System prompt: {len(full_system)} chars")

    results = []
    for i, conv in enumerate(conversations, 1):
        conv_id = conv["id"]
        test_input = conv.get("test_input", "")
        ground_truth = conv.get("ground_truth", "")
        conv_type = conv.get("type", "unknown")
        language = conv.get("language", "es")

        logger.info(f"[{i}/{len(conversations)}] {conv_id}: {conv_type}/{language}")

        # Build message history
        messages = [{"role": "system", "content": full_system}]
        for turn in conv.get("turns", [])[-6:]:
            role = turn.get("role", "")
            content = turn.get("content", "")
            if not content:
                continue
            if role == "iris":
                messages.append({"role": "assistant", "content": content})
            elif role == "lead":
                messages.append({"role": "user", "content": content})

        # Add the test input as the final user message
        messages.append({"role": "user", "content": test_input})

        t0 = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.7,
                max_tokens=150,
            )
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            bot_response = response.choices[0].message.content.strip()
            # Strip <think>...</think> reasoning tags (Qwen3, DeepSeek, etc.)
            # Also handle truncated thinking (no closing tag — increase max_tokens and retry)
            bot_response = re.sub(r"<think>.*?</think>\s*", "", bot_response, flags=re.DOTALL).strip()
            if bot_response.startswith("<think>"):
                # Thinking was truncated — retry with more tokens
                try:
                    response2 = client.chat.completions.create(
                        model=model, messages=messages, temperature=0.7, max_tokens=512,
                    )
                    bot_response = response2.choices[0].message.content.strip()
                    bot_response = re.sub(r"<think>.*?</think>\s*", "", bot_response, flags=re.DOTALL).strip()
                except Exception:
                    pass
                # If still stuck in think mode, extract any text after </think> or discard
                if bot_response.startswith("<think>"):
                    bot_response = ""
        except Exception as e:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            logger.error(f"[{conv_id}] FAILED: {e}")
            bot_response = ""

        sm_score = compute_sm_score(bot_response, ground_truth)
        logger.info(f"  -> SM={sm_score}% | {elapsed_ms}ms | '{bot_response[:50]}...'")

        results.append({
            "id": conv_id,
            "type": conv_type,
            "language": language,
            "test_input": test_input,
            "bot_response": bot_response,
            "ground_truth": ground_truth,
            "sm_score": sm_score,
            "elapsed_ms": elapsed_ms,
        })

        # Rate limit: small sleep between calls
        time.sleep(0.2)

    return results


# =========================================================================
# LLM-AS-JUDGE (GPT-4o-mini)
# =========================================================================

def get_openai_client():
    from openai import OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY not set")
        sys.exit(1)
    return OpenAI(api_key=api_key)


def judge_single(client, conv: Dict) -> Dict:
    """Call GPT-4o-mini to evaluate a single bot response. Returns dimension scores."""
    prompt = JUDGE_USER_PROMPT.format(
        conv_type=conv["type"],
        language=conv["language"],
        lead_message=conv.get("test_input", "(unknown)"),
        ground_truth=conv["ground_truth"],
        bot_response=conv["bot_response"],
    )

    try:
        response = client.chat.completions.create(
            model=JUDGE_MODEL,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=200,
        )
        raw = response.choices[0].message.content.strip()
        # Clean markdown wrappers if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()

        result = json.loads(raw)
        # Validate expected fields
        dimensions = ["tono", "contenido", "idioma", "longitud", "naturalidad", "utilidad"]
        for d in dimensions:
            if d not in result:
                result[d] = 0
            result[d] = max(0, min(10, int(result[d])))
        if "overall" not in result:
            result["overall"] = round(sum(result[d] for d in dimensions) / len(dimensions), 1)
        else:
            result["overall"] = round(float(result["overall"]), 1)
        return result

    except json.JSONDecodeError as e:
        logger.warning(f"Judge JSON parse error: {e} | raw: {raw[:100]}")
        return {"tono": 0, "contenido": 0, "idioma": 0, "longitud": 0,
                "naturalidad": 0, "utilidad": 0, "overall": 0, "error": str(e)}
    except Exception as e:
        logger.warning(f"Judge API error: {e}")
        return {"tono": 0, "contenido": 0, "idioma": 0, "longitud": 0,
                "naturalidad": 0, "utilidad": 0, "overall": 0, "error": str(e)}


def run_judge(conversations: List[Dict]) -> List[Dict]:
    """Evaluate all conversations with LLM-as-judge."""
    client = get_openai_client()
    results = []

    for i, conv in enumerate(conversations, 1):
        cid = conv["id"]
        if not conv.get("bot_response"):
            logger.warning(f"[{cid}] No bot_response, skipping judge")
            conv["judge"] = {"overall": 0, "error": "no_bot_response"}
            results.append(conv)
            continue

        judge_result = judge_single(client, conv)
        conv["judge"] = judge_result

        logger.info(
            f"[{i}/{len(conversations)}] {cid}: "
            f"Judge={judge_result['overall']}/10 SM={conv.get('sm_score', 'N/A')}% "
            f"| {judge_result.get('comentario', '')[:50]}"
        )
        results.append(conv)
        time.sleep(0.3)  # Rate limit courtesy

    return results


# =========================================================================
# AGGREGATION & OUTPUT
# =========================================================================

def aggregate(conversations: List[Dict]) -> Dict:
    """Compute aggregate metrics from judged conversations."""
    valid = [c for c in conversations if c.get("judge", {}).get("overall", 0) > 0]
    if not valid:
        return {"overall_judge": 0, "overall_sm": 0}

    judge_scores = [c["judge"]["overall"] for c in valid]
    sm_scores = [c.get("sm_score", 0) for c in conversations]
    dimensions = ["tono", "contenido", "idioma", "longitud", "naturalidad", "utilidad"]

    # By type
    type_judge = {}
    type_sm = {}
    for c in valid:
        t = c["type"]
        type_judge.setdefault(t, []).append(c["judge"]["overall"])
        type_sm.setdefault(t, []).append(c.get("sm_score", 0))

    # By language
    lang_judge = {}
    lang_sm = {}
    for c in valid:
        lang = c["language"]
        lang_judge.setdefault(lang, []).append(c["judge"]["overall"])
        lang_sm.setdefault(lang, []).append(c.get("sm_score", 0))

    # Dimension averages
    dim_avgs = {}
    for d in dimensions:
        vals = [c["judge"].get(d, 0) for c in valid]
        dim_avgs[d] = round(sum(vals) / len(vals), 1) if vals else 0

    return {
        "overall_judge": round(sum(judge_scores) / len(judge_scores), 1),
        "overall_sm": round(sum(sm_scores) / len(sm_scores), 1) if sm_scores else 0,
        "judge_std_dev": round(statistics.stdev(judge_scores), 1) if len(judge_scores) > 1 else 0,
        "dimensions": dim_avgs,
        "by_type_judge": {t: round(sum(s) / len(s), 1) for t, s in type_judge.items()},
        "by_type_sm": {t: round(sum(s) / len(s), 1) for t, s in type_sm.items()},
        "by_type_counts": {t: len(s) for t, s in type_judge.items()},
        "by_language_judge": {l: round(sum(s) / len(s), 1) for l, s in lang_judge.items()},
        "by_language_sm": {l: round(sum(s) / len(s), 1) for l, s in lang_sm.items()},
        "by_language_counts": {l: len(s) for l, s in lang_judge.items()},
        "n_conversations": len(conversations),
        "n_judged": len(valid),
        "n_errors": len(conversations) - len(valid),
    }


def print_summary(agg: Dict, output_path: str):
    """Print human-readable summary to stdout."""
    judge = agg["overall_judge"]
    sm = agg["overall_sm"]
    dims = agg.get("dimensions", {})

    delta_v1_j = round(judge - BASELINE_V1_JUDGE, 1)
    delta_v3_j = round(judge - BASELINE_V3_JUDGE, 1)
    delta_v1_sm = round(sm - BASELINE_V1_SM, 1)
    delta_v3_sm = round(sm - BASELINE_V3_SM, 1)

    def _fmt(d):
        return f"+{d}" if d >= 0 else str(d)

    print()
    print("=" * 55)
    print("  CLONE QUALITY MEASUREMENT — LLM-as-Judge (primary)")
    print("=" * 55)
    print(f"  Judge (GPT-4o-mini):     {judge}/10")
    print(f"  SequenceMatcher:         {sm}%")
    print(f"  Judge StdDev:            {agg.get('judge_std_dev', 0)}")
    print(f"  Judged/Total:            {agg['n_judged']}/{agg['n_conversations']}")
    print()
    print("  DIMENSIONS:")
    dim_labels = {
        "tono": "Tono",
        "contenido": "Contenido",
        "idioma": "Idioma",
        "longitud": "Longitud",
        "naturalidad": "Naturalidad",
        "utilidad": "Utilidad",
    }
    for key, label in dim_labels.items():
        val = dims.get(key, 0)
        bar = "#" * int(val) + "." * (10 - int(val))
        print(f"    {label:<14} {val:>4}/10  [{bar}]")
    print()
    print("  BY TYPE (Judge / SM):")
    type_labels = {
        "precio": "Precios",
        "saludo": "Saludos",
        "objecion": "Objeciones",
        "lead_caliente": "Lead caliente",
        "audio": "Audio",
        "personal": "Personal",
    }
    type_counts = agg.get("by_type_counts", {})
    for key, label in type_labels.items():
        j = agg.get("by_type_judge", {}).get(key)
        s = agg.get("by_type_sm", {}).get(key)
        n = type_counts.get(key, "")
        n_str = f" (n={n})" if n else ""
        if j is not None:
            print(f"    {label:<14}{n_str:<7} {j:>4}/10  |  {s}%")
    print()
    print("  BY LANGUAGE (Judge / SM):")
    lang_counts = agg.get("by_language_counts", {})
    for lang_key, lang_label in [("ca", "Catalan"), ("es", "Spanish"), ("mixto", "Mixto")]:
        j = agg.get("by_language_judge", {}).get(lang_key)
        s = agg.get("by_language_sm", {}).get(lang_key)
        n = lang_counts.get(lang_key, "")
        if j is not None:
            print(f"    {lang_label:<14} (n={n:<2}) {j:>4}/10  |  {s}%")
    print()
    print("  DELTA vs BASELINES:")
    print(f"    vs v1 (pre-fixes):  Judge {_fmt(delta_v1_j)} pts  |  SM {_fmt(delta_v1_sm)} pts")
    print(f"    vs v3 (last run):   Judge {_fmt(delta_v3_j)} pts  |  SM {_fmt(delta_v3_sm)} pts")
    print("=" * 55)
    print(f"  Output: {output_path}")
    print()


# =========================================================================
# MAIN
# =========================================================================

async def main():
    import argparse
    parser = argparse.ArgumentParser(description="LLM-as-Judge Clone Quality Measurement")
    parser.add_argument("--output", "-o", type=str, default=str(DEFAULT_OUTPUT_PATH),
                        help="Output JSON path")
    parser.add_argument("--test-set", type=str, default=None,
                        help="Custom test set JSON (default: tests/test_set_v2.json)")
    parser.add_argument("--judge-only", type=str, default=None,
                        help="Skip pipeline, judge an existing baseline JSON file")
    parser.add_argument("--provider", type=str, default="gemini",
                        choices=["gemini", "together", "fireworks", "deepinfra", "openrouter"],
                        help="Model provider for generating responses (default: gemini)")
    parser.add_argument("--model", type=str, default=None,
                        help="Model ID for external providers (e.g. Qwen/Qwen3-32B)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of conversations to evaluate")
    args = parser.parse_args()

    # Validate: external providers require --model
    if args.provider != "gemini" and not args.model and not args.judge_only:
        parser.error(f"--model is required when using --provider {args.provider}")

    output_path = Path(args.output)

    # Load test set (always needed for test_input)
    test_set_path = Path(args.test_set) if args.test_set else TEST_SET_PATH
    logger.info(f"Using test set: {test_set_path}")
    with open(test_set_path) as f:
        test_data = json.load(f)
    test_convs = test_data.get("conversations", [])
    test_inputs = {c["id"]: c.get("test_input", "") for c in test_convs}

    # Apply limit if specified
    if args.limit and not args.judge_only:
        test_convs = test_convs[:args.limit]
    logger.info(f"Loaded {len(test_convs)} conversations from test set")

    if args.judge_only:
        # Judge-only mode: load existing results
        logger.info(f"Judge-only mode: loading {args.judge_only}")
        with open(args.judge_only) as f:
            existing = json.load(f)
        conversations = []
        for c in existing.get("conversations", []):
            conversations.append({
                "id": c["id"],
                "type": c["type"],
                "language": c["language"],
                "test_input": test_inputs.get(c["id"], ""),
                "bot_response": c.get("bot_response", ""),
                "ground_truth": c.get("ground_truth", ""),
                "sm_score": c.get("clone_score", c.get("sm_score", 0)),
                "elapsed_ms": c.get("elapsed_ms", 0),
            })
        if args.limit:
            conversations = conversations[:args.limit]
    elif args.provider == "gemini":
        # Production pipeline (local agent with Gemini)
        logger.info(f"Full mode: running pipeline on {len(test_convs)} conversations")
        conversations = await run_pipeline(test_convs)
    else:
        # External provider pipeline
        logger.info(f"External mode: {args.provider}/{args.model} on {len(test_convs)} conversations")
        conversations = await run_provider_pipeline(test_convs, args.provider, args.model)

    # Run LLM-as-judge
    logger.info(f"Running LLM-as-Judge ({JUDGE_MODEL}) on {len(conversations)} conversations...")
    conversations = run_judge(conversations)

    # Aggregate
    agg = aggregate(conversations)

    # Build output
    if args.provider == "gemini":
        try:
            from core.config.llm_models import GEMINI_PRIMARY_MODEL
            bot_model = GEMINI_PRIMARY_MODEL
        except Exception:
            bot_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    else:
        bot_model = f"{args.provider}/{args.model}"

    output = {
        "version": "llm_judge",
        "date": str(date.today()),
        "judge_model": JUDGE_MODEL,
        "bot_model": bot_model,
        "provider": args.provider,
        "baselines": {
            "v1_sm": BASELINE_V1_SM,
            "v1_judge": BASELINE_V1_JUDGE,
            "v3_sm": BASELINE_V3_SM,
            "v3_judge": BASELINE_V3_JUDGE,
        },
        "results": agg,
        "conversations": [
            {
                "id": c["id"],
                "type": c["type"],
                "language": c["language"],
                "test_input": c.get("test_input", ""),
                "bot_response": c["bot_response"],
                "ground_truth": c["ground_truth"],
                "sm_score": c.get("sm_score", 0),
                "judge": c.get("judge", {}),
                "elapsed_ms": c.get("elapsed_ms", 0),
            }
            for c in conversations
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print_summary(agg, str(output_path))


if __name__ == "__main__":
    asyncio.run(main())
