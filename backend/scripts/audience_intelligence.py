#!/usr/bin/env python3
"""
AUDIENCE INTELLIGENCE: Complete Value Extraction
================================================

Extracts actionable intelligence from Stefan's conversation data.

7 Modules:
1. Network Intelligence - Referrals, VIPs, clusters
2. Opportunity Detection - Lost revenue, ignored proposals
3. Follow-up Tracker - Broken commitments
4. Testimonial Extractor - Social proof
5. Proposal Tracker - Job offers, collaborations
6. FAQ Analyzer - Question categories
7. Communication Patterns - Response time, message length

Usage:
    DATABASE_URL=postgresql://... python audience_intelligence.py [--creator-id ID]
"""

import os
import sys
import re
import json
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from dataclasses import dataclass, field, asdict
from typing import Optional
import argparse

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class NetworkContact:
    """A contact in the creator's network"""
    follower_id: str
    username: str
    name: str
    category: str  # vip, referrer, cluster_member, regular
    referrals_made: int = 0
    mentions: list = field(default_factory=list)
    total_messages: int = 0
    purchase_intent: float = 0.0
    tags: list = field(default_factory=list)


@dataclass
class Opportunity:
    """A detected business opportunity"""
    follower_id: str
    username: str
    opportunity_type: str  # lost_sale, ignored_request, abandoned_conversation
    description: str
    estimated_value: float = 0.0
    last_message: str = ""
    last_contact: str = ""
    recovery_action: str = ""


@dataclass
class FollowUp:
    """A follow-up that was promised but not completed"""
    follower_id: str
    username: str
    commitment: str
    commitment_date: str
    status: str  # pending, overdue, completed
    days_overdue: int = 0
    context: str = ""


@dataclass
class Testimonial:
    """Extracted testimonial from conversation"""
    follower_id: str
    username: str
    content: str
    sentiment_score: float
    date: str
    category: str  # result, gratitude, recommendation
    usable_for: list = field(default_factory=list)


@dataclass
class Proposal:
    """A collaboration or job proposal"""
    follower_id: str
    username: str
    proposal_type: str  # job_offer, collaboration, partnership, speaking
    description: str
    date: str
    status: str  # pending, responded, ignored
    value_indicator: str = ""


@dataclass
class FAQ:
    """Frequently asked question"""
    question_pattern: str
    frequency: int
    category: str
    example_messages: list = field(default_factory=list)
    suggested_answer: str = ""


@dataclass
class CommunicationPattern:
    """Communication pattern analysis"""
    follower_id: str
    username: str
    avg_response_time_hours: float
    avg_message_length: int
    most_active_hours: list = field(default_factory=list)
    conversation_depth: int = 0
    engagement_score: float = 0.0


# =============================================================================
# PATTERN DEFINITIONS
# =============================================================================

# Network patterns
REFERRAL_PATTERNS = [
    r"me lo recomend[óo]",
    r"me habl[óo] de ti",
    r"me dijo que",
    r"un amig[oa] me pas[óo]",
    r"vi tu perfil (por|gracias a)",
    r"me lo pas[óo]",
    r"alguien me recomend[óo]",
    r"me dijeron que",
]

VIP_INDICATORS = [
    r"(?:soy|trabajo como|trabajo en)\s+(?:coach|mentor|empresari[oa]|director|ceo|founder|psic[óo]log[oa])",
    r"(?:mi empresa|mi negocio|mi marca)",
    r"(?:tengo|gestiono)\s+(?:\d+|varios|muchos)\s+(?:empleados|clientes|seguidores)",
    r"(?:factur[oa]|vend[oa]|genero)\s+\d+",
]

# Opportunity patterns
LOST_SALE_PATTERNS = [
    r"(?:cu[aá]nto|precio|cost[ea]|vale)",
    r"(?:me interesa|quiero|necesito)",
    r"(?:c[óo]mo puedo|d[óo]nde puedo)",
    r"(?:link|enlace|comprar)",
]

ABANDONED_INDICATORS = [
    r"(?:lo pienso|ya te digo|luego|despu[ée]s)",
    r"(?:ahora no puedo|no tengo tiempo)",
    r"(?:cuando tenga|cuando pueda)",
]

# Follow-up patterns
COMMITMENT_PATTERNS = [
    r"(?:te escribo|te aviso|te cuento|te paso)\s+(?:ma[ñn]ana|la semana|el lunes|pronto)",
    r"(?:luego te|despu[ée]s te)",
    r"(?:voy a|vamos a)\s+(?:hablar|ver|revisar)",
    r"(?:te envío|te mando)\s+(?:algo|info|el)",
]

# Testimonial patterns
POSITIVE_PATTERNS = [
    r"(?:gracias|muchas gracias|mil gracias)",
    r"(?:incre[íi]ble|amazing|genial|brutal|wow)",
    r"(?:me ayud[óo]|me sirvi[óo]|me funcion[óo])",
    r"(?:cambi[óo] mi|transform[óo]|mejor[óo])",
    r"(?:lo recomiendo|te recomiendo)",
    r"(?:eres (?:el|la) mejor)",
]

RESULT_PATTERNS = [
    r"(?:logr[ée]|consegu[íi]|ahora tengo)",
    r"(?:gracias a ti|por ti)",
    r"(?:mi vida|mi negocio|mis resultados)",
    r"(?:dupliqu[ée]|tripl[ée]|aumenté)",
]

# Proposal patterns
PROPOSAL_PATTERNS = [
    r"(?:te interesar[íi]a|quieres|podr[íi]as)\s+(?:colaborar|participar|trabajar)",
    r"(?:oferta|propuesta|oportunidad)",
    r"(?:busco|necesito)\s+(?:alguien|a alguien|un)\s+(?:coach|mentor|experto)",
    r"(?:podcast|entrevista|charla|conferencia)",
    r"(?:proyecto|trabajo|contrato)",
]

# FAQ categories
FAQ_CATEGORIES = {
    "pricing": [r"(?:cu[áa]nto|precio|cost[ea]|vale|tarifa)"],
    "process": [r"(?:c[óo]mo|funciona|proceso|metodolog[íi]a)"],
    "availability": [r"(?:disponib|cu[áa]ndo|horario|agenda)"],
    "results": [r"(?:resultado|garant[íi]a|funciona|sirve)"],
    "content": [r"(?:d[óo]nde|recurso|material|contenido)"],
    "personal": [r"(?:qui[ée]n eres|tu historia|experiencia)"],
}


# =============================================================================
# MODULE 1: NETWORK INTELLIGENCE
# =============================================================================

def extract_network_intelligence(session, creator_id: str) -> dict:
    """Extract network intelligence: referrals, VIPs, clusters"""
    print("\n" + "="*60)
    print("MODULE 1: NETWORK INTELLIGENCE")
    print("="*60)

    contacts = []
    referrers = []
    vips = []

    # Get all leads with their messages
    query = text("""
        SELECT
            l.id, l.platform_user_id, l.username, l.full_name, l.status,
            l.score, l.purchase_intent, l.tags, l.notes,
            COUNT(m.id) as message_count
        FROM leads l
        LEFT JOIN messages m ON m.lead_id = l.id
        WHERE l.creator_id = :creator_id
        GROUP BY l.id
        ORDER BY COUNT(m.id) DESC
    """)

    leads = session.execute(query, {"creator_id": creator_id}).fetchall()

    for lead in leads:
        # Get messages for this lead
        msg_query = text("""
            SELECT content, role, created_at
            FROM messages
            WHERE lead_id = :lead_id
            ORDER BY created_at
        """)
        messages = session.execute(msg_query, {"lead_id": lead.id}).fetchall()

        mentions = []
        is_referrer = False
        is_vip = False

        for msg in messages:
            if msg.role == "user":
                content = msg.content.lower() if msg.content else ""

                # Check for referral patterns
                for pattern in REFERRAL_PATTERNS:
                    if re.search(pattern, content, re.IGNORECASE):
                        is_referrer = True
                        mentions.append(msg.content[:100])
                        break

                # Check for VIP indicators
                for pattern in VIP_INDICATORS:
                    if re.search(pattern, content, re.IGNORECASE):
                        is_vip = True
                        break

        category = "regular"
        if is_vip:
            category = "vip"
        elif is_referrer:
            category = "referrer"
        elif lead.message_count > 20:
            category = "engaged"

        contact = NetworkContact(
            follower_id=lead.platform_user_id or str(lead.id),
            username=lead.username or "unknown",
            name=lead.full_name or "",
            category=category,
            referrals_made=1 if is_referrer else 0,
            mentions=mentions[:3],
            total_messages=lead.message_count or 0,
            purchase_intent=lead.purchase_intent or 0.0,
            tags=lead.tags or []
        )
        contacts.append(contact)

        if is_referrer:
            referrers.append(contact)
        if is_vip:
            vips.append(contact)

    # Calculate statistics
    stats = {
        "total_contacts": len(contacts),
        "vips": len(vips),
        "referrers": len(referrers),
        "engaged": len([c for c in contacts if c.category == "engaged"]),
        "avg_messages_per_contact": sum(c.total_messages for c in contacts) / len(contacts) if contacts else 0,
    }

    print(f"  Total contacts analyzed: {stats['total_contacts']}")
    print(f"  VIPs identified: {stats['vips']}")
    print(f"  Referrers found: {stats['referrers']}")
    print(f"  Highly engaged: {stats['engaged']}")

    return {
        "contacts": [asdict(c) for c in contacts[:50]],  # Top 50
        "vips": [asdict(c) for c in vips],
        "referrers": [asdict(c) for c in referrers],
        "statistics": stats
    }


# =============================================================================
# MODULE 2: OPPORTUNITY DETECTION
# =============================================================================

def detect_opportunities(session, creator_id: str) -> dict:
    """Detect lost opportunities: abandoned carts, ignored requests"""
    print("\n" + "="*60)
    print("MODULE 2: OPPORTUNITY DETECTION")
    print("="*60)

    opportunities = []

    # Find leads with price inquiries that didn't convert
    query = text("""
        SELECT
            l.id, l.platform_user_id, l.username, l.full_name, l.status,
            l.last_contact_at, l.purchase_intent, l.deal_value
        FROM leads l
        WHERE l.creator_id = :creator_id
        AND l.status NOT IN ('cliente', 'customer')
        ORDER BY l.last_contact_at DESC
    """)

    leads = session.execute(query, {"creator_id": creator_id}).fetchall()

    for lead in leads:
        msg_query = text("""
            SELECT content, role, created_at
            FROM messages
            WHERE lead_id = :lead_id
            ORDER BY created_at DESC
            LIMIT 20
        """)
        messages = session.execute(msg_query, {"lead_id": lead.id}).fetchall()

        showed_interest = False
        showed_price_interest = False
        last_user_msg = None
        abandoned = False

        for msg in messages:
            content = msg.content.lower() if msg.content else ""

            if msg.role == "user":
                if not last_user_msg:
                    last_user_msg = msg.content

                # Check for purchase interest
                for pattern in LOST_SALE_PATTERNS:
                    if re.search(pattern, content, re.IGNORECASE):
                        showed_interest = True
                        if "precio" in content or "cuanto" in content or "cost" in content:
                            showed_price_interest = True
                        break

                # Check for abandonment signals
                for pattern in ABANDONED_INDICATORS:
                    if re.search(pattern, content, re.IGNORECASE):
                        abandoned = True
                        break

        # Calculate days since last contact
        days_inactive = 0
        if lead.last_contact_at:
            days_inactive = (datetime.now() - lead.last_contact_at.replace(tzinfo=None)).days

        # Determine opportunity type
        if showed_price_interest and days_inactive > 3:
            opp_type = "lost_sale"
            description = "Asked about pricing but didn't convert"
            recovery = "Send follow-up with special offer or payment plan"
            estimated_value = lead.deal_value or 97.0
        elif showed_interest and abandoned:
            opp_type = "abandoned_conversation"
            description = "Showed interest but conversation dropped"
            recovery = "Gentle check-in asking if they have questions"
            estimated_value = lead.deal_value or 50.0
        elif days_inactive > 7 and (lead.purchase_intent or 0) > 0.3:
            opp_type = "cold_lead"
            description = f"Hot lead gone cold ({days_inactive} days)"
            recovery = "Re-engagement with value content"
            estimated_value = lead.deal_value or 30.0
        else:
            continue

        opportunity = Opportunity(
            follower_id=lead.platform_user_id or str(lead.id),
            username=lead.username or "unknown",
            opportunity_type=opp_type,
            description=description,
            estimated_value=estimated_value,
            last_message=last_user_msg[:200] if last_user_msg else "",
            last_contact=str(lead.last_contact_at)[:10] if lead.last_contact_at else "",
            recovery_action=recovery
        )
        opportunities.append(opportunity)

    # Group by type
    by_type = defaultdict(list)
    for opp in opportunities:
        by_type[opp.opportunity_type].append(opp)

    total_value = sum(opp.estimated_value for opp in opportunities)

    print(f"  Lost sales: {len(by_type['lost_sale'])}")
    print(f"  Abandoned conversations: {len(by_type['abandoned_conversation'])}")
    print(f"  Cold leads: {len(by_type['cold_lead'])}")
    print(f"  Total estimated value at risk: €{total_value:.0f}")

    return {
        "opportunities": [asdict(o) for o in opportunities],
        "by_type": {k: [asdict(o) for o in v] for k, v in by_type.items()},
        "statistics": {
            "total_opportunities": len(opportunities),
            "total_value_at_risk": total_value,
            "lost_sales": len(by_type["lost_sale"]),
            "abandoned": len(by_type["abandoned_conversation"]),
            "cold_leads": len(by_type["cold_lead"])
        }
    }


# =============================================================================
# MODULE 3: FOLLOW-UP TRACKER
# =============================================================================

def track_followups(session, creator_id: str) -> dict:
    """Track promised follow-ups that weren't completed"""
    print("\n" + "="*60)
    print("MODULE 3: FOLLOW-UP TRACKER")
    print("="*60)

    followups = []

    # Get all assistant messages (outbound)
    query = text("""
        SELECT
            m.id, m.lead_id, m.content, m.created_at,
            l.platform_user_id, l.username
        FROM messages m
        JOIN leads l ON m.lead_id = l.id
        WHERE l.creator_id = :creator_id
        AND m.role = 'assistant'
        ORDER BY m.created_at DESC
    """)

    messages = session.execute(query, {"creator_id": creator_id}).fetchall()

    commitments_by_lead = defaultdict(list)

    for msg in messages:
        content = msg.content.lower() if msg.content else ""

        for pattern in COMMITMENT_PATTERNS:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                commitments_by_lead[msg.lead_id].append({
                    "commitment": msg.content[:200] if msg.content else "",
                    "date": msg.created_at,
                    "username": msg.username or "unknown",
                    "follower_id": msg.platform_user_id or str(msg.lead_id)
                })
                break

    # Check if commitments were fulfilled (subsequent messages)
    for lead_id, commitments in commitments_by_lead.items():
        for commit in commitments[:5]:  # Max 5 per lead
            # Check for follow-up messages after commitment
            followup_query = text("""
                SELECT COUNT(*) as cnt
                FROM messages
                WHERE lead_id = :lead_id
                AND role = 'assistant'
                AND created_at > :commit_date
            """)
            result = session.execute(followup_query, {
                "lead_id": lead_id,
                "commit_date": commit["date"]
            }).fetchone()

            days_since = (datetime.now() - commit["date"].replace(tzinfo=None)).days

            if result.cnt == 0 and days_since > 2:
                status = "overdue"
            elif result.cnt > 0:
                status = "completed"
            else:
                status = "pending"

            followup = FollowUp(
                follower_id=commit["follower_id"],
                username=commit["username"],
                commitment=commit["commitment"],
                commitment_date=str(commit["date"])[:10],
                status=status,
                days_overdue=max(0, days_since - 2) if status == "overdue" else 0,
                context=""
            )

            if status in ["overdue", "pending"]:
                followups.append(followup)

    # Sort by overdue days
    followups.sort(key=lambda x: x.days_overdue, reverse=True)

    overdue = [f for f in followups if f.status == "overdue"]
    pending = [f for f in followups if f.status == "pending"]

    print(f"  Overdue follow-ups: {len(overdue)}")
    print(f"  Pending follow-ups: {len(pending)}")

    return {
        "followups": [asdict(f) for f in followups],
        "overdue": [asdict(f) for f in overdue],
        "pending": [asdict(f) for f in pending],
        "statistics": {
            "total_tracked": len(followups),
            "overdue_count": len(overdue),
            "pending_count": len(pending),
            "avg_days_overdue": sum(f.days_overdue for f in overdue) / len(overdue) if overdue else 0
        }
    }


# =============================================================================
# MODULE 4: TESTIMONIAL EXTRACTOR
# =============================================================================

def extract_testimonials(session, creator_id: str) -> dict:
    """Extract usable testimonials from conversations"""
    print("\n" + "="*60)
    print("MODULE 4: TESTIMONIAL EXTRACTOR")
    print("="*60)

    testimonials = []

    # Get all user messages
    query = text("""
        SELECT
            m.id, m.lead_id, m.content, m.created_at,
            l.platform_user_id, l.username, l.full_name
        FROM messages m
        JOIN leads l ON m.lead_id = l.id
        WHERE l.creator_id = :creator_id
        AND m.role = 'user'
        ORDER BY m.created_at DESC
    """)

    messages = session.execute(query, {"creator_id": creator_id}).fetchall()

    for msg in messages:
        content = msg.content if msg.content else ""
        content_lower = content.lower()

        # Skip short messages
        if len(content) < 30:
            continue

        sentiment_score = 0.0
        category = None

        # Check for result patterns (highest value)
        for pattern in RESULT_PATTERNS:
            if re.search(pattern, content_lower, re.IGNORECASE):
                sentiment_score = 0.9
                category = "result"
                break

        # Check for positive patterns
        if not category:
            for pattern in POSITIVE_PATTERNS:
                if re.search(pattern, content_lower, re.IGNORECASE):
                    sentiment_score = 0.7
                    category = "gratitude"
                    break

        if category:
            # Determine what it can be used for
            usable_for = []
            if category == "result":
                usable_for = ["case_study", "landing_page", "social_proof"]
            elif "recomiendo" in content_lower:
                usable_for = ["social_proof", "referral_program"]
            else:
                usable_for = ["social_proof"]

            testimonial = Testimonial(
                follower_id=msg.platform_user_id or str(msg.lead_id),
                username=msg.username or "anonymous",
                content=content[:500],
                sentiment_score=sentiment_score,
                date=str(msg.created_at)[:10] if msg.created_at else "",
                category=category,
                usable_for=usable_for
            )
            testimonials.append(testimonial)

    # Sort by sentiment score
    testimonials.sort(key=lambda x: x.sentiment_score, reverse=True)

    # Group by category
    by_category = defaultdict(list)
    for t in testimonials:
        by_category[t.category].append(t)

    print(f"  Result testimonials: {len(by_category['result'])}")
    print(f"  Gratitude testimonials: {len(by_category['gratitude'])}")
    print(f"  Recommendation testimonials: {len(by_category.get('recommendation', []))}")

    return {
        "testimonials": [asdict(t) for t in testimonials[:30]],  # Top 30
        "by_category": {k: [asdict(t) for t in v[:10]] for k, v in by_category.items()},
        "statistics": {
            "total_found": len(testimonials),
            "results": len(by_category["result"]),
            "gratitude": len(by_category["gratitude"]),
            "avg_sentiment": sum(t.sentiment_score for t in testimonials) / len(testimonials) if testimonials else 0
        }
    }


# =============================================================================
# MODULE 5: PROPOSAL TRACKER
# =============================================================================

def track_proposals(session, creator_id: str) -> dict:
    """Track collaboration proposals and job offers"""
    print("\n" + "="*60)
    print("MODULE 5: PROPOSAL TRACKER")
    print("="*60)

    proposals = []

    # Get all user messages
    query = text("""
        SELECT
            m.id, m.lead_id, m.content, m.created_at,
            l.platform_user_id, l.username
        FROM messages m
        JOIN leads l ON m.lead_id = l.id
        WHERE l.creator_id = :creator_id
        AND m.role = 'user'
        ORDER BY m.created_at DESC
    """)

    messages = session.execute(query, {"creator_id": creator_id}).fetchall()

    proposal_keywords = {
        "collaboration": ["colaborar", "colaboración", "juntos", "partnership"],
        "job_offer": ["trabajo", "oferta", "contratar", "proyecto", "presupuesto"],
        "speaking": ["podcast", "entrevista", "charla", "conferencia", "evento"],
        "partnership": ["socio", "partner", "invertir", "negocio conjunto"]
    }

    for msg in messages:
        content = msg.content if msg.content else ""
        content_lower = content.lower()

        # Skip short messages
        if len(content) < 20:
            continue

        proposal_type = None

        # Check for proposal patterns
        for pattern in PROPOSAL_PATTERNS:
            if re.search(pattern, content_lower, re.IGNORECASE):
                # Determine type
                for ptype, keywords in proposal_keywords.items():
                    if any(kw in content_lower for kw in keywords):
                        proposal_type = ptype
                        break
                if not proposal_type:
                    proposal_type = "general"
                break

        if proposal_type:
            # Check if responded
            response_query = text("""
                SELECT COUNT(*) as cnt
                FROM messages
                WHERE lead_id = :lead_id
                AND role = 'assistant'
                AND created_at > :msg_date
            """)
            result = session.execute(response_query, {
                "lead_id": msg.lead_id,
                "msg_date": msg.created_at
            }).fetchone()

            status = "responded" if result.cnt > 0 else "pending"
            days_since = (datetime.now() - msg.created_at.replace(tzinfo=None)).days
            if status == "pending" and days_since > 7:
                status = "ignored"

            proposal = Proposal(
                follower_id=msg.platform_user_id or str(msg.lead_id),
                username=msg.username or "unknown",
                proposal_type=proposal_type,
                description=content[:300],
                date=str(msg.created_at)[:10] if msg.created_at else "",
                status=status,
                value_indicator="high" if proposal_type in ["job_offer", "partnership"] else "medium"
            )
            proposals.append(proposal)

    # Group by type and status
    by_type = defaultdict(list)
    by_status = defaultdict(list)
    for p in proposals:
        by_type[p.proposal_type].append(p)
        by_status[p.status].append(p)

    print(f"  Collaborations: {len(by_type['collaboration'])}")
    print(f"  Job offers: {len(by_type['job_offer'])}")
    print(f"  Speaking requests: {len(by_type['speaking'])}")
    print(f"  Ignored proposals: {len(by_status['ignored'])}")

    return {
        "proposals": [asdict(p) for p in proposals],
        "by_type": {k: [asdict(p) for p in v] for k, v in by_type.items()},
        "by_status": {k: [asdict(p) for p in v] for k, v in by_status.items()},
        "statistics": {
            "total_proposals": len(proposals),
            "collaborations": len(by_type["collaboration"]),
            "job_offers": len(by_type["job_offer"]),
            "speaking": len(by_type["speaking"]),
            "ignored": len(by_status["ignored"]),
            "response_rate": 1 - (len(by_status["ignored"]) / len(proposals)) if proposals else 1.0
        }
    }


# =============================================================================
# MODULE 6: FAQ ANALYZER
# =============================================================================

def analyze_faqs(session, creator_id: str) -> dict:
    """Analyze frequently asked questions"""
    print("\n" + "="*60)
    print("MODULE 6: FAQ ANALYZER")
    print("="*60)

    question_counter = Counter()
    category_examples = defaultdict(list)

    # Get all user messages that are questions
    query = text("""
        SELECT m.content, m.intent
        FROM messages m
        JOIN leads l ON m.lead_id = l.id
        WHERE l.creator_id = :creator_id
        AND m.role = 'user'
    """)

    messages = session.execute(query, {"creator_id": creator_id}).fetchall()

    for msg in messages:
        content = msg.content if msg.content else ""
        content_lower = content.lower()

        # Check if it's a question
        is_question = "?" in content or any(
            qw in content_lower for qw in
            ["cómo", "como", "qué", "que", "cuánto", "cuanto", "dónde", "donde", "cuándo", "cuando", "por qué"]
        )

        if not is_question:
            continue

        # Categorize
        for category, patterns in FAQ_CATEGORIES.items():
            for pattern in patterns:
                if re.search(pattern, content_lower, re.IGNORECASE):
                    question_counter[category] += 1
                    if len(category_examples[category]) < 5:
                        category_examples[category].append(content[:200])
                    break

    # Build FAQ list
    faqs = []
    for category, count in question_counter.most_common():
        faq = FAQ(
            question_pattern=category,
            frequency=count,
            category=category,
            example_messages=category_examples[category],
            suggested_answer=""
        )
        faqs.append(faq)

    print(f"  Pricing questions: {question_counter.get('pricing', 0)}")
    print(f"  Process questions: {question_counter.get('process', 0)}")
    print(f"  Availability questions: {question_counter.get('availability', 0)}")
    print(f"  Results questions: {question_counter.get('results', 0)}")

    return {
        "faqs": [asdict(f) for f in faqs],
        "category_counts": dict(question_counter),
        "examples_by_category": dict(category_examples),
        "statistics": {
            "total_questions_analyzed": sum(question_counter.values()),
            "categories_found": len(question_counter),
            "top_category": question_counter.most_common(1)[0][0] if question_counter else None
        }
    }


# =============================================================================
# MODULE 7: COMMUNICATION PATTERNS
# =============================================================================

def analyze_communication_patterns(session, creator_id: str) -> dict:
    """Analyze communication patterns"""
    print("\n" + "="*60)
    print("MODULE 7: COMMUNICATION PATTERNS")
    print("="*60)

    patterns = []

    # Get leads with message stats
    query = text("""
        SELECT
            l.id, l.platform_user_id, l.username, l.first_contact_at, l.last_contact_at
        FROM leads l
        WHERE l.creator_id = :creator_id
    """)

    leads = session.execute(query, {"creator_id": creator_id}).fetchall()

    overall_response_times = []
    overall_msg_lengths = []
    hour_distribution = Counter()

    for lead in leads:
        # Get message details
        msg_query = text("""
            SELECT content, role, created_at
            FROM messages
            WHERE lead_id = :lead_id
            ORDER BY created_at
        """)
        messages = session.execute(msg_query, {"lead_id": lead.id}).fetchall()

        if not messages:
            continue

        # Calculate metrics
        user_msg_lengths = []
        response_times = []
        active_hours = []

        prev_msg = None
        for msg in messages:
            if msg.role == "user":
                user_msg_lengths.append(len(msg.content) if msg.content else 0)
                if msg.created_at:
                    active_hours.append(msg.created_at.hour)
                    hour_distribution[msg.created_at.hour] += 1

                # Calculate response time if previous was assistant
                if prev_msg and prev_msg.role == "assistant" and msg.created_at and prev_msg.created_at:
                    delta = (msg.created_at - prev_msg.created_at).total_seconds() / 3600
                    if 0 < delta < 168:  # Less than a week
                        response_times.append(delta)

            prev_msg = msg

        if user_msg_lengths:
            avg_length = sum(user_msg_lengths) / len(user_msg_lengths)
            overall_msg_lengths.extend(user_msg_lengths)
        else:
            avg_length = 0

        if response_times:
            avg_response = sum(response_times) / len(response_times)
            overall_response_times.extend(response_times)
        else:
            avg_response = 0

        # Most common hours
        hour_counts = Counter(active_hours)
        most_active = [h for h, _ in hour_counts.most_common(3)]

        # Engagement score
        engagement = min(1.0, (len(messages) / 50) * 0.5 + (avg_length / 200) * 0.3 + (1 / max(1, avg_response)) * 0.2)

        pattern = CommunicationPattern(
            follower_id=lead.platform_user_id or str(lead.id),
            username=lead.username or "unknown",
            avg_response_time_hours=round(avg_response, 2),
            avg_message_length=int(avg_length),
            most_active_hours=most_active,
            conversation_depth=len(messages),
            engagement_score=round(engagement, 2)
        )
        patterns.append(pattern)

    # Sort by engagement
    patterns.sort(key=lambda x: x.engagement_score, reverse=True)

    # Overall statistics
    peak_hours = [h for h, _ in hour_distribution.most_common(5)]

    print(f"  Contacts analyzed: {len(patterns)}")
    print(f"  Avg response time: {sum(overall_response_times) / len(overall_response_times):.1f}h" if overall_response_times else "  Avg response time: N/A")
    print(f"  Avg message length: {sum(overall_msg_lengths) / len(overall_msg_lengths):.0f} chars" if overall_msg_lengths else "  Avg message length: N/A")
    print(f"  Peak hours: {peak_hours}")

    return {
        "patterns": [asdict(p) for p in patterns[:50]],  # Top 50
        "statistics": {
            "total_analyzed": len(patterns),
            "avg_response_time_hours": round(sum(overall_response_times) / len(overall_response_times), 2) if overall_response_times else 0,
            "avg_message_length": round(sum(overall_msg_lengths) / len(overall_msg_lengths)) if overall_msg_lengths else 0,
            "peak_hours": peak_hours,
            "highly_engaged_count": len([p for p in patterns if p.engagement_score > 0.6])
        }
    }


# =============================================================================
# REPORT GENERATION
# =============================================================================

def generate_markdown_report(results: dict, creator_id: str) -> str:
    """Generate comprehensive Markdown report"""

    report = f"""# 🎯 Audience Intelligence Report
## Creator: {creator_id}
## Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

---

## Executive Summary

| Module | Key Metric | Value |
|--------|-----------|-------|
| Network | VIPs Identified | {results['network']['statistics']['vips']} |
| Network | Referrers | {results['network']['statistics']['referrers']} |
| Opportunities | Value at Risk | €{results['opportunities']['statistics']['total_value_at_risk']:.0f} |
| Follow-ups | Overdue | {results['followups']['statistics']['overdue_count']} |
| Testimonials | Usable | {results['testimonials']['statistics']['total_found']} |
| Proposals | Ignored | {results['proposals']['statistics']['ignored']} |
| FAQs | Top Category | {results['faqs']['statistics']['top_category'] or 'N/A'} |
| Communication | Highly Engaged | {results['communication']['statistics']['highly_engaged_count']} |

---

## 1. Network Intelligence

### VIP Contacts ({results['network']['statistics']['vips']})
"""

    for vip in results['network']['vips'][:5]:
        report += f"\n- **@{vip['username']}** ({vip['name'] or 'N/A'}) - {vip['total_messages']} messages"

    report += f"""

### Referrers ({results['network']['statistics']['referrers']})
"""

    for ref in results['network']['referrers'][:5]:
        report += f"\n- **@{ref['username']}** - Mention: _{ref['mentions'][0][:80] if ref['mentions'] else 'N/A'}..._"

    report += f"""

---

## 2. Opportunity Detection

### Lost Sales ({results['opportunities']['statistics']['lost_sales']})
"""

    for opp in results['opportunities']['by_type'].get('lost_sale', [])[:5]:
        report += f"\n- **@{opp['username']}** - €{opp['estimated_value']:.0f} - Last: {opp['last_contact']}"
        report += f"\n  - Recovery: {opp['recovery_action']}"

    report += f"""

### Abandoned Conversations ({results['opportunities']['statistics']['abandoned']})
"""

    for opp in results['opportunities']['by_type'].get('abandoned_conversation', [])[:5]:
        report += f"\n- **@{opp['username']}** - Last: {opp['last_contact']}"

    report += f"""

**Total Value at Risk: €{results['opportunities']['statistics']['total_value_at_risk']:.0f}**

---

## 3. Follow-up Tracker

### Overdue Follow-ups ({results['followups']['statistics']['overdue_count']})
"""

    for fu in results['followups']['overdue'][:5]:
        report += f"\n- **@{fu['username']}** - {fu['days_overdue']} days overdue"
        report += f"\n  - Commitment: _{fu['commitment'][:100]}..._"

    report += f"""

---

## 4. Testimonials

### Top Results Testimonials ({results['testimonials']['statistics']['results']})
"""

    for test in results['testimonials']['by_category'].get('result', [])[:3]:
        report += f"\n> \"{test['content'][:200]}...\" - @{test['username']}"

    report += f"""

### Gratitude Messages ({results['testimonials']['statistics']['gratitude']})
"""

    for test in results['testimonials']['by_category'].get('gratitude', [])[:3]:
        report += f"\n> \"{test['content'][:150]}...\" - @{test['username']}"

    report += f"""

---

## 5. Proposals

### Pending/Ignored Proposals ({results['proposals']['statistics']['ignored']})
"""

    for prop in results['proposals']['by_status'].get('ignored', [])[:5]:
        report += f"\n- **@{prop['username']}** ({prop['proposal_type']}) - {prop['date']}"
        report += f"\n  - _{prop['description'][:150]}..._"

    report += f"""

### Response Rate: {results['proposals']['statistics']['response_rate']*100:.0f}%

---

## 6. FAQ Analysis

### Most Common Questions
"""

    for faq in results['faqs']['faqs'][:5]:
        report += f"\n- **{faq['category'].title()}** ({faq['frequency']} times)"
        if faq['example_messages']:
            report += f"\n  - Example: _{faq['example_messages'][0][:100]}..._"

    report += f"""

---

## 7. Communication Patterns

### Peak Activity Hours
{', '.join(f"{h}:00" for h in results['communication']['statistics']['peak_hours'][:5])}

### Most Engaged Contacts
"""

    for pat in results['communication']['patterns'][:5]:
        report += f"\n- **@{pat['username']}** - Score: {pat['engagement_score']} - {pat['conversation_depth']} messages"

    report += f"""

---

## Action Items

### Immediate (This Week)
1. Contact {min(5, len(results['opportunities']['by_type'].get('lost_sale', [])))} lost sales with recovery offers
2. Follow up on {min(3, results['followups']['statistics']['overdue_count'])} overdue commitments
3. Respond to {min(3, results['proposals']['statistics']['ignored'])} ignored proposals

### Short-term (This Month)
1. Create FAQ answers for top {len(results['faqs']['faqs'])} question categories
2. Request testimonial permissions from top {min(5, results['testimonials']['statistics']['results'])} result-sharers
3. Nurture {min(10, results['network']['statistics']['vips'])} VIP contacts

### Revenue Recovery Potential
**€{results['opportunities']['statistics']['total_value_at_risk']:.0f}** in identified opportunities

---

_Report generated by Clonnect Audience Intelligence v1.0_
"""

    return report


# =============================================================================
# MAIN EXECUTION
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Audience Intelligence Extraction")
    parser.add_argument("--creator-id", help="Creator ID to analyze")
    parser.add_argument("--output-dir", default=".", help="Output directory for reports")
    args = parser.parse_args()

    # Get DATABASE_URL
    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set")
        print("Usage: DATABASE_URL=postgresql://... python audience_intelligence.py")
        sys.exit(1)

    # Fix Railway postgres:// scheme
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    # Add sslmode if needed
    if "sslmode" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"

    print("="*60)
    print("AUDIENCE INTELLIGENCE EXTRACTION")
    print("="*60)
    print(f"Connecting to database...")

    # Create engine and session
    engine = create_engine(database_url, pool_pre_ping=True)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Get creator ID if not specified
        creator_id = args.creator_id
        if not creator_id:
            query = text("SELECT id, name FROM creators LIMIT 5")
            creators = session.execute(query).fetchall()

            if not creators:
                print("ERROR: No creators found in database")
                sys.exit(1)

            print("\nAvailable creators:")
            for c in creators:
                print(f"  - {c.id}: {c.name}")

            creator_id = str(creators[0].id)
            print(f"\nUsing first creator: {creator_id}")

        # Run all modules
        results = {
            "creator_id": creator_id,
            "generated_at": datetime.now().isoformat(),
            "network": extract_network_intelligence(session, creator_id),
            "opportunities": detect_opportunities(session, creator_id),
            "followups": track_followups(session, creator_id),
            "testimonials": extract_testimonials(session, creator_id),
            "proposals": track_proposals(session, creator_id),
            "faqs": analyze_faqs(session, creator_id),
            "communication": analyze_communication_patterns(session, creator_id),
        }

        # Save JSON report
        json_path = os.path.join(args.output_dir, f"audience_intelligence_{creator_id[:8]}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n✓ JSON report saved: {json_path}")

        # Generate and save Markdown report
        markdown_report = generate_markdown_report(results, creator_id)
        md_path = os.path.join(args.output_dir, f"audience_intelligence_{creator_id[:8]}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_report)
        print(f"✓ Markdown report saved: {md_path}")

        # Print summary
        print("\n" + "="*60)
        print("EXTRACTION COMPLETE")
        print("="*60)
        print(f"""
Summary:
- Network: {results['network']['statistics']['total_contacts']} contacts, {results['network']['statistics']['vips']} VIPs
- Opportunities: €{results['opportunities']['statistics']['total_value_at_risk']:.0f} at risk
- Follow-ups: {results['followups']['statistics']['overdue_count']} overdue
- Testimonials: {results['testimonials']['statistics']['total_found']} found
- Proposals: {results['proposals']['statistics']['total_proposals']} tracked
- FAQs: {results['faqs']['statistics']['categories_found']} categories
- Communication: {results['communication']['statistics']['highly_engaged_count']} highly engaged
""")

    finally:
        session.close()

    return results


if __name__ == "__main__":
    main()
