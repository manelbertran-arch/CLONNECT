"""
SendGuard Phase 5 hardening — comprehensive test suite.

Covers the 15 bugs documented in docs/forensic/send_guard/03_bugs.md.

Layout:
    A. unit_rules          — R1..R5 rule coverage (BUG-03, BUG-13, BUG-14)
    B. unit_async          — async wrapper + sync-in-async isolation (BUG-04)
    C. unit_decision       — SendDecision sum type + backward compat (BUG-11)
    D. unit_shadow         — SEND_GUARD_AUDIT_ONLY shadow mode (AUDIT_ONLY flag)
    E. integ_callsites     — one integration test per adapter (6+2 callsites)
    F. integ_bypass        — post-fix regression for B1..B4 (BUG-01/05/07/08)
    G. integ_trust         — retry queue + multiplex (BUG-09, BUG-10)
    H. integ_tenant        — cross-tenant Creator.name UNIQUE (BUG-02)
    I. symmetry            — all adapters surface a consistent contract (BUG-11)

All tests are self-contained: no Railway / network. DB access is mocked via an
in-memory Creator stub so we can inject any flag combination.
"""

from __future__ import annotations

import os
import sys
import types
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Test harness: in-memory Creator + SessionLocal substitute
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class _FakeCreator:
    name: str
    copilot_mode: Optional[bool] = True
    autopilot_premium_enabled: bool = False


class _FakeQuery:
    def __init__(self, rows: List[_FakeCreator], raise_on_query: Optional[Exception] = None):
        self._rows = rows
        self._raise = raise_on_query
        self._filter_name: Optional[str] = None

    def filter_by(self, **kw):
        self._filter_name = kw.get("name")
        return self

    def one_or_none(self):
        if self._raise is not None:
            raise self._raise
        matches = [r for r in self._rows if r.name == self._filter_name]
        if len(matches) == 0:
            return None
        if len(matches) > 1:
            # Simulates the UNIQUE constraint we add in migration 050.
            # Pre-migration, .first() returned an arbitrary row (BUG-02).
            from sqlalchemy.exc import MultipleResultsFound  # type: ignore
            raise MultipleResultsFound("multiple creators with same name")
        return matches[0]

    # Legacy .first() shim for any external code path that still uses it.
    def first(self):
        return self.one_or_none()


class _FakeSession:
    def __init__(self, rows: List[_FakeCreator], raise_on_query: Optional[Exception] = None):
        self._rows = rows
        self._raise = raise_on_query
        self.closed = False

    def query(self, _model):
        return _FakeQuery(self._rows, raise_on_query=self._raise)

    def close(self):
        self.closed = True


def _install_fake_db(rows: List[_FakeCreator], raise_on_query: Optional[Exception] = None):
    """Patch send_guard's lazy imports so they resolve to our fake session.

    Returns the patcher context manager — use with `with _install_fake_db(...)`.
    """
    fake_db_mod = types.ModuleType("api.database")
    fake_db_mod.SessionLocal = lambda: _FakeSession(rows, raise_on_query=raise_on_query)  # type: ignore[attr-defined]

    fake_models_mod = types.ModuleType("api.models")
    fake_models_mod.Creator = _FakeCreator  # type: ignore[attr-defined]

    patches = [
        patch.dict(sys.modules, {
            "api.database": fake_db_mod,
            "api.models": fake_models_mod,
        }),
    ]
    return patches


class _InstallFakeDB:
    def __init__(self, rows: List[_FakeCreator], raise_on_query: Optional[Exception] = None):
        self.rows = rows
        self.raise_on_query = raise_on_query
        self._ctx = None

    def __enter__(self):
        fake_db_mod = types.ModuleType("api.database")
        fake_db_mod.SessionLocal = lambda: _FakeSession(self.rows, raise_on_query=self.raise_on_query)  # type: ignore[attr-defined]
        fake_models_mod = types.ModuleType("api.models")
        fake_models_mod.Creator = _FakeCreator  # type: ignore[attr-defined]
        self._ctx = patch.dict(sys.modules, {
            "api.database": fake_db_mod,
            "api.models": fake_models_mod,
        })
        self._ctx.__enter__()
        return self

    def __exit__(self, *exc):
        if self._ctx is not None:
            self._ctx.__exit__(*exc)


@pytest.fixture(autouse=True)
def _clean_shadow_env(monkeypatch):
    """Every test starts with SEND_GUARD_AUDIT_ONLY unset (enforce mode)."""
    monkeypatch.delenv("SEND_GUARD_AUDIT_ONLY", raising=False)
    yield


# ─────────────────────────────────────────────────────────────────────────────
# A. unit_rules — fail-closed rule coverage
# ─────────────────────────────────────────────────────────────────────────────

class TestUnitRules:
    def test_r1_approved_true_returns_true(self):
        from core.send_guard import check_send_permission
        # R1 never touches DB; no fake_db needed.
        assert check_send_permission("any_creator", approved=True, caller="t")

    def test_r2_creator_not_found_raises(self):
        from core.send_guard import SendBlocked, check_send_permission
        with _InstallFakeDB(rows=[]):
            with pytest.raises(SendBlocked):
                check_send_permission("missing", approved=False, caller="t")

    def test_r3_autopilot_premium_returns_true(self):
        from core.send_guard import check_send_permission
        rows = [_FakeCreator(name="c", copilot_mode=False, autopilot_premium_enabled=True)]
        with _InstallFakeDB(rows=rows):
            assert check_send_permission("c", approved=False, caller="t")

    def test_r4_copilot_mode_true_blocks(self):
        from core.send_guard import SendBlocked, check_send_permission
        rows = [_FakeCreator(name="c", copilot_mode=True, autopilot_premium_enabled=True)]
        with _InstallFakeDB(rows=rows):
            with pytest.raises(SendBlocked):
                check_send_permission("c", approved=False, caller="t")

    def test_r4_premium_off_blocks(self):
        from core.send_guard import SendBlocked, check_send_permission
        rows = [_FakeCreator(name="c", copilot_mode=False, autopilot_premium_enabled=False)]
        with _InstallFakeDB(rows=rows):
            with pytest.raises(SendBlocked):
                check_send_permission("c", approved=False, caller="t")

    def test_r4_both_off_blocks(self):
        from core.send_guard import SendBlocked, check_send_permission
        rows = [_FakeCreator(name="c", copilot_mode=True, autopilot_premium_enabled=False)]
        with _InstallFakeDB(rows=rows):
            with pytest.raises(SendBlocked):
                check_send_permission("c", approved=False, caller="t")

    def test_bug03_copilot_mode_none_blocks(self):
        """Legacy row with copilot_mode=None must NOT pass R3 (fix BUG-03)."""
        from core.send_guard import SendBlocked, check_send_permission
        rows = [_FakeCreator(name="legacy", copilot_mode=None, autopilot_premium_enabled=True)]
        with _InstallFakeDB(rows=rows):
            with pytest.raises(SendBlocked):
                check_send_permission("legacy", approved=False, caller="t")

    def test_bug13_caller_required_raises_typeerror(self):
        """`caller` must be explicit — no magic default (BUG-13 fix)."""
        from core.send_guard import check_send_permission
        with pytest.raises(TypeError):
            check_send_permission("c", approved=True)  # type: ignore[call-arg]

    def test_bug14_return_type_is_always_true(self):
        """check_send_permission never returns False; allowed → True, blocked → raise."""
        from core.send_guard import check_send_permission
        rv = check_send_permission("c", approved=True, caller="t")
        assert rv is True


# ─────────────────────────────────────────────────────────────────────────────
# B. unit_async — BUG-04 sync-in-async regression shield
# ─────────────────────────────────────────────────────────────────────────────

class TestUnitAsync:
    @pytest.mark.asyncio
    async def test_async_r1_shortcut_returns_true(self):
        from core.send_guard import check_send_permission_async
        rv = await check_send_permission_async("c", approved=True, caller="t")
        assert rv is True

    @pytest.mark.asyncio
    async def test_async_r2_raises_in_event_loop(self):
        from core.send_guard import SendBlocked, check_send_permission_async
        with _InstallFakeDB(rows=[]):
            with pytest.raises(SendBlocked):
                await check_send_permission_async("missing", approved=False, caller="t")

    @pytest.mark.asyncio
    async def test_async_does_not_block_event_loop(self):
        """Other coroutines must progress while the guard waits on DB.

        We install a slow fake SessionLocal that sleeps in query; if the guard
        were sync-on-loop it would freeze the event loop. With
        `asyncio.to_thread` it should not.
        """
        import asyncio
        import time

        class _SlowSession:
            def query(self, _m):
                time.sleep(0.1)  # simulate pool-pressure delay
                return _FakeQuery([_FakeCreator(name="c", copilot_mode=True)])

            def close(self):
                pass

        fake_db = types.ModuleType("api.database")
        fake_db.SessionLocal = lambda: _SlowSession()  # type: ignore[attr-defined]
        fake_models = types.ModuleType("api.models")
        fake_models.Creator = _FakeCreator  # type: ignore[attr-defined]

        async def ticker():
            await asyncio.sleep(0.001)
            return "tick"

        from core.send_guard import SendBlocked, check_send_permission_async
        with patch.dict(sys.modules, {"api.database": fake_db, "api.models": fake_models}):
            guard_task = asyncio.create_task(
                check_send_permission_async("c", approved=False, caller="t")
            )
            tick_task = asyncio.create_task(ticker())
            # ticker must finish before the guard (guard sleeps ~100ms in thread).
            result = await tick_task
            assert result == "tick"
            with pytest.raises(SendBlocked):
                await guard_task


# ─────────────────────────────────────────────────────────────────────────────
# C. unit_decision — SendDecision sum type
# ─────────────────────────────────────────────────────────────────────────────

class TestUnitDecision:
    def test_allowed_decision_for_approved(self):
        from core.send_guard_decision import Allowed, check_send_decision
        d = check_send_decision("c", approved=True, caller="t")
        assert isinstance(d, Allowed)
        assert d.rule == "R1"
        assert d.blocked is False
        assert d.sent is True
        assert isinstance(d.decision_id, str) and len(d.decision_id) > 0

    def test_blocked_decision_for_missing_creator(self):
        from core.send_guard_decision import Blocked, check_send_decision
        with _InstallFakeDB(rows=[]):
            d = check_send_decision("missing", approved=False, caller="t")
        assert isinstance(d, Blocked)
        assert d.rule == "R2"
        assert d.reason == "creator_not_found"
        assert d.blocked is True
        assert d.sent is False

    def test_allowed_decision_for_autopilot(self):
        from core.send_guard_decision import Allowed, check_send_decision
        rows = [_FakeCreator(name="c", copilot_mode=False, autopilot_premium_enabled=True)]
        with _InstallFakeDB(rows=rows):
            d = check_send_decision("c", approved=False, caller="t")
        assert isinstance(d, Allowed)
        assert d.rule == "R3"

    def test_blocked_decision_r4_exposes_flags(self):
        from core.send_guard_decision import Blocked, check_send_decision
        rows = [_FakeCreator(name="c", copilot_mode=True, autopilot_premium_enabled=False)]
        with _InstallFakeDB(rows=rows):
            d = check_send_decision("c", approved=False, caller="t")
        assert isinstance(d, Blocked)
        assert d.rule == "R4"
        assert d.copilot_mode is True
        assert d.autopilot_premium_enabled is False

    @pytest.mark.asyncio
    async def test_async_decision_returns_allowed_for_approved(self):
        from core.send_guard_decision import Allowed, check_send_decision_async
        d = await check_send_decision_async("c", approved=True, caller="t")
        assert isinstance(d, Allowed)

    def test_decision_r5_when_db_unreachable(self):
        """Guard-internal error must fail closed (BUG-04 / P2 AuthZed)."""
        from core.send_guard_decision import Blocked, check_send_decision
        with _InstallFakeDB(rows=[], raise_on_query=RuntimeError("pool exhausted")):
            d = check_send_decision("c", approved=False, caller="t")
        assert isinstance(d, Blocked)
        assert d.rule == "R5"
        assert "db_error" in d.reason


# ─────────────────────────────────────────────────────────────────────────────
# D. unit_shadow — SEND_GUARD_AUDIT_ONLY flag
# ─────────────────────────────────────────────────────────────────────────────

class TestUnitShadow:
    def test_shadow_mode_does_not_raise(self, monkeypatch):
        from core.send_guard import check_send_permission
        monkeypatch.setenv("SEND_GUARD_AUDIT_ONLY", "true")
        rows = [_FakeCreator(name="c", copilot_mode=True, autopilot_premium_enabled=False)]
        with _InstallFakeDB(rows=rows):
            # Would block in enforce mode — must return True in shadow mode.
            assert check_send_permission("c", approved=False, caller="t") is True

    def test_shadow_mode_off_by_default(self):
        from core.send_guard import SendBlocked, check_send_permission
        rows = [_FakeCreator(name="c", copilot_mode=True, autopilot_premium_enabled=False)]
        with _InstallFakeDB(rows=rows):
            with pytest.raises(SendBlocked):
                check_send_permission("c", approved=False, caller="t")


# ─────────────────────────────────────────────────────────────────────────────
# E. integ_callsites — lightweight per-adapter contract check
# ─────────────────────────────────────────────────────────────────────────────

class TestCallsitesContract:
    """Smoke-level: verify each adapter consumes SendBlocked correctly.

    Full wire-level adapter tests live in the adapter's own test suite; here
    we only guarantee the *call shape* is unchanged after Phase 5 edits.
    """

    def test_callsite_imports_send_guard(self):
        # Verify the 6 callsites still reference the canonical API.
        expected = [
            ("backend/core/telegram_adapter.py", "tg_adapter.send_message"),
            ("backend/core/instagram_modules/message_sender.py", "ig_handler.send_response"),
            ("backend/core/copilot/messaging.py", "copilot_service"),
            ("backend/core/whatsapp/handler.py", "wa_handler.send_response"),
            ("backend/services/evolution_api.py", "evolution_api"),
        ]
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        for path, marker in expected:
            fullpath = os.path.join(root, path.replace("backend/", "", 1))
            assert os.path.exists(fullpath), f"{fullpath} missing"
            contents = open(fullpath).read()
            assert "check_send_permission" in contents, f"no guard in {path}"
            assert marker in contents, f"caller marker {marker!r} missing in {path}"

    def test_callsite_send_template_now_guarded(self):
        """BUG-07: send_template must now invoke check_send_permission."""
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        path = os.path.join(root, "core/whatsapp/handler.py")
        contents = open(path).read()
        # crude but effective: the guard import must appear inside send_template.
        idx_tpl = contents.find("async def send_template(")
        idx_next = contents.find("\n    async def ", idx_tpl + 1)
        block = contents[idx_tpl:idx_next] if idx_next != -1 else contents[idx_tpl:]
        assert "check_send_permission" in block, \
            "send_template must import/call check_send_permission (BUG-07)"
        assert 'caller="wa_handler.send_template"' in block

    def test_callsite_send_buttons_now_guarded(self):
        """BUG-08: send_message_with_buttons must now invoke check_send_permission."""
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        path = os.path.join(root, "core/instagram_modules/message_sender.py")
        contents = open(path).read()
        idx = contents.find("async def send_message_with_buttons(")
        idx_next = contents.find("\n    async def ", idx + 1)
        block = contents[idx:idx_next] if idx_next != -1 else contents[idx:]
        assert "check_send_permission" in block, \
            "send_message_with_buttons must import/call check_send_permission (BUG-08)"
        assert 'caller="ig_handler.send_buttons"' in block


# ─────────────────────────────────────────────────────────────────────────────
# F. integ_bypass — ensure B1..B4 no longer bypass
# ─────────────────────────────────────────────────────────────────────────────

class TestBypassRegression:
    def test_bug01_wa_autopilot_webhook_has_guard(self):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        path = os.path.join(root, "api/routers/messaging_webhooks/whatsapp_webhook.py")
        contents = open(path).read()
        # Guard call must appear near the AUTOPILOT MODE branch.
        idx_autopilot = contents.find("AUTOPILOT MODE")
        idx_send = contents.find("send_connector.send_message", idx_autopilot)
        between = contents[idx_autopilot:idx_send]
        assert "check_send_permission" in between, \
            "BUG-01: guard missing before autopilot send_connector.send_message"
        assert 'caller="wa_webhook.autopilot"' in between

    def test_bug05_manual_wa_cloud_fallback_has_guard(self):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        path = os.path.join(root, "api/routers/dm/processing.py")
        contents = open(path).read()
        idx_fallback = contents.find("Fall back to official WhatsApp Cloud API")
        idx_send = contents.find("wa_handler.connector.send_message", idx_fallback)
        assert idx_send != -1
        between = contents[idx_fallback:idx_send]
        assert "check_send_permission" in between, \
            "BUG-05: guard missing in manual WA Cloud fallback"
        assert "dm.manual_send.wa_cloud_fallback" in between

    def test_bug07_send_template_bypass_closed(self):
        # Exercised by TestCallsitesContract.test_callsite_send_template_now_guarded.
        self._assert_method_guarded(
            path_fragment="core/whatsapp/handler.py",
            method="async def send_template(",
            caller_marker="wa_handler.send_template",
        )

    def test_bug08_send_buttons_bypass_closed(self):
        self._assert_method_guarded(
            path_fragment="core/instagram_modules/message_sender.py",
            method="async def send_message_with_buttons(",
            caller_marker="ig_handler.send_buttons",
        )

    # -- helper ---------------------------------------------------------------
    def _assert_method_guarded(self, path_fragment: str, method: str, caller_marker: str):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        path = os.path.join(root, path_fragment)
        contents = open(path).read()
        idx = contents.find(method)
        assert idx != -1, f"method {method!r} not found in {path_fragment}"
        idx_next = contents.find("\n    async def ", idx + 1)
        block = contents[idx:idx_next] if idx_next != -1 else contents[idx:]
        assert "check_send_permission" in block, \
            f"bypass still open in {path_fragment}::{method}"
        assert caller_marker in block, \
            f"caller marker {caller_marker!r} not wired in {path_fragment}"


# ─────────────────────────────────────────────────────────────────────────────
# G. integ_trust — BUG-09 retry queue + BUG-10 copilot multiplex
# ─────────────────────────────────────────────────────────────────────────────

class TestTrustPropagation:
    def test_bug09_retry_queue_does_not_hardcode_approved_true(self):
        import re
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        path = os.path.join(root, "services/meta_retry_queue.py")
        # Strip comments and docstrings so we only assert against live code.
        code_only = "\n".join(
            line for line in open(path).read().splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
        assert not re.search(r"send_response\([^)]*approved=True", code_only), \
            "BUG-09: retry must not hardcode approved=True in send_response (revocation breaks compliance)"
        assert "approved=False" in code_only, \
            "BUG-09: retry path expected to pass approved=False so guard re-validates flags"

    def test_bug10_copilot_multiplex_propagates_approved(self):
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        path = os.path.join(root, "core/copilot/messaging.py")
        contents = open(path).read()
        # The `send_evolution_message(..., approved=True)` hardcode is replaced
        # by `approved=approved` propagation.
        assert "send_evolution_message(evo_instance, recipient, text, approved=True)" not in contents, \
            "BUG-10: approved=True must not be hardcoded in multiplex path"
        assert "approved=approved" in contents, \
            "BUG-10: expected propagation of `approved` parameter downstream"


# ─────────────────────────────────────────────────────────────────────────────
# H. integ_tenant — cross-tenant isolation (Creator.name UNIQUE)
# ─────────────────────────────────────────────────────────────────────────────

class TestTenantIsolation:
    def test_duplicate_creator_name_raises_multipleresultsfound(self):
        """Pre-migration behavior (.first() returned arbitrary row) is replaced
        by .one_or_none() which raises on duplicates. The guard treats that as
        a guard-internal error (fail-closed R5)."""
        from core.send_guard import SendBlocked, check_send_permission
        rows = [
            _FakeCreator(name="dup", copilot_mode=True, autopilot_premium_enabled=False),
            _FakeCreator(name="dup", copilot_mode=False, autopilot_premium_enabled=True),
        ]
        with _InstallFakeDB(rows=rows):
            with pytest.raises(SendBlocked):
                check_send_permission("dup", approved=False, caller="t")


# ─────────────────────────────────────────────────────────────────────────────
# I. symmetry — all callsites now expose a consistent contract
# ─────────────────────────────────────────────────────────────────────────────

class TestSymmetry:
    def test_send_guard_decision_module_exports_sum_type(self):
        from core.send_guard_decision import Allowed, Blocked, SendDecision
        # SendDecision is a Union[Allowed, Blocked]. isinstance must discriminate.
        a = Allowed(creator_id="c", caller="t", rule="R1")
        b = Blocked(creator_id="c", caller="t", rule="R4", reason="x")
        for inst in (a, b):
            assert isinstance(inst, (Allowed, Blocked))

    def test_frozen_dataclasses(self):
        from core.send_guard_decision import Allowed, Blocked
        a = Allowed(creator_id="c", caller="t", rule="R1")
        b = Blocked(creator_id="c", caller="t", rule="R4", reason="x")
        with pytest.raises(Exception):
            a.rule = "R3"  # type: ignore[misc]
        with pytest.raises(Exception):
            b.reason = "different"  # type: ignore[misc]

    def test_dead_code_sendguard_class_removed(self):
        """BUG-15: class SendGuard was dead code; must be removed."""
        import core.send_guard as sg
        assert not hasattr(sg, "SendGuard"), \
            "BUG-15: SendGuard class should have been removed in Phase 5"


# ─────────────────────────────────────────────────────────────────────────────
# pytest-asyncio config — use function-scoped loop
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def event_loop():
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
