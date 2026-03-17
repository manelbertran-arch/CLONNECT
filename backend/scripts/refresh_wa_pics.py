"""
Bulk refresh WhatsApp profile pictures for iris_bertran using Evolution API.
Run with: railway run python3 scripts/refresh_wa_pics.py
"""

import logging
import os
import re
import sys
import time

import psycopg2
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "")
INSTANCE = "iris-bertran"
CREATOR_NAME = "iris_bertran"
BATCH_SIZE = 50
RATE_DELAY = 0.5  # seconds between API calls


def get_wa_leads_without_photo(conn) -> list:
    """Get WhatsApp leads without profile pics."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT l.id, l.platform_user_id, l.username
            FROM leads l
            JOIN creators c ON l.creator_id = c.id
            WHERE c.name = %s
              AND l.platform_user_id LIKE 'wa_%%'
              AND (l.profile_pic_url IS NULL OR l.profile_pic_url = '')
            ORDER BY l.last_contact_at DESC NULLS LAST
        """, (CREATOR_NAME,))
        return cur.fetchall()


def fetch_profile_picture(number: str) -> str | None:
    """Fetch profile pic URL from Evolution API."""
    url = f"{EVOLUTION_API_URL}/chat/fetchProfilePictureUrl/{INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        resp = requests.post(url, json={"number": number}, headers=headers, timeout=10)
        if resp.status_code >= 400:
            return None
        result = resp.json()
        return result.get("profilePictureUrl") or result.get("url") or None
    except Exception as e:
        logger.warning(f"Error fetching pic for {number}: {e}")
        return None


def extract_number(platform_user_id: str) -> str | None:
    """Extract phone number from wa_XXXXX format."""
    if not platform_user_id or not platform_user_id.startswith("wa_"):
        return None
    number = platform_user_id[3:]
    if re.match(r"^\d{8,15}$", number):
        return number
    return None


def main():
    if not DATABASE_URL:
        logger.error("DATABASE_URL not set")
        sys.exit(1)
    if not EVOLUTION_API_URL:
        logger.error("EVOLUTION_API_URL not set")
        sys.exit(1)

    conn = psycopg2.connect(DATABASE_URL)
    leads = get_wa_leads_without_photo(conn)
    logger.info(f"Found {len(leads)} WhatsApp leads without profile pics")

    if not leads:
        conn.close()
        return

    updated = 0
    failed = 0
    skipped = 0

    for i, (lead_id, platform_user_id, username) in enumerate(leads):
        number = extract_number(platform_user_id)
        if not number:
            skipped += 1
            continue

        pic_url = fetch_profile_picture(number)
        if pic_url:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE leads SET profile_pic_url = %s WHERE id = %s",
                    (pic_url, lead_id),
                )
            updated += 1
        else:
            failed += 1

        # Commit in batches
        if (i + 1) % BATCH_SIZE == 0:
            conn.commit()
            logger.info(f"Progress: {i+1}/{len(leads)} | updated={updated} failed={failed} skipped={skipped}")

        time.sleep(RATE_DELAY)

    conn.commit()
    conn.close()

    logger.info(f"DONE: updated={updated} failed={failed} skipped={skipped} total={len(leads)}")


if __name__ == "__main__":
    main()
