"""
Application startup — backward-compatible re-export shim.

The implementation has been decomposed into:
  api/startup_tasks/handlers.py          — register_startup_handlers
  api/startup_tasks/jobs_maintenance.py  — maintenance scheduled jobs
  api/startup_tasks/jobs_ai.py           — AI/ML scheduled jobs
  api/startup_tasks/jobs_infra.py        — infrastructure scheduled jobs
  api/startup_tasks/cache.py             — cache pre-warming and refresh

All original imports continue to work.
"""

from api.startup_tasks.handlers import register_startup_handlers  # noqa: F401
from api.startup_tasks.cache import (  # noqa: F401
    do_cache_refresh as _do_cache_refresh,
    do_prewarm as _do_prewarm,
)
