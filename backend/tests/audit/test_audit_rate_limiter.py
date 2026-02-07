"""Audit tests for core/rate_limiter.py - RateLimiter"""

from core.rate_limiter import RateLimiter


class TestAuditRateLimiter:
    def test_import(self):
        from core.rate_limiter import RateLimiter  # noqa: F811

        assert RateLimiter is not None

    def test_init(self):
        rl = RateLimiter()
        assert rl is not None

    def test_happy_path_allows_request(self):
        rl = RateLimiter()
        allowed, msg = rl.check_limit("test_user_audit")
        assert allowed is True

    def test_edge_case_many_requests(self):
        rl = RateLimiter(requests_per_minute=2)
        rl.check_limit("user1_audit")
        rl.check_limit("user1_audit")
        result, msg = rl.check_limit("user1_audit")
        assert result is False

    def test_error_handling_empty_key(self):
        rl = RateLimiter()
        result, msg = rl.check_limit("")
        assert isinstance(result, bool)
