"""Audit tests for services/cloudinary_service.py."""

import os
from datetime import datetime
from unittest.mock import patch

from services.cloudinary_service import (
    CloudinaryService,
    MediaType,
    UploadResult,
    get_cloudinary_service,
)


class TestCloudinaryServiceInit:
    """Test 1: init/import - Service initializes and detects configuration."""

    def test_upload_result_dataclass_defaults(self):
        result = UploadResult(success=False)
        assert result.success is False
        assert result.url is None
        assert result.public_id is None
        assert result.error is None

    def test_media_type_enum_values(self):
        assert MediaType.IMAGE.value == "image"
        assert MediaType.VIDEO.value == "video"
        assert MediaType.AUDIO.value == "audio"
        assert MediaType.RAW.value == "raw"

    def test_service_not_configured_without_env(self):
        """Without any CLOUDINARY env vars, service remains unconfigured."""
        svc = CloudinaryService.__new__(CloudinaryService)
        svc._configured = False
        # Simulate _configure with no env
        with patch.dict(os.environ, {}, clear=True):
            with patch("cloudinary.config"):
                svc._configured = False
                svc._configure()
        assert svc.is_configured is False

    @patch.dict(
        os.environ,
        {
            "CLOUDINARY_CLOUD_NAME": "test_cloud",
            "CLOUDINARY_API_KEY": "123",
            "CLOUDINARY_API_SECRET": "secret",
        },
    )
    def test_service_configured_with_individual_vars(self):
        with patch("cloudinary.config") as _mock_config:  # noqa: F841
            svc = CloudinaryService()
        assert svc.is_configured is True

    def test_singleton_returns_same_instance(self):
        import services.cloudinary_service as mod

        mod._cloudinary_service = None
        s1 = get_cloudinary_service()
        s2 = get_cloudinary_service()
        assert s1 is s2
        mod._cloudinary_service = None  # cleanup


class TestCloudinaryUploadMock:
    """Test 2: happy path - Upload from URL succeeds with mocked Cloudinary."""

    def _make_configured_service(self):
        svc = CloudinaryService.__new__(CloudinaryService)
        svc._configured = True
        return svc

    @patch("cloudinary.uploader.upload")
    def test_upload_from_url_success(self, mock_upload):
        mock_upload.return_value = {
            "secure_url": "https://res.cloudinary.com/test/image.jpg",
            "public_id": "clonnect/img_123",
            "resource_type": "image",
        }
        svc = self._make_configured_service()
        result = svc.upload_from_url(
            "https://instagram.com/temp/photo.jpg",
            media_type="image",
            folder="clonnect/creator1",
        )
        assert result.success is True
        assert result.url == "https://res.cloudinary.com/test/image.jpg"
        assert result.public_id == "clonnect/img_123"
        assert isinstance(result.uploaded_at, datetime)

    @patch("cloudinary.uploader.upload")
    def test_upload_from_url_with_tags(self, mock_upload):
        mock_upload.return_value = {
            "secure_url": "https://cdn.example.com/v.mp4",
            "public_id": "vid1",
            "resource_type": "video",
        }
        svc = self._make_configured_service()
        result = svc.upload_from_url(
            "https://example.com/v.mp4",
            media_type="video",
            tags=["instagram", "reel"],
        )
        assert result.success is True
        call_kwargs = mock_upload.call_args
        assert "tags" in call_kwargs[1]

    @patch("cloudinary.uploader.upload")
    def test_upload_from_file_success(self, mock_upload):
        mock_upload.return_value = {
            "secure_url": "https://cdn.example.com/file.jpg",
            "public_id": "file1",
            "resource_type": "image",
        }
        svc = self._make_configured_service()
        with patch("os.path.exists", return_value=True):
            result = svc.upload_from_file("/tmp/photo.jpg")
        assert result.success is True
        assert result.url == "https://cdn.example.com/file.jpg"

    @patch("cloudinary.uploader.upload")
    def test_upload_passes_folder_option(self, mock_upload):
        mock_upload.return_value = {
            "secure_url": "https://cdn.example.com/img.jpg",
            "public_id": "test",
            "resource_type": "image",
        }
        svc = self._make_configured_service()
        svc.upload_from_url(
            "https://example.com/img.jpg",
            folder="clonnect/c1/2026-02",
        )
        _, kwargs = mock_upload.call_args
        assert kwargs["folder"] == "clonnect/c1/2026-02"

    @patch("cloudinary.uploader.upload")
    def test_upload_preserves_original_url(self, mock_upload):
        mock_upload.return_value = {
            "secure_url": "https://cdn.example.com/img.jpg",
            "public_id": "test",
            "resource_type": "image",
        }
        svc = self._make_configured_service()
        original = "https://scontent.instagram.com/temp/12345.jpg"
        result = svc.upload_from_url(original)
        assert result.original_url == original


class TestCloudinaryInvalidUrl:
    """Test 3: edge case - Invalid URLs and unconfigured service handled gracefully."""

    def test_upload_when_not_configured_returns_error(self):
        svc = CloudinaryService.__new__(CloudinaryService)
        svc._configured = False
        result = svc.upload_from_url("https://example.com/photo.jpg")
        assert result.success is False
        assert "not configured" in result.error

    def test_upload_from_file_not_found(self):
        svc = CloudinaryService.__new__(CloudinaryService)
        svc._configured = True
        with patch("os.path.exists", return_value=False):
            result = svc.upload_from_file("/nonexistent/photo.jpg")
        assert result.success is False
        assert "File not found" in result.error

    @patch("cloudinary.uploader.upload", side_effect=Exception("Network error"))
    def test_upload_from_url_exception_returns_error(self, mock_upload):
        svc = CloudinaryService.__new__(CloudinaryService)
        svc._configured = True
        result = svc.upload_from_url("https://example.com/broken.jpg")
        assert result.success is False
        assert "Network error" in result.error

    def test_upload_from_file_not_configured(self):
        svc = CloudinaryService.__new__(CloudinaryService)
        svc._configured = False
        result = svc.upload_from_file("/tmp/photo.jpg")
        assert result.success is False
        assert "not configured" in result.error

    @patch("cloudinary.uploader.upload", side_effect=Exception("timeout"))
    def test_upload_from_file_exception_returns_error(self, mock_upload):
        svc = CloudinaryService.__new__(CloudinaryService)
        svc._configured = True
        with patch("os.path.exists", return_value=True):
            result = svc.upload_from_file("/tmp/photo.jpg")
        assert result.success is False
        assert "timeout" in result.error


class TestCloudinaryTransformationParams:
    """Test 4: error handling - Resource type mapping is correct."""

    def test_image_types_map_to_image(self):
        svc = CloudinaryService.__new__(CloudinaryService)
        svc._configured = True
        for media in ("image", "photo", "sticker", "gif"):
            assert svc._get_resource_type(media) == "image"

    def test_video_types_map_to_video(self):
        svc = CloudinaryService.__new__(CloudinaryService)
        svc._configured = True
        for media in ("video", "reel"):
            assert svc._get_resource_type(media) == "video"

    def test_audio_maps_to_video(self):
        """Cloudinary handles audio as video resource type."""
        svc = CloudinaryService.__new__(CloudinaryService)
        svc._configured = True
        assert svc._get_resource_type("audio") == "video"

    def test_unknown_type_maps_to_raw(self):
        svc = CloudinaryService.__new__(CloudinaryService)
        svc._configured = True
        assert svc._get_resource_type("pdf") == "raw"
        assert svc._get_resource_type("document") == "raw"

    def test_get_stats_when_not_configured(self):
        svc = CloudinaryService.__new__(CloudinaryService)
        svc._configured = False
        stats = svc.get_stats()
        assert stats["configured"] is False
        assert stats["cloud_name"] == "not_set"


class TestCloudinaryDeleteMock:
    """Test 5: integration check - Delete operation works with mock."""

    @patch("cloudinary.uploader.destroy")
    def test_delete_success(self, mock_destroy):
        mock_destroy.return_value = {"result": "ok"}
        svc = CloudinaryService.__new__(CloudinaryService)
        svc._configured = True
        assert svc.delete("clonnect/img_123") is True

    @patch("cloudinary.uploader.destroy")
    def test_delete_not_found(self, mock_destroy):
        mock_destroy.return_value = {"result": "not found"}
        svc = CloudinaryService.__new__(CloudinaryService)
        svc._configured = True
        assert svc.delete("nonexistent") is False

    def test_delete_when_not_configured(self):
        svc = CloudinaryService.__new__(CloudinaryService)
        svc._configured = False
        assert svc.delete("some_id") is False

    @patch("cloudinary.uploader.destroy", side_effect=Exception("API error"))
    def test_delete_exception_returns_false(self, mock_destroy):
        svc = CloudinaryService.__new__(CloudinaryService)
        svc._configured = True
        assert svc.delete("some_id") is False

    @patch("cloudinary.uploader.destroy")
    def test_delete_passes_resource_type(self, mock_destroy):
        mock_destroy.return_value = {"result": "ok"}
        svc = CloudinaryService.__new__(CloudinaryService)
        svc._configured = True
        svc.delete("vid_123", resource_type="video")
        mock_destroy.assert_called_once_with("vid_123", resource_type="video")
