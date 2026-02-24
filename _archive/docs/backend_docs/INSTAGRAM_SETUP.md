# Instagram Setup - Complete Guide

This guide explains how to set up Instagram integration for Clonnect, including webhook configuration, OAuth flow, and multi-creator support.

## Prerequisites

- Facebook Developer account
- Instagram Business or Creator account
- Instagram account must be connected to a Facebook Page
- Facebook Page must have messaging enabled

## 1. Create Meta App

1. Go to [Meta Developers](https://developers.facebook.com)
2. Click "My Apps" → "Create App"
3. Select "Business" type
4. Enter app name (e.g., "Clonnect DM Bot")
5. Select your Business Portfolio (or create one)

## 2. Add Products to Your App

In the App Dashboard, add these products:

### Instagram API
1. Click "Add Product" → "Instagram" → "Set Up"
2. This enables Instagram Graph API access

### Webhooks
1. Click "Add Product" → "Webhooks" → "Set Up"
2. Configure webhook subscriptions (see step 5)

### Facebook Login (for OAuth)
1. Click "Add Product" → "Facebook Login" → "Set Up"
2. Enable "Web" platform
3. Add Valid OAuth Redirect URIs:
   ```
   https://www.clonnectapp.com/oauth/instagram/callback
   ```

## 3. Configure App Settings

### Basic Settings
Go to "Settings" → "Basic":
- Note your **App ID** (META_APP_ID)
- Note your **App Secret** (META_APP_SECRET)
- Add Privacy Policy URL (required for production)
- Add App Domains: `www.clonnectapp.com`

### Advanced Settings
Go to "Settings" → "Advanced":
- Enable "Allow API Access to App Settings"
- Set "App Type" to "Business"

## 4. Request Permissions (App Review)

For production use, you must submit for App Review with these permissions:

| Permission | Purpose |
|------------|---------|
| `instagram_basic` | Basic Instagram account info |
| `instagram_manage_messages` | Send and receive DMs |
| `pages_messaging` | Page messaging capability |
| `pages_show_list` | List connected pages |
| `pages_read_engagement` | Read engagement data |
| `pages_manage_metadata` | Manage page metadata (for Ice Breakers) |

### Testing Before App Review
While in development mode, you can test with:
- App admins and testers (add in "Roles")
- Test users created in the App Dashboard

## 5. Configure Webhooks

### Webhook URL
```
https://www.clonnectapp.com/webhook/instagram
```

### Verify Token
```
clonnect_verify_2024
```

### Required Webhook Fields

Subscribe to these webhook fields:

#### Instagram Webhooks
| Field | Purpose |
|-------|---------|
| `messages` | Receive incoming DMs |
| `messaging_postbacks` | Ice Breaker button clicks |
| `messaging_optins` | User opt-in events |
| `message_echoes` | Confirm message delivery |
| `messaging_referrals` | Deep link referrals |
| `story_mentions` | When users mention you in stories |
| `comments` | Post comments (for auto-DM on comments) |

### Setting Up Webhooks in Dashboard
1. Go to "Webhooks" in your app
2. Click "Add Subscription" for Instagram
3. Enter Callback URL: `https://www.clonnectapp.com/webhook/instagram`
4. Enter Verify Token: `clonnect_verify_2024`
5. Click "Verify and Save"
6. Select the webhook fields listed above

## 6. Environment Variables

Add these to your backend environment:

```bash
# Meta App credentials
META_APP_ID=your_app_id
META_APP_SECRET=your_app_secret

# OAuth redirect
META_REDIRECT_URI=https://www.clonnectapp.com/oauth/instagram/callback

# Webhook verification
INSTAGRAM_VERIFY_TOKEN=clonnect_verify_2024

# Optional: App Secret for webhook signature verification
INSTAGRAM_APP_SECRET=your_app_secret

# Feature flags
AUTO_DM_ON_COMMENTS=true
STORY_MENTION_RESPONSE="Thanks for sharing! How can I help you?"
```

## 7. OAuth Flow for Creators

### How Creators Connect Instagram

1. Creator clicks "Connect Instagram" in Clonnect dashboard
2. Redirects to: `GET /oauth/instagram/start?creator_id={creator_name}`
3. Facebook OAuth dialog opens
4. User authorizes the app
5. Redirects to callback: `/oauth/instagram/callback`
6. Backend exchanges code for tokens
7. Stores tokens and page_id in database
8. Auto-onboarding begins (scraping, tone analysis, RAG indexing)

### API Endpoints

```
# Start OAuth flow
GET /oauth/instagram/start?creator_id=manel

# OAuth callback (handled automatically)
GET /oauth/instagram/callback?code=xxx&state=xxx

# Check connection status
GET /instagram/status/{creator_id}

# Manual page connection (for debugging)
POST /instagram/connect?creator_id=manel&page_id=123456789
```

## 8. Multi-Creator Routing

Clonnect supports multiple creators, each with their own Instagram account.

### How It Works

1. Webhook receives event with `page_id` in payload
2. Backend looks up creator by `instagram_page_id` in database
3. Routes message to creator-specific handler
4. Response is sent using creator's tokens

### Database Fields (Creator table)

| Field | Description |
|-------|-------------|
| `instagram_token` | Page Access Token (long-lived, 60 days) |
| `instagram_page_id` | Facebook Page ID linked to Instagram |
| `instagram_user_id` | Instagram Business Account ID |
| `bot_active` | Whether bot should respond |
| `copilot_mode` | If true, suggestions need approval |

### API Endpoints

```
# List all creators with Instagram
GET /instagram/creators

# Get specific creator status
GET /instagram/status/{creator_id}

# Manual page connection
POST /instagram/connect?creator_id=xxx&page_id=xxx
```

## 9. Ice Breakers Configuration

Ice Breakers are conversation starters shown to users when they open a new chat.

### Set Ice Breakers

```bash
POST /instagram/icebreakers/{creator_id}
Content-Type: application/json

[
    {"question": "What services do you offer?", "payload": "SERVICES"},
    {"question": "How much does it cost?", "payload": "PRICING"},
    {"question": "How can I book?", "payload": "BOOKING"},
    {"question": "Tell me more", "payload": "INFO"}
]
```

### Get Current Ice Breakers

```bash
GET /instagram/icebreakers/{creator_id}
```

### Delete Ice Breakers

```bash
DELETE /instagram/icebreakers/{creator_id}
```

### Handling Ice Breaker Clicks

When a user clicks an Ice Breaker, the webhook receives:
```json
{
  "messaging": [{
    "sender": {"id": "user_id"},
    "postback": {
      "payload": "SERVICES",
      "title": "What services do you offer?"
    }
  }]
}
```

The DM agent processes this like a regular message.

## 10. Persistent Menu

The persistent menu appears as a hamburger icon in the chat.

### Set Persistent Menu

```bash
POST /instagram/persistent-menu/{creator_id}
Content-Type: application/json

[
    {"type": "postback", "title": "Services", "payload": "SERVICES"},
    {"type": "postback", "title": "Book a Call", "payload": "BOOKING"},
    {"type": "web_url", "title": "Visit Website", "url": "https://example.com"}
]
```

## 11. Story Replies & Mentions

### Story Reply Handler

When someone replies to your Instagram story, the webhook receives the message with story context. The bot processes it like a regular DM.

### Story Mention Handler

When someone mentions you in their story, Clonnect can auto-send a thank-you DM.

Configure with environment variable:
```bash
STORY_MENTION_RESPONSE="Thanks for sharing! How can I help you?"
```

## 12. Comments Auto-DM

When enabled, Clonnect monitors post comments for interest signals and sends a DM to interested commenters.

### Enable

```bash
AUTO_DM_ON_COMMENTS=true
COMMENT_DM_TEMPLATE="Hi! I saw your comment and wanted to reach out. How can I help?"
```

### Interest Keywords

Default keywords that trigger auto-DM:
- Price-related: precio, cuánto, cost, how much
- Interest: interesa, interested, quiero, want
- Action: comprar, buy, reservar, book

## 13. Token Refresh

Instagram Page Access Tokens expire after 60 days. To handle this:

1. **Monitor expiration**: Check token status via `/oauth/status/{creator_id}`
2. **Auto-refresh**: Implement token refresh logic (requires storing refresh tokens)
3. **Manual re-auth**: Creator can reconnect via OAuth if token expires

## 14. Troubleshooting

### Webhook Not Receiving Events

1. Check webhook URL is correct and accessible
2. Verify the verify token matches
3. Ensure webhook subscriptions are active
4. Check Meta App status (not in "Development" mode issues)

### Messages Not Sending

1. Check `bot_active` is true for the creator
2. Verify `instagram_token` is valid (not expired)
3. Check rate limits (200 messages/day per user)
4. Ensure Page messaging is enabled in Facebook settings

### OAuth Failing

1. Check META_APP_ID and META_APP_SECRET are correct
2. Verify redirect URI matches exactly
3. Ensure required scopes are requested
4. Check if app is in Development mode (only testers can use)

### Multi-Creator Not Working

1. Verify `instagram_page_id` is set for each creator
2. Check creator lookup: `GET /instagram/creators`
3. Review webhook logs for page_id extraction

## 15. Rate Limits

Instagram API has strict rate limits:

| Limit | Value |
|-------|-------|
| Messages per user per day | 200 |
| API calls per hour | 200 per user |
| Webhook events | No limit |

If you hit rate limits, messages will fail silently. Monitor the `errors` count in handler stats.

## 16. Security Best Practices

1. **Webhook Signature Verification**: Always verify `X-Hub-Signature-256` header
2. **Token Storage**: Store tokens encrypted in database
3. **Scopes**: Request only necessary permissions
4. **App Review**: Complete App Review before production launch
5. **Rate Limiting**: Implement client-side rate limiting to avoid bans

## Quick Reference

| Endpoint | Purpose |
|----------|---------|
| `POST /webhook/instagram` | Receive webhook events |
| `GET /webhook/instagram` | Webhook verification |
| `GET /oauth/instagram/start` | Start OAuth flow |
| `GET /instagram/status/{id}` | Check connection status |
| `GET /instagram/creators` | List all connected creators |
| `POST /instagram/icebreakers/{id}` | Set Ice Breakers |
| `POST /instagram/persistent-menu/{id}` | Set Persistent Menu |
| `POST /instagram/connect` | Manual page connection |
