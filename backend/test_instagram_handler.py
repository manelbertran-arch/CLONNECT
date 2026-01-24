#!/usr/bin/env python3
"""Test Instagram handler credentials loading"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Clear any Instagram ENV vars to test DB loading
for var in ['INSTAGRAM_ACCESS_TOKEN', 'INSTAGRAM_PAGE_ID', 'INSTAGRAM_USER_ID']:
    if var in os.environ:
        del os.environ[var]

print("=" * 70)
print("🔍 TEST INSTAGRAM HANDLER - Credentials from DB")
print("=" * 70)

# Reset the global handler
import core.instagram_handler as ih
ih._handler = None

# Get handler (should load from DB)
handler = ih.get_instagram_handler()

print(f"\n✅ Handler created:")
print(f"   creator_id: {handler.creator_id}")
print(f"   access_token: {len(handler.access_token)} chars" if handler.access_token else "   access_token: EMPTY")
print(f"   page_id: {handler.page_id}")
print(f"   ig_user_id: {handler.ig_user_id}")
print(f"   connector: {'✅ Initialized' if handler.connector else '❌ Not initialized'}")
print(f"   dm_agent: {'✅ Initialized' if handler.dm_agent else '❌ Not initialized'}")

print("\n" + "=" * 70)
if handler.access_token and len(handler.access_token) > 50:
    print("✅ SUCCESS: Instagram credentials loaded from database!")
else:
    print("❌ FAIL: Instagram credentials NOT loaded")
print("=" * 70)
