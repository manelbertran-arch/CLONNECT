"""
Database service — decomposed into domain-specific modules.

All functions are re-exported here for backward compatibility.
Import from api.services.db or from individual submodules.
"""
from .session import get_session
from .creators import (
    get_creator_by_name, get_instagram_credentials, get_or_create_creator,
    update_creator, toggle_bot
)
from .leads import (
    get_leads, get_conversations_with_counts, create_lead, update_lead,
    delete_lead, get_lead_by_id, get_lead_by_platform_id, create_lead_async,
    get_or_create_lead
)
from .products import get_products, create_product, update_product, delete_product
from .messages import (
    save_message, get_messages, get_message_count, get_messages_by_lead_id,
    get_recent_messages, count_user_messages_by_lead_id
)
from .conversations import (
    archive_conversation, mark_conversation_spam, reset_conversation_status,
    delete_conversation
)
from .knowledge import (
    get_knowledge_items, add_knowledge_item, delete_knowledge_item,
    update_knowledge_item, get_knowledge_about, update_knowledge_about,
    get_full_knowledge
)
from .dashboard import get_dashboard_metrics, get_creator_stats
