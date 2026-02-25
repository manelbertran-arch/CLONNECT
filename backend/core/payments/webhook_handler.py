"""Hotmart and PayPal webhook processing logic."""
import hmac
import json
import logging
from typing import Dict, Any

from core.payments.models import PaymentPlatform, PurchaseStatus

logger = logging.getLogger("clonnect-payments")


# ==========================================================================
# HOTMART
# ==========================================================================

def verify_hotmart_token(hotmart_webhook_token: str, token: str) -> bool:
    """Verify Hotmart webhook token"""
    if not hotmart_webhook_token:
        logger.warning("Hotmart webhook token not configured, skipping verification")
        return True
    return hmac.compare_digest(token, hotmart_webhook_token)


async def process_hotmart_webhook(
    manager,
    payload: dict,
    token: str = ""
) -> Dict[str, Any]:
    """
    Process Hotmart webhook event.

    Supported events:
    - PURCHASE_COMPLETE
    - PURCHASE_APPROVED
    - PURCHASE_REFUNDED
    - PURCHASE_CANCELED
    """
    # Verify token
    if manager.hotmart_webhook_token and token:
        if not verify_hotmart_token(manager.hotmart_webhook_token, token):
            logger.warning("Invalid Hotmart webhook token")
            return {"status": "error", "reason": "invalid_token"}

    event_type = payload.get("event", "")
    data = payload.get("data", {})

    logger.info(f"Processing Hotmart event: {event_type}")

    if event_type in ["PURCHASE_COMPLETE", "PURCHASE_APPROVED"]:
        return await _handle_hotmart_purchase(manager, data)
    elif event_type in ["PURCHASE_REFUNDED", "PURCHASE_CANCELED"]:
        return await _handle_hotmart_refund(manager, data, event_type)
    else:
        logger.info(f"Ignoring Hotmart event: {event_type}")
        return {"status": "ignored", "event_type": event_type}


async def _handle_hotmart_purchase(manager, data: dict) -> Dict[str, Any]:
    """Handle Hotmart purchase event"""
    try:
        from core.payments.subscription_manager import find_follower_by_email

        # Extract buyer info
        buyer = data.get("buyer", {})
        customer_email = buyer.get("email", "")
        customer_name = buyer.get("name", "")

        # Extract product info
        product = data.get("product", {})
        product_id = str(product.get("id", ""))
        product_name = product.get("name", "Unknown Product")

        # Extract purchase info
        purchase_data = data.get("purchase", {})
        external_id = purchase_data.get("transaction", "")
        amount = float(purchase_data.get("price", {}).get("value", 0))
        currency = purchase_data.get("price", {}).get("currency_code", "BRL")

        # Get creator_id from product name or metadata
        creator_id = data.get("creator_id", "manel")

        # Try to find follower
        follower_id = await find_follower_by_email(creator_id, customer_email)

        # Check for duplicates
        purchases = manager._load_purchases(creator_id)
        if any(p.external_id == external_id for p in purchases):
            logger.info(f"Hotmart purchase {external_id} already processed")
            return {"status": "already_processed", "external_id": external_id}

        # Record purchase
        purchase = await manager.record_purchase(
            creator_id=creator_id,
            follower_id=follower_id,
            product_id=product_id,
            product_name=product_name,
            amount=amount,
            currency=currency,
            platform=PaymentPlatform.HOTMART.value,
            external_id=external_id,
            customer_email=customer_email,
            customer_name=customer_name,
            metadata=data
        )

        logger.info(f"Hotmart purchase recorded: {purchase.purchase_id}")

        return {
            "status": "ok",
            "purchase_id": purchase.purchase_id,
            "amount": amount,
            "currency": currency
        }

    except Exception as e:
        logger.error(f"Error processing Hotmart purchase: {e}")
        return {"status": "error", "reason": str(e)}


async def _handle_hotmart_refund(manager, data: dict, event_type: str) -> Dict[str, Any]:
    """Handle Hotmart refund/cancel event"""
    try:
        purchase_data = data.get("purchase", {})
        external_id = purchase_data.get("transaction", "")
        creator_id = data.get("creator_id", "manel")

        purchases = manager._load_purchases(creator_id)
        for purchase in purchases:
            if purchase.external_id == external_id:
                if event_type == "PURCHASE_REFUNDED":
                    purchase.status = PurchaseStatus.REFUNDED.value
                else:
                    purchase.status = PurchaseStatus.CANCELLED.value
                break

        manager._save_purchases(creator_id, purchases)

        return {"status": "ok", "action": f"{event_type.lower()}_recorded"}

    except Exception as e:
        logger.error(f"Error processing Hotmart {event_type}: {e}")
        return {"status": "error", "reason": str(e)}


# ==========================================================================
# PAYPAL
# ==========================================================================

async def verify_paypal_webhook(
    paypal_config: dict,
    payload: bytes,
    headers: Dict[str, str]
) -> bool:
    """
    Verify PayPal webhook signature using PayPal API.

    Args:
        paypal_config: Dict with webhook_id, client_id, client_secret, mode
        payload: Raw request body
        headers: Request headers

    Returns:
        True if valid
    """
    webhook_id = paypal_config.get("webhook_id", "")
    if not webhook_id:
        logger.warning("PayPal webhook ID not configured, skipping verification")
        return True

    try:
        import httpx
        import base64

        # Get required headers
        transmission_id = headers.get("paypal-transmission-id", "")
        transmission_time = headers.get("paypal-transmission-time", "")
        transmission_sig = headers.get("paypal-transmission-sig", "")
        cert_url = headers.get("paypal-cert-url", "")
        auth_algo = headers.get("paypal-auth-algo", "SHA256withRSA")

        if not all([transmission_id, transmission_time, transmission_sig]):
            logger.warning("Missing PayPal webhook headers")
            return False

        # Get access token
        mode = paypal_config.get("mode", "sandbox")
        base_url = "https://api-m.paypal.com" if mode == "live" else "https://api-m.sandbox.paypal.com"
        credentials = base64.b64encode(
            f"{paypal_config['client_id']}:{paypal_config['client_secret']}".encode()
        ).decode()

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Get access token
            token_response = await client.post(
                f"{base_url}/v1/oauth2/token",
                headers={
                    "Authorization": f"Basic {credentials}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={"grant_type": "client_credentials"}
            )
            token_data = token_response.json()
            access_token = token_data.get("access_token")

            if not access_token:
                logger.error("Failed to get PayPal access token for verification")
                return True  # Allow in development

            # Verify webhook signature
            verify_response = await client.post(
                f"{base_url}/v1/notifications/verify-webhook-signature",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "transmission_id": transmission_id,
                    "transmission_time": transmission_time,
                    "cert_url": cert_url,
                    "auth_algo": auth_algo,
                    "transmission_sig": transmission_sig,
                    "webhook_id": webhook_id,
                    "webhook_event": json.loads(payload.decode())
                }
            )
            verify_data = verify_response.json()

            verification_status = verify_data.get("verification_status", "")
            if verification_status == "SUCCESS":
                return True
            else:
                logger.warning(f"PayPal webhook verification failed: {verify_data}")
                return False

    except Exception as e:
        logger.error(f"Error verifying PayPal webhook: {e}")
        return True  # Allow in development to not block webhooks


async def process_paypal_webhook(
    manager,
    payload: dict,
    headers: Dict[str, str] = None,
    raw_payload: bytes = None
) -> Dict[str, Any]:
    """
    Process PayPal webhook event.

    Supported events:
    - PAYMENT.SALE.COMPLETED
    - PAYMENT.CAPTURE.COMPLETED
    - CHECKOUT.ORDER.APPROVED
    - PAYMENT.SALE.REFUNDED
    """
    # Verify signature if configured
    if manager.paypal_webhook_id and raw_payload and headers:
        paypal_config = {
            "webhook_id": manager.paypal_webhook_id,
            "client_id": manager.paypal_client_id,
            "client_secret": manager.paypal_client_secret,
            "mode": manager.paypal_mode,
        }
        if not await verify_paypal_webhook(paypal_config, raw_payload, headers):
            logger.warning("Invalid PayPal webhook signature")
            return {"status": "error", "reason": "invalid_signature"}

    event_type = payload.get("event_type", "")
    resource = payload.get("resource", {})

    logger.info(f"Processing PayPal event: {event_type}")

    if event_type in ["PAYMENT.SALE.COMPLETED", "PAYMENT.CAPTURE.COMPLETED"]:
        return await _handle_paypal_payment_completed(manager, resource, event_type)
    elif event_type == "CHECKOUT.ORDER.APPROVED":
        return await _handle_paypal_order_approved(manager, resource)
    elif event_type == "PAYMENT.SALE.REFUNDED":
        return await _handle_paypal_refund(manager, resource)
    else:
        logger.info(f"Ignoring PayPal event: {event_type}")
        return {"status": "ignored", "event_type": event_type}


async def _handle_paypal_payment_completed(
    manager,
    resource: dict,
    event_type: str
) -> Dict[str, Any]:
    """Handle PayPal payment completed event"""
    try:
        from core.payments.subscription_manager import find_follower_by_email

        # Extract payment data
        external_id = resource.get("id", "")
        amount_data = resource.get("amount", {})
        amount = float(amount_data.get("total", amount_data.get("value", 0)))
        currency = amount_data.get("currency", amount_data.get("currency_code", "USD"))

        # Get payer info
        payer_info = resource.get("payer_info", {})
        customer_email = payer_info.get("email", resource.get("payer", {}).get("email_address", ""))
        customer_name = f"{payer_info.get('first_name', '')} {payer_info.get('last_name', '')}".strip()

        # Get custom data (metadata)
        custom_data = resource.get("custom", "") or resource.get("custom_id", "")
        metadata = {}
        if custom_data:
            try:
                metadata = json.loads(custom_data) if isinstance(custom_data, str) else custom_data
            except json.JSONDecodeError:
                metadata = {"custom": custom_data}

        creator_id = metadata.get("creator_id", "manel")
        product_id = metadata.get("product_id", "")
        product_name = metadata.get("product_name", "PayPal Purchase")
        follower_id = metadata.get("follower_id", "")

        # Try to find follower by email
        if not follower_id and customer_email:
            follower_id = await find_follower_by_email(creator_id, customer_email)

        # Check for duplicates
        purchases = manager._load_purchases(creator_id)
        if any(p.external_id == external_id for p in purchases):
            logger.info(f"PayPal payment {external_id} already processed")
            return {"status": "already_processed", "external_id": external_id}

        # Record purchase
        purchase = await manager.record_purchase(
            creator_id=creator_id,
            follower_id=follower_id,
            product_id=product_id,
            product_name=product_name,
            amount=amount,
            currency=currency,
            platform=PaymentPlatform.PAYPAL.value,
            external_id=external_id,
            customer_email=customer_email,
            customer_name=customer_name,
            metadata={"paypal_event": event_type, **metadata}
        )

        logger.info(f"PayPal purchase recorded: {purchase.purchase_id}")

        return {
            "status": "ok",
            "purchase_id": purchase.purchase_id,
            "amount": amount,
            "currency": currency
        }

    except Exception as e:
        logger.error(f"Error processing PayPal payment: {e}")
        return {"status": "error", "reason": str(e)}


async def _handle_paypal_order_approved(manager, resource: dict) -> Dict[str, Any]:
    """Handle PayPal checkout order approved event"""
    try:
        from core.payments.subscription_manager import find_follower_by_email

        # Extract order data
        external_id = resource.get("id", "")

        # Get purchase units
        purchase_units = resource.get("purchase_units", [])
        if not purchase_units:
            return {"status": "ignored", "reason": "no_purchase_units"}

        unit = purchase_units[0]
        amount_data = unit.get("amount", {})
        amount = float(amount_data.get("value", 0))
        currency = amount_data.get("currency_code", "USD")

        # Get payer info
        payer = resource.get("payer", {})
        customer_email = payer.get("email_address", "")
        customer_name = f"{payer.get('name', {}).get('given_name', '')} {payer.get('name', {}).get('surname', '')}".strip()

        # Get custom data
        custom_id = unit.get("custom_id", "")
        metadata = {}
        if custom_id:
            try:
                metadata = json.loads(custom_id) if isinstance(custom_id, str) else custom_id
            except json.JSONDecodeError:
                metadata = {"custom_id": custom_id}

        creator_id = metadata.get("creator_id", "manel")
        product_id = metadata.get("product_id", unit.get("reference_id", ""))
        product_name = metadata.get("product_name", unit.get("description", "PayPal Order"))
        follower_id = metadata.get("follower_id", "")

        # Try to find follower by email
        if not follower_id and customer_email:
            follower_id = await find_follower_by_email(creator_id, customer_email)

        # Check for duplicates
        purchases = manager._load_purchases(creator_id)
        if any(p.external_id == external_id for p in purchases):
            logger.info(f"PayPal order {external_id} already processed")
            return {"status": "already_processed", "external_id": external_id}

        # Record purchase
        purchase = await manager.record_purchase(
            creator_id=creator_id,
            follower_id=follower_id,
            product_id=product_id,
            product_name=product_name,
            amount=amount,
            currency=currency,
            platform=PaymentPlatform.PAYPAL.value,
            external_id=external_id,
            customer_email=customer_email,
            customer_name=customer_name,
            metadata={"paypal_event": "CHECKOUT.ORDER.APPROVED", **metadata}
        )

        logger.info(f"PayPal order recorded: {purchase.purchase_id}")

        return {
            "status": "ok",
            "purchase_id": purchase.purchase_id,
            "amount": amount,
            "currency": currency
        }

    except Exception as e:
        logger.error(f"Error processing PayPal order: {e}")
        return {"status": "error", "reason": str(e)}


async def _handle_paypal_refund(manager, resource: dict) -> Dict[str, Any]:
    """Handle PayPal refund event"""
    try:
        # Get the sale ID that was refunded
        sale_id = resource.get("sale_id", resource.get("id", ""))
        creator_id = "manel"  # Default, would need metadata for proper routing

        # Find and update the purchase
        purchases = manager._load_purchases(creator_id)
        found = False
        for purchase in purchases:
            if purchase.external_id == sale_id:
                purchase.status = PurchaseStatus.REFUNDED.value
                found = True
                break

        if found:
            manager._save_purchases(creator_id, purchases)
            logger.info(f"PayPal refund recorded for {sale_id}")
            return {"status": "ok", "action": "refund_recorded"}

        return {"status": "ok", "action": "refund_not_found"}

    except Exception as e:
        logger.error(f"Error processing PayPal refund: {e}")
        return {"status": "error", "reason": str(e)}
