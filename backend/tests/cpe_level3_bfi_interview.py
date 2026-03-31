"""
CPE Level 3: BFI Personality Interview — InCharacter Method

Based on: InCharacter (ACL 2024, Fudan University) — arXiv 2310.17976
Method: Interview-based personality assessment using Expert Rating (ER)

Flow:
  1. Send 44 BFI interview questions to the bot (via DM pipeline)
  2. Bot responds "as the creator would"
  3. Prometheus 7B local evaluates each response → score 1-5 per dimension
  4. Aggregate: bot BFI profile {O, C, E, A, N}
  5. Compare with creator's real BFI profile via cosine similarity

Usage:
    python3 tests/cpe_level3_bfi_interview.py --creator iris_bertran
    python3 tests/cpe_level3_bfi_interview.py --creator iris_bertran --skip-pipeline
    python3 tests/cpe_level3_bfi_interview.py --creator iris_bertran --judge-model gpt-4o-mini

Universal: works for any creator with a bfi_profile in DB or fallback dict.
"""

import argparse
import asyncio
import json
import logging
import math
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cpe_level3")
logger.setLevel(logging.INFO)


# =========================================================================
# BFI QUESTIONS — 44 items from InCharacter (adapted for LLM interview)
# =========================================================================

BFI_QUESTIONS = [
    # Extraversion (8 items)
    {"q": "Q1",  "dim": "E", "cat": "+", "text": "Are you talkative?"},
    {"q": "Q6",  "dim": "E", "cat": "-", "text": "Are you reserved?"},
    {"q": "Q11", "dim": "E", "cat": "+", "text": "Are you full of energy?"},
    {"q": "Q16", "dim": "E", "cat": "+", "text": "Do you generate a lot of enthusiasm?"},
    {"q": "Q21", "dim": "E", "cat": "-", "text": "Do you tend to be quiet?"},
    {"q": "Q26", "dim": "E", "cat": "+", "text": "Do you have an assertive personality?"},
    {"q": "Q31", "dim": "E", "cat": "-", "text": "Are you sometimes shy, inhibited?"},
    {"q": "Q36", "dim": "E", "cat": "+", "text": "Are you outgoing, sociable?"},
    # Agreeableness (9 items)
    {"q": "Q2",  "dim": "A", "cat": "-", "text": "Do you tend to find fault with others?"},
    {"q": "Q7",  "dim": "A", "cat": "+", "text": "Are you helpful and unselfish with others?"},
    {"q": "Q12", "dim": "A", "cat": "-", "text": "Do you start quarrels with others?"},
    {"q": "Q17", "dim": "A", "cat": "+", "text": "Do you have a forgiving nature?"},
    {"q": "Q22", "dim": "A", "cat": "+", "text": "Are you generally trusting?"},
    {"q": "Q27", "dim": "A", "cat": "-", "text": "Can you be cold and aloof?"},
    {"q": "Q32", "dim": "A", "cat": "+", "text": "Are you considerate and kind to almost everyone?"},
    {"q": "Q37", "dim": "A", "cat": "-", "text": "Are you sometimes rude to others?"},
    {"q": "Q42", "dim": "A", "cat": "+", "text": "Do you like to cooperate with others?"},
    # Conscientiousness (9 items)
    {"q": "Q3",  "dim": "C", "cat": "+", "text": "Do you do a thorough job?"},
    {"q": "Q8",  "dim": "C", "cat": "-", "text": "Can you be somewhat careless?"},
    {"q": "Q13", "dim": "C", "cat": "+", "text": "Are you a reliable worker?"},
    {"q": "Q18", "dim": "C", "cat": "-", "text": "Do you tend to be disorganized?"},
    {"q": "Q23", "dim": "C", "cat": "-", "text": "Do you tend to be lazy?"},
    {"q": "Q28", "dim": "C", "cat": "+", "text": "Do you persevere until the task is finished?"},
    {"q": "Q33", "dim": "C", "cat": "+", "text": "Do you do things efficiently?"},
    {"q": "Q38", "dim": "C", "cat": "+", "text": "Do you make plans and follow through with them?"},
    {"q": "Q43", "dim": "C", "cat": "-", "text": "Are you easily distracted?"},
    # Neuroticism (8 items)
    {"q": "Q4",  "dim": "N", "cat": "+", "text": "Are you depressed, blue?"},
    {"q": "Q9",  "dim": "N", "cat": "-", "text": "Are you relaxed and handle stress well?"},
    {"q": "Q14", "dim": "N", "cat": "+", "text": "Can you be tense?"},
    {"q": "Q19", "dim": "N", "cat": "+", "text": "Do you worry a lot?"},
    {"q": "Q24", "dim": "N", "cat": "-", "text": "Are you emotionally stable, not easily upset?"},
    {"q": "Q29", "dim": "N", "cat": "+", "text": "Can you be moody?"},
    {"q": "Q34", "dim": "N", "cat": "-", "text": "Do you remain calm in tense situations?"},
    {"q": "Q39", "dim": "N", "cat": "+", "text": "Do you get nervous easily?"},
    # Openness (10 items)
    {"q": "Q5",  "dim": "O", "cat": "+", "text": "Do you come up with new ideas?"},
    {"q": "Q10", "dim": "O", "cat": "+", "text": "Are you curious about many different things?"},
    {"q": "Q15", "dim": "O", "cat": "+", "text": "Are you ingenious, a deep thinker?"},
    {"q": "Q20", "dim": "O", "cat": "+", "text": "Do you have an active imagination?"},
    {"q": "Q25", "dim": "O", "cat": "+", "text": "Are you inventive?"},
    {"q": "Q30", "dim": "O", "cat": "+", "text": "Do you value artistic, aesthetic experiences?"},
    {"q": "Q35", "dim": "O", "cat": "-", "text": "Do you prefer work that is routine?"},
    {"q": "Q40", "dim": "O", "cat": "+", "text": "Do you like to reflect, play with ideas?"},
    {"q": "Q41", "dim": "O", "cat": "-", "text": "Do you have few artistic interests?"},
    {"q": "Q44", "dim": "O", "cat": "+", "text": "Are you sophisticated in art, music, or literature?"},
]

DIM_LABELS = {
    "E": "Extraversion",
    "A": "Agreeableness",
    "C": "Conscientiousness",
    "N": "Neuroticism",
    "O": "Openness",
}

# InCharacter dimension descriptions for Expert Rating prompts
DIM_DESCRIPTIONS = {
    "E": (
        "Extraversion measures the quantity and intensity of interpersonal interaction, "
        "need for stimulation, and capacity for joy, contrasting social, outgoing "
        "individuals with reserved, shy types."
    ),
    "A": (
        "Agreeableness assesses an individual's likability and attitudes towards others, "
        "balancing compassion and sympathy with antagonism and distrust."
    ),
    "C": (
        "Conscientiousness relates to impulse control, organization, and goal-directed "
        "behavior. It differentiates disciplined, reliable individuals from those who "
        "are disorganized."
    ),
    "N": (
        "Neuroticism refers to tendencies towards anxiety, hostility, depression, "
        "self-consciousness, impulsiveness, and vulnerability."
    ),
    "O": (
        "Openness relates to a cognitive style that values exploration and appreciation "
        "of new experiences. It involves a preference for abstract over concrete thinking."
    ),
}

# BFI crowd norms (n=6,076) for context
CROWD_NORMS = {
    "E": {"mean": 3.25, "std": 0.90},
    "A": {"mean": 3.64, "std": 0.72},
    "C": {"mean": 3.45, "std": 0.73},
    "N": {"mean": 3.32, "std": 0.82},
    "O": {"mean": 3.92, "std": 0.74},
}

# Fallback BFI profiles for known creators (when DB unavailable)
FALLBACK_BFI = {
    "iris_bertran": {"E": 4.4, "A": 4.0, "O": 3.5, "C": 3.1, "N": 2.8},
}


# =========================================================================
# EXPERT RATING — InCharacter ER prompt (anonymous mode)
# =========================================================================

ER_SYSTEM_PROMPT = """You are an expert in Psychometrics, especially the Big Five Inventory (BFI).
I am conducting the BFI test on someone.
I am gauging his/her position on the {dimension} dimension through a series of open-ended questions.
For clarity, here's some background on this particular dimension:
===
{dim_desc}
===

I've invited a participant and we had conversations. I will input the conversations.

Please help me assess the participant's score within the {dimension} dimension of the BFI.

You should provide the score of {dimension} in terms of BFI, which is a number between 1 and 5.
1 denotes 'not {dimension} at all', 3 denotes 'neutral', and 5 denotes 'strongly {dimension}'.
Other numbers in this range represent different degrees of '{dimension}'.

Please output in the following json format:
===
{{
    "analysis": "<your analysis based on the conversations>",
    "result": <your score as a number between 1.0 and 5.0>
}}"""

ER_USER_TEMPLATE = """Our conversation is as follows:
{conversations}"""


# =========================================================================
# BFI PROFILE LOADER
# =========================================================================

def load_bfi_profile(creator_id: str) -> Optional[Dict[str, float]]:
    """Load creator's real BFI from DB, then fallback."""
    try:
        from services.creator_profile_service import get_bfi
        bfi = get_bfi(creator_id)
        if bfi:
            return {k: bfi[k] for k in "EACON" if k in bfi}
    except Exception:
        pass
    return FALLBACK_BFI.get(creator_id)


# =========================================================================
# PIPELINE RUNNER — send BFI questions to bot
# =========================================================================

async def run_bfi_interview(creator_id: str, questions: List[Dict]) -> List[Dict]:
    """Send each BFI question through the production DM pipeline."""
    from core.dm.agent import DMResponderAgentV2

    agent = DMResponderAgentV2(creator_id=creator_id)
    results = []

    for i, q in enumerate(questions, 1):
        metadata = {
            "history": [],
            "username": "bfi_interviewer",
            "message_id": f"bfi_{q['q']}",
        }

        t0 = time.monotonic()
        try:
            dm_response = await agent.process_dm(
                message=q["text"],
                sender_id="bfi_test_participant",
                metadata=metadata,
            )
            bot_response = dm_response.content if dm_response else ""
        except Exception as e:
            logger.error(f"[{q['q']}] Pipeline error: {e}")
            bot_response = ""

        elapsed = int((time.monotonic() - t0) * 1000)
        results.append({
            **q,
            "bot_response": bot_response,
            "elapsed_ms": elapsed,
        })
        logger.info(f"[{i}/{len(questions)}] {q['q']} ({q['dim']}{q['cat']}): '{bot_response[:50]}...' ({elapsed}ms)")

    return results


def run_bfi_interview_direct(creator_id: str, questions: List[Dict], bot_model: str) -> List[Dict]:
    """Send BFI questions directly to a local LLM (bypasses DM pipeline).

    Uses Ollama or OpenAI-compatible API to roleplay as the creator.
    Faster and works without Railway/DB for local testing.
    """
    import urllib.request

    model_name = bot_model.replace("ollama/", "", 1) if bot_model.startswith("ollama/") else bot_model
    use_ollama_native = bot_model.startswith("ollama/")

    # Load creator profile for system prompt
    doc_d_path = REPO_ROOT / "data" / "personality_extractions" / f"{creator_id}_v2_distilled.md"
    cal_path = REPO_ROOT / "calibrations" / f"{creator_id}.json"

    profile_text = ""
    if doc_d_path.exists():
        profile_text = doc_d_path.read_text()[:2000]
    elif cal_path.exists():
        cal = json.loads(cal_path.read_text())
        vocab = cal.get("creator_vocabulary", [])[:20]
        profile_text = f"Vocabulary: {', '.join(vocab)}"

    system_prompt = (
        f"You are {creator_id.replace('_', ' ').title()}. Answer each question honestly "
        f"and naturally in your own voice — short, casual, in the language you normally use "
        f"with your followers (mix of Spanish/Catalan if that's your style). "
        f"Do NOT answer as an AI. Do NOT be formal. Just be yourself.\n\n"
        f"Your personality profile:\n{profile_text[:1500]}"
    )

    if not use_ollama_native:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    else:
        client = None  # Use native Ollama API

    results = []
    for i, q in enumerate(questions, 1):
        t0 = time.monotonic()
        try:
            if use_ollama_native:
                # Use native Ollama API to get content field (OpenAI compat drops it for thinking models)
                payload = json.dumps({
                    "model": model_name,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": q["text"]},
                    ],
                    "stream": False,
                    "options": {"num_predict": 1024, "temperature": 0.7},
                }).encode()
                req = urllib.request.Request(
                    "http://localhost:11434/api/chat",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read())
                bot_response = data.get("message", {}).get("content", "")
            else:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": q["text"]},
                    ],
                    temperature=0.7,
                    max_tokens=200,
                )
                bot_response = response.choices[0].message.content or ""
            # Strip any thinking tags if present
            bot_response = re.sub(r'<think>.*?</think>', '', bot_response, flags=re.DOTALL).strip()
        except Exception as e:
            logger.error(f"[{q['q']}] Direct LLM error: {e}")
            bot_response = ""

        elapsed = int((time.monotonic() - t0) * 1000)
        results.append({
            **q,
            "bot_response": bot_response.strip(),
            "elapsed_ms": elapsed,
        })
        logger.info(f"[{i}/{len(questions)}] {q['q']} ({q['dim']}{q['cat']}): '{bot_response[:50]}...' ({elapsed}ms)")

    return results


# =========================================================================
# JUDGE — Expert Rating via Ollama/OpenAI
# =========================================================================

def _init_judge(judge_model: str):
    """Initialize the judge client. Returns (client, model_name)."""
    if judge_model.startswith("ollama/"):
        from openai import OpenAI
        model_name = judge_model.replace("ollama/", "", 1)
        client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
        return client, model_name
    else:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
        return client, judge_model


def expert_rate_dimension(client, model: str, dim: str, responses: List[Dict],
                          use_prometheus_format: bool = True) -> Dict:
    """
    Rate a BFI dimension from interview responses.

    Two modes:
    - Prometheus format (default): Uses ###Task Description / [RESULT] format
      that Prometheus 7B was trained on. Works reliably with local Prometheus.
    - ER format: InCharacter Expert Rating JSON format. Better for GPT-4/GPT-4o.
    """
    dim_label = DIM_LABELS[dim]

    # Build conversation summary from all responses
    conv_parts = []
    for idx, r in enumerate(responses, 1):
        conv_parts.append(
            f"{idx}. Interviewer: \"{r['text']}\"\n"
            f"   Participant: \"{r['bot_response']}\""
        )
    conversations_str = "\n".join(conv_parts)

    is_local = "localhost" in str(getattr(client, '_base_url', ''))

    if use_prometheus_format and is_local:
        # Use Prometheus ABSOLUTE_PROMPT_WO_REF format (trained on this)
        rubric = (
            f"[How strongly does the participant exhibit {dim_label}?]\n"
            f"Score 1: The participant shows very low {dim_label}. "
            f"Their responses strongly contradict this trait.\n"
            f"Score 2: The participant shows below-average {dim_label}. "
            f"Weak or inconsistent signals of this trait.\n"
            f"Score 3: The participant shows moderate {dim_label}. "
            f"Neither strongly present nor absent.\n"
            f"Score 4: The participant shows above-average {dim_label}. "
            f"Clear and consistent signals of this trait.\n"
            f"Score 5: The participant shows very high {dim_label}. "
            f"Strong, unmistakable expression of this trait throughout."
        )

        prompt = (
            f"###Task Description:\n"
            f"An instruction (might include an Input inside it), a response to evaluate, "
            f"and a score rubric representing a evaluation criteria are given.\n"
            f"1. Write a detailed feedback that assess the quality of the response strictly "
            f"based on the given score rubric, not evaluating in general.\n"
            f"2. After writing a feedback, write a score that is an integer between 1 and 5. "
            f"You should refer to the score rubric.\n"
            f"3. The output format should look as follows: "
            f"\"(write a feedback for criteria) [RESULT] (an integer number between 1 and 5)\"\n"
            f"4. Please do not generate any other opening, closing, and explanations.\n\n"
            f"###The instruction to evaluate:\n"
            f"A psychometric interviewer asked a participant {len(responses)} questions "
            f"to assess their level of {dim_label}.\n"
            f"Background on {dim_label}: {DIM_DESCRIPTIONS[dim]}\n\n"
            f"###Response to evaluate:\n"
            f"{conversations_str}\n\n"
            f"###Score Rubrics:\n"
            f"{rubric}\n\n"
            f"###Feedback:"
        )

        system_prompt = (
            "You are a fair judge assistant tasked with providing clear, objective feedback "
            "based on specific criteria, ensuring each assessment reflects the absolute "
            "standards set for performance."
        )
    else:
        # Original ER format for GPT-4/GPT-4o
        system_prompt = ER_SYSTEM_PROMPT.format(
            dimension=dim_label,
            dim_desc=DIM_DESCRIPTIONS[dim],
        )
        prompt = ER_USER_TEMPLATE.format(conversations=conversations_str)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=600 if is_local else 400,
        )
        text = response.choices[0].message.content or ""

        if use_prometheus_format and is_local:
            score, analysis = _parse_prometheus_result(text)
        else:
            score, analysis = _parse_er_response(text)

        return {
            "dimension": dim,
            "label": dim_label,
            "score": score,
            "analysis": analysis,
            "raw_response": text[:500],
            "n_items": len(responses),
        }
    except Exception as e:
        logger.error(f"Expert rating error ({dim}): {e}")
        return {
            "dimension": dim,
            "label": dim_label,
            "score": 0.0,
            "analysis": f"Error: {e}",
            "raw_response": "",
            "n_items": len(responses),
        }


def _parse_prometheus_result(text: str) -> tuple:
    """Parse Prometheus [RESULT] N format with multiple fallback strategies."""
    # Strategy 1: [RESULT] N pattern (standard Prometheus format)
    match = re.search(r'\[RESULT\]\s*(\d)', text)
    if match:
        score = int(match.group(1))
        feedback = text[:text.index("[RESULT]")].strip() if "[RESULT]" in text else text[:300]
        return (min(5.0, max(1.0, float(score))), feedback)

    # Strategy 2: "score of N" or "score: N" or "Score N"
    match = re.search(r'[Ss]core\s*(?:of\s*|:\s*|is\s*)(\d(?:\.\d)?)', text)
    if match:
        score = float(match.group(1))
        return (min(5.0, max(1.0, score)), text[:300])

    # Strategy 3: "N out of 5" or "N/5"
    match = re.search(r'(\d(?:\.\d)?)\s*(?:out of|\/)\s*5', text)
    if match:
        score = float(match.group(1))
        return (min(5.0, max(1.0, score)), text[:300])

    # Strategy 4: "rating of N" or "rated N"
    match = re.search(r'rat(?:ing|ed)\s*(?:of\s*|:\s*|as\s*)?(\d(?:\.\d)?)', text)
    if match:
        score = float(match.group(1))
        return (min(5.0, max(1.0, score)), text[:300])

    # Strategy 5: look for pattern like "strongly [trait]" → 5, "moderately" → 3, etc.
    text_lower = text.lower()
    if "strongly" in text_lower or "very high" in text_lower or "extremely" in text_lower:
        return (5.0, text[:300])
    if ("high level" in text_lower or "above average" in text_lower or "above-average" in text_lower
            or "fairly high" in text_lower or "clearly high" in text_lower):
        return (4.0, text[:300])
    if "moderate" in text_lower or "average" in text_lower or "neutral" in text_lower:
        return (3.0, text[:300])
    if "below average" in text_lower or "below-average" in text_lower or "somewhat low" in text_lower:
        return (2.0, text[:300])
    if "very low" in text_lower or "not at all" in text_lower:
        return (1.0, text[:300])

    # Strategy 6: last integer 1-5 in text
    nums = re.findall(r'\b([1-5])\b', text)
    if nums:
        return (float(nums[-1]), text[:300])

    logger.warning(f"Could not parse Prometheus result from: {text[:150]}")
    return (0.0, text[:300])


def _parse_er_response(text: str) -> tuple:
    """Parse InCharacter ER JSON response → (score, analysis)."""
    # Try JSON parse
    json_match = re.search(r'\{[^{}]*"result"\s*:\s*[\d.]+[^{}]*\}', text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            score = float(data.get("result", 0))
            analysis = data.get("analysis", "")
            return (min(5.0, max(1.0, score)), analysis)
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: look for "result": N pattern
    result_match = re.search(r'"result"\s*:\s*([\d.]+)', text)
    if result_match:
        score = float(result_match.group(1))
        return (min(5.0, max(1.0, score)), text[:300])

    # Last resort: any float between 1 and 5
    nums = re.findall(r'\b([1-5](?:\.\d+)?)\b', text)
    if nums:
        score = float(nums[-1])
        return (min(5.0, max(1.0, score)), text[:300])

    logger.warning(f"Could not parse ER score from: {text[:200]}")
    return (0.0, text[:300])


# =========================================================================
# METRICS — cosine similarity and comparison
# =========================================================================

def cosine_similarity(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Cosine similarity between two BFI profiles."""
    keys = sorted(set(a.keys()) & set(b.keys()))
    if not keys:
        return 0.0
    dot = sum(a[k] * b[k] for k in keys)
    mag_a = math.sqrt(sum(a[k] ** 2 for k in keys))
    mag_b = math.sqrt(sum(b[k] ** 2 for k in keys))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def mae(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Mean Absolute Error between two BFI profiles."""
    keys = sorted(set(a.keys()) & set(b.keys()))
    if not keys:
        return 0.0
    return sum(abs(a[k] - b[k]) for k in keys) / len(keys)


# =========================================================================
# MAIN
# =========================================================================

def main():
    parser = argparse.ArgumentParser(description="CPE Level 3: BFI Personality Interview")
    parser.add_argument("--creator", required=True, help="Creator slug (e.g. iris_bertran)")
    parser.add_argument("--judge-model", default="ollama/vicgalle/prometheus-7b-v2.0",
                        help="Judge model (default: local Prometheus 7B via Ollama)")
    parser.add_argument("--skip-pipeline", action="store_true",
                        help="Reuse bot responses from latest results file")
    parser.add_argument("--direct-llm", default=None,
                        help="Bypass DM pipeline; send questions directly to this LLM "
                             "(e.g. ollama/qwen3:14b). Useful for local testing without Railway.")
    parser.add_argument("--output", help="Output JSON path (auto-generated if omitted)")
    parser.add_argument("--limit", type=int, help="Limit number of questions (for testing)")
    args = parser.parse_args()

    creator = args.creator
    results_dir = REPO_ROOT / "tests" / "cpe_data" / creator / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    # Load creator's real BFI
    real_bfi = load_bfi_profile(creator)
    if not real_bfi:
        logger.error(f"No BFI profile found for {creator}. Add to FALLBACK_BFI or DB.")
        sys.exit(1)

    logger.info(f"Creator {creator} real BFI: {real_bfi}")

    questions = BFI_QUESTIONS[:]
    if args.limit:
        questions = questions[:args.limit]

    # Step 1: Get bot responses
    if args.skip_pipeline:
        # Load latest results
        latest = sorted(results_dir.glob("level3_bfi_*.json"), key=lambda p: p.stat().st_mtime)
        if not latest:
            logger.error("No previous results to reuse. Run without --skip-pipeline first.")
            sys.exit(1)
        with open(latest[-1]) as f:
            prev = json.load(f)
        responses = prev.get("interview_responses", [])
        logger.info(f"Reusing {len(responses)} responses from {latest[-1].name}")
    elif args.direct_llm:
        logger.info(f"Running BFI interview: {len(questions)} questions via direct LLM ({args.direct_llm})...")
        responses = run_bfi_interview_direct(creator, questions, args.direct_llm)
    else:
        logger.info(f"Running BFI interview: {len(questions)} questions through DM pipeline...")
        responses = asyncio.run(run_bfi_interview(creator, questions))
        # Filter out empty responses
        empty = sum(1 for r in responses if not r.get("bot_response"))
        if empty:
            logger.warning(f"{empty}/{len(responses)} questions got empty responses")

    # Step 2: Expert Rating — group by dimension and judge
    logger.info(f"Expert Rating with {args.judge_model}...")
    client, model_name = _init_judge(args.judge_model)

    dim_results = {}
    for dim in ["E", "A", "C", "N", "O"]:
        dim_responses = [r for r in responses if r["dim"] == dim and r.get("bot_response")]
        if not dim_responses:
            logger.warning(f"No responses for {DIM_LABELS[dim]}, skipping")
            continue
        result = expert_rate_dimension(client, model_name, dim, dim_responses)
        dim_results[dim] = result
        logger.info(f"  {DIM_LABELS[dim]}: {result['score']:.1f}/5 ({result['n_items']} items)")

    # Step 3: Build bot BFI profile
    bot_bfi = {dim: r["score"] for dim, r in dim_results.items() if r["score"] > 0}

    if not bot_bfi:
        logger.error("No valid dimension scores. Check judge output.")
        sys.exit(1)

    # Step 4: Compare with real BFI
    cos_sim = cosine_similarity(bot_bfi, real_bfi)
    mean_abs_err = mae(bot_bfi, real_bfi)

    dim_deltas = {}
    for dim in sorted(set(bot_bfi.keys()) & set(real_bfi.keys())):
        dim_deltas[dim] = {
            "bot": bot_bfi[dim],
            "real": real_bfi[dim],
            "delta": round(bot_bfi[dim] - real_bfi[dim], 2),
            "abs_delta": round(abs(bot_bfi[dim] - real_bfi[dim]), 2),
            "crowd_mean": CROWD_NORMS.get(dim, {}).get("mean", 0),
        }

    # Step 5: Build output
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = args.output or str(results_dir / f"level3_bfi_{timestamp}.json")

    output = {
        "meta": {
            "creator": creator,
            "judge_model": args.judge_model,
            "n_questions": len(questions),
            "n_responses": sum(1 for r in responses if r.get("bot_response")),
            "timestamp": timestamp,
            "method": "InCharacter Expert Rating (anonymous, batch per dimension)",
            "paper": "arXiv:2310.17976",
        },
        "bot_bfi": bot_bfi,
        "real_bfi": real_bfi,
        "comparison": {
            "cosine_similarity": round(cos_sim, 4),
            "mae": round(mean_abs_err, 2),
            "target_cosine": 0.85,
            "target_met": cos_sim >= 0.85,
        },
        "dimensions": dim_deltas,
        "dimension_details": dim_results,
        "interview_responses": responses,
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Print summary
    print("\n" + "=" * 65)
    print(f"  CPE Level 3: BFI Personality Interview — {creator}")
    print("=" * 65)

    print(f"\n  {'Dimension':<20s} {'Bot':>5s} {'Real':>5s} {'Delta':>6s} {'Crowd':>6s}")
    print("  " + "-" * 48)
    for dim in ["E", "A", "O", "C", "N"]:
        if dim in dim_deltas:
            d = dim_deltas[dim]
            print(f"  {DIM_LABELS[dim]:<20s} {d['bot']:>5.1f} {d['real']:>5.1f} {d['delta']:>+6.1f} {d['crowd_mean']:>6.2f}")
    print("  " + "-" * 48)

    print(f"\n  Cosine Similarity: {cos_sim:.4f}  (target ≥ 0.85: {'PASS' if cos_sim >= 0.85 else 'FAIL'})")
    print(f"  Mean Absolute Error: {mean_abs_err:.2f}  (target ≤ 0.50: {'PASS' if mean_abs_err <= 0.50 else 'FAIL'})")
    print(f"\n  Output: {output_path}")
    print("=" * 65)


if __name__ == "__main__":
    main()
