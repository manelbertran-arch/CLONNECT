# backend/tests/contracts/test_paypal_contract.py
"""
Contract tests para PayPal API.
Verifican que los payloads de webhooks y orders cumplen el contrato esperado.
"""
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum


# === CONTRATOS ===

class PayPalWebhookEventType(str, Enum):
    PAYMENT_COMPLETED = "PAYMENT.CAPTURE.COMPLETED"
    PAYMENT_DENIED = "PAYMENT.CAPTURE.DENIED"
    CHECKOUT_APPROVED = "CHECKOUT.ORDER.APPROVED"
    CHECKOUT_COMPLETED = "CHECKOUT.ORDER.COMPLETED"


class PayPalAmount(BaseModel):
    currency_code: str
    value: str  # PayPal usa string para amounts


class PayPalWebhookResource(BaseModel):
    id: str
    status: str
    amount: Optional[PayPalAmount] = None
    custom_id: Optional[str] = None


class PayPalWebhookPayload(BaseModel):
    id: str
    event_type: str
    resource: PayPalWebhookResource


class PayPalPurchaseUnit(BaseModel):
    amount: dict
    description: Optional[str] = None
    custom_id: Optional[str] = None


class PayPalOrderRequest(BaseModel):
    intent: str  # "CAPTURE"
    purchase_units: List[PayPalPurchaseUnit]


class PayPalLink(BaseModel):
    rel: str
    href: str
    method: Optional[str] = None


class PayPalOrderResponse(BaseModel):
    id: str
    status: str
    links: List[PayPalLink]


# === TESTS ===

class TestPayPalWebhookContract:
    """Tests de contrato para webhooks de PayPal"""

    def test_payment_completed_webhook(self):
        """Webhook de pago completado"""
        payload = {
            "id": "WH-123456",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {
                "id": "CAP-123456",
                "status": "COMPLETED",
                "amount": {
                    "currency_code": "EUR",
                    "value": "99.00"
                }
            }
        }
        validated = PayPalWebhookPayload(**payload)
        assert validated.event_type == PayPalWebhookEventType.PAYMENT_COMPLETED
        assert validated.resource.status == "COMPLETED"

    def test_checkout_approved_webhook(self):
        """Webhook de checkout aprobado"""
        payload = {
            "id": "WH-789",
            "event_type": "CHECKOUT.ORDER.APPROVED",
            "resource": {
                "id": "ORDER-123",
                "status": "APPROVED"
            }
        }
        validated = PayPalWebhookPayload(**payload)
        assert validated.resource.status == "APPROVED"

    def test_payment_denied_webhook(self):
        """Webhook de pago denegado"""
        payload = {
            "id": "WH-DENIED",
            "event_type": "PAYMENT.CAPTURE.DENIED",
            "resource": {
                "id": "CAP-DENIED",
                "status": "DENIED"
            }
        }
        validated = PayPalWebhookPayload(**payload)
        assert validated.event_type == PayPalWebhookEventType.PAYMENT_DENIED

    def test_webhook_with_custom_id(self):
        """Webhook con custom_id para tracking"""
        payload = {
            "id": "WH-CUSTOM",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {
                "id": "CAP-123",
                "status": "COMPLETED",
                "custom_id": "order_clonnect_789",
                "amount": {
                    "currency_code": "EUR",
                    "value": "199.00"
                }
            }
        }
        validated = PayPalWebhookPayload(**payload)
        assert validated.resource.custom_id == "order_clonnect_789"

    def test_amount_as_string(self):
        """PayPal siempre envía amounts como string"""
        payload = {
            "id": "WH-123",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {
                "id": "CAP-123",
                "status": "COMPLETED",
                "amount": {
                    "currency_code": "EUR",
                    "value": "99.99"  # String, no float
                }
            }
        }
        validated = PayPalWebhookPayload(**payload)
        assert isinstance(validated.resource.amount.value, str)
        assert validated.resource.amount.value == "99.99"


class TestPayPalOrderContract:
    """Tests de contrato para órdenes de PayPal"""

    def test_valid_order_request(self):
        """Request de orden válido"""
        request = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "amount": {
                    "currency_code": "EUR",
                    "value": "99.00"
                },
                "description": "Curso de Fitness"
            }]
        }
        validated = PayPalOrderRequest(**request)
        assert validated.intent == "CAPTURE"
        assert len(validated.purchase_units) == 1

    def test_order_with_custom_id(self):
        """Orden con custom_id para tracking"""
        request = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "amount": {
                    "currency_code": "EUR",
                    "value": "99.00"
                },
                "custom_id": "lead_123_product_456"
            }]
        }
        validated = PayPalOrderRequest(**request)
        assert validated.purchase_units[0].custom_id == "lead_123_product_456"

    def test_order_response_with_links(self):
        """Respuesta de orden con links"""
        response = {
            "id": "ORDER-123456",
            "status": "CREATED",
            "links": [
                {"rel": "approve", "href": "https://paypal.com/approve", "method": "GET"},
                {"rel": "capture", "href": "https://api.paypal.com/capture", "method": "POST"}
            ]
        }
        validated = PayPalOrderResponse(**response)
        assert len(validated.links) == 2
        assert validated.links[0].rel == "approve"

    def test_order_multiple_purchase_units(self):
        """Orden con múltiples purchase units"""
        request = {
            "intent": "CAPTURE",
            "purchase_units": [
                {"amount": {"currency_code": "EUR", "value": "99.00"}},
                {"amount": {"currency_code": "EUR", "value": "49.00"}}
            ]
        }
        validated = PayPalOrderRequest(**request)
        assert len(validated.purchase_units) == 2


class TestPayPalCurrencyContract:
    """Tests de contrato para manejo de monedas"""

    def test_eur_currency(self):
        """Moneda EUR"""
        amount = PayPalAmount(currency_code="EUR", value="99.00")
        assert amount.currency_code == "EUR"

    def test_usd_currency(self):
        """Moneda USD"""
        amount = PayPalAmount(currency_code="USD", value="109.00")
        assert amount.currency_code == "USD"

    def test_decimal_precision(self):
        """Precisión decimal en amounts"""
        amount = PayPalAmount(currency_code="EUR", value="99.99")
        assert "." in amount.value
        # Verificar que tiene 2 decimales
        decimals = amount.value.split(".")[1]
        assert len(decimals) == 2
