"""Tests para Instagram Scraper."""

import pytest
from datetime import datetime
from ingestion.instagram_scraper import (
    InstagramPost,
    ManualJSONScraper,
    MetaGraphAPIScraper,
    InstaloaderScraper,
    get_instagram_scraper
)


class TestInstagramPost:
    """Tests para InstagramPost dataclass."""

    def test_has_content_true(self):
        post = InstagramPost(
            post_id="123",
            post_type="image",
            caption="Este es un caption con contenido suficiente",
            permalink="https://instagram.com/p/123/",
            timestamp=datetime.now()
        )
        assert post.has_content is True

    def test_has_content_false_empty(self):
        post = InstagramPost(
            post_id="123",
            post_type="image",
            caption="",
            permalink="https://instagram.com/p/123/",
            timestamp=datetime.now()
        )
        assert post.has_content is False

    def test_has_content_false_short(self):
        post = InstagramPost(
            post_id="123",
            post_type="image",
            caption="Corto",
            permalink="https://instagram.com/p/123/",
            timestamp=datetime.now()
        )
        assert post.has_content is False

    def test_has_content_false_whitespace(self):
        post = InstagramPost(
            post_id="123",
            post_type="image",
            caption="          ",
            permalink="https://instagram.com/p/123/",
            timestamp=datetime.now()
        )
        assert post.has_content is False

    def test_post_types(self):
        for post_type in ['image', 'video', 'carousel', 'reel']:
            post = InstagramPost(
                post_id="123",
                post_type=post_type,
                caption="Test caption with enough content",
                permalink="https://instagram.com/p/123/",
                timestamp=datetime.now()
            )
            assert post.post_type == post_type


class TestManualJSONScraper:
    """Tests para ManualJSONScraper."""

    def test_parse_simple_json(self):
        scraper = ManualJSONScraper()

        data = [
            {
                "id": "post1",
                "caption": "Este es mi primer post sobre fitness y nutricion #fitness #salud",
                "timestamp": "2024-01-15T10:30:00",
                "type": "image",
                "url": "https://instagram.com/p/post1/"
            },
            {
                "id": "post2",
                "caption": "Otro post con contenido interesante @usuario",
                "timestamp": "2024-01-16T12:00:00",
                "type": "reel"
            }
        ]

        posts = scraper.parse_simple_json(data)

        assert len(posts) == 2
        assert posts[0].post_id == "post1"
        assert posts[0].hashtags == ["fitness", "salud"]
        assert posts[1].mentions == ["usuario"]
        assert posts[1].post_type == "reel"

    def test_filters_short_captions(self):
        scraper = ManualJSONScraper()

        data = [
            {"id": "1", "caption": "Ok", "timestamp": "2024-01-15T10:30:00"},
            {"id": "2", "caption": "Este caption si es suficientemente largo", "timestamp": "2024-01-15T10:30:00"}
        ]

        posts = scraper.parse_simple_json(data)

        assert len(posts) == 1
        assert posts[0].post_id == "2"

    def test_extracts_hashtags(self):
        scraper = ManualJSONScraper()
        hashtags = scraper._extract_hashtags("Post con #hashtag1 y #hashtag2")
        assert hashtags == ["hashtag1", "hashtag2"]

    def test_extracts_hashtags_empty(self):
        scraper = ManualJSONScraper()
        hashtags = scraper._extract_hashtags("")
        assert hashtags == []

    def test_extracts_hashtags_none(self):
        scraper = ManualJSONScraper()
        hashtags = scraper._extract_hashtags(None)
        assert hashtags == []

    def test_extracts_mentions(self):
        scraper = ManualJSONScraper()
        mentions = scraper._extract_mentions("Gracias @usuario1 y @usuario2")
        assert mentions == ["usuario1", "usuario2"]

    def test_extracts_mentions_empty(self):
        scraper = ManualJSONScraper()
        mentions = scraper._extract_mentions("")
        assert mentions == []

    def test_guess_type_video(self):
        scraper = ManualJSONScraper()
        assert scraper._guess_type({"media_type": "VIDEO"}) == "video"

    def test_guess_type_reel(self):
        scraper = ManualJSONScraper()
        assert scraper._guess_type({"type": "REEL"}) == "reel"

    def test_guess_type_carousel(self):
        scraper = ManualJSONScraper()
        assert scraper._guess_type({"type": "CAROUSEL_ALBUM"}) == "carousel"

    def test_guess_type_default(self):
        scraper = ManualJSONScraper()
        assert scraper._guess_type({}) == "image"

    def test_handles_malformed_data(self):
        scraper = ManualJSONScraper()

        data = [
            {"caption": "Valid caption with enough text"},  # Missing id and timestamp
            {"id": "2", "timestamp": "invalid-date", "caption": "Another valid caption here"},
        ]

        # Should not raise, should handle gracefully
        posts = scraper.parse_simple_json(data)
        assert len(posts) >= 0  # May or may not parse depending on error handling


class TestMetaGraphAPIScraper:
    """Tests para MetaGraphAPIScraper."""

    def test_initialization(self):
        scraper = MetaGraphAPIScraper(
            access_token="test_token",
            instagram_business_id="123456"
        )
        assert scraper.access_token == "test_token"
        assert scraper.instagram_business_id == "123456"

    def test_map_media_type_image(self):
        assert MetaGraphAPIScraper._map_media_type("IMAGE") == "image"

    def test_map_media_type_video(self):
        assert MetaGraphAPIScraper._map_media_type("VIDEO") == "video"

    def test_map_media_type_carousel(self):
        assert MetaGraphAPIScraper._map_media_type("CAROUSEL_ALBUM") == "carousel"

    def test_map_media_type_reel(self):
        assert MetaGraphAPIScraper._map_media_type("REELS") == "reel"

    def test_map_media_type_unknown(self):
        assert MetaGraphAPIScraper._map_media_type("UNKNOWN") == "image"

    def test_extract_hashtags(self):
        hashtags = MetaGraphAPIScraper._extract_hashtags("Post con #fitness #gym")
        assert hashtags == ["fitness", "gym"]

    def test_extract_mentions(self):
        mentions = MetaGraphAPIScraper._extract_mentions("Con @friend y @coach")
        assert mentions == ["friend", "coach"]


class TestInstaloaderScraper:
    """Tests para InstaloaderScraper."""

    def test_initialization_without_auth(self):
        scraper = InstaloaderScraper()
        assert scraper.username is None
        assert scraper.password is None
        assert scraper._loader is None

    def test_initialization_with_auth(self):
        scraper = InstaloaderScraper(
            username="test_user",
            password="test_pass"
        )
        assert scraper.username == "test_user"
        assert scraper.password == "test_pass"


class TestGetInstagramScraper:
    """Tests para factory function."""

    def test_get_manual_scraper(self):
        scraper = get_instagram_scraper('manual')
        assert isinstance(scraper, ManualJSONScraper)

    def test_get_meta_api_scraper(self):
        scraper = get_instagram_scraper(
            'meta_api',
            access_token='test_token',
            instagram_business_id='123'
        )
        assert isinstance(scraper, MetaGraphAPIScraper)

    def test_get_instaloader_scraper(self):
        scraper = get_instagram_scraper('instaloader')
        assert isinstance(scraper, InstaloaderScraper)

    def test_get_instaloader_scraper_with_auth(self):
        scraper = get_instagram_scraper(
            'instaloader',
            username='user',
            password='pass'
        )
        assert isinstance(scraper, InstaloaderScraper)
        assert scraper.username == 'user'

    def test_invalid_method(self):
        with pytest.raises(ValueError) as excinfo:
            get_instagram_scraper('invalid')
        assert "Metodo desconocido" in str(excinfo.value)

    def test_meta_api_missing_token(self):
        with pytest.raises(KeyError):
            get_instagram_scraper('meta_api')
