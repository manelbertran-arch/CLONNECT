"""
Cloudinary Service.

Provides permanent media storage for Instagram/WhatsApp attachments.
Instagram media URLs expire after ~24 hours, so we upload to Cloudinary
for permanent storage.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class MediaType(Enum):
    """Supported media types for upload."""

    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    RAW = "raw"  # PDFs, other files


@dataclass
class UploadResult:
    """
    Result of a Cloudinary upload operation.

    Attributes:
        success: Whether the upload succeeded
        url: Permanent Cloudinary URL (secure_url)
        public_id: Cloudinary public ID for the asset
        resource_type: Type of resource (image, video, raw)
        original_url: Original temporary URL that was uploaded
        error: Error message if upload failed
    """

    success: bool
    url: Optional[str] = None
    public_id: Optional[str] = None
    resource_type: Optional[str] = None
    original_url: Optional[str] = None
    error: Optional[str] = None
    uploaded_at: Optional[datetime] = None


class CloudinaryService:
    """
    Service for uploading media to Cloudinary for permanent storage.

    Provides:
    - Upload from URL (for Instagram/WhatsApp media)
    - Upload from file path
    - Resource type detection
    - Folder organization by creator/date

    Environment Variables:
        CLOUDINARY_URL: Full Cloudinary URL (cloudinary://API_KEY:API_SECRET@CLOUD_NAME)
        OR individual variables:
        CLOUDINARY_CLOUD_NAME: Cloud name
        CLOUDINARY_API_KEY: API key
        CLOUDINARY_API_SECRET: API secret
    """

    def __init__(self) -> None:
        """Initialize Cloudinary service with environment configuration."""
        self._configured = False
        self._configure()

    def _configure(self) -> None:
        """Configure Cloudinary from environment variables."""
        try:
            import cloudinary

            # CLOUDINARY_URL takes precedence (Railway format)
            cloudinary_url = os.getenv("CLOUDINARY_URL")

            if cloudinary_url:
                # cloudinary auto-configures from CLOUDINARY_URL env var
                cloudinary.config()
                self._configured = True
                logger.info("[CloudinaryService] Configured from CLOUDINARY_URL")
            else:
                # Fallback to individual env vars
                cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
                api_key = os.getenv("CLOUDINARY_API_KEY")
                api_secret = os.getenv("CLOUDINARY_API_SECRET")

                if all([cloud_name, api_key, api_secret]):
                    cloudinary.config(
                        cloud_name=cloud_name,
                        api_key=api_key,
                        api_secret=api_secret,
                        secure=True,
                    )
                    self._configured = True
                    logger.info("[CloudinaryService] Configured from individual env vars")
                else:
                    logger.warning(
                        "[CloudinaryService] Not configured - missing CLOUDINARY_URL or "
                        "CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET"
                    )

        except ImportError:
            logger.error("[CloudinaryService] cloudinary package not installed")
        except Exception as e:
            logger.error(f"[CloudinaryService] Configuration error: {e}")

    @property
    def is_configured(self) -> bool:
        """Check if Cloudinary is properly configured."""
        return self._configured

    def _get_resource_type(self, media_type: str) -> str:
        """
        Map media type to Cloudinary resource type.

        Args:
            media_type: Media type from Instagram (image, video, audio, etc.)

        Returns:
            Cloudinary resource type (image, video, raw)
        """
        media_type_lower = media_type.lower()

        if media_type_lower in ("image", "photo", "sticker", "gif"):
            return "image"
        elif media_type_lower in ("video", "reel"):
            return "video"
        elif media_type_lower == "audio":
            return "video"  # Cloudinary handles audio as video
        else:
            return "raw"

    def upload_from_url(
        self,
        url: str,
        media_type: str = "image",
        folder: Optional[str] = None,
        public_id: Optional[str] = None,
        tags: Optional[list] = None,
    ) -> UploadResult:
        """
        Upload media from a URL to Cloudinary.

        Args:
            url: Source URL (Instagram/WhatsApp temporary URL)
            media_type: Type of media (image, video, audio)
            folder: Cloudinary folder path (e.g., "clonnect/creator_123/2026-02")
            public_id: Custom public ID (auto-generated if not provided)
            tags: List of tags for organization

        Returns:
            UploadResult with permanent URL or error
        """
        if not self._configured:
            return UploadResult(
                success=False,
                original_url=url,
                error="Cloudinary not configured",
            )

        try:
            import cloudinary.uploader

            resource_type = self._get_resource_type(media_type)

            upload_options: Dict[str, Any] = {
                "resource_type": resource_type,
                "secure": True,
            }

            if folder:
                upload_options["folder"] = folder

            if public_id:
                upload_options["public_id"] = public_id

            if tags:
                upload_options["tags"] = tags

            logger.info(
                f"[CloudinaryService] Uploading {media_type} from URL "
                f"(resource_type={resource_type}, folder={folder})"
            )

            result = cloudinary.uploader.upload(url, **upload_options)

            return UploadResult(
                success=True,
                url=result.get("secure_url"),
                public_id=result.get("public_id"),
                resource_type=result.get("resource_type"),
                original_url=url,
                uploaded_at=datetime.utcnow(),
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[CloudinaryService] Upload failed: {error_msg}")
            return UploadResult(
                success=False,
                original_url=url,
                error=error_msg,
            )

    def upload_from_file(
        self,
        file_path: str,
        media_type: str = "image",
        folder: Optional[str] = None,
        public_id: Optional[str] = None,
        tags: Optional[list] = None,
    ) -> UploadResult:
        """
        Upload media from a local file to Cloudinary.

        Args:
            file_path: Path to local file
            media_type: Type of media (image, video, audio)
            folder: Cloudinary folder path
            public_id: Custom public ID
            tags: List of tags

        Returns:
            UploadResult with permanent URL or error
        """
        if not self._configured:
            return UploadResult(
                success=False,
                original_url=file_path,
                error="Cloudinary not configured",
            )

        if not os.path.exists(file_path):
            return UploadResult(
                success=False,
                original_url=file_path,
                error=f"File not found: {file_path}",
            )

        try:
            import cloudinary.uploader

            resource_type = self._get_resource_type(media_type)

            upload_options: Dict[str, Any] = {
                "resource_type": resource_type,
                "secure": True,
            }

            if folder:
                upload_options["folder"] = folder

            if public_id:
                upload_options["public_id"] = public_id

            if tags:
                upload_options["tags"] = tags

            logger.info(f"[CloudinaryService] Uploading file: {file_path}")

            result = cloudinary.uploader.upload(file_path, **upload_options)

            return UploadResult(
                success=True,
                url=result.get("secure_url"),
                public_id=result.get("public_id"),
                resource_type=result.get("resource_type"),
                original_url=file_path,
                uploaded_at=datetime.utcnow(),
            )

        except Exception as e:
            error_msg = str(e)
            logger.error(f"[CloudinaryService] File upload failed: {error_msg}")
            return UploadResult(
                success=False,
                original_url=file_path,
                error=error_msg,
            )

    def delete(self, public_id: str, resource_type: str = "image") -> bool:
        """
        Delete a resource from Cloudinary.

        Args:
            public_id: Cloudinary public ID
            resource_type: Type of resource

        Returns:
            True if deleted successfully
        """
        if not self._configured:
            return False

        try:
            import cloudinary.uploader

            result = cloudinary.uploader.destroy(public_id, resource_type=resource_type)
            return result.get("result") == "ok"

        except Exception as e:
            logger.error(f"[CloudinaryService] Delete failed: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        cloud_name = "not_set"
        if self._configured:
            try:
                import cloudinary
                cloud_name = cloudinary.config().cloud_name or "not_set"
            except Exception:
                pass
        return {
            "configured": self._configured,
            "cloud_name": cloud_name,
        }


# Singleton instance for easy import
_cloudinary_service: Optional[CloudinaryService] = None


def get_cloudinary_service() -> CloudinaryService:
    """Get or create singleton CloudinaryService instance."""
    global _cloudinary_service
    if _cloudinary_service is None:
        _cloudinary_service = CloudinaryService()
    return _cloudinary_service
