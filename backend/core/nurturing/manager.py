"""
Nurturing Manager - NurturingManager class and factory function.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.nurturing.models import NURTURING_SEQUENCES, FollowUp
from core.nurturing.utils import get_sequence_steps

logger = logging.getLogger(__name__)

# Lazy import for DB storage to avoid circular imports
_db_storage = None
_db_storage_checked = False


def _get_db_storage():
    """Lazy load DB storage module."""
    global _db_storage, _db_storage_checked
    if not _db_storage_checked:
        _db_storage_checked = True
        try:
            from core.nurturing_db import get_nurturing_db_storage, is_db_storage_enabled

            if is_db_storage_enabled():
                _db_storage = get_nurturing_db_storage()
                logger.info("[NURTURING] Database storage enabled (NURTURING_USE_DB=true)")
            else:
                logger.info("[NURTURING] Using JSON file storage (NURTURING_USE_DB=false)")
        except Exception as e:
            logger.warning(f"[NURTURING] DB storage not available: {e}")
    return _db_storage


# Base directory for data files (backend/)
_BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Lazy import for Reflexion to avoid circular imports
_reflexion_improver = None


def _get_reflexion():
    """Lazy load Reflexion improver"""
    global _reflexion_improver
    if _reflexion_improver is None:
        try:
            from core.reasoning import get_reflexion_improver

            _reflexion_improver = get_reflexion_improver()
        except Exception as e:
            logger.warning(f"Could not load Reflexion: {e}")
    return _reflexion_improver


class NurturingManager:
    """Gestiona los follow-ups autom\u00e1ticos de nurturing"""

    def __init__(self, storage_path: str = None):
        # Use absolute path based on _BASE_DIR
        if storage_path is None:
            storage_path = str(_BASE_DIR / "data" / "nurturing")
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        self._cache: Dict[str, List[FollowUp]] = {}
        # Initialize DB storage (lazy loaded)
        self._db_storage = _get_db_storage()

    def _get_file_path(self, creator_id: str) -> str:
        """Obtener ruta del archivo de followups del creador"""
        return os.path.join(self.storage_path, f"{creator_id}_followups.json")

    def _load_followups(self, creator_id: str) -> List[FollowUp]:
        """Cargar followups del creador (DB first, fallback to JSON)"""
        if creator_id in self._cache:
            return self._cache[creator_id]

        # Try DB storage first if available
        if self._db_storage:
            try:
                data = self._db_storage.load_followups(creator_id)
                if data:
                    followups = [FollowUp.from_dict(item) for item in data]
                    self._cache[creator_id] = followups
                    logger.debug(f"[NURTURING] Loaded {len(followups)} from DB for {creator_id}")
                    return followups
            except Exception as e:
                logger.warning(f"[NURTURING] DB load failed, falling back to JSON: {e}")

        # Fallback to JSON file storage
        file_path = self._get_file_path(creator_id)
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    followups = [FollowUp.from_dict(item) for item in data]
                    self._cache[creator_id] = followups
                    return followups
            except Exception as e:
                logger.error(f"Error loading followups for {creator_id}: {e}")

        self._cache[creator_id] = []
        return []

    def _save_followups(self, creator_id: str, followups: List[FollowUp]):
        """Guardar followups del creador (DB + JSON backup)"""
        self._cache[creator_id] = followups

        # Save to DB if available
        db_saved = False
        if self._db_storage:
            try:
                db_saved = self._db_storage.save_followups(creator_id, followups)
                if db_saved:
                    logger.debug(f"[NURTURING] Saved {len(followups)} to DB for {creator_id}")
            except Exception as e:
                logger.warning(f"[NURTURING] DB save failed: {e}")

        # Always save to JSON as backup (or primary if DB disabled)
        file_path = self._get_file_path(creator_id)
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump([fu.to_dict() for fu in followups], f, indent=2, ensure_ascii=False)
            if not db_saved:
                logger.info(f"[NURTURING] Saved {len(followups)} followups to {file_path}")
        except Exception as e:
            logger.error(f"Error saving followups for {creator_id}: {e}")

    def _save_single_followup(self, creator_id: str, followup: FollowUp):
        """Save only a single changed followup (DB upsert + cache update + JSON backup).

        This avoids re-saving ALL followups when only one changed,
        preventing the event loop from blocking on 957+ DB merges.
        """
        # Update cache in-place (already done by caller mutating the object)
        # Save single record to DB
        if self._db_storage:
            try:
                self._db_storage.save_followup(followup)
                logger.debug(f"[NURTURING] Saved single followup {followup.id} to DB")
            except Exception as e:
                logger.warning(f"[NURTURING] DB single save failed: {e}")

        # Save full list to JSON backup (fast local I/O)
        cached = self._cache.get(creator_id)
        if cached is not None:
            file_path = self._get_file_path(creator_id)
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump([fu.to_dict() for fu in cached], f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Error saving JSON backup for {creator_id}: {e}")

    def schedule_followup(
        self,
        creator_id: str,
        follower_id: str,
        sequence_type: str,
        product_name: str = "",
        start_step: int = 0,
    ) -> List[FollowUp]:
        """
        Programar una secuencia de followups.

        Uses custom message templates from creator config if available,
        otherwise falls back to default templates.

        Args:
            creator_id: ID del creador
            follower_id: ID del seguidor
            sequence_type: Tipo de secuencia (de SequenceType)
            product_name: Nombre del producto mencionado
            start_step: Paso inicial de la secuencia

        Returns:
            Lista de followups creados
        """
        # Cancelar followups existentes del mismo tipo
        self.cancel_followups(creator_id, follower_id, sequence_type)

        # Get steps from config (custom) or fall back to defaults
        sequence = get_sequence_steps(creator_id, sequence_type)
        source = "custom config"
        if not sequence:
            # Try default templates
            sequence = NURTURING_SEQUENCES.get(sequence_type, [])
            source = "default NURTURING_SEQUENCES"

        if not sequence:
            logger.warning(f"Unknown sequence type: {sequence_type}")
            return []

        # Log the delays being used
        delays = [f"step{i}={delay_hours}h" for i, (delay_hours, _) in enumerate(sequence)]
        logger.info(f"[NURTURING] Using {source} for '{sequence_type}': {', '.join(delays)}")

        followups = self._load_followups(creator_id)
        created = []
        now = datetime.now(timezone.utc)

        for step, (delay_hours, message_template) in enumerate(
            sequence[start_step:], start=start_step
        ):
            scheduled_time = now + timedelta(hours=delay_hours)
            logger.info(
                f"[NURTURING] Scheduling step {step}: delay={delay_hours}h, now={now.isoformat()}, scheduled={scheduled_time.isoformat()}"
            )
            followup_id = (
                f"{creator_id}_{follower_id}_{sequence_type}_{step}_{int(now.timestamp())}"
            )

            followup = FollowUp(
                id=followup_id,
                creator_id=creator_id,
                follower_id=follower_id,
                sequence_type=sequence_type,
                step=step,
                scheduled_at=scheduled_time.isoformat(),
                message_template=message_template,
                metadata={"product_name": product_name},
            )

            followups.append(followup)
            created.append(followup)
            logger.info(f"Scheduled followup {followup_id} for {scheduled_time}")

        self._save_followups(creator_id, followups)
        logger.info(f"Scheduled {len(created)} {sequence_type} followups for {follower_id}")
        return created

    def get_pending_followups(self, creator_id: str = None) -> List[FollowUp]:
        """
        Obtener followups pendientes que ya deber\u00edan enviarse.

        Args:
            creator_id: Si se especifica, solo de ese creador

        Returns:
            Lista de followups pendientes listos para enviar
        """
        # Try DB first for efficient querying
        if self._db_storage:
            try:
                data = self._db_storage.get_pending_followups(creator_id)
                if data is not None:
                    pending = [FollowUp.from_dict(item) for item in data]
                    logger.info(f"[NURTURING] Found {len(pending)} due followups from DB")
                    return pending
            except Exception as e:
                logger.warning(f"[NURTURING] DB query failed, falling back to JSON: {e}")

        # Fallback to JSON file scanning
        pending = []
        now = datetime.now(timezone.utc)

        if creator_id:
            creators = [creator_id]
        else:
            # Buscar todos los archivos de followups
            creators = []
            logger.info(f"[NURTURING] Looking for followup files in: {self.storage_path}")
            if os.path.exists(self.storage_path):
                files = os.listdir(self.storage_path)
                logger.info(f"[NURTURING] Found files: {files}")
                for file in files:
                    if file.endswith("_followups.json"):
                        creators.append(file.replace("_followups.json", ""))
            else:
                logger.warning(f"[NURTURING] Storage path does not exist: {self.storage_path}")

        logger.info(f"[NURTURING] Checking creators: {creators}")

        for cid in creators:
            followups = self._load_followups(cid)
            logger.info(f"[NURTURING] Creator {cid}: {len(followups)} total followups")
            for fu in followups:
                if fu.status == "pending":
                    scheduled = datetime.fromisoformat(fu.scheduled_at)
                    logger.info(
                        f"[NURTURING] Followup {fu.id}: scheduled={scheduled}, now={now}, due={scheduled <= now}"
                    )
                    if scheduled <= now:
                        pending.append(fu)

        # Ordenar por fecha programada
        pending.sort(key=lambda x: x.scheduled_at)
        logger.info(f"[NURTURING] Found {len(pending)} due followups")
        return pending

    def get_all_followups(self, creator_id: str, status: str = None) -> List[FollowUp]:
        """Obtener todos los followups de un creador"""
        followups = self._load_followups(creator_id)
        if status:
            return [fu for fu in followups if fu.status == status]
        return followups

    def mark_as_sent(self, followup: FollowUp) -> bool:
        """Marcar un followup como enviado"""
        followups = self._load_followups(followup.creator_id)

        for fu in followups:
            if fu.id == followup.id:
                fu.status = "sent"
                fu.sent_at = datetime.now(timezone.utc).isoformat()
                self._save_single_followup(followup.creator_id, fu)
                logger.info(f"Followup {followup.id} marked as sent")
                return True

        return False

    def mark_as_window_expired(self, followup: FollowUp, reason: str = "") -> bool:
        """Mark a followup as window_expired (outside Meta 24h messaging window)"""
        followups = self._load_followups(followup.creator_id)

        for fu in followups:
            if fu.id == followup.id:
                fu.status = "window_expired"
                if reason:
                    fu.metadata["expire_reason"] = reason
                self._save_single_followup(followup.creator_id, fu)
                logger.info(f"Followup {followup.id} marked as window_expired: {reason}")
                return True

        return False

    def cancel_followups(self, creator_id: str, follower_id: str, sequence_type: str = None) -> int:
        """
        Cancelar followups pendientes.

        Args:
            creator_id: ID del creador
            follower_id: ID del seguidor
            sequence_type: Si se especifica, solo cancela ese tipo

        Returns:
            N\u00famero de followups cancelados
        """
        followups = self._load_followups(creator_id)
        cancelled = 0

        for fu in followups:
            if fu.follower_id == follower_id and fu.status == "pending":
                if sequence_type is None or fu.sequence_type == sequence_type:
                    fu.status = "cancelled"
                    cancelled += 1

        if cancelled > 0:
            self._save_followups(creator_id, followups)
            logger.info(f"Cancelled {cancelled} followups for {follower_id}")

        return cancelled

    def cancel_all_for_follower(self, creator_id: str, follower_id: str) -> int:
        """Cancelar todos los followups de un seguidor"""
        return self.cancel_followups(creator_id, follower_id)

    def get_followup_message(self, followup: FollowUp) -> str:
        """Generar el mensaje del followup con variables reemplazadas"""
        message = followup.message_template
        product_name = followup.metadata.get("product_name", "mi producto")

        # Reemplazar variables
        message = message.replace("{product_name}", product_name)

        return message

    async def get_personalized_followup_message(
        self, followup: FollowUp, follower_context: Dict[str, Any] = None
    ) -> str:
        """
        Generate personalized followup message using Reflexion.

        Uses AI to personalize the generic template based on follower context.

        Args:
            followup: The followup to generate message for
            follower_context: Context about the follower (name, interests, etc.)

        Returns:
            Personalized message string
        """
        # First, get the basic rendered message
        base_message = self.get_followup_message(followup)

        # If no context or Reflexion not available, return base message
        if not follower_context:
            return base_message

        reflexion = _get_reflexion()
        if not reflexion:
            return base_message

        try:
            # Prepare context for Reflexion
            context = {
                "follower_name": follower_context.get("name", ""),
                "interests": follower_context.get("interests", []),
                "products_discussed": follower_context.get("products_discussed", []),
                "language": follower_context.get("preferred_language", "es"),
                "sequence_type": followup.sequence_type,
                "step": followup.step,
            }

            # Use Reflexion to personalize
            result = await reflexion.improve_response(
                response=base_message,
                target_quality="personalizado, emp\u00e1tico y natural - no suene rob\u00f3tico",
                context=context,
                min_quality=0.6,
            )

            logger.info(
                f"Reflexion personalized message: quality={result.quality_score:.2f}, "
                f"iterations={result.iterations}"
            )

            return result.final_answer

        except Exception as e:
            logger.warning(f"Reflexion personalization failed: {e}")
            return base_message

    def cleanup_old_followups(self, creator_id: str, days: int = 30) -> int:
        """Eliminar followups antiguos (enviados o cancelados)"""
        followups = self._load_followups(creator_id)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        original_count = len(followups)

        followups = [
            fu
            for fu in followups
            if fu.status == "pending" or datetime.fromisoformat(fu.created_at) > cutoff
        ]

        removed = original_count - len(followups)
        if removed > 0:
            self._save_followups(creator_id, followups)
            logger.info(f"Cleaned up {removed} old followups for {creator_id}")

        return removed

    def get_stats(self, creator_id: str) -> Dict[str, Any]:
        """Obtener estad\u00edsticas de nurturing"""
        followups = self._load_followups(creator_id)

        stats = {
            "total": len(followups),
            "pending": len([fu for fu in followups if fu.status == "pending"]),
            "sent": len([fu for fu in followups if fu.status == "sent"]),
            "cancelled": len([fu for fu in followups if fu.status == "cancelled"]),
            "by_sequence": {},
        }

        for fu in followups:
            seq = fu.sequence_type
            if seq not in stats["by_sequence"]:
                stats["by_sequence"][seq] = {"pending": 0, "sent": 0, "cancelled": 0}
            stats["by_sequence"][seq][fu.status] = stats["by_sequence"][seq].get(fu.status, 0) + 1

        return stats


# Instancia global
_nurturing_manager: Optional[NurturingManager] = None


def get_nurturing_manager() -> NurturingManager:
    """Obtener instancia global del NurturingManager"""
    global _nurturing_manager
    if _nurturing_manager is None:
        _nurturing_manager = NurturingManager()
    return _nurturing_manager
