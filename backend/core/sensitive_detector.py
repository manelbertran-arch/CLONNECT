"""
Detector de Contenido Sensible v2.0.0 para Clonnect.

Detecta contenido que requiere manejo especial:
- SELF_HARM: Autolesiones, ideación suicida -> Escalado inmediato
- EATING_DISORDER: TCA, conductas alimentarias peligrosas -> Respuesta empática
- MINOR: Menores de edad -> No presionar venta
- PHISHING: Intentos de obtener info personal -> Bloquear
- SPAM: Bots, spam -> No responder
- THREAT: Amenazas -> Escalar

CRÍTICO: Este módulo es de seguridad. Cualquier cambio debe ser revisado.
"""

import re
import logging
from enum import Enum
from typing import Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class SensitiveType(Enum):
    """Tipos de contenido sensible detectado."""
    NONE = "none"
    SELF_HARM = "self_harm"
    EATING_DISORDER = "eating_disorder"
    MINOR = "minor"
    PHISHING = "phishing"
    SPAM = "spam"
    THREAT = "threat"
    ECONOMIC_DISTRESS = "economic_distress"


@dataclass
class SensitiveResult:
    """Resultado de la detección de contenido sensible."""
    type: SensitiveType
    confidence: float  # 0.0 - 1.0
    reason: Optional[str]  # Patrón que matcheó
    action_required: str  # Acción a tomar

    def __bool__(self):
        """Permite usar: if sensitive_result:"""
        return self.type != SensitiveType.NONE


# =============================================================================
# PATRONES DE DETECCIÓN
# =============================================================================

# AUTOLESIÓN / SUICIDIO - PRIORIDAD MÁXIMA
SELF_HARM_PATTERNS = [
    # Español - autolesión directa
    r'\bme\s+(?:hago|corto|lastimo|provoco)\s+da[ñn]o\b',
    r'\bme\s+corto\b',  # "me corto" simple
    r'\bme\s+lastimo\b',  # "me lastimo" simple
    # Ideación suicida
    r'\b(?:quiero\s+(?:morir(?:me)?|desaparecer|acabar\s+con\s+todo))\b',
    r'\b(?:no\s+quiero\s+(?:vivir|seguir|existir))\b',
    r'\b(?:pienso\s+en\s+(?:suicid|matarme|quitarme\s+la\s+vida))\b',
    r'\bsuicid(?:arme|io|a)\b',  # suicidarme, suicidio, suicida
    # Autolesión explícita
    r'\b(?:autolesion(?:es|arme)?|cortarme|hacerme\s+da[ñn]o)\b',
    # Frases directas frecuentes en español
    r'\b(?:me\s+voy\s+a\s+(?:suicidar|matar|hacer\s+da[ñn]o))\b',
    r'\b(?:voy\s+a\s+(?:suicidarme|matarme|quitarme\s+la\s+vida))\b',
    r'\b(?:voy\s+a\s+acabar\s+con\s+todo)\b',
    r'\b(?:quiero\s+(?:quitarme\s+la\s+vida|matarme|acabar\s+con\s+todo))\b',
    # Métodos específicos
    r'\b(?:tomar(?:me)?\s+(?:todas?\s+las?\s+)?(?:pastillas|medicamentos))\b',
    r'\bsobredosis\b',
    r'\b(?:tirarme\s+(?:de|del|por))\b',
    # Español — future (synthetic) tense. BUG-S3 (2026-04-17): existing list
    # only covered "voy a + inf" volitive. Narrow lookaheads on me_cortaré
    # excise the common "me cortaré el pelo/las uñas" false positives;
    # me_haré_daño accepts up to 3 intervening words ("me haré mucho daño")
    # but a negative lookahead excludes "me haré cargo/responsable del daño"
    # (taking responsibility ≠ self-harm).
    r'\bme\s+matar[eé]\b',
    r'\bme\s+cortar[eé]\b(?!\s+(?:el\s+pelo|el\s+cabello|las?\s+u[ñn]as|la\s+barba))',
    r'\bme\s+har[eé]\s+(?!cargo\b|responsable\b)(?:\S+\s+){0,3}da[ñn]o\b',
    r'\bme\s+quitar[eé]\s+la\s+vida\b',
    r'\bacabar[eé]\s+con\s+(?:todo|mi\s+vida)\b',
    # Catalán
    r'\b(?:vull\s+morir)\b',
    r'\b(?:em\s+vull\s+matar)\b',
    r'\b(?:no\s+vull\s+viure)\b',
    r'\b(?:em\s+faig\s+mal)\b',
    r'\b(?:em\s+tallo)\b',  # me corto
    r'\b(?:vull\s+desapar[eè]ixer)\b',
    r'\b(?:vull\s+acabar\s+amb\s+tot)\b',
    r'\b(?:su[ïi]cid(?:ar-me|i))\b',
    # Catalán — future / conditional self-harm. BUG-S3 (2026-04-17):
    # CCEE case 5 input "em faré mal si no em contestes amb sinceritat"
    # bypassed detection because only present-tense "em faig mal" existed.
    # em_tallaré lookahead excludes "em tallaré el pèl/els cabells"
    # (common haircut phrasing that would otherwise fire).
    r'\bem\s+far[eé](?:\s+\S+){0,3}\s+mal\b',
    r'\bem\s+tallar[eé]\b(?!\s+(?:el\s+p[èe]l|el\s+cabell|els\s+cabells|les?\s+ungles|la\s+barba))',
    r'\bem\s+matar[eé]\b',
    r'\bem\s+su[ïi]cidar[eé]\b',
    r'\bacabar[eé]\s+amb\s+(?:la\s+meva\s+vida|tot)\b',
    # English
    r'\b(?:want\s+to\s+(?:die|disappear|end\s+it))\b',
    r'\b(?:self[\s-]?harm|cutting\s+myself)\b',
    r'\b(?:suicid\w*|kill\s+myself)\b',  # BUG-F1 fix: suicid\w* matches suicide/suicidal/suicidio
    r'\b(?:thinking\s+about\s+(?:suicide|killing\s+myself|ending\s+(?:it|my\s+life)))\b',
    r'\b(?:don\'?t\s+want\s+to\s+(?:live|be\s+here)\s+(?:anymore|any\s+more))\b',
    r'\b(?:(?:end|take)\s+my\s+(?:own\s+)?life)\b',
    r'\b(?:harm(?:ing)?\s+myself)\b',
    # English — future forms. BUG-S3 (2026-04-17): "I'll hurt myself" and
    # "I'll cut myself" were not covered (existing only "harm myself" /
    # "cutting myself").
    r'\bhurt\s+myself\b',
    r'\bcut\s+myself\b',
]

# TRASTORNOS DE CONDUCTA ALIMENTARIA
EATING_DISORDER_PATTERNS = [
    # Restricción extrema de calorías
    r'\b(?:como\s+(?:solo|menos\s+de)\s+\d{2,3}\s*calor[ií]as?)\b',
    r'\b(?:\d{2,3}\s*calor[ií]as?\s+al\s+d[ií]a)\b',
    # Ayunos extremos
    r'\b(?:ayuno\s+(?:de\s+)?\d{2}\s*horas?)\b',
    r'\b(?:llevo\s+\d+\s+d[ií]as?\s+sin\s+comer)\b',
    # Pérdida de peso extrema
    r'\b(?:perder\s+\d{2,}\s*kilos?\s+en\s+(?:una?\s+semana|un\s+mes|pocos\s+d[ií]as))\b',
    r'\b(?:adelgazar\s+\d{2,}\s*kilos?\s+r[aá]pido)\b',
    # Conductas purgativas
    r'\b(?:vomit|purg|laxant)\b',
    r'\b(?:me\s+provoco\s+(?:el\s+)?v[oó]mito)\b',
    # Señales de alarma
    r'\b(?:no\s+me\s+importa\s+si\s+es\s+extremo)\b',
    r'\b(?:cualquier\s+cosa\s+para\s+(?:adelgazar|perder\s+peso))\b',
]

# MENORES DE EDAD
MINOR_PATTERNS = [
    r'\b(?:tengo\s+1[0-7]\s*a[ñn]os?)\b',  # 10-17 años
    r'\b(?:soy\s+menor)\b',
    r'\b(?:mis\s+padres\s+(?:me\s+)?(?:lo\s+)?pagar[ií]an?)\b',
    r'\b(?:en\s+el\s+(?:colegio|instituto|secundaria))\b',
    r'\b(?:voy\s+al\s+(?:cole|insti))\b',
    # English (BUG-F3 fix: English minor signals not covered)
    r'\b(?:i\'?m\s+(?:a\s+)?(?:minor|underage))\b',
    r'\b(?:my\s+parents?\s+(?:would\s+)?(?:pay|buy))\b',
    r'\b(?:in\s+(?:high\s+school|middle\s+school|elementary\s+school))\b',
]

# PHISHING / INGENIERÍA SOCIAL
# NOTE: In Instagram/WhatsApp DMs, leads legitimately ask for contact info
# ("dame tu email", "pasa tu número", "tienes WhatsApp?"). These are NOT
# phishing — they're normal lead behavior. Only flag actual social engineering.
PHISHING_PATTERNS = [
    # Suplantación de autoridad
    r'\b(?:soy\s+(?:de\s+la\s+)?polic[ií]a)\b',
    r'\b(?:guardia\s+civil|investigaci[oó]n\s+oficial)\b',
    r'\b(?:requerimiento\s+judicial|orden\s+judicial)\b',
    # Solicitud de datos del CREATOR a terceros (not lead asking for themselves)
    r'\b(?:necesito|dame)\s+(?:sus?|los?)\s+datos\s+personales\b',
    r'\bdatos\s+personales\s+(?:de|del)\s+creador\b',
    r'\b(?:informaci[oó]n\s+(?:personal|privada)\s+(?:de|sobre)\s+(?:el|la)\s+(?:creador[a]?|due[ñn][oa]|propietari[oa]|admin))',
    # Urgencia + amenaza (not just urgency)
    r'\b(?:tendr[aá]s?\s+problemas?\s+si\s+no)\b',
    # Account verification scams
    r'\b(?:verifica(?:r)?\s+(?:tu|su)\s+cuenta)\b',
    r'\b(?:tu\s+cuenta\s+(?:ser[aá]|ha\s+sido)\s+(?:suspendida|bloqueada|eliminada))\b',
    # Credential theft (password/token requests targeting the creator)
    r'\b(?:dame|env[ií]a(?:me)?|pas[ae](?:me)?)\s+(?:tu\s+)?(?:contrase[ñn]a|password|token|credenciales)\b',
]

# SPAM / BOTS
SPAM_PATTERNS = [
    # Perfil/links sospechosos
    r'\b(?:check|mira)\s*(?:out\s+)?(?:my|mi)\s+(?:profile|perfil)\b',
    r'\b(?:click|haz\s+click)\s+(?:here|aqu[ií])\b',
    r'\b(?:bit\.ly|tinyurl|t\.co)/\w+\b',
    # Ofertas de dinero
    r'\b(?:ganar|make|earn)\s+\$?\d+\s*(?:desde\s+casa|working\s+from\s+home|diarios?)\b',
    r'\b(?:\$\d{3,}\s+(?:al\s+d[ií]a|daily|per\s+day))\b',
    # Giveaways falsos
    r'\b(?:free|gratis)\s+(?:iphone|regalo|giveaway|prize)\b',
    r'\b(?:last\s+chance|[úu]ltima\s+oportunidad)\s+(?:to\s+win|para\s+ganar)\b',
    # Contenido adulto
    r'\b(?:hot\s+pics?|sexy\s+(?:pics?|photos?)|onlyfans)\b',
    r'\b(?:dm\s+(?:me\s+)?for\s+(?:exclusive|private)\s+content)\b',
]

# AMENAZAS
THREAT_PATTERNS = [
    r'\b(?:s[eé]\s+d[oó]nde\s+vive)\b',
    r'\b(?:(?:te|le|os)\s+voy\s+a\s+(?:encontrar|buscar|matar))\b',
    r'\b(?:esto\s+no\s+va\s+a\s+quedar\s+as[ií])\b',
    r'\b(?:(?:te|se)\s+va[ns]?\s+a\s+enterar)\b',
    r'\b(?:(?:voy|vamos)\s+a\s+denunciar)\b.{0,80}(?:estafa\w*|robo|fraude)\b',
    r'\b(?:me\s+las\s+vas?\s+a\s+pagar)\b',
]

# SITUACIÓN ECONÓMICA DIFÍCIL (para respuesta empática, no bloqueo)
ECONOMIC_DISTRESS_PATTERNS = [
    r'\b(?:estoy\s+en\s+(?:el\s+)?paro)\b',
    r'\b(?:no\s+tengo\s+trabajo)\b',
    r'\bsituaci[oó]n\s+econ[oó]mica\b.{0,60}(?:dif[ií]cil|complicada|mala)\b',
    r'\b(?:no\s+(?:puedo|tengo\s+(?:para|dinero\s+para))\s+pagar)\b',
    r'\b(?:sin\s+dinero|sin\s+recursos)\b',
]


# =============================================================================
# FUNCIONES DE DETECCIÓN
# =============================================================================

def _check_patterns(message: str, patterns: List[str]) -> Optional[str]:
    """Verifica si el mensaje contiene alguno de los patrones."""
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return pattern
    return None


def detect_sensitive_content(message: str) -> SensitiveResult:
    """
    Detecta contenido sensible en un mensaje.

    Args:
        message: Texto del mensaje del usuario

    Returns:
        SensitiveResult con tipo, confianza, razón y acción requerida

    Prioridad de detección (de mayor a menor):
    1. SELF_HARM - Escalado inmediato
    2. THREAT - Escalado inmediato
    3. PHISHING - Bloquear respuesta
    4. SPAM - No responder
    5. EATING_DISORDER - Respuesta empática
    6. MINOR - No presionar venta
    7. ECONOMIC_DISTRESS - Empatía (no bloquea)
    """
    if not message or not message.strip():
        return SensitiveResult(SensitiveType.NONE, 0.0, None, "none")

    msg = message.lower().strip()

    # 1. AUTOLESIÓN - PRIORIDAD MÁXIMA
    pattern = _check_patterns(msg, SELF_HARM_PATTERNS)
    if pattern:
        logger.critical(f"[SENSITIVE] SELF_HARM detected: pattern='{pattern}'")
        return SensitiveResult(
            type=SensitiveType.SELF_HARM,
            confidence=0.95,
            reason=pattern,
            action_required="escalate_immediate"
        )

    # 2. AMENAZAS
    pattern = _check_patterns(msg, THREAT_PATTERNS)
    if pattern:
        logger.warning(f"[SENSITIVE] THREAT detected: pattern='{pattern}'")
        return SensitiveResult(
            type=SensitiveType.THREAT,
            confidence=0.85,
            reason=pattern,
            action_required="escalate_immediate"
        )

    # 3. PHISHING
    pattern = _check_patterns(msg, PHISHING_PATTERNS)
    if pattern:
        logger.warning(f"[SENSITIVE] PHISHING detected: pattern='{pattern}'")
        return SensitiveResult(
            type=SensitiveType.PHISHING,
            confidence=0.90,
            reason=pattern,
            action_required="block_response"
        )

    # 4. SPAM
    pattern = _check_patterns(msg, SPAM_PATTERNS)
    if pattern:
        logger.info(f"[SENSITIVE] SPAM detected: pattern='{pattern}'")
        return SensitiveResult(
            type=SensitiveType.SPAM,
            confidence=0.90,
            reason=pattern,
            action_required="no_response"
        )

    # 5. TCA (Trastorno de Conducta Alimentaria)
    pattern = _check_patterns(msg, EATING_DISORDER_PATTERNS)
    if pattern:
        logger.warning(f"[SENSITIVE] EATING_DISORDER detected: pattern='{pattern}'")
        return SensitiveResult(
            type=SensitiveType.EATING_DISORDER,
            confidence=0.80,
            reason=pattern,
            action_required="empathetic_response"
        )

    # 6. MENOR DE EDAD
    # Verificación especial: extraer edad y validar (ES + EN)
    age_match = re.search(r'\b(?:tengo|soy\s+de)\s+(\d{1,2})\s*a[ñn]os?\b', msg)
    if not age_match:  # BUG-F4 fix: English age expressions not detected
        age_match = re.search(r'\b(?:i\'?m|i\s+am)\s+(\d{1,2})\s+years?\s+old\b', msg)
    if age_match:
        age = int(age_match.group(1))
        if age < 18:
            logger.info(f"[SENSITIVE] MINOR detected: age={age}")
            return SensitiveResult(
                type=SensitiveType.MINOR,
                confidence=0.95,
                reason=f"age={age}",
                action_required="no_pressure_sale"
            )

    # También verificar otros patrones de menor
    pattern = _check_patterns(msg, MINOR_PATTERNS)
    if pattern and not age_match:  # Solo si no detectamos edad específica
        logger.info(f"[SENSITIVE] MINOR detected: pattern='{pattern}'")
        return SensitiveResult(
            type=SensitiveType.MINOR,
            confidence=0.75,
            reason=pattern,
            action_required="no_pressure_sale"
        )

    # 7. SITUACIÓN ECONÓMICA DIFÍCIL (no bloquea, solo para contexto)
    pattern = _check_patterns(msg, ECONOMIC_DISTRESS_PATTERNS)
    if pattern:
        logger.info(f"[SENSITIVE] ECONOMIC_DISTRESS detected: pattern='{pattern}'")
        return SensitiveResult(
            type=SensitiveType.ECONOMIC_DISTRESS,
            confidence=0.75,
            reason=pattern,
            action_required="empathetic_response"
        )

    # Sin contenido sensible detectado
    return SensitiveResult(SensitiveType.NONE, 0.0, None, "none")


_CATALUNYA_HINT_RE = re.compile(
    r"\b(?:barcelona|catalunya|catalu[ñn]a|bcn)\b", re.IGNORECASE
)


def get_crisis_resources(
    language: str = "es",
    location_hint: Optional[str] = None,
) -> str:
    """Returns crisis hotline resources, region-routed.

    Hotlines verified out-of-band 2026-04-17 (see
    docs/safety/self_harm_guardrail.md for source links):
      - ES nacional: 024 (línea conducta suicida, Ministerio de Sanidad, 24/7)
      - Catalunya: 900 925 555 (Telèfon de Prevenció del Suïcidi Barcelona)
      - UK & ROI: Samaritans 116 123
      - Teléfono de la Esperanza: 717 003 717 (ES, secondary)
      - Cruz Roja Escucha: 900 107 917 (ES, secondary)
      - Emergency: 112 (EU)

    Args:
        language: dialect-resolved language code (``es``, ``ca``, ``en``).
            Unknown codes fall back to Spanish.
        location_hint: free-text location signal (e.g. ``"Barcelona"``).
            When it matches Catalunya the regional hotline is placed first
            even if the user's interface language is Spanish.

    Returns:
        Plain-text message suitable for embedding in a DM response.
    """
    is_catalunya = bool(location_hint and _CATALUNYA_HINT_RE.search(location_hint))

    if language == "ca" or is_catalunya:
        # Regional first, national second, emergencies last.
        return (
            "Si estàs passant per un moment difícil, hi ha persones que et poden ajudar:\n"
            "- Telèfon de Prevenció del Suïcidi (Barcelona): 900 925 555 "
            "(24h, català i castellà)\n"
            "- Línia d'atenció a la conducta suïcida: 024 (24h, tot l'Estat)\n"
            "- Emergències: 112"
        )

    if language == "en":
        return (
            "If you're going through a difficult time, there are people who can help:\n"
            "- Samaritans (UK & ROI, 24/7, free): 116 123\n"
            "- Emergency services: 112 (EU) / 911 (US) / 999 (UK)"
        )

    # Spanish (also used as fallback for unknown language codes).
    return (
        "Si estás pasando por un momento difícil, hay personas que pueden ayudarte:\n"
        "- Línea de atención a la conducta suicida: 024 (24h, Ministerio de Sanidad)\n"
        "- Teléfono de la Esperanza: 717 003 717 (24h)\n"
        "- Cruz Roja Escucha: 900 107 917\n"
        "- Emergencias: 112"
    )


# =============================================================================
# SINGLETON
# =============================================================================

_detector_instance = None


def get_sensitive_detector():
    """Obtiene la instancia singleton del detector."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = SensitiveContentDetector()
    return _detector_instance


class SensitiveContentDetector:
    """
    Wrapper class para el detector de contenido sensible.
    Mantiene estadísticas y permite configuración.
    """

    def __init__(self):
        self.detections_count = {t: 0 for t in SensitiveType}

    def detect(self, message: str) -> SensitiveResult:
        """Detecta contenido sensible y actualiza estadísticas."""
        result = detect_sensitive_content(message)
        self.detections_count[result.type] += 1
        return result

    def get_stats(self) -> dict:
        """Devuelve estadísticas de detecciones."""
        return {t.value: count for t, count in self.detections_count.items()}
