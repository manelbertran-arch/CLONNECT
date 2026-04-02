"""Compressed Doc D — Universal personality prompt builder.

Generates a ~2-3K char personality prompt from:
- BFI profile (tests/cpe_data/{creator}/bfi_profile.json)
- Baseline metrics (tests/cpe_data/{creator}/baseline_metrics.json)
- Creator DB data (name, products)
- Calibration few-shot examples (calibrations/{creator}.json)

Based on:
- PersonaGym (EMNLP 2025): 150-300 word structured descriptions outperform
  verbose documents. Quantitative constraints need behavioral examples.
- RoleLLM (ACL 2024): 3-5 few-shot examples are the #1 lever for style fidelity.
- CharacterEval (ACL 2024): Structured sections beat prose paragraphs.

Structure: Identity → Personality → Style → Examples → Constraints
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Canonical stopwords — imported from vocabulary_extractor (single source of truth)
from services.vocabulary_extractor import STOPWORDS as _STOP_WORDS

# BFI trait labels (Big Five Inventory) — gender-neutral phrasing
# Each label must read naturally after "muy " prefix
_BFI_LABELS = {
    "O": ("Openness", "abierta/o a nuevas experiencias", "convencional y práctica/o"),
    "C": ("Conscientiousness", "organizada/o y disciplinada/o", "espontánea/o y flexible"),
    "E": ("Extraversion", "sociable y extrovertida/o", "reservada/o e introvertida/o"),
    "A": ("Agreeableness", "empática/o y cooperativa/o", "directa/o y competitiva/o"),
    "N": ("Neuroticism", "emocionalmente reactiva/o", "emocionalmente estable"),
}


def _bfi_summary(scores: Dict[str, float]) -> str:
    """Convert BFI scores to natural language personality summary."""
    traits = []
    for dim, score in scores.items():
        if dim not in _BFI_LABELS:
            continue
        _, high_label, low_label = _BFI_LABELS[dim]
        if score >= 4.0:
            traits.append(f"muy {high_label}")
        elif score >= 3.5:
            traits.append(high_label)
        elif score <= 2.0:
            traits.append(f"muy {low_label}")
        elif score <= 2.5:
            traits.append(low_label)
    return ", ".join(traits) if traits else "personalidad equilibrada"


def _load_json(path: str) -> Optional[dict]:
    """Load JSON file, return None on failure."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Failed to load %s: %s", path, e)
        return None


def _load_profile_with_db_fallback(creator_id: str, profile_type: str, file_name: str) -> Optional[dict]:
    """Load profile from DB first, then fall back to local file."""
    # 1. Try DB
    try:
        from services.creator_profile_service import get_profile
        db_data = get_profile(creator_id, profile_type)
        if db_data:
            return db_data
    except Exception:
        pass
    # 2. Fallback: local file
    path = Path("tests/cpe_data") / creator_id / file_name
    return _load_json(str(path))


def _get_creator_products(creator_id: str) -> str:
    """Get product list from DB."""
    try:
        from api.database import SessionLocal
        from sqlalchemy import text

        session = SessionLocal()
        try:
            rows = session.execute(
                text(
                    "SELECT p.name, p.price FROM products p "
                    "JOIN creators c ON c.id = p.creator_id "
                    "WHERE c.name = :cid AND p.active = true "
                    "ORDER BY p.name LIMIT 10"
                ),
                {"cid": creator_id},
            ).fetchall()
            if not rows:
                return ""
            lines = [f"  - {r[0]}: {r[1]}€" for r in rows]
            return "\n".join(lines)
        finally:
            session.close()
    except Exception as e:
        logger.debug("Failed to load products for %s: %s", creator_id, e)
        return ""


def _get_creator_display_name(creator_id: str) -> str:
    """Get creator display name from DB."""
    try:
        from api.database import SessionLocal
        from sqlalchemy import text

        session = SessionLocal()
        try:
            row = session.execute(
                text("SELECT display_name, name FROM creators WHERE name = :cid"),
                {"cid": creator_id},
            ).first()
            if row:
                return row[0] or row[1].replace("_", " ").title()
            return creator_id.replace("_", " ").title()
        finally:
            session.close()
    except Exception:
        return creator_id.replace("_", " ").title()


def _get_length_divergence(creator_id: str) -> Optional[float]:
    """Read stored length divergence (bot_mean / creator_median) from DB.

    Populated by Level 1 runs: save_profile(creator_id, "bot_natural_rates",
    {"length_divergence": bot_mean / creator_median, ...}).

    Returns None if no measurement exists.
    """
    try:
        from services.creator_profile_service import get_profile
        data = get_profile(creator_id, "bot_natural_rates")
        if data and data.get("length_divergence") is not None:
            return float(data["length_divergence"])
    except Exception:
        pass
    return None


def _get_characteristic_vocab(metrics: Dict[str, Any]) -> str:
    """Extract characteristic vocabulary from creator's data.

    Merges top_50 vocabulary + greeting openers, filters stop words,
    deduplicates, and returns a single compact section.
    """
    lines = []

    vocab = metrics.get("vocabulary", {})
    top_words = vocab.get("top_50", [])

    # Filter stop words and short tokens, keep characteristic words only
    char_words = [
        w[0] for w in top_words
        if w[0].lower() not in _STOP_WORDS and len(w[0]) > 1
    ][:15]
    if char_words:
        lines.append(f"- Vocabulario habitual: {', '.join(char_words)}")

    # Opener expressions (deduplicated vs vocab)
    greeting = metrics.get("greeting_patterns", {})
    openers = greeting.get("top_15_openers", [])
    seen = set(w.lower() for w in char_words)
    char_openers = [
        o[0] for o in openers
        if o[0].lower() not in _STOP_WORDS
        and len(o[0]) > 1
        and o[0].lower() not in seen
    ][:5]
    if char_openers:
        lines.append(f"- Expresiones de apertura: {', '.join(char_openers)}")

    return "\n".join(lines)


def _get_few_shot_examples(
    creator_id: str,
    baseline: Optional[Dict] = None,
    n: int = 5,
) -> str:
    """Load few-shot examples with stratified sampling by length + intent.

    Selection strategy (based on RoleLLM + CharacterEval):
    1. Define length buckets from creator's real percentiles (p25, p75)
    2. Sample proportionally: ~25% short, ~50% medium, ~25% long
    3. Maximize intent/context diversity (no duplicate contexts)
    4. Within each bucket: prefer no-emoji majority (mirrors real distribution)

    Args:
        creator_id: Creator slug
        baseline: Baseline metrics dict (optional, used for length percentiles)
        n: Number of examples to select (default 5)
    """
    try:
        from services.calibration_loader import load_calibration

        cal = load_calibration(creator_id)
        if not cal:
            return ""

        examples = cal.get("few_shot_examples", [])
        if not examples:
            return ""

        # --- Length buckets from creator's real distribution ---
        p25, p75 = 13, 53  # defaults (Iris-like)
        if baseline and baseline.get("metrics"):
            length_m = baseline["metrics"].get("length", {})
            p25 = length_m.get("char_p25", 13)
            p75 = length_m.get("char_p75", 53)

        # Bucket assignment
        def _bucket(ex):
            resp_len = len(ex.get("response", ""))
            if resp_len < p25:
                return "short"
            elif resp_len <= p75:
                return "medium"
            else:
                return "long"

        # Split into buckets
        buckets = {"short": [], "medium": [], "long": []}
        for ex in examples:
            if len(ex.get("response", "")) >= 3:  # skip empty/trivial
                buckets[_bucket(ex)].append(ex)

        # Target allocation: match real distribution (25/50/25)
        n_short = max(1, round(n * 0.25))
        n_long = max(1, round(n * 0.25))
        n_medium = n - n_short - n_long

        # --- Intent-diverse selection within each bucket ---
        emoji_pat = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]")

        def _pick_diverse(
            pool: List[Dict], count: int, seen_contexts: set, seen_responses: set,
        ) -> List[Dict]:
            """Pick examples maximizing context + response diversity."""
            if not pool:
                return []

            # Sort: no-emoji first (majority), then by response length (ascending)
            pool_sorted = sorted(
                pool,
                key=lambda ex: (
                    bool(emoji_pat.search(ex.get("response", ""))),  # no-emoji first
                    len(ex.get("response", "")),
                ),
            )

            picked = []
            for ex in pool_sorted:
                if len(picked) >= count:
                    break
                ctx = ex.get("context", "unknown")
                resp = ex.get("response", "").strip()
                # Skip duplicate responses
                if resp in seen_responses:
                    continue
                # Prefer unseen contexts for diversity
                if ctx not in seen_contexts:
                    picked.append(ex)
                    seen_contexts.add(ctx)
                    seen_responses.add(resp)

            # If not enough unique contexts, fill from remaining
            for ex in pool_sorted:
                if len(picked) >= count:
                    break
                resp = ex.get("response", "").strip()
                if ex not in picked and resp not in seen_responses:
                    picked.append(ex)
                    seen_responses.add(resp)

            return picked

        seen_ctx = set()
        seen_resp = set()
        selected = []
        # Pick medium first (largest allocation, most representative)
        selected.extend(_pick_diverse(buckets["medium"], n_medium, seen_ctx, seen_resp))
        # Then short and long
        selected.extend(_pick_diverse(buckets["short"], n_short, seen_ctx, seen_resp))
        selected.extend(_pick_diverse(buckets["long"], n_long, seen_ctx, seen_resp))

        if not selected:
            return ""

        # Ensure at least 1 emoji example if creator uses emoji (>5%)
        emoji_rate = 50  # default
        if baseline and baseline.get("metrics"):
            emoji_rate = baseline["metrics"].get("emoji", {}).get("emoji_rate_pct", 50)
        has_any_emoji = any(emoji_pat.search(ex.get("response", "")) for ex in selected)
        if emoji_rate > 5 and not has_any_emoji and len(selected) >= 3:
            # Swap one MEDIUM example (largest bucket) for an emoji example
            # from the same bucket to preserve length diversity
            emoji_candidates = [
                ex for ex in buckets["medium"]
                if emoji_pat.search(ex.get("response", ""))
                and ex.get("response", "").strip() not in seen_resp
            ]
            if emoji_candidates:
                pick = emoji_candidates[0]
                # Replace a medium-bucket no-emoji example (not the first one)
                for i in range(len(selected) - 1, -1, -1):
                    if _bucket(selected[i]) == "medium":
                        selected[i] = pick
                        break

        # Sort final selection by length for natural reading order (short→long)
        selected.sort(key=lambda ex: len(ex.get("response", "")))

        lines = []
        for ex in selected:
            user = ex.get("user_message", "")[:60]
            resp = ex.get("response", "")
            lines.append(f"Lead: \"{user}\"\nTú: \"{resp}\"")

        return "\n".join(lines)

    except Exception as e:
        logger.debug("Failed to load few-shot for %s: %s", creator_id, e)
        return ""


def _detect_prompt_language(metrics: Dict[str, Any]) -> str:
    """Detect the dominant language for prompt instructions.

    Returns 'es' (Spanish), 'ca' (Catalan), 'pt' (Portuguese), 'en' (English).
    """
    detected = metrics.get("languages", {}).get("detected", [])
    if not detected:
        return "es"

    # Check if there's a clear dominant language
    top = detected[0]
    lang = top.get("lang", "es").lower()

    # Map to supported prompt languages (we write instructions in ES for now)
    # This is a future hook — when we add i18n, we'll use this
    return lang


def build_compressed_doc_d(creator_id: str) -> str:
    """Build a compressed personality prompt for any creator.

    Structure follows CharacterEval + PersonaGym best practices:
    Identity → Personality → Style → Examples → Constraints

    Returns:
        Compressed Doc D string (~2-3K chars including few-shot)
    """
    # Load data sources (DB first, then local file fallback)
    baseline = _load_profile_with_db_fallback(creator_id, "baseline_metrics", "baseline_metrics.json")
    bfi = _load_profile_with_db_fallback(creator_id, "bfi_profile", "bfi_profile.json")

    creator_name = _get_creator_display_name(creator_id)
    products_str = _get_creator_products(creator_id)

    # === Build sections (ordered per literature: Identity → Style → Examples → Constraints) ===
    sections = []

    # 1. Identity (1 line) — gender-neutral wording
    sections.append(
        f"Eres {creator_name}. Respondes DMs de Instagram y WhatsApp "
        f"como si fueras tú — natural, sin filtros de asistente."
    )

    # 2. Personality from BFI
    if bfi and bfi.get("scores"):
        personality = _bfi_summary(bfi["scores"])
        sections.append(f"PERSONALIDAD: {personality}.")

    # 3. Quantitative style from baseline
    if baseline and baseline.get("metrics"):
        m = baseline["metrics"]
        length = m.get("length", {})
        emoji = m.get("emoji", {})
        punct = m.get("punctuation", {})
        lang = m.get("languages", {})
        formality = m.get("formality", {})

        style_lines = ["ESTILO (respeta estas frecuencias):"]

        # Length — adaptive wording based on measured divergence
        median = length.get("char_median", 30)
        p25 = length.get("char_p25", 10)
        p75 = length.get("char_p75", 60)
        length_div = _get_length_divergence(creator_id)
        if length_div is not None and length_div <= 1.5:
            style_lines.append(
                f"- Longitud típica: {p25}-{p75} caracteres (mediana {median}). "
                f"Mensajes CORTOS."
            )
        else:
            style_lines.append(
                f"- Longitud: MÁXIMO {p75} caracteres. Mediana real: {median}. "
                f"Regla estricta — sé breve."
            )

        # Emoji — behavioral constraint (quantitative alone fails per Layer 1 data)
        emoji_rate = emoji.get("emoji_rate_pct", 20)
        no_emoji_rate = 100 - emoji_rate
        top_emojis = emoji.get("top_20_emojis", [])
        # Filter out skin tone modifiers (U+1F3FB-1F3FF) that appear as standalone
        emoji_list = " ".join(
            e[0] for e in top_emojis[:8]
            if len(e[0]) > 0 and not (len(e[0]) == 1 and 0x1F3FB <= ord(e[0]) <= 0x1F3FF)
        ) if top_emojis else ""
        n_with = max(1, round(5 * emoji_rate / 100))
        n_without = 5 - n_with
        style_lines.append(
            f"- Emoji: tu DEFAULT es NO poner emoji. "
            f"Solo {emoji_rate:.0f}% de tus mensajes reales llevan emoji — "
            f"el {no_emoji_rate:.0f}% van SIN NINGUNO. "
            f"De cada 5 mensajes, {n_without} van sin emoji y solo "
            f"{n_with} {'lleva' if n_with == 1 else 'llevan'} emoji."
        )
        if emoji_list:
            style_lines.append(f"- Si pones emoji (raro): {emoji_list}")

        # Exclamation — behavioral framing (74% failure in L1 shows numbers don't work)
        excl_rate = punct.get("exclamation_rate_pct", 10)
        if excl_rate < 10:
            style_lines.append(
                f"- Exclamaciones (!): CASI NUNCA (solo {excl_rate:.0f}% de mensajes reales). "
                f"Tu tono natural es tranquilo, sin '!' al final."
            )
        else:
            style_lines.append(
                f"- Exclamaciones (!): {excl_rate:.0f}% de mensajes."
            )

        # Questions
        q_rate = punct.get("question_rate_pct", 15)
        style_lines.append(f"- Preguntas (?): {q_rate:.0f}% de mensajes.")

        # CAPS — use creator's actual examples if available from top_50
        caps_rate = punct.get("all_caps_rate_pct", 3)
        if caps_rate > 2:
            # Try to find actual CAPS words from the creator's vocabulary
            vocab = m.get("vocabulary", {})
            top_words = vocab.get("top_50", [])
            caps_examples = [w[0] for w in top_words if w[0].isupper() and len(w[0]) > 2][:4]
            if caps_examples:
                style_lines.append(
                    f"- CAPS para énfasis: {caps_rate:.0f}% de mensajes. "
                    f"Ej: {', '.join(caps_examples)}"
                )
            else:
                style_lines.append(
                    f"- CAPS para énfasis: {caps_rate:.0f}% de mensajes."
                )

        # Languages
        detected = lang.get("detected", [])
        if detected:
            lang_parts = [f"{d['lang'].upper()} {d['pct']:.0f}%" for d in detected[:3]]
            style_lines.append(f"- Idiomas: {', '.join(lang_parts)}.")

        # Formality
        if formality.get("dominant"):
            style_lines.append(
                f"- Trato: {formality['dominant']} (nunca de usted)."
            )

        sections.append("\n".join(style_lines))

    # 4. Characteristic vocabulary (merged, stop-words filtered)
    if baseline and baseline.get("metrics"):
        char_vocab = _get_characteristic_vocab(baseline["metrics"])
        if char_vocab:
            sections.append(f"VOCABULARIO:\n{char_vocab}")

    # 5. Products
    if products_str:
        sections.append(f"PRODUCTOS/SERVICIOS:\n{products_str}")

    # 6. Few-shot examples (RoleLLM: #1 lever for style fidelity)
    few_shot = _get_few_shot_examples(creator_id, baseline=baseline, n=5)
    if few_shot:
        sections.append(
            f"EJEMPLOS REALES (imita este estilo exacto):\n{few_shot}"
        )

    # 7. Anti-patterns (max 5 per CharacterEval — recency position for enforcement)
    # Adapt rules to creator's actual metrics
    emoji_rate_val = 50  # default: assume high
    excl_rate_val = 50
    if baseline and baseline.get("metrics"):
        emoji_rate_val = baseline["metrics"].get("emoji", {}).get("emoji_rate_pct", 50)
        excl_rate_val = baseline["metrics"].get("punctuation", {}).get("exclamation_rate_pct", 50)

    rules = ["REGLAS (si no las cumples, se nota que eres IA):"]
    if emoji_rate_val < 40:
        rules.append("- NO pongas emoji por defecto. La mayoría de tus mensajes van SIN emoji.")
    rules.append("- NO respondas como asistente ('¿En qué puedo ayudarte?', 'Estoy aquí para...')")
    if excl_rate_val < 15:
        rules.append("- NO pongas '!' por defecto. Tu tono es tranquilo.")
    rules.append("- NO inventes horarios, precios ni nombres que no estén en el contexto")
    rules.append("- Mensajes cortos — 1-2 frases")
    rules.append("- NUNCA repitas lo que dice el lead. Si no sabes qué decir, responde con una reacción breve (ja, vale, uf).")
    rules.append("- Usa SOLO vocabulario que aparece en tus ejemplos reales. NO inventes expresiones ni palabras que no uses.")
    sections.append("\n".join(rules))

    result = "\n\n".join(sections)
    logger.info(
        "[COMPRESSED-DOC-D] Generated for %s: %d chars",
        creator_id, len(result),
    )
    return result
