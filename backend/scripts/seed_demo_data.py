#!/usr/bin/env python3
"""
Seed Demo Data Script

SPRINT4: Populates database with realistic demo data for testing and demos.
Idempotent - can be run multiple times safely.

Usage:
    cd backend
    python scripts/seed_demo_data.py
"""
import os
import sys
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import demo data modules
from scripts.demo_data.config import (
    CREATOR_ID,
    SEGMENT_DISTRIBUTION,
    PRODUCTS,
    BOOKING_LINKS,
)
from scripts.demo_data.names import (
    get_random_name,
    generate_username,
    generate_email,
    generate_phone,
    get_assigned_to,
)
from scripts.demo_data.interests import (
    get_random_interests,
    get_random_objections,
    get_arguments_for_objections,
    get_notes_for_segment,
    get_profile_pic_url,
    get_user_context,
    TOPICS,
)
from scripts.demo_data.messages import (
    get_messages_for_segment,
    get_last_message_for_segment,
    BOT_RESPONSES,
    COMPETITOR_MENTIONS,
    TRENDING_MESSAGES,
    CONTENT_QUESTIONS,
)
from scripts.demo_data.interests import COMPETITORS, TRENDING_TERMS, get_interests_with_weights

# Database imports
from api.database import SessionLocal, engine
from api.models import (
    Creator,
    Lead,
    LeadActivity,
    LeadTask,
    Message,
    Product,
    CalendarBooking,
    BookingLink,
    FollowerMemoryDB,
    UserProfileDB,
    ConversationStateDB,
)
from core.analytics.analytics_manager import get_analytics_manager, EventType


def log(msg: str):
    """Simple logging with timestamp"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def get_or_create_creator(db) -> tuple[uuid.UUID, str]:
    """
    Get existing creator or create fitpack_global.
    Returns (creator_uuid, creator_name_string)
    """
    # Try to find existing creator
    creator = db.query(Creator).filter(Creator.name == CREATOR_ID).first()

    if creator:
        log(f"Found existing creator: {creator.name} ({creator.id})")
        return creator.id, CREATOR_ID

    # Try "manel" as fallback
    creator = db.query(Creator).filter(Creator.name == "manel").first()
    if creator:
        log(f"Using existing creator: {creator.name} ({creator.id})")
        return creator.id, creator.name

    # Create new creator
    creator = Creator(
        id=uuid.uuid4(),
        name=CREATOR_ID,
        email=f"{CREATOR_ID}@demo.clonnect.com",
        clone_name="FitPack",
        bot_active=True,
    )
    db.add(creator)
    db.commit()
    log(f"Created new creator: {creator.name} ({creator.id})")
    return creator.id, CREATOR_ID


def clear_demo_data(db, creator_uuid: uuid.UUID, creator_name: str):
    """Clear existing demo data for creator"""
    log(f"Clearing existing data for {creator_name} ({creator_uuid})...")

    # Get leads for this creator to delete messages and activities
    # Lead uses UUID for creator_id
    leads = db.query(Lead).filter(Lead.creator_id == creator_uuid).all()
    lead_ids = [lead.id for lead in leads]

    # Delete in order (foreign key constraints)
    if lead_ids:
        deleted_activities = db.query(LeadActivity).filter(LeadActivity.lead_id.in_(lead_ids)).delete(synchronize_session=False)
        log(f"  Deleted {deleted_activities} lead activities")
        deleted_tasks = db.query(LeadTask).filter(LeadTask.lead_id.in_(lead_ids)).delete(synchronize_session=False)
        log(f"  Deleted {deleted_tasks} lead tasks")
        deleted_msgs = db.query(Message).filter(Message.lead_id.in_(lead_ids)).delete(synchronize_session=False)
        log(f"  Deleted {deleted_msgs} messages")

    deleted_leads = db.query(Lead).filter(Lead.creator_id == creator_uuid).delete(synchronize_session=False)
    log(f"  Deleted {deleted_leads} leads")

    # These tables use string for creator_id
    deleted_fm = db.query(FollowerMemoryDB).filter(FollowerMemoryDB.creator_id == creator_name).delete(synchronize_session=False)
    log(f"  Deleted {deleted_fm} follower memories")

    deleted_up = db.query(UserProfileDB).filter(UserProfileDB.creator_id == creator_name).delete(synchronize_session=False)
    log(f"  Deleted {deleted_up} user profiles")

    deleted_cs = db.query(ConversationStateDB).filter(ConversationStateDB.creator_id == creator_name).delete(synchronize_session=False)
    log(f"  Deleted {deleted_cs} conversation states")

    deleted_bookings = db.query(CalendarBooking).filter(CalendarBooking.creator_id == creator_name).delete(synchronize_session=False)
    log(f"  Deleted {deleted_bookings} bookings")

    # Product uses UUID for creator_id
    deleted_products = db.query(Product).filter(Product.creator_id == creator_uuid).delete(synchronize_session=False)
    log(f"  Deleted {deleted_products} products")

    deleted_links = db.query(BookingLink).filter(BookingLink.creator_id == creator_name).delete(synchronize_session=False)
    log(f"  Deleted {deleted_links} booking links")

    db.commit()
    log("  Done clearing data")


def create_products(db, creator_uuid: uuid.UUID) -> list:
    """Create products for the creator"""
    log("Creating products...")
    created = []

    for prod_data in PRODUCTS:
        product = Product(
            id=uuid.uuid4(),
            creator_id=creator_uuid,  # UUID type
            name=prod_data["name"],
            description=prod_data["description"],
            price=prod_data["price"],
            currency=prod_data["currency"],
            category=prod_data["category"],
            is_active=prod_data["is_active"],
        )
        db.add(product)
        created.append(product)

    db.commit()
    log(f"  Created {len(created)} products")
    return created


def create_booking_links(db, creator_name: str) -> list:
    """Create booking links for the creator"""
    log("Creating booking links...")
    created = []

    for link_data in BOOKING_LINKS:
        link = BookingLink(
            id=uuid.uuid4(),
            creator_id=creator_name,  # String type
            title=link_data["title"],
            meeting_type=link_data["meeting_type"],
            duration_minutes=link_data["duration_minutes"],
            platform=link_data["platform"],
            price=link_data["price"],
            url=f"https://calendly.com/fitpack/{link_data['meeting_type']}",
            is_active=True,
        )
        db.add(link)
        created.append(link)

    db.commit()
    log(f"  Created {len(created)} booking links")
    return created


def create_followers_and_leads(db, products: list, creator_uuid: uuid.UUID, creator_name: str) -> tuple[list, list]:
    """Create followers and leads based on segment distribution"""
    log("Creating followers and leads...")

    followers = []
    leads = []
    all_messages = []

    follower_index = 0
    now = datetime.now(timezone.utc)

    for segment, count in SEGMENT_DISTRIBUTION.items():
        log(f"  Creating {count} {segment} followers...")

        for i in range(count):
            # Generate identity
            first_name, full_name = get_random_name()
            username = generate_username(first_name, follower_index)
            follower_id = f"ig_{random.randint(1000000000, 9999999999)}"

            # Calculate dates based on segment
            if segment == "new":
                first_contact = now - timedelta(days=random.randint(0, 3))
                last_contact = now - timedelta(hours=random.randint(0, 24))
                total_messages = random.randint(1, 3)
            elif segment == "ghost":
                first_contact = now - timedelta(days=random.randint(14, 60))
                last_contact = now - timedelta(days=random.randint(7, 30))
                total_messages = random.randint(3, 8)
            elif segment == "customer":
                first_contact = now - timedelta(days=random.randint(30, 90))
                last_contact = now - timedelta(days=random.randint(0, 14))
                total_messages = random.randint(15, 40)
            else:
                first_contact = now - timedelta(days=random.randint(7, 45))
                last_contact = now - timedelta(hours=random.randint(1, 72))
                total_messages = random.randint(5, 25)

            # Generate interests
            interests = get_random_interests(random.randint(2, 5))

            # Generate products discussed
            products_discussed = []
            if segment in ["hot_lead", "warm_lead", "price_objector", "customer"]:
                products_discussed = [random.choice(products).name for _ in range(random.randint(1, 2))]

            # Calculate purchase intent based on segment
            intent_ranges = {
                "hot_lead": (0.75, 0.95),
                "warm_lead": (0.45, 0.70),
                "price_objector": (0.35, 0.55),
                "time_objector": (0.30, 0.50),
                "ghost": (0.10, 0.30),
                "engaged_fan": (0.20, 0.45),
                "new": (0.15, 0.35),
                "customer": (0.05, 0.20),  # Already bought
            }
            min_intent, max_intent = intent_ranges.get(segment, (0.2, 0.5))
            purchase_intent = round(random.uniform(min_intent, max_intent), 2)

            # Generate objections for objector segments (simple string list for aggregation)
            objections_raised = []
            objections_handled = []
            if segment == "price_objector":
                objections_raised = ["precio"]
            elif segment == "time_objector":
                objections_raised = ["tiempo"]
            elif segment == "customer":
                # Customers had objections but they were resolved
                objections_raised = random.sample(["precio", "tiempo", "duda"], k=random.randint(1, 2))
                objections_handled = objections_raised.copy()  # All resolved

            # Determine status
            status_map = {
                "hot_lead": "caliente",
                "warm_lead": "interesado",
                "price_objector": "interesado",
                "time_objector": "interesado",
                "ghost": "fantasma",
                "engaged_fan": "nuevo",
                "new": "nuevo",
                "customer": "cliente",
            }
            status = status_map.get(segment, "nuevo")

            # Generate conversation FIRST so we can populate last_messages
            conversation = get_messages_for_segment(segment, min(total_messages, 12))
            last_role, last_content = get_last_message_for_segment(segment)
            if conversation:
                conversation[-1] = {"role": last_role, "content": last_content}

            # Add special messages for Audience Intelligence (higher probabilities)
            # 40% chance for competitor @mentions (for /audiencia/competition)
            if random.random() < 0.40 and segment not in ["new"]:
                conversation.insert(
                    random.randint(1, max(1, len(conversation) - 1)),
                    {"role": "user", "content": random.choice(COMPETITOR_MENTIONS)}
                )
            # 35% chance for trending terms (for /audiencia/trends)
            if random.random() < 0.35:
                conversation.insert(
                    random.randint(1, max(1, len(conversation) - 1)),
                    {"role": "user", "content": random.choice(TRENDING_MESSAGES)}
                )
            # 40% chance for content questions (for /audiencia/content-requests)
            if random.random() < 0.40:
                conversation.insert(
                    random.randint(1, max(1, len(conversation) - 1)),
                    {"role": "user", "content": random.choice(CONTENT_QUESTIONS)}
                )

            # Get last 10 messages for last_messages field
            last_messages = conversation[-10:] if len(conversation) > 10 else conversation

            # Get arguments used for handling objections
            arguments_used = get_arguments_for_objections(objections_handled) if objections_handled else []

            # Alternative contact info (some customers provided WhatsApp/Telegram)
            has_alt_contact = random.random() < (0.5 if segment == "customer" else 0.15)
            alt_contact = ""
            alt_contact_type = ""
            contact_requested = False
            if has_alt_contact:
                alt_contact_type = random.choice(["whatsapp", "telegram"])
                alt_contact = generate_phone() if alt_contact_type == "whatsapp" else f"@{username}"
                contact_requested = True

            # Greeting styles used
            greeting_styles = ["casual", "formal", "enthusiastic", "empathetic", "direct"]
            emoji_sets = [["😊", "💪"], ["🙌", "✨"], ["❤️", "🔥"], ["👋", "🎯"], []]

            # Create FollowerMemoryDB (uses string for creator_id)
            is_customer = segment == "customer"
            follower_memory = FollowerMemoryDB(
                id=uuid.uuid4(),
                creator_id=creator_name,  # String type
                follower_id=follower_id,
                username=username,
                name=full_name,
                first_contact=first_contact.isoformat(),
                last_contact=last_contact.isoformat(),
                total_messages=total_messages,
                interests=interests,
                products_discussed=products_discussed,
                objections_raised=objections_raised,
                purchase_intent_score=purchase_intent,
                is_lead=segment not in ["new", "engaged_fan"],
                is_customer=is_customer,
                status=status,
                preferred_language="es",
                last_messages=last_messages,  # Populated with conversation
                # Link control
                links_sent_count=random.randint(0, 3) if segment in ["hot_lead", "warm_lead"] else 0,
                last_link_message_num=random.randint(3, 8) if segment in ["hot_lead", "warm_lead"] else 0,
                # Objection handling
                objections_handled=objections_handled,
                arguments_used=arguments_used,
                # Greeting variation
                greeting_variant_index=random.randint(0, 4),
                # Naturalness fields
                last_greeting_style=random.choice(greeting_styles),
                last_emojis_used=random.choice(emoji_sets),
                messages_since_name_used=random.randint(0, 5),
                # Alternative contact
                alternative_contact=alt_contact,
                alternative_contact_type=alt_contact_type,
                contact_requested=contact_requested,
            )
            db.add(follower_memory)
            followers.append(follower_memory)

            # Create Lead for non-new segments (uses UUID for creator_id)
            if segment not in ["new"]:
                deal_value = None
                if segment == "customer":
                    deal_value = random.choice(products).price
                elif segment == "hot_lead":
                    deal_value = random.choice(products).price
                elif segment == "warm_lead":
                    deal_value = random.choice(products).price * 0.7  # Weighted

                # Generate email and phone (higher chance for hot leads/customers)
                has_email = random.random() < (0.9 if segment in ["hot_lead", "customer"] else 0.4)
                has_phone = random.random() < (0.7 if segment in ["hot_lead", "customer"] else 0.2)

                lead = Lead(
                    id=uuid.uuid4(),
                    creator_id=creator_uuid,  # UUID type
                    platform="instagram",
                    platform_user_id=follower_id,
                    username=username,
                    full_name=full_name,
                    profile_pic_url=get_profile_pic_url(follower_id),
                    status=status,
                    score=int(purchase_intent * 100),
                    purchase_intent=purchase_intent,
                    context={
                        "segment": segment,
                        "interests": interests,
                        "objections": objections_raised,  # Now a simple list of strings
                    },
                    first_contact_at=first_contact,
                    last_contact_at=last_contact,
                    deal_value=deal_value,
                    tags=[segment] + interests[:2],
                    source=random.choice(["instagram_dm", "story_reply", "story_mention"]),
                    # NEW FIELDS
                    email=generate_email(username, first_name) if has_email else None,
                    phone=generate_phone() if has_phone else None,
                    notes=get_notes_for_segment(segment),
                    assigned_to=get_assigned_to() if segment in ["hot_lead", "warm_lead"] else None,
                )
                db.add(lead)
                leads.append(lead)

                # Create ConversationStateDB (uses string for creator_id)
                phase_map = {
                    "hot_lead": "cierre",
                    "warm_lead": "propuesta",
                    "price_objector": "objeciones",
                    "time_objector": "objeciones",
                    "ghost": "inicio",
                    "engaged_fan": "cualificacion",
                    "customer": "cierre",
                }
                # Get user context with situation/goal/constraints (for ProfilePanel)
                user_context = get_user_context() if segment in ["hot_lead", "warm_lead", "customer"] else {}

                conv_state = ConversationStateDB(
                    id=uuid.uuid4(),
                    creator_id=creator_name,  # String type
                    follower_id=follower_id,
                    phase=phase_map.get(segment, "inicio"),
                    message_count=total_messages,
                    context={
                        "interests": interests,
                        "objections": objections_raised,
                        "products_discussed": products_discussed,
                        # ProfilePanel fields
                        **user_context,
                    },
                )
                db.add(conv_state)

                # Create Messages (use already generated conversation)
                msg_time = first_contact
                for msg_data in conversation:
                    msg = Message(
                        id=uuid.uuid4(),
                        lead_id=lead.id,
                        role=msg_data["role"],
                        content=msg_data["content"],
                        intent=segment if msg_data["role"] == "user" else None,
                        status="sent",
                        created_at=msg_time,
                    )
                    db.add(msg)
                    all_messages.append(msg)
                    msg_time += timedelta(minutes=random.randint(5, 120))

            # Create UserProfileDB (uses string for creator_id)
            user_profile = UserProfileDB(
                id=uuid.uuid4(),
                creator_id=creator_name,  # String type
                user_id=follower_id,
                preferences={"language": "es", "response_style": "friendly"},
                interests={topic: random.uniform(0.3, 1.0) for topic in interests},
                objections=objections_raised,
                interested_products=[{"name": p, "interest_count": random.randint(1, 5)} for p in products_discussed],
                interaction_count=total_messages,
                last_interaction=last_contact,
            )
            db.add(user_profile)

            follower_index += 1

    db.commit()
    log(f"  Created {len(followers)} followers, {len(leads)} leads, {len(all_messages)} messages")
    return followers, leads


def create_lead_activities(db, leads: list, creator_uuid: uuid.UUID) -> list:
    """Create LeadActivity timeline records for leads"""
    log("Creating lead activities...")
    activities = []
    now = datetime.now(timezone.utc)

    for lead in leads:
        segment = lead.context.get("segment", "new")
        lead_activities_list = []

        # Activity 1: Lead created (always)
        lead_activities_list.append({
            "activity_type": "lead_created",
            "description": f"Lead creado desde {lead.source}",
            "created_at": lead.first_contact_at,
            "created_by": "system",
        })

        # Activity 2: Status change (for non-new leads)
        if segment in ["warm_lead", "hot_lead", "customer"]:
            status_time = lead.first_contact_at + timedelta(hours=random.randint(2, 48))
            old_status = "nuevo"
            if segment == "warm_lead":
                new_status = "interesado"
            elif segment == "hot_lead":
                new_status = "caliente"
            else:
                new_status = "cliente"

            lead_activities_list.append({
                "activity_type": "status_change",
                "description": f"Estado cambiado de {old_status} a {new_status}",
                "old_value": old_status,
                "new_value": new_status,
                "created_at": status_time,
                "created_by": "system",
            })

        # Activity 3: Note added (30% chance)
        if lead.notes and random.random() < 0.3:
            note_time = lead.first_contact_at + timedelta(hours=random.randint(1, 72))
            lead_activities_list.append({
                "activity_type": "note",
                "description": lead.notes,
                "created_at": note_time,
                "created_by": "creator",
            })

        # Activity 4: Tag added (for some leads)
        if len(lead.tags) > 1 and random.random() < 0.4:
            tag = lead.tags[1]  # Second tag (first is segment)
            tag_time = lead.first_contact_at + timedelta(hours=random.randint(1, 24))
            lead_activities_list.append({
                "activity_type": "tag_added",
                "description": f"Etiqueta '{tag}' añadida",
                "extra_data": {"tag": tag},
                "created_at": tag_time,
                "created_by": "creator",
            })

        # Activity 5: Email captured (for leads with email)
        if lead.email:
            email_time = lead.first_contact_at + timedelta(hours=random.randint(4, 96))
            lead_activities_list.append({
                "activity_type": "email",
                "description": f"Email capturado: {lead.email}",
                "created_at": email_time,
                "created_by": "system",
            })

        # Activity 6: Call/meeting scheduled (for hot leads, customers)
        if segment in ["hot_lead", "customer"] and random.random() < 0.5:
            call_time = lead.last_contact_at - timedelta(days=random.randint(1, 7))
            lead_activities_list.append({
                "activity_type": "meeting",
                "description": "Llamada de discovery programada",
                "extra_data": {"meeting_type": "discovery"},
                "created_at": call_time,
                "created_by": "creator",
            })

        # Activity 7: Conversion (for customers)
        if segment == "customer":
            conv_time = lead.last_contact_at - timedelta(days=random.randint(1, 14))
            lead_activities_list.append({
                "activity_type": "status_change",
                "description": "Conversión: Lead convertido a cliente",
                "old_value": "caliente",
                "new_value": "cliente",
                "extra_data": {"deal_value": lead.deal_value},
                "created_at": conv_time,
                "created_by": "system",
            })

        # Create activity records
        for activity_data in lead_activities_list:
            activity = LeadActivity(
                id=uuid.uuid4(),
                lead_id=lead.id,
                creator_id=creator_uuid,
                activity_type=activity_data["activity_type"],
                description=activity_data.get("description"),
                old_value=activity_data.get("old_value"),
                new_value=activity_data.get("new_value"),
                extra_data=activity_data.get("extra_data", {}),
                created_by=activity_data.get("created_by", "system"),
                created_at=activity_data["created_at"],
            )
            db.add(activity)
            activities.append(activity)

    db.commit()
    log(f"  Created {len(activities)} lead activities")
    return activities


def track_analytics_events(leads: list, creator_name: str):
    """Track analytics events for demo data"""
    log("Tracking analytics events...")
    analytics = get_analytics_manager()
    events_tracked = 0

    for lead in leads:
        segment = lead.context.get("segment", "new")
        follower_id = lead.platform_user_id

        # Track message received
        analytics.track_message(
            creator_id=creator_name,
            follower_id=follower_id,
            direction="received",
            intent=segment,
            platform="instagram",
            metadata={"segment": segment},
        )
        events_tracked += 1

        # Track message sent
        analytics.track_message(
            creator_id=creator_name,
            follower_id=follower_id,
            direction="sent",
            platform="instagram",
        )
        events_tracked += 1

        # Track lead creation
        analytics.track_lead(
            creator_id=creator_name,
            follower_id=follower_id,
            score=lead.purchase_intent,
            source=lead.source,
            platform="instagram",
        )
        events_tracked += 1

        # Track objections
        for objection in lead.context.get("objections", []):
            analytics.track_objection(
                creator_id=creator_name,
                follower_id=follower_id,
                objection_type=objection,
                platform="instagram",
            )
            events_tracked += 1

        # Track conversions (for customers)
        if segment == "customer" and lead.deal_value:
            analytics.track_conversion(
                creator_id=creator_name,
                follower_id=follower_id,
                product_id="plan_12_semanas",
                amount=lead.deal_value,
                platform="instagram",
            )
            events_tracked += 1

    log(f"  Tracked {events_tracked} analytics events")


def create_bookings(db, leads: list, booking_links: list, creator_name: str) -> list:
    """Create bookings - 5 for today, 10 historical"""
    log("Creating bookings...")
    created = []
    now = datetime.now(timezone.utc)
    today = now.date()

    # Pick some leads for bookings
    hot_leads = [l for l in leads if l.context.get("segment") == "hot_lead"]
    warm_leads = [l for l in leads if l.context.get("segment") == "warm_lead"]
    booking_candidates = hot_leads[:5] + warm_leads[:10]

    if not booking_candidates:
        booking_candidates = leads[:15]

    random.shuffle(booking_candidates)

    # 5 bookings for today
    for i, lead in enumerate(booking_candidates[:5]):
        hour = 9 + i * 2  # 9am, 11am, 1pm, 3pm, 5pm
        scheduled_at = datetime.combine(today, datetime.min.time().replace(hour=hour, minute=0))
        scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)

        link = random.choice(booking_links)
        booking = CalendarBooking(
            id=uuid.uuid4(),
            creator_id=creator_name,  # String type
            follower_id=lead.platform_user_id,
            meeting_type=link.meeting_type,
            platform=link.platform,
            status="scheduled",
            scheduled_at=scheduled_at,
            duration_minutes=link.duration_minutes,
            guest_name=lead.full_name,
            guest_email=f"{lead.username}@gmail.com",
            meeting_url=f"https://meet.google.com/abc-{i}-xyz",
        )
        db.add(booking)
        created.append(booking)

    # 10 historical bookings (past 30 days)
    for i, lead in enumerate(booking_candidates[5:15]):
        days_ago = random.randint(1, 30)
        hour = random.randint(9, 17)
        scheduled_at = now - timedelta(days=days_ago)
        scheduled_at = scheduled_at.replace(hour=hour, minute=0, second=0, microsecond=0)

        link = random.choice(booking_links)
        status = random.choice(["completed", "completed", "completed", "no_show", "cancelled"])

        booking = CalendarBooking(
            id=uuid.uuid4(),
            creator_id=creator_name,  # String type
            follower_id=lead.platform_user_id,
            meeting_type=link.meeting_type,
            platform=link.platform,
            status=status,
            scheduled_at=scheduled_at,
            duration_minutes=link.duration_minutes,
            guest_name=lead.full_name,
            guest_email=f"{lead.username}@gmail.com",
        )
        db.add(booking)
        created.append(booking)

    db.commit()
    log(f"  Created {len(created)} bookings (5 today, 10 historical)")
    return created


def print_summary(followers, leads, products, bookings, activities):
    """Print summary of created data"""
    log("\n" + "=" * 60)
    log("DEMO DATA SEED COMPLETE")
    log("=" * 60)
    log(f"Creator:           {CREATOR_ID}")
    log(f"Followers:         {len(followers)}")
    log(f"Leads:             {len(leads)}")
    log(f"Products:          {len(products)}")
    log(f"Bookings:          {len(bookings)}")
    log(f"Lead Activities:   {len(activities)}")
    log("")
    log("Segment distribution:")
    for segment, count in SEGMENT_DISTRIBUTION.items():
        log(f"  {segment:20s}: {count}")

    # Field population stats
    leads_with_email = sum(1 for l in leads if l.email)
    leads_with_phone = sum(1 for l in leads if l.phone)
    leads_with_notes = sum(1 for l in leads if l.notes)
    leads_assigned = sum(1 for l in leads if l.assigned_to)

    log("")
    log("Field population:")
    log(f"  Leads with email:    {leads_with_email} ({leads_with_email*100//len(leads) if leads else 0}%)")
    log(f"  Leads with phone:    {leads_with_phone} ({leads_with_phone*100//len(leads) if leads else 0}%)")
    log(f"  Leads with notes:    {leads_with_notes} ({leads_with_notes*100//len(leads) if leads else 0}%)")
    log(f"  Leads assigned:      {leads_assigned} ({leads_assigned*100//len(leads) if leads else 0}%)")
    log("=" * 60)


def main():
    """Main entry point"""
    log("Starting demo data seed...")
    log(f"Target creator: {CREATOR_ID}")

    if SessionLocal is None:
        log("ERROR: Database not configured. Set DATABASE_URL environment variable.")
        sys.exit(1)

    db = SessionLocal()

    try:
        # Get or create creator (returns UUID and string name)
        creator_uuid, creator_name = get_or_create_creator(db)

        # Clear existing data
        clear_demo_data(db, creator_uuid, creator_name)

        # Create data (using appropriate ID type for each table)
        products = create_products(db, creator_uuid)
        booking_links = create_booking_links(db, creator_name)
        followers, leads = create_followers_and_leads(db, products, creator_uuid, creator_name)
        activities = create_lead_activities(db, leads, creator_uuid)
        bookings = create_bookings(db, leads, booking_links, creator_name)

        # Track analytics events (stored in JSON files)
        track_analytics_events(leads, creator_name)

        # Summary
        print_summary(followers, leads, products, bookings, activities)

        log("\nSeed completed successfully!")

    except Exception as e:
        log(f"ERROR: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
