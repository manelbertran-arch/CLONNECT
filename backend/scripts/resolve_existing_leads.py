"""
One-time migration script: create UnifiedLeads for all existing leads.

Steps:
  1. For each creator, get all leads
  2. Group leads by exact full_name (case-insensitive) across platforms
  3. For groups with >1 lead: create a shared UnifiedLead
  4. For single leads: create an individual UnifiedLead
  5. Link all leads via unified_lead_id

Run once after deploying migration 018:
    python -m scripts.resolve_existing_leads
"""

import logging
import os
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone

# Add parent to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

PLATFORM_PRIORITY = {"instagram": 0, "telegram": 1, "whatsapp": 2}


def normalise_name(name):
    if not name:
        return ""
    return " ".join(name.lower().strip().split())


def normalise_phone(phone):
    if not phone:
        return ""
    import re
    return re.sub(r"[^\d+]", "", phone)


def run():
    from api.database import SessionLocal
    from api.models import Creator, Lead, UnifiedLead

    session = SessionLocal()
    if not session:
        logger.error("No database session")
        return

    try:
        creators = session.query(Creator).all()
        logger.info(f"Processing {len(creators)} creators")

        total_unified = 0
        total_merged = 0

        for creator in creators:
            leads = (
                session.query(Lead)
                .filter(Lead.creator_id == creator.id, Lead.unified_lead_id.is_(None))
                .all()
            )
            if not leads:
                continue

            logger.info(f"[{creator.name}] {len(leads)} unlinked leads")

            # Group by normalised name (cross-platform only)
            name_groups = defaultdict(list)
            for lead in leads:
                name = normalise_name(lead.full_name)
                if name and len(name) >= 3:
                    name_groups[name].append(lead)

            # Also group by email
            email_groups = defaultdict(list)
            for lead in leads:
                if lead.email:
                    email_groups[lead.email.lower().strip()].append(lead)

            # Also group by phone (WhatsApp ID)
            phone_groups = defaultdict(list)
            for lead in leads:
                phone = None
                if lead.platform == "whatsapp" and lead.platform_user_id:
                    raw = lead.platform_user_id.replace("wa_", "")
                    if raw.isdigit():
                        phone = raw
                elif lead.phone:
                    phone = normalise_phone(lead.phone)
                if phone:
                    phone_groups[phone].append(lead)

            # Merge groups: combine name/email/phone groups via connected components
            lead_to_group = {}  # lead.id -> group_id
            group_leads = defaultdict(set)  # group_id -> set of lead ids
            next_group = 0

            def union(lead_ids):
                nonlocal next_group
                existing_groups = {lead_to_group[lid] for lid in lead_ids if lid in lead_to_group}
                if existing_groups:
                    target = min(existing_groups)
                    for gid in existing_groups:
                        if gid != target:
                            for lid in group_leads[gid]:
                                lead_to_group[lid] = target
                                group_leads[target].add(lid)
                            del group_leads[gid]
                else:
                    target = next_group
                    next_group += 1
                for lid in lead_ids:
                    lead_to_group[lid] = target
                    group_leads[target].add(lid)

            # Process name groups (only cross-platform matches)
            for name, group in name_groups.items():
                platforms = {l.platform for l in group}
                if len(platforms) > 1:
                    union([str(l.id) for l in group])

            # Process email groups
            for email, group in email_groups.items():
                if len(group) > 1:
                    union([str(l.id) for l in group])

            # Process phone groups
            for phone, group in phone_groups.items():
                if len(group) > 1:
                    union([str(l.id) for l in group])

            # Assign remaining ungrouped leads their own group
            for lead in leads:
                lid = str(lead.id)
                if lid not in lead_to_group:
                    lead_to_group[lid] = next_group
                    group_leads[next_group] = {lid}
                    next_group += 1

            # Create UnifiedLeads
            lead_by_id = {str(l.id): l for l in leads}

            for gid, member_ids in group_leads.items():
                members = [lead_by_id[lid] for lid in member_ids if lid in lead_by_id]
                if not members:
                    continue

                members_sorted = sorted(members, key=lambda l: PLATFORM_PRIORITY.get(l.platform, 99))

                # Best display name
                display_name = None
                for l in members_sorted:
                    if l.full_name and len(l.full_name.strip()) > 1:
                        display_name = l.full_name
                        break
                if not display_name:
                    display_name = members[0].username or members[0].platform_user_id

                # Best profile pic
                profile_pic_url = None
                for l in members_sorted:
                    if l.profile_pic_url:
                        profile_pic_url = l.profile_pic_url
                        break

                # Email
                email = None
                for l in members:
                    if l.email:
                        email = l.email.lower().strip()
                        break

                # Phone
                phone = None
                for l in members:
                    if l.platform == "whatsapp" and l.platform_user_id:
                        raw = l.platform_user_id.replace("wa_", "")
                        if raw.isdigit():
                            phone = raw
                            break
                if not phone:
                    for l in members:
                        if l.phone:
                            phone = normalise_phone(l.phone)
                            break

                # Score, status, timestamps
                max_score = max((float(l.score or 0) for l in members), default=0)
                status_priority = {"cliente": 0, "caliente": 1, "interesado": 2, "nuevo": 3, "fantasma": 4}
                best_status = min(members, key=lambda l: status_priority.get(l.status or "nuevo", 99))

                first_dates = [l.first_contact_at for l in members if l.first_contact_at]
                last_dates = [l.last_contact_at for l in members if l.last_contact_at]

                unified = UnifiedLead(
                    id=uuid.uuid4(),
                    creator_id=creator.id,
                    display_name=display_name,
                    email=email,
                    phone=phone,
                    profile_pic_url=profile_pic_url,
                    unified_score=max_score,
                    status=best_status.status or "nuevo",
                    first_contact_at=min(first_dates) if first_dates else None,
                    last_contact_at=max(last_dates) if last_dates else None,
                    merge_history=[{
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "tier": "MIGRATION",
                        "signal": "initial_backfill",
                        "leads": [str(l.id) for l in members],
                        "platforms": list({l.platform for l in members}),
                    }],
                )
                session.add(unified)
                session.flush()

                for l in members:
                    l.unified_lead_id = unified.id

                total_unified += 1
                if len(members) > 1:
                    total_merged += 1
                    platforms = ", ".join(sorted({l.platform for l in members}))
                    logger.info(
                        f"  MERGED {len(members)} leads -> '{display_name}' ({platforms})"
                    )

            session.commit()
            logger.info(f"[{creator.name}] Created {total_unified} unified leads ({total_merged} multi-channel)")

        logger.info(f"DONE: {total_unified} unified leads, {total_merged} cross-platform merges")

    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    run()
