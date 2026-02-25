"""
Context Detector - Individual Detection Functions

Individual detection functions for contextual signals in messages.
Detectors only INFORM, they do NOT respond. The LLM decides what to do.

Part of refactor/context-injection-v2
"""

import re
from typing import Any, Dict, List, Optional

from core.intent_classifier import Intent

from .models import B2BResult, FrustrationResult, SarcasmResult


def detect_frustration(
    message: str, history: Optional[List[Dict[str, Any]]] = None
) -> FrustrationResult:
    """
    Detect user frustration from message and history.

    Patterns migrated from dm_agent.py _detect_meta_message.

    Args:
        message: Current user message
        history: Conversation history (optional)

    Returns:
        FrustrationResult with level and reason
    """
    if not message:
        return FrustrationResult()

    msg_lower = message.lower().strip()

    # Severe frustration patterns
    severe_patterns = [
        (r"\bin\u00fatil\b", "Insulto directo"),
        (r"\bno sirves\b", "Cr\u00edtica directa al bot"),
        (r"\beres (un )?bot\b", "Identificaci\u00f3n como bot"),
        (r"\bpersona real\b", "Solicita humano"),
        (r"\bhab(lar|la) con (una? )?persona\b", "Quiere hablar con humano"),
        (r"\b(3|tres|cuatro|4|cinco|5|mil) veces\b", "Repetici\u00f3n excesiva"),
        (r"\bya te (lo )?dije (mil veces|muchas veces)\b", "Frustraci\u00f3n por repetici\u00f3n"),
    ]

    for pattern, reason in severe_patterns:
        if re.search(pattern, msg_lower):
            return FrustrationResult(
                is_frustrated=True,
                level="severe",
                reason=reason,
                matched_pattern=pattern,
            )

    # Moderate frustration patterns
    moderate_patterns = [
        (r"\bno me entiendes\b", "No se siente comprendido"),
        (r"\bno entiendes\b", "Falta de comprensi\u00f3n"),
        (r"\bno me escuchas\b", "No se siente escuchado"),
        (r"\bno ayudas\b", "Percibe falta de ayuda"),
        (r"\bqu\u00e9 malo\b", "Cr\u00edtica de calidad"),
        (r"\bya te (lo )?dije\b", "Repetici\u00f3n"),
        (r"\bte lo (acabo de )?decir\b", "Repetici\u00f3n reciente"),
        (r"\brevisa el chat\b", "Pide que lea el historial"),
        (r"\blee (el chat|arriba)\b", "Pide que revise mensajes"),
        (r"\bmira (el chat|arriba)\b", "Pide que revise mensajes"),
    ]

    for pattern, reason in moderate_patterns:
        if re.search(pattern, msg_lower):
            return FrustrationResult(
                is_frustrated=True,
                level="moderate",
                reason=reason,
                matched_pattern=pattern,
            )

    # Mild frustration patterns
    mild_patterns = [
        (r"\botra vez\b", "Repetici\u00f3n solicitada"),
        (r"\bde nuevo\b", "Pide repetici\u00f3n"),
        (r"\bno entend[\u00edi]\b", "No entendi\u00f3"),
        (r"^\?+$", "Solo signos de interrogaci\u00f3n"),
        (r"\bpero\s+ya\b", "Impaciencia"),
    ]

    for pattern, reason in mild_patterns:
        if re.search(pattern, msg_lower):
            return FrustrationResult(
                is_frustrated=True,
                level="mild",
                reason=reason,
                matched_pattern=pattern,
            )

    # Check history for repeated questions (indicates frustration)
    if history and len(history) >= 4:
        user_messages = [
            m.get("content", "").lower()
            for m in history
            if m.get("role") == "user"
        ]
        if len(user_messages) >= 2:
            # If user is repeating similar questions
            last_msg = user_messages[-1] if user_messages else ""
            for prev_msg in user_messages[-3:-1]:
                # Simple similarity check
                if _messages_similar(last_msg, prev_msg):
                    return FrustrationResult(
                        is_frustrated=True,
                        level="moderate",
                        reason="Usuario repitiendo preguntas similares",
                        matched_pattern="history_repetition",
                    )

    return FrustrationResult()


def _messages_similar(msg1: str, msg2: str, threshold: float = 0.6) -> bool:
    """Check if two messages are similar (simple word overlap)."""
    if not msg1 or not msg2:
        return False

    words1 = set(msg1.lower().split())
    words2 = set(msg2.lower().split())

    if not words1 or not words2:
        return False

    intersection = words1 & words2
    union = words1 | words2

    return len(intersection) / len(union) >= threshold


def detect_sarcasm(message: str) -> SarcasmResult:
    """
    Detect sarcasm/irony in message.

    IMPORTANT: Uses word boundaries (\\b) to avoid false positives.
    Example: "trabajado" should NOT match "aj\u00e1".

    Patterns migrated from dm_agent.py with proper boundaries.

    Args:
        message: User message

    Returns:
        SarcasmResult with confidence
    """
    if not message:
        return SarcasmResult()

    msg_lower = message.lower().strip()

    # High confidence sarcasm patterns (with word boundaries)
    high_confidence_patterns = [
        (r"\baj[\u00e1a]\b", 0.85),  # "aj\u00e1" but not "trabajado"
        (r"\bya ya\b", 0.85),
        (r"\bseguro que s[\u00edi]\b", 0.80),
        (r"\bqu[\u00e9e] gracioso\b", 0.90),
        (r"\bclaro[,\s]+como si\b", 0.85),
        (r"\bobvio que no\b", 0.85),
    ]

    for pattern, confidence in high_confidence_patterns:
        if re.search(pattern, msg_lower):
            return SarcasmResult(
                is_sarcastic=True,
                confidence=confidence,
                matched_pattern=pattern,
            )

    # Medium confidence patterns
    medium_confidence_patterns = [
        (r"\bcomo si\b", 0.60),
        (r"\bya ver[\u00e1a]s\b", 0.55),
        (r"\bs[\u00edi].*(?:claro|seguro).*no\b", 0.65),
        (r"\bseguro.*(?:vas|puedes|sabes)\b", 0.55),
        (r"\botra vez.*(?:igual|lo mismo)\b", 0.60),
    ]

    for pattern, confidence in medium_confidence_patterns:
        if re.search(pattern, msg_lower):
            return SarcasmResult(
                is_sarcastic=True,
                confidence=confidence,
                matched_pattern=pattern,
            )

    return SarcasmResult()


def extract_user_name(message: str) -> Optional[str]:
    """
    Extract user name from message if they introduce themselves.

    Patterns:
    - "soy [Nombre]"
    - "me llamo [Nombre]"
    - "mi nombre es [Nombre]"
    - "les escribe [Nombre]"  (B2B case)
    - "I'm [Name]" / "my name is [Name]"

    Migrated from dm_agent.py extract_name_from_message.

    Args:
        message: User message

    Returns:
        Extracted name or None
    """
    if not message:
        return None

    text = message.strip()

    # Patterns in Spanish and English (order matters - more specific first)
    # Note: "soy X de [Company]" - we only want X, not "X de"
    patterns = [
        # Spanish - stop before "de [Company]" pattern
        r"(?i)(?:^|\s)soy\s+([A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1][a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+)\s+de\s+[A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1]",  # "soy Pedro de Company"
        r"(?i)(?:^|\s)les escribe\s+([A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1][a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+)\s+de\s+[A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1]",  # "les escribe Silvia de Bamos"
        # Spanish with full name support (first + last name)
        r"(?i)(?:^|\s)me llamo\s+([A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1][a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+(?:\s+[A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1][a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+)?)",
        r"(?i)(?:^|\s)mi nombre es\s+([A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1][a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+(?:\s+[A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1][a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+)?)",
        r"(?i)(?:^|\s)soy\s+([A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1][a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+(?:\s+[A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1][a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+)?)",
        r"(?i)(?:^|\s)(?:hola[,!]?\s*)?soy\s+([A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1][a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+)",
        # B2B pattern: "les escribe [Name]"
        r"(?i)(?:^|\s)les escribe\s+([A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1][a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1]+)",
        # English
        r"(?i)(?:^|\s)(?:i'?m|my name is|call me|i am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"(?i)(?:^|\s)(?:hey[,!]?\s*)?i'?m\s+([A-Z][a-z]+)",
        # Fallback for single word
        r"(?i)(?:^|\s)(?:soy|me llamo|les escribe|mi nombre es)\s+(\w+)",
        r"(?i)(?:^|\s)(?:i'?m|my name is)\s+(\w+)",
    ]

    common_words = {
        "el", "la", "un", "una", "de", "que", "a", "the", "an", "of",
        "interested", "looking", "here", "nuevo", "nueva", "good", "fine",
        "ok", "okay", "bien", "mal", "not", "no", "yes", "si", "tu", "your",
        "aqu\u00ed", "aca", "para", "por", "con", "sin", "muy", "m\u00e1s", "less",
    }

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            if name.lower() not in common_words and len(name) >= 2:
                return name.title()

    return None


def detect_b2b(message: str) -> B2BResult:
    """
    Detect B2B/collaboration context in message.

    NEW detector for cases like Silvia:
    "Les escribe Silvia de Bamos, ya hab\u00edamos trabajado antes con
    grupos de estudiantes Erasmus"

    Args:
        message: User message

    Returns:
        B2BResult with company context
    """
    if not message:
        return B2BResult()

    msg_lower = message.lower().strip()

    result = B2BResult()

    # Pattern 1: "[Name] de [Company]" - extract company
    company_pattern = r"(?:soy|les escribe|mi nombre es|me llamo)\s+\w+\s+de\s+([A-Z\u00c1\u00c9\u00cd\u00d3\u00da\u00d1a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1\s]+?)(?:[,.\s]|$)"
    company_match = re.search(company_pattern, message, re.IGNORECASE)
    if company_match:
        company = company_match.group(1).strip()
        # Filter out common non-company words
        non_companies = {"aqu\u00ed", "ac\u00e1", "espa\u00f1a", "madrid", "barcelona", "m\u00e9xico"}
        if company.lower() not in non_companies and len(company) >= 2:
            result.is_b2b = True
            result.company_context = company
            result.collaboration_type = "company_intro"

    # Pattern 2: Previous collaboration
    previous_work_patterns = [
        r"ya hab[\u00edi]amos trabajado",
        r"trabajamos (antes|juntos|anteriormente)",
        r"colabor(amos|\u00e1bamos|aci\u00f3n anterior)",
        r"hemos trabajado",
        r"trabaj\u00e9 con (ustedes|vosotros)",
    ]
    for pattern in previous_work_patterns:
        if re.search(pattern, msg_lower):
            result.is_b2b = True
            result.collaboration_type = "previous_work"
            break

    # Pattern 3: B2B keywords
    b2b_keywords = [
        (r"\bcolaboraci[o\u00f3]n\b", "collaboration"),
        (r"\bpartnership\b", "partnership"),
        (r"\bpropuesta\b", "proposal"),
        (r"\bempresa\b", "company"),
        (r"\bcorporativo\b", "corporate"),
        (r"\bgrupos?\s+de\s+estudiantes\b", "student_groups"),
        (r"\berasmus\b", "erasmus"),
        (r"\buniversidad\b", "university"),
        (r"\binstituto\b", "institute"),
        (r"\borganizaci[o\u00f3]n\b", "organization"),
        (r"\bfundaci[o\u00f3]n\b", "foundation"),
        (r"\bempresa\b", "business"),
        (r"\bclientes?\s+corporativos?\b", "corporate_clients"),
        (r"\bcontrato\b", "contract"),
        (r"\bacuerdo\b", "agreement"),
        (r"\bproveedor\b", "supplier"),
        (r"\bservicio\s+para\s+empresas\b", "b2b_service"),
    ]

    for pattern, collab_type in b2b_keywords:
        if re.search(pattern, msg_lower):
            result.is_b2b = True
            if not result.collaboration_type:
                result.collaboration_type = collab_type
            break

    # Extract contact name if B2B detected
    if result.is_b2b:
        name = extract_user_name(message)
        if name:
            result.contact_name = name

    # Build company context string
    if result.is_b2b and not result.company_context:
        # Build context from matched type
        context_map = {
            "previous_work": "Cliente B2B con historial de colaboraci\u00f3n",
            "collaboration": "Solicitud de colaboraci\u00f3n profesional",
            "partnership": "Propuesta de partnership",
            "proposal": "Propuesta de negocio",
            "student_groups": "Grupos de estudiantes/educativo",
            "erasmus": "Programa Erasmus/educativo",
            "university": "Instituci\u00f3n universitaria",
            "corporate": "Cliente corporativo",
        }
        result.company_context = context_map.get(
            result.collaboration_type, "Contexto B2B"
        )

    return result


def detect_interest_level(message: str, intent: Optional[Intent] = None) -> str:
    """
    Detect level of purchase interest.

    Uses patterns from intent_classifier.py.

    Args:
        message: User message
        intent: Optional already-classified intent

    Returns:
        "strong", "soft", or "none"
    """
    if not message:
        return "none"

    msg_lower = message.lower().strip()

    # Strong interest keywords (direct purchase intent)
    strong_patterns = [
        r"\bquiero comprar\b",
        r"\bc\u00f3mo pago\b",
        r"\bcomo pago\b",
        r"\bme apunto\b",
        r"\blo quiero\b",
        r"\bd\u00f3nde compro\b",
        r"\bdonde compro\b",
        r"\bquiero el curso\b",
        r"\bquiero inscribirme\b",
        r"\bme lo llevo\b",
        r"\breservar\b",
        r"\bagendar\b",
        r"\blink de pago\b",
        r"\bcu\u00e1ndo empezamos\b",
        r"\bcuando empezamos\b",
        r"\bquiero contratar\b",
    ]

    for pattern in strong_patterns:
        if re.search(pattern, msg_lower):
            return "strong"

    # Also check intent if provided
    if intent in (Intent.INTEREST_STRONG,):
        return "strong"

    # Soft interest keywords
    soft_patterns = [
        r"\bme interesa\b",
        r"\bcu\u00e9ntame m\u00e1s\b",
        r"\bcuentame mas\b",
        r"\bsuena bien\b",
        r"\bsuena interesante\b",
        r"\bquiero saber m\u00e1s\b",
        r"\bm\u00e1s informaci\u00f3n\b",
        r"\binfo\b",
        r"\bdetalles\b",
        r"\bqu\u00e9 incluye\b",
        r"\bque incluye\b",
    ]

    for pattern in soft_patterns:
        if re.search(pattern, msg_lower):
            return "soft"

    # Also check intent if provided
    if intent in (Intent.INTEREST_SOFT, Intent.QUESTION_PRODUCT):
        return "soft"

    return "none"


def detect_meta_message(message: str) -> bool:
    """
    Detect if user is referencing the conversation itself.

    Patterns like "ya te lo dije", "revisa el chat", etc.

    Args:
        message: User message

    Returns:
        True if meta-message detected
    """
    if not message:
        return False

    msg_lower = message.lower().strip()

    meta_patterns = [
        r"\bya te (lo )?dije\b",
        r"\bte lo (acabo de )?decir\b",
        r"\brevisa el chat\b",
        r"\blee (el chat|arriba)\b",
        r"\bmira (el chat|arriba)\b",
        r"\bscroll up\b",
        r"\bya lo mencion[\u00e9e]\b",
        r"\bcomo te dije\b",
        r"\bcomo ya te dije\b",
        r"\bte lo coment[\u00e9e]\b",
    ]

    for pattern in meta_patterns:
        if re.search(pattern, msg_lower):
            return True

    return False


def detect_correction(message: str) -> bool:
    """
    Detect if user is correcting a misunderstanding.

    Args:
        message: User message

    Returns:
        True if correction detected
    """
    if not message:
        return False

    msg_lower = message.lower().strip()

    correction_patterns = [
        r"\bno te he dicho\b",
        r"\bno he dicho\b",
        r"\bno quiero comprar\b",
        r"\bme has entendido mal\b",
        r"\bno es eso\b",
        r"\bno me refiero\b",
        r"\bno era eso\b",
        r"\bmalentendido\b",
        r"\bno he pedido\b",
        r"\byo no dije\b",
        r"\bno dije eso\b",
        r"\bno es lo que dije\b",
        r"\bno quise decir\b",
    ]

    for pattern in correction_patterns:
        if re.search(pattern, msg_lower):
            return True

    return False


def detect_objection_type(message: str) -> str:
    """
    Detect type of objection in message.

    Args:
        message: User message

    Returns:
        Objection type: "price", "time", "trust", "need", or ""
    """
    if not message:
        return ""

    msg_lower = message.lower().strip()

    # Price objection
    price_patterns = [
        r"\bcaro\b",
        r"\bmuy caro\b",
        r"\bdemasiado caro\b",
        r"\bno puedo pagar\b",
        r"\bno tengo (el )?dinero\b",
        r"\bfuera de (mi )?presupuesto\b",
        r"\bprecio\b.*\b(alto|mucho)\b",
    ]
    for pattern in price_patterns:
        if re.search(pattern, msg_lower):
            return "price"

    # Time objection
    time_patterns = [
        r"\bno tengo tiempo\b",
        r"\bahora no\b",
        r"\bm\u00e1s adelante\b",
        r"\bdespu\u00e9s\b",
        r"\bno es (el )?buen momento\b",
        r"\bm[\u00e1a]s tarde\b",
        r"\bla semana que viene\b",
        r"\bel mes que viene\b",
    ]
    for pattern in time_patterns:
        if re.search(pattern, msg_lower):
            return "time"

    # Trust objection
    trust_patterns = [
        r"\bno (me )?f[\u00edi]o\b",
        r"\bno conf\u00edo\b",
        r"\bno (estoy )?seguro\b",
        r"\blo pienso\b",
        r"\blo voy a pensar\b",
        r"\bno s\u00e9 si\b",
        r"\bno me convence\b",
        r"\bdudas\b",
    ]
    for pattern in trust_patterns:
        if re.search(pattern, msg_lower):
            return "trust"

    # Need objection
    need_patterns = [
        r"\bno lo necesito\b",
        r"\bno me hace falta\b",
        r"\bpara qu\u00e9\b.*\b(sirve|necesito)\b",
        r"\bno creo que (me )?sirva\b",
        r"\bno es para m[\u00edi]\b",
    ]
    for pattern in need_patterns:
        if re.search(pattern, msg_lower):
            return "need"

    return ""
