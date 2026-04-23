"""
Commitment Tracker — ECHO Engine HARMONIZE Layer

Detecta, almacena y gestiona promesas/compromisos del clon en conversaciones.
Inyecta recordatorios de compromisos pendientes en el prompt.

Detección: regex patterns por creator (vocab_meta), con fallback cold-start
en español embebido aquí. Validación LLM opcional.
Persistencia: tabla `commitments` en PostgreSQL.
Inyección: bloque de texto en el prompt vía RelationshipAdapter.

Feature flag: flags.commitment_tracking (env: ENABLE_COMMITMENT_TRACKING).

Ejemplo de compromisos detectados:
- "te envío el link mañana" → type=delivery, due=mañana
- "te confirmo disponibilidad" → type=info_request
- "quedamos el martes a las 10" → type=meeting, due=martes 10:00
- "te paso el descuento" → type=delivery

Migración zero-hardcoding (Sprint Top-6, 2026-04-23):
    El bloque `_FALLBACK_COMMITMENT_PATTERNS` / `_FALLBACK_TEMPORAL_PATTERNS`
    es el seed cold-start (ES) y se usa SOLO cuando el creator no tiene
    `personality_docs.vocab_meta.content.commitment_patterns` / `.temporal_patterns`
    poblado. Cuando existen, los patterns del creator sobreescriben el fallback.
    El bootstrap consolidado (`scripts/bootstrap_sprint_top6_activations.py`)
    puede copiar este seed como punto de partida para `iris_bertran`.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from core.feature_flags import flags
from core.observability.metrics import emit_metric

logger = logging.getLogger(__name__)

# Module-level proxy to the central registry. Kept as a name for backward
# compat with tests using ``patch("services.commitment_tracker.ENABLE_COMMITMENT_TRACKING", ...)``.
ENABLE_COMMITMENT_TRACKING = flags.commitment_tracking


# ---------------------------------------------------------------------------
# Commitment detection (regex-first, LLM optional)
# ---------------------------------------------------------------------------

# Cold-start seed (Spanish). ONLY used when the creator has no vocab_meta
# entry for commitment_patterns. Per-creator overrides live in
# personality_docs.vocab_meta.content.commitment_patterns (list of
# {"pattern": <regex str>, "type": <str>}).
_FALLBACK_COMMITMENT_PATTERNS: List[Tuple[str, str]] = [
    # Sending information
    (r"te\s+(envío|mando|paso|comparto)\b", "delivery"),
    (r"(mañana|esta semana|luego|después)\s+te\s+(envío|mando|paso)", "delivery"),
    (r"te\s+(lo|la|los|las)\s+(envío|mando|paso)\b", "delivery"),
    # Pending confirmation
    (r"te\s+(confirmo|aviso|digo|cuento)\b", "info_request"),
    (r"(voy\s+a|vamos\s+a)\s+(verificar|consultar|revisar|checar)", "info_request"),
    # Meeting/appointment
    (r"(quedamos|nos\s+vemos|te\s+espero)\s+(el|la|a\s+las)", "meeting"),
    (r"(agend|reserv)(o|amos|é)\s+(una|la|tu)", "meeting"),
    # Follow-up
    (r"te\s+(escribo|contacto|llamo)\s+(mañana|luego|pronto)", "follow_up"),
    (r"(hago|haré)\s+(seguimiento|follow[\s-]?up)", "follow_up"),
    # Generic promises
    (r"te\s+(prometo|aseguro|garantizo)\b", "promise"),
    (r"sin\s+falta\s+te\b", "promise"),
]

# Temporal patterns for due_date extraction (Spanish cold-start seed).
_FALLBACK_TEMPORAL_PATTERNS: List[Tuple[str, int]] = [
    (r"\bmañana\b", 1),
    (r"\bpasado\s+mañana\b", 2),
    (r"\besta\s+semana\b", 5),
    (r"\bla\s+semana\s+que\s+viene\b", 7),
    (r"\bhoy\b", 0),
    (r"\bluego\b", 0),
    (r"\bpronto\b", 2),
]

# Module-level aliases kept for backward-compat with existing tests that may
# reference these names directly. New code should call _load_creator_patterns.
COMMITMENT_PATTERNS = _FALLBACK_COMMITMENT_PATTERNS
TEMPORAL_PATTERNS = _FALLBACK_TEMPORAL_PATTERNS

_COMPILED_FALLBACK_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(p, re.IGNORECASE), t) for p, t in _FALLBACK_COMMITMENT_PATTERNS
]
_COMPILED_FALLBACK_TEMPORAL: List[Tuple[re.Pattern, int]] = [
    (re.compile(p, re.IGNORECASE), d) for p, d in _FALLBACK_TEMPORAL_PATTERNS
]

# Legacy aliases (tests may reference these).
_COMPILED_PATTERNS = _COMPILED_FALLBACK_PATTERNS
_COMPILED_TEMPORAL = _COMPILED_FALLBACK_TEMPORAL


def _load_creator_patterns(
    creator_id: Optional[str],
) -> Tuple[List[Tuple[re.Pattern, str]], List[Tuple[re.Pattern, int]], str]:
    """Return (compiled_commitment_patterns, compiled_temporal_patterns, source).

    ``source`` is one of {"mined", "hardcoded_fallback"}.

    When ``creator_id`` is None or vocab_meta.commitment_patterns is missing,
    the cold-start Spanish fallback is returned. When present, the creator's
    own patterns replace the fallback entirely (no merge — explicit override).
    """
    if not creator_id:
        return _COMPILED_FALLBACK_PATTERNS, _COMPILED_FALLBACK_TEMPORAL, "hardcoded_fallback"

    try:
        import json
        from api.database import SessionLocal
        from sqlalchemy import text as sql

        with SessionLocal() as session:
            row = session.execute(
                sql(
                    """
                    SELECT pd.content
                    FROM personality_docs pd
                    JOIN creators c ON c.id::text = pd.creator_id
                    WHERE (c.name = :cid OR pd.creator_id = :cid)
                      AND pd.doc_type = 'vocab_meta'
                    LIMIT 1
                    """
                ),
                {"cid": creator_id},
            ).fetchone()

        if not row or not row.content:
            return _COMPILED_FALLBACK_PATTERNS, _COMPILED_FALLBACK_TEMPORAL, "hardcoded_fallback"

        parsed = json.loads(row.content)
        cp = parsed.get("commitment_patterns") or []
        tp = parsed.get("temporal_patterns") or []

        if not cp:
            return _COMPILED_FALLBACK_PATTERNS, _COMPILED_FALLBACK_TEMPORAL, "hardcoded_fallback"

        compiled_cp = [
            (re.compile(entry["pattern"], re.IGNORECASE), entry["type"])
            for entry in cp
            if isinstance(entry, dict) and entry.get("pattern") and entry.get("type")
        ]
        compiled_tp = [
            (re.compile(entry["pattern"], re.IGNORECASE), int(entry.get("days", 0)))
            for entry in tp
            if isinstance(entry, dict) and entry.get("pattern")
        ]
        if not compiled_cp:
            return _COMPILED_FALLBACK_PATTERNS, _COMPILED_FALLBACK_TEMPORAL, "hardcoded_fallback"

        return compiled_cp, (compiled_tp or _COMPILED_FALLBACK_TEMPORAL), "mined"
    except Exception as exc:
        logger.debug("[commitment_tracker] vocab_meta load failed for %s: %s", creator_id, exc)
        return _COMPILED_FALLBACK_PATTERNS, _COMPILED_FALLBACK_TEMPORAL, "hardcoded_fallback"


def detect_commitments_regex(
    message: str,
    sender: str = "assistant",
    creator_id: Optional[str] = None,
) -> List[dict]:
    """Detect commitments in a message using regex.

    Only detects BOT commitments (sender="assistant"), not user's.

    Args:
        message: Message text.
        sender: "assistant" or "user".
        creator_id: optional slug/UUID. When provided, the creator's
            vocab_meta.commitment_patterns overrides the cold-start fallback.

    Returns:
        List of dicts with keys: commitment_text, commitment_type, due_days.
    """
    if sender != "assistant":
        return []

    if not flags.commitment_tracking:
        return []

    compiled_patterns, compiled_temporal, source = _load_creator_patterns(creator_id)
    emit_metric(
        "commitment_tracker_patterns_source",
        creator_id=creator_id or "unknown",
        source=source,
    )

    results = []
    seen_types = set()

    for pattern, c_type in compiled_patterns:
        match = pattern.search(message)
        if match and c_type not in seen_types:
            seen_types.add(c_type)

            # Extract context around match (±40 chars)
            start = max(0, match.start() - 40)
            end = min(len(message), match.end() + 40)
            context = message[start:end].strip()

            # Try to extract due_date
            due_days = None
            for t_pattern, days in compiled_temporal:
                if t_pattern.search(message):
                    due_days = days
                    break

            results.append({
                "commitment_text": context,
                "commitment_type": c_type,
                "due_days": due_days,
            })
            emit_metric(
                "commitment_detected_total",
                creator_id=creator_id or "unknown",
                commitment_type=c_type,
                source=source,
            )

    return results


# ---------------------------------------------------------------------------
# Persistence service (sync, matching Clonnect's SessionLocal pattern)
# ---------------------------------------------------------------------------

class CommitmentTrackerService:
    """Manages commitments in the database.

    Typical usage:
        tracker = CommitmentTrackerService()

        # Post-send: detect and store
        tracker.detect_and_store(response_text, creator_id, lead_id, msg_id)

        # Pre-generation: get pending for prompt injection
        text = tracker.get_pending_text(lead_id)

        # Post-fulfillment: mark as fulfilled
        tracker.mark_fulfilled(commitment_id, fulfilled_msg_id)
    """

    def detect_and_store(
        self,
        response_text: str,
        creator_id: str,
        lead_id: str,
        source_message_id: Optional[str] = None,
    ) -> List:
        """Detect commitments in a bot response and store them.

        Executed as fire-and-forget after sending response.

        Returns:
            List of CommitmentModel objects created.
        """
        if not ENABLE_COMMITMENT_TRACKING:
            return []

        detected = detect_commitments_regex(
            response_text, sender="assistant", creator_id=creator_id
        )
        if not detected:
            return []

        from api.database import SessionLocal
        from api.models import CommitmentModel

        session = SessionLocal()
        created = []
        now = datetime.now(timezone.utc)

        try:
            for item in detected:
                due_date = None
                if item["due_days"] is not None:
                    due_date = now + timedelta(days=item["due_days"])

                commitment = CommitmentModel(
                    creator_id=creator_id,
                    lead_id=lead_id,
                    commitment_text=item["commitment_text"],
                    commitment_type=item["commitment_type"],
                    due_date=due_date,
                    source_message_id=source_message_id,
                    status="pending",
                    detected_by="regex",
                )
                session.add(commitment)
                created.append(commitment)
                logger.info(
                    "[COMMITMENT] Detected: type=%s text='%s' lead=%s",
                    item["commitment_type"],
                    item["commitment_text"][:60],
                    lead_id,
                )

            if created:
                session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"[COMMITMENT] Failed to store: {e}")
            created = []
        finally:
            session.close()

        return created

    def get_pending_for_lead(
        self,
        lead_id: str,
        limit: int = 5,
    ) -> List:
        """Return pending commitments for a lead.

        Executed in Phase 2 (parallel IO) for prompt injection.
        """
        if not ENABLE_COMMITMENT_TRACKING:
            return []

        from api.database import SessionLocal
        from api.models import CommitmentModel

        session = SessionLocal()
        try:
            commitments = (
                session.query(CommitmentModel)
                .filter(
                    CommitmentModel.lead_id == lead_id,
                    CommitmentModel.status == "pending",
                )
                .order_by(CommitmentModel.created_at.desc())
                .limit(limit)
                .all()
            )
            # Detach from session to avoid lazy load issues
            for c in commitments:
                session.expunge(c)
            return commitments
        except Exception as e:
            logger.error(f"[COMMITMENT] Failed to get pending: {e}")
            return []
        finally:
            session.close()

    def get_pending_text(
        self,
        lead_id: str,
        limit: int = 3,
    ) -> str:
        """Return formatted text of pending commitments for prompt injection.

        Format:
            - [hace 2 días] Prometiste enviarle el link del curso.
            - [vence mañana] Confirmaste disponibilidad para el martes.
        """
        commitments = self.get_pending_for_lead(lead_id, limit=limit)
        if not commitments:
            return ""

        now = datetime.now(timezone.utc)
        lines = []

        for c in commitments:
            # Calculate elapsed time
            created = c.created_at
            if created and created.tzinfo is None:
                from datetime import timezone as tz
                created = created.replace(tzinfo=tz.utc)

            if created:
                delta = now - created
                if delta.days == 0:
                    time_str = "hoy"
                elif delta.days == 1:
                    time_str = "ayer"
                else:
                    time_str = f"hace {delta.days} días"
            else:
                time_str = "reciente"

            # Due date info
            due_str = ""
            if c.due_date:
                due = c.due_date
                if due.tzinfo is None:
                    due = due.replace(tzinfo=timezone.utc)
                due_delta = due - now
                if due_delta.days < 0:
                    due_str = " (VENCIDO)"
                elif due_delta.days == 0:
                    due_str = " (vence hoy)"
                elif due_delta.days == 1:
                    due_str = " (vence mañana)"
                else:
                    due_str = f" (vence en {due_delta.days} días)"

            lines.append(f"- [{time_str}] {c.commitment_text}{due_str}")

        return "\n".join(lines)

    def mark_fulfilled(
        self,
        commitment_id: str,
        fulfilled_message_id: Optional[str] = None,
    ) -> bool:
        """Mark a commitment as fulfilled."""
        from api.database import SessionLocal
        from api.models import CommitmentModel

        session = SessionLocal()
        try:
            commitment = (
                session.query(CommitmentModel)
                .filter(
                    CommitmentModel.id == commitment_id,
                    CommitmentModel.status == "pending",
                )
                .first()
            )
            if not commitment:
                return False

            commitment.status = "fulfilled"
            commitment.fulfilled_at = datetime.now(timezone.utc)
            commitment.updated_at = datetime.now(timezone.utc)
            session.commit()
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"[COMMITMENT] Failed to mark fulfilled: {e}")
            return False
        finally:
            session.close()

    def expire_overdue(
        self,
        creator_id: str,
        grace_days: int = 3,
    ) -> int:
        """Mark overdue commitments as expired.

        Runs as background job (every 24h).

        Args:
            creator_id: Creator ID.
            grace_days: Grace days after due_date.

        Returns:
            Number of expired commitments.
        """
        from api.database import SessionLocal
        from api.models import CommitmentModel

        session = SessionLocal()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=grace_days)
            count = (
                session.query(CommitmentModel)
                .filter(
                    CommitmentModel.creator_id == creator_id,
                    CommitmentModel.status == "pending",
                    CommitmentModel.due_date.isnot(None),
                    CommitmentModel.due_date < cutoff,
                )
                .update(
                    {
                        "status": "expired",
                        "updated_at": datetime.now(timezone.utc),
                    },
                    synchronize_session=False,
                )
            )
            session.commit()
            return count
        except Exception as e:
            session.rollback()
            logger.error(f"[COMMITMENT] Failed to expire overdue: {e}")
            return 0
        finally:
            session.close()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_tracker_instance: Optional[CommitmentTrackerService] = None


def get_commitment_tracker() -> CommitmentTrackerService:
    """Get singleton CommitmentTrackerService instance."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = CommitmentTrackerService()
    return _tracker_instance
