"""
LLM Judge (B2, B5, C2, C3, H1)

Single backend: Qwen3-30B-A3B via DeepInfra.

Same Prometheus rubric format: instruction + response + reference + rubric.
Drop-in replacement for the previous M-Prometheus 14B / Ollama implementation.

Params measured:
  B2 — Persona Consistency (direct assessment 1-5)
  B5 — Emotional Signature (direct assessment 1-5)
  C2 — Naturalness (direct assessment 1-5)
  C3 — Contextual Appropriateness (direct assessment 1-5)
  H1 — TTR Turing Test Rate (pairwise comparison)
"""

import logging
import os
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import openai

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider config — DeepInfra / Qwen3-30B-A3B only
# ---------------------------------------------------------------------------

_DEEPINFRA_MODEL = "Qwen/Qwen3-30B-A3B"
_DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/openai"
_DEEPINFRA_COST_PER_1K_INPUT  = 0.00008   # $0.08 per 1M input tokens
_DEEPINFRA_COST_PER_1K_OUTPUT = 0.00028   # $0.28 per 1M output tokens

MODEL_NAME = _DEEPINFRA_MODEL

TIMEOUT = 30
MAX_RETRIES = 3

# Cost tracking (cumulative for this session)
_total_input_tokens = 0
_total_output_tokens = 0
_total_cost_usd = 0.0


# ---------------------------------------------------------------------------
# Rubrics (Spanish — matches content language)
# ---------------------------------------------------------------------------

_RUBRIC_B2_TEMPLATE = """\
[5] Tono perfectamente consistente con el perfil del creator descrito arriba. \
Lenguaje, mezcla idiomática, registro y estilo son indistinguibles del creator real.
[4] Mayormente consistente con el perfil. Algún desliz menor en el tono, idioma o registro, \
pero la respuesta se siente del creator.
[3] No viola el perfil, pero tampoco lo demuestra. Respuesta genérica y amigable \
que cualquier persona podría escribir — sin marcadores específicos del creator.
[2] Elementos que no encajan con el perfil del creator: registro incorrecto, \
nivel de formalidad inadecuado, o faltan marcadores clave de la persona.
[1] Claramente no corresponde al perfil: idioma incorrecto, tono opuesto, \
o contradice directamente la persona del creator.

IMPORTANT: Do NOT default to score 3 when unsure.
- Wrong language or opposite tone for the creator = score 1
- Right language but robotic/formal when creator is informal = score 2
- Generic but acceptable = score 3
- Some creator-specific markers present = score 4
- Indistinguishable from the real creator = score 5"""


def _build_rubric_b2(creator_summary: str = "", doc_d_text: str = "", creator_id: str = "") -> str:
    """Build dynamic B2 rubric. Injects creator summary and exemplar calibration if available."""
    if creator_summary:
        header = f"=== CREATOR PROFILE ===\n{creator_summary}\n\n=== RUBRIC ===\n"
    else:
        header = ""

    # Try exemplar calibration (PersonaGym methodology)
    if doc_d_text or creator_id:
        try:
            from core.evaluation.exemplar_generator import get_exemplar_rubric_block
            _d = doc_d_text or creator_summary
            if _d:
                exemplar_rubric = get_exemplar_rubric_block(_d, creator_id=creator_id, base_rubric=_RUBRIC_B2_TEMPLATE)
                if exemplar_rubric and exemplar_rubric != _RUBRIC_B2_TEMPLATE:
                    return header + exemplar_rubric
        except Exception as e:
            logger.warning(f"B2 exemplar generation failed, using base rubric: {e}")

    return header + _RUBRIC_B2_TEMPLATE

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


_SYSTEM_PROMPT = (
    "You are an expert evaluator. After your analysis, "
    "you MUST end your response with exactly: [RESULT] N "
    "(where N is your score 1-5). This format is mandatory."
)


# ---------------------------------------------------------------------------
# Backend: DeepInfra / Qwen3-30B-A3B
# ---------------------------------------------------------------------------

def _call_deepinfra(prompt: str, max_tokens: int = 1500) -> Optional[str]:
    """Call Qwen3-30B-A3B via DeepInfra (OpenAI-compatible). Returns raw text or None."""
    global _total_input_tokens, _total_output_tokens, _total_cost_usd
    api_key = os.environ.get("DEEPINFRA_API_KEY") or os.environ.get("DEEPINFRA_TOKEN")
    if not api_key:
        raise RuntimeError("DEEPINFRA_API_KEY not set")
    client = openai.OpenAI(api_key=api_key, base_url=_DEEPINFRA_BASE_URL, timeout=TIMEOUT)

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=_DEEPINFRA_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": prompt + " /no_think"},
                ],
                temperature=0.1,
                max_tokens=max_tokens,
            )
            usage = resp.usage
            if usage:
                in_tok = usage.prompt_tokens
                out_tok = usage.completion_tokens
                cost = (in_tok / 1000 * _DEEPINFRA_COST_PER_1K_INPUT) + (out_tok / 1000 * _DEEPINFRA_COST_PER_1K_OUTPUT)
                _total_input_tokens += in_tok
                _total_output_tokens += out_tok
                _total_cost_usd += cost
                logger.debug(f"DeepInfra call: in={in_tok} out={out_tok} cost=${cost:.5f} total=${_total_cost_usd:.4f}")
            text = resp.choices[0].message.content or ""
            # Strip <think>...</think> artifacts from Qwen3 judge responses
            from core.providers.deepinfra_provider import strip_thinking_artifacts
            text = strip_thinking_artifacts(text)
            return text
        except openai.RateLimitError as e:
            wait = 2 ** attempt
            logger.warning(f"DeepInfra RateLimit (attempt {attempt+1}/{MAX_RETRIES}), retrying in {wait}s: {e}")
            time.sleep(wait)
        except openai.APITimeoutError as e:
            logger.warning(f"DeepInfra Timeout (attempt {attempt+1}/{MAX_RETRIES}): {e}")
        except openai.APIError as e:
            logger.warning(f"DeepInfra API error (attempt {attempt+1}/{MAX_RETRIES}): {e}")
            time.sleep(1)
    return None


# ---------------------------------------------------------------------------
# Unified dispatcher
# ---------------------------------------------------------------------------

def _call_judge(prompt: str, max_tokens: int = 1500) -> Optional[str]:
    """Route to DeepInfra backend (Qwen3-30B-A3B)."""
    return _call_deepinfra(prompt, max_tokens=max_tokens)


def get_total_cost() -> float:
    """Return cumulative USD cost of all judge calls this session."""
    return _total_cost_usd


def _parse_result_score(text: str) -> Optional[int]:
    """Extract 1-5 rating from judge output."""
    if not text:
        return None
    # Primary: [RESULT] N
    m = re.search(r'\[RESULT\]\s*(\d)', text)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 5:
            return val
    # "Score: N" or "Rating: N"
    m = re.search(r'(?:Score|Rating|Puntuación|Nota)\s*[:=]\s*(\d)', text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 5:
            return val
    # "score is N" / "nota es N"
    m = re.search(r'(?:score|puntuación|nota)\s+(?:is|es|de)\s+(\d)', text, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        if 1 <= val <= 5:
            return val
    # Last resort: final standalone digit 1-5 in text
    digits = re.findall(r'\b([1-5])\b', text)
    if digits:
        return int(digits[-1])
    return None


def _parse_pairwise_result(text: str) -> Optional[str]:
    """Extract [RESULT] A or B from pairwise output."""
    if not text:
        return None
    # Primary: [RESULT] A/B
    m = re.search(r'\[RESULT\]\s*([AB])', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # "Respuesta A/B" or "Response A/B" patterns
    m = re.search(r'[Rr]espue?sta\s+([AB])\b', text)
    if m:
        return m.group(1).upper()
    m = re.search(r'[Rr]esponse\s+([AB])\b', text)
    if m:
        return m.group(1).upper()
    # "better/mejor/choose/elijo" + A/B
    m = re.search(r'(?:better|mejor|choose|elijo)\s+(?:response\s+)?([AB])', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    # Last resort: final standalone A or B
    letters = re.findall(r'\b([AB])\b', text)
    if letters:
        return letters[-1].upper()
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
    creator_summary: str = "",
    doc_d_text: str = "",
    creator_id: str = "",
) -> Tuple[float, str]:
    """B2: Persona consistency (0-100). Returns (score, feedback)."""
    if creator_summary:
        instruction = (
            f"Evalúa si la respuesta del bot es consistente con el perfil del creator descrito en el rubric.\n"
            f"Mensaje del lead: {user_message}"
        )
    else:
        instruction = (
            f"Evalúa si la respuesta del bot es consistente con la persona del creator.\n"
            f"Mensaje del lead: {user_message}"
        )
    rubric = _build_rubric_b2(creator_summary, doc_d_text=doc_d_text, creator_id=creator_id)
    prompt = _build_direct_prompt(instruction, bot_response, reference, rubric)

    for attempt in range(MAX_RETRIES):
        t0 = time.time()
        raw = _call_judge(prompt)
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
        raw = _call_judge(prompt)
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
        raw = _call_judge(prompt)
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
        raw = _call_judge(prompt)
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
        raw = _call_judge(prompt)
        elapsed = time.time() - t0
        if raw:
            chosen = _parse_pairwise_result(raw)
            if chosen:
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
    max_cases: int = 50,
    creator_summary: str = "",
    doc_d_text: str = "",
    creator_id: str = "",
) -> Dict[str, Any]:
    """Run all 5 judge params on a list of per_case_records.

    Each case dict must have: bot_response, ground_truth, user_input (or test_input).
    creator_summary: dynamic creator profile text injected into B2 rubric.
    doc_d_text: Creator's Doc D for exemplar calibration (PersonaGym).
    creator_id: Creator slug for exemplar caching.
    Returns aggregate scores and per-case details.
    """
    eval_cases = cases[:max_cases]
    n = len(eval_cases)
    print(f"  Evaluating {n} cases with {MODEL_NAME} (deepinfra)...")

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

        # B2: Persona consistency (with exemplar calibration if doc_d available)
        b2, b2_fb = judge_persona_consistency(
            bot_resp, ground_truth, user_msg, creator_summary,
            doc_d_text=doc_d_text, creator_id=creator_id,
        )
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
        cost_so_far = get_total_cost()
        print(
            f"  Case {i+1}/{n} | B2={b2:.0f} B5={b5:.0f} C2={c2:.0f} C3={c3:.0f} "
            f"H1={'✓' if h1_fooled else '✗'} | {case_time:.1f}s | cost=${cost_so_far:.4f}"
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

    final_cost = get_total_cost()
    print(f"  {MODEL_NAME} judge total cost: ${final_cost:.4f} | time: {total_time:.1f}s")

    return {
        "B2_persona_consistency": _mean(b2_scores),
        "B5_emotional_signature": _mean(b5_scores),
        "C2_naturalness": _mean(c2_scores),
        "C3_contextual_appropriateness": _mean(c3_scores),
        "H1_turing_test_rate": round(h1_rate, 1),
        "n_cases": n,
        "total_time_seconds": round(total_time, 1),
        "total_cost_usd": round(final_cost, 4),
        "model": MODEL_NAME,
        "per_case": per_case,
    }
