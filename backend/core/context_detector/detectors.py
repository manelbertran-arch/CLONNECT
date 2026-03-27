"""
Context Detector — Individual Detection Functions (Universal/Multilingual).

Redesigned: language-extensible via keyword dicts. No hardcoded Spanish.
Removed: frustration (FrustrationDetector v2), sarcasm (LLM handles it).
Kept: B2B, meta-message, correction, objection, user name, interest.

To add a language: add a key to the relevant KEYWORDS dict.
"""

import re
from typing import Any, Dict, List, Optional

from .models import B2BResult

# =============================================================================
# Multilingual keyword dictionaries
# To add a new language: add a key (ISO 639-1 code) with its keyword list.
# "universal" patterns work regardless of language.
# =============================================================================

B2B_KEYWORDS: Dict[str, List[str]] = {
    "universal": [
        r"@\w+\.\w+",          # email pattern
        r"https?://",           # URL
        r"www\.",               # website
    ],
    "es": [
        r"\bcolaboraci[oó]n\b", r"\bempresa\b", r"\bmarca\b",
        r"\bsponsor\b", r"\bpropuesta\b", r"\bcorporativo\b",
        r"\bcontrato\b", r"\bacuerdo\b", r"\bproveedor\b",
    ],
    "ca": [
        r"\bcol·laboraci[oó]\b", r"\bempresa\b", r"\bmarca\b",
        r"\bproposta\b", r"\bcorporatiu\b", r"\bcontracte\b",
        r"\bacord\b",
    ],
    "en": [
        r"\bcollaboration\b", r"\bcompany\b", r"\bbrand\b",
        r"\bpartnership\b", r"\bproposal\b", r"\bcorporate\b",
        r"\bcontract\b", r"\bagreement\b", r"\bsupplier\b",
        r"\bsponsor\b",
    ],
    "it": [
        r"\bcollaborazione\b", r"\bazienda\b", r"\bmarca\b",
        r"\bproposta\b", r"\bcorporativo\b", r"\bcontratto\b",
    ],
    "fr": [
        r"\bcollaboration\b", r"\bentreprise\b", r"\bmarque\b",
        r"\bproposition\b", r"\bcorporatif\b", r"\bcontrat\b",
    ],
    "pt": [
        r"\bcolaboração\b", r"\bempresa\b", r"\bmarca\b",
        r"\bproposta\b", r"\bcorporativo\b", r"\bcontrato\b",
    ],
}

B2B_INTRO_PATTERNS: Dict[str, List[str]] = {
    "es": [
        r"(?:soy|les escribe|mi nombre es|me llamo)\s+\w+\s+de\s+([A-ZÁÉÍÓÚÑa-záéíóúñ\s]+?)(?:[,.\s]|$)",
    ],
    "ca": [
        r"(?:sóc|em dic|el meu nom és)\s+(?:l[ae]\s+)?\w+\s+de\s+([A-ZÀÈÉÍÒÓÚÇa-zàèéíòóúç\s]+?)(?:[,.\s]|$)",
    ],
    "en": [
        r"(?:i'?m|my name is|this is)\s+\w+\s+from\s+([A-Za-z\s]+?)(?:[,.\s]|$)",
    ],
    "it": [
        r"(?:sono|mi chiamo)\s+\w+\s+di\s+([A-ZÀÈÉÌÒÙa-zàèéìòù\s]+?)(?:[,.\s]|$)",
    ],
    "fr": [
        r"(?:je suis|je m'appelle)\s+\w+\s+de\s+([A-ZÀÂÆÇÈÉÊa-zàâæçèéê\s]+?)(?:[,.\s]|$)",
    ],
    "pt": [
        r"(?:sou|meu nome é|me chamo)\s+\w+\s+(?:de|da)\s+([A-ZÃÁÂÉÊÍÓÔÚa-zãáâéêíóôú\s]+?)(?:[,.\s]|$)",
    ],
}

B2B_PREVIOUS_WORK: Dict[str, List[str]] = {
    "es": [r"ya habíamos trabajado", r"trabajamos (?:antes|juntos)", r"hemos trabajado",
           r"colabor(?:amos|ábamos|ación anterior)"],
    "ca": [r"ja havíem treballat", r"vam treballar junts", r"hem col·laborat"],
    "en": [r"we(?:'ve)? worked (?:together|before)", r"previous collaboration",
           r"we collaborated"],
    "it": [r"abbiamo (?:lavorato|collaborato)", r"collaborazione precedente"],
    "fr": [r"nous avons (?:travaillé|collaboré)", r"collaboration précédente"],
    "pt": [r"já trabalhamos", r"colaboração anterior"],
}

META_KEYWORDS: Dict[str, List[str]] = {
    "es": [r"\bya te (?:lo )?dije\b", r"\bte lo (?:acabo de )?decir\b",
           r"\brevisa el chat\b", r"\blee (?:el chat|arriba)\b",
           r"\bmira (?:el chat|arriba)\b", r"\bya lo mencion[ée]\b",
           r"\bcomo (?:ya )?te dije\b", r"\bte lo coment[ée]\b"],
    "ca": [r"\bja t'ho (?:he|vaig) dir\b", r"\bmira (?:el xat|amunt)\b",
           r"\bcom (?:ja )?et vaig dir\b", r"\brellegeix\b"],
    "en": [r"\bi (?:already|just) (?:said|told|asked)\b", r"\bcheck above\b",
           r"\bscroll up\b", r"\bread (?:above|back)\b",
           r"\bas i (?:said|mentioned)\b"],
    "it": [r"\bte l'ho già detto\b", r"\brileggi\b", r"\bcome (?:ho|ti ho) detto\b"],
    "fr": [r"\bje (?:te )?l'ai déjà dit\b", r"\brelis\b", r"\bcomme je (?:t'ai )?dit\b"],
    "pt": [r"\bjá te disse\b", r"\breleia\b", r"\bcomo eu disse\b"],
}

CORRECTION_KEYWORDS: Dict[str, List[str]] = {
    "es": [r"\bno (?:te )?he dicho\b", r"\bno quiero comprar\b",
           r"\bme has entendido mal\b", r"\bno es eso\b",
           r"\bno me refiero\b", r"\bno era eso\b", r"\bmalentendido\b",
           r"\bno he pedido\b", r"\bno dije eso\b", r"\bno quise decir\b"],
    "ca": [r"\bno (?:t')?he dit\b", r"\bno és això\b",
           r"\bm'has entès malament\b", r"\bno em refereixo\b",
           r"\bmalentès\b", r"\bno volia dir\b"],
    "en": [r"\bthat'?s not what i (?:said|meant)\b", r"\bi didn'?t say\b",
           r"\bmisunderstanding\b", r"\bi don'?t mean\b",
           r"\bthat'?s not (?:it|right)\b", r"\byou misunderstood\b"],
    "it": [r"\bnon (?:è|ho detto) (?:quello|così)\b", r"\bmalinteso\b",
           r"\bnon intendevo\b"],
    "fr": [r"\bce n'est pas ce que j'ai dit\b", r"\bmalentendu\b",
           r"\bje n'ai pas dit\b"],
    "pt": [r"\bnão (?:é|foi) isso\b", r"\bmal-entendido\b",
           r"\bnão quis dizer\b"],
}

OBJECTION_KEYWORDS: Dict[str, Dict[str, List[str]]] = {
    "price": {
        "es": [r"\bcaro\b", r"\bmuy caro\b", r"\bno puedo pagar\b",
               r"\bno tengo (?:el )?dinero\b", r"\bfuera de (?:mi )?presupuesto\b"],
        "ca": [r"\bcar\b", r"\bmolt car\b", r"\bno puc pagar\b",
               r"\bno tinc (?:els )?diners\b"],
        "en": [r"\bexpensive\b", r"\btoo much\b", r"\bcan'?t afford\b",
               r"\bout of (?:my )?budget\b"],
    },
    "time": {
        "es": [r"\bno tengo tiempo\b", r"\bahora no\b", r"\bmás adelante\b",
               r"\bno es (?:el )?buen momento\b"],
        "ca": [r"\bno tinc temps\b", r"\bara no\b", r"\bmés endavant\b"],
        "en": [r"\bno time\b", r"\bnot now\b", r"\bmaybe later\b",
               r"\bnot (?:a )?good time\b"],
    },
    "trust": {
        "es": [r"\bno (?:me )?fío\b", r"\bno confío\b", r"\blo pienso\b",
               r"\blo voy a pensar\b", r"\bno me convence\b"],
        "ca": [r"\bno m'ho crec\b", r"\bm'ho pensaré\b", r"\bno em convenç\b"],
        "en": [r"\bi'?m not sure\b", r"\blet me think\b", r"\bnot convinced\b"],
    },
    "need": {
        "es": [r"\bno lo necesito\b", r"\bno me hace falta\b",
               r"\bno creo que (?:me )?sirva\b", r"\bno es para mí\b"],
        "ca": [r"\bno ho necessito\b", r"\bno em fa falta\b",
               r"\bno crec que em serveixi\b"],
        "en": [r"\bdon'?t need\b", r"\bnot for me\b", r"\bi'?m fine without\b"],
    },
}

NAME_PATTERNS: Dict[str, List[str]] = {
    "es": [
        r"(?i)(?:^|\s)(?:soy|me llamo|mi nombre es|les escribe)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)",
    ],
    "ca": [
        r"(?i)(?:^|\s)(?:sóc|em dic|el meu nom és)\s+(?:l[ae]\s+)?([A-ZÀÈÉÍÒÓÚÇ][a-zàèéíòóúç]+(?:\s+[A-ZÀÈÉÍÒÓÚÇ][a-zàèéíòóúç]+)?)",
    ],
    "en": [
        r"(?i)(?:^|\s)(?:i'?m|my name is|call me|i am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
    ],
    "it": [
        r"(?i)(?:^|\s)(?:sono|mi chiamo)\s+([A-ZÀÈÉÌÒÙ][a-zàèéìòù]+(?:\s+[A-ZÀÈÉÌÒÙ][a-zàèéìòù]+)?)",
    ],
    "fr": [
        r"(?i)(?:^|\s)(?:je suis|je m'appelle)\s+([A-ZÀÂÆÇÈÉÊ][a-zàâæçèéê]+(?:\s+[A-ZÀÂÆÇÈÉÊ][a-zàâæçèéê]+)?)",
    ],
    "pt": [
        r"(?i)(?:^|\s)(?:sou|meu nome é|me chamo)\s+([A-ZÃÁÂÉÊÍÓÔÚ][a-zãáâéêíóôú]+(?:\s+[A-ZÃÁÂÉÊÍÓÔÚ][a-zãáâéêíóôú]+)?)",
    ],
}

_COMMON_WORDS = {
    "el", "la", "un", "una", "de", "que", "a", "the", "an", "of",
    "interested", "looking", "here", "nuevo", "nueva", "good", "fine",
    "ok", "okay", "bien", "mal", "not", "no", "yes", "si", "tu", "your",
    "aquí", "aca", "para", "por", "con", "sin", "muy", "más", "less",
    "jo", "tu", "ell", "ella", "io", "je", "eu",
    "from", "di", "da", "del", "las", "los", "les", "il",
}

# Words that should be stripped from end of extracted names (prepositions/articles)
_NAME_SUFFIX_STRIP = {"de", "del", "from", "di", "da", "la", "el", "les"}


def _match_any(msg_lower: str, keywords_dict: Dict[str, List[str]]) -> bool:
    """Check if message matches any keyword from any language."""
    for _lang, patterns in keywords_dict.items():
        for pattern in patterns:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                return True
    return False


def _match_which(msg_lower: str, keywords_dict: Dict[str, List[str]]) -> Optional[str]:
    """Return the matched pattern, or None."""
    for _lang, patterns in keywords_dict.items():
        for pattern in patterns:
            if re.search(pattern, msg_lower, re.IGNORECASE):
                return pattern
    return None


# =============================================================================
# Detectors
# =============================================================================


def detect_b2b(message: str) -> B2BResult:
    """Detect B2B/collaboration context. Universal/multilingual."""
    if not message:
        return B2BResult()

    msg_lower = message.lower().strip()
    result = B2BResult()

    # 1. Company intro pattern: "[Name] de/from [Company]"
    for _lang, patterns in B2B_INTRO_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                company = match.group(1).strip()
                non_companies = {"aquí", "acá", "españa", "madrid", "barcelona",
                                 "méxico", "here", "there", "home"}
                if company.lower() not in non_companies and len(company) >= 2:
                    result.is_b2b = True
                    result.company_context = company
                    result.collaboration_type = "company_intro"
                    break
        if result.is_b2b:
            break

    # 2. Previous collaboration
    if not result.is_b2b:
        if _match_any(msg_lower, B2B_PREVIOUS_WORK):
            result.is_b2b = True
            result.collaboration_type = "previous_work"

    # 3. B2B keywords (any language)
    if not result.is_b2b:
        if _match_any(msg_lower, B2B_KEYWORDS):
            result.is_b2b = True
            result.collaboration_type = "keyword"

    # Extract contact name
    if result.is_b2b:
        name = extract_user_name(message)
        if name:
            result.contact_name = name
        if not result.company_context:
            context_map = {
                "previous_work": "Cliente B2B con historial",
                "keyword": "Contexto B2B",
                "company_intro": "Empresa",
            }
            result.company_context = context_map.get(result.collaboration_type, "B2B")

    return result


def extract_user_name(message: str) -> Optional[str]:
    """Extract user name from self-introduction. Universal/multilingual."""
    if not message:
        return None

    for _lang, patterns in NAME_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, message.strip())
            if match:
                name = match.group(1).strip()
                # Strip trailing prepositions/articles (e.g. "María De" → "María")
                words = name.split()
                while len(words) > 1 and words[-1].lower() in _NAME_SUFFIX_STRIP:
                    words.pop()
                name = " ".join(words)
                if name.lower() not in _COMMON_WORDS and len(name) >= 2:
                    return name.title()
    return None


def detect_meta_message(message: str) -> bool:
    """Detect lead referencing earlier messages. Universal/multilingual."""
    if not message:
        return False
    return _match_any(message.lower().strip(), META_KEYWORDS)


def detect_correction(message: str) -> bool:
    """Detect lead correcting a misunderstanding. Universal/multilingual."""
    if not message:
        return False
    return _match_any(message.lower().strip(), CORRECTION_KEYWORDS)


def detect_objection_type(message: str) -> str:
    """Detect objection type. Universal/multilingual.

    Returns: "price", "time", "trust", "need", or "".
    """
    if not message:
        return ""
    msg_lower = message.lower().strip()
    for obj_type, lang_patterns in OBJECTION_KEYWORDS.items():
        if _match_any(msg_lower, lang_patterns):
            return obj_type
    return ""


def detect_interest_level(message: str, intent=None) -> str:
    """Detect interest level. Delegates to intent classifier when available.

    Returns: "strong", "soft", or "none".
    """
    # If intent already classified, reuse it (no duplication)
    if intent is not None:
        intent_val = intent.value if hasattr(intent, "value") else str(intent)
        if intent_val in ("interest_strong", "purchase"):
            return "strong"
        if intent_val in ("interest_soft", "question_product"):
            return "soft"
    return "none"


# Backward compat stubs — these are no longer used in production but
# tests import them. Return empty/no-op results.

def detect_frustration(message: str, history=None):
    """Stub — frustration detection moved to FrustrationDetector v2."""
    from .models import FrustrationResult
    return FrustrationResult()


def detect_sarcasm(message: str):
    """Stub — sarcasm detection removed (LLM handles natively)."""
    from .models import SarcasmResult
    return SarcasmResult()
