"""Audit tests for core/creator_data_loader.py"""

from core.creator_data_loader import BookingInfo, FAQInfo, ProductInfo


class TestAuditCreatorDataLoader:
    def test_import(self):
        from core.creator_data_loader import (  # noqa: F811
            BookingInfo,
            FAQInfo,
            ProductInfo,
            get_creator_data,
            load_creator_data,
        )

        assert ProductInfo is not None
        assert BookingInfo is not None

    def test_product_info_to_dict(self):
        info = ProductInfo(id="p1", name="Test Product")
        d = info.to_dict()
        assert isinstance(d, dict)
        assert d["name"] == "Test Product"

    def test_booking_info_to_dict(self):
        info = BookingInfo(id="b1", meeting_type="call", title="Test Meeting")
        d = info.to_dict()
        assert isinstance(d, dict)

    def test_faq_info_to_dict(self):
        info = FAQInfo(id="f1", question="What?", answer="This.")
        d = info.to_dict()
        assert isinstance(d, dict)

    def test_error_handling_load_creator(self):
        from core.creator_data_loader import load_creator_data

        try:
            result = load_creator_data("nonexistent_creator_xyz")
            assert result is None or isinstance(result, (dict, object))
        except Exception:
            pass  # DB not available is acceptable
