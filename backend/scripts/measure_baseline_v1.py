"""
Baseline Measurement Script v1 — Post-Blackout Clone Score

Measures Clone Score for the 20 test conversations in tests/test_set_v1.json
using the REAL production pipeline (same agent used in prod).

Usage:
    railway run .venv/bin/python3 scripts/measure_baseline_v1.py

DO NOT modify production code. This is measurement only.
"""

import asyncio
import json
import logging
import os
import random
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
    level=logging.WARNING,  # Suppress verbose INFO from pipeline
    format="%(levelname)s %(name)s: %(message)s",
)
# Only show our own script messages
logger = logging.getLogger("measure_baseline")
logger.setLevel(logging.INFO)

CREATOR_ID = "iris_bertran"
TEST_SET_PATH = REPO_ROOT / "tests" / "test_set_v1.json"
OUTPUT_PATH = REPO_ROOT / "tests" / "baseline_v1.json"

# Pre-blackout reference value (from memory.md)
PRE_BLACKOUT_SCORE = 17.1


def compute_clone_score(bot_response: str, ground_truth: str) -> float:
    """
    Compute Clone Score as SequenceMatcher similarity ratio (0-100).

    This is the same metric used in production for 'similarity_score'
    (copilot actions.py: _compute_similarity). Scaled to 0-100%.
    """
    if not bot_response or not ground_truth:
        return 0.0
    ratio = SequenceMatcher(None, bot_response.lower(), ground_truth.lower()).ratio()
    return round(ratio * 100, 1)


def get_platform_user_id(lead_id: str) -> Optional[str]:
    """Resolve lead UUID -> platform_user_id from DB."""
    try:
        from api.database import SessionLocal
        from api.models import Lead

        session = SessionLocal()
        try:
            row = session.query(Lead.platform_user_id).filter_by(id=lead_id).first()
            if row and row[0]:
                return row[0]
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"Could not resolve lead_id={lead_id}: {e}")
    return None


def build_history_metadata(turns: List[Dict], test_input: str) -> Dict:
    """
    Build metadata dict with conversation history formatted for the agent.

    Maps 'iris' role -> 'assistant', 'lead' role -> 'user'.
    Excludes the test_input itself (it's the current message).
    """
    history = []
    for turn in turns:
        role = turn.get("role", "")
        content = turn.get("content", "")
        if not content:
            continue
        if role == "iris":
            history.append({"role": "assistant", "content": content})
        elif role == "lead":
            # Skip if this is the test_input (last lead message)
            history.append({"role": "user", "content": content})

    # Remove the last entry if it matches test_input (the agent will receive it as message=)
    if history and history[-1].get("role") == "user" and history[-1].get("content") == test_input:
        history = history[:-1]

    return {"history": history}


async def run_single_conversation(
    agent,
    conv: Dict,
) -> Dict[str, Any]:
    """
    Run the production pipeline for a single test conversation.

    Returns result dict with bot_response, ground_truth, clone_score.
    """
    conv_id = conv["id"]
    lead_id = conv.get("lead_id", "")
    test_input = conv.get("test_input", "")
    ground_truth = conv.get("ground_truth", "")
    conv_type = conv.get("type", "unknown")
    language = conv.get("language", "es")
    lead_name = conv.get("lead_name", "")

    logger.info(f"[{conv_id}] Processing: type={conv_type}, lang={language}, lead={lead_name}")

    # Resolve sender_id (platform_user_id) from DB
    sender_id = get_platform_user_id(lead_id)
    if not sender_id:
        logger.warning(f"[{conv_id}] Could not find platform_user_id for lead_id={lead_id}, using lead_id as fallback")
        sender_id = lead_id

    # Build metadata with conversation history
    turns = conv.get("turns", [])
    metadata = build_history_metadata(turns, test_input)
    metadata["username"] = lead_name or sender_id
    metadata["message_id"] = f"baseline_test_{conv_id}"

    t0 = time.monotonic()
    try:
        dm_response = await agent.process_dm(
            message=test_input,
            sender_id=sender_id,
            metadata=metadata,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)

        bot_response = dm_response.content if dm_response else ""
        clone_score = compute_clone_score(bot_response, ground_truth)

        logger.info(
            f"[{conv_id}] OK in {elapsed_ms}ms | score={clone_score}% | "
            f"bot='{bot_response[:60]}...' | gt='{ground_truth[:60]}...'"
        )

        return {
            "id": conv_id,
            "type": conv_type,
            "language": language,
            "lead_id": lead_id,
            "sender_id": sender_id,
            "bot_response": bot_response,
            "ground_truth": ground_truth,
            "clone_score": clone_score,
            "elapsed_ms": elapsed_ms,
            "error": None,
        }

    except Exception as e:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.error(f"[{conv_id}] FAILED after {elapsed_ms}ms: {e}", exc_info=True)
        return {
            "id": conv_id,
            "type": conv_type,
            "language": language,
            "lead_id": lead_id,
            "sender_id": sender_id,
            "bot_response": "",
            "ground_truth": ground_truth,
            "clone_score": 0.0,
            "elapsed_ms": elapsed_ms,
            "error": str(e),
        }


def get_active_flags() -> Dict[str, bool]:
    """Read current feature flag state from env vars."""
    return {
        "ENABLE_LEARNING_RULES": os.getenv("ENABLE_LEARNING_RULES", "false").lower() == "true",
        "ENABLE_BEST_OF_N": os.getenv("ENABLE_BEST_OF_N", "false").lower() == "true",
        "ENABLE_SELF_CONSISTENCY": os.getenv("ENABLE_SELF_CONSISTENCY", "false").lower() == "true",
        "ENABLE_REFLEXION": os.getenv("ENABLE_REFLEXION", "true").lower() == "true",
        "ENABLE_MEMORY_ENGINE": os.getenv("ENABLE_MEMORY_ENGINE", "false").lower() == "true",
        "ENABLE_CLONE_SCORE": os.getenv("ENABLE_CLONE_SCORE", "false").lower() == "true",
    }


def get_model_name() -> str:
    """Get actual LLM model being used."""
    try:
        from core.config.llm_models import GEMINI_PRIMARY_MODEL
        return GEMINI_PRIMARY_MODEL
    except Exception:
        return os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")


async def main():
    logger.info("=" * 50)
    logger.info("BASELINE MEASUREMENT v1 — POST-BLACKOUT")
    logger.info("=" * 50)

    # Load test set
    logger.info(f"Loading test set from {TEST_SET_PATH}")
    with open(TEST_SET_PATH) as f:
        test_data = json.load(f)

    conversations = test_data.get("conversations", [])
    logger.info(f"Loaded {len(conversations)} conversations")

    # Initialize the production agent ONCE (same factory as prod)
    logger.info(f"Initializing DMResponderAgent for creator_id='{CREATOR_ID}'...")
    t_init = time.monotonic()
    try:
        from core.dm_agent_v2 import DMResponderAgent
        agent = DMResponderAgent(creator_id=CREATOR_ID)
        logger.info(f"Agent initialized in {int((time.monotonic() - t_init) * 1000)}ms")
    except Exception as e:
        logger.error(f"Failed to initialize agent: {e}", exc_info=True)
        sys.exit(1)

    # Run all conversations
    results_raw = []
    errors = []

    for i, conv in enumerate(conversations, 1):
        logger.info(f"\n--- Conversation {i}/{len(conversations)}: {conv['id']} ---")
        result = await run_single_conversation(agent, conv)
        results_raw.append(result)
        if result["error"]:
            errors.append(result["id"])

    # Compute aggregated metrics
    all_scores = [r["clone_score"] for r in results_raw]
    successful_scores = [r["clone_score"] for r in results_raw if r["error"] is None]

    overall_score = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0.0
    std_dev = round(statistics.stdev(all_scores), 1) if len(all_scores) > 1 else 0.0

    # By type
    type_scores: Dict[str, List[float]] = {}
    for r in results_raw:
        t = r["type"]
        type_scores.setdefault(t, []).append(r["clone_score"])

    by_type = {
        t: round(sum(scores) / len(scores), 1)
        for t, scores in type_scores.items()
    }

    # By language
    lang_scores: Dict[str, List[float]] = {}
    for r in results_raw:
        lang = r["language"]
        lang_scores.setdefault(lang, []).append(r["clone_score"])

    by_language = {
        lang: round(sum(scores) / len(scores), 1)
        for lang, scores in lang_scores.items()
    }

    # Build output JSON
    output = {
        "version": "v1",
        "date": str(date.today()),
        "system_state": "post-blackout, pre-canonical-fixes",
        "flags": get_active_flags(),
        "model": get_model_name(),
        "results": {
            "overall_clone_score": overall_score,
            "by_type": by_type,
            "by_language": by_language,
            "std_dev": std_dev,
            "n_conversations": len(conversations),
            "n_successful": len(conversations) - len(errors),
            "n_errors": len(errors),
        },
        "conversations": [
            {
                "id": r["id"],
                "type": r["type"],
                "language": r["language"],
                "bot_response": r["bot_response"],
                "ground_truth": r["ground_truth"],
                "clone_score": r["clone_score"],
                "elapsed_ms": r["elapsed_ms"],
                "error": r["error"],
            }
            for r in results_raw
        ],
    }

    # Save results
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    logger.info(f"\nResults saved to {OUTPUT_PATH}")

    # Print summary
    delta = round(overall_score - PRE_BLACKOUT_SCORE, 1)
    delta_str = f"+{delta}" if delta >= 0 else str(delta)

    print("\n==========================================")
    print("BASELINE MEASUREMENT — POST-BLACKOUT")
    print("==========================================")
    print(f"Clone Score medio: {overall_score}% (antes del apagón era {PRE_BLACKOUT_SCORE}%)")
    print()
    print("Por tipo:")
    type_labels = {
        "precio": "Precios",
        "saludo": "Saludos",
        "objecion": "Objeciones",
        "lead_caliente": "Lead caliente",
        "audio": "Audio",
        "personal": "Personal",
    }
    for key, label in type_labels.items():
        score = by_type.get(key)
        if score is not None:
            print(f"  - {label}: {score}%")
        else:
            print(f"  - {label}: N/A (no samples)")
    print()
    print("Por idioma:")
    print(f"  - Catalán: {by_language.get('ca', 'N/A')}%")
    print(f"  - Español: {by_language.get('es', 'N/A')}%")
    print()
    print(f"Delta vs pre-apagón: {delta_str} puntos")
    print(f"Std Dev: {std_dev}")
    print(f"Errores: {len(errors)}/{len(conversations)}")
    if errors:
        print(f"Conversations con error: {', '.join(errors)}")
    print("==========================================")
    print(f"\nResultados completos en: {OUTPUT_PATH}")

    if errors:
        logger.warning(f"{len(errors)} conversations failed: {errors}")

    return output


if __name__ == "__main__":
    asyncio.run(main())
