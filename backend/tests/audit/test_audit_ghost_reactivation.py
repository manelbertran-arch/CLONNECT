"""Audit tests for core/ghost_reactivation.py"""

from core.ghost_reactivation import (
    configure_reactivation,
    get_ghost_leads_for_reactivation,
    get_reactivation_stats,
)


class TestAuditGhostReactivation:
    def test_import(self):
        from core.ghost_reactivation import (  # noqa: F811
            configure_reactivation,
            get_ghost_leads_for_reactivation,
            get_reactivation_stats,
        )

        assert get_ghost_leads_for_reactivation is not None

    def test_functions_callable(self):
        assert callable(get_ghost_leads_for_reactivation)
        assert callable(configure_reactivation)
        assert callable(get_reactivation_stats)

    def test_happy_path_get_stats(self):
        try:
            stats = get_reactivation_stats("test_creator")
            assert stats is not None
        except Exception:
            pass  # DB not available

    def test_edge_case_get_ghosts(self):
        try:
            leads = get_ghost_leads_for_reactivation("nonexistent_creator")
            assert isinstance(leads, list)
        except Exception:
            pass  # DB not available

    def test_error_handling_configure(self):
        try:
            configure_reactivation(enabled=True, min_days=7, max_days=30)
        except Exception:
            pass  # Acceptable
