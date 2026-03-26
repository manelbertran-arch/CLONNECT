"""
Bootstrap vocab_metadata entries in personality_docs from on-disk doc_d files.

Reads existing doc_d_bot_configuration.md and *_distilled.md files, extracts
structured vocabulary (blacklist_words, blacklist_emojis, approved_terms,
approved_emojis) and upserts a 'vocab_meta' JSON row in personality_docs.

Once in the DB, _load_creator_vocab() can serve it to Railway production where
the data/ dir is gitignored and absent.

Run:
    railway run python3 scripts/bootstrap_vocab_metadata.py
    railway run python3 scripts/bootstrap_vocab_metadata.py --dry-run
    railway run python3 scripts/bootstrap_vocab_metadata.py --creator iris_bertran
"""
import argparse
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _parse_vocab_from_file(path: Path) -> dict:
    """Parse vocabulary from a doc_d file using calibration_loader logic."""
    import services.calibration_loader as cl
    cl._vocab_cache.clear()
    old_paths = None

    # Temporarily monkey-patch to force reading this specific file
    content = path.read_text(encoding="utf-8")

    import re as _re

    def _dedup(lst):
        seen = set()
        return [x for x in lst if x and not (x in seen or seen.add(x))]

    _EMOJI_RE = _re.compile(
        r"[\U0001F300-\U0001FAFF\u2600-\u27BF][\U0001F3FB-\U0001F3FF\uFE0F]?"
    )
    _SKIN_TONE_RE = _re.compile(r"^[\U0001F3FB-\U0001F3FF]$")

    # 1. blacklist_words: "NO usa: X, Y, Z"
    blacklist_words = []
    for m in _re.finditer(r"NO\s+usa:\s*([^\n.]+)", content, _re.IGNORECASE):
        raw = _re.sub(r"\([^)]*\)", "", m.group(1))
        for part in _re.split(r"[,;/]", raw):
            term = part.strip().strip('"').strip("'").strip()
            if 2 <= len(term) <= 30:
                blacklist_words.append(term.lower())

    # 2. approved_terms: "SÍ usa: X, Y, Z"
    approved_terms = []
    for m in _re.finditer(r"SÍ\s+usa:\s*([^\n]+)", content, _re.IGNORECASE):
        raw = _re.sub(r"\([^)]*\)", "", m.group(1))
        for part in _re.split(r"[,;]", raw):
            term = part.strip().strip('"').strip("'").strip()
            if 2 <= len(term) <= 20:
                approved_terms.append(term.lower())

    # 3. blacklist_emojis: "NUNCA uses: ..."
    blacklist_emojis = []
    for m in _re.finditer(r"NUNCA\s+uses?:\s*([^\n\(]+)", content, _re.IGNORECASE):
        blacklist_emojis.extend(
            e for e in _EMOJI_RE.findall(m.group(1)) if not _SKIN_TONE_RE.match(e)
        )

    # 4. approved_emojis: "Top emojis: ..."
    approved_emojis = []
    for m in _re.finditer(r"Top emojis[^:]*:\s*([^\n]+)", content, _re.IGNORECASE):
        approved_emojis.extend(
            e for e in _EMOJI_RE.findall(m.group(1)) if not _SKIN_TONE_RE.match(e)
        )

    # 5. blacklist_phrases: §4.2 BLACKLIST quoted phrases
    blacklist_phrases = []
    in_blacklist = False
    for line in content.splitlines():
        if "4.2" in line or "BLACKLIST" in line.upper():
            in_blacklist = True
        elif line.startswith("## ") and in_blacklist:
            in_blacklist = False
        if in_blacklist:
            for m in _re.finditer(r'"([^"]{4,60})"', line):
                phrase = m.group(1).strip().lower()
                if phrase:
                    blacklist_phrases.append(phrase)

    return {
        "blacklist_words": _dedup(blacklist_words),
        "blacklist_emojis": _dedup(blacklist_emojis),
        "approved_terms": _dedup(approved_terms),
        "approved_emojis": _dedup(approved_emojis),
        "blacklist_phrases": _dedup(blacklist_phrases),
    }


def _collect_creators(creator_filter: str | None) -> dict[str, Path]:
    """Return {slug: best_doc_d_path} for creators with on-disk vocabulary files."""
    extractions_dir = ROOT / "data" / "personality_extractions"
    creators: dict[str, Path] = {}

    if extractions_dir.exists():
        # Directory-style: iris_bertran/doc_d_bot_configuration.md
        for p in sorted(extractions_dir.glob("*/doc_d_bot_configuration.md")):
            slug = p.parent.name
            try:
                uuid.UUID(slug)
                continue  # UUID dir — no vocab here
            except ValueError:
                creators[slug] = p

        # File-style: iris_bertran_v2_distilled.md (prefer over plain distilled)
        # Process most-specific suffix first; skip files already processed.
        _seen_files: set = set()
        for suffix in ["_v2_distilled.md", "_distilled.md"]:
            for p in sorted(extractions_dir.glob(f"*{suffix}")):
                if p in _seen_files:
                    continue
                _seen_files.add(p)
                slug = p.stem[: -len(suffix.removesuffix(".md"))]
                if slug and slug not in creators:
                    creators[slug] = p

    if creator_filter:
        creators = {k: v for k, v in creators.items() if k == creator_filter}

    return creators


def bootstrap(dry_run: bool, creator_filter: str | None) -> None:
    from api.database import SessionLocal
    from sqlalchemy import text

    creators = _collect_creators(creator_filter)
    if not creators:
        print("No on-disk doc_d files found.")
        return

    print(f"Found {len(creators)} creator(s): {list(creators.keys())}\n")

    s = SessionLocal()
    try:
        for slug, path in creators.items():
            print(f"[{slug}] Parsing {path.name}...")
            vocab = _parse_vocab_from_file(path)

            if not vocab.get("blacklist_words") and not vocab.get("approved_terms"):
                print(f"  (no vocabulary data found, skipping)\n")
                continue

            print(f"  blacklist_words:  {vocab['blacklist_words']}")
            print(f"  blacklist_emojis: {vocab['blacklist_emojis']}")
            print(f"  approved_terms:   {vocab['approved_terms']}")
            print(f"  approved_emojis:  {vocab['approved_emojis']}")
            print(f"  blacklist_phrases: {len(vocab['blacklist_phrases'])} entries")

            if dry_run:
                print(f"  [DRY RUN] Would upsert vocab_metadata for {slug}\n")
                continue

            # Resolve creator UUID
            row = s.execute(
                text("SELECT id FROM creators WHERE name = :name LIMIT 1"),
                {"name": slug},
            ).fetchone()
            if not row:
                print(f"  [SKIP] Creator '{slug}' not found in creators table\n")
                continue

            creator_uuid = str(row.id)
            content_json = json.dumps(vocab, ensure_ascii=False, indent=2)

            existing = s.execute(
                text(
                    "SELECT id FROM personality_docs "
                    "WHERE creator_id = :cid AND doc_type = 'vocab_meta' LIMIT 1"
                ),
                {"cid": creator_uuid},
            ).fetchone()

            if existing:
                s.execute(
                    text(
                        "UPDATE personality_docs SET content = :content, updated_at = NOW() "
                        "WHERE id = :id"
                    ),
                    {"content": content_json, "id": existing.id},
                )
                print(f"  ✓ Updated vocab_metadata (id={existing.id})\n")
            else:
                s.execute(
                    text(
                        "INSERT INTO personality_docs (id, creator_id, doc_type, content, created_at, updated_at) "
                        "VALUES (gen_random_uuid(), :cid, 'vocab_meta', :content, NOW(), NOW())"
                    ),
                    {"cid": creator_uuid, "content": content_json},
                )
                print(f"  ✓ Inserted new vocab_metadata for {slug}\n")

            s.commit()

        print("Done.")
        if dry_run:
            print("(DRY RUN — no writes performed)")
    finally:
        s.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bootstrap vocab_metadata in personality_docs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--creator", default=None)
    args = parser.parse_args()

    print("=" * 60)
    print("Vocab Metadata Bootstrap")
    print("=" * 60)
    if args.dry_run:
        print("MODE: DRY RUN")
    else:
        print("MODE: APPLY")
    print()

    bootstrap(dry_run=args.dry_run, creator_filter=args.creator)
