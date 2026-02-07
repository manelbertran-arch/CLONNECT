"""Audit tests for core/link_preview.py"""

from core.link_preview import detect_platform, extract_urls, get_domain


class TestAuditLinkPreview:
    def test_import(self):
        from core.link_preview import detect_platform, extract_urls, get_domain  # noqa: F811

        assert extract_urls is not None

    def test_happy_path_extract_urls(self):
        urls = extract_urls("Visita https://example.com para mas info")
        assert isinstance(urls, list)
        assert len(urls) >= 1

    def test_happy_path_get_domain(self):
        domain = get_domain("https://www.example.com/path")
        assert isinstance(domain, str)
        assert "example" in domain

    def test_edge_case_detect_platform(self):
        platform = detect_platform("https://www.instagram.com/user")
        assert platform is not None

    def test_error_handling_no_urls(self):
        urls = extract_urls("No hay enlaces aqui")
        assert isinstance(urls, list)
        assert len(urls) == 0
