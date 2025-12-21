"""
Data loading utilities for Clonnect Admin Dashboard.
Handles loading and saving JSON data from the data directory.
"""
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import streamlit as st

BASE_DIR = Path(__file__).parent.parent.parent
DATA_DIR = BASE_DIR / "data"


# =============================================================================
# BASIC I/O
# =============================================================================

def load_json(filepath: Path) -> Any:
    """Load a JSON file."""
    try:
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        st.error(f"Error loading {filepath}: {e}")
    return None


def save_json(filepath: Path, data: Any) -> bool:
    """Save data to a JSON file."""
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        st.error(f"Error saving {filepath}: {e}")
        return False


def load_jsonl(filepath: Path) -> List[Dict]:
    """Load a JSONL file (one JSON per line)."""
    items = []
    try:
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        items.append(json.loads(line))
    except Exception as e:
        st.error(f"Error loading {filepath}: {e}")
    return items


# =============================================================================
# CREATORS
# =============================================================================

def get_creators() -> List[str]:
    """Get list of all creator IDs."""
    creators = []
    creators_dir = DATA_DIR / "creators"
    if creators_dir.exists():
        for f in creators_dir.glob("*_config.json"):
            creator_id = f.stem.replace("_config", "")
            creators.append(creator_id)
    return creators or ["manel"]


def load_creator_config(creator_id: str) -> Optional[Dict]:
    """Load creator configuration."""
    filepath = DATA_DIR / "creators" / f"{creator_id}_config.json"
    return load_json(filepath)


def save_creator_config(creator_id: str, config: Dict) -> bool:
    """Save creator configuration."""
    filepath = DATA_DIR / "creators" / f"{creator_id}_config.json"
    return save_json(filepath, config)


# =============================================================================
# PRODUCTS
# =============================================================================

def load_products(creator_id: str) -> List[Dict]:
    """Load products for a creator."""
    filepath = DATA_DIR / "products" / f"{creator_id}_products.json"
    return load_json(filepath) or []


def save_products(creator_id: str, products: List[Dict]) -> bool:
    """Save products for a creator."""
    filepath = DATA_DIR / "products" / f"{creator_id}_products.json"
    return save_json(filepath, products)


# =============================================================================
# FOLLOWERS
# =============================================================================

def load_followers(creator_id: str) -> List[Dict]:
    """Load all followers for a creator."""
    followers = []
    followers_dir = DATA_DIR / "followers" / creator_id
    if followers_dir.exists():
        for f in followers_dir.glob("*.json"):
            data = load_json(f)
            if data:
                followers.append(data)
    return followers


def load_follower(creator_id: str, follower_id: str) -> Optional[Dict]:
    """Load a specific follower."""
    filepath = DATA_DIR / "followers" / creator_id / f"{follower_id}.json"
    return load_json(filepath)


def save_follower(creator_id: str, follower_id: str, data: Dict) -> bool:
    """Save follower data."""
    filepath = DATA_DIR / "followers" / creator_id / f"{follower_id}.json"
    return save_json(filepath, data)


# =============================================================================
# ANALYTICS
# =============================================================================

def load_analytics(creator_id: str) -> List[Dict]:
    """Load analytics events for a creator."""
    filepath = DATA_DIR / "analytics" / f"{creator_id}_events.json"
    return load_json(filepath) or []


# =============================================================================
# ESCALATIONS
# =============================================================================

def load_escalations(creator_id: str) -> List[Dict]:
    """Load escalations for a creator."""
    filepath = DATA_DIR / "escalations" / f"{creator_id}_escalations.jsonl"
    return load_jsonl(filepath)


# =============================================================================
# PAYMENTS / REVENUE
# =============================================================================

def load_payments(creator_id: str) -> List[Dict]:
    """Load payment/purchase records for a creator."""
    filepath = DATA_DIR / "payments" / f"{creator_id}_purchases.json"
    return load_json(filepath) or []


# =============================================================================
# CALENDAR / BOOKINGS
# =============================================================================

def load_bookings(creator_id: str) -> List[Dict]:
    """Load calendar bookings for a creator."""
    filepath = DATA_DIR / "calendar" / f"{creator_id}_bookings.json"
    return load_json(filepath) or []


# =============================================================================
# NURTURING
# =============================================================================

def load_nurturing_sequences(creator_id: str) -> List[Dict]:
    """Load nurturing sequences for a creator."""
    filepath = DATA_DIR / "nurturing" / f"{creator_id}_sequences.json"
    return load_json(filepath) or []


def load_nurturing_followups(creator_id: str) -> List[Dict]:
    """Load nurturing followups for a creator."""
    filepath = DATA_DIR / "nurturing" / f"{creator_id}_followups.json"
    return load_json(filepath) or []


# =============================================================================
# COMPUTED METRICS
# =============================================================================

def get_dashboard_metrics(creator_id: str) -> Dict[str, Any]:
    """Compute dashboard metrics for a creator."""
    followers = load_followers(creator_id)
    analytics = load_analytics(creator_id)
    payments = load_payments(creator_id)
    escalations = load_escalations(creator_id)

    # Calculate metrics
    total_followers = len(followers)
    messages_received = len([e for e in analytics if e.get("event_type") == "message_received"])
    messages_sent = len([e for e in analytics if e.get("event_type") == "message_sent"])

    # Response rate
    response_rate = (messages_sent / messages_received * 100) if messages_received > 0 else 0

    # Hot leads (score >= 0.7)
    hot_leads = [f for f in followers if f.get("purchase_intent_score", 0) >= 0.7]

    # Revenue
    total_revenue = sum(p.get("amount", 0) for p in payments if p.get("status") == "completed")

    # Pending escalations
    pending_escalations = [e for e in escalations if e.get("status") == "pending"]

    # Today's activity
    today = datetime.now(timezone.utc).date().isoformat()
    today_messages = [e for e in analytics if e.get("timestamp", "").startswith(today)]
    today_received = len([e for e in today_messages if e.get("event_type") == "message_received"])
    today_sent = len([e for e in today_messages if e.get("event_type") == "message_sent"])

    # Today's revenue
    today_revenue = sum(
        p.get("amount", 0) for p in payments
        if p.get("status") == "completed" and p.get("timestamp", "").startswith(today)
    )
    today_sales = len([
        p for p in payments
        if p.get("status") == "completed" and p.get("timestamp", "").startswith(today)
    ])

    return {
        "total_followers": total_followers,
        "messages_received": messages_received,
        "messages_sent": messages_sent,
        "response_rate": round(response_rate, 1),
        "hot_leads_count": len(hot_leads),
        "hot_leads": hot_leads,
        "total_revenue": total_revenue,
        "pending_escalations": len(pending_escalations),
        "escalations": pending_escalations,
        "today_received": today_received,
        "today_sent": today_sent,
        "today_revenue": today_revenue,
        "today_sales": today_sales,
    }


def get_revenue_metrics(creator_id: str) -> Dict[str, Any]:
    """Compute revenue metrics for a creator."""
    payments = load_payments(creator_id)
    analytics = load_analytics(creator_id)
    followers = load_followers(creator_id)

    # This month
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_str = month_start.strftime("%Y-%m")

    month_payments = [
        p for p in payments
        if p.get("status") == "completed" and p.get("timestamp", "").startswith(month_str)
    ]

    month_revenue = sum(p.get("amount", 0) for p in month_payments)
    month_transactions = len(month_payments)

    # By source
    by_source = {}
    for p in month_payments:
        source = p.get("source", "unknown")
        by_source[source] = by_source.get(source, 0) + p.get("amount", 0)

    # Funnel
    total_messages = len([e for e in analytics if e.get("event_type") == "message_received"])
    total_leads = len([f for f in followers if f.get("purchase_intent_score", 0) > 0.3])
    hot_leads = len([f for f in followers if f.get("purchase_intent_score", 0) >= 0.7])
    customers = len([f for f in followers if f.get("is_customer")])

    return {
        "month_revenue": month_revenue,
        "month_transactions": month_transactions,
        "by_source": by_source,
        "recent_payments": sorted(payments, key=lambda x: x.get("timestamp", ""), reverse=True)[:10],
        "funnel": {
            "messages": total_messages,
            "leads": total_leads,
            "hot": hot_leads,
            "customers": customers
        }
    }


def get_pipeline_data(creator_id: str) -> Dict[str, List[Dict]]:
    """Get leads organized by pipeline stage."""
    followers = load_followers(creator_id)

    pipeline = {
        "new": [],
        "active": [],
        "hot": [],
        "customers": []
    }

    for f in followers:
        score = f.get("purchase_intent_score", 0)
        is_customer = f.get("is_customer", False)
        total_messages = f.get("total_messages", 0)

        if is_customer:
            pipeline["customers"].append(f)
        elif score >= 0.7:
            pipeline["hot"].append(f)
        elif score >= 0.3 or total_messages >= 3:
            pipeline["active"].append(f)
        else:
            pipeline["new"].append(f)

    # Sort each column by score
    for key in pipeline:
        pipeline[key] = sorted(
            pipeline[key],
            key=lambda x: x.get("purchase_intent_score", 0),
            reverse=True
        )

    return pipeline


def get_platform_icon(follower_id: str) -> str:
    """Get platform icon based on follower ID prefix."""
    if follower_id.startswith("ig_"):
        return "📸"
    elif follower_id.startswith("tg_"):
        return "📱"
    elif follower_id.startswith("wa_"):
        return "💬"
    return "👤"


def get_platform_name(follower_id: str) -> str:
    """Get platform name based on follower ID prefix."""
    if follower_id.startswith("ig_"):
        return "Instagram"
    elif follower_id.startswith("tg_"):
        return "Telegram"
    elif follower_id.startswith("wa_"):
        return "WhatsApp"
    return "Unknown"
