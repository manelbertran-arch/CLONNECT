# WhatsApp Business API — Setup Guide

## Current Status

**Code: READY** | **Meta Verification: PENDING**

All code is prepared and tested. Activation requires Meta Business Verification (external process, 1-7 days).

## Prerequisites

1. **Facebook Business Account** (you already have one for Instagram)
2. **Meta Developer Account** (same as Instagram)
3. **Meta Business Verification** (can take 1-7 business days)

## Architecture

```
WhatsApp Cloud API → POST /webhook/whatsapp → DMResponderAgent → WhatsApp Cloud API
                                                    ↓
                                              Lead created (wa_{phone})
                                              Message saved to DB
                                              Copilot/Autopilot mode
```

### Code Files
| File | Purpose |
|------|---------|
| `core/whatsapp.py` | WhatsAppConnector (Cloud API) + WhatsAppHandler (DM bridge) |
| `api/routers/messaging_webhooks.py` | Webhook endpoints (GET verify + POST receive) |
| `api/main.py` | Router registration |

### Endpoints
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/webhook/whatsapp` | Meta webhook verification (challenge response) |
| POST | `/webhook/whatsapp` | Receive incoming messages |
| GET | `/whatsapp/status` | Connection status |
| POST | `/admin/whatsapp/test-message` | Test pipeline without real WhatsApp |

## Setup Steps

### Step 1: Create WhatsApp Business App

1. Go to https://developers.facebook.com/apps/
2. **Option A**: Use your existing Instagram app (if type allows adding WhatsApp)
3. **Option B**: Create new app → type "Business" → add WhatsApp product
4. In the app dashboard → WhatsApp → Getting Started

### Step 2: Get Credentials

From the Meta App Dashboard → WhatsApp → API Setup:

| Credential | Where to find | Env var |
|------------|---------------|---------|
| Phone Number ID | API Setup page | `WHATSAPP_PHONE_NUMBER_ID` |
| Access Token | API Setup → Generate token | `WHATSAPP_ACCESS_TOKEN` |
| App Secret | App Settings → Basic | `WHATSAPP_APP_SECRET` |

**Note**: The temporary access token expires in 24h. For production, create a **System User Token**:
1. Meta Business Suite → Business Settings → System Users
2. Create system user → Generate token with `whatsapp_business_messaging` permission

### Step 3: Configure Webhook in Meta

1. Meta App Dashboard → WhatsApp → Configuration → Webhook
2. **Callback URL**: `https://www.clonnectapp.com/webhook/whatsapp`
3. **Verify Token**: Use the value you set in `WHATSAPP_VERIFY_TOKEN` (default: `clonnect_whatsapp_verify_2024`)
4. **Subscribe to**: `messages`
5. Click "Verify and Save" — Meta will send a GET request to verify

### Step 4: Set Environment Variables in Railway

```bash
# Required
WHATSAPP_PHONE_NUMBER_ID=<phone-number-id-from-meta>
WHATSAPP_ACCESS_TOKEN=<system-user-token-or-temporary-token>
WHATSAPP_VERIFY_TOKEN=clonnect_whatsapp_verify_2024

# Optional (for webhook signature verification)
WHATSAPP_APP_SECRET=<app-secret>

# Creator mapping (which creator handles WhatsApp DMs)
WHATSAPP_CREATOR_ID=stefano_bonanno
```

Set via Railway CLI:
```bash
cd /Users/manelbertranluque/Clonnect
railway link -p "beta creators"
railway variables --set "WHATSAPP_PHONE_NUMBER_ID=xxx"
railway variables --set "WHATSAPP_ACCESS_TOKEN=xxx"
railway variables --set "WHATSAPP_VERIFY_TOKEN=clonnect_whatsapp_verify_2024"
railway variables --set "WHATSAPP_CREATOR_ID=stefano_bonanno"
```

### Step 5: Test Without Real WhatsApp

Use the admin test endpoint to verify the pipeline works:

```bash
curl -X POST https://www.clonnectapp.com/admin/whatsapp/test-message \
  -H "Content-Type: application/json" \
  -d '{
    "creator_id": "stefano_bonanno",
    "phone": "+34612345678",
    "text": "Hola, me interesa tu programa de coaching"
  }'
```

Expected response:
```json
{
  "status": "ok",
  "test_mode": true,
  "pipeline_response": {
    "response_text": "Hola! ...",
    "intent": "interest_strong",
    "confidence": 0.92
  },
  "note": "Response NOT sent to WhatsApp - test mode only"
}
```

### Step 6: Test With Real WhatsApp (Post-Verification)

1. Send a message to your WhatsApp Business number from a personal phone
2. Check Railway logs: `railway logs -f` — look for `WHATSAPP WEBHOOK HIT`
3. Verify response is sent back to the phone
4. Verify lead created in dashboard: `/new/clientes` with platform=whatsapp

### Step 7: Go to Production

1. **Request Meta Business Verification**: Meta Business Suite → Settings → Business Verification
2. Submit required documents (business registration, etc.)
3. Wait for approval (1-7 business days)
4. Once approved:
   - Test phone number becomes production
   - No more 24h messaging window for test numbers
   - Can send template messages to initiate conversations

## Meta Business Verification Checklist

| Step | Status | Notes |
|------|--------|-------|
| Facebook Business Account | Done | Same as Instagram |
| Meta Developer Account | Done | Same as Instagram |
| Create WhatsApp Business App | Pending | |
| Get Phone Number ID | Pending | From API Setup |
| Generate System User Token | Pending | For permanent access |
| Configure Webhook | Pending | URL + verify token |
| Set Railway env vars | Pending | 4 variables |
| Submit Business Verification | Pending | 1-7 days review |
| Test with real message | Pending | After verification |

## Troubleshooting

### Webhook verification fails
- Check `WHATSAPP_VERIFY_TOKEN` matches what you entered in Meta Dashboard
- Check Railway logs for the GET request
- Ensure the URL is exactly `https://www.clonnectapp.com/webhook/whatsapp`

### Messages received but no response
- Check `WHATSAPP_ACCESS_TOKEN` is valid (not expired)
- Check `WHATSAPP_PHONE_NUMBER_ID` is correct
- Check Railway logs for errors in DM pipeline
- Try the test endpoint first: `POST /admin/whatsapp/test-message`

### "Phone number not registered" error
- The phone number must be registered in Meta Business Suite
- For testing, use the test phone number provided by Meta

## Template Messages (Future)

For re-engaging leads outside the 24h messaging window, you'll need approved templates:

1. Meta Business Suite → WhatsApp Manager → Message Templates
2. Create template (e.g., "followup_interest")
3. Submit for approval (usually 24h)
4. Use via `WhatsAppConnector.send_template()` in nurturing sequences
