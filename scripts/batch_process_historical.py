#!/usr/bin/env python3
"""
Batch Historical Conversation Processor for Clonnect Cognitive Engine v3.0

Processes 6 months of Stefan's Instagram DM conversations through all
cognitive modules to generate:
- Lead categorizations
- Conversation states
- RelationshipDNA profiles
- Fact timelines
- Writing pattern analysis
- Lead scores

Usage:
    python scripts/batch_process_historical.py --creator stefano_bonanno --dry-run
    python scripts/batch_process_historical.py --creator stefano_bonanno --phase all
    python scripts/batch_process_historical.py --creator stefano_bonanno --phase categorize
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"batch_process_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
    ],
)
logger = logging.getLogger("batch_processor")


class BatchProcessor:
    """Main batch processor for historical conversations."""

    def __init__(self, creator_id: str, dry_run: bool = False):
        self.creator_id = creator_id
        self.dry_run = dry_run
        self.stats = {
            "leads_processed": 0,
            "states_reconstructed": 0,
            "dna_generated": 0,
            "facts_extracted": 0,
            "errors": [],
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        self._init_services()

    def _init_services(self):
        """Initialize all cognitive services."""
        logger.info(f"Initializing services for {self.creator_id}...")

        # Lead categorizer (keyword-based, no LLM)
        try:
            from core.lead_categorizer import get_lead_categorizer

            self.categorizer = get_lead_categorizer()
            logger.info("  Lead categorizer: OK")
        except Exception as e:
            logger.warning(f"  Lead categorizer: FAILED ({e})")
            self.categorizer = None

        # Conversation state machine (PostgreSQL-backed)
        try:
            from core.conversation_state import get_state_manager

            self.state_manager = get_state_manager()
            logger.info("  State manager: OK")
        except Exception as e:
            logger.warning(f"  State manager: FAILED ({e})")
            self.state_manager = None

        # Relationship type detector (keyword scoring)
        try:
            from services.relationship_type_detector import RelationshipTypeDetector

            self.relationship_detector = RelationshipTypeDetector()
            logger.info("  Relationship detector: OK")
        except Exception as e:
            logger.warning(f"  Relationship detector: FAILED ({e})")
            self.relationship_detector = None

        # Relationship analyzer (full DNA generation)
        try:
            from services.relationship_analyzer import RelationshipAnalyzer

            self.relationship_analyzer = RelationshipAnalyzer()
            logger.info("  Relationship analyzer: OK")
        except Exception as e:
            logger.warning(f"  Relationship analyzer: FAILED ({e})")
            self.relationship_analyzer = None

        # DNA service (orchestrates DNA storage and retrieval)
        try:
            from services.relationship_dna_service import get_dna_service

            self.dna_service = get_dna_service()
            logger.info("  DNA service: OK")
        except Exception as e:
            logger.warning(f"  DNA service: FAILED ({e})")
            self.dna_service = None

        # DNA update triggers (determines when re-analysis is needed)
        try:
            from services.dna_update_triggers import get_dna_triggers

            self.dna_triggers = get_dna_triggers()
            logger.info("  DNA triggers: OK")
        except Exception as e:
            logger.warning(f"  DNA triggers: FAILED ({e})")
            self.dna_triggers = None

        # Intent classifier (keyword-based, from services)
        try:
            from services.intent_service import IntentClassifier

            self.intent_classifier = IntentClassifier()
            logger.info("  Intent classifier (services): OK")
        except Exception as e:
            logger.warning(f"  Intent classifier (services): FAILED ({e})")
            self.intent_classifier = None

        # Intent classifier (LLM-based, from core)
        try:
            from core.intent_classifier import IntentClassifier as CoreIntentClassifier

            self.core_intent_classifier = CoreIntentClassifier()
            logger.info("  Intent classifier (core/LLM): OK")
        except Exception as e:
            logger.warning(f"  Intent classifier (core/LLM): FAILED ({e})")
            self.core_intent_classifier = None

    def load_leads(self) -> List[Dict]:
        """Load all leads for the creator from the database."""
        logger.info(f"Loading leads for {self.creator_id}...")
        try:
            from api.services.db_service import get_session
            from api.models import Creator, Lead

            session = get_session()
            if not session:
                logger.warning("No database session available, falling back to JSON")
                return self._load_leads_from_json()

            try:
                creator = session.query(Creator).filter_by(name=self.creator_id).first()
                if not creator:
                    logger.error(f"Creator {self.creator_id} not found in database")
                    return []

                leads = session.query(Lead).filter_by(creator_id=creator.id).all()
                result = []
                for lead in leads:
                    result.append({
                        "id": str(lead.id),
                        "platform_user_id": lead.platform_user_id,
                        "username": lead.username,
                        "full_name": lead.full_name,
                        "status": lead.status,
                        "score": lead.score,
                        "purchase_intent": lead.purchase_intent,
                        "first_contact_at": str(lead.first_contact_at) if lead.first_contact_at else None,
                        "last_contact_at": str(lead.last_contact_at) if lead.last_contact_at else None,
                    })
                logger.info(f"Loaded {len(result)} leads from database")
                return result
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Database load failed: {e}, falling back to JSON")
            return self._load_leads_from_json()

    def _load_leads_from_json(self) -> List[Dict]:
        """Fallback: load leads from JSON files."""
        data_dir = Path(__file__).parent.parent / "backend" / "data" / "followers" / self.creator_id
        if not data_dir.exists():
            logger.error(f"Data directory not found: {data_dir}")
            return []

        leads = []
        for f in data_dir.glob("*.json"):
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    leads.append(data)
            except Exception as e:
                logger.warning(f"Failed to load {f.name}: {e}")
        logger.info(f"Loaded {len(leads)} leads from JSON files")
        return leads

    def load_messages(self, lead_id: str = None, platform_user_id: str = None) -> List[Dict]:
        """Load messages for a specific lead from PostgreSQL."""
        try:
            from api.services.db_service import get_session
            from api.models import Message

            session = get_session()
            if not session:
                return []
            try:
                query = session.query(Message)
                if lead_id:
                    query = query.filter(Message.lead_id == lead_id)
                messages = query.order_by(Message.created_at.asc()).all()
                return [
                    {
                        "role": m.role,
                        "content": m.content,
                        "intent": m.intent,
                        "created_at": str(m.created_at) if m.created_at else None,
                    }
                    for m in messages
                ]
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"DB message load failed: {e}")
            return []

    # =========================================================================
    # PHASE 1: LEAD CATEGORIZATION
    # =========================================================================

    def phase_categorize_leads(self, leads: List[Dict]):
        """Categorize all leads using the lead_categorizer module.

        Uses keyword-based scoring to assign each lead a funnel category:
        NUEVO, INTERESADO, CALIENTE, CLIENTE, or FANTASMA.
        """
        logger.info("=" * 60)
        logger.info("PHASE 1: Lead Categorization")
        logger.info("=" * 60)

        if not self.categorizer:
            logger.error("Lead categorizer not available, skipping phase 1")
            return

        for i, lead in enumerate(leads):
            try:
                messages = self.load_messages(lead_id=lead.get("id"))
                if not messages:
                    continue

                # Parse timestamps for ghost detection
                last_user_msg_time = None
                last_bot_msg_time = None
                for msg in reversed(messages):
                    ts = msg.get("created_at")
                    if ts and msg["role"] == "user" and not last_user_msg_time:
                        try:
                            last_user_msg_time = datetime.fromisoformat(
                                str(ts).replace("Z", "+00:00")
                            )
                        except (ValueError, TypeError):
                            pass
                    if ts and msg["role"] == "assistant" and not last_bot_msg_time:
                        try:
                            last_bot_msg_time = datetime.fromisoformat(
                                str(ts).replace("Z", "+00:00")
                            )
                        except (ValueError, TypeError):
                            pass
                    if last_user_msg_time and last_bot_msg_time:
                        break

                category, score, reason = self.categorizer.categorize(
                    messages=messages,
                    is_customer=lead.get("status") == "cliente",
                    last_user_message_time=last_user_msg_time,
                    last_bot_message_time=last_bot_msg_time,
                )

                logger.info(
                    f"  [{i+1}/{len(leads)}] {lead.get('username', 'unknown')}: "
                    f"{category.value} (score={score:.2f}) - {reason}"
                )

                if not self.dry_run:
                    # TODO: Update lead.status and lead.purchase_intent in database
                    pass

                self.stats["leads_processed"] += 1

            except Exception as e:
                logger.error(f"  Error categorizing {lead.get('username')}: {e}")
                self.stats["errors"].append(f"categorize:{lead.get('username')}:{e}")

    # =========================================================================
    # PHASE 2: CONVERSATION STATE RECONSTRUCTION
    # =========================================================================

    def phase_reconstruct_states(self, leads: List[Dict]):
        """Reconstruct conversation states by replaying message history.

        Replays each conversation through the state machine to reconstruct
        the sales funnel phase: INICIO -> CUALIFICACION -> DESCUBRIMIENTO ->
        PROPUESTA -> OBJECIONES -> CIERRE.
        """
        logger.info("=" * 60)
        logger.info("PHASE 2: Conversation State Reconstruction")
        logger.info("=" * 60)

        if not self.state_manager:
            logger.error("State manager not available, skipping phase 2")
            return

        for i, lead in enumerate(leads):
            try:
                messages = self.load_messages(lead_id=lead.get("id"))
                if not messages:
                    continue

                follower_id = lead.get("platform_user_id", "")

                # Get initial state (creates new if not found)
                state = self.state_manager.get_state(follower_id, self.creator_id)

                # Replay messages chronologically to reconstruct state
                pending_response = ""
                for j, msg in enumerate(messages):
                    if msg["role"] == "user":
                        # Classify intent for state transition
                        intent = msg.get("intent") or "other"
                        if not msg.get("intent") and self.intent_classifier:
                            classified = self.intent_classifier.classify(msg["content"])
                            intent = classified.value if hasattr(classified, "value") else str(classified)

                        # Look ahead for the assistant response
                        response = ""
                        if j + 1 < len(messages) and messages[j + 1]["role"] == "assistant":
                            response = messages[j + 1]["content"]

                        if not self.dry_run:
                            self.state_manager.update_state(
                                state=state,
                                message=msg["content"],
                                intent=intent,
                                response=response,
                            )

                logger.info(
                    f"  [{i+1}/{len(leads)}] {lead.get('username', 'unknown')}: "
                    f"phase={state.phase.value}, messages={state.message_count}"
                )

                self.stats["states_reconstructed"] += 1

            except Exception as e:
                logger.error(f"  Error reconstructing state for {lead.get('username')}: {e}")
                self.stats["errors"].append(f"state:{lead.get('username')}:{e}")

    # =========================================================================
    # PHASE 3: RELATIONSHIP DNA GENERATION
    # =========================================================================

    def phase_generate_dna(self, leads: List[Dict]):
        """Generate RelationshipDNA for leads with sufficient messages.

        Uses RelationshipAnalyzer for full analysis and RelationshipTypeDetector
        for type classification. Only processes leads with >= 5 messages.
        """
        logger.info("=" * 60)
        logger.info("PHASE 3: RelationshipDNA Generation")
        logger.info("=" * 60)

        MIN_MESSAGES = 5
        processed = 0
        skipped = 0

        for i, lead in enumerate(leads):
            try:
                messages = self.load_messages(lead_id=lead.get("id"))
                if len(messages) < MIN_MESSAGES:
                    skipped += 1
                    continue

                follower_id = lead.get("platform_user_id", "")

                # Detect relationship type (keyword scoring)
                rel_type = "DESCONOCIDO"
                rel_conf = 0.0
                if self.relationship_detector:
                    rel_result = self.relationship_detector.detect(messages)
                    rel_type = rel_result.get("type", "DESCONOCIDO")
                    rel_conf = rel_result.get("confidence", 0.0)

                # Run full relationship analysis
                dna = None
                if self.relationship_analyzer and not self.dry_run:
                    dna = self.relationship_analyzer.analyze(
                        creator_id=self.creator_id,
                        follower_id=follower_id,
                        messages=messages,
                    )

                # Persist via DNA service
                if self.dna_service and dna and not self.dry_run:
                    self.dna_service.analyze_and_update_dna(
                        creator_id=self.creator_id,
                        follower_id=follower_id,
                        messages=messages,
                    )

                logger.info(
                    f"  [{i+1}/{len(leads)}] {lead.get('username', 'unknown')}: "
                    f"type={rel_type} (conf={rel_conf:.2f}), msgs={len(messages)}"
                    + (f", trust={dna.get('trust_score', 0):.2f}" if dna else "")
                )

                processed += 1
                self.stats["dna_generated"] += 1

            except Exception as e:
                logger.error(f"  Error generating DNA for {lead.get('username')}: {e}")
                self.stats["errors"].append(f"dna:{lead.get('username')}:{e}")

        logger.info(f"  Processed: {processed}, Skipped (< {MIN_MESSAGES} msgs): {skipped}")

    # =========================================================================
    # PHASE 4: FACT EXTRACTION
    # =========================================================================

    def phase_extract_facts(self, leads: List[Dict]):
        """Extract facts (prices, links, topics, dates) from all conversations.

        Scans assistant messages for price mentions, shared links, and
        other actionable facts to build a fact timeline per lead.
        """
        logger.info("=" * 60)
        logger.info("PHASE 4: Fact Extraction")
        logger.info("=" * 60)

        price_pattern = re.compile(r"\d+\s*\u20ac|\d+\s*euros?|\$\d+", re.IGNORECASE)
        link_pattern = re.compile(r"https?://[^\s<>\"')\\]+")
        date_pattern = re.compile(
            r"\b\d{1,2}\s+de\s+(?:enero|febrero|marzo|abril|mayo|junio|"
            r"julio|agosto|septiembre|octubre|noviembre|diciembre)\b",
            re.IGNORECASE,
        )

        total_facts = {"PRICE_GIVEN": 0, "LINK_SHARED": 0, "DATE_MENTIONED": 0}
        all_facts_by_lead: Dict[str, List[Dict]] = {}

        for i, lead in enumerate(leads):
            try:
                messages = self.load_messages(lead_id=lead.get("id"))
                lead_facts = []

                for msg in messages:
                    facts = []
                    content = msg.get("content", "")

                    # Check assistant messages for facts shared with user
                    if msg["role"] == "assistant":
                        if price_pattern.search(content):
                            facts.append("PRICE_GIVEN")
                            total_facts["PRICE_GIVEN"] += 1
                        if link_pattern.search(content):
                            facts.append("LINK_SHARED")
                            total_facts["LINK_SHARED"] += 1

                    # Check all messages for date mentions
                    if date_pattern.search(content):
                        facts.append("DATE_MENTIONED")
                        total_facts["DATE_MENTIONED"] += 1

                    if facts:
                        lead_facts.append({
                            "timestamp": msg.get("created_at"),
                            "role": msg["role"],
                            "facts": facts,
                            "content_preview": content[:100],
                        })

                if lead_facts:
                    username = lead.get("username", "unknown")
                    all_facts_by_lead[username] = lead_facts
                    logger.info(
                        f"  [{i+1}/{len(leads)}] {username}: "
                        f"{len(lead_facts)} fact events"
                    )
                    self.stats["facts_extracted"] += len(lead_facts)

            except Exception as e:
                logger.error(f"  Error extracting facts for {lead.get('username')}: {e}")
                self.stats["errors"].append(f"facts:{lead.get('username')}:{e}")

        logger.info(f"  Total facts: {total_facts}")

        # Save facts to file for analysis
        if not self.dry_run and all_facts_by_lead:
            facts_file = Path(__file__).parent / f"facts_{self.creator_id}.json"
            with open(facts_file, "w") as f:
                json.dump(all_facts_by_lead, f, indent=2, default=str)
            logger.info(f"  Facts saved to: {facts_file}")

    # =========================================================================
    # PHASE 5: WRITING PATTERN ANALYSIS
    # =========================================================================

    def phase_analyze_patterns(self, leads: List[Dict]):
        """Analyze Stefan's writing patterns from all assistant messages.

        Computes statistics on message length, question frequency, emoji usage,
        common phrases, and response style to inform tone profile tuning.
        """
        logger.info("=" * 60)
        logger.info("PHASE 5: Writing Pattern Analysis")
        logger.info("=" * 60)

        all_assistant_messages: List[str] = []
        all_user_messages: List[str] = []

        for lead in leads:
            messages = self.load_messages(lead_id=lead.get("id"))
            for msg in messages:
                if msg["role"] == "assistant":
                    all_assistant_messages.append(msg["content"])
                elif msg["role"] == "user":
                    all_user_messages.append(msg["content"])

        if not all_assistant_messages:
            logger.warning("No assistant messages found for pattern analysis")
            return

        # Calculate basic stats
        lengths = [len(m) for m in all_assistant_messages]
        question_count = sum(1 for m in all_assistant_messages if "?" in m)
        emoji_count = sum(
            1 for m in all_assistant_messages if any(ord(c) > 127000 for c in m)
        )
        exclamation_end = sum(
            1 for m in all_assistant_messages if m.rstrip().endswith("!")
        )

        # Word frequency analysis (top 20 non-stopword terms)
        stopwords = {
            "de", "la", "el", "en", "y", "a", "que", "es", "un", "una", "los",
            "las", "por", "con", "para", "del", "al", "se", "no", "lo", "su",
            "te", "me", "mi", "tu", "como", "si", "pero", "o", "le", "ya",
            "este", "esto", "esta", "muy", "mas", "ha", "he", "ser", "hay",
        }
        word_freq: Dict[str, int] = {}
        for msg in all_assistant_messages:
            for word in re.findall(r"\b[a-zA-ZaeiouAEIOU\u00e0-\u00ff]+\b", msg.lower()):
                if word not in stopwords and len(word) > 2:
                    word_freq[word] = word_freq.get(word, 0) + 1
        top_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:20]

        # Greeting patterns
        greeting_patterns: Dict[str, int] = {}
        for msg in all_assistant_messages:
            first_line = msg.strip().split("\n")[0].lower()[:50]
            greeting_patterns[first_line] = greeting_patterns.get(first_line, 0) + 1
        top_greetings = sorted(greeting_patterns.items(), key=lambda x: x[1], reverse=True)[:10]

        stats = {
            "total_assistant_messages": len(all_assistant_messages),
            "total_user_messages": len(all_user_messages),
            "mean_length": sum(lengths) / len(lengths) if lengths else 0,
            "median_length": sorted(lengths)[len(lengths) // 2] if lengths else 0,
            "min_length": min(lengths) if lengths else 0,
            "max_length": max(lengths) if lengths else 0,
            "question_frequency": question_count / len(all_assistant_messages),
            "emoji_frequency": emoji_count / len(all_assistant_messages),
            "exclamation_end_frequency": exclamation_end / len(all_assistant_messages),
            "top_words": top_words,
            "top_greetings": top_greetings,
        }

        logger.info(f"  Analyzed {stats['total_assistant_messages']} assistant messages")
        logger.info(f"  User messages for comparison: {stats['total_user_messages']}")
        logger.info(f"  Mean length: {stats['mean_length']:.1f} chars")
        logger.info(f"  Median length: {stats['median_length']} chars")
        logger.info(f"  Min/Max length: {stats['min_length']}/{stats['max_length']} chars")
        logger.info(f"  Question frequency: {stats['question_frequency']:.1%}")
        logger.info(f"  Emoji frequency: {stats['emoji_frequency']:.1%}")
        logger.info(f"  Exclamation endings: {stats['exclamation_end_frequency']:.1%}")
        logger.info(f"  Top words: {[w for w, _ in top_words[:10]]}")
        logger.info(f"  Top greetings: {[g for g, _ in top_greetings[:5]]}")

        # Save pattern analysis
        if not self.dry_run:
            patterns_file = Path(__file__).parent / f"patterns_{self.creator_id}.json"
            with open(patterns_file, "w") as f:
                json.dump(stats, f, indent=2, default=str)
            logger.info(f"  Patterns saved to: {patterns_file}")

    # =========================================================================
    # PHASE 6: LEAD SCORING
    # =========================================================================

    def phase_score_leads(self, leads: List[Dict]):
        """Calculate final lead scores and priority ranking.

        Identifies hot leads (high purchase intent), ghost leads (inactive 7+ days),
        and produces a priority-ranked list for creator review.
        """
        logger.info("=" * 60)
        logger.info("PHASE 6: Lead Scoring & Priority")
        logger.info("=" * 60)

        hot_leads: List[Dict] = []
        ghost_leads: List[Tuple[Dict, int]] = []
        active_leads: List[Dict] = []
        now = datetime.now(timezone.utc)

        for lead in leads:
            intent_score = lead.get("purchase_intent", 0) or 0
            last_contact = lead.get("last_contact_at")

            # Classify into priority buckets
            if intent_score >= 0.7:
                hot_leads.append(lead)
            elif last_contact:
                try:
                    last_dt = datetime.fromisoformat(str(last_contact).replace("Z", "+00:00"))
                    days_inactive = (now - last_dt).days
                    if days_inactive >= 7:
                        ghost_leads.append((lead, days_inactive))
                    else:
                        active_leads.append(lead)
                except (ValueError, TypeError):
                    active_leads.append(lead)
            else:
                active_leads.append(lead)

        logger.info(f"  Hot leads (score >= 0.7): {len(hot_leads)}")
        for lead in sorted(hot_leads, key=lambda x: x.get("purchase_intent", 0), reverse=True):
            logger.info(
                f"    HOT: {lead.get('username')} - "
                f"score={lead.get('purchase_intent', 0):.2f}, status={lead.get('status')}"
            )

        logger.info(f"  Active leads: {len(active_leads)}")

        logger.info(f"  Ghost leads (7+ days): {len(ghost_leads)}")
        for lead, days in sorted(ghost_leads, key=lambda x: x[1], reverse=True)[:10]:
            logger.info(
                f"    GHOST: {lead.get('username')} - "
                f"{days} days inactive, status={lead.get('status')}"
            )

        # Summary by status
        status_counts: Dict[str, int] = {}
        for lead in leads:
            status = lead.get("status", "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        logger.info("  Status distribution:")
        for status, count in sorted(status_counts.items(), key=lambda x: x[1], reverse=True):
            logger.info(f"    {status}: {count}")

    # =========================================================================
    # PHASE 7: VALIDATION
    # =========================================================================

    def phase_validate(self, leads: List[Dict], sample_size: int = 10):
        """Validate cognitive processing quality.

        Picks a random sample of conversations and logs user/assistant pairs
        for manual review. Also cross-checks categorization consistency.
        """
        logger.info("=" * 60)
        logger.info("PHASE 7: Quality Validation")
        logger.info("=" * 60)

        import random

        # Filter to leads with enough messages for meaningful validation
        eligible = [l for l in leads if l.get("id")]
        sample = random.sample(eligible, min(sample_size, len(eligible)))
        logger.info(f"  Validating {len(sample)} random conversations...")

        validation_results: List[Dict] = []

        for lead in sample:
            messages = self.load_messages(lead_id=lead.get("id"))
            if len(messages) < 4:
                continue

            # Find a user message that has a following assistant response
            for j in range(len(messages) - 1):
                if messages[j]["role"] == "user" and messages[j + 1]["role"] == "assistant":
                    user_msg = messages[j]["content"]
                    actual_response = messages[j + 1]["content"]

                    # Classify intent if classifier available
                    intent = "N/A"
                    if self.intent_classifier:
                        classified = self.intent_classifier.classify(user_msg)
                        intent = classified.value if hasattr(classified, "value") else str(classified)

                    logger.info(
                        f"  {lead.get('username')}: "
                        f"Intent={intent} | "
                        f"User: '{user_msg[:60]}...' -> "
                        f"Bot: '{actual_response[:60]}...'"
                    )

                    validation_results.append({
                        "username": lead.get("username"),
                        "intent": intent,
                        "user_message": user_msg[:200],
                        "bot_response": actual_response[:200],
                        "status": lead.get("status"),
                    })
                    break

        if validation_results:
            logger.info(f"  Validated {len(validation_results)} conversation samples")

    # =========================================================================
    # MAIN EXECUTION
    # =========================================================================

    def run(self, phases: str = "all"):
        """Run all or specific phases."""
        logger.info("=" * 60)
        logger.info(f"BATCH PROCESSOR - Creator: {self.creator_id}")
        logger.info(f"Mode: {'DRY RUN' if self.dry_run else 'LIVE'}")
        logger.info(f"Phases: {phases}")
        logger.info("=" * 60)

        start_time = time.monotonic()

        leads = self.load_leads()
        if not leads:
            logger.error("No leads found. Aborting.")
            return

        logger.info(f"Loaded {len(leads)} leads. Starting processing...")

        phase_map = {
            "categorize": lambda: self.phase_categorize_leads(leads),
            "states": lambda: self.phase_reconstruct_states(leads),
            "dna": lambda: self.phase_generate_dna(leads),
            "facts": lambda: self.phase_extract_facts(leads),
            "patterns": lambda: self.phase_analyze_patterns(leads),
            "score": lambda: self.phase_score_leads(leads),
            "validate": lambda: self.phase_validate(leads),
        }

        if phases == "all":
            for name, func in phase_map.items():
                phase_start = time.monotonic()
                try:
                    func()
                    elapsed = time.monotonic() - phase_start
                    logger.info(f"  Phase '{name}' completed in {elapsed:.1f}s")
                except Exception as e:
                    logger.error(f"Phase '{name}' failed: {e}")
                    self.stats["errors"].append(f"phase:{name}:{e}")
        elif phases in phase_map:
            phase_map[phases]()
        else:
            logger.error(f"Unknown phase: {phases}. Available: {list(phase_map.keys())}")
            return

        # Final report
        total_elapsed = time.monotonic() - start_time
        self.stats["completed_at"] = datetime.now(timezone.utc).isoformat()
        self.stats["total_elapsed_seconds"] = round(total_elapsed, 1)

        logger.info("=" * 60)
        logger.info("BATCH PROCESSING COMPLETE")
        logger.info("=" * 60)
        for key, value in self.stats.items():
            if key != "errors":
                logger.info(f"  {key}: {value}")
        if self.stats["errors"]:
            logger.warning(f"  Errors: {len(self.stats['errors'])}")
            for err in self.stats["errors"][:10]:
                logger.warning(f"    - {err}")
        logger.info(f"  Total time: {total_elapsed:.1f}s")

        # Save stats
        stats_file = Path(__file__).parent / f"batch_stats_{self.creator_id}.json"
        with open(stats_file, "w") as f:
            json.dump(self.stats, f, indent=2, default=str)
        logger.info(f"  Stats saved to: {stats_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Batch process historical conversations through the Clonnect cognitive engine"
    )
    parser.add_argument(
        "--creator",
        required=True,
        help="Creator ID (e.g., stefano_bonanno)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run without writing to database (analysis only)",
    )
    parser.add_argument(
        "--phase",
        default="all",
        choices=["all", "categorize", "states", "dna", "facts", "patterns", "score", "validate"],
        help="Phase to run: all, categorize, states, dna, facts, patterns, score, validate",
    )
    args = parser.parse_args()

    processor = BatchProcessor(creator_id=args.creator, dry_run=args.dry_run)
    processor.run(phases=args.phase)


if __name__ == "__main__":
    main()
