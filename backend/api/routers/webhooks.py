"""
Webhooks Router - Payment and Calendar webhook endpoints
Extracted from main.py as part of refactoring
"""
import logging

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

# Core imports
from core.calendar import get_calendar_manager
from core.payments import get_payment_manager

router = APIRouter(prefix="/webhook", tags=["webhooks"])


# ---------------------------------------------------------
# PAYMENT WEBHOOKS
# ---------------------------------------------------------
@router.post("/stripe")
async def stripe_webhook(request: Request):
    """
    Stripe webhook endpoint.

    Processes:
    - checkout.session.completed
    - payment_intent.succeeded
    - charge.refunded

    Include metadata in Stripe checkout:
    - creator_id
    - follower_id
    - product_id
    - product_name
    """
    try:
        raw_payload = await request.body()
        payload = await request.json()
        signature = request.headers.get("Stripe-Signature", "")

        payment_manager = get_payment_manager()
        result = await payment_manager.process_stripe_webhook(
            payload=payload, signature=signature, raw_payload=raw_payload
        )

        logger.info(f"Stripe webhook processed: {result}")
        return result

    except Exception as e:
        logger.error(f"Stripe webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/hotmart")
async def hotmart_webhook(request: Request):
    """
    Hotmart webhook (postback) endpoint.

    Processes:
    - PURCHASE_COMPLETE
    - PURCHASE_APPROVED
    - PURCHASE_REFUNDED
    - PURCHASE_CANCELED
    """
    try:
        payload = await request.json()
        token = request.headers.get("X-Hotmart-Hottok", "")

        payment_manager = get_payment_manager()
        result = await payment_manager.process_hotmart_webhook(payload=payload, token=token)

        logger.info(f"Hotmart webhook processed: {result}")
        return result

    except Exception as e:
        logger.error(f"Hotmart webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/paypal")
async def paypal_webhook(request: Request):
    """
    PayPal webhook endpoint.

    Processes:
    - PAYMENT.SALE.COMPLETED
    - PAYMENT.CAPTURE.COMPLETED
    - CHECKOUT.ORDER.APPROVED
    - PAYMENT.SALE.REFUNDED

    Include custom_id in PayPal checkout with JSON:
    - creator_id
    - follower_id
    - product_id
    - product_name
    """
    try:
        raw_payload = await request.body()
        payload = await request.json()

        # Get PayPal verification headers
        headers = {
            "paypal-transmission-id": request.headers.get("paypal-transmission-id", ""),
            "paypal-transmission-time": request.headers.get("paypal-transmission-time", ""),
            "paypal-transmission-sig": request.headers.get("paypal-transmission-sig", ""),
            "paypal-cert-url": request.headers.get("paypal-cert-url", ""),
            "paypal-auth-algo": request.headers.get("paypal-auth-algo", ""),
        }

        payment_manager = get_payment_manager()
        result = await payment_manager.process_paypal_webhook(
            payload=payload, headers=headers, raw_payload=raw_payload
        )

        logger.info(f"PayPal webhook processed: {result}")
        return result

    except Exception as e:
        logger.error(f"PayPal webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ---------------------------------------------------------
# CALENDAR WEBHOOKS
# ---------------------------------------------------------
@router.post("/calendly")
async def calendly_webhook(request: Request):
    """
    Calendly webhook endpoint.

    Processes:
    - invitee.created (new booking)
    - invitee.canceled (booking cancelled)

    Use UTM parameters in Calendly link:
    - utm_source: creator_id
    - utm_campaign: follower_id
    """
    try:
        raw_payload = await request.body()
        payload = await request.json()
        signature = request.headers.get("Calendly-Webhook-Signature", "")

        calendar_manager = get_calendar_manager()
        result = await calendar_manager.process_calendly_webhook(
            payload=payload, signature=signature, raw_payload=raw_payload
        )

        logger.info(f"Calendly webhook processed: {result}")
        return result

    except Exception as e:
        logger.error(f"Calendly webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/calcom")
async def calcom_webhook(request: Request):
    """
    Cal.com webhook endpoint.

    Processes:
    - BOOKING_CREATED
    - BOOKING_CANCELLED
    - BOOKING_RESCHEDULED

    Include in booking metadata:
    - creator_id
    - follower_id
    """
    try:
        raw_payload = await request.body()
        payload = await request.json()
        signature = request.headers.get("X-Cal-Signature-256", "")

        calendar_manager = get_calendar_manager()
        result = await calendar_manager.process_calcom_webhook(
            payload=payload, signature=signature, raw_payload=raw_payload
        )

        logger.info(f"Cal.com webhook processed: {result}")
        return result

    except Exception as e:
        logger.error(f"Cal.com webhook error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
