"""Health check endpoints for Kubernetes probes and system monitoring"""
import logging
import os
import shutil
import time
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

# Version for tracking deployments
VERSION = "1.0.0"

# Optional psutil for memory health checks
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None


# =============================================================================
# HEALTH CHECK HELPERS
# =============================================================================

async def check_llm_health() -> Dict[str, Any]:
    """Verify connection to LLM (Groq/OpenAI/Anthropic)"""
    try:
        from core.llm import get_llm_client

        start = time.time()
        llm_client = get_llm_client()

        # Make a simple test call
        _response = await llm_client.generate(prompt="Responde solo 'ok'", max_tokens=5)

        latency_ms = int((time.time() - start) * 1000)

        return {
            "status": "ok",
            "latency_ms": latency_ms,
            "provider": os.getenv("LLM_PROVIDER", "openai"),
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "provider": os.getenv("LLM_PROVIDER", "openai")}


def check_disk_health() -> Dict[str, Any]:
    """Verify disk space availability"""
    try:
        data_path = os.getenv("DATA_PATH", "./data")

        # Get disk info
        total, used, free = shutil.disk_usage(data_path)
        free_gb = round(free / (1024**3), 2)

        # Warning if less than 1GB, error if less than 100MB
        if free_gb < 0.1:
            status = "error"
        elif free_gb < 1.0:
            status = "warning"
        else:
            status = "ok"

        return {
            "status": status,
            "free_gb": free_gb,
            "total_gb": round(total / (1024**3), 2),
            "used_percent": round((used / total) * 100, 1),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_memory_health() -> Dict[str, Any]:
    """Verify available RAM"""
    try:
        if not PSUTIL_AVAILABLE:
            return {"status": "unknown", "error": "psutil not installed"}

        mem = psutil.virtual_memory()
        free_mb = round(mem.available / (1024**2), 1)

        # Warning if less than 256MB, error if less than 128MB
        if free_mb < 128:
            status = "error"
        elif free_mb < 256:
            status = "warning"
        else:
            status = "ok"

        return {
            "status": status,
            "free_mb": free_mb,
            "total_mb": round(mem.total / (1024**2), 1),
            "used_percent": round(mem.percent, 1),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_data_dir_health() -> Dict[str, Any]:
    """Verify access to data directory"""
    try:
        data_path = os.getenv("DATA_PATH", "./data")

        # Check if exists
        if not os.path.exists(data_path):
            return {"status": "error", "error": "data directory does not exist"}

        # Check important subdirectories
        subdirs = ["followers", "products", "creators", "analytics"]
        missing = []

        for subdir in subdirs:
            path = os.path.join(data_path, subdir)
            if not os.path.exists(path):
                missing.append(subdir)

        if missing:
            return {"status": "warning", "path": data_path, "missing_subdirs": missing}

        # Check if writable
        test_file = os.path.join(data_path, ".health_check")
        try:
            with open(test_file, "w") as f:
                f.write("test")
            os.remove(test_file)
            writable = True
        except Exception as e:
            logger.warning(f"Data path not writable: {e}")
            writable = False

        return {"status": "ok" if writable else "error", "path": data_path, "writable": writable}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def determine_overall_status(checks: Dict[str, Dict]) -> str:
    """Determine overall status based on individual checks"""
    statuses = [check.get("status", "unknown") for check in checks.values()]

    if "error" in statuses:
        return "unhealthy"
    elif "warning" in statuses or "unknown" in statuses:
        return "degraded"
    else:
        return "healthy"


# =============================================================================
# HEALTH ENDPOINTS
# =============================================================================

@router.get("/health")
def health():
    """
    Fast system health check - NO LLM calls.

    Verifies:
    - Disk space
    - RAM memory
    - Access to data directory

    NOTE: LLM check removed to keep response <1s.
    Use /health/ready for full readiness check including LLM.

    Returns:
        status: healthy | degraded | unhealthy
        checks: Details of each verification
    """
    checks = {
        "disk": check_disk_health(),
        "memory": check_memory_health(),
        "data_dir": check_data_dir_health(),
    }

    overall_status = determine_overall_status(checks)

    return {
        "status": overall_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "version": VERSION,
        "service": "clonnect-creators",
    }


@router.get("/health/live")
def health_live():
    """
    Liveness probe for Kubernetes.

    Only verifies that the process is alive and can respond.
    Minimal response for low overhead.

    Returns:
        status: ok | error
    """
    return {"status": "ok"}


@router.get("/health/ready")
def health_ready():
    """
    Readiness probe for Kubernetes.

    Verifies that the service can process requests:
    - Data directory accessible

    NOTE: LLM check removed to keep response fast.
    LLM availability is verified by actual message processing.

    Returns:
        status: ok | error
        ready: boolean
    """
    try:
        # Check data access
        data_check = check_data_dir_health()
        if data_check.get("status") == "error":
            return {"status": "error", "ready": False, "reason": "data_dir_not_accessible"}

        return {"status": "ok", "ready": True}

    except Exception as e:
        return {"status": "error", "ready": False, "reason": str(e)}


@router.get("/health/llm")
async def health_llm():
    """
    Explicit LLM health check - use sparingly (slow).

    Makes an actual LLM API call to verify connectivity.
    Expected latency: 1-20 seconds depending on provider.

    Returns:
        status: ok | error
        latency_ms: Response time
        provider: LLM provider name
    """
    return await check_llm_health()


@router.get("/health/cache")
def health_cache():
    """Debug endpoint to check API cache stats and contents."""
    try:
        from api.cache import api_cache

        stats = api_cache.stats()

        # Get list of cached keys (without values to avoid memory issues)
        with api_cache._lock:
            keys = list(api_cache._cache.keys())

        return {
            "status": "ok",
            "stats": stats,
            "cached_keys": keys[:50],  # Limit to first 50 keys
            "total_keys": len(keys),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@router.get("/health/scheduler")
def health_scheduler():
    """List all background scheduled jobs and their status.

    Returns each job's name, interval, and whether it's enabled.
    """
    jobs = []

    # 1. Token refresh (24h)
    jobs.append({
        "name": "token_refresh",
        "interval": "24h",
        "initial_delay": "60s",
        "enabled": True,
        "description": "Refreshes Instagram OAuth tokens expiring within 30 days",
    })

    # 2. Profile pic refresh (24h)
    enabled_pics = os.getenv("ENABLE_PROFILE_PIC_REFRESH", "true").lower() == "true"
    jobs.append({
        "name": "profile_pic_refresh",
        "interval": "24h",
        "initial_delay": "90s",
        "enabled": enabled_pics,
        "description": "Refreshes Instagram CDN profile picture URLs expiring within 48h",
    })

    # 3. Nurturing scheduler (5min)
    try:
        from api.routers.nurturing import (
            _scheduler_interval,
            _scheduler_last_run,
            _scheduler_run_count,
            _scheduler_running,
        )

        jobs.append({
            "name": "nurturing",
            "interval": f"{_scheduler_interval}s",
            "initial_delay": "30s",
            "enabled": True,
            "running": _scheduler_running,
            "last_run": _scheduler_last_run,
            "total_runs": _scheduler_run_count,
            "description": "Processes nurturing follow-up sequences",
        })
    except ImportError:
        jobs.append({
            "name": "nurturing",
            "interval": "300s",
            "enabled": True,
            "running": "unknown",
            "description": "Processes nurturing follow-up sequences",
        })

    # 4. Content refresh (24h)
    enabled_content = os.getenv("CONTENT_REFRESH_ENABLED", "true").lower() == "true"
    jobs.append({
        "name": "content_refresh",
        "interval": os.getenv("CONTENT_REFRESH_INTERVAL_SECONDS", "86400") + "s",
        "initial_delay": os.getenv("CONTENT_REFRESH_INITIAL_DELAY", "120") + "s",
        "enabled": enabled_content,
        "description": "Re-scrapes Instagram posts, chunks, and generates embeddings",
    })

    # 5. Media capture (6h)
    enabled_media = os.getenv("ENABLE_MEDIA_CAPTURE", "true").lower() == "true"
    jobs.append({
        "name": "media_capture",
        "interval": os.getenv("MEDIA_CAPTURE_INTERVAL_SECONDS", "21600") + "s",
        "initial_delay": os.getenv("MEDIA_CAPTURE_INITIAL_DELAY", "180") + "s",
        "enabled": enabled_media,
        "description": "Captures expiring CDN media URLs as base64 before they expire",
    })

    # 6. Post context refresh (12h)
    jobs.append({
        "name": "post_context_refresh",
        "interval": "12h",
        "initial_delay": "150s",
        "enabled": True,
        "description": "Refreshes expired post contexts for creator content",
    })

    # 7. Keep-alive (1min)
    jobs.append({
        "name": "keep_alive",
        "interval": "60s",
        "initial_delay": "3s",
        "enabled": True,
        "description": "DB ping to prevent Railway scale-to-zero",
    })

    # 8. Score decay (24h)
    jobs.append({
        "name": "score_decay",
        "interval": "24h",
        "initial_delay": "210s",
        "enabled": os.getenv("ENABLE_SCORE_DECAY", "true").lower() == "true",
        "description": "Recalculates lead scores so ghost scores decay via recency",
    })

    # 9. Followup cleanup (24h)
    jobs.append({
        "name": "followup_cleanup",
        "interval": "24h",
        "initial_delay": "240s",
        "enabled": os.getenv("ENABLE_FOLLOWUP_CLEANUP", "true").lower() == "true",
        "description": "Deletes sent/cancelled/failed nurturing followups older than 30 days",
    })

    # 10. Activities cleanup (24h)
    jobs.append({
        "name": "activities_cleanup",
        "interval": "24h",
        "initial_delay": "270s",
        "enabled": os.getenv("ENABLE_ACTIVITIES_CLEANUP", "true").lower() == "true",
        "description": "Deletes lead_activities older than 90 days",
    })

    # 11. Queue cleanup (24h)
    jobs.append({
        "name": "queue_cleanup",
        "interval": "24h",
        "initial_delay": "300s",
        "enabled": os.getenv("ENABLE_QUEUE_CLEANUP", "true").lower() == "true",
        "description": "Purges unmatched_webhooks and sync_queue older than 7 days",
    })

    # 12. Reconciliation (30min)
    jobs.append({
        "name": "reconciliation",
        "interval": "30min",
        "initial_delay": "330s",
        "enabled": os.getenv("ENABLE_RECONCILIATION", "true").lower() == "true",
        "description": "Recovers missing Instagram messages (1h lookback)",
    })

    # 13. Lead enrichment (6h)
    jobs.append({
        "name": "lead_enrichment",
        "interval": "6h",
        "initial_delay": "360s",
        "enabled": os.getenv("ENABLE_LEAD_ENRICHMENT", "true").lower() == "true",
        "description": "Enriches leads without profile info (fixes ig_XXXX leads)",
    })

    # 14. Ghost reactivation (24h)
    jobs.append({
        "name": "ghost_reactivation",
        "interval": "24h",
        "initial_delay": "390s",
        "enabled": os.getenv("ENABLE_GHOST_REACTIVATION", "true").lower() == "true",
        "description": "Finds ghost leads and schedules re-engagement nurturing",
    })

    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_jobs": len(jobs),
        "jobs": jobs,
    }
