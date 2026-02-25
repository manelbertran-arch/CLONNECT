"""Stripe webhook processing logic."""
import hmac
import hashlib
import logging
from typing import Dict, Any

from core.payments.models import PaymentPlatform, PurchaseStatus

logger = logging.getLogger("clonnect-payments")


def verify_stripe_signature(webhook_secret: str, payload: bytes, signature: str) -> bool:
    """
    Verify Stripe webhook signature.

    Args:
        webhook_secret: Stripe webhook secret
        payload: Raw request body
        signature: Stripe-Signature header

    Returns:
        True if valid
    """
    if not webhook_secret:
        logger.warning("Stripe webhook secret not configured, skipping verification")
        return True

    try:
        # Parse signature header
        elements = dict(item.split("=") for item in signature.split(","))
        timestamp = elements.get("t", "")
        v1_signature = elements.get("v1", "")

        # Compute expected signature
        signed_payload = f"{timestamp}.{payload.decode()}"
        expected = hmac.new(
            webhook_secret.encode(),
            signed_payload.encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, v1_signature)
    except Exception as e:
        logger.error(f"Error verifying Stripe signature: {e}")
        return False


async def process_stripe_webhook(
    manager,
    payload: dict,
    signature: str = "",
    raw_payload: bytes = None
) -> Dict[str, Any]:
    """
    Process Stripe webhook event.

    Supported events:
    - checkout.session.completed
    - payment_intent.succeeded
    - charge.refunded
    """
    # Verify signature if secret is configured
    if manager.stripe_webhook_secret and raw_payload and signature:
        if not verify_stripe_signature(manager.stripe_webhook_secret, raw_payload, signature):
            logger.warning("Invalid Stripe webhook signature")
            return {"status": "error", "reason": "invalid_signature"}

    event_type = payload.get("type", "")
    event_data = payload.get("data", {}).get("object", {})

    logger.info(f"Processing Stripe event: {event_type}")

    if event_type == "checkout.session.completed":
        return await _handle_stripe_checkout_completed(manager, event_data)
    elif event_type == "payment_intent.succeeded":
        return await _handle_stripe_payment_succeeded(manager, event_data)
    elif event_type == "charge.refunded":
        return await _handle_stripe_refund(manager, event_data)
    else:
        logger.info(f"Ignoring Stripe event: {event_type}")
        return {"status": "ignored", "event_type": event_type}


async def _handle_stripe_checkout_completed(manager, session: dict) -> Dict[str, Any]:
    """Handle Stripe checkout.session.completed event"""
    try:
        from core.payments.subscription_manager import find_follower_by_email

        # Extract data
        customer_email = session.get("customer_details", {}).get("email", "")
        customer_name = session.get("customer_details", {}).get("name", "")
        amount = session.get("amount_total", 0) / 100  # Convert from cents
        currency = session.get("currency", "eur").upper()
        external_id = session.get("id", "")

        # Get metadata
        metadata = session.get("metadata", {})
        creator_id = metadata.get("creator_id", "manel")
        product_id = metadata.get("product_id", "")
        product_name = metadata.get("product_name", "Unknown Product")
        follower_id = metadata.get("follower_id", "")

        # If no follower_id, try to find by email
        if not follower_id and customer_email:
            follower_id = await find_follower_by_email(creator_id, customer_email)

        # Record purchase
        purchase = await manager.record_purchase(
            creator_id=creator_id,
            follower_id=follower_id,
            product_id=product_id,
            product_name=product_name,
            amount=amount,
            currency=currency,
            platform=PaymentPlatform.STRIPE.value,
            external_id=external_id,
            customer_email=customer_email,
            customer_name=customer_name,
            metadata=metadata
        )

        logger.info(f"Stripe purchase recorded: {purchase.purchase_id}")

        return {
            "status": "ok",
            "purchase_id": purchase.purchase_id,
            "amount": amount,
            "currency": currency
        }

    except Exception as e:
        logger.error(f"Error processing Stripe checkout: {e}")
        return {"status": "error", "reason": str(e)}


async def _handle_stripe_payment_succeeded(manager, payment_intent: dict) -> Dict[str, Any]:
    """Handle Stripe payment_intent.succeeded event"""
    try:
        amount = payment_intent.get("amount", 0) / 100
        currency = payment_intent.get("currency", "eur").upper()
        external_id = payment_intent.get("id", "")

        metadata = payment_intent.get("metadata", {})
        creator_id = metadata.get("creator_id", "manel")
        product_id = metadata.get("product_id", "")
        product_name = metadata.get("product_name", "Unknown Product")
        follower_id = metadata.get("follower_id", "")

        # Check if already processed (avoid duplicates)
        purchases = manager._load_purchases(creator_id)
        if any(p.external_id == external_id for p in purchases):
            logger.info(f"Payment {external_id} already processed")
            return {"status": "already_processed", "external_id": external_id}

        purchase = await manager.record_purchase(
            creator_id=creator_id,
            follower_id=follower_id,
            product_id=product_id,
            product_name=product_name,
            amount=amount,
            currency=currency,
            platform=PaymentPlatform.STRIPE.value,
            external_id=external_id,
            metadata=metadata
        )

        return {
            "status": "ok",
            "purchase_id": purchase.purchase_id,
            "amount": amount
        }

    except Exception as e:
        logger.error(f"Error processing Stripe payment: {e}")
        return {"status": "error", "reason": str(e)}


async def _handle_stripe_refund(manager, charge: dict) -> Dict[str, Any]:
    """Handle Stripe charge.refunded event"""
    try:
        external_id = charge.get("payment_intent", "")
        creator_id = charge.get("metadata", {}).get("creator_id", "manel")

        purchases = manager._load_purchases(creator_id)
        for purchase in purchases:
            if purchase.external_id == external_id:
                purchase.status = PurchaseStatus.REFUNDED.value
                break

        manager._save_purchases(creator_id, purchases)

        return {"status": "ok", "action": "refund_recorded"}

    except Exception as e:
        logger.error(f"Error processing Stripe refund: {e}")
        return {"status": "error", "reason": str(e)}
