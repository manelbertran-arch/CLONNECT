"""
Test Set Generator — Extracts real creator responses for CloneScore evaluation.

Generates ground-truth test sets from:
  1. Copilot edits (copilot_action='edited') — creator corrections
  2. Manual overrides (copilot_action='manual_override') — from-scratch responses
  3. Approved responses (copilot_action='approved') — creator agrees bot sounds like them
  4. Resolved externally (copilot_action='resolved_externally') — unbiased signal

Test sets are stratified by intent to ensure balanced coverage.

Entry points:
  - generate_from_db()  — generate test set from message history
  - get_active_test_set() — load existing test set
"""

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Minimum pairs needed for a useful test set
MIN_PAIRS_THRESHOLD = 10

# Maximum pairs per intent for stratification
MAX_PER_INTENT = 15


class TestSetGenerator:
    """Generates and manages CloneScore test sets."""

    def generate_from_db(
        self,
        creator_id: str,
        creator_db_id,
        min_pairs: int = 50,
    ) -> Optional[Dict[str, Any]]:
        """Generate a test set from the creator's message history.

        Extracts real creator responses from copilot actions and stratifies
        them by intent for balanced evaluation.
        """
        from api.database import SessionLocal

        session = SessionLocal()
        try:
            edited_pairs = self._extract_edited_responses(session, creator_db_id)
            manual_pairs = self._extract_manual_responses(session, creator_db_id)
            approved_pairs = self._extract_approved_responses(session, creator_db_id)
            external_pairs = self._extract_external_responses(session, creator_db_id)

            all_pairs = edited_pairs + manual_pairs + approved_pairs + external_pairs
            logger.info(
                f"[TEST_SET] Raw pairs for {creator_id}: "
                f"edited={len(edited_pairs)}, manual={len(manual_pairs)}, "
                f"approved={len(approved_pairs)}, external={len(external_pairs)}, "
                f"total={len(all_pairs)}"
            )

            if len(all_pairs) < MIN_PAIRS_THRESHOLD:
                logger.warning(
                    f"[TEST_SET] Only {len(all_pairs)} pairs for {creator_id} "
                    f"(need {MIN_PAIRS_THRESHOLD}), skipping"
                )
                return None

            stratified = self._stratify_by_intent(all_pairs, min_pairs)

            test_set_data = {
                "name": f"auto_{creator_id}_{datetime.now(timezone.utc).strftime('%Y%m%d')}",
                "pairs_count": len(stratified),
                "sources": {
                    "edited": len(edited_pairs),
                    "manual": len(manual_pairs),
                    "approved": len(approved_pairs),
                    "external": len(external_pairs),
                },
                "intents": dict(
                    defaultdict(int, {p.get("intent", "unknown"): 0 for p in stratified})
                ),
            }

            for pair in stratified:
                intent = pair.get("intent", "unknown")
                test_set_data["intents"][intent] = (
                    test_set_data["intents"].get(intent, 0) + 1
                )

            self._store_test_set(
                session, creator_db_id, test_set_data["name"], stratified,
            )

            logger.info(
                f"[TEST_SET] Generated for {creator_id}: "
                f"{len(stratified)} pairs, intents={test_set_data['intents']}"
            )

            return {**test_set_data, "test_pairs": stratified}

        except Exception as e:
            logger.error(f"[TEST_SET] generate_from_db error for {creator_id}: {e}")
            session.rollback()
            return None
        finally:
            session.close()

    def get_active_test_set(self, creator_db_id) -> Optional[List[Dict]]:
        """Load the active test set for a creator."""
        from api.database import SessionLocal
        from api.models import CloneScoreTestSet

        session = SessionLocal()
        try:
            test_set = (
                session.query(CloneScoreTestSet)
                .filter_by(creator_id=creator_db_id, is_active=True)
                .order_by(CloneScoreTestSet.created_at.desc())
                .first()
            )
            if test_set:
                return test_set.test_pairs
            return None
        except Exception as e:
            logger.error(f"[TEST_SET] get_active_test_set error: {e}")
            return None
        finally:
            session.close()

    # =====================================================================
    # EXTRACTION: different copilot action types
    # =====================================================================
    def _extract_edited_responses(self, session, creator_db_id) -> List[Dict]:
        """Extract pairs from edited responses (medium-high signal)."""
        from api.models import Lead, Message

        rows = (
            session.query(
                Message.content,
                Message.suggested_response,
                Message.intent,
                Lead.status,
            )
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator_db_id,
                Message.role == "assistant",
                Message.copilot_action == "edited",
                Message.content.isnot(None),
                Message.suggested_response.isnot(None),
            )
            .order_by(Message.created_at.desc())
            .limit(200)
            .all()
        )

        return [
            self._format_test_pair(
                lead_message="(contexto de edicion)",
                creator_response=r.content,
                bot_response=r.suggested_response,
                intent=r.intent,
                lead_stage=r.status,
                source="edited",
            )
            for r in rows
            if r.content and r.suggested_response
        ]

    def _extract_manual_responses(self, session, creator_db_id) -> List[Dict]:
        """Extract pairs from manual overrides (highest signal)."""
        from api.models import Lead, Message

        rows = (
            session.query(
                Message.content,
                Message.suggested_response,
                Message.intent,
                Lead.status,
            )
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator_db_id,
                Message.role == "assistant",
                Message.copilot_action == "manual_override",
                Message.content.isnot(None),
            )
            .order_by(Message.created_at.desc())
            .limit(100)
            .all()
        )

        return [
            self._format_test_pair(
                lead_message="(respuesta manual del creador)",
                creator_response=r.content,
                bot_response=r.suggested_response or "",
                intent=r.intent,
                lead_stage=r.status,
                source="manual_override",
            )
            for r in rows
            if r.content
        ]

    def _extract_approved_responses(self, session, creator_db_id) -> List[Dict]:
        """Extract pairs from approved responses (positive signal)."""
        from api.models import Lead, Message

        rows = (
            session.query(
                Message.content,
                Message.intent,
                Lead.status,
            )
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator_db_id,
                Message.role == "assistant",
                Message.copilot_action == "approved",
                Message.content.isnot(None),
            )
            .order_by(Message.created_at.desc())
            .limit(200)
            .all()
        )

        return [
            self._format_test_pair(
                lead_message="(aprobacion directa)",
                creator_response=r.content,
                bot_response=r.content,
                intent=r.intent,
                lead_stage=r.status,
                source="approved",
            )
            for r in rows
            if r.content
        ]

    def _extract_external_responses(self, session, creator_db_id) -> List[Dict]:
        """Extract pairs from externally resolved messages (highest unbiased signal)."""
        from api.models import Lead, Message

        rows = (
            session.query(
                Message.content,
                Message.suggested_response,
                Message.intent,
                Lead.status,
            )
            .join(Lead, Message.lead_id == Lead.id)
            .filter(
                Lead.creator_id == creator_db_id,
                Message.role == "assistant",
                Message.copilot_action == "resolved_externally",
                Message.content.isnot(None),
            )
            .order_by(Message.created_at.desc())
            .limit(100)
            .all()
        )

        return [
            self._format_test_pair(
                lead_message="(resuelto externamente)",
                creator_response=r.content,
                bot_response=r.suggested_response or "",
                intent=r.intent,
                lead_stage=r.status,
                source="resolved_externally",
            )
            for r in rows
            if r.content
        ]

    # =====================================================================
    # STRATIFICATION
    # =====================================================================
    def _stratify_by_intent(
        self,
        pairs: List[Dict],
        target_total: int = 50,
    ) -> List[Dict]:
        """Stratify test pairs by intent for balanced coverage."""
        by_intent: Dict[str, List[Dict]] = defaultdict(list)
        for pair in pairs:
            intent = pair.get("intent") or "unknown"
            by_intent[intent].append(pair)

        num_intents = len(by_intent)
        if num_intents == 0:
            return pairs[:target_total]

        base_per_intent = max(2, target_total // num_intents)
        result = []

        for intent, intent_pairs in by_intent.items():
            cap = min(len(intent_pairs), base_per_intent, MAX_PER_INTENT)
            result.extend(intent_pairs[:cap])

        if len(result) < target_total:
            remaining = [p for p in pairs if p not in result]
            remaining.sort(
                key=lambda p: {
                    "manual_override": 0,
                    "resolved_externally": 1,
                    "edited": 2,
                    "approved": 3,
                }.get(p.get("source", ""), 4)
            )
            result.extend(remaining[: target_total - len(result)])

        return result[:target_total]

    # =====================================================================
    # FORMATTING + STORAGE
    # =====================================================================
    def _format_test_pair(
        self,
        lead_message: str,
        creator_response: str,
        bot_response: str,
        intent: Optional[str],
        lead_stage: Optional[str],
        source: str,
    ) -> Dict:
        """Format a single test pair."""
        return {
            "lead_message": lead_message[:300],
            "creator_response": creator_response[:500],
            "bot_response": bot_response[:500],
            "intent": intent or "unknown",
            "lead_stage": lead_stage or "nuevo",
            "source": source,
        }

    def _store_test_set(
        self,
        session,
        creator_db_id,
        name: str,
        test_pairs: List[Dict],
    ):
        """Store test set in clone_score_test_sets table."""
        from api.models import CloneScoreTestSet

        try:
            session.query(CloneScoreTestSet).filter_by(
                creator_id=creator_db_id, is_active=True,
            ).update({"is_active": False})

            test_set = CloneScoreTestSet(
                creator_id=creator_db_id,
                name=name,
                test_pairs=test_pairs,
                is_active=True,
            )
            session.add(test_set)
            session.commit()
        except Exception as e:
            logger.error(f"[TEST_SET] _store_test_set error: {e}")
            session.rollback()
