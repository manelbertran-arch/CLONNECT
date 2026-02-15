#!/usr/bin/env python3
"""
Setup script to connect a Telegram bot to Clonnect.

Prerequisites:
1. Create a bot via @BotFather on Telegram -> get the token
2. Have the Clonnect backend running (local or production)

Usage:
  python scripts/setup_telegram_bot.py <bot_token> <creator_id> [--webhook-url URL]

Examples:
  # Production
  python scripts/setup_telegram_bot.py "123456:ABC-DEF" "stefano_bonanno" \
    --webhook-url "https://www.clonnectapp.com/webhook/telegram"

  # Local development
  python scripts/setup_telegram_bot.py "123456:ABC-DEF" "manel" \
    --webhook-url "https://your-ngrok-url.ngrok.io/webhook/telegram"

  # Register via Clonnect API instead of Telegram directly
  python scripts/setup_telegram_bot.py "123456:ABC-DEF" "stefano_bonanno" \
    --api-url "https://www.clonnectapp.com"

Steps performed:
1. Verify the bot token with Telegram API (getMe)
2. Register the webhook with Telegram (setWebhook)
3. Optionally register the bot in Clonnect via /telegram/register-bot API
4. Verify webhook is set correctly (getWebhookInfo)
"""
import argparse
import sys

import httpx


def verify_token(token: str) -> dict | None:
    """Verify bot token by calling Telegram getMe."""
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        resp = httpx.get(url, timeout=10.0)
        data = resp.json()
        if data.get("ok"):
            bot = data["result"]
            print(f"  Bot verified: @{bot['username']} ({bot['first_name']})")
            print(f"  Bot ID: {bot['id']}")
            return bot
        else:
            print(f"  ERROR: Invalid token - {data.get('description', 'Unknown error')}")
            return None
    except Exception as e:
        print(f"  ERROR: Could not reach Telegram API - {e}")
        return None


def set_webhook(token: str, webhook_url: str) -> bool:
    """Register webhook with Telegram."""
    url = f"https://api.telegram.org/bot{token}/setWebhook"
    try:
        resp = httpx.post(url, json={
            "url": webhook_url,
            "allowed_updates": ["message", "callback_query"]
        }, timeout=10.0)
        data = resp.json()
        if data.get("ok"):
            print(f"  Webhook set: {webhook_url}")
            return True
        else:
            print(f"  ERROR: {data.get('description', 'Unknown error')}")
            return False
    except Exception as e:
        print(f"  ERROR: Could not set webhook - {e}")
        return False


def verify_webhook(token: str) -> dict | None:
    """Verify webhook is configured correctly."""
    url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
    try:
        resp = httpx.get(url, timeout=10.0)
        data = resp.json()
        if data.get("ok"):
            info = data["result"]
            print(f"  Current URL: {info.get('url', 'NOT SET')}")
            print(f"  Pending updates: {info.get('pending_update_count', 0)}")
            if info.get("last_error_message"):
                print(f"  Last error: {info['last_error_message']}")
            return info
        return None
    except Exception as e:
        print(f"  ERROR: Could not verify webhook - {e}")
        return None


def register_in_clonnect(api_url: str, token: str, creator_id: str) -> bool:
    """Register bot via Clonnect /telegram/register-bot API."""
    url = f"{api_url.rstrip('/')}/telegram/register-bot"
    try:
        resp = httpx.post(url, json={
            "creator_id": creator_id,
            "bot_token": token,
            "set_webhook": True
        }, timeout=30.0)

        if resp.status_code == 200:
            data = resp.json()
            print(f"  Registered in Clonnect: bot_id={data.get('bot_id')}")
            print(f"  Creator: {data.get('creator_id')}")
            print(f"  Webhook set by API: {data.get('webhook_set')}")
            return True
        else:
            print(f"  ERROR: API returned {resp.status_code} - {resp.text}")
            return False
    except Exception as e:
        print(f"  ERROR: Could not reach Clonnect API - {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Setup a Telegram bot for Clonnect"
    )
    parser.add_argument("bot_token", help="Bot token from @BotFather")
    parser.add_argument("creator_id", help="Clonnect creator ID (e.g. stefano_bonanno)")
    parser.add_argument(
        "--webhook-url",
        default=None,
        help="Webhook URL (default: https://www.clonnectapp.com/webhook/telegram)"
    )
    parser.add_argument(
        "--api-url",
        default=None,
        help="Clonnect API URL to register bot via API (e.g. https://www.clonnectapp.com)"
    )
    parser.add_argument(
        "--skip-webhook",
        action="store_true",
        help="Skip webhook setup (useful for polling mode)"
    )

    args = parser.parse_args()

    webhook_url = args.webhook_url or "https://www.clonnectapp.com/webhook/telegram"

    print("=" * 60)
    print("Clonnect Telegram Bot Setup")
    print("=" * 60)

    # Step 1: Verify token
    print("\n[1/4] Verifying bot token...")
    bot_info = verify_token(args.bot_token)
    if not bot_info:
        print("\nSetup FAILED: Invalid bot token")
        sys.exit(1)

    # Step 2: Register via Clonnect API (if --api-url provided)
    if args.api_url:
        print(f"\n[2/4] Registering bot in Clonnect via API ({args.api_url})...")
        if not register_in_clonnect(args.api_url, args.bot_token, args.creator_id):
            print("\nWARNING: Could not register via API, continuing with direct setup...")
    else:
        print("\n[2/4] Skipping API registration (no --api-url provided)")

    # Step 3: Set webhook
    if not args.skip_webhook:
        print(f"\n[3/4] Setting webhook -> {webhook_url}")
        if not set_webhook(args.bot_token, webhook_url):
            print("\nSetup FAILED: Could not set webhook")
            sys.exit(1)
    else:
        print("\n[3/4] Skipping webhook setup (--skip-webhook)")

    # Step 4: Verify
    print("\n[4/4] Verifying webhook configuration...")
    verify_webhook(args.bot_token)

    print("\n" + "=" * 60)
    print("Setup COMPLETE")
    print("=" * 60)
    print(f"\nBot: @{bot_info['username']}")
    print(f"Creator: {args.creator_id}")
    print(f"Webhook: {webhook_url}")
    print("\nNext steps:")
    print("  1. Set TELEGRAM_BOT_TOKEN in Railway environment variables")
    print("  2. Send a message to your bot on Telegram")
    print("  3. Check /telegram/status on the backend for status")
    print("  4. Check /telegram/diagnose for webhook health")
    print("  5. Verify lead appears in the CRM with platform=telegram")


if __name__ == "__main__":
    main()
