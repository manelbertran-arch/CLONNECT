"""
Turbo Onboarding Pipeline — Bootstrap ALL AI systems from conversation history.

Processes existing DB messages (or fetches new ones) and feeds every learning
system so a new creator has a fully functional bot in ~15 minutes instead of weeks.

Usage:
    # Process existing messages already in DB (e.g. for Iris/Stefano):
    railway run python3 scripts/turbo_onboarding.py iris_bertran --source existing

    # Fetch WhatsApp history first, then process:
    railway run python3 scripts/turbo_onboarding.py iris_bertran --source whatsapp --instance iris-bertran

    # Fetch Instagram DM history first, then process:
    railway run python3 scripts/turbo_onboarding.py iris_bertran --source instagram

    # Run only specific phases (e.g. just the missing ones):
    railway run python3 scripts/turbo_onboarding.py iris_bertran --source existing --phases 3,4,5,6

Phases:
    1. Fetch & Store messages (skipped if --source existing)
    2. Style Analysis (tone, vocabulary)
    3. Lead Analysis (scoring, relationships)
    4. Memory & Intelligence (facts, semantic memory, personality, gold examples, DNA)
    5. Summaries & Pairs (conversation summaries, preference pairs) [NEW]
    6. Calibration (clone score, pattern analysis, learning rules)
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

# Setup path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TURBO] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Suppress noisy loggers
for name in ["httpx", "httpcore", "urllib3", "sqlalchemy.engine"]:
    logging.getLogger(name).setLevel(logging.WARNING)


class TurboOnboarding:
    """Unified onboarding pipeline for any platform."""

    def __init__(self, creator_name: str, source: str = "existing",
                 instance_name: str = None, phases: List[int] = None):
        self.creator_name = creator_name
        self.source = source
        self.instance_name = instance_name
        self.phases = phases or [1, 2, 3, 4, 5, 6]
        self.creator_db_id: str = ""
        self.creator_uuid = None
        self.results: Dict[str, Any] = {}
        self.t0 = time.time()

    def _log(self, msg: str):
        elapsed = time.time() - self.t0
        logger.info(f"[{elapsed:6.1f}s] {msg}")

    async def run(self) -> dict:
        """Execute all requested phases."""
        if not await self._resolve_creator():
            return {"status": "error", "error": "creator_not_found"}

        self._log(f"Starting turbo onboarding for {self.creator_name} (source={self.source})")
        self._log(f"Creator UUID: {self.creator_db_id}")
        self._log(f"Phases: {self.phases}")

        # Phase 1: Fetch & Store
        if 1 in self.phases and self.source != "existing":
            self._log("═══ PHASE 1/6: FETCH & STORE MESSAGES ═══")
            self.results["phase1"] = await self._phase1_fetch()
        else:
            self._log("═══ PHASE 1/6: SKIPPED (using existing DB data) ═══")
            self.results["phase1"] = {"status": "skipped"}

        # Phase 2: Style Analysis
        if 2 in self.phases:
            self._log("═══ PHASE 2/6: STYLE ANALYSIS ═══")
            self.results["phase2"] = await self._safe_run(self._phase2_style)
        else:
            self.results["phase2"] = {"status": "skipped"}

        # Phase 3: Lead Analysis
        if 3 in self.phases:
            self._log("═══ PHASE 3/6: LEAD ANALYSIS ═══")
            self.results["phase3"] = await self._safe_run(self._phase3_leads)
        else:
            self.results["phase3"] = {"status": "skipped"}

        # Phase 4: Memory & Intelligence
        if 4 in self.phases:
            self._log("═══ PHASE 4/6: MEMORY & INTELLIGENCE ═══")
            self.results["phase4"] = await self._safe_run(self._phase4_memory)
        else:
            self.results["phase4"] = {"status": "skipped"}

        # Phase 5: Summaries & Pairs (NEW — missing from WA pipeline)
        if 5 in self.phases:
            self._log("═══ PHASE 5/6: CONVERSATION SUMMARIES & PREFERENCE PAIRS ═══")
            self.results["phase5"] = await self._safe_run(self._phase5_summaries_pairs)
        else:
            self.results["phase5"] = {"status": "skipped"}

        # Phase 6: Calibration
        if 6 in self.phases:
            self._log("═══ PHASE 6/6: CALIBRATION ═══")
            self.results["phase6"] = await self._safe_run(self._phase6_calibration)
        else:
            self.results["phase6"] = {"status": "skipped"}

        self._print_summary()
        return {"status": "complete", "results": self.results}

    async def _safe_run(self, fn) -> dict:
        try:
            return await fn()
        except Exception as e:
            logger.error(f"Phase failed: {e}", exc_info=True)
            return {"status": "error", "error": str(e)}

    # ─── RESOLVE ──────────────────────────────────────────────────────

    async def _resolve_creator(self) -> bool:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=self.creator_name).first()
            if not creator:
                logger.error(f"Creator not found: {self.creator_name}")
                return False
            self.creator_db_id = str(creator.id)
            self.creator_uuid = creator.id
            return True
        finally:
            session.close()

    # ─── PHASE 1: FETCH ──────────────────────────────────────────────

    async def _phase1_fetch(self) -> dict:
        if self.source == "whatsapp":
            return await self._fetch_whatsapp()
        elif self.source == "instagram":
            return await self._fetch_instagram()
        return {"status": "skipped", "reason": f"unknown source: {self.source}"}

    async def _fetch_whatsapp(self) -> dict:
        if not self.instance_name:
            return {"status": "error", "error": "instance_name required for whatsapp"}

        from services.whatsapp_onboarding_pipeline import WhatsAppOnboardingPipeline

        pipeline = WhatsAppOnboardingPipeline(
            creator_id=self.creator_name,
            instance_name=self.instance_name,
        )
        pipeline.creator_db_id = self.creator_db_id
        pipeline.creator_uuid = self.creator_uuid

        result = await pipeline._phase1_extraction()
        self._log(f"WhatsApp extraction: {result.get('messages_stored', 0)} messages stored")
        return result

    async def _fetch_instagram(self) -> dict:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message
        from api.services.db_service import get_or_create_lead
        from core.instagram import Instagram

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=self.creator_name).first()
            if not creator or not creator.instagram_token:
                return {"status": "error", "error": "no instagram token"}

            connector = Instagram(
                access_token=creator.instagram_token,
                page_id=creator.facebook_page_id,
                ig_user_id=creator.instagram_user_id,
            )
        finally:
            session.close()

        self._log("Fetching Instagram conversations...")
        conversations = await connector.get_all_conversations(max_pages=20)
        self._log(f"Found {len(conversations)} conversations")

        messages_stored = 0
        leads_created = 0

        session = SessionLocal()
        try:
            for i, conv in enumerate(conversations):
                conv_id = conv.get("id")
                participants = conv.get("participants", {}).get("data", [])

                # Find the other participant (not the creator)
                other = None
                for p in participants:
                    if p.get("id") != creator.instagram_user_id:
                        other = p
                        break
                if not other:
                    continue

                ig_user_id = other.get("id", "")
                username = other.get("username", "")

                # Get or create lead
                lead_result = get_or_create_lead(
                    creator_name=self.creator_name,
                    platform_user_id=ig_user_id,
                    platform="instagram",
                    full_name=username,
                )
                if not lead_result:
                    continue
                leads_created += 1

                # Fetch messages for this conversation
                try:
                    messages = await connector.get_all_conversation_messages(
                        conv_id, max_pages=10
                    )
                except Exception as e:
                    logger.warning(f"Failed to fetch messages for conv {conv_id}: {e}")
                    continue

                # Check existing messages to avoid duplicates
                existing_ids = set()
                existing = (
                    session.query(Message.platform_message_id)
                    .filter(
                        Message.lead_id == lead_result["id"],
                        Message.platform_message_id.isnot(None),
                    )
                    .all()
                )
                existing_ids = {r[0] for r in existing}

                batch = []
                for msg in messages:
                    msg_id = msg.get("id", "")
                    if msg_id in existing_ids:
                        continue

                    content = msg.get("message", "")
                    if not content:
                        continue

                    from_creator = msg.get("from", {}).get("id") == creator.instagram_user_id
                    created_time = msg.get("created_time")

                    from datetime import datetime, timezone
                    created_at = datetime.now(timezone.utc)
                    if created_time:
                        try:
                            created_at = datetime.fromisoformat(
                                created_time.replace("Z", "+00:00")
                            )
                        except (ValueError, TypeError):
                            pass

                    batch.append(Message(
                        lead_id=lead_result["id"],
                        role="assistant" if from_creator else "user",
                        content=content,
                        status="sent",
                        approved_by="historical_sync",
                        platform_message_id=msg_id,
                        msg_metadata={"source": "ig_onboarding_sync"},
                        created_at=created_at,
                    ))
                    messages_stored += 1

                if batch:
                    session.bulk_save_objects(batch)
                    if (i + 1) % 10 == 0:
                        session.commit()
                        self._log(f"  Conversations processed: {i+1}/{len(conversations)}")

                # Rate limit
                await asyncio.sleep(0.3)

            session.commit()
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()

        self._log(f"Instagram extraction: {messages_stored} messages, {leads_created} leads")
        return {"messages_stored": messages_stored, "leads_created": leads_created}

    # ─── PHASE 2: STYLE ──────────────────────────────────────────────

    async def _phase2_style(self) -> dict:
        results = {}

        # Reuse WA pipeline's style analysis
        from services.whatsapp_onboarding_pipeline import WhatsAppOnboardingPipeline
        pipeline = WhatsAppOnboardingPipeline(self.creator_name, self.instance_name or "")
        pipeline.creator_db_id = self.creator_db_id
        pipeline.creator_uuid = self.creator_uuid

        results = await pipeline._phase2_style_analysis()
        self._log(f"Style analysis: {results}")
        return results

    # ─── PHASE 3: LEADS ──────────────────────────────────────────────

    async def _phase3_leads(self) -> dict:
        results = {}

        # 3a. Batch scoring
        try:
            from api.database import SessionLocal
            from services.lead_scoring import batch_recalculate_scores

            session = SessionLocal()
            try:
                score_results = batch_recalculate_scores(session, self.creator_name)
                results["scoring"] = score_results
                self._log(f"Lead scoring: {score_results}")
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"Lead scoring failed: {e}")
            results["scoring"] = {"error": str(e)}

        # 3b. Relationship Analyzer
        try:
            from services.relationship_analyzer import RelationshipAnalyzer

            top_leads = self._get_top_leads(limit=30)
            ra = RelationshipAnalyzer()
            analyzed = 0
            for lead in top_leads:
                msgs = self._get_messages_for_lead(lead["id"])
                if len(msgs) >= 5:
                    ra.analyze(self.creator_name, str(lead["platform_user_id"]), msgs)
                    analyzed += 1
            results["relationship_analyzer"] = {"leads_analyzed": analyzed}
            self._log(f"Relationship analysis: {analyzed} leads")
        except Exception as e:
            logger.warning(f"RelationshipAnalyzer failed: {e}")
            results["relationship_analyzer"] = {"error": str(e)}

        return results

    # ─── PHASE 4: MEMORY ─────────────────────────────────────────────

    async def _phase4_memory(self) -> dict:
        results = {}
        top_leads = self._get_top_leads(limit=50)
        self._log(f"Processing {len(top_leads)} top leads")

        # 4a. MemoryEngine facts
        try:
            from services.memory_engine import MemoryEngine

            me = MemoryEngine()
            facts_total = 0
            for i, lead in enumerate(top_leads):
                msgs = self._get_messages_for_lead(lead["id"])
                if not msgs:
                    continue
                conversation = [
                    {"role": m["role"], "content": m["content"]}
                    for m in msgs[-30:]
                    if m.get("content") and not m["content"].startswith("[")
                ]
                if not conversation:
                    continue
                stored = await me.add(
                    creator_id=self.creator_db_id,
                    lead_id=str(lead["id"]),
                    conversation_messages=conversation,
                )
                facts_total += len(stored) if stored else 0
                if (i + 1) % 10 == 0:
                    self._log(f"  Memory: {i+1}/{len(top_leads)} leads, {facts_total} facts")
            results["memory_engine"] = {"facts": facts_total, "leads": len(top_leads)}
            self._log(f"Memory engine: {facts_total} facts from {len(top_leads)} leads")
        except Exception as e:
            logger.warning(f"MemoryEngine failed: {e}")
            results["memory_engine"] = {"error": str(e)}

        # 4b. PersonalityExtraction
        try:
            from api.database import SessionLocal
            from core.personality_extraction.extractor import PersonalityExtractor

            session = SessionLocal()
            try:
                extractor = PersonalityExtractor(db=session)
                extraction_result = await extractor.run(
                    creator_id=self.creator_db_id,
                    creator_name=self.creator_name,
                    skip_llm=False,
                    limit_leads=50,
                )
                results["personality"] = {"status": "ok"}
                self._log("Personality extraction: done")
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"PersonalityExtraction failed: {e}")
            results["personality"] = {"error": str(e)}

        # 4c. GoldExamples
        try:
            from services.gold_examples_service import curate_examples

            r = await curate_examples(self.creator_name, self.creator_db_id)
            results["gold_examples"] = r
            self._log(f"Gold examples: {r}")
        except Exception as e:
            logger.warning(f"GoldExamples failed: {e}")
            results["gold_examples"] = {"error": str(e)}

        # 4d. RelationshipDNA
        try:
            from services.relationship_dna_service import get_dna_service

            dna_svc = get_dna_service()
            dna_count = 0
            for lead in top_leads[:30]:
                msgs = self._get_messages_for_lead(lead["id"])
                if len(msgs) >= 5:
                    dna_svc.analyze_and_update_dna(
                        self.creator_name,
                        str(lead["platform_user_id"]),
                        msgs,
                    )
                    dna_count += 1
            results["relationship_dna"] = {"leads": dna_count}
            self._log(f"Relationship DNA: {dna_count} leads")
        except Exception as e:
            logger.warning(f"RelationshipDNA failed: {e}")
            results["relationship_dna"] = {"error": str(e)}

        return results

    # ─── PHASE 5: SUMMARIES & PAIRS (NEW) ────────────────────────────

    async def _phase5_summaries_pairs(self) -> dict:
        """Generate conversation summaries and mine preference pairs."""
        results = {}

        # 5a. Conversation Summaries
        try:
            from services.memory_engine import MemoryEngine

            me = MemoryEngine()
            top_leads = self._get_top_leads(limit=100)
            summaries_created = 0
            skipped = 0

            for i, lead in enumerate(top_leads):
                msgs = self._get_messages_for_lead(lead["id"])
                if len(msgs) < 4:
                    skipped += 1
                    continue

                # Check if summary already exists
                existing = await me._get_latest_summary(self.creator_db_id, str(lead["id"]))
                if existing:
                    skipped += 1
                    continue

                conversation = [
                    {"role": m["role"], "content": m["content"]}
                    for m in msgs[-50:]
                    if m.get("content") and not m["content"].startswith("[")
                ]
                if len(conversation) < 3:
                    skipped += 1
                    continue

                summary = await me.summarize_conversation(
                    creator_id=self.creator_db_id,
                    lead_id=str(lead["id"]),
                    messages=conversation,
                )
                if summary:
                    summaries_created += 1

                if (i + 1) % 20 == 0:
                    self._log(f"  Summaries: {i+1}/{len(top_leads)}, created={summaries_created}")

                # Small delay to avoid hammering LLM
                await asyncio.sleep(0.1)

            results["summaries"] = {
                "created": summaries_created,
                "skipped": skipped,
                "total_leads": len(top_leads),
            }
            self._log(f"Conversation summaries: {summaries_created} created, {skipped} skipped")
        except Exception as e:
            logger.warning(f"Summaries failed: {e}")
            results["summaries"] = {"error": str(e)}

        # 5b. Preference Pairs (historical mining)
        try:
            from services.preference_pairs_service import mine_historical_pairs

            pairs_created = await mine_historical_pairs(
                self.creator_name, self.creator_db_id, limit=500
            )
            results["preference_pairs"] = {"historical_created": pairs_created}
            self._log(f"Preference pairs: {pairs_created} historical pairs mined")
        except Exception as e:
            logger.warning(f"Preference pairs failed: {e}")
            results["preference_pairs"] = {"error": str(e)}

        return results

    # ─── PHASE 6: CALIBRATION ────────────────────────────────────────

    async def _phase6_calibration(self) -> dict:
        results = {}

        # 6a. Pattern Analysis → Learning Rules
        try:
            from services.pattern_analyzer import run_pattern_analysis

            r = await run_pattern_analysis(self.creator_name, self.creator_db_id)
            results["pattern_analyzer"] = r
            self._log(f"Pattern analysis: {r}")
        except Exception as e:
            logger.warning(f"PatternAnalyzer failed: {e}")
            results["pattern_analyzer"] = {"error": str(e)}

        # 6b. Clone Score Engine
        try:
            from services.clone_score_engine import CloneScoreEngine

            engine = CloneScoreEngine()
            score = await engine.evaluate_batch(self.creator_name, self.creator_db_id)
            results["clone_score"] = score
            self._log(f"Clone score: {score}")
        except Exception as e:
            logger.warning(f"CloneScoreEngine failed: {e}")
            results["clone_score"] = {"error": str(e)}

        return results

    # ─── DB HELPERS ───────────────────────────────────────────────────

    def _get_top_leads(self, limit: int = 50) -> List[dict]:
        from api.database import SessionLocal
        from api.models import Lead

        session = SessionLocal()
        try:
            leads = (
                session.query(Lead)
                .filter(Lead.creator_id == self.creator_uuid)
                .order_by(Lead.last_contact_at.desc().nullslast())
                .limit(limit)
                .all()
            )
            return [
                {"id": l.id, "platform_user_id": l.platform_user_id,
                 "full_name": l.full_name, "status": l.status}
                for l in leads
            ]
        finally:
            session.close()

    def _get_messages_for_lead(self, lead_id) -> List[dict]:
        from api.database import SessionLocal
        from api.models import Message

        session = SessionLocal()
        try:
            msgs = (
                session.query(Message)
                .filter(Message.lead_id == lead_id)
                .order_by(Message.created_at.asc())
                .all()
            )
            return [
                {"role": m.role, "content": m.content or "",
                 "created_at": m.created_at.isoformat() if m.created_at else None}
                for m in msgs
            ]
        finally:
            session.close()

    # ─── SUMMARY ──────────────────────────────────────────────────────

    def _print_summary(self):
        elapsed = time.time() - self.t0
        self._log("═" * 60)
        self._log(f"TURBO ONBOARDING COMPLETE — {elapsed:.0f}s total")
        self._log("═" * 60)

        for phase_name, phase_result in self.results.items():
            if isinstance(phase_result, dict):
                status = phase_result.get("status", "ok")
                if status == "skipped":
                    self._log(f"  {phase_name}: skipped")
                elif status == "error":
                    self._log(f"  {phase_name}: ERROR — {phase_result.get('error', '?')}")
                else:
                    # Print key metrics
                    metrics = {k: v for k, v in phase_result.items()
                               if k not in ("status", "error") and not isinstance(v, dict)}
                    sub_results = {k: v for k, v in phase_result.items() if isinstance(v, dict)}

                    if metrics:
                        self._log(f"  {phase_name}: {metrics}")
                    for sub_name, sub_data in sub_results.items():
                        self._log(f"    {sub_name}: {sub_data}")


def main():
    parser = argparse.ArgumentParser(description="Turbo Onboarding Pipeline")
    parser.add_argument("creator_name", help="Creator slug (e.g. iris_bertran)")
    parser.add_argument(
        "--source", default="existing",
        choices=["existing", "whatsapp", "instagram"],
        help="Message source: existing (DB), whatsapp (Evolution API), instagram (Graph API)",
    )
    parser.add_argument("--instance", help="Evolution API instance name (for whatsapp source)")
    parser.add_argument(
        "--phases", default="1,2,3,4,5,6",
        help="Comma-separated phase numbers to run (default: all)",
    )
    args = parser.parse_args()

    phases = [int(p.strip()) for p in args.phases.split(",")]

    pipeline = TurboOnboarding(
        creator_name=args.creator_name,
        source=args.source,
        instance_name=args.instance,
        phases=phases,
    )
    asyncio.run(pipeline.run())


if __name__ == "__main__":
    main()
