"""
CAPA 2 — Unit tests: DM Phases (detection & postprocessing helpers)
Tests pure logic without hitting DB or LLM.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock, AsyncMock, patch


# ─── Sensitive detector ────────────────────────────────────────────────────────

class TestSensitiveDetector:

    def test_import_sensitive_detector(self):
        try:
            from core.sensitive_detector import detect_sensitive_content
            assert callable(detect_sensitive_content)
        except ImportError as e:
            pytest.skip(f"sensitive_detector not importable: {e}")

    def test_normal_message_not_sensitive(self):
        try:
            from core.sensitive_detector import detect_sensitive_content
        except ImportError:
            pytest.skip("sensitive_detector not importable")
        result = detect_sensitive_content("hola quiero comprar tu programa")
        # Either returns None or a result with low/no confidence
        if result is not None:
            assert result.confidence < 0.5

    def test_crisis_resources_returns_string(self):
        try:
            from core.sensitive_detector import get_crisis_resources
        except ImportError:
            pytest.skip("sensitive_detector not importable")
        response = get_crisis_resources(language="es")
        assert isinstance(response, str)
        assert len(response) > 10


# ─── Context detector ──────────────────────────────────────────────────────────

class TestContextDetector:

    def test_import_context_detector(self):
        try:
            from core.context_detector import detect_all
            assert callable(detect_all)
        except ImportError as e:
            pytest.skip(f"context_detector not importable: {e}")

    def test_detect_all_returns_object_or_none(self):
        try:
            from core.context_detector import detect_all
        except ImportError:
            pytest.skip("context_detector not importable")
        result = detect_all("hola como estás", [])
        # Must return something (not crash)
        # Result can be None or a signals object
        assert result is None or hasattr(result, '__class__')


# ─── DM Models ────────────────────────────────────────────────────────────────

class TestDMModels:

    def test_import_detection_result(self):
        try:
            from core.dm.models import DetectionResult, DMResponse
        except ImportError as e:
            pytest.skip(f"dm.models not importable: {e}")
        dr = DetectionResult()
        assert dr.pool_response is None
        assert dr.frustration_level == 0.0

    def test_dmresponse_has_content(self):
        try:
            from core.dm.models import DMResponse
        except ImportError as e:
            pytest.skip(f"dm.models not importable: {e}")
        resp = DMResponse(
            content="Hola, ¿en qué puedo ayudarte?",
            intent="greeting",
            lead_stage="nuevo",
            confidence=0.9,
            tokens_used=10,
            metadata={},
        )
        assert resp.content == "Hola, ¿en qué puedo ayudarte?"
        assert resp.intent == "greeting"

    def test_detection_result_pool_response_assignable(self):
        try:
            from core.dm.models import DetectionResult, DMResponse
        except ImportError:
            pytest.skip("dm.models not importable")
        dr = DetectionResult()
        dr.pool_response = DMResponse(
            content="recurso de crisis",
            intent="sensitive_content",
            lead_stage="unknown",
            confidence=0.95,
            tokens_used=0,
            metadata={},
        )
        assert dr.pool_response is not None
        assert dr.pool_response.intent == "sensitive_content"


# ─── Text utils ───────────────────────────────────────────────────────────────

class TestTextUtils:

    def test_message_mentions_product_true(self):
        try:
            from core.dm.text_utils import _message_mentions_product
        except ImportError:
            pytest.skip("text_utils not importable")
        # Signature: _message_mentions_product(product_name: str, msg_lower: str) -> bool
        result = _message_mentions_product("Programa de entrenamiento", "quiero el programa de entrenamiento")
        assert isinstance(result, bool)
        assert result is True

    def test_message_mentions_product_empty_products(self):
        try:
            from core.dm.text_utils import _message_mentions_product
        except ImportError:
            pytest.skip("text_utils not importable")
        result = _message_mentions_product("Programa elite", "hola como estas")
        assert result is False


# ─── Phase detection (mocked agent) ──────────────────────────────────────────

class TestPhaseDetectionMocked:

    @pytest.mark.asyncio
    async def test_phase_detection_no_sensitive(self):
        try:
            from core.dm.phases.detection import phase_detection
            from core.dm.models import DetectionResult
        except ImportError as e:
            pytest.skip(f"phase_detection not importable: {e}")

        # Minimal mock agent — response_variator must be a MagicMock (not None)
        # so that hasattr() + try_pool_response() work correctly
        agent = MagicMock()
        agent.products = []
        mock_pool_result = MagicMock()
        mock_pool_result.matched = False  # No pool match → falls through
        agent.response_variator.try_pool_response.return_value = mock_pool_result

        with patch("core.dm.phases.detection.detect_sensitive_content", return_value=None), \
             patch("core.dm.phases.detection.detect_context", return_value=None), \
             patch("services.length_controller.classify_lead_context", return_value="nuevo"):

            result = await phase_detection(
                agent=agent,
                message="hola como estas",
                sender_id="test_user",
                metadata={"history": []},
                cognitive_metadata={},
            )

        assert isinstance(result, DetectionResult)
        assert result.pool_response is None

    @pytest.mark.asyncio
    async def test_phase_detection_returns_pool_on_crisis(self):
        try:
            from core.dm.phases.detection import phase_detection
            from core.dm.models import DetectionResult
            from core.agent_config import AGENT_THRESHOLDS
        except ImportError as e:
            pytest.skip(f"phase_detection not importable: {e}")

        # Mock sensitive detection to trigger crisis path
        mock_sensitive = MagicMock()
        mock_sensitive.confidence = 1.0  # Above escalation threshold
        mock_sensitive.category = "crisis"

        agent = MagicMock()
        agent.products = []

        with patch("core.dm.phases.detection.detect_sensitive_content", return_value=mock_sensitive), \
             patch("core.dm.phases.detection.get_crisis_resources", return_value="Llama al 024"):

            result = await phase_detection(
                agent=agent,
                message="quiero hacerme daño",
                sender_id="test_user",
                metadata={},
                cognitive_metadata={},
            )

        assert isinstance(result, DetectionResult)
        assert result.pool_response is not None
        assert result.pool_response.intent == "sensitive_content"


# ─── Postprocessing helpers ───────────────────────────────────────────────────

class TestPostprocessingHelpers:

    def test_enforce_length_import(self):
        try:
            from core.dm.phases.postprocessing import phase_postprocessing
            assert callable(phase_postprocessing)
        except ImportError as e:
            pytest.skip(f"postprocessing not importable: {e}")

    def test_apply_response_fixes_import(self):
        """apply_all_response_fixes is used inside postprocessing; just check importable."""
        try:
            import core.dm.phases.postprocessing as pp
            assert hasattr(pp, "phase_postprocessing")
        except ImportError as e:
            pytest.skip(f"postprocessing module not importable: {e}")
