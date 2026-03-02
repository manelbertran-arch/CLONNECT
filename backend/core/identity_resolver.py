"""
Cross-platform identity resolution system.

Detects when leads from different channels (Instagram, WhatsApp, Telegram)
belong to the same real person and unifies them under a single UnifiedLead.

Matching tiers:
  TIER 1 (auto-merge): exact email or phone match
  TIER 2 (auto-merge): exact full name or cross-platform username match
  TIER 3 (suggest only): partial name or fuzzy match — logged but not auto-merged
"""

import logging
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Contact signal patterns
# ---------------------------------------------------------------------------

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_PATTERN = re.compile(r"\+?\d{1,3}[\s.\-]?\(?\d{1,4}\)?[\s.\-]?\d{3,12}")
INSTAGRAM_HANDLE_PATTERN = re.compile(r"@([a-zA-Z0-9_.]{1,30})")


def extract_contact_signals(text: str) -> Dict[str, str]:
    """
    Extract email, phone and Instagram handle from a user message.

    Returns dict with keys: email, phone, instagram_handle (only present if found).
    """
    if not text:
        return {}

    signals: Dict[str, str] = {}

    email_match = EMAIL_PATTERN.search(text)
    if email_match:
        signals["email"] = email_match.group(0).lower()

    phone_match = PHONE_PATTERN.search(text)
    if phone_match:
        raw = re.sub(r"[\s.\-()]", "", phone_match.group(0))
        if len(raw) >= 7:
            signals["phone"] = raw

    ig_match = INSTAGRAM_HANDLE_PATTERN.search(text)
    if ig_match:
        handle = ig_match.group(1).lower()
        # Exclude common false positives
        if handle not in {"gmail", "hotmail", "yahoo", "outlook", "icloud"}:
            signals["instagram_handle"] = handle

    return signals


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _normalise_name(name: Optional[str]) -> str:
    """Lowercase, strip, collapse whitespace."""
    if not name:
        return ""
    return " ".join(name.lower().strip().split())


def _normalise_phone(phone: Optional[str]) -> str:
    """Strip non-digit chars (except leading +)."""
    if not phone:
        return ""
    digits = re.sub(r"[^\d+]", "", phone)
    return digits


def _levenshtein(a: str, b: str) -> int:
    """Simple Levenshtein distance for short strings."""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
        prev = curr
    return prev[-1]


# ---------------------------------------------------------------------------
# Core resolver
# ---------------------------------------------------------------------------

PLATFORM_PRIORITY = {"instagram": 0, "telegram": 1, "whatsapp": 2}


async def resolve_identity(
    creator_id: str,
    lead_id: str,
    platform: str,
) -> Optional[str]:
    """
    Find or create a UnifiedLead for the given channel lead.

    Called asynchronously after processing a message — never blocks the response.
    Returns the unified_lead_id or None on failure.
    """
    try:
        from api.database import SessionLocal
        from api.models import Lead, UnifiedLead

        session = SessionLocal()
        if not session:
            return None

        try:
            lead = session.query(Lead).filter_by(id=lead_id).first()
            if not lead:
                return None

            creator_uuid = lead.creator_id

            # Already linked?
            if lead.unified_lead_id:
                unified = session.query(UnifiedLead).filter_by(id=lead.unified_lead_id).first()
                if unified:
                    _refresh_unified(unified, session, creator_uuid)
                    session.commit()
                    return str(unified.id)

            # TIER 1: email match
            unified = _match_by_email(session, creator_uuid, lead)
            if unified:
                _link_and_log(session, lead, unified, "TIER_1", "email")
                return str(unified.id)

            # TIER 1: phone match
            unified = _match_by_phone(session, creator_uuid, lead, platform)
            if unified:
                _link_and_log(session, lead, unified, "TIER_1", "phone")
                return str(unified.id)

            # TIER 2: exact name match
            unified = _match_by_exact_name(session, creator_uuid, lead)
            if unified:
                _link_and_log(session, lead, unified, "TIER_2", "exact_name")
                return str(unified.id)

            # TIER 2: cross-platform username
            unified = _match_by_username(session, creator_uuid, lead)
            if unified:
                _link_and_log(session, lead, unified, "TIER_2", "username")
                return str(unified.id)

            # TIER 3: fuzzy name (log only, don't auto-merge)
            _check_fuzzy_name(session, creator_uuid, lead)

            # No match — create new UnifiedLead
            unified = _create_unified(session, lead, creator_uuid)
            _link_and_log(session, lead, unified, "NEW", "created")
            return str(unified.id)

        finally:
            session.close()

    except Exception as e:
        logger.error(f"[IDENTITY] resolve_identity failed for lead {lead_id}: {e}")
        return None


# ---------------------------------------------------------------------------
# Matching functions
# ---------------------------------------------------------------------------

def _match_by_email(session, creator_uuid, lead) -> Optional[object]:
    """TIER 1: match by exact email."""
    from api.models import Lead, UnifiedLead

    if not lead.email:
        return None

    email_lower = lead.email.lower().strip()

    # Check UnifiedLead table
    unified = (
        session.query(UnifiedLead)
        .filter(UnifiedLead.creator_id == creator_uuid, UnifiedLead.email == email_lower)
        .first()
    )
    if unified:
        return unified

    # Check other leads with same email
    other = (
        session.query(Lead)
        .filter(
            Lead.creator_id == creator_uuid,
            Lead.email == email_lower,
            Lead.id != lead.id,
            Lead.unified_lead_id.isnot(None),
        )
        .first()
    )
    if other and other.unified_lead_id:
        return session.query(UnifiedLead).filter_by(id=other.unified_lead_id).first()

    return None


def _match_by_phone(session, creator_uuid, lead, platform: str) -> Optional[object]:
    """TIER 1: match by phone number."""
    from api.models import Lead, UnifiedLead

    phone = None

    # WhatsApp leads have phone embedded in platform_user_id (wa_34612345678)
    if platform == "whatsapp" and lead.platform_user_id:
        raw = lead.platform_user_id.replace("wa_", "")
        if raw.isdigit() and len(raw) >= 7:
            phone = raw
    elif lead.phone:
        phone = _normalise_phone(lead.phone)

    if not phone:
        return None

    # Check UnifiedLead table
    unified = (
        session.query(UnifiedLead)
        .filter(UnifiedLead.creator_id == creator_uuid, UnifiedLead.phone == phone)
        .first()
    )
    if unified:
        return unified

    # Check other WhatsApp leads with matching phone in platform_user_id
    other = (
        session.query(Lead)
        .filter(
            Lead.creator_id == creator_uuid,
            Lead.id != lead.id,
            Lead.unified_lead_id.isnot(None),
            Lead.platform_user_id.in_([f"wa_{phone}", phone]),
        )
        .first()
    )
    if other and other.unified_lead_id:
        return session.query(UnifiedLead).filter_by(id=other.unified_lead_id).first()

    # Check leads with phone field
    other = (
        session.query(Lead)
        .filter(
            Lead.creator_id == creator_uuid,
            Lead.id != lead.id,
            Lead.unified_lead_id.isnot(None),
            Lead.phone == phone,
        )
        .first()
    )
    if other and other.unified_lead_id:
        return session.query(UnifiedLead).filter_by(id=other.unified_lead_id).first()

    return None


def _match_by_exact_name(session, creator_uuid, lead) -> Optional[object]:
    """TIER 2: exact full name match (case-insensitive)."""
    from sqlalchemy import func
    from api.models import Lead, UnifiedLead

    name = _normalise_name(lead.full_name)
    if not name or len(name) < 3:
        return None

    # SQL-level case-insensitive exact match across different platforms
    other = (
        session.query(Lead)
        .filter(
            Lead.creator_id == creator_uuid,
            Lead.id != lead.id,
            Lead.platform != lead.platform,
            Lead.unified_lead_id.isnot(None),
            func.lower(func.trim(Lead.full_name)) == name,
        )
        .limit(10)
        .first()
    )
    if other:
        unified = session.query(UnifiedLead).filter_by(id=other.unified_lead_id).first()
        if unified:
            return unified

    return None


def _match_by_username(session, creator_uuid, lead) -> Optional[object]:
    """TIER 2: cross-platform username match."""
    from sqlalchemy import func
    from api.models import Lead, UnifiedLead

    username = (lead.username or "").lower().strip().lstrip("@")
    if not username or len(username) < 3:
        return None

    # SQL-level case-insensitive username match across different platforms
    other = (
        session.query(Lead)
        .filter(
            Lead.creator_id == creator_uuid,
            Lead.id != lead.id,
            Lead.platform != lead.platform,
            Lead.unified_lead_id.isnot(None),
            func.lower(func.trim(Lead.username)) == username,
        )
        .limit(10)
        .first()
    )
    if other:
        unified = session.query(UnifiedLead).filter_by(id=other.unified_lead_id).first()
        if unified:
            return unified

    return None


def _check_fuzzy_name(session, creator_uuid, lead) -> None:
    """TIER 3: log fuzzy name matches for manual review (no auto-merge)."""
    from api.models import Lead

    name = _normalise_name(lead.full_name)
    if not name or len(name) < 4:
        return

    others = (
        session.query(Lead)
        .filter(
            Lead.creator_id == creator_uuid,
            Lead.id != lead.id,
            Lead.platform != lead.platform,
            Lead.full_name.isnot(None),
        )
        .limit(100)
        .all()
    )
    for o in others:
        other_name = _normalise_name(o.full_name)
        if not other_name or other_name == name:
            continue

        # Partial containment
        if name in other_name or other_name in name:
            logger.info(
                f"[IDENTITY] TIER_3 partial name match: "
                f"'{lead.full_name}' ({lead.platform}:{lead.platform_user_id}) "
                f"~ '{o.full_name}' ({o.platform}:{o.platform_user_id})"
            )
            continue

        # Levenshtein
        if len(name) > 4 and _levenshtein(name, other_name) <= 2:
            logger.info(
                f"[IDENTITY] TIER_3 fuzzy name match: "
                f"'{lead.full_name}' ({lead.platform}:{lead.platform_user_id}) "
                f"~ '{o.full_name}' ({o.platform}:{o.platform_user_id})"
            )


# ---------------------------------------------------------------------------
# Create / link helpers
# ---------------------------------------------------------------------------

def _create_unified(session, lead, creator_uuid) -> object:
    """Create a new UnifiedLead from a channel lead."""
    import uuid as _uuid
    from api.models import UnifiedLead

    phone = None
    if lead.platform == "whatsapp" and lead.platform_user_id:
        raw = lead.platform_user_id.replace("wa_", "")
        if raw.isdigit():
            phone = raw
    phone = phone or _normalise_phone(lead.phone) or None

    unified = UnifiedLead(
        id=_uuid.uuid4(),
        creator_id=creator_uuid,
        display_name=lead.full_name or lead.username or lead.platform_user_id,
        email=(lead.email or "").lower().strip() or None,
        phone=phone,
        profile_pic_url=lead.profile_pic_url,
        unified_score=float(lead.score or 0),
        status=lead.status or "nuevo",
        first_contact_at=lead.first_contact_at,
        last_contact_at=lead.last_contact_at,
        merge_history=[],
    )
    session.add(unified)
    session.flush()
    return unified


def _link_and_log(session, lead, unified, tier: str, signal: str) -> None:
    """Link a lead to a UnifiedLead and log the merge."""
    from datetime import datetime, timezone

    lead.unified_lead_id = unified.id

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tier": tier,
        "signal": signal,
        "lead_id": str(lead.id),
        "platform": lead.platform,
        "platform_user_id": lead.platform_user_id,
    }

    history = list(unified.merge_history or [])
    history.append(entry)
    unified.merge_history = history

    _refresh_unified(unified, session, unified.creator_id)
    session.commit()

    logger.info(
        f"[IDENTITY] {tier} merge: {lead.platform}:{lead.platform_user_id} "
        f"-> unified {unified.id} (signal={signal})"
    )


def _refresh_unified(unified, session, creator_uuid) -> None:
    """Recalculate unified fields from all linked leads."""
    from api.models import Lead

    leads = (
        session.query(Lead)
        .filter(Lead.unified_lead_id == unified.id)
        .limit(100)
        .all()
    )
    if not leads:
        return

    # Sort by platform priority for name/pic selection
    leads_sorted = sorted(leads, key=lambda l: PLATFORM_PRIORITY.get(l.platform, 99))

    # Best display name: prefer Instagram > Telegram > WhatsApp
    for l in leads_sorted:
        if l.full_name and len(l.full_name.strip()) > 1:
            unified.display_name = l.full_name
            break

    # Best profile pic: prefer Instagram > Telegram (WhatsApp never has one)
    for l in leads_sorted:
        if l.profile_pic_url:
            unified.profile_pic_url = l.profile_pic_url
            break

    # Email: first non-empty
    for l in leads_sorted:
        if l.email:
            unified.email = l.email.lower().strip()
            break

    # Phone: WhatsApp ID or captured phone
    for l in leads:
        if l.platform == "whatsapp" and l.platform_user_id:
            raw = l.platform_user_id.replace("wa_", "")
            if raw.isdigit():
                unified.phone = raw
                break
    if not unified.phone:
        for l in leads:
            if l.phone:
                unified.phone = _normalise_phone(l.phone)
                break

    # Score: max across all channels
    unified.unified_score = max((float(l.score or 0) for l in leads), default=0)

    # Status: best status (cliente > caliente > interesado > nuevo)
    status_priority = {"cliente": 0, "caliente": 1, "interesado": 2, "nuevo": 3, "fantasma": 4}
    best = min(leads, key=lambda l: status_priority.get(l.status or "nuevo", 99))
    unified.status = best.status or "nuevo"

    # Timestamps
    first_dates = [l.first_contact_at for l in leads if l.first_contact_at]
    last_dates = [l.last_contact_at for l in leads if l.last_contact_at]
    if first_dates:
        unified.first_contact_at = min(first_dates)
    if last_dates:
        unified.last_contact_at = max(last_dates)


# ---------------------------------------------------------------------------
# Manual merge / unmerge
# ---------------------------------------------------------------------------

async def manual_merge(creator_id: str, lead_ids: List[str]) -> Optional[str]:
    """
    Manually merge multiple leads into a single UnifiedLead.
    Returns the unified_lead_id or None on failure.
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, UnifiedLead

        session = SessionLocal()
        if not session:
            return None

        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return None

            leads = (
                session.query(Lead)
                .filter(Lead.creator_id == creator.id, Lead.id.in_(lead_ids))
                .limit(50)
                .all()
            )
            if len(leads) < 2:
                return None

            # Use existing UnifiedLead if any lead is already linked
            unified = None
            for l in leads:
                if l.unified_lead_id:
                    unified = session.query(UnifiedLead).filter_by(id=l.unified_lead_id).first()
                    if unified:
                        break

            if not unified:
                unified = _create_unified(session, leads[0], creator.id)

            for l in leads:
                if l.unified_lead_id != unified.id:
                    _link_and_log(session, l, unified, "MANUAL", "manual_merge")

            return str(unified.id)

        finally:
            session.close()

    except Exception as e:
        logger.error(f"[IDENTITY] manual_merge failed: {e}")
        return None


async def manual_unmerge(creator_id: str, unified_lead_id: str, lead_id: str) -> bool:
    """
    Remove a single lead from a UnifiedLead group.
    Creates a new individual UnifiedLead for the separated lead.
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, UnifiedLead

        session = SessionLocal()
        if not session:
            return False

        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return False

            lead = (
                session.query(Lead)
                .filter(Lead.id == lead_id, Lead.creator_id == creator.id)
                .first()
            )
            if not lead or str(lead.unified_lead_id) != unified_lead_id:
                return False

            # Create new individual UnifiedLead
            new_unified = _create_unified(session, lead, creator.id)
            lead.unified_lead_id = new_unified.id
            session.commit()

            # Refresh the old unified lead
            old_unified = session.query(UnifiedLead).filter_by(id=unified_lead_id).first()
            if old_unified:
                remaining = session.query(Lead).filter(Lead.unified_lead_id == old_unified.id).count()
                if remaining == 0:
                    session.delete(old_unified)
                    session.commit()
                else:
                    _refresh_unified(old_unified, session, creator.id)
                    session.commit()

            logger.info(
                f"[IDENTITY] UNMERGE: lead {lead_id} ({lead.platform}) "
                f"separated from unified {unified_lead_id}"
            )
            return True

        finally:
            session.close()

    except Exception as e:
        logger.error(f"[IDENTITY] manual_unmerge failed: {e}")
        return False
