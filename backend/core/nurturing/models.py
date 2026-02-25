"""
Nurturing Models - Enums, dataclasses, and sequence definitions.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class SequenceType(Enum):
    """Tipos de secuencias de nurturing"""

    INTEREST_COLD = "interest_cold"  # Interés soft sin conversión
    OBJECTION_PRICE = "objection_price"  # Objeción de precio
    OBJECTION_TIME = "objection_time"  # Objeción de tiempo
    OBJECTION_DOUBT = "objection_doubt"  # Dudas generales
    OBJECTION_LATER = "objection_later"  # "Luego te escribo"
    ABANDONED = "abandoned"  # Quiso comprar pero no completó
    RE_ENGAGEMENT = "re_engagement"  # Sin actividad en X días
    POST_PURCHASE = "post_purchase"  # Después de comprar
    # Scarcity/Urgency sequences
    DISCOUNT_URGENCY = "discount_urgency"  # Descuento con fecha límite
    SPOTS_LIMITED = "spots_limited"  # Plazas limitadas
    OFFER_EXPIRING = "offer_expiring"  # Oferta por tiempo limitado
    FLASH_SALE = "flash_sale"  # Venta flash


@dataclass
class FollowUp:
    """Representa un follow-up programado"""

    id: str
    creator_id: str
    follower_id: str
    sequence_type: str
    step: int  # Paso en la secuencia (0, 1, 2...)
    scheduled_at: str  # ISO format datetime
    message_template: str
    status: str = "pending"  # pending, sent, cancelled
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
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
        (
            24,
            "Ey! Vi que te interesaba {product_name}. \u00bfTe qued\u00f3 alguna duda? Estoy aqu\u00ed para ayudarte \U0001f4aa",
        ),
        (
            72,
            "\u00bfQu\u00e9 tal? Solo quer\u00eda recordarte que {product_name} sigue disponible. Si tienes preguntas, escr\u00edbeme sin compromiso.",
        ),
        (
            168,
            "\u00daltima vez que te escribo sobre esto: {product_name} ha ayudado a +200 personas. Si en alg\u00fan momento te interesa, aqu\u00ed estar\u00e9. \u00a1Un abrazo!",
        ),
    ],
    SequenceType.OBJECTION_PRICE.value: [
        (
            48,
            "Hola! Estuve pensando en lo que me dijiste sobre el precio. \u00bfSab\u00edas que {product_name} tiene garant\u00eda de 30 d\u00edas? Si no ves resultados, te devuelvo el dinero. Sin preguntas.",
        ),
    ],
    SequenceType.OBJECTION_TIME.value: [
        (
            48,
            "Ey! Sobre lo del tiempo: {product_name} est\u00e1 dise\u00f1ado para gente ocupada. Son solo 15 min al d\u00eda. \u00bfTe cuento c\u00f3mo funciona?",
        ),
    ],
    SequenceType.OBJECTION_DOUBT.value: [
        (
            24,
            "Hola! \u00bfPudiste pensar en lo que hablamos? Si tienes m\u00e1s dudas sobre {product_name}, aqu\u00ed estoy para resolverlas.",
        ),
    ],
    SequenceType.OBJECTION_LATER.value: [
        (
            48,
            "Ey! \u00bfYa tuviste tiempo de pensarlo? {product_name} sigue aqu\u00ed esper\u00e1ndote. Sin presi\u00f3n, pero si tienes preguntas, escr\u00edbeme.",
        ),
        (
            168,
            "Hola! Hace una semana hablamos de {product_name}. \u00bfSigues interesado? Si cambi\u00f3 algo, cu\u00e9ntame.",
        ),
    ],
    SequenceType.ABANDONED.value: [
        (
            1,
            "Ey! Vi que estabas a punto de apuntarte a {product_name}. \u00bfTe surgi\u00f3 alg\u00fan problema? Te ayudo con lo que necesites.",
        ),
        (
            24,
            "Hola! Solo quer\u00eda asegurarme de que pudiste ver toda la info de {product_name}. Si te qued\u00f3 alguna duda, escr\u00edbeme.",
        ),
    ],
    SequenceType.RE_ENGAGEMENT.value: [
        (0, "\u00a1Hola! Hace tiempo que no hablamos. \u00bfC\u00f3mo va todo? Si necesitas algo, aqu\u00ed estoy."),
    ],
    SequenceType.POST_PURCHASE.value: [
        (
            24,
            "\u00a1Gracias por confiar en m\u00ed! \u00bfYa pudiste empezar con {product_name}? Si tienes dudas, escr\u00edbeme.",
        ),
        (72, "\u00bfQu\u00e9 tal va todo con {product_name}? \u00bfNecesitas ayuda con algo?"),
        (168, "\u00a1Una semana ya! \u00bfC\u00f3mo te est\u00e1 yendo? Me encantar\u00eda saber tu progreso."),
    ],
    # Scarcity/Urgency sequences
    SequenceType.DISCOUNT_URGENCY.value: [
        (
            0,
            "\U0001f525 \u00a1Oferta especial solo para ti! {product_name} con {discount}% de descuento. Solo hasta {expires_at}. {product_link}",
        ),
        (
            24,
            "\u23f0 \u00a1\u00daltimo d\u00eda! El descuento del {discount}% en {product_name} termina hoy. No te lo pierdas \U0001f449 {product_link}",
        ),
    ],
    SequenceType.SPOTS_LIMITED.value: [
        (0, "\U0001f3af Solo quedan {spots_left} plazas para {product_name}. \u00bfTe reservo una? \U0001f440"),
        (
            24,
            "\u26a0\ufe0f Ya solo quedan {spots_left} plazas... Si lo est\u00e1s pensando, es ahora o nunca. {product_link}",
        ),
    ],
    SequenceType.OFFER_EXPIRING.value: [
        (
            0,
            "Hey! La oferta de {product_name} termina en {expires_in}. No quiero que te la pierdas \U0001f64c {product_link}",
        ),
        (
            12,
            "\u23f3 Quedan solo {expires_in} para aprovechar el precio especial de {product_name}. {product_link}",
        ),
    ],
    SequenceType.FLASH_SALE.value: [
        (
            0,
            "\u26a1 FLASH SALE: {product_name} a mitad de precio solo las pr\u00f3ximas {expires_in}. {product_link}",
        ),
    ],
}
