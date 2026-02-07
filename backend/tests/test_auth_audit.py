"""Audit tests for core/auth.py."""

import json
import os
import tempfile
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Test 1: Init / Import
# ---------------------------------------------------------------------------


class TestAuthImport:
    """Verify module imports and key constants."""

    def test_import_module(self):
        from core.auth import (
            API_KEY_LENGTH,
            API_KEY_PREFIX,
            get_auth_manager,
            is_admin_key,
            validate_api_key,
        )

        assert API_KEY_PREFIX == "clk_"
        assert API_KEY_LENGTH == 32
        assert callable(get_auth_manager)
        assert callable(validate_api_key)
        assert callable(is_admin_key)

    def test_api_key_dataclass(self):
        from core.auth import APIKey

        key = APIKey(
            key_hash="abc123",
            key_prefix="clk_abcd1234",
            creator_id="test_creator",
            created_at="2026-01-01T00:00:00",
            active=True,
            name="Test Key",
        )
        assert key.key_hash == "abc123"
        assert key.active is True

        # to_dict and from_dict round-trip
        d = key.to_dict()
        assert d["creator_id"] == "test_creator"
        restored = APIKey.from_dict(d)
        assert restored.key_hash == key.key_hash
        assert restored.name == key.name


# ---------------------------------------------------------------------------
# Test 2: Happy Path -- Key generation and validation
# ---------------------------------------------------------------------------


class TestAuthHappyPath:
    """Happy path: generate key, then validate it."""

    def test_generate_and_validate_api_key(self):
        from core.auth import AuthManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AuthManager(data_path=tmpdir)

            # Generate a key for a creator
            full_key = mgr.generate_api_key("creator_manel", name="Test Key")

            # Key should have the correct prefix
            assert full_key.startswith("clk_")
            # 4 prefix chars + 64 hex chars = 68 total
            assert len(full_key) == 4 + 64

            # Validate the key
            creator_id = mgr.validate_api_key(full_key)
            assert creator_id == "creator_manel"

    def test_key_hash_is_deterministic(self):
        from core.auth import AuthManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AuthManager(data_path=tmpdir)
            h1 = mgr._hash_key("clk_abc123")
            h2 = mgr._hash_key("clk_abc123")
            assert h1 == h2

    def test_list_api_keys_for_creator(self):
        from core.auth import AuthManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AuthManager(data_path=tmpdir)
            mgr.generate_api_key("creator_a", name="Key 1")
            mgr.generate_api_key("creator_a", name="Key 2")
            mgr.generate_api_key("creator_b", name="Key B")

            keys_a = mgr.list_api_keys("creator_a")
            assert len(keys_a) == 2

            keys_b = mgr.list_api_keys("creator_b")
            assert len(keys_b) == 1


# ---------------------------------------------------------------------------
# Test 3: Happy Path -- Admin key and hashing
# ---------------------------------------------------------------------------


class TestAuthAdminAndHashing:
    """Admin key validation and password hashing."""

    def test_admin_key_validation(self):
        from core.auth import AuthManager

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"CLONNECT_ADMIN_KEY": "super_secret_admin"}):
                mgr = AuthManager(data_path=tmpdir)

                result = mgr.validate_api_key("super_secret_admin")
                assert result == "__admin__"

                assert mgr.is_admin_key("super_secret_admin") is True
                assert mgr.is_admin_key("wrong_key") is False

    def test_hash_key_produces_hex_string(self):
        from core.auth import AuthManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AuthManager(data_path=tmpdir)
            h = mgr._hash_key("clk_test_key_1234")
            # Should be 16 hex chars
            assert len(h) == 16
            assert all(c in "0123456789abcdef" for c in h)


# ---------------------------------------------------------------------------
# Test 4: Error Handling -- Invalid credentials and revocation
# ---------------------------------------------------------------------------


class TestAuthErrorHandling:
    """Error handling for invalid keys and revocation."""

    def test_validate_empty_key_returns_none(self):
        from core.auth import AuthManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AuthManager(data_path=tmpdir)
            assert mgr.validate_api_key("") is None
            assert mgr.validate_api_key(None) is None

    def test_validate_unknown_key_returns_none(self):
        from core.auth import AuthManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AuthManager(data_path=tmpdir)
            assert mgr.validate_api_key("clk_nonexistent_key_abcdef") is None

    def test_revoke_then_validate_fails(self):
        from core.auth import AuthManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AuthManager(data_path=tmpdir)

            full_key = mgr.generate_api_key("creator_x")
            assert mgr.validate_api_key(full_key) == "creator_x"

            # Revoke
            revoked = mgr.revoke_api_key(full_key)
            assert revoked is True

            # Now validation should fail
            assert mgr.validate_api_key(full_key) is None

    def test_revoke_nonexistent_key_returns_false(self):
        from core.auth import AuthManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AuthManager(data_path=tmpdir)
            assert mgr.revoke_api_key("clk_does_not_exist") is False

    def test_delete_api_key(self):
        from core.auth import AuthManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AuthManager(data_path=tmpdir)

            full_key = mgr.generate_api_key("creator_d")
            assert mgr.delete_api_key(full_key) is True
            assert mgr.validate_api_key(full_key) is None

            # Delete again returns False
            assert mgr.delete_api_key(full_key) is False


# ---------------------------------------------------------------------------
# Test 5: Integration Check -- Persistence and key info
# ---------------------------------------------------------------------------


class TestAuthIntegration:
    """Integration: keys persist to disk and reload correctly."""

    def test_keys_persist_across_instances(self):
        from core.auth import AuthManager

        with tempfile.TemporaryDirectory() as tmpdir:
            # Instance 1: generate key
            mgr1 = AuthManager(data_path=tmpdir)
            full_key = mgr1.generate_api_key("persistent_creator", name="Persist Test")

            # Instance 2: reload from same path
            mgr2 = AuthManager(data_path=tmpdir)
            creator_id = mgr2.validate_api_key(full_key)
            assert creator_id == "persistent_creator"

    def test_get_key_info(self):
        from core.auth import AuthManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AuthManager(data_path=tmpdir)
            full_key = mgr.generate_api_key("info_creator", name="Info Key")

            info = mgr.get_key_info(full_key)
            assert info is not None
            assert info["creator_id"] == "info_creator"
            assert info["name"] == "Info Key"
            assert info["active"] is True

    def test_get_key_info_by_prefix(self):
        from core.auth import AuthManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AuthManager(data_path=tmpdir)
            full_key = mgr.generate_api_key("prefix_creator")

            prefix = full_key[:12]  # clk_ + 8 chars
            info = mgr.get_key_info(prefix)
            assert info is not None
            assert info["creator_id"] == "prefix_creator"

    def test_list_all_keys_admin(self):
        from core.auth import AuthManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AuthManager(data_path=tmpdir)
            mgr.generate_api_key("c1")
            mgr.generate_api_key("c2")
            mgr.generate_api_key("c1")

            all_keys = mgr.list_all_keys()
            assert len(all_keys) == 3

    def test_json_file_created(self):
        from core.auth import AuthManager

        with tempfile.TemporaryDirectory() as tmpdir:
            mgr = AuthManager(data_path=tmpdir)
            mgr.generate_api_key("file_creator")

            keys_file = os.path.join(tmpdir, "auth", "api_keys.json")
            assert os.path.exists(keys_file)

            with open(keys_file, "r") as f:
                data = json.load(f)

            assert "keys" in data
            assert "updated_at" in data
            assert len(data["keys"]) == 1
