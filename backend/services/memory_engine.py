"""
Memory Engine — Per-lead fact extraction, semantic recall, and Ebbinghaus decay.

Three-level memory architecture:
  1. Conversation Buffer — exists (follower.last_messages in dm_agent_v2)
  2. Lead Memory — NEW (this module): extracted facts + pgvector search
  3. Creator Knowledge — exists (RAG + personality)

Entry points:
  - add()       — Extract facts from conversation and store
  - search()    — Semantic search for relevant facts
  - recall()    — Format memories for prompt injection
  - summarize_conversation() — Generate and store summary
  - resolve_conflict() — Handle duplicate/contradictory facts
  - forget_lead() — GDPR right to erasure
  - decay_memories() — Ebbinghaus eviction of stale facts

Feature flags: ENABLE_MEMORY_ENGINE, ENABLE_MEMORY_DECAY
"""

import asyncio
import json
import logging
import math
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Feature flags
ENABLE_MEMORY_ENGINE = os.getenv("ENABLE_MEMORY_ENGINE", "false").lower() == "true"
ENABLE_MEMORY_DECAY = os.getenv("ENABLE_MEMORY_DECAY", "false").lower() == "true"

# Configuration
MAX_FACTS_PER_EXTRACTION = int(os.getenv("MEMORY_MAX_FACTS_PER_EXTRACTION", "5"))
MAX_FACTS_IN_PROMPT = int(os.getenv("MEMORY_MAX_FACTS_IN_PROMPT", "10"))
MEMORY_MIN_SIMILARITY = float(os.getenv("MEMORY_MIN_SIMILARITY", "0.4"))
DECAY_HALF_LIFE_BASE_DAYS = float(os.getenv("MEMORY_DECAY_HALF_LIFE_DAYS", "30"))
DECAY_THRESHOLD = float(os.getenv("MEMORY_DECAY_THRESHOLD", "0.1"))

# In-memory recall cache (per-lead, short TTL)
# BoundedTTLCache: LRU eviction + TTL, prevents unbounded growth with many leads.
from core.cache import BoundedTTLCache as _BoundedTTLCache
_RECALL_CACHE_MAX_SIZE = int(os.getenv("MEMORY_RECALL_CACHE_MAX_SIZE", "500"))
_RECALL_CACHE_TTL = int(os.getenv("MEMORY_RECALL_CACHE_TTL", "60"))
_recall_cache = _BoundedTTLCache(max_size=_RECALL_CACHE_MAX_SIZE, ttl_seconds=_RECALL_CACHE_TTL)


# ═══════════════════════════════════════════════════════════════════════════════
# DATACLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LeadMemory:
    """Represents a single extracted fact about a lead."""
    id: str = ""
    creator_id: str = ""
    lead_id: str = ""
    fact_type: str = ""
    fact_text: str = ""
    confidence: float = 0.7
    source_message_id: Optional[str] = None
    source_type: str = "extracted"
    times_accessed: int = 0
    last_accessed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    similarity: float = 0.0


@dataclass
class ConversationSummaryData:
    """Represents a conversation summary."""
    id: str = ""
    creator_id: str = ""
    lead_id: str = ""
    summary_text: str = ""
    key_topics: List[str] = field(default_factory=list)
    commitments_made: List[str] = field(default_factory=list)
    sentiment: str = "neutral"
    message_count: int = 0
    created_at: Optional[datetime] = None


@dataclass
class ExtractionResult:
    """Result of LLM fact extraction."""
    facts: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    sentiment: str = "neutral"
    key_topics: List[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# LLM PROMPTS (Spanish)
# ═══════════════════════════════════════════════════════════════════════════════

# FACT_EXTRACTION_PROMPT moved to services/memory_extraction.py
# (CC-faithful prompt with manifest pre-injection, exclusion rules, date conversion)

CONVERSATION_SUMMARY_PROMPT = """Resume esta conversacion de DMs entre un creador y un lead.

Conversacion:
{messages}

Responde UNICAMENTE con JSON valido:
{{"summary": "Resumen breve de la conversacion (max 2 frases)", "key_topics": ["tema1", "tema2"], "commitments": ["promesa1"], "sentiment": "positive|neutral|negative"}}"""

MEMO_COMPRESSION_PROMPT = """Eres un asistente que resume informacion sobre un lead (seguidor/cliente).

Dado estos hechos sobre un lead de {creator_name}, crea un resumen narrativo breve que capture la esencia de quien es, que quiere, y cual es su relacion con {creator_name}.

El memo debe incluir (solo si hay datos):
- Nombre y datos basicos
- Servicios o contenido de interes
- Estado de la relacion (nuevo, cliente habitual, amigo/a)
- Compromisos pendientes o eventos importantes
- Idioma preferido

Hechos:
{facts}

Escribe el resumen en el mismo idioma predominante de los hechos proporcionados.
Escribe el resumen narrativo en 2-4 frases. NO uses formato de lista. NO inventes datos que no esten en los hechos. Responde SOLO con el texto del resumen, sin comillas ni formato."""

# Threshold: compress when a lead has more than this many facts
MEMO_COMPRESSION_THRESHOLD = int(os.getenv("MEMO_COMPRESSION_THRESHOLD", "8"))

# TTL for temporal facts (days)
TEMPORAL_FACT_TTL_DAYS = int(os.getenv("MEMORY_TEMPORAL_TTL_DAYS", "7"))

# Temporal markers (multilingual: ES/CA/EN) — facts containing these expire
_TEMPORAL_MARKERS = re.compile(
    r'\b(mañana|hoy|esta semana|próximo|siguiente|'
    r'demà|avui|aquesta setmana|proper|següent|'
    r'tomorrow|today|this week|next week|'
    r'lunes|martes|miércoles|jueves|viernes|sábado|domingo|'
    r'dilluns|dimarts|dimecres|dijous|divendres|dissabte|diumenge|'
    r'monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
    re.IGNORECASE,
)


def _is_temporal_fact(fact_text: str) -> bool:
    """Check if a fact contains temporal markers that make it ephemeral."""
    return bool(_TEMPORAL_MARKERS.search(fact_text))


# ═══════════════════════════════════════════════════════════════════════════════
# MEMORY ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class MemoryEngine:
    """Per-lead memory engine with fact extraction and semantic recall."""

    # ─────────────────────────────────────────────────────────────────────
    # PRIVATE: _resolve_creator_uuid() — resolve slug → UUID
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    async def _resolve_creator_uuid(creator_id: str) -> str:
        """Return the DB UUID for a creator, resolving slug names if needed."""
        try:
            uuid.UUID(creator_id)
            return creator_id  # Already a valid UUID
        except (ValueError, AttributeError):
            pass
        # Slug path: look up by name
        def _lookup():
            from api.database import SessionLocal
            from sqlalchemy import text
            session = SessionLocal()
            try:
                row = session.execute(
                    text("SELECT id FROM creators WHERE name = :name LIMIT 1"),
                    {"name": creator_id},
                ).fetchone()
                if row:
                    return str(row[0])
            finally:
                session.close()
            return None
        try:
            result = await asyncio.to_thread(_lookup)
            if result:
                return result
        except Exception as e:
            logger.debug("[MemoryEngine] _resolve_creator_uuid failed for %s: %s", creator_id, e)
        return creator_id

    async def _resolve_lead_uuid(self, creator_uuid: str, lead_id: str) -> str:
        """Return the DB UUID for a lead, resolving platform_user_id if needed.

        BUG-001 fix: Strip platform prefixes (ig_, wa_, tg_) before building
        the search array so both "ig_1234567890" and "1234567890" resolve to
        the same lead regardless of how platform_user_id is stored in the DB.
        """
        try:
            uuid.UUID(lead_id)
            return lead_id  # Already a valid UUID
        except (ValueError, AttributeError):
            pass

        # Strip platform prefix to get raw numeric ID (BUG-001)
        raw_id = lead_id
        for prefix in ("ig_", "wa_", "tg_"):
            if raw_id.startswith(prefix):
                raw_id = raw_id[len(prefix):]
                break

        # platform_user_id path: look up by creator + platform_user_id
        def _lookup():
            from api.database import SessionLocal
            from sqlalchemy import text
            session = SessionLocal()
            try:
                row = session.execute(
                    text(
                        "SELECT id FROM leads "
                        "WHERE creator_id = CAST(:cid AS uuid) "
                        "AND platform_user_id = ANY(ARRAY[:pid, :pid_raw, :pid_ig, :pid_wa, :pid_tg]) "
                        "LIMIT 1"
                    ),
                    {
                        "cid": creator_uuid,
                        "pid": lead_id,
                        "pid_raw": raw_id,
                        "pid_ig": f"ig_{raw_id}",
                        "pid_wa": f"wa_{raw_id}",
                        "pid_tg": f"tg_{raw_id}",
                    },
                ).fetchone()
                if row:
                    return str(row[0])
            finally:
                session.close()
            return None
        try:
            result = await asyncio.to_thread(_lookup)
            if result:
                return result
        except Exception as e:
            logger.warning("[MemoryEngine] _resolve_lead_uuid failed for %s: %s", lead_id, e)
        return lead_id

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC: add() — Extract and store facts from conversation
    # ─────────────────────────────────────────────────────────────────────

    async def add(
        self,
        creator_id: str,
        lead_id: str,
        conversation_messages: List[Dict[str, str]],
        source_message_id: Optional[str] = None,
    ) -> List[LeadMemory]:
        """Extract facts from conversation and store them.

        Delegates to MemoryExtractor (services/memory_extraction.py) which
        applies CC-faithful guards: overlap, throttle, manifest, cursor.
        CC pattern: extractMemories.ts:598-603 delegates to closure.
        """
        if not ENABLE_MEMORY_ENGINE:
            return []
        from services.memory_extraction import get_memory_extractor
        extractor = get_memory_extractor(self)
        return await extractor.extract_and_store(
            creator_id, lead_id, conversation_messages, source_message_id,
        )

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC: search() — Semantic search for relevant facts
    # ─────────────────────────────────────────────────────────────────────

    async def search(
        self,
        creator_id: str,
        lead_id: str,
        query: str,
        top_k: int = 5,
    ) -> List[LeadMemory]:
        """Semantic search for facts about a lead using pgvector."""
        if not ENABLE_MEMORY_ENGINE:
            return []

        creator_id = await self._resolve_creator_uuid(creator_id)

        try:
            query_embedding = await self._generate_embedding(query)
            if not query_embedding:
                return await self._get_recent_facts(creator_id, lead_id, top_k)

            results = await self._pgvector_search(
                creator_id=creator_id,
                lead_id=lead_id,
                query_embedding=query_embedding,
                top_k=top_k,
                min_similarity=MEMORY_MIN_SIMILARITY,
            )

            if results:
                await self._update_access_counters([m.id for m in results])

            return results

        except Exception as e:
            logger.error("[MemoryEngine] search() failed: %s", e, exc_info=True)
            return []

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC: recall() — Format memories for prompt injection
    # ─────────────────────────────────────────────────────────────────────

    async def recall(
        self,
        creator_id: str,
        lead_id: str,
        new_message: str,
    ) -> str:
        """Recall relevant memories and format them for prompt injection."""
        if not ENABLE_MEMORY_ENGINE:
            return ""

        creator_id = await self._resolve_creator_uuid(creator_id)
        lead_id = await self._resolve_lead_uuid(creator_id, lead_id)
        cache_key = f"{creator_id}:{lead_id}"
        cached = _recall_cache.get(cache_key)
        if cached is not None:
            logger.debug("[MemoryEngine] recall() cache hit for %s", lead_id[:8])
            return cached

        try:
            facts = await self.search(creator_id, lead_id, new_message, top_k=MAX_FACTS_IN_PROMPT)
            # Fetch compressed memo (stored without embedding, so search() won't find it)
            memo = await self._get_compressed_memo(creator_id, lead_id)
            if memo:
                facts = [memo] + facts
            summary = await self._get_latest_summary(creator_id, lead_id)
            result = self._format_memory_section(facts, summary)

            _recall_cache.set(cache_key, result)

            if result:
                logger.info(
                    "[MemoryEngine] recall() returning %d chars for lead=%s",
                    len(result),
                    lead_id[:8],
                )

            return result

        except Exception as e:
            logger.error("[MemoryEngine] recall() failed: %s", e, exc_info=True)
            return ""

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC: summarize_conversation()
    # ─────────────────────────────────────────────────────────────────────

    async def summarize_conversation(
        self,
        creator_id: str,
        lead_id: str,
        messages: List[Dict[str, str]],
        precomputed_summary: Optional[str] = None,
        precomputed_topics: Optional[List[str]] = None,
        precomputed_sentiment: Optional[str] = None,
    ) -> Optional[ConversationSummaryData]:
        """Generate and store a conversation summary."""
        creator_id = await self._resolve_creator_uuid(creator_id)
        lead_id = await self._resolve_lead_uuid(creator_id, lead_id)
        try:
            summary_text = precomputed_summary
            key_topics = precomputed_topics or []
            commitments = []
            sentiment = precomputed_sentiment or "neutral"

            if not summary_text:
                formatted_msgs = self._format_messages_for_llm(messages)
                if not formatted_msgs:
                    return None

                prompt = CONVERSATION_SUMMARY_PROMPT.format(messages=formatted_msgs)
                llm_response = await self._call_llm(prompt)
                parsed = self._parse_json_response(llm_response)

                if parsed:
                    summary_text = parsed.get("summary", "")
                    key_topics = parsed.get("key_topics", [])
                    commitments = parsed.get("commitments", [])
                    sentiment = parsed.get("sentiment", "neutral")

            if not summary_text:
                return None

            return await self._store_summary(
                creator_id=creator_id,
                lead_id=lead_id,
                summary_text=summary_text,
                key_topics=key_topics,
                commitments_made=commitments,
                sentiment=sentiment,
                message_count=len(messages),
            )

        except Exception as e:
            logger.error("[MemoryEngine] summarize_conversation() failed: %s", e, exc_info=True)
            return None

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC: compress_lead_memory() — COMEDY-inspired narrative memo
    # ─────────────────────────────────────────────────────────────────────

    async def compress_lead_memory(
        self,
        creator_id: str,
        lead_id: str,
        _skip_lock_check: bool = False,
    ) -> Optional[str]:
        """Compress all facts about a lead into a narrative memo.

        Based on the COMEDY paper (COLING 2025): a single narrative summary
        outperforms retrieval of individual facts for long-context leads.

        Stores the memo as fact_type='compressed_memo' in lead_memories.
        Returns the memo text, or None if not enough facts to compress.

        Args:
            _skip_lock_check: If True, skip consolidation lock check.
                Used when called FROM the consolidator itself (already holds lock).
        """
        creator_id = await self._resolve_creator_uuid(creator_id)
        lead_id = await self._resolve_lead_uuid(creator_id, lead_id)

        # FIX Gap 1 (audit): warn if consolidation is active (unless called by consolidator)
        if not _skip_lock_check:
            try:
                from services.memory_consolidator import is_consolidation_locked
                if is_consolidation_locked(creator_id):
                    logger.warning(
                        "[MemoryEngine] compress_lead_memory() while consolidation active "
                        "for creator=%s — proceeding anyway",
                        creator_id[:8],
                    )
            except Exception:
                pass

        try:
            all_facts = await self._get_existing_active_facts(creator_id, lead_id)
            # Filter out any existing compressed_memo
            real_facts = [f for f in all_facts if f.fact_type != "compressed_memo"]

            if len(real_facts) < MEMO_COMPRESSION_THRESHOLD:
                logger.debug(
                    "[MemoryEngine] compress: only %d facts for lead=%s, skipping",
                    len(real_facts), lead_id[:8],
                )
                return None

            # Build fact list for the prompt
            fact_lines = []
            for f in real_facts:
                fact_lines.append(f"- [{f.fact_type}] {f.fact_text}")
            facts_text = "\n".join(fact_lines)

            creator_name = creator_id.replace("_", " ").title()
            prompt = MEMO_COMPRESSION_PROMPT.format(
                creator_name=creator_name,
                facts=facts_text,
            )
            memo_text = await self._call_llm_text(prompt)

            if not memo_text or len(memo_text.strip()) < 20:
                logger.warning("[MemoryEngine] compress: LLM returned empty/short memo")
                return None

            memo_text = memo_text.strip()

            # Deactivate old compressed_memo if exists
            await self._deactivate_old_memos(creator_id, lead_id)

            # Store as a special fact_type
            await self._store_fact(
                creator_id=creator_id,
                lead_id=lead_id,
                fact_type="compressed_memo",
                fact_text=memo_text,
                confidence=1.0,
                embedding=None,
                source_message_id=None,
                source_type="compressed",
            )

            # Invalidate recall cache
            cache_key = f"{creator_id}:{lead_id}"
            _recall_cache.pop(cache_key, None)

            logger.info(
                "[MemoryEngine] Compressed %d facts into memo (%d chars) for lead=%s",
                len(real_facts), len(memo_text), lead_id[:8],
            )
            return memo_text

        except Exception as e:
            logger.error("[MemoryEngine] compress_lead_memory() failed: %s", e, exc_info=True)
            return None

    async def _deactivate_old_memos(self, creator_id: str, lead_id: str) -> None:
        """Deactivate existing compressed_memo entries for a lead."""
        def _sync():
            from api.database import SessionLocal
            from sqlalchemy import text
            session = SessionLocal()
            try:
                session.execute(
                    text(
                        "UPDATE lead_memories SET is_active = false "
                        "WHERE creator_id = CAST(:cid AS uuid) "
                        "AND lead_id = CAST(:lid AS uuid) "
                        "AND fact_type = 'compressed_memo' "
                        "AND is_active = true"
                    ),
                    {"cid": creator_id, "lid": lead_id},
                )
                session.commit()
            finally:
                session.close()
        try:
            await asyncio.to_thread(_sync)
        except Exception as e:
            logger.error("[MemoryEngine] _deactivate_old_memos() failed: %s", e)

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC: resolve_conflict()
    # ─────────────────────────────────────────────────────────────────────

    async def resolve_conflict(
        self,
        new_fact: Dict[str, Any],
        existing_facts: List[LeadMemory],
        new_embedding: Optional[List[float]] = None,
        creator_id: Optional[str] = None,
        lead_id: Optional[str] = None,
    ) -> str:
        """
        Resolve conflict between a new fact and existing facts.

        Uses two-pass dedup:
          1. Jaccard text similarity (fast, no DB) — catches exact/near-exact
          2. Embedding cosine similarity via pgvector — catches semantic dupes

        Returns: "skip" | "supersede" | "store"
        """
        if not existing_facts:
            return "store"

        new_text = new_fact.get("text", "").lower().strip()
        new_type = new_fact.get("type", "")

        # Pass 1: Jaccard text similarity (fast)
        for existing in existing_facts:
            existing_text = existing.fact_text.lower().strip()

            if self._text_similarity(new_text, existing_text) > 0.85:
                # Refresh timestamp on the existing fact instead of inserting
                await self._refresh_fact_timestamp(existing.id)
                return "skip"

            if (
                existing.fact_type == new_type
                and new_type in ("preference", "personal_info", "purchase_history")
                and self._text_similarity(new_text, existing_text) > 0.5
            ):
                await self._supersede_fact(existing.id, None)
                return "store"

        # Pass 2: Embedding cosine similarity via pgvector (semantic dedup)
        if new_embedding and creator_id and lead_id:
            similar = await self._find_similar_fact_by_embedding(
                creator_id, lead_id, new_type, new_embedding, threshold=0.15,
            )
            if similar:
                await self._refresh_fact_timestamp(similar["id"])
                logger.debug(
                    "[MemoryEngine] Semantic dedup: '%s' ≈ '%s' (dist=%.3f)",
                    new_text[:40], similar["text"][:40], similar["distance"],
                )
                return "skip"

        return "store"

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC: forget_lead() — GDPR compliance
    # ─────────────────────────────────────────────────────────────────────

    async def forget_lead(self, creator_id: str, lead_id: str) -> int:
        """Delete ALL memories for a specific lead (GDPR right to erasure)."""
        creator_id = await self._resolve_creator_uuid(creator_id)
        def _sync():
            from api.database import SessionLocal
            from sqlalchemy import text
            session = SessionLocal()
            total_deleted = 0
            try:
                result1 = session.execute(
                    text(
                        "DELETE FROM lead_memories "
                        "WHERE creator_id = CAST(:cid AS uuid) "
                        "AND lead_id = CAST(:lid AS uuid)"
                    ),
                    {"cid": creator_id, "lid": lead_id},
                )
                total_deleted += result1.rowcount
                result2 = session.execute(
                    text(
                        "DELETE FROM conversation_summaries "
                        "WHERE creator_id = CAST(:cid AS uuid) "
                        "AND lead_id = CAST(:lid AS uuid)"
                    ),
                    {"cid": creator_id, "lid": lead_id},
                )
                total_deleted += result2.rowcount
                session.commit()
                logger.info(
                    "[MemoryEngine] GDPR forget: deleted %d records for lead=%s",
                    total_deleted, lead_id[:8],
                )
                cache_key = f"{creator_id}:{lead_id}"
                _recall_cache.pop(cache_key, None)
                return total_deleted
            finally:
                session.close()
        try:
            return await asyncio.to_thread(_sync)
        except Exception as e:
            logger.error("[MemoryEngine] forget_lead() failed: %s", e, exc_info=True)
            return 0

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC: decay_memories() — Ebbinghaus eviction
    # ─────────────────────────────────────────────────────────────────────

    async def decay_memories(self, creator_id: str) -> int:
        """Apply Ebbinghaus decay to all active memories for a creator.

        Formula:
            decay_factor = exp(-0.693 * days_since_last_access / half_life)
            half_life = DECAY_HALF_LIFE_BASE_DAYS * (1 + times_accessed)
            If confidence * decay_factor < DECAY_THRESHOLD -> deactivate
        """
        if not ENABLE_MEMORY_DECAY:
            return 0

        # Expire temporal facts first (independent of Ebbinghaus)
        temporal_expired = await self._expire_temporal_facts()

        def _sync():
            from api.database import SessionLocal
            from sqlalchemy import text
            session = SessionLocal()
            deactivated = temporal_expired
            try:
                rows = session.execute(
                    text(
                        "SELECT id, confidence, times_accessed, "
                        "last_accessed_at, created_at "
                        "FROM lead_memories "
                        "WHERE creator_id = CAST(:cid AS uuid) "
                        "AND is_active = true"
                    ),
                    {"cid": creator_id},
                ).fetchall()
                now = datetime.now(timezone.utc)
                ids_to_deactivate = []
                for row in rows:
                    mem_id = str(row[0])
                    confidence = float(row[1]) if row[1] else 0.7
                    times_accessed = int(row[2]) if row[2] else 0
                    last_accessed = row[3] or row[4]
                    if last_accessed is None:
                        continue
                    if last_accessed.tzinfo is None:
                        last_accessed = last_accessed.replace(tzinfo=timezone.utc)
                    days_since = (now - last_accessed).total_seconds() / 86400.0
                    half_life = DECAY_HALF_LIFE_BASE_DAYS * (1 + times_accessed)
                    decay_factor = math.exp(-0.693 * days_since / half_life)
                    effective_confidence = confidence * decay_factor
                    if effective_confidence < DECAY_THRESHOLD:
                        ids_to_deactivate.append(mem_id)
                if ids_to_deactivate:
                    for mem_id in ids_to_deactivate:
                        session.execute(
                            text(
                                "UPDATE lead_memories SET is_active = false, "
                                "updated_at = NOW() WHERE id = CAST(:mid AS uuid)"
                            ),
                            {"mid": mem_id},
                        )
                    session.commit()
                    deactivated += len(ids_to_deactivate)
                logger.info(
                    "[MemoryEngine] decay: checked %d memories, deactivated %d for creator=%s",
                    len(rows), deactivated, creator_id[:8],
                )
                return deactivated
            finally:
                session.close()
        try:
            return await asyncio.to_thread(_sync)
        except Exception as e:
            logger.error("[MemoryEngine] decay_memories() failed: %s", e, exc_info=True)
            return 0

    # ═══════════════════════════════════════════════════════════════════════
    # PRIVATE: LLM integration
    # ═══════════════════════════════════════════════════════════════════════

    # _extract_facts_via_llm moved to services/memory_extraction.py

    async def _call_llm(self, prompt: str) -> str:
        """Call Gemini Flash-Lite (primary) or GPT-4o-mini (fallback) for extraction."""
        try:
            from core.providers.gemini_provider import generate_dm_response

            messages = [
                {"role": "system", "content": "Eres un analizador de conversaciones. Responde SOLO con JSON valido."},
                {"role": "user", "content": prompt},
            ]
            result = await generate_dm_response(messages, max_tokens=500)

            if result and result.get("content"):
                return result["content"]

            logger.warning("[MemoryEngine] LLM returned empty response")
            return ""

        except Exception as e:
            logger.error("[MemoryEngine] LLM call failed: %s", e)
            return ""

    async def _call_llm_text(self, prompt: str) -> str:
        """Call LLM for plain-text output (no JSON system prompt)."""
        try:
            from core.providers.gemini_provider import generate_dm_response

            messages = [
                {"role": "system", "content": "Eres un asistente que resume informacion. Responde SOLO con texto plano, sin JSON, sin markdown, sin comillas."},
                {"role": "user", "content": prompt},
            ]
            result = await generate_dm_response(messages, max_tokens=200)

            if result and result.get("content"):
                text = result["content"].strip()
                # Strip any JSON/markdown wrapping the LLM might add
                if text.startswith("```"):
                    lines = text.split("\n")
                    lines = [l for l in lines if not l.strip().startswith("```")]
                    text = "\n".join(lines).strip()
                if text.startswith("{") and text.endswith("}"):
                    # LLM wrapped in JSON despite instructions — extract the value
                    import json as _json
                    try:
                        parsed = _json.loads(text)
                        text = parsed.get("resumen", parsed.get("memo", str(list(parsed.values())[0])))
                    except (ValueError, IndexError):
                        pass
                return text

            return ""
        except Exception as e:
            logger.error("[MemoryEngine] _call_llm_text failed: %s", e)
            return ""

    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """Parse JSON from LLM response, handling markdown fences."""
        if not response:
            return None

        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass

            logger.warning("[MemoryEngine] Failed to parse JSON from LLM: %s", text[:100])
            return None

    # ═══════════════════════════════════════════════════════════════════════
    # PRIVATE: Embedding operations
    # ═══════════════════════════════════════════════════════════════════════

    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for a single text using OpenAI."""
        try:
            from core.embeddings import generate_embedding

            return await asyncio.to_thread(generate_embedding, text)
        except Exception as e:
            logger.error("[MemoryEngine] Embedding generation failed: %s", e)
            return None

    async def _generate_embeddings_batch(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Generate embeddings for multiple texts in batch."""
        if not texts:
            return []

        try:
            from core.embeddings import generate_embeddings_batch

            return await asyncio.to_thread(generate_embeddings_batch, texts)
        except Exception as e:
            logger.error("[MemoryEngine] Batch embedding generation failed: %s", e)
            return [None] * len(texts)

    # ═══════════════════════════════════════════════════════════════════════
    # PRIVATE: Database operations (raw SQL for pgvector)
    # ═══════════════════════════════════════════════════════════════════════

    async def _store_fact(
        self,
        creator_id: str,
        lead_id: str,
        fact_type: str,
        fact_text: str,
        confidence: float,
        embedding: Optional[List[float]],
        source_message_id: Optional[str],
        source_type: str,
    ) -> Optional[LeadMemory]:
        """Store a single fact in lead_memories with optional embedding."""
        def _sync():
            from api.database import SessionLocal
            from sqlalchemy import text
            session = SessionLocal()
            try:
                fact_id = str(uuid.uuid4())
                if embedding:
                    validated_floats = [float(v) for v in embedding]
                    embedding_str = "[" + ",".join(str(x) for x in validated_floats) + "]"
                    session.execute(
                        text(
                            "INSERT INTO lead_memories "
                            "(id, creator_id, lead_id, fact_type, fact_text, "
                            "fact_embedding, confidence, source_message_id, "
                            "source_type, created_at, updated_at) "
                            "VALUES ("
                            "CAST(:id AS uuid), CAST(:cid AS uuid), CAST(:lid AS uuid), "
                            ":ftype, :ftext, CAST(:embedding AS vector), :conf, "
                            "CAST(:smid AS uuid), :stype, NOW(), NOW())"
                        ),
                        {"id": fact_id, "cid": creator_id, "lid": lead_id,
                         "ftype": fact_type, "ftext": fact_text, "embedding": embedding_str,
                         "conf": confidence, "smid": source_message_id, "stype": source_type},
                    )
                else:
                    session.execute(
                        text(
                            "INSERT INTO lead_memories "
                            "(id, creator_id, lead_id, fact_type, fact_text, "
                            "confidence, source_message_id, source_type, "
                            "created_at, updated_at) "
                            "VALUES ("
                            "CAST(:id AS uuid), CAST(:cid AS uuid), CAST(:lid AS uuid), "
                            ":ftype, :ftext, :conf, "
                            "CAST(:smid AS uuid), :stype, NOW(), NOW())"
                        ),
                        {"id": fact_id, "cid": creator_id, "lid": lead_id,
                         "ftype": fact_type, "ftext": fact_text,
                         "conf": confidence, "smid": source_message_id, "stype": source_type},
                    )
                session.commit()
                return LeadMemory(
                    id=fact_id, creator_id=creator_id, lead_id=lead_id,
                    fact_type=fact_type, fact_text=fact_text, confidence=confidence,
                    source_message_id=source_message_id, source_type=source_type,
                    created_at=datetime.now(timezone.utc),
                )
            finally:
                session.close()
        try:
            return await asyncio.to_thread(_sync)
        except Exception as e:
            logger.error("[MemoryEngine] _store_fact() failed: %s", e, exc_info=True)
            return None

    async def _pgvector_search(
        self,
        creator_id: str,
        lead_id: str,
        query_embedding: List[float],
        top_k: int,
        min_similarity: float,
    ) -> List[LeadMemory]:
        """Semantic search via pgvector cosine similarity with temporal decay.

        O2 optimization (THEANINE NAACL 2025, Memobase 2025): final ranking
        blends semantic similarity (70%) with recency (30%) over a 90-day
        window.  This prevents stale-but-semantically-similar facts from
        burying recent relevant ones.

        Formula: score = sim * (0.7 + 0.3 * max(0, 1 - age_days/90))
        """
        def _sync():
            from api.database import SessionLocal
            from sqlalchemy import text
            validated_floats = [float(v) for v in query_embedding]
            embedding_str = "[" + ",".join(str(x) for x in validated_floats) + "]"
            session = SessionLocal()
            try:
                rows = session.execute(
                    text(
                        "SELECT id, creator_id, lead_id, fact_type, fact_text, "
                        "confidence, source_type, times_accessed, "
                        "last_accessed_at, created_at, "
                        "(1 - (fact_embedding <=> CAST(:query AS vector))) "
                        "  * (0.7 + 0.3 * GREATEST(0, "
                        "      1.0 - EXTRACT(EPOCH FROM (NOW() - created_at)) "
                        "             / (90 * 86400))) "
                        "  AS similarity "
                        "FROM lead_memories "
                        "WHERE creator_id = CAST(:cid AS uuid) "
                        "AND lead_id = CAST(:lid AS uuid) "
                        "AND is_active = true "
                        "AND fact_embedding IS NOT NULL "
                        "AND 1 - (fact_embedding <=> CAST(:query AS vector)) >= :min_sim "
                        "ORDER BY similarity DESC "
                        "LIMIT :top_k"
                    ),
                    {"query": embedding_str, "cid": creator_id, "lid": lead_id,
                     "min_sim": min_similarity, "top_k": top_k},
                ).fetchall()
                return [
                    LeadMemory(
                        id=str(row[0]), creator_id=str(row[1]), lead_id=str(row[2]),
                        fact_type=row[3], fact_text=row[4],
                        confidence=float(row[5]) if row[5] else 0.7,
                        source_type=row[6] or "extracted",
                        times_accessed=int(row[7]) if row[7] else 0,
                        last_accessed_at=row[8], created_at=row[9],
                        similarity=float(row[10]) if row[10] else 0.0,
                    )
                    for row in rows
                ]
            finally:
                session.close()
        try:
            return await asyncio.to_thread(_sync)
        except Exception as e:
            logger.error("[MemoryEngine] _pgvector_search() failed: %s", e, exc_info=True)
            return []

    async def _get_existing_active_facts(
        self, creator_id: str, lead_id: str
    ) -> List[LeadMemory]:
        """Get all active facts for a lead (for conflict resolution)."""
        def _sync():
            from api.database import SessionLocal
            from sqlalchemy import text
            session = SessionLocal()
            try:
                rows = session.execute(
                    text(
                        "SELECT id, fact_type, fact_text, confidence, created_at "
                        "FROM lead_memories "
                        "WHERE creator_id = CAST(:cid AS uuid) "
                        "AND lead_id = CAST(:lid AS uuid) "
                        "AND is_active = true "
                        "ORDER BY created_at DESC"
                    ),
                    {"cid": creator_id, "lid": lead_id},
                ).fetchall()
                return [
                    LeadMemory(
                        id=str(row[0]), creator_id=creator_id, lead_id=lead_id,
                        fact_type=row[1], fact_text=row[2],
                        confidence=float(row[3]) if row[3] else 0.7, created_at=row[4],
                    )
                    for row in rows
                ]
            finally:
                session.close()
        try:
            return await asyncio.to_thread(_sync)
        except Exception as e:
            logger.error("[MemoryEngine] _get_existing_active_facts() failed: %s", e)
            return []

    # O1 (Memobase/RMM): Type-priority weights for non-semantic fallback.
    # Commitments and personal info are more actionable than generic topics.
    _FALLBACK_TYPE_WEIGHT = {
        "commitment": 4,
        "personal_info": 3,
        "preference": 2,
        "objection": 2,
        "purchase_history": 2,
        "topic": 1,
        "compressed_memo": 5,
    }

    async def _get_recent_facts(
        self, creator_id: str, lead_id: str, limit: int
    ) -> List[LeadMemory]:
        """Fallback: get active facts weighted by type priority + recency.

        O1 optimization (Memobase, 2025): instead of pure recency, fetch a
        wider set and re-rank by type_weight * recency_decay * confidence.
        This ensures commitments and personal info surface even when
        embedding search is unavailable (e.g. OpenAI 429).
        """
        def _sync():
            from api.database import SessionLocal
            from sqlalchemy import text
            session = SessionLocal()
            try:
                # Fetch 3x limit to allow re-ranking
                rows = session.execute(
                    text(
                        "SELECT id, creator_id, lead_id, fact_type, fact_text, "
                        "confidence, source_type, times_accessed, "
                        "last_accessed_at, created_at "
                        "FROM lead_memories "
                        "WHERE creator_id = CAST(:cid AS uuid) "
                        "AND lead_id = CAST(:lid AS uuid) "
                        "AND is_active = true "
                        "ORDER BY created_at DESC "
                        "LIMIT :limit"
                    ),
                    {"cid": creator_id, "lid": lead_id, "limit": limit * 3},
                ).fetchall()
                now = datetime.now(timezone.utc)
                scored = []
                for row in rows:
                    mem = LeadMemory(
                        id=str(row[0]), creator_id=str(row[1]), lead_id=str(row[2]),
                        fact_type=row[3], fact_text=row[4],
                        confidence=float(row[5]) if row[5] else 0.7,
                        source_type=row[6] or "extracted",
                        times_accessed=int(row[7]) if row[7] else 0,
                        last_accessed_at=row[8], created_at=row[9],
                    )
                    type_w = self._FALLBACK_TYPE_WEIGHT.get(mem.fact_type, 1)
                    age_days = max(0.1, (now - (mem.created_at or now).replace(tzinfo=timezone.utc if (mem.created_at and mem.created_at.tzinfo is None) else (mem.created_at.tzinfo if mem.created_at else timezone.utc))).total_seconds() / 86400)
                    recency = 1.0 / (1.0 + age_days / 30.0)  # half-score at 30 days
                    score = type_w * recency * mem.confidence
                    scored.append((score, mem))
                scored.sort(key=lambda x: -x[0])
                return [mem for _, mem in scored[:limit]]
            finally:
                session.close()
        try:
            return await asyncio.to_thread(_sync)
        except Exception as e:
            logger.error("[MemoryEngine] _get_recent_facts() failed: %s", e)
            return []

    async def _update_access_counters(self, memory_ids: List[str]) -> None:
        """Increment times_accessed and update last_accessed_at."""
        def _sync():
            from api.database import SessionLocal
            from sqlalchemy import text
            session = SessionLocal()
            try:
                for mem_id in memory_ids:
                    session.execute(
                        text(
                            "UPDATE lead_memories "
                            "SET times_accessed = times_accessed + 1, "
                            "last_accessed_at = NOW(), "
                            "updated_at = NOW() "
                            "WHERE id = CAST(:mid AS uuid)"
                        ),
                        {"mid": mem_id},
                    )
                session.commit()
            finally:
                session.close()
        try:
            await asyncio.to_thread(_sync)
        except Exception as e:
            logger.debug("[MemoryEngine] _update_access_counters() failed: %s", e)

    async def _supersede_fact(self, old_fact_id: str, new_fact_id: Optional[str]) -> None:
        """Deactivate an old fact and link to its replacement."""
        def _sync():
            from api.database import SessionLocal
            from sqlalchemy import text
            session = SessionLocal()
            try:
                if new_fact_id:
                    session.execute(
                        text(
                            "UPDATE lead_memories "
                            "SET is_active = false, "
                            "superseded_by = CAST(:new_id AS uuid), "
                            "updated_at = NOW() "
                            "WHERE id = CAST(:old_id AS uuid)"
                        ),
                        {"old_id": old_fact_id, "new_id": new_fact_id},
                    )
                else:
                    session.execute(
                        text(
                            "UPDATE lead_memories "
                            "SET is_active = false, updated_at = NOW() "
                            "WHERE id = CAST(:old_id AS uuid)"
                        ),
                        {"old_id": old_fact_id},
                    )
                session.commit()
            finally:
                session.close()
        try:
            await asyncio.to_thread(_sync)
        except Exception as e:
            logger.debug("[MemoryEngine] _supersede_fact() failed: %s", e)

    async def _find_similar_fact_by_embedding(
        self,
        creator_id: str,
        lead_id: str,
        fact_type: str,
        embedding: List[float],
        threshold: float = 0.15,
    ) -> Optional[Dict[str, Any]]:
        """Find a semantically similar active fact via pgvector cosine distance.

        Returns dict with id, text, distance if found within threshold, else None.
        Threshold 0.15 cosine distance ≈ 0.85 cosine similarity.
        """
        def _sync():
            from api.database import SessionLocal
            from sqlalchemy import text
            validated = [float(v) for v in embedding]
            emb_str = "[" + ",".join(str(x) for x in validated) + "]"
            session = SessionLocal()
            try:
                row = session.execute(
                    text(
                        "SELECT id, fact_text, "
                        "fact_embedding <=> CAST(:emb AS vector) AS distance "
                        "FROM lead_memories "
                        "WHERE creator_id = CAST(:cid AS uuid) "
                        "AND lead_id = CAST(:lid AS uuid) "
                        "AND fact_type = :ftype "
                        "AND is_active = true "
                        "AND fact_embedding IS NOT NULL "
                        "ORDER BY fact_embedding <=> CAST(:emb AS vector) "
                        "LIMIT 1"
                    ),
                    {"emb": emb_str, "cid": creator_id, "lid": lead_id, "ftype": fact_type},
                ).fetchone()
                if row and row[2] < threshold:
                    return {"id": str(row[0]), "text": row[1], "distance": row[2]}
                return None
            finally:
                session.close()
        try:
            return await asyncio.to_thread(_sync)
        except Exception as e:
            logger.debug("[MemoryEngine] _find_similar_fact_by_embedding() failed: %s", e)
            return None

    async def _refresh_fact_timestamp(self, fact_id: str) -> None:
        """Refresh updated_at on an existing fact (dedup touch)."""
        def _sync():
            from api.database import SessionLocal
            from sqlalchemy import text
            session = SessionLocal()
            try:
                session.execute(
                    text(
                        "UPDATE lead_memories "
                        "SET updated_at = NOW(), "
                        "times_accessed = times_accessed + 1 "
                        "WHERE id = CAST(:fid AS uuid)"
                    ),
                    {"fid": fact_id},
                )
                session.commit()
            finally:
                session.close()
        try:
            await asyncio.to_thread(_sync)
        except Exception as e:
            logger.debug("[MemoryEngine] _refresh_fact_timestamp() failed: %s", e)

    async def _expire_temporal_facts(self) -> int:
        """Deactivate temporal facts older than TTL. Called from decay_memories()."""
        def _sync():
            from api.database import SessionLocal
            from sqlalchemy import text
            session = SessionLocal()
            try:
                result = session.execute(
                    text(
                        "UPDATE lead_memories "
                        "SET is_active = false, updated_at = NOW() "
                        "WHERE is_active = true "
                        "AND created_at < NOW() - CAST(:ttl || ' days' AS INTERVAL) "
                        "AND ("
                        "  fact_text ~* '(mañana|hoy|esta semana|próximo|siguiente"
                        "|demà|avui|aquesta setmana|proper|següent"
                        "|tomorrow|today|this week|next week"
                        "|lunes|martes|miércoles|jueves|viernes|sábado|domingo"
                        "|dilluns|dimarts|dimecres|dijous|divendres|dissabte|diumenge"
                        "|monday|tuesday|wednesday|thursday|friday|saturday|sunday)'"
                        ")"
                    ),
                    {"ttl": str(TEMPORAL_FACT_TTL_DAYS)},
                )
                expired = result.rowcount
                session.commit()
                if expired > 0:
                    logger.info("[MemoryEngine] Expired %d temporal facts (TTL=%dd)", expired, TEMPORAL_FACT_TTL_DAYS)
                return expired
            finally:
                session.close()
        try:
            return await asyncio.to_thread(_sync)
        except Exception as e:
            logger.error("[MemoryEngine] _expire_temporal_facts() failed: %s", e)
            return 0

    async def _store_summary(
        self,
        creator_id: str,
        lead_id: str,
        summary_text: str,
        key_topics: List[str],
        commitments_made: List[str],
        sentiment: str,
        message_count: int,
    ) -> Optional[ConversationSummaryData]:
        """Store a conversation summary in the DB."""
        def _sync():
            from api.database import SessionLocal
            from sqlalchemy import text
            session = SessionLocal()
            try:
                summary_id = str(uuid.uuid4())
                session.execute(
                    text(
                        "INSERT INTO conversation_summaries "
                        "(id, creator_id, lead_id, summary_text, key_topics, "
                        "commitments_made, sentiment, message_count, "
                        "created_at, updated_at) "
                        "VALUES ("
                        "CAST(:id AS uuid), CAST(:cid AS uuid), CAST(:lid AS uuid), "
                        ":summary, CAST(:topics AS jsonb), CAST(:commits AS jsonb), "
                        ":sentiment, :count, NOW(), NOW())"
                    ),
                    {"id": summary_id, "cid": creator_id, "lid": lead_id,
                     "summary": summary_text, "topics": json.dumps(key_topics),
                     "commits": json.dumps(commitments_made),
                     "sentiment": sentiment, "count": message_count},
                )
                session.commit()
                return ConversationSummaryData(
                    id=summary_id, creator_id=creator_id, lead_id=lead_id,
                    summary_text=summary_text, key_topics=key_topics,
                    commitments_made=commitments_made, sentiment=sentiment,
                    message_count=message_count, created_at=datetime.now(timezone.utc),
                )
            finally:
                session.close()
        try:
            return await asyncio.to_thread(_sync)
        except Exception as e:
            logger.error("[MemoryEngine] _store_summary() failed: %s", e, exc_info=True)
            return None

    async def _get_latest_summary(
        self, creator_id: str, lead_id: str
    ) -> Optional[ConversationSummaryData]:
        """Get the most recent conversation summary for a lead."""
        def _sync():
            from api.database import SessionLocal
            from sqlalchemy import text
            session = SessionLocal()
            try:
                row = session.execute(
                    text(
                        "SELECT id, summary_text, key_topics, "
                        "commitments_made, sentiment, message_count, created_at "
                        "FROM conversation_summaries "
                        "WHERE creator_id = CAST(:cid AS uuid) "
                        "AND lead_id = CAST(:lid AS uuid) "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"cid": creator_id, "lid": lead_id},
                ).fetchone()
                if not row:
                    return None
                return ConversationSummaryData(
                    id=str(row[0]), creator_id=creator_id, lead_id=lead_id,
                    summary_text=row[1], key_topics=row[2] or [],
                    commitments_made=row[3] or [], sentiment=row[4] or "neutral",
                    message_count=row[5] or 0, created_at=row[6],
                )
            finally:
                session.close()
        try:
            return await asyncio.to_thread(_sync)
        except Exception as e:
            logger.error("[MemoryEngine] _get_latest_summary() failed: %s", e)
            return None

    async def _get_compressed_memo(
        self, creator_id: str, lead_id: str
    ) -> Optional[LeadMemory]:
        """Get the active compressed memo for a lead, if one exists."""
        def _sync():
            from api.database import SessionLocal
            from sqlalchemy import text
            session = SessionLocal()
            try:
                row = session.execute(
                    text(
                        "SELECT id, fact_text, created_at "
                        "FROM lead_memories "
                        "WHERE creator_id = CAST(:cid AS uuid) "
                        "AND lead_id = CAST(:lid AS uuid) "
                        "AND fact_type = 'compressed_memo' "
                        "AND is_active = true "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"cid": creator_id, "lid": lead_id},
                ).fetchone()
                if not row:
                    return None
                return LeadMemory(
                    id=str(row[0]), creator_id=creator_id, lead_id=lead_id,
                    fact_type="compressed_memo", fact_text=row[1],
                    confidence=1.0, created_at=row[2],
                )
            finally:
                session.close()
        try:
            return await asyncio.to_thread(_sync)
        except Exception as e:
            logger.error("[MemoryEngine] _get_compressed_memo() failed: %s", e)
            return None

    # ═══════════════════════════════════════════════════════════════════════
    # PRIVATE: Formatting
    # ═══════════════════════════════════════════════════════════════════════

    # _format_messages_for_llm moved to services/memory_extraction.py

    @staticmethod
    def _dedup_facts(facts: List[LeadMemory], threshold: float = 0.6) -> List[LeadMemory]:
        """O3 (Mem0/MemOS): Remove near-duplicate facts using Jaccard similarity.

        When the same fact is extracted multiple times with slightly different
        wording, keep only the most recent version.  Threshold 0.6 catches
        paraphrases like 'Le gusta el yoga' / 'Le interesa el yoga'.
        """
        if len(facts) <= 1:
            return facts
        kept: List[LeadMemory] = []
        for fact in facts:
            words_new = set(fact.fact_text.lower().split())
            is_dup = False
            for existing in kept:
                words_old = set(existing.fact_text.lower().split())
                union = words_new | words_old
                if not union:
                    continue
                jaccard = len(words_new & words_old) / len(union)
                if jaccard >= threshold and fact.fact_type == existing.fact_type:
                    is_dup = True
                    break
            if not is_dup:
                kept.append(fact)
        return kept

    # ------------------------------------------------------------------
    # Memory formatting v3 — bulleted list (mem0 pattern, Zep pattern)
    #
    # Research: mem0 (25K stars), Zep, Letta all use bulleted/labeled
    # lists, NOT key=value.  Mem0 paper (2025): k=1-2 memories optimal,
    # k>2 negates selective benefits.  MRPrompt (2026): explicit usage
    # protocol required.  SeCom (ICLR 2025): compression-as-denoising.
    # ------------------------------------------------------------------

    # Name-detection heuristics for personal_info facts (universal, not
    # hardcoded to any language).  Patterns: "se llama X", "nombre: X",
    # "apodo X", "llamado/a X", "identificado/a como X".
    # Note: trigger keywords are case-insensitive but name capture requires
    # a capitalized first letter to avoid matching common nouns.
    _NAME_PATTERNS = re.compile(
        r"(?i:se llama|nombre[:\s]+|apodo[:\s]*|"
        r"llamad[oa]\s+|identificad[oa]\s+(?:como\s+))\s*"
        r"['\"]?([A-ZÁÉÍÓÚÑÇ][a-záéíóúñç]+(?:\s+[A-ZÁÉÍÓÚÑÇ][a-záéíóúñç]+)?)",
    )

    def _extract_lead_name(self, facts: List["LeadMemory"]) -> Optional[str]:
        """Extract lead's name from personal_info facts (universal regex)."""
        for f in facts:
            if f.fact_type != "personal_info":
                continue
            m = self._NAME_PATTERNS.search(f.fact_text)
            if m:
                return m.group(1).strip()
        return None

    def _fact_to_bullet(self, fact: "LeadMemory") -> str:
        """Convert a LeadMemory fact to a compact bulleted line.

        Format follows mem0 pattern: `- {fact_text}`
        with [PENDIENTE] suffix for commitments (Zep temporal-flag pattern).
        """
        text = fact.fact_text.strip()[:200]
        suffix = " [PENDIENTE]" if fact.fact_type == "commitment" else ""
        return f"- {text}{suffix}"

    def _format_memory_section(
        self,
        facts: List[LeadMemory],
        summary: Optional[ConversationSummaryData],
        max_chars: int = 2000,
    ) -> str:
        """Format memories as bulleted list with explicit usage protocol.

        Research-backed v3 redesign:
        - mem0 (2025): bulleted list `- fact` is production standard
        - Zep (2025): XML-tagged facts with timestamps
        - MRPrompt (2026): explicit 4-stage usage protocol required
        - Mem0 paper: k≤2 retrieved memories optimal, k>2 hurts
        - SeCom (ICLR 2025): compression as denoising
        - LangChain EntityMemory: separate name extraction
        - Context Rot (Chroma 2025): focused 300 tokens >> 113K tokens

        Output format:
            <memoria>
            Nombre: Cuca
            - Fact 1
            - Fact 2 [PENDIENTE]
            Último tema: resumen
            </memoria>
            Instrucción: Responde usando la info de <memoria>. No la repitas textual.
        """
        if not facts and not summary:
            return ""

        MAX_FACTS = 5  # Mem0 paper: k>2 hurts; we allow up to 5 for commitments
        lines: list[str] = ["<memoria>"]

        # Extract lead name (LangChain EntityMemory pattern — universal regex)
        name = self._extract_lead_name(facts)
        if name:
            lines.append(f"Nombre: {name}")

        # CC-aligned: memo + facts coexist (CC injects all selected files, no discarding)
        memo = next((f for f in facts if f.fact_type == "compressed_memo"), None)
        non_memo_facts = [f for f in facts if f.fact_type != "compressed_memo"]

        if memo:
            memo_text = memo.fact_text.strip()
            lines.append(f"- {memo_text}")

        if non_memo_facts:
            deduped = self._dedup_facts(non_memo_facts)
            priority_order = {
                "commitment": 0, "preference": 1, "objection": 2,
                "personal_info": 3, "purchase_history": 4, "topic": 5,
            }
            sorted_facts = sorted(
                deduped,
                key=lambda f: (
                    priority_order.get(f.fact_type, 9),
                    -(f.created_at or datetime.min.replace(tzinfo=timezone.utc)).timestamp(),
                ),
            )
            for fact in sorted_facts[:MAX_FACTS]:
                lines.append(self._fact_to_bullet(fact))

        # Conversation summary (single line, compressed)
        if summary:
            s_text = summary.summary_text.strip()[:120].rstrip(".")
            lines.append(f"Último tema: {s_text}")

        lines.append("</memoria>")

        # Enforce char budget — trim bullets from the end
        while len("\n".join(lines)) > max_chars and len(lines) > 3:
            lines.pop(-2)  # remove last bullet before </memoria>

        # Explicit usage protocol (MRPrompt 2026, Zep pattern)
        instruction = "Instrucción: Responde usando la info de <memoria>. No la repitas textual."

        return "\n".join(lines) + "\n" + instruction

    def _relative_time(self, dt: Optional[datetime]) -> str:
        """Convert datetime to relative time string in Spanish."""
        if not dt:
            return "fecha desconocida"

        now = datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        delta = now - dt
        days = delta.days

        if days == 0:
            hours = delta.seconds // 3600
            if hours == 0:
                return "hace unos minutos"
            elif hours == 1:
                return "hace 1 hora"
            else:
                return f"hace {hours} horas"
        elif days == 1:
            return "ayer"
        elif days < 7:
            return f"hace {days} dias"
        elif days < 30:
            weeks = days // 7
            return f"hace {weeks} semana{'s' if weeks > 1 else ''}"
        else:
            months = days // 30
            return f"hace {months} mes{'es' if months > 1 else ''}"

    @staticmethod
    def _text_similarity(text_a: str, text_b: str) -> float:
        """Simple word-overlap Jaccard similarity for conflict detection."""
        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())
        if not words_a or not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return len(intersection) / len(union)


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════

_memory_engine: Optional[MemoryEngine] = None


def get_memory_engine() -> MemoryEngine:
    """Get the global MemoryEngine singleton."""
    global _memory_engine
    if _memory_engine is None:
        _memory_engine = MemoryEngine()
    return _memory_engine
