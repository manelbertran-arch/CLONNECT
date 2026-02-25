"""Database migrations, ingestion testing, and backup endpoints."""
import json
import logging
import os

from api.auth import require_admin
from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/run-migration/email-capture")
async def run_email_capture_migration(admin: str = Depends(require_admin)):
    """
    Run migration to add email capture tables and columns.
    Safe to run multiple times (uses IF NOT EXISTS).
    """
    try:
        from api.database import SessionLocal
        from sqlalchemy import text

        session = SessionLocal()
        try:
            # Add email_capture_config column
            session.execute(
                text(
                    """
                ALTER TABLE creators
                ADD COLUMN IF NOT EXISTS email_capture_config JSONB DEFAULT NULL
            """
                )
            )

            # Create unified_profiles table
            session.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS unified_profiles (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    email VARCHAR(255) UNIQUE NOT NULL,
                    name VARCHAR(255),
                    phone VARCHAR(50),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """
                )
            )

            # Create platform_identities table
            session.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS platform_identities (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    unified_profile_id UUID REFERENCES unified_profiles(id),
                    creator_id UUID REFERENCES creators(id),
                    platform VARCHAR(50) NOT NULL,
                    platform_user_id VARCHAR(255) NOT NULL,
                    username VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """
                )
            )

            # Create unique index
            session.execute(
                text(
                    """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_platform_identity_unique
                ON platform_identities(platform, platform_user_id)
            """
                )
            )

            # Create email_ask_tracking table
            session.execute(
                text(
                    """
                CREATE TABLE IF NOT EXISTS email_ask_tracking (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    creator_id UUID REFERENCES creators(id),
                    platform VARCHAR(50) NOT NULL,
                    platform_user_id VARCHAR(255) NOT NULL,
                    ask_level INTEGER DEFAULT 0,
                    last_asked_at TIMESTAMP WITH TIME ZONE,
                    declined_count INTEGER DEFAULT 0,
                    captured_email VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """
                )
            )

            # Create index for fast lookups
            session.execute(
                text(
                    """
                CREATE INDEX IF NOT EXISTS idx_email_ask_tracking_lookup
                ON email_ask_tracking(platform, platform_user_id)
            """
                )
            )

            session.commit()
            logger.info("Email capture migration completed successfully")

            return {
                "status": "success",
                "message": "Migration completed",
                "tables_created": ["unified_profiles", "platform_identities", "email_ask_tracking"],
                "columns_added": ["creators.email_capture_config"],
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return {"status": "error", "error": str(e)}


@router.post("/test-ingestion-v2/{creator_id}")
async def test_ingestion_v2(creator_id: str, website_url: str, admin: str = Depends(require_admin)):
    """
    Test endpoint to run IngestionV2Pipeline directly.

    Usage: POST /admin/test-ingestion-v2/stefano?website_url=https://stefanobonanno.com
    """
    try:
        from api.database import SessionLocal
        from ingestion.v2.pipeline import IngestionV2Pipeline

        session = SessionLocal()
        try:
            pipeline = IngestionV2Pipeline(db_session=session)
            result = await pipeline.run(
                creator_id=creator_id, website_url=website_url, clean_before=True, re_verify=True
            )

            # Ensure commit is done
            session.commit()

            return {
                "status": result.status,
                "success": result.success,
                "products_saved": result.products_saved,
                "knowledge_saved": result.knowledge_saved,
                "products_count": len(result.products),
                "products": result.products[:5] if result.products else [],
                "bio": result.bio,
                "faqs_count": len(result.faqs) if result.faqs else 0,
                "faqs": result.faqs[:3] if result.faqs else [],
                "tone": result.tone,
                "errors": result.errors,
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"test_ingestion_v2 error: {e}")
        import traceback

        traceback.print_exc()
        return {"status": "error", "error": str(e)}


# ---------------------------------------------------------
# BACKUP ENDPOINTS
# ---------------------------------------------------------
@router.post("/backup")
async def admin_create_backup(creators_only: bool = False, admin: str = Depends(require_admin)):
    """
    [ADMIN] Create a database backup.
    Exports critical data to JSON files.

    Args:
        creators_only: If True, only backup creator config (faster)

    Returns:
        Backup location and stats
    """
    import subprocess
    import sys

    try:
        # Run backup script
        script_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "backup_db.py")
        cmd = [sys.executable, script_path]
        if creators_only:
            cmd.append("--creators-only")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

        if result.returncode != 0:
            logger.error(f"Backup failed: {result.stderr}")
            raise HTTPException(status_code=500, detail=f"Backup failed: {result.stderr}")

        logger.info(f"Backup completed: {result.stdout}")

        return {
            "status": "ok",
            "message": "Backup created successfully",
            "output": result.stdout,
            "creators_only": creators_only,
        }

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Backup timed out (5 min limit)")
    except Exception as e:
        logger.error(f"Error creating backup: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/backups")
async def admin_list_backups(admin: str = Depends(require_admin)):
    """
    [ADMIN] List available backups.
    """
    try:
        backup_dir = os.path.join(os.getenv("DATA_PATH", "./data"), "backups")
        backups = []

        if os.path.exists(backup_dir):
            for item in sorted(os.listdir(backup_dir), reverse=True)[:20]:  # Last 20
                item_path = os.path.join(backup_dir, item)
                if os.path.isdir(item_path):
                    meta_file = os.path.join(item_path, "_backup_meta.json")
                    if os.path.exists(meta_file):
                        with open(meta_file) as f:
                            meta = json.load(f)
                        backups.append(
                            {
                                "name": item,
                                "created_at": meta.get("created_at"),
                                "tables": list(meta.get("stats", {}).get("tables", {}).keys()),
                            }
                        )

        return {"status": "ok", "backups": backups, "total": len(backups)}

    except Exception as e:
        logger.error(f"Error listing backups: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
