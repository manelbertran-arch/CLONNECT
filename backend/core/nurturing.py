"""
Nurturing Manager - Sistema de follow-ups automáticos para Clonnect Creators.

Gestiona secuencias de mensajes automatizados para:
- Leads que mostraron interés pero no compraron
- Usuarios con objeciones
- Carritos abandonados (preguntaron cómo comprar pero no lo hicieron)
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict, field
from enum import Enum

logger = logging.getLogger(__name__)


class SequenceType(Enum):
    """Tipos de secuencias de nurturing"""
    INTEREST_COLD = "interest_cold"          # Interés soft sin conversión
    OBJECTION_PRICE = "objection_price"      # Objeción de precio
    OBJECTION_TIME = "objection_time"        # Objeción de tiempo
    OBJECTION_DOUBT = "objection_doubt"      # Dudas generales
    OBJECTION_LATER = "objection_later"      # "Luego te escribo"
    ABANDONED = "abandoned"                   # Quiso comprar pero no completó
    RE_ENGAGEMENT = "re_engagement"          # Sin actividad en X días
    POST_PURCHASE = "post_purchase"          # Después de comprar
    # Scarcity/Urgency sequences
    DISCOUNT_URGENCY = "discount_urgency"    # Descuento con fecha límite
    SPOTS_LIMITED = "spots_limited"          # Plazas limitadas
    OFFER_EXPIRING = "offer_expiring"        # Oferta por tiempo limitado
    FLASH_SALE = "flash_sale"                # Venta flash


@dataclass
class FollowUp:
    """Representa un follow-up programado"""
    id: str
    creator_id: str
    follower_id: str
    sequence_type: str
    step: int                                 # Paso en la secuencia (0, 1, 2...)
    scheduled_at: str                         # ISO format datetime
    message_template: str
    status: str = "pending"                   # pending, sent, cancelled
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    sent_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FollowUp":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# Secuencias predefinidas: (delay_hours, mensaje)
NURTURING_SEQUENCES = {
    SequenceType.INTEREST_COLD.value: [
        (24, "Ey! Vi que te interesaba {product_name}. ¿Te quedó alguna duda? Estoy aquí para ayudarte 💪"),
        (72, "¿Qué tal? Solo quería recordarte que {product_name} sigue disponible. Si tienes preguntas, escríbeme sin compromiso."),
        (168, "Última vez que te escribo sobre esto: {product_name} ha ayudado a +200 personas. Si en algún momento te interesa, aquí estaré. ¡Un abrazo!")
    ],
    SequenceType.OBJECTION_PRICE.value: [
        (48, "Hola! Estuve pensando en lo que me dijiste sobre el precio. ¿Sabías que {product_name} tiene garantía de 30 días? Si no ves resultados, te devuelvo el dinero. Sin preguntas."),
    ],
    SequenceType.OBJECTION_TIME.value: [
        (48, "Ey! Sobre lo del tiempo: {product_name} está diseñado para gente ocupada. Son solo 15 min al día. ¿Te cuento cómo funciona?"),
    ],
    SequenceType.OBJECTION_DOUBT.value: [
        (24, "Hola! ¿Pudiste pensar en lo que hablamos? Si tienes más dudas sobre {product_name}, aquí estoy para resolverlas."),
    ],
    SequenceType.OBJECTION_LATER.value: [
        (48, "Ey! ¿Ya tuviste tiempo de pensarlo? {product_name} sigue aquí esperándote. Sin presión, pero si tienes preguntas, escríbeme."),
        (168, "Hola! Hace una semana hablamos de {product_name}. ¿Sigues interesado? Si cambió algo, cuéntame."),
    ],
    SequenceType.ABANDONED.value: [
        (1, "Ey! Vi que estabas a punto de apuntarte a {product_name}. ¿Te surgió algún problema? Te ayudo con lo que necesites."),
        (24, "Hola! Solo quería asegurarme de que pudiste ver toda la info de {product_name}. Si te quedó alguna duda, escríbeme."),
    ],
    SequenceType.RE_ENGAGEMENT.value: [
        (0, "¡Hola! Hace tiempo que no hablamos. ¿Cómo va todo? Si necesitas algo, aquí estoy."),
    ],
    SequenceType.POST_PURCHASE.value: [
        (24, "¡Gracias por confiar en mí! ¿Ya pudiste empezar con {product_name}? Si tienes dudas, escríbeme."),
        (72, "¿Qué tal va todo con {product_name}? ¿Necesitas ayuda con algo?"),
        (168, "¡Una semana ya! ¿Cómo te está yendo? Me encantaría saber tu progreso."),
    ],
    # Scarcity/Urgency sequences
    SequenceType.DISCOUNT_URGENCY.value: [
        (0, "🔥 ¡Oferta especial solo para ti! {product_name} con {discount}% de descuento. Solo hasta {expires_at}. {product_link}"),
        (24, "⏰ ¡Último día! El descuento del {discount}% en {product_name} termina hoy. No te lo pierdas 👉 {product_link}"),
    ],
    SequenceType.SPOTS_LIMITED.value: [
        (0, "🎯 Solo quedan {spots_left} plazas para {product_name}. ¿Te reservo una? 👀"),
        (24, "⚠️ Ya solo quedan {spots_left} plazas... Si lo estás pensando, es ahora o nunca. {product_link}"),
    ],
    SequenceType.OFFER_EXPIRING.value: [
        (0, "Hey! La oferta de {product_name} termina en {expires_in}. No quiero que te la pierdas 🙌 {product_link}"),
        (12, "⏳ Quedan solo {expires_in} para aprovechar el precio especial de {product_name}. {product_link}"),
    ],
    SequenceType.FLASH_SALE.value: [
        (0, "⚡ FLASH SALE: {product_name} a mitad de precio solo las próximas {expires_in}. {product_link}"),
    ],
}


def render_template(template: str, variables: Dict[str, Any]) -> str:
    """
    Render a nurturing template with variables.

    Args:
        template: Template string with {variable} placeholders
        variables: Dict with variable values

    Returns:
        Rendered message string
    """
    try:
        return template.format(**variables)
    except KeyError as e:
        logger.warning(f"Missing variable in template: {e}")
        # Return template with missing vars as-is
        return template


class NurturingManager:
    """Gestiona los follow-ups automáticos de nurturing"""

    def __init__(self, storage_path: str = "data/nurturing"):
        self.storage_path = storage_path
        os.makedirs(storage_path, exist_ok=True)
        self._cache: Dict[str, List[FollowUp]] = {}

    def _get_file_path(self, creator_id: str) -> str:
        """Obtener ruta del archivo de followups del creador"""
        return os.path.join(self.storage_path, f"{creator_id}_followups.json")

    def _load_followups(self, creator_id: str) -> List[FollowUp]:
        """Cargar followups del creador"""
        if creator_id in self._cache:
            return self._cache[creator_id]

        file_path = self._get_file_path(creator_id)
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    followups = [FollowUp.from_dict(item) for item in data]
                    self._cache[creator_id] = followups
                    return followups
            except Exception as e:
                logger.error(f"Error loading followups for {creator_id}: {e}")

        self._cache[creator_id] = []
        return []

    def _save_followups(self, creator_id: str, followups: List[FollowUp]):
        """Guardar followups del creador"""
        self._cache[creator_id] = followups
        file_path = self._get_file_path(creator_id)

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump([fu.to_dict() for fu in followups], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving followups for {creator_id}: {e}")

    def schedule_followup(
        self,
        creator_id: str,
        follower_id: str,
        sequence_type: str,
        product_name: str = "",
        start_step: int = 0
    ) -> List[FollowUp]:
        """
        Programar una secuencia de followups.

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

        sequence = NURTURING_SEQUENCES.get(sequence_type, [])
        if not sequence:
            logger.warning(f"Unknown sequence type: {sequence_type}")
            return []

        followups = self._load_followups(creator_id)
        created = []
        now = datetime.now()

        for step, (delay_hours, message_template) in enumerate(sequence[start_step:], start=start_step):
            scheduled_time = now + timedelta(hours=delay_hours)
            followup_id = f"{creator_id}_{follower_id}_{sequence_type}_{step}_{int(now.timestamp())}"

            followup = FollowUp(
                id=followup_id,
                creator_id=creator_id,
                follower_id=follower_id,
                sequence_type=sequence_type,
                step=step,
                scheduled_at=scheduled_time.isoformat(),
                message_template=message_template,
                metadata={"product_name": product_name}
            )

            followups.append(followup)
            created.append(followup)
            logger.info(f"Scheduled followup {followup_id} for {scheduled_time}")

        self._save_followups(creator_id, followups)
        return created

    def get_pending_followups(self, creator_id: str = None) -> List[FollowUp]:
        """
        Obtener followups pendientes que ya deberían enviarse.

        Args:
            creator_id: Si se especifica, solo de ese creador

        Returns:
            Lista de followups pendientes listos para enviar
        """
        pending = []
        now = datetime.now()

        if creator_id:
            creators = [creator_id]
        else:
            # Buscar todos los archivos de followups
            creators = []
            if os.path.exists(self.storage_path):
                for file in os.listdir(self.storage_path):
                    if file.endswith("_followups.json"):
                        creators.append(file.replace("_followups.json", ""))

        for cid in creators:
            followups = self._load_followups(cid)
            for fu in followups:
                if fu.status == "pending":
                    scheduled = datetime.fromisoformat(fu.scheduled_at)
                    if scheduled <= now:
                        pending.append(fu)

        # Ordenar por fecha programada
        pending.sort(key=lambda x: x.scheduled_at)
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
                fu.sent_at = datetime.now().isoformat()
                self._save_followups(followup.creator_id, followups)
                logger.info(f"Followup {followup.id} marked as sent")
                return True

        return False

    def cancel_followups(
        self,
        creator_id: str,
        follower_id: str,
        sequence_type: str = None
    ) -> int:
        """
        Cancelar followups pendientes.

        Args:
            creator_id: ID del creador
            follower_id: ID del seguidor
            sequence_type: Si se especifica, solo cancela ese tipo

        Returns:
            Número de followups cancelados
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

    def cleanup_old_followups(self, creator_id: str, days: int = 30) -> int:
        """Eliminar followups antiguos (enviados o cancelados)"""
        followups = self._load_followups(creator_id)
        cutoff = datetime.now() - timedelta(days=days)
        original_count = len(followups)

        followups = [
            fu for fu in followups
            if fu.status == "pending" or
               datetime.fromisoformat(fu.created_at) > cutoff
        ]

        removed = original_count - len(followups)
        if removed > 0:
            self._save_followups(creator_id, followups)
            logger.info(f"Cleaned up {removed} old followups for {creator_id}")

        return removed

    def get_stats(self, creator_id: str) -> Dict[str, Any]:
        """Obtener estadísticas de nurturing"""
        followups = self._load_followups(creator_id)

        stats = {
            "total": len(followups),
            "pending": len([fu for fu in followups if fu.status == "pending"]),
            "sent": len([fu for fu in followups if fu.status == "sent"]),
            "cancelled": len([fu for fu in followups if fu.status == "cancelled"]),
            "by_sequence": {}
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


# Mapeo de intents a secuencias
INTENT_TO_SEQUENCE = {
    "interest_soft": SequenceType.INTEREST_COLD.value,
    "objection_price": SequenceType.OBJECTION_PRICE.value,
    "objection_time": SequenceType.OBJECTION_TIME.value,
    "objection_doubt": SequenceType.OBJECTION_DOUBT.value,
    "objection_later": SequenceType.OBJECTION_LATER.value,
    "interest_strong": SequenceType.ABANDONED.value,  # Si no completa, es abandono
}


def should_schedule_nurturing(intent: str, has_purchased: bool = False) -> Optional[str]:
    """
    Determinar si se debe programar nurturing basado en el intent.

    Args:
        intent: Intent del mensaje
        has_purchased: Si el usuario ya compró

    Returns:
        Tipo de secuencia a programar, o None
    """
    if has_purchased:
        return None

    return INTENT_TO_SEQUENCE.get(intent)
