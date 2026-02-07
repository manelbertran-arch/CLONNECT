"""Audit tests for core/auth.py - AuthManager"""

import tempfile

from core.auth import APIKey, AuthManager


class TestAuditAuth:
    def test_import(self):
        from core.auth import APIKey, AuthManager  # noqa: F811

        assert APIKey is not None
        assert AuthManager is not None

    def test_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            auth = AuthManager(data_path=tmpdir)
            assert auth is not None

    def test_happy_path_generate_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            auth = AuthManager(data_path=tmpdir)
            key = auth.generate_api_key(creator_id="test_creator", name="test_key")
            assert key is not None
            assert isinstance(key, str)

    def test_edge_case_validate_invalid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            auth = AuthManager(data_path=tmpdir)
            result = auth.validate_api_key("invalid_key_12345")
            assert result is None or result is False

    def test_error_handling_revoke_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            auth = AuthManager(data_path=tmpdir)
            try:
                result = auth.revoke_api_key("nonexistent_prefix")
                assert result is False or result is None
            except (KeyError, ValueError):
                pass  # Acceptable
