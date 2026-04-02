"""
CPE Doc D Length Sweep — Test 4 compressed Doc D size variants.

Generates 50 responses for each variant (500 / current~1300 / 2500 / 5000 chars)
using Qwen3-14B via DeepInfra, then runs Level 1 quantitative metrics.

Usage:
    railway run python3 tests/cpe_docd_sweep.py --creator iris_bertran
    railway run python3 tests/cpe_docd_sweep.py --creator iris_bertran --skip-gen
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
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("cpe_sweep")

# =========================================================================
# DOC D VARIANT BUILDERS (universal — creator_id injected, no hardcoding)
# =========================================================================

_BFI_LABELS = {
    "O": ("Openness", "abierta a nuevas experiencias, creativa, curiosa", "convencional y práctica"),
    "C": ("Conscientiousness", "organizada, disciplinada y fiable", "espontánea y flexible"),
    "E": ("Extraversion", "extrovertida, energética y sociable", "reservada e introspectiva"),
    "A": ("Agreeableness", "empática, cooperativa y cercana", "directa y competitiva"),
    "N": ("Neuroticism", "emocionalmente reactiva", "emocionalmente estable y tranquila"),
}


def _load_json(path: str) -> Optional[dict]:
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def _get_creator_name(creator_id: str) -> str:
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
        finally:
            session.close()
    except Exception:
        pass
    return creator_id.replace("_", " ").title()


def _get_products(creator_id: str) -> List[str]:
    try:
        from api.database import SessionLocal
        from sqlalchemy import text
        session = SessionLocal()
        try:
            rows = session.execute(
                text(
                    "SELECT p.name, p.price, p.description FROM products p "
                    "JOIN creators c ON c.id = p.creator_id "
                    "WHERE c.name = :cid AND p.active = true ORDER BY p.name LIMIT 15"
                ),
                {"cid": creator_id},
            ).fetchall()
            return [(r[0], r[1], r[2] or "") for r in rows]
        finally:
            session.close()
    except Exception:
        return []


def _bfi_one_line(scores: dict) -> str:
    """Single-line BFI summary for variant A."""
    traits = []
    for dim, score in scores.items():
        if dim not in _BFI_LABELS:
            continue
        _, high, low = _BFI_LABELS[dim]
        if score >= 3.8:
            traits.append(high.split(",")[0])
        elif score <= 2.5:
            traits.append(low.split(" y ")[0])
    return ", ".join(traits[:4]) if traits else "equilibrada"


def _bfi_detailed(scores: dict, scores_detailed: dict = None) -> str:
    """Per-dimension BFI narrative for variants C/D."""
    lines = []
    for dim, score in scores.items():
        if dim not in _BFI_LABELS:
            continue
        name, high, low = _BFI_LABELS[dim]
        label = high if score >= 3.0 else low
        intensity = "muy " if abs(score - 3.0) >= 1.5 else ("bastante " if abs(score - 3.0) >= 0.8 else "moderadamente ")
        lines.append(f"  {name} ({score:.1f}/5): {intensity}{label}")
    return "\n".join(lines)


def build_docd_a(creator_id: str, baseline: dict, bfi: dict, products: list, creator_name: str) -> str:
    """Variant A: ~500 chars — pure numbers + identity. Floor of usefulness."""
    m = baseline.get("metrics", {})
    length = m.get("length", {})
    emoji = m.get("emoji", {})
    punct = m.get("punctuation", {})
    lang = m.get("languages", {})
    vocab = m.get("vocabulary", {})

    p25 = length.get("char_p25", 10)
    p75 = length.get("char_p75", 60)
    median = length.get("char_median", 26)
    emoji_rate = emoji.get("emoji_rate_pct", 22)
    top_emojis = " ".join(e[0] for e in emoji.get("top_20_emojis", [])[:6])
    excl = punct.get("exclamation_rate_pct", 2)
    q_rate = punct.get("question_rate_pct", 14)
    detected = lang.get("detected", [])
    lang_str = ", ".join(f"{d['lang'].upper()} {d['pct']:.0f}%" for d in detected[:2])
    top_words = ", ".join(w[0] for w in vocab.get("top_50", [])[:10])
    personality = _bfi_one_line(bfi.get("scores", {})) if bfi else ""

    lines = [
        f"Eres {creator_name}. Respondes DMs de Instagram/WhatsApp como tú — sin filtros de asistente.",
        f"Personalidad: {personality}." if personality else "",
        f"Estilo: mensajes de {p25}-{p75} chars (mediana {median}). Emoji en {emoji_rate:.0f}% de msgs: {top_emojis}",
        f"'!' en {excl:.0f}% — casi nunca. Preguntas en {q_rate:.0f}% de msgs.",
        f"Idiomas: {lang_str}. Palabras frecuentes: {top_words}",
        f"NUNCA respondas como asistente ('¿En qué puedo ayudarte?', 'Estoy aquí para...')",
    ]
    return "\n".join(l for l in lines if l)


def build_docd_b(creator_id: str, baseline: dict, bfi: dict, products: list, creator_name: str) -> str:
    """Variant B: current production build_compressed_doc_d — ~1.3K chars."""
    # Directly import and call the existing function
    sys.path.insert(0, str(REPO_ROOT))
    from core.dm.compressed_doc_d import build_compressed_doc_d
    return build_compressed_doc_d(creator_id)


def build_docd_c(creator_id: str, baseline: dict, bfi: dict, products: list, creator_name: str) -> str:
    """Variant C: ~2500 chars — B + per-dim BFI + CA/ES rules + greeting patterns."""
    m = baseline.get("metrics", {})
    length = m.get("length", {})
    emoji = m.get("emoji", {})
    punct = m.get("punctuation", {})
    lang = m.get("languages", {})
    vocab = m.get("vocabulary", {})
    greet = m.get("greeting_patterns", {})
    formality = m.get("formality", {})

    p25 = length.get("char_p25", 10)
    p75 = length.get("char_p75", 60)
    median = length.get("char_median", 26)
    p90 = length.get("char_p90", 193)

    emoji_rate = emoji.get("emoji_rate_pct", 22)
    no_emoji_rate = 100 - emoji_rate
    avg_emoji = emoji.get("avg_emoji_count", 0.71)
    top_emojis_raw = emoji.get("top_20_emojis", [])
    top_emojis = " ".join(e[0] for e in top_emojis_raw[:12])

    excl = punct.get("exclamation_rate_pct", 2)
    q_rate = punct.get("question_rate_pct", 14)
    caps = punct.get("all_caps_rate_pct", 3)
    laugh = punct.get("laugh_rate_pct", 2)

    detected = lang.get("detected", [])
    lang_pairs = [(d["lang"], d["pct"]) for d in detected[:4]]

    top_words = vocab.get("top_50", [])
    word_str_full = ", ".join(w[0] for w in top_words[:25])

    openers = greet.get("top_15_openers", [])
    opener_str = ", ".join(f'"{w[0]}"' for w in openers[:8]) if openers else ""

    bfi_scores = bfi.get("scores", {}) if bfi else {}
    bfi_detail = _bfi_detailed(bfi_scores, bfi.get("scores_detailed", {})) if bfi else ""

    ca_words = [w[0] for w in top_words if any(c in w[0] for c in ['à', 'è', 'é', 'ï', 'ó', 'ú', 'ç'])][:8]
    es_words = [w[0] for w in top_words if w[0] in ['ya', 'me', 'lo', 'la', 'el', 'un', 'pero', 'yo', 'tú', 'que', 'qué', 'ok', 'vale', 'bueno', 'sí']][:6]

    sections = []

    # Identity
    sections.append(
        f"Eres {creator_name}. Respondes DMs de Instagram y WhatsApp "
        f"exactamente como tú — natural, directa, sin filtros de asistente ni formalidades."
    )

    # Personality (BFI per-dimension)
    if bfi_detail:
        sections.append(f"PERSONALIDAD (Big Five):\n{bfi_detail}")

    # Quantitative style
    style = [
        "ESTILO CUANTITATIVO — respeta EXACTAMENTE estas frecuencias:",
        f"- Longitud: {p25}-{p75} chars (mediana {median}, p90={p90}). La MAYORÍA de tus msgs son muy cortos.",
        f"- Emoji: {emoji_rate:.0f}% de tus mensajes llevan emoji, el {no_emoji_rate:.0f}% NO. Promedio: {avg_emoji:.1f}/msg.",
        f"  Cuando usas emoji: {top_emojis}",
        f"- '!': SOLO {excl:.0f}% de mensajes — casi nunca. No uses '!' por defecto.",
        f"- '?': {q_rate:.0f}% de mensajes tienen pregunta.",
        f"- Mayúsculas para énfasis: {caps:.0f}% de mensajes.",
        f"- Risas (jaja/jajaja/etc): {laugh:.0f}% de mensajes.",
    ]
    sections.append("\n".join(style))

    # Languages
    lang_detail = ["IDIOMAS — code-switching natural:"]
    for lcode, pct in lang_pairs:
        lang_detail.append(f"  {lcode.upper()}: {pct:.0f}% de tus mensajes")
    if ca_words:
        lang_detail.append(f"  Palabras CA frecuentes: {', '.join(ca_words)}")
    if es_words:
        lang_detail.append(f"  Palabras ES frecuentes: {', '.join(es_words)}")
    lang_detail.append("  Responde en el idioma del mensaje recibido. Mezcla CA/ES cuando sea natural para ti.")
    sections.append("\n".join(lang_detail))

    # Vocabulary
    sections.append(f"VOCABULARIO FRECUENTE (úsalo cuando encaje):\n  {word_str_full}")

    # Greeting patterns
    if opener_str:
        sections.append(f"COMIENZOS DE MENSAJE frecuentes: {opener_str}")

    # Products
    if products:
        prod_lines = [f"  - {p[0]}: {p[1]}€" for p in products[:8]]
        sections.append("PRODUCTOS/SERVICIOS:\n" + "\n".join(prod_lines))

    # Anti-patterns
    sections.append(
        "REGLAS CRÍTICAS:\n"
        "- La MAYORÍA de tus mensajes van SIN emoji. No pongas emoji por defecto.\n"
        "- Casi NUNCA usas '!' — termina frases con punto, coma o sin puntuación.\n"
        "- NO respondas como asistente ('¿En qué puedo ayudarte?', 'Estoy aquí para...', '¡Claro!')\n"
        "- NO inventes precios, horarios o datos que no tengas\n"
        "- Mensajes cortos — la mayoría son 1-2 frases\n"
        "- NO uses lenguaje corporativo ni formal\n"
        "- Reacciona al contenido concreto del mensaje, no des respuestas genéricas"
    )

    return "\n\n".join(sections)


def build_docd_d(creator_id: str, baseline: dict, bfi: dict, products: list, creator_name: str) -> str:
    """Variant D: ~5000 chars — C + narrative persona + example patterns + full products."""
    base = build_docd_c(creator_id, baseline, bfi, products, creator_name)

    m = baseline.get("metrics", {})
    vocab = m.get("vocabulary", {})
    lang = m.get("languages", {})
    punct = m.get("punctuation", {})

    top_words = vocab.get("top_50", [])
    all_words = ", ".join(w[0] for w in top_words[:50])
    ellipsis = punct.get("ellipsis_rate_pct", 4)
    detected = lang.get("detected", [])

    # BFI narrative paragraph
    bfi_scores = bfi.get("scores", {}) if bfi else {}
    e_score = bfi_scores.get("E", 3.0)
    a_score = bfi_scores.get("A", 3.0)
    n_score = bfi_scores.get("N", 3.0)
    persona_energy = "muy energética y expresiva" if e_score >= 4.0 else "moderadamente extrovertida"
    persona_warmth = "cálida y cercana con todo el mundo" if a_score >= 3.8 else "directa pero amable"
    persona_calm = "emocionalmente estable, rara vez muestra ansiedad" if n_score <= 3.0 else "emocionalmente expresiva"

    persona_narrative = (
        f"DESCRIPCIÓN DE PERSONALIDAD (para entender tu voz):\n"
        f"{creator_name} es {persona_energy}, {persona_warmth} y {persona_calm}. "
        f"En conversaciones de DM es espontánea, usa el humor con naturalidad y "
        f"se adapta al tono del interlocutor sin perder su carácter. "
        f"No le importa mezclar idiomas si sale natural. "
        f"Sus respuestas son auténticas — no performativas ni de servicio al cliente."
    )

    # Code-switching guide
    ca_pct = next((d["pct"] for d in detected if d["lang"] == "ca"), 0)
    es_pct = next((d["pct"] for d in detected if d["lang"] == "es"), 0)
    codeswitching = (
        f"GUÍA DE IDIOMAS:\n"
        f"- {creator_name} habla principalmente {('catalán' if ca_pct > es_pct else 'español')} ({max(ca_pct, es_pct):.0f}%) "
        f"y también {('español' if ca_pct > es_pct else 'catalán')} ({min(ca_pct, es_pct):.0f}%)\n"
        f"- Regla: responde en el idioma en que te escribe el lead\n"
        f"- Si el lead mezcla idiomas, mezcla tú también\n"
        f"- Nunca corrijas el idioma del lead ni comentes sobre el idioma\n"
        f"- Algunas palabras son tuyas en cualquier idioma: {', '.join(w[0] for w in top_words[:8])}"
    )

    # Full vocabulary
    full_vocab = f"VOCABULARIO COMPLETO (top 50 palabras más frecuentes):\n  {all_words}"

    # Extended anti-patterns with examples
    anti_extended = (
        "ANTI-PATRONES CONCRETOS (lo que NO debes hacer):\n"
        f"- ❌ '¡Hola! ¿En qué puedo ayudarte hoy?' → demasiado asistente\n"
        f"- ❌ '¡Claro que sí! Con mucho gusto te ayudo.' → lenguaje corporativo\n"
        f"- ❌ Terminar CADA mensaje con emoji → sobre-emoji\n"
        f"- ❌ Usar '!' en respuestas neutras → sobre-entusiasmo falso\n"
        f"- ❌ Responder con preguntas cuando no necesitas información → fill questions\n"
        f"- ❌ Repetir palabras del lead en tu respuesta artificialmente → eco forzado\n"
        f"- ❌ Mensajes de más de 150 chars para cosas simples → sobre-explicación\n"
        f"- ✅ Responde al contenido concreto, de forma breve y natural\n"
        f"- ✅ Si no sabes, dilo directamente sin dar vueltas\n"
        f"- ✅ Usa puntos suspensivos cuando salga natural ({ellipsis:.0f}% de tus msgs)"
    )

    # Full products
    if products:
        prod_lines = [f"  - {p[0]}: {p[1]}€{(' — ' + p[2][:60]) if p[2] else ''}" for p in products]
        full_products = "CATÁLOGO COMPLETO:\n" + "\n".join(prod_lines)
    else:
        full_products = ""

    extra_sections = [persona_narrative, codeswitching, full_vocab, anti_extended]
    if full_products:
        extra_sections.append(full_products)

    return base + "\n\n" + "\n\n".join(extra_sections)


VARIANTS = [
    ("A_500",   build_docd_a),
    ("B_1300",  build_docd_b),
    ("C_2500",  build_docd_c),
    ("D_5000",  build_docd_d),
]


# =========================================================================
# LEVEL 1 METRICS (inline — no pipeline, just compute)
# =========================================================================

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


def compute_metrics(text: str) -> dict:
    if not text:
        return {"length": 0, "emoji_count": 0, "has_emoji": False,
                "has_question": False, "has_exclamation": False, "words": set()}
    words = set(re.findall(r"\b\w+\b", text.lower()))
    emojis = _EMOJI_RE.findall(text)
    ca_hits = len(_CA_MARKERS.findall(text))
    es_hits = len(_ES_MARKERS.findall(text))
    lang = "ca-es" if ca_hits and es_hits else ("ca" if ca_hits > es_hits else "es")
    return {
        "length": len(text),
        "emoji_count": len(emojis),
        "has_emoji": len(emojis) > 0,
        "has_question": "?" in text,
        "has_exclamation": "!" in text,
        "language": lang,
        "words": words,
    }


def level1_score(bot_responses: list, baseline_metrics: dict) -> dict:
    """Compute Level 1 match score from a list of response strings."""
    bm = baseline_metrics.get("metrics", {})
    emoji_b = bm.get("emoji", {})
    punct_b = bm.get("punctuation", {})
    length_b = bm.get("length", {})
    vocab_b = bm.get("vocabulary", {})
    lang_b = bm.get("languages", {})

    iris_emoji_rate = emoji_b.get("emoji_rate_pct", 22)
    iris_excl_rate = punct_b.get("exclamation_rate_pct", 2)
    iris_q_rate = punct_b.get("question_rate_pct", 14)
    iris_len_median = length_b.get("char_median", 26)
    iris_len_mean = length_b.get("char_mean", 95)
    iris_ca_pct = next((d["pct"] for d in lang_b.get("detected", []) if d["lang"] == "ca"), 0)
    iris_top_words = set(w[0] for w in vocab_b.get("top_50", [])[:50])

    n = len(bot_responses)
    if not n:
        return {"overall": 0.0}

    all_m = []
    all_bot_words = set()
    for text in bot_responses:
        m = compute_metrics(text)
        all_bot_words |= m.pop("words", set())
        all_m.append(m)

    bot_emoji_rate = sum(1 for m in all_m if m["has_emoji"]) / n * 100
    bot_excl_rate  = sum(1 for m in all_m if m["has_exclamation"]) / n * 100
    bot_q_rate     = sum(1 for m in all_m if m["has_question"]) / n * 100
    bot_len_mean   = statistics.mean(m["length"] for m in all_m)
    bot_len_median = statistics.median(m["length"] for m in all_m)
    bot_ca_rate    = sum(1 for m in all_m if m.get("language") in ("ca", "ca-es")) / n * 100

    vocab_jaccard = len(iris_top_words & all_bot_words) / len(iris_top_words | all_bot_words) if (iris_top_words | all_bot_words) else 0

    # Flag if divergence > threshold
    flags = []
    def check_pct(name, bot_val, iris_val, tol_pp=20):
        div = abs(bot_val - iris_val)
        ok = div <= tol_pp
        flags.append((name, bot_val, iris_val, div, ok))
        return ok

    def check_num(name, bot_val, iris_val, tol_pct=30):
        div = abs(bot_val - iris_val) / iris_val * 100 if iris_val else 0
        ok = div <= tol_pct
        flags.append((name, bot_val, iris_val, div, ok))
        return ok

    check_pct("emoji_rate",  bot_emoji_rate, iris_emoji_rate)
    check_pct("excl_rate",   bot_excl_rate,  iris_excl_rate,  tol_pp=10)
    check_pct("q_rate",      bot_q_rate,     iris_q_rate)
    check_num("len_mean",    bot_len_mean,   iris_len_mean)
    check_num("len_median",  bot_len_median, iris_len_median)
    check_pct("ca_rate",     bot_ca_rate,    iris_ca_pct)
    check_pct("vocab_jac",   vocab_jaccard * 100, 5.0, tol_pp=10)  # target: >5% jaccard

    passed = sum(1 for _, _, _, _, ok in flags if ok)
    overall = round(passed / len(flags), 2)

    return {
        "overall": overall,
        "passed": passed,
        "total": len(flags),
        "details": {name: {"bot": round(bot, 2), "iris": round(iris, 2), "div": round(div, 2), "ok": ok}
                    for name, bot, iris, div, ok in flags},
        "bot_emoji_rate": round(bot_emoji_rate, 1),
        "bot_excl_rate": round(bot_excl_rate, 1),
        "bot_q_rate": round(bot_q_rate, 1),
        "bot_len_mean": round(bot_len_mean, 1),
        "bot_len_median": round(bot_len_median, 1),
        "bot_ca_rate": round(bot_ca_rate, 1),
        "vocab_jaccard": round(vocab_jaccard, 4),
    }


# =========================================================================
# GENERATION
# =========================================================================

async def generate_responses(test_cases: list, system_prompt: str, delay: float = 1.2) -> list:
    """Generate bot responses for all test cases using a given system prompt."""
    from core.providers.deepinfra_provider import call_deepinfra

    results = []
    for i, tc in enumerate(test_cases, 1):
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": tc["test_input"]},
        ]
        try:
            resp = await call_deepinfra(messages, max_tokens=150, temperature=0.7)
            bot_response = resp["content"].strip() if resp else ""
        except Exception as e:
            bot_response = ""
            print(f"  ERR [{i}] {e}")
        results.append({"id": tc["id"], "input": tc["test_input"],
                        "bot_response": bot_response, "ground_truth": tc.get("ground_truth", "")})
        if i % 10 == 0:
            print(f"  [{i}/{len(test_cases)}] {tc['id']}: {bot_response[:60]}")
        await asyncio.sleep(delay)
    return results


# =========================================================================
# MAIN
# =========================================================================

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--creator", required=True)
    parser.add_argument("--skip-gen", action="store_true", help="Skip generation, only recompute metrics")
    args = parser.parse_args()

    creator_id = args.creator
    cpe_dir = REPO_ROOT / "tests" / "cpe_data" / creator_id
    results_dir = cpe_dir / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    baseline = _load_json(str(cpe_dir / "baseline_metrics.json"))
    bfi = _load_json(str(cpe_dir / "bfi_profile.json"))
    test_data = _load_json(str(cpe_dir / "test_set.json"))
    test_cases = test_data.get("conversations", []) if isinstance(test_data, dict) else test_data

    creator_name = _get_creator_name(creator_id)
    products = _get_products(creator_id)

    print(f"\n{'='*70}")
    print(f"  CPE DOC-D LENGTH SWEEP — @{creator_id} ({creator_name})")
    print(f"  Test cases: {len(test_cases)} | Products: {len(products)}")
    print(f"{'='*70}\n")

    # Build all 4 Doc D variants
    doc_ds = {}
    for name, builder_fn in VARIANTS:
        if name == "B_1300":
            doc = builder_fn(creator_id, baseline, bfi, products, creator_name)
        else:
            doc = builder_fn(creator_id, baseline, bfi, products, creator_name)
        doc_ds[name] = doc
        print(f"  Variant {name}: {len(doc):,} chars")

    # Save variants for inspection
    for name, doc in doc_ds.items():
        with open(results_dir / f"docd_variant_{name.lower()}.txt", "w") as f:
            f.write(doc)
    print()

    # Generate or load responses for each variant
    all_scores = {}
    for name, _ in VARIANTS:
        result_path = results_dir / f"docd_{name.lower()}.json"

        if args.skip_gen and result_path.exists():
            print(f"  [{name}] Loading existing responses from {result_path.name}...")
            with open(result_path) as f:
                saved = json.load(f)
            responses = [r["bot_response"] for r in saved]
        else:
            print(f"  [{name}] Generating {len(test_cases)} responses...")
            results = await generate_responses(test_cases, doc_ds[name], delay=1.2)
            with open(result_path, "w") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            responses = [r["bot_response"] for r in results]
            print(f"  [{name}] Saved → {result_path.name}")

        score = level1_score(responses, baseline)
        all_scores[name] = score
        print(f"  [{name}] Overall match: {score['overall']:.2f} ({score['passed']}/{score['total']} passed)\n")

    # Print summary table
    print(f"\n{'='*90}")
    print(f"  RESULTS SUMMARY — Doc D Length vs Level 1 Match")
    print(f"{'='*90}")
    iris_bm = baseline.get("metrics", {})
    iris_emoji = iris_bm.get("emoji", {}).get("emoji_rate_pct", 22)
    iris_excl  = iris_bm.get("punctuation", {}).get("exclamation_rate_pct", 2)
    iris_q     = iris_bm.get("punctuation", {}).get("question_rate_pct", 14)
    iris_len   = iris_bm.get("length", {}).get("char_mean", 95)
    iris_ca    = next((d["pct"] for d in iris_bm.get("languages", {}).get("detected", []) if d["lang"] == "ca"), 0)

    print(f"  {'Variant':<12} {'Chars':>7} {'Match':>7} {'Emoji%':>8} {'Excl%':>7} {'Q%':>7} {'Len':>7} {'CA%':>7} {'VocJac':>8}")
    print(f"  {'-'*80}")
    print(f"  {'[Iris real]':<12} {'—':>7} {'—':>7} {iris_emoji:>7.1f}% {iris_excl:>6.1f}% {iris_q:>6.1f}% {iris_len:>6.0f}c {iris_ca:>6.1f}% {'—':>8}")
    print(f"  {'-'*80}")

    best_name, best_score = max(all_scores.items(), key=lambda x: x[1]["overall"])
    for name, _ in VARIANTS:
        s = all_scores[name]
        chars = len(doc_ds[name])
        marker = " ← BEST" if name == best_name else ""
        print(f"  {name:<12} {chars:>7,} {s['overall']:>7.2f} {s['bot_emoji_rate']:>7.1f}% "
              f"{s['bot_excl_rate']:>6.1f}% {s['bot_q_rate']:>6.1f}% "
              f"{s['bot_len_mean']:>6.0f}c {s['bot_ca_rate']:>6.1f}% "
              f"{s['vocab_jaccard']:>8.4f}{marker}")

    print(f"\n  Winner: {best_name} ({len(doc_ds[best_name]):,} chars) — "
          f"match={all_scores[best_name]['overall']:.2f}\n")

    # Per-metric detail table for winner
    print(f"  Detail for winner [{best_name}]:")
    for metric, d in all_scores[best_name]["details"].items():
        ok_str = "✓" if d["ok"] else "✗ >>>"
        print(f"    {metric:<15} bot={d['bot']:>8.2f}  iris={d['iris']:>8.2f}  div={d['div']:>8.2f}  {ok_str}")

    print(f"\n  Saved Doc D variants: {results_dir}/docd_variant_*.txt")
    print(f"  Saved responses:      {results_dir}/docd_*.json")
    print(f"{'='*90}\n")


if __name__ == "__main__":
    asyncio.run(main())
