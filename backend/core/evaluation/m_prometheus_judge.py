"""
M-Prometheus 14B LLM Judge (B2, B5, C2, C3, H1)

Uses M-Prometheus 14B (Q6_K) via local Ollama for evaluation.
Based on Prometheus evaluation format: instruction + response + reference + rubric.

Params measured:
  B2 — Persona Consistency (direct assessment 1-5)
  B5 — Emotional Signature (direct assessment 1-5)
  C2 — Naturalness (direct assessment 1-5)
  C3 — Contextual Appropriateness (direct assessment 1-5)
  H1 — TTR Turing Test Rate (pairwise comparison)
"""

import json
import logging
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# Model config
OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL_NAME = "hf.co/mradermacher/M-Prometheus-14B-GGUF:Q6_K"
TIMEOUT = 180  # seconds per call (CPU inference is slow)
MAX_RETRIES = 2

# ---------------------------------------------------------------------------
# Rubrics (Spanish — matches content language)
# ---------------------------------------------------------------------------

RUBRIC_B2 = """\
5 = Tono perfectamente consistente con una profesora de fitness/danza en Barcelona \
que mezcla catalán y español, vocabulario natural, mezcla idiomática creíble
4 = Mayormente consistente, algún desliz menor en el tono o idioma
3 = Parcialmente consistente, mezcla de registros o tono genérico
2 = Inconsistente, cambia de personalidad o suena impersonal
1 = Completamente fuera de personaje"""

RUBRIC_B5 = """\
5 = Emoción perfecta para el contexto, reacción natural y cercana
4 = Emoción mayormente apropiada, algún matiz incorrecto
3 = Emoción neutra o genérica, no destaca ni molesta
2 = Emoción inapropiada para el contexto
1 = Sin emoción o completamente errónea"""

RUBRIC_C2 = """\
5 = Completamente natural, indistinguible de un mensaje de DM humano
4 = Natural con algún detalle ligeramente artificial
3 = Aceptable pero se nota generado por IA
2 = Claramente artificial, lenguaje demasiado formal o estructurado
1 = Obviamente un bot"""

RUBRIC_C3 = """\
5 = Perfectamente apropiada en contenido y tono para el contexto
4 = Apropiada con algún detalle menor fuera de contexto
3 = Parcialmente apropiada, alguna desconexión con el tema
2 = Mayormente inapropiada para la conversación
1 = Completamente fuera de contexto"""


# ---------------------------------------------------------------------------
# Core Ollama call
# ---------------------------------------------------------------------------

def _call_ollama(prompt: str) -> Optional[str]:
    """Call Ollama with M-Prometheus model. Returns raw text or None."""
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 1024},
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("message", {}).get("content", "")
        else:
            logger.warning(f"Ollama returned {resp.status_code}: {resp.text[:200]}")
    except requests.exceptions.Timeout:
        logger.warning(f"Ollama timeout after {TIMEOUT}s")
    except Exception as e:
        logger.warning(f"Ollama error: {e}")
    return None


def _parse_result_score(text: str) -> Optional[int]:
    """Extract [RESULT] N from Prometheus-format output."""
    if not text:
        return None
    # Primary: [RESULT] N
    m = re.search(r'\[RESULT\]\s*(\d)', text)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 5:
            return val
    # Fallback: "score is N" or "overall score is N"
    m = re.search(r'(?:score|puntuación|nota)\s+(?:is|es|de)\s+(\d)', text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 5:
            return val
    # Last resort: "So the overall score is N."
    m = re.search(r'score is (\d)', text)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 5:
            return val
    return None


def _parse_pairwise_result(text: str) -> Optional[str]:
    """Extract [RESULT] A or B from pairwise output."""
    if not text:
        return None
    m = re.search(r'\[RESULT\]\s*([AB])', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # Fallback
    m = re.search(r'(?:better|mejor|choose|elijo)\s+(?:response\s+)?([AB])', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return None


def _score_to_100(score_1_5: Optional[int]) -> float:
    """Convert 1-5 to 0-100 scale."""
    if score_1_5 is None:
        return 50.0
    return (score_1_5 - 1) * 25.0


# ---------------------------------------------------------------------------
# Prometheus prompt builders
# ---------------------------------------------------------------------------

def _build_direct_prompt(
    instruction: str,
    response: str,
    reference: str,
    rubric: str,
) -> str:
    return f"""###Task Description:
An instruction (might include an Input inside it), a response to evaluate, a reference answer that gets a score of 5, and a score rubric representing an evaluation criteria are given.
1. Write a detailed feedback that assesses the quality of the response strictly based on the given score rubric, not evaluating in general.
2. After writing a feedback, write a score that is an integer between 1 and 5.
3. The output format should look as follows: "Feedback: (write a feedback) [RESULT] (an integer between 1 and 5)"
4. Please do not generate any other opening, closing, or explanations.

###Instruction:
{instruction}

###Response to evaluate:
{response}

###Reference Answer (Score 5):
{reference}

###Score Rubric:
{rubric}

###Feedback:"""


def _build_pairwise_prompt(
    instruction: str,
    response_a: str,
    response_b: str,
) -> str:
    return f"""###Task Description:
An instruction and two responses are given. Compare and determine which response was more likely written by a real human (not an AI).
Write detailed feedback explaining your choice.
The output format: "Feedback: (feedback) [RESULT] A or B"

###Instruction:
{instruction}

###Response A:
{response_a}

###Response B:
{response_b}

###Feedback:"""


# ---------------------------------------------------------------------------
# Individual judge functions
# ---------------------------------------------------------------------------

def judge_persona_consistency(
    bot_response: str,
    reference: str,
    user_message: str,
) -> Tuple[float, str]:
    """B2: Persona consistency (0-100). Returns (score, feedback)."""
    instruction = (
        f"Responde como una profesora de fitness y danza en Barcelona que mezcla "
        f"catalán y español en sus DMs de Instagram.\n"
        f"Mensaje del lead: {user_message}"
    )
    prompt = _build_direct_prompt(instruction, bot_response, reference, RUBRIC_B2)

    for attempt in range(MAX_RETRIES):
        t0 = time.time()
        raw = _call_ollama(prompt)
        elapsed = time.time() - t0
        if raw:
            score = _parse_result_score(raw)
            if score is not None:
                logger.info(f"B2: score={score}, time={elapsed:.1f}s")
                return _score_to_100(score), raw
            logger.warning(f"B2 parse failed (attempt {attempt+1}): {raw[:100]}")
    return 50.0, "parse_failed"


def judge_emotional_signature(
    bot_response: str,
    reference: str,
    user_message: str,
) -> Tuple[float, str]:
    """B5: Emotional signature match (0-100). Returns (score, feedback)."""
    instruction = (
        f"Evalúa si la respuesta tiene la reacción emocional apropiada para este "
        f"contexto, similar a cómo respondería una persona cercana y directa.\n"
        f"Mensaje del lead: {user_message}"
    )
    prompt = _build_direct_prompt(instruction, bot_response, reference, RUBRIC_B5)

    for attempt in range(MAX_RETRIES):
        t0 = time.time()
        raw = _call_ollama(prompt)
        elapsed = time.time() - t0
        if raw:
            score = _parse_result_score(raw)
            if score is not None:
                logger.info(f"B5: score={score}, time={elapsed:.1f}s")
                return _score_to_100(score), raw
            logger.warning(f"B5 parse failed (attempt {attempt+1}): {raw[:100]}")
    return 50.0, "parse_failed"


def judge_naturalness(
    bot_response: str,
    reference: str,
) -> Tuple[float, str]:
    """C2: Naturalness (0-100). Returns (score, feedback)."""
    instruction = (
        "Evalúa si esta respuesta suena como un mensaje de DM de Instagram "
        "escrito por una persona real, no por un bot."
    )
    prompt = _build_direct_prompt(instruction, bot_response, reference, RUBRIC_C2)

    for attempt in range(MAX_RETRIES):
        t0 = time.time()
        raw = _call_ollama(prompt)
        elapsed = time.time() - t0
        if raw:
            score = _parse_result_score(raw)
            if score is not None:
                logger.info(f"C2: score={score}, time={elapsed:.1f}s")
                return _score_to_100(score), raw
            logger.warning(f"C2 parse failed (attempt {attempt+1}): {raw[:100]}")
    return 50.0, "parse_failed"


def judge_contextual_appropriateness(
    bot_response: str,
    reference: str,
    user_message: str,
    history: str = "",
) -> Tuple[float, str]:
    """C3: Contextual appropriateness (0-100). Returns (score, feedback)."""
    ctx = f"\nHistorial:\n{history}" if history else ""
    instruction = (
        f"Dado el mensaje del lead y el contexto, evalúa si la respuesta es "
        f"apropiada en contenido y tono.{ctx}\n"
        f"Mensaje del lead: {user_message}"
    )
    prompt = _build_direct_prompt(instruction, bot_response, reference, RUBRIC_C3)

    for attempt in range(MAX_RETRIES):
        t0 = time.time()
        raw = _call_ollama(prompt)
        elapsed = time.time() - t0
        if raw:
            score = _parse_result_score(raw)
            if score is not None:
                logger.info(f"C3: score={score}, time={elapsed:.1f}s")
                return _score_to_100(score), raw
            logger.warning(f"C3 parse failed (attempt {attempt+1}): {raw[:100]}")
    return 50.0, "parse_failed"


def judge_turing_test(
    bot_response: str,
    real_response: str,
    user_message: str,
    seed: int = 42,
) -> Tuple[bool, str, str]:
    """H1: Turing test (pairwise). Returns (bot_picked_as_human, chosen, feedback).

    Randomly assigns bot to A or B position (seeded for reproducibility).
    Returns True if the judge picks the BOT as the human-written one.
    """
    rng = random.Random(seed)
    bot_is_a = rng.random() < 0.5

    if bot_is_a:
        resp_a, resp_b = bot_response, real_response
    else:
        resp_a, resp_b = real_response, bot_response

    instruction = (
        f"Lee el mensaje del lead y las dos respuestas. Determina cuál fue "
        f"escrita por una persona real (no por IA).\n"
        f"Mensaje del lead: {user_message}"
    )
    prompt = _build_pairwise_prompt(instruction, resp_a, resp_b)

    for attempt in range(MAX_RETRIES):
        t0 = time.time()
        raw = _call_ollama(prompt)
        elapsed = time.time() - t0
        if raw:
            chosen = _parse_pairwise_result(raw)
            if chosen:
                # Bot picked as human = judge chose the position where bot is
                bot_picked = (chosen == "A" and bot_is_a) or (chosen == "B" and not bot_is_a)
                logger.info(f"H1: chosen={chosen}, bot_is_A={bot_is_a}, fooled={bot_picked}, time={elapsed:.1f}s")
                return bot_picked, chosen, raw
            logger.warning(f"H1 parse failed (attempt {attempt+1}): {raw[:100]}")
    return False, "?", "parse_failed"


# ---------------------------------------------------------------------------
# Batch evaluation
# ---------------------------------------------------------------------------

def evaluate_all_params(
    cases: List[Dict],
    max_cases: int = 20,
) -> Dict[str, Any]:
    """Run all 5 judge params on a list of per_case_records.

    Each case dict must have: bot_response, ground_truth, user_input (or test_input).
    Returns aggregate scores and per-case details.
    """
    # Limit cases for CPU performance
    eval_cases = cases[:max_cases]
    n = len(eval_cases)
    print(f"  Evaluating {n} cases with M-Prometheus 14B...")

    b2_scores, b5_scores, c2_scores, c3_scores = [], [], [], []
    h1_results = []
    per_case = []
    total_start = time.time()

    for i, case in enumerate(eval_cases):
        bot_resp = case.get("bot_response", "")
        ground_truth = case.get("ground_truth", case.get("iris_real_response", ""))
        user_msg = case.get("user_input", case.get("test_input", ""))

        if not bot_resp or not ground_truth:
            continue

        case_start = time.time()

        # B2: Persona consistency
        b2, b2_fb = judge_persona_consistency(bot_resp, ground_truth, user_msg)
        b2_scores.append(b2)

        # B5: Emotional signature
        b5, b5_fb = judge_emotional_signature(bot_resp, ground_truth, user_msg)
        b5_scores.append(b5)

        # C2: Naturalness
        c2, c2_fb = judge_naturalness(bot_resp, ground_truth)
        c2_scores.append(c2)

        # C3: Contextual appropriateness
        c3, c3_fb = judge_contextual_appropriateness(bot_resp, ground_truth, user_msg)
        c3_scores.append(c3)

        # H1: Turing test
        h1_fooled, h1_chosen, h1_fb = judge_turing_test(
            bot_resp, ground_truth, user_msg, seed=42 + i
        )
        h1_results.append(h1_fooled)

        case_time = time.time() - case_start
        print(
            f"  Case {i+1}/{n} | B2={b2:.0f} B5={b5:.0f} C2={c2:.0f} C3={c3:.0f} "
            f"H1={'✓' if h1_fooled else '✗'} | {case_time:.1f}s"
        )

        per_case.append({
            "case_idx": i,
            "B2": b2, "B5": b5, "C2": c2, "C3": c3,
            "H1_fooled": h1_fooled,
        })

    total_time = time.time() - total_start

    def _mean(lst):
        return round(sum(lst) / max(len(lst), 1), 2)

    h1_rate = sum(1 for x in h1_results if x) / max(len(h1_results), 1) * 100

    return {
        "B2_persona_consistency": _mean(b2_scores),
        "B5_emotional_signature": _mean(b5_scores),
        "C2_naturalness": _mean(c2_scores),
        "C3_contextual_appropriateness": _mean(c3_scores),
        "H1_turing_test_rate": round(h1_rate, 1),
        "n_cases": n,
        "total_time_seconds": round(total_time, 1),
        "model": MODEL_NAME,
        "per_case": per_case,
    }
