"""Compressed Doc D — Universal personality prompt builder.

Generates a ~3K char personality prompt from:
- BFI profile (tests/cpe_data/{creator}/bfi_profile.json)
- Baseline metrics (tests/cpe_data/{creator}/baseline_metrics.json)
- Creator DB data (name, products)

Based on PersonaGym (ACL 2025): short structured descriptions outperform
verbose 38K-char personality documents. Quantitative style constraints
replace post-processing enforcement.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# BFI trait labels (Big Five Inventory)
_BFI_LABELS = {
    "O": ("Openness", "abierta a nuevas experiencias", "convencional y práctica"),
    "C": ("Conscientiousness", "organizada y disciplinada", "espontánea y flexible"),
    "E": ("Extraversion", "extrovertida y sociable", "reservada e introspectiva"),
    "A": ("Agreeableness", "empática y cooperativa", "directa y competitiva"),
    "N": ("Neuroticism", "emocionalmente reactiva", "emocionalmente estable"),
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


def build_compressed_doc_d(creator_id: str) -> str:
    """Build a compressed ~3K char personality prompt for any creator.

    Combines:
    - BFI personality profile → natural language summary
    - Baseline quantitative metrics → style constraints
    - Creator DB data → name, products

    Returns:
        Compressed Doc D string (~2-3K chars)
    """
    # Load data sources (DB first, then local file fallback)
    baseline = _load_profile_with_db_fallback(creator_id, "baseline_metrics", "baseline_metrics.json")
    bfi = _load_profile_with_db_fallback(creator_id, "bfi_profile", "bfi_profile.json")

    creator_name = _get_creator_display_name(creator_id)
    products_str = _get_creator_products(creator_id)

    # === Build sections ===
    sections = []

    # 1. Identity (1 line)
    sections.append(
        f"Eres {creator_name}. Respondes DMs de Instagram y WhatsApp "
        f"como si fueras tú — natural, directa, sin filtros de asistente."
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
        vocab = m.get("vocabulary", {})
        formality = m.get("formality", {})

        style_lines = ["ESTILO CUANTITATIVO (respeta estas frecuencias):"]

        # Length — adaptive wording based on measured divergence
        median = length.get("char_median", 30)
        p25 = length.get("char_p25", 10)
        p75 = length.get("char_p75", 60)
        length_div = _get_length_divergence(creator_id)
        if length_div is not None and length_div <= 1.5:
            # Measured divergence is acceptable — soft wording (validated)
            style_lines.append(
                f"- Longitud típica: {p25}-{p75} caracteres (mediana {median}). "
                f"Mensajes CORTOS y directos."
            )
        else:
            # No data or high divergence — strict wording to overcorrect
            style_lines.append(
                f"- Longitud: MÁXIMO {p75} caracteres. Mediana real: {median}. "
                f"Regla estricta — sé breve."
            )

        # Emoji — strongest constraint (models over-emoji by default)
        emoji_rate = emoji.get("emoji_rate_pct", 20)
        avg_emoji = emoji.get("avg_emoji_count", 0.5)
        no_emoji_rate = 100 - emoji_rate
        top_emojis = emoji.get("top_20_emojis", [])
        emoji_list = " ".join(e[0] for e in top_emojis[:8]) if top_emojis else ""
        style_lines.append(
            f"- Emoji: SOLO {emoji_rate:.0f}% de tus mensajes llevan emoji. "
            f"El {no_emoji_rate:.0f}% NO llevan NINGÚN emoji. "
            f"De cada 5 mensajes, {max(1, round(5 * emoji_rate / 100))} llevan emoji y "
            f"{5 - max(1, round(5 * emoji_rate / 100))} van SIN emoji."
        )
        if emoji_list:
            style_lines.append(f"- Cuando SÍ uses emoji, usa: {emoji_list}")

        # Punctuation — exclamation is heavily over-generated by LLMs
        excl_rate = punct.get("exclamation_rate_pct", 10)
        q_rate = punct.get("question_rate_pct", 15)
        caps_rate = punct.get("all_caps_rate_pct", 3)
        style_lines.append(
            f"- Exclamaciones (!): {excl_rate:.0f}% de tus mensajes usan '!'. "
            f"Úsalas solo cuando el contexto pide énfasis emocional — no como defecto."
        )
        style_lines.append(f"- Preguntas (?): {q_rate:.0f}% de mensajes.")
        if caps_rate > 2:
            style_lines.append(
                f"- Mayúsculas para énfasis (CAPS): {caps_rate:.0f}% de mensajes. "
                f"Ejemplo: 'NOOOO', 'AVUI', 'QUE FUEEERT', 'AYYYY'. "
                f"Úsalas cuando quieras expresar sorpresa, énfasis o emoción fuerte."
            )

        # Languages
        detected = lang.get("detected", [])
        if detected:
            lang_parts = [f"{d['lang'].upper()} {d['pct']:.0f}%" for d in detected[:3]]
            style_lines.append(f"- Idiomas: {', '.join(lang_parts)}.")

        # Vocabulary
        top_words = vocab.get("top_50", [])
        if top_words:
            word_list = ", ".join(w[0] for w in top_words[:15])
            style_lines.append(f"- Palabras frecuentes: {word_list}")

        # Formality
        if formality.get("dominant"):
            style_lines.append(
                f"- Trato: {formality['dominant']} (nunca de usted)."
            )

        sections.append("\n".join(style_lines))

    # 4. Products
    if products_str:
        sections.append(f"PRODUCTOS/SERVICIOS:\n{products_str}")

    # 5. Anti-patterns (universal + emoji emphasis)
    sections.append(
        "REGLAS CRÍTICAS (si no las cumples, se nota que eres IA):\n"
        "- La MAYORÍA de tus mensajes van SIN emoji. No pongas emoji por defecto.\n"
        "- NO respondas como asistente ('¿En qué puedo ayudarte?', 'Estoy aquí para...')\n"
        "- NO inventes precios, horarios o datos que no tengas\n"
        "- Mensajes cortos — la mayoría son 1-2 frases"
    )

    result = "\n\n".join(sections)
    logger.info(
        "[COMPRESSED-DOC-D] Generated for %s: %d chars",
        creator_id, len(result),
    )
    return result
