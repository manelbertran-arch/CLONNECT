# Stripe Payment Integration Setup

## Prerequisites
- Stripe account (free to create)
- Products/Prices configured in Stripe Dashboard

## Steps

### 1. Get API Keys
From [Stripe Dashboard](https://dashboard.stripe.com/apikeys):
- `STRIPE_SECRET_KEY`: Secret key (starts with `sk_test_` or `sk_live_`)
- `STRIPE_WEBHOOK_SECRET`: Created in step 3

### 2. Set Environment Variables
```bash
STRIPE_SECRET_KEY=sk_test_your_secret_key
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret
```

### 3. Configure Webhook
1. Go to Stripe Dashboard → Developers → Webhooks
2. Add endpoint: `https://www.clonnectapp.com/webhook/stripe`
3. Select events:
   - `checkout.session.completed`
   - `payment_intent.succeeded`
   - `charge.refunded`
4. Copy signing secret → `STRIPE_WEBHOOK_SECRET`

### 4. Create Checkout Links
Include metadata in your Stripe checkout session:
```json
{
  "metadata": {
    "creator_id": "your_creator_id",
    "follower_id": "tg_123456789",
    "product_id": "product_uuid",
    "product_name": "Product Name"
  }
}
```

## Endpoints Available
- `POST /webhook/stripe` - Receive Stripe events
- `GET /payments/{creator_id}/revenue` - Revenue stats
- `GET /payments/{creator_id}/purchases` - Purchase history
- `POST /payments/{creator_id}/purchases` - Manual purchase record

## Hotmart Integration
Also supported via `POST /webhook/hotmart`:
- Set `HOTMART_WEBHOOK_TOKEN` for signature verification
- Events: `PURCHASE_COMPLETE`, `PURCHASE_APPROVED`, `PURCHASE_REFUNDED`

## Code Files
- `core/payments.py` - Payment processing
- `core/sales_tracker.py` - Sales analytics
- `api/routers/payments.py` - Payment endpoints
- `api/main.py` - Webhook handlers

## Testing
1. Use Stripe test mode (`sk_test_*` key)
2. Use Stripe CLI for local testing:
   ```bash
   stripe listen --forward-to localhost:8000/webhook/stripe
   ```
3. Create test payment → check webhook received
