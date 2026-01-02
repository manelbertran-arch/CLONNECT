"""
DMResponderAgent - Agent simplificado para responder DMs
Carga configuración y productos directamente de JSON
Genera respuestas personalizadas usando Groq/LLM
"""

import json
import os
import time
import logging
import random
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from core.llm import get_llm_client
from core.nurturing import get_nurturing_manager, should_schedule_nurturing
from core.i18n import (
    detect_language,
    get_i18n_manager,
    translate_response,
    DEFAULT_LANGUAGE
)
from core.analytics import get_analytics_manager, detect_platform
from core.gdpr import get_gdpr_manager, ConsentType
from core.rate_limiter import get_rate_limiter
from core.notifications import get_notification_service, EscalationNotification
from core.cache import get_response_cache
from core.alerts import get_alert_manager
from core.creator_config import CreatorConfigManager
from core.sales_tracker import get_sales_tracker
from core.guardrails import get_response_guardrail
from core.reasoning import get_self_consistency_validator, get_chain_of_thought_reasoner
from core.metrics import (
    record_message_processed,
    record_llm_error,
    record_escalation,
    record_cache_hit,
    record_cache_miss,
    DM_PROCESSING_TIME
)


# PostgreSQL integration
USE_POSTGRES = bool(os.getenv("DATABASE_URL"))
db_service = None
if USE_POSTGRES:
    try:
        from api.services import db_service
    except ImportError:
        try:
            from api import db_service
        except ImportError:
            USE_POSTGRES = False

logger = logging.getLogger(__name__)


# Configuration: Set to True to require consent before processing
REQUIRE_CONSENT = os.getenv("REQUIRE_GDPR_CONSENT", "false").lower() == "true"


class Intent(Enum):
    """Intenciones posibles del mensaje"""
    GREETING = "greeting"
    INTEREST_SOFT = "interest_soft"
    INTEREST_STRONG = "interest_strong"
    OBJECTION_PRICE = "objection_price"
    OBJECTION_TIME = "objection_time"
    OBJECTION_DOUBT = "objection_doubt"
    OBJECTION_LATER = "objection_later"
    OBJECTION_WORKS = "objection_works"
    OBJECTION_NOT_FOR_ME = "objection_not_for_me"
    OBJECTION_COMPLICATED = "objection_complicated"
    OBJECTION_ALREADY_HAVE = "objection_already_have"
    QUESTION_PRODUCT = "question_product"
    QUESTION_GENERAL = "question_general"
    LEAD_MAGNET = "lead_magnet"
    BOOKING = "booking"  # Quiere agendar una llamada/reunión
    THANKS = "thanks"
    GOODBYE = "goodbye"
    SUPPORT = "support"
    ESCALATION = "escalation"
    OTHER = "other"


# Inicializar intents que no deben cachearse
NON_CACHEABLE_INTENTS = {
    Intent.OBJECTION_PRICE,
    Intent.OBJECTION_TIME,
    Intent.OBJECTION_DOUBT,
    Intent.OBJECTION_LATER,
    Intent.OBJECTION_WORKS,
    Intent.OBJECTION_NOT_FOR_ME,
    Intent.INTEREST_STRONG,  # Conversiones activas
    Intent.ESCALATION,
    Intent.SUPPORT,  # Soporte necesita respuestas personalizadas
    Intent.OTHER,  # Fallback - siempre regenerar para evitar respuestas genéricas
}


def truncate_response(response: str, max_sentences: int = 2) -> str:
    """Trunca respuestas largas a máximo N frases - AGRESIVO"""
    if not response:
        return response

    import re

    # Clean up the response first
    response = response.strip()

    # Split by sentence endings (. ! ? followed by space or end)
    # Also handle cases like "297€." or "30 días."
    sentences = re.split(r'(?<=[.!?])\s+', response)
    sentences = [s.strip() for s in sentences if s.strip()]

    original_count = len(sentences)

    if original_count > max_sentences:
        truncated = ' '.join(sentences[:max_sentences])
        # Ensure it ends with punctuation
        if truncated and truncated[-1] not in '.!?':
            truncated += '.'
        logger.info(f"TRUNCATED response from {original_count} to {max_sentences} sentences")
        return truncated

    return response


def clean_response_placeholders(response: str, payment_links: list) -> str:
    """Reemplaza placeholders de links con links reales y añade link si falta"""
    if not response:
        return response

    import re

    # Get first available payment link
    real_link = ""
    for link in payment_links:
        if link and isinstance(link, str) and link.startswith("http"):
            real_link = link
            break

    logger.info(f"Payment links available: {payment_links}, using: {real_link}")

    # Replace common placeholders
    placeholders = [
        "[LINK_REAL]", "[link de pago]", "[link]", "[LINK]",
        "(link de pago)", "(link)", "[payment link]", "[pago]"
    ]

    for placeholder in placeholders:
        if placeholder in response:
            if real_link:
                response = response.replace(placeholder, real_link)
            else:
                # Remove placeholder if no link available
                response = response.replace(placeholder, "")

    # If response mentions giving a link but no URL present, add it
    link_phrases = ['aquí tienes', 'here you go', 'aquí está', 'here is', 'este enlace', 'this link']
    has_link_phrase = any(phrase in response.lower() for phrase in link_phrases)
    has_url = 'http' in response.lower()

    if has_link_phrase and not has_url and real_link:
        logger.info(f"Response mentions link but has no URL, appending: {real_link}")
        response = f"{response} {real_link}"

    # Clean up empty link patterns like "enlace: ." or "link: ."
    # Remove patterns like "siguiente enlace: ." or "aquí: ." when link was empty
    response = re.sub(r'(enlace|link|aquí|here):\s*\.', '', response, flags=re.IGNORECASE)
    # Remove double spaces
    response = re.sub(r'\s+', ' ', response)
    # Remove orphaned punctuation
    response = re.sub(r'\s+([.!?])', r'\1', response)

    return response.strip()


# === VARIEDAD EN SALUDOS ===
GREETING_VARIANTS = {
    "es": [
        "¡Hola {name}!",
        "¡Hey {name}!",
        "¡Qué tal {name}!",
        "¡Buenas {name}!",
        "¡Hola! 👋",
        "¡Hey! ¿Cómo estás?",
        "{name}! Qué bueno verte por aquí",
        "¡Ey {name}! ¿Qué tal todo?",
    ],
    "en": [
        "Hey {name}!",
        "Hi {name}!",
        "Hello {name}!",
        "What's up {name}!",
        "Hi there! 👋",
        "Hey! How are you?",
    ],
    "pt": [
        "Oi {name}!",
        "Olá {name}!",
        "E aí {name}!",
        "Opa {name}!",
        "Oi! 👋",
        "Hey! Tudo bem?",
    ],
}

# === VARIEDAD EN EMOJIS ===
EMOJI_POOLS = {
    "positive": ["🙌", "💪", "🔥", "✨", "🚀", "👏", "💯", "⚡"],
    "friendly": ["😊", "😄", "🤗", "☺️", "😉", "🙂", "👍"],
    "thinking": ["🤔", "💭", "🧐", "💡"],
    "celebration": ["🎉", "🎊", "🥳", "🏆"],
}

# === KEYWORDS PARA DETECCIÓN DE IDIOMA ROBUSTA ===
LANG_KEYWORDS = {
    "es": ['hola', 'qué', 'cómo', 'tengo', 'quiero', 'puedo', 'gracias', 'precio',
           'caro', 'tiempo', 'buenas', 'vale', 'claro', 'genial', 'estoy', 'soy',
           'necesito', 'dudas', 'funciona', 'cuánto', 'dónde', 'cuándo', 'ahora'],
    "en": ['hello', 'hi', 'how', 'what', 'want', 'can', 'thanks', 'price',
           'expensive', 'time', 'okay', 'sure', 'great', "i'm", "i am", 'need',
           'doubt', 'works', 'much', 'where', 'when', 'now', 'please', 'the'],
    "pt": ['olá', 'oi', 'como', 'quero', 'posso', 'obrigado', 'obrigada', 'preço',
           'caro', 'tempo', 'tudo', 'bem', 'você', 'voce', 'muito', 'também',
           'preciso', 'dúvida', 'funciona', 'quanto', 'onde', 'quando', 'agora'],
}


def detect_language_robust(text: str, current_language: str = None) -> str:
    """
    Detecta idioma del texto de forma robusta.
    Si ya hay un idioma establecido, solo cambia si hay evidencia FUERTE.

    Args:
        text: Texto a analizar
        current_language: Idioma actual del usuario (si existe)

    Returns:
        Código de idioma ("es", "en", "pt")
    """
    if not text or len(text.strip()) < 2:
        return current_language or "es"

    text_lower = text.lower()

    # Contar coincidencias por idioma
    scores = {}
    for lang, keywords in LANG_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text_lower)
        scores[lang] = count

    max_score = max(scores.values()) if scores else 0

    # Si ya hay idioma establecido, necesita evidencia FUERTE para cambiar
    if current_language and current_language in scores:
        current_score = scores.get(current_language, 0)

        # Solo cambiar si:
        # 1. El nuevo idioma tiene al menos 3 coincidencias más
        # 2. Y el score actual es bajo (< 2)
        best_lang = max(scores, key=scores.get)
        if best_lang != current_language:
            diff = scores[best_lang] - current_score
            if diff < 3 or current_score >= 2:
                # No hay suficiente evidencia, mantener idioma actual
                return current_language

    # Detectar nuevo idioma
    if max_score == 0:
        return current_language or "es"

    # Resolver empates favoreciendo español > inglés > portugués
    best_lang = "es"
    best_score = scores.get("es", 0)

    for lang in ["en", "pt"]:
        if scores.get(lang, 0) > best_score:
            best_lang = lang
            best_score = scores[lang]

    return best_lang


def get_random_greeting(language: str, name: str, variant_index: int = 0) -> str:
    """
    Obtiene un saludo variado basado en el idioma y un índice rotativo.

    Args:
        language: Código de idioma
        name: Nombre del usuario
        variant_index: Índice para rotar saludos

    Returns:
        Saludo formateado
    """
    greetings = GREETING_VARIANTS.get(language, GREETING_VARIANTS["es"])
    # Usar índice rotativo para variar
    idx = variant_index % len(greetings)
    greeting = greetings[idx]
    return greeting.format(name=name)


def get_random_emoji(category: str = "positive") -> str:
    """
    Obtiene un emoji aleatorio de una categoría.

    Args:
        category: Categoría de emoji (positive, friendly, thinking, celebration)

    Returns:
        Emoji aleatorio
    """
    pool = EMOJI_POOLS.get(category, EMOJI_POOLS["positive"])
    return random.choice(pool)


def get_first_name(full_name: str) -> str:
    """
    Extrae solo el PRIMER nombre de un nombre completo.

    Args:
        full_name: Nombre completo (ej: "James Hawk")

    Returns:
        Solo el primer nombre (ej: "James")
    """
    if not full_name or not full_name.strip():
        return "amigo"

    # Limpiar y dividir por espacios
    parts = full_name.strip().split()
    first_name = parts[0] if parts else "amigo"

    # Si el primer nombre es muy corto o parece un username, usar completo
    if len(first_name) < 2 or first_name.startswith('@'):
        return full_name.strip()

    return first_name


import re

def extract_name_from_message(message: str) -> Optional[str]:
    """
    Extrae el nombre del usuario si se presenta en el mensaje.

    Detecta patrones como:
    - "soy [nombre]"
    - "me llamo [nombre]"
    - "mi nombre es [nombre]"
    - "I'm [name]"
    - "my name is [name]"
    - "call me [name]"

    Args:
        message: El mensaje del usuario

    Returns:
        El nombre extraído o None si no se detecta
    """
    if not message:
        return None

    # Normalizar mensaje
    text = message.strip()

    # Patrones en español e inglés
    patterns = [
        # Español
        r"(?:^|\s)(?:soy|me llamo|mi nombre es)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)?)",
        r"(?:^|\s)(?:hola[,!]?\s*)?soy\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)",
        # Inglés
        r"(?:^|\s)(?:i'?m|my name is|call me|i am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"(?:^|\s)(?:hey[,!]?\s*)?i'?m\s+([A-Z][a-z]+)",
        # Caso insensitivo para detectar más
        r"(?i)(?:^|\s)(?:soy|me llamo)\s+(\w+)",
        r"(?i)(?:^|\s)(?:i'?m|my name is)\s+(\w+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            # Validar que parece un nombre real (no una palabra común)
            common_words = {'el', 'la', 'un', 'una', 'de', 'que', 'a', 'the', 'an', 'of',
                          'interested', 'looking', 'here', 'nuevo', 'nueva', 'good', 'fine',
                          'ok', 'okay', 'bien', 'mal', 'not', 'no', 'yes', 'si', 'tu', 'your'}
            if name.lower() not in common_words and len(name) >= 2:
                # Capitalizar correctamente
                return name.title()

    return None


# Keywords that indicate DIRECT purchase intent (user wants to pay NOW)
DIRECT_PURCHASE_KEYWORDS = [
    "quiero comprar",
    "como pago",
    "cómo pago",
    "dame el link",
    "me apunto",
    "lo quiero",
    "donde pago",
    "dónde pago",
    "link de pago",
    "quiero el curso",
    "lo compro",
    "donde compro",
    "dónde compro",
    "pasame el link",
    "pásame el link",
    "quiero pagar",
    "como lo compro",
    "cómo lo compro",
    "envíame el link",
    "enviame el link",
    "manda el link",
    "quiero comprarlo",
    "lo voy a comprar",
    "voy a comprarlo",
    # Affirmative responses (after bot asks "¿quieres el link?")
    "sí",
    "si",
    "yes",
    "ok",
    "vale",
    "claro",
    "por supuesto",
    "adelante",
    "proceder",
    "venga",
    "dale",
    "vamos",
    "perfecto",
    "porfa",
    "por favor",
    "ahora",
    "ya",
    # Explicit link requests
    "por aqui",
    "por aquí",
    "aquí",
    "aqui",
    "mandalo",
    "mándalo",
    "envialo",
    "envíalo",
]


def is_direct_purchase_intent(message: str) -> bool:
    """
    Detecta si el mensaje indica intención de compra DIRECTA.

    Cuando el usuario dice explícitamente que quiere comprar/pagar,
    no hay que volver a venderle - solo dar el link.

    Args:
        message: El mensaje del usuario

    Returns:
        True si es compra directa, False si no
    """
    if not message:
        return False

    msg_lower = message.lower()

    # Check direct purchase keywords
    for keyword in DIRECT_PURCHASE_KEYWORDS:
        if keyword in msg_lower:
            return True

    return False


def get_transparency_disclosure(creator_name: str, language: str = "es") -> str:
    """
    Get AI transparency disclosure message for first interaction.

    Args:
        creator_name: Name of the creator
        language: User's preferred language

    Returns:
        Disclosure message string
    """
    disclosures = {
        "es": f"👋 Soy el asistente de IA de {creator_name}. Estoy aquí para ayudarte.",
        "en": f"👋 I'm {creator_name}'s AI assistant. I'm here to help you.",
        "ca": f"👋 Sóc l'assistent d'IA de {creator_name}. Estic aquí per ajudar-te.",
        "pt": f"👋 Sou o assistente de IA de {creator_name}. Estou aqui para ajudá-lo.",
        "fr": f"👋 Je suis l'assistant IA de {creator_name}. Je suis là pour vous aider.",
    }
    return disclosures.get(language, disclosures["es"])


@dataclass
class DMResponse:
    """Respuesta generada por el agent"""
    response_text: str
    intent: Intent
    action_taken: str = ""
    product_mentioned: Optional[str] = None
    follow_up_needed: bool = False
    escalate_to_human: bool = False
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FollowerMemory:
    """Memoria simplificada del seguidor"""
    follower_id: str
    creator_id: str
    username: str = ""
    name: str = ""
    first_contact: str = ""
    last_contact: str = ""
    total_messages: int = 0
    interests: List[str] = field(default_factory=list)
    products_discussed: List[str] = field(default_factory=list)
    objections_raised: List[str] = field(default_factory=list)
    purchase_intent_score: float = 0.0
    is_lead: bool = False
    is_customer: bool = False
    # Pipeline status: new, active, hot, customer
    status: str = "new"
    preferred_language: str = "es"  # Idioma preferido del seguidor
    last_messages: List[Dict] = field(default_factory=list)
    # Campos para control de links y objeciones
    links_sent_count: int = 0  # Contador de links enviados en conversación
    last_link_message_num: int = 0  # Número de mensaje cuando se envió último link
    objections_handled: List[str] = field(default_factory=list)  # Objeciones ya manejadas
    arguments_used: List[str] = field(default_factory=list)  # Argumentos ya usados
    greeting_variant_index: int = 0  # Para variar saludos
    # Campos para naturalidad - evitar repetición
    last_greeting_style: str = ""  # Último estilo de saludo usado
    last_emojis_used: List[str] = field(default_factory=list)  # Últimos emojis usados
    messages_since_name_used: int = 0  # Mensajes desde que se usó el nombre


class MemoryStore:
    """Almacén simplificado de memoria"""

    def __init__(self, storage_path: str = "data/followers"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        self._cache: Dict[str, FollowerMemory] = {}

    def _get_file_path(self, creator_id: str, follower_id: str) -> str:
        creator_dir = os.path.join(self.storage_path, creator_id)
        os.makedirs(creator_dir, exist_ok=True)
        # Sanitize follower_id for filename
        safe_id = follower_id.replace("/", "_").replace("\\", "_")
        return os.path.join(creator_dir, f"{safe_id}.json")

    async def get(self, creator_id: str, follower_id: str) -> Optional[FollowerMemory]:
        cache_key = f"{creator_id}:{follower_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        file_path = self._get_file_path(creator_id, follower_id)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    memory = FollowerMemory(**{k: v for k, v in data.items() if k in FollowerMemory.__dataclass_fields__})
                    self._cache[cache_key] = memory
                    return memory
            except Exception as e:
                logger.error(f"Error loading memory: {e}")
        return None

    async def save(self, memory: FollowerMemory):
        cache_key = f"{memory.creator_id}:{memory.follower_id}"
        self._cache[cache_key] = memory

        file_path = self._get_file_path(memory.creator_id, memory.follower_id)
        try:
            data = {
                "follower_id": memory.follower_id,
                "creator_id": memory.creator_id,
                "username": memory.username,
                "name": memory.name,
                "first_contact": memory.first_contact,
                "last_contact": memory.last_contact,
                "total_messages": memory.total_messages,
                "interests": memory.interests,
                "products_discussed": memory.products_discussed,
                "objections_raised": memory.objections_raised,
                "purchase_intent_score": memory.purchase_intent_score,
                "is_lead": memory.is_lead,
                "is_customer": memory.is_customer,
                "status": memory.status,  # Pipeline status: new, active, hot, customer
                "preferred_language": memory.preferred_language,
                "last_messages": memory.last_messages[-20:],  # Keep last 20
                # Campos para control de links y objeciones
                "links_sent_count": memory.links_sent_count,
                "last_link_message_num": memory.last_link_message_num,
                "objections_handled": memory.objections_handled,
                "arguments_used": memory.arguments_used,
                "greeting_variant_index": memory.greeting_variant_index,
                # Campos para naturalidad
                "last_greeting_style": memory.last_greeting_style,
                "last_emojis_used": memory.last_emojis_used[-5:],  # Últimos 5
                "messages_since_name_used": memory.messages_since_name_used
            }
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving memory: {e}")

    async def get_or_create(
        self,
        creator_id: str,
        follower_id: str,
        name: str = "",
        username: str = ""
    ) -> FollowerMemory:
        memory = await self.get(creator_id, follower_id)
        if memory is None:
            memory = FollowerMemory(
                follower_id=follower_id,
                creator_id=creator_id,
                name=name,
                username=username,
                first_contact=datetime.now().isoformat(),
                last_contact=datetime.now().isoformat()
            )
            await self.save(memory)
            logger.info(f"Created new follower: {follower_id} (name={name}, username={username})")
        return memory


class DMResponderAgent:
    """Agent principal que procesa DMs y genera respuestas personalizadas"""

    async def _save_message_to_db(self, follower_id: str, role: str, content: str, intent: str = None):
        """Save message to PostgreSQL if available"""
        if not USE_POSTGRES or not db_service:
            logger.debug(f"PostgreSQL disabled: USE_POSTGRES={USE_POSTGRES}, db_service={db_service}")
            return
        try:
            lead = await db_service.get_lead_by_platform_id(self.creator_id, follower_id)
            if not lead:
                logger.info(f"Creating new lead for {follower_id}")
                lead = await db_service.create_lead_async(self.creator_id, {"platform_user_id": follower_id, "platform": "telegram" if follower_id.startswith("tg_") else "instagram", "username": follower_id})
            if lead and "id" in lead:
                result = await db_service.save_message(lead["id"], role, content, intent)
                logger.info(f"Message saved to PostgreSQL: lead={lead['id']}, role={role}, result={result}")
            else:
                logger.warning(f"Could not get/create lead for {follower_id}: lead={lead}")
        except Exception as e:
            logger.error(f"PostgreSQL save failed for {follower_id}: {e}", exc_info=True)

    def __init__(self, creator_id: str = "manel"):
        self.creator_id = creator_id
        self.creator_config = self._load_creator_config()
        self.products = self._load_products()
        self.llm = get_llm_client()
        self.memory_store = MemoryStore()
        self.config_manager = CreatorConfigManager()
        self._follower_cache: Dict[str, FollowerMemory] = {}

        logger.info(f"DM Agent initialized for creator: {creator_id}")
        logger.info(f"Creator: {self.creator_config.get('name', 'Unknown')}")
        logger.info(f"Loaded {len(self.products)} products")

    def _load_creator_config(self) -> dict:
        """Cargar configuración del creador desde PostgreSQL (primero) o JSON (fallback)"""
        # Try PostgreSQL first (where Settings page saves)
        if USE_POSTGRES and db_service:
            try:
                creator = db_service.get_creator_by_name(self.creator_id)
                if creator:
                    logger.info(f"Loaded creator config from DB: {creator.get('name')}, tone={creator.get('clone_tone')}")
                    # Map DB fields to config format expected by _build_system_prompt
                    return {
                        "name": creator.get("name", "Asistente"),
                        "clone_name": creator.get("clone_name") or creator.get("name", "Asistente"),
                        "clone_tone": creator.get("clone_tone", "friendly"),
                        "clone_vocabulary": creator.get("clone_vocabulary", ""),
                        "welcome_message": creator.get("welcome_message", ""),
                        "bot_active": creator.get("bot_active", True),
                        "clone_active": creator.get("bot_active", True),
                        # Keep these for compatibility
                        "personality": "amable y profesional",
                        "language": "Español",
                        "greeting_style": "Hola! Que tal?",
                        "emoji_usage": "moderado",
                        "response_length": "conciso, maximo 2-3 frases",
                        "escalation_keywords": ["urgente", "reembolso", "hablar con humano"]
                    }
            except Exception as e:
                logger.warning(f"Failed to load config from PostgreSQL: {e}")

        # Fallback to JSON file
        config_path = Path(f"data/creators/{self.creator_id}_config.json")
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    logger.info(f"Loaded creator config from JSON: {config.get('name')}")
                    return config
            except Exception as e:
                logger.error(f"Error loading creator config from JSON: {e}")

        logger.warning(f"Creator config not found in DB or JSON")
        return self._default_config()

    def _load_products(self) -> list:
        """Cargar productos desde PostgreSQL (primero) o JSON (fallback)"""
        # Try PostgreSQL first
        if USE_POSTGRES and db_service:
            try:
                products = db_service.get_products(self.creator_id)
                if products:
                    logger.info(f"Loaded {len(products)} products from PostgreSQL")
                    return products
            except Exception as e:
                logger.warning(f"Error loading products from DB: {e}")

        # Fallback to JSON
        products_path = Path(f"data/products/{self.creator_id}_products.json")
        if products_path.exists():
            try:
                with open(products_path, 'r', encoding='utf-8') as f:
                    products = json.load(f)
                    # Handle both list and dict with 'products' key
                    if isinstance(products, dict):
                        products = products.get('products', [])
                    logger.info(f"Loaded {len(products)} products from JSON")
                    return products
            except Exception as e:
                logger.error(f"Error loading products from JSON: {e}")

        logger.warning(f"No products found for {self.creator_id}")
        return []

    def _default_config(self) -> dict:
        """Configuración por defecto"""
        return {
            "name": "Asistente",
            "personality": "amable y profesional",
            "tone": "cercano pero profesional",
            "language": "Español",
            "greeting_style": "Hola! Que tal?",
            "emoji_usage": "moderado",
            "response_length": "conciso, maximo 2-3 frases",
            "escalation_keywords": ["urgente", "reembolso", "hablar con humano"]
        }

    def _load_booking_links(self) -> list:
        """Load booking links from database"""
        try:
            from api.database import SessionLocal
            from api.models import BookingLink

            if not SessionLocal:
                logger.warning("SessionLocal not available, cannot load booking links")
                return []

            with SessionLocal() as db:
                links = db.query(BookingLink).filter(
                    BookingLink.creator_id == self.creator_id,
                    BookingLink.is_active == True
                ).all()

                return [
                    {
                        "id": str(link.id),
                        "title": link.title,
                        "description": link.description,
                        "duration_minutes": link.duration_minutes,
                        "platform": link.platform,
                        "url": link.url,
                        "price": getattr(link, 'price', 0) or 0,
                        "meeting_type": link.meeting_type
                    }
                    for link in links
                ]
        except Exception as e:
            logger.error(f"Error loading booking links: {e}")
            return []

    def _get_service_emoji(self, meeting_type: str) -> str:
        """Get emoji for service type"""
        emoji_map = {
            "discovery": "🔍",
            "coaching": "🎯",
            "consultation": "💼",
            "consultoria": "💼",
            "mentoring": "🧠",
            "mentoria": "🧠",
            "strategy": "📊",
        }
        if "qa" in meeting_type.lower() or "q&a" in meeting_type.lower():
            return "❓"
        return emoji_map.get(meeting_type, "📞")

    def _format_booking_response(self, links: list, language: str = "es", platform: str = "instagram") -> dict:
        """
        Format booking links as a friendly message with internal Clonnect URLs.
        Returns dict with 'text' and optionally 'telegram_keyboard' for inline buttons.
        For Telegram, uses URL buttons that open the booking page directly.
        """
        if not links:
            creator_name = self.creator_config.get('name', 'el creador')
            if language == "es":
                text = f"Actualmente no tengo servicios de llamada configurados. Contacta directamente con {creator_name} para agendar."
            else:
                text = f"I don't have any call services set up right now. Contact {creator_name} directly to schedule."
            return {"text": text}

        # Frontend URL for internal booking system
        frontend_url = os.getenv("FRONTEND_URL", "https://clonnect.vercel.app")

        # Build keyboard for Telegram (list of button rows)
        telegram_keyboard = []
        formatted_links = []

        for link in links:
            service_id = link.get('id', '')
            duration = link.get('duration_minutes', 30)
            price = link.get('price', 0)
            title = link.get('title', 'Llamada')
            meeting_type = link.get('meeting_type', 'call')

            emoji = self._get_service_emoji(meeting_type)

            # Price text (shorter format)
            if price == 0:
                price_text = "Gratis" if language == "es" else "Free"
            else:
                price_text = f"{price}€"

            # Generate internal Clonnect booking URL
            booking_url = f"{frontend_url}/book/{self.creator_id}/{service_id}"

            # Shorten title if too long (Telegram buttons have limited width)
            short_title = title[:15] + "..." if len(title) > 18 else title

            # For Telegram: create URL button with shortened text
            # Format: "🎯 Coaching (60m) Gratis" - much shorter to avoid truncation
            button_text = f"{emoji} {short_title} ({duration}m) {price_text}"
            telegram_keyboard.append({
                "text": button_text,
                "url": booking_url  # Direct URL to booking page
            })

            # For Instagram/other: text with URL
            formatted_links.append(f"{emoji} {title} - {duration} min - {price_text}\n   ➜ {booking_url}")

        # Build response based on platform
        if platform == "telegram":
            # Telegram gets short intro + inline buttons
            if language == "es":
                text = "📅 ¡Reserva tu llamada conmigo!\n\nElige el servicio:"
            else:
                text = "📅 Book a call with me!\n\nChoose a service:"

            return {
                "text": text,
                "telegram_keyboard": telegram_keyboard
            }
        else:
            # Instagram/other gets full text with URLs
            if language == "es":
                intro = "¡Genial! Estos son mis servicios disponibles:\n\n"
                outro = "\n\nHaz clic en el que te interese para elegir tu horario."
            else:
                intro = "Great! Here are my available services:\n\n"
                outro = "\n\nClick on the one you're interested in to choose your time slot."

            return {"text": intro + "\n\n".join(formatted_links) + outro}

    def _classify_intent(self, message: str) -> tuple:
        """Clasificar intención del mensaje por keywords"""
        msg = message.lower()

        # Escalación (prioridad máxima)
        # Patrones por defecto para detectar solicitud de humano
        default_escalation = [
            "hablar con persona", "hablar con humano", "persona real",
            "agente humano", "agente real", "quiero hablar con alguien",
            "pasame con", "pásame con", "hablar con un humano",
            "contactar persona", "necesito hablar con", "prefiero hablar con",
            "quiero un humano", "eres un bot", "eres robot", "no eres real",
            "hablar con soporte", "hablar con atención", "operador",
            "quiero hablar con una persona", "conectame con", "conéctame con"
        ]
        escalation_kw = self.creator_config.get('escalation_keywords', []) + default_escalation
        if any(kw.lower() in msg for kw in escalation_kw):
            return Intent.ESCALATION, 0.95

        # === INTERÉS SE DETECTA PRIMERO (prioridad sobre saludos) ===
        # Esto permite que "Hola, me interesa el curso" se clasifique como INTEREST, no GREETING

        # Interés fuerte (quiere comprar)
        if any(w in msg for w in ['comprar', 'quiero comprar', 'adquirir', 'donde compro', 'link de pago', 'pagar', 'apuntarme', 'me apunto']):
            return Intent.INTEREST_STRONG, 0.90

        # Interés soft - ANTES de saludos para que "hola, me interesa" sea INTEREST_SOFT
        if any(w in msg for w in ['interesa', 'cuentame', 'cuéntame', 'info', 'información', 'saber mas', 'saber más', 'como funciona', 'cómo funciona']):
            return Intent.INTEREST_SOFT, 0.85

        # Booking / Agendar llamada - ANTES de saludos para que "hola, quiero agendar" sea BOOKING
        if any(w in msg for w in [
            'agendar', 'reservar', 'llamada', 'reunion', 'reunión', 'cita',
            'agenda', 'book', 'booking', 'appointment', 'schedule',
            'videollamada', 'zoom', 'meet', 'calendly', 'hablar contigo',
            'cuando podemos hablar', 'podemos hablar', 'disponibilidad',
            'sesion', 'sesión', 'consulta', 'consultoria', 'consultoría',
            'coaching', 'mentoria', 'mentoría', 'discovery'
        ]):
            return Intent.BOOKING, 0.90

        # Saludos (solo si NO hay interés ni booking)
        if any(w in msg for w in ['hola', 'hey', 'ey', 'buenas', 'buenos dias', 'que tal', 'hi']):
            return Intent.GREETING, 0.90

        # Objeción precio
        if any(w in msg for w in ['caro', 'costoso', 'mucho dinero', 'no puedo pagar', 'precio alto', 'barato']):
            return Intent.OBJECTION_PRICE, 0.90

        # Objeción tiempo
        if any(w in msg for w in ['no tengo tiempo', 'ocupado', 'sin tiempo', 'no puedo ahora']):
            return Intent.OBJECTION_TIME, 0.90

        # Objeción duda
        if any(w in msg for w in ['pensarlo', 'pensar', 'no se', 'no estoy seguro', 'dudas']):
            return Intent.OBJECTION_DOUBT, 0.85

        # Objeción "luego" / "después"
        if any(w in msg for w in ['luego', 'despues', 'otro dia', 'ahora no', 'mas adelante', 'en otro momento']):
            return Intent.OBJECTION_LATER, 0.85

        # Objeción "¿funciona?" / resultados
        if any(w in msg for w in ['funciona', 'resultados', 'garantia', 'pruebas', 'testimonios', 'casos de exito']):
            return Intent.OBJECTION_WORKS, 0.85

        # Objeción "no es para mí"
        if any(w in msg for w in ['no es para mi', 'no se si', 'principiante', 'no tengo experiencia', 'soy nuevo']):
            return Intent.OBJECTION_NOT_FOR_ME, 0.85

        # Objeción "es complicado"
        if any(w in msg for w in ['complicado', 'dificil', 'tecnico', 'complejo', 'no entiendo']):
            return Intent.OBJECTION_COMPLICATED, 0.85

        # Objeción "ya tengo algo"
        if any(w in msg for w in ['ya tengo', 'algo similar', 'parecido', 'otro curso', 'ya compre']):
            return Intent.OBJECTION_ALREADY_HAVE, 0.85

        # Pregunta sobre producto - EXPANDIDO con tildes y métodos de pago
        product_question_kw = [
            # Precio
            'que incluye', 'qué incluye', 'contenido', 'modulos', 'módulos',
            'cuanto cuesta', 'cuánto cuesta', 'precio', 'beneficios', 'vale',
            'cuanto vale', 'cuánto vale', 'que cuesta', 'qué cuesta',
            # Garantía
            'garantia', 'garantía', 'devolucion', 'devolución', 'reembolso',
            # Métodos de pago
            'como pago', 'cómo pago', 'como puedo pagar', 'cómo puedo pagar',
            'metodos de pago', 'métodos de pago', 'formas de pago',
            'bizum', 'paypal', 'stripe', 'transferencia', 'tarjeta',
            # Acceso
            'acceso', 'duracion', 'duración', 'cuanto dura', 'cuánto dura',
            'que tiene', 'qué tiene'
        ]
        matched_kw = [w for w in product_question_kw if w in msg]
        if matched_kw:
            logger.info(f"=== QUESTION_PRODUCT detected === msg='{msg}' matched={matched_kw}")
            return Intent.QUESTION_PRODUCT, 0.90

        # Pregunta general
        if any(w in msg for w in ['quien eres', 'que haces', 'a que te dedicas', 'sobre ti']):
            return Intent.QUESTION_GENERAL, 0.85

        # Lead magnet
        if any(w in msg for w in ['gratis', 'free', 'sin pagar', 'regalo', 'gratuito']):
            return Intent.LEAD_MAGNET, 0.90

        # Agradecimiento
        if any(w in msg for w in ['gracias', 'genial', 'perfecto', 'guay', 'thanks']):
            return Intent.THANKS, 0.85

        # Despedida
        if any(w in msg for w in ['adios', 'hasta luego', 'chao', 'nos vemos', 'bye']):
            return Intent.GOODBYE, 0.85

        # Soporte
        if any(w in msg for w in ['problema', 'no funciona', 'error', 'ayuda', 'falla']):
            return Intent.SUPPORT, 0.85

        # No match - log for debugging
        logger.info(f"=== INTENT OTHER (no match) === msg='{msg}'")
        return Intent.OTHER, 0.50

    def _get_relevant_product(self, message: str, intent: Intent) -> Optional[dict]:
        """Buscar producto relevante según mensaje e intent"""
        msg = message.lower()

        # Buscar por keywords del producto
        for product in self.products:
            keywords = product.get('keywords', [])
            if any(kw.lower() in msg for kw in keywords):
                return product

        # Si busca gratis, devolver lead magnet
        if intent == Intent.LEAD_MAGNET:
            for product in self.products:
                if product.get('price', 0) == 0:
                    return product

        # Si hay interés, devolver producto destacado o principal
        if intent in [Intent.INTEREST_STRONG, Intent.INTEREST_SOFT, Intent.QUESTION_PRODUCT]:
            for product in self.products:
                if product.get('is_featured', False):
                    return product
            # Si no hay destacado, devolver el primero con precio > 0
            for product in self.products:
                if product.get('price', 0) > 0:
                    return product

        return None

    def _get_objection_handler(self, intent: Intent, product: Optional[dict]) -> Optional[str]:
        """Obtener handler de objeción del producto"""
        if not product:
            return None

        handlers = product.get('objection_handlers', {})

        if intent == Intent.OBJECTION_PRICE:
            return handlers.get('precio', handlers.get('caro', None))
        if intent == Intent.OBJECTION_TIME:
            return handlers.get('tiempo', handlers.get('no tengo tiempo', None))
        if intent == Intent.OBJECTION_DOUBT:
            return handlers.get('pensarlo', handlers.get('dudas', None))
        if intent == Intent.OBJECTION_LATER:
            return handlers.get('luego', handlers.get('despues', None))
        if intent == Intent.OBJECTION_WORKS:
            return handlers.get('funciona', handlers.get('resultados', None))
        if intent == Intent.OBJECTION_NOT_FOR_ME:
            return handlers.get('no_para_mi', handlers.get('principiante', None))
        if intent == Intent.OBJECTION_COMPLICATED:
            return handlers.get('complicado', handlers.get('dificil', None))
        if intent == Intent.OBJECTION_ALREADY_HAVE:
            return handlers.get('ya_tengo', handlers.get('similar', None))

        return None

    def _build_system_prompt(self) -> str:
        """Construir system prompt con configuración y productos"""
        # Reload config to get latest settings (from DB)
        self.creator_config = self._load_creator_config()
        config = self.creator_config
        # Use clone_name (from Settings) with fallback to name
        name = config.get('clone_name') or config.get('name', 'Asistente')

        # Get clone_tone from Settings (professional, casual, friendly)
        clone_tone = config.get('clone_tone', 'friendly')
        clone_vocabulary = config.get('clone_vocabulary', '')
        logger.info(f"Building system prompt: name={name}, tone={clone_tone}, vocabulary_length={len(clone_vocabulary)}")

        # IMPORTANT: If clone_vocabulary has instructions, they take PRIORITY
        # Detect preset type from vocabulary to override clone_tone
        vocab_lower = clone_vocabulary.lower() if clone_vocabulary else ""
        detected_preset = None
        if "trata de usted" in vocab_lower or "evita emojis" in vocab_lower:
            clone_tone = "professional"
            detected_preset = "profesional"
        elif "ve al grano" in vocab_lower or "llamadas a la acción" in vocab_lower:
            clone_tone = "casual"  # Vendedor is direct
            detected_preset = "vendedor"
        elif "posiciónate como experto" in vocab_lower or "da consejos prácticos" in vocab_lower:
            detected_preset = "mentor"
            # Mentor keeps friendly tone but with expert positioning
        elif "tutea siempre" in vocab_lower or "amigo de confianza" in vocab_lower:
            detected_preset = "amigo"

        if detected_preset:
            logger.info(f"Detected personality preset: {detected_preset}, tone override: {clone_tone}")

        # Build tone instruction based on clone_tone
        if clone_tone == "professional":
            tone_instruction = "Responde de manera formal y profesional, sin emojis, con lenguaje corporativo y serio."
            emoji_instruction = "- Uso de emojis: NINGUNO (tono profesional)"
        elif clone_tone == "casual":
            tone_instruction = "Responde de manera muy informal, con jerga, emojis frecuentes y como si fueras un amigo cercano."
            emoji_instruction = "- Uso de emojis: frecuente (2-3 por mensaje)"
        else:  # friendly (default)
            tone_instruction = "Responde de manera amigable y cercana, equilibrando profesionalismo con calidez."
            emoji_instruction = "- Uso de emojis: moderado (1-2 por mensaje, VARIADOS)"

        # Get custom vocabulary/instructions from Settings - BUILD PRIORITY SECTION
        vocabulary_section = ""
        if clone_vocabulary:
            vocabulary_section = f"""

=== INSTRUCCIONES DE PERSONALIDAD (MÁXIMA PRIORIDAD) ===
{clone_vocabulary.strip()}

IMPORTANTE: Las instrucciones anteriores son OBLIGATORIAS y tienen prioridad sobre cualquier otra regla.
- Si dice "trata de usted" → NUNCA tutees
- Si dice "evita emojis" → NO uses emojis
- Si dice "ve al grano" → NO hagas preámbulos largos
=== FIN INSTRUCCIONES PRIORITARIAS ===
"""

        # Construir lista de productos CON links de pago claros
        products_text = ""
        payment_links_text = ""
        for p in self.products:
            price = p.get('price', 0)
            price_text = f"{price}€" if price > 0 else "GRATIS"
            benefits = p.get('features', p.get('benefits', []))[:3]
            benefits_text = ", ".join(benefits) if benefits else ""
            url = p.get('payment_link', p.get('url', ''))
            product_name = p.get('name', 'Producto')

            products_text += f"""
- {product_name}: {price_text}
  Descripcion: {p.get('description', '')}
  Beneficios: {benefits_text}
"""
            # Build payment links section
            if url:
                payment_links_text += f"- {product_name}: {url}\n"

        # If no payment links from products, note that
        if not payment_links_text:
            payment_links_text = "- No hay links configurados todavía\n"

        # Ejemplos de respuestas
        examples_text = ""
        examples = config.get('example_responses', [])
        if examples:
            examples_text = "\nEJEMPLOS DE COMO RESPONDO:\n"
            for ex in examples[:3]:
                examples_text += f"Usuario: {ex.get('question', '')}\nYo: {ex.get('response', '')}\n\n"

        # Build emoji rules section based on tone
        if clone_tone == "professional":
            emoji_rules = """EMOJIS - TONO PROFESIONAL:
- NO uses emojis en tus respuestas
- Mantén un tono serio y corporativo"""
        elif clone_tone == "casual":
            emoji_rules = """EMOJIS - USA VARIADOS Y FRECUENTES:
- Usa 2-3 emojis por mensaje para dar energia
- NUNCA repitas el mismo emoji en mensajes consecutivos
- Opciones: 💪 🚀 ✨ 🔥 👏 😊 🤔 👋 💯 🙌 😎 🎉"""
        else:  # friendly
            emoji_rules = """EMOJIS - USA DIFERENTES:
- NUNCA repitas el mismo emoji en mensajes consecutivos
- Si usaste 🙌 antes, usa otro: 💪 🚀 ✨ 🔥 👏 😊 🤔 👋 💯
- Maximo 1-2 emojis por mensaje"""

        # Formality rule based on tone
        if clone_tone == "professional":
            formality_rule = "Usa usted, sea formal y corporativo"
        elif clone_tone == "casual":
            formality_rule = "Tutea, usa jerga y se muy informal"
        else:  # friendly
            formality_rule = "Tutea al usuario, se cercano pero profesional"

        # Load knowledge base (FAQs and About)
        knowledge_section = ""
        if USE_POSTGRES and db_service:
            try:
                knowledge = db_service.get_full_knowledge(self.creator_id)
                faqs = knowledge.get("faqs", [])
                about = knowledge.get("about", {})
                logger.info(f"Loaded knowledge: {len(faqs)} FAQs, about has {sum(1 for v in about.values() if v)} fields")

                # Build About section
                if about and any(about.values()):
                    about_text = "\nSOBRE MI/MI NEGOCIO:\n"
                    if about.get("bio"):
                        about_text += f"- Bio: {about['bio']}\n"
                    if about.get("specialties"):
                        specs = about["specialties"]
                        if isinstance(specs, list):
                            about_text += f"- Especialidades: {', '.join(specs)}\n"
                        else:
                            about_text += f"- Especialidades: {specs}\n"
                    if about.get("experience"):
                        about_text += f"- Experiencia: {about['experience']}\n"
                    if about.get("target_audience"):
                        about_text += f"- Publico objetivo: {about['target_audience']}\n"
                    knowledge_section += about_text

                # Build FAQs section
                if faqs:
                    faqs_text = "\nPREGUNTAS FRECUENTES (usa esta info para responder):\n"
                    for faq in faqs[:10]:  # Limit to 10 FAQs
                        faqs_text += f"P: {faq.get('question', '')}\n"
                        faqs_text += f"R: {faq.get('answer', '')}\n\n"
                    knowledge_section += faqs_text

            except Exception as e:
                logger.warning(f"Failed to load knowledge base: {e}")

        # Get first payment link for examples
        first_payment_link = ""
        for p in self.products:
            link = p.get('payment_link', p.get('url', ''))
            if link:
                first_payment_link = link
                break

        # Format payment link for examples
        link_example = first_payment_link if first_payment_link else "https://pay.ejemplo.com/curso"

        # NEW PROMPT: Optimized for Llama/Grok - few-shot examples at END
        return f"""Eres {name}, un creador de contenido que responde mensajes de Instagram/WhatsApp.
{vocabulary_section}
PERSONALIDAD:
- {tone_instruction}
- {formality_rule}
{emoji_instruction}

SOBRE MÍ:
{knowledge_section}

MIS PRODUCTOS:
{products_text}

LINKS DE PAGO:
{payment_links_text}

---

FORMATO DE RESPUESTA (MUY IMPORTANTE):

Responde como si fuera un mensaje de WhatsApp entre amigos:
- Máximo 1-2 líneas cortas
- Directo al punto, sin rodeos
- Sin explicaciones largas
- Termina con pregunta corta cuando tenga sentido

EJEMPLOS DE CÓMO DEBES RESPONDER:

Usuario: ¿Cuánto cuesta el curso?
Tú: 297€ 🎯 ¿Quieres saber qué incluye?

Usuario: ¿Cómo puedo pagar?
Tú: Tarjeta, PayPal, Bizum o transferencia. ¿Cuál te va mejor?

Usuario: ¿Hay garantía?
Tú: Sí, 30 días. Si no te convence, te devuelvo el dinero 👍

Usuario: Quiero comprar
Tú: ¡Genial! Aquí tienes: {link_example}

Usuario: Hola
Tú: ¡Hola! ¿En qué puedo ayudarte? 😊

EJEMPLOS DE CÓMO NO RESPONDER (PROHIBIDO):

❌ MAL: "El precio del Curso Trading Pro es de 297€, lo que incluye 20 horas de vídeo, acceso a comunidad privada, sesiones Q&A semanales..."
✅ BIEN: "297€ 🎯 ¿Te cuento qué incluye?"

❌ MAL: Párrafos de más de 2 líneas
❌ MAL: Repetir toda la info del producto
❌ MAL: Decir "[link]" en vez del link real

RECUERDA: Eres un humano respondiendo WhatsApp, NO un folleto de ventas. Sé breve y natural."""

    def _build_user_prompt(
        self,
        message: str,
        intent: Intent,
        username: str,
        product: Optional[dict],
        objection_handler: Optional[str],
        conversation_history: List[dict],
        follower: Optional['FollowerMemory'] = None
    ) -> str:
        """Construir prompt del usuario con contexto"""

        # Historial de conversación
        history_text = ""
        if conversation_history:
            history_text = "\nCONVERSACION RECIENTE:\n"
            for msg in conversation_history[-4:]:
                role = "Usuario" if msg.get("role") == "user" else "Yo"
                history_text += f"{role}: {msg.get('content', '')}\n"

        # Extraer SOLO el primer nombre
        first_name = get_first_name(username)

        # Construir contexto del usuario (memoria)
        user_context = ""
        if follower:
            user_context = f"\nINFORMACION DEL USUARIO QUE CONOZCO:"
            user_context += f"\n- Nombre: {first_name}"
            user_context += f"\n- Total de mensajes: {follower.total_messages}"
            if follower.interests:
                user_context += f"\n- Intereses: {', '.join(follower.interests[:3])}"
            if follower.products_discussed:
                user_context += f"\n- Productos que le interesan: {', '.join(follower.products_discussed[:3])}"
            if follower.is_customer:
                user_context += f"\n- ES CLIENTE (ya ha comprado)"
            elif follower.is_lead:
                user_context += f"\n- Es un lead interesado (intencion de compra: {int(follower.purchase_intent_score * 100)}%)"
            user_context += "\n"

        # Construir contexto de naturalidad - qué NO repetir
        naturalidad_context = ""
        if follower:
            # Decidir si usar el nombre (solo 1 de cada 5 mensajes, y NUNCA consecutivos)
            # Requiere >= 5 mensajes desde el último uso
            if follower.messages_since_name_used >= 5:
                naturalidad_context += f"\n✓ PUEDES usar '{first_name}' (solo primer nombre, NO '{username}')"
            else:
                msgs_restantes = 5 - follower.messages_since_name_used
                naturalidad_context += f"\n⚠️ PROHIBIDO usar el nombre (faltan {msgs_restantes} mensajes)"

            # Evitar repetir emojis
            if follower.last_emojis_used:
                emojis_to_avoid = ", ".join(follower.last_emojis_used[-3:])
                naturalidad_context += f"\n⚠️ NO uses estos emojis (ya los usaste): {emojis_to_avoid}"

            # Evitar repetir estilo de saludo
            if follower.last_greeting_style:
                naturalidad_context += f"\n⚠️ NO empieces con '{follower.last_greeting_style}' (ya lo usaste)"

        prompt = f"""CONTEXTO:
- Usuario: {first_name} (usar SOLO este nombre, no el completo)
- Intent detectado: {intent.value}
{user_context}{history_text}
MENSAJE DEL USUARIO: "{message}"
{naturalidad_context}
"""

        # Control de links - no repetir demasiado
        include_link = True
        link_note = ""
        if follower:
            messages_since_last_link = follower.total_messages - follower.last_link_message_num
            # Solo incluir link si:
            # 1. Es la primera vez, O
            # 2. Han pasado 3+ mensajes desde el ultimo link, O
            # 3. El usuario pregunta explicitamente "como pago", "donde compro", etc.
            asking_for_link = any(kw in message.lower() for kw in ['pagar', 'compro', 'comprar', 'link', 'donde', 'how to pay', 'buy'])

            if follower.links_sent_count > 0 and messages_since_last_link < 3 and not asking_for_link:
                include_link = False
                link_note = "\n⚠️ NOTA: Ya enviaste el link recientemente. NO lo repitas a menos que el usuario pregunte."

        # Añadir producto relevante
        if product:
            price = product.get('price', 0)
            price_text = f"{price}€" if price > 0 else "GRATIS"
            benefits = product.get('features', product.get('benefits', []))[:3]

            if include_link:
                prompt += f"""
PRODUCTO RELEVANTE PARA MENCIONAR:
- Nombre: {product.get('name')}
- Precio: {price_text}
- Link: {product.get('payment_link', product.get('url', ''))}
- Beneficios: {', '.join(benefits)}
"""
            else:
                prompt += f"""
PRODUCTO RELEVANTE (sin link, ya lo enviaste):
- Nombre: {product.get('name')}
- Precio: {price_text}
- Beneficios: {', '.join(benefits)}
{link_note}
"""

        # Control de argumentos - no repetir los mismos
        if follower and follower.objections_handled:
            prompt += f"\nOBJECIONES YA MANEJADAS (usa argumentos DIFERENTES): {', '.join(follower.objections_handled[-3:])}"
            if follower.arguments_used:
                prompt += f"\nARGUMENTOS YA USADOS (NO repitas estos): {', '.join(follower.arguments_used[-5:])}"

        # Añadir handler de objeción
        if objection_handler:
            prompt += f"""
USA ESTA RESPUESTA PARA LA OBJECION (adaptala a tu tono):
"{objection_handler}"
"""

        # Instrucciones según intent
        instructions = {
            Intent.GREETING: "Saluda de forma cercana y VARIADA (no uses siempre 'Ey!'). Pregunta en que puedes ayudar.",
            Intent.INTEREST_STRONG: "El usuario QUIERE COMPRAR. Dale el link directamente y destaca 2-3 beneficios clave.",
            Intent.INTEREST_SOFT: "Hay interes. Pregunta que necesita y menciona sutilmente el producto.",
            Intent.OBJECTION_PRICE: "Maneja la objecion de precio. Se empatico, menciona garantia/valor.",
            Intent.OBJECTION_TIME: "Maneja la objecion de tiempo. Destaca que es rapido/flexible.",
            Intent.OBJECTION_DOUBT: "Resuelve dudas sin presionar. Ofrece mas info.",
            Intent.OBJECTION_LATER: "Maneja la objecion de 'luego'. Crea urgencia sutil, menciona que es el mejor momento.",
            Intent.OBJECTION_WORKS: "Maneja la objecion de resultados. Comparte casos de exito, garantia, testimonios.",
            Intent.OBJECTION_NOT_FOR_ME: "Maneja la objecion de 'no es para mi'. Empatiza, explica que es para todos los niveles.",
            Intent.OBJECTION_COMPLICATED: "Maneja la objecion de complejidad. Destaca que es facil y hay soporte.",
            Intent.OBJECTION_ALREADY_HAVE: "Maneja la objecion de 'ya tengo algo'. Diferencia tu producto, valor unico.",
            Intent.QUESTION_PRODUCT: "Responde la pregunta con los beneficios del producto.",
            Intent.QUESTION_GENERAL: "Explica brevemente quien eres y que haces.",
            Intent.LEAD_MAGNET: "Ofrece el recurso GRATIS con entusiasmo y da el link.",
            Intent.THANKS: "Agradece genuinamente y ofrece mas ayuda.",
            Intent.GOODBYE: "Despidete de forma calida, deja la puerta abierta.",
            Intent.SUPPORT: "Muestra empatia y ofrece ayuda concreta.",
            Intent.OTHER: "Responde de forma util y cercana."
        }

        prompt += f"\nINSTRUCCION: {instructions.get(intent, instructions[Intent.OTHER])}"

        return prompt

    def _build_language_instruction(self, language: str) -> str:
        """Construir instruccion de idioma para el prompt - MUY EXPLICITA"""
        if language == "es":
            return """

⚠️ IDIOMA OBLIGATORIO: ESPAÑOL
- Responde ÚNICAMENTE en ESPAÑOL
- NO uses palabras en inglés como "I", "don't", "you've", "they"
- Respuesta en español (máximo 2-3 frases):"""
        elif language == "en":
            return """

⚠️ MANDATORY LANGUAGE: ENGLISH
- Reply ONLY in ENGLISH
- Do NOT use Spanish words
- Response in English (max 2-3 sentences):"""
        elif language == "pt":
            return """

⚠️ IDIOMA OBRIGATÓRIO: PORTUGUÊS
- Responda SOMENTE em PORTUGUÊS
- NÃO use palavras em espanhol ou inglês
- Resposta em português (máximo 2-3 frases):"""
        else:
            return f"\n\nResponde en español (máximo 2-3 frases):"

    async def process_dm(
        self,
        sender_id: str,
        message_text: str,
        message_id: str = "",
        username: str = "amigo",
        name: str = ""
    ) -> DMResponse:
        """Procesar DM y generar respuesta personalizada"""

        logger.info(f"Processing DM from {sender_id}: {message_text}")

        # Verificar si el bot esta activo (PostgreSQL primero, luego JSON config)
        bot_is_active = True  # Default to active
        if USE_POSTGRES and db_service:
            try:
                creator = db_service.get_creator_by_name(self.creator_id)
                if creator:
                    bot_is_active = creator.get("bot_active", True)
                    logger.debug(f"Bot status from PostgreSQL: {bot_is_active}")
            except Exception as e:
                logger.warning(f"Failed to get bot status from PostgreSQL: {e}")
                # Fallback to config manager
                bot_is_active = self.config_manager.is_bot_active(self.creator_id)
        else:
            bot_is_active = self.config_manager.is_bot_active(self.creator_id)

        if not bot_is_active:
            logger.info(f"Bot paused for creator {self.creator_id}")
            return DMResponse(
                response_text="",  # No enviar respuesta cuando esta pausado
                intent=Intent.OTHER,
                action_taken="bot_paused",
                confidence=1.0,
                metadata={"status": "paused", "message": "Bot pausado por el creador"}
            )

        # Rate limiting para prevenir abuse y controlar costes
        rate_limiter = get_rate_limiter()
        rate_key = f"{self.creator_id}:{sender_id}"
        allowed, reason = rate_limiter.check_limit(rate_key)
        if not allowed:
            logger.warning(f"Rate limited: {rate_key} - {reason}")
            return DMResponse(
                response_text="Dame un momento, estoy procesando varios mensajes. Te respondo enseguida!",
                intent=Intent.OTHER,
                action_taken="rate_limited",
                confidence=1.0,
                metadata={"rate_limit_reason": reason}
            )

        # Obtener/crear memoria del seguidor (with name/username if available)
        follower = await self.memory_store.get_or_create(
            self.creator_id,
            sender_id,
            name=name,
            username=username if username != "amigo" else ""
        )

        # Extraer nombre del mensaje si el usuario se presenta
        # Patrones: "soy [nombre]", "me llamo [nombre]", "I'm [name]", etc.
        extracted_name = extract_name_from_message(message_text)
        if extracted_name:
            # SIEMPRE actualizar cuando el usuario dice explícitamente su nombre
            # Esto sobreescribe el nombre de Telegram/Instagram
            old_name = follower.name
            follower.name = extracted_name
            logger.info(f"Name extracted from message: '{extracted_name}' (was: '{old_name}')")
            # Guardar inmediatamente en memoria
            await self.memory_store.save(follower)

        # Verificar consentimiento GDPR (si esta habilitado)
        if REQUIRE_CONSENT:
            consent_response = await self._check_gdpr_consent(sender_id, message_text, follower)
            if consent_response:
                return consent_response

        # Detectar idioma del mensaje usando detección ROBUSTA
        # Solo cambia el idioma si hay evidencia fuerte (3+ keywords)
        current_lang = follower.preferred_language if follower.total_messages > 0 else None
        detected_lang = detect_language_robust(message_text, current_lang)

        # Actualizar idioma preferido solo si:
        # 1. Es el primer mensaje, O
        # 2. La detección robusta cambió el idioma (evidencia fuerte)
        if follower.total_messages == 0:
            follower.preferred_language = detected_lang
            logger.info(f"Language set on first message: {detected_lang}")
        elif detected_lang != follower.preferred_language:
            # detect_language_robust ya verifica evidencia fuerte
            old_lang = follower.preferred_language
            follower.preferred_language = detected_lang
            logger.info(f"Language changed from {old_lang} to {detected_lang} (strong evidence)")

        # Clasificar intent
        intent, confidence = self._classify_intent(message_text)
        logger.info(f"Intent: {intent.value} ({confidence:.0%})")

        # Verificar escalación
        if intent == Intent.ESCALATION:
            response_text = self._get_escalation_response()
            await self._update_memory(follower, message_text, response_text, intent)

            # Registrar escalacion en metricas
            record_escalation(self.creator_id, reason="user_requested")

            # Notificar al creador de la escalación
            try:
                notification_service = get_notification_service()
                escalation = EscalationNotification(
                    creator_id=self.creator_id,
                    follower_id=sender_id,
                    follower_username=username,
                    follower_name=follower.name or username,
                    reason="Usuario solicita hablar con humano",
                    last_message=message_text,
                    conversation_summary=f"Último tema: {follower.products_discussed[-1] if follower.products_discussed else 'General'}",
                    purchase_intent_score=follower.purchase_intent_score,
                    total_messages=follower.total_messages,
                    products_discussed=follower.products_discussed
                )
                await notification_service.notify_escalation(escalation)
                logger.info(f"Escalation notification sent for {sender_id}")
            except Exception as e:
                logger.error(f"Failed to send escalation notification: {e}")

            return DMResponse(
                response_text=response_text,
                intent=intent,
                action_taken="escalate",
                escalate_to_human=True,
                confidence=confidence
            )

        # Verificar si quiere agendar una llamada
        if intent == Intent.BOOKING:
            booking_links = self._load_booking_links()
            user_language = follower.preferred_language or "es"

            # Detect platform from sender_id
            platform = "telegram" if sender_id.startswith("tg_") else "instagram"

            # Get formatted response (returns dict with 'text' and optionally 'telegram_keyboard')
            booking_response = self._format_booking_response(booking_links, user_language, platform)
            response_text = booking_response.get("text", "")

            await self._update_memory(follower, message_text, response_text, intent)

            logger.info(f"Booking intent detected - found {len(booking_links)} links (platform: {platform})")

            # Include telegram keyboard in metadata if present
            metadata = {}
            if "telegram_keyboard" in booking_response:
                metadata["telegram_keyboard"] = booking_response["telegram_keyboard"]

            return DMResponse(
                response_text=response_text,
                intent=intent,
                action_taken="show_booking_links",
                confidence=confidence,
                metadata=metadata
            )

        # Buscar producto relevante
        product = self._get_relevant_product(message_text, intent)
        if product:
            logger.info(f"Relevant product: {product.get('name')}, payment_link={product.get('payment_link', 'NONE')}")
            if product.get('id') and product.get('id') not in follower.products_discussed:
                follower.products_discussed.append(product.get('id'))

        # === FAST PATH: Compra directa ===
        # Cuando usuario QUIERE COMPRAR, solo dar el link - NO volver a vender
        if is_direct_purchase_intent(message_text):
            logger.info(f"=== DIRECT PURCHASE INTENT DETECTED ===")
            logger.info(f"Message: {message_text}")
            logger.info(f"All products: {[(p.get('name'), p.get('payment_link', 'NONE')) for p in self.products]}")

            # Try to find a product with a payment link
            product_url = ""
            product_name = "el producto"

            # First try the relevant product
            if product:
                product_url = product.get('payment_link', product.get('url', ''))
                product_name = product.get('name', 'el producto')

            # If no link, try to find ANY product with a payment link
            if not product_url:
                for p in self.products:
                    link = p.get('payment_link', p.get('url', ''))
                    if link and link.startswith('http'):
                        product_url = link
                        product_name = p.get('name', 'el producto')
                        logger.info(f"Found fallback payment link from product: {product_name}")
                        break

            logger.info(f"DIRECT PURCHASE: product={product_name}, payment_link={product_url}")

            # Subir purchase_intent a 85%+ inmediatamente
            follower.purchase_intent_score = max(follower.purchase_intent_score, 0.85)
            follower.is_lead = True

            logger.info(f"DIRECT PURCHASE detected - giving link only, score set to {follower.purchase_intent_score}")

            # Elegir emoji basado en idioma
            emoji = "🚀" if follower.preferred_language == "es" else "🎉"

            # Respuesta CORTA - solo el link (si hay link)
            if product_url:
                if follower.preferred_language == "es":
                    response_text = f"¡Perfecto! {emoji} Aquí tienes: {product_url}"
                else:
                    response_text = f"Perfect! {emoji} Here you go: {product_url}"
            else:
                # No hay link configurado - escalate to human
                logger.warning(f"NO PAYMENT LINK FOUND for any product!")
                if follower.preferred_language == "es":
                    response_text = f"¡Genial que quieras comprar! {emoji} Te paso con el equipo para completar el pago. Escríbenos y te atendemos enseguida."
                else:
                    response_text = f"Great that you want to buy! {emoji} Let me connect you with the team to complete the payment."

            # Guardar en historial
            follower.last_messages.append({
                "role": "user",
                "content": message_text,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            follower.last_messages.append({
                "role": "assistant",
                "content": response_text,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            follower.total_messages += 1
            follower.last_contact = datetime.now(timezone.utc).isoformat()

            # Limitar historial
            if len(follower.last_messages) > 20:
                follower.last_messages = follower.last_messages[-20:]

            await self.memory_store.save(follower)
            # Save BOTH messages to PostgreSQL
            await self._save_message_to_db(follower.follower_id, 'user', message_text, str(intent))
            await self._save_message_to_db(follower.follower_id, 'assistant', response_text, None)

            # Track product link click
            try:
                sales_tracker = get_sales_tracker()
                sales_tracker.record_click(
                    creator_id=self.creator_id,
                    product_id=product.get('id', ''),
                    follower_id=follower.follower_id,
                    product_name=product_name,
                    link_url=product_url
                )
            except Exception as e:
                logger.warning(f"Failed to track click: {e}")

            return DMResponse(
                response_text=response_text,
                intent=intent,
                action_taken="direct_purchase_link",
                product_mentioned=product_name,
                confidence=0.95,
                metadata={
                    "direct_purchase": True,
                    "product_url": product_url,
                    "purchase_intent_score": follower.purchase_intent_score
                }
            )

        # Obtener handler de objeción
        objection_handler = self._get_objection_handler(intent, product)

        # Usar el nombre guardado del follower si existe, sino el username del mensaje
        display_name = follower.name or username

        # Construir prompts
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            message=message_text,
            intent=intent,
            username=display_name,  # Usar nombre guardado del follower
            product=product,
            objection_handler=objection_handler,
            conversation_history=follower.last_messages,
            follower=follower  # Para control de links y objeciones
        )

        # Agregar instruccion de idioma al prompt
        user_language = follower.preferred_language
        user_prompt += self._build_language_instruction(user_language)

        # Check cache para respuestas frecuentes (solo intents cacheables)
        response_cache = get_response_cache()
        # Include clone_tone and clone_vocabulary hash in cache key so config changes invalidate cache
        clone_tone = self.creator_config.get('clone_tone', 'friendly')
        clone_vocabulary = self.creator_config.get('clone_vocabulary', '')
        # Use hash of vocabulary to avoid long cache keys
        vocab_hash = hash(clone_vocabulary) if clone_vocabulary else 0
        cache_key_params = {
            "creator_id": self.creator_id,
            "intent": intent.value,
            "language": user_language,
            "tone": clone_tone,
            "vocab": vocab_hash
        }

        # Solo cachear intents que lo permiten
        is_cacheable = intent not in NON_CACHEABLE_INTENTS
        cached_response = None

        # TEMPORARY: Bypass cache to debug fallback issue
        bypass_cache = True  # TODO: Remove after fixing fallback bug

        if is_cacheable and not bypass_cache:
            # Normalizar mensaje para cache (sin puntuacion, minusculas)
            normalized_msg = message_text.lower().strip()
            cached_response = response_cache.get(normalized_msg, **cache_key_params)

            if cached_response:
                logger.info(f"Cache HIT for intent {intent.value}: {cached_response[:50]}")
                response_text = cached_response
                record_cache_hit(self.creator_id)
            else:
                logger.debug(f"Cache MISS for intent {intent.value}")
                record_cache_miss(self.creator_id)
        else:
            logger.info(f"Cache BYPASSED for debugging")

        # Generar respuesta con LLM solo si no hay cache
        if not cached_response:
            try:
                # === CHAIN OF THOUGHT FOR COMPLEX QUERIES ===
                # Use CoT reasoning for complex/health-related queries
                cot_used = False
                try:
                    cot_reasoner = get_chain_of_thought_reasoner(self.llm)
                    if cot_reasoner.is_complex_query(message_text):
                        logger.info("Using Chain of Thought for complex query")
                        cot_context = {
                            "creator_name": self.creator_config.get("name", "el creador"),
                            "products": self.products
                        }
                        cot_result = await cot_reasoner.generate(message_text, cot_context)

                        if cot_result.is_complex and cot_result.answer:
                            response_text = cot_result.answer
                            cot_used = True
                            logger.info(f"CoT response: type={cot_result.query_type}, steps={len(cot_result.reasoning_steps)}")
                except Exception as cot_error:
                    logger.warning(f"Chain of Thought failed: {cot_error}")

                # Standard LLM response if CoT not used
                if not cot_used:
                    messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ]
                    logger.info(f"=== DEBUG: Calling LLM ===")
                    logger.info(f"Message: {message_text[:100]}")
                    logger.info(f"Intent: {intent.value} ({confidence:.2f})")
                    logger.info(f"Products loaded: {len(self.products)}")

                    response_text = await self.llm.chat(
                        messages,
                        max_tokens=80,  # CORTO - 1-2 frases máximo
                        temperature=0.8  # Más natural, menos robótico
                    )
                    response_text = response_text.strip()
                    logger.info(f"LLM Response: {response_text[:150] if response_text else 'EMPTY'}")

                # Validate response with guardrails
                try:
                    guardrail = get_response_guardrail()
                    product_prices = [p.get("price") for p in self.products if p.get("price")]
                    logger.debug(f"Guardrail context: {len(self.products)} products, prices: {product_prices}")
                    guardrail_context = {
                        "products": self.products,
                        "allowed_urls": [p.get("payment_link", "") for p in self.products if p.get("payment_link")],
                        "creator_config": self.creator_config,
                        "language": user_language
                    }
                    response_text = guardrail.get_safe_response(
                        query=message_text,
                        response=response_text,
                        context=guardrail_context
                    )
                except Exception as ge:
                    logger.warning(f"Guardrail check failed: {ge}")

                # === POST-PROCESSING: BREVEDAD Y LINKS ===
                # 1. Truncar a máximo 2 frases (AGRESIVO - el LLM ignora instrucciones)
                response_text = truncate_response(response_text, max_sentences=2)

                # 2. Reemplazar placeholders de links con links reales
                payment_links = [p.get('payment_link', p.get('url', '')) for p in self.products]
                response_text = clean_response_placeholders(response_text, payment_links)

                # === SELF-CONSISTENCY CHECK ===
                # Validate response confidence before sending
                # If confidence < 0.6 -> use safe fallback response
                # SKIP for most intents - only validate objections and escalations
                intents_needing_validation = {
                    Intent.ESCALATION,
                    Intent.SUPPORT,
                }
                # Skip consistency for most intents (trust the LLM with good prompt)
                skip_consistency = intent not in intents_needing_validation

                if skip_consistency:
                    logger.info(f"Skipping self-consistency for simple intent {intent.value} (confidence={confidence:.2f})")
                else:
                    try:
                        consistency_validator = get_self_consistency_validator(self.llm)
                        consistency_result = await consistency_validator.validate_response(
                            query=message_text,
                            response=response_text,
                            system_prompt=system_prompt,
                            max_tokens=200
                        )

                        # Log confidence for monitoring
                        logger.info(
                            f"Self-consistency: confidence={consistency_result.confidence:.2f}, "
                            f"consistent={consistency_result.is_consistent}"
                        )

                        if not consistency_result.is_consistent:
                            # Low confidence -> safe fallback
                            creator_name = self.creator_config.get('name', 'el creador')
                            if user_language == "es":
                                response_text = f"Déjame confirmarlo con {creator_name} y te respondo enseguida."
                            elif user_language == "en":
                                response_text = f"Let me confirm this with {creator_name} and I'll get back to you shortly."
                            elif user_language == "pt":
                                response_text = f"Deixe-me confirmar isso com {creator_name} e já te respondo."
                            else:
                                response_text = f"Déjame confirmarlo con {creator_name} y te respondo enseguida."

                            logger.info(f"Low confidence ({consistency_result.confidence:.2f}) - using safe fallback")

                            # Record for analytics (optional: track escalations due to low confidence)
                            try:
                                record_escalation(self.creator_id, reason="low_confidence")
                            except Exception:
                                pass
                        else:
                            # Use validated response (may be refined by consistency check)
                            response_text = consistency_result.response

                    except Exception as sc_error:
                        logger.warning(f"Self-consistency check failed: {sc_error}")
                        # Continue with original response on error

                # Si el idioma no es espanol y la respuesta parece en espanol, traducir
                if user_language != DEFAULT_LANGUAGE:
                    # Verificar si necesitamos traducir (el LLM a veces ignora la instruccion)
                    response_lang = detect_language(response_text)
                    if response_lang != user_language:
                        logger.info(f"Translating response from {response_lang} to {user_language}")
                        response_text = await translate_response(
                            response_text,
                            user_language,
                            response_lang,
                            self.llm
                        )

                # Cachear respuesta si es cacheable
                if is_cacheable and response_text:
                    normalized_msg = message_text.lower().strip()
                    response_cache.set(normalized_msg, response_text, **cache_key_params)
                    logger.debug(f"Cached response for intent {intent.value}")

            except Exception as e:
                import traceback
                logger.error(f"=== ERROR generating response ===")
                logger.error(f"Error type: {type(e).__name__}")
                logger.error(f"Error message: {e}")
                logger.error(f"Traceback: {traceback.format_exc()}")
                response_text = self._get_fallback_response(intent)
                logger.info(f"Using fallback response: {response_text[:100]}")

                # Registrar error en metricas
                provider = os.getenv("LLM_PROVIDER", "unknown")
                record_llm_error(
                    creator_id=self.creator_id,
                    provider=provider,
                    error_type=type(e).__name__
                )

                # Enviar alerta de error LLM
                try:
                    alert_manager = get_alert_manager()
                    await alert_manager.alert_llm_error(
                        error=str(e),
                        creator_id=self.creator_id,
                        provider=provider
                    )
                except Exception as alert_error:
                    logger.debug(f"Could not send alert: {alert_error}")

        # Actualizar memoria
        await self._update_memory(follower, message_text, response_text, intent)

        # Programar nurturing si aplica
        nurturing_scheduled = await self._schedule_nurturing_if_needed(
            follower_id=sender_id,
            intent=intent,
            product=product,
            is_customer=follower.is_customer
        )

        # Add AI transparency disclosure for first message if enabled
        transparency_enabled = os.getenv("TRANSPARENCY_ENABLED", "false").lower() == "true"
        is_first_message = follower.total_messages <= 1
        if transparency_enabled and is_first_message:
            creator_name = self.config.get("name", self.creator_id)
            disclosure = get_transparency_disclosure(creator_name, user_language)
            response_text = f"{disclosure}\n\n{response_text}"
            logger.info(f"Added transparency disclosure for first message")

        logger.info(f"Response: {response_text[:100]}...")

        # Track product link click if response contains a link and product was mentioned
        if product and ('http' in response_text.lower() or '.com' in response_text.lower() or 'hotmart' in response_text.lower()):
            try:
                sales_tracker = get_sales_tracker()
                product_url = product.get('payment_link', product.get('url', ''))
                sales_tracker.record_click(
                    creator_id=self.creator_id,
                    product_id=product.get('id', ''),
                    follower_id=sender_id,
                    product_name=product.get('name', ''),
                    link_url=product_url
                )
                logger.info(f"Click tracked for product {product.get('name')} -> follower {sender_id}")
            except Exception as e:
                logger.warning(f"Failed to track click: {e}")

        # Track analytics
        await self._track_analytics(
            sender_id=sender_id,
            intent=intent,
            is_lead=follower.is_lead,
            score=follower.purchase_intent_score
        )

        # Registrar mensaje procesado en metricas Prometheus
        record_message_processed(
            creator_id=self.creator_id,
            platform="instagram",
            intent=intent.value
        )

        return DMResponse(
            response_text=response_text,
            intent=intent,
            action_taken=intent.value,
            product_mentioned=product.get('name') if product else None,
            follow_up_needed=intent in [Intent.INTEREST_SOFT, Intent.OBJECTION_PRICE, Intent.OBJECTION_TIME],
            escalate_to_human=False,
            confidence=confidence,
            metadata={
                "product_id": product.get('id') if product else None,
                "follower_messages": follower.total_messages,
                "nurturing_scheduled": nurturing_scheduled,
                "language": user_language
            }
        )

    async def _update_memory(
        self,
        follower: FollowerMemory,
        message: str,
        response: str,
        intent: Intent
    ):
        """Actualizar memoria del seguidor"""
        follower.total_messages += 1
        timestamp = datetime.now(timezone.utc).isoformat()
        follower.last_contact = timestamp

        # Añadir al historial con timestamps
        follower.last_messages.append({
            "role": "user",
            "content": message,
            "timestamp": timestamp
        })
        follower.last_messages.append({
            "role": "assistant",
            "content": response,
            "timestamp": timestamp
        })

        # Limitar historial
        if len(follower.last_messages) > 20:
            follower.last_messages = follower.last_messages[-20:]

        # Trackear links enviados (detectar si la respuesta contiene un link)
        if 'http' in response.lower() or '.com' in response.lower() or 'hotmart' in response.lower():
            follower.links_sent_count += 1
            follower.last_link_message_num = follower.total_messages
            logger.debug(f"Link detected in response. Total links sent: {follower.links_sent_count}")

        # Trackear objeciones manejadas y argumentos usados
        if intent.value.startswith('objection_'):
            objection_type = intent.value.replace('objection_', '')
            if objection_type not in follower.objections_handled:
                follower.objections_handled.append(objection_type)

            # Detectar argumentos usados en la respuesta
            argument_keywords = {
                'garantia': ['garantía', 'garantia', '30 días', '30 dias', 'devolucion'],
                'roi': ['recuperas', 'rentabiliza', 'primera semana', 'roi'],
                'tiempo_corto': ['15 minutos', 'poco tiempo', 'rápido', 'flexible'],
                'testimonios': ['alumnos', 'casos', 'testimonios', 'resultados'],
                'soporte': ['soporte', 'ayuda', 'acompaño', 'comunidad'],
                'niveles': ['todos los niveles', 'desde cero', 'principiante'],
                'facil': ['fácil', 'sencillo', 'paso a paso'],
                'unico': ['único', 'diferente', 'exclusivo'],
            }
            for arg_name, keywords in argument_keywords.items():
                if any(kw in response.lower() for kw in keywords):
                    if arg_name not in follower.arguments_used:
                        follower.arguments_used.append(arg_name)

        # Incrementar índice de saludo para variar
        if intent == Intent.GREETING:
            follower.greeting_variant_index += 1

        # === TRACKING DE NATURALIDAD ===

        # Detectar y trackear emojis usados en la respuesta
        emoji_pattern = ['🙌', '💪', '🔥', '✨', '🚀', '👏', '💯', '⚡', '😊', '😄',
                        '🤗', '☺️', '😉', '🙂', '👍', '🤔', '💭', '🧐', '💡', '🎉',
                        '🎊', '🥳', '🏆', '👋', '🎯', '📈']
        for emoji in emoji_pattern:
            if emoji in response:
                if emoji not in follower.last_emojis_used:
                    follower.last_emojis_used.append(emoji)
                # Limitar a últimos 5
                if len(follower.last_emojis_used) > 5:
                    follower.last_emojis_used = follower.last_emojis_used[-5:]

        # Detectar estilo de inicio del mensaje para no repetir
        response_start = response[:20].lower() if response else ""
        greeting_styles = ['ey ', 'hey ', 'hola', 'buenas', 'genial', 'claro', 'entiendo', 'mira']
        for style in greeting_styles:
            if response_start.startswith(style) or f'¡{style}' in response_start:
                follower.last_greeting_style = style.strip()
                break

        # Trackear uso del nombre del usuario
        # Buscar el PRIMER nombre del follower en la respuesta
        full_name = follower.name or follower.username
        first_name = get_first_name(full_name)
        if first_name and len(first_name) > 2 and first_name != "amigo":
            # Verificar si se usó el primer nombre en la respuesta
            if first_name.lower() in response.lower():
                # Se usó el nombre, resetear contador
                follower.messages_since_name_used = 0
                logger.debug(f"Name '{first_name}' used in response, counter reset")
            else:
                # No se usó el nombre, incrementar contador
                follower.messages_since_name_used += 1
        else:
            follower.messages_since_name_used += 1

        # Actualizar score de intención
        # Usamos MÍNIMOS para intenciones positivas (el score no baja de ese valor)
        # y DECREMENTOS para objeciones

        # === SCORE RANGES: 25% / 50% / 75% / 100% ===
        # New Leads: 0-25% | Warm: 25-50% | Hot: 50-75% | Customer: 75%+

        # BOOST: Si hay keywords de compra directa, subir a 75% (Hot)
        if is_direct_purchase_intent(message):
            follower.purchase_intent_score = max(follower.purchase_intent_score, 0.75)
            logger.info(f"Direct purchase keywords detected - score boosted to {follower.purchase_intent_score}")
        elif intent == Intent.INTEREST_STRONG:
            # Interés fuerte ("quiero comprar"): 75% → Hot
            follower.purchase_intent_score = max(follower.purchase_intent_score, 0.75)
            logger.info(f"INTEREST_STRONG detected - score set to 75% (Hot)")
        elif intent == Intent.INTEREST_SOFT:
            # Interés suave ("me interesa"): 50% → Warm
            follower.purchase_intent_score = max(follower.purchase_intent_score, 0.50)
            logger.info(f"INTEREST_SOFT detected - score set to 50% (Warm)")
        elif intent == Intent.QUESTION_PRODUCT:
            # Pregunta sobre producto: 25% → sale de New Leads
            follower.purchase_intent_score = max(follower.purchase_intent_score, 0.25)
        else:
            # Para objeciones y otros, aplicar decrementos
            objection_decrements = {
                Intent.OBJECTION_PRICE: -0.05,
                Intent.OBJECTION_TIME: -0.05,
                Intent.OBJECTION_DOUBT: -0.05,
                Intent.OBJECTION_LATER: -0.03,
                Intent.OBJECTION_WORKS: 0.05,  # Pide pruebas = interés real
                Intent.OBJECTION_NOT_FOR_ME: -0.05,
                Intent.OBJECTION_COMPLICATED: -0.03,
                Intent.OBJECTION_ALREADY_HAVE: -0.1,
            }
            change = objection_decrements.get(intent, 0)
            if change != 0:
                follower.purchase_intent_score = max(0.0, min(1.0, follower.purchase_intent_score + change))

        # Marcar como lead (score > 25% = sale de New Leads)
        if follower.purchase_intent_score > 0.25 or intent == Intent.INTEREST_STRONG:
            follower.is_lead = True

        # ============================================================
        # AUTO-TRANSITION: Update pipeline status based on rules
        # ============================================================
        # NEVER downgrade status: customer > hot > active > new
        # Each transition only moves UP, never down

        # Constants for thresholds
        HOT_INTENT_THRESHOLD = 0.60  # 60% intent = hot

        # Intents that indicate buying intent (→ hot)
        hot_intents = {Intent.INTEREST_STRONG}

        # Intents that indicate active engagement (→ active)
        active_intents = {
            Intent.INTEREST_SOFT,
            Intent.QUESTION_PRODUCT,
            Intent.OBJECTION_PRICE,  # Asking about price = engaged
            Intent.OBJECTION_TIME,
            Intent.OBJECTION_DOUBT,
            Intent.OBJECTION_LATER,
            Intent.OBJECTION_WORKS,
        }

        old_status = follower.status
        current_status = follower.status or "new"

        # Rule: Customer status is permanent (set via payment webhooks)
        if current_status == "customer" or follower.is_customer:
            follower.status = "customer"
        # Rule: NEW → HOT (direct purchase intent or high AI score)
        elif current_status in ["new", "active", ""] and (
            intent in hot_intents or
            is_direct_purchase_intent(message) or
            follower.purchase_intent_score >= HOT_INTENT_THRESHOLD
        ):
            follower.status = "hot"
            logger.info(f"Pipeline transition: {old_status} → hot (intent={intent.value}, score={follower.purchase_intent_score:.0%})")
        # Rule: NEW → ACTIVE (engagement without clear buy intent)
        elif current_status in ["new", ""] and (
            intent in active_intents or
            follower.total_messages >= 2  # At least one back-and-forth
        ):
            follower.status = "active"
            logger.info(f"Pipeline transition: {old_status} → active (intent={intent.value}, messages={follower.total_messages})")
        # Keep current status if no transition rule applies
        elif not follower.status:
            follower.status = "new"

        await self.memory_store.save(follower)
        # Save BOTH messages to PostgreSQL for dashboard stats
        await self._save_message_to_db(follower.follower_id, 'user', message, str(intent))
        await self._save_message_to_db(follower.follower_id, 'assistant', response, None)
        # Sync lead data to PostgreSQL
        if USE_POSTGRES and db_service:
            try:
                from api.services.data_sync import sync_json_to_postgres
                sync_json_to_postgres(self.creator_id, follower.follower_id)
            except Exception as e:
                logger.debug(f"Lead sync skipped: {e}")

    async def _schedule_nurturing_if_needed(
        self,
        follower_id: str,
        intent: Intent,
        product: Optional[dict],
        is_customer: bool
    ) -> bool:
        """
        Programar nurturing automático si aplica.

        Args:
            follower_id: ID del seguidor
            intent: Intent detectado
            product: Producto relevante
            is_customer: Si ya es cliente

        Returns:
            True si se programó nurturing
        """
        try:
            sequence_type = should_schedule_nurturing(intent.value, is_customer)

            if not sequence_type:
                return False

            nurturing = get_nurturing_manager()
            product_name = product.get('name', 'mi producto') if product else 'mi producto'

            # Cancelar nurturing existente del mismo tipo antes de programar nuevo
            nurturing.cancel_followups(self.creator_id, follower_id, sequence_type)

            # Programar nueva secuencia
            followups = nurturing.schedule_followup(
                creator_id=self.creator_id,
                follower_id=follower_id,
                sequence_type=sequence_type,
                product_name=product_name
            )

            if followups:
                logger.info(f"Scheduled {len(followups)} nurturing followups for {follower_id} ({sequence_type})")
                return True

        except Exception as e:
            logger.error(f"Error scheduling nurturing: {e}")

        return False

    async def _track_analytics(
        self,
        sender_id: str,
        intent: Intent,
        is_lead: bool,
        score: float
    ):
        """
        Track analytics for the processed message.

        Args:
            sender_id: Follower ID
            intent: Detected intent
            is_lead: Whether follower is a lead
            score: Purchase intent score
        """
        try:
            analytics = get_analytics_manager()
            platform = detect_platform(sender_id)

            # Track received message
            analytics.track_message(
                creator_id=self.creator_id,
                follower_id=sender_id,
                direction="received",
                intent=intent.value,
                platform=platform
            )

            # Track sent message (response)
            analytics.track_message(
                creator_id=self.creator_id,
                follower_id=sender_id,
                direction="sent",
                platform=platform
            )

            # Track lead if applicable
            if is_lead and score > 0.3:
                analytics.track_lead(
                    creator_id=self.creator_id,
                    follower_id=sender_id,
                    score=score,
                    source="dm",
                    platform=platform
                )

            # Track objection if applicable
            if intent.value.startswith("objection_"):
                analytics.track_objection(
                    creator_id=self.creator_id,
                    follower_id=sender_id,
                    objection_type=intent.value,
                    platform=platform
                )

            # Track escalation if applicable
            if intent == Intent.ESCALATION:
                analytics.track_escalation(
                    creator_id=self.creator_id,
                    follower_id=sender_id,
                    platform=platform
                )

        except Exception as e:
            logger.error(f"Error tracking analytics: {e}")

    async def _check_gdpr_consent(
        self,
        sender_id: str,
        message_text: str,
        follower
    ) -> Optional[DMResponse]:
        """
        Check GDPR consent and handle consent flow if needed.

        Args:
            sender_id: Follower ID
            message_text: User's message
            follower: Follower memory object

        Returns:
            DMResponse if consent flow is triggered, None otherwise
        """
        try:
            gdpr = get_gdpr_manager()

            # Check if user has data processing consent
            has_consent = gdpr.has_consent(
                self.creator_id,
                sender_id,
                ConsentType.DATA_PROCESSING.value
            )

            if has_consent:
                return None  # Continue normal processing

            # Check if user is giving consent in this message
            msg_lower = message_text.lower()
            consent_keywords = ['acepto', 'si acepto', 'de acuerdo', 'ok', 'vale', 'accept', 'i agree', 'yes']
            decline_keywords = ['no acepto', 'no quiero', 'rechazar', 'decline', 'no thanks']

            if any(kw in msg_lower for kw in consent_keywords):
                # Record consent
                gdpr.record_consent(
                    creator_id=self.creator_id,
                    follower_id=sender_id,
                    consent_type=ConsentType.DATA_PROCESSING.value,
                    granted=True,
                    source="dm"
                )
                logger.info(f"Consent granted by {sender_id}")
                return None  # Continue with normal processing

            if any(kw in msg_lower for kw in decline_keywords):
                # Record declined consent
                gdpr.record_consent(
                    creator_id=self.creator_id,
                    follower_id=sender_id,
                    consent_type=ConsentType.DATA_PROCESSING.value,
                    granted=False,
                    source="dm"
                )
                response_text = (
                    "Entendido, respeto tu decision. Si cambias de opinion, "
                    "solo escribe 'acepto' y podre ayudarte. Hasta pronto!"
                )
                return DMResponse(
                    response_text=response_text,
                    intent=Intent.OTHER,
                    action_taken="consent_declined",
                    confidence=1.0
                )

            # First message without consent - ask for consent
            if follower.total_messages == 0:
                response_text = (
                    "Hola! Antes de continuar, necesito tu consentimiento para procesar "
                    "tus mensajes y poder ayudarte mejor. "
                    "Tus datos se usaran solo para responder tus consultas. "
                    "Responde 'acepto' para continuar o 'no acepto' si prefieres no hacerlo."
                )
                return DMResponse(
                    response_text=response_text,
                    intent=Intent.OTHER,
                    action_taken="consent_request",
                    confidence=1.0
                )

            # Subsequent message without consent - remind
            response_text = (
                "Recuerda que necesito tu consentimiento para procesar tus mensajes. "
                "Responde 'acepto' para que pueda ayudarte!"
            )
            return DMResponse(
                response_text=response_text,
                intent=Intent.OTHER,
                action_taken="consent_reminder",
                confidence=1.0
            )

        except Exception as e:
            logger.error(f"Error checking GDPR consent: {e}")
            return None  # On error, continue normal processing

    def _get_escalation_response(self) -> str:
        """Respuesta de escalación cuando el usuario pide hablar con humano"""
        name = self.creator_config.get('name', 'el equipo')
        email = self.creator_config.get('escalation_email', '')

        # Variantes de respuesta para ser más natural
        responses = [
            f"Entendido, paso tu mensaje a {name} y te contactará pronto. 🙌",
            f"Perfecto, le paso tu mensaje a {name} y se pondrá en contacto contigo lo antes posible.",
            f"Sin problema, {name} te responderá personalmente en breve.",
            f"Claro, he tomado nota y {name} te contactará pronto para ayudarte mejor."
        ]
        response = random.choice(responses)
        if email:
            response += f" Si es urgente, puedes escribir a {email}."
        return response

    def _get_fallback_response(self, intent: Intent, language: str = "es") -> str:
        """
        Respuesta de fallback cuando LLM falla.
        Uses varied responses to seem more natural.
        """
        name = self.creator_config.get('name', 'yo')

        # Spanish fallbacks with variations
        fallbacks_es = {
            Intent.GREETING: [
                f"Ey! Que tal? Soy {name}. En que puedo ayudarte?",
                f"Hola! Soy {name}, encantado de saludarte. Que necesitas?",
            ],
            Intent.INTEREST_STRONG: [
                "Genial que te interese! Te paso toda la info ahora mismo.",
                "Me encanta tu interes! Dejame contarte todo.",
            ],
            Intent.INTEREST_SOFT: [
                "Me alegra que te interese! Cuentame, que necesitas exactamente?",
                "Que bien! Que te gustaria saber mas?",
            ],
            Intent.OBJECTION_PRICE: [
                "Entiendo que es una inversion. Que es lo que mas te preocupa?",
                "Comprendo. Es normal pensarselo. Que te gustaria saber sobre el valor?",
            ],
            Intent.OBJECTION_TIME: [
                "Lo entiendo, el tiempo es oro. Precisamente esto te ayuda a ganar tiempo.",
                "Claro, el tiempo es importante. Por eso esta disenado para ser rapido.",
            ],
            Intent.OBJECTION_DOUBT: [
                "Normal tener dudas. Que te gustaria saber?",
                "Entiendo tus dudas. Cuentame, que te preocupa?",
            ],
            Intent.OBJECTION_LATER: [
                "Claro, sin prisa. Aunque te digo que el mejor momento es ahora.",
                "Entiendo! Cuando estes listo, aqui estoy.",
            ],
            Intent.OTHER: [
                "Gracias por tu mensaje! Dame un momento para responder.",
                "Recibido! En un momento te cuento mas.",
                "Gracias por escribir! En que puedo ayudarte?",
            ],
        }

        # English fallbacks
        fallbacks_en = {
            Intent.GREETING: [
                f"Hey! I'm {name}. How can I help you?",
                f"Hi there! {name} here. What can I do for you?",
            ],
            Intent.OTHER: [
                "Thanks for your message! I'll get back to you shortly.",
                "Got it! Give me a moment to respond.",
            ],
        }

        fallbacks = fallbacks_es if language == "es" else fallbacks_en
        options = fallbacks.get(intent, fallbacks.get(Intent.OTHER, ["Gracias por escribir!"]))
        return random.choice(options)

    async def get_all_conversations(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Obtener todas las conversaciones del creador"""
        conversations = []
        storage_path = os.path.join(self.memory_store.storage_path, self.creator_id)

        if not os.path.exists(storage_path):
            return conversations

        try:
            files = sorted(
                [f for f in os.listdir(storage_path) if f.endswith('.json')],
                key=lambda x: os.path.getmtime(os.path.join(storage_path, x)),
                reverse=True
            )[:limit]

            for file in files:
                file_path = os.path.join(storage_path, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # Count actual user messages in last_messages (more accurate than stored counter)
                        last_messages = data.get("last_messages", [])
                        user_msg_count = len([m for m in last_messages if m.get("role") == "user"])
                        # Use the higher of stored counter or actual count
                        total_msgs = max(data.get("total_messages", 0), user_msg_count)
                        conversations.append({
                            "follower_id": data.get("follower_id", ""),
                            "username": data.get("username", ""),
                            "name": data.get("name", ""),
                            "platform": data.get("platform", "instagram"),
                            "total_messages": total_msgs,
                            "last_contact": data.get("last_contact", ""),
                            "first_contact": data.get("first_contact", ""),
                            "is_lead": data.get("is_lead", False),
                            "is_customer": data.get("is_customer", False),
                            "purchase_intent": data.get("purchase_intent_score", 0),
                            "interests": data.get("interests", []),
                            "products_discussed": data.get("products_discussed", []),
                            "preferred_language": data.get("preferred_language", "es"),
                            # Contact fields from JSON storage
                            "email": data.get("email", ""),
                            "phone": data.get("phone", ""),
                            "notes": data.get("notes", ""),
                            "last_messages": last_messages[-5:] if last_messages else [],
                        })
                except Exception as e:
                    logger.error(f"Error reading conversation file {file}: {e}")

        except Exception as e:
            logger.error(f"Error listing conversations: {e}")

        return conversations

    async def get_leads(self) -> List[Dict[str, Any]]:
        """Obtener todos los leads del creador"""
        conversations = await self.get_all_conversations(limit=500)
        leads = [c for c in conversations if c.get("is_lead", False)]
        # Ordenar por intención de compra
        leads.sort(key=lambda x: x.get("purchase_intent", 0), reverse=True)
        return leads

    async def get_metrics(self) -> Dict[str, Any]:
        """Obtener métricas del agente"""
        conversations = await self.get_all_conversations(limit=1000)

        total_messages = sum(c.get("total_messages", 0) for c in conversations)
        total_followers = len(conversations)
        leads = [c for c in conversations if c.get("is_lead", False)]
        customers = [c for c in conversations if c.get("is_customer", False)]
        high_intent = [c for c in conversations if c.get("purchase_intent", 0) > 0.5]

        return {
            "total_messages": total_messages,
            "total_followers": total_followers,
            "leads": len(leads),
            "customers": len(customers),
            "high_intent_followers": len(high_intent),
            "conversion_rate": len(customers) / total_followers if total_followers > 0 else 0,
            "lead_rate": len(leads) / total_followers if total_followers > 0 else 0
        }

    async def get_follower_detail(self, follower_id: str) -> Optional[Dict[str, Any]]:
        """Obtener detalle de un seguidor específico"""
        follower = await self.memory_store.get(self.creator_id, follower_id)

        if not follower:
            return None

        return {
            "follower_id": follower.follower_id,
            "username": follower.username,
            "name": follower.name,
            "first_contact": follower.first_contact,
            "last_contact": follower.last_contact,
            "total_messages": follower.total_messages,
            "interests": follower.interests,
            "products_discussed": follower.products_discussed,
            "objections_raised": follower.objections_raised,
            "purchase_intent_score": follower.purchase_intent_score,
            "is_lead": follower.is_lead,
            "is_customer": follower.is_customer,
            "preferred_language": follower.preferred_language,
            "last_messages": follower.last_messages[-10:]  # Últimos 10 mensajes
        }

    async def save_manual_message(
        self,
        follower_id: str,
        message_text: str,
        sent: bool = True
    ) -> bool:
        """
        Save a manually sent message in the conversation history.

        Args:
            follower_id: The follower's ID
            message_text: The message text that was sent
            sent: Whether the message was successfully sent

        Returns:
            True if saved successfully
        """
        try:
            follower = await self.memory_store.get(self.creator_id, follower_id)

            if not follower:
                logger.warning(f"Follower {follower_id} not found for saving manual message")
                return False

            # Add the message to history
            timestamp = datetime.now(timezone.utc).isoformat()
            follower.last_messages.append({
                "role": "assistant",
                "content": message_text,
                "timestamp": timestamp,
                "manual": True,  # Mark as manually sent
                "sent": sent
            })

            # Keep only last 50 messages
            if len(follower.last_messages) > 50:
                follower.last_messages = follower.last_messages[-50:]

            # Update last contact time
            follower.last_contact = timestamp

            # Save to memory store
            await self.memory_store.save(follower)
            # Save to PostgreSQL (manual message from assistant)
            await self._save_message_to_db(follower.follower_id, 'assistant', message_text, None)

            logger.info(f"Saved manual message for {follower_id}")
            return True

        except Exception as e:
            logger.error(f"Error saving manual message: {e}")
            return False

    async def update_follower_status(
        self,
        follower_id: str,
        status: str,
        purchase_intent: float,
        is_customer: bool = False
    ) -> bool:
        """
        Update the lead status for a follower.

        Args:
            follower_id: The follower's ID
            status: The new status (cold, warm, hot, customer)
            purchase_intent: The purchase intent score (0.0 to 1.0)
            is_customer: Whether the follower is now a customer

        Returns:
            True if updated successfully
        """
        try:
            follower = await self.memory_store.get(self.creator_id, follower_id)

            if not follower:
                logger.warning(f"Follower {follower_id} not found for status update")
                return False

            # Update the follower's status
            old_score = follower.purchase_intent_score
            follower.purchase_intent_score = purchase_intent

            # Update is_lead based on score
            if purchase_intent >= 0.3:
                follower.is_lead = True

            # Update is_customer
            if is_customer:
                follower.is_customer = True

            # Save to memory store (no message added to history)
            await self.memory_store.save(follower)

            logger.info(f"Updated status for {follower_id}: {status} (intent: {old_score:.0%} → {purchase_intent:.0%})")
            return True

        except Exception as e:
            logger.error(f"Error updating follower status: {e}")
            return False

# ============================================================
# POSTGRESQL INTEGRATION (saves messages to DB for dashboard)
# ============================================================