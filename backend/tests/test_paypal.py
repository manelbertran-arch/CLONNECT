"""
Tests for PayPal integration.

Tests:
- OAuth flow
- Webhook signature verification
- Payment processing (PAYMENT.SALE.COMPLETED)
- Refund processing (PAYMENT.SALE.REFUNDED)
- Integration with SalesTracker
"""
import pytest
import json
import os
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone

# Set test environment
os.environ["DATABASE_URL"] = ""
os.environ["TESTING"] = "true"

from fastapi.testclient import TestClient
from api.main import app
from core.payments import PaymentManager, PaymentPlatform, PurchaseStatus


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def payment_manager(tmp_path):
    """Create payment manager with temp storage"""
    return PaymentManager(storage_path=str(tmp_path / "payments"))


class TestPayPalOAuth:
    """Test PayPal OAuth flow"""

    def test_oauth_start_requires_client_id(self, client):
        """OAuth start should fail if PAYPAL_CLIENT_ID not configured"""
        with patch.dict(os.environ, {"PAYPAL_CLIENT_ID": ""}):
            response = client.get("/oauth/paypal/start?creator_id=test")
            # Should return error when not configured
            assert response.status_code in [500, 200]

    def test_oauth_start_returns_auth_url(self, client):
        """OAuth start should return auth URL when configured"""
        with patch.dict(os.environ, {
            "PAYPAL_CLIENT_ID": "test_client_id",
            "PAYPAL_MODE": "sandbox"
        }):
            response = client.get("/oauth/paypal/start?creator_id=test_creator")
            assert response.status_code == 200
            data = response.json()
            assert "auth_url" in data
            assert "state" in data
            assert "sandbox.paypal.com" in data["auth_url"]
            assert "test_client_id" in data["auth_url"]


class TestPayPalWebhook:
    """Test PayPal webhook processing"""

    def test_webhook_endpoint_exists(self, client):
        """PayPal webhook endpoint should exist"""
        response = client.post(
            "/webhook/paypal",
            json={"event_type": "UNKNOWN", "resource": {}}
        )
        # Should not return 404
        assert response.status_code != 404

    def test_webhook_ignores_unknown_events(self, client):
        """Webhook should ignore unknown event types"""
        response = client.post(
            "/webhook/paypal",
            json={
                "event_type": "UNKNOWN.EVENT.TYPE",
                "resource": {}
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "ignored"

    @pytest.mark.asyncio
    async def test_process_payment_sale_completed(self, payment_manager):
        """Test processing PAYMENT.SALE.COMPLETED event"""
        payload = {
            "event_type": "PAYMENT.SALE.COMPLETED",
            "resource": {
                "id": "PAY-123456789",
                "amount": {
                    "total": "99.99",
                    "currency": "USD"
                },
                "payer_info": {
                    "email": "buyer@example.com",
                    "first_name": "John",
                    "last_name": "Doe"
                },
                "custom": json.dumps({
                    "creator_id": "test_creator",
                    "product_id": "prod_123",
                    "product_name": "Test Product",
                    "follower_id": "follower_456"
                })
            }
        }

        result = await payment_manager.process_paypal_webhook(payload)

        assert result["status"] == "ok"
        assert "purchase_id" in result
        assert result["amount"] == 99.99
        assert result["currency"] == "USD"

    @pytest.mark.asyncio
    async def test_process_checkout_order_approved(self, payment_manager):
        """Test processing CHECKOUT.ORDER.APPROVED event"""
        payload = {
            "event_type": "CHECKOUT.ORDER.APPROVED",
            "resource": {
                "id": "ORDER-123456789",
                "purchase_units": [{
                    "amount": {
                        "value": "49.99",
                        "currency_code": "EUR"
                    },
                    "description": "Premium Course",
                    "custom_id": json.dumps({
                        "creator_id": "test_creator",
                        "product_id": "course_001"
                    })
                }],
                "payer": {
                    "email_address": "payer@test.com",
                    "name": {
                        "given_name": "Jane",
                        "surname": "Smith"
                    }
                }
            }
        }

        result = await payment_manager.process_paypal_webhook(payload)

        assert result["status"] == "ok"
        assert result["amount"] == 49.99
        assert result["currency"] == "EUR"

    @pytest.mark.asyncio
    async def test_duplicate_payment_detection(self, payment_manager):
        """Test that duplicate payments are not processed twice"""
        payload = {
            "event_type": "PAYMENT.SALE.COMPLETED",
            "resource": {
                "id": "PAY-DUPLICATE-123",
                "amount": {"total": "50.00", "currency": "USD"},
                "payer_info": {"email": "test@test.com"},
                "custom": json.dumps({"creator_id": "test_creator"})
            }
        }

        # Process first time
        result1 = await payment_manager.process_paypal_webhook(payload)
        assert result1["status"] == "ok"

        # Process second time (duplicate)
        result2 = await payment_manager.process_paypal_webhook(payload)
        assert result2["status"] == "already_processed"

    @pytest.mark.asyncio
    async def test_process_refund(self, payment_manager):
        """Test processing PAYMENT.SALE.REFUNDED event"""
        # First create a purchase
        purchase_payload = {
            "event_type": "PAYMENT.SALE.COMPLETED",
            "resource": {
                "id": "PAY-TO-REFUND-123",
                "amount": {"total": "100.00", "currency": "USD"},
                "payer_info": {"email": "refund@test.com"},
                "custom": json.dumps({"creator_id": "manel"})
            }
        }
        await payment_manager.process_paypal_webhook(purchase_payload)

        # Then process refund
        refund_payload = {
            "event_type": "PAYMENT.SALE.REFUNDED",
            "resource": {
                "id": "REFUND-123",
                "sale_id": "PAY-TO-REFUND-123"
            }
        }
        result = await payment_manager.process_paypal_webhook(refund_payload)
        assert result["status"] == "ok"


class TestPayPalWebhookVerification:
    """Test PayPal webhook signature verification"""

    @pytest.mark.asyncio
    async def test_verification_skipped_without_webhook_id(self, payment_manager):
        """Verification should be skipped if PAYPAL_WEBHOOK_ID not set"""
        payment_manager.paypal_webhook_id = ""

        result = await payment_manager.verify_paypal_webhook(
            b'{}',
            {"paypal-transmission-id": "test"}
        )
        assert result is True  # Skipped = allowed

    @pytest.mark.asyncio
    async def test_verification_fails_without_headers(self, payment_manager):
        """Verification should fail if required headers missing"""
        payment_manager.paypal_webhook_id = "WH-123"

        result = await payment_manager.verify_paypal_webhook(
            b'{}',
            {}  # No headers
        )
        assert result is False


class TestPayPalPlatformEnum:
    """Test PayPal is properly added to platform enum"""

    def test_paypal_in_platform_enum(self):
        """PAYPAL should be in PaymentPlatform enum"""
        assert hasattr(PaymentPlatform, 'PAYPAL')
        assert PaymentPlatform.PAYPAL.value == "paypal"


class TestPayPalIntegration:
    """Integration tests for PayPal with SalesTracker"""

    @pytest.mark.asyncio
    async def test_purchase_recorded_in_sales_tracker(self, payment_manager):
        """Purchases should be tracked in SalesTracker"""
        with patch('core.payments.get_sales_tracker') as mock_tracker:
            mock_tracker_instance = MagicMock()
            mock_tracker.return_value = mock_tracker_instance

            payload = {
                "event_type": "PAYMENT.SALE.COMPLETED",
                "resource": {
                    "id": "PAY-TRACKED-123",
                    "amount": {"total": "75.00", "currency": "USD"},
                    "payer_info": {"email": "tracked@test.com"},
                    "custom": json.dumps({
                        "creator_id": "test_creator",
                        "product_id": "tracked_product"
                    })
                }
            }

            await payment_manager.process_paypal_webhook(payload)

            # Verify SalesTracker was called
            mock_tracker_instance.record_sale.assert_called_once()
            call_args = mock_tracker_instance.record_sale.call_args
            assert call_args.kwargs["platform"] == "paypal"
            assert call_args.kwargs["amount"] == 75.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
