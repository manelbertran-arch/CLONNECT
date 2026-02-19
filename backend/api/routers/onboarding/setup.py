"""Full reset endpoint for testing/development."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends

from api.auth import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.delete("/full-reset/{creator_id}")
async def full_reset_creator(
    creator_id: str,
    email: Optional[str] = None,
    confirm: str = None,
    admin: str = Depends(require_admin),
):
    """
    Delete ALL data for a creator. Use for testing/starting fresh.

    Requires admin API key (X-API-Key header).
    DANGER: Requires confirmation parameter.

    Deletes:
    - Creator record from DB
    - User record (if email provided)
    - All leads and messages
    - All products
    - Instagram posts
    - Content chunks (RAG)
    - ToneProfile
    - ContentIndex files

    WARNING: This is destructive and cannot be undone!

    Usage:
        DELETE /onboarding/full-reset/stefano_bonanno?confirm=DELETE_EVERYTHING&email=stefano@fitpackglobal.com
    """
    # SAFETY: Require explicit confirmation
    if confirm != "DELETE_EVERYTHING":
        return {
            "error": "Safety check failed",
            "usage": f"DELETE /onboarding/full-reset/{creator_id}?confirm=DELETE_EVERYTHING",
            "warning": "This will PERMANENTLY delete ALL data for this creator. Cannot be undone.",
        }

    logger.warning(f"[DANGER] full_reset_creator called for {creator_id} (email={email})")

    deleted = {
        "creator": False,
        "user": False,
        "leads": 0,
        "messages": 0,
        "products": 0,
        "instagram_posts": 0,
        "content_chunks": 0,
        "tone_profile": False,
        "content_index": False,
    }
    errors = []

    try:
        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Message, Product, UserCreator

        if not DATABASE_URL or not SessionLocal:
            return {"success": False, "error": "Database not configured"}

        session = SessionLocal()
        try:
            # Find creator by name
            creator = session.query(Creator).filter_by(name=creator_id).first()

            if creator:
                creator_uuid = creator.id

                # Delete messages for all leads
                leads = session.query(Lead).filter_by(creator_id=creator_uuid).all()
                for lead in leads:
                    msg_count = session.query(Message).filter_by(lead_id=lead.id).delete()
                    deleted["messages"] += msg_count

                # Delete leads
                deleted["leads"] = session.query(Lead).filter_by(creator_id=creator_uuid).delete()

                # Delete products
                deleted["products"] = (
                    session.query(Product).filter_by(creator_id=creator_uuid).delete()
                )

                # Delete user_creators relationships (MUST be before creator delete)
                user_creators_deleted = (
                    session.query(UserCreator).filter_by(creator_id=creator_uuid).delete()
                )
                logger.info(
                    f"[FullReset] Deleted {user_creators_deleted} user_creators relationships"
                )

                # Delete creator
                session.delete(creator)
                deleted["creator"] = True

                logger.info(f"[FullReset] Deleted creator {creator_id} and related data")

            # Delete user by email if provided
            if email:
                try:
                    from api.models import User

                    user = session.query(User).filter_by(email=email).first()
                    if user:
                        session.delete(user)
                        deleted["user"] = True
                        logger.info(f"[FullReset] Deleted user {email}")
                except Exception as e:
                    errors.append(f"User deletion failed: {str(e)}")

            session.commit()

        finally:
            session.close()

        # Delete Instagram posts from DB
        try:
            from core.tone_profile_db import delete_content_chunks_db, delete_instagram_posts_db

            posts_deleted = await delete_instagram_posts_db(creator_id)
            deleted["instagram_posts"] = posts_deleted or 0

            chunks_deleted = await delete_content_chunks_db(creator_id)
            deleted["content_chunks"] = chunks_deleted or 0

        except Exception as e:
            errors.append(f"Instagram/chunks deletion failed: {str(e)}")

        # Delete ToneProfile
        try:
            from core.tone_service import delete_tone_profile

            deleted["tone_profile"] = delete_tone_profile(creator_id)
        except Exception as e:
            errors.append(f"ToneProfile deletion failed: {str(e)}")

        # Delete ContentIndex files
        try:
            from core.citation_service import delete_content_index

            deleted["content_index"] = delete_content_index(creator_id)
        except Exception as e:
            errors.append(f"ContentIndex deletion failed: {str(e)}")

        # Delete local data files
        try:
            import shutil
            from pathlib import Path

            paths_to_delete = [
                Path(f"data/content_index/{creator_id}"),
                Path(f"data/tone_profiles/{creator_id}.json"),
                Path(f"data/creators/{creator_id}_config.json"),
                Path(f"data/products/{creator_id}_products.json"),
                Path(f"data/followers/{creator_id}"),
            ]

            for path in paths_to_delete:
                if path.exists():
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    logger.info(f"[FullReset] Deleted {path}")

        except Exception as e:
            errors.append(f"File deletion failed: {str(e)}")

        return {
            "success": True,
            "creator_id": creator_id,
            "email": email,
            "deleted": deleted,
            "errors": errors if errors else None,
        }

    except Exception as e:
        logger.error(f"[FullReset] Error: {e}")
        import traceback

        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}
