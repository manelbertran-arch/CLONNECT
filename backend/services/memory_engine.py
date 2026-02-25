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
_recall_cache: Dict[str, str] = {}
_recall_cache_ts: Dict[str, float] = {}
_RECALL_CACHE_TTL = 60  # seconds


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

FACT_EXTRACTION_PROMPT = """Analiza esta conversacion de DMs entre un creador y un lead.
Extrae SOLO hechos concretos sobre el LEAD (no sobre el creador ni sus productos).

Tipos de hechos a extraer:
- preference: gustos, intereses, estilo preferido del lead
- commitment: promesas hechas por el bot/creador AL lead (ej: "te envio el enlace manana")
- topic: temas principales discutidos en la conversacion
- objection: objeciones, dudas o resistencias del lead
- personal_info: datos personales del lead (nombre, ciudad, situacion, profesion)
- purchase_history: compras, pagos o transacciones mencionadas

Conversacion:
{messages}

Responde UNICAMENTE con JSON valido (sin markdown, sin ```):
{{"facts": [{{"type": "preference", "text": "Le interesa el curso de nutricion", "confidence": 0.9}}, {{"type": "commitment", "text": "Se le prometio enviar el enlace manana", "confidence": 0.8}}], "summary": "El lead pregunto por precios del curso de nutricion...", "sentiment": "positive", "key_topics": ["nutricion", "precios"]}}

REGLAS:
- Maximo {max_facts} hechos por conversacion
- Solo hechos CONCRETOS y verificables, no inferencias vagas
- Confianza entre 0.5 y 1.0 segun certeza
- NO extraer hechos sobre los productos del creador (eso ya esta en RAG)
- NO repetir hechos que sean obvios del contexto de la conversacion
- Si no hay hechos extraibles, retorna {{"facts": [], "summary": "...", "sentiment": "neutral", "key_topics": []}}
- "text" debe ser una frase completa y autocontenida
- "commitment" solo si hay una promesa EXPLICITA, no implicita"""

CONVERSATION_SUMMARY_PROMPT = """Resume esta conversacion de DMs entre un creador y un lead.

Conversacion:
{messages}

Responde UNICAMENTE con JSON valido:
{{"summary": "Resumen breve de la conversacion (max 2 frases)", "key_topics": ["tema1", "tema2"], "commitments": ["promesa1"], "sentiment": "positive|neutral|negative"}}"""


# ═══════════════════════════════════════════════════════════════════════════════
# MEMORY ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

class MemoryEngine:
    """Per-lead memory engine with fact extraction and semantic recall."""

    # ─────────────────────────────────────────────────────────────────────
    # PRIVATE: _resolve_creator_uuid() — resolve slug → UUID
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _resolve_creator_uuid(creator_id: str) -> str:
        """Return the DB UUID for a creator, resolving slug names if needed."""
        try:
            uuid.UUID(creator_id)
            return creator_id  # Already a valid UUID
        except (ValueError, AttributeError):
            pass
        # Slug path: look up by name
        try:
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
        except Exception as e:
            logger.debug("[MemoryEngine] _resolve_creator_uuid failed for %s: %s", creator_id, e)
        return creator_id  # Fall back (will fail at DB layer with a clear error)

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
        """
        Extract facts from a conversation and store them.

        Args:
            creator_id: Creator UUID or name slug
            lead_id: Lead UUID as string
            conversation_messages: List of {"role": "user|assistant", "content": "..."}
            source_message_id: Optional message ID that triggered extraction

        Returns:
            List of stored LeadMemory objects (empty on error)
        """
        if not ENABLE_MEMORY_ENGINE:
            return []

        creator_id = self._resolve_creator_uuid(creator_id)

        try:
            formatted_msgs = self._format_messages_for_llm(conversation_messages)
            if not formatted_msgs or len(formatted_msgs) < 20:
                logger.debug("[MemoryEngine] Conversation too short for extraction")
                return []

            extraction = await self._extract_facts_via_llm(formatted_msgs)
            if not extraction.facts and not extraction.summary:
                logger.debug("[MemoryEngine] No facts or summary extracted")
                return []

            fact_texts = [f["text"] for f in extraction.facts]
            embeddings = await self._generate_embeddings_batch(fact_texts)

            existing_facts = await self._get_existing_active_facts(creator_id, lead_id)

            stored_memories = []
            for i, fact in enumerate(extraction.facts):
                embedding = embeddings[i] if i < len(embeddings) else None

                resolution = await self.resolve_conflict(fact, existing_facts)
                if resolution == "skip":
                    logger.debug("[MemoryEngine] Skipping duplicate fact: %s", fact["text"][:50])
                    continue

                memory = await self._store_fact(
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

            if extraction.summary:
                await self.summarize_conversation(
                    creator_id=creator_id,
                    lead_id=lead_id,
                    messages=conversation_messages,
                    precomputed_summary=extraction.summary,
                    precomputed_topics=extraction.key_topics,
                    precomputed_sentiment=extraction.sentiment,
                )

            logger.info(
                "[MemoryEngine] Stored %d facts + summary for lead=%s creator=%s",
                len(stored_memories),
                lead_id[:8],
                creator_id[:8],
            )

            cache_key = f"{creator_id}:{lead_id}"
            _recall_cache.pop(cache_key, None)
            _recall_cache_ts.pop(cache_key, None)

            return stored_memories

        except Exception as e:
            logger.error("[MemoryEngine] add() failed: %s", e, exc_info=True)
            return []

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

        creator_id = self._resolve_creator_uuid(creator_id)

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

        creator_id = self._resolve_creator_uuid(creator_id)
        cache_key = f"{creator_id}:{lead_id}"
        now = time.time()
        cached_ts = _recall_cache_ts.get(cache_key, 0)
        if (now - cached_ts) < _RECALL_CACHE_TTL and cache_key in _recall_cache:
            logger.debug("[MemoryEngine] recall() cache hit for %s", lead_id[:8])
            return _recall_cache[cache_key]

        try:
            facts = await self.search(creator_id, lead_id, new_message, top_k=MAX_FACTS_IN_PROMPT)
            summary = await self._get_latest_summary(creator_id, lead_id)
            result = self._format_memory_section(facts, summary)

            _recall_cache[cache_key] = result
            _recall_cache_ts[cache_key] = now

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
        creator_id = self._resolve_creator_uuid(creator_id)
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
    # PUBLIC: resolve_conflict()
    # ─────────────────────────────────────────────────────────────────────

    async def resolve_conflict(
        self,
        new_fact: Dict[str, Any],
        existing_facts: List[LeadMemory],
    ) -> str:
        """
        Resolve conflict between a new fact and existing facts.

        Returns: "skip" | "supersede" | "store"
        """
        if not existing_facts:
            return "store"

        new_text = new_fact.get("text", "").lower().strip()
        new_type = new_fact.get("type", "")

        for existing in existing_facts:
            existing_text = existing.fact_text.lower().strip()

            if self._text_similarity(new_text, existing_text) > 0.85:
                return "skip"

            if (
                existing.fact_type == new_type
                and new_type in ("preference", "personal_info", "purchase_history")
                and self._text_similarity(new_text, existing_text) > 0.5
            ):
                await self._supersede_fact(existing.id, None)
                return "store"

        return "store"

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC: forget_lead() — GDPR compliance
    # ─────────────────────────────────────────────────────────────────────

    async def forget_lead(self, creator_id: str, lead_id: str) -> int:
        """Delete ALL memories for a specific lead (GDPR right to erasure)."""
        creator_id = self._resolve_creator_uuid(creator_id)
        try:
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
                    total_deleted,
                    lead_id[:8],
                )

                cache_key = f"{creator_id}:{lead_id}"
                _recall_cache.pop(cache_key, None)
                _recall_cache_ts.pop(cache_key, None)

                return total_deleted

            finally:
                session.close()

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

        try:
            from api.database import SessionLocal
            from sqlalchemy import text

            session = SessionLocal()
            deactivated = 0

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
                    deactivated = len(ids_to_deactivate)

                logger.info(
                    "[MemoryEngine] decay: checked %d memories, deactivated %d for creator=%s",
                    len(rows),
                    deactivated,
                    creator_id[:8],
                )
                return deactivated

            finally:
                session.close()

        except Exception as e:
            logger.error("[MemoryEngine] decay_memories() failed: %s", e, exc_info=True)
            return 0

    # ═══════════════════════════════════════════════════════════════════════
    # PRIVATE: LLM integration
    # ═══════════════════════════════════════════════════════════════════════

    async def _extract_facts_via_llm(self, formatted_messages: str) -> ExtractionResult:
        """Call LLM to extract facts from conversation."""
        prompt = FACT_EXTRACTION_PROMPT.format(
            messages=formatted_messages,
            max_facts=MAX_FACTS_PER_EXTRACTION,
        )

        response = await self._call_llm(prompt)
        parsed = self._parse_json_response(response)

        if not parsed:
            return ExtractionResult()

        facts = parsed.get("facts", [])
        valid_types = {"preference", "commitment", "topic", "objection", "personal_info", "purchase_history"}
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
            sentiment=parsed.get("sentiment", "neutral") if parsed.get("sentiment") in ("positive", "neutral", "negative") else "neutral",
            key_topics=parsed.get("key_topics", [])[:5],
        )

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
        try:
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
                        {
                            "id": fact_id,
                            "cid": creator_id,
                            "lid": lead_id,
                            "ftype": fact_type,
                            "ftext": fact_text,
                            "embedding": embedding_str,
                            "conf": confidence,
                            "smid": source_message_id,
                            "stype": source_type,
                        },
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
                        {
                            "id": fact_id,
                            "cid": creator_id,
                            "lid": lead_id,
                            "ftype": fact_type,
                            "ftext": fact_text,
                            "conf": confidence,
                            "smid": source_message_id,
                            "stype": source_type,
                        },
                    )

                session.commit()

                return LeadMemory(
                    id=fact_id,
                    creator_id=creator_id,
                    lead_id=lead_id,
                    fact_type=fact_type,
                    fact_text=fact_text,
                    confidence=confidence,
                    source_message_id=source_message_id,
                    source_type=source_type,
                    created_at=datetime.now(timezone.utc),
                )

            finally:
                session.close()

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
        """Semantic search via pgvector cosine similarity."""
        try:
            from api.database import SessionLocal
            from sqlalchemy import text

            session = SessionLocal()
            try:
                validated_floats = [float(v) for v in query_embedding]
                embedding_str = "[" + ",".join(str(x) for x in validated_floats) + "]"

                rows = session.execute(
                    text(
                        "SELECT id, creator_id, lead_id, fact_type, fact_text, "
                        "confidence, source_type, times_accessed, "
                        "last_accessed_at, created_at, "
                        "1 - (fact_embedding <=> CAST(:query AS vector)) as similarity "
                        "FROM lead_memories "
                        "WHERE creator_id = CAST(:cid AS uuid) "
                        "AND lead_id = CAST(:lid AS uuid) "
                        "AND is_active = true "
                        "AND fact_embedding IS NOT NULL "
                        "AND 1 - (fact_embedding <=> CAST(:query AS vector)) >= :min_sim "
                        "ORDER BY fact_embedding <=> CAST(:query AS vector) "
                        "LIMIT :top_k"
                    ),
                    {
                        "query": embedding_str,
                        "cid": creator_id,
                        "lid": lead_id,
                        "min_sim": min_similarity,
                        "top_k": top_k,
                    },
                ).fetchall()

                results = []
                for row in rows:
                    results.append(
                        LeadMemory(
                            id=str(row[0]),
                            creator_id=str(row[1]),
                            lead_id=str(row[2]),
                            fact_type=row[3],
                            fact_text=row[4],
                            confidence=float(row[5]) if row[5] else 0.7,
                            source_type=row[6] or "extracted",
                            times_accessed=int(row[7]) if row[7] else 0,
                            last_accessed_at=row[8],
                            created_at=row[9],
                            similarity=float(row[10]) if row[10] else 0.0,
                        )
                    )

                return results

            finally:
                session.close()

        except Exception as e:
            logger.error("[MemoryEngine] _pgvector_search() failed: %s", e, exc_info=True)
            return []

    async def _get_existing_active_facts(
        self, creator_id: str, lead_id: str
    ) -> List[LeadMemory]:
        """Get all active facts for a lead (for conflict resolution)."""
        try:
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
                        id=str(row[0]),
                        creator_id=creator_id,
                        lead_id=lead_id,
                        fact_type=row[1],
                        fact_text=row[2],
                        confidence=float(row[3]) if row[3] else 0.7,
                        created_at=row[4],
                    )
                    for row in rows
                ]

            finally:
                session.close()

        except Exception as e:
            logger.error("[MemoryEngine] _get_existing_active_facts() failed: %s", e)
            return []

    async def _get_recent_facts(
        self, creator_id: str, lead_id: str, limit: int
    ) -> List[LeadMemory]:
        """Fallback: get most recent active facts (no semantic search)."""
        try:
            from api.database import SessionLocal
            from sqlalchemy import text

            session = SessionLocal()
            try:
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
                    {"cid": creator_id, "lid": lead_id, "limit": limit},
                ).fetchall()

                return [
                    LeadMemory(
                        id=str(row[0]),
                        creator_id=str(row[1]),
                        lead_id=str(row[2]),
                        fact_type=row[3],
                        fact_text=row[4],
                        confidence=float(row[5]) if row[5] else 0.7,
                        source_type=row[6] or "extracted",
                        times_accessed=int(row[7]) if row[7] else 0,
                        last_accessed_at=row[8],
                        created_at=row[9],
                    )
                    for row in rows
                ]

            finally:
                session.close()

        except Exception as e:
            logger.error("[MemoryEngine] _get_recent_facts() failed: %s", e)
            return []

    async def _update_access_counters(self, memory_ids: List[str]) -> None:
        """Increment times_accessed and update last_accessed_at."""
        try:
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

        except Exception as e:
            logger.debug("[MemoryEngine] _update_access_counters() failed: %s", e)

    async def _supersede_fact(self, old_fact_id: str, new_fact_id: Optional[str]) -> None:
        """Deactivate an old fact and link to its replacement."""
        try:
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

        except Exception as e:
            logger.debug("[MemoryEngine] _supersede_fact() failed: %s", e)

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
        try:
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
                    {
                        "id": summary_id,
                        "cid": creator_id,
                        "lid": lead_id,
                        "summary": summary_text,
                        "topics": json.dumps(key_topics),
                        "commits": json.dumps(commitments_made),
                        "sentiment": sentiment,
                        "count": message_count,
                    },
                )
                session.commit()

                return ConversationSummaryData(
                    id=summary_id,
                    creator_id=creator_id,
                    lead_id=lead_id,
                    summary_text=summary_text,
                    key_topics=key_topics,
                    commitments_made=commitments_made,
                    sentiment=sentiment,
                    message_count=message_count,
                    created_at=datetime.now(timezone.utc),
                )

            finally:
                session.close()

        except Exception as e:
            logger.error("[MemoryEngine] _store_summary() failed: %s", e, exc_info=True)
            return None

    async def _get_latest_summary(
        self, creator_id: str, lead_id: str
    ) -> Optional[ConversationSummaryData]:
        """Get the most recent conversation summary for a lead."""
        try:
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
                    id=str(row[0]),
                    creator_id=creator_id,
                    lead_id=lead_id,
                    summary_text=row[1],
                    key_topics=row[2] or [],
                    commitments_made=row[3] or [],
                    sentiment=row[4] or "neutral",
                    message_count=row[5] or 0,
                    created_at=row[6],
                )

            finally:
                session.close()

        except Exception as e:
            logger.error("[MemoryEngine] _get_latest_summary() failed: %s", e)
            return None

    # ═══════════════════════════════════════════════════════════════════════
    # PRIVATE: Formatting
    # ═══════════════════════════════════════════════════════════════════════

    def _format_messages_for_llm(self, messages: List[Dict[str, str]]) -> str:
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

    def _format_memory_section(
        self,
        facts: List[LeadMemory],
        summary: Optional[ConversationSummaryData],
        max_chars: int = 1200,
    ) -> str:
        """Format memories into the prompt section (max ~300 tokens / 1200 chars)."""
        if not facts and not summary:
            return ""

        lines = ["=== MEMORIA DEL LEAD ==="]

        if facts:
            priority_order = {
                "commitment": 0,
                "preference": 1,
                "objection": 2,
                "personal_info": 3,
                "purchase_history": 4,
                "topic": 5,
            }

            sorted_facts = sorted(
                facts,
                key=lambda f: (priority_order.get(f.fact_type, 9), -(f.created_at or datetime.min.replace(tzinfo=timezone.utc)).timestamp()),
            )

            lines.append("Hechos conocidos sobre este lead:")
            char_budget = max_chars
            chars_used = 0

            for fact in sorted_facts[:MAX_FACTS_IN_PROMPT]:
                time_str = self._relative_time(fact.created_at)

                suffix = ""
                if fact.fact_type == "commitment":
                    suffix = " [PENDIENTE]"

                line = f"- {fact.fact_text} ({time_str}){suffix}"

                if chars_used + len(line) > char_budget:
                    break

                lines.append(line)
                chars_used += len(line)

        if summary:
            time_str = self._relative_time(summary.created_at)
            lines.append(f"\nResumen ultima conversacion ({time_str}):")
            summary_text = summary.summary_text[:150]
            lines.append(summary_text)

        lines.append("=== FIN MEMORIA ===")

        return "\n".join(lines)

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
