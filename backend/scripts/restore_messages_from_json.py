#!/usr/bin/env python3
"""
Restore messages from stefan_conversations_full.json backup.
Uses UPSERT logic to avoid duplicates.
"""
import json
import os
import sys
import uuid
from datetime import datetime
from typing import Optional
import psycopg2
from psycopg2.extras import execute_values

# Database connection
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://neondb_owner:npg_91lRcgDvZAIy@ep-raspy-truth-agjtq3o5-pooler.c-2.eu-central-1.aws.neon.tech/neondb?sslmode=require"
)

# JSON backup file
JSON_FILE = "/Users/manelbertranluque/Desktop/clonnect_audience_intelligence/data/stefan_conversations_full.json"

# Creator ID from metadata
CREATOR_ID = "5e5c2364-c99a-4484-b986-741bb84a11cf"


def load_backup_data() -> dict:
    """Load the JSON backup file."""
    print(f"Loading backup from: {JSON_FILE}")
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"Loaded {len(data.get('conversations', []))} conversations")
    return data


def get_existing_leads(conn) -> dict:
    """Get all existing leads for the creator, indexed by username."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, username, platform_user_id, full_name
        FROM leads
        WHERE creator_id = %s
    """, (CREATOR_ID,))
    leads = {}
    for row in cursor.fetchall():
        lead_id, username, platform_user_id, full_name = row
        if username:
            leads[username.lower()] = {
                'id': lead_id,
                'username': username,
                'platform_user_id': platform_user_id,
                'full_name': full_name
            }
    cursor.close()
    print(f"Found {len(leads)} existing leads in DB")
    return leads


def get_existing_messages(conn, lead_id: str) -> set:
    """Get existing message fingerprints for a lead (timestamp + content hash)."""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT created_at, LEFT(content, 100)
        FROM messages
        WHERE lead_id = %s
    """, (lead_id,))
    fingerprints = set()
    for row in cursor.fetchall():
        created_at, content_prefix = row
        # Create fingerprint: timestamp (rounded to second) + content prefix
        ts_str = created_at.strftime('%Y-%m-%d %H:%M:%S') if created_at else ''
        fingerprints.add(f"{ts_str}|{content_prefix}")
    cursor.close()
    return fingerprints


def create_lead(conn, username: str, full_name: str) -> str:
    """Create a new lead and return its ID."""
    lead_id = str(uuid.uuid4())
    platform_user_id = f"restored_{username}_{int(datetime.now().timestamp())}"

    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO leads (id, creator_id, platform, platform_user_id, username, full_name, status, first_contact_at, last_contact_at)
        VALUES (%s, %s, 'instagram', %s, %s, %s, 'active', NOW(), NOW())
        RETURNING id
    """, (lead_id, CREATOR_ID, platform_user_id, username, full_name))
    result = cursor.fetchone()
    cursor.close()
    return result[0]


def import_messages(conn, lead_id: str, messages: list, existing_fingerprints: set) -> tuple:
    """Import messages for a lead. Returns (imported, skipped) counts."""
    if not messages:
        return 0, 0

    imported = 0
    skipped = 0
    messages_to_insert = []

    for msg in messages:
        content = msg.get('content', '')
        timestamp_str = msg.get('timestamp', '')
        sender = msg.get('sender', '')
        intent = msg.get('intent')
        status = msg.get('status', 'sent')

        # Parse timestamp
        try:
            if timestamp_str:
                created_at = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                created_at = datetime.now()
        except Exception:
            created_at = datetime.now()

        # Create fingerprint to check for duplicates
        ts_str = created_at.strftime('%Y-%m-%d %H:%M:%S')
        fingerprint = f"{ts_str}|{content[:100]}"

        if fingerprint in existing_fingerprints:
            skipped += 1
            continue

        # Map sender to role
        role = 'assistant' if sender == 'stefan' else 'user'

        # Prepare message for insert
        msg_id = str(uuid.uuid4())
        messages_to_insert.append((
            msg_id,
            lead_id,
            role,
            content,
            intent,
            created_at,
            status
        ))
        existing_fingerprints.add(fingerprint)
        imported += 1

    # Batch insert
    if messages_to_insert:
        cursor = conn.cursor()
        execute_values(cursor, """
            INSERT INTO messages (id, lead_id, role, content, intent, created_at, status)
            VALUES %s
            ON CONFLICT DO NOTHING
        """, messages_to_insert)
        cursor.close()

    return imported, skipped


def update_lead_timestamps(conn, lead_id: str):
    """Update lead's first_contact_at and last_contact_at based on messages."""
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE leads SET
            first_contact_at = COALESCE(
                (SELECT MIN(created_at) FROM messages WHERE lead_id = %s),
                first_contact_at
            ),
            last_contact_at = COALESCE(
                (SELECT MAX(created_at) FROM messages WHERE lead_id = %s),
                last_contact_at
            ),
            updated_at = NOW()
        WHERE id = %s
    """, (lead_id, lead_id, lead_id))
    cursor.close()


def main():
    print("=" * 60)
    print("MESSAGE RESTORATION FROM JSON BACKUP")
    print("=" * 60)

    # Load backup
    data = load_backup_data()
    conversations = data.get('conversations', [])

    # Connect to database
    print(f"\nConnecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False

    # Get existing leads
    existing_leads = get_existing_leads(conn)

    # Statistics
    stats = {
        'leads_updated': 0,
        'leads_created': 0,
        'messages_imported': 0,
        'messages_skipped': 0,
        'conversations_processed': 0,
        'errors': 0
    }

    try:
        batch_size = 50
        for i, conv in enumerate(conversations):
            username = conv.get('lead_username', '').lower()
            full_name = conv.get('lead_name', '')
            messages = conv.get('messages', [])

            if not username:
                print(f"  [SKIP] Conversation {i+1}: no username")
                continue

            # Find or create lead
            if username in existing_leads:
                lead_id = existing_leads[username]['id']
                stats['leads_updated'] += 1
            else:
                # Create new lead
                lead_id = create_lead(conn, username, full_name)
                existing_leads[username] = {'id': lead_id, 'username': username}
                stats['leads_created'] += 1
                print(f"  [NEW] Created lead: {username}")

            # Get existing messages to avoid duplicates
            existing_fingerprints = get_existing_messages(conn, lead_id)

            # Import messages
            imported, skipped = import_messages(conn, lead_id, messages, existing_fingerprints)
            stats['messages_imported'] += imported
            stats['messages_skipped'] += skipped

            # Update timestamps
            if imported > 0:
                update_lead_timestamps(conn, lead_id)

            stats['conversations_processed'] += 1

            # Progress
            if (i + 1) % 10 == 0:
                print(f"  Progress: {i+1}/{len(conversations)} conversations, {stats['messages_imported']} imported, {stats['messages_skipped']} skipped")

            # Commit in batches
            if (i + 1) % batch_size == 0:
                conn.commit()
                print(f"  [COMMIT] Batch {(i+1)//batch_size} committed")

        # Final commit
        conn.commit()
        print("\n[COMMIT] Final batch committed")

    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] {e}")
        stats['errors'] += 1
        raise
    finally:
        conn.close()

    # Print summary
    print("\n" + "=" * 60)
    print("RESTORATION SUMMARY")
    print("=" * 60)
    print(f"Conversations processed: {stats['conversations_processed']}")
    print(f"Leads updated:          {stats['leads_updated']}")
    print(f"Leads created:          {stats['leads_created']}")
    print(f"Messages imported:      {stats['messages_imported']}")
    print(f"Messages skipped (dup): {stats['messages_skipped']}")
    print(f"Errors:                 {stats['errors']}")
    print("=" * 60)

    return stats


if __name__ == "__main__":
    main()
