"""ARC3 Phase 1 — StyleDistillCache service.

Manages distilled (compressed) versions of creator Doc D (style_prompt).
Distillation reduces ~5 500-char Doc D to ~1 500 chars while preserving
voice, concrete examples, tone rules, and form constraints.

SHADOW phase: distillation is generated and cached but NOT used in prod
until USE_DISTILLED_DOC_D=true (Phase 3 activation).

Env vars:
  OPENROUTER_API_KEY      — required for LLM calls
  OPENROUTER_MODEL        — model override (default: google/gemma-4-31b-it)

Usage:
    from services.style_distill_service import StyleDistillService
    service = StyleDistillService(session)
    distilled = await service.get_or_generate(creator_id, doc_d)
"""

import asyncio
import hashlib
import logging
import os
import uuid
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Distillation prompt version — bump this to force re-distillation of all creators.
DISTILL_PROMPT_VERSION: int = 1

# Target output length in chars.
DISTILL_TARGET_CHARS: int = 1500
DISTILL_MIN_CHARS: int = 1200
DISTILL_MAX_CHARS: int = 1800

# LLM call settings.
_DISTILL_TIMEOUT_S: float = 90.0
_DISTILL_MAX_RETRIES: int = 2

# ─────────────────────────────────────────────────────────────────────────────
# Distillation prompt v1 (ARC3 §2.2.3)
# ─────────────────────────────────────────────────────────────────────────────

DISTILL_PROMPT_V1 = """
Eres un experto en preservar la voz y el estilo comunicativo de un creador de contenido.

A continuación tienes el "Doc D" completo de un creador (su style_prompt). Tu tarea es
producir una versión DESTILADA que preserve:

1. La VOZ única (tics verbales, expresiones características, tono)
2. Los EJEMPLOS concretos más representativos (al menos 3-5)
3. Las reglas de tono según situación (cold/warm/hot lead si existen)
4. Las restricciones de forma (longitud, emojis, puntuación si existen)

Debes ELIMINAR:
- Frases genéricas sobre "ser auténtico" o "conectar con el lead"
- Redundancias (misma idea dicha 2+ veces)
- Meta-comentarios sobre el estilo (decir "mi estilo es X" en lugar de demostrarlo)
- Ejemplos menos informativos si hay varios similares

TARGET: {target_chars} caracteres (±15%).

FORMATO DE SALIDA: Solo el texto destilado, sin meta-explicaciones ni preámbulo.

DOC D ORIGINAL:
---
{doc_d}
---

VERSIÓN DESTILADA:
"""


class StyleDistillService:
    """Cache and generate distilled Doc D for creators.

    Args:
        session: SQLAlchemy session (sync). Passed in from caller.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    async def get_or_generate(
        self,
        creator_id: str,
        source_doc_d: str,
        prompt_version: int = DISTILL_PROMPT_VERSION,
        force: bool = False,
    ) -> str:
        """Return distilled_short for (creator_id, source_doc_d, prompt_version).

        If a cached row exists and force=False, returns it immediately.
        Otherwise calls the LLM, stores the result, and returns it.

        Args:
            creator_id: UUID string of the creator.
            source_doc_d: Full Doc D text (style_prompt).
            prompt_version: Distillation prompt version (default 1).
            force: If True, regenerate even when a cached row exists.

        Returns:
            Distilled text (approximately DISTILL_TARGET_CHARS chars).

        Raises:
            RuntimeError: If LLM call fails after all retries.
        """
        doc_d_hash = self.compute_hash(source_doc_d)

        if not force:
            cached = self._fetch_cached(creator_id, doc_d_hash, prompt_version)
            if cached is not None:
                logger.info(
                    "StyleDistillCache HIT: creator=%s hash=%s version=%d → %d chars",
                    creator_id, doc_d_hash, prompt_version, len(cached),
                )
                return cached

        logger.info(
            "StyleDistillCache MISS: creator=%s hash=%s version=%d force=%s — calling LLM",
            creator_id, doc_d_hash, prompt_version, force,
        )

        distilled = await self._call_llm_for_distill(source_doc_d, DISTILL_TARGET_CHARS)

        self._upsert_row(
            creator_id=creator_id,
            doc_d_hash=doc_d_hash,
            doc_d_chars=len(source_doc_d),
            doc_d_version=0,  # no versioning at this layer; caller may pass via force
            distilled_short=distilled,
            distilled_chars=len(distilled),
            distill_model=_distill_model(),
            distill_prompt_version=prompt_version,
        )

        logger.info(
            "StyleDistillCache STORED: creator=%s hash=%s → %d chars (ratio=%.0f%%)",
            creator_id, doc_d_hash, len(distilled),
            100 * len(distilled) / max(len(source_doc_d), 1),
        )
        return distilled

    def compute_hash(self, content: str) -> str:
        """Return first 16 hex chars of SHA-256 of content."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def list_distills(self, creator_id: Optional[str] = None) -> list:
        """List distill rows, optionally filtered by creator_id UUID string."""
        try:
            from sqlalchemy import text as _text

            if creator_id is not None:
                result = self.session.execute(
                    _text(
                        "SELECT id, creator_id, doc_d_hash, doc_d_chars, distilled_chars,"
                        " distill_model, distill_prompt_version, quality_score,"
                        " human_validated, created_at"
                        " FROM creator_style_distill"
                        " WHERE creator_id = :cid"
                        " ORDER BY created_at DESC"
                    ),
                    {"cid": creator_id},
                )
            else:
                result = self.session.execute(
                    _text(
                        "SELECT id, creator_id, doc_d_hash, doc_d_chars, distilled_chars,"
                        " distill_model, distill_prompt_version, quality_score,"
                        " human_validated, created_at"
                        " FROM creator_style_distill"
                        " ORDER BY created_at DESC"
                    )
                )
            rows = result.fetchall()
            return [dict(r._mapping) for r in rows]
        except Exception as exc:
            logger.warning("StyleDistillService.list_distills failed: %s", exc)
            return []

    async def mark_quality_score(self, record_id: str, score: float) -> None:
        """Update quality_score for a distill row identified by its UUID."""
        try:
            from sqlalchemy import text as _text

            self.session.execute(
                _text(
                    "UPDATE creator_style_distill"
                    " SET quality_score = :score, updated_at = NOW()"
                    " WHERE id = :rid"
                ),
                {"score": score, "rid": record_id},
            )
            self.session.commit()
            logger.info("StyleDistillService: marked quality_score=%.2f for record %s", score, record_id)
        except Exception as exc:
            logger.warning("StyleDistillService.mark_quality_score failed: %s", exc)

    # ─────────────────────────────────────────────────────────────────────────
    # LLM call
    # ─────────────────────────────────────────────────────────────────────────

    async def _call_llm_for_distill(
        self, source_doc_d: str, target_chars: int = DISTILL_TARGET_CHARS
    ) -> str:
        """Call OpenRouter to distill source_doc_d.

        Retries up to _DISTILL_MAX_RETRIES times with exponential backoff.
        Validates output length in [DISTILL_MIN_CHARS, DISTILL_MAX_CHARS].
        After one length-validation failure, retries once more.

        Args:
            source_doc_d: Original Doc D text.
            target_chars: Target output length hint passed to the prompt.

        Returns:
            Distilled text string.

        Raises:
            RuntimeError: If all attempts fail or output never validates.
        """
        prompt = DISTILL_PROMPT_V1.format(
            target_chars=target_chars,
            doc_d=source_doc_d,
        )
        messages = [{"role": "user", "content": prompt}]
        model = _distill_model()

        for attempt in range(_DISTILL_MAX_RETRIES):
            try:
                from core.providers.openrouter_provider import call_openrouter

                result = await asyncio.wait_for(
                    call_openrouter(
                        messages=messages,
                        model=model,
                        max_tokens=900,
                        temperature=0.3,
                    ),
                    timeout=_DISTILL_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "StyleDistillService: LLM timeout on attempt %d/%d",
                    attempt + 1, _DISTILL_MAX_RETRIES,
                )
                if attempt < _DISTILL_MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                continue
            except Exception as exc:
                logger.error(
                    "StyleDistillService: LLM error on attempt %d/%d: %s",
                    attempt + 1, _DISTILL_MAX_RETRIES, exc,
                )
                if attempt < _DISTILL_MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                continue

            if result is None:
                logger.warning(
                    "StyleDistillService: LLM returned None on attempt %d/%d",
                    attempt + 1, _DISTILL_MAX_RETRIES,
                )
                if attempt < _DISTILL_MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                continue

            content = result.get("content", "")

            if not (DISTILL_MIN_CHARS <= len(content) <= DISTILL_MAX_CHARS):
                logger.warning(
                    "StyleDistillService: length validation FAILED (got %d chars, "
                    "expected [%d, %d]) on attempt %d/%d — retrying",
                    len(content), DISTILL_MIN_CHARS, DISTILL_MAX_CHARS,
                    attempt + 1, _DISTILL_MAX_RETRIES,
                )
                if attempt < _DISTILL_MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                continue

            return content

        raise RuntimeError(
            f"StyleDistillService: all {_DISTILL_MAX_RETRIES} distillation attempts failed"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # DB helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _fetch_cached(
        self,
        creator_id: str,
        doc_d_hash: str,
        prompt_version: int,
    ) -> Optional[str]:
        """Return distilled_short from DB, or None if not found."""
        try:
            from sqlalchemy import text as _text

            result = self.session.execute(
                _text(
                    "SELECT distilled_short FROM creator_style_distill"
                    " WHERE creator_id = :cid"
                    "   AND doc_d_hash = :hash"
                    "   AND distill_prompt_version = :pv"
                    " LIMIT 1"
                ),
                {"cid": creator_id, "hash": doc_d_hash, "pv": prompt_version},
            )
            row = result.fetchone()
            if row is not None:
                return row[0]
            return None
        except Exception as exc:
            logger.warning("StyleDistillService._fetch_cached error: %s", exc)
            return None

    def _upsert_row(
        self,
        creator_id: str,
        doc_d_hash: str,
        doc_d_chars: int,
        doc_d_version: int,
        distilled_short: str,
        distilled_chars: int,
        distill_model: str,
        distill_prompt_version: int,
    ) -> None:
        """Insert or update a distill row (ON CONFLICT upsert)."""
        try:
            from sqlalchemy import text as _text

            self.session.execute(
                _text(
                    "INSERT INTO creator_style_distill"
                    " (id, creator_id, doc_d_hash, doc_d_chars, doc_d_version,"
                    "  distilled_short, distilled_chars, distill_model,"
                    "  distill_prompt_version, created_at, updated_at)"
                    " VALUES"
                    " (gen_random_uuid(), :cid, :hash, :dc, :dv,"
                    "  :ds, :dsc, :dm, :dpv, NOW(), NOW())"
                    " ON CONFLICT (creator_id, doc_d_hash, distill_prompt_version)"
                    " DO UPDATE SET"
                    "   distilled_short = EXCLUDED.distilled_short,"
                    "   distilled_chars = EXCLUDED.distilled_chars,"
                    "   distill_model = EXCLUDED.distill_model,"
                    "   doc_d_chars = EXCLUDED.doc_d_chars,"
                    "   doc_d_version = EXCLUDED.doc_d_version,"
                    "   updated_at = NOW()"
                ),
                {
                    "cid": creator_id,
                    "hash": doc_d_hash,
                    "dc": doc_d_chars,
                    "dv": doc_d_version,
                    "ds": distilled_short,
                    "dsc": distilled_chars,
                    "dm": distill_model,
                    "dpv": distill_prompt_version,
                },
            )
            self.session.commit()
        except Exception as exc:
            logger.error("StyleDistillService._upsert_row failed: %s", exc)
            raise


def _distill_model() -> str:
    """Return the model string to use for distillation."""
    return os.getenv("OPENROUTER_MODEL", "google/gemma-4-31b-it")
