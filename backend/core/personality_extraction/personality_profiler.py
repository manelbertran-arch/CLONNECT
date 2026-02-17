"""
Phase 3 — Personality Profiler (Doc C)

Generates the Personality Profile (conversational DNA) from all analyzed
conversations. This is the most important output — the "genome" of the clone.

Three-step process:
1. Statistical analysis of writing patterns (computed locally, no LLM)
2. Creator dictionary extraction with real phrase frequencies (no LLM)
3. LLM synthesis split into 3 parallel calls to prevent truncation:
   - Call 1: Identity + Catchphrases
   - Call 2: Tone map (all 7 contexts)
   - Call 3: Sales method + Limitations
"""

import asyncio
import logging
import re
import statistics
from collections import Counter
from datetime import datetime
from typing import Optional

from core.personality_extraction.llm_client import extract_with_llm, _strip_code_blocks
from core.personality_extraction.models import (
    CleanedConversation,
    CreatorDictionary,
    MessageOrigin,
    PersonalityProfile,
    SalesMethod,
    ToneAdaptation,
    WritingStyle,
)

logger = logging.getLogger(__name__)

# ── Emoji regex ─────────────────────────────────────────────────────
EMOJI_PATTERN = re.compile(
    "[\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U0000FE00-\U0000FE0F"
    "\U0000200D"
    "\U00002640\U00002642"
    "\U0000231A\U0000231B"
    "\U000023E9-\U000023F3"
    "\U000023F8-\U000023FA"
    "\U000025AA\U000025AB\U000025B6\U000025C0\U000025FB-\U000025FE"
    "\U00002934\U00002935"
    "\U00002B05-\U00002B07\U00002B1B\U00002B1C\U00002B50\U00002B55"
    "\U00003030\U0000303D\U00003297\U00003299"
    "]+",
    flags=re.UNICODE,
)

LAUGH_PATTERN = re.compile(r"\b[jJhH][aAeE][jJhH]?[aAeE]*(?:[jJhH][aAeE])*\b")

# ── Dialect detection patterns ──────────────────────────────────────
_VOSEO_RE = re.compile(
    r'\b(?:vos|sos|tenés|podés|querés|sabés|venís|decí|decime|mirá|andá|hacé|tomá|pensá|contá|andás|ponés|salís|sentís|che)\b',
    re.IGNORECASE,
)
_LUNFARDO_RE = re.compile(
    r'\b(?:bolud[oa]|pibe|piba|mina|gros[oa]|bárbaro|copad[oa]|piol[oa]|zarpad[oa]|labur[oa]r?|guita|quilombo|bondi|birra|morfi|garpa|chamuy[oa]?|flashe[oa]r?)\b|\bde una\b',
    re.IGNORECASE,
)
_TUTEO_RE = re.compile(
    r'\b(?:tú|tienes|puedes|quieres|sabes|dime|venga|vale|tío|tía|mola|guay|joder|ostras|flipar|currar)\b',
    re.IGNORECASE,
)

# ── Character repetition ───────────────────────────────────────────
_CHAR_REPEAT_RE = re.compile(r'\b(\w*?(\w)\2{2,}\w*)\b')

# ── Dictionary category patterns ────────────────────────────────────
_GREETING_RE = re.compile(
    r'^(?:hola|hey|ey+|buenas?|qué tal|qué onda|buenos?\s*d[ií]as?|buenas\s*(?:tardes|noches))',
    re.IGNORECASE,
)
_FAREWELL_RE = re.compile(
    r'(?:chau|adi[oó]s|nos vemos|hasta (?:luego|pronto|mañana)|buenas noches|un abrazo|abrazo|un beso|cu[ií]date)',
    re.IGNORECASE,
)
_GRATITUDE_RE = re.compile(r'(?:gracias|te agradezco|mil gracias|muchas gracias)', re.IGNORECASE)
_VALIDATION_RE = re.compile(
    r'(?:genial|excelente|increíble|tremendo|bien ah[ií]|crack|gros[oa]|fenómenal?|espectacular|buen[ií]simo|brutal|qué crack|grande)',
    re.IGNORECASE,
)
_CONFIRMATION_RE = re.compile(
    r'^(?:dale|s[ií]|claro|obvio|por supuesto|de una|exacto|perfecto|listo|ok|okey|bueno|vamo)',
    re.IGNORECASE,
)
_LAUGH_ONLY_RE = re.compile(r'^[jJhH][aAeE][jJhH]?[aAeE]*(?:[jJhH][aAeE])*[!\s]*$')
_ENCOURAGEMENT_RE = re.compile(
    r'(?:vamos|vas a poder|vas bien|metele|dale que|éxitos|mucha suerte|tú puedes|vos pod[eé]s|ánimo|fuerza)',
    re.IGNORECASE,
)


def _extract_emojis(text: str) -> list[str]:
    return EMOJI_PATTERN.findall(text)


def _count_emojis(text: str) -> int:
    return len(_extract_emojis(text))


def _detect_laughs(text: str) -> list[str]:
    return LAUGH_PATTERN.findall(text)


def compute_writing_style(conversations: list[CleanedConversation]) -> WritingStyle:
    """Compute writing style statistics from all creator real messages."""
    style = WritingStyle()

    all_messages: list[str] = []
    all_lengths: list[int] = []
    emoji_counts: list[int] = []
    emoji_counter: Counter = Counter()
    laugh_counter: Counter = Counter()
    turn_bubble_counts: list[int] = []

    for conv in conversations:
        current_turn_bubbles = 0
        for msg in conv.messages:
            if msg.origin != MessageOrigin.CREATOR_REAL:
                if current_turn_bubbles > 0:
                    turn_bubble_counts.append(current_turn_bubbles)
                    current_turn_bubbles = 0
                continue

            content = msg.content or ""
            all_messages.append(content)
            all_lengths.append(len(content))

            emojis = _extract_emojis(content)
            emoji_counts.append(len(emojis))
            for e in emojis:
                emoji_counter[e] += 1

            for laugh in _detect_laughs(content):
                laugh_counter[laugh.lower()] += 1

            current_turn_bubbles += 1

        if current_turn_bubbles > 0:
            turn_bubble_counts.append(current_turn_bubbles)

    if not all_messages:
        return style

    total_msgs = len(all_messages)

    # Fragmentation
    single_bubble = sum(1 for b in turn_bubble_counts if b == 1)
    multi_bubble = sum(1 for b in turn_bubble_counts if b > 1)
    total_turns = len(turn_bubble_counts)
    if total_turns > 0:
        style.fragmentation_single_pct = round(single_bubble / total_turns * 100, 1)
        style.fragmentation_multi_pct = round(multi_bubble / total_turns * 100, 1)
        style.avg_bubbles_per_turn = round(sum(turn_bubble_counts) / total_turns, 1)

    # Length
    if all_lengths:
        style.avg_message_length = round(statistics.mean(all_lengths), 1)
        style.median_message_length = round(statistics.median(all_lengths), 1)
        sorted_lengths = sorted(all_lengths)
        p90_idx = int(len(sorted_lengths) * 0.9)
        style.p90_message_length = float(sorted_lengths[min(p90_idx, len(sorted_lengths) - 1)])
        style.short_msgs_pct = round(sum(1 for l in all_lengths if l < 30) / total_msgs * 100, 1)
        style.medium_msgs_pct = round(sum(1 for l in all_lengths if l < 60) / total_msgs * 100, 1)
        style.long_msgs_pct = round(sum(1 for l in all_lengths if l > 100) / total_msgs * 100, 1)

    # Emojis
    msgs_with_emoji = sum(1 for c in emoji_counts if c > 0)
    style.emoji_pct = round(msgs_with_emoji / total_msgs * 100, 1) if total_msgs else 0
    total_emojis = sum(emoji_counts)
    style.avg_emojis_per_msg = round(total_emojis / total_msgs, 2) if total_msgs else 0
    style.max_emojis_observed = max(emoji_counts) if emoji_counts else 0
    style.top_emojis = [{"emoji": e, "count": c} for e, c in emoji_counter.most_common(15)]

    # Laughs
    style.laugh_variants = [{"variant": v, "count": c} for v, c in laugh_counter.most_common(10)]

    # Punctuation
    style.punctuation_patterns = {
        "double_exclamation": sum(1 for m in all_messages if "!!" in m),
        "single_exclamation": sum(1 for m in all_messages if "!" in m and "!!" not in m),
        "double_question": sum(1 for m in all_messages if "??" in m),
        "single_question": sum(1 for m in all_messages if "?" in m and "??" not in m),
        "caps_emphasis": sum(1 for m in all_messages if re.search(r"[A-Z]{3,}", m)),
        "total_messages": total_msgs,
    }

    # Language detection
    es_indicators = sum(1 for m in all_messages if any(w in m.lower() for w in ["que", "por", "con", "para", "como", "más", "pero"]))
    en_indicators = sum(1 for m in all_messages if any(w in m.lower() for w in ["the", "and", "for", "you", "with", "this", "that"]))
    if es_indicators > en_indicators * 2:
        style.primary_language = "es"
    elif en_indicators > es_indicators * 2:
        style.primary_language = "en"
    else:
        style.primary_language = "mixed"

    # Dialect detection (regex word boundaries)
    voseo_count = sum(len(_VOSEO_RE.findall(m)) for m in all_messages)
    lunfardo_count = sum(len(_LUNFARDO_RE.findall(m)) for m in all_messages)
    tuteo_count = sum(len(_TUTEO_RE.findall(m)) for m in all_messages)
    style.dialect_details = {
        "voseo_matches": voseo_count,
        "lunfardo_matches": lunfardo_count,
        "tuteo_matches": tuteo_count,
    }
    rioplatense_total = voseo_count + lunfardo_count
    if rioplatense_total > tuteo_count * 2 or rioplatense_total >= 5:
        style.dialect = "rioplatense"
    elif tuteo_count > rioplatense_total * 2:
        style.dialect = "peninsular/neutro"
    elif rioplatense_total > 0 or tuteo_count > 0:
        style.dialect = "mixto"

    # Character repetition (todooo, findeee, siii)
    repeat_counter: Counter = Counter()
    for m in all_messages:
        for match in _CHAR_REPEAT_RE.finditer(m.lower()):
            word = match.group(1)
            if len(word) >= 3:
                repeat_counter[word] += 1
    style.vowel_repetitions = [{"word": w, "count": c} for w, c in repeat_counter.most_common(20)]

    # Language mix
    if en_indicators > 0 and es_indicators > 0:
        style.language_mix = {
            "es_indicators": es_indicators,
            "en_indicators": en_indicators,
            "mix_ratio": round(en_indicators / max(es_indicators, 1) * 100, 1),
        }

    return style


def compute_creator_dictionary(conversations: list[CleanedConversation]) -> CreatorDictionary:
    """Extract real phrase frequencies from creator messages. No LLM needed."""
    all_msgs: list[str] = []
    for conv in conversations:
        for msg in conv.messages:
            if msg.origin == MessageOrigin.CREATOR_REAL and msg.content:
                all_msgs.append(msg.content.strip())

    if not all_msgs:
        return CreatorDictionary()

    short_msgs = [m for m in all_msgs if len(m) < 80]

    def _match_and_count(messages: list[str], pattern: re.Pattern, use_start: bool = False) -> list[dict]:
        counter: Counter = Counter()
        for m in messages:
            if (use_start and pattern.match(m)) or (not use_start and pattern.search(m)):
                counter[m] += 1
        return [{"phrase": p, "count": c} for p, c in counter.most_common(15)]

    dictionary = CreatorDictionary()
    dictionary.greetings = _match_and_count(short_msgs, _GREETING_RE, use_start=True)
    dictionary.farewells = _match_and_count(short_msgs, _FAREWELL_RE)
    dictionary.gratitude = _match_and_count(short_msgs, _GRATITUDE_RE)
    dictionary.validation = _match_and_count(short_msgs, _VALIDATION_RE)
    dictionary.confirmation = _match_and_count(short_msgs, _CONFIRMATION_RE, use_start=True)
    dictionary.laughter = _match_and_count(short_msgs, _LAUGH_ONLY_RE, use_start=True)
    dictionary.encouragement = _match_and_count(short_msgs, _ENCOURAGEMENT_RE)

    questions: Counter = Counter()
    for m in all_msgs:
        if m.endswith("?") and len(m) < 120:
            questions[m] += 1
    dictionary.frequent_questions = [{"phrase": p, "count": c} for p, c in questions.most_common(15)]

    return dictionary


# ── LLM Prompts (split into 3 to prevent truncation) ───────────────

_SHARED_RULES = """REGLAS ABSOLUTAS:
1. NO INVENTES NADA. Todo debe derivar de los datos.
2. CUANTIFICA TODO con evidencia textual.
3. Extrae FRASES TEXTUALES reales como evidencia.
4. NO generes el diccionario de frases (secciones 2.1-2.8) — ya esta computado.
5. Tu respuesta DEBE ser DETALLADA y EXHAUSTIVA. MINIMO 800 palabras.
6. Incluye MULTIPLES ejemplos reales textuales para cada punto."""

PROFILE_IDENTITY_PROMPT = f"""Eres un analista experto en comportamiento conversacional y clonacion de personalidad.

{_SHARED_RULES}

Genera las siguientes secciones con MAXIMO DETALLE. MINIMO 800 PALABRAS en total.

## 1. IDENTIDAD CONVERSACIONAL

### 1.1 Datos duros (extraidos de conversaciones, NO inventados):
- **Profesion/actividad**: [que hace, con evidencia textual: "frase real del creador"]
- **Ubicacion**: [donde vive, con evidencia: "frase real"]
- **Idioma base + dialecto**: [que idioma usa, con ejemplos de voseo/tuteo/lunfardo]
- **Intereses personales**: [lista de al menos 5 intereses con frases reales como evidencia]

### 1.2 Autoimagen (MINIMO 5 frases reales donde el creador se describe a si mismo)
Para cada frase: "[frase real textual]" — contexto de cuando lo dijo

### 1.3 Imagen externa (MINIMO 5 frases reales de los leads sobre el creador)
Para cada frase: "[frase real textual]" — quien lo dijo y en que contexto

## 2. MULETILLAS Y VOCABULARIO UNICO

### 2.9 Muletillas unicas (MINIMO 8 muletillas):
Para cada una: "[frase]" — Solo este creador usaria esto porque: [explicacion detallada]

### 2.10 Vocabulario PROHIBIDO (MINIMO 5 frases):
Para cada una: "[frase]" — Por que este creador NUNCA diria esto"""

PROFILE_TONE_PROMPT = f"""Eres un analista experto en comportamiento conversacional y clonacion de personalidad.

{_SHARED_RULES}

Genera la seccion 3 COMPLETA con TODAS las 7 subsecciones. MINIMO 800 PALABRAS en total.
Para CADA subseccion DEBES incluir TODOS estos campos con detalle:

## 3. MAPA DE ADAPTACION DE TONO POR CONTEXTO

### 3.1 Con amigos cercanos
- **Tono base**: [descripcion detallada del tono: informal/formal, cercano/distante, con adjetivos especificos]
- **Longitud vs promedio**: [mas corto/igual/mas largo que el promedio general, con cifra estimada]
- **Emojis vs promedio**: [mas/menos/igual que el promedio general, cuales usa mas en este contexto]
- **Ejemplos reales**: [MINIMO 3 frases textuales reales del creador hablando con amigos]
- **Diferencias clave**: [que cambia respecto al estilo general]

### 3.2 Con leads/clientes potenciales
[MISMO formato completo con los 5 campos]

### 3.3 Con colaboradores B2B
[MISMO formato completo con los 5 campos]

### 3.4 Con fans/seguidores casuales
[MISMO formato completo con los 5 campos]

### 3.5 Con vendors/proveedores
[MISMO formato completo con los 5 campos]

### 3.6 En contexto de venta
[MISMO formato completo con los 5 campos]

### 3.7 En contexto emocional
[MISMO formato completo con los 5 campos]

ES OBLIGATORIO completar las 7 subsecciones. Si no hay datos para alguna, indica "Sin datos suficientes" pero completa el formato."""

PROFILE_SALES_PROMPT = f"""Eres un analista experto en comportamiento conversacional y clonacion de personalidad.

{_SHARED_RULES}

Genera las siguientes secciones con MAXIMO DETALLE. MINIMO 600 PALABRAS en total.

## 4. METODO DE VENTA DEL CREADOR

- **Vende directamente por DM?**: [si/no — con MINIMO 3 frases reales como evidencia]
- **Funnel real observado**: [describir paso a paso el funnel con ejemplos textuales]
- **Frases de venta reales**: [MINIMO 5 frases textuales reales] Para cada una: "[frase]" — Contexto y lead
- **Usa presion?**: [si/no — con evidencia textual]
- **Cuando migra a otro canal**: [email, whatsapp, link — con frases reales como evidencia]
- **Senales de compra que activan al creador**: [lista de al menos 3 senales con ejemplos]

## 5. LIMITACIONES DEL PERFIL

Para cada limitacion, cuantifica el impacto:
- **Audios no transcritos**: [cuantos audios hay en los datos? que % del total?]
- **Stories expiradas**: [cuantas menciones de stories? que informacion se pierde?]
- **Sesgo de muestra**: [que tipo de leads predominan? que falta?]
- **Gaps temporales**: [hay periodos sin actividad? cuales?]"""


def _format_emoji_list(emojis: list[dict]) -> str:
    return ", ".join(e["emoji"] + " (" + str(e["count"]) + "x)" for e in emojis)


def _format_laugh_list(laughs: list[dict]) -> str:
    return ", ".join(v["variant"] + " (" + str(v["count"]) + "x)" for v in laughs)


def _build_profile_context(
    creator_name: str,
    profile: PersonalityProfile,
    writing_style: WritingStyle,
    dictionary: CreatorDictionary,
    lead_analyses_text: str,
    conversations: list[CleanedConversation],
) -> str:
    """Build the shared context string for all 3 LLM profile calls."""
    # Stats
    stats_lines = [
        f"CREADOR: {creator_name}",
        f"DATOS: {profile.messages_analyzed} mensajes reales / {profile.leads_analyzed} leads / {profile.months_covered} meses",
        f"CONFIANZA: {profile.confidence}",
        "",
        "ESTADISTICAS DE ESCRITURA:",
        f"- Fragmentacion: {writing_style.avg_bubbles_per_turn} burbujas/turno ({writing_style.fragmentation_multi_pct}% multi-burbuja)",
        f"- Longitud media: {writing_style.avg_message_length} chars, mediana: {writing_style.median_message_length}, P90: {writing_style.p90_message_length}",
        f"- % mensajes <30 chars: {writing_style.short_msgs_pct}%",
        f"- Emojis: {writing_style.emoji_pct}% mensajes, media {writing_style.avg_emojis_per_msg}/msg",
        f"- Top emojis: {_format_emoji_list(writing_style.top_emojis[:10])}",
        f"- Risas: {_format_laugh_list(writing_style.laugh_variants[:5])}",
        f"- Idioma: {writing_style.primary_language}, Dialecto: {writing_style.dialect or 'no detectado'}",
        f"  (voseo={writing_style.dialect_details.get('voseo_matches', 0)}, lunfardo={writing_style.dialect_details.get('lunfardo_matches', 0)}, tuteo={writing_style.dialect_details.get('tuteo_matches', 0)})",
    ]

    if writing_style.vowel_repetitions:
        reps = ", ".join(f"{r['word']} ({r['count']}x)" for r in writing_style.vowel_repetitions[:10])
        stats_lines.append(f"- Repeticiones: {reps}")

    # Dictionary (top 5 per category to keep context lean)
    stats_lines.append("\nDICCIONARIO COMPUTADO (NO regeneres esto, usa como referencia):")
    for label, entries in [
        ("Saludos", dictionary.greetings),
        ("Despedidas", dictionary.farewells),
        ("Gratitud", dictionary.gratitude),
        ("Validacion", dictionary.validation),
        ("Confirmacion", dictionary.confirmation),
        ("Risa", dictionary.laughter),
        ("Animo", dictionary.encouragement),
        ("Preguntas", dictionary.frequent_questions),
    ]:
        if entries:
            stats_lines.append(f"  {label}:")
            for e in entries[:5]:
                stats_lines.append(f"    \"{e['phrase']}\" — {e['count']}x")

    # Lead analyses (trimmed to ~3000 chars for context efficiency)
    stats_lines.append(f"\nANALISIS POR LEAD (resumen):\n{lead_analyses_text[:3000]}")

    # Conversation samples (10 convs x 8 msgs to keep under ~4000 tokens total)
    top_convs = sorted(conversations, key=lambda c: c.creator_real_count, reverse=True)[:10]
    stats_lines.append("\nMUESTRAS DE CONVERSACIONES REALES (las 10 mas ricas):")
    for conv in top_convs:
        creator_msgs = [m.content for m in conv.messages if m.origin == MessageOrigin.CREATOR_REAL and m.content]
        if creator_msgs:
            name = conv.full_name or conv.username
            stats_lines.append(f"--- Con @{conv.username} ({name}) ---")
            for msg in creator_msgs[:8]:
                stats_lines.append(f"  CREADOR: {msg}")
            stats_lines.append("")

    return "\n".join(stats_lines)


async def generate_personality_profile(
    conversations: list[CleanedConversation],
    lead_analyses_text: str,
    writing_style: WritingStyle,
    dictionary: CreatorDictionary,
    creator_name: str = "",
) -> PersonalityProfile:
    """
    Generate the full personality profile using 3 parallel LLM calls.
    Each call generates specific sections to prevent truncation.
    """
    profile = PersonalityProfile(
        creator_name=creator_name,
        messages_analyzed=sum(c.creator_real_count for c in conversations),
        leads_analyzed=len(conversations),
        writing_style=writing_style,
        dictionary=dictionary,
    )

    # Calculate months covered
    all_dates = []
    for conv in conversations:
        if conv.first_message_at:
            all_dates.append(conv.first_message_at)
        if conv.last_message_at:
            all_dates.append(conv.last_message_at)
    if all_dates:
        span = max(all_dates) - min(all_dates)
        profile.months_covered = max(1, span.days // 30)

    if profile.messages_analyzed >= 200:
        profile.confidence = "alta"
    elif profile.messages_analyzed >= 50:
        profile.confidence = "media"
    else:
        profile.confidence = "baja"

    # Build shared context
    context = _build_profile_context(
        creator_name, profile, writing_style, dictionary,
        lead_analyses_text, conversations,
    )

    # 3 parallel LLM calls — each generates its section
    logger.info("Launching 3 parallel LLM calls for personality profile (context=%d chars)...", len(context))
    identity_result, tone_result, sales_result = await asyncio.gather(
        extract_with_llm(
            system_prompt=PROFILE_IDENTITY_PROMPT,
            user_message=context,
            max_tokens=8192,
            temperature=0.4,
        ),
        extract_with_llm(
            system_prompt=PROFILE_TONE_PROMPT,
            user_message=context,
            max_tokens=8192,
            temperature=0.4,
        ),
        extract_with_llm(
            system_prompt=PROFILE_SALES_PROMPT,
            user_message=context,
            max_tokens=8192,
            temperature=0.4,
        ),
    )

    # Concatenate results
    parts = []
    for part in [identity_result, tone_result, sales_result]:
        if part:
            parts.append(_strip_code_blocks(part))

    combined = "\n\n".join(parts)
    if combined:
        profile.raw_profile_text = combined
        _parse_profile_sections(profile, combined)
        logger.info(
            "Profile LLM complete: %d chars (identity=%d, tone=%d, sales=%d)",
            len(combined),
            len(identity_result or ""),
            len(tone_result or ""),
            len(sales_result or ""),
        )
    else:
        logger.warning("All 3 profile LLM calls returned empty")

    return profile


def _parse_profile_sections(profile: PersonalityProfile, text: str) -> None:
    """Extract structured data from the LLM personality profile text."""
    lines = text.split("\n")
    current_section = ""
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        if "identidad conversacional" in line_stripped.lower():
            current_section = "identity"
        elif "adaptación de tono" in line_stripped.lower() or "adaptacion de tono" in line_stripped.lower():
            current_section = "tone"
        elif "método de venta" in line_stripped.lower() or "metodo de venta" in line_stripped.lower():
            current_section = "sales"
        elif "limitaciones" in line_stripped.lower():
            current_section = "limitations"
        if current_section == "limitations" and line_stripped.startswith("-"):
            profile.limitations.append(line_stripped.lstrip("- "))

    for pattern, key in [
        (r"profesi[oó]n[/:]?\s*(?:actividad:?)?\s*(.+)", "profession"),
        (r"ubicaci[oó]n:?\s*(.+)", "location"),
        (r"idioma[^:]*:?\s*(.+)", "language"),
    ]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            profile.identity_facts[key] = match.group(1).strip()


def _add_dict_section(sections: list[str], title: str, entries: list[dict]) -> None:
    """Add a dictionary section to the doc output."""
    sections.append(title)
    if entries:
        for e in entries:
            sections.append(f'  "{e["phrase"]}" — {e["count"]} veces')
    else:
        sections.append("  (sin datos suficientes)")


def generate_doc_c(profile: PersonalityProfile) -> str:
    """Generate the complete Doc C text."""
    ws = profile.writing_style
    d = profile.dictionary

    sections = [
        "# DOCUMENTO C: PERSONALITY PROFILE (ADN CONVERSACIONAL)",
        f"{'=' * 60}",
        f"PERSONALITY PROFILE: {profile.creator_name}",
        f"Basado en: {profile.messages_analyzed} mensajes reales / {profile.leads_analyzed} leads / {profile.months_covered} meses",
        f"Confianza del perfil: {profile.confidence}",
        f"{'=' * 60}",
        "",
        "## ESTADISTICAS COMPUTADAS",
        "",
        "### Fragmentacion",
        f"- % turnos con mensaje unico: {ws.fragmentation_single_pct}%",
        f"- % turnos con 2+ burbujas: {ws.fragmentation_multi_pct}%",
        f"- Promedio burbujas por turno: {ws.avg_bubbles_per_turn}",
        "",
        "### Longitud de mensajes",
        f"- Media: {ws.avg_message_length} chars | Mediana: {ws.median_message_length} chars",
        f"- Percentil 90: {ws.p90_message_length} chars",
        f"- % mensajes < 30 chars: {ws.short_msgs_pct}%",
        f"- % mensajes < 60 chars: {ws.medium_msgs_pct}%",
        f"- % mensajes > 100 chars: {ws.long_msgs_pct}%",
        "",
        "### Emojis",
        f"- % mensajes con emoji: {ws.emoji_pct}%",
        f"- Media por mensaje: {ws.avg_emojis_per_msg}",
        f"- Maximo observado: {ws.max_emojis_observed}",
        "- Top emojis:",
    ]
    for e in ws.top_emojis[:10]:
        sections.append(f"  {e['emoji']} -> {e['count']} veces")

    sections.extend(["", "### Risas"])
    for v in ws.laugh_variants[:5]:
        sections.append(f"  \"{v['variant']}\" -> {v['count']} veces")

    if ws.vowel_repetitions:
        sections.extend(["", "### Repeticiones de caracteres (expresividad)"])
        for r in ws.vowel_repetitions[:15]:
            sections.append(f"  \"{r['word']}\" -> {r['count']} veces")

    sections.extend([
        "", "### Idioma",
        f"- Primario: {ws.primary_language}",
        f"- Dialecto: {ws.dialect or 'no detectado'}",
    ])
    if ws.dialect_details:
        sections.append(
            f"  (voseo={ws.dialect_details.get('voseo_matches', 0)}, "
            f"lunfardo={ws.dialect_details.get('lunfardo_matches', 0)}, "
            f"tuteo={ws.dialect_details.get('tuteo_matches', 0)})"
        )

    # Dictionary
    sections.extend(["", "## DICCIONARIO DEL CREADOR (computado de mensajes reales)", ""])
    _add_dict_section(sections, "### 2.1 Saludos", d.greetings)
    _add_dict_section(sections, "### 2.2 Despedidas", d.farewells)
    _add_dict_section(sections, "### 2.3 Gratitud", d.gratitude)
    _add_dict_section(sections, "### 2.4 Validacion/celebracion", d.validation)
    _add_dict_section(sections, "### 2.5 Confirmacion/acuerdo", d.confirmation)
    _add_dict_section(sections, "### 2.6 Risa/humor", d.laughter)
    _add_dict_section(sections, "### 2.7 Animo/motivacion", d.encouragement)
    _add_dict_section(sections, "### 2.8 Preguntas frecuentes que hace", d.frequent_questions)

    # LLM analysis
    sections.extend([
        "", "## ANALISIS LLM", "",
        profile.raw_profile_text or "LLM analysis not available",
        "", f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ])

    return "\n".join(sections)
