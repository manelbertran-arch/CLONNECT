"""Leads endpoints package — combines CRUD, escalations, and actions sub-routers."""

from fastapi import APIRouter

from api.routers.leads.crud import router as crud_router
from api.routers.leads.escalations import router as escalations_router
from api.routers.leads.actions import router as actions_router

# Combined router with the original prefix and tags
router = APIRouter(prefix="/dm/leads", tags=["leads"])

# Include sub-routers in the correct order.
# IMPORTANT: escalations must be included BEFORE crud because
# /{creator_id}/escalations must match before /{creator_id}/{lead_id}.
router.include_router(escalations_router)
router.include_router(crud_router)
router.include_router(actions_router)

# Re-export all public symbols for backwards compatibility
from api.routers.leads.crud import (  # noqa: E402, F401
    get_leads,
    get_lead,
    create_lead,
    create_manual_lead,
    update_lead,
    delete_lead,
    update_lead_status,
    # Shared helpers / state
    USE_DB,
    ENABLE_JSON_FALLBACK,
    db_service,
    adapt_leads_response,
    adapt_lead_response,
    BASE_DIR,
    STORAGE_PATH,
)

from api.routers.leads.escalations import (  # noqa: E402, F401
    get_escalation_alerts,
    mark_escalation_read,
    clear_escalations,
)

from api.routers.leads.actions import (  # noqa: E402, F401
    get_lead_activities,
    create_lead_activity,
    delete_lead_activity,
    get_lead_tasks,
    create_lead_task,
    update_lead_task,
    delete_lead_task,
    get_lead_stats,
)
