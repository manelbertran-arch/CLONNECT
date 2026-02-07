"""
Batch Process Historical DM Conversations.

Processes historical Instagram DM data through the Cognitive Engine modules
to generate RelationshipDNA, extract facts, categorize leads, reconstruct
conversation states, and update lead scoring.

Usage:
    python scripts/batch_process_historical.py --creator stefano_bonanno --dry-run
    python scripts/batch_process_historical.py --creator stefano_bonanno --execute
    python scripts/batch_process_historical.py --creator stefano_bonanno --phase categorize
    python scripts/batch_process_historical.py --creator stefano_bonanno --execute --batch-size 5

Phases (run in order):
    1. collect    - Collect and normalize all conversation data
    2. categorize - Categorize leads (NUEVO/INTERESADO/CALIENTE/CLIENTE/FANTASMA)
    3. states     - Reconstruct conversation states (funnel phases)
    4. dna        - Generate RelationshipDNA for leads with 5+ messages
    5. facts      - Extract facts (prices, links, products, contacts)
    6. patterns   - Analyze writing patterns from Stefan's responses
    7. score      - Recalculate lead scores from full history
    8. validate   - Generate validation report

Environment:
    Requires DATABASE_URL environment variable set.
    Run from backend/ directory or with PYTHONPATH=backend.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"batch_process_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
    ],
)
logger = logging.getLogger("batch_processor")


# =============================================================================
# PHASE 1: DATA COLLECTION & NORMALIZATION
# =============================================================================


def collect_json_followers(creator_id: str) -> Dict[str, List[Dict]]:
    """
    Load all follower conversation data from JSON files.

    Args:
        creator_id: Creator identifier (e.g., 'stefano_bonanno')

    Returns:
        Dict mapping follower_id -> list of messages (chronological)
    """
    data_dir = Path(f"data/followers/{creator_id}")
    followers = {}

    if not data_dir.exists():
        logger.warning(f"Data directory not found: {data_dir}")
        return followers

    json_files = list(data_dir.glob("*.json"))
    logger.info(f"Found {len(json_files)} JSON follower files in {data_dir}")

    for json_file in json_files:
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            follower_id = data.get("follower_id", json_file.stem)
            messages = data.get("last_messages", data.get("messages", []))

            # Normalize message format
            normalized = []
            for msg in messages:
                if isinstance(msg, dict):
                    normalized.append(
                        {
                            "role": msg.get("role", "user"),
                            "content": msg.get("content", ""),
                            "timestamp": msg.get("timestamp", ""),
                        }
                    )

            if normalized:
                followers[follower_id] = {
                    "messages": normalized,
                    "username": data.get("username", follower_id),
                    "name": data.get("name", ""),
                    "is_customer": data.get("is_customer", False),
                    "total_messages": len(normalized),
                    "first_contact": data.get("first_contact", ""),
                    "last_contact": data.get("last_contact", ""),
                    "purchase_intent_score": data.get("purchase_intent_score", 0.0),
                }

        except Exception as e:
            logger.error(f"Error loading {json_file}: {e}")

    logger.info(f"Loaded {len(followers)} followers with conversations")
    return followers


def collect_db_followers(creator_id: str) -> Dict[str, List[Dict]]:
    """
    Load follower data AND messages from PostgreSQL database.

    Queries both the leads table (metadata) and messages table (full history).
    Tags each message with source: 'bot', 'human', or 'user'.

    Returns:
        Dict mapping follower_id -> follower data with messages
    """
    if not os.getenv("DATABASE_URL"):
        logger.warning("DATABASE_URL not set, skipping DB collection")
        return {}

    try:
        from api.models import Creator, Lead, Message
        from api.services.db_service import get_session

        session = get_session()
        if not session:
            return {}

        # Step 0: Resolve creator name to UUID
        creator = session.query(Creator).filter(Creator.name == creator_id).first()
        if not creator:
            logger.warning(f"Creator '{creator_id}' not found in database")
            session.close()
            return {}
        creator_uuid = creator.id
        logger.info(f"Resolved creator '{creator_id}' -> UUID {creator_uuid}")

        # Step 1: Load all leads with metadata
        leads = session.query(Lead).filter(Lead.creator_id == creator_uuid).all()
        lead_map = {}  # lead.id -> lead object
        db_followers = {}

        for lead in leads:
            lead_map[lead.id] = lead
            db_followers[lead.platform_user_id] = {
                "username": lead.username or lead.platform_user_id,
                "name": lead.full_name or "",
                "status": lead.status,
                "email": lead.email,
                "phone": lead.phone,
                "profile_pic_url": lead.profile_pic_url,
                "is_customer": lead.status == "cliente",
                "messages": [],
                "total_messages": 0,
                "first_contact": None,
                "last_contact": None,
                "purchase_intent_score": lead.purchase_intent or 0.0,
            }

        logger.info(f"Loaded {len(db_followers)} leads from database")

        # Step 2: Load ALL messages, ordered by lead and time
        lead_ids = list(lead_map.keys())
        if not lead_ids:
            session.close()
            return db_followers

        total_msgs = 0
        bot_msgs = 0
        human_msgs = 0
        user_msgs = 0

        # Query in batches of 50 leads to avoid huge queries
        batch_size = 50
        for i in range(0, len(lead_ids), batch_size):
            batch_ids = lead_ids[i : i + batch_size]
            messages = (
                session.query(Message)
                .filter(Message.lead_id.in_(batch_ids))
                .order_by(Message.lead_id, Message.created_at)
                .all()
            )

            for msg in messages:
                lead = lead_map.get(msg.lead_id)
                if not lead:
                    continue

                fid = lead.platform_user_id

                # Determine message source
                source = "user"
                if msg.role == "assistant":
                    approved_by = msg.approved_by or ""
                    metadata = msg.msg_metadata or {}
                    is_manual = metadata.get("is_manual", False)

                    if approved_by in ("creator_manual", "creator") or is_manual:
                        # Stefan wrote or approved this himself
                        source = "human"
                        human_msgs += 1
                    elif approved_by == "autopilot" or approved_by == "auto":
                        # Bot auto-generated and auto-sent
                        source = "bot"
                        bot_msgs += 1
                    elif approved_by == "historical_sync":
                        # Synced from Instagram - Stefan's real messages
                        source = "human"
                        human_msgs += 1
                    else:
                        # Unknown origin - likely synced from Instagram (human)
                        source = "human"
                        human_msgs += 1
                else:
                    user_msgs += 1

                normalized_msg = {
                    "role": msg.role or "user",
                    "content": msg.content or "",
                    "timestamp": msg.created_at.isoformat() if msg.created_at else "",
                    "source": source,
                    "intent": msg.intent or "",
                    "approved_by": msg.approved_by or "",
                }

                if fid in db_followers:
                    db_followers[fid]["messages"].append(normalized_msg)
                    total_msgs += 1

        # Step 3: Set first/last contact and total_messages
        for fid, data in db_followers.items():
            msgs = data["messages"]
            data["total_messages"] = len(msgs)
            if msgs:
                data["first_contact"] = msgs[0].get("timestamp", "")
                data["last_contact"] = msgs[-1].get("timestamp", "")

        session.close()

        logger.info(
            f"Loaded {total_msgs} messages from database "
            f"(user={user_msgs}, bot={bot_msgs}, human={human_msgs})"
        )
        return db_followers

    except Exception as e:
        logger.error(f"DB collection failed: {e}")
        import traceback

        traceback.print_exc()
        return {}


def merge_data_sources(json_data: Dict[str, Dict], db_data: Dict[str, Dict]) -> Dict[str, Dict]:
    """
    Merge JSON and DB data sources.

    Priority: DB messages over JSON (DB has full history with source tags).
    JSON is only used as fallback when DB has no messages for a follower.

    Returns:
        Merged follower data dict
    """
    merged = {}

    # Start with DB data (has full message history + source tags)
    for fid, data in db_data.items():
        merged[fid] = data.copy()

    # Add JSON-only followers or use JSON messages as fallback
    for fid, data in json_data.items():
        if fid not in merged:
            # JSON-only follower (not in DB)
            merged[fid] = data.copy()
        elif not merged[fid].get("messages"):
            # DB has lead metadata but no messages - use JSON messages
            merged[fid]["messages"] = data.get("messages", [])
            merged[fid]["total_messages"] = len(merged[fid]["messages"])

    db_with_msgs = sum(1 for d in db_data.values() if d.get("messages"))
    json_only = sum(1 for fid in json_data if fid not in db_data)
    logger.info(
        f"Merged: {db_with_msgs} DB (with msgs) + {json_only} JSON-only "
        f"= {len(merged)} unique followers"
    )
    return merged


def build_conversation_windows(messages: List[Dict], gap_hours: int = 4) -> List[List[Dict]]:
    """
    Group messages into conversation windows based on time gaps.

    Args:
        messages: Chronological list of messages
        gap_hours: Hours of silence that defines a new conversation

    Returns:
        List of conversation windows (each is a list of messages)
    """
    if not messages:
        return []

    windows = []
    current_window = [messages[0]]

    for msg in messages[1:]:
        try:
            prev_ts = current_window[-1].get("timestamp", "")
            curr_ts = msg.get("timestamp", "")

            if prev_ts and curr_ts:
                prev_dt = datetime.fromisoformat(prev_ts.replace("Z", "+00:00"))
                curr_dt = datetime.fromisoformat(curr_ts.replace("Z", "+00:00"))

                if (curr_dt - prev_dt) > timedelta(hours=gap_hours):
                    windows.append(current_window)
                    current_window = []
        except (ValueError, TypeError):
            pass  # If timestamps can't be parsed, keep in same window

        current_window.append(msg)

    if current_window:
        windows.append(current_window)

    return windows


# =============================================================================
# PHASE 2: LEAD CATEGORIZATION
# =============================================================================


def categorize_leads(
    followers: Dict[str, Dict], dry_run: bool = True
) -> Dict[str, Tuple[str, float, str]]:
    """
    Categorize all leads using the lead_categorizer module.

    Returns:
        Dict mapping follower_id -> (category, score, reason)
    """
    from core.lead_categorizer import get_lead_categorizer

    categorizer = get_lead_categorizer()
    results = {}

    for fid, data in followers.items():
        messages = data.get("messages", [])
        if not messages:
            results[fid] = ("nuevo", 0.0, "No messages")
            continue

        try:
            is_customer = data.get("is_customer", False)
            category, score, reason = categorizer.categorize(
                messages=messages, is_customer=is_customer
            )
            results[fid] = (category.value, score, reason)
            logger.debug(f"  {fid}: {category.value} ({score:.2f}) - {reason}")
        except Exception as e:
            logger.error(f"  Categorization failed for {fid}: {e}")
            results[fid] = ("nuevo", 0.0, f"Error: {e}")

    # Summary
    categories = {}
    for _, (cat, _, _) in results.items():
        categories[cat] = categories.get(cat, 0) + 1
    logger.info(f"Categorization results: {categories}")

    if not dry_run:
        _save_categories_to_db(results)

    return results


def _save_categories_to_db(results: Dict[str, Tuple[str, float, str]]) -> None:
    """Save lead categories to database."""
    if not os.getenv("DATABASE_URL"):
        logger.warning("DATABASE_URL not set, skipping DB save")
        return

    try:
        from api.models import Lead
        from api.services.db_service import get_session

        session = get_session()
        if not session:
            return

        updated = 0
        for fid, (category, score, reason) in results.items():
            lead = session.query(Lead).filter(Lead.platform_user_id == fid).first()
            if lead:
                lead.status = category
                updated += 1

        session.commit()
        session.close()
        logger.info(f"Updated {updated} lead categories in database")
    except Exception as e:
        logger.error(f"Failed to save categories: {e}")


# =============================================================================
# PHASE 3: CONVERSATION STATE RECONSTRUCTION
# =============================================================================


def reconstruct_states(
    followers: Dict[str, Dict], creator_id: str, dry_run: bool = True
) -> Dict[str, str]:
    """
    Reconstruct conversation states (funnel phases) from history.

    Returns:
        Dict mapping follower_id -> current_phase
    """
    try:
        from core.conversation_state import get_state_manager
    except ImportError:
        logger.warning("conversation_state module not available, skipping")
        return {}

    state_mgr = get_state_manager()
    results = {}

    for fid, data in followers.items():
        messages = data.get("messages", [])
        if not messages:
            results[fid] = "initial"
            continue

        try:
            windows = build_conversation_windows(messages)
            current_phase = "initial"

            for window in windows:
                state = state_mgr.get_state(fid, creator_id)
                current_phase = (
                    state.phase.value if hasattr(state.phase, "value") else str(state.phase)
                )

            results[fid] = current_phase
            logger.debug(f"  {fid}: phase={current_phase} ({len(windows)} conversations)")
        except Exception as e:
            logger.error(f"  State reconstruction failed for {fid}: {e}")
            results[fid] = "unknown"

    # Summary
    phases = {}
    for _, phase in results.items():
        phases[phase] = phases.get(phase, 0) + 1
    logger.info(f"State reconstruction results: {phases}")

    return results


# =============================================================================
# PHASE 4: RELATIONSHIP DNA GENERATION
# =============================================================================


def generate_dna(
    followers: Dict[str, Dict],
    creator_id: str,
    min_messages: int = 5,
    dry_run: bool = True,
) -> Dict[str, Dict]:
    """
    Generate RelationshipDNA for followers with sufficient history.

    Args:
        followers: Follower data dict
        creator_id: Creator identifier
        min_messages: Minimum messages required for DNA generation
        dry_run: If True, don't persist to database

    Returns:
        Dict mapping follower_id -> DNA profile dict
    """
    try:
        from services.relationship_analyzer import RelationshipAnalyzer
    except ImportError:
        logger.warning("relationship_analyzer not available, skipping DNA generation")
        return {}

    analyzer = RelationshipAnalyzer()
    results = {}
    eligible = 0
    generated = 0

    for fid, data in followers.items():
        messages = data.get("messages", [])
        if len(messages) < min_messages:
            continue

        eligible += 1

        try:
            # Use last 20 messages for DNA
            recent_messages = messages[-20:]
            dna = analyzer.analyze(
                creator_id=creator_id,
                follower_id=fid,
                messages=recent_messages,
            )

            if dna:
                results[fid] = dna if isinstance(dna, dict) else {"raw": str(dna)}
                generated += 1
                logger.debug(f"  DNA generated for {fid}")
        except Exception as e:
            logger.error(f"  DNA generation failed for {fid}: {e}")

    logger.info(
        f"DNA generation: {eligible} eligible, {generated} generated "
        f"(min {min_messages} messages required)"
    )

    return results


# =============================================================================
# PHASE 5: FACT EXTRACTION
# =============================================================================


FACT_PATTERNS = {
    "PRICE_GIVEN": r"\d+\s*€|\d+\s*euros?|\$\d+|\d+\s*dólares?",
    "LINK_SHARED": r"https?://\S+",
    "CONTACT_EMAIL": r"[\w.-]+@[\w.-]+\.\w+",
    "CONTACT_PHONE": r"\+?\d{9,}",
    "CONTACT_INSTAGRAM": r"@\w{3,}",
    "APPOINTMENT": r"(?:mañana|lunes|martes|miércoles|jueves|viernes|sábado|domingo)\s+a\s+las?\s+\d+",
}


def extract_facts(followers: Dict[str, Dict]) -> Dict[str, List[Dict]]:
    """
    Extract structured facts from all conversations.

    Returns:
        Dict mapping follower_id -> list of fact dicts
    """
    results = {}
    total_facts = 0

    for fid, data in followers.items():
        messages = data.get("messages", [])
        facts = []

        for msg in messages:
            content = msg.get("content", "")
            role = msg.get("role", "user")
            timestamp = msg.get("timestamp", "")

            for fact_type, pattern in FACT_PATTERNS.items():
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    facts.append(
                        {
                            "type": fact_type,
                            "value": match[:200],
                            "message_preview": content[:100],
                            "role": role,
                            "timestamp": timestamp,
                        }
                    )

        if facts:
            results[fid] = facts
            total_facts += len(facts)

    # Summary by type
    type_counts = {}
    for _, facts in results.items():
        for fact in facts:
            ft = fact["type"]
            type_counts[ft] = type_counts.get(ft, 0) + 1

    logger.info(f"Fact extraction: {total_facts} facts from {len(results)} followers")
    logger.info(f"  By type: {type_counts}")

    return results


# =============================================================================
# PHASE 6: WRITING PATTERN ANALYSIS
# =============================================================================


def _analyze_message_set(messages: List[str], label: str) -> Dict[str, Any]:
    """Analyze writing patterns for a set of messages."""
    if not messages:
        return {}

    lengths = [len(m) for m in messages if m]
    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"
        "\U0001f300-\U0001f5ff"
        "\U0001f680-\U0001f6ff"
        "\U0001f1e0-\U0001f1ff"
        "\U00002702-\U000027b0"
        "]+",
        flags=re.UNICODE,
    )
    emoji_msgs = sum(1 for m in messages if emoji_pattern.search(m))

    # Common bigrams (3+ occurrences)
    phrase_counts: Dict[str, int] = {}
    for msg in messages:
        words = msg.lower().split()
        for i in range(len(words) - 1):
            bigram = f"{words[i]} {words[i + 1]}"
            phrase_counts[bigram] = phrase_counts.get(bigram, 0) + 1

    common_phrases = {
        phrase: count
        for phrase, count in sorted(phrase_counts.items(), key=lambda x: x[1], reverse=True)[:20]
        if count >= 3
    }

    result = {
        "total_messages": len(messages),
        "avg_length": sum(lengths) / len(lengths) if lengths else 0,
        "min_length": min(lengths) if lengths else 0,
        "max_length": max(lengths) if lengths else 0,
        "median_length": sorted(lengths)[len(lengths) // 2] if lengths else 0,
        "emoji_frequency": emoji_msgs / len(messages),
        "common_phrases": common_phrases,
        "exclamation_rate": sum(1 for m in messages if "!" in m) / len(messages),
        "question_rate": sum(1 for m in messages if "?" in m) / len(messages),
    }

    logger.info(
        f"  [{label}] {result['total_messages']} msgs, "
        f"avg={result['avg_length']:.0f} chars, "
        f"emoji={result['emoji_frequency']:.1%}, "
        f"questions={result['question_rate']:.1%}"
    )
    return result


def analyze_writing_patterns(followers: Dict[str, Dict]) -> Dict[str, Any]:
    """
    Analyze writing patterns, separating HUMAN Stefan from BOT messages.

    Uses the 'source' field set by collect_db_followers():
      - source='human' → Stefan wrote this manually (creator_manual/creator)
      - source='bot'   → Bot generated this (autopilot)
      - No source tag  → Legacy JSON data (cannot distinguish)

    Returns:
        Dict with pattern analysis for human, bot, and combined
    """
    human_messages = []
    bot_messages = []
    all_assistant = []

    for _, data in followers.items():
        for msg in data.get("messages", []):
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", "")
            if not content:
                continue

            all_assistant.append(content)
            source = msg.get("source", "")

            if source == "human":
                human_messages.append(content)
            elif source == "bot":
                bot_messages.append(content)
            # No source tag = legacy JSON, counted in all_assistant only

    logger.info(
        f"Writing patterns: {len(all_assistant)} total assistant msgs "
        f"(human={len(human_messages)}, bot={len(bot_messages)}, "
        f"untagged={len(all_assistant) - len(human_messages) - len(bot_messages)})"
    )

    results = {
        "human_stefan": _analyze_message_set(human_messages, "HUMAN Stefan"),
        "bot": _analyze_message_set(bot_messages, "BOT"),
        "combined": _analyze_message_set(all_assistant, "ALL assistant"),
        "breakdown": {
            "total_assistant": len(all_assistant),
            "human_count": len(human_messages),
            "bot_count": len(bot_messages),
            "untagged_count": len(all_assistant) - len(human_messages) - len(bot_messages),
            "human_pct": len(human_messages) / len(all_assistant) if all_assistant else 0,
        },
    }

    return results


# =============================================================================
# PHASE 7: LEAD SCORING UPDATE
# =============================================================================


def update_lead_scores(followers: Dict[str, Dict], dry_run: bool = True) -> Dict[str, float]:
    """
    Recalculate lead scores based on full conversation history.

    Returns:
        Dict mapping follower_id -> new_score
    """
    try:
        from services import IntentClassifier, LeadService
    except ImportError:
        logger.warning("IntentClassifier/LeadService not available, skipping scoring")
        return {}

    classifier = IntentClassifier()
    lead_service = LeadService()
    results = {}

    for fid, data in followers.items():
        messages = data.get("messages", [])
        user_messages = [m for m in messages if m.get("role") == "user"]

        if not user_messages:
            results[fid] = 0.0
            continue

        score = data.get("purchase_intent_score", 0.0)
        for msg in user_messages:
            try:
                intent = classifier.classify(msg.get("content", ""))
                intent_val = intent.value if hasattr(intent, "value") else str(intent)
                score = lead_service.calculate_intent_score(
                    current_score=score,
                    intent=intent_val.upper(),
                    has_direct_purchase_keywords=False,
                )
            except Exception:
                pass

        results[fid] = score
        original = data.get("purchase_intent_score", 0.0)
        if abs(score - original) > 0.1:
            logger.debug(f"  {fid}: score {original:.2f} -> {score:.2f}")

    # Score distribution
    score_ranges = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
    for _, score in results.items():
        if score < 0.2:
            score_ranges["0.0-0.2"] += 1
        elif score < 0.4:
            score_ranges["0.2-0.4"] += 1
        elif score < 0.6:
            score_ranges["0.4-0.6"] += 1
        elif score < 0.8:
            score_ranges["0.6-0.8"] += 1
        else:
            score_ranges["0.8-1.0"] += 1

    logger.info(f"Lead scoring distribution: {score_ranges}")

    if not dry_run:
        _save_scores_to_db(results)

    return results


def _save_scores_to_db(results: Dict[str, float]) -> None:
    """Save updated lead scores to database."""
    if not os.getenv("DATABASE_URL"):
        return

    try:
        from api.models import Lead
        from api.services.db_service import get_session

        session = get_session()
        if not session:
            return

        updated = 0
        for fid, score in results.items():
            lead = session.query(Lead).filter(Lead.platform_user_id == fid).first()
            if lead:
                lead.purchase_intent_score = score
                updated += 1

        session.commit()
        session.close()
        logger.info(f"Updated {updated} lead scores in database")
    except Exception as e:
        logger.error(f"Failed to save scores: {e}")


# =============================================================================
# PHASE 8: VALIDATION & REPORTING
# =============================================================================


def generate_report(
    followers: Dict[str, Dict],
    categories: Dict[str, Tuple[str, float, str]],
    states: Dict[str, str],
    dna_results: Dict[str, Dict],
    facts: Dict[str, List[Dict]],
    patterns: Dict[str, Any],
    scores: Dict[str, float],
    elapsed: float,
) -> Dict[str, Any]:
    """Generate comprehensive ingestion report."""
    total_messages = sum(len(data.get("messages", [])) for data in followers.values())
    total_facts = sum(len(f) for f in facts.values())

    # Category distribution
    cat_dist = {}
    for _, (cat, _, _) in categories.items():
        cat_dist[cat] = cat_dist.get(cat, 0) + 1

    # Phase distribution
    phase_dist = {}
    for _, phase in states.items():
        phase_dist[phase] = phase_dist.get(phase, 0) + 1

    report = {
        "timestamp": datetime.now().isoformat(),
        "creator_id": "stefano_bonanno",
        "summary": {
            "total_followers": len(followers),
            "total_messages": total_messages,
            "followers_with_messages": sum(1 for d in followers.values() if d.get("messages")),
            "processing_time_seconds": round(elapsed, 1),
        },
        "categorization": {
            "total_categorized": len(categories),
            "distribution": cat_dist,
        },
        "conversation_states": {
            "total_reconstructed": len(states),
            "distribution": phase_dist,
        },
        "dna_generation": {
            "total_generated": len(dna_results),
            "min_messages_required": 5,
        },
        "fact_extraction": {
            "total_facts": total_facts,
            "followers_with_facts": len(facts),
            "by_type": {},
        },
        "writing_patterns": patterns,
        "lead_scoring": {
            "total_scored": len(scores),
            "avg_score": sum(scores.values()) / len(scores) if scores else 0,
        },
    }

    # Fact type breakdown
    for fid_facts in facts.values():
        for fact in fid_facts:
            ft = fact["type"]
            report["fact_extraction"]["by_type"][ft] = (
                report["fact_extraction"]["by_type"].get(ft, 0) + 1
            )

    return report


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================


def main():
    parser = argparse.ArgumentParser(
        description="Batch process historical DM conversations through Cognitive Engine"
    )
    parser.add_argument(
        "--creator",
        required=True,
        help="Creator ID (e.g., stefano_bonanno)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Run without persisting changes (default: True)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute and persist changes to database",
    )
    parser.add_argument(
        "--phase",
        choices=[
            "collect",
            "categorize",
            "states",
            "dna",
            "facts",
            "patterns",
            "score",
            "validate",
            "all",
        ],
        default="all",
        help="Run specific phase only (default: all)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Process followers in batches of N (default: 10)",
    )
    parser.add_argument(
        "--min-messages",
        type=int,
        default=5,
        help="Minimum messages for DNA generation (default: 5)",
    )

    args = parser.parse_args()
    dry_run = not args.execute

    if dry_run:
        logger.info("=" * 60)
        logger.info("DRY RUN MODE - No changes will be persisted")
        logger.info("=" * 60)
    else:
        logger.info("=" * 60)
        logger.info("EXECUTE MODE - Changes WILL be persisted to database")
        logger.info("=" * 60)

    start_time = time.time()
    creator_id = args.creator
    run_phase = args.phase

    # ─────────────────────────────────────────────────────
    # PHASE 1: COLLECT
    # ─────────────────────────────────────────────────────
    logger.info("\n" + "=" * 60)
    logger.info("PHASE 1: DATA COLLECTION & NORMALIZATION")
    logger.info("=" * 60)

    json_data = collect_json_followers(creator_id)
    db_data = collect_db_followers(creator_id)
    followers = merge_data_sources(json_data, db_data)

    if not followers:
        logger.error("No follower data found. Exiting.")
        sys.exit(1)

    logger.info(f"Total followers to process: {len(followers)}")

    if run_phase == "collect":
        logger.info("Phase 'collect' complete. Exiting.")
        return

    # ─────────────────────────────────────────────────────
    # PHASE 2: CATEGORIZE
    # ─────────────────────────────────────────────────────
    categories = {}
    if run_phase in ("all", "categorize"):
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 2: LEAD CATEGORIZATION")
        logger.info("=" * 60)
        categories = categorize_leads(followers, dry_run=dry_run)

        if run_phase == "categorize":
            return

    # ─────────────────────────────────────────────────────
    # PHASE 3: STATES
    # ─────────────────────────────────────────────────────
    states = {}
    if run_phase in ("all", "states"):
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 3: CONVERSATION STATE RECONSTRUCTION")
        logger.info("=" * 60)
        states = reconstruct_states(followers, creator_id, dry_run=dry_run)

        if run_phase == "states":
            return

    # ─────────────────────────────────────────────────────
    # PHASE 4: DNA
    # ─────────────────────────────────────────────────────
    dna_results = {}
    if run_phase in ("all", "dna"):
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 4: RELATIONSHIP DNA GENERATION")
        logger.info("=" * 60)
        dna_results = generate_dna(
            followers, creator_id, min_messages=args.min_messages, dry_run=dry_run
        )

        if run_phase == "dna":
            return

    # ─────────────────────────────────────────────────────
    # PHASE 5: FACTS
    # ─────────────────────────────────────────────────────
    facts = {}
    if run_phase in ("all", "facts"):
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 5: FACT EXTRACTION")
        logger.info("=" * 60)
        facts = extract_facts(followers)

        if run_phase == "facts":
            return

    # ─────────────────────────────────────────────────────
    # PHASE 6: PATTERNS
    # ─────────────────────────────────────────────────────
    patterns = {}
    if run_phase in ("all", "patterns"):
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 6: WRITING PATTERN ANALYSIS")
        logger.info("=" * 60)
        patterns = analyze_writing_patterns(followers)

        if run_phase == "patterns":
            return

    # ─────────────────────────────────────────────────────
    # PHASE 7: SCORE
    # ─────────────────────────────────────────────────────
    scores = {}
    if run_phase in ("all", "score"):
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 7: LEAD SCORING UPDATE")
        logger.info("=" * 60)
        scores = update_lead_scores(followers, dry_run=dry_run)

        if run_phase == "score":
            return

    # ─────────────────────────────────────────────────────
    # PHASE 8: VALIDATE
    # ─────────────────────────────────────────────────────
    elapsed = time.time() - start_time

    logger.info("\n" + "=" * 60)
    logger.info("PHASE 8: VALIDATION & REPORT")
    logger.info("=" * 60)

    report = generate_report(
        followers=followers,
        categories=categories,
        states=states,
        dna_results=dna_results,
        facts=facts,
        patterns=patterns,
        scores=scores,
        elapsed=elapsed,
    )

    # Save report
    report_path = f"reports/batch_ingestion_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    os.makedirs("reports", exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    logger.info(f"\nReport saved to: {report_path}")
    logger.info(f"Total processing time: {elapsed:.1f}s")

    # Print summary
    print("\n" + "=" * 60)
    print("INGESTION SUMMARY")
    print("=" * 60)
    print(f"Followers processed:  {report['summary']['total_followers']}")
    print(f"Messages processed:   {report['summary']['total_messages']}")
    print(f"Leads categorized:    {report['categorization']['total_categorized']}")
    print(f"States reconstructed: {report['conversation_states']['total_reconstructed']}")
    print(f"DNA profiles created: {report['dna_generation']['total_generated']}")
    print(f"Facts extracted:      {report['fact_extraction']['total_facts']}")
    print(f"Leads scored:         {report['lead_scoring']['total_scored']}")
    print(f"Processing time:      {elapsed:.1f}s")
    print(f"Mode:                 {'DRY RUN' if dry_run else 'EXECUTED'}")

    # Writing pattern breakdown
    wp = report.get("writing_patterns", {})
    breakdown = wp.get("breakdown", {})
    if breakdown:
        print("\nMessage Source Breakdown:")
        print(f"  Human Stefan:       {breakdown.get('human_count', 0)}")
        print(f"  Bot (autopilot):    {breakdown.get('bot_count', 0)}")
        print(f"  Untagged (legacy):  {breakdown.get('untagged_count', 0)}")
        print(f"  Human %:            {breakdown.get('human_pct', 0):.1%}")

    print("=" * 60)


if __name__ == "__main__":
    main()
