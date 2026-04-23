"""
Bootstrap dialect_label / formality_label into tone_profiles.profile_data.

After PR #83 refactor, contextual_prefix.py reads human-readable labels
directly from the creator's tone_profile — no hardcoded translation dict.
Legacy creators have profile_data without these keys; this script populates
them idempotently.

Usage (from Railway or locally with a DB URL):
    railway run python3 scripts/bootstrap_tone_labels.py --dry-run
    railway run python3 scripts/bootstrap_tone_labels.py
    railway run python3 scripts/bootstrap_tone_labels.py --creator iris_bertran

Idempotency:
    - If dialect_label already set and non-empty → leave untouched (unless --force).
    - If formality_label already set and non-empty → leave untouched (unless --force).
    - If profile_data absent → creator skipped (nothing to patch onto).
    - All decisions logged before the UPDATE.

Post-run expected effect:
    core.contextual_prefix.build_contextual_prefix picks up the labels on the
    next prefix build (cache TTL 5 min; invoke /admin/contextual-prefix/
    invalidate/{creator_id} to force). New embeddings generated after that
    include the labels; old embeddings require a refresh-content job to pick
    up the change.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bootstrap_tone_labels")


# Per-creator curated labels. Strings are human-readable and will be emitted
# VERBATIM inside the contextual prefix, so phrasing matters. Add entries for
# new creators here as they onboard; or edit through the admin UI directly
# (this script is a convenience for the initial populate).
TONE_LABELS: Dict[str, Dict[str, str]] = {
    "iris_bertran": {
        "dialect_label": "en catalán y castellano coloquial",
        "formality_label": "con tono cercano y desenfadado",
    },
    "stefano_bonanno": {
        "dialect_label": "in italiano colloquiale",
        "formality_label": "con tono professionale e diretto",
    },
}


def _patch_profile_data(
    current: Optional[dict], new_labels: Dict[str, str], force: bool = False,
) -> tuple[Optional[dict], list[str]]:
    """Return (updated_profile_data, list_of_changes) or (None, []) if no change."""
    changes: list[str] = []
    if current is None:
        return None, changes
    patched = dict(current)  # shallow copy
    for key, value in new_labels.items():
        existing = patched.get(key) or ""
        if existing and not force:
            continue
        if existing == value:
            continue
        patched[key] = value
        changes.append(f"{key}: {existing!r} -> {value!r}")
    if not changes:
        return None, changes
    return patched, changes


def _run(creator_filter: Optional[str], dry_run: bool, force: bool) -> int:
    from api.database import get_db_session
    from sqlalchemy import text

    exit_code = 0
    with get_db_session() as db:
        for creator_name, labels in TONE_LABELS.items():
            if creator_filter and creator_name != creator_filter:
                continue

            # Join creators → tone_profiles by creator_id (UUID)
            row = db.execute(
                text("""
                    SELECT c.id, tp.id AS tone_id, tp.profile_data
                    FROM creators c
                    LEFT JOIN tone_profiles tp ON tp.creator_id = c.id
                    WHERE c.name = :name
                """),
                {"name": creator_name},
            ).fetchone()

            if not row:
                logger.warning("[%s] creator not found — skipping", creator_name)
                continue

            if row.tone_id is None:
                logger.warning(
                    "[%s] no tone_profiles row yet — skipping (run onboarding/tone_service first)",
                    creator_name,
                )
                continue

            profile_data = row.profile_data
            # Some drivers return JSONB as str, normalize
            if isinstance(profile_data, str):
                profile_data = json.loads(profile_data)

            patched, changes = _patch_profile_data(profile_data, labels, force=force)

            if patched is None:
                logger.info("[%s] already up-to-date — skipping", creator_name)
                continue

            logger.info("[%s] planned changes:", creator_name)
            for c in changes:
                logger.info("  - %s", c)

            if dry_run:
                logger.info("[%s] dry-run — no UPDATE issued", creator_name)
                continue

            db.execute(
                text("""
                    UPDATE tone_profiles
                    SET profile_data = CAST(:data AS jsonb),
                        updated_at = NOW()
                    WHERE id = :tone_id
                """),
                {"data": json.dumps(patched), "tone_id": str(row.tone_id)},
            )
            logger.info("[%s] UPDATE committed", creator_name)

        if not dry_run:
            db.commit()

    return exit_code


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--creator", default=None, help="Only process this creator name")
    p.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    p.add_argument("--force", action="store_true",
                   help="Overwrite existing labels (default is leave existing untouched)")
    args = p.parse_args()

    return _run(creator_filter=args.creator, dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
