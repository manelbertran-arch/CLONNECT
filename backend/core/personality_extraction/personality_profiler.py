"""
Phase 3 — Personality Profiler (Doc C)

Generates the Personality Profile (conversational DNA) from all analyzed
conversations. This is the most important output — the "genome" of the clone.

Two-step process:
1. Statistical analysis of writing patterns (computed locally, no LLM)
2. LLM synthesis of personality traits, dictionary, tone adaptations, sales method
"""

import logging
import re
import statistics
from collections import Counter
from datetime import datetime
from typing import Optional

from core.personality_extraction.llm_client import extract_with_llm
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
    "[\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess, etc.
    "\U0001FA70-\U0001FAFF"  # more symbols
    "\U00002600-\U000026FF"  # misc symbols
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0000200D"  # zero width joiner
    "\U00002640\U00002642"  # gender symbols
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


def _extract_emojis(text: str) -> list[str]:
    """Extract all individual emojis from text."""
    return EMOJI_PATTERN.findall(text)


def _count_emojis(text: str) -> int:
    """Count emojis in text."""
    return len(_extract_emojis(text))


def _detect_laughs(text: str) -> list[str]:
    """Detect laugh variants (jaja, jajaja, haha, etc.)."""
    return LAUGH_PATTERN.findall(text)


def compute_writing_style(conversations: list[CleanedConversation]) -> WritingStyle:
    """
    Compute writing style statistics from all creator real messages.
    Pure computation — no LLM needed.
    """
    style = WritingStyle()

    # Collect all creator real messages
    all_messages: list[str] = []
    all_lengths: list[int] = []
    emoji_counts: list[int] = []
    emoji_counter: Counter = Counter()
    laugh_counter: Counter = Counter()
    turn_bubble_counts: list[int] = []

    for conv in conversations:
        # Track multi-bubble turns (consecutive creator messages)
        current_turn_bubbles = 0
        for msg in conv.messages:
            if msg.origin != MessageOrigin.CREATOR_REAL:
                if current_turn_bubbles > 0:
                    turn_bubble_counts.append(current_turn_bubbles)
                    current_turn_bubbles = 0
                continue

            content = msg.content or ""
            all_messages.append(content)
            msg_len = len(content)
            all_lengths.append(msg_len)

            # Emoji analysis
            emojis = _extract_emojis(content)
            emoji_counts.append(len(emojis))
            for e in emojis:
                emoji_counter[e] += 1

            # Laugh analysis
            laughs = _detect_laughs(content)
            for laugh in laughs:
                laugh_counter[laugh.lower()] += 1

            current_turn_bubbles += 1

        # Don't forget last turn
        if current_turn_bubbles > 0:
            turn_bubble_counts.append(current_turn_bubbles)

    if not all_messages:
        return style

    total_msgs = len(all_messages)

    # ── Fragmentation ──
    single_bubble = sum(1 for b in turn_bubble_counts if b == 1)
    multi_bubble = sum(1 for b in turn_bubble_counts if b > 1)
    total_turns = len(turn_bubble_counts)

    if total_turns > 0:
        style.fragmentation_single_pct = round(single_bubble / total_turns * 100, 1)
        style.fragmentation_multi_pct = round(multi_bubble / total_turns * 100, 1)
        style.avg_bubbles_per_turn = round(
            sum(turn_bubble_counts) / total_turns, 1
        )

    # ── Length ──
    if all_lengths:
        style.avg_message_length = round(statistics.mean(all_lengths), 1)
        style.median_message_length = round(statistics.median(all_lengths), 1)
        sorted_lengths = sorted(all_lengths)
        p90_idx = int(len(sorted_lengths) * 0.9)
        style.p90_message_length = float(sorted_lengths[min(p90_idx, len(sorted_lengths) - 1)])
        style.short_msgs_pct = round(sum(1 for l in all_lengths if l < 30) / total_msgs * 100, 1)
        style.medium_msgs_pct = round(sum(1 for l in all_lengths if l < 60) / total_msgs * 100, 1)
        style.long_msgs_pct = round(sum(1 for l in all_lengths if l > 100) / total_msgs * 100, 1)

    # ── Emojis ──
    msgs_with_emoji = sum(1 for c in emoji_counts if c > 0)
    style.emoji_pct = round(msgs_with_emoji / total_msgs * 100, 1) if total_msgs else 0
    total_emojis = sum(emoji_counts)
    style.avg_emojis_per_msg = round(total_emojis / total_msgs, 2) if total_msgs else 0
    style.max_emojis_observed = max(emoji_counts) if emoji_counts else 0
    style.top_emojis = [
        {"emoji": emoji, "count": count}
        for emoji, count in emoji_counter.most_common(15)
    ]

    # ── Laughs ──
    style.laugh_variants = [
        {"variant": variant, "count": count}
        for variant, count in laugh_counter.most_common(10)
    ]

    # ── Punctuation ──
    excl_double = sum(1 for m in all_messages if "!!" in m)
    excl_single = sum(1 for m in all_messages if "!" in m and "!!" not in m)
    question_double = sum(1 for m in all_messages if "??" in m)
    question_single = sum(1 for m in all_messages if "?" in m and "??" not in m)
    caps_emphasis = sum(1 for m in all_messages if re.search(r"[A-Z]{3,}", m))

    style.punctuation_patterns = {
        "double_exclamation": excl_double,
        "single_exclamation": excl_single,
        "double_question": question_double,
        "single_question": question_single,
        "caps_emphasis": caps_emphasis,
        "total_messages": total_msgs,
    }

    # ── Language detection (basic) ──
    es_indicators = sum(1 for m in all_messages if any(w in m.lower() for w in ["que", "por", "con", "para", "como", "más", "pero"]))
    en_indicators = sum(1 for m in all_messages if any(w in m.lower() for w in ["the", "and", "for", "you", "with", "this", "that"]))

    if es_indicators > en_indicators * 2:
        style.primary_language = "es"
    elif en_indicators > es_indicators * 2:
        style.primary_language = "en"
    else:
        style.primary_language = "mixed"

    # Dialect detection
    voseo = sum(1 for m in all_messages if any(w in m.lower() for w in ["vos", "tenés", "podés", "querés", "sabés", "decime", "mirá"]))
    tuteo = sum(1 for m in all_messages if any(w in m.lower() for w in ["tú", "tienes", "puedes", "quieres", "sabes", "dime", "mira"]))

    if voseo > tuteo * 2:
        style.dialect = "rioplatense"
    elif tuteo > voseo * 2:
        style.dialect = "peninsular/neutro"
    elif voseo > 0 or tuteo > 0:
        style.dialect = "mixto"

    if en_indicators > 0 and es_indicators > 0:
        style.language_mix = {
            "es_indicators": es_indicators,
            "en_indicators": en_indicators,
            "mix_ratio": round(en_indicators / max(es_indicators, 1) * 100, 1),
        }

    return style


# ── LLM Personality Synthesis ───────────────────────────────────────

PERSONALITY_SYSTEM_PROMPT = """Eres un analista experto en comportamiento conversacional humano y diseño de sistemas de clonación de personalidad.

Tu tarea es sintetizar el PERSONALITY PROFILE (ADN conversacional) de un creador de contenido basándote en:
1. Los análisis individuales de cada lead (Doc B)
2. Las estadísticas computadas de escritura
3. Las conversaciones reales más relevantes

REGLAS ABSOLUTAS:
1. NO INVENTES NADA. Todo debe derivar de los datos.
2. CUANTIFICA TODO con evidencia textual.
3. Extrae FRASES TEXTUALES reales como evidencia.
4. Las excepciones son tan valiosas como las reglas.

Genera el perfil con estas secciones exactas:

## 1. IDENTIDAD CONVERSACIONAL

### 1.1 Datos duros (extraídos de conversaciones, NO inventados):
- Profesión/actividad
- Ubicación
- Idioma base + dialecto
- Intereses personales (extraídos de conversaciones)

### 1.2 Autoimagen (frases reales donde el creador se describe)

### 1.3 Imagen externa (frases reales de los leads sobre el creador)

## 2. DICCIONARIO DEL CREADOR

Para CADA categoría, listar TODAS las variaciones reales con frecuencia:

### 2.1 Saludos: "[frase]" — [N veces]
### 2.2 Despedidas: "[frase]" — [N veces]
### 2.3 Gratitud: "[frase]" — [N veces]
### 2.4 Validación/celebración: "[frase]" — [N veces]
### 2.5 Confirmación/acuerdo: "[frase]" — [N veces]
### 2.6 Risa/humor: "[frase]" — [N veces]
### 2.7 Ánimo/motivación: "[frase]" — [N veces]
### 2.8 Preguntas frecuentes que hace: "[frase]" — [N veces]
### 2.9 Muletillas únicas: "[frase]" — [N veces] — Solo este creador usaría esto porque: [...]
### 2.10 Vocabulario PROHIBIDO (nunca dice el humano real): "[frase]" — Por qué no

## 3. MAPA DE ADAPTACIÓN DE TONO POR CONTEXTO

### 3.1 Con amigos cercanos: Tono, longitud, emojis, ejemplo
### 3.2 Con leads/clientes potenciales: Tono, longitud, emojis, ejemplo
### 3.3 Con colaboradores B2B: Tono, ejemplo
### 3.4 Con fans/seguidores casuales: Tono, ejemplo
### 3.5 En contexto de venta: Técnica, ejemplo
### 3.6 En contexto emocional: Tono, ejemplo

## 4. MÉTODO DE VENTA DEL CREADOR

- ¿Vende directamente por DM?: [sí/no — evidencia]
- Funnel real observado: [pasos]
- Frases de venta reales: "[frase]" — Contexto
- ¿Usa presión?: [sí/no — evidencia]
- Cuándo migra a otro canal
- Señales de compra que activan al creador

## 5. LIMITACIONES DEL PERFIL

- Audios no transcritos
- Stories expiradas
- Sesgo de muestra
- Gaps"""


async def generate_personality_profile(
    conversations: list[CleanedConversation],
    lead_analyses_text: str,
    writing_style: WritingStyle,
    creator_name: str = "",
) -> PersonalityProfile:
    """
    Generate the full personality profile by combining statistical analysis
    with LLM synthesis.
    """
    profile = PersonalityProfile(
        creator_name=creator_name,
        messages_analyzed=sum(c.creator_real_count for c in conversations),
        leads_analyzed=len(conversations),
        writing_style=writing_style,
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

    # Set confidence based on data volume
    if profile.messages_analyzed >= 200:
        profile.confidence = "alta"
    elif profile.messages_analyzed >= 50:
        profile.confidence = "media"
    else:
        profile.confidence = "baja"

    # ── Build representative conversation samples for LLM ──
    # Select top conversations (most creator messages) for the LLM
    top_convs = sorted(conversations, key=lambda c: c.creator_real_count, reverse=True)[:20]

    samples = []
    for conv in top_convs:
        creator_msgs = [
            m.content for m in conv.messages
            if m.origin == MessageOrigin.CREATOR_REAL and m.content
        ]
        if creator_msgs:
            name = conv.full_name or conv.username
            samples.append(f"--- Con @{conv.username} ({name}) ---")
            for msg in creator_msgs[:15]:  # Max 15 messages per lead
                samples.append(f"  CREADOR: {msg}")
            samples.append("")

    # ── Build writing stats summary for LLM ──
    stats_text = f"""ESTADÍSTICAS DE ESCRITURA COMPUTADAS:

Fragmentación:
- % turnos con mensaje único: {writing_style.fragmentation_single_pct}%
- % turnos con 2+ burbujas: {writing_style.fragmentation_multi_pct}%
- Promedio burbujas por turno: {writing_style.avg_bubbles_per_turn}

Longitud:
- Media: {writing_style.avg_message_length} chars
- Mediana: {writing_style.median_message_length} chars
- Percentil 90: {writing_style.p90_message_length} chars
- % mensajes < 30 chars: {writing_style.short_msgs_pct}%
- % mensajes < 60 chars: {writing_style.medium_msgs_pct}%
- % mensajes > 100 chars: {writing_style.long_msgs_pct}%

Emojis:
- % mensajes con emoji: {writing_style.emoji_pct}%
- Media por mensaje: {writing_style.avg_emojis_per_msg}
- Máximo observado: {writing_style.max_emojis_observed}
- Top emojis: {', '.join(f"{e['emoji']} ({e['count']}x)" for e in writing_style.top_emojis[:10])}

Risas:
{chr(10).join(f"- {v['variant']}: {v['count']}x" for v in writing_style.laugh_variants[:5])}

Idioma: {writing_style.primary_language}
Dialecto: {writing_style.dialect or 'no detectado'}
Mezcla: {writing_style.language_mix or 'ninguna'}"""

    # ── Call LLM for personality synthesis ──
    user_message = (
        f"CREADOR: {creator_name}\n"
        f"DATOS: {profile.messages_analyzed} mensajes reales / {profile.leads_analyzed} leads / {profile.months_covered} meses\n"
        f"CONFIANZA: {profile.confidence}\n\n"
        f"{stats_text}\n\n"
        f"ANÁLISIS POR LEAD (resumen):\n{lead_analyses_text[:20000]}\n\n"  # Truncate if too long
        f"MUESTRAS DE CONVERSACIONES REALES:\n" + "\n".join(samples)
    )

    llm_result = await extract_with_llm(
        system_prompt=PERSONALITY_SYSTEM_PROMPT,
        user_message=user_message,
        max_tokens=8192,
        temperature=0.3,
    )

    if llm_result:
        profile.raw_profile_text = llm_result
        _parse_profile_sections(profile, llm_result)

    return profile


def _parse_profile_sections(profile: PersonalityProfile, text: str) -> None:
    """Extract structured data from the LLM personality profile text."""
    # This is a best-effort parser — the raw text is always available
    lines = text.split("\n")

    current_section = ""
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Detect sections
        if "identidad conversacional" in line_stripped.lower():
            current_section = "identity"
        elif "diccionario del creador" in line_stripped.lower():
            current_section = "dictionary"
        elif "adaptación de tono" in line_stripped.lower():
            current_section = "tone"
        elif "método de venta" in line_stripped.lower():
            current_section = "sales"
        elif "limitaciones" in line_stripped.lower():
            current_section = "limitations"

        # Parse limitations
        if current_section == "limitations" and line_stripped.startswith("-"):
            profile.limitations.append(line_stripped.lstrip("- "))

    # Extract identity facts from raw text
    for pattern, key in [
        (r"profesión[/:]?\s*(?:actividad:?)?\s*(.+)", "profession"),
        (r"ubicación:?\s*(.+)", "location"),
        (r"idioma[^:]*:?\s*(.+)", "language"),
    ]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            profile.identity_facts[key] = match.group(1).strip()


def generate_doc_c(profile: PersonalityProfile) -> str:
    """Generate the complete Doc C text."""
    ws = profile.writing_style

    sections = [
        "# DOCUMENTO C: PERSONALITY PROFILE (ADN CONVERSACIONAL)",
        f"{'=' * 60}",
        f"PERSONALITY PROFILE: {profile.creator_name}",
        f"Basado en: {profile.messages_analyzed} mensajes reales / {profile.leads_analyzed} leads / {profile.months_covered} meses",
        f"Confianza del perfil: {profile.confidence}",
        f"{'=' * 60}",
        "",
        "## ESTADÍSTICAS COMPUTADAS",
        "",
        f"### Fragmentación",
        f"- % turnos con mensaje único: {ws.fragmentation_single_pct}%",
        f"- % turnos con 2+ burbujas: {ws.fragmentation_multi_pct}%",
        f"- Promedio burbujas por turno: {ws.avg_bubbles_per_turn}",
        "",
        f"### Longitud de mensajes",
        f"- Media: {ws.avg_message_length} chars | Mediana: {ws.median_message_length} chars",
        f"- Percentil 90: {ws.p90_message_length} chars",
        f"- % mensajes < 30 chars: {ws.short_msgs_pct}%",
        f"- % mensajes < 60 chars: {ws.medium_msgs_pct}%",
        f"- % mensajes > 100 chars: {ws.long_msgs_pct}%",
        "",
        f"### Emojis",
        f"- % mensajes con emoji: {ws.emoji_pct}%",
        f"- Media por mensaje: {ws.avg_emojis_per_msg}",
        f"- Máximo observado: {ws.max_emojis_observed}",
        f"- Top emojis:",
    ]
    for e in ws.top_emojis[:10]:
        sections.append(f"  {e['emoji']} → {e['count']} veces")

    sections.extend([
        "",
        f"### Risas",
    ])
    for v in ws.laugh_variants[:5]:
        sections.append(f"  \"{v['variant']}\" → {v['count']} veces")

    sections.extend([
        "",
        f"### Idioma",
        f"- Primario: {ws.primary_language}",
        f"- Dialecto: {ws.dialect or 'no detectado'}",
        "",
        "## ANÁLISIS LLM",
        "",
        profile.raw_profile_text or "⚠️ LLM analysis not available",
        "",
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ])

    return "\n".join(sections)
