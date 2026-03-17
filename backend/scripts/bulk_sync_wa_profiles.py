#!/usr/bin/env python3
"""
Bulk sync WhatsApp profile photos and names from Evolution API contacts cache.

Uses the findContacts endpoint which returns cached contact data (profilePicUrl, pushName)
without needing to hit WhatsApp servers per-contact. Much faster and more complete.

Usage:
    python3 scripts/bulk_sync_wa_profiles.py iris_bertran
    python3 scripts/bulk_sync_wa_profiles.py stefano_bonanno
    python3 scripts/bulk_sync_wa_profiles.py --all
"""
import os
import sys
import json
import requests

# DB connection
DATABASE_URL = os.environ.get("DATABASE_URL", "")
EVOLUTION_API_URL = os.environ.get("EVOLUTION_API_URL", "https://evolution-api-production-d840.up.railway.app")
EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY", "clonnect-evo-2026-prod")

INSTANCE_MAP = {
    "iris_bertran": "iris-bertran",
    "stefano_bonanno": "stefano-fitpack",
}


def fetch_evolution_contacts(instance: str) -> list:
    """Fetch all contacts from Evolution API findContacts endpoint."""
    url = f"{EVOLUTION_API_URL}/chat/findContacts/{instance}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    resp = requests.post(url, json={}, headers=headers, timeout=30)
    if resp.status_code != 200:
        print(f"  ERROR: findContacts returned {resp.status_code}: {resp.text[:200]}")
        return []
    return resp.json()


def sync_profiles(creator_name: str):
    """Sync Evolution contact profiles to DB leads."""
    import sqlalchemy
    from sqlalchemy import text

    instance = INSTANCE_MAP.get(creator_name)
    if not instance:
        print(f"ERROR: Unknown creator {creator_name}")
        return

    print(f"\n{'='*60}")
    print(f"Syncing WA profiles for {creator_name} (instance: {instance})")
    print(f"{'='*60}")

    # 1. Fetch all contacts from Evolution
    print("Fetching Evolution contacts...")
    contacts = fetch_evolution_contacts(instance)
    print(f"  Got {len(contacts)} contacts total")

    # Build lookup: remoteJid -> {pic, name}
    # remoteJid format: "34654949433@s.whatsapp.net"
    contact_map = {}
    for c in contacts:
        jid = c.get("remoteJid", "")
        if not jid or c.get("isGroup"):
            continue
        number = jid.split("@")[0]
        pic_url = c.get("profilePicUrl") or ""
        push_name = c.get("pushName") or ""
        if pic_url or push_name:
            contact_map[number] = {"pic": pic_url, "name": push_name}

    print(f"  Individual contacts with data: {len(contact_map)}")
    print(f"  With pics: {sum(1 for v in contact_map.values() if v['pic'])}")
    print(f"  With names: {sum(1 for v in contact_map.values() if v['name'])}")

    # 2. Get DB leads missing pics or names
    engine = sqlalchemy.create_engine(DATABASE_URL)
    with engine.connect() as conn:
        # Get creator UUID
        result = conn.execute(
            text("SELECT id FROM creators WHERE name = :name"),
            {"name": creator_name}
        )
        row = result.fetchone()
        if not row:
            print(f"ERROR: Creator {creator_name} not found in DB")
            return
        creator_id = str(row[0])

        # Get all WA leads
        result = conn.execute(
            text("""
                SELECT id, platform_user_id, profile_pic_url, full_name
                FROM leads
                WHERE creator_id = :cid AND platform = 'whatsapp'
            """),
            {"cid": creator_id}
        )
        leads = result.fetchall()
        print(f"\n  DB leads (WA): {len(leads)}")

        updated_pics = 0
        updated_names = 0
        matched = 0

        for lead_id, puid, current_pic, current_name in leads:
            if not puid:
                continue
            # Extract number from platform_user_id (wa_34654949433)
            number = puid.replace("wa_", "").lstrip("+")

            contact = contact_map.get(number)
            if not contact:
                continue

            matched += 1
            updates = {}

            # Update pic if missing
            if (not current_pic or current_pic == "") and contact["pic"]:
                updates["profile_pic_url"] = contact["pic"]

            # Update name if missing (and not just a phone number)
            if (not current_name or current_name == "") and contact["name"]:
                # Skip if pushName is just a number
                if not contact["name"].strip().replace("+", "").replace(" ", "").isdigit():
                    updates["full_name"] = contact["name"]

            if updates:
                set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
                updates["lid"] = str(lead_id)
                conn.execute(
                    text(f"UPDATE leads SET {set_clauses} WHERE id = :lid"),
                    updates
                )
                if "profile_pic_url" in updates:
                    updated_pics += 1
                if "full_name" in updates:
                    updated_names += 1

        conn.commit()

    print(f"\n  Results:")
    print(f"    Matched contacts: {matched}")
    print(f"    Updated pics: {updated_pics}")
    print(f"    Updated names: {updated_names}")
    print(f"  Done!")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/bulk_sync_wa_profiles.py <creator_name|--all>")
        sys.exit(1)

    target = sys.argv[1]

    if target == "--all":
        for creator in INSTANCE_MAP:
            sync_profiles(creator)
    else:
        sync_profiles(target)

    # Print final stats
    import sqlalchemy
    from sqlalchemy import text
    engine = sqlalchemy.create_engine(DATABASE_URL)
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT c.name, l.platform,
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE l.profile_pic_url IS NOT NULL AND l.profile_pic_url != '') as has_pic,
                COUNT(*) FILTER (WHERE l.full_name IS NOT NULL AND l.full_name != '') as has_name
            FROM leads l JOIN creators c ON l.creator_id = c.id
            WHERE l.platform = 'whatsapp'
            GROUP BY c.name, l.platform
            ORDER BY c.name
        """))
        print(f"\n{'='*60}")
        print("Final WA profile stats:")
        print(f"{'='*60}")
        for row in result:
            name, platform, total, has_pic, has_name = row
            print(f"  {name}: {total} total, {has_pic} pics ({100*has_pic//total}%), {has_name} names ({100*has_name//total}%)")


if __name__ == "__main__":
    main()
