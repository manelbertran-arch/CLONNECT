"""
Memory Service - Manage follower conversation memory.

Extracted from dm_agent.py as part of REFACTOR-PHASE2.
Provides in-memory caching with JSON file persistence.
"""
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
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

    Provides in-memory caching with JSON file persistence.
    Can be extended to support database persistence.
    """

    def __init__(self, storage_path: str = "data/followers") -> None:
        """
        Initialize memory store.

        Args:
            storage_path: Directory path for JSON file storage
        """
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        self._cache: Dict[str, FollowerMemory] = {}
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
        if cache_key in self._cache:
            logger.debug(f"[MemoryStore] Cache hit for {follower_id}")
            return self._cache[cache_key]

        # Load from JSON
        memory = self._load_from_json(creator_id, follower_id)
        if memory:
            self._cache[cache_key] = memory
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
        self._cache[cache_key] = memory
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
        now = datetime.now().isoformat()
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
