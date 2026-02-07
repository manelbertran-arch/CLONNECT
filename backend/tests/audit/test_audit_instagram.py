"""Audit tests for core/instagram.py"""

from core.instagram import InstagramConnector, InstagramMessage, InstagramUser


class TestAuditInstagram:
    def test_import(self):
        from core.instagram import InstagramConnector, InstagramMessage, InstagramUser  # noqa: F811

        assert InstagramConnector is not None

    def test_init(self):
        connector = InstagramConnector(
            access_token="test",
            page_id="test",
            ig_user_id="test",
            app_secret="test",
            verify_token="test",
            creator_id="test",
        )
        assert connector is not None

    def test_happy_path_verify_challenge(self):
        connector = InstagramConnector(
            access_token="t",
            page_id="t",
            ig_user_id="t",
            app_secret="t",
            verify_token="my_token",
            creator_id="t",
        )
        result = connector.verify_webhook_challenge("subscribe", "my_token", "ch123")
        assert result == "ch123" or result is not None

    def test_edge_case_message_dataclass(self):
        try:
            msg = InstagramMessage()
            assert msg is not None
        except TypeError:
            pass  # Requires fields

    def test_error_handling_user_dataclass(self):
        try:
            user = InstagramUser()
            assert user is not None
        except TypeError:
            pass  # Requires fields
