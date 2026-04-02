"""
CPE Ablation — Layer 2 + System #7: User Context Builder.

Systems active (same as Layer 2):
  #4 Input Guards      — empty gate, injection flag, media flag, length truncation
  #1 Sensitive         — crisis/threat/spam → crisis response, SKIP LLM
  #5 Pool Matching     — short social msg → pool response, SKIP LLM
  #2 Frustration       — annotate level 0-3 in metadata
  #3 Context Signals   — annotate language, B2B, correction, objection, name

ADDED (System #7):
  #7 User Context      — inject lead profile (name, language, interests, relationship)
                         into system prompt before LLM generation

LLM generation (if not intercepted):
  - Base: DeepInfra Qwen3-14B + Doc D v3 system prompt
  - + User context block (name, language, interests, conversation status)
  - Frustration ≥ 2: append empathy note
  - B2B detected: append professional context note
  - Correction: append correction awareness note
  - Price objection: append objection note

Methodology:
  - PersonaGym (EMNLP 2025) + AbGen (ACL 2025)
  - 3 runs × 50 cases = 150 observations
  - L1 (9) + L2 (5) + L3 (BERTScore + rep + hallucination)
  - Wilcoxon + Cliff's delta vs Layer 2

Usage:
    railway run python3 tests/cpe_ablation_layer2_plus_system07.py --creator iris_bertran
    railway run python3 tests/cpe_ablation_layer2_plus_system07.py --creator iris_bertran --evaluate-only

Output:
    tests/cpe_data/{creator}/sweep/layer2_plus_system07_run{N}_{ts}.json
    tests/cpe_data/{creator}/sweep/layer2_plus_system07.json
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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("DEEPINFRA_TIMEOUT", "30")
os.environ.setdefault("DEEPINFRA_CB_THRESHOLD", "999")

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("cpe_layer2_sys07")
logger.setLevel(logging.INFO)

DEFAULT_MODEL    = "Qwen/Qwen3-14B"
RATE_LIMIT_DELAY = 1.2

# Thresholds — mirror production values from AGENT_THRESHOLDS
SENSITIVE_CONFIDENCE  = 0.70
SENSITIVE_ESCALATION  = 0.85
POOL_CONFIDENCE       = 0.80
POOL_MAX_MSG_LEN      = 80     # chars; pool matching only for short social msgs
INPUT_MAX_LEN         = 3000   # truncation guard


# =============================================================================
# LOAD SYSTEM PROMPT — compressed Doc D
# =============================================================================

def load_system_prompt(creator_id: str) -> str:
    try:
        from services.creator_profile_service import get_profile
        data = get_profile(creator_id, "compressed_doc_d")
        if data and data.get("text"):
            return data["text"]
    except Exception as e:
        logger.warning("DB profile lookup failed: %s", e)
    try:
        from core.dm.compressed_doc_d import build_compressed_doc_d
        return build_compressed_doc_d(creator_id)
    except Exception as e:
        raise RuntimeError(f"Cannot load compressed Doc D for '{creator_id}': {e}") from e


# =============================================================================
# POOL VARIATOR + CALIBRATION  (same fix as docd_v3_plus_pool script)
# =============================================================================

def load_pool_variator(creator_id: str):
    from services.response_variator_v2 import ResponseVariatorV2
    variator = ResponseVariatorV2()
    variator._load_extraction_pools(creator_id)
    if not variator._extraction_pools.get(creator_id):
        cal_path = REPO_ROOT / "calibrations" / f"{creator_id}.json"
        if cal_path.exists():
            with open(cal_path, encoding="utf-8") as f:
                cal_data = json.load(f)
            cal_pools = cal_data.get("response_pools", {})
            if cal_pools:
                variator._extraction_pools[creator_id] = cal_pools
                variator._extraction_attempted.add(creator_id)
                total = sum(len(v) for v in cal_pools.values())
                print(f"  Pool variator: {len(cal_pools)} categories, {total} responses (calibration)")
    return variator


def load_calibration(creator_id: str) -> dict:
    cal_path = REPO_ROOT / "calibrations" / f"{creator_id}.json"
    if cal_path.exists():
        with open(cal_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


# =============================================================================
# INPUT GUARDS  (#4)
# =============================================================================

_PROMPT_INJECTION_RE = [
    re.compile(r"ignor[ae].{0,20}(previous|prior|your|all|mis|tus?|sus?).{0,20}(instructions?|prompt|rules?|instrucciones?)", re.IGNORECASE),
    re.compile(r"olvida.{0,20}(tus?|sus?|las?|mis?).{0,20}(instrucciones?|reglas?|prompt)", re.IGNORECASE),
    re.compile(r"\bact\s+as\s+(DAN|GPT|an?\s+AI\s+without|a\s+model\s+without)", re.IGNORECASE),
    re.compile(r"\b(you are now|ahora eres|now you are|eres ahora)\b.{0,40}(DAN|GPT|unrestricted|sin restricciones)", re.IGNORECASE),
    re.compile(r"\b(jailbreak|bypass your|forget everything( you)?|from now on you are|pretend you have no)\b", re.IGNORECASE),
    re.compile(r"\b(mu[eé]strame|show me|reveal|display|tell me).{0,20}(system prompt|tu prompt|tus instrucciones|your instructions)", re.IGNORECASE),
]

_MEDIA_PLACEHOLDERS = {
    "sent an attachment", "sent a photo", "sent a video",
    "shared a reel", "shared a story", "sent a voice message",
    "[image]", "[video]", "[sticker]", "[🏷️ sticker]",
    "[audio]", "[🎤 audio]", "[🎤 audio message]",
    "[📷 photo]", "[📷 foto]", "[📸 photo]", "[📸 foto]",
    "audio message", "mensaje de voz",
    "envió un archivo adjunto", "envió una foto", "envió un video",
    "compartió un reel", "compartió una historia",
}


def _is_text_ground_truth(gt: str) -> bool:
    """Return True if ground_truth is real text (not an audio/sticker/media placeholder)."""
    if not gt or not gt.strip():
        return False
    gt_lower = gt.strip().lower()
    if gt_lower in _MEDIA_PLACEHOLDERS:
        return False
    if gt_lower.startswith("[") and gt_lower.endswith("]") and len(gt_lower) < 40:
        inner = gt_lower[1:-1].strip()
        media_words = {"audio", "sticker", "photo", "foto", "video", "image",
                       "reel", "story", "historia", "archivo", "attachment"}
        if any(w in inner for w in media_words):
            return False
    return True


def _get_conversation_context(case_id: str, conversations: list) -> list:
    """Extract last 5 turns from the test case's conversation history."""
    for tc in conversations:
        if tc.get("id") == case_id:
            turns = tc.get("turns", [])
            return turns[-5:] if turns else []
    return []


def run_input_guards(message: str) -> Tuple[str, dict]:
    flags: dict = {
        "is_empty":         False,
        "is_truncated":     False,
        "injection_flagged": False,
        "is_media":         False,
    }
    if not message or not message.strip():
        flags["is_empty"] = True
        return message, flags
    if len(message) > INPUT_MAX_LEN:
        message = message[:INPUT_MAX_LEN]
        flags["is_truncated"] = True
    for pat in _PROMPT_INJECTION_RE:
        if pat.search(message):
            flags["injection_flagged"] = True
            break
    msg_stripped = message.strip().lower().rstrip(".")
    if msg_stripped in _MEDIA_PLACEHOLDERS:
        flags["is_media"] = True
    return message, flags


# =============================================================================
# SYSTEM #7: USER CONTEXT BUILDER — simulate for ablation
# =============================================================================

# Catalan/Spanish first names for deriving display names from usernames
_NAME_LIKE_RE = re.compile(r'^[A-ZÁÉÍÓÚÀÈÌÒÙÜÏÇ][a-záéíóúàèìòùüïç]{2,}(?:[._][A-Za-záéíóúàèìòùüïç]+)*$')


def _extract_display_name(username: str) -> str:
    """Extract a human name from username if it looks like one."""
    if not username:
        return ""
    # WhatsApp phone numbers → no name
    if username.startswith("wa_") or username.startswith("+"):
        return ""
    # Instagram handles that look like names
    if _NAME_LIKE_RE.match(username):
        # Split on dots/underscores, capitalize
        parts = re.split(r'[._]', username)
        return parts[0].capitalize()
    # Try first part of handle
    clean = re.sub(r'[0-9_]+$', '', username)
    if clean and len(clean) >= 3 and clean[0].isalpha():
        return clean.capitalize()
    return ""


def _detect_language_from_turns(turns: List[dict], test_input: str) -> str:
    """Detect predominant language from conversation turns."""
    _CA = re.compile(
        r"\b(tinc|estic|però|molt|doncs|també|perquè|això|vull|puc|"
        r"gràcies|gracies|bon dia|bona tarda|setmana|nosaltres|puguis|"
        r"sí|feia|bastant|bé|clar|ara|aquí|només)\b", re.IGNORECASE
    )
    _ES = re.compile(
        r"\b(tengo|estoy|pero|mucho|entonces|también|porque|quiero|"
        r"puedo|necesito|bueno|gracias|vale|claro|genial|ahora)\b", re.IGNORECASE
    )
    all_text = test_input + " " + " ".join(t.get("content", "") for t in turns)
    ca_hits = len(_CA.findall(all_text))
    es_hits = len(_ES.findall(all_text))
    if ca_hits > es_hits:
        return "ca"
    if es_hits > 0:
        return "es"
    return "es"  # default


def _derive_interests_from_turns(turns: List[dict], category: str) -> List[str]:
    """Derive interests from conversation context and category."""
    interests = []
    all_text = " ".join(t.get("content", "") for t in turns).lower()

    # Category-based interests
    cat_interests = {
        "booking": ["sesiones", "reservas"],
        "product_inquiry": ["productos", "servicios"],
        "objection": ["precios"],
        "long_personal": ["bienestar personal"],
    }
    if category in cat_interests:
        interests.extend(cat_interests[category])

    # Content-based interest detection
    interest_patterns = [
        (r"\b(yoga|meditaci[oó]n|mindfulness)\b", "bienestar"),
        (r"\b(retiro|retreat)\b", "retiros"),
        (r"\b(coaching|mentoring|mentoría)\b", "coaching"),
        (r"\b(curso|taller|formaci[oó]n|clase)\b", "formación"),
        (r"\b(nutrici[oó]n|dieta|alimentaci[oó]n)\b", "nutrición"),
        (r"\b(deporte|fitness|entreno|ejercicio)\b", "fitness"),
    ]
    for pat, interest in interest_patterns:
        if re.search(pat, all_text, re.IGNORECASE):
            if interest not in interests:
                interests.append(interest)

    return interests[:3]  # max 3


def _derive_conversation_status(msg_count: int, is_multi_turn: bool) -> str:
    """Derive conversation status label for prompt context."""
    if msg_count == 0 or (msg_count <= 1 and not is_multi_turn):
        return "PRIMER MENSAJE - Dar bienvenida"
    elif msg_count <= 3:
        return None  # short conv, no special label
    elif msg_count <= 10:
        return f"Conversación activa ({msg_count} mensajes)"
    else:
        return f"Conversación activa ({msg_count} mensajes)"


def build_user_context_block(
    username: str,
    language: str,
    interests: List[str],
    conv_status: Optional[str],
) -> str:
    """
    Build the user context block for prompt injection.
    Mirrors format_user_context_for_prompt() from core/user_context_loader.py.
    """
    lines = ["=== CONTEXTO DEL USUARIO ==="]

    # Name
    display_name = _extract_display_name(username)
    if display_name:
        lines.append(f"- Nombre: {display_name}")

    # Language (only if non-default)
    if language and language != "es":
        lines.append(f"- Idioma preferido: {language}")

    # Interests
    if interests:
        lines.append(f"- Intereses: {', '.join(interests)}")

    # Conversation status
    if conv_status:
        lines.append(f"- {conv_status}")

    if len(lines) == 1:
        return ""  # No context to add

    return "\n".join(lines)


# =============================================================================
# SYSTEM PROMPT AUGMENTATION based on detection results + user context
# =============================================================================

def build_augmented_prompt(base_prompt: str, frustration_level: int,
                            context_signals, user_context_block: str) -> str:
    """Append detection-driven notes + user context to the base Doc D system prompt."""
    sections = []

    # System #7: User context block (injected BEFORE detection notes)
    if user_context_block:
        sections.append(user_context_block)

    # Detection notes (same as Layer 2)
    notes = []
    if frustration_level >= 2:
        notes.append(
            "El lead está frustrado. Responde con más empatía y sin preguntas."
        )

    if context_signals:
        if getattr(context_signals, "is_b2b", False):
            notes.append("Es un contexto profesional/B2B.")

        if getattr(context_signals, "is_correction", False):
            notes.append("El lead está corrigiendo algo que dijo antes.")

        obj = getattr(context_signals, "objection_type", "")
        if obj == "price":
            notes.append("El lead tiene objeción de precio.")
        elif obj == "time":
            notes.append("El lead menciona que no tiene tiempo ahora.")
        elif obj == "trust":
            notes.append("El lead muestra objeción de confianza.")

    if notes:
        sections.append(" ".join(notes))

    if not sections:
        return base_prompt

    return base_prompt + "\n\n" + "\n\n".join(sections)


# =============================================================================
# METRICS  (verbatim from layer2 script)
# =============================================================================

_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\u2600-\u27BF\U0001F900-\U0001F9FF][\U0001F3FB-\U0001F3FF\uFE0F]?"
)
_CA_MARKERS = re.compile(
    r"\b(tinc|estic|però|molt|doncs|també|perquè|això|vull|puc|"
    r"gràcies|gracies|bon dia|bona tarda|bona nit|setmana|"
    r"dimarts|dijous|dissabte|diumenge|nosaltres|puguis|vulguis)\b",
    re.IGNORECASE,
)
_ES_MARKERS = re.compile(
    r"\b(tengo|estoy|pero|mucho|entonces|también|porque|quiero|"
    r"puedo|necesito|bueno|gracias|vale|claro|genial|"
    r"miércoles|jueves|sábado|domingo|nosotros)\b",
    re.IGNORECASE,
)


def _text_metrics(text: str) -> dict:
    if not text:
        return {"length": 0, "has_emoji": False, "has_question": False,
                "has_exclamation": False, "language": "unknown", "words": set()}
    words   = set(re.findall(r"\b\w+\b", text.lower()))
    emojis  = _EMOJI_RE.findall(text)
    ca_hits = len(_CA_MARKERS.findall(text))
    es_hits = len(_ES_MARKERS.findall(text))
    lang    = "ca-es" if (ca_hits and es_hits) else ("ca" if ca_hits > es_hits else "es")
    return {
        "length":          len(text),
        "has_emoji":       len(emojis) > 0,
        "has_question":    "?" in text,
        "has_exclamation": "!" in text,
        "language":        lang,
        "words":           words,
    }


def _tokenize(text: str) -> List[str]:
    return re.findall(r"\b\w+\b", text.lower())


def _count_sentences(text: str) -> int:
    text = text.strip()
    if not text:
        return 0
    parts = re.split(r"[.!?]+(?:\s|$)", text)
    return max(1, len([p for p in parts if p.strip()]))


def _distinct2(texts: List[str]) -> float:
    all_bgs: List[Tuple] = []
    unique_bgs: set = set()
    for t in texts:
        toks = _tokenize(t)
        bgs  = list(zip(toks, toks[1:]))
        all_bgs.extend(bgs)
        unique_bgs.update(bgs)
    return len(unique_bgs) / len(all_bgs) if all_bgs else 0.0


def _chrf(candidate: str, reference: str, n: int = 6, beta: float = 2.0) -> float:
    if not candidate or not reference:
        return 0.0
    def _char_ngrams(text: str, order: int) -> Counter:
        ctr: Counter = Counter()
        for w in text.split():
            w = " " + w + " "
            for i in range(len(w) - order + 1):
                ctr[w[i:i + order]] += 1
        return ctr
    precs, recs = [], []
    for order in range(1, n + 1):
        ref_ng  = _char_ngrams(reference, order)
        cand_ng = _char_ngrams(candidate, order)
        tc, tr  = sum(cand_ng.values()), sum(ref_ng.values())
        if tc == 0 or tr == 0:
            precs.append(0.0); recs.append(0.0); continue
        m = sum(min(cnt, ref_ng[ng]) for ng, cnt in cand_ng.items())
        precs.append(m / tc); recs.append(m / tr)
    p = statistics.mean(precs) if precs else 0.0
    r = statistics.mean(recs)  if recs  else 0.0
    if p + r == 0:
        return 0.0
    return round((1 + beta ** 2) * p * r / (beta ** 2 * p + r), 4)


def _bleu4(candidate: str, reference: str) -> float:
    cand_tok = _tokenize(candidate)
    ref_tok  = _tokenize(reference)
    if not cand_tok or not ref_tok:
        return 0.0
    precs = []
    for n in range(1, 5):
        c_ng = Counter(tuple(cand_tok[i:i+n]) for i in range(len(cand_tok)-n+1))
        r_ng = Counter(tuple(ref_tok[i:i+n])  for i in range(len(ref_tok)-n+1))
        matches = sum(min(cnt, r_ng[ng]) for ng, cnt in c_ng.items())
        total   = sum(c_ng.values())
        if total == 0:
            return 0.0
        precs.append(matches / total)
    if any(p == 0 for p in precs):
        return 0.0
    log_avg = sum(math.log(p) for p in precs) / 4
    bp = min(1.0, len(cand_tok) / len(ref_tok))
    return round(bp * math.exp(log_avg), 4)


def _rouge_l(candidate: str, reference: str) -> float:
    cand_tok = _tokenize(candidate)
    ref_tok  = _tokenize(reference)
    m, n     = len(ref_tok), len(cand_tok)
    if m == 0 or n == 0:
        return 0.0
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            dp[i][j] = (dp[i-1][j-1] + 1) if ref_tok[i-1] == cand_tok[j-1] \
                       else max(dp[i-1][j], dp[i][j-1])
    lcs = dp[m][n]
    if lcs == 0:
        return 0.0
    p = lcs / n; r = lcs / m
    return round(2 * p * r / (p + r), 4)


def _meteor(candidate: str, reference: str) -> float:
    from nltk.translate.meteor_score import single_meteor_score
    c, r = _tokenize(candidate), _tokenize(reference)
    if not c or not r:
        return 0.0
    return round(single_meteor_score(r, c), 4)


def _repetition_rate(text: str) -> bool:
    toks = _tokenize(text)
    if len(toks) < 8:
        return False
    ngs = list(zip(toks, toks[1:], toks[2:], toks[3:]))
    return len(ngs) != len(set(ngs))


_HALLU_RE = re.compile(
    r"https?://|www\.|\.com|\.es|\.org|amazon|instagram\.com|linktr\.ee|"
    r"shopify|booking|aliexpress|temu|zara|shein|nike|adidas", re.I
)


# =============================================================================
# L1 — 9 metrics
# =============================================================================

def compute_l1(responses: List[str], baseline_metrics: dict) -> dict:
    bm        = baseline_metrics.get("metrics", {})
    iris_emj  = bm.get("emoji",       {}).get("emoji_rate_pct",       22.0)
    iris_excl = bm.get("punctuation", {}).get("exclamation_rate_pct",  1.8)
    iris_q    = bm.get("punctuation", {}).get("question_rate_pct",    14.2)
    iris_lmed = bm.get("length",      {}).get("char_median",           26.0)
    iris_lmn  = bm.get("length",      {}).get("char_mean",             95.2)
    iris_ca   = next((d["pct"] for d in bm.get("languages", {}).get("detected", []) if d["lang"] == "ca"), 43.5)
    iris_top  = set(w[0] for w in bm.get("vocabulary", {}).get("top_50", [])[:50])
    iris_sc   = 1.81
    iris_d2   = 0.934

    n = len(responses)
    if not n:
        return {}

    all_m: List[dict] = []
    all_bot_words: set = set()
    for text in responses:
        m = _text_metrics(text)
        all_bot_words |= m.pop("words", set())
        all_m.append(m)

    bot_emj  = sum(1 for m in all_m if m["has_emoji"])       / n * 100
    bot_excl = sum(1 for m in all_m if m["has_exclamation"]) / n * 100
    bot_q    = sum(1 for m in all_m if m["has_question"])    / n * 100
    bot_lmn  = statistics.mean(m["length"] for m in all_m)
    bot_lmed = statistics.median(m["length"] for m in all_m)
    bot_ca   = sum(1 for m in all_m if m.get("language") in ("ca", "ca-es")) / n * 100
    voc_jac  = len(iris_top & all_bot_words) / len(iris_top | all_bot_words) if (iris_top | all_bot_words) else 0
    bot_sc   = statistics.mean(_count_sentences(r) for r in responses)
    bot_d2   = _distinct2(responses)

    def chk_pct(bot_v, iris_v, tol=20):  return abs(bot_v - iris_v) <= tol
    def chk_num(bot_v, iris_v, tol=30):  return abs(bot_v - iris_v) / iris_v * 100 <= tol if iris_v else False
    def chk_pct10(bot_v, iris_v):         return abs(bot_v - iris_v) <= 10

    results = {
        "has_emoji_pct":    {"bot": round(bot_emj,  2), "iris": iris_emj,  "pass": chk_pct(bot_emj,  iris_emj)},
        "has_excl_pct":     {"bot": round(bot_excl, 2), "iris": iris_excl, "pass": chk_pct10(bot_excl, iris_excl)},
        "q_rate_pct":       {"bot": round(bot_q,    2), "iris": iris_q,    "pass": chk_pct(bot_q,    iris_q)},
        "len_mean_chars":   {"bot": round(bot_lmn,  2), "iris": iris_lmn,  "pass": chk_num(bot_lmn,  iris_lmn)},
        "len_median_chars": {"bot": round(bot_lmed, 2), "iris": iris_lmed, "pass": chk_num(bot_lmed, iris_lmed)},
        "ca_rate_pct":      {"bot": round(bot_ca,   2), "iris": iris_ca,   "pass": chk_pct(bot_ca,   iris_ca)},
        "vocab_jac_pct":    {"bot": round(voc_jac * 100, 2), "iris": 5.0,  "pass": chk_pct10(voc_jac * 100, 5.0)},
        "sentence_count":   {"bot": round(bot_sc,   3), "iris": iris_sc,   "pass": chk_num(bot_sc,   iris_sc)},
        "distinct_2":       {"bot": round(bot_d2,   4), "iris": iris_d2,   "pass": chk_num(bot_d2,   iris_d2)},
    }
    passed = sum(1 for v in results.values() if v["pass"])
    return {"score": f"{passed}/9", "passed": passed, "metrics": results}


# =============================================================================
# L2 — 5 metrics
# =============================================================================

def compute_l2(results: List[Dict]) -> dict:
    pairs    = [(r["bot_response"], r["ground_truth"]) for r in results
                if r.get("bot_response") and r.get("ground_truth")]
    chrf_s   = [_chrf(b, g)    for b, g in pairs]
    bleu4_s  = [_bleu4(b, g)   for b, g in pairs]
    rouge_s  = [_rouge_l(b, g)  for b, g in pairs]
    meteor_s = [_meteor(b, g)   for b, g in pairs]
    lenrat_s = [len(b) / len(g) if len(g) > 0 else 0.0 for b, g in pairs]
    n = len(pairs)
    return {
        "n_pairs":         n,
        "chrf":            round(statistics.mean(chrf_s),   4),
        "bleu4":           round(statistics.mean(bleu4_s),  4),
        "rouge_l":         round(statistics.mean(rouge_s),  4),
        "meteor":          round(statistics.mean(meteor_s), 4),
        "len_ratio":       round(statistics.mean(lenrat_s), 4),
        "_chrf_scores":    chrf_s,
        "_bleu4_scores":   bleu4_s,
        "_rougel_scores":  rouge_s,
        "_meteor_scores":  meteor_s,
        "_lenrat_scores":  lenrat_s,
    }


# =============================================================================
# L3 — repetition + hallucination
# =============================================================================

def compute_l3_quick(results: List[Dict]) -> dict:
    bots        = [r["bot_response"] for r in results]
    rep_flags   = [_repetition_rate(b) for b in bots]
    hallu_flags = [bool(_HALLU_RE.search(b)) for b in bots]
    return {
        "rep_rate_pct":   round(sum(rep_flags)   / len(rep_flags)   * 100, 2),
        "hallu_rate_pct": round(sum(hallu_flags) / len(hallu_flags) * 100, 2),
        "_rep_flags":     [int(f) for f in rep_flags],
        "_hallu_flags":   [int(f) for f in hallu_flags],
    }


# =============================================================================
# STATISTICAL TESTS
# =============================================================================

def wilcoxon_signed_rank(x: List[float], y: List[float]) -> Tuple[float, float]:
    diffs = [xi - yi for xi, yi in zip(x, y)]
    diffs = [d for d in diffs if d != 0]
    n = len(diffs)
    if n < 2:
        return 0.0, 1.0
    abs_diffs = sorted(enumerate(abs(d) for d in diffs), key=lambda t: t[1])
    ranked = [0.0] * len(abs_diffs)
    i = 0
    while i < len(abs_diffs):
        j = i
        while j < len(abs_diffs) - 1 and abs_diffs[j + 1][1] == abs_diffs[i][1]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranked[abs_diffs[k][0]] = avg_rank
        i = j + 1
    w_plus  = sum(r for d, r in zip(diffs, ranked) if d > 0)
    w_minus = sum(r for d, r in zip(diffs, ranked) if d < 0)
    w_stat  = min(w_plus, w_minus)
    mean_w = n * (n + 1) / 4
    var_w  = n * (n + 1) * (2 * n + 1) / 24
    if var_w == 0:
        return w_stat, 1.0
    z = abs((w_stat - mean_w) / math.sqrt(var_w))
    p = 2 * _norm_sf(z)
    return round(w_stat, 2), round(p, 4)


def _norm_sf(z: float) -> float:
    t    = 1.0 / (1.0 + 0.2316419 * z)
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    pdf  = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
    return pdf * poly


def cliffs_delta(x: List[float], y: List[float]) -> float:
    n = len(x)
    if n == 0:
        return 0.0
    greater = sum(1 for xi, yi in zip(x, y) if xi > yi)
    less    = sum(1 for xi, yi in zip(x, y) if xi < yi)
    return round((greater - less) / n, 4)


def cliffs_magnitude(d: float) -> str:
    a = abs(d)
    if a < 0.147: return "negligible"
    if a < 0.330: return "small"
    if a < 0.474: return "medium"
    return "large"


# =============================================================================
# LOAD PER-CASE SCORES from Layer 2 baseline
# =============================================================================

def _extract_per_case_from_files(run_files: List[Path]) -> Dict[str, List[float]]:
    pc: Dict[str, List[float]] = {k: [] for k in [
        "has_emoji", "has_excl", "q_rate", "char_len",
        "is_ca", "sentence_count", "chrf", "bleu4",
        "rouge_l", "meteor", "len_ratio", "rep_rate",
    ]}
    for rf in run_files:
        data = json.loads(rf.read_text())
        for r in data["results"]:
            bot = r.get("bot_response", "")
            gt  = r.get("ground_truth", "")
            m   = _text_metrics(bot)
            pc["has_emoji"].append(float(m["has_emoji"]))
            pc["has_excl"].append(float(m["has_exclamation"]))
            pc["q_rate"].append(float(m["has_question"]))
            pc["char_len"].append(float(m["length"]))
            pc["is_ca"].append(float(m["language"] in ("ca", "ca-es")))
            pc["sentence_count"].append(float(_count_sentences(bot)))
            pc["chrf"].append(_chrf(bot, gt))
            pc["bleu4"].append(_bleu4(bot, gt))
            pc["rouge_l"].append(_rouge_l(bot, gt))
            pc["meteor"].append(_meteor(bot, gt))
            pc["len_ratio"].append(len(bot) / len(gt) if len(gt) > 0 else 0.0)
            pc["rep_rate"].append(float(_repetition_rate(bot)))
    return pc


def load_layer2_per_case(sweep_dir: Path) -> Dict[str, List[float]]:
    """Load Layer 2 baseline per-case scores for statistical comparison."""
    # Try locked baseline first
    locked = sweep_dir / "layer2_v2_baseline_locked.json"
    if locked.exists():
        data = json.loads(locked.read_text())
        # If it has run files referenced, load those
        pass

    # Find the most recent complete 3-run set
    by_ts: Dict[str, List[Path]] = defaultdict(list)
    for f in sorted(sweep_dir.glob("layer2_full_detection_run*.json")):
        parts = f.stem.split("_")
        ts = "_".join(parts[-2:])
        by_ts[ts].append(f)
    complete = sorted(
        [(ts, fs) for ts, fs in by_ts.items() if len(fs) == 3],
        key=lambda t: t[0], reverse=True,
    )
    if not complete:
        logger.warning("No complete layer2 3-run set — stat comparison vs L2 skipped")
        return {}
    ts, files = complete[0]
    logger.info("Layer2 baseline: %s (%d files)", ts, len(files))
    return _extract_per_case_from_files(files)


def extract_per_case_from_results(run_results_list: List[List[Dict]]) -> Dict[str, List[float]]:
    pc: Dict[str, List[float]] = {k: [] for k in [
        "has_emoji", "has_excl", "q_rate", "char_len",
        "is_ca", "sentence_count", "chrf", "bleu4",
        "rouge_l", "meteor", "len_ratio", "rep_rate",
    ]}
    for results in run_results_list:
        for r in results:
            bot = r.get("bot_response", "")
            gt  = r.get("ground_truth", "")
            m   = _text_metrics(bot)
            pc["has_emoji"].append(float(m["has_emoji"]))
            pc["has_excl"].append(float(m["has_exclamation"]))
            pc["q_rate"].append(float(m["has_question"]))
            pc["char_len"].append(float(m["length"]))
            pc["is_ca"].append(float(m["language"] in ("ca", "ca-es")))
            pc["sentence_count"].append(float(_count_sentences(bot)))
            pc["chrf"].append(_chrf(bot, gt))
            pc["bleu4"].append(_bleu4(bot, gt))
            pc["rouge_l"].append(_rouge_l(bot, gt))
            pc["meteor"].append(_meteor(bot, gt))
            pc["len_ratio"].append(len(bot) / len(gt) if len(gt) > 0 else 0.0)
            pc["rep_rate"].append(float(_repetition_rate(bot)))
    return pc


# =============================================================================
# GENERATION — Layer 2 + System #7: User Context Builder
# =============================================================================

async def generate_layer2_sys07_run(
    test_cases: List[Dict],
    base_prompt: str,
    variator,
    calibration: dict,
    creator_id: str,
    model: str,
    run_idx: int,
    delay: float = RATE_LIMIT_DELAY,
) -> Tuple[List[Dict], Dict[str, int]]:
    """
    One run through Layer 2 detection pipeline + System #7 user context.
    Returns (results, intercept_counts).
    """
    from core.sensitive_detector import detect_sensitive_content, get_crisis_resources
    from core.frustration_detector import get_frustration_detector
    from core.context_detector import detect_all as detect_context
    from services.length_controller import classify_lead_context
    from core.providers.deepinfra_provider import call_deepinfra

    frustration_detector = get_frustration_detector()

    counts = defaultdict(int)

    logger.info("[Run %d] layer2+sys07 | model=%s | cases=%d", run_idx, model, len(test_cases))

    results = []
    for i, tc in enumerate(test_cases, 1):
        original_message = tc["test_input"]
        t0 = time.monotonic()

        bot_response = ""
        source       = "llm"
        intercept_by = None
        frust_level  = 0
        ctx_signals  = None
        guard_flags: dict = {}
        pool_cat     = None
        pool_conf    = 0.0
        tokens_in    = 0
        tokens_out   = 0
        augmented    = False
        user_ctx_injected = False

        # ── SYSTEM #7: Build user context ──────────────────────────────────
        turns = tc.get("turns", [])
        username = tc.get("lead_username", "")
        msg_count = tc.get("msg_count", len(turns))
        is_multi = tc.get("is_multi_turn", False)
        tc_lang = tc.get("language", "unknown")

        # Derive user context from test case metadata
        detected_lang = _detect_language_from_turns(turns, original_message) if tc_lang == "unknown" else tc_lang
        interests = _derive_interests_from_turns(turns, tc.get("category", ""))
        conv_status = _derive_conversation_status(msg_count, is_multi)

        user_context_block = build_user_context_block(
            username=username,
            language=detected_lang,
            interests=interests,
            conv_status=conv_status,
        )

        if user_context_block:
            counts["user_context_injected"] += 1
            user_ctx_injected = True

        # ── GUARD #4: Input Guards ─────────────────────────────────────────
        message, guard_flags = run_input_guards(original_message)

        if guard_flags["is_empty"]:
            counts["empty_skipped"] += 1
            source      = "empty_skip"
            intercept_by = "input_guard_empty"
            bot_response = ""
        else:
            if guard_flags["is_truncated"]:
                counts["truncated"] += 1
            if guard_flags["injection_flagged"]:
                counts["injection_flagged"] += 1
            if guard_flags["is_media"]:
                counts["media_flagged"] += 1

            # ── SYSTEM #1: Sensitive Detection ─────────────────────────────
            try:
                sensitive = detect_sensitive_content(message)
                if sensitive and sensitive.confidence >= SENSITIVE_CONFIDENCE:
                    counts["sensitive_flagged"] += 1
                    if sensitive.confidence >= SENSITIVE_ESCALATION:
                        bot_response = get_crisis_resources(language="es")
                        source        = "crisis"
                        intercept_by  = f"sensitive_{sensitive.type.value}"
                        counts["sensitive_escalated"] += 1
            except Exception as e:
                logger.debug("Sensitive detection error: %s", e)

            # ── SYSTEM #5: Pool Matching (only if not yet intercepted) ──────
            if not bot_response and len(message.strip()) <= POOL_MAX_MSG_LEN:
                try:
                    pool_context = classify_lead_context(message)
                    match = variator.try_pool_response(
                        lead_message  = message,
                        min_confidence= 0.70,
                        calibration   = calibration,
                        turn_index    = i,
                        conv_id       = f"l2s07_ablation_run{run_idx}_{i}",
                        context       = pool_context,
                        creator_id    = creator_id,
                    )
                    if match.matched and match.confidence >= POOL_CONFIDENCE:
                        bot_response = match.response.strip()
                        source        = "pool"
                        intercept_by  = f"pool_{match.category}"
                        pool_cat      = match.category
                        pool_conf     = round(match.confidence, 3)
                        counts["pool_matched"] += 1
                except Exception as e:
                    logger.debug("Pool matching error: %s", e)

            # ── SYSTEM #2: Frustration Detection (always annotates) ─────────
            try:
                frust_signals, frust_score = frustration_detector.analyze_message(
                    message, f"l2s07_run{run_idx}_{i}"
                )
                frust_level = frust_signals.level
                if frust_level >= 2:
                    counts["frustration_moderate_plus"] += 1
                elif frust_level == 1:
                    counts["frustration_soft"] += 1
            except Exception as e:
                logger.debug("Frustration detection error: %s", e)

            # ── SYSTEM #3: Context Signals (always annotates) ───────────────
            try:
                ctx_signals = detect_context(message)
                if getattr(ctx_signals, "is_b2b", False):
                    counts["b2b_detected"] += 1
                if getattr(ctx_signals, "is_correction", False):
                    counts["correction_detected"] += 1
                obj = getattr(ctx_signals, "objection_type", "")
                if obj:
                    counts[f"objection_{obj}"] += 1
                name = getattr(ctx_signals, "user_name", "")
                if name:
                    counts["name_extracted"] += 1
            except Exception as e:
                logger.debug("Context detection error: %s", e)

            # ── LLM GENERATION (if not intercepted) ────────────────────────
            if not bot_response:
                counts["llm_calls"] += 1
                # Build augmented prompt: user context + detection signals
                prompt = build_augmented_prompt(
                    base_prompt, frust_level, ctx_signals, user_context_block
                )
                augmented = (prompt != base_prompt)
                if augmented:
                    counts["prompt_augmented"] += 1

                messages = [
                    {"role": "system", "content": prompt},
                    {"role": "user",   "content": message},
                ]
                resp = None
                try:
                    resp = await call_deepinfra(
                        messages, max_tokens=150, temperature=0.7, model=model,
                    )
                except Exception as e:
                    logger.warning("[Run %d] LLM error case %d: %s", run_idx, i, e)

                bot_response = resp["content"].strip() if resp else ""
                tokens_in    = resp.get("tokens_in",  0) if resp else 0
                tokens_out   = resp.get("tokens_out", 0) if resp else 0

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        results.append({
            "id":            tc["id"],
            "test_input":    original_message,
            "ground_truth":  tc.get("ground_truth", ""),
            "bot_response":  bot_response,
            "category":      tc.get("category", ""),
            "language":      tc.get("language", ""),
            "elapsed_ms":    elapsed_ms,
            "tokens_in":     tokens_in,
            "tokens_out":    tokens_out,
            "run":           run_idx,
            # Detection metadata
            "source":           source,
            "intercept_by":     intercept_by,
            "frustration_level": frust_level,
            "is_b2b":           getattr(ctx_signals, "is_b2b",         False) if ctx_signals else False,
            "is_correction":    getattr(ctx_signals, "is_correction",   False) if ctx_signals else False,
            "objection_type":   getattr(ctx_signals, "objection_type",  "")   if ctx_signals else "",
            "user_name":        getattr(ctx_signals, "user_name",       "")   if ctx_signals else "",
            "prompt_augmented": augmented,
            "pool_category":    pool_cat,
            "pool_conf":        pool_conf,
            "guard_flags":      guard_flags,
            # System #7 metadata
            "user_context_injected": user_ctx_injected,
            "user_context_block":    user_context_block if user_ctx_injected else "",
        })

        if i % 10 == 0 or not bot_response:
            tag = source.upper()[:5]
            ctx_tag = "+CTX" if user_ctx_injected else ""
            print(f"  [{tag:5}]{ctx_tag} [{i:02d}/{len(test_cases)}] {tc['id']}: {bot_response[:55]!r}")

        if source == "llm":
            await asyncio.sleep(delay)

    n_ok  = sum(1 for r in results if r["bot_response"])
    ok_ms = [r["elapsed_ms"] for r in results if r["bot_response"] and r["elapsed_ms"] > 0]
    avg_ms = statistics.mean(ok_ms) if ok_ms else 0
    ctx_n = counts["user_context_injected"]
    print(
        f"  Run {run_idx}: {n_ok}/{len(results)} OK | "
        f"llm={counts['llm_calls']} pool={counts['pool_matched']} "
        f"crisis={counts['sensitive_escalated']} ctx={ctx_n} | avg {avg_ms:.0f}ms"
    )
    return results, dict(counts)


# =============================================================================
# MAIN
# =============================================================================

async def main():
    parser = argparse.ArgumentParser(description="CPE Ablation — Layer 2 + System #7: User Context Builder")
    parser.add_argument("--creator",        default="iris_bertran")
    parser.add_argument("--runs",    type=int, default=3)
    parser.add_argument("--model",          default=DEFAULT_MODEL)
    parser.add_argument("--delay",   type=float, default=RATE_LIMIT_DELAY)
    parser.add_argument("--evaluate-only",  action="store_true")
    args = parser.parse_args()

    creator_id = args.creator
    n_runs     = max(1, args.runs)
    model      = args.model

    data_dir  = Path(f"tests/cpe_data/{creator_id}")
    sweep_dir = data_dir / "sweep"
    sweep_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "="*74)
    print("LAYER 2 + SYSTEM #7 ABLATION — Doc D v3 + Detection + User Context")
    print("="*74)

    base_prompt = load_system_prompt(creator_id)
    print(f"System prompt: {len(base_prompt)} chars")

    test_set_v2 = data_dir / "test_set_v2_stratified.json"
    test_set_v1 = data_dir / "test_set.json"
    test_set_path = test_set_v2 if test_set_v2.exists() else test_set_v1
    with open(test_set_path, encoding="utf-8") as f:
        test_set = json.load(f)
    conversations = test_set.get("conversations", [])
    version = test_set.get("metadata", {}).get("version", "v1")
    n_mt = sum(1 for c in conversations if c.get("is_multi_turn"))
    print(f"Test cases: {len(conversations)} (version={version}, multi-turn={n_mt})")

    bm_path = data_dir / "baseline_metrics.json"
    baseline_metrics = json.loads(bm_path.read_text()) if bm_path.exists() else {}
    print(f"Baseline metrics: {'loaded' if baseline_metrics else 'NOT FOUND'}")

    variator    = load_pool_variator(creator_id)
    calibration = load_calibration(creator_id)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # ── GENERATION ────────────────────────────────────────────────────────────
    run_files: List[Path]      = []
    all_counts: List[dict]     = []

    if args.evaluate_only:
        run_files = sorted(sweep_dir.glob("layer2_plus_system07_run*.json"))[:n_runs]
        if not run_files:
            print("ERROR: --evaluate-only but no layer2_plus_system07_run*.json found.")
            sys.exit(1)
        print(f"Evaluate-only: {len(run_files)} files")
        for rf in run_files:
            d = json.loads(rf.read_text())
            all_counts.append(d.get("intercept_counts", {}))
    else:
        api_key = os.getenv("DEEPINFRA_API_KEY")
        if not api_key:
            print("ERROR: DEEPINFRA_API_KEY not set.")
            sys.exit(1)

        for run_idx in range(1, n_runs + 1):
            print(f"\n--- RUN {run_idx}/{n_runs} ---")
            try:
                import core.providers.deepinfra_provider as _di
                _di._deepinfra_consecutive_failures = 0
                _di._deepinfra_circuit_open_until   = 0.0
            except Exception:
                pass

            run_results, counts = await generate_layer2_sys07_run(
                conversations, base_prompt, variator, calibration,
                creator_id, model, run_idx, args.delay,
            )
            all_counts.append(counts)

            rf = sweep_dir / f"layer2_plus_system07_run{run_idx}_{ts}.json"
            payload = {
                "ablation":        "layer2_plus_system07",
                "creator":         creator_id,
                "model":           model,
                "system_prompt":   base_prompt,
                "systems_active":  [
                    "input_guards", "sensitive_detection", "pool_matching",
                    "frustration_detection", "context_signals", "compressed_doc_d",
                    "user_context_builder",
                ],
                "run":             run_idx,
                "n_cases":         len(run_results),
                "timestamp":       datetime.now(timezone.utc).isoformat(),
                "intercept_counts": counts,
                "results":         run_results,
            }
            rf.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
            print(f"Saved: {rf}")
            run_files.append(rf)

    # ── EVALUATION ────────────────────────────────────────────────────────────
    print("\n--- EVALUATING METRICS ---")
    all_run_results: List[List[Dict]] = []
    run_l1: List[dict] = []
    run_l2: List[dict] = []
    run_l3: List[dict] = []

    for rf in run_files:
        data    = json.loads(rf.read_text())
        results = data["results"]
        all_run_results.append(results)

        pool_n  = sum(1 for r in results if r.get("source") == "pool")
        crisis_n = sum(1 for r in results if r.get("source") == "crisis")
        llm_n   = sum(1 for r in results if r.get("source") == "llm")
        aug_n   = sum(1 for r in results if r.get("prompt_augmented"))
        ctx_n   = sum(1 for r in results if r.get("user_context_injected"))

        responses = [r["bot_response"] for r in results]
        l1 = compute_l1(responses, baseline_metrics)
        l2 = compute_l2(results)
        l3 = compute_l3_quick(results)
        run_l1.append(l1)
        run_l2.append(l2)
        run_l3.append(l3)

        print(f"  Run {data['run']}: L1={l1['score']}  "
              f"chrF={l2['chrf']:.4f}  BLEU={l2['bleu4']:.4f}  "
              f"ROUGE={l2['rouge_l']:.4f}  METEOR={l2['meteor']:.4f}  "
              f"rep={l3['rep_rate_pct']}%  "
              f"[llm={llm_n} pool={pool_n} crisis={crisis_n} aug={aug_n} ctx={ctx_n}]")

    # ── Aggregate intercept counts ─────────────────────────────────────────────
    agg_counts: Dict[str, float] = {}
    all_keys = set(k for c in all_counts for k in c)
    for k in sorted(all_keys):
        vals = [c.get(k, 0) for c in all_counts]
        agg_counts[k] = round(statistics.mean(vals), 1)

    # ── BERTScore ─────────────────────────────────────────────────────────────
    print("\nComputing BERTScore (L3)...")
    from bert_score import score as bert_score_fn

    bert_f1s: List[float] = []
    for run_data in all_run_results:
        bots  = [r["bot_response"] for r in run_data]
        leads = [r["test_input"]   for r in run_data]
        _, _, F1 = bert_score_fn(bots, leads, lang="es", verbose=False,
                                  model_type="distilbert-base-multilingual-cased")
        bert_f1s.append(float(F1.mean()))
        print(f"  BERTScore run: {F1.mean():.4f}")

    # ── STATISTICAL COMPARISONS ───────────────────────────────────────────────
    METRIC_MAP = {
        "has_emoji":    ("has_emoji",      "lower_is_better"),
        "has_excl":     ("has_excl",       "lower_is_better"),
        "q_rate":       ("q_rate",         "lower_is_better"),
        "len_mean":     ("char_len",       "lower_is_better"),
        "sentence_cnt": ("sentence_count", "lower_is_better"),
        "ca_rate":      ("is_ca",          "higher_is_better"),
        "chrf":         ("chrf",           "higher_is_better"),
        "bleu4":        ("bleu4",          "higher_is_better"),
        "rouge_l":      ("rouge_l",        "higher_is_better"),
        "meteor":       ("meteor",         "higher_is_better"),
        "len_ratio":    ("len_ratio",      "lower_is_better"),
        "rep_rate":     ("rep_rate",       "lower_is_better"),
    }

    current_pc = extract_per_case_from_results(all_run_results)

    def _compare(current: dict, reference: dict, ref_label: str) -> dict:
        out: dict = {}
        for label, (key, direction) in METRIC_MAP.items():
            cv = current.get(key, [])
            rv = reference.get(key, [])
            if not cv or not rv or len(cv) != len(rv):
                continue
            w_stat, p_val = wilcoxon_signed_rank(cv, rv)
            d = cliffs_delta(cv, rv)
            out[label] = {
                f"{ref_label}_mean": round(statistics.mean(rv), 4),
                "current_mean":      round(statistics.mean(cv), 4),
                "delta":             round(statistics.mean(cv) - statistics.mean(rv), 4),
                "wilcoxon_W":        w_stat,
                "p_value":           p_val,
                "cliffs_d":          d,
                "magnitude":         cliffs_magnitude(d),
                "significant":       p_val < 0.05,
                "direction":         direction,
            }
        return out

    print("\n--- LOADING BASELINES ---")
    layer2_pc = load_layer2_per_case(sweep_dir)

    stat_vs_layer2 = _compare(current_pc, layer2_pc, "layer2") if layer2_pc else {}

    # Also load Layer 2 BERTScore for comparison
    layer2_bert = 0.828
    try:
        with open(sweep_dir / "layer2_full_detection.json") as f:
            _l2 = json.load(f)
        layer2_bert = _l2["l3"]["agg"]["coherence_bert_f1"]["mean"]
    except Exception:
        pass

    # ── AGGREGATE ─────────────────────────────────────────────────────────────
    def _agg(vals: List[float]) -> dict:
        return {"mean": round(statistics.mean(vals), 4),
                "std":  round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0,
                "runs": [round(v, 4) for v in vals]}

    l1_agg: dict = {}
    for mk in ["has_emoji_pct", "has_excl_pct", "q_rate_pct", "len_mean_chars",
               "len_median_chars", "ca_rate_pct", "vocab_jac_pct", "sentence_count", "distinct_2"]:
        vals = [r["metrics"][mk]["bot"] for r in run_l1 if mk in r.get("metrics", {})]
        if vals:
            l1_agg[mk] = _agg(vals)

    # ── SAMPLE CASES: diverse selection (text-only GT) ──────────────────────
    import random
    random.seed(42)
    r1 = all_run_results[0]

    # Filter: only cases with real text ground_truth
    r1_text = [r for r in r1 if _is_text_ground_truth(r.get("ground_truth", ""))]

    pool_cases    = [r for r in r1_text if r.get("source") == "pool"]
    ctx_injected  = [r for r in r1_text if r.get("user_context_injected") and r.get("source") == "llm"]
    frust_cases   = [r for r in r1_text if r.get("frustration_level", 0) >= 2]
    normal_cases  = [r for r in r1_text if r.get("source") == "llm" and not r.get("frustration_level") and not r.get("is_b2b")]
    signal_cases  = [r for r in r1_text if r.get("is_b2b") or r.get("is_correction") or r.get("objection_type")]

    sample: List[Dict] = []
    def _pick(pool: List, n: int = 1) -> List:
        return random.sample(pool, min(n, len(pool))) if pool else []

    # Prioritize cases where user context was injected (the delta we're testing)
    for r in (_pick(ctx_injected, 2) + _pick(pool_cases) + _pick(frust_cases) + _pick(signal_cases)):
        if r["id"] not in {s["id"] for s in sample}:
            sample.append(r)

    # Pad to 5 if needed
    remaining = [r for r in r1_text if r["id"] not in {s["id"] for s in sample}]
    sample += random.sample(remaining, max(0, 5 - len(sample)))
    sample = sample[:5]

    sample_cases = []
    SOURCE_ICONS = {"pool": "POOL", "crisis": "CRISIS", "llm": "LLM", "empty_skip": "EMPTY"}
    for idx, r in enumerate(sample, 1):
        sample_cases.append({
            "case_idx":          idx,
            "id":                r["id"],
            "category":          r.get("category", ""),
            "language":          r.get("language", ""),
            "source":            r.get("source", ""),
            "intercept_by":      r.get("intercept_by"),
            "frustration_level": r.get("frustration_level", 0),
            "is_b2b":            r.get("is_b2b", False),
            "is_correction":     r.get("is_correction", False),
            "objection_type":    r.get("objection_type", ""),
            "user_name":         r.get("user_name", ""),
            "prompt_augmented":  r.get("prompt_augmented", False),
            "pool_category":     r.get("pool_category"),
            "pool_conf":         r.get("pool_conf", 0.0),
            "guard_flags":       r.get("guard_flags", {}),
            "user_context_injected": r.get("user_context_injected", False),
            "user_context_block":    r.get("user_context_block", ""),
            "lead":              r["test_input"],
            "bot_response":      r["bot_response"],
            "ground_truth":      r["ground_truth"],
            "conversation_context": _get_conversation_context(r["id"], conversations),
        })

    # ── FINAL JSON ────────────────────────────────────────────────────────────
    final = {
        "ablation":          "layer2_plus_system07",
        "version":           "v1",
        "creator":           creator_id,
        "model":             model,
        "system_prompt":     base_prompt,
        "system_prompt_chars": len(base_prompt),
        "systems_active":    [
            "input_guards", "sensitive_detection", "pool_matching",
            "frustration_detection", "context_signals", "compressed_doc_d",
            "user_context_builder",
        ],
        "n_runs":     len(all_run_results),
        "n_cases":    len(conversations),
        "computed":   datetime.now(timezone.utc).isoformat(),

        "intercept_counts_per_run":  all_counts,
        "intercept_counts_avg":      agg_counts,

        "l1": {
            "score_per_run": [r["score"] for r in run_l1],
            "agg_metrics":   l1_agg,
            "per_run":       [{"run": i+1, **r} for i, r in enumerate(run_l1)],
        },
        "l2": {
            "agg": {
                "chrf":      _agg([r["chrf"]      for r in run_l2]),
                "bleu4":     _agg([r["bleu4"]     for r in run_l2]),
                "rouge_l":   _agg([r["rouge_l"]   for r in run_l2]),
                "meteor":    _agg([r["meteor"]    for r in run_l2]),
                "len_ratio": _agg([r["len_ratio"] for r in run_l2]),
            },
            "per_run": [{"run": i+1, "chrf": r["chrf"], "bleu4": r["bleu4"],
                         "rouge_l": r["rouge_l"], "meteor": r["meteor"],
                         "len_ratio": r["len_ratio"], "n_pairs": r["n_pairs"]}
                        for i, r in enumerate(run_l2)],
        },
        "l3": {
            "agg": {
                "coherence_bert_f1":      _agg(bert_f1s),
                "repetition_rate_pct":    _agg([r["rep_rate_pct"]   for r in run_l3]),
                "hallucination_rate_pct": _agg([r["hallu_rate_pct"] for r in run_l3]),
            },
        },

        "statistical_comparison_vs_layer2": stat_vs_layer2,
        "sample_cases": sample_cases,
    }

    out_path = sweep_dir / "layer2_plus_system07.json"
    out_path.write_text(json.dumps(final, indent=2, ensure_ascii=False))
    print(f"\nSaved → {out_path}")

    _print_report(final, layer2_bert)


# =============================================================================
# REPORT
# =============================================================================

def _print_report(data: dict, layer2_bert: float) -> None:
    n_total = data["n_runs"] * data["n_cases"]
    ac      = data["intercept_counts_avg"]

    print(f"\n{'='*76}")
    print(f"ABLATION REPORT — Layer 2 + System #7: User Context Builder")
    print(f"Creator: {data['creator']} | Model: {data['model']}")
    print(f"Runs: {data['n_runs']} × {data['n_cases']} = {n_total} observations")
    print(f"{'='*76}")

    print(f"\n  SYSTEM INTERCEPTS (avg per run / {data['n_cases']} cases):")
    intercept_labels = [
        ("llm_calls",             "LLM calls"),
        ("pool_matched",          "#5 Pool matched"),
        ("sensitive_flagged",     "#1 Sensitive flagged (>=0.70)"),
        ("sensitive_escalated",   "#1 Sensitive escalated (>=0.85) -> crisis"),
        ("frustration_soft",      "#2 Frustration soft (level 1)"),
        ("frustration_moderate_plus", "#2 Frustration moderate+ (level >=2)"),
        ("b2b_detected",          "#3 B2B detected"),
        ("correction_detected",   "#3 Correction detected"),
        ("objection_price",       "#3 Price objection"),
        ("prompt_augmented",      "   Prompt augmented (any signal)"),
        ("user_context_injected", "#7 User context injected"),
        ("injection_flagged",     "#4 Injection flagged"),
        ("media_flagged",         "#4 Media placeholder"),
        ("truncated",             "#4 Input truncated"),
        ("empty_skipped",         "#4 Empty skipped"),
    ]
    for key, label in intercept_labels:
        v = ac.get(key, 0)
        if v > 0 or key in ("llm_calls", "user_context_injected"):
            pct = v / data["n_cases"] * 100
            print(f"    {label:<42} {v:5.1f} ({pct:4.1f}%)")

    sc_l2 = data.get("statistical_comparison_vs_layer2", {})

    print(f"\n  {'METRIC':<22} {'L2(Base)':>8} {'L2+Sys7':>8}  "
          f"{'delta':>8}  {'p-value':>8}  {'Cliff-d':>8}  {'Mag':>10}  {'Sig':>4}")
    print(f"{'─'*96}")

    DISPLAY = [
        ("has_emoji (%)",    "has_emoji"),
        ("has_excl (%)",     "has_excl"),
        ("q_rate (%)",       "q_rate"),
        ("len_mean (ch)",    "len_mean"),
        ("sentence_cnt",     "sentence_cnt"),
        ("ca_rate (%)",      "ca_rate"),
        ("chrF++",           "chrf"),
        ("BLEU-4",           "bleu4"),
        ("ROUGE-L",          "rouge_l"),
        ("METEOR",           "meteor"),
        ("len_ratio",        "len_ratio"),
        ("rep_rate (%)",     "rep_rate"),
    ]

    def _fmt(v): return f"{v:8.4f}" if isinstance(v, float) else f"{'--':>8}"

    for label, key in DISPLAY:
        l2 = sc_l2.get(key, {})
        l2_mean = l2.get("layer2_mean", "--")
        cur     = l2.get("current_mean", "--")
        delta   = l2.get("delta", "--")
        p_val   = l2.get("p_value", "--")
        cd      = l2.get("cliffs_d", "--")
        mag     = l2.get("magnitude", "--")
        sig     = "Y" if l2.get("significant") else "."
        print(f"  {label:<22} {_fmt(l2_mean)} {_fmt(cur)}  "
              f"{_fmt(delta)}  {_fmt(p_val)}  {_fmt(cd)}  {mag:>10}  {sig:>4}")

    bert_cur = data["l3"]["agg"]["coherence_bert_f1"]["mean"]
    print(f"  {'BERTScore':<22} {_fmt(layer2_bert)} {_fmt(bert_cur)}  "
          f"{_fmt(bert_cur - layer2_bert)}")

    print(f"\n  L1 scores: {data['l1']['score_per_run']}")

    print(f"\n{'─'*76}")
    print("  5 SAMPLE CASES — showing user context injection effect")
    print(f"{'─'*76}")

    SOURCE_ICONS = {"pool": "POOL", "crisis": "CRISIS", "llm": "LLM", "empty_skip": "EMPTY"}
    for c in data["sample_cases"]:
        src_label = SOURCE_ICONS.get(c.get("source", ""), c.get("source", "?").upper())
        signals = []
        if c.get("user_context_injected"):
            signals.append("CTX_INJECTED")
        if c.get("frustration_level", 0) >= 1:
            signals.append(f"frust={c['frustration_level']}")
        if c.get("is_b2b"):       signals.append("B2B")
        if c.get("is_correction"): signals.append("correction")
        if c.get("objection_type"): signals.append(f"obj={c['objection_type']}")
        if c.get("user_name"):    signals.append(f"name={c['user_name']!r}")
        if c.get("pool_category"): signals.append(f"pool_cat={c['pool_category']}")
        if c.get("prompt_augmented"): signals.append("aug_prompt")
        sig_str = " | ".join(signals) if signals else "--"
        print(f"\n  Case {c['case_idx']} [{src_label}] [{c['category']}/{c['language']}]")
        print(f"  Signals: {sig_str}")
        if c.get("user_context_block"):
            # Show context block (compact)
            ctx_lines = c["user_context_block"].replace("\n", " | ")
            print(f"  UserCtx: {ctx_lines[:120]}")
        ctx = c.get("conversation_context", [])
        if ctx:
            print(f"  Context (last {len(ctx)} turns):")
            for t in ctx:
                role_tag = "👤" if t["role"] == "user" else "🤖"
                print(f"    {role_tag} {t['content'][:120]}")
        print(f"  Lead:    {c['lead'][:120]!r}")
        print(f"  Bot:     {c['bot_response'][:200]!r}")
        print(f"  GT:      {c['ground_truth'][:100]!r}")

    print(f"\n{'='*76}")
    print("CRITERION: IMPROVES = p<0.05 AND Cliff's |d| >= 0.147 (small effect)")
    print(f"{'='*76}\n")


if __name__ == "__main__":
    asyncio.run(main())
