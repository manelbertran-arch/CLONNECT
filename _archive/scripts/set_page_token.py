#!/usr/bin/env python3
"""
Quick script to set Page Access Token for Instagram Messaging.

Usage:
    python3 set_page_token.py 'EAA_YOUR_TOKEN_HERE'

Get the token from:
    https://developers.facebook.com/tools/explorer/
    1. Select your App
    2. Select "Page" (not User)
    3. Add permissions: pages_messaging, instagram_manage_messages
    4. Generate Access Token
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 set_page_token.py 'EAA_YOUR_TOKEN_HERE'")
        print("\nGet the token from Graph API Explorer:")
        print("  https://developers.facebook.com/tools/explorer/")
        sys.exit(1)

    token = sys.argv[1]
    creator_id = sys.argv[2] if len(sys.argv) > 2 else "stefano_bonanno"

    print(f"Setting Page Access Token for: {creator_id}")
    print(f"Token prefix: {token[:15]}...")
    print(f"Token type: {'PAGE (EAA)' if token.startswith('EAA') else 'INSTAGRAM (IGAAT)' if token.startswith('IGAAT') else 'UNKNOWN'}")

    if not token.startswith("EAA"):
        print("\n⚠️  WARNING: Token doesn't start with 'EAA'")
        print("    This may not be a Page Access Token!")
        confirm = input("Continue anyway? (y/n): ")
        if confirm.lower() != 'y':
            print("Aborted.")
            sys.exit(1)

    from api.database import SessionLocal
    from api.models import Creator

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()

        if not creator:
            print(f"Error: Creator '{creator_id}' not found")
            sys.exit(1)

        old_prefix = creator.instagram_token[:15] if creator.instagram_token else "NONE"
        creator.instagram_token = token
        session.commit()

        print(f"\n✅ Token updated successfully!")
        print(f"   Old: {old_prefix}...")
        print(f"   New: {token[:15]}...")

        # Test the token
        print("\n🧪 Testing token...")
        import requests

        # Test with /me/accounts to verify it's a Page token
        url = "https://graph.facebook.com/v21.0/me/accounts"
        params = {"access_token": token, "fields": "id,name"}
        resp = requests.get(url, params=params, timeout=10)

        if resp.status_code == 200:
            data = resp.json()
            if data.get("data"):
                print(f"   ✅ Token can access Pages: {len(data['data'])} pages found")
                for page in data['data'][:2]:
                    print(f"      - {page.get('name')} (ID: {page.get('id')})")
            else:
                print("   ⚠️  No pages found - might be wrong token type")
        else:
            print(f"   ❌ API error: {resp.text[:200]}")

    finally:
        session.close()


if __name__ == "__main__":
    main()
