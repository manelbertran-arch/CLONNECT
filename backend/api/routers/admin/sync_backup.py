"""Database backup endpoints."""
import json
import logging
import os

from api.auth import require_admin
from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------
# ADMIN PANEL ENDPOINTS (moved from main.py)
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
        script_path = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "backup_db.py")
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
