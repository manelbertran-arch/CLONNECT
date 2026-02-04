"""Repository functions for RelationshipDNA CRUD operations.

Follows the same pattern as api/services/db_service.py for consistency.

Part of RELATIONSHIP-DNA feature.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def get_session():
    """Get database session using the same pattern as db_service."""
    try:
        from api.services.db_service import get_session as db_get_session

        return db_get_session()
    except ImportError:
        logger.error("Could not import get_session from db_service")
        return None


def _dna_to_dict(dna) -> Dict:
    """Convert SQLAlchemy model to dictionary."""
    return {
        "id": str(dna.id),
        "creator_id": dna.creator_id,
        "follower_id": dna.follower_id,
        "relationship_type": dna.relationship_type,
        "trust_score": dna.trust_score,
        "depth_level": dna.depth_level,
        "vocabulary_uses": dna.vocabulary_uses or [],
        "vocabulary_avoids": dna.vocabulary_avoids or [],
        "emojis": dna.emojis or [],
        "avg_message_length": dna.avg_message_length,
        "questions_frequency": dna.questions_frequency,
        "multi_message_frequency": dna.multi_message_frequency,
        "tone_description": dna.tone_description,
        "recurring_topics": dna.recurring_topics or [],
        "private_references": dna.private_references or [],
        "bot_instructions": dna.bot_instructions,
        "golden_examples": dna.golden_examples or [],
        "total_messages_analyzed": dna.total_messages_analyzed or 0,
        "last_analyzed_at": (
            dna.last_analyzed_at.isoformat() if dna.last_analyzed_at else None
        ),
        "version": dna.version or 1,
        "created_at": dna.created_at.isoformat() if dna.created_at else None,
        "updated_at": dna.updated_at.isoformat() if dna.updated_at else None,
    }


def create_relationship_dna(
    creator_id: str,
    follower_id: str,
    relationship_type: str = "DESCONOCIDO",
    trust_score: float = 0.0,
    depth_level: int = 0,
    vocabulary_uses: Optional[List[str]] = None,
    vocabulary_avoids: Optional[List[str]] = None,
    emojis: Optional[List[str]] = None,
    bot_instructions: Optional[str] = None,
    golden_examples: Optional[List[Dict]] = None,
) -> Optional[Dict]:
    """Create a new RelationshipDNA record.

    Args:
        creator_id: Creator identifier
        follower_id: Follower/lead identifier
        relationship_type: One of INTIMA, AMISTAD_CERCANA, AMISTAD_CASUAL,
                          CLIENTE, COLABORADOR, DESCONOCIDO
        trust_score: 0.0-1.0 trust level
        depth_level: 0-4 conversation depth
        vocabulary_uses: Words/phrases to use
        vocabulary_avoids: Words/phrases to avoid
        emojis: Emojis appropriate for this relationship
        bot_instructions: Generated instructions for the bot
        golden_examples: Example exchanges for few-shot learning

    Returns:
        Dict with created record info or None on error
    """
    session = get_session()
    if not session:
        logger.error("create_relationship_dna: no session available")
        return None

    try:
        from api.models import RelationshipDNAModel

        dna = RelationshipDNAModel(
            creator_id=creator_id,
            follower_id=follower_id,
            relationship_type=relationship_type,
            trust_score=trust_score,
            depth_level=depth_level,
            vocabulary_uses=vocabulary_uses or [],
            vocabulary_avoids=vocabulary_avoids or [],
            emojis=emojis or [],
            bot_instructions=bot_instructions,
            golden_examples=golden_examples or [],
        )
        session.add(dna)
        session.commit()

        logger.info(
            f"Created RelationshipDNA for {creator_id}/{follower_id}: {relationship_type}"
        )
        return _dna_to_dict(dna)

    except Exception as e:
        logger.error(f"create_relationship_dna error: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def get_relationship_dna(creator_id: str, follower_id: str) -> Optional[Dict]:
    """Get RelationshipDNA by creator_id and follower_id.

    Args:
        creator_id: Creator identifier
        follower_id: Follower/lead identifier

    Returns:
        Dict with DNA data or None if not found
    """
    session = get_session()
    if not session:
        return None

    try:
        from api.models import RelationshipDNAModel

        dna = (
            session.query(RelationshipDNAModel)
            .filter_by(creator_id=creator_id, follower_id=follower_id)
            .first()
        )

        if dna:
            return _dna_to_dict(dna)
        return None

    except Exception as e:
        logger.error(f"get_relationship_dna error: {e}")
        return None
    finally:
        session.close()


def update_relationship_dna(
    creator_id: str, follower_id: str, data: Dict
) -> bool:
    """Update an existing RelationshipDNA record.

    Args:
        creator_id: Creator identifier
        follower_id: Follower/lead identifier
        data: Dict with fields to update

    Returns:
        True if updated, False if not found or error
    """
    session = get_session()
    if not session:
        return False

    try:
        from api.models import RelationshipDNAModel

        dna = (
            session.query(RelationshipDNAModel)
            .filter_by(creator_id=creator_id, follower_id=follower_id)
            .first()
        )

        if not dna:
            logger.warning(
                f"update_relationship_dna: DNA not found for {creator_id}/{follower_id}"
            )
            return False

        # Update allowed fields
        allowed_fields = {
            "relationship_type",
            "trust_score",
            "depth_level",
            "vocabulary_uses",
            "vocabulary_avoids",
            "emojis",
            "avg_message_length",
            "questions_frequency",
            "multi_message_frequency",
            "tone_description",
            "recurring_topics",
            "private_references",
            "bot_instructions",
            "golden_examples",
            "total_messages_analyzed",
            "last_analyzed_at",
        }

        for key, value in data.items():
            if key in allowed_fields and hasattr(dna, key):
                setattr(dna, key, value)

        # Increment version on update
        dna.version = (dna.version or 1) + 1

        session.commit()
        logger.info(f"Updated RelationshipDNA for {creator_id}/{follower_id}")
        return True

    except Exception as e:
        logger.error(f"update_relationship_dna error: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def get_or_create_relationship_dna(
    creator_id: str, follower_id: str
) -> Optional[Dict]:
    """Get existing DNA or create new one with defaults.

    Args:
        creator_id: Creator identifier
        follower_id: Follower/lead identifier

    Returns:
        Dict with DNA data
    """
    session = get_session()
    if not session:
        return None

    try:
        from api.models import RelationshipDNAModel

        # Try to find existing
        dna = (
            session.query(RelationshipDNAModel)
            .filter_by(creator_id=creator_id, follower_id=follower_id)
            .first()
        )

        if dna:
            return _dna_to_dict(dna)

        # Create new with defaults
        dna = RelationshipDNAModel(
            creator_id=creator_id,
            follower_id=follower_id,
            relationship_type="DESCONOCIDO",
            trust_score=0.0,
            depth_level=0,
            vocabulary_uses=[],
            vocabulary_avoids=[],
            emojis=[],
            golden_examples=[],
        )
        session.add(dna)
        session.commit()

        logger.info(f"Created new RelationshipDNA for {creator_id}/{follower_id}")
        return _dna_to_dict(dna)

    except Exception as e:
        logger.error(f"get_or_create_relationship_dna error: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def list_relationship_dnas_by_creator(creator_id: str) -> List[Dict]:
    """List all RelationshipDNA records for a creator.

    Args:
        creator_id: Creator identifier

    Returns:
        List of DNA dicts
    """
    session = get_session()
    if not session:
        return []

    try:
        from api.models import RelationshipDNAModel

        dnas = (
            session.query(RelationshipDNAModel)
            .filter_by(creator_id=creator_id)
            .all()
        )

        return [_dna_to_dict(dna) for dna in dnas]

    except Exception as e:
        logger.error(f"list_relationship_dnas_by_creator error: {e}")
        return []
    finally:
        session.close()


def delete_relationship_dna(creator_id: str, follower_id: str) -> bool:
    """Delete a RelationshipDNA record.

    Args:
        creator_id: Creator identifier
        follower_id: Follower/lead identifier

    Returns:
        True if deleted, False if not found or error
    """
    session = get_session()
    if not session:
        return False

    try:
        from api.models import RelationshipDNAModel

        dna = (
            session.query(RelationshipDNAModel)
            .filter_by(creator_id=creator_id, follower_id=follower_id)
            .first()
        )

        if not dna:
            logger.warning(
                f"delete_relationship_dna: DNA not found for {creator_id}/{follower_id}"
            )
            return False

        session.delete(dna)
        session.commit()
        logger.info(f"Deleted RelationshipDNA for {creator_id}/{follower_id}")
        return True

    except Exception as e:
        logger.error(f"delete_relationship_dna error: {e}")
        session.rollback()
        return False
    finally:
        session.close()
