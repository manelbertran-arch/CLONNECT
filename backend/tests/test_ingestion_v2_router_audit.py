"""Audit tests for api/routers/ingestion_v2.py."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# 1. Init / Import
# ---------------------------------------------------------------------------
class TestIngestionV2RouterImport:
    """Verify that the ingestion_v2 router and its models can be imported."""

    def test_router_imports_successfully(self):
        """Router object and prefix should be correct."""
        from api.routers.ingestion_v2 import router

        assert router is not None
        assert router.prefix == "/ingestion/v2"
        assert "ingestion-v2" in router.tags

    def test_request_response_models_importable(self):
        """All Pydantic request/response models should be importable."""
        from api.routers.ingestion_v2 import IngestV2Request, InstagramV2Request, YouTubeV2Request

        # Verify model instantiation with required fields
        req = IngestV2Request(creator_id="test", url="https://example.com")
        assert req.creator_id == "test"
        assert req.max_pages == 10
        assert req.clean_before is True

        ig_req = InstagramV2Request(creator_id="test", instagram_username="testuser")
        assert ig_req.max_posts == 20

        yt_req = YouTubeV2Request(creator_id="test", channel_url="https://youtube.com/@test")
        assert yt_req.max_videos == 20
        assert yt_req.fallback_to_whisper is True


# ---------------------------------------------------------------------------
# 2. Happy Path -- Ingestion trigger (mocked pipeline)
# ---------------------------------------------------------------------------
class TestIngestionTriggerMock:
    """Test POST /ingestion/v2/website with mocked IngestionV2Pipeline."""

    @pytest.mark.asyncio
    async def test_ingest_website_success(self):
        """ingest_website_v2 should return IngestV2Response on success."""
        from api.routers.ingestion_v2 import IngestV2Request, ingest_website_v2

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.status = "success"
        mock_result.creator_id = "test_creator"
        mock_result.website_url = "https://example.com"
        mock_result.pages_scraped = 5
        mock_result.total_chars = 10000
        mock_result.products_detected = 3
        mock_result.products_verified = 2
        mock_result.products = [{"name": "Product A", "price": 99.0, "confidence": 0.9}]
        mock_result.sanity_checks = [{"check": "max_products", "passed": True}]
        mock_result.products_saved = 2
        mock_result.rag_docs_saved = 5
        mock_result.products_deleted = 0
        mock_result.duration_seconds = 12.5
        mock_result.errors = []

        mock_pipeline = AsyncMock()
        mock_pipeline.run.return_value = mock_result

        # The function does `from ingestion.v2 import IngestionV2Pipeline` lazily,
        # so we patch the module in sys.modules before the import happens.
        mock_ingestion_v2 = MagicMock()
        mock_ingestion_v2.IngestionV2Pipeline.return_value = mock_pipeline

        with patch.dict("sys.modules", {"ingestion.v2": mock_ingestion_v2}):
            request = IngestV2Request(creator_id="test_creator", url="https://example.com")
            result = await ingest_website_v2(request, db=MagicMock())

        assert result.success is True
        assert result.pages_scraped == 5
        assert result.products_verified == 2


# ---------------------------------------------------------------------------
# 3. Edge Case -- Invalid URL handling
# ---------------------------------------------------------------------------
class TestInvalidURLHandling:
    """Test behavior when the pipeline encounters errors with the URL."""

    @pytest.mark.asyncio
    async def test_ingest_website_propagates_pipeline_error(self):
        """When the pipeline raises an exception, endpoint should return 500."""
        from api.routers.ingestion_v2 import IngestV2Request, ingest_website_v2

        with patch.dict(
            "sys.modules",
            {
                "ingestion.v2": MagicMock(
                    IngestionV2Pipeline=MagicMock(side_effect=Exception("Connection refused"))
                )
            },
        ):
            request = IngestV2Request(creator_id="test_creator", url="https://invalid-domain.xyz")
            with pytest.raises(HTTPException) as exc_info:
                await ingest_website_v2(request, db=MagicMock())

            assert exc_info.value.status_code == 500

    def test_request_model_requires_url(self):
        """IngestV2Request should require a url field."""
        from api.routers.ingestion_v2 import IngestV2Request
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            IngestV2Request(creator_id="test")  # Missing url


# ---------------------------------------------------------------------------
# 4. Integration Check -- Progress tracking / status endpoint
# ---------------------------------------------------------------------------
class TestProgressTracking:
    """Test the Instagram ingestion status endpoint."""

    @pytest.mark.asyncio
    async def test_instagram_status_empty(self):
        """Status endpoint should return 'empty' when no posts indexed."""
        from api.routers.ingestion_v2 import get_instagram_ingestion_status

        mock_get_posts_count = MagicMock(return_value=0)
        mock_get_chunks = AsyncMock(return_value=[])

        with patch.dict(
            "sys.modules",
            {
                "core.tone_profile_db": MagicMock(
                    get_instagram_posts_count_db=mock_get_posts_count,
                    get_content_chunks_db=mock_get_chunks,
                )
            },
        ):
            result = await get_instagram_ingestion_status("test_creator")

        assert result["status"] == "empty"
        assert result["instagram_posts_in_db"] == 0

    @pytest.mark.asyncio
    async def test_instagram_status_ready(self):
        """Status endpoint should return 'ready' when posts are indexed."""
        from api.routers.ingestion_v2 import get_instagram_ingestion_status

        mock_get_posts_count = MagicMock(return_value=15)
        mock_get_chunks = AsyncMock(
            return_value=[
                {"source_type": "instagram_post", "content": "post1"},
                {"source_type": "instagram_post", "content": "post2"},
                {"source_type": "website", "content": "web"},
            ]
        )

        with patch.dict(
            "sys.modules",
            {
                "core.tone_profile_db": MagicMock(
                    get_instagram_posts_count_db=mock_get_posts_count,
                    get_content_chunks_db=mock_get_chunks,
                )
            },
        ):
            result = await get_instagram_ingestion_status("test_creator")

        assert result["status"] == "ready"
        assert result["instagram_posts_in_db"] == 15
        assert result["instagram_chunks_in_db"] == 2
        assert result["total_chunks_in_db"] == 3


# ---------------------------------------------------------------------------
# 5. Content type validation -- Pydantic model checks
# ---------------------------------------------------------------------------
class TestContentTypeValidation:
    """Validate that Pydantic models enforce correct types and defaults."""

    def test_ingest_v2_response_model_fields(self):
        """IngestV2Response should accept all required fields."""
        from api.routers.ingestion_v2 import IngestV2Response

        resp = IngestV2Response(
            success=True,
            status="success",
            creator_id="test",
            website_url="https://example.com",
            pages_scraped=3,
            total_chars=5000,
            products_detected=2,
            products_verified=1,
            products=[],
            sanity_checks=[],
            products_saved=1,
            rag_docs_saved=3,
            products_deleted=0,
            duration_seconds=8.2,
            errors=[],
        )
        assert resp.success is True
        assert resp.duration_seconds == 8.2

    def test_product_v2_response_allows_null_price(self):
        """ProductV2Response should allow price=None when not found."""
        from api.routers.ingestion_v2 import ProductV2Response

        product = ProductV2Response(
            name="Mystery Product",
            description="No price found",
            price=None,
            currency="EUR",
            source_url="https://example.com/product",
            price_source_text=None,
            signals_matched=["dedicated_page", "cta_present", "substantial_description"],
            confidence=0.7,
        )
        assert product.price is None
        assert product.confidence == 0.7

    def test_instagram_request_defaults(self):
        """InstagramV2Request should have sensible defaults."""
        from api.routers.ingestion_v2 import InstagramV2Request

        req = InstagramV2Request(creator_id="creator", instagram_username="user")
        assert req.max_posts == 20
        assert req.clean_before is True

    def test_youtube_request_defaults(self):
        """YouTubeV2Request should default fallback_to_whisper to True."""
        from api.routers.ingestion_v2 import YouTubeV2Request

        req = YouTubeV2Request(creator_id="creator", channel_url="https://youtube.com/@test")
        assert req.fallback_to_whisper is True
        assert req.max_videos == 20
