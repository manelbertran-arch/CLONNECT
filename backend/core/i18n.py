"""
Sistema de Internacionalizacion (i18n) para Clonnect Creators.

Permite:
- Detectar idioma del usuario
- Traducir respuestas al idioma preferido
- Mensajes del sistema en multiples idiomas
"""

import os
import re
import logging
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


class Language(Enum):
    """Idiomas soportados"""
    SPANISH = "es"
    ENGLISH = "en"
    PORTUGUESE = "pt"
    CATALAN = "ca"


# Idioma por defecto
DEFAULT_LANGUAGE = Language.SPANISH.value


# Patrones para deteccion de idioma
LANGUAGE_PATTERNS = {
    Language.ENGLISH.value: [
        # Saludos
        r'\b(hello|hi|hey|good morning|good afternoon|good evening)\b',
        # Preguntas
        r'\b(how much|what is|where|when|why|who|which|can you|could you|would you)\b',
        # Palabras comunes
        r'\b(please|thanks|thank you|sorry|yes|no|okay|sure|great|nice|good|bad)\b',
        r'\b(want|need|like|love|have|get|buy|know|think|help)\b',
        r'\b(course|product|price|money|time|work|business)\b',
        # Articulos y preposiciones
        r'\b(the|a|an|is|are|was|were|be|been|being)\b',
        r'\b(i|you|he|she|it|we|they|my|your|his|her|its|our|their)\b',
    ],
    Language.PORTUGUESE.value: [
        # Saludos - patrones unicos portugueses
        r'\b(ola|oi|bom dia|boa tarde|boa noite|tudo bem|tudo bom)\b',
        # Preguntas portuguesas
        r'\b(quanto custa|qual e|onde fica|quando|porque|quem|como voce)\b',
        # Palabras MUY distintivas del portugues (no existen en espanol)
        r'\b(voce|voces|obrigado|obrigada|nao|sim|legal|otimo|muito|tambem)\b',
        r'\b(quero|preciso|gosto|amo|tenho|comprar|saber|pensar|ajudar)\b',
        r'\b(curso|produto|preco|dinheiro|tempo|trabalho|negocio)\b',
        # Verbos y articulos portugueses distintivos
        r'\b(eu|ele|ela|nos|eles|elas|meu|seu|sua|isso|isso mesmo)\b',
        r'\b(esta|estou|estamos|vai|vou|vamos|pode|posso|podemos|fazer)\b',
        # Palabras que NO existen en espanol - peso extra
        r'\b(voce|nao|muito|tambem|fazer|agora|depois|ainda)\b',
    ],
    Language.CATALAN.value: [
        # Saludos
        r'\b(hola|bon dia|bona tarda|bona nit|que tal)\b',
        # Preguntas
        r'\b(quant|quin|quina|on|quan|perque|qui|com)\b',
        # Palabras comunes
        r'\b(gracies|si us plau|perdona|si|no|genial|molt be)\b',
        r'\b(vull|necessito|magrada|estimo|tinc|comprar|saber|pensar|ajudar)\b',
        r'\b(curs|producte|preu|diners|temps|feina|negoci)\b',
        # Articulos y verbos
        r'\b(jo|tu|ell|ella|nosaltres|ells|elles|el|la|els|les)\b',
        r'\b(estic|estas|esta|estem|puc|pots|pot|podem)\b',
    ],
    Language.SPANISH.value: [
        # Saludos
        r'\b(hola|buenos dias|buenas tardes|buenas noches|que tal|como estas)\b',
        # Preguntas
        r'\b(cuanto|cual|donde|cuando|porque|por que|quien|como)\b',
        # Palabras comunes
        r'\b(gracias|por favor|perdona|si|no|genial|muy bien|vale|claro)\b',
        r'\b(quiero|necesito|me gusta|tengo|comprar|saber|pensar|ayudar)\b',
        r'\b(curso|producto|precio|dinero|tiempo|trabajo|negocio)\b',
        # Articulos y verbos
        r'\b(yo|tu|el|ella|nosotros|ellos|ellas|mi|tu|su|nuestro)\b',
        r'\b(estoy|estas|esta|estamos|puedo|puedes|puede|podemos)\b',
    ],
}


# Traducciones de mensajes del sistema
SYSTEM_MESSAGES = {
    # Saludos
    "greeting": {
        "es": "Hola! Que tal? En que puedo ayudarte?",
        "en": "Hi! How are you? How can I help you?",
        "pt": "Ola! Tudo bem? Como posso ajudar?",
        "ca": "Hola! Que tal? En que puc ajudar-te?",
    },
    # Despedidas
    "goodbye": {
        "es": "Hasta pronto! Un abrazo.",
        "en": "See you soon! Take care.",
        "pt": "Ate logo! Um abraco.",
        "ca": "Fins aviat! Una abracada.",
    },
    # Agradecimientos
    "thanks_response": {
        "es": "A ti! Si necesitas algo mas, aqui estoy.",
        "en": "Thank you! If you need anything else, I'm here.",
        "pt": "Obrigado! Se precisar de algo mais, estou aqui.",
        "ca": "A tu! Si necessites alguna cosa mes, aqui estic.",
    },
    # Interes
    "interest_soft": {
        "es": "Me alegra que te interese! Cuentame, que necesitas exactamente?",
        "en": "Glad you're interested! Tell me, what exactly do you need?",
        "pt": "Que bom que voce esta interessado! Me conta, do que voce precisa exatamente?",
        "ca": "M'alegra que t'interessi! Explica'm, que necessites exactament?",
    },
    "interest_strong": {
        "es": "Genial que te interese! Te paso toda la info ahora mismo.",
        "en": "Great that you're interested! I'll send you all the info right now.",
        "pt": "Otimo que voce esta interessado! Vou te passar toda a info agora mesmo.",
        "ca": "Genial que t'interessi! Et passo tota la info ara mateix.",
    },
    # Objeciones
    "objection_price": {
        "es": "Entiendo que es una inversion. Que es lo que mas te preocupa?",
        "en": "I understand it's an investment. What concerns you the most?",
        "pt": "Entendo que e um investimento. O que mais te preocupa?",
        "ca": "Entenc que es una inversio. Que es el que mes et preocupa?",
    },
    "objection_time": {
        "es": "Lo entiendo, el tiempo es oro. Precisamente esto te ayuda a ganar tiempo.",
        "en": "I understand, time is gold. This actually helps you save time.",
        "pt": "Entendo, tempo e dinheiro. Justamente isso te ajuda a ganhar tempo.",
        "ca": "Ho entenc, el temps es or. Precisament aixo t'ajuda a guanyar temps.",
    },
    "objection_doubt": {
        "es": "Normal tener dudas. Que te gustaria saber?",
        "en": "It's normal to have doubts. What would you like to know?",
        "pt": "Normal ter duvidas. O que voce gostaria de saber?",
        "ca": "Normal tenir dubtes. Que t'agradaria saber?",
    },
    "objection_later": {
        "es": "Claro, sin prisa. Aunque te digo que el mejor momento es ahora.",
        "en": "Sure, no rush. Although I'd say the best time is now.",
        "pt": "Claro, sem pressa. Embora eu diga que o melhor momento e agora.",
        "ca": "Clar, sense pressa. Encara que et dic que el millor moment es ara.",
    },
    "objection_works": {
        "es": "Totalmente valido preguntar! Tengo casos de resultados increibles.",
        "en": "Totally valid to ask! I have cases with amazing results.",
        "pt": "Totalmente valido perguntar! Tenho casos com resultados incriveis.",
        "ca": "Totalment valid preguntar! Tinc casos amb resultats increibles.",
    },
    "objection_not_for_me": {
        "es": "Entiendo la duda. Esta disenado para todos los niveles.",
        "en": "I understand the doubt. It's designed for all levels.",
        "pt": "Entendo a duvida. Foi projetado para todos os niveis.",
        "ca": "Entenc el dubte. Esta dissenyat per a tots els nivells.",
    },
    "objection_complicated": {
        "es": "Para nada! Esta pensado para que sea facil y tienes soporte.",
        "en": "Not at all! It's designed to be easy and you have support.",
        "pt": "De jeito nenhum! Foi pensado para ser facil e voce tem suporte.",
        "ca": "De cap manera! Esta pensat per ser facil i tens suport.",
    },
    "objection_already_have": {
        "es": "Genial que ya tengas base! Esto es diferente y da resultados mas rapido.",
        "en": "Great that you have a foundation! This is different and gives faster results.",
        "pt": "Otimo que voce ja tem base! Isso e diferente e da resultados mais rapidos.",
        "ca": "Genial que ja tinguis base! Aixo es diferent i dona resultats mes rapids.",
    },
    # Soporte
    "escalation": {
        "es": "Este tema prefiero atenderlo personalmente. Te respondere lo antes posible.",
        "en": "I prefer to handle this personally. I'll respond as soon as possible.",
        "pt": "Prefiro resolver isso pessoalmente. Vou responder o mais rapido possivel.",
        "ca": "Aquest tema prefereixo atendre'l personalment. Et respondre el mes aviat possible.",
    },
    "support": {
        "es": "Vaya, lamento eso. Cuentame que pasa y lo solucionamos.",
        "en": "Oh, I'm sorry about that. Tell me what's happening and we'll fix it.",
        "pt": "Puxa, sinto muito. Me conta o que esta acontecendo e vamos resolver.",
        "ca": "Vaja, ho sento. Explica'm que passa i ho solucionem.",
    },
    # General
    "default": {
        "es": "Gracias por escribir! En que puedo ayudarte?",
        "en": "Thanks for writing! How can I help you?",
        "pt": "Obrigado por escrever! Como posso ajudar?",
        "ca": "Gracies per escriure! En que puc ajudar-te?",
    },
}


class LanguageDetector:
    """Detecta el idioma de un texto usando patrones y LLM como fallback"""

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: Cliente LLM para fallback (opcional)
        """
        self._llm_client = llm_client

    def detect(self, text: str) -> str:
        """
        Detectar idioma del texto.

        Args:
            text: Texto a analizar

        Returns:
            Codigo de idioma ("es", "en", "pt", "ca")
        """
        if not text or len(text.strip()) < 2:
            return DEFAULT_LANGUAGE

        text_lower = text.lower().strip()

        # Contar matches por idioma
        scores = {}
        for lang, patterns in LANGUAGE_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = re.findall(pattern, text_lower, re.IGNORECASE)
                score += len(matches)
            scores[lang] = score

        # Si hay un claro ganador, devolverlo
        if scores:
            max_score = max(scores.values())
            if max_score > 0:
                # Obtener idioma con mayor score
                best_lang = max(scores, key=scores.get)

                # Solo devolver si hay diferencia clara con el segundo
                sorted_scores = sorted(scores.values(), reverse=True)
                if len(sorted_scores) > 1:
                    second_score = sorted_scores[1]
                    # Si la diferencia es significativa o el score es alto
                    if max_score >= 2 or (max_score > second_score):
                        return best_lang

        # Fallback a espanol si no hay matches claros
        return DEFAULT_LANGUAGE

    async def detect_with_llm(self, text: str) -> str:
        """
        Detectar idioma usando LLM como fallback.

        Args:
            text: Texto a analizar

        Returns:
            Codigo de idioma
        """
        # Primero intentar con patrones
        detected = self.detect(text)

        # Si hay confianza baja y tenemos LLM, usar como fallback
        if self._llm_client and len(text) > 10:
            try:
                prompt = f"""Detect the language of this text. Reply ONLY with one of: es, en, pt, ca

Text: "{text}"

Language code:"""
                response = await self._llm_client.generate(
                    prompt,
                    max_tokens=5,
                    temperature=0
                )
                lang_code = response.strip().lower()[:2]
                if lang_code in ["es", "en", "pt", "ca"]:
                    return lang_code
            except Exception as e:
                logger.error(f"Error detecting language with LLM: {e}")

        return detected


def get_system_message(key: str, language: str = DEFAULT_LANGUAGE) -> str:
    """
    Obtener mensaje del sistema traducido.

    Args:
        key: Clave del mensaje
        language: Codigo de idioma

    Returns:
        Mensaje traducido
    """
    messages = SYSTEM_MESSAGES.get(key, SYSTEM_MESSAGES["default"])
    return messages.get(language, messages.get(DEFAULT_LANGUAGE, ""))


async def translate_response(
    text: str,
    target_lang: str,
    source_lang: str = None,
    llm_client=None
) -> str:
    """
    Traducir respuesta al idioma objetivo usando Groq/LLM.

    Args:
        text: Texto a traducir
        target_lang: Idioma destino ("es", "en", "pt", "ca")
        source_lang: Idioma origen (opcional, se detecta automaticamente)
        llm_client: Cliente LLM a usar

    Returns:
        Texto traducido
    """
    if not text or target_lang == source_lang:
        return text

    # Si no hay cliente LLM, obtener uno
    if llm_client is None:
        try:
            from core.llm import get_llm_client
            llm_client = get_llm_client()
        except Exception as e:
            logger.error(f"Error getting LLM client: {e}")
            return text

    # Mapeo de codigos a nombres
    lang_names = {
        "es": "Spanish",
        "en": "English",
        "pt": "Portuguese",
        "ca": "Catalan"
    }

    target_name = lang_names.get(target_lang, "Spanish")

    prompt = f"""Translate this text to {target_name}. Keep the same tone, style and emojis. Only respond with the translation, nothing else.

Text to translate:
{text}

Translation:"""

    try:
        response = await llm_client.generate(
            prompt,
            max_tokens=len(text) * 2,  # Dar espacio para expansion
            temperature=0.3
        )
        return response.strip()
    except Exception as e:
        logger.error(f"Error translating: {e}")
        return text


class I18nManager:
    """Manager centralizado de internacionalizacion"""

    def __init__(self, llm_client=None):
        self._llm_client = llm_client
        self.detector = LanguageDetector(llm_client)
        self._cache: Dict[str, str] = {}

    def detect_language(self, text: str) -> str:
        """Detectar idioma de texto"""
        return self.detector.detect(text)

    async def detect_language_advanced(self, text: str) -> str:
        """Detectar idioma con LLM como fallback"""
        return await self.detector.detect_with_llm(text)

    def get_message(self, key: str, language: str = DEFAULT_LANGUAGE) -> str:
        """Obtener mensaje del sistema traducido"""
        return get_system_message(key, language)

    async def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: str = None
    ) -> str:
        """Traducir texto"""
        return await translate_response(
            text,
            target_lang,
            source_lang,
            self._llm_client
        )

    async def respond_in_language(
        self,
        response: str,
        user_language: str,
        default_language: str = DEFAULT_LANGUAGE
    ) -> str:
        """
        Asegurar que la respuesta esta en el idioma del usuario.

        Si la respuesta esta en el idioma por defecto y el usuario
        habla otro idioma, traduce la respuesta.
        """
        if user_language == default_language:
            return response

        # Traducir si es necesario
        return await self.translate(response, user_language, default_language)


# Instancia global
_i18n_manager: Optional[I18nManager] = None


def get_i18n_manager(llm_client=None) -> I18nManager:
    """Obtener instancia global del I18nManager"""
    global _i18n_manager
    if _i18n_manager is None:
        _i18n_manager = I18nManager(llm_client)
    return _i18n_manager


# Funciones de conveniencia
def detect_language(text: str) -> str:
    """Detectar idioma de texto"""
    return get_i18n_manager().detect_language(text)


def get_translated_message(key: str, language: str = DEFAULT_LANGUAGE) -> str:
    """Obtener mensaje traducido"""
    return get_system_message(key, language)
