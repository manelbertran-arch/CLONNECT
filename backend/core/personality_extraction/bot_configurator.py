"""
Phase 4 — Bot Configurator (Doc D)

Generates the system prompt, blacklist, and template pool
from the Personality Profile (Doc C).

Bug fixes v3:
- Bug 5: Universal blacklist + copilot-extracted phrases + LLM additions
- Bug 7: Template pool extracted from real creator messages, not LLM-generated
- Bug 8: System prompt split into 3 parallel LLM calls (anti-truncation)
- Bug 11: Multi-bubble metadata messages filtered out
- Bug 12: 6 new template categories (sales_soft, reconnect, emotional,
          scheduling, content_validation, expand_reaction)
- Bug 13: Full name parametrization across ALL templates
"""

import asyncio
import json
import logging
import re
from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from core.personality_extraction.llm_client import (
    _strip_code_blocks,
    extract_json_with_llm,
    extract_with_llm,
)
from core.personality_extraction.models import (
    BotConfiguration,
    CleanedConversation,
    MessageOrigin,
    MultiBubbleTemplate,
    PersonalityProfile,
    TemplateCategory,
    TemplateEntry,
    WritingStyle,
)

logger = logging.getLogger(__name__)

# ── Universal blacklist (Bug 5 fix) ────────────────────────────────
UNIVERSAL_BLACKLIST = [
    "en qué puedo ayudarte",
    "puedo ayudarte",
    "no dudes en",
    "estoy aquí para",
    "con gusto te ayudo",
    "será un placer",
    "quedo a tu disposición",
    "feliz de ayudarte",
    "no dudes en contactarme",
    "estoy a tu disposición",
    "con mucho gusto",
    "me encantaría ayudarte",
    "estaré encantado de",
    "estaré encantada de",
    "si necesitas algo más",
    "no dudes en preguntar",
    "cualquier duda que tengas",
    "quedo atento a tu respuesta",
    "quedo atenta a tu respuesta",
    "no dudes en escribirme",
    "estoy para ayudarte",
    "hay algo más en lo que pueda",
    "espero haberte ayudado",
    "fue un placer ayudarte",
    "me llamó la atención",
    "me parece muy interesante tu",
    "me parece súper interesante",
    "me encanta lo que compartes",
    "Agradezco tu colaboración.",
    "Espero que tengas un excelente día.",
    "Estoy a tu disposición para cualquier consulta.",
    "Saludos cordiales.",
    # Formal/automated phrases
    "Adjunto encontrará la información solicitada",
    "Confirmación de su solicitud",
    "Esperamos que esta información le sea útil",
    "Este es un mensaje automático, por favor no responda",
    "Estimado usuario",
    "Gracias por elegir nuestros servicios",
    "Gracias por su comprensión",
    "Hemos recibido su mensaje",
    "Le deseamos un excelente día",
    "Le mantendremos informado sobre cualquier novedad",
    "Nos pondremos en contacto a la brevedad",
    "Nuestro equipo de soporte está disponible para ayudarle",
    "Para cancelar su suscripción, haga clic aquí",
    "Para más información, visite nuestro sitio web",
    "Reciba un cordial saludo",
]

# ── Metadata message filter (Bug 11) ───────────────────────────────
_METADATA_RE = re.compile(
    r'^(?:Menci[oó]n en story|Mentioned you in their story|Shared content|'
    r'Contenido compartido|Sent an attachment|Replied to (?:your|their) story|'
    r'Liked a message|Shared a (?:post|reel|story)|You sent an attachment|'
    r'\[Media/?Attachment\]|\[Media\]|Reacci[oó]n [\U0001F600-\U0001FAFF\U00002600-\U000027BF\U0000FE0F].*)',
    re.IGNORECASE,
)


def _is_metadata_message(text: str) -> bool:
    """Check if a message is IG metadata, not real content (Bug 11)."""
    return bool(_METADATA_RE.match(text.strip()))


# ── Phone number filter (Bug 14) ────────────────────────────────────
_PHONE_RE = re.compile(r'(?:\+?\d[\d\s\-]{5,})')


def _contains_phone_number(text: str) -> bool:
    """Check if text contains a phone number (6+ digit sequence)."""
    return bool(_PHONE_RE.search(text))


# ── Protected words for parametrization (Bug 15) ────────────────────
PROTECTED_WORDS = {
    # Common Spanish nouns/adjectives that could match lead names
    "semana", "amiga", "amigo", "hermano", "hermana", "crack", "bro",
    "proceso", "abrazo", "día", "dia", "noche", "mes", "año", "hora",
    "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo",
    "coach", "mentor", "life", "yoga", "zen", "sol", "luna", "mar",
    "rio", "río", "rey", "flor", "paz", "luz", "arte", "amor",
    "bella", "linda", "dulce", "angel", "ángel", "rosa", "iris",
    "todo", "bien", "mal", "gran", "buena", "bueno", "nueva", "nuevo",
    "queen", "king", "joy", "hope", "grace",
    # Greeting/farewell words that IGNORECASE can capture as "names"
    "tardes", "noches", "mañana", "como", "cómo", "buen", "buenos",
    "días", "dias", "hola", "buenas", "tales",
    # Articles/prepositions/short words that should never be treated as names
    "un", "una", "uno", "el", "la", "los", "las", "de", "del", "en",
    "con", "por", "para", "que", "qué", "tal", "más", "muy", "son",
    "van", "hay", "mis", "tus", "sus", "nos", "les",
}

# ── Sales direction filter (Bug 18) ─────────────────────────────────
_CREATOR_BUYING_RE = re.compile(
    r'(?:cu[aá]nto me (?:sale|cuesta|cobr)|me apunto|me inscribo|quiero (?:comprar|reservar|apuntarme)|'
    r'd[oó]nde (?:puedo|me) (?:apunt|inscrib|reserv))',
    re.IGNORECASE,
)


# ── Template category patterns (expanded with 6 new — Bug 12) ──────
_CAT_PATTERNS = {
    "greeting": re.compile(
        r'^(?:hola|hey|ey+|buenas?|qué tal|qué onda|buenos?\s*d[ií]as?|buenas\s*(?:tardes|noches)|'
        r'c[oó]mo\s+(?:est[aá]s|and[aá]s|va)|todo\s+bien|bien\s+y\s+(?:vos|t[uú]))',
        re.IGNORECASE,
    ),
    "farewell": re.compile(
        r'(?:chau|adi[oó]s|nos vemos|hasta (?:luego|pronto|mañana)|buenas noches|un abrazo|abrazo|un beso|cu[ií]date)',
        re.IGNORECASE,
    ),
    "gratitude": re.compile(
        r'(?:gracias|te agradezco|mil gracias|muchas gracias)',
        re.IGNORECASE,
    ),
    "celebration": re.compile(
        r'(?:genial|excelente|increíble|tremendo|bien ah[ií]|crack|gros[oa]|fenómenal?|espectacular|buen[ií]simo|brutal|qué crack|grande)',
        re.IGNORECASE,
    ),
    "confirmation": re.compile(
        r'^(?:dale|s[ií]|claro|obvio|por supuesto|de una|exacto|perfecto|listo|ok|okey|bueno|vamo|100\s*%)',
        re.IGNORECASE,
    ),
    "laugh": re.compile(r'^[jJhH][aAeE][jJhH]?[aAeE]*(?:[jJhH][aAeE])*[!\s]*$'),
    "encouragement": re.compile(
        r'(?:vamos|vas a poder|vas bien|metele|dale que|éxitos|mucha suerte|tú puedes|vos pod[eé]s|ánimo|fuerza)',
        re.IGNORECASE,
    ),
    "emoji_only": re.compile(
        r'^[\U0001F600-\U0001FAFF\U00002600-\U000027BF\U0000FE0F\s]+$',
        re.UNICODE,
    ),
    "reaction": re.compile(
        r'^(?:wow|ohh?|aahh?|uff|uy|ah)[!.\s]*$',
        re.IGNORECASE,
    ),
    # ── New categories (Bug 12) ──
    "sales_soft": re.compile(
        r'(?:taller|sesi[oó]n|breathwork|coaching|mentor[ií]a|retiro|programa|formaci[oó]n|inscrib|apunt|precio|costo|oferta|reserv[aá]|plaza|cupo)',
        re.IGNORECASE,
    ),
    "emotional": re.compile(
        r'(?:fuerza|valiente|proceso|sanar|sanaci[oó]n|sentir|emoci[oó]n|coraz[oó]n|llorar|transformaci[oó]n|vulnerab|te (?:acompaño|abrazo|quiero|mando))',
        re.IGNORECASE,
    ),
    "scheduling": re.compile(
        r'(?:(?:a las|para el)\s+\d|(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)|semana que viene|pr[oó]xim[oa]\s+(?:semana|lunes|martes)|esta semana|ma[ñn]ana (?:a las|por|de)|(?:\d{1,2}[:.]\d{2})|(?:\d{1,2}\s*(?:hs?|horas?)))',
        re.IGNORECASE,
    ),
    "content_validation": re.compile(
        r'(?:buen contenido|te felicito|inspirad|incre[ií]ble (?:post|video|contenido)|buen post|gran contenido|me encant[oó] (?:tu|el|lo))',
        re.IGNORECASE,
    ),
}

# Start-anchored categories (use .match() instead of .search())
_START_ANCHORED = {"greeting", "confirmation", "laugh", "emoji_only", "reaction"}

# Pattern matching order — more specific first
_MATCH_ORDER = [
    "laugh", "emoji_only", "greeting", "farewell", "gratitude",
    "confirmation", "celebration", "reaction", "encouragement",
    "sales_soft", "emotional", "scheduling", "content_validation",
]

# Category metadata for risk and mode assignment
_CAT_METADATA = {
    "greeting": {"risk": "low", "mode": "AUTO"},
    "farewell": {"risk": "low", "mode": "AUTO"},
    "gratitude": {"risk": "low", "mode": "AUTO"},
    "celebration": {"risk": "low", "mode": "AUTO"},
    "confirmation": {"risk": "low", "mode": "AUTO"},
    "laugh": {"risk": "low", "mode": "AUTO"},
    "encouragement": {"risk": "medium", "mode": "DRAFT"},
    "emoji_only": {"risk": "low", "mode": "AUTO"},
    "reaction": {"risk": "low", "mode": "AUTO"},
    "sales_soft": {"risk": "high", "mode": "DRAFT"},
    "reconnect": {"risk": "medium", "mode": "DRAFT"},
    "emotional": {"risk": "high", "mode": "MANUAL"},
    "scheduling": {"risk": "high", "mode": "MANUAL"},
    "content_validation": {"risk": "medium", "mode": "DRAFT"},
    "expand_reaction": {"risk": "low", "mode": "AUTO"},
}

# ── Reconnect gap threshold ─────────────────────────────────────────
_RECONNECT_GAP = timedelta(hours=48)


def _collect_lead_names(conversations: list[CleanedConversation]) -> set[str]:
    """
    Collect ALL lead name variants for parametrization (Bug 13).

    Sources:
    1. Parts of full_name (>2 chars, starts with uppercase)
    2. Names extracted from greeting patterns ("Hola Mire!" → "Mire")
    """
    names: set[str] = set()

    for conv in conversations:
        # From full_name
        if conv.full_name:
            for part in conv.full_name.split():
                cleaned = part.strip(".,!?¿¡()@#")
                # Bug 15: min 4 chars + skip protected words
                if len(cleaned) >= 4 and cleaned[0].isupper() and cleaned.lower() not in PROTECTED_WORDS:
                    names.add(cleaned)

        # From greeting patterns — extract the name after "Hola/Hey/Buenos días"
        for msg in conv.messages:
            if msg.origin != MessageOrigin.CREATOR_REAL or not msg.content:
                continue
            content = msg.content.strip()
            # "Hola Mire!" → "Mire", "Hola Nati! Como estas?" → "Nati"
            m = re.match(
                r'^(?:hola|hey|buenas?|buenos?\s*d[ií]as?)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]{2,})',
                content,
                re.IGNORECASE,
            )
            if m:
                candidate = m.group(1)
                # Bug 15: min 4 chars + skip protected words
                if len(candidate) >= 4 and candidate.lower() not in PROTECTED_WORDS:
                    names.add(candidate)

    logger.info("Collected %d lead names for parametrization: %s", len(names), names)
    return names


def _parametrize_template(text: str, lead_names: set[str]) -> str:
    """Replace actual lead names with {nombre} in a template (Bug 13).

    Uses word boundary matching to avoid replacing substrings
    (e.g. "valentía" should NOT become "valen{nombre}").
    """
    result = text
    for name in sorted(lead_names, key=len, reverse=True):  # Longest first
        # Bug 15: skip protected words
        if name.lower() in PROTECTED_WORDS:
            continue
        # Word boundary match — name must be a standalone word
        pattern = re.compile(r'\b' + re.escape(name) + r'\b')
        if pattern.search(result):
            result = pattern.sub("{nombre}", result, count=1)
            break
    return result


def _extract_copilot_phrases(conversations: list[CleanedConversation]) -> list[str]:
    """
    Extract common phrase patterns from copilot/bot messages.
    These get added to the blacklist so the bot doesn't repeat them.
    """
    copilot_msgs = []
    for conv in conversations:
        for msg in conv.messages:
            if msg.origin == MessageOrigin.COPILOT_AI and msg.content:
                copilot_msgs.append(msg.content.strip())

    if not copilot_msgs:
        return []

    openings: Counter = Counter()
    for msg in copilot_msgs:
        first_sentence = msg.split(".")[0].split("!")[0].split("?")[0].strip()
        if 10 < len(first_sentence) < 80:
            openings[first_sentence.lower()] += 1

    return [phrase for phrase, count in openings.most_common(20) if count >= 2]


def _detect_reconnect_messages(
    conversations: list[CleanedConversation],
) -> set[str]:
    """
    Find messages that are the first creator message after a >48h gap (Bug 12).
    Returns a set of message content strings that should be categorized as 'reconnect'.
    """
    reconnect_texts: set[str] = set()

    for conv in conversations:
        last_msg_time = None
        for msg in conv.messages:
            if last_msg_time and msg.origin == MessageOrigin.CREATOR_REAL and msg.content:
                gap = msg.timestamp - last_msg_time
                if gap >= _RECONNECT_GAP and len(msg.content.strip()) < 80:
                    reconnect_texts.add(msg.content.strip())
            last_msg_time = msg.timestamp

    return reconnect_texts


def _extract_real_templates(
    conversations: list[CleanedConversation],
    writing_style: WritingStyle,
) -> tuple[list[TemplateCategory], list[MultiBubbleTemplate]]:
    """
    Extract template pool from real creator messages.

    Bug 7: Templates from actual data, not LLM.
    Bug 11: Filter metadata from multi-bubble.
    Bug 12: 6 new categories.
    Bug 13: Full name parametrization on ALL templates.
    """
    # Collect all lead names (Bug 13)
    lead_names = _collect_lead_names(conversations)

    # Detect reconnect messages (Bug 12)
    reconnect_texts = _detect_reconnect_messages(conversations)

    # Collect all short creator messages by category
    messages_by_cat: dict[str, Counter] = {cat: Counter() for cat in _MATCH_ORDER}
    messages_by_cat["reconnect"] = Counter()
    messages_by_cat["expand_reaction"] = Counter()

    for conv in conversations:
        for msg in conv.messages:
            if msg.origin != MessageOrigin.CREATOR_REAL or not msg.content:
                continue
            content = msg.content.strip()
            # Bug 14: filter phone numbers; Bug 11: filter metadata
            if len(content) > 80 or _is_metadata_message(content) or _contains_phone_number(content):
                continue

            # Pattern-based categorization FIRST (takes priority)
            matched = False
            for cat_name in _MATCH_ORDER:
                pattern = _CAT_PATTERNS[cat_name]
                if cat_name in _START_ANCHORED:
                    hit = pattern.match(content)
                else:
                    hit = pattern.search(content)
                if hit:
                    # Bug 18: skip sales_soft when creator is buying, not selling
                    if cat_name == "sales_soft" and _CREATOR_BUYING_RE.search(content):
                        continue
                    messages_by_cat[cat_name][content] += 1
                    matched = True
                    break

            if matched:
                continue

            # Reconnect: only if no other category matched (timestamp-based)
            if content in reconnect_texts:
                messages_by_cat["reconnect"][content] += 1
            # Expand reaction: <20 chars uncategorized (Bug 12)
            elif len(content) < 20:
                messages_by_cat["expand_reaction"][content] += 1

    # Build template categories from real data
    categories: list[TemplateCategory] = []
    total_categorized = sum(sum(c.values()) for c in messages_by_cat.values())

    all_cat_names = _MATCH_ORDER + ["reconnect", "expand_reaction"]
    for cat_name in all_cat_names:
        counter = messages_by_cat.get(cat_name)
        if not counter:
            continue

        meta = _CAT_METADATA.get(cat_name, {"risk": "medium", "mode": "DRAFT"})
        cat_total = sum(counter.values())
        freq_pct = round(cat_total / max(total_categorized, 1) * 100, 1)

        templates = []
        for text, count in counter.most_common(10):
            # Parametrize ALL templates (Bug 13 — not just count >= 2)
            parametrized = _parametrize_template(text, lead_names)

            templates.append(TemplateEntry(
                text=parametrized,
                context=f"real message ({count}x observed)",
                observed_count=count,
            ))

        categories.append(TemplateCategory(
            category=cat_name,
            frequency_pct=freq_pct,
            risk_level=meta["risk"],
            mode=meta["mode"],
            templates=templates,
        ))

    # Extract multi-bubble templates — timestamp-based burst detection (Bug 17)
    # A "burst" is consecutive creator messages sent within 60s of each other
    multi_bubble: list[MultiBubbleTemplate] = []

    def _flush_burst(burst: list[str], username: str) -> None:
        if len(burst) >= 2:
            # Skip bursts where all messages are identical (bug: repeated sends)
            if len(set(m.lower().strip() for m in burst)) == 1:
                return
            multi_bubble.append(MultiBubbleTemplate(
                template_id=f"mb_{len(multi_bubble)}",
                intent="multi-bubble response",
                messages=list(burst),
                risk="low",
                mode="AUTO",
                source_leads=[username],
            ))

    for conv in conversations:
        creator_burst: list[str] = []
        prev_time = None
        for msg in conv.messages:
            if msg.origin == MessageOrigin.CREATOR_REAL and msg.content:
                content = msg.content.strip()
                # Skip metadata, phone numbers, and long messages
                if _is_metadata_message(content) or _contains_phone_number(content):
                    continue
                if len(content) > 80:
                    _flush_burst(creator_burst, conv.username)
                    creator_burst = []
                    prev_time = None
                    continue
                # Check timestamp gap — <60s means same burst
                if prev_time and (msg.timestamp - prev_time).total_seconds() <= 60:
                    creator_burst.append(content)
                else:
                    # Gap too large — flush previous burst, start new one
                    _flush_burst(creator_burst, conv.username)
                    creator_burst = [content]
                prev_time = msg.timestamp
            else:
                # Non-creator message — flush burst
                _flush_burst(creator_burst, conv.username)
                creator_burst = []
                prev_time = None
        # Flush final burst in conversation
        _flush_burst(creator_burst, conv.username)

    # Deduplicate multi-bubble templates
    mb_counter: Counter = Counter()
    mb_examples: dict = {}
    for mb in multi_bubble:
        key = tuple(m.lower().rstrip("!.? ") for m in mb.messages)
        mb_counter[key] += 1
        if key not in mb_examples:
            mb_examples[key] = mb

    deduped_mb = []
    for key, count in mb_counter.most_common(20):
        template = mb_examples[key]
        template.template_id = f"mb_{len(deduped_mb)}"
        template.intent = f"multi-bubble ({count}x observed)"
        # Parametrize multi-bubble messages too (Bug 13)
        template.messages = [
            _parametrize_template(m, lead_names) for m in template.messages
        ]
        deduped_mb.append(template)

    return categories, deduped_mb


# ── System prompt generation — 3 parallel LLM calls (Bug 8) ────────

_SP_SHARED_RULES = """REGLAS:
- Sé ESPECÍFICO y CUANTIFICADO. "Sé informal" -> MAL. "Usa tuteo, máximo 40 chars por mensaje, 1 emoji cada 3 mensajes" -> BIEN.
- Incluye ejemplos reales CORRECTO vs INCORRECTO para cada regla clave.
- El prompt debe ser autocontenido (no referenciar documentos externos).
- Escribe en español.
- Tu respuesta DEBE ser DETALLADA. MINIMO 400 palabras para esta seccion.
- Devuelve SOLO el contenido de las secciones pedidas, sin explicaciones adicionales."""

SYSPROMPT_IDENTITY = f"""Eres un experto en diseño de system prompts para LLMs que replican personalidades conversacionales.

Genera estas 2 secciones del system prompt del clon. MINIMO 500 PALABRAS en total.

## 1. IDENTIDAD
Datos duros del creador en primera persona, como si el LLM fuera el creador.
Incluye: nombre completo, profesion, ubicacion, idioma/dialecto, intereses.
EJEMPLO de formato esperado:
"Eres [Nombre Creator], un [profesión] de [ciudad], [país]. Tu objetivo es replicar su personalidad conversacional en DMs con una fidelidad del 80-90%."
Luego: "1.1 Datos duros: [completo]", "Idioma: [idioma y dialecto con detalles específicos]"

## 2. REGLAS DE ESTILO
Instrucciones cuantificadas para el LLM. Para CADA regla incluye CORRECTO vs INCORRECTO:
- **Longitud**: maximo X chars por mensaje (usa P90). CORRECTO: "Dale genial!" INCORRECTO: "Me parece genial lo que me dices, dale vamos para adelante con eso"
- **Fragmentacion**: enviar X burbujas por turno.
- **Emojis**: usar en X% de mensajes, maximo X por mensaje. Top emojis permitidos: [lista]
- **Puntuacion**: !! (frecuencia), ?? (frecuencia), mayusculas enfaticas
- **Risas**: variantes exactas (jaja, jajaja, etc.) con frecuencia
- **Formato**: SIN negritas, SIN asteriscos, SIN bullet points, SIN markdown en DMs
- **Repeticion de caracteres**: usar "daleee", "siii", "hermosoooo" (con frecuencias)

{_SP_SHARED_RULES}"""

SYSPROMPT_TONE = f"""Eres un experto en diseño de system prompts para LLMs que replican personalidades conversacionales.

Genera esta seccion del system prompt del clon. MINIMO 400 PALABRAS.

## 3. TONO
Reglas de adaptacion del tono. Para CADA tipo incluye instrucciones especificas y un ejemplo:
- **Con amigos cercanos** → Tono: [detalle]. Longitud: [vs promedio]. Emojis: [vs promedio]. Ejemplo: "[frase real]"
- **Con leads/clientes potenciales** → [mismo formato]
- **Con colaboradores B2B** → [mismo formato]
- **Con fans/seguidores casuales** → [mismo formato]
- **En contexto de venta** → [mismo formato]
- **En contexto emocional** → [mismo formato]

DEBES completar los 6 tipos. Si no hay datos para alguno, usa el tono general como base.

{_SP_SHARED_RULES}"""

SYSPROMPT_VOCAB_SALES = f"""Eres un experto en diseño de system prompts para LLMs que replican personalidades conversacionales.

Genera estas 3 secciones del system prompt del clon. MINIMO 500 PALABRAS en total.

## 4. VOCABULARIO
Diccionario que el LLM debe usar. Para cada categoria incluye las frases reales mas frecuentes:
- **Saludos**: [top 5 con frecuencia]
- **Despedidas**: [top 5 con frecuencia]
- **Confirmaciones**: [top 5: dale, obvio, perfecto, etc.]
- **Risas**: [variantes exactas]
- **Muletillas unicas**: [frases que solo este creador usa]
- **Palabras frecuentes**: hermano, amigo, crack, etc.

## 5. MÉTODO DE VENTA
Como el creador vende por DM (instrucciones para el LLM):
- Estilo: [directo/indirecto, con ejemplo CORRECTO vs INCORRECTO]
- Frases de venta: "[frase real]" — cuando usarla
- Migracion de canal: cuando derivar a email/whatsapp/link
- Señales de compra: [que keywords del lead activan modo venta]

## 6. PROHIBICIONES
Frases que el LLM NUNCA debe generar (blacklist):
- Lista de al menos 10 frases tipicas de bot que no encajan con el estilo del creador
- Para cada frase, breve explicacion de por que no la usa

{_SP_SHARED_RULES}"""


def _build_sysprompt_context(profile: PersonalityProfile) -> str:
    """Build the context string for system prompt generation LLM calls.

    Includes full stats + dictionary directly (not just raw_profile_text)
    to ensure the LLM has enough data even if the profile was truncated.
    """
    ws = profile.writing_style
    d = profile.dictionary
    lines = [
        f"PERSONALITY PROFILE DE: {profile.creator_name}",
        f"Confianza: {profile.confidence}",
        f"Basado en: {profile.messages_analyzed} mensajes / {profile.leads_analyzed} leads / {profile.months_covered} meses",
        "",
        "ESTADISTICAS DE ESCRITURA:",
        f"- Longitud media: {ws.avg_message_length} chars (mediana: {ws.median_message_length})",
        f"- P90: {ws.p90_message_length} chars",
        f"- % cortos (<30 chars): {ws.short_msgs_pct}%",
        f"- % medios (<60 chars): {ws.medium_msgs_pct}%",
        f"- % largos (>100 chars): {ws.long_msgs_pct}%",
        f"- Emojis en {ws.emoji_pct}% de mensajes, media {ws.avg_emojis_per_msg}/msg, max {ws.max_emojis_observed}",
    ]

    # Top emojis inline
    emoji_strs = [e["emoji"] + "(" + str(e["count"]) + "x)" for e in ws.top_emojis[:8]]
    lines.append(f"- Top emojis: {', '.join(emoji_strs)}")

    lines.extend([
        f"- Fragmentacion: {ws.avg_bubbles_per_turn} burbujas/turno ({ws.fragmentation_multi_pct}% multi-burbuja)",
        f"- Idioma: {ws.primary_language} ({ws.dialect})",
    ])

    # Laughs inline
    laugh_strs = [v["variant"] + "(" + str(v["count"]) + "x)" for v in ws.laugh_variants[:5]]
    lines.append(f"- Risas: {', '.join(laugh_strs)}")

    if ws.vowel_repetitions:
        rep_strs = [r["word"] + "(" + str(r["count"]) + "x)" for r in ws.vowel_repetitions[:8]]
        lines.append(f"- Repeticiones: {', '.join(rep_strs)}")

    if ws.punctuation_patterns:
        pp = ws.punctuation_patterns
        lines.append(
            f"- Puntuacion: !!={pp.get('double_exclamation', 0)}, "
            f"??={pp.get('double_question', 0)}, "
            f"CAPS={pp.get('caps_emphasis', 0)} (de {pp.get('total_messages', 0)} msgs)"
        )

    # Include dictionary data directly
    lines.append("\nDICCIONARIO REAL (frases mas frecuentes):")
    for label, entries in [
        ("Saludos", d.greetings),
        ("Despedidas", d.farewells),
        ("Gratitud", d.gratitude),
        ("Confirmacion", d.confirmation),
        ("Validacion", d.validation),
        ("Risa", d.laughter),
        ("Animo", d.encouragement),
    ]:
        if entries:
            top_phrases = ['"' + e["phrase"] + '"(' + str(e["count"]) + "x)" for e in entries[:5]]
            lines.append(f"  {label}: {', '.join(top_phrases)}")

    # Include the LLM profile analysis
    if profile.raw_profile_text:
        lines.append(f"\nANALISIS DE PERSONALIDAD:\n{profile.raw_profile_text[:4000]}")

    return "\n".join(lines)


async def generate_system_prompt(profile: PersonalityProfile) -> str:
    """
    Generate the calibrated system prompt from the personality profile.

    Bug 8 fix: Split into 3 parallel LLM calls to prevent truncation.
    Each generates its section, then Python concatenates.
    """
    context = _build_sysprompt_context(profile)

    logger.info("Launching 3 parallel LLM calls for system prompt (context=%d chars)...", len(context))
    identity_result, tone_result, vocab_result = await asyncio.gather(
        extract_with_llm(
            system_prompt=SYSPROMPT_IDENTITY,
            user_message=context,
            max_tokens=8192,
            temperature=0.4,
        ),
        extract_with_llm(
            system_prompt=SYSPROMPT_TONE,
            user_message=context,
            max_tokens=8192,
            temperature=0.4,
        ),
        extract_with_llm(
            system_prompt=SYSPROMPT_VOCAB_SALES,
            user_message=context,
            max_tokens=8192,
            temperature=0.4,
        ),
    )

    # Build the system prompt header
    ws = profile.writing_style
    header = (
        f"Eres {profile.creator_name}, replicando su personalidad conversacional en DMs "
        f"con una fidelidad del 80-90%.\n\n---"
    )

    parts = [header]
    for label, result in [
        ("IDENTITY+RULES", identity_result),
        ("TONE", tone_result),
        ("VOCAB+SALES+PROHIBITIONS", vocab_result),
    ]:
        if result:
            cleaned = _strip_code_blocks(result)
            # Sanitize: remove repetition loops (e.g. "iiiiii..." from LLM glitch)
            cleaned = re.sub(r'(.)\1{20,}', '', cleaned)
            parts.append(cleaned)
        else:
            logger.warning("System prompt section %s returned empty", label)

    combined = "\n\n".join(parts)
    logger.info(
        "System prompt generated: %d chars (identity=%d, tone=%d, vocab=%d)",
        len(combined),
        len(identity_result or ""),
        len(tone_result or ""),
        len(vocab_result or ""),
    )
    return combined


async def generate_bot_configuration(
    profile: PersonalityProfile,
    conversations: list[CleanedConversation] | None = None,
) -> BotConfiguration:
    """
    Generate the complete bot configuration (Doc D).

    Bug 5: Merges universal blacklist + copilot-extracted phrases + LLM additions.
    Bug 7: Template pool extracted from real creator messages.
    Bug 8: System prompt split into 3 parallel LLM calls.
    Bug 11-13: Template improvements.
    """
    config = BotConfiguration()
    ws = profile.writing_style
    conversations = conversations or []

    # ── System prompt (3 parallel LLM calls — Bug 8) ──
    logger.info("Generating system prompt (3 parallel calls)...")
    config.system_prompt = await generate_system_prompt(profile)

    # ── Negation reducer (post-generation cleanup) ──
    try:
        from core.personality_extraction.negation_reducer import reduce_negations
        config.system_prompt, _nr_kept, _nr_removed = reduce_negations(config.system_prompt)
        if _nr_removed:
            logger.info(
                "[NegRed] system_prompt cleaned: %d negation lines removed, %d kept",
                _nr_removed, _nr_kept,
            )
    except Exception as _e:
        logger.warning("[NegRed] reduce_negations failed (non-critical): %s", _e)

    # ── Blacklist (Bug 5: multi-source merge) ──
    logger.info("Building blacklist...")
    all_blacklist = set(UNIVERSAL_BLACKLIST)

    if conversations:
        copilot_phrases = _extract_copilot_phrases(conversations)
        all_blacklist.update(copilot_phrases)
        logger.info("Added %d copilot-extracted phrases to blacklist", len(copilot_phrases))

    # ── Templates (Bug 7 + 11 + 12 + 13) ──
    logger.info("Extracting templates from real messages...")
    if conversations:
        real_categories, real_multi_bubble = _extract_real_templates(conversations, ws)
        config.template_categories = real_categories
        config.multi_bubble_templates = real_multi_bubble
        logger.info(
            "Extracted %d template categories, %d multi-bubble templates from real messages",
            len(real_categories), len(real_multi_bubble),
        )
    else:
        config.template_categories = []
        config.multi_bubble_templates = []

    # ── LLM supplement (additional blacklist phrases) ──
    logger.info("Generating LLM template pool supplement...")
    llm_pool = await _generate_llm_template_supplement(profile, conversations)
    if llm_pool:
        llm_blacklist = llm_pool.get("blacklist_phrases", [])
        all_blacklist.update(llm_blacklist)
        logger.info("Added %d LLM-suggested blacklist phrases", len(llm_blacklist))

    # Finalize blacklist
    config.blacklist_phrases = sorted(all_blacklist)
    logger.info("Final blacklist: %d phrases", len(config.blacklist_phrases))

    # ── Calibration parameters ──
    config.max_message_length_chars = int(ws.p90_message_length) if ws.p90_message_length else 200
    config.max_emojis_per_message = ws.max_emojis_observed or 3
    config.max_emojis_per_block = min(ws.max_emojis_observed * 2, 5) if ws.max_emojis_observed else 5
    config.enforce_fragmentation = ws.fragmentation_multi_pct > 30
    config.min_bubbles = 1
    config.max_bubbles = max(1, min(int(ws.avg_bubbles_per_turn + 1), 4))

    return config


async def _generate_llm_template_supplement(
    profile: PersonalityProfile,
    conversations: list[CleanedConversation],
) -> Optional[dict]:
    """Call LLM for additional blacklist phrases. Templates already extracted from messages."""
    ws = profile.writing_style

    sample_lines = []
    if conversations:
        msg_counter: Counter = Counter()
        for conv in conversations:
            for msg in conv.messages:
                if msg.origin == MessageOrigin.CREATOR_REAL and msg.content:
                    content = msg.content.strip()
                    if len(content) < 80:
                        msg_counter[content] += 1

        sample_lines.append("MENSAJES MAS FRECUENTES DEL CREADOR (reales):")
        for text, count in msg_counter.most_common(40):
            sample_lines.append(f'  "{text}" — {count}x')

    prompt = """Analiza el perfil del creador y sus mensajes reales.

Devuelve un JSON con:
{
  "blacklist_phrases": ["frases que el creador NUNCA usaria y un bot podria generar"]
}

REGLAS:
- Las blacklist_phrases deben ser frases genéricas de bot que NO aparecen en los mensajes reales.
- Solo incluye frases genéricas de servicio al cliente o formalidades que no encajan con el estilo.
- Devuelve SOLO JSON válido."""

    user_message = (
        f"CREADOR: {profile.creator_name}\n"
        f"Dialecto: {ws.dialect or 'no detectado'}\n"
        f"Longitud media: {ws.avg_message_length} chars\n"
        f"Emojis: {ws.emoji_pct}%\n\n"
        f"PERFIL:\n{(profile.raw_profile_text or '')[:5000]}\n\n"
        + "\n".join(sample_lines)
    )

    return await extract_json_with_llm(
        system_prompt=prompt,
        user_message=user_message,
        max_tokens=2048,
        temperature=0.2,
    )


def generate_doc_d(config: BotConfiguration) -> str:
    """Generate the complete Doc D text."""
    sections = [
        "# DOCUMENTO D: CONFIGURACION TECNICA DEL BOT",
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 4.1 SYSTEM PROMPT DEL CLON",
        "```",
        config.system_prompt,
        "```",
        "",
        "## 4.2 BLACKLIST DE FRASES",
        f"Total frases prohibidas: {len(config.blacklist_phrases)}",
    ]
    for phrase in config.blacklist_phrases:
        sections.append(f'  - "{phrase}"')

    sections.extend([
        "",
        "## 4.3 PARAMETROS DE CALIBRACION",
        f"- max_message_length_chars: {config.max_message_length_chars}",
        f"- max_emojis_per_message: {config.max_emojis_per_message}",
        f"- max_emojis_per_block: {config.max_emojis_per_block}",
        f"- enforce_fragmentation: {config.enforce_fragmentation}",
        f"- min_bubbles: {config.min_bubbles}",
        f"- max_bubbles: {config.max_bubbles}",
        "",
        "## 4.4 TEMPLATE POOL (extraido de mensajes reales)",
        f"Total categorias: {len(config.template_categories)}",
    ])

    for cat in config.template_categories:
        sections.append(f"\n### {cat.category} (freq={cat.frequency_pct}%, risk={cat.risk_level}, mode={cat.mode})")
        for t in cat.templates:
            sections.append(f'  -> "{t.text}" — {t.context} ({t.observed_count}x)')

    if config.multi_bubble_templates:
        sections.extend([
            "",
            "## 4.5 PLANTILLAS MULTI-BURBUJA",
            f"Total: {len(config.multi_bubble_templates)}",
        ])
        for mb in config.multi_bubble_templates:
            sections.append(f"\n### {mb.template_id} ({mb.intent}, risk={mb.risk}, mode={mb.mode})")
            for j, m in enumerate(mb.messages):
                sections.append(f'  Burbuja {j+1}: "{m}"')

    return "\n".join(sections)
