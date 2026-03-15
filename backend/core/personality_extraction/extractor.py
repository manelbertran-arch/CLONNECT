"""
PersonalityExtractor — Main orchestrator for the extraction pipeline.

Executes all 5 phases sequentially and produces the complete extraction result
with 5 output documents.
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from core.personality_extraction.bot_configurator import (
    generate_bot_configuration,
    generate_doc_d,
)
from core.personality_extraction.conversation_formatter import (
    format_all_conversations,
    generate_doc_a,
)
from core.personality_extraction.copilot_rules import (
    generate_copilot_rules,
    generate_doc_e,
)
from core.personality_extraction.data_cleaner import extract_conversations
from core.personality_extraction.lead_analyzer import (
    analyze_all_leads,
    generate_doc_b,
)
from core.personality_extraction.models import ExtractionResult
from core.personality_extraction.personality_profiler import (
    compute_creator_dictionary,
    compute_writing_style,
    generate_doc_c,
    generate_personality_profile,
)

logger = logging.getLogger(__name__)

# Output directory for extraction results
OUTPUT_DIR = Path("data/personality_extractions")


class PersonalityExtractor:
    """
    Orchestrates the complete personality extraction pipeline.

    Usage:
        extractor = PersonalityExtractor(db_session)
        result = await extractor.run(creator_id="some-uuid")
    """

    def __init__(self, db: Session):
        self.db = db

    async def run(
        self,
        creator_id: str,
        creator_name: str = "",
        output_dir: Optional[str] = None,
        skip_llm: bool = False,
        limit_leads: Optional[int] = None,
    ) -> ExtractionResult:
        """
        Run the complete extraction pipeline.

        Args:
            creator_id: UUID of the creator in the database
            creator_name: Display name for reports
            output_dir: Directory to save output documents (default: data/personality_extractions/{creator_id}/)
            skip_llm: If True, skip LLM phases (only do statistical analysis). Useful for testing.
            limit_leads: Max leads to process (None = all)

        Returns:
            ExtractionResult with all 5 documents
        """
        start_time = time.monotonic()
        result = ExtractionResult(
            creator_id=creator_id,
            creator_name=creator_name,
            started_at=datetime.now(),
        )

        from api.database import SessionLocal as _SL

        # Resolve creator name from DB if not provided — short-lived session
        if not creator_name:
            from sqlalchemy import text
            _s = _SL()
            try:
                row = _s.execute(
                    text("SELECT name FROM creators WHERE id = :id OR name = :id LIMIT 1"),
                    {"id": creator_id},
                ).fetchone()
                if row:
                    result.creator_name = row.name
                    creator_name = row.name
            finally:
                _s.close()

        # Setup output directory
        out_dir = Path(output_dir) if output_dir else OUTPUT_DIR / creator_id
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            # ── Phase 0: Data Cleaning ──────────────────────────────
            logger.info("═══ PHASE 0: Data Cleaning ═══")
            _s = _SL()
            try:
                # Default limit: 50 leads to cap LLM costs in Phase 2
                # (each lead = 1 LLM call). Override via limit_leads param.
                effective_limit = limit_leads or int(os.getenv("EXTRACTION_MAX_LEADS", "50"))
                conversations, stats = extract_conversations(
                    _s, creator_id, min_messages=1, limit_leads=effective_limit,
                )
            finally:
                _s.close()
            result.cleaning_stats = stats

            if not conversations:
                result.errors.append("No conversations found for this creator")
                result.completed_at = datetime.now()
                result.duration_seconds = time.monotonic() - start_time
                return result

            logger.info(
                "Phase 0 complete: %d leads, %d creator real messages, %.1f%% clean",
                stats.total_leads, stats.creator_real, stats.clean_ratio * 100,
            )

            # ── Phase 1: Doc A — Formatted Conversations ──────────
            logger.info("═══ PHASE 1: Formatting Conversations (Doc A) ═══")
            formatted = format_all_conversations(conversations)
            result.conversations = formatted
            doc_a = generate_doc_a(formatted)
            _save_document(out_dir / "doc_a_conversations.md", doc_a)
            logger.info("Phase 1 complete: %d conversations formatted", len(formatted))

            # ── Phase 2: Doc B — Lead Analysis ────────────────────
            if skip_llm:
                logger.info("═══ PHASE 2: SKIPPED (skip_llm=True) ═══")
                doc_b = "# Doc B: SKIPPED (skip_llm=True)"
            else:
                logger.info("═══ PHASE 2: Analyzing Leads (Doc B) ═══")
                analyses, superficial = await analyze_all_leads(conversations, creator_name)
                result.lead_analyses = analyses
                result.superficial_leads = superficial
                doc_b = generate_doc_b(analyses, superficial)
                logger.info(
                    "Phase 2 complete: %d full + %d superficial analyses",
                    len(analyses), len(superficial),
                )

            _save_document(out_dir / "doc_b_lead_analysis.md", doc_b)

            # ── Phase 3: Doc C — Personality Profile ──────────────
            logger.info("═══ PHASE 3: Computing Writing Style + Dictionary + Personality Profile (Doc C) ═══")
            writing_style = compute_writing_style(conversations)
            dictionary = compute_creator_dictionary(conversations)
            logger.info(
                "Dictionary computed: %d greetings, %d farewells, %d gratitude, %d questions",
                len(dictionary.greetings), len(dictionary.farewells),
                len(dictionary.gratitude), len(dictionary.frequent_questions),
            )

            # Calculate months covered
            all_dates = []
            for conv in conversations:
                if conv.first_message_at:
                    all_dates.append(conv.first_message_at)
                if conv.last_message_at:
                    all_dates.append(conv.last_message_at)
            months_covered = 0
            if all_dates:
                span = max(all_dates) - min(all_dates)
                months_covered = max(1, span.days // 30)

            # Confidence based on data volume
            if stats.creator_real >= 200:
                confidence = "alta"
            elif stats.creator_real >= 50:
                confidence = "media"
            else:
                confidence = "baja"

            if skip_llm:
                from core.personality_extraction.models import PersonalityProfile
                result.personality_profile = PersonalityProfile(
                    creator_name=creator_name,
                    messages_analyzed=stats.creator_real,
                    leads_analyzed=stats.total_leads,
                    months_covered=months_covered,
                    writing_style=writing_style,
                    dictionary=dictionary,
                    confidence=confidence,
                )
            else:
                result.personality_profile = await generate_personality_profile(
                    conversations=conversations,
                    lead_analyses_text=doc_b,
                    writing_style=writing_style,
                    dictionary=dictionary,
                    creator_name=creator_name,
                )

            doc_c = generate_doc_c(result.personality_profile)
            _save_document(out_dir / "doc_c_personality_profile.md", doc_c)
            logger.info(
                "Phase 3 complete: %d messages analyzed, confidence=%s",
                result.personality_profile.messages_analyzed,
                result.personality_profile.confidence,
            )

            # ── Phase 4: Doc D — Bot Configuration ────────────────
            if skip_llm:
                logger.info("═══ PHASE 4: SKIPPED (skip_llm=True) ═══")
                doc_d = "# Doc D: SKIPPED (skip_llm=True)"
            else:
                logger.info("═══ PHASE 4: Generating Bot Configuration (Doc D) ═══")
                result.bot_configuration = await generate_bot_configuration(
                    result.personality_profile,
                    conversations=conversations,
                )
                doc_d = generate_doc_d(result.bot_configuration)
                logger.info(
                    "Phase 4 complete: system_prompt=%d chars, %d template categories, %d blacklist phrases",
                    len(result.bot_configuration.system_prompt),
                    len(result.bot_configuration.template_categories),
                    len(result.bot_configuration.blacklist_phrases),
                )

            _save_document(out_dir / "doc_d_bot_configuration.md", doc_d)

            # ── Phase 5: Doc E — Copilot Rules ────────────────────
            if skip_llm:
                logger.info("═══ PHASE 5: SKIPPED (skip_llm=True) ═══")
                doc_e = "# Doc E: SKIPPED (skip_llm=True)"
            else:
                logger.info("═══ PHASE 5: Generating Copilot Rules (Doc E) ═══")
                bot_summary = (
                    f"System prompt: {len(result.bot_configuration.system_prompt)} chars\n"
                    f"Blacklist: {len(result.bot_configuration.blacklist_phrases)} phrases\n"
                    f"Templates: {len(result.bot_configuration.template_categories)} categories\n"
                    f"Max length: {result.bot_configuration.max_message_length_chars}\n"
                    f"Max emojis/msg: {result.bot_configuration.max_emojis_per_message}\n"
                )
                result.copilot_rules = await generate_copilot_rules(
                    result.personality_profile,
                    bot_config_summary=bot_summary,
                )
                doc_e = generate_doc_e(result.copilot_rules)
                logger.info(
                    "Phase 5 complete: mode=%s, AUTO=%.0f%%, DRAFT=%.0f%%, MANUAL=%.0f%%",
                    result.copilot_rules.global_mode,
                    result.copilot_rules.auto_pct,
                    result.copilot_rules.draft_pct,
                    result.copilot_rules.manual_pct,
                )

            _save_document(out_dir / "doc_e_copilot_rules.md", doc_e)

            # ── Save summary JSON ─────────────────────────────────
            result.completed_at = datetime.now()
            result.duration_seconds = round(time.monotonic() - start_time, 2)

            summary = {
                "creator_id": creator_id,
                "creator_name": creator_name,
                "started_at": result.started_at.isoformat(),
                "completed_at": result.completed_at.isoformat(),
                "duration_seconds": result.duration_seconds,
                "cleaning_stats": {
                    "total_messages": stats.total_messages,
                    "creator_real": stats.creator_real,
                    "copilot_ai": stats.copilot_ai,
                    "uncertain": stats.uncertain,
                    "lead_messages": stats.lead_messages,
                    "total_leads": stats.total_leads,
                    "leads_with_enough_data": stats.leads_with_enough_data,
                    "clean_ratio": round(stats.clean_ratio, 4),
                },
                "profile": {
                    "messages_analyzed": result.personality_profile.messages_analyzed,
                    "leads_analyzed": result.personality_profile.leads_analyzed,
                    "months_covered": result.personality_profile.months_covered,
                    "confidence": result.personality_profile.confidence,
                },
                "bot_config": {
                    "system_prompt_length": len(result.bot_configuration.system_prompt),
                    "blacklist_count": len(result.bot_configuration.blacklist_phrases),
                    "template_categories": len(result.bot_configuration.template_categories),
                    "max_message_length": result.bot_configuration.max_message_length_chars,
                },
                "copilot": {
                    "mode": result.copilot_rules.global_mode,
                    "auto_pct": result.copilot_rules.auto_pct,
                    "draft_pct": result.copilot_rules.draft_pct,
                    "manual_pct": result.copilot_rules.manual_pct,
                },
                "errors": result.errors,
                "warnings": result.warnings,
            }
            _save_document(out_dir / "extraction_summary.json", json.dumps(summary, indent=2, ensure_ascii=False))

            # Persist Doc D and Doc E to DB (survives Railway deploys)
            _save_docs_to_db(creator_id, {"doc_d": doc_d, "doc_e": doc_e})

            logger.info(
                "═══ EXTRACTION COMPLETE in %.1fs ═══ "
                "Creator: %s | %d messages | %d leads | %d docs saved to %s",
                result.duration_seconds,
                creator_name,
                stats.total_messages,
                stats.total_leads,
                5,
                out_dir,
            )

        except Exception as e:
            logger.error("Extraction failed: %s", e, exc_info=True)
            result.errors.append(str(e))
            result.completed_at = datetime.now()
            result.duration_seconds = round(time.monotonic() - start_time, 2)

        return result


def _save_document(path: Path, content: str) -> None:
    """Save a document to disk."""
    try:
        path.write_text(content, encoding="utf-8")
        logger.info("Saved: %s (%d chars)", path, len(content))
    except Exception as e:
        logger.error("Failed to save %s: %s", path, e)


def _save_docs_to_db(creator_id: str, docs: dict) -> None:
    """Persist Doc D and/or Doc E to PostgreSQL personality_docs table.

    This is the critical persistence layer — Railway's ephemeral filesystem
    loses all disk files on every deploy. DB storage survives deploys.

    Args:
        creator_id: Creator UUID or slug
        docs: Dict mapping doc_type ('doc_d', 'doc_e') -> markdown content string
    """
    try:
        from api.database import SessionLocal as _SL
        from sqlalchemy import text

        _s = _SL()
        try:
            for doc_type, content in docs.items():
                if not content or content.startswith("# Doc"):
                    # Skip skipped/empty docs (e.g. "# Doc D: SKIPPED (skip_llm=True)")
                    continue
                _s.execute(
                    text(
                        """
                        INSERT INTO personality_docs (id, creator_id, doc_type, content)
                        VALUES (CAST(:id AS uuid), :creator_id, :doc_type, :content)
                        ON CONFLICT (creator_id, doc_type)
                        DO UPDATE SET content = EXCLUDED.content,
                                      updated_at = now()
                        """
                    ),
                    {"id": str(uuid.uuid4()), "creator_id": creator_id, "doc_type": doc_type, "content": content},
                )
            _s.commit()
            logger.info(
                "Persisted docs to DB for creator %s: %s",
                creator_id,
                list(docs.keys()),
            )
        finally:
            _s.close()
    except Exception as e:
        logger.error("Failed to persist docs to DB for creator %s: %s", creator_id, e)
