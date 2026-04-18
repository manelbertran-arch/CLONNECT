"""Typed metadata read/write boundary (ARC5 Phase 1).

Mirrors docs/sprint5_planning/ARC5_observability.md §2.2.2 and §2.2.4.

Deviation from the design pseudo-code: the SQLAlchemy Message column is
`msg_metadata` (api/models/message.py:41), not `metadata` (which collides
with SQLAlchemy's Base.metadata). We bind to `msg_metadata` here; the
Pydantic model layer is unchanged.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from core.metadata.models import MessageMetadata

logger = logging.getLogger(__name__)

_LEGACY_READ_COUNTER = 0  # Local fallback when prometheus client is absent.


def _bump_legacy_read_counter() -> None:
    """Increment the legacy_metadata_read counter.

    Uses prometheus_client if available (Phase 2 wires the real registry);
    otherwise falls back to a module-level int so tests can assert the
    behaviour without a metrics backend.
    """
    global _LEGACY_READ_COUNTER
    _LEGACY_READ_COUNTER += 1
    try:  # pragma: no cover - metrics backend is optional in Phase 1
        from core.observability import metrics  # type: ignore[attr-defined]

        counter = getattr(metrics, "legacy_metadata_read", None)
        if counter is not None and hasattr(counter, "inc"):
            counter.inc()
    except Exception:
        pass


def get_legacy_read_count() -> int:
    """Testing hook — number of legacy reads since process start."""
    return _LEGACY_READ_COUNTER


def reset_legacy_read_count() -> None:
    """Testing hook — reset the local counter."""
    global _LEGACY_READ_COUNTER
    _LEGACY_READ_COUNTER = 0


def _get_raw(message: Any) -> Any:
    """Return the raw JSONB dict stored on the message.

    The production column is `msg_metadata`; fall back to `metadata`
    attribute for duck-typed test doubles that mirror the design-doc name.
    """
    if hasattr(message, "msg_metadata"):
        return getattr(message, "msg_metadata")
    return getattr(message, "metadata", None)


def _set_raw(message: Any, value: dict[str, Any]) -> None:
    if hasattr(message, "msg_metadata"):
        setattr(message, "msg_metadata", value)
    else:
        setattr(message, "metadata", value)


def write_metadata(message: Any, typed: MessageMetadata) -> None:
    """Write typed metadata to message's JSONB column."""
    _set_raw(message, typed.model_dump(mode="json", exclude_none=True))


def read_metadata(message: Any) -> MessageMetadata:
    """Read typed metadata from a message.

    Legacy fallback (§2.2.4): if the stored dict fails Pydantic validation
    (pre-typed rows written by the old code path), increment the
    `legacy_metadata_read` counter and return an empty container rather
    than crash the read path.
    """
    raw = _get_raw(message)
    if not raw:
        return MessageMetadata()
    try:
        return MessageMetadata.model_validate(raw)
    except ValidationError:
        _bump_legacy_read_counter()
        logger.debug("[metadata] legacy row — returning empty MessageMetadata")
        return MessageMetadata()
