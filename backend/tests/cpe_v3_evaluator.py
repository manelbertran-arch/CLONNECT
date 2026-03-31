"""
CPE v3 Evaluator — Pure metrics library for AI clone quality evaluation.

4 dimensions:
  D1: Linguistic Style       (CharacterEval "Utterance Consistency")
  D2: Semantic Similarity    (BERTScore + lexical)
  D3: Persona Consistency    (CharacterEval "Character Consistency")
  D4: Conversational Quality (CharacterEval "Conversational Ability")

Paper refs:
- CharacterEval (Tu et al., ACL 2024): 13 metrics, 4 dimensions
- PersonaGym (Samuel et al., EMNLP 2025): PersonaScore
- InCharacter (Wang et al., ACL 2024): BFI interview method
- BERTScore (Zhang et al., ICLR 2020): ρ=0.59 with humans
- Distinct-N (Li et al., NAACL 2016): response diversity
- chrF++ (Popović, WMT 2015): ρ=0.52 for morphologically rich languages
- METEOR (Banerjee & Lavie, ACL 2005): recall-oriented + synonymy
"""

import collections
import math
import re
import statistics
from typing import Dict, List, Optional, Tuple

__all__ = [
    "dim1_linguistic_style",
    "dim2_semantic_similarity",
    "dim3_persona_consistency",
    "dim4_conversational_quality",
    "cpe_v3_score",
    "wilcoxon_signed_rank",
    "cliffs_delta",
    "cliff_magnitude",
    "compare_to_baseline",
    "aggregate_runs",
]

# ---------------------------------------------------------------------------
# Shared regex patterns (copied from cpe_level1_quantitative.py)
# ---------------------------------------------------------------------------

EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\u2600-\u27BF\U0001F900-\U0001F9FF]"
    r"[\U0001F3FB-\U0001F3FF\uFE0F]?"
)

CA_MARKERS = re.compile(
    r"\b(tinc|estic|però|molt|doncs|també|perquè|això|vull|puc|"
    r"gràcies|gracies|bon dia|bona tarda|bona nit|setmana|"
    r"dimarts|dijous|dissabte|diumenge|nosaltres|puguis|vulguis)\b",
    re.IGNORECASE,
)

ES_MARKERS = re.compile(
    r"\b(tengo|estoy|pero|mucho|entonces|también|porque|quiero|"
    r"puedo|necesito|bueno|gracias|vale|claro|genial|"
    r"miércoles|jueves|sábado|domingo|nosotros)\b",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"[.!?]+")
_PRICE_RE = re.compile(r"(\d+)[€$]|[€$](\d+)")
_ASSISTANT_PATTERNS = [
    re.compile(r"en qué puedo ayudarte", re.IGNORECASE),
    re.compile(r"estoy aquí para", re.IGNORECASE),
    re.compile(r"how can i help", re.IGNORECASE),
    re.compile(r"is there anything", re.IGNORECASE),
    re.compile(r"¿en qué te puedo", re.IGNORECASE),
    re.compile(r"how may i assist", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> List[str]:
    """Whitespace + punctuation tokenizer (ES/CA friendly)."""
    return re.findall(r"\b\w+\b", text.lower())


def _detect_lang(text: str) -> str:
    """Fast CA/ES language detection (no external deps)."""
    ca_hits = len(CA_MARKERS.findall(text))
    es_hits = len(ES_MARKERS.findall(text))
    if ca_hits and es_hits:
        return "ca-es"
    if ca_hits > es_hits:
        return "ca"
    if es_hits > 0:
        return "es"
    return "es"


def _compute_bleu4(candidate: str, reference: str) -> float:
    """BLEU-4 (Papineni et al., ACL 2002). Smoothing method 1."""
    cand_tokens = _tokenize(candidate)
    ref_tokens = _tokenize(reference)
    if not cand_tokens or not ref_tokens:
        return 0.0
    bp = 1.0 if len(cand_tokens) >= len(ref_tokens) else math.exp(1 - len(ref_tokens) / len(cand_tokens))
    precisions = []
    for n in range(1, 5):
        cand_ngrams = collections.Counter(
            tuple(cand_tokens[i:i + n]) for i in range(len(cand_tokens) - n + 1)
        )
        ref_ngrams = collections.Counter(
            tuple(ref_tokens[i:i + n]) for i in range(len(ref_tokens) - n + 1)
        )
        clipped = sum(min(cnt, ref_ngrams[ng]) for ng, cnt in cand_ngrams.items())
        total = max(1, sum(cand_ngrams.values()))
        if clipped == 0:
            clipped, total = 1, total + 1
        precisions.append(clipped / total)
    log_avg = sum(math.log(p) for p in precisions) / 4
    return round(bp * math.exp(log_avg), 4)


def _compute_rouge_l(candidate: str, reference: str) -> float:
    """ROUGE-L F1 (Lin, ACL 2004) via LCS dynamic programming."""
    cand_tokens = _tokenize(candidate)
    ref_tokens = _tokenize(reference)
    if not cand_tokens or not ref_tokens:
        return 0.0
    m, n = len(ref_tokens), len(cand_tokens)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if ref_tokens[i - 1] == cand_tokens[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs_len = dp[m][n]
    precision = lcs_len / n if n > 0 else 0.0
    recall = lcs_len / m if m > 0 else 0.0
    if precision + recall == 0:
        return 0.0
    return round(2 * precision * recall / (precision + recall), 4)


def _compute_chrf(candidate: str, reference: str, n: int = 6) -> float:
    """chrF++ (Popović, WMT 2015). Character n-gram F1."""
    if not candidate or not reference:
        return 0.0
    cand = candidate.lower()
    ref = reference.lower()
    total_p = total_r = 0.0
    count = 0
    for order in range(1, n + 1):
        cand_ngrams = collections.Counter(cand[i:i + order] for i in range(len(cand) - order + 1))
        ref_ngrams = collections.Counter(ref[i:i + order] for i in range(len(ref) - order + 1))
        matched = sum(min(cand_ngrams[ng], ref_ngrams[ng]) for ng in cand_ngrams if ng in ref_ngrams)
        total_p += matched / max(1, sum(cand_ngrams.values()))
        total_r += matched / max(1, sum(ref_ngrams.values()))
        count += 1
    avg_p = total_p / count
    avg_r = total_r / count
    if avg_p + avg_r == 0:
        return 0.0
    return round(2 * avg_p * avg_r / (avg_p + avg_r), 4)


def _compute_vocab_overlap(candidate: str, reference: str) -> float:
    """Jaccard similarity of word sets."""
    cand_words = set(_tokenize(candidate))
    ref_words = set(_tokenize(reference))
    if not cand_words or not ref_words:
        return 0.0
    union = cand_words | ref_words
    return round(len(cand_words & ref_words) / len(union), 4) if union else 0.0


def _compute_meteor(candidate: str, reference: str) -> Optional[float]:
    """METEOR (Banerjee & Lavie 2005) via nltk. Returns None if unavailable."""
    try:
        import nltk
        from nltk.translate.meteor_score import meteor_score as nltk_meteor
        try:
            nltk.data.find("wordnet")
        except LookupError:
            nltk.download("wordnet", quiet=True)
        try:
            nltk.data.find("omw-1.4")
        except LookupError:
            nltk.download("omw-1.4", quiet=True)
        cand_tokens = _tokenize(candidate)
        ref_tokens = _tokenize(reference)
        if not cand_tokens or not ref_tokens:
            return 0.0
        return round(float(nltk_meteor([ref_tokens], cand_tokens)), 4)
    except (ImportError, Exception):
        return None


def _compute_bertscore_batch(
    candidates: List[str],
    references: List[str],
    model_type: str = "xlm-roberta-large",
) -> Optional[List[float]]:
    """Returns per-pair F1 list or None if bert_score unavailable."""
    try:
        from bert_score import score as bert_score_fn
    except ImportError:
        return None

    valid_idx, valid_cands, valid_refs = [], [], []
    for i, (c, r) in enumerate(zip(candidates, references)):
        if c and r:
            valid_idx.append(i)
            valid_cands.append(c)
            valid_refs.append(r)

    if not valid_cands:
        return [0.0] * len(candidates)

    _, _, F1 = bert_score_fn(
        cands=valid_cands,
        refs=valid_refs,
        model_type=model_type,
        batch_size=16,
        verbose=False,
        rescale_with_baseline=False,
    )

    per_pair = [0.0] * len(candidates)
    for list_idx, orig_idx in enumerate(valid_idx):
        per_pair[orig_idx] = round(F1[list_idx].item(), 4)
    return per_pair


def _safe_mean(vals: List[float]) -> float:
    return statistics.mean(vals) if vals else 0.0


def _safe_median(vals: List[float]) -> float:
    return statistics.median(vals) if vals else 0.0


def _safe_std(vals: List[float]) -> float:
    return statistics.stdev(vals) if len(vals) > 1 else 0.0


# ---------------------------------------------------------------------------
# DIMENSION 1: Linguistic Style
# ---------------------------------------------------------------------------

def dim1_linguistic_style(
    responses: List[str],
    baseline_metrics: dict,
    calibration: dict,
) -> dict:
    """D1 — Linguistic Style (CharacterEval Utterance Consistency).

    Args:
        responses: list of bot response strings
        baseline_metrics: dict from baseline_metrics.json (metrics.* keys)
        calibration: dict from calibrations/*.json

    Returns:
        dict with char stats, rate metrics, diversity, l1_score
    """
    if not responses:
        return {
            "char_mean": 0.0, "char_median": 0.0, "char_std": 0.0,
            "emoji_rate": 0.0, "excl_rate": 0.0, "q_rate": 0.0,
            "distinct_1": 0.0, "distinct_2": 0.0,
            "avg_sentences": 0.0, "avg_tokens": 0.0,
            "code_switching": {}, "l1_score": 0.0,
            "l1_passed": 0, "l1_total": 7, "details": {},
        }

    responses = [r or "" for r in responses]
    n = len(responses)

    # Character length stats
    lengths = [len(r) for r in responses]
    char_mean = _safe_mean(lengths)
    char_median = _safe_median(lengths)
    char_std = _safe_std(lengths)

    # Binary rates
    has_emoji = [bool(EMOJI_RE.search(r)) for r in responses]
    has_excl = ["!" in r for r in responses]
    has_q = ["?" in r for r in responses]
    emoji_rate = sum(has_emoji) / n
    excl_rate = sum(has_excl) / n
    q_rate = sum(has_q) / n

    # Distinct-N (Li et al., NAACL 2016) — across all responses concatenated
    all_tokens: List[str] = []
    for r in responses:
        all_tokens.extend(_tokenize(r))

    if all_tokens:
        unigrams = all_tokens
        distinct_1 = len(set(unigrams)) / len(unigrams)
        bigrams = [tuple(all_tokens[i:i + 2]) for i in range(len(all_tokens) - 1)]
        distinct_2 = len(set(bigrams)) / len(bigrams) if bigrams else 0.0
    else:
        distinct_1 = distinct_2 = 0.0

    # Sentence and token averages
    sentence_counts = [max(1, len([s for s in _SENTENCE_SPLIT.split(r.strip()) if s.strip()])) for r in responses]
    token_counts = [len(r.split()) for r in responses]
    avg_sentences = _safe_mean(sentence_counts)
    avg_tokens = _safe_mean(token_counts)

    # Code-switching distribution
    langs = [_detect_lang(r) for r in responses]
    lang_counter = collections.Counter(langs)
    code_switching = {lang: round(cnt / n * 100, 2) for lang, cnt in lang_counter.items()}

    # --- L1 pass-rate vs baseline ---
    bm = baseline_metrics.get("metrics", baseline_metrics)  # handle both wrapped and flat

    def _bm(key: str, default: float = 0.0) -> float:
        """Navigate dotted path like 'emoji.emoji_rate_pct'."""
        parts = key.split(".")
        node = bm
        for p in parts:
            if isinstance(node, dict):
                node = node.get(p, None)
            else:
                return default
            if node is None:
                return default
        # Return raw value for non-scalar types; try float for scalars
        if isinstance(node, (list, dict)):
            return node  # type: ignore[return-value]
        try:
            return float(node)
        except (TypeError, ValueError):
            return default

    creator_emoji_rate = _bm("emoji.emoji_rate_pct", 0.0) / 100.0
    creator_excl_rate = _bm("punctuation.exclamation_rate_pct", 0.0) / 100.0
    creator_q_rate = _bm("punctuation.question_rate_pct", 0.0) / 100.0
    creator_len_mean = _bm("length.char_mean", 1.0)
    creator_len_median = _bm("length.char_median", 1.0)

    # CA rate from baseline languages.detected — list of {lang, pct} dicts
    creator_langs_raw = _bm("languages.detected", [])
    if isinstance(creator_langs_raw, list):
        creator_ca_rate = sum(
            d.get("pct", 0) for d in creator_langs_raw
            if isinstance(d, dict) and d.get("lang") in ("ca", "ca-es")
        ) / 100.0
    elif isinstance(creator_langs_raw, dict):
        creator_ca_rate = (creator_langs_raw.get("ca", 0) + creator_langs_raw.get("ca-es", 0)) / 100.0
    else:
        creator_ca_rate = 0.0

    bot_ca_rate = (code_switching.get("ca", 0.0) + code_switching.get("ca-es", 0.0)) / 100.0

    # Vocab Jaccard: bot words vs baseline top_50 (list of [word, count] pairs)
    top50_raw = _bm("vocabulary.top_50", [])
    if isinstance(top50_raw, list) and top50_raw:
        if isinstance(top50_raw[0], (list, tuple)):
            creator_top50 = set(w[0] for w in top50_raw if w)
        else:
            creator_top50 = set(top50_raw)
    else:
        creator_top50 = set()
    creator_top50_for_jaccard = creator_top50  # alias for clarity
    if not creator_top50:
        creator_top50 = set()
    bot_vocab = set(all_tokens)
    if creator_top50 and bot_vocab:
        vocab_jaccard = len(creator_top50 & bot_vocab) / len(creator_top50 | bot_vocab)
    else:
        vocab_jaccard = 0.0

    tolerances = [
        ("emoji_rate", abs(emoji_rate - creator_emoji_rate) <= 0.20, emoji_rate, creator_emoji_rate, "±20pp"),
        ("excl_rate", abs(excl_rate - creator_excl_rate) <= 0.10, excl_rate, creator_excl_rate, "±10pp"),
        ("q_rate", abs(q_rate - creator_q_rate) <= 0.20, q_rate, creator_q_rate, "±20pp"),
        ("len_mean", (creator_len_mean == 0 or abs(char_mean - creator_len_mean) / max(creator_len_mean, 1) <= 0.30),
         char_mean, creator_len_mean, "±30%"),
        ("len_median", (creator_len_median == 0 or abs(char_median - creator_len_median) / max(creator_len_median, 1) <= 0.30),
         char_median, creator_len_median, "±30%"),
        ("ca_rate", abs(bot_ca_rate - creator_ca_rate) <= 0.20, bot_ca_rate, creator_ca_rate, "±20pp"),
        ("vocab_jaccard", vocab_jaccard > 0.05, vocab_jaccard, None, ">5%"),
    ]

    details = {}
    passed = 0
    for name, ok, bot_val, creator_val, tol in tolerances:
        details[name] = {
            "bot": round(bot_val, 4),
            "creator": round(creator_val, 4) if creator_val is not None else None,
            "tolerance": tol,
            "pass": ok,
        }
        if ok:
            passed += 1

    total = len(tolerances)
    l1_score = round(passed / total, 4)

    return {
        "char_mean": round(char_mean, 2),
        "char_median": round(char_median, 2),
        "char_std": round(char_std, 2),
        "emoji_rate": round(emoji_rate, 4),
        "excl_rate": round(excl_rate, 4),
        "q_rate": round(q_rate, 4),
        "distinct_1": round(distinct_1, 4),
        "distinct_2": round(distinct_2, 4),
        "avg_sentences": round(avg_sentences, 2),
        "avg_tokens": round(avg_tokens, 2),
        "code_switching": code_switching,
        "l1_score": l1_score,
        "l1_passed": passed,
        "l1_total": total,
        "details": details,
    }


# ---------------------------------------------------------------------------
# DIMENSION 2: Semantic Similarity
# ---------------------------------------------------------------------------

def dim2_semantic_similarity(
    results: List[dict],
    *,
    bert_model: str = "xlm-roberta-large",
    skip_bertscore: bool = False,
) -> dict:
    """D2 — Semantic Similarity (BERTScore + lexical).

    Args:
        results: list of test case dicts with 'bot_response' and 'ground_truth'
        bert_model: BERTScore model identifier
        skip_bertscore: if True, skip BERTScore computation

    Returns:
        dict with bertscore_f1, chrf, rouge_l, bleu4, meteor, vocab_overlap, composite
    """
    if not results:
        return {
            "bertscore_f1": None, "chrf": 0.0, "rouge_l": 0.0,
            "bleu4": 0.0, "meteor": None, "vocab_overlap": 0.0,
            "composite": 0.0,
            "_per_case_bertscore": [], "_per_case_chrf": [],
        }

    candidates = [r.get("bot_response") or "" for r in results]
    references = [r.get("ground_truth") or "" for r in results]

    # Lexical metrics
    chrf_scores = [_compute_chrf(c, r) for c, r in zip(candidates, references)]
    rouge_scores = [_compute_rouge_l(c, r) for c, r in zip(candidates, references)]
    bleu_scores = [_compute_bleu4(c, r) for c, r in zip(candidates, references)]
    vocab_scores = [_compute_vocab_overlap(c, r) for c, r in zip(candidates, references)]

    mean_chrf = _safe_mean(chrf_scores)
    mean_rouge = _safe_mean(rouge_scores)
    mean_bleu = _safe_mean(bleu_scores)
    mean_vocab = _safe_mean(vocab_scores)

    # METEOR (optional)
    meteor_scores_raw = [_compute_meteor(c, r) for c, r in zip(candidates, references)]
    valid_meteor = [s for s in meteor_scores_raw if s is not None]
    mean_meteor: Optional[float] = _safe_mean(valid_meteor) if valid_meteor else None  # type: ignore[assignment]

    # BERTScore (optional)
    mean_bertscore: Optional[float] = None
    per_case_bertscore: List[float] = []
    if not skip_bertscore:
        bs_list = _compute_bertscore_batch(candidates, references, model_type=bert_model)
        if bs_list is not None:
            per_case_bertscore = bs_list
            valid_bs = [s for s in bs_list if s > 0.0]
            mean_bertscore = round(_safe_mean(valid_bs), 4) if valid_bs else 0.0

    # Composite score with weight fallback
    if mean_bertscore is not None and mean_meteor is not None:
        composite = (
            0.4 * mean_bertscore
            + 0.2 * mean_chrf
            + 0.2 * mean_meteor
            + 0.1 * mean_rouge
            + 0.1 * mean_bleu
        )
    elif mean_bertscore is None and mean_meteor is not None:
        composite = (
            0.35 * mean_chrf
            + 0.30 * mean_meteor
            + 0.20 * mean_rouge
            + 0.15 * mean_bleu
        )
    elif mean_bertscore is not None and mean_meteor is None:
        # BERTScore available, METEOR not
        composite = (
            0.4 * mean_bertscore
            + 0.25 * mean_chrf
            + 0.20 * mean_rouge
            + 0.15 * mean_bleu
        )
    else:
        # Neither BERTScore nor METEOR
        composite = (
            0.40 * mean_chrf
            + 0.35 * mean_rouge
            + 0.25 * mean_bleu
        )

    return {
        "bertscore_f1": round(mean_bertscore, 4) if mean_bertscore is not None else None,
        "chrf": round(mean_chrf, 4),
        "rouge_l": round(mean_rouge, 4),
        "bleu4": round(mean_bleu, 4),
        "meteor": round(mean_meteor, 4) if mean_meteor is not None else None,
        "vocab_overlap": round(mean_vocab, 4),
        "composite": round(composite, 4),
        "_per_case_bertscore": per_case_bertscore,
        "_per_case_chrf": chrf_scores,
    }


# ---------------------------------------------------------------------------
# DIMENSION 3: Persona Consistency
# ---------------------------------------------------------------------------

def dim3_persona_consistency(results: List[dict], calibration: dict) -> dict:
    """D3 — Persona Consistency (CharacterEval Character Consistency).

    Args:
        results: list of test case dicts with 'bot_response'
        calibration: dict from calibrations/*.json (uses 'creator_vocabulary')

    Returns:
        dict with catchphrase_hit_rate, repetition_rate, persona_score, etc.
    """
    responses = [r.get("bot_response") or "" for r in results]
    n = len(responses)

    if n == 0:
        return {
            "catchphrase_hit_rate": None,
            "repetition_rate": 0.0,
            "no_response_rate": 0.0,
            "assistant_language_rate": 0.0,
            "persona_score": 0.0,
        }

    creator_vocab = [w.lower() for w in (calibration.get("creator_vocabulary") or [])]

    # Catchphrase hit rate
    if creator_vocab:
        hits = 0
        for resp in responses:
            resp_lower = resp.lower()
            if any(word in resp_lower for word in creator_vocab):
                hits += 1
        catchphrase_hit_rate: Optional[float] = hits / n
    else:
        catchphrase_hit_rate = None

    # Repetition rate: any 3+ token sequence that repeats within the same response
    repetition_count = 0
    for resp in responses:
        tokens = _tokenize(resp)
        if len(tokens) < 6:
            continue
        trigrams = [tuple(tokens[i:i + 3]) for i in range(len(tokens) - 2)]
        tg_counts = collections.Counter(trigrams)
        if any(cnt > 1 for cnt in tg_counts.values()):
            repetition_count += 1
    repetition_rate = repetition_count / n

    # No-response rate (empty or < 5 chars)
    no_resp_count = sum(1 for r in responses if len(r.strip()) < 5)
    no_response_rate = no_resp_count / n

    # Assistant language rate
    assistant_count = 0
    for resp in responses:
        if any(pat.search(resp) for pat in _ASSISTANT_PATTERNS):
            assistant_count += 1
    assistant_language_rate = assistant_count / n

    # Persona score composite
    persona_score = (
        (catchphrase_hit_rate if catchphrase_hit_rate is not None else 0.5) * 0.4
        + (1.0 - repetition_rate) * 0.3
        + (1.0 - assistant_language_rate) * 0.3
    )

    return {
        "catchphrase_hit_rate": round(catchphrase_hit_rate, 4) if catchphrase_hit_rate is not None else None,
        "repetition_rate": round(repetition_rate, 4),
        "no_response_rate": round(no_response_rate, 4),
        "assistant_language_rate": round(assistant_language_rate, 4),
        "persona_score": round(persona_score, 4),
    }


# ---------------------------------------------------------------------------
# DIMENSION 4: Conversational Quality
# ---------------------------------------------------------------------------

def dim4_conversational_quality(results: List[dict], calibration: dict) -> dict:
    """D4 — Conversational Quality (CharacterEval Conversational Ability).

    Args:
        results: list of test case dicts with 'test_input', 'bot_response'
        calibration: dict from calibrations/*.json

    Returns:
        dict with coherence_bertscore, hallucination_rate, length_ratio, quality_score
    """
    if not results:
        return {
            "coherence_bertscore": 0.0,
            "hallucination_rate": 0.0,
            "length_ratio": 0.0,
            "quality_score": 0.0,
        }

    inputs = [r.get("test_input") or "" for r in results]
    responses = [r.get("bot_response") or "" for r in results]
    n = len(results)

    # Coherence: BERTScore between input and bot_response
    coherence_bertscore: float
    bs_list = _compute_bertscore_batch(inputs, responses)
    if bs_list is not None:
        valid_bs = [s for s in bs_list if s > 0.0]
        coherence_bertscore = round(_safe_mean(valid_bs), 4) if valid_bs else 0.0
    else:
        # Fallback: vocabulary overlap between input and response
        overlap_scores = [_compute_vocab_overlap(inp, resp) for inp, resp in zip(inputs, responses)]
        coherence_bertscore = round(_safe_mean(overlap_scores), 4)

    # Hallucination rate: % responses mentioning a price not in calibration
    cal_text = str(calibration.get("response_pools", {}))
    cal_prices_raw = re.findall(r"(\d+)[€$]|[€$](\d+)", cal_text)
    cal_prices = set()
    for a, b in cal_prices_raw:
        cal_prices.add(a or b)

    hallucination_count = 0
    for resp in responses:
        price_matches = _PRICE_RE.findall(resp)
        if price_matches:
            if cal_prices:
                mentioned = {a or b for a, b in price_matches}
                if not mentioned.issubset(cal_prices):
                    hallucination_count += 1
            # If no calibration prices, assume any price mention is fine
    hallucination_rate = hallucination_count / n if n > 0 else 0.0

    # Length ratio: bot_len_mean / creator_len_median
    baseline = calibration.get("baseline", {})
    creator_len_median = float(baseline.get("median_length", 0) or 0)
    bot_lengths = [len(r) for r in responses]
    bot_len_mean = _safe_mean(bot_lengths)
    if creator_len_median > 0:
        length_ratio = bot_len_mean / creator_len_median
    else:
        length_ratio = 1.0
    length_deviation = abs(length_ratio - 1.0)

    # Coherence gap: invert so that higher coherence = lower gap
    # coherence_bertscore is already in [0,1] — use (1 - coherence) as the gap
    coherence_gap = 1.0 - coherence_bertscore

    quality_score = (
        (1.0 - coherence_gap) * 0.5
        + (1.0 - hallucination_rate) * 0.3
        + max(0.0, 1.0 - length_deviation) * 0.2
    )

    return {
        "coherence_bertscore": coherence_bertscore,
        "hallucination_rate": round(hallucination_rate, 4),
        "length_ratio": round(length_deviation, 4),
        "quality_score": round(quality_score, 4),
    }


# ---------------------------------------------------------------------------
# COMPOSITE SCORE
# ---------------------------------------------------------------------------

def cpe_v3_score(d1: dict, d2: dict, d3: dict, d4: dict) -> dict:
    """Compute overall CPE v3 composite score from the 4 dimension dicts.

    Returns:
        dict with 'overall' (0-1), 'grade' (A/B/C/D), 'dimensions' breakdown
    """
    l1 = float(d1.get("l1_score") or 0.0)
    d2_comp = float(d2.get("composite") or 0.0)
    persona = float(d3.get("persona_score") or 0.0)
    quality = float(d4.get("quality_score") or 0.0)

    overall = round(
        0.25 * l1
        + 0.35 * d2_comp
        + 0.20 * persona
        + 0.20 * quality,
        4,
    )

    if overall > 0.7:
        grade = "A"
    elif overall > 0.5:
        grade = "B"
    elif overall > 0.3:
        grade = "C"
    else:
        grade = "D"

    return {
        "overall": overall,
        "grade": grade,
        "dimensions": {
            "d1_linguistic_style": round(l1, 4),
            "d2_semantic_similarity": round(d2_comp, 4),
            "d3_persona_consistency": round(persona, 4),
            "d4_conversational_quality": round(quality, 4),
        },
    }


# ---------------------------------------------------------------------------
# STATISTICAL FUNCTIONS
# ---------------------------------------------------------------------------

def wilcoxon_signed_rank(x: List[float], y: List[float]) -> Tuple[float, float]:
    """Wilcoxon signed-rank test. Returns (statistic, p_value).

    Uses scipy.stats.wilcoxon if available, otherwise implements manually.
    """
    if len(x) != len(y):
        raise ValueError("x and y must have the same length")

    try:
        from scipy.stats import wilcoxon as scipy_wilcoxon
        stat, p = scipy_wilcoxon(x, y)
        return float(stat), float(p)
    except ImportError:
        pass

    # Manual implementation (normal approximation for n>=10)
    diffs = [xi - yi for xi, yi in zip(x, y)]
    non_zero = [(abs(d), d) for d in diffs if d != 0]
    if not non_zero:
        return 0.0, 1.0

    # Rank absolute differences
    sorted_nd = sorted(enumerate(non_zero), key=lambda t: t[1][0])
    ranks = [0.0] * len(non_zero)
    i = 0
    while i < len(sorted_nd):
        j = i
        while j < len(sorted_nd) - 1 and sorted_nd[j + 1][1][0] == sorted_nd[j][1][0]:
            j += 1
        avg_rank = (i + j + 2) / 2.0  # 1-indexed
        for k in range(i, j + 1):
            ranks[sorted_nd[k][0]] = avg_rank
        i = j + 1

    w_plus = sum(r for r, (_, (_, d)) in zip(ranks, sorted_nd) if d > 0)
    w_minus = sum(r for r, (_, (_, d)) in zip(ranks, sorted_nd) if d < 0)
    stat = min(w_plus, w_minus)

    n = len(non_zero)
    if n < 10:
        # Return statistic only, p approximation not reliable
        return stat, float("nan")

    # Normal approximation
    mean_w = n * (n + 1) / 4.0
    var_w = n * (n + 1) * (2 * n + 1) / 24.0
    z = (stat - mean_w) / math.sqrt(var_w) if var_w > 0 else 0.0

    # Two-tailed p-value via error function approximation
    def _norm_cdf(z_val: float) -> float:
        return 0.5 * (1.0 + math.erf(z_val / math.sqrt(2)))

    p_value = 2.0 * min(_norm_cdf(z), 1.0 - _norm_cdf(z))
    return stat, round(p_value, 6)


def cliffs_delta(x: List[float], y: List[float]) -> float:
    """Cliff's delta effect size. Negative = x worse than y, positive = x better.

    d = (number of x>y pairs - number of x<y pairs) / (n_x * n_y)
    """
    if not x or not y:
        return 0.0
    greater = sum(1 for xi in x for yi in y if xi > yi)
    less = sum(1 for xi in x for yi in y if xi < yi)
    return round((greater - less) / (len(x) * len(y)), 4)


def cliff_magnitude(d: float) -> str:
    """Interpret Cliff's delta magnitude.

    Thresholds: Romano et al. (2006) as used in NLP ablation literature.
    """
    abs_d = abs(d)
    if abs_d < 0.147:
        return "negligible"
    if abs_d < 0.330:
        return "small"
    if abs_d < 0.474:
        return "medium"
    return "large"


def compare_to_baseline(
    current_d2_scores: List[float],
    baseline_d2_scores: List[float],
) -> dict:
    """Statistical comparison of two score lists (e.g. D2 per-case chrF).

    Returns:
        dict with wilcoxon_p, cliffs_delta, magnitude, decision
        decision: 'IMPROVES' | 'HURTS' | 'NO_EFFECT'
    """
    if not current_d2_scores or not baseline_d2_scores:
        return {
            "wilcoxon_p": None,
            "cliffs_delta": None,
            "magnitude": None,
            "decision": "NO_EFFECT",
        }

    min_len = min(len(current_d2_scores), len(baseline_d2_scores))
    cur = current_d2_scores[:min_len]
    base = baseline_d2_scores[:min_len]

    _, p_value = wilcoxon_signed_rank(cur, base)
    delta = cliffs_delta(cur, base)
    magnitude = cliff_magnitude(delta)

    p_significant = (not math.isnan(p_value)) and p_value < 0.05
    if p_significant and delta > 0:
        decision = "IMPROVES"
    elif p_significant and delta < 0:
        decision = "HURTS"
    else:
        decision = "NO_EFFECT"

    return {
        "wilcoxon_p": round(p_value, 6) if not math.isnan(p_value) else None,
        "cliffs_delta": delta,
        "magnitude": magnitude,
        "decision": decision,
    }


def aggregate_runs(run_dicts: List[dict]) -> dict:
    """Aggregate multiple evaluation run dicts (same keys, float values).

    Returns:
        {key: {mean, std, runs: [...]}} for each numeric key
    """
    if not run_dicts:
        return {}

    all_keys = set()
    for rd in run_dicts:
        all_keys.update(k for k, v in rd.items() if isinstance(v, (int, float)) and v is not None)

    result = {}
    for key in sorted(all_keys):
        vals = [float(rd[key]) for rd in run_dicts if key in rd and isinstance(rd[key], (int, float))]
        result[key] = {
            "mean": round(_safe_mean(vals), 6),
            "std": round(_safe_std(vals), 6),
            "runs": vals,
        }
    return result
