# WhatsApp Business API Setup

## Prerequisites
- Meta Business Account
- Facebook Page linked to WhatsApp Business
- Meta Developer Account

## Steps

### 1. Create Meta App
1. Go to [developers.facebook.com](https://developers.facebook.com)
2. Create new app → Business type
3. Add WhatsApp product

### 2. Configure WhatsApp Business
1. In Meta Business Suite, set up WhatsApp Business Account
2. Add phone number for testing
3. Verify phone number via SMS/voice

### 3. Get Credentials
From Meta App Dashboard:
- `WHATSAPP_PHONE_NUMBER_ID`: Your WhatsApp phone number ID
- `WHATSAPP_ACCESS_TOKEN`: Permanent access token (or system user token)
- `WHATSAPP_APP_SECRET`: App secret for webhook signature verification

### 4. Configure Webhook
1. In Meta App → WhatsApp → Configuration
2. Webhook URL: `https://web-production-9f69.up.railway.app/webhook/whatsapp`
3. Verify Token: `clonnect_whatsapp_verify_2024`
4. Subscribe to: `messages`, `messaging_postbacks`

### 5. Set Environment Variables in Railway
```bash
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_ACCESS_TOKEN=your_access_token
WHATSAPP_APP_SECRET=your_app_secret
WHATSAPP_VERIFY_TOKEN=clonnect_whatsapp_verify_2024
```

### 6. Template Messages (Optional)
For initiating conversations (outside 24h window):
1. Create message templates in Meta Business Suite
2. Submit for approval
3. Use via API: `POST /webhook/whatsapp/send-template`

## Endpoints Available
- `GET /webhook/whatsapp` - Webhook verification
- `POST /webhook/whatsapp` - Receive messages
- `GET /whatsapp/status` - Check connection status

## Code Files
- `core/whatsapp.py` - WhatsApp connector and handler
- `api/main.py` - Webhook endpoints

## Testing
1. Send message to your WhatsApp Business number
2. Check Railway logs for incoming webhook
3. Verify response is sent back
