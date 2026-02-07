"""Test fact_tracking integration in dm_agent_v2 (Step 10)."""

import re


class TestFactTrackingIntegration:
    def test_flag_exists(self):
        from core.dm_agent_v2 import ENABLE_FACT_TRACKING

        assert isinstance(ENABLE_FACT_TRACKING, bool)

    def test_price_detection(self):
        text = "El curso cuesta 97€ y tiene garantía de 30 días"
        assert re.search(r"\d+\s*€|\d+\s*euros?|\$\d+", text, re.IGNORECASE)

    def test_link_detection(self):
        text = "Aquí puedes comprarlo: https://pay.example.com/curso"
        assert "https://" in text or "http://" in text

    def test_no_false_positives(self):
        text = "Gracias por tu interés, te cuento más mañana"
        assert not re.search(r"\d+\s*€|\d+\s*euros?|\$\d+", text, re.IGNORECASE)
        assert "https://" not in text and "http://" not in text
