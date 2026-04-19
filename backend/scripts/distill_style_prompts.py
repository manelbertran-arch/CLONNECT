#!/usr/bin/env python3
"""ARC3 Phase 1 — Batch distillation script for creator Doc D.

Iterates over all active creators (or a single one), loads their Doc D
(style_prompt), and calls StyleDistillService.get_or_generate() to produce
and cache distilled versions.

SHADOW phase: distillations are stored in creator_style_distill but NOT used
in prod. Set USE_DISTILLED_DOC_D=true (Phase 3) to activate.

Usage:
    python3.11 scripts/distill_style_prompts.py
    python3.11 scripts/distill_style_prompts.py --creator-id <uuid>
    python3.11 scripts/distill_style_prompts.py --force
    python3.11 scripts/distill_style_prompts.py --dry-run

Env vars required:
    DATABASE_URL          — PostgreSQL connection string
    OPENROUTER_API_KEY    — for LLM distillation calls
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Ensure backend root is importable
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Load .env if present (set -a && source .env equivalent)
_env_file = _BACKEND / ".env"
if _env_file.exists():
    try:
        with open(_env_file) as _f:
            for _line in _f:
                _line = _line.strip()
                if not _line or _line.startswith("#") or "=" not in _line:
                    continue
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())
    except Exception as _e:
        pass  # non-fatal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("distill_style_prompts")

MIN_DOC_D_CHARS: int = 1500  # skip creators with shorter Doc D


# ─────────────────────────────────────────────────────────────────────────────
# Data classes for reporting
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CreatorResult:
    creator_id: str
    nickname: str
    status: str  # "ok" | "skipped" | "error"
    source_chars: int = 0
    distilled_chars: int = 0
    ratio: float = 0.0
    error: str = ""


@dataclass
class Report:
    results: list[CreatorResult] = field(default_factory=list)

    def add(self, r: CreatorResult) -> None:
        self.results.append(r)

    def summary(self) -> str:
        ok = [r for r in self.results if r.status == "ok"]
        skipped = [r for r in self.results if r.status == "skipped"]
        errors = [r for r in self.results if r.status == "error"]
        lines = [
            "",
            "=" * 60,
            "DISTILLATION SUMMARY",
            "=" * 60,
            f"  Processed : {len(ok)}",
            f"  Skipped   : {len(skipped)}",
            f"  Errors    : {len(errors)}",
            "",
        ]
        if ok:
            lines.append("PROCESSED:")
            for r in ok:
                lines.append(
                    f"  {r.nickname}: {r.source_chars} → {r.distilled_chars} chars"
                    f" ({r.ratio:.0%})"
                )
        if skipped:
            lines.append("SKIPPED:")
            for r in skipped:
                lines.append(f"  {r.nickname}: {r.error}")
        if errors:
            lines.append("ERRORS:")
            for r in errors:
                lines.append(f"  {r.nickname}: {r.error}")
        lines.append("=" * 60)
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_session():
    """Return a SQLAlchemy Session connected to DATABASE_URL."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise EnvironmentError("DATABASE_URL is not set")
    engine = create_engine(db_url, pool_pre_ping=True, pool_size=2, max_overflow=0)
    Session = sessionmaker(bind=engine)
    return Session()


def _fetch_active_creators(session, creator_id: Optional[str] = None) -> list[dict]:
    """Return list of dicts with {id, name} for active creators."""
    from sqlalchemy import text

    if creator_id:
        result = session.execute(
            text(
                "SELECT id::text, name FROM creators"
                " WHERE name = :cid"
            ),
            {"cid": creator_id},
        )
    else:
        result = session.execute(
            text(
                "SELECT id::text, name FROM creators"
                " WHERE bot_active = true"
                " ORDER BY name"
            )
        )
    rows = result.fetchall()
    return [{"id": r[0], "name": r[1]} for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Core logic
# ─────────────────────────────────────────────────────────────────────────────

async def _process_creator(
    session,
    creator: dict,
    prompt_version: int,
    force: bool,
    dry_run: bool,
) -> CreatorResult:
    """Distill Doc D for a single creator. Returns CreatorResult."""
    cid = creator["id"]
    nickname = creator["name"]

    # Load Doc D
    try:
        from services.creator_style_loader import get_creator_style_prompt

        doc_d = get_creator_style_prompt(nickname)  # creator_id is the slug/name
    except Exception as exc:
        return CreatorResult(
            creator_id=cid, nickname=nickname, status="error",
            error=f"Could not load Doc D: {exc}",
        )

    if not doc_d or len(doc_d) < MIN_DOC_D_CHARS:
        return CreatorResult(
            creator_id=cid, nickname=nickname, status="skipped",
            source_chars=len(doc_d) if doc_d else 0,
            error=f"Doc D too short ({len(doc_d) if doc_d else 0} < {MIN_DOC_D_CHARS} chars)",
        )

    source_chars = len(doc_d)

    if dry_run:
        logger.info("[DRY-RUN] %s: would distill %d chars", nickname, source_chars)
        return CreatorResult(
            creator_id=cid, nickname=nickname, status="ok",
            source_chars=source_chars,
            distilled_chars=0,
            ratio=0.0,
            error="dry-run",
        )

    try:
        from services.style_distill_service import StyleDistillService

        svc = StyleDistillService(session)
        distilled = await svc.get_or_generate(
            creator_id=cid,
            source_doc_d=doc_d,
            prompt_version=prompt_version,
            force=force,
        )
        distilled_chars = len(distilled)
        ratio = distilled_chars / source_chars if source_chars else 0.0
        logger.info(
            "%s: %d → %d chars (%.0f%%)",
            nickname, source_chars, distilled_chars, ratio * 100,
        )
        return CreatorResult(
            creator_id=cid, nickname=nickname, status="ok",
            source_chars=source_chars,
            distilled_chars=distilled_chars,
            ratio=ratio,
        )
    except Exception as exc:
        logger.error("%s: distillation failed: %s", nickname, exc)
        return CreatorResult(
            creator_id=cid, nickname=nickname, status="error",
            source_chars=source_chars,
            error=str(exc),
        )


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="ARC3 — Batch distill creator Doc D into creator_style_distill cache."
    )
    parser.add_argument(
        "--creator-id",
        default=None,
        help="UUID of a single creator to distill. If absent, all active creators.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Regenerate distillation even if a cached row already exists.",
    )
    parser.add_argument(
        "--prompt-version",
        type=int,
        default=1,
        help="Distillation prompt version (default: 1).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Log what would be distilled without writing to DB.",
    )
    args = parser.parse_args()

    logger.info(
        "Starting distill_style_prompts: creator_id=%s force=%s version=%d dry_run=%s",
        args.creator_id or "all",
        args.force,
        args.prompt_version,
        args.dry_run,
    )

    session = _get_session()
    report = Report()

    try:
        creators = _fetch_active_creators(session, args.creator_id)
        if not creators:
            logger.warning("No active creators found (creator_id=%s)", args.creator_id)
            return

        logger.info("Found %d active creator(s) to process", len(creators))

        for creator in creators:
            t0 = time.monotonic()
            result = await _process_creator(
                session=session,
                creator=creator,
                prompt_version=args.prompt_version,
                force=args.force,
                dry_run=args.dry_run,
            )
            elapsed = time.monotonic() - t0
            report.add(result)
            logger.info(
                "[%s] %s in %.1fs", result.status.upper(), result.nickname, elapsed
            )

    except Exception as exc:
        logger.error("Fatal error: %s", exc)
        raise
    finally:
        session.close()

    print(report.summary())


if __name__ == "__main__":
    asyncio.run(main())
