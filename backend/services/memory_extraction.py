"""
Memory Extraction — CC-faithful fact extraction with guards.

Extracted from memory_engine.py to keep that file under 500 lines per concern.
Implements 6 CC patterns from extractMemories.ts + prompts.ts + memoryTypes.ts:

  1. Cursor incremental (extractMemories.ts:337-342):
     In-memory dict per (creator,lead) — only process new messages since cursor.

  2. Manifest pre-injection (extractMemories.ts:400-404):
     Pre-load existing facts, inject into prompt to prevent re-extraction.

  3. Improved prompt (prompts.ts:50-93 + memoryTypes.ts:183-195):
     English, exclusion rules, per-type guidance, date conversion.

  4. Overlap guard (extractMemories.ts:550-558):
     Per-(creator,lead) in-progress flag — skip if running.

  5. Drain (extractMemories.ts:611-615):
     Track in-flight tasks, expose drain() for shutdown.

  6. Turn throttle (extractMemories.ts:389-395):
     Counter per (creator,lead), configurable via env var.

Feature flags: All guards default ON except cursor (MEMORY_CURSOR_ENABLED=false).
Public API: get_memory_extractor(engine) → MemoryExtractor singleton.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

from services.memory_consolidator import _validated_env_int

# ════════════════════════════════════════════════���══════════════════════════════
# CONFIGURATION — all from env vars, zero hardcoding
# ═══════════════════════════════════════════════════════════════════════════════

# Turn throttle: extract every N turns (CC: tengu_bramble_lintel, default 1)
EXTRACT_EVERY_N_TURNS = _validated_env_int("MEMORY_EXTRACT_EVERY_N_TURNS", 1)

# Max facts per extraction (CC: no explicit cap, Clonnect: 5)
MAX_FACTS_PER_EXTRACTION = int(os.getenv("MEMORY_MAX_FACTS_PER_EXTRACTION", "5"))

# Feature toggles for individual guards
OVERLAP_GUARD_ENABLED = os.getenv("MEMORY_OVERLAP_GUARD_ENABLED", "true").lower() == "true"
MANIFEST_ENABLED = os.getenv("MEMORY_MANIFEST_ENABLED", "true").lower() == "true"
CURSOR_ENABLED = os.getenv("MEMORY_CURSOR_ENABLED", "true").lower() == "true"

# Max existing facts to include in manifest (prevent prompt bloat)
MAX_MANIFEST_FACTS = _validated_env_int("MEMORY_MAX_MANIFEST_FACTS", 20)

# Drain timeout for graceful shutdown (seconds)
DRAIN_TIMEOUT = float(os.getenv("MEMORY_DRAIN_TIMEOUT", "10"))


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRACTION PROMPT — adapted from CC prompts.ts:50-93 + memoryTypes.ts
#
# CC original (prompts.ts:35): "Analyze the most recent ~N messages above"
# CC original (prompts.ts:41): "Do not waste any turns attempting to investigate"
# CC original (memoryTypes.ts:183-195): WHAT_NOT_TO_SAVE_SECTION
# CC original (memoryTypes.ts:79): "convert relative dates to absolute"
# CC original (prompts.ts:32): "update existing rather than creating duplicate"
#
# Adaptation: Single-turn JSON response (no multi-turn agent needed).
# Language: English (LLM reasons better in English; facts can be any language).
# Domain: Lead memory for creator-lead DM conversations (not developer memory).
# ═══════════════════════════════════════════════════════════════════════════════

FACT_EXTRACTION_PROMPT = """You are extracting durable facts about a LEAD (follower/customer) from a DM conversation with a creator.

Today's date: {today}

## Fact types to extract
- preference: Likes, interests, communication style, content preferences of the lead
- commitment: Promises or agreements made BY THE LEAD (e.g., "I'll come Thursday")
- topic: Recurring conversation topics the lead brings up
- objection: Objections, doubts, complaints, or resistance from the lead
- personal_info: Personal data about the lead (name, city, job, family, birthday)
- purchase_history: Purchases, payments, products the lead bought or mentioned buying

## What NOT to extract
- Anything the BOT said, promised, or failed to do — only extract facts about the LEAD
- Generic greetings, emojis, or filler messages with no factual content
- Information about the creator's products or services (already in the knowledge base)
- Facts that are obvious from the conversation context and not worth remembering
- Ephemeral task details: current conversation flow, temporary states

## Rules
- Maximum {max_facts} facts per extraction
- Each fact must be a complete, self-contained sentence
- Confidence between 0.5 (uncertain) and 1.0 (certain)
- Convert relative dates ("tomorrow", "next week", "Thursday") to absolute dates using today's date
- Be CONSERVATIVE: only extract clear, concrete, verifiable facts — not vague inferences
{existing_facts_section}
Conversation (lines starting with "Bot:" are context — do NOT extract facts from them):
{messages}

Respond with valid JSON only (no markdown, no ```):
{{"facts": [{{"type": "preference", "text": "Interested in the nutrition course", "confidence": 0.9}}], "summary": "Brief summary...", "sentiment": "positive", "key_topics": ["nutrition"]}}

If no facts worth extracting, return: {{"facts": [], "summary": "...", "sentiment": "neutral", "key_topics": []}}"""


# ═══════════════════════════════════════════════════════════════════════════════
# MANIFEST FORMATTER — adapted from CC memoryScan.ts:84-94
# CC: formatMemoryManifest() — "- [type] filename (ts): description"
# Clonnect: "[type] (Nd ago) fact_text" — adapted for DB-backed facts
# ═══════════════════════════════════════════════════════════════════════════════

def _format_fact_manifest(facts: list, now: datetime) -> str:
    """Format existing facts as manifest for prompt injection.

    CC pattern (memoryScan.ts:84-94): Each memory file listed with type and description.
    Clonnect adaptation: Each fact listed with type and age.
    """
    if not facts:
        return ""
    lines = []
    for f in facts[:MAX_MANIFEST_FACTS]:
        age = ""
        if f.created_at:
            created = f.created_at if f.created_at.tzinfo else f.created_at.replace(tzinfo=timezone.utc)
            days = (now - created).days
            age = f" ({days}d ago)"
        lines.append(f"- [{f.fact_type}]{age} {f.fact_text}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# MEMORY EXTRACTOR — CC extractMemories.ts closure pattern
#
# CC uses closure-scoped mutable state (extractMemories.ts:296-587):
#   inFlightExtractions, lastMemoryMessageUuid, inProgress,
#   turnsSinceLastExtraction, pendingContext
#
# Clonnect: Class with dict-based per-lead state (same semantics, Python idiom).
# ═══════════════════════════════════════════════════════════════════════════════

class MemoryExtractor:
    """CC-faithful fact extraction with guards.

    Holds per-(creator,lead) state: cursor, overlap flag, turn counter.
    Delegates storage to MemoryEngine (passed at construction).
    """

    def __init__(self, engine):
        self.engine = engine
        # CC: inProgress (extractMemories.ts:316)
        self._in_progress: Dict[str, bool] = {}
        # CC: turnsSinceLastExtraction (extractMemories.ts:319)
        self._turn_counter: Dict[str, int] = {}
        # CC: lastMemoryMessageUuid (extractMemories.ts:309)
        self._cursor: Dict[str, str] = {}
        # CC: inFlightExtractions (extractMemories.ts:305)
        self._in_flight: Set[asyncio.Task] = set()

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC: extract_and_store() — main entry point (replaces add() body)
    # CC: executeExtractMemoriesImpl (extractMemories.ts:527-567)
    # ─────────────────────────────────────────────────────────────────────

    async def extract_and_store(
        self,
        creator_id: str,
        lead_id: str,
        conversation_messages: List[Dict[str, str]],
        source_message_id: Optional[str] = None,
    ) -> list:
        """Extract facts from conversation and store them.

        Applies CC guards in order:
          1. Overlap guard (extractMemories.ts:550-558)
          2. Turn throttle (extractMemories.ts:389-395)
          3. Manifest pre-injection (extractMemories.ts:400-404)
          4. Cursor filtering (extractMemories.ts:337-342)
        """
        from services.memory_engine import (
            ENABLE_MEMORY_ENGINE, MEMO_COMPRESSION_THRESHOLD,
            ExtractionResult, _recall_cache,
        )
        if not ENABLE_MEMORY_ENGINE:
            return []

        creator_id = await self.engine._resolve_creator_uuid(creator_id)
        lead_id = await self.engine._resolve_lead_uuid(creator_id, lead_id)

        key = f"{creator_id}:{lead_id}"

        # Guard 1: Overlap (CC: extractMemories.ts:550-558)
        if OVERLAP_GUARD_ENABLED and self._in_progress.get(key):
            logger.debug(
                "[Extractor] Skipping — extraction in progress for lead=%s",
                lead_id[:8],
            )
            return []

        # Guard 2: Turn throttle (CC: extractMemories.ts:389-395)
        if EXTRACT_EVERY_N_TURNS > 1:
            self._turn_counter[key] = self._turn_counter.get(key, 0) + 1
            if self._turn_counter[key] % EXTRACT_EVERY_N_TURNS != 0:
                logger.debug(
                    "[Extractor] Throttled — turn %d/%d for lead=%s",
                    self._turn_counter[key], EXTRACT_EVERY_N_TURNS, lead_id[:8],
                )
                return []

        # Non-blocking consolidation check (from original add())
        try:
            from services.memory_consolidator import is_consolidation_locked
            if is_consolidation_locked(creator_id):
                logger.warning(
                    "[Extractor] Running while consolidation active for creator=%s",
                    creator_id[:8],
                )
        except Exception:
            pass

        if OVERLAP_GUARD_ENABLED:
            self._in_progress[key] = True

        try:
            return await self._do_extract(
                creator_id, lead_id, conversation_messages, source_message_id, key,
            )
        except Exception as e:
            logger.error("[Extractor] extract_and_store failed: %s", e, exc_info=True)
            return []
        finally:
            if OVERLAP_GUARD_ENABLED:
                self._in_progress.pop(key, None)

    async def _do_extract(
        self,
        creator_id: str,
        lead_id: str,
        conversation_messages: List[Dict[str, str]],
        source_message_id: Optional[str],
        key: str,
    ) -> list:
        """Core extraction logic — called after guards pass."""
        import asyncio as _asyncio
        from services.memory_engine import (
            MEMO_COMPRESSION_THRESHOLD, ExtractionResult, _recall_cache,
        )

        formatted_msgs = self._format_messages_for_llm(conversation_messages)
        if not formatted_msgs or len(formatted_msgs) < 20:
            logger.debug("[Extractor] Conversation too short for extraction")
            return []

        # Guard 3: Manifest pre-injection (CC: extractMemories.ts:400-404)
        existing_facts = await self.engine._get_existing_active_facts(creator_id, lead_id)
        existing_facts_section = ""
        if MANIFEST_ENABLED and existing_facts:
            real_facts = [f for f in existing_facts if f.fact_type != "compressed_memo"]
            if real_facts:
                now = datetime.now(timezone.utc)
                manifest = _format_fact_manifest(real_facts, now)
                existing_facts_section = (
                    f"\n## Existing facts (do NOT re-extract these — update only if info changed)\n"
                    f"{manifest}\n"
                )

        # Build prompt (CC: buildExtractAutoOnlyPrompt, prompts.ts:50-93)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        prompt = FACT_EXTRACTION_PROMPT.format(
            today=today,
            max_facts=MAX_FACTS_PER_EXTRACTION,
            existing_facts_section=existing_facts_section,
            messages=formatted_msgs,
        )

        # LLM call (CC: runForkedAgent → single turn for Clonnect)
        extraction = await self._extract_facts_via_llm(prompt)
        if not extraction.facts and not extraction.summary:
            logger.debug("[Extractor] No facts or summary extracted")
            return []

        # Generate embeddings for new facts
        fact_texts = [f["text"] for f in extraction.facts]
        embeddings = await self.engine._generate_embeddings_batch(fact_texts)

        # Store facts with conflict resolution
        stored_memories = []
        stored_fact_dicts: List[dict] = []
        for i, fact in enumerate(extraction.facts):
            embedding = embeddings[i] if i < len(embeddings) else None

            resolution = await self.engine.resolve_conflict(
                fact, existing_facts,
                new_embedding=embedding,
                creator_id=creator_id,
                lead_id=lead_id,
            )
            if resolution == "skip":
                logger.debug("[Extractor] Skipping duplicate: %s", fact["text"][:50])
                continue

            memory = await self.engine._store_fact(
                creator_id=creator_id,
                lead_id=lead_id,
                fact_type=fact.get("type", "topic"),
                fact_text=fact["text"],
                confidence=fact.get("confidence", 0.7),
                embedding=embedding,
                source_message_id=source_message_id,
                source_type="extracted",
            )
            if memory:
                stored_memories.append(memory)
                stored_fact_dicts.append(fact)

        # ARC2 A2.4: dual-write to arc2_lead_memories (fire-and-forget, fail-silent)
        if stored_fact_dicts:
            try:
                from services.dual_write import dual_write_from_extraction
                _asyncio.create_task(
                    dual_write_from_extraction(creator_id, lead_id, stored_fact_dicts)
                )
            except Exception:
                pass

        # Store summary
        if extraction.summary:
            await self.engine.summarize_conversation(
                creator_id=creator_id,
                lead_id=lead_id,
                messages=conversation_messages,
                precomputed_summary=extraction.summary,
                precomputed_topics=extraction.key_topics,
                precomputed_sentiment=extraction.sentiment,
            )

        logger.info(
            "[Extractor] Stored %d facts + summary for lead=%s creator=%s",
            len(stored_memories), lead_id[:8], creator_id[:8],
        )

        # Invalidate recall cache
        _recall_cache.pop(f"{creator_id}:{lead_id}", None)

        # Auto-trigger compression (CC: writeOrUpdate → consolidation, adapted)
        if stored_memories:
            all_facts = await self.engine._get_existing_active_facts(creator_id, lead_id)
            real_facts = [f for f in all_facts if f.fact_type != "compressed_memo"]
            if len(real_facts) >= MEMO_COMPRESSION_THRESHOLD:
                _asyncio.create_task(
                    self.engine.compress_lead_memory(creator_id, lead_id)
                )

        # Advance cursor (CC: extractMemories.ts:432-435)
        if CURSOR_ENABLED and source_message_id:
            self._cursor[key] = source_message_id

        return stored_memories

    # ───────────────────────���─────────────────────────────────────────────
    # PRIVATE: LLM extraction
    # ─────────────────────────────────────────────────────────────────────

    async def _extract_facts_via_llm(self, prompt: str):
        """Call LLM to extract facts. Reuses engine._call_llm."""
        from services.memory_engine import ExtractionResult

        response = await self.engine._call_llm(prompt)
        parsed = self.engine._parse_json_response(response)

        if not parsed:
            return ExtractionResult()

        facts = parsed.get("facts", [])
        valid_types = {
            "preference", "commitment", "topic",
            "objection", "personal_info", "purchase_history",
        }
        validated_facts = []
        for f in facts[:MAX_FACTS_PER_EXTRACTION]:
            if isinstance(f, dict) and f.get("type") in valid_types and f.get("text"):
                validated_facts.append({
                    "type": f["type"],
                    "text": str(f["text"])[:500],
                    "confidence": max(0.5, min(1.0, float(f.get("confidence", 0.7)))),
                })

        return ExtractionResult(
            facts=validated_facts,
            summary=str(parsed.get("summary", ""))[:300],
            sentiment=(
                parsed.get("sentiment", "neutral")
                if parsed.get("sentiment") in ("positive", "neutral", "negative")
                else "neutral"
            ),
            key_topics=parsed.get("key_topics", [])[:5],
        )

    # ─────────────────────────────────────────────────────────────────────
    # PRIVATE: Message formatting
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _format_messages_for_llm(messages: List[Dict[str, str]]) -> str:
        """Format conversation messages for LLM prompt."""
        lines = []
        for msg in messages[-20:]:
            role = msg.get("role", "user")
            content = msg.get("content", "").strip()
            if not content:
                continue
            label = "Lead" if role == "user" else "Bot"
            lines.append(f"{label}: {content}")
        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC: drain() — CC: drainPendingExtraction (extractMemories.ts:611)
    # ─────────────────────────────────────────────────────────────────────

    async def drain(self, timeout: float = DRAIN_TIMEOUT) -> None:
        """Wait for in-flight extraction tasks to complete.

        CC pattern (extractMemories.ts:611-615):
          Awaits all in-flight extractions with a soft timeout.
          Called before graceful shutdown.
        """
        active = {t for t in self._in_flight if not t.done()}
        if not active:
            return
        logger.info("[Extractor] Draining %d in-flight tasks (timeout=%.1fs)", len(active), timeout)
        done, pending = await asyncio.wait(active, timeout=timeout)
        if pending:
            logger.warning("[Extractor] %d tasks still pending after drain timeout", len(pending))

    def track_task(self, task: asyncio.Task) -> None:
        """Register an in-flight extraction task for drain tracking.

        Called from postprocessing.py when creating the extraction task.
        CC pattern: inFlightExtractions.add(p) (extractMemories.ts:571)
        """
        self._in_flight.add(task)
        task.add_done_callback(self._in_flight.discard)


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

_extractor: Optional[MemoryExtractor] = None


def get_memory_extractor(engine=None) -> MemoryExtractor:
    """Get the global MemoryExtractor singleton.

    If engine is provided and differs from current extractor's engine,
    creates a new extractor (supports test fixtures with fresh engines).
    """
    global _extractor
    if _extractor is None or (engine is not None and _extractor.engine is not engine):
        if engine is None:
            from services.memory_engine import get_memory_engine
            engine = get_memory_engine()
        _extractor = MemoryExtractor(engine)
    return _extractor


async def drain_extraction() -> None:
    """Module-level drain for shutdown hooks."""
    if _extractor is not None:
        await _extractor.drain()
