"""
CPE Level 2: LLM-as-Judge — Multi-Dimensional Persona Evaluation

Evaluates bot responses across 5 dimensions using structured rubrics
adapted from CharacterEval (Tu et al., 2024) and PersonaGym (Samuel et al., 2024).
Uses the Prometheus 2 ABSOLUTE_PROMPT format with reference answers.

Modes:
  absolute  — 5-dimension scoring (1-5 scale each) with full conversation history
  pairwise  — blind A/B comparison (bot vs reference, randomly assigned)
  both      — run absolute + pairwise sequentially

Judge model: GPT-4o-mini by default (configurable via --judge-model).
Also supports Ollama local models (--judge-model ollama/<model>) and
prometheus-eval library (--judge-model prometheus).

Dimensions (absolute mode, 1-5 scale each):
  1. Conversational Ability — coherence, fluency, contextual consistency
  2. Persona Fidelity — speech patterns, tone, vocabulary, behavioral consistency
  3. Knowledge Accuracy — correctness of facts, avoidance of hallucination
  4. Emotional Intelligence — empathy, emotional perception, appropriate response
  5. Engagement — humanlikeness, avoids generic/assistant patterns, proactive

Default test set: tests/cpe_data/{creator}/test_set_v2_stratified.json (50 cases, ~41 valid text)
Media cases ([audio], [sticker], [image] in test_input/ground_truth) are excluded automatically.

Usage:
    railway run python3 tests/cpe_level2_llm_judge.py --creator iris_bertran
    railway run python3 tests/cpe_level2_llm_judge.py --creator iris_bertran --mode pairwise
    railway run python3 tests/cpe_level2_llm_judge.py --creator iris_bertran --mode both --judge-model gpt-4o
    railway run python3 tests/cpe_level2_llm_judge.py --creator iris_bertran --mode absolute --limit 5
    railway run python3 tests/cpe_level2_llm_judge.py --creator iris_bertran --include-media
"""

import argparse
import asyncio
import json
import logging
import os
import random
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cpe_level2")
logger.setLevel(logging.INFO)

DEFAULT_JUDGE_MODEL = "hf/prometheus"
MAX_HISTORY_TURNS = 20


# =========================================================================
# MEDIA FILTER
# =========================================================================

_MEDIA_RE = re.compile(
    r"\[(audio|sticker|image|video|reel|🏷️\s*Sticker|🎤\s*Audio)\]",
    re.IGNORECASE,
)


def _is_media_case(conv: dict) -> bool:
    """Return True if test_input or ground_truth is a media-only message."""
    test_input = conv.get("test_input", "")
    ground_truth = conv.get("ground_truth", "")
    # A case is media if the entire content is just a media tag (possibly with whitespace)
    for text in (test_input, ground_truth):
        stripped = text.strip()
        if _MEDIA_RE.fullmatch(stripped):
            return True
        # Also catch cases like "[audio]" as the only meaningful content
        if _MEDIA_RE.search(stripped) and len(_MEDIA_RE.sub("", stripped).strip()) == 0:
            return True
    return False


def _filter_media_cases(conversations: List[dict]) -> List[dict]:
    """Filter out cases where test_input or ground_truth is media-only."""
    before = len(conversations)
    filtered = [c for c in conversations if not _is_media_case(c)]
    excluded = before - len(filtered)
    if excluded:
        logger.info(f"Media filter: {before} → {len(filtered)} cases ({excluded} excluded)")
    return filtered


# =========================================================================
# CONVERSATION HISTORY FORMATTER
# =========================================================================

def _format_history(turns: List[dict], creator_name: str) -> str:
    """Format conversation turns for the judge prompt.

    Shows all turns (capped at MAX_HISTORY_TURNS most recent).
    Media turns are replaced with descriptive placeholders.
    """
    if not turns:
        return "(no prior conversation)"

    # Cap at most recent turns if too long
    if len(turns) > MAX_HISTORY_TURNS:
        omitted = len(turns) - MAX_HISTORY_TURNS
        turns = turns[-MAX_HISTORY_TURNS:]
        lines = [f"... ({omitted} earlier turns omitted)"]
    else:
        lines = []

    for t in turns:
        role = t.get("role", "")
        content = t.get("content", "").strip()
        if not content:
            continue

        label = f"[{creator_name}]" if role in ("iris", "assistant") else "[Follower]"

        # Replace media tags with descriptive placeholders
        if _MEDIA_RE.fullmatch(content):
            media_type = _MEDIA_RE.match(content).group(1).lower()
            content = f"(sent a {media_type})"
        elif content.startswith("[🎤 Audio]:"):
            # Transcribed audio — keep the transcription
            content = content.replace("[🎤 Audio]: ", "(voice message) ")
        elif content.startswith("[🏷️ Sticker]"):
            content = "(sent a sticker)"

        lines.append(f"{label} {content}")

    return "\n".join(lines)


# =========================================================================
# RUBRICS (adapted from CharacterEval + PersonaGym, Prometheus 2 format)
# =========================================================================

JUDGE_SYSTEM_PROMPT = (
    "You are a fair judge assistant tasked with providing clear, objective feedback "
    "based on specific criteria, ensuring each assessment reflects the absolute "
    "standards set for performance."
)

RUBRICS = {
    "conversational_ability": {
        "name": "Conversational Ability",
        "rubric": (
            "[Is the response coherent, fluent, and contextually consistent with the conversation history?]\n"
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
# ABSOLUTE MODE: PROMETHEUS 2 ABSOLUTE_PROMPT FORMAT
# =========================================================================

ABSOLUTE_PROMPT = """###Task Description:
An instruction (might include an Input inside it), a response to evaluate, a reference answer that gets a score of 5, and a score rubric representing a evaluation criteria are given.
1. Write a detailed feedback that assess the quality of the response strictly based on the given score rubric, not evaluating in general.
2. After writing a feedback, write a score that is an integer between 1 and 5. You should refer to the score rubric.
3. The output format should look as follows: "(write a feedback for criteria) [RESULT] (an integer number between 1 and 5)"
4. Please do not generate any other opening, closing, and explanations.

###The instruction to evaluate:
You are {creator_name}, a real person who communicates via DMs with followers. A follower sent you this message:
"{lead_message}"

Context about {creator_name}: {creator_profile}

Conversation history ({n_turns} turns):
{history}

###Response to evaluate:
{bot_response}

###Reference Answer (Score 5):
{reference_answer}

###Score Rubrics:
{rubric}

###Feedback:"""


# =========================================================================
# PAIRWISE MODE: BLIND A/B COMPARISON
# =========================================================================

PAIRWISE_PROMPT = """###Task Description:
You are comparing two responses to determine which one sounds more authentically like {creator_name} (a real person communicating via DMs).

A follower sent this message: "{lead_message}"

Context about {creator_name}: {creator_profile}

Conversation history ({n_turns} turns):
{history}

###Response A:
{response_a}

###Response B:
{response_b}

###Evaluation Criteria:
Which response sounds more like a real message from {creator_name}? Consider:
1. Speech patterns, tone, and vocabulary — does it match how {creator_name} actually writes?
2. Emoji usage, code-switching between languages, message length
3. Emotional appropriateness for the context
4. Naturalness — avoids bot-like patterns (numbered lists, "How can I help you?", overly formal language)
5. Specificity — uses concrete details rather than vague/generic responses

###Instructions:
1. Write a brief comparison (2-3 sentences) explaining which response is more authentic and why.
2. End with your verdict: [RESULT] A or [RESULT] B
3. Focus ONLY on authenticity to {creator_name}'s real communication style, not general quality."""


# =========================================================================
# CREATOR PROFILE LOADER
# =========================================================================

def load_creator_profile(creator_id: str) -> str:
    """Load creator profile summary from personality_docs or calibration."""
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
        with psycopg2.connect(os.environ["DATABASE_URL"]) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT pd.content FROM personality_docs pd
                    JOIN creators c ON c.id::text = pd.creator_id
                    WHERE c.name = %s AND pd.doc_type IN ('doc_d_distilled', 'doc_d')
                    ORDER BY CASE pd.doc_type WHEN 'doc_d_distilled' THEN 0 ELSE 1 END
                    LIMIT 1
                """, (creator_id,))
                row = cur.fetchone()
                if row:
                    return row[0][:2000]
    except Exception as e:
        logger.debug(f"DB profile fallback failed: {e}")

    return f"Creator: {creator_id}. No profile available."


# =========================================================================
# JUDGE: ABSOLUTE MODE
# =========================================================================

def judge_single(client, model: str, dimension: str, rubric_info: dict,
                 creator_name: str, creator_profile: str,
                 conv: dict) -> dict:
    """Call LLM judge for one dimension on one conversation (absolute mode)."""
    turns = conv.get("turns", [])
    history_str = _format_history(turns, creator_name)

    prompt = ABSOLUTE_PROMPT.format(
        creator_name=creator_name,
        lead_message=conv.get("test_input", conv.get("lead_message", "")),
        creator_profile=creator_profile[:1500],
        history=history_str,
        n_turns=len(turns),
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
            max_tokens=400,
        )
        raw = response.choices[0].message.content.strip()

        match = re.search(r"\[RESULT\]\s*(\d)", raw)
        score = int(match.group(1)) if match else 0
        feedback = raw.split("[RESULT]")[0].strip() if "[RESULT]" in raw else raw

        return {
            "dimension": dimension,
            "score": min(5, max(1, score)) if score else 0,
            "feedback": feedback[:400],
        }
    except Exception as e:
        logger.warning(f"Judge error ({dimension}): {e}")
        return {"dimension": dimension, "score": 0, "feedback": f"Error: {e}"}


# =========================================================================
# JUDGE: PAIRWISE MODE
# =========================================================================

def judge_pairwise(client, model: str,
                   creator_name: str, creator_profile: str,
                   conv: dict) -> dict:
    """Blind A/B comparison between bot response and ground truth."""
    turns = conv.get("turns", [])
    history_str = _format_history(turns, creator_name)

    bot_response = conv.get("bot_response", "")
    ground_truth = conv.get("ground_truth", "")

    # Randomly assign to A/B
    if random.random() < 0.5:
        response_a, response_b = bot_response, ground_truth
        assignment = "bot_is_A"
    else:
        response_a, response_b = ground_truth, bot_response
        assignment = "bot_is_B"

    prompt = PAIRWISE_PROMPT.format(
        creator_name=creator_name,
        lead_message=conv.get("test_input", conv.get("lead_message", "")),
        creator_profile=creator_profile[:1500],
        history=history_str,
        n_turns=len(turns),
        response_a=response_a,
        response_b=response_b,
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=400,
        )
        raw = response.choices[0].message.content.strip()

        match = re.search(r"\[RESULT\]\s*([AB])", raw)
        verdict_raw = match.group(1) if match else None
        explanation = raw.split("[RESULT]")[0].strip() if "[RESULT]" in raw else raw

        # Map verdict back to bot/reference
        if verdict_raw is None:
            chosen = "inconclusive"
        elif (verdict_raw == "A" and assignment == "bot_is_A") or \
             (verdict_raw == "B" and assignment == "bot_is_B"):
            chosen = "bot"
        else:
            chosen = "reference"

        return {
            "id": conv.get("id", ""),
            "assignment": assignment,
            "verdict_raw": verdict_raw,
            "chosen": chosen,
            "explanation": explanation[:400],
        }
    except Exception as e:
        logger.warning(f"Pairwise judge error: {e}")
        return {
            "id": conv.get("id", ""),
            "assignment": assignment,
            "verdict_raw": None,
            "chosen": "error",
            "explanation": f"Error: {e}",
        }


# =========================================================================
# JUDGE: PROMETHEUS-EVAL LIBRARY (absolute mode only)
# =========================================================================

def _get_prometheus_judge(model_name: str = "gpt-4o-mini"):
    """Initialize prometheus-eval PrometheusEval with LiteLLM backend."""
    from prometheus_eval.litellm import LiteLLM
    from prometheus_eval import PrometheusEval
    from prometheus_eval.prompts import ABSOLUTE_PROMPT as _PROM_ABS

    model = LiteLLM(model_name)
    return PrometheusEval(model=model, absolute_grade_template=_PROM_ABS)


def _build_prometheus_rubric(dimension: str, rubric_info: dict) -> str:
    """Convert our rubric dict to Prometheus SCORE_RUBRIC_TEMPLATE format."""
    from prometheus_eval.prompts import SCORE_RUBRIC_TEMPLATE

    lines = rubric_info["rubric"].strip().split("\n")
    criteria = lines[0].strip("[]") if lines else rubric_info["name"]
    scores = {}
    for line in lines[1:]:
        m = re.match(r"Score (\d): (.+)", line.strip())
        if m:
            scores[int(m.group(1))] = m.group(2)

    return SCORE_RUBRIC_TEMPLATE.format(
        criteria=criteria,
        score1_description=scores.get(1, "Poor"),
        score2_description=scores.get(2, "Below average"),
        score3_description=scores.get(3, "Average"),
        score4_description=scores.get(4, "Good"),
        score5_description=scores.get(5, "Excellent"),
    )


def judge_single_prometheus(prom_judge, dimension: str, rubric_info: dict,
                            creator_name: str, creator_profile: str,
                            conv: dict) -> dict:
    """Evaluate one dimension using prometheus-eval library."""
    turns = conv.get("turns", [])
    history_str = _format_history(turns, creator_name)

    instruction = (
        f"You are {creator_name}, a real person. A follower sent you: "
        f"\"{conv.get('test_input', conv.get('lead_message', ''))}\"\n"
        f"Context: {creator_profile[:800]}\n"
        f"History ({len(turns)} turns): {history_str}"
    )

    rubric = _build_prometheus_rubric(dimension, rubric_info)

    try:
        feedbacks, scores = prom_judge.single_absolute_grade(
            instruction=instruction,
            response=conv.get("bot_response", ""),
            reference_answer=conv.get("ground_truth", "(no reference)"),
            rubric=rubric,
        )
        score = int(scores) if scores else 0
        feedback = str(feedbacks)[:400] if feedbacks else ""

        return {
            "dimension": dimension,
            "score": min(5, max(1, score)) if score else 0,
            "feedback": feedback,
        }
    except Exception as e:
        logger.warning(f"Prometheus judge error ({dimension}): {e}")
        return {"dimension": dimension, "score": 0, "feedback": f"Error: {e}"}


# =========================================================================
# JUDGE: HF INFERENCE API (Prometheus 7B via HuggingFace)
# =========================================================================

def _call_hf_inference(prompt: str, hf_token: str, model: str, max_tokens: int = 400) -> Optional[str]:
    """Call HuggingFace Inference API synchronously."""
    import urllib.request
    import urllib.error

    url = f"https://api-inference.huggingface.co/models/{model}"
    headers = {
        "Authorization": f"Bearer {hf_token}",
        "Content-Type": "application/json",
    }
    payload = json.dumps({
        "inputs": prompt,
        "parameters": {"max_new_tokens": max_tokens, "temperature": 0.1, "return_full_text": False},
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            # HF returns {"error": "Model is loading", "estimated_time": N} on cold start
            if isinstance(data, dict) and "error" in data:
                est = data.get("estimated_time", "?")
                logger.info(f"HF model loading: {data['error']} (est {est}s), will use fallback")
                return None
            if isinstance(data, list) and data:
                return data[0].get("generated_text", "")
            return None
    except urllib.error.HTTPError as e:
        if e.code == 503:
            logger.info(f"HF model loading (503), will use fallback")
        else:
            logger.warning(f"HF API error {e.code}: {e.read().decode()[:200]}")
        return None
    except Exception as e:
        logger.warning(f"HF API call failed: {e}")
        return None


def _call_gemini_fallback(prompt: str) -> Optional[str]:
    """Call Gemini Flash Lite as fallback judge.

    Handles both sync and async calling contexts safely.
    """
    import asyncio
    import concurrent.futures

    try:
        from core.providers.gemini_provider import generate_simple
    except ImportError as e:
        logger.warning(f"Gemini provider not available: {e}")
        return None

    async def _do_call():
        return await generate_simple(
            prompt=prompt,
            system_prompt=JUDGE_SYSTEM_PROMPT,
            max_tokens=400,
            temperature=0.1,
        )

    try:
        # If we're inside an async event loop (main() is async), run in a thread
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(asyncio.run, _do_call()).result(timeout=30)
        return result
    except RuntimeError:
        # No running loop — safe to use asyncio.run directly
        pass

    try:
        return asyncio.run(_do_call())
    except Exception as e:
        logger.warning(f"Gemini fallback failed: {e}")
        return None


def judge_single_hf(
    dimension: str, rubric_info: dict,
    creator_name: str, creator_profile: str,
    conv: dict,
    hf_token: str, hf_model: str,
) -> dict:
    """Judge one dimension using HF Inference API (Prometheus) with Gemini fallback."""
    turns = conv.get("turns", [])
    history_str = _format_history(turns, creator_name)

    prompt = ABSOLUTE_PROMPT.format(
        creator_name=creator_name,
        lead_message=conv.get("test_input", conv.get("lead_message", "")),
        creator_profile=creator_profile[:1500],
        history=history_str,
        n_turns=len(turns),
        bot_response=conv.get("bot_response", ""),
        reference_answer=conv.get("ground_truth", "(no reference available)"),
        rubric=rubric_info["rubric"],
    )

    full_prompt = f"{JUDGE_SYSTEM_PROMPT}\n\n{prompt}"
    judge_used = "prometheus"

    # Try Prometheus via HF
    raw = _call_hf_inference(full_prompt, hf_token, hf_model)

    # Fallback to Gemini
    if not raw:
        judge_used = "gemini_fallback"
        raw = _call_gemini_fallback(prompt)

    if not raw:
        return {"dimension": dimension, "score": 0, "feedback": "Both Prometheus and Gemini failed", "judge_used": "none"}

    match = re.search(r"\[RESULT\]\s*(\d)", raw)
    score = int(match.group(1)) if match else 0
    feedback = raw.split("[RESULT]")[0].strip() if "[RESULT]" in raw else raw

    return {
        "dimension": dimension,
        "score": min(5, max(1, score)) if score else 0,
        "feedback": feedback[:400],
        "judge_used": judge_used,
    }


def judge_pairwise_hf(
    creator_name: str, creator_profile: str,
    conv: dict,
    hf_token: str, hf_model: str,
) -> dict:
    """Pairwise blind A/B using HF Inference API (Prometheus) with Gemini fallback."""
    turns = conv.get("turns", [])
    history_str = _format_history(turns, creator_name)

    bot_response = conv.get("bot_response", "")
    ground_truth = conv.get("ground_truth", "")

    if random.random() < 0.5:
        response_a, response_b = bot_response, ground_truth
        assignment = "bot_is_A"
    else:
        response_a, response_b = ground_truth, bot_response
        assignment = "bot_is_B"

    prompt = PAIRWISE_PROMPT.format(
        creator_name=creator_name,
        lead_message=conv.get("test_input", conv.get("lead_message", "")),
        creator_profile=creator_profile[:1500],
        history=history_str,
        n_turns=len(turns),
        response_a=response_a,
        response_b=response_b,
    )

    full_prompt = f"{JUDGE_SYSTEM_PROMPT}\n\n{prompt}"
    judge_used = "prometheus"

    raw = _call_hf_inference(full_prompt, hf_token, hf_model)
    if not raw:
        judge_used = "gemini_fallback"
        raw = _call_gemini_fallback(prompt)

    if not raw:
        return {
            "id": conv.get("id", ""),
            "assignment": assignment,
            "verdict_raw": None,
            "chosen": "error",
            "explanation": "Both Prometheus and Gemini failed",
            "judge_used": "none",
        }

    match = re.search(r"\[RESULT\]\s*([AB])", raw)
    verdict_raw = match.group(1) if match else None
    explanation = raw.split("[RESULT]")[0].strip() if "[RESULT]" in raw else raw

    if verdict_raw is None:
        chosen = "inconclusive"
    elif (verdict_raw == "A" and assignment == "bot_is_A") or \
         (verdict_raw == "B" and assignment == "bot_is_B"):
        chosen = "bot"
    else:
        chosen = "reference"

    return {
        "id": conv.get("id", ""),
        "assignment": assignment,
        "verdict_raw": verdict_raw,
        "chosen": chosen,
        "explanation": explanation[:400],
        "judge_used": judge_used,
    }


# =========================================================================
# PIPELINE RUNNER
# =========================================================================

def _get_platform_user_id(lead_id: str) -> Optional[str]:
    try:
        from api.database import SessionLocal
        from api.models import Lead
        with SessionLocal() as session:
            row = session.query(Lead.platform_user_id).filter_by(id=lead_id).first()
            return row[0] if row and row[0] else None
    except Exception:
        return None


async def run_pipeline(creator_id: str, conversations: List[Dict]) -> List[Dict]:
    """Run production DM pipeline on test cases."""
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
    parser.add_argument("--mode", choices=["absolute", "pairwise", "both"], default="absolute",
                        help="Evaluation mode (default: absolute)")
    parser.add_argument("--test-set", default=None, help="Custom test set path")
    parser.add_argument("--responses", default=None, help="Reuse responses from existing file (skip pipeline)")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL, help="Judge model (default: gpt-4o-mini)")
    parser.add_argument("--output", default=None, help="Custom output path")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of test cases")
    parser.add_argument("--include-media", action="store_true", help="Include media cases (normally filtered)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for pairwise A/B assignment")
    args = parser.parse_args()

    random.seed(args.seed)

    creator = args.creator
    cpe_dir = REPO_ROOT / "tests" / "cpe_data" / creator / "results"
    cpe_dir.mkdir(parents=True, exist_ok=True)

    # ---- Load test set ----
    if args.responses:
        with open(args.responses) as f:
            prev = json.load(f)
        conversations = prev if isinstance(prev, list) else prev.get("conversations", [])
        # Normalize field names
        normalized = []
        for c in conversations:
            if "input" in c and "test_input" not in c:
                c = dict(c)
                c["test_input"] = c.pop("input")
            if "creator_real_response" in c and "ground_truth" not in c:
                c = dict(c)
                c["ground_truth"] = c.pop("creator_real_response")
            normalized.append(c)
        conversations = normalized

        # Enrich missing ground_truth from test_set if available
        missing_gt = sum(1 for c in conversations if not c.get("ground_truth"))
        if missing_gt > 0:
            for ts_name in ["test_set_v2_stratified.json", "test_set.json"]:
                ts_path = REPO_ROOT / "tests" / "cpe_data" / creator / ts_name
                if ts_path.exists():
                    with open(ts_path) as f:
                        ts_data = json.load(f)
                    ts_items = ts_data if isinstance(ts_data, list) else ts_data.get("test_cases", ts_data.get("conversations", []))
                    gt_map = {}
                    for t in ts_items:
                        key = t.get("id", t.get("test_input", ""))
                        gt = t.get("ground_truth", t.get("creator_real_response", ""))
                        if key and gt:
                            gt_map[key] = gt
                        inp = t.get("test_input", "")
                        if inp and gt:
                            gt_map[inp] = gt

                    filled = 0
                    for c in conversations:
                        if not c.get("ground_truth"):
                            gt = gt_map.get(c.get("id", "")) or gt_map.get(c.get("test_input", ""))
                            if gt:
                                c["ground_truth"] = gt
                                filled += 1
                    if filled:
                        logger.info(f"Enriched {filled}/{missing_gt} missing ground_truths from {ts_name}")
                        break

        logger.info(f"Reusing {len(conversations)} responses from {args.responses}")
    else:
        # Default: stratified test set per creator
        test_path = (
            Path(args.test_set) if args.test_set
            else REPO_ROOT / "tests" / "cpe_data" / creator / "test_set_v2_stratified.json"
        )
        with open(test_path) as f:
            data = json.load(f)
        conversations = data if isinstance(data, list) else data.get("conversations", data.get("test_cases", []))

        if args.limit:
            conversations = conversations[:args.limit]

        logger.info(f"Running pipeline on {len(conversations)} conversations...")
        conversations = await run_pipeline(creator, conversations)

    # ---- Media filter ----
    total_loaded = len(conversations)
    if not args.include_media:
        conversations = _filter_media_cases(conversations)
    logger.info(f"Test cases: {len(conversations)} valid (from {total_loaded} loaded)")

    if args.limit and len(conversations) > args.limit:
        conversations = conversations[:args.limit]

    # ---- Load creator profile ----
    creator_profile = load_creator_profile(creator)
    creator_name = creator.replace("_", " ").title()
    logger.info(f"Creator profile loaded: {len(creator_profile)} chars")

    # ---- Initialize judge ----
    # Modes: "hf" (HF Inference API), "prometheus" (prometheus-eval lib), "ollama", "openai"
    judge_model_original = args.judge_model
    judge_model_resolved = args.judge_model
    judge_backend = "openai"  # default
    prom_judge = None
    client = None
    hf_token = os.environ.get("HF_TOKEN", "")
    hf_model = os.environ.get("PROMETHEUS_MODEL", "prometheus-eval/prometheus-7b-v2.0")

    if args.judge_model.startswith("hf/"):
        judge_backend = "hf"
        # Parse model from arg: "hf/prometheus" uses env var, "hf/org/model" uses that model
        hf_arg_model = args.judge_model[3:]  # strip "hf/"
        if hf_arg_model and hf_arg_model != "prometheus" and "/" in hf_arg_model:
            hf_model = hf_arg_model  # user specified a custom HF model
        # else: use PROMETHEUS_MODEL env var (default)
        judge_model_resolved = hf_model
        if not hf_token:
            logger.warning("HF_TOKEN not set — will use Gemini fallback for all calls")
        logger.info(f"Using HF Inference API: {hf_model} (fallback: Gemini)")
    elif args.judge_model.startswith("ollama/"):
        judge_backend = "ollama"
        from openai import OpenAI
        judge_model_resolved = args.judge_model.replace("ollama/", "", 1)
        client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
        logger.info(f"Using Ollama local model: {judge_model_resolved}")
    elif args.judge_model.startswith("prometheus") or args.judge_model == "prometheus":
        judge_backend = "prometheus_lib"
        backend = "gpt-4o-mini"
        if "/" in args.judge_model:
            backend = args.judge_model
        try:
            prom_judge = _get_prometheus_judge(backend)
            logger.info(f"Using prometheus-eval library with backend: {backend}")
        except (ImportError, Exception) as e:
            logger.warning(f"prometheus-eval unavailable ({e}), falling back to HF API")
            judge_backend = "hf"
            judge_model_resolved = hf_model
    else:
        # OpenAI models (gpt-4o-mini, gpt-4o, etc.)
        judge_backend = "openai"
        from openai import OpenAI
        client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    mode = args.mode
    is_local = (judge_backend == "ollama")
    rate_delay = 0.0 if is_local else 0.3

    # ==== ABSOLUTE MODE ====
    absolute_output = {}
    if mode in ("absolute", "both"):
        all_results = []
        dimension_scores = {d: [] for d in RUBRICS}

        for i, conv in enumerate(conversations, 1):
            if not conv.get("bot_response"):
                logger.warning(f"[{conv.get('id', i)}] No bot_response, skipping")
                continue

            conv_scores = {}
            for dim_key, rubric_info in RUBRICS.items():
                if judge_backend == "hf":
                    result = judge_single_hf(
                        dim_key, rubric_info,
                        creator_name, creator_profile, conv,
                        hf_token, hf_model,
                    )
                elif judge_backend == "prometheus_lib" and prom_judge:
                    result = judge_single_prometheus(
                        prom_judge, dim_key, rubric_info,
                        creator_name, creator_profile, conv,
                    )
                else:
                    result = judge_single(
                        client, judge_model_resolved, dim_key, rubric_info,
                        creator_name, creator_profile, conv,
                    )
                conv_scores[dim_key] = result
                if result["score"] > 0:
                    dimension_scores[dim_key].append(result["score"])
                if rate_delay:
                    time.sleep(rate_delay)

            valid_scores = [v["score"] for v in conv_scores.values() if v["score"] > 0]
            overall = round(sum(valid_scores) / len(valid_scores), 2) if valid_scores else 0

            all_results.append({
                "id": conv.get("id", f"conv_{i}"),
                "test_input": conv.get("test_input", conv.get("lead_message", "")),
                "bot_response": conv.get("bot_response", ""),
                "ground_truth": conv.get("ground_truth", ""),
                "category": conv.get("category", ""),
                "overall_score": overall,
                "dimensions": conv_scores,
                "elapsed_ms": conv.get("elapsed_ms", 0),
            })

            logger.info(
                f"[ABS {i}/{len(conversations)}] {conv.get('id', '?')}: "
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

        absolute_output = {
            "n_evaluated": len(all_results),
            "overall": {"mean": overall_mean, "std": overall_std, "scale": "1-5"},
            "dimensions": dim_summary,
            "conversations": all_results,
        }

    # ==== PAIRWISE MODE ====
    pairwise_output = {}
    if mode in ("pairwise", "both"):
        pairwise_results = []
        bot_wins = 0
        ref_wins = 0
        inconclusive = 0
        a_chosen = 0
        b_chosen = 0

        for i, conv in enumerate(conversations, 1):
            if not conv.get("bot_response") or not conv.get("ground_truth"):
                logger.warning(f"[{conv.get('id', i)}] Missing bot_response or ground_truth, skipping pairwise")
                continue

            if judge_backend in ("hf", "prometheus_lib"):
                # HF and prometheus_lib both use HF API for pairwise (no native pairwise in prometheus-eval)
                result = judge_pairwise_hf(
                    creator_name, creator_profile, conv,
                    hf_token, hf_model,
                )
            elif judge_backend in ("openai", "ollama"):
                if not client:
                    from openai import OpenAI
                    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
                result = judge_pairwise(client, judge_model_resolved, creator_name, creator_profile, conv)

            pairwise_results.append(result)

            if result["chosen"] == "bot":
                bot_wins += 1
            elif result["chosen"] == "reference":
                ref_wins += 1
            else:
                inconclusive += 1

            if result["verdict_raw"] == "A":
                a_chosen += 1
            elif result["verdict_raw"] == "B":
                b_chosen += 1

            logger.info(
                f"[PAIR {i}/{len(conversations)}] {conv.get('id', '?')}: "
                f"chosen={result['chosen']} (verdict={result['verdict_raw']}, {result['assignment']})"
            )

            if rate_delay:
                time.sleep(rate_delay)

        total_decided = bot_wins + ref_wins
        win_rate = round(bot_wins / total_decided, 3) if total_decided else 0

        pairwise_output = {
            "summary": {
                "bot_wins": bot_wins,
                "reference_wins": ref_wins,
                "inconclusive": inconclusive,
                "win_rate": win_rate,
                "positional_bias_check": {"A_chosen": a_chosen, "B_chosen": b_chosen},
            },
            "details": pairwise_results,
        }

    # ==== OUTPUT ====
    timestamp = datetime.now(timezone.utc).isoformat()
    mode_suffix = f"_{mode}" if mode != "absolute" else ""
    output_path = (
        Path(args.output) if args.output
        else cpe_dir / f"level2{mode_suffix}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    )

    output = {
        "creator": creator,
        "timestamp": timestamp,
        "judge_model": judge_model_original,
        "mode": mode,
        "seed": args.seed,
        "n_cases_loaded": total_loaded,
        "n_cases_after_filter": len(conversations),
        "media_filter": not args.include_media,
    }
    if absolute_output:
        output["absolute"] = absolute_output
    if pairwise_output:
        output["pairwise"] = pairwise_output

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # ==== PRINT SUMMARY ====
    print()
    print("=" * 65)
    print(f"  CPE LEVEL 2 — LLM-as-Judge: @{creator}")
    print("=" * 65)
    print(f"  Judge: {judge_model_original} | Mode: {mode} | Seed: {args.seed}")
    print(f"  Cases: {len(conversations)} valid (from {total_loaded} loaded)")
    print()

    if absolute_output:
        ao = absolute_output
        print(f"  ABSOLUTE SCORING (1-5)")
        print(f"  Overall: {ao['overall']['mean']}/5 (std={ao['overall']['std']})")
        print()
        print(f"  {'Dimension':<25s} {'Mean':>5s} {'Med':>5s} {'Std':>5s} {'n':>3s}  Bar")
        print(f"  {'-'*55}")
        for dim_key in RUBRICS:
            d = ao["dimensions"][dim_key]
            bar = "#" * int(d["mean"]) + "." * (5 - int(d["mean"]))
            print(f"  {d['name']:<25s} {d['mean']:>5.2f} {d['median']:>5.1f} {d['std']:>5.2f} {d['n']:>3d}  [{bar}]")
        print()

    if pairwise_output:
        ps = pairwise_output["summary"]
        total_decided = ps["bot_wins"] + ps["reference_wins"]
        print(f"  PAIRWISE COMPARISON (blind A/B)")
        print(f"  Bot wins: {ps['bot_wins']}/{total_decided} ({ps['win_rate']*100:.1f}%)"
              f"  |  Reference wins: {ps['reference_wins']}/{total_decided}"
              f" ({(1-ps['win_rate'])*100:.1f}%)" if total_decided else "  No decided comparisons")
        if ps["inconclusive"]:
            print(f"  Inconclusive: {ps['inconclusive']}")
        bias = ps["positional_bias_check"]
        total_pos = bias["A_chosen"] + bias["B_chosen"]
        if total_pos:
            a_pct = bias["A_chosen"] / total_pos * 100
            bias_ok = "no bias" if 35 < a_pct < 65 else "POSITIONAL BIAS DETECTED"
            print(f"  Position check: A={bias['A_chosen']} B={bias['B_chosen']} ({bias_ok})")
        print()

    print(f"  Output: {output_path}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
