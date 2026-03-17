"""
One-time script: Refresh profile pics for all Instagram leads.
Uses Instagram's public API + Cloudinary for permanent URLs.

Run: cd ~/Clonnect/backend && railway run python3 scripts/refresh_pics_now.py
"""
import os
import sys
import time

import psycopg2
import requests

BATCH_SIZE = 50
DELAY_BETWEEN_CALLS = 2.0  # seconds between API calls (avoid rate limiting)
RATE_LIMIT_PAUSE = 120  # seconds to wait when rate limited
MAX_RATE_LIMIT_RETRIES = 3  # max times to pause and retry after rate limit
IG_APP_ID = "936619743392459"


def fetch_profile_pic(username: str) -> str | None:
    """Fetch profile pic URL from Instagram's public API."""
    try:
        resp = requests.get(
            f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}",
            headers={
                "User-Agent": "Instagram 76.0.0.15.395 Android",
                "x-ig-app-id": IG_APP_ID,
            },
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            user = data.get("data", {}).get("user", {})
            if user:
                return user.get("profile_pic_url_hd") or user.get("profile_pic_url") or None
            return None
        elif resp.status_code in (401, 429):
            return "RATE_LIMITED"
        return None
    except Exception:
        return None


def upload_to_cloudinary(pic_url: str, creator_name: str, platform_uid: str):
    """Upload pic to Cloudinary, return permanent URL or None."""
    try:
        import cloudinary
        import cloudinary.uploader

        cloudinary_url = os.environ.get("CLOUDINARY_URL")
        if not cloudinary_url:
            return None
        cloudinary.config()

        result = cloudinary.uploader.upload(
            pic_url,
            resource_type="image",
            secure=True,
            folder=f"clonnect/{creator_name}/profiles",
            public_id=f"profile_{platform_uid}",
            overwrite=True,
        )
        return result.get("secure_url")
    except Exception as e:
        print(f"    Cloudinary error: {e}")
        return None


def main():
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not set. Run with: railway run python3 scripts/refresh_pics_now.py")
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    # Get creator info
    cur.execute("SELECT id, name FROM creators WHERE instagram_token IS NOT NULL LIMIT 1")
    creator = cur.fetchone()
    if not creator:
        print("No creator with IG token found")
        sys.exit(1)

    creator_id, creator_name = creator
    print(f"Creator: {creator_name}")

    # Check Cloudinary
    has_cloudinary = bool(os.environ.get("CLOUDINARY_URL"))
    print(f"Cloudinary: {'configured' if has_cloudinary else 'NOT configured'}")

    # Get all IG leads needing profile pic refresh
    cur.execute("""
        SELECT id, platform_user_id, username, profile_pic_url
        FROM leads
        WHERE creator_id = %s
          AND platform = 'instagram'
          AND platform_user_id IS NOT NULL
          AND username IS NOT NULL
          AND username != ''
          AND (profile_pic_url IS NULL OR profile_pic_url NOT LIKE '%%cloudinary%%')
        ORDER BY last_contact_at DESC NULLS LAST
    """, (str(creator_id),))
    leads = cur.fetchall()
    print(f"Leads to refresh: {len(leads)}")
    print("=" * 60)

    refreshed = 0
    failed = 0
    no_pic = 0
    rate_limit_hits = 0

    for i, (lead_id, platform_uid, username, current_pic) in enumerate(leads):
        # Skip empty usernames
        if not username or username.strip() in ("", "@"):
            failed += 1
            continue

        # Fetch pic from IG public API
        clean_username = username.strip().lstrip("@")
        pic_url = fetch_profile_pic(clean_username)

        if pic_url == "RATE_LIMITED":
            rate_limit_hits += 1
            if rate_limit_hits > MAX_RATE_LIMIT_RETRIES:
                print(f"  [{i+1}] Rate limited {rate_limit_hits}x, stopping.")
                break
            print(f"  [{i+1}] Rate limited! Pausing {RATE_LIMIT_PAUSE}s... (attempt {rate_limit_hits}/{MAX_RATE_LIMIT_RETRIES})")
            time.sleep(RATE_LIMIT_PAUSE)
            # Retry this lead
            pic_url = fetch_profile_pic(clean_username)
            if pic_url == "RATE_LIMITED" or not pic_url:
                print(f"  [{i+1}] Still rate limited after pause, continuing...")
                no_pic += 1
                continue

        if not pic_url:
            no_pic += 1
            if i < 5:
                print(f"  [{i+1}/{len(leads)}] @{username} -> no pic from API")
            continue

        # Upload to Cloudinary
        final_url = pic_url
        if has_cloudinary:
            cloud_url = upload_to_cloudinary(pic_url, creator_name, platform_uid)
            if cloud_url:
                final_url = cloud_url

        # Update DB
        cur.execute(
            "UPDATE leads SET profile_pic_url = %s WHERE id = %s",
            (final_url, str(lead_id))
        )
        refreshed += 1

        status = "cloudinary" if "cloudinary" in final_url else "cdn"
        if (i + 1) % 10 == 0 or i < 3:
            print(f"  [{i+1}/{len(leads)}] @{username} -> {status} OK")

        # Commit every batch
        if (i + 1) % BATCH_SIZE == 0:
            conn.commit()
            print(f"  --- Batch {(i+1)//BATCH_SIZE} committed ({refreshed} ok, {failed} fail, {no_pic} no pic) ---")

        time.sleep(DELAY_BETWEEN_CALLS)

    conn.commit()
    conn.close()

    print("\n" + "=" * 60)
    print(f"DONE:")
    print(f"  Refreshed: {refreshed}")
    print(f"  Failed (no username): {failed}")
    print(f"  No pic from API: {no_pic}")
    print(f"  Rate limit pauses: {rate_limit_hits}")
    print(f"  Total processed: {i + 1 if leads else 0}/{len(leads)}")


if __name__ == "__main__":
    main()
