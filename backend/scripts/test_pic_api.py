"""Test different Graph API endpoints for fetching profile pics."""
import json
import os
import sys

import psycopg2
import requests

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()
cur.execute("SELECT instagram_token, instagram_page_id FROM creators WHERE instagram_token IS NOT NULL LIMIT 1")
row = cur.fetchone()
token = row[0]
page_id = row[1]
print(f"Token prefix: {token[:15]}...")
print(f"Page ID: {page_id}")

# A known working IGSID and a failing one
test_ids = [
    ("1797892410735315", "joshfeldberg"),   # has cloudinary pic
    ("24216120874689533", "_soham.yoga"),    # no pic
]

# Test 1: Standard /user endpoint
print("\n=== Test 1: Standard /{user_id} endpoint ===")
for uid, name in test_ids:
    resp = requests.get(
        f"https://graph.facebook.com/v21.0/{uid}",
        params={"fields": "id,username,name,profile_pic", "access_token": token},
        timeout=5,
    )
    d = resp.json()
    err = d.get("error", {}).get("message", "")
    pic = d.get("profile_pic", "")[:60] if not err else ""
    print(f"  @{name}: {resp.status_code} | err={err[:80]} | pic={pic}")

# Test 2: me/conversations with senders
print("\n=== Test 2: /me/conversations ===")
resp = requests.get(
    f"https://graph.facebook.com/v21.0/me/conversations",
    params={
        "platform": "instagram",
        "fields": "participants,updated_time",
        "access_token": token,
        "limit": 5,
    },
    timeout=10,
)
d = resp.json()
if "data" in d:
    for conv in d["data"][:5]:
        participants = conv.get("participants", {}).get("data", [])
        for p in participants:
            print(f"  Conv participant: id={p.get('id')} name={p.get('name','?')} username={p.get('username','?')}")
elif "error" in d:
    print(f"  Error: {d['error']['message']}")
else:
    print(f"  Response: {json.dumps(d)[:200]}")

# Test 3: Try IG Business API endpoint if we have ig_business_id
print("\n=== Test 3: Check creator fields ===")
cur.execute("SELECT instagram_page_id, instagram_business_id FROM creators WHERE instagram_token IS NOT NULL LIMIT 1")
row2 = cur.fetchone()
print(f"  instagram_page_id: {row2[0]}")
print(f"  instagram_business_id: {row2[1]}")

# Test 4: Try getting user info from a conversation message
print("\n=== Test 4: Get conversations with messages ===")
resp = requests.get(
    f"https://graph.facebook.com/v21.0/me/conversations",
    params={
        "platform": "instagram",
        "fields": "participants{id,name,username,profile_pic}",
        "access_token": token,
        "limit": 3,
    },
    timeout=10,
)
d = resp.json()
if "data" in d:
    for conv in d["data"][:3]:
        participants = conv.get("participants", {}).get("data", [])
        for p in participants:
            print(f"  id={p.get('id')} | name={p.get('name','?')} | pic={str(p.get('profile_pic',''))[:60]}")
elif "error" in d:
    print(f"  Error: {d['error']['message']}")

conn.close()
