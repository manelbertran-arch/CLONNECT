"""
Safety Guard: Prevents bot messages from being sent without explicit approval.

LAST LINE OF DEFENSE against accidental auto-send.
Every outbound bot message MUST pass through check_send_permission() (or its
async / decision-returning siblings).

The ONLY ways a message can pass:
1. approved=True (creator approved in dashboard, or creator manual send).
2. Autopilot premium: copilot_mode IS FALSE AND autopilot_premium_enabled IS TRUE.

DO NOT REMOVE THIS MODULE.

Phase 5 hardening (branch forensic/send-guard-20260423):
- `check_send_permission` retained for backward compat (raises SendBlocked on deny).
- `check_send_permission_async` added (BUG-04: pool exhaustion in async context).
- `check_send_decision` / `_async` return a typed `SendDecision` (BUG-11).
- `is False` truthiness fix on `copilot_mode` (BUG-03: None legacy leak).
- `.one_or_none()` + upstream UNIQUE constraint on Creator.name (BUG-02).
- SEND_GUARD_AUDIT_ONLY flag for Istio-style shadow mode (testing scoped).
- Prometheus metrics via `core.observability.metrics.emit_metric`.
- Structured JSON logs with correlation decision_id.
- `caller` argument now REQUIRED — magic default removed (BUG-13).
- Dead code `SendGuard` class removed (BUG-15).
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class SendBlocked(Exception):
    """Raised when a send is blocked by the safety guard."""

    pass


# ── Shadow mode (SEND_GUARD_AUDIT_ONLY) ────────────────────────────────────
#
# When set to "true" (case-insensitive), the guard evaluates all rules and
# emits logs + shadow metrics but DOES NOT raise SendBlocked. Used for
# production-safe testing of new enforcement paths (Istio dry-run pattern).
# Default is OFF — any other value (or missing) enables real enforcement.
def _shadow_mode_enabled() -> bool:
    return os.getenv("SEND_GUARD_AUDIT_ONLY", "false").strip().lower() == "true"


# ── Metrics helper (no-op if prometheus_client not installed) ──────────────
def _emit(name: str, value: float = 1, **labels: str) -> None:
    try:
        from core.observability.metrics import emit_metric

        emit_metric(name, value, **labels)
    except Exception:  # pragma: no cover — observability must never break the guard
        pass


def _emit_log(level: int, event: str, **fields) -> None:
    """
    Emit a structured log entry. Uses `extra={}` so a JSON formatter downstream
    can serialise the fields without parsing the message string.
    """
    message = f"[send_guard] {event}"
    logger.log(level, message, extra={"send_guard": fields})


# ── Core evaluator used by every public entry point ────────────────────────
def _evaluate(*, creator_id: str, approved: bool, caller: str):
    """
    Evaluate the guard rules and return a SendDecision.

    Defined here (rather than in send_guard_decision.py) so `check_send_permission`
    can reuse it and keep the DB-touching logic in a single place.
    """
    # Import lazily to avoid circulars.
    from core.send_guard_decision import Allowed, Blocked

    start_t = time.perf_counter()
    decision_id = str(uuid.uuid4())
    adapter = caller.split(".")[0] if caller else "unknown"

    # ── R1: Pre-approved path ─────────────────────────────────────────────
    if approved:
        _emit("send_guard_decision_total", adapter=adapter, caller=caller,
              decision="allowed", rule="R1")
        _emit("send_guard_latency_seconds",
              value=time.perf_counter() - start_t,
              adapter=adapter)
        _emit_log(
            logging.DEBUG,
            "decision_allowed",
            decision_id=decision_id,
            creator_id=creator_id,
            caller=caller,
            adapter=adapter,
            decision="allowed",
            rule="R1",
            reason="approved",
            latency_ms=(time.perf_counter() - start_t) * 1000,
        )
        return Allowed(creator_id=creator_id, caller=caller, rule="R1",
                       decision_id=decision_id)

    # ── DB lookup for flag-based rules ────────────────────────────────────
    try:
        from api.database import SessionLocal
        from api.models import Creator
    except Exception as exc:  # pragma: no cover — environment must have these
        return _fail_closed(
            creator_id=creator_id, caller=caller, adapter=adapter,
            decision_id=decision_id, start_t=start_t,
            reason=f"import_error: {exc}", rule="R5",
        )

    session = SessionLocal()
    try:
        try:
            creator = (
                session.query(Creator)
                .filter_by(name=creator_id)
                .one_or_none()  # BUG-02: enforce UNIQUE assumption explicitly.
            )
        except Exception as exc:
            return _fail_closed(
                creator_id=creator_id, caller=caller, adapter=adapter,
                decision_id=decision_id, start_t=start_t,
                reason=f"db_error: {exc.__class__.__name__}", rule="R5",
            )

        # ── R2: Creator not found ────────────────────────────────────────
        if creator is None:
            return _block(
                creator_id=creator_id, caller=caller, adapter=adapter,
                decision_id=decision_id, start_t=start_t,
                rule="R2", reason="creator_not_found",
                copilot_mode=None, autopilot_premium_enabled=None,
            )

        # Snapshot flags at decision time (avoid races within this evaluation).
        copilot_mode = creator.copilot_mode
        autopilot_premium_enabled = creator.autopilot_premium_enabled

        # ── R3: Autopilot premium path ───────────────────────────────────
        # BUG-03 fix: `is False` rejects None (legacy rows) explicitly.
        if copilot_mode is False and autopilot_premium_enabled is True:
            from core.send_guard_decision import Allowed  # re-import for type

            _emit("send_guard_decision_total", adapter=adapter, caller=caller,
                  decision="allowed", rule="R3")
            _emit("send_guard_latency_seconds",
                  value=time.perf_counter() - start_t,
                  adapter=adapter)
            _emit_log(
                logging.INFO,
                "decision_allowed",
                decision_id=decision_id,
                creator_id=creator_id,
                caller=caller,
                adapter=adapter,
                decision="allowed",
                rule="R3",
                reason="autopilot_premium",
                copilot_mode=copilot_mode,
                autopilot_premium_enabled=autopilot_premium_enabled,
                latency_ms=(time.perf_counter() - start_t) * 1000,
            )
            return Allowed(creator_id=creator_id, caller=caller, rule="R3",
                           decision_id=decision_id)

        # ── R4: Default block (insufficient flags) ───────────────────────
        return _block(
            creator_id=creator_id, caller=caller, adapter=adapter,
            decision_id=decision_id, start_t=start_t,
            rule="R4", reason="insufficient_flags",
            copilot_mode=copilot_mode,
            autopilot_premium_enabled=autopilot_premium_enabled,
        )
    finally:
        session.close()


def _block(
    *,
    creator_id: str,
    caller: str,
    adapter: str,
    decision_id: str,
    start_t: float,
    rule: str,
    reason: str,
    copilot_mode: Optional[bool],
    autopilot_premium_enabled: Optional[bool],
):
    """Build a Blocked decision and emit metrics + log uniformly."""
    from core.send_guard_decision import Blocked

    shadow = _shadow_mode_enabled()
    _emit(
        "send_guard_decision_total", adapter=adapter, caller=caller,
        decision="blocked_shadow" if shadow else "blocked", rule=rule,
    )
    if shadow:
        _emit("send_guard_shadow_blocked_total",
              adapter=adapter, caller=caller, reason=reason)
    _emit("send_guard_latency_seconds",
          value=time.perf_counter() - start_t, adapter=adapter)

    _emit_log(
        logging.CRITICAL,
        "decision_shadow_blocked" if shadow else "decision_blocked",
        decision_id=decision_id,
        creator_id=creator_id,
        caller=caller,
        adapter=adapter,
        decision="blocked_shadow" if shadow else "blocked",
        rule=rule,
        reason=reason,
        copilot_mode=copilot_mode,
        autopilot_premium_enabled=autopilot_premium_enabled,
        latency_ms=(time.perf_counter() - start_t) * 1000,
        audit_only=shadow,
    )

    return Blocked(
        creator_id=creator_id, caller=caller, rule=rule, reason=reason,
        copilot_mode=copilot_mode,
        autopilot_premium_enabled=autopilot_premium_enabled,
        decision_id=decision_id,
    )


def _fail_closed(
    *,
    creator_id: str, caller: str, adapter: str,
    decision_id: str, start_t: float, reason: str, rule: str,
):
    """Guard-internal error path — always denies (P2 AuthZed)."""
    return _block(
        creator_id=creator_id, caller=caller, adapter=adapter,
        decision_id=decision_id, start_t=start_t,
        rule=rule, reason=reason,
        copilot_mode=None, autopilot_premium_enabled=None,
    )


# ── Public API ─────────────────────────────────────────────────────────────
def check_send_permission(
    creator_id: str,
    *,
    approved: bool = False,
    caller: str,
) -> bool:
    """
    Check if an outbound message is allowed to be sent (legacy contract).

    Kept for backward compatibility with the 6 existing callsites. New code
    should prefer `check_send_decision(...)` which returns a structured result.

    Args:
        creator_id: Creator slug (maps to Creator.name).
        approved: True if message was explicitly approved by the creator.
        caller: Adapter identifier — REQUIRED (BUG-13 fix; was defaulted to "unknown").

    Returns:
        True if allowed.

    Raises:
        SendBlocked if not allowed. In SEND_GUARD_AUDIT_ONLY shadow mode, does
        not raise even when the rules would block (callers receive True and the
        block is only visible in shadow metrics / logs).
    """
    decision = _evaluate(creator_id=creator_id, approved=approved, caller=caller)

    if decision.blocked:
        if _shadow_mode_enabled():
            # Shadow: log + metric already emitted inside _evaluate; do not raise.
            return True
        raise SendBlocked(decision.reason)  # type: ignore[attr-defined]

    return True


async def check_send_permission_async(
    creator_id: str,
    *,
    approved: bool = False,
    caller: str,
) -> bool:
    """
    Async variant — offloads the sync DB session to a thread pool so the async
    event loop is not blocked under DB pool pressure (BUG-04).
    """
    import asyncio

    return await asyncio.to_thread(
        check_send_permission,
        creator_id,
        approved=approved,
        caller=caller,
    )
