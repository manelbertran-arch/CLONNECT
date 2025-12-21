"""
Sistema de memoria simplificado para Clonnect Creators
Usa almacenamiento en JSON para persistencia
"""

import os
import json
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict, field
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@dataclass
class FollowerMemory:
    """Memoria de un seguidor"""
    follower_id: str
    creator_id: str
    username: str = ""
    name: str = ""

    # Historial
    first_contact: str = ""
    last_contact: str = ""
    total_messages: int = 0

    # Perfil inferido
    interests: List[str] = field(default_factory=list)
    products_discussed: List[str] = field(default_factory=list)
    objections_raised: List[str] = field(default_factory=list)

    # Scoring
    purchase_intent_score: float = 0.0
    engagement_score: float = 0.0

    # Estado
    is_lead: bool = False
    is_customer: bool = False
    needs_followup: bool = False

    # Idioma preferido
    preferred_language: str = "es"

    # Conversacion
    conversation_summary: str = ""
    last_messages: List[Dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'FollowerMemory':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class MemoryStore:
    """Almacen de memoria para seguidores"""

    def __init__(self, storage_path: str = "data/followers"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        self._cache: Dict[str, FollowerMemory] = {}

    def _get_file_path(self, creator_id: str, follower_id: str) -> str:
        creator_dir = os.path.join(self.storage_path, creator_id)
        os.makedirs(creator_dir, exist_ok=True)
        return os.path.join(creator_dir, f"{follower_id}.json")

    def _get_cache_key(self, creator_id: str, follower_id: str) -> str:
        return f"{creator_id}:{follower_id}"

    async def get(self, creator_id: str, follower_id: str) -> Optional[FollowerMemory]:
        """Obtener memoria de un seguidor"""
        cache_key = self._get_cache_key(creator_id, follower_id)

        # Buscar en cache
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Buscar en disco
        file_path = self._get_file_path(creator_id, follower_id)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    memory = FollowerMemory.from_dict(data)
                    self._cache[cache_key] = memory
                    return memory
            except Exception as e:
                logger.error(f"Error loading memory: {e}")

        return None

    async def save(self, memory: FollowerMemory):
        """Guardar memoria de un seguidor"""
        cache_key = self._get_cache_key(memory.creator_id, memory.follower_id)
        self._cache[cache_key] = memory

        file_path = self._get_file_path(memory.creator_id, memory.follower_id)
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(memory.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving memory: {e}")

    async def get_or_create(
        self,
        creator_id: str,
        follower_id: str,
        username: str = "",
        name: str = ""
    ) -> FollowerMemory:
        """Obtener o crear memoria de seguidor"""
        memory = await self.get(creator_id, follower_id)

        if memory is None:
            memory = FollowerMemory(
                follower_id=follower_id,
                creator_id=creator_id,
                username=username,
                name=name,
                first_contact=datetime.now().isoformat(),
                last_contact=datetime.now().isoformat()
            )
            await self.save(memory)

        return memory

    async def update_after_interaction(
        self,
        memory: FollowerMemory,
        user_message: str,
        bot_response: str,
        intent: str = "",
        entities: List[str] = None
    ):
        """Actualizar memoria despues de una interaccion"""
        memory.total_messages += 1
        memory.last_contact = datetime.now().isoformat()

        # Actualizar ultimos mensajes (mantener ultimos 10)
        memory.last_messages.append({
            "role": "user",
            "content": user_message,
            "timestamp": datetime.now().isoformat()
        })
        memory.last_messages.append({
            "role": "assistant",
            "content": bot_response,
            "timestamp": datetime.now().isoformat()
        })
        memory.last_messages = memory.last_messages[-20:]  # Mantener ultimos 20

        # Actualizar intereses con entidades detectadas
        if entities:
            for entity in entities:
                if entity not in memory.interests:
                    memory.interests.append(entity)

        # Actualizar scores segun intencion
        if intent == "interest_strong":
            memory.purchase_intent_score = min(1.0, memory.purchase_intent_score + 0.3)
            memory.is_lead = True
        elif intent == "interest_soft":
            memory.purchase_intent_score = min(1.0, memory.purchase_intent_score + 0.1)
        elif intent == "objection":
            memory.purchase_intent_score = max(0.0, memory.purchase_intent_score - 0.05)

        # Actualizar engagement
        memory.engagement_score = min(1.0, memory.total_messages / 20)

        await self.save(memory)

    async def get_all_for_creator(self, creator_id: str) -> List[FollowerMemory]:
        """Obtener todas las memorias de un creador"""
        creator_dir = os.path.join(self.storage_path, creator_id)
        memories = []

        if os.path.exists(creator_dir):
            for filename in os.listdir(creator_dir):
                if filename.endswith('.json'):
                    follower_id = filename[:-5]
                    memory = await self.get(creator_id, follower_id)
                    if memory:
                        memories.append(memory)

        return memories

    async def get_leads(self, creator_id: str) -> List[FollowerMemory]:
        """Obtener leads de un creador"""
        all_memories = await self.get_all_for_creator(creator_id)
        return [m for m in all_memories if m.is_lead]

    async def get_high_intent(self, creator_id: str, threshold: float = 0.5) -> List[FollowerMemory]:
        """Obtener seguidores con alta intencion de compra"""
        all_memories = await self.get_all_for_creator(creator_id)
        return [m for m in all_memories if m.purchase_intent_score >= threshold]
