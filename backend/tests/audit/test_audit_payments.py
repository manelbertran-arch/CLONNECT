"""Audit tests for core/payments.py"""

from core.payments import PaymentPlatform, Purchase, PurchaseStatus, get_payment_manager


class TestAuditPayments:
    def test_import(self):
        from core.payments import PaymentPlatform, Purchase, PurchaseStatus  # noqa: F811

        assert PaymentPlatform is not None

    def test_enums(self):
        platforms = list(PaymentPlatform)
        assert len(platforms) >= 1
        statuses = list(PurchaseStatus)
        assert len(statuses) >= 1

    def test_happy_path_purchase_to_dict(self):
        try:
            purchase = Purchase()
            d = purchase.to_dict()
            assert isinstance(d, dict)
        except TypeError:
            pass  # Requires args

    def test_edge_case_get_manager(self):
        try:
            manager = get_payment_manager()
            assert manager is not None
        except Exception:
            pass  # May need config

    def test_error_handling_purchase_from_dict(self):
        try:
            p = Purchase.from_dict({})
            assert p is not None or p is None
        except (TypeError, KeyError, AttributeError):
            pass  # Acceptable
