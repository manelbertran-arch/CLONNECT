"""
Instagram Service tests - Written BEFORE implementation (TDD).
Run these tests FIRST - they should FAIL until service is created.
"""


class TestInstagramServiceImport:
    """Test instagram service can be imported."""

    def test_instagram_service_module_exists(self):
        """Instagram service module should exist."""
        import services.instagram_service
        assert services.instagram_service is not None

    def test_instagram_service_class_exists(self):
        """InstagramService class should exist."""
        from services.instagram_service import InstagramService
        assert InstagramService is not None

    def test_instagram_service_has_format_message(self):
        """InstagramService should have format_message method."""
        from services.instagram_service import InstagramService
        assert hasattr(InstagramService, 'format_message')

    def test_instagram_service_has_parse_user(self):
        """InstagramService should have parse_user method."""
        from services.instagram_service import InstagramService
        assert hasattr(InstagramService, 'parse_user')

    def test_instagram_service_has_is_rate_limited(self):
        """InstagramService should have is_rate_limited method."""
        from services.instagram_service import InstagramService
        assert hasattr(InstagramService, 'is_rate_limited')


class TestInstagramServiceInstantiation:
    """Test InstagramService instantiation."""

    def test_instagram_service_instantiation(self):
        """InstagramService should be instantiable."""
        from services.instagram_service import InstagramService
        service = InstagramService()
        assert service is not None

    def test_instagram_service_with_access_token(self):
        """InstagramService should accept access token."""
        from services.instagram_service import InstagramService
        service = InstagramService(access_token="test_token")
        assert service.access_token == "test_token"


class TestMessageFormatting:
    """Test message formatting methods."""

    def test_format_message_returns_string(self):
        """format_message should return a string."""
        from services.instagram_service import InstagramService
        service = InstagramService()
        result = service.format_message("Hello")
        assert isinstance(result, str)

    def test_format_message_truncates_long_text(self):
        """format_message should truncate long text."""
        from services.instagram_service import InstagramService
        service = InstagramService()
        long_text = "A" * 2000
        formatted = service.format_message(long_text)
        assert len(formatted) <= 1000

    def test_format_message_preserves_short_text(self):
        """format_message should preserve short text."""
        from services.instagram_service import InstagramService
        service = InstagramService()
        short_text = "Hello!"
        formatted = service.format_message(short_text)
        assert formatted == short_text

    def test_format_message_handles_empty(self):
        """format_message should handle empty string."""
        from services.instagram_service import InstagramService
        service = InstagramService()
        formatted = service.format_message("")
        assert formatted == ""


class TestUserParsing:
    """Test user data parsing."""

    def test_parse_user_returns_dict(self):
        """parse_user should return a dictionary."""
        from services.instagram_service import InstagramService
        service = InstagramService()
        raw_data = {"username": "testuser", "id": "123"}
        user = service.parse_user(raw_data)
        assert isinstance(user, dict)

    def test_parse_user_extracts_username(self):
        """parse_user should extract username."""
        from services.instagram_service import InstagramService
        service = InstagramService()
        raw_data = {"username": "testuser", "id": "123"}
        user = service.parse_user(raw_data)
        assert user["username"] == "testuser"

    def test_parse_user_extracts_id(self):
        """parse_user should extract user_id."""
        from services.instagram_service import InstagramService
        service = InstagramService()
        raw_data = {"username": "testuser", "id": "123"}
        user = service.parse_user(raw_data)
        assert user["user_id"] == "123"

    def test_parse_user_handles_missing_fields(self):
        """parse_user should handle missing fields gracefully."""
        from services.instagram_service import InstagramService
        service = InstagramService()
        raw_data = {"id": "123"}
        user = service.parse_user(raw_data)
        assert user["username"] == ""


class TestRateLimiting:
    """Test rate limiting functionality."""

    def test_initial_state_not_rate_limited(self):
        """New service should not be rate limited."""
        from services.instagram_service import InstagramService
        service = InstagramService()
        assert service.is_rate_limited() is False

    def test_increment_request_count(self):
        """increment_request_count should increase counter."""
        from services.instagram_service import InstagramService
        service = InstagramService()
        initial = service._request_count
        service.increment_request_count()
        assert service._request_count == initial + 1


class TestWebhookParsing:
    """Test webhook message parsing."""

    def test_parse_webhook_message_exists(self):
        """parse_webhook_message method should exist."""
        from services.instagram_service import InstagramService
        service = InstagramService()
        assert hasattr(service, 'parse_webhook_message')

    def test_parse_webhook_extracts_message(self):
        """parse_webhook_message should extract message text."""
        from services.instagram_service import InstagramService
        service = InstagramService()
        payload = {
            "entry": [{
                "messaging": [{
                    "sender": {"id": "123"},
                    "recipient": {"id": "456"},
                    "timestamp": 1234567890,
                    "message": {"text": "Hello!"}
                }]
            }]
        }
        result = service.parse_webhook_message(payload)
        assert result["message"] == "Hello!"
        assert result["sender_id"] == "123"

    def test_parse_webhook_handles_invalid(self):
        """parse_webhook_message should handle invalid payload."""
        from services.instagram_service import InstagramService
        service = InstagramService()
        result = service.parse_webhook_message({})
        assert result is None
