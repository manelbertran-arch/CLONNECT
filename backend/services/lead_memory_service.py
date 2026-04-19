"""LeadMemoryService — ARC2 A2.1.

Single interface for reading/writing arc2_lead_memories.
The 3 legacy systems (MemoryEngine, ConversationMemoryService, MemoryStore)
remain untouched; this service only touches arc2_lead_memories.

Single-writer enforcement: advisory lock per lead_id to prevent interleaved
writes from concurrent extractors.
"""

import logging
from typing import Any, Literal, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MemoryType = Literal[
    "identity", "interest", "objection", "intent_signal", "relationship_state"
]

WriterName = Literal["dm_extractor", "copilot", "onboarding", "migration", "manual"]

MEMORY_TYPES: list[str] = [
    "identity", "interest", "objection", "intent_signal", "relationship_state"
]

# Types that require why + how_to_apply (mirrors DB CHECK constraints)
_REQUIRES_WHY_HOW: frozenset[str] = frozenset({"objection", "relationship_state"})


# ─────────────────────────────────────────────────────────────────────────────
# Data models
# ─────────────────────────────────────────────────────────────────────────────

class LeadMemory:
    """Hydrated row from arc2_lead_memories."""

    __slots__ = (
        "id", "creator_id", "lead_id", "memory_type", "content",
        "why", "how_to_apply", "body_extras", "embedding",
        "source_message_id", "confidence", "last_writer",
        "created_at", "updated_at", "deleted_at", "superseded_by",
    )

    def __init__(self, row: Any) -> None:
        for slot in self.__slots__:
            setattr(self, slot, getattr(row, slot, None))

    def __repr__(self) -> str:
        return (
            f"<LeadMemory id={self.id} type={self.memory_type!r} "
            f"writer={self.last_writer!r}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_memory_type(memory_type: str) -> None:
    if memory_type not in MEMORY_TYPES:
        raise ValueError(
            f"Invalid memory_type {memory_type!r}. "
            f"Must be one of: {MEMORY_TYPES}"
        )


def validate_body_structure(
    memory_type: str,
    why: Optional[str],
    how_to_apply: Optional[str],
) -> None:
    """Raise ValueError if required fields are missing for the given type."""
    if memory_type in _REQUIRES_WHY_HOW:
        if not why:
            raise ValueError(
                f"memory_type={memory_type!r} requires 'why' to be non-empty"
            )
        if not how_to_apply:
            raise ValueError(
                f"memory_type={memory_type!r} requires 'how_to_apply' to be non-empty"
            )


def validate_confidence(confidence: float) -> None:
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(
            f"confidence must be in [0, 1], got {confidence}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Service
# ─────────────────────────────────────────────────────────────────────────────

class LeadMemoryService:
    """Único interface para leer/escribir arc2_lead_memories."""

    def __init__(self, session: Session) -> None:
        self._db = session

    # ── Advisory lock ─────────────────────────────────────────────────────

    def _acquire_advisory_lock(self, lead_id: UUID) -> None:
        lock_key = hash(str(lead_id)) & 0x7FFFFFFFFFFFFFFF
        self._db.execute(
            text("SELECT pg_advisory_xact_lock(:key)"),
            {"key": lock_key},
        )

    # ── Writes ────────────────────────────────────────────────────────────

    def upsert(
        self,
        *,
        creator_id: UUID,
        lead_id: UUID,
        memory_type: str,
        content: str,
        last_writer: str,
        why: Optional[str] = None,
        how_to_apply: Optional[str] = None,
        body_extras: Optional[dict[str, Any]] = None,
        source_message_id: Optional[UUID] = None,
        confidence: float = 1.0,
        embedding: Optional[list[float]] = None,
    ) -> LeadMemory:
        """Insert or update a memory (dedup key: creator_id, lead_id, memory_type, content).

        Single-writer enforcement via PostgreSQL advisory lock.
        If a row exists with a different last_writer, logs a warning and proceeds
        with newer-wins semantics.
        """
        validate_memory_type(memory_type)
        validate_body_structure(memory_type, why, how_to_apply)
        validate_confidence(confidence)

        self._acquire_advisory_lock(lead_id)

        existing = self._db.execute(
            text(
                "SELECT id, last_writer FROM arc2_lead_memories "
                "WHERE creator_id = :cid AND lead_id = :lid "
                "AND memory_type = :mtype AND content = :content "
                "AND deleted_at IS NULL"
            ),
            {
                "cid": str(creator_id),
                "lid": str(lead_id),
                "mtype": memory_type,
                "content": content,
            },
        ).fetchone()

        if existing and existing.last_writer != last_writer:
            logger.warning(
                "arc2_lead_memories writer conflict: lead=%s type=%s "
                "prev_writer=%s new_writer=%s — newer-wins",
                lead_id, memory_type, existing.last_writer, last_writer,
            )

        embedding_sql = ":emb::vector" if embedding is not None else "NULL"
        params: dict[str, Any] = {
            "cid": str(creator_id),
            "lid": str(lead_id),
            "mtype": memory_type,
            "content": content,
            "why": why,
            "how_to_apply": how_to_apply,
            "body_extras": body_extras or {},
            "src": str(source_message_id) if source_message_id else None,
            "confidence": confidence,
            "last_writer": last_writer,
        }
        if embedding is not None:
            params["emb"] = str(embedding)

        row = self._db.execute(
            text(f"""
                INSERT INTO arc2_lead_memories
                    (creator_id, lead_id, memory_type, content, why, how_to_apply,
                     body_extras, source_message_id, confidence, last_writer, embedding)
                VALUES
                    (:cid, :lid, :mtype, :content, :why, :how_to_apply,
                     :body_extras::jsonb, :src, :confidence, :last_writer,
                     {embedding_sql})
                ON CONFLICT (creator_id, lead_id, memory_type, content) DO UPDATE SET
                    why            = EXCLUDED.why,
                    how_to_apply   = EXCLUDED.how_to_apply,
                    body_extras    = EXCLUDED.body_extras,
                    confidence     = EXCLUDED.confidence,
                    last_writer    = EXCLUDED.last_writer,
                    embedding      = EXCLUDED.embedding,
                    deleted_at     = NULL,
                    updated_at     = now()
                RETURNING *
            """),
            params,
        ).fetchone()

        self._db.commit()
        return LeadMemory(row)

    def soft_delete(self, memory_id: UUID, writer: str) -> None:
        self._db.execute(
            text(
                "UPDATE arc2_lead_memories SET deleted_at = now(), last_writer = :writer "
                "WHERE id = :id AND deleted_at IS NULL"
            ),
            {"id": str(memory_id), "writer": writer},
        )
        self._db.commit()

    def supersede(
        self,
        old_id: UUID,
        *,
        creator_id: UUID,
        lead_id: UUID,
        memory_type: str,
        content: str,
        last_writer: str,
        why: Optional[str] = None,
        how_to_apply: Optional[str] = None,
        body_extras: Optional[dict[str, Any]] = None,
        confidence: float = 1.0,
        embedding: Optional[list[float]] = None,
    ) -> LeadMemory:
        """Mark old memory as superseded, insert new correction."""
        new_memory = self.upsert(
            creator_id=creator_id,
            lead_id=lead_id,
            memory_type=memory_type,
            content=content,
            last_writer=last_writer,
            why=why,
            how_to_apply=how_to_apply,
            body_extras=body_extras,
            confidence=confidence,
            embedding=embedding,
        )
        self._db.execute(
            text(
                "UPDATE arc2_lead_memories "
                "SET superseded_by = :new_id, deleted_at = now() "
                "WHERE id = :old_id"
            ),
            {"new_id": str(new_memory.id), "old_id": str(old_id)},
        )
        self._db.commit()
        return new_memory

    # ── Reads ─────────────────────────────────────────────────────────────

    def get_all(
        self,
        creator_id: UUID,
        lead_id: UUID,
    ) -> list[LeadMemory]:
        rows = self._db.execute(
            text(
                "SELECT * FROM arc2_lead_memories "
                "WHERE creator_id = :cid AND lead_id = :lid "
                "AND deleted_at IS NULL "
                "ORDER BY created_at"
            ),
            {"cid": str(creator_id), "lid": str(lead_id)},
        ).fetchall()
        return [LeadMemory(r) for r in rows]

    def get_by_type(
        self,
        creator_id: UUID,
        lead_id: UUID,
        types: list[str],
    ) -> list[LeadMemory]:
        for t in types:
            validate_memory_type(t)
        rows = self._db.execute(
            text(
                "SELECT * FROM arc2_lead_memories "
                "WHERE creator_id = :cid AND lead_id = :lid "
                "AND memory_type = ANY(:types) AND deleted_at IS NULL "
                "ORDER BY created_at"
            ),
            {"cid": str(creator_id), "lid": str(lead_id), "types": types},
        ).fetchall()
        return [LeadMemory(r) for r in rows]

    def get_one(
        self,
        creator_id: UUID,
        lead_id: UUID,
        memory_type: str,
        content: str,
    ) -> Optional[LeadMemory]:
        validate_memory_type(memory_type)
        row = self._db.execute(
            text(
                "SELECT * FROM arc2_lead_memories "
                "WHERE creator_id = :cid AND lead_id = :lid "
                "AND memory_type = :mtype AND content = :content "
                "AND deleted_at IS NULL"
            ),
            {
                "cid": str(creator_id),
                "lid": str(lead_id),
                "mtype": memory_type,
                "content": content,
            },
        ).fetchone()
        return LeadMemory(row) if row else None

    def recall_semantic(
        self,
        creator_id: UUID,
        lead_id: UUID,
        query_embedding: list[float],
        top_k: int = 5,
        threshold: float = 0.7,
    ) -> list[LeadMemory]:
        """pgvector cosine similarity search, filtered by threshold."""
        rows = self._db.execute(
            text(
                "SELECT *, 1 - (embedding <=> :emb::vector) AS _score "
                "FROM arc2_lead_memories "
                "WHERE creator_id = :cid AND lead_id = :lid "
                "AND deleted_at IS NULL AND embedding IS NOT NULL "
                "AND 1 - (embedding <=> :emb::vector) >= :thr "
                "ORDER BY embedding <=> :emb::vector "
                "LIMIT :top_k"
            ),
            {
                "cid": str(creator_id),
                "lid": str(lead_id),
                "emb": str(query_embedding),
                "thr": threshold,
                "top_k": top_k,
            },
        ).fetchall()
        return [LeadMemory(r) for r in rows]

    def count_by_type(
        self,
        creator_id: UUID,
        lead_id: UUID,
    ) -> dict[str, int]:
        rows = self._db.execute(
            text(
                "SELECT memory_type, COUNT(*) AS cnt "
                "FROM arc2_lead_memories "
                "WHERE creator_id = :cid AND lead_id = :lid "
                "AND deleted_at IS NULL "
                "GROUP BY memory_type"
            ),
            {"cid": str(creator_id), "lid": str(lead_id)},
        ).fetchall()
        result = {t: 0 for t in MEMORY_TYPES}
        for row in rows:
            result[row.memory_type] = row.cnt
        return result

    def delete_by_lead(self, creator_id: UUID, lead_id: UUID) -> int:
        """Soft-delete all memories for a lead. Returns count deleted."""
        result = self._db.execute(
            text(
                "UPDATE arc2_lead_memories SET deleted_at = now() "
                "WHERE creator_id = :cid AND lead_id = :lid "
                "AND deleted_at IS NULL"
            ),
            {"cid": str(creator_id), "lid": str(lead_id)},
        )
        self._db.commit()
        return result.rowcount

    def get_current_state(
        self,
        creator_id: UUID,
        lead_id: UUID,
    ) -> dict[str, Any]:
        """Consolidated snapshot: identity + active objections + current state + recent intents."""
        all_memories = self.get_all(creator_id, lead_id)
        snapshot: dict[str, Any] = {
            "identity": [],
            "interest": [],
            "objections": [],
            "intent_signals": [],
            "relationship_state": None,
        }
        for m in all_memories:
            if m.memory_type == "identity":
                snapshot["identity"].append(m)
            elif m.memory_type == "interest":
                snapshot["interest"].append(m)
            elif m.memory_type == "objection":
                snapshot["objections"].append(m)
            elif m.memory_type == "intent_signal":
                snapshot["intent_signals"].append(m)
            elif m.memory_type == "relationship_state":
                if snapshot["relationship_state"] is None:
                    snapshot["relationship_state"] = m
                elif m.created_at and snapshot["relationship_state"].created_at:
                    if m.created_at > snapshot["relationship_state"].created_at:
                        snapshot["relationship_state"] = m
        return snapshot
