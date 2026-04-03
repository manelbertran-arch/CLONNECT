"""
WhatsApp Onboarding Pipeline — bootstraps the AI stack from Evolution API history.

When a WhatsApp instance connects (CONNECTION_UPDATE state=open), this pipeline:
  1. Extracts all historical messages via Evolution API findMessages
  2. Runs style analysis (ToneAnalyzer, VocabularyExtractor)
  3. Runs lead analysis (scoring, RelationshipAnalyzer)
  4. Builds memory & intelligence (MemoryEngine, SemanticMemory, PersonalityExtraction, GoldExamples, RelationshipDNA)
  5. Calibrates (CloneScoreEngine, PatternAnalyzer)

CRITICAL: Services like memory_engine.py use CAST(:cid AS uuid) in raw SQL.
The pipeline resolves creator_name → UUID early and passes UUIDs everywhere.

Env: ENABLE_WA_ONBOARDING_PIPELINE (default: "true")
"""

import asyncio
import logging
import os
import re
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class WhatsAppOnboardingPipeline:
    """5-phase onboarding pipeline for WhatsApp creators."""

    def __init__(self, creator_id: str, instance_name: str):
        """
        Args:
            creator_id: Creator name (e.g. "iris_bertran") — NOT a UUID.
            instance_name: Evolution API instance name (e.g. "iris-bertran").
        """
        self.creator_name = creator_id
        self.instance_name = instance_name
        self.creator_db_id: str = ""    # UUID as string, resolved in _resolve_creator()
        self.creator_uuid = None        # UUID object
        self._all_records: List[dict] = []  # Raw Evolution API records from Phase 1

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC: run()
    # ─────────────────────────────────────────────────────────────────────

    async def run(self) -> dict:
        """Execute all 5 phases. Returns summary dict."""
        if not os.getenv("ENABLE_WA_ONBOARDING_PIPELINE", "true").lower() == "true":
            logger.info(f"[WA-PIPELINE] Disabled for {self.creator_name}")
            return {"status": "disabled"}

        if not await self._resolve_creator():
            return {"status": "error", "error": "creator_not_found"}

        self._update_progress(0, "starting", 0)
        results: Dict[str, Any] = {}

        # Phase 1: Extraction (blocking — all others depend on it)
        try:
            results["phase1"] = await self._phase1_extraction()
        except Exception as e:
            logger.error(f"[WA-PIPELINE] Phase 1 failed: {e}", exc_info=True)
            results["phase1"] = {"error": str(e)}
            self._mark_complete("error", str(e))
            return {"status": "error", "results": results}

        # Phases 2+3: Style + Lead analysis (parallel)
        try:
            phase2_task = self._phase2_style_analysis()
            phase3_task = self._phase3_lead_analysis()
            r2, r3 = await asyncio.gather(phase2_task, phase3_task, return_exceptions=True)
            results["phase2"] = r2 if not isinstance(r2, Exception) else {"error": str(r2)}
            results["phase3"] = r3 if not isinstance(r3, Exception) else {"error": str(r3)}
        except Exception as e:
            logger.error(f"[WA-PIPELINE] Phase 2+3 failed: {e}", exc_info=True)

        # Phase 4: Memory & Intelligence
        try:
            results["phase4"] = await self._phase4_memory_intelligence()
        except Exception as e:
            logger.error(f"[WA-PIPELINE] Phase 4 failed: {e}", exc_info=True)
            results["phase4"] = {"error": str(e)}

        # Phase 5: Calibration
        try:
            results["phase5"] = await self._phase5_calibration()
        except Exception as e:
            logger.error(f"[WA-PIPELINE] Phase 5 failed: {e}", exc_info=True)
            results["phase5"] = {"error": str(e)}

        self._mark_complete("complete")
        return {"status": "complete", "results": results}

    # ─────────────────────────────────────────────────────────────────────
    # INTERNAL: resolve creator, progress, helpers
    # ─────────────────────────────────────────────────────────────────────

    async def _resolve_creator(self) -> bool:
        """Resolve creator_name → UUID. Returns False if not found."""
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=self.creator_name).first()
            if not creator:
                logger.error(f"[WA-PIPELINE] Creator not found: {self.creator_name}")
                return False
            self.creator_db_id = str(creator.id)   # UUID as string
            self.creator_uuid = creator.id          # UUID object
            logger.info(f"[WA-PIPELINE] Resolved {self.creator_name} → {self.creator_db_id}")
            return True
        finally:
            session.close()

    def _update_progress(self, phase: int, phase_name: str, percent: int, details: dict = None):
        """Update Creator.clone_progress JSON column."""
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=self.creator_name).first()
            if not creator:
                return
            creator.clone_status = "in_progress"
            creator.clone_progress = {
                "pipeline": "whatsapp_onboarding",
                "phase": phase,
                "phase_name": phase_name,
                "percent": percent,
                "details": details or {},
                "updated_at": datetime.now(UTC).isoformat(),
            }
            if phase == 0:
                creator.clone_started_at = datetime.now(UTC)
            session.commit()
        except Exception as e:
            logger.warning(f"[WA-PIPELINE] Progress update failed: {e}")
            session.rollback()
        finally:
            session.close()

    def _mark_complete(self, status: str, error: str = None):
        """Set final clone_status and clone_completed_at."""
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=self.creator_name).first()
            if not creator:
                return
            creator.clone_status = status
            creator.clone_completed_at = datetime.now(UTC)
            if error:
                creator.clone_error = error
            session.commit()
        except Exception as e:
            logger.warning(f"[WA-PIPELINE] Mark complete failed: {e}")
            session.rollback()
        finally:
            session.close()

    # ─────────────────────────────────────────────────────────────────────
    # PHASE 1: EXTRACTION
    # ─────────────────────────────────────────────────────────────────────

    async def _phase1_extraction(self) -> dict:
        """
        Paginate Evolution API findMessages, create Lead + Message records.

        Returns stats dict with total_messages, leads_created, etc.
        """
        from services.evolution_api import find_messages

        # Fetch page 1 to get total
        first = await find_messages(self.instance_name, page=1)
        total = first.get("messages", {}).get("total", 0)
        total_pages = first.get("messages", {}).get("pages", 0)

        if total == 0:
            logger.warning(f"[WA-PIPELINE] No messages found for {self.instance_name}")
            self._update_progress(1, "extraction", 100, {"total_messages": 0})
            return {"total_messages": 0, "leads_created": 0, "messages_stored": 0}

        self._update_progress(1, "extraction", 5, {
            "total_messages": total,
            "total_pages": total_pages,
        })
        logger.info(f"[WA-PIPELINE] Found {total} messages across {total_pages} pages")

        # Paginate all pages
        all_records = first.get("messages", {}).get("records", [])
        for page in range(2, total_pages + 1):
            data = await find_messages(self.instance_name, page=page)
            records = data.get("messages", {}).get("records", [])
            if not records:
                break
            all_records.extend(records)

            if page % 50 == 0:
                pct = int(5 + (page / total_pages) * 60)
                self._update_progress(1, "extraction", pct, {"pages_fetched": page})
            if page % 10 == 0:
                await asyncio.sleep(0.2)  # Rate limiting

        self._all_records = all_records
        logger.info(f"[WA-PIPELINE] Fetched {len(all_records)} raw records")

        # Parse and store
        stats = await self._store_messages(all_records)

        # Language detection on a sample of creator messages
        try:
            from core.i18n import detect_language

            creator_texts = [
                self._extract_text(r) for r in all_records
                if r.get("key", {}).get("fromMe", False)
            ]
            creator_texts = [t for t in creator_texts if t and len(t) > 10]
            sample = creator_texts[:100]
            if sample:
                lang_counts: Dict[str, int] = {}
                for text in sample:
                    lang = detect_language(text)
                    lang_counts[lang] = lang_counts.get(lang, 0) + 1
                stats["languages"] = lang_counts
                stats["primary_language"] = max(lang_counts, key=lang_counts.get)
        except Exception as e:
            logger.warning(f"[WA-PIPELINE] Language detection failed: {e}")

        self._update_progress(1, "extraction", 100, stats)
        logger.info(f"[WA-PIPELINE] Phase 1 complete: {stats}")
        return stats

    async def _store_messages(self, records: List[dict]) -> dict:
        """Group records by phone, create Leads, batch-insert Messages.

        Deduplicates by platform_message_id to prevent re-inserting
        historical messages on every Evolution API reconnection.
        """
        from api.database import SessionLocal
        from api.models import Message
        from api.services.db_service import get_or_create_lead

        # Group by remote JID (phone number)
        contacts: Dict[str, List[dict]] = {}
        for r in records:
            key_obj = r.get("key", {})
            remote_jid = key_obj.get("remoteJid", "")
            if not remote_jid or remote_jid.endswith("@g.us"):
                continue  # Skip group messages
            phone = remote_jid.split("@")[0]
            if phone not in contacts:
                contacts[phone] = []
            contacts[phone].append(r)

        leads_created = 0
        messages_stored = 0
        skipped_empty = 0
        skipped_duplicate = 0

        session = SessionLocal()
        try:
            batch: List[Message] = []

            for phone, msgs in contacts.items():
                # Get push_name from first non-fromMe message
                push_name = None
                for m in msgs:
                    if not m.get("key", {}).get("fromMe", False):
                        push_name = m.get("pushName")
                        if push_name:
                            break

                # Create or get lead
                lead_result = get_or_create_lead(
                    creator_name=self.creator_name,
                    platform_user_id=f"wa_{phone}",
                    platform="whatsapp",
                    full_name=push_name,
                )
                if not lead_result:
                    continue
                leads_created += 1
                lead_uuid = lead_result["id"]

                # Pre-fetch existing platform_message_ids for this lead to dedup
                existing_pmids = set()
                rows = (
                    session.query(Message.platform_message_id)
                    .filter(
                        Message.lead_id == lead_uuid,
                        Message.platform_message_id.isnot(None),
                    )
                    .all()
                )
                existing_pmids = {r[0] for r in rows}

                # Content-based dedup: Evolution API generates new IDs on reconnect
                # so we also dedup by (content, created_at) to prevent re-imports
                existing_content_keys = set()
                content_rows = (
                    session.query(Message.content, Message.created_at)
                    .filter(Message.lead_id == lead_uuid)
                    .all()
                )
                for cr in content_rows:
                    if cr[0] and cr[1]:
                        existing_content_keys.add((cr[0], str(cr[1])))

                for record in msgs:
                    text = self._extract_text(record)
                    if not text:
                        skipped_empty += 1
                        continue

                    from_me = record.get("key", {}).get("fromMe", False)
                    msg_type = self._detect_message_type(record)
                    msg_id = record.get("key", {}).get("id", "")
                    timestamp = record.get("messageTimestamp")

                    # Skip if this message already exists in DB (by platform_message_id)
                    if msg_id and msg_id in existing_pmids:
                        skipped_duplicate += 1
                        continue
                    if msg_id:
                        existing_pmids.add(msg_id)

                    # Parse timestamp for content-based dedup check
                    _created_at = None
                    if timestamp:
                        try:
                            _created_at = datetime.fromtimestamp(int(timestamp), tz=UTC)
                        except (ValueError, TypeError, OSError):
                            pass

                    # Content-based dedup: skip if same content+timestamp already exists
                    if _created_at:
                        content_key = (text, str(_created_at))
                        if content_key in existing_content_keys:
                            skipped_duplicate += 1
                            continue
                        existing_content_keys.add(content_key)

                    created_at = _created_at or datetime.now(UTC)

                    msg = Message(
                        lead_id=lead_uuid,
                        role="assistant" if from_me else "user",
                        content=text,
                        status="sent",
                        approved_by="historical_sync",
                        platform_message_id=msg_id,
                        msg_metadata={
                            "source": "wa_onboarding_sync",
                            "message_type": msg_type,
                        },
                        created_at=created_at,
                    )
                    batch.append(msg)
                    messages_stored += 1

                    # Commit in batches of 500
                    if len(batch) >= 500:
                        session.bulk_save_objects(batch)
                        session.commit()
                        batch = []

            # Final batch
            if batch:
                session.bulk_save_objects(batch)
                session.commit()

        except Exception as e:
            logger.error(f"[WA-PIPELINE] Store messages failed: {e}", exc_info=True)
            session.rollback()
            raise
        finally:
            session.close()

        logger.info(
            f"[WA-PIPELINE] _store_messages: stored={messages_stored}, "
            f"skipped_dup={skipped_duplicate}, skipped_empty={skipped_empty}"
        )
        return {
            "total_messages": len(records),
            "contacts": len(contacts),
            "leads_created": leads_created,
            "messages_stored": messages_stored,
            "skipped_duplicate": skipped_duplicate,
            "skipped_empty": skipped_empty,
        }

    @staticmethod
    def _extract_text(record: dict) -> Optional[str]:
        """Extract text content from a Baileys message record."""
        msg = record.get("message", {})
        if not msg:
            return None

        text = (
            msg.get("conversation")
            or (msg.get("extendedTextMessage") or {}).get("text")
            or (msg.get("imageMessage") or {}).get("caption")
            or (msg.get("videoMessage") or {}).get("caption")
        )
        if text:
            return text.strip()

        # Non-text media types — return descriptive placeholder
        if msg.get("audioMessage") or msg.get("pttMessage"):
            return "[audio]"
        if msg.get("imageMessage"):
            return "[image]"
        if msg.get("videoMessage"):
            return "[video]"
        if msg.get("stickerMessage"):
            return "[sticker]"
        if msg.get("documentMessage"):
            filename = (msg.get("documentMessage") or {}).get("fileName", "file")
            return f"[document: {filename}]"
        if msg.get("contactMessage"):
            return "[contact]"
        if msg.get("locationMessage"):
            return "[location]"
        if msg.get("reactionMessage"):
            emoji = (msg.get("reactionMessage") or {}).get("text", "")
            return f"[reaction: {emoji}]" if emoji else None

        return None

    @staticmethod
    def _detect_message_type(record: dict) -> str:
        """Detect the message type from a Baileys record."""
        msg = record.get("message", {})
        if not msg:
            return "unknown"
        if msg.get("conversation") or msg.get("extendedTextMessage"):
            return "text"
        if msg.get("audioMessage") or msg.get("pttMessage"):
            return "audio"
        if msg.get("imageMessage"):
            return "image"
        if msg.get("videoMessage"):
            return "video"
        if msg.get("stickerMessage"):
            return "sticker"
        if msg.get("documentMessage"):
            return "document"
        if msg.get("contactMessage"):
            return "contact"
        if msg.get("locationMessage"):
            return "location"
        if msg.get("reactionMessage"):
            return "reaction"
        return "unknown"

    # ─────────────────────────────────────────────────────────────────────
    # PHASE 2: STYLE ANALYSIS
    # ─────────────────────────────────────────────────────────────────────

    async def _phase2_style_analysis(self) -> dict:
        """Run ToneAnalyzer and VocabularyExtractor on creator messages."""
        self._update_progress(2, "style_analysis", 30)
        results: Dict[str, Any] = {}

        # 2a. ToneAnalyzer — expects posts with "caption" field
        #     ADAPTER: convert WhatsApp messages to posts format
        try:
            from ingestion.tone_analyzer import ToneAnalyzer

            iris_msgs = self._get_creator_messages(limit=100)
            posts = [
                {"caption": m["content"], "timestamp": m["created_at"]}
                for m in iris_msgs
                if m.get("content") and not m["content"].startswith("[")
            ]

            if posts:
                analyzer = ToneAnalyzer()
                tone_profile = await analyzer.analyze(self.creator_name, posts, max_posts=50)
                results["tone_analyzer"] = {
                    "status": "ok",
                    "posts_analyzed": len(posts[:50]),
                    "confidence": getattr(tone_profile, "confidence_score", None),
                }
            else:
                results["tone_analyzer"] = {"status": "skipped", "reason": "no_text_messages"}
        except Exception as e:
            logger.warning(f"[WA-PIPELINE] ToneAnalyzer failed: {e}")
            results["tone_analyzer"] = {"status": "error", "error": str(e)}

        # 2b. VocabularyExtractor — takes List[str]
        try:
            from services.vocabulary_extractor import VocabularyExtractor

            texts = [
                m["content"] for m in iris_msgs
                if m.get("content") and not m["content"].startswith("[")
            ]
            if texts:
                vocab = VocabularyExtractor().extract_all(texts)
                results["vocabulary"] = {
                    "status": "ok",
                    "common_words": len(vocab.get("common_words", [])),
                    "emojis": len(vocab.get("emojis", [])),
                }
            else:
                results["vocabulary"] = {"status": "skipped", "reason": "no_text_messages"}
        except Exception as e:
            logger.warning(f"[WA-PIPELINE] VocabularyExtractor failed: {e}")
            results["vocabulary"] = {"status": "error", "error": str(e)}

        self._update_progress(2, "style_analysis", 100)
        return results

    # ─────────────────────────────────────────────────────────────────────
    # PHASE 3: LEAD ANALYSIS
    # ─────────────────────────────────────────────────────────────────────

    async def _phase3_lead_analysis(self) -> dict:
        """Score leads and run RelationshipAnalyzer on top contacts."""
        self._update_progress(3, "lead_analysis", 30)
        results: Dict[str, Any] = {}

        # 3a. Batch recalculate scores — takes session + creator_name
        try:
            from api.database import SessionLocal
            from services.lead_scoring import batch_recalculate_scores

            session = SessionLocal()
            try:
                score_results = batch_recalculate_scores(session, self.creator_name)
                results["scoring"] = score_results
            finally:
                session.close()
        except Exception as e:
            logger.warning(f"[WA-PIPELINE] Lead scoring failed: {e}")
            results["scoring"] = {"error": str(e)}

        # 3b. RelationshipAnalyzer — top 20 leads by recent contact
        try:
            from services.relationship_analyzer import RelationshipAnalyzer

            top_leads = self._get_top_leads(limit=20)
            ra = RelationshipAnalyzer()
            analyzed = 0
            for lead in top_leads:
                msgs = self._get_messages_for_lead(lead["id"])
                if len(msgs) >= 5:
                    ra.analyze(self.creator_name, str(lead["platform_user_id"]), msgs)
                    analyzed += 1
            results["relationship_analyzer"] = {"status": "ok", "leads_analyzed": analyzed}
        except Exception as e:
            logger.warning(f"[WA-PIPELINE] RelationshipAnalyzer failed: {e}")
            results["relationship_analyzer"] = {"error": str(e)}

        self._update_progress(3, "lead_analysis", 100)
        return results

    # ─────────────────────────────────────────────────────────────────────
    # PHASE 4: MEMORY & INTELLIGENCE
    # ─────────────────────────────────────────────────────────────────────

    async def _phase4_memory_intelligence(self) -> dict:
        """Build memory, semantic index, personality, gold examples, DNA."""
        self._update_progress(4, "memory_intelligence", 10)
        results: Dict[str, Any] = {}

        # 4a. MemoryEngine — CRITICAL: pass UUID strings, not names!
        try:
            from services.memory_engine import MemoryEngine

            me = MemoryEngine()
            top_leads = self._get_top_leads(limit=50)
            facts_total = 0
            for lead in top_leads:
                msgs = self._get_messages_for_lead(lead["id"])
                if not msgs:
                    continue
                # Pass last 30 messages per lead to avoid token overload
                conversation = [
                    {"role": m["role"], "content": m["content"]}
                    for m in msgs[-30:]
                    if m.get("content") and not m["content"].startswith("[")
                ]
                if not conversation:
                    continue
                stored = await me.add(
                    creator_id=self.creator_db_id,      # UUID string!
                    lead_id=str(lead["id"]),             # UUID string!
                    conversation_messages=conversation,
                )
                facts_total += len(stored) if stored else 0
            results["memory_engine"] = {"status": "ok", "facts": facts_total, "leads": len(top_leads)}
        except Exception as e:
            logger.warning(f"[WA-PIPELINE] MemoryEngine failed: {e}")
            results["memory_engine"] = {"error": str(e)}

        self._update_progress(4, "memory_intelligence", 30)

        # 4b. SemanticMemory — top 30 leads, index last 50 messages each
        try:
            from core.semantic_memory_pgvector import get_semantic_memory

            top_leads = self._get_top_leads(limit=30)
            indexed = 0
            for lead in top_leads:
                sm = get_semantic_memory(self.creator_db_id, str(lead["id"]))  # UUIDs!
                msgs = self._get_messages_for_lead(lead["id"])
                for m in msgs[-50:]:
                    content = m.get("content", "")
                    if content and not content.startswith("["):
                        sm.add_message(role=m["role"], content=content)
                        indexed += 1
            results["semantic_memory"] = {"status": "ok", "indexed": indexed}
        except Exception as e:
            logger.warning(f"[WA-PIPELINE] SemanticMemory failed: {e}")
            results["semantic_memory"] = {"error": str(e)}

        self._update_progress(4, "memory_intelligence", 50)

        # 4c. PersonalityExtraction — needs creator UUID + DB session
        try:
            from api.database import SessionLocal
            from core.personality_extraction.extractor import PersonalityExtractor

            session = SessionLocal()
            try:
                extractor = PersonalityExtractor(db=session)
                extraction_result = await extractor.run(
                    creator_id=self.creator_db_id,      # UUID!
                    creator_name=self.creator_name,
                    skip_llm=False,
                    limit_leads=50,
                )
                docs_generated = sum([
                    bool(extraction_result.conversations),
                    bool(extraction_result.lead_analyses),
                    bool(extraction_result.personality_profile.raw_profile_text),
                    bool(extraction_result.bot_configuration.system_prompt),
                    bool(extraction_result.copilot_rules.raw_rules_text),
                ])
                results["personality_extraction"] = {
                    "status": "ok",
                    "docs_generated": docs_generated,
                }
            finally:
                session.close()

            # 4c-bis: Upsert ToneProfile from WritingStyle + Dictionary
            try:
                from api.models import ToneProfile

                ws = extraction_result.personality_profile.writing_style
                dic = extraction_result.personality_profile.dictionary

                filler_words = [
                    item.get("phrase", "") for item in (dic.greetings + dic.validation)[:15]
                    if isinstance(item, dict) and item.get("phrase")
                ]
                slang_words = [
                    item.get("phrase", "") for item in dic.unique_catchphrases[:10]
                    if isinstance(item, dict) and item.get("phrase")
                ]
                vocab_sample = list({
                    item.get("phrase", "")
                    for lst in [dic.greetings, dic.farewells, dic.gratitude, dic.unique_catchphrases]
                    for item in lst
                    if isinstance(item, dict) and item.get("phrase")
                })[:30]

                profile_data = {
                    "avg_message_length": ws.avg_message_length or 80.0,
                    "emoji_frequency": round(ws.emoji_pct / 100.0, 4),
                    "question_frequency": 0.2,
                    "filler_words": filler_words,
                    "slang_words": slang_words,
                    "vocabulary_sample": vocab_sample,
                    "primary_language": ws.primary_language,
                    "avg_emojis_per_msg": ws.avg_emojis_per_msg,
                    "top_emojis": [
                        e.get("emoji") for e in ws.top_emojis[:5]
                        if isinstance(e, dict)
                    ],
                }
                confidence_map = {"alta": 0.9, "media": 0.6, "baja": 0.3}
                confidence = confidence_map.get(
                    extraction_result.personality_profile.confidence, 0.6
                )

                from api.database import SessionLocal as _SL
                tp_session = _SL()
                try:
                    existing = tp_session.query(ToneProfile).filter_by(
                        creator_id=self.creator_name
                    ).first()
                    if existing:
                        existing.profile_data = profile_data
                        existing.analyzed_posts_count = (
                            extraction_result.personality_profile.messages_analyzed
                        )
                        existing.confidence_score = confidence
                    else:
                        tp_session.add(ToneProfile(
                            creator_id=self.creator_name,
                            profile_data=profile_data,
                            analyzed_posts_count=(
                                extraction_result.personality_profile.messages_analyzed
                            ),
                            confidence_score=confidence,
                        ))
                    tp_session.commit()
                    results["tone_profile"] = {"status": "ok", "confidence": confidence}
                    logger.info(
                        f"[WA-PIPELINE] ToneProfile upserted for {self.creator_name} "
                        f"(confidence={confidence})"
                    )
                finally:
                    tp_session.close()
            except Exception as tp_e:
                logger.warning(f"[WA-PIPELINE] ToneProfile write failed: {tp_e}")
                results["tone_profile"] = {"error": str(tp_e)}
        except Exception as e:
            logger.warning(f"[WA-PIPELINE] PersonalityExtraction failed: {e}")
            results["personality_extraction"] = {"error": str(e)}

        self._update_progress(4, "memory_intelligence", 70)

        # 4d. GoldExamples — reads from DB (copilot actions)
        try:
            from services.gold_examples_service import curate_examples

            r = await curate_examples(self.creator_name, self.creator_db_id)
            results["gold_examples"] = r
        except Exception as e:
            logger.warning(f"[WA-PIPELINE] GoldExamples failed: {e}")
            results["gold_examples"] = {"error": str(e)}

        # 4e. RelationshipDNA — per top lead
        try:
            from services.relationship_dna_service import get_dna_service

            dna_svc = get_dna_service()
            top_leads = self._get_top_leads(limit=30)
            dna_count = 0
            for lead in top_leads:
                msgs = self._get_messages_for_lead(lead["id"])
                if len(msgs) >= 5:
                    dna_svc.analyze_and_update_dna(
                        self.creator_name,
                        str(lead["platform_user_id"]),
                        msgs,
                    )
                    dna_count += 1
            results["relationship_dna"] = {"status": "ok", "leads": dna_count}
        except Exception as e:
            logger.warning(f"[WA-PIPELINE] RelationshipDNA failed: {e}")
            results["relationship_dna"] = {"error": str(e)}

        self._update_progress(4, "memory_intelligence", 100)
        return results

    # ─────────────────────────────────────────────────────────────────────
    # PHASE 5: CALIBRATION
    # ─────────────────────────────────────────────────────────────────────

    async def _phase5_calibration(self) -> dict:
        """Run CloneScoreEngine and PatternAnalyzer."""
        self._update_progress(5, "calibration", 50)
        results: Dict[str, Any] = {}

        # 5a. CloneScoreEngine — evaluate_batch reads from DB
        try:
            from services.clone_score_engine import CloneScoreEngine

            engine = CloneScoreEngine()
            score = await engine.evaluate_batch(self.creator_name, self.creator_db_id)
            results["clone_score"] = score
        except Exception as e:
            logger.warning(f"[WA-PIPELINE] CloneScoreEngine failed: {e}")
            results["clone_score"] = {"error": str(e)}

        # 5b. PatternAnalyzer — reads from DB
        try:
            from services.persona_compiler import compile_persona as run_pattern_analysis

            r = await run_pattern_analysis(self.creator_name, self.creator_db_id)
            results["pattern_analyzer"] = r
        except Exception as e:
            logger.warning(f"[WA-PIPELINE] PatternAnalyzer failed: {e}")
            results["pattern_analyzer"] = {"error": str(e)}

        self._update_progress(5, "calibration", 100)
        return results

    # ─────────────────────────────────────────────────────────────────────
    # DB HELPERS — query leads and messages
    # ─────────────────────────────────────────────────────────────────────

    def _get_creator_messages(self, limit: int = 100) -> List[dict]:
        """Get creator (assistant) messages from DB, ordered by created_at desc."""
        from api.database import SessionLocal
        from api.models import Lead, Message

        session = SessionLocal()
        try:
            rows = (
                session.query(Message)
                .join(Lead, Message.lead_id == Lead.id)
                .filter(
                    Lead.creator_id == self.creator_uuid,
                    Message.role == "assistant",
                    Message.content.isnot(None),
                )
                .order_by(Message.created_at.desc())
                .limit(limit)
                .all()
            )
            return [
                {
                    "content": m.content,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                    "role": m.role,
                }
                for m in rows
            ]
        finally:
            session.close()

    def _get_top_leads(self, limit: int = 50) -> List[dict]:
        """Get top leads by most recent contact."""
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
                {
                    "id": lead.id,
                    "platform_user_id": lead.platform_user_id,
                    "full_name": lead.full_name,
                    "status": lead.status,
                }
                for lead in leads
            ]
        finally:
            session.close()

    def _get_messages_for_lead(self, lead_id) -> List[dict]:
        """Get all messages for a lead, ordered chronologically."""
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
                {
                    "role": m.role,
                    "content": m.content or "",
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in msgs
            ]
        finally:
            session.close()
