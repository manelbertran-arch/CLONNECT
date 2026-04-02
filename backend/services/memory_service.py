"""
Memory Service - Manage follower conversation memory.

Extracted from dm_agent.py as part of REFACTOR-PHASE2.
Provides in-memory caching with JSON file persistence.
"""
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class FollowerMemory:
    """
    Memory dataclass for a follower.

    Stores conversation history, interests, objections, and lead scoring data.
    """

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
    status: str = "new"  # new, active, hot, customer
    preferred_language: str = "es"
    last_messages: List[Dict[str, Any]] = field(default_factory=list)
    # Link and objection tracking
    links_sent_count: int = 0
    last_link_message_num: int = 0
    objections_handled: List[str] = field(default_factory=list)
    arguments_used: List[str] = field(default_factory=list)
    greeting_variant_index: int = 0
    # Naturalness - avoid repetition
    last_greeting_style: str = ""
    last_emojis_used: List[str] = field(default_factory=list)
    messages_since_name_used: int = 0
    # Alternative contact (WhatsApp/Telegram)
    alternative_contact: str = ""
    alternative_contact_type: str = ""
    contact_requested: bool = False
    # Conversation summary (used by dm_agent_v2 for lead context)
    conversation_summary: str = ""

    def __post_init__(self) -> None:
        """Sanitize None values that may come from JSON loading."""
        # Int fields
        if self.total_messages is None:
            self.total_messages = 0
        if self.links_sent_count is None:
            self.links_sent_count = 0
        if self.last_link_message_num is None:
            self.last_link_message_num = 0
        if self.greeting_variant_index is None:
            self.greeting_variant_index = 0
        if self.messages_since_name_used is None:
            self.messages_since_name_used = 0

        # Float fields
        if self.purchase_intent_score is None:
            self.purchase_intent_score = 0.0

        # String fields
        if self.username is None:
            self.username = ""
        if self.name is None:
            self.name = ""
        if self.first_contact is None:
            self.first_contact = ""
        if self.last_contact is None:
            self.last_contact = ""
        if self.status is None:
            self.status = "new"
        if self.preferred_language is None:
            self.preferred_language = "es"
        if self.last_greeting_style is None:
            self.last_greeting_style = ""
        if self.alternative_contact is None:
            self.alternative_contact = ""
        if self.alternative_contact_type is None:
            self.alternative_contact_type = ""

        # Bool fields
        if self.is_lead is None:
            self.is_lead = False
        if self.is_customer is None:
            self.is_customer = False
        if self.contact_requested is None:
            self.contact_requested = False

        # List fields
        if self.interests is None:
            self.interests = []
        if self.products_discussed is None:
            self.products_discussed = []
        if self.objections_raised is None:
            self.objections_raised = []
        if self.last_messages is None:
            self.last_messages = []
        if self.objections_handled is None:
            self.objections_handled = []
        if self.arguments_used is None:
            self.arguments_used = []
        if self.last_emojis_used is None:
            self.last_emojis_used = []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "follower_id": self.follower_id,
            "creator_id": self.creator_id,
            "username": self.username,
            "name": self.name,
            "first_contact": self.first_contact,
            "last_contact": self.last_contact,
            "total_messages": self.total_messages,
            "interests": self.interests,
            "products_discussed": self.products_discussed,
            "objections_raised": self.objections_raised,
            "purchase_intent_score": self.purchase_intent_score,
            "is_lead": self.is_lead,
            "is_customer": self.is_customer,
            "status": self.status,
            "preferred_language": self.preferred_language,
            "last_messages": self.last_messages[-20:],  # Keep last 20
            "links_sent_count": self.links_sent_count,
            "last_link_message_num": self.last_link_message_num,
            "objections_handled": self.objections_handled,
            "arguments_used": self.arguments_used,
            "greeting_variant_index": self.greeting_variant_index,
            "last_greeting_style": self.last_greeting_style,
            "last_emojis_used": self.last_emojis_used[-5:],  # Keep last 5
            "messages_since_name_used": self.messages_since_name_used,
            "alternative_contact": self.alternative_contact,
            "alternative_contact_type": self.alternative_contact_type,
            "contact_requested": self.contact_requested,
            "conversation_summary": self.conversation_summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FollowerMemory":
        """Create from dictionary."""
        # Filter to only known fields
        known_fields = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)


class MemoryStore:
    """
    Store for follower memory.

    Provides BoundedTTLCache with JSON file persistence.
    """

    def __init__(self, storage_path: str = "data/followers") -> None:
        """
        Initialize memory store.

        Args:
            storage_path: Directory path for JSON file storage
        """
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        # BUG-MEM-07 fix: bounded cache instead of unbounded dict
        from core.cache import BoundedTTLCache
        self._cache = BoundedTTLCache(max_size=500, ttl_seconds=600)
        logger.info(f"[MemoryStore] Initialized with path: {storage_path}")

    def _get_cache_key(self, creator_id: str, follower_id: str) -> str:
        """Generate cache key for creator/follower pair."""
        return f"{creator_id}:{follower_id}"

    def _get_file_path(self, creator_id: str, follower_id: str) -> str:
        """Get JSON file path for a follower."""
        creator_dir = os.path.join(self.storage_path, creator_id)
        os.makedirs(creator_dir, exist_ok=True)
        # Sanitize follower_id for filename
        safe_id = follower_id.replace("/", "_").replace("\\", "_")
        return os.path.join(creator_dir, f"{safe_id}.json")

    def _load_from_json(
        self, creator_id: str, follower_id: str
    ) -> Optional[FollowerMemory]:
        """Load follower memory from JSON file."""
        file_path = self._get_file_path(creator_id, follower_id)
        if not os.path.exists(file_path):
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return FollowerMemory.from_dict(data)
        except Exception as e:
            logger.error(f"[MemoryStore] Error loading from JSON: {e}")
            return None

    def _save_to_json(self, memory: FollowerMemory) -> bool:
        """Save follower memory to JSON file."""
        file_path = self._get_file_path(memory.creator_id, memory.follower_id)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(memory.to_dict(), f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"[MemoryStore] Error saving to JSON: {e}")
            return False

    async def get(
        self, creator_id: str, follower_id: str
    ) -> Optional[FollowerMemory]:
        """
        Get follower memory.

        Checks cache first, then loads from JSON if not cached.

        Args:
            creator_id: Creator identifier
            follower_id: Follower identifier

        Returns:
            FollowerMemory if found, None otherwise
        """
        cache_key = self._get_cache_key(creator_id, follower_id)

        # Check cache first
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug(f"[MemoryStore] Cache hit for {follower_id}")
            return cached

        # Load from JSON
        memory = self._load_from_json(creator_id, follower_id)
        if memory:
            self._cache.set(cache_key, memory)
            logger.debug(f"[MemoryStore] Loaded {follower_id} from JSON")

        return memory

    async def save(self, memory: FollowerMemory) -> None:
        """
        Save follower memory.

        Updates cache and persists to JSON.

        Args:
            memory: FollowerMemory to save
        """
        cache_key = self._get_cache_key(memory.creator_id, memory.follower_id)
        self._cache.set(cache_key, memory)
        self._save_to_json(memory)
        logger.debug(f"[MemoryStore] Saved {memory.follower_id}")

    async def get_or_create(
        self,
        creator_id: str,
        follower_id: str,
        name: str = "",
        username: str = "",
    ) -> FollowerMemory:
        """
        Get existing memory or create new one.

        Args:
            creator_id: Creator identifier
            follower_id: Follower identifier
            name: Follower's display name (used only for new records)
            username: Follower's username (used only for new records)

        Returns:
            Existing or newly created FollowerMemory
        """
        memory = await self.get(creator_id, follower_id)
        if memory is not None:
            return memory

        # Create new memory
        now = datetime.now(timezone.utc).isoformat()
        memory = FollowerMemory(
            follower_id=follower_id,
            creator_id=creator_id,
            name=name,
            username=username,
            first_contact=now,
            last_contact=now,
        )
        await self.save(memory)
        logger.info(
            f"[MemoryStore] Created new follower: {follower_id} "
            f"(name={name}, username={username})"
        )
        return memory

    def clear_cache(self) -> None:
        """Clear the in-memory cache."""
        self._cache.clear()
        logger.info("[MemoryStore] Cache cleared")

    def get_cache_size(self) -> int:
        """Get number of items in cache."""
        return len(self._cache)


# ═══════════════════════════════════════════════════════════════════════════════
# CONVERSATION MEMORY SERVICE (Phase 2)
# ═══════════════════════════════════════════════════════════════════════════════

import re
from typing import Tuple

from models.conversation_memory import ConversationFact, ConversationMemory, FactType


class ConversationMemoryService:
    """Servicio para gestionar memoria de conversaciones con detección de facts."""

    # Patrones para detectar referencias al pasado
    PAST_REFERENCE_PATTERNS = [
        r"ya te (lo )?dije",
        r"ya me (lo )?dijiste",
        r"como te (comenté|dije|mencioné)",
        r"te (había|habia) (dicho|comentado)",
        r"recuerdas que",
        r"la otra vez",
        r"la vez pasada",
        r"antes (me dijiste|hablamos)",
        r"el otro día",
        r"hace (unos )?días",
        r"cuando hablamos",
        r"lo que me dijiste",
        r"seguimos con",
        r"retomamos",
    ]

    # Patrones para extraer precios
    PRICE_PATTERNS = [
        r"(\d+)\s*€",
        r"(\d+)\s*euros?",
        r"(\d+)\s*EUR",
        r"€\s*(\d+)",
        r"cuesta\s*(\d+)",
        r"precio[:\s]+(\d+)",
        r"son\s*(\d+)",
    ]

    # Patrones para detectar preguntas
    QUESTION_PATTERNS = [
        r"\?",
        r"cuánto\s+(cuesta|vale|es)",
        r"qué\s+(es|incluye|ofrece)",
        r"cómo\s+(funciona|puedo)",
        r"dónde\s+(puedo|está)",
        r"cuándo\s+(es|empieza|puedo)",
    ]

    def __init__(self, storage_path: str = "data/conversation_memory"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)

    def _get_memory_path(self, lead_id: str, creator_id: str) -> str:
        """Ruta del archivo de memoria."""
        return os.path.join(self.storage_path, f"{creator_id}_{lead_id}.json")

    async def load(self, lead_id: str, creator_id: str) -> ConversationMemory:
        """Carga la memoria de una conversación (DB first, JSON fallback)."""
        import asyncio as _aio
        # BUG-MEM-06 fix: try DB first (survives Railway deploys)
        try:
            def _load_db():
                from api.database import SessionLocal
                from sqlalchemy import text
                session = SessionLocal()
                try:
                    row = session.execute(
                        text(
                            "SELECT fact_text FROM lead_memories "
                            "WHERE creator_id = CAST(:cid AS uuid) "
                            "AND lead_id = CAST(:lid AS uuid) "
                            "AND fact_type = '_conv_memory_state' "
                            "AND is_active = true "
                            "ORDER BY updated_at DESC LIMIT 1"
                        ),
                        {"cid": creator_id, "lid": lead_id},
                    ).fetchone()
                    return row[0] if row else None
                finally:
                    session.close()
            data_str = await _aio.to_thread(_load_db)
            if data_str:
                return ConversationMemory.from_dict(json.loads(data_str))
        except Exception:
            pass  # Fall through to JSON

        # Fallback: JSON file (legacy)
        path = self._get_memory_path(lead_id, creator_id)
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                    return ConversationMemory.from_dict(data)
            except Exception as e:
                logger.error(f"Error loading conversation memory from {path}: {e}")

        return ConversationMemory(lead_id=lead_id, creator_id=creator_id)

    async def save(self, memory: ConversationMemory):
        """Guarda la memoria de una conversación (DB + JSON fallback)."""
        import asyncio as _aio
        import uuid as _uuid
        data = memory.to_dict()
        data_str = json.dumps(data, ensure_ascii=False)

        # BUG-MEM-06 fix: persist to DB (survives Railway deploys)
        try:
            def _save_db():
                from api.database import SessionLocal
                from sqlalchemy import text
                session = SessionLocal()
                try:
                    # Deactivate old state
                    session.execute(
                        text(
                            "UPDATE lead_memories SET is_active = false, updated_at = NOW() "
                            "WHERE creator_id = CAST(:cid AS uuid) "
                            "AND lead_id = CAST(:lid AS uuid) "
                            "AND fact_type = '_conv_memory_state' "
                            "AND is_active = true"
                        ),
                        {"cid": memory.creator_id, "lid": memory.lead_id},
                    )
                    # Insert new state
                    session.execute(
                        text(
                            "INSERT INTO lead_memories "
                            "(id, creator_id, lead_id, fact_type, fact_text, "
                            "confidence, source_type, created_at, updated_at) "
                            "VALUES ("
                            "CAST(:id AS uuid), CAST(:cid AS uuid), CAST(:lid AS uuid), "
                            "'_conv_memory_state', :ftext, 1.0, 'system', NOW(), NOW())"
                        ),
                        {"id": str(_uuid.uuid4()), "cid": memory.creator_id,
                         "lid": memory.lead_id, "ftext": data_str},
                    )
                    session.commit()
                finally:
                    session.close()
            await _aio.to_thread(_save_db)
        except Exception as e:
            logger.debug(f"[ConvMemory] DB save failed, using JSON only: {e}")

        # Also save to JSON as fallback
        path = self._get_memory_path(memory.lead_id, memory.creator_id)
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving conversation memory to {path}: {e}")

    def detect_past_reference(self, message: str) -> bool:
        """Detecta si el usuario hace referencia a conversación pasada."""
        message_lower = message.lower()
        return any(
            re.search(pattern, message_lower)
            for pattern in self.PAST_REFERENCE_PATTERNS
        )

    def extract_facts(
        self, message: str, response: str, is_bot_response: bool = True,
        products: Optional[List[str]] = None,
    ) -> list:
        """Extrae facts de un intercambio de mensajes.

        Args:
            message: Mensaje del lead.
            response: Respuesta del bot.
            is_bot_response: True para analizar la respuesta del bot.
            products: Lista de nombres de productos del creador (desde DB).
                      Si es None o vacía, se omite la detección de productos.
        """
        facts = []
        text = response if is_bot_response else message

        # Detectar precios mencionados
        for pattern in self.PRICE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                price = match.group(1) if match.lastindex else match.group(0)
                facts.append(
                    ConversationFact(
                        fact_type=FactType.PRICE_GIVEN,
                        content=f"{price}€",
                        confidence=0.95,
                    )
                )
                break

        # Detectar links compartidos
        link_match = re.search(r"https?://\S+", text)
        if link_match:
            facts.append(
                ConversationFact(
                    fact_type=FactType.LINK_SHARED,
                    content=link_match.group(),
                    confidence=0.99,
                )
            )

        # Detectar productos mencionados — usa catálogo del creador, no hardcoded
        for product in (products or []):
            if product and len(product) > 2 and product.lower() in text.lower() and len(text) > 50:
                facts.append(
                    ConversationFact(
                        fact_type=FactType.PRODUCT_EXPLAINED,
                        content=product,
                        confidence=0.8,
                    )
                )

        # Detectar preguntas del lead
        if not is_bot_response:
            for pattern in self.QUESTION_PATTERNS:
                if re.search(pattern, message, re.IGNORECASE):
                    facts.append(
                        ConversationFact(
                            fact_type=FactType.QUESTION_ASKED,
                            content=message[:100],
                            confidence=0.9,
                        )
                    )
                    break

        return facts

    def should_repeat_info(
        self, memory: ConversationMemory, info_type: str
    ) -> Tuple[bool, Optional[str]]:
        """Determina si es necesario repetir información."""
        if not memory.has_given_info(info_type):
            return True, None

        previous_value = memory.get_info(info_type)

        days = memory.get_days_since_last_interaction()
        if days and days > 7:
            return True, previous_value

        return False, previous_value

    def detect_question_type(self, message: str) -> Optional[str]:
        """Detecta el tipo de pregunta del usuario."""
        message_lower = message.lower()

        if any(
            p in message_lower for p in ["cuánto", "cuanto", "precio", "cuesta", "vale"]
        ):
            return "precio"
        if any(
            p in message_lower
            for p in ["qué es", "que es", "qué incluye", "cómo funciona"]
        ):
            return "producto"
        if any(p in message_lower for p in ["cuándo", "cuando", "horario", "fecha"]):
            return "disponibilidad"
        if any(p in message_lower for p in ["dónde", "donde", "ubicación", "dirección"]):
            return "ubicacion"

        return None

    async def update_memory_after_exchange(
        self, memory: ConversationMemory, lead_message: str, bot_response: str
    ) -> ConversationMemory:
        """Actualiza la memoria después de un intercambio."""
        lead_facts = self.extract_facts(lead_message, "", is_bot_response=False)
        for fact in lead_facts:
            memory.add_fact(fact)

        bot_facts = self.extract_facts(lead_message, bot_response, is_bot_response=True)
        for fact in bot_facts:
            memory.add_fact(fact)

        question_type = self.detect_question_type(lead_message)
        if question_type and "?" in lead_message:
            if lead_message not in memory.unanswered_lead_questions:
                memory.unanswered_lead_questions.append(lead_message[:100])

        if question_type == "precio" and any(
            f.fact_type == FactType.PRICE_GIVEN for f in bot_facts
        ):
            memory.unanswered_lead_questions = [
                q
                for q in memory.unanswered_lead_questions
                if "precio" not in q.lower() and "cuánto" not in q.lower()
            ]

        memory.last_interaction = datetime.now(timezone.utc)
        memory.total_messages += 2

        if not memory.conversation_started:
            memory.conversation_started = datetime.now(timezone.utc)

        return memory

    def get_memory_context_for_prompt(self, memory: ConversationMemory) -> str:
        """Genera contexto de memoria para inyectar en el prompt."""
        context = memory.get_context_summary()

        if not context:
            return ""

        return f"""
=== MEMORIA DE CONVERSACIÓN ===
{context}

⚠️ Si ya diste un precio o info, NO lo repitas textualmente.
   Di algo como "como te comenté" o "el precio que te dije".
=== FIN MEMORIA ===
"""


# Singleton para ConversationMemoryService
_conversation_memory_service: Optional[ConversationMemoryService] = None


def get_conversation_memory_service() -> ConversationMemoryService:
    """Obtiene la instancia global del servicio de memoria de conversación."""
    global _conversation_memory_service
    if _conversation_memory_service is None:
        _conversation_memory_service = ConversationMemoryService()
    return _conversation_memory_service
