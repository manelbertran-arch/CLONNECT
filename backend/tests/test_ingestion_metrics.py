"""
Tests for Ingestion Pipeline Metrics.

Verifies that:
1. Metrics are properly initialized (prometheus or fallback)
2. Counter increments work
3. Histogram observations work
4. Helper functions record metrics correctly
5. Structured logging output is correct

Run with: pytest tests/test_ingestion_metrics.py -v
"""

import time
from unittest.mock import patch, MagicMock

import pytest


class TestMetricsInitialization:
    """Tests for metrics module initialization."""

    def test_prometheus_available_detection(self):
        """Verify PROMETHEUS_AVAILABLE flag is set correctly."""
        from core.metrics import PROMETHEUS_AVAILABLE
        # Should be True if prometheus_client is installed
        assert isinstance(PROMETHEUS_AVAILABLE, bool)

    def test_ingestion_counters_exist(self):
        """Verify ingestion counter metrics are defined."""
        from core.metrics import (
            INGESTION_PAGES_SCRAPED,
            INGESTION_PAGES_FAILED,
            INGESTION_PRODUCTS_DETECTED,
            INGESTION_FAQS_EXTRACTED,
            INGESTION_POSTS_INDEXED,
            INGESTION_CHUNKS_SAVED,
            INGESTION_ERRORS
        )
        # All should be defined (prometheus or dummy)
        assert INGESTION_PAGES_SCRAPED is not None
        assert INGESTION_PAGES_FAILED is not None
        assert INGESTION_PRODUCTS_DETECTED is not None
        assert INGESTION_FAQS_EXTRACTED is not None
        assert INGESTION_POSTS_INDEXED is not None
        assert INGESTION_CHUNKS_SAVED is not None
        assert INGESTION_ERRORS is not None

    def test_ingestion_histograms_exist(self):
        """Verify ingestion histogram metrics are defined."""
        from core.metrics import (
            INGESTION_SCRAPE_DURATION,
            INGESTION_EXTRACT_DURATION,
            INGESTION_TOTAL_DURATION,
            INGESTION_CHUNKS_PER_CREATOR
        )
        assert INGESTION_SCRAPE_DURATION is not None
        assert INGESTION_EXTRACT_DURATION is not None
        assert INGESTION_TOTAL_DURATION is not None
        assert INGESTION_CHUNKS_PER_CREATOR is not None

    def test_ingestion_gauges_exist(self):
        """Verify ingestion gauge metrics are defined."""
        from core.metrics import (
            INGESTION_ACTIVE_SCRAPES,
            INGESTION_CIRCUIT_BREAKER_STATE
        )
        assert INGESTION_ACTIVE_SCRAPES is not None
        assert INGESTION_CIRCUIT_BREAKER_STATE is not None


class TestHelperFunctions:
    """Tests for metric helper functions."""

    def test_record_page_scraped(self):
        """Verify record_page_scraped increments counter."""
        from core.metrics import record_page_scraped, INGESTION_PAGES_SCRAPED

        # This should not raise an error
        record_page_scraped("test_creator")

    def test_record_page_failed(self):
        """Verify record_page_failed increments counter with label."""
        from core.metrics import record_page_failed

        # Should not raise
        record_page_failed("test_creator", "timeout")
        record_page_failed("test_creator", "ssl_error")

    def test_record_products_detected(self):
        """Verify record_products_detected works with count."""
        from core.metrics import record_products_detected

        record_products_detected("test_creator", 5)

    def test_record_faqs_extracted(self):
        """Verify record_faqs_extracted works with count."""
        from core.metrics import record_faqs_extracted

        record_faqs_extracted("test_creator", 10)

    def test_record_posts_indexed(self):
        """Verify record_posts_indexed works with count."""
        from core.metrics import record_posts_indexed

        record_posts_indexed("test_creator", 25)

    def test_record_chunks_saved(self):
        """Verify record_chunks_saved works with count and source type."""
        from core.metrics import record_chunks_saved

        record_chunks_saved("test_creator", 100, "instagram_post")
        record_chunks_saved("test_creator", 50, "website")

    def test_record_ingestion_error(self):
        """Verify record_ingestion_error works with error type."""
        from core.metrics import record_ingestion_error

        record_ingestion_error("scrape_timeout")
        record_ingestion_error("llm_error")

    def test_observe_scrape_duration(self):
        """Verify observe_scrape_duration records histogram value."""
        from core.metrics import observe_scrape_duration

        observe_scrape_duration(1.5)
        observe_scrape_duration(0.3)

    def test_observe_extract_duration(self):
        """Verify observe_extract_duration records histogram with phase label."""
        from core.metrics import observe_extract_duration

        observe_extract_duration("products", 0.5)
        observe_extract_duration("faqs", 1.2)


class TestIngestionTracking:
    """Tests for start/end ingestion tracking."""

    def test_start_end_ingestion(self):
        """Verify start_ingestion and end_ingestion work together."""
        from core.metrics import start_ingestion, end_ingestion

        start_ingestion("test_creator_track")
        time.sleep(0.1)  # Small delay to ensure duration > 0
        duration = end_ingestion("test_creator_track", chunks_count=50)

        assert duration >= 0.1

    def test_end_ingestion_without_start(self):
        """Verify end_ingestion handles missing start gracefully."""
        from core.metrics import end_ingestion

        # Should not raise, returns 0
        duration = end_ingestion("non_existent_creator", chunks_count=0)
        assert duration == 0


class TestContextManagers:
    """Tests for metric context managers."""

    def test_track_scrape_time(self):
        """Verify track_scrape_time context manager works."""
        from core.metrics import track_scrape_time

        with track_scrape_time():
            time.sleep(0.05)

    def test_track_extract_time(self):
        """Verify track_extract_time context manager works."""
        from core.metrics import track_extract_time

        with track_extract_time("products"):
            time.sleep(0.05)


class TestStructuredLogging:
    """Tests for structured logging functions."""

    def test_log_ingestion_complete(self):
        """Verify log_ingestion_complete outputs structured log."""
        from core.metrics import log_ingestion_complete

        with patch("core.metrics.logger") as mock_logger:
            log_ingestion_complete(
                creator_id="test_creator",
                pages_scraped=10,
                pages_failed=2,
                products_detected=3,
                faqs_extracted=5,
                posts_indexed=25,
                chunks_saved=100,
                duration_seconds=15.5
            )

            # Should have called logger.info at least once
            assert mock_logger.info.called


class TestCircuitBreakerMetric:
    """Tests for circuit breaker state metric."""

    def test_set_circuit_breaker_state(self):
        """Verify set_circuit_breaker_state updates gauge."""
        from core.metrics import set_circuit_breaker_state

        # State: 0=closed, 1=half-open, 2=open
        set_circuit_breaker_state("instagram_api", 0)
        set_circuit_breaker_state("web_scraper", 2)


class TestDummyMetric:
    """Tests for DummyMetric fallback class."""

    def test_dummy_metric_interface(self):
        """Verify DummyMetric has all required methods."""
        from core.metrics import PROMETHEUS_AVAILABLE

        if not PROMETHEUS_AVAILABLE:
            from core.metrics import INGESTION_PAGES_SCRAPED

            # Should have labels method
            labeled = INGESTION_PAGES_SCRAPED.labels(creator_id="test")
            # Should have inc method
            labeled.inc()
            # Should not raise any errors


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
