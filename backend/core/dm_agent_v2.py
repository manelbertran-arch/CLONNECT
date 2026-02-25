"""
DM Responder Agent V2 — Re-export hub.

All implementation lives in `core.dm.*` submodules.
This file re-exports every public symbol for backward compatibility.
"""

# --- Text utilities ---
from core.dm.text_utils import (  # noqa: F401
    _strip_accents,
    _message_mentions_product,
    _truncate_at_boundary,
    _smart_truncate_context,
    apply_voseo,
    NON_CACHEABLE_INTENTS,
    _PRODUCT_STOPWORDS,
)

# --- Data models ---
from core.dm.models import (  # noqa: F401
    AgentConfig,
    DMResponse,
    DetectionResult,
    ContextBundle,
)

# --- Response strategy ---
from core.dm.strategy import _determine_response_strategy  # noqa: F401

# --- Helper functions ---
from core.dm.helpers import (  # noqa: F401
    format_rag_context,
    get_lead_stage,
    get_history_from_follower,
    get_conversation_summary,
    error_response,
    detect_platform,
)

# --- Post-response processing ---
from core.dm.post_response import (  # noqa: F401
    background_post_response,
    sync_post_response,
    update_follower_memory,
    update_lead_score,
    step_email_capture,
    check_and_notify_escalation,
    trigger_identity_resolution,
)

# --- Knowledge management ---
from core.dm.knowledge import (  # noqa: F401
    add_knowledge,
    add_knowledge_batch,
    clear_knowledge,
)

# --- Follower API ---
from core.dm.follower_api import (  # noqa: F401
    get_follower_detail,
    enrich_from_database,
    save_manual_message,
    update_follower_status,
)

# --- Agent class + factory (the core) ---
from core.dm.agent import (  # noqa: F401
    DMResponderAgentV2,
    DMResponderAgent,
    get_dm_agent,
    invalidate_dm_agent_cache,
)

# Re-export Intent for callers that do `from core.dm_agent_v2 import Intent`
from services.intent_service import Intent  # noqa: F401
