"""Partial per-phase metadata updates (ARC5 Phase 1).

Mirrors docs/sprint5_planning/ARC5_observability.md §2.2.3. Each helper
reads the existing container, replaces ONE sub-section, and writes back —
guaranteeing phases don't step on each other.

Session handling intentionally matches the design-doc pseudo-code (async
`session.get` / `await session.commit`). Phase 2 integration decides the
actual async/sync session flavour used per call site.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from core.metadata.models import (
    DetectionMetadata,
    GenerationMetadata,
    MessageMetadata,
    PostGenMetadata,
    ScoringMetadata,
)
from core.metadata.serdes import read_metadata, write_metadata


async def _load_message(session: Any, message_id: UUID) -> Any:
    """Resolve a message by id. Prefers async `session.get`, falls back to
    synchronous `session.query(Message).get(message_id)` so the helper works
    in both async and sync codepaths until Phase 2 decides.
    """
    # Local import: api.models is heavy and only needed at call time.
    from api.models import Message  # type: ignore[attr-defined]

    getter = getattr(session, "get", None)
    if getter is not None:
        maybe = getter(Message, message_id)
        if hasattr(maybe, "__await__"):
            return await maybe
        return maybe
    # Legacy sync session fallback.
    return session.query(Message).get(message_id)  # type: ignore[attr-defined]


async def _commit(session: Any) -> None:
    commit = session.commit()
    if hasattr(commit, "__await__"):
        await commit


async def update_detection_metadata(
    session: Any, message_id: UUID, detection: DetectionMetadata
) -> None:
    """Replace only the `detection` sub-section of a message's metadata."""
    msg = await _load_message(session, message_id)
    current = read_metadata(msg)
    current.detection = detection
    write_metadata(msg, current)
    await _commit(session)


async def update_scoring_metadata(
    session: Any, message_id: UUID, scoring: ScoringMetadata
) -> None:
    """Replace only the `scoring` sub-section of a message's metadata."""
    msg = await _load_message(session, message_id)
    current = read_metadata(msg)
    current.scoring = scoring
    write_metadata(msg, current)
    await _commit(session)


async def update_generation_metadata(
    session: Any, message_id: UUID, generation: GenerationMetadata
) -> None:
    """Replace only the `generation` sub-section of a message's metadata."""
    msg = await _load_message(session, message_id)
    current = read_metadata(msg)
    current.generation = generation
    write_metadata(msg, current)
    await _commit(session)


async def update_post_gen_metadata(
    session: Any, message_id: UUID, post_gen: PostGenMetadata
) -> None:
    """Replace only the `post_gen` sub-section of a message's metadata."""
    msg = await _load_message(session, message_id)
    current = read_metadata(msg)
    current.post_gen = post_gen
    write_metadata(msg, current)
    await _commit(session)


__all__ = [
    "MessageMetadata",
    "update_detection_metadata",
    "update_scoring_metadata",
    "update_generation_metadata",
    "update_post_gen_metadata",
]
