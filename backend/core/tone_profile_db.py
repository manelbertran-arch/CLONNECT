"""
DEPRECATED — backward-compat shim.

This module has been split (branch forensic/tone-profile-db-20260423) into
three domain-scoped repositories under `core.data`:

    core.data.tone_profile_repo       — tone profiles       (BOOTSTRAP / Doc D)
    core.data.content_chunks_repo     — RAG chunks          (INGESTIÓN batch)
    core.data.instagram_posts_repo    — IG post content     (INGESTIÓN batch)

Existing imports through `core.tone_profile_db` continue to work via the
re-exports below. New code MUST import from the domain-specific repo.

See backend/docs/forensic/tone_profile_db/ for the refactor rationale.
"""

from core.data.tone_profile_repo import (  # noqa: F401
    _tone_cache,
    clear_cache,
    delete_tone_profile_db,
    get_tone_cache_stats,
    get_tone_profile_db,
    get_tone_profile_db_sync,
    list_profiles_db,
    save_tone_profile_db,
)
from core.data.content_chunks_repo import (  # noqa: F401
    delete_content_chunks_db,
    get_content_chunks_db,
    save_content_chunks_db,
)
from core.data.instagram_posts_repo import (  # noqa: F401
    delete_instagram_posts_db,
    get_instagram_posts_count_db,
    get_instagram_posts_db,
    save_instagram_posts_db,
)

__all__ = [
    # Domain A — tone profiles
    "save_tone_profile_db",
    "get_tone_profile_db",
    "get_tone_profile_db_sync",
    "delete_tone_profile_db",
    "list_profiles_db",
    "clear_cache",
    "_tone_cache",
    "get_tone_cache_stats",
    # Domain B — content chunks
    "save_content_chunks_db",
    "get_content_chunks_db",
    "delete_content_chunks_db",
    # Domain C — Instagram posts
    "save_instagram_posts_db",
    "get_instagram_posts_db",
    "delete_instagram_posts_db",
    "get_instagram_posts_count_db",
]
