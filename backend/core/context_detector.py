"""
Context Detector Module

Detects contextual signals in messages for LLM prompt injection.
Detectors only INFORM, they do NOT respond. The LLM decides what to do.

Part of refactor/context-injection-v2
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.intent_classifier import Intent, IntentClassifier, classify_intent_simple

logger = logging.getLogger(__name__)


# =============================================================================
# RESULT DATACLASSES
# =============================================================================


@dataclass
class FrustrationResult:
    """Result of frustration detection."""

    is_frustrated: bool = False
    level: str = "none"  # none, mild, moderate, severe
    reason: str = ""
    matched_pattern: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_frustrated": self.is_frustrated,
            "level": self.level,
            "reason": self.reason,
            "matched_pattern": self.matched_pattern,
        }


@dataclass
class SarcasmResult:
    """Result of sarcasm detection."""

    is_sarcastic: bool = False
    confidence: float = 0.0
    matched_pattern: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_sarcastic": self.is_sarcastic,
            "confidence": self.confidence,
            "matched_pattern": self.matched_pattern,
        }


@dataclass
class B2BResult:
    """Result of B2B context detection."""

    is_b2b: bool = False
    company_context: str = ""
    contact_name: str = ""
    collaboration_type: str = ""  # partnership, previous_work, proposal, etc.

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_b2b": self.is_b2b,
            "company_context": self.company_context,
            "contact_name": self.contact_name,
            "collaboration_type": self.collaboration_type,
        }


@dataclass
class DetectedContext:
    """Complete detected context from a message."""

    # Emotional state
    sentiment: str = "neutral"  # frustrated, sarcastic, positive, neutral
    frustration_level: str = "none"  # none, mild, moderate, severe
    frustration_reason: str = ""

    # B2B context
    is_b2b: bool = False
    company_context: str = ""
    b2b_contact_name: str = ""

    # Intent (from existing classifier)
    intent: Intent = Intent.OTHER
    intent_confidence: float = 0.0
    intent_sub: str = ""
    objection_type: str = ""

    # Interest level
    interest_level: str = "none"  # strong, soft, none

    # User name
    user_name: str = ""

    # Flags
    is_first_message: bool = True
    is_meta_message: bool = False  # "ya te dije", "revisa el chat", etc.
    is_correction: bool = False  # "no quise decir eso", etc.

    # Generated alerts for LLM prompt
    alerts: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sentiment": self.sentiment,
            "frustration_level": self.frustration_level,
            "frustration_reason": self.frustration_reason,
            "is_b2b": self.is_b2b,
            "company_context": self.company_context,
            "b2b_contact_name": self.b2b_contact_name,
            "intent": self.intent.value if self.intent else "other",
            "intent_confidence": self.intent_confidence,
            "intent_sub": self.intent_sub,
            "objection_type": self.objection_type,
            "interest_level": self.interest_level,
            "user_name": self.user_name,
            "is_first_message": self.is_first_message,
            "is_meta_message": self.is_meta_message,
            "is_correction": self.is_correction,
            "alerts": self.alerts,
        }

    def build_alerts(self) -> List[str]:
        """Generate list of alerts to inject into LLM prompt."""
        alerts = []

        # Frustration alerts (highest priority)
        if self.frustration_level == "severe":
            alerts.append(
                "⚠️ USUARIO MUY FRUSTRADO - Responde con máxima empatía, "
                "reconoce el problema y ofrece solución clara"
            )
        elif self.frustration_level == "moderate":
            alerts.append(
                "⚠️ Usuario frustrado - Muestra empatía y resuelve directamente"
            )
        elif self.frustration_level == "mild":
            alerts.append("ℹ️ Usuario algo impaciente - Sé conciso y directo")

        # Sarcasm alert
        if self.sentiment == "sarcastic":
            alerts.append(
                "ℹ️ Posible sarcasmo/ironía detectado - No interpretar literalmente"
            )

        # B2B alerts (high priority)
        if self.is_b2b:
            if self.company_context:
                alerts.append(
                    f"🏢 CONTEXTO B2B: {self.company_context} - "
                    "Tratar como colaboración profesional, NO como venta individual"
                )
            else:
                alerts.append(
                    "🏢 Contexto B2B detectado - Tratar como colaboración profesional"
                )

        # Meta-message alerts
        if self.is_meta_message:
            alerts.append(
                "📝 Usuario hace referencia al historial - Revisar mensajes anteriores"
            )

        # Correction alerts
        if self.is_correction:
            alerts.append(
                "🔄 Usuario corrigiendo malentendido - "
                "Reconocer error y ajustar respuesta"
            )

        # Interest level alerts
        if self.interest_level == "strong":
            alerts.append(
                "🔥 Alta intención de compra - Facilitar proceso de pago/reserva"
            )
        elif self.interest_level == "soft":
            alerts.append("💡 Interés detectado - Nutrir y cualificar")

        # Objection alerts
        if self.objection_type:
            objection_messages = {
                "price": "💰 Objeción de precio - Enfatizar valor, ofrecer alternativas",
                "time": "⏰ Objeción de tiempo - Mostrar flexibilidad y facilidad",
                "trust": "🤔 Objeción de confianza - Ofrecer garantías y testimonios",
                "need": "❓ Objeción de necesidad - Conectar con sus problemas específicos",
            }
            if self.objection_type in objection_messages:
                alerts.append(objection_messages[self.objection_type])

        # User name alert
        if self.user_name:
            alerts.append(f"👤 Nombre del usuario: {self.user_name}")

        # First message alert
        if self.is_first_message:
            alerts.append("🆕 Primer mensaje - Dar bienvenida cálida")

        self.alerts = alerts
        return alerts


# =============================================================================
# DETECTION FUNCTIONS
# =============================================================================


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
        (r"\binútil\b", "Insulto directo"),
        (r"\bno sirves\b", "Crítica directa al bot"),
        (r"\beres (un )?bot\b", "Identificación como bot"),
        (r"\bpersona real\b", "Solicita humano"),
        (r"\bhab(lar|la) con (una? )?persona\b", "Quiere hablar con humano"),
        (r"\b(3|tres|cuatro|4|cinco|5|mil) veces\b", "Repetición excesiva"),
        (r"\bya te (lo )?dije (mil veces|muchas veces)\b", "Frustración por repetición"),
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
        (r"\bno entiendes\b", "Falta de comprensión"),
        (r"\bno me escuchas\b", "No se siente escuchado"),
        (r"\bno ayudas\b", "Percibe falta de ayuda"),
        (r"\bqué malo\b", "Crítica de calidad"),
        (r"\bya te (lo )?dije\b", "Repetición"),
        (r"\bte lo (acabo de )?decir\b", "Repetición reciente"),
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
        (r"\botra vez\b", "Repetición solicitada"),
        (r"\bde nuevo\b", "Pide repetición"),
        (r"\bno entend[íi]\b", "No entendió"),
        (r"^\?+$", "Solo signos de interrogación"),
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
    Example: "trabajado" should NOT match "ajá".

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
        (r"\baj[áa]\b", 0.85),  # "ajá" but not "trabajado"
        (r"\bya ya\b", 0.85),
        (r"\bseguro que s[íi]\b", 0.80),
        (r"\bqu[ée] gracioso\b", 0.90),
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
        (r"\bya ver[áa]s\b", 0.55),
        (r"\bs[íi].*(?:claro|seguro).*no\b", 0.65),
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
        r"(?i)(?:^|\s)soy\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)\s+de\s+[A-ZÁÉÍÓÚÑ]",  # "soy Pedro de Company"
        r"(?i)(?:^|\s)les escribe\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)\s+de\s+[A-ZÁÉÍÓÚÑ]",  # "les escribe Silvia de Bamos"
        # Spanish with full name support (first + last name)
        r"(?i)(?:^|\s)me llamo\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)",
        r"(?i)(?:^|\s)mi nombre es\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)",
        r"(?i)(?:^|\s)soy\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)",
        r"(?i)(?:^|\s)(?:hola[,!]?\s*)?soy\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)",
        # B2B pattern: "les escribe [Name]"
        r"(?i)(?:^|\s)les escribe\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)",
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
        "aquí", "aca", "para", "por", "con", "sin", "muy", "más", "less",
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
    "Les escribe Silvia de Bamos, ya habíamos trabajado antes con
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
    company_pattern = r"(?:soy|les escribe|mi nombre es|me llamo)\s+\w+\s+de\s+([A-ZÁÉÍÓÚÑa-záéíóúñ\s]+?)(?:[,.\s]|$)"
    company_match = re.search(company_pattern, message, re.IGNORECASE)
    if company_match:
        company = company_match.group(1).strip()
        # Filter out common non-company words
        non_companies = {"aquí", "acá", "españa", "madrid", "barcelona", "méxico"}
        if company.lower() not in non_companies and len(company) >= 2:
            result.is_b2b = True
            result.company_context = company
            result.collaboration_type = "company_intro"

    # Pattern 2: Previous collaboration
    previous_work_patterns = [
        r"ya hab[íi]amos trabajado",
        r"trabajamos (antes|juntos|anteriormente)",
        r"colabor(amos|ábamos|ación anterior)",
        r"hemos trabajado",
        r"trabajé con (ustedes|vosotros)",
    ]
    for pattern in previous_work_patterns:
        if re.search(pattern, msg_lower):
            result.is_b2b = True
            result.collaboration_type = "previous_work"
            break

    # Pattern 3: B2B keywords
    b2b_keywords = [
        (r"\bcolaboraci[oó]n\b", "collaboration"),
        (r"\bpartnership\b", "partnership"),
        (r"\bpropuesta\b", "proposal"),
        (r"\bempresa\b", "company"),
        (r"\bcorporativo\b", "corporate"),
        (r"\bgrupos?\s+de\s+estudiantes\b", "student_groups"),
        (r"\berasmus\b", "erasmus"),
        (r"\buniversidad\b", "university"),
        (r"\binstituto\b", "institute"),
        (r"\borganizaci[oó]n\b", "organization"),
        (r"\bfundaci[oó]n\b", "foundation"),
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
            "previous_work": "Cliente B2B con historial de colaboración",
            "collaboration": "Solicitud de colaboración profesional",
            "partnership": "Propuesta de partnership",
            "proposal": "Propuesta de negocio",
            "student_groups": "Grupos de estudiantes/educativo",
            "erasmus": "Programa Erasmus/educativo",
            "university": "Institución universitaria",
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
        r"\bcómo pago\b",
        r"\bcomo pago\b",
        r"\bme apunto\b",
        r"\blo quiero\b",
        r"\bdónde compro\b",
        r"\bdonde compro\b",
        r"\bquiero el curso\b",
        r"\bquiero inscribirme\b",
        r"\bme lo llevo\b",
        r"\breservar\b",
        r"\bagendar\b",
        r"\blink de pago\b",
        r"\bcuándo empezamos\b",
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
        r"\bcuéntame más\b",
        r"\bcuentame mas\b",
        r"\bsuena bien\b",
        r"\bsuena interesante\b",
        r"\bquiero saber más\b",
        r"\bmás información\b",
        r"\binfo\b",
        r"\bdetalles\b",
        r"\bqué incluye\b",
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
        r"\bya lo mencion[ée]\b",
        r"\bcomo te dije\b",
        r"\bcomo ya te dije\b",
        r"\bte lo coment[ée]\b",
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
        r"\bmás adelante\b",
        r"\bdespués\b",
        r"\bno es (el )?buen momento\b",
        r"\bm[áa]s tarde\b",
        r"\bla semana que viene\b",
        r"\bel mes que viene\b",
    ]
    for pattern in time_patterns:
        if re.search(pattern, msg_lower):
            return "time"

    # Trust objection
    trust_patterns = [
        r"\bno (me )?f[íi]o\b",
        r"\bno confío\b",
        r"\bno (estoy )?seguro\b",
        r"\blo pienso\b",
        r"\blo voy a pensar\b",
        r"\bno sé si\b",
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
        r"\bpara qué\b.*\b(sirve|necesito)\b",
        r"\bno creo que (me )?sirva\b",
        r"\bno es para m[íi]\b",
    ]
    for pattern in need_patterns:
        if re.search(pattern, msg_lower):
            return "need"

    return ""


# =============================================================================
# MAIN DETECTION FUNCTION
# =============================================================================


def detect_all(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    is_first_message: bool = True,
    use_llm_intent: bool = False,
) -> DetectedContext:
    """
    Run all detectors and return complete context.

    This is the main entry point for context detection.

    Args:
        message: Current user message
        history: Conversation history (optional)
        is_first_message: Whether this is the first message
        use_llm_intent: Whether to use LLM for intent (requires async)

    Returns:
        DetectedContext with all detected signals and alerts
    """
    ctx = DetectedContext()
    ctx.is_first_message = is_first_message

    if not message:
        ctx.build_alerts()
        return ctx

    # 1. Detect frustration
    frustration = detect_frustration(message, history)
    if frustration.is_frustrated:
        ctx.frustration_level = frustration.level
        ctx.frustration_reason = frustration.reason
        ctx.sentiment = "frustrated"

    # 2. Detect sarcasm (only if not already frustrated)
    if ctx.sentiment != "frustrated":
        sarcasm = detect_sarcasm(message)
        if sarcasm.is_sarcastic and sarcasm.confidence >= 0.6:
            ctx.sentiment = "sarcastic"

    # 3. Detect B2B context
    b2b = detect_b2b(message)
    if b2b.is_b2b:
        ctx.is_b2b = True
        ctx.company_context = b2b.company_context
        ctx.b2b_contact_name = b2b.contact_name

        # B2B context should reset frustration detection
        # "ya habíamos trabajado" should NOT be seen as frustrated
        if b2b.collaboration_type == "previous_work":
            ctx.frustration_level = "none"
            ctx.frustration_reason = ""
            if ctx.sentiment == "frustrated":
                ctx.sentiment = "neutral"

    # 4. Extract user name
    name = extract_user_name(message)
    if name:
        ctx.user_name = name
    elif b2b.contact_name:
        ctx.user_name = b2b.contact_name

    # 5. Classify intent (simple, non-LLM)
    intent_str = classify_intent_simple(message)
    intent_map = {
        "interest_strong": Intent.INTEREST_STRONG,
        "purchase": Intent.INTEREST_STRONG,
        "interest_soft": Intent.INTEREST_SOFT,
        "question_product": Intent.QUESTION_PRODUCT,
        "objection": Intent.OBJECTION,
        "greeting": Intent.GREETING,
        "support": Intent.SUPPORT,
        "other": Intent.OTHER,
    }
    ctx.intent = intent_map.get(intent_str, Intent.OTHER)
    ctx.intent_sub = intent_str

    # 6. Detect interest level
    ctx.interest_level = detect_interest_level(message, ctx.intent)

    # 7. Detect meta-message
    ctx.is_meta_message = detect_meta_message(message)

    # 8. Detect correction
    ctx.is_correction = detect_correction(message)

    # 9. Detect objection type
    if ctx.intent == Intent.OBJECTION or intent_str == "objection":
        ctx.objection_type = detect_objection_type(message)

    # 10. Check for positive sentiment (if not already set)
    if ctx.sentiment == "neutral":
        positive_patterns = [
            r"\bgracias\b",
            r"\bgenial\b",
            r"\bperfecto\b",
            r"\bexcelente\b",
            r"\bincre[íi]ble\b",
            r"\bme encanta\b",
        ]
        for pattern in positive_patterns:
            if re.search(pattern, message.lower()):
                ctx.sentiment = "positive"
                break

    # Build alerts
    ctx.build_alerts()

    return ctx


# =============================================================================
# ASYNC VERSION (for LLM intent classification)
# =============================================================================


async def detect_all_async(
    message: str,
    history: Optional[List[Dict[str, Any]]] = None,
    is_first_message: bool = True,
    llm_client=None,
    creator_context: str = "",
) -> DetectedContext:
    """
    Async version of detect_all that can use LLM for intent classification.

    Args:
        message: Current user message
        history: Conversation history (optional)
        is_first_message: Whether this is the first message
        llm_client: Optional LLM client for intent classification
        creator_context: Context about the creator for intent classification

    Returns:
        DetectedContext with all detected signals and alerts
    """
    # Start with sync detection
    ctx = detect_all(message, history, is_first_message, use_llm_intent=False)

    # If LLM client provided, enhance intent classification
    if llm_client:
        try:
            classifier = IntentClassifier(llm_client)
            result = await classifier.classify(
                message,
                creator_context=creator_context,
                conversation_history=history,
                use_llm=True,
            )
            ctx.intent = result.intent
            ctx.intent_confidence = result.confidence
            ctx.intent_sub = result.sub_intent

            # Update interest level based on LLM intent
            if result.intent == Intent.INTEREST_STRONG:
                ctx.interest_level = "strong"
            elif result.intent in (Intent.INTEREST_SOFT, Intent.QUESTION_PRODUCT):
                ctx.interest_level = "soft"

            # Rebuild alerts with new data
            ctx.build_alerts()
        except Exception as e:
            logger.warning(f"LLM intent classification failed: {e}")

    return ctx


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def format_alerts_for_prompt(ctx: DetectedContext) -> str:
    """
    Format detected context alerts for LLM prompt injection.

    Args:
        ctx: DetectedContext with alerts

    Returns:
        Formatted string for prompt injection
    """
    if not ctx.alerts:
        return ""

    lines = ["=== ALERTAS DE CONTEXTO ==="]
    for alert in ctx.alerts:
        lines.append(f"• {alert}")
    lines.append("")

    return "\n".join(lines)


def get_context_summary(ctx: DetectedContext) -> str:
    """
    Get a brief summary of detected context for logging.

    Args:
        ctx: DetectedContext

    Returns:
        Brief summary string
    """
    parts = []

    if ctx.is_b2b:
        parts.append(f"B2B({ctx.company_context[:20]})" if ctx.company_context else "B2B")

    if ctx.frustration_level != "none":
        parts.append(f"Frustration({ctx.frustration_level})")

    if ctx.sentiment == "sarcastic":
        parts.append("Sarcasm")

    if ctx.interest_level != "none":
        parts.append(f"Interest({ctx.interest_level})")

    if ctx.user_name:
        parts.append(f"Name({ctx.user_name})")

    # Only add intent if it's meaningful (not OTHER)
    if ctx.intent and ctx.intent != Intent.OTHER:
        parts.append(f"Intent({ctx.intent.value})")

    return " | ".join(parts) if parts else "neutral"
