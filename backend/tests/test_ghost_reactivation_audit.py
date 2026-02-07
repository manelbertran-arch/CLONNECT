"""Audit tests for core/ghost_reactivation.py."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Test 1: init / import
# ---------------------------------------------------------------------------
class TestGhostReactivationInit:
    """Verify module imports and configuration structure."""

    def test_imports_and_config_keys(self):
        from core.ghost_reactivation import REACTIVATION_CONFIG

        assert isinstance(REACTIVATION_CONFIG, dict)
        expected_keys = {
            "min_days_ghost",
            "max_days_ghost",
            "cooldown_days",
            "max_per_cycle",
            "enabled",
        }
        assert expected_keys == set(REACTIVATION_CONFIG.keys())

    def test_reactivation_messages_non_empty(self):
        from core.ghost_reactivation import REACTIVATION_MESSAGES

        assert isinstance(REACTIVATION_MESSAGES, list)
        assert len(REACTIVATION_MESSAGES) >= 1
        for msg in REACTIVATION_MESSAGES:
            assert isinstance(msg, str) and len(msg) > 10

    def test_default_config_values(self):
        from core.ghost_reactivation import REACTIVATION_CONFIG

        assert REACTIVATION_CONFIG["min_days_ghost"] == 7
        assert REACTIVATION_CONFIG["max_days_ghost"] == 90
        assert REACTIVATION_CONFIG["cooldown_days"] == 30
        assert REACTIVATION_CONFIG["max_per_cycle"] == 5

    def test_reactivation_key_generation(self):
        from core.ghost_reactivation import _get_reactivation_key

        key = _get_reactivation_key("creator1", "lead_abc")
        assert key == "creator1:lead_abc"


# ---------------------------------------------------------------------------
# Test 2: happy path - ghost lead identification via mock
# ---------------------------------------------------------------------------
class TestGhostLeadIdentification:
    """Test ghost identification with mocked DB."""

    def test_was_recently_reactivated_false_initially(self):
        from core.ghost_reactivation import _reactivated_leads, _was_recently_reactivated

        # Ensure fresh state
        key = "test_ghost_creator:lead_1"
        _reactivated_leads.pop(key, None)

        result = _was_recently_reactivated("test_ghost_creator", "lead_1")
        assert result is False

    def test_mark_then_check_recently_reactivated(self):
        from core.ghost_reactivation import (
            _mark_as_reactivated,
            _reactivated_leads,
            _was_recently_reactivated,
        )

        _mark_as_reactivated("creator_x", "lead_42")
        assert _was_recently_reactivated("creator_x", "lead_42") is True

        # Cleanup
        _reactivated_leads.pop("creator_x:lead_42", None)

    def test_get_ghost_leads_returns_empty_on_db_error(self):
        from core.ghost_reactivation import get_ghost_leads_for_reactivation

        # With no real DB, should return []
        result = get_ghost_leads_for_reactivation("nonexistent_creator")
        assert result == []


# ---------------------------------------------------------------------------
# Test 3: non-ghost lead handling
# ---------------------------------------------------------------------------
class TestNonGhostLeadHandling:
    """Verify that recent contacts and old contacts are excluded."""

    def test_cooldown_not_expired(self):
        from core.ghost_reactivation import (
            _get_reactivation_key,
            _reactivated_leads,
            _was_recently_reactivated,
        )

        key = _get_reactivation_key("creator_cool", "lead_cool")
        # Mark as reactivated just now
        _reactivated_leads[key] = datetime.now(timezone.utc)

        assert _was_recently_reactivated("creator_cool", "lead_cool") is True

        # Cleanup
        _reactivated_leads.pop(key, None)

    def test_cooldown_expired(self):
        from core.ghost_reactivation import (
            REACTIVATION_CONFIG,
            _get_reactivation_key,
            _reactivated_leads,
            _was_recently_reactivated,
        )

        key = _get_reactivation_key("creator_old", "lead_old")
        days = REACTIVATION_CONFIG["cooldown_days"]
        # Mark as reactivated long ago
        _reactivated_leads[key] = datetime.now(timezone.utc) - timedelta(days=days + 1)

        assert _was_recently_reactivated("creator_old", "lead_old") is False

        # Cleanup
        _reactivated_leads.pop(key, None)

    @pytest.mark.asyncio
    async def test_reactivate_disabled(self):
        """When disabled, reactivate_ghost_leads returns disabled status."""
        from core.ghost_reactivation import REACTIVATION_CONFIG, reactivate_ghost_leads

        original = REACTIVATION_CONFIG["enabled"]
        try:
            REACTIVATION_CONFIG["enabled"] = False
            result = await reactivate_ghost_leads("any_creator")
            assert result["status"] == "disabled"
        finally:
            REACTIVATION_CONFIG["enabled"] = original


# ---------------------------------------------------------------------------
# Test 4: reactivation message generation and dry run
# ---------------------------------------------------------------------------
class TestGhostReactivationMessageGeneration:
    """Test the reactivation scheduling flow with mocks."""

    @pytest.mark.asyncio
    async def test_reactivate_dry_run(self):
        from core.ghost_reactivation import REACTIVATION_CONFIG, reactivate_ghost_leads

        original_enabled = REACTIVATION_CONFIG["enabled"]
        try:
            REACTIVATION_CONFIG["enabled"] = True

            with patch(
                "core.ghost_reactivation.get_ghost_leads_for_reactivation",
                return_value=[
                    {
                        "lead_id": "lead_1",
                        "platform_user_id": "user_1",
                        "username": "ghost_user",
                        "platform": "instagram",
                        "days_since_contact": 10,
                        "last_contact": "2026-01-01T00:00:00+00:00",
                    }
                ],
            ):
                result = await reactivate_ghost_leads("creator1", dry_run=True)

            assert result["ghosts_found"] == 1
            assert result["scheduled"] == 0  # dry run does not schedule
            assert len(result["details"]) == 1
            assert result["details"][0]["status"] == "dry_run"
        finally:
            REACTIVATION_CONFIG["enabled"] = original_enabled

    @pytest.mark.asyncio
    async def test_reactivate_no_ghosts(self):
        from core.ghost_reactivation import REACTIVATION_CONFIG, reactivate_ghost_leads

        original_enabled = REACTIVATION_CONFIG["enabled"]
        try:
            REACTIVATION_CONFIG["enabled"] = True
            with patch(
                "core.ghost_reactivation.get_ghost_leads_for_reactivation",
                return_value=[],
            ):
                result = await reactivate_ghost_leads("creator_empty")

            assert result["ghosts_found"] == 0
            assert result["scheduled"] == 0
        finally:
            REACTIVATION_CONFIG["enabled"] = original_enabled


# ---------------------------------------------------------------------------
# Test 5: time threshold check and configure_reactivation
# ---------------------------------------------------------------------------
class TestGhostReactivationThresholds:
    """Verify configuration mutation and threshold boundaries."""

    def test_configure_reactivation_updates(self):
        from core.ghost_reactivation import REACTIVATION_CONFIG, configure_reactivation

        # Save originals
        originals = REACTIVATION_CONFIG.copy()

        try:
            result = configure_reactivation(
                min_days=14,
                max_days=60,
                cooldown_days=15,
                max_per_cycle=10,
            )
            assert result["min_days_ghost"] == 14
            assert result["max_days_ghost"] == 60
            assert result["cooldown_days"] == 15
            assert result["max_per_cycle"] == 10
        finally:
            # Restore
            for k, v in originals.items():
                REACTIVATION_CONFIG[k] = v

    def test_configure_reactivation_partial_update(self):
        from core.ghost_reactivation import REACTIVATION_CONFIG, configure_reactivation

        originals = REACTIVATION_CONFIG.copy()
        try:
            result = configure_reactivation(enabled=False)
            assert result["enabled"] is False
            # Other values unchanged
            assert result["min_days_ghost"] == originals["min_days_ghost"]
        finally:
            for k, v in originals.items():
                REACTIVATION_CONFIG[k] = v

    def test_configure_reactivation_returns_copy(self):
        """Returned dict should be a copy, not a reference to the config."""
        from core.ghost_reactivation import REACTIVATION_CONFIG, configure_reactivation

        originals = REACTIVATION_CONFIG.copy()
        try:
            result = configure_reactivation()
            result["min_days_ghost"] = 999
            assert REACTIVATION_CONFIG["min_days_ghost"] != 999
        finally:
            for k, v in originals.items():
                REACTIVATION_CONFIG[k] = v

    def test_get_reactivation_stats_returns_dict(self):
        """Stats should return structured dict even with no DB."""
        from core.ghost_reactivation import get_reactivation_stats

        stats = get_reactivation_stats("nonexistent_creator")
        assert "config" in stats
        assert "pending_ghosts" in stats
        assert "total_reactivated" in stats
        assert isinstance(stats["pending_ghosts"], int)
        assert isinstance(stats["total_reactivated"], int)

    @pytest.mark.asyncio
    async def test_run_cycle_disabled(self):
        from core.ghost_reactivation import REACTIVATION_CONFIG, run_ghost_reactivation_cycle

        originals = REACTIVATION_CONFIG.copy()
        try:
            REACTIVATION_CONFIG["enabled"] = False
            result = await run_ghost_reactivation_cycle()
            assert result["status"] == "disabled"
        finally:
            for k, v in originals.items():
                REACTIVATION_CONFIG[k] = v
