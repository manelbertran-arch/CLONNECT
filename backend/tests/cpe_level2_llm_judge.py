"""
CPE Level 2: LLM-as-Judge — Multi-Dimensional Persona Evaluation

Evaluates bot responses across 5 dimensions using structured rubrics
adapted from CharacterEval (Tu et al., 2024) and PersonaGym (Samuel et al., 2024).
Uses the Prometheus 2 ABSOLUTE_PROMPT format with reference answers.

Judge model: GPT-4o-mini by default (configurable via --judge-model).
Rubric format: Prometheus 2 (###Task Description + score rubric + reference answer).

Dimensions (1-5 scale each):
  1. Conversational Ability — coherence, fluency, contextual consistency
  2. Persona Fidelity — speech patterns, tone, vocabulary, behavioral consistency
  3. Knowledge Accuracy — correctness of facts, avoidance of hallucination
  4. Emotional Intelligence — empathy, emotional perception, appropriate response
  5. Engagement — humanlikeness, avoids generic/assistant patterns, proactive

Usage:
    railway run python3 tests/cpe_level2_llm_judge.py --creator iris_bertran
    railway run python3 tests/cpe_level2_llm_judge.py --creator iris_bertran --responses tests/cpe_data/iris_bertran/results/level1_*.json
    railway run python3 tests/cpe_level2_llm_judge.py --creator iris_bertran --judge-model gpt-4o

Universal: works for any creator. Creator profile loaded from personality_docs.
"""

import argparse
import asyncio
import json
import logging
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
logger = logging.getLogger("cpe_level2")
logger.setLevel(logging.INFO)

DEFAULT_JUDGE_MODEL = "gpt-4o-mini"


# =========================================================================
# RUBRICS (adapted from CharacterEval + PersonaGym, Prometheus 2 format)
# =========================================================================

# System prompt per Prometheus 2 spec
JUDGE_SYSTEM_PROMPT = (
    "You are a fair judge assistant tasked with providing clear, objective feedback "
    "based on specific criteria, ensuring each assessment reflects the absolute "
    "standards set for performance."
)

# 5 rubrics, each with 1-5 scale descriptions
RUBRICS = {
    "conversational_ability": {
        "name": "Conversational Ability",
        "rubric": (
            "[Is the response coherent, fluent, and contextually consistent?]\n"
            "Score 1: Completely incoherent, grammatically broken, or contradicts the conversation context.\n"
            "Score 2: Partially coherent but contains noticeable inconsistencies or awkward phrasing.\n"
            "Score 3: Generally coherent and fluent, with minor inconsistencies.\n"
            "Score 4: Coherent, fluent, and consistent with the conversation context. Minor imperfections.\n"
            "Score 5: Perfectly coherent, fluent, and fully consistent with all prior conversation context."
        ),
    },
    "persona_fidelity": {
        "name": "Persona Fidelity",
        "rubric": (
            "[Does the response match the creator's speech patterns, tone, vocabulary, and behavioral style?]\n"
            "Score 1: Sounds like a generic AI assistant. No trace of the creator's personality.\n"
            "Score 2: Occasional hints of the creator's style but mostly generic or inconsistent.\n"
            "Score 3: Recognizably the creator's style in some aspects (tone OR vocabulary OR length) but not all.\n"
            "Score 4: Strong match with the creator's voice. Correct tone, vocabulary, and behavioral patterns with minor deviations.\n"
            "Score 5: Indistinguishable from the creator. Perfect match in speech patterns, pet names, emoji usage, code-switching, message length, and tone."
        ),
    },
    "knowledge_accuracy": {
        "name": "Knowledge Accuracy",
        "rubric": (
            "[Does the response contain correct factual information and avoid hallucination?]\n"
            "Score 1: Contains fabricated facts, wrong prices, or information the creator would not know.\n"
            "Score 2: Mostly vague or evasive, with one or more factual errors.\n"
            "Score 3: No obvious errors but lacks specific factual content that the reference answer includes.\n"
            "Score 4: Factually correct with minor omissions compared to the reference.\n"
            "Score 5: All facts are correct and complete. No hallucination. Matches or exceeds the reference in factual accuracy."
        ),
    },
    "emotional_intelligence": {
        "name": "Emotional Intelligence",
        "rubric": (
            "[Does the response show appropriate emotional perception and empathetic engagement?]\n"
            "Score 1: Tone-deaf or inappropriate emotional response (e.g., cheerful response to sad message).\n"
            "Score 2: Acknowledges the emotional context but responds mechanically or with canned phrases.\n"
            "Score 3: Adequate emotional awareness. Neither warm nor cold.\n"
            "Score 4: Emotionally perceptive. Responds with appropriate warmth, concern, or enthusiasm.\n"
            "Score 5: Deeply empathetic. The emotional tone perfectly matches what the creator would express — warm when needed, direct when needed, playful when appropriate."
        ),
    },
    "engagement": {
        "name": "Engagement",
        "rubric": (
            "[Does the response feel human-like, avoid generic bot patterns, and maintain conversational momentum?]\n"
            "Score 1: Robotic, formulaic, or uses assistant-like patterns ('How can I help you?', numbered lists).\n"
            "Score 2: Mostly natural but includes occasional bot-like phrases or overly formal language.\n"
            "Score 3: Natural tone but passive — responds without advancing the conversation.\n"
            "Score 4: Engaging and human-like. Adds personality and moves the conversation forward.\n"
            "Score 5: Completely human. Indistinguishable from a real person texting. Proactive, witty, and natural."
        ),
    },
}


# =========================================================================
# PROMETHEUS 2 ABSOLUTE_PROMPT FORMAT
# =========================================================================

ABSOLUTE_PROMPT = """###Task Description:
An instruction (might include an Input inside it), a response to evaluate, a reference answer that gets a score of 5, and a score rubric representing a evaluation criteria are given.
1. Write a detailed feedback that assess the quality of the response strictly based on the given score rubric, not evaluating in general.
2. After writing a feedback, write a score that is an integer between 1 and 5. You should refer to the score rubric.
3. The output format should look as follows: "(write a feedback for criteria) [RESULT] (an integer number between 1 and 5)"
4. Please do not generate any other opening, closing, and explanations.

###The instruction to evaluate:
You are {creator_name}, a real person. A follower sent you this message:
"{lead_message}"

Context about {creator_name}: {creator_profile}

Conversation history:
{history}

###Response to evaluate:
{bot_response}

###Reference Answer (Score 5):
{reference_answer}

###Score Rubrics:
{rubric}

###Feedback:"""


# =========================================================================
# CREATOR PROFILE LOADER
# =========================================================================

def load_creator_profile(creator_id: str) -> str:
    """Load creator profile summary from personality_docs or calibration."""
    # Try calibration file first
    cal_path = REPO_ROOT / "calibrations" / f"{creator_id}.json"
    if cal_path.exists():
        with open(cal_path) as f:
            cal = json.load(f)
        vocab = cal.get("creator_vocabulary", [])
        baseline = cal.get("baseline", {})
        examples = cal.get("few_shot_examples", [])[:3]

        parts = [f"Creator: {creator_id}"]
        if vocab:
            parts.append(f"Vocabulary: {', '.join(vocab[:15])}")
        if baseline:
            parts.append(f"Style: median length {baseline.get('median_length', '?')} chars, "
                        f"emoji {baseline.get('emoji_pct', '?')}%, "
                        f"questions {baseline.get('question_frequency_pct', '?')}%")
        if examples:
            parts.append("Example responses:")
            for ex in examples:
                parts.append(f'  Lead: "{ex.get("user_message", "")}" -> Creator: "{ex.get("response", "")}"')
        return "\n".join(parts)

    # Fallback: try DB
    try:
        import psycopg2
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute("""
            SELECT pd.content FROM personality_docs pd
            JOIN creators c ON c.id::text = pd.creator_id
            WHERE c.name = %s AND pd.doc_type IN ('doc_d_distilled', 'doc_d')
            ORDER BY CASE pd.doc_type WHEN 'doc_d_distilled' THEN 0 ELSE 1 END
            LIMIT 1
        """, (creator_id,))
        row = cur.fetchone()
        conn.close()
        if row:
            return row[0][:2000]
    except Exception:
        pass

    return f"Creator: {creator_id}. No profile available."


# =========================================================================
# JUDGE CALL
# =========================================================================

def judge_single(client, model: str, dimension: str, rubric_info: dict,
                 creator_name: str, creator_profile: str,
                 conv: dict) -> dict:
    """Call LLM judge for one dimension on one conversation."""

    # Build history string
    turns = conv.get("turns", [])
    history_str = ""
    for t in turns[-6:]:
        role = "Creator" if t.get("role") in ("iris", "assistant") else "Follower"
        history_str += f"{role}: {t.get('content', '')}\n"
    if not history_str:
        history_str = "(no prior conversation)"

    prompt = ABSOLUTE_PROMPT.format(
        creator_name=creator_name,
        lead_message=conv.get("test_input", conv.get("lead_message", "")),
        creator_profile=creator_profile[:1500],
        history=history_str,
        bot_response=conv.get("bot_response", ""),
        reference_answer=conv.get("ground_truth", "(no reference available)"),
        rubric=rubric_info["rubric"],
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=300,
        )
        raw = response.choices[0].message.content.strip()

        # Parse "[RESULT] N" from output
        match = re.search(r"\[RESULT\]\s*(\d)", raw)
        score = int(match.group(1)) if match else 0
        feedback = raw.split("[RESULT]")[0].strip() if "[RESULT]" in raw else raw

        return {
            "dimension": dimension,
            "score": min(5, max(1, score)) if score else 0,
            "feedback": feedback[:300],
        }
    except Exception as e:
        logger.warning(f"Judge error ({dimension}): {e}")
        return {"dimension": dimension, "score": 0, "feedback": f"Error: {e}"}


# =========================================================================
# PIPELINE RUNNER (reuse from level 1)
# =========================================================================

def _get_platform_user_id(lead_id: str) -> Optional[str]:
    try:
        from api.database import SessionLocal
        from api.models import Lead
        session = SessionLocal()
        try:
            row = session.query(Lead.platform_user_id).filter_by(id=lead_id).first()
            return row[0] if row and row[0] else None
        finally:
            session.close()
    except Exception:
        return None


async def run_pipeline(creator_id: str, conversations: List[Dict]) -> List[Dict]:
    """Run production DM pipeline."""
    from core.dm_agent_v2 import DMResponderAgent
    agent = DMResponderAgent(creator_id=creator_id)
    results = []

    for i, conv in enumerate(conversations, 1):
        test_input = conv.get("test_input", conv.get("lead_message", conv.get("message", "")))
        lead_id = conv.get("lead_id", "")
        sender_id = _get_platform_user_id(lead_id) or lead_id

        history = []
        for turn in conv.get("turns", []):
            role = turn.get("role", "")
            content = turn.get("content", "")
            if not content:
                continue
            if role in ("iris", "assistant"):
                history.append({"role": "assistant", "content": content})
            elif role in ("lead", "user"):
                history.append({"role": "user", "content": content})
        if history and history[-1].get("content") == test_input:
            history = history[:-1]

        metadata = {
            "history": history,
            "username": conv.get("username", conv.get("lead_name", sender_id)),
            "message_id": f"cpe2_{conv.get('id', i)}",
        }

        t0 = time.monotonic()
        try:
            dm_response = await agent.process_dm(message=test_input, sender_id=sender_id, metadata=metadata)
            bot_response = dm_response.content if dm_response else ""
        except Exception as e:
            logger.error(f"[{conv.get('id', i)}] Pipeline error: {e}")
            bot_response = ""

        results.append({**conv, "bot_response": bot_response, "elapsed_ms": int((time.monotonic() - t0) * 1000)})
        logger.info(f"[{i}/{len(conversations)}] {conv.get('id', '?')}: '{bot_response[:40]}...'")

    return results


# =========================================================================
# MAIN
# =========================================================================

async def main():
    parser = argparse.ArgumentParser(description="CPE Level 2: LLM-as-Judge Persona Evaluation")
    parser.add_argument("--creator", required=True, help="Creator slug")
    parser.add_argument("--test-set", default=None, help="Custom test set")
    parser.add_argument("--responses", default=None, help="Reuse responses from existing file (skip pipeline)")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, help="Judge model (default: gpt-4o-mini)")
    parser.add_argument("--output", default=None, help="Custom output path")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of test cases")
    args = parser.parse_args()

    creator = args.creator
    cpe_dir = REPO_ROOT / "tests" / "cpe_data" / creator / "results"
    cpe_dir.mkdir(parents=True, exist_ok=True)

    # Load test set
    if args.responses:
        with open(args.responses) as f:
            prev = json.load(f)
        conversations = prev.get("conversations", prev if isinstance(prev, list) else [])
        logger.info(f"Reusing {len(conversations)} responses from {args.responses}")
    else:
        test_path = Path(args.test_set) if args.test_set else REPO_ROOT / "tests" / "test_set_real_leads.json"
        with open(test_path) as f:
            data = json.load(f)
        conversations = data if isinstance(data, list) else data.get("conversations", data.get("test_cases", []))

        if args.limit:
            conversations = conversations[:args.limit]

        # Run pipeline
        logger.info(f"Running pipeline on {len(conversations)} conversations...")
        conversations = await run_pipeline(creator, conversations)

    # Load creator profile
    creator_profile = load_creator_profile(creator)
    creator_name = creator.replace("_", " ").title()
    logger.info(f"Creator profile loaded: {len(creator_profile)} chars")

    # Initialize judge
    from openai import OpenAI
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    # Evaluate each conversation across all 5 dimensions
    all_results = []
    dimension_scores = {d: [] for d in RUBRICS}

    for i, conv in enumerate(conversations, 1):
        if not conv.get("bot_response"):
            logger.warning(f"[{conv.get('id', i)}] No bot_response, skipping")
            continue

        conv_scores = {}
        for dim_key, rubric_info in RUBRICS.items():
            result = judge_single(
                client, args.judge_model, dim_key, rubric_info,
                creator_name, creator_profile, conv,
            )
            conv_scores[dim_key] = result
            if result["score"] > 0:
                dimension_scores[dim_key].append(result["score"])
            time.sleep(0.2)  # Rate limit

        # Compute per-conversation aggregate
        valid_scores = [v["score"] for v in conv_scores.values() if v["score"] > 0]
        overall = round(sum(valid_scores) / len(valid_scores), 2) if valid_scores else 0

        all_results.append({
            "id": conv.get("id", f"conv_{i}"),
            "test_input": conv.get("test_input", conv.get("lead_message", "")),
            "bot_response": conv.get("bot_response", ""),
            "ground_truth": conv.get("ground_truth", ""),
            "overall_score": overall,
            "dimensions": conv_scores,
            "elapsed_ms": conv.get("elapsed_ms", 0),
        })

        logger.info(
            f"[{i}/{len(conversations)}] {conv.get('id', '?')}: "
            f"overall={overall}/5 | " +
            " ".join(f"{k[:4]}={v['score']}" for k, v in conv_scores.items())
        )

    # Aggregate
    dim_summary = {}
    for dim_key, scores in dimension_scores.items():
        dim_summary[dim_key] = {
            "name": RUBRICS[dim_key]["name"],
            "mean": round(statistics.mean(scores), 2) if scores else 0,
            "median": round(statistics.median(scores), 1) if scores else 0,
            "std": round(statistics.stdev(scores), 2) if len(scores) > 1 else 0,
            "n": len(scores),
        }

    all_overalls = [r["overall_score"] for r in all_results if r["overall_score"] > 0]
    overall_mean = round(statistics.mean(all_overalls), 2) if all_overalls else 0
    overall_std = round(statistics.stdev(all_overalls), 2) if len(all_overalls) > 1 else 0

    # Output
    timestamp = datetime.now(timezone.utc).isoformat()
    output_path = Path(args.output) if args.output else cpe_dir / f"level2_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    output = {
        "creator": creator,
        "timestamp": timestamp,
        "judge_model": args.judge_model,
        "n_evaluated": len(all_results),
        "overall": {
            "mean": overall_mean,
            "std": overall_std,
            "scale": "1-5",
        },
        "dimensions": dim_summary,
        "conversations": all_results,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Print summary
    print()
    print("=" * 65)
    print(f"  CPE LEVEL 2 — LLM-as-Judge: @{creator}")
    print("=" * 65)
    print(f"  Judge: {args.judge_model}")
    print(f"  Evaluated: {len(all_results)} conversations")
    print(f"  Overall: {overall_mean}/5 (std={overall_std})")
    print()
    print(f"  {'Dimension':<25s} {'Mean':>5s} {'Med':>5s} {'Std':>5s} {'n':>3s}  Bar")
    print(f"  {'-'*55}")
    for dim_key in RUBRICS:
        d = dim_summary[dim_key]
        bar = "#" * int(d["mean"]) + "." * (5 - int(d["mean"]))
        print(f"  {d['name']:<25s} {d['mean']:>5.2f} {d['median']:>5.1f} {d['std']:>5.2f} {d['n']:>3d}  [{bar}]")
    print()
    print(f"  Output: {output_path}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
