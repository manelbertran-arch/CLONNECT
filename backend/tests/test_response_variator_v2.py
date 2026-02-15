"""Tests for ResponseVariatorV2."""

import pytest
from services.response_variator_v2 import ResponseVariatorV2


@pytest.fixture
def variator():
    return ResponseVariatorV2()


class TestCategoryDetection:
    def test_greeting(self, variator):
        result = variator.try_pool_response("Hola!")
        assert result.matched == True
        assert result.category == "greeting"

    def test_confirmation(self, variator):
        result = variator.try_pool_response("Ok")
        assert result.matched == True
        assert result.category in ("confirmation", "conversational")

    def test_laugh(self, variator):
        result = variator.try_pool_response("Jajaja")
        assert result.matched == True
        assert result.category in ("laugh", "humor")

    def test_thanks(self, variator):
        result = variator.try_pool_response("Gracias!")
        assert result.matched == True
        assert result.category in ("thanks", "gratitude")

    def test_emoji_only(self, variator):
        result = variator.try_pool_response("😊")
        assert result.matched == True
        assert result.category == "emoji"

    def test_complex_not_matched(self, variator):
        result = variator.try_pool_response("Me mudé a Barcelona y estoy buscando trabajo")
        assert result.matched == False


class TestPoolResponses:
    def test_greeting_returns_valid(self, variator):
        result = variator.try_pool_response("Hola!")
        assert result.response is not None
        assert len(result.response) > 0
        assert len(result.response) < 20

    def test_confirmation_returns_valid(self, variator):
        result = variator.try_pool_response("Dale")
        assert result.response is not None
        assert len(result.response) < 50

    def test_randomness(self, variator):
        responses = set()
        for _ in range(20):
            result = variator.try_pool_response("Hola!")
            responses.add(result.response)

        assert len(responses) > 1


class TestConfidence:
    def test_high_confidence_greeting(self, variator):
        result = variator.try_pool_response("Hola")
        assert result.confidence >= 0.8

    def test_high_confidence_confirmation(self, variator):
        result = variator.try_pool_response("Ok")
        assert result.confidence >= 0.8


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
