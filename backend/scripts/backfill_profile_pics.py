"""
Backfill profile pics and usernames for leads missing them.

Strategy:
- Iris: Use Graph API (IGAAT token) to fetch profile_pic for each lead
- Stefano: Token expired → try Graph API with Iris token for shared leads,
  otherwise skip (needs token refresh)
- Stores IG CDN URL directly. Railway's refresh_profile_pics_job will later
  upload to Cloudinary for permanent storage.

Usage:
    python3 scripts/backfill_profile_pics.py
    python3 scripts/backfill_profile_pics.py --creator iris_bertran
    python3 scripts/backfill_profile_pics.py --dry-run
"""

import argparse
import os
import sys
import time

import psycopg2
import requests

DB_URL = os.environ.get("DATABASE_URL")
if not DB_URL:
    print("ERROR: DATABASE_URL environment variable is required")
    sys.exit(1)
API_BASE = "https://graph.instagram.com/v21.0"
REQUEST_DELAY = 0.3  # 200 requests/min — well within limits


def get_creator_config(cur, creator_name):
    cur.execute(
        "SELECT id, instagram_token, instagram_user_id FROM creators WHERE name = %s",
        (creator_name,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {"id": str(row[0]), "token": row[1], "ig_user_id": row[2]}


def verify_token(token):
    """Check if token works."""
    try:
        r = requests.get(
            f"{API_BASE}/me?fields=id,username&access_token={token}", timeout=10
        )
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


def fetch_profile_graph_api(user_id, token):
    """Fetch profile via Graph API. Returns dict or None."""
    try:
        r = requests.get(
            f"{API_BASE}/{user_id}",
            params={"fields": "id,username,name,profile_pic", "access_token": token},
            timeout=10,
        )
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="Backfill profile pics for leads")
    parser.add_argument("--creator", type=str, default=None, help="Specific creator (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--limit", type=int, default=0, help="Max leads to process (0=all)")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False
    cur = conn.cursor()

    creators_to_process = [args.creator] if args.creator else ["iris_bertran", "stefano_bonanno"]

    for creator_name in creators_to_process:
        print(f"\n{'='*60}")
        print(f"Processing: {creator_name}")
        print(f"{'='*60}")

        config = get_creator_config(cur, creator_name)
        if not config:
            print(f"  Creator not found, skipping")
            continue

        # Verify token
        token = config["token"]
        token_info = verify_token(token) if token else None
        if token_info:
            print(f"  Token OK: @{token_info.get('username')} (id={token_info.get('id')})")
        else:
            print(f"  Token EXPIRED or invalid — skipping Graph API enrichment")
            token = None

        creator_uuid = config["id"]

        # ── Part A: Leads without username ──
        cur.execute(
            """
            SELECT id, platform_user_id FROM leads
            WHERE creator_id = %s AND platform = 'instagram'
            AND (username IS NULL OR username = '')
            """,
            (creator_uuid,),
        )
        no_username = cur.fetchall()
        print(f"\n  [A] Leads without username: {len(no_username)}")

        if no_username and token:
            enriched_u = 0
            failed_u = 0
            for lead_id, puid in no_username:
                time.sleep(REQUEST_DELAY)
                profile = fetch_profile_graph_api(puid, token)
                if profile and profile.get("username"):
                    if not args.dry_run:
                        cur.execute(
                            """
                            UPDATE leads SET username = %s, full_name = %s, profile_pic_url = %s
                            WHERE id = %s
                            """,
                            (
                                profile["username"],
                                profile.get("name") or None,
                                profile.get("profile_pic") or None,
                                lead_id,
                            ),
                        )
                        conn.commit()
                    enriched_u += 1
                    print(f"    ✓ {puid} → @{profile['username']}")
                else:
                    failed_u += 1
                    print(f"    ✗ {puid} — profile not found")

            print(f"  [A] Result: {enriched_u} enriched, {failed_u} failed")
        elif no_username and not token:
            print(f"  [A] Skipped — token expired")

        # ── Part B: Leads with username but no profile pic ──
        limit_clause = f"LIMIT {args.limit}" if args.limit > 0 else ""
        cur.execute(
            f"""
            SELECT id, platform_user_id, username FROM leads
            WHERE creator_id = %s AND platform = 'instagram'
            AND username IS NOT NULL AND username != ''
            AND (profile_pic_url IS NULL OR profile_pic_url = '')
            ORDER BY last_contact_at DESC NULLS LAST
            {limit_clause}
            """,
            (creator_uuid,),
        )
        no_pic = cur.fetchall()
        print(f"\n  [B] Leads with username but no pic: {len(no_pic)}")

        if no_pic and token:
            enriched_p = 0
            failed_p = 0
            for lead_id, puid, username in no_pic:
                time.sleep(REQUEST_DELAY)
                profile = fetch_profile_graph_api(puid, token)
                pic_url = profile.get("profile_pic") if profile else None

                if pic_url:
                    if not args.dry_run:
                        # Also update username/name if we got better data
                        cur.execute(
                            """
                            UPDATE leads SET
                                profile_pic_url = %s,
                                full_name = COALESCE(NULLIF(%s, ''), full_name)
                            WHERE id = %s
                            """,
                            (pic_url, profile.get("name", ""), lead_id),
                        )
                        conn.commit()
                    enriched_p += 1
                    if enriched_p % 50 == 0 or enriched_p <= 5:
                        print(f"    ✓ [{enriched_p}/{len(no_pic)}] @{username} — pic fetched")
                else:
                    failed_p += 1
                    if failed_p <= 5:
                        print(f"    ✗ @{username} ({puid}) — no pic returned")

            print(f"  [B] Result: {enriched_p} pics fetched, {failed_p} failed")
        elif no_pic and not token:
            print(f"  [B] Skipped — token expired")

        # ── Also check for self-lead (iraais5 showing in Iris's leads) ──
        if creator_name == "iris_bertran":
            cur.execute(
                """
                SELECT id, platform_user_id, username FROM leads
                WHERE creator_id = %s AND platform_user_id = '17841400999933058'
                """,
                (creator_uuid,),
            )
            self_lead = cur.fetchone()
            if self_lead:
                print(f"\n  [C] Found self-lead @{self_lead[2]} (uid=17841400999933058) — this is Iris herself")

    # Final summary
    print(f"\n{'='*60}")
    print("Final counts:")
    for creator_name in creators_to_process:
        config = get_creator_config(cur, creator_name)
        if not config:
            continue
        cur.execute(
            "SELECT count(*) FROM leads WHERE creator_id = %s AND platform = 'instagram' AND (username IS NULL OR username = '')",
            (config["id"],),
        )
        no_u = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM leads WHERE creator_id = %s AND platform = 'instagram' AND username IS NOT NULL AND username != '' AND (profile_pic_url IS NULL OR profile_pic_url = '')",
            (config["id"],),
        )
        no_p = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM leads WHERE creator_id = %s AND platform = 'instagram' AND profile_pic_url IS NOT NULL AND profile_pic_url != ''",
            (config["id"],),
        )
        with_p = cur.fetchone()[0]
        print(f"  {creator_name}: no_username={no_u}, no_pic={no_p}, with_pic={with_p}")

    cur.close()
    conn.close()
    print("\nDone!")


if __name__ == "__main__":
    main()
