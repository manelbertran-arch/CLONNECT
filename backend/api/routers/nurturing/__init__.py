"""Nurturing sequences endpoints - Full implementation"""

from fastapi import APIRouter

from api.routers.nurturing.followups import router as followups_router
from api.routers.nurturing.scheduler import (
    start_scheduler,
    stop_scheduler,
    router as scheduler_router,
)
from api.routers.nurturing.sequences import router as sequences_router

router = APIRouter(prefix="/nurturing", tags=["nurturing"])
router.include_router(sequences_router)
router.include_router(followups_router)
router.include_router(scheduler_router)

# Mutable scheduler state variables live in scheduler.py and are modified at runtime.
# We use __getattr__ to proxy access so that external code (e.g. health.py) always
# reads the *current* value from scheduler.py rather than a stale snapshot.
_SCHEDULER_ATTRS = frozenset({
    "_scheduler_running",
    "_scheduler_task",
    "_scheduler_last_run",
    "_scheduler_run_count",
    "_scheduler_interval",
})


def __getattr__(name: str):
    if name in _SCHEDULER_ATTRS:
        from api.routers.nurturing import scheduler as _sched_mod
        return getattr(_sched_mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "router",
    "start_scheduler",
    "stop_scheduler",
    "_scheduler_running",
    "_scheduler_task",
    "_scheduler_last_run",
    "_scheduler_run_count",
    "_scheduler_interval",
]
