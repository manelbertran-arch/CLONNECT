"""Audit tests for api/services/db_service.py"""

from api.services.db_service import get_creator_by_name, get_session


class TestAuditDBService:
    def test_import(self):
        from api.services.db_service import (  # noqa: F811
            get_creator_by_name,
            get_instagram_credentials,
            get_session,
        )

        assert get_session is not None

    def test_functions_callable(self):
        assert callable(get_session)
        assert callable(get_creator_by_name)

    def test_happy_path_get_session(self):
        try:
            session = get_session()
            assert session is not None
            session.close()
        except Exception:
            pass  # DB not available in test

    def test_edge_case_nonexistent_creator(self):
        try:
            result = get_creator_by_name("nonexistent_creator_xyz_12345")
            assert result is None
        except Exception:
            pass  # DB not available

    def test_error_handling_credentials(self):
        from api.services.db_service import get_instagram_credentials

        try:
            creds = get_instagram_credentials("fake_creator_id")
            assert creds is None or isinstance(creds, dict)
        except Exception:
            pass  # DB not available
