"""
Clonnect Creators - API Key Authentication
Sistema de autenticacion basado en API keys por creador
"""

import os
import json
import secrets
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, asdict
from pathlib import Path

logger = logging.getLogger(__name__)

# Prefijo para API keys de Clonnect
API_KEY_PREFIX = "clk_"
API_KEY_LENGTH = 32  # 32 bytes = 64 hex chars


@dataclass
class APIKey:
    """Representa una API key"""
    key_hash: str  # No guardamos la key completa, solo un hash
    key_prefix: str  # Primeros 8 chars para identificar
    creator_id: str
    created_at: str
    last_used: Optional[str] = None
    active: bool = True
    name: Optional[str] = None  # Nombre descriptivo opcional

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'APIKey':
        return cls(**data)


class AuthManager:
    """
    Gestor de autenticacion con API keys.

    Cada creador puede tener multiples API keys.
    Existe una admin key maestra para operaciones privilegiadas.
    """

    def __init__(self, data_path: Optional[str] = None):
        self.data_path = data_path or os.getenv("DATA_PATH", "./data")
        self.auth_dir = Path(self.data_path) / "auth"
        self.keys_file = self.auth_dir / "api_keys.json"

        # Admin key desde variable de entorno
        self.admin_key = os.getenv("CLONNECT_ADMIN_KEY", "")

        # Cache de keys en memoria: full_key -> APIKey
        self._keys_cache: Dict[str, APIKey] = {}

        self._ensure_dirs()
        self._load_keys()

    def _ensure_dirs(self):
        """Crear directorios necesarios"""
        self.auth_dir.mkdir(parents=True, exist_ok=True)

    def _load_keys(self):
        """Cargar keys desde archivo"""
        if not self.keys_file.exists():
            self._save_keys()
            return

        try:
            with open(self.keys_file, 'r') as f:
                data = json.load(f)

            self._keys_cache = {}
            for full_key, key_data in data.get("keys", {}).items():
                self._keys_cache[full_key] = APIKey.from_dict(key_data)

            logger.info(f"Loaded {len(self._keys_cache)} API keys")

        except Exception as e:
            logger.error(f"Error loading API keys: {e}")
            self._keys_cache = {}

    def _save_keys(self):
        """Guardar keys a archivo"""
        try:
            data = {
                "keys": {
                    full_key: key.to_dict()
                    for full_key, key in self._keys_cache.items()
                },
                "updated_at": datetime.now(timezone.utc).isoformat()
            }

            with open(self.keys_file, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Error saving API keys: {e}")

    def _generate_key(self) -> str:
        """Generar una nueva API key unica"""
        random_bytes = secrets.token_hex(API_KEY_LENGTH)
        return f"{API_KEY_PREFIX}{random_bytes}"

    def _hash_key(self, api_key: str) -> str:
        """
        Hash de la API key para almacenamiento.
        Usamos los ultimos 16 chars como 'hash' simple.
        En produccion usar bcrypt o similar.
        """
        import hashlib
        return hashlib.sha256(api_key.encode()).hexdigest()[:16]

    def generate_api_key(
        self,
        creator_id: str,
        name: Optional[str] = None
    ) -> str:
        """
        Genera una nueva API key para un creador.

        Args:
            creator_id: ID del creador
            name: Nombre descriptivo opcional

        Returns:
            La API key completa (solo se muestra una vez)
        """
        full_key = self._generate_key()

        api_key = APIKey(
            key_hash=self._hash_key(full_key),
            key_prefix=full_key[:12],  # clk_ + 8 chars
            creator_id=creator_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            active=True,
            name=name
        )

        self._keys_cache[full_key] = api_key
        self._save_keys()

        logger.info(f"Generated new API key for creator: {creator_id}")
        return full_key

    def validate_api_key(self, api_key: str) -> Optional[str]:
        """
        Valida una API key y retorna el creator_id asociado.

        Args:
            api_key: La API key a validar

        Returns:
            creator_id si es valida, None si no
        """
        if not api_key:
            return None

        # Verificar si es la admin key
        if self.admin_key and api_key == self.admin_key:
            return "__admin__"

        # Buscar en cache
        key_obj = self._keys_cache.get(api_key)

        if not key_obj:
            return None

        if not key_obj.active:
            logger.warning(f"Attempted use of inactive key: {key_obj.key_prefix}...")
            return None

        # Actualizar last_used
        key_obj.last_used = datetime.now(timezone.utc).isoformat()
        self._save_keys()

        return key_obj.creator_id

    def is_admin_key(self, api_key: str) -> bool:
        """Verifica si es la admin key"""
        return bool(self.admin_key and api_key == self.admin_key)

    def revoke_api_key(self, api_key: str) -> bool:
        """
        Revoca una API key (la desactiva).

        Args:
            api_key: La API key a revocar

        Returns:
            True si se revoco, False si no existe
        """
        key_obj = self._keys_cache.get(api_key)

        if not key_obj:
            # Buscar por prefijo
            for full_key, k in self._keys_cache.items():
                if k.key_prefix == api_key or full_key == api_key:
                    key_obj = k
                    api_key = full_key
                    break

        if not key_obj:
            return False

        key_obj.active = False
        self._save_keys()

        logger.info(f"Revoked API key: {key_obj.key_prefix}...")
        return True

    def delete_api_key(self, api_key: str) -> bool:
        """
        Elimina completamente una API key.

        Args:
            api_key: La API key a eliminar

        Returns:
            True si se elimino, False si no existe
        """
        if api_key in self._keys_cache:
            del self._keys_cache[api_key]
            self._save_keys()
            return True

        # Buscar por prefijo
        for full_key, k in list(self._keys_cache.items()):
            if k.key_prefix == api_key:
                del self._keys_cache[full_key]
                self._save_keys()
                return True

        return False

    def list_api_keys(self, creator_id: str) -> List[Dict[str, Any]]:
        """
        Lista las API keys de un creador.

        Args:
            creator_id: ID del creador

        Returns:
            Lista de keys (sin la key completa, solo metadata)
        """
        keys = []
        for full_key, key_obj in self._keys_cache.items():
            if key_obj.creator_id == creator_id:
                keys.append({
                    "key_prefix": key_obj.key_prefix,
                    "name": key_obj.name,
                    "created_at": key_obj.created_at,
                    "last_used": key_obj.last_used,
                    "active": key_obj.active
                })

        # Ordenar por fecha de creacion (mas reciente primero)
        keys.sort(key=lambda x: x["created_at"], reverse=True)
        return keys

    def list_all_keys(self) -> List[Dict[str, Any]]:
        """
        Lista todas las API keys (solo para admin).

        Returns:
            Lista de todas las keys con metadata
        """
        keys = []
        for full_key, key_obj in self._keys_cache.items():
            keys.append({
                "key_prefix": key_obj.key_prefix,
                "creator_id": key_obj.creator_id,
                "name": key_obj.name,
                "created_at": key_obj.created_at,
                "last_used": key_obj.last_used,
                "active": key_obj.active
            })

        keys.sort(key=lambda x: x["created_at"], reverse=True)
        return keys

    def get_key_info(self, api_key: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene informacion de una API key.

        Args:
            api_key: La API key o su prefijo

        Returns:
            Info de la key o None
        """
        key_obj = self._keys_cache.get(api_key)

        if not key_obj:
            # Buscar por prefijo
            for full_key, k in self._keys_cache.items():
                if k.key_prefix == api_key:
                    key_obj = k
                    break

        if not key_obj:
            return None

        return {
            "key_prefix": key_obj.key_prefix,
            "creator_id": key_obj.creator_id,
            "name": key_obj.name,
            "created_at": key_obj.created_at,
            "last_used": key_obj.last_used,
            "active": key_obj.active
        }


# Singleton
_auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    """Obtener instancia singleton del AuthManager"""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager


def validate_api_key(api_key: str) -> Optional[str]:
    """Funcion de conveniencia para validar API key"""
    return get_auth_manager().validate_api_key(api_key)


def is_admin_key(api_key: str) -> bool:
    """Funcion de conveniencia para verificar admin key"""
    return get_auth_manager().is_admin_key(api_key)
