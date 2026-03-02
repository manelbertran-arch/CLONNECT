"""Repository functions for RelationshipDNA CRUD operations.

Follows the same pattern as api/services/db_service.py for consistency.
Falls back to JSON file storage when database is not available.

Part of RELATIONSHIP-DNA feature.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# JSON file storage path
DNA_BASE_DIR = Path(__file__).parent.parent / "data" / "relationship_dna"


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
        "last_analyzed_at": (dna.last_analyzed_at.isoformat() if dna.last_analyzed_at else None),
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
        from sqlalchemy.exc import IntegrityError

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

        logger.info(f"Created RelationshipDNA for {creator_id}/{follower_id}: {relationship_type}")
        return _dna_to_dict(dna)

    except IntegrityError:
        # Race condition: another request created this DNA concurrently.
        # Return the existing record instead.
        session.rollback()
        logger.info(f"RelationshipDNA already exists for {creator_id}/{follower_id} (concurrent create)")
        try:
            existing = session.query(RelationshipDNAModel).filter_by(
                creator_id=creator_id, follower_id=follower_id
            ).first()
            return _dna_to_dict(existing) if existing else None
        except Exception:
            return None
    except Exception as e:
        logger.error(f"create_relationship_dna error: {e}")
        session.rollback()
        return None
    finally:
        session.close()


def _get_dna_from_json(creator_id: str, follower_id: str) -> Optional[Dict]:
    """Get DNA from JSON file storage.

    Args:
        creator_id: Creator identifier
        follower_id: Follower/lead identifier

    Returns:
        Dict with DNA data or None if not found
    """
    # Build possible file paths
    creator_dir = DNA_BASE_DIR / creator_id
    if not creator_dir.exists():
        return None

    # Try different follower_id formats
    follower_ids_to_try = [follower_id]
    if "_" in follower_id:
        without_prefix = follower_id.split("_", 1)[1]
        follower_ids_to_try.append(without_prefix)
    else:
        follower_ids_to_try.append(f"ig_{follower_id}")

    for fid in follower_ids_to_try:
        json_path = creator_dir / f"{fid}.json"
        if json_path.exists():
            try:
                with open(json_path) as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error reading DNA JSON {json_path}: {e}")
                continue

    return None


def get_relationship_dna(creator_id: str, follower_id: str) -> Optional[Dict]:
    """Get RelationshipDNA by creator_id and follower_id.

    Handles both formats of follower_id:
    - With platform prefix: "ig_687843303852230"
    - Without prefix: "687843303852230"

    Falls back to JSON file storage when database is not available.

    Args:
        creator_id: Creator identifier
        follower_id: Follower/lead identifier

    Returns:
        Dict with DNA data or None if not found
    """
    session = get_session()

    # If no database session, try JSON files
    if not session:
        return _get_dna_from_json(creator_id, follower_id)

    try:
        from api.models import RelationshipDNAModel

        # Normalize follower_id - try both with and without prefix
        follower_ids_to_try = [follower_id]

        # If has prefix (ig_, wa_, etc.), also try without
        if "_" in follower_id:
            without_prefix = follower_id.split("_", 1)[1]
            follower_ids_to_try.append(without_prefix)
        else:
            # If no prefix, also try with common prefixes
            follower_ids_to_try.append(f"ig_{follower_id}")

        for fid in follower_ids_to_try:
            dna = (
                session.query(RelationshipDNAModel)
                .filter_by(creator_id=creator_id, follower_id=fid)
                .first()
            )
            if dna:
                return _dna_to_dict(dna)

        # If not in database, try JSON files as fallback
        return _get_dna_from_json(creator_id, follower_id)

    except Exception as e:
        logger.error(f"get_relationship_dna error: {e}")
        # Try JSON as last resort
        return _get_dna_from_json(creator_id, follower_id)
    finally:
        session.close()


def update_relationship_dna(creator_id: str, follower_id: str, data: Dict) -> bool:
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
            logger.warning(f"update_relationship_dna: DNA not found for {creator_id}/{follower_id}")
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


def get_or_create_relationship_dna(creator_id: str, follower_id: str) -> Optional[Dict]:
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


def _list_dnas_from_json(creator_id: str) -> List[Dict]:
    """List all DNA records from JSON files for a creator.

    Args:
        creator_id: Creator identifier

    Returns:
        List of DNA dicts
    """
    creator_dir = DNA_BASE_DIR / creator_id
    if not creator_dir.exists():
        return []

    dnas = []
    for json_file in creator_dir.glob("*.json"):
        try:
            with open(json_file) as f:
                dnas.append(json.load(f))
        except Exception as e:
            logger.error(f"Error reading DNA JSON {json_file}: {e}")
            continue

    return dnas


def list_relationship_dnas_by_creator(creator_id: str) -> List[Dict]:
    """List all RelationshipDNA records for a creator.

    Falls back to JSON file storage when database is not available.

    Args:
        creator_id: Creator identifier

    Returns:
        List of DNA dicts
    """
    session = get_session()

    # If no database session, try JSON files
    if not session:
        return _list_dnas_from_json(creator_id)

    try:
        from api.models import RelationshipDNAModel

        dnas = session.query(RelationshipDNAModel).filter_by(creator_id=creator_id).limit(100).all()

        db_dnas = [_dna_to_dict(dna) for dna in dnas]

        # Also include JSON files (for local development)
        json_dnas = _list_dnas_from_json(creator_id)

        # Merge, preferring database records
        seen_ids = {d["follower_id"] for d in db_dnas}
        for jd in json_dnas:
            if jd.get("follower_id") not in seen_ids:
                db_dnas.append(jd)

        return db_dnas

    except Exception as e:
        logger.error(f"list_relationship_dnas_by_creator error: {e}")
        return _list_dnas_from_json(creator_id)
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
            logger.warning(f"delete_relationship_dna: DNA not found for {creator_id}/{follower_id}")
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
