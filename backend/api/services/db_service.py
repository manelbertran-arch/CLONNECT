"""
Database service — backward-compatible re-export shim.

The implementation has been decomposed into:
  api/services/db_ops/common.py        — get_session, constants
  api/services/db_ops/creators.py      — creator CRUD
  api/services/db_ops/leads.py         — lead CRUD (sync + async)
  api/services/db_ops/analytics.py     — conversations_with_counts, dashboard, stats
  api/services/db_ops/messages.py      — message CRUD
  api/services/db_ops/conversations.py — archive, spam, reset, delete
  api/services/db_ops/products.py      — product CRUD
  api/services/db_ops/knowledge.py     — knowledge base CRUD

All original imports continue to work.
"""

# Common
from api.services.db_ops.common import (  # noqa: F401
    DATABASE_URL,
    USE_POSTGRES,
    get_session,
    pg_pool,
)

# Creators
from api.services.db_ops.creators import (  # noqa: F401
    get_creator_by_name,
    get_instagram_credentials,
    get_or_create_creator,
    toggle_bot,
    update_creator,
)

# Leads
from api.services.db_ops.leads import (  # noqa: F401
    create_lead,
    create_lead_async,
    delete_lead,
    get_lead_by_id,
    get_lead_by_platform_id,
    get_leads,
    get_or_create_lead,
    update_lead,
)

# Analytics
from api.services.db_ops.analytics import (  # noqa: F401
    get_conversations_with_counts,
    get_creator_stats,
    get_dashboard_metrics,
)

# Messages
from api.services.db_ops.messages import (  # noqa: F401
    count_user_messages_by_lead_id,
    get_message_count,
    get_messages,
    get_messages_by_lead_id,
    get_recent_messages,
    save_message,
)

# Conversations
from api.services.db_ops.conversations import (  # noqa: F401
    archive_conversation,
    delete_conversation,
    mark_conversation_spam,
    reset_conversation_status,
)

# Products
from api.services.db_ops.products import (  # noqa: F401
    create_product,
    delete_product,
    get_products,
    update_product,
)

# Knowledge
from api.services.db_ops.knowledge import (  # noqa: F401
    add_knowledge_item,
    delete_knowledge_item,
    get_full_knowledge,
    get_knowledge_about,
    get_knowledge_items,
    update_knowledge_about,
    update_knowledge_item,
)
