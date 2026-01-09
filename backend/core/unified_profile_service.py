"""
Unified Profile Service - Cross-platform identity & email capture.

El bot solo ofrece lo que el creador configura:
- none: Solo memoria/servicio
- discount: Codigo de descuento
- content: Contenido exclusivo
- priority: Lista prioritaria
- custom: Mensaje personalizado
"""

import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Regex para detectar email en texto
EMAIL_REGEX = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'


@dataclass
class EmailAskDecision:
    """Decision about whether to ask for email."""
    should_ask: bool
    message: str
    reason: str


# =============================================================================
# MENSAJES SEGUN OFFER_TYPE
# =============================================================================

def get_ask_message_by_offer_type(offer_type: str, offer_config: Dict = None) -> str:
    """
    Genera mensaje de ask segun el tipo de oferta configurada.

    REGLA ESTRICTA: NUNCA usar valores por defecto que el creador no configuro.
    Si falta config requerida → fallback a mensaje basico (solo memoria).
    """
    offer_config = offer_config or {}

    # Mensaje basico - solo memoria/servicio (SAFE DEFAULT)
    BASE_MESSAGE = (
        "Por cierto, si me dejas tu email puedo recordar nuestras conversaciones "
        "y darte mejor atencion. Asi no tenes que repetirme las cosas 😊 ¿Te parece?"
    )

    if offer_type == "none" or not offer_type:
        return BASE_MESSAGE

    elif offer_type == "discount":
        # REQUIERE: percent Y code configurados explicitamente
        percent = offer_config.get("percent")
        code = offer_config.get("code")
        if percent and code:
            return (
                f"Si me dejas tu email te envio un codigo de {percent}% de descuento "
                "para cuando decidas dar el paso. Ademas asi puedo recordar lo que hablamos "
                "y atenderte mejor. ¿Que decis?"
            )
        # Config incompleta → fallback a mensaje basico
        logger.warning(f"discount config incompleta: percent={percent}, code={code}")
        return BASE_MESSAGE

    elif offer_type == "content":
        # REQUIERE: description configurada explicitamente
        description = offer_config.get("description")
        if description:
            return (
                f"Si me das tu email, te envio {description} que no comparto en redes. "
                "Tambien me ayuda a recordar nuestras conversaciones. ¿Te interesa?"
            )
        # Config incompleta → fallback
        logger.warning(f"content config incompleta: description={description}")
        return BASE_MESSAGE

    elif offer_type == "priority":
        # REQUIERE: description configurada explicitamente
        description = offer_config.get("description")
        if description:
            return (
                f"¿Queres que te avise antes que a nadie sobre {description}? "
                "Dejame tu email y te pongo en mi lista prioritaria. "
                "Ademas asi puedo recordar lo que hablamos 👍"
            )
        # Config incompleta → fallback
        logger.warning(f"priority config incompleta: description={description}")
        return BASE_MESSAGE

    elif offer_type == "custom":
        # REQUIERE: message configurado explicitamente
        message = offer_config.get("message")
        if message:
            return f"{message}\n\n¿Me dejas tu email?"
        # Config incompleta → fallback
        logger.warning(f"custom config incompleta: message={message}")
        return BASE_MESSAGE

    return BASE_MESSAGE


def get_captured_message(name: str, offer_type: str, offer_config: Dict = None) -> str:
    """
    Genera mensaje cuando capturamos el email segun configuracion.

    REGLA ESTRICTA: Solo mencionar ofertas si el creador las configuro explicitamente.
    """
    offer_config = offer_config or {}
    name_part = f" {name}" if name else ""

    # Base message - siempre igual
    base = (
        f"¡Genial{name_part}! Ya te tengo 😊\n\n"
        "A partir de ahora voy a recordar quien sos y lo que hablamos.\n"
        "Si me escribis desde otra app, decime tu email y seguimos donde lo dejamos."
    )

    # Añadir SOLO si la config esta completa
    if offer_type == "discount":
        code = offer_config.get("code")
        percent = offer_config.get("percent")
        # Solo mencionar si AMBOS estan configurados
        if code and percent:
            base += f"\n\n🎁 Te envio el codigo {code} ({percent}% off) a tu correo."

    elif offer_type == "content":
        description = offer_config.get("description")
        # Solo mencionar si description esta configurada
        if description:
            base += f"\n\n📩 Te envio {description} a tu correo."

    return base


CROSS_PLATFORM_NEW_USER = (
    "¡Hola! ¿Ya hemos hablado antes por otro lado? "
    "Si me decis tu email puedo recuperar nuestra conversacion y seguir donde lo dejamos. "
    "Si es primera vez, ¡encantado de conocerte! 😊"
)

CROSS_PLATFORM_RECOGNIZED = (
    "¡{name}! Que bueno verte por aca tambien 🙌\n\n"
    "La ultima vez hablamos de {topic}. ¿Seguimos por ahi o en que te ayudo?"
)


# =============================================================================
# FUNCIONES DE EXTRACCION
# =============================================================================

def extract_email(text: str) -> Optional[str]:
    """Extrae el primer email encontrado en un texto."""
    if not text:
        return None
    match = re.search(EMAIL_REGEX, text.lower())
    return match.group(0) if match else None


def extract_name_from_text(text: str) -> Optional[str]:
    """Extrae nombre si el usuario se presenta."""
    patterns = [
        r'(?:me llamo|soy|mi nombre es)\s+([A-Z][a-z]+)',
        r"(?:i'm|i am|my name is)\s+([A-Z][a-z]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).capitalize()
    return None


# =============================================================================
# UNIFIED PROFILE FUNCTIONS
# =============================================================================

def get_unified_profile(platform: str, platform_user_id: str) -> Optional[Dict[str, Any]]:
    """
    Busca si el usuario tiene un perfil unificado (ya dio su email).
    """
    try:
        from api.database import SessionLocal
        from api.models import PlatformIdentity, UnifiedProfile

        session = SessionLocal()
        try:
            identity = session.query(PlatformIdentity).filter_by(
                platform=platform,
                platform_user_id=platform_user_id
            ).first()

            if identity and identity.unified_profile_id:
                profile = session.query(UnifiedProfile).filter_by(
                    id=identity.unified_profile_id
                ).first()
                if profile:
                    return {
                        "id": str(profile.id),
                        "email": profile.email,
                        "name": profile.name,
                        "phone": profile.phone
                    }
            return None
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error getting unified profile: {e}")
        return None


def get_unified_profile_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Busca perfil unificado por email."""
    try:
        from api.database import SessionLocal
        from api.models import UnifiedProfile

        session = SessionLocal()
        try:
            profile = session.query(UnifiedProfile).filter_by(
                email=email.lower()
            ).first()
            if profile:
                return {
                    "id": str(profile.id),
                    "email": profile.email,
                    "name": profile.name,
                    "phone": profile.phone
                }
            return None
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error getting profile by email: {e}")
        return None


def create_unified_profile(
    email: str,
    name: str = None,
    phone: str = None
) -> Dict[str, Any]:
    """Crea un nuevo perfil unificado."""
    try:
        from api.database import SessionLocal
        from api.models import UnifiedProfile

        session = SessionLocal()
        try:
            # Check if exists
            existing = session.query(UnifiedProfile).filter_by(
                email=email.lower()
            ).first()
            if existing:
                return {
                    "id": str(existing.id),
                    "email": existing.email,
                    "name": existing.name,
                    "is_new": False
                }

            profile = UnifiedProfile(
                email=email.lower(),
                name=name,
                phone=phone
            )
            session.add(profile)
            session.commit()

            logger.info(f"Created unified profile for {email}")
            return {
                "id": str(profile.id),
                "email": profile.email,
                "name": profile.name,
                "is_new": True
            }
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error creating unified profile: {e}")
        return {"error": str(e)}


def link_platform_identity(
    unified_profile_id: str,
    platform: str,
    platform_user_id: str,
    username: str = None
) -> bool:
    """Vincula una identidad de plataforma a un perfil unificado."""
    try:
        from api.database import SessionLocal
        from api.models import PlatformIdentity
        from uuid import UUID

        session = SessionLocal()
        try:
            # Check if identity exists
            identity = session.query(PlatformIdentity).filter_by(
                platform=platform,
                platform_user_id=platform_user_id
            ).first()

            if identity:
                identity.unified_profile_id = UUID(unified_profile_id)
                if username:
                    identity.username = username
            else:
                identity = PlatformIdentity(
                    unified_profile_id=UUID(unified_profile_id),
                    platform=platform,
                    platform_user_id=platform_user_id,
                    username=username
                )
                session.add(identity)

            session.commit()
            logger.info(f"Linked {platform}:{platform_user_id} to profile {unified_profile_id}")
            return True
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error linking platform identity: {e}")
        return False


def get_all_platform_identities(unified_profile_id: str) -> List[Dict[str, Any]]:
    """Obtiene todas las identidades de plataforma de un perfil."""
    try:
        from api.database import SessionLocal
        from api.models import PlatformIdentity
        from uuid import UUID

        session = SessionLocal()
        try:
            identities = session.query(PlatformIdentity).filter_by(
                unified_profile_id=UUID(unified_profile_id)
            ).all()

            return [
                {
                    "platform": i.platform,
                    "platform_user_id": i.platform_user_id,
                    "username": i.username
                }
                for i in identities
            ]
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error getting platform identities: {e}")
        return []


# =============================================================================
# EMAIL ASK TRACKING
# =============================================================================

def get_email_ask_tracking(platform: str, platform_user_id: str) -> Dict[str, Any]:
    """Obtiene el estado de tracking de email ask."""
    try:
        from api.database import SessionLocal
        from api.models import EmailAskTracking

        session = SessionLocal()
        try:
            tracking = session.query(EmailAskTracking).filter_by(
                platform=platform,
                platform_user_id=platform_user_id
            ).first()

            if tracking:
                return {
                    "ask_count": tracking.ask_level,  # Reusing ask_level as ask_count
                    "last_asked_at": tracking.last_asked_at.isoformat() if tracking.last_asked_at else None,
                    "captured_email": tracking.captured_email
                }
            return {"ask_count": 0, "last_asked_at": None, "captured_email": None}
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error getting email ask tracking: {e}")
        return {"ask_count": 0}


def record_email_ask(platform: str, platform_user_id: str, creator_id: str):
    """Registra que pedimos email."""
    try:
        from api.database import SessionLocal
        from api.models import EmailAskTracking, Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return

            tracking = session.query(EmailAskTracking).filter_by(
                platform=platform,
                platform_user_id=platform_user_id
            ).first()

            if not tracking:
                tracking = EmailAskTracking(
                    creator_id=creator.id,
                    platform=platform,
                    platform_user_id=platform_user_id,
                    ask_level=1,
                    last_asked_at=datetime.now(timezone.utc)
                )
                session.add(tracking)
            else:
                tracking.ask_level += 1
                tracking.last_asked_at = datetime.now(timezone.utc)

            session.commit()
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error recording email ask: {e}")


def mark_email_captured(platform: str, platform_user_id: str, email: str):
    """Marca que capturamos el email."""
    try:
        from api.database import SessionLocal
        from api.models import EmailAskTracking

        session = SessionLocal()
        try:
            tracking = session.query(EmailAskTracking).filter_by(
                platform=platform,
                platform_user_id=platform_user_id
            ).first()

            if tracking:
                tracking.captured_email = email.lower()
                tracking.updated_at = datetime.now(timezone.utc)
                session.commit()
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error marking email captured: {e}")


# =============================================================================
# DECISION LOGIC
# =============================================================================

def get_creator_email_config(creator_id: str) -> Dict[str, Any]:
    """
    Obtiene la configuracion de email capture del creator.

    REGLA ESTRICTA: Si el creador NO configura email_capture,
    el bot NUNCA pide email (enabled=False por defecto).
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if creator and creator.email_capture_config:
                # Creador tiene config explicita
                return creator.email_capture_config
            # NO HAY CONFIG = NO PEDIR EMAIL
            return {
                "enabled": False,
                "ask_after_messages": 3,
                "offer_type": "none",
                "offer_config": None
            }
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error getting email config: {e}")
        # Error = NO pedir email (safe default)
        return {"enabled": False, "ask_after_messages": 3, "offer_type": "none"}


def should_ask_email(
    platform: str,
    platform_user_id: str,
    creator_id: str,
    intent: str,
    message_count: int
) -> EmailAskDecision:
    """
    Decide si debemos pedir email.

    Returns:
        EmailAskDecision con should_ask, message, reason
    """
    # Get config
    config = get_creator_email_config(creator_id)

    # REGLA ESTRICTA: Si enabled no es explicitamente True, NO pedir
    if not config.get("enabled", False):
        return EmailAskDecision(False, "", "disabled")

    # Check if already has email
    profile = get_unified_profile(platform, platform_user_id)
    if profile:
        return EmailAskDecision(False, "", "already_has_email")

    # Check tracking
    tracking = get_email_ask_tracking(platform, platform_user_id)
    if tracking.get("captured_email"):
        return EmailAskDecision(False, "", "email_already_captured")

    # Check if asked recently (last 24h)
    last_asked = tracking.get("last_asked_at")
    if last_asked:
        try:
            last_asked_dt = datetime.fromisoformat(last_asked.replace('Z', '+00:00'))
            if datetime.now(timezone.utc) - last_asked_dt < timedelta(hours=24):
                return EmailAskDecision(False, "", "asked_recently")
        except:
            pass

    # Check conditions
    ask_after = config.get("ask_after_messages", 3)
    offer_type = config.get("offer_type", "none")
    offer_config = config.get("offer_config")

    # High intent triggers immediate ask
    high_intent = intent.lower() in [
        "purchase", "pricing", "booking",
        "interest_strong", "question_product"
    ]

    should_ask = message_count >= ask_after or high_intent

    if should_ask:
        message = get_ask_message_by_offer_type(offer_type, offer_config)
        reason = "high_intent" if high_intent else "message_threshold"
        return EmailAskDecision(True, message, reason)

    return EmailAskDecision(False, "", "no_trigger")


def process_email_capture(
    email: str,
    platform: str,
    platform_user_id: str,
    creator_id: str,
    name: str = None
) -> Dict[str, Any]:
    """
    Procesa la captura de un email.
    Crea o vincula perfil unificado.

    Returns:
        Dict con profile info y response message
    """
    config = get_creator_email_config(creator_id)
    offer_type = config.get("offer_type", "none")
    offer_config = config.get("offer_config")

    # Check if profile exists
    existing = get_unified_profile_by_email(email)

    if existing:
        # Link this platform to existing profile
        link_platform_identity(
            existing["id"],
            platform,
            platform_user_id
        )
        mark_email_captured(platform, platform_user_id, email)

        # Generate recognition message
        response = CROSS_PLATFORM_RECOGNIZED.format(
            name=existing.get("name") or name or "",
            topic="lo que estabamos viendo"
        )
        return {
            "profile": existing,
            "is_new": False,
            "response": response
        }
    else:
        # Create new profile
        result = create_unified_profile(email, name)
        if result.get("error"):
            return {"error": result["error"]}

        # Link platform
        link_platform_identity(
            result["id"],
            platform,
            platform_user_id
        )
        mark_email_captured(platform, platform_user_id, email)

        # Generate captured message
        response = get_captured_message(name, offer_type, offer_config)
        return {
            "profile": result,
            "is_new": True,
            "response": response
        }


def get_cross_platform_context(
    unified_profile_id: str,
    creator_id: str,
    current_platform: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Obtiene contexto de conversaciones en otras plataformas.
    """
    try:
        from api.database import SessionLocal
        from api.models import PlatformIdentity, Lead, Message, Creator
        from uuid import UUID

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return []

            # Get identities from OTHER platforms
            identities = session.query(PlatformIdentity).filter(
                PlatformIdentity.unified_profile_id == UUID(unified_profile_id),
                PlatformIdentity.platform != current_platform
            ).all()

            all_messages = []
            for identity in identities:
                lead = session.query(Lead).filter_by(
                    creator_id=creator.id,
                    platform=identity.platform,
                    platform_user_id=identity.platform_user_id
                ).first()

                if lead:
                    messages = session.query(Message).filter_by(
                        lead_id=lead.id
                    ).order_by(Message.created_at.desc()).limit(limit).all()

                    for msg in messages:
                        all_messages.append({
                            "platform": identity.platform,
                            "role": msg.role,
                            "content": msg.content,
                            "created_at": msg.created_at.isoformat() if msg.created_at else None
                        })

            all_messages.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return all_messages[:limit]
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error getting cross-platform context: {e}")
        return []
