"""
User Profiles - Gestión de perfiles, intereses y preferencias por lead.

Permite:
- Trackear intereses del lead automáticamente
- Guardar preferencias de comunicación
- Registrar interacciones (queries, clicks, ratings)
- Obtener perfil para personalizar respuestas
"""
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from datetime import datetime, timezone

logger = logging.getLogger("clonnect.user_profiles")


class UserProfile:
    """
    Perfil de usuario/lead con preferencias e historial de interacciones.

    Uso:
        >>> profile = UserProfile("lead_123", "creator_456")
        >>> profile.add_interest("fitness", weight=2.0)
        >>> profile.set_preference("response_style", "detailed")
        >>> print(profile.get_top_interests(5))
    """

    def __init__(
        self,
        user_id: str,
        creator_id: str,
        storage_path: str = "data/profiles"
    ):
        self.user_id = user_id
        self.creator_id = creator_id
        self.storage_path = Path(storage_path) / creator_id
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.profile_file = self.storage_path / f"{user_id}.json"

        # Default profile structure
        self.profile = {
            "user_id": user_id,
            "creator_id": creator_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),

            # Preferencias de respuesta
            "preferences": {
                "language": "es",
                "response_style": "balanced",  # concise, balanced, detailed
                "communication_tone": "friendly",  # formal, friendly, casual
            },

            # Intereses detectados (topic -> weight)
            "interests": {},

            # Objeciones mencionadas
            "objections": [],

            # Productos de interés
            "interested_products": [],

            # Historial resumido
            "interaction_count": 0,
            "last_interaction": None,

            # Scores de contenido preferido (content_id -> score)
            "content_scores": {}
        }

        self._load()

    def _load(self):
        """Carga perfil desde archivo"""
        try:
            if self.profile_file.exists():
                with open(self.profile_file, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    # Merge con defaults para nuevos campos
                    self.profile.update(saved)
                logger.debug(f"Loaded profile for {self.user_id}")
        except Exception as e:
            logger.error(f"Error loading profile: {e}")

    def _save(self):
        """Guarda perfil a archivo"""
        try:
            self.profile["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(self.profile_file, 'w', encoding='utf-8') as f:
                json.dump(self.profile, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving profile: {e}")

    # === PREFERENCIAS ===

    def set_preference(self, key: str, value: Any):
        """Establece una preferencia"""
        self.profile["preferences"][key] = value
        self._save()

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Obtiene una preferencia"""
        return self.profile["preferences"].get(key, default)

    # === INTERESES ===

    def add_interest(self, topic: str, weight: float = 1.0):
        """
        Añade o incrementa un interés.

        Args:
            topic: Tema de interés (ej: "fitness", "nutrición")
            weight: Peso a añadir (default 1.0)
        """
        topic = topic.lower().strip()
        if topic:
            current = self.profile["interests"].get(topic, 0.0)
            self.profile["interests"][topic] = current + weight
            self._save()

    def get_interests(self) -> Dict[str, float]:
        """Obtiene todos los intereses"""
        return self.profile["interests"].copy()

    def get_top_interests(self, limit: int = 10) -> List[Tuple[str, float]]:
        """Obtiene los principales intereses ordenados por peso"""
        interests = sorted(
            self.profile["interests"].items(),
            key=lambda x: x[1],
            reverse=True
        )
        return interests[:limit]

    def has_interest(self, topic: str) -> bool:
        """Verifica si tiene un interés específico"""
        return topic.lower() in self.profile["interests"]

    # === OBJECIONES ===

    def add_objection(self, objection: str, context: str = None):
        """
        Registra una objeción del lead.

        Args:
            objection: Tipo de objeción (ej: "precio", "tiempo", "no_seguro")
            context: Contexto adicional
        """
        self.profile["objections"].append({
            "type": objection,
            "context": context,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        # Mantener últimas 20 objeciones
        self.profile["objections"] = self.profile["objections"][-20:]
        self._save()

    def get_objections(self) -> List[Dict]:
        """Obtiene historial de objeciones"""
        return self.profile["objections"]

    def has_objection(self, objection_type: str) -> bool:
        """Verifica si ha mencionado cierta objeción"""
        return any(o["type"] == objection_type for o in self.profile["objections"])

    # === PRODUCTOS ===

    def add_interested_product(self, product_id: str, product_name: str = None):
        """Registra interés en un producto"""
        existing = [p for p in self.profile["interested_products"] if p["id"] == product_id]
        if not existing:
            self.profile["interested_products"].append({
                "id": product_id,
                "name": product_name,
                "first_interest": datetime.now(timezone.utc).isoformat(),
                "interest_count": 1
            })
        else:
            existing[0]["interest_count"] = existing[0].get("interest_count", 0) + 1
        self._save()

    def get_interested_products(self) -> List[Dict]:
        """Obtiene productos de interés"""
        return self.profile["interested_products"]

    # === INTERACCIONES ===

    def record_interaction(self):
        """Registra una interacción"""
        self.profile["interaction_count"] += 1
        self.profile["last_interaction"] = datetime.now(timezone.utc).isoformat()
        self._save()

    # === CONTENT SCORES ===

    def boost_content(self, content_id: str, boost: float = 1.0):
        """Incrementa score de un contenido preferido"""
        current = self.profile["content_scores"].get(content_id, 0.0)
        self.profile["content_scores"][content_id] = current + boost
        self._save()

    def get_content_score(self, content_id: str) -> float:
        """Obtiene score de un contenido"""
        return self.profile["content_scores"].get(content_id, 0.0)

    # === EXPORT ===

    def to_dict(self) -> Dict[str, Any]:
        """Exporta perfil como diccionario"""
        return self.profile.copy()

    def get_summary(self) -> Dict[str, Any]:
        """Resumen del perfil para incluir en contexto"""
        return {
            "top_interests": self.get_top_interests(5),
            "recent_objections": [o["type"] for o in self.profile["objections"][-3:]],
            "interested_products": [p["name"] for p in self.profile["interested_products"][:3]],
            "interaction_count": self.profile["interaction_count"],
            "preferences": self.profile["preferences"]
        }


# Cache global de perfiles
_profiles: Dict[str, UserProfile] = {}


def get_user_profile(
    user_id: str,
    creator_id: str,
    storage_path: str = "data/profiles"
) -> UserProfile:
    """
    Obtiene o crea perfil de usuario (singleton por user_id+creator_id).
    """
    cache_key = f"{creator_id}:{user_id}"
    if cache_key not in _profiles:
        _profiles[cache_key] = UserProfile(user_id, creator_id, storage_path)
    return _profiles[cache_key]


def clear_profile_cache():
    """Limpia cache de perfiles"""
    global _profiles
    _profiles = {}
