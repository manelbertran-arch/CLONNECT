"""
CPE Test Set Generator — Universal, data-driven.

Generates evaluation test sets from a creator's real conversations.
Works for ANY creator without code changes.

Usage:
    python scripts/cpe_generate_test_set.py --creator iris_bertran --n 50
    python scripts/cpe_generate_test_set.py --creator stefano_bonanno --n 30

Output: tests/cpe_data/{creator}/test_set.json
"""

import argparse
import json
import os
import random
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── Universal message classifier (no language-specific keywords) ──────

def _classify_structural(content: str) -> str:
    """Classify a user message by structural signals. Universal."""
    if not content or len(content.strip()) < 2:
        return "empty"
    c = content.strip()
    cl = c.lower()

    if c.startswith("[audio") or c.startswith("[Audio") or c.startswith("[🎤"):
        return "audio"
    if re.match(r'^[\U0001f000-\U0001ffff\u2600-\u27bf\u2764\ufe0f\s]+$', c):
        return "emoji_reaction"
    if re.search(r'[€$£¥]|\d+\s*(eur|usd|gbp)', cl):
        return "product_inquiry"
    if re.match(r'^(hol[ae]|hey|hi|bon\s*dia|buen[ao]s|ey|ei|hello|ciao)', cl) and len(c) <= 25:
        return "greeting"
    if re.search(r'graci|merci|thanks|gràci', cl):
        return "thanks"
    if re.search(r'bye|adeu|nanit|adi[oó]s|bona\s*nit', cl):
        return "farewell"
    if re.search(r'[jh]a[jh]a|😂|🤣', cl) and len(c) < 40:
        return "humor"
    if re.search(r'no\s+(puc|puedo|tinc|tengo)|car[oa]|pensar|tiempo|temps', cl):
        return "objection"
    if re.search(r'reserv|apunt|book|inscri', cl):
        return "booking"
    if "?" in c and len(c) > 15:
        return "question"
    if len(c) <= 12 and "?" not in c:
        return "short_response"
    if len(c) > 80:
        return "long_personal"
    return "casual"


def _detect_language(text: str) -> str:
    """Detect language. Returns ISO code or 'mixed'."""
    try:
        from langdetect import detect, DetectorFactory
        DetectorFactory.seed = 0

        ca_markers = re.compile(r'\b(tinc|estic|però|molt|doncs|també|gràcies|gracies|bon dia)\b')
        es_markers = re.compile(r'\b(tengo|estoy|pero|mucho|gracias|bueno|vale)\b')

        lower = text.lower()
        ca = len(ca_markers.findall(lower))
        es = len(es_markers.findall(lower))

        if ca > 0 and es > 0:
            return "mixed"
        if ca > 0:
            return "ca"
        return detect(text)
    except Exception:
        return "unknown"


def _detect_platform(lead_username: str) -> str:
    """Detect platform from username pattern."""
    if lead_username and lead_username.startswith("wa_"):
        return "whatsapp"
    return "instagram"


def generate_test_set(creator_slug: str, n: int = 50, db_url: str = None):
    """Generate a test set from a creator's real conversations."""
    from sqlalchemy import create_engine, text

    db_url = db_url or os.environ.get("DATABASE_URL", "")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    if "sslmode" not in db_url:
        db_url += ("&" if "?" in db_url else "?") + "sslmode=require"

    engine = create_engine(db_url, pool_pre_ping=True, connect_args={"connect_timeout": 30})

    with engine.connect() as conn:
        # Get creator UUID
        creator = conn.execute(text(
            "SELECT id, name FROM creators WHERE name = :slug LIMIT 1"
        ), {"slug": creator_slug}).fetchone()
        if not creator:
            print(f"ERROR: Creator '{creator_slug}' not found")
            sys.exit(1)

        creator_id = str(creator.id)
        print(f"Creator: {creator.name} ({creator_id})")

        # Fetch candidate pairs: user message + next creator response
        # Only manual responses (copilot_action IS NULL or manual_override)
        # From the last 3 months, with content > 10 chars
        pairs = conn.execute(text("""
            WITH ordered AS (
                SELECT
                    m.id, m.lead_id, m.role, m.content, m.copilot_action,
                    m.created_at, l.username, l.platform,
                    LAG(m.content) OVER (PARTITION BY m.lead_id ORDER BY m.created_at) AS prev_content,
                    LAG(m.role) OVER (PARTITION BY m.lead_id ORDER BY m.created_at) AS prev_role,
                    LAG(m.created_at) OVER (PARTITION BY m.lead_id ORDER BY m.created_at) AS prev_at
                FROM messages m
                JOIN leads l ON l.id = m.lead_id
                WHERE l.creator_id = :cid
                  AND m.deleted_at IS NULL
                  AND m.content IS NOT NULL
                  AND length(m.content) > 5
                  AND m.created_at > NOW() - INTERVAL '3 months'
            )
            SELECT id, lead_id, content, copilot_action, created_at,
                   username, platform, prev_content, prev_role, prev_at
            FROM ordered
            WHERE role = 'assistant'
              AND prev_role = 'user'
              AND prev_content IS NOT NULL
              AND length(prev_content) > 5
              AND length(content) > 3
              AND (copilot_action IS NULL OR copilot_action = 'manual_override')
            ORDER BY created_at DESC
            LIMIT :limit
        """), {"cid": creator_id, "limit": n * 5}).fetchall()

        print(f"Candidate pairs: {len(pairs)}")
        if len(pairs) == 0:
            print("ERROR: No pairs found. Check creator has conversations.")
            sys.exit(1)

        # Classify and group by category
        by_category = defaultdict(list)
        for p in pairs:
            cat = _classify_structural(p.prev_content)
            if cat == "empty":
                continue
            by_category[cat].append(p)

        total = sum(len(v) for v in by_category.values())
        print(f"\nCategories found ({len(by_category)}):")
        for cat, items in sorted(by_category.items(), key=lambda x: -len(x[1])):
            pct = len(items) / total * 100
            print(f"  {cat:18s}: {len(items):4d} ({pct:.0f}%)")

        # Select proportionally
        selected = []
        for cat, items in by_category.items():
            proportion = len(items) / total
            n_select = max(1, round(n * proportion))
            n_select = min(n_select, len(items))
            picks = random.sample(items, n_select)
            selected.extend([(cat, p) for p in picks])

        # Trim to n
        random.shuffle(selected)
        selected = selected[:n]

        print(f"\nSelected {len(selected)} test cases")

        # Build test cases with history
        test_cases = []
        for idx, (cat, pair) in enumerate(selected):
            # Get conversation history (up to 8 turns before this pair)
            history = conn.execute(text("""
                SELECT role, content FROM messages
                WHERE lead_id = :lid
                  AND deleted_at IS NULL
                  AND content IS NOT NULL
                  AND length(content) > 1
                  AND created_at < :before
                ORDER BY created_at DESC
                LIMIT 8
            """), {"lid": pair.lead_id, "before": pair.prev_at}).fetchall()

            turns = [{"role": h.role, "content": h.content[:300]} for h in reversed(history)]

            lang = _detect_language(pair.prev_content)
            platform = _detect_platform(pair.username) if pair.username else (pair.platform or "unknown")

            test_cases.append({
                "id": f"cpe_{creator_slug[:6]}_{idx+1:03d}",
                "test_input": pair.prev_content.strip(),
                "ground_truth": pair.content.strip(),
                "category": cat,
                "language": lang,
                "platform": platform,
                "lead_username": pair.username or "unknown",
                "turns": turns,
                "msg_count": len(turns),
                "creator_id": creator_slug,
                "source_msg_id": str(pair.id),
                "timestamp": pair.created_at.isoformat() if pair.created_at else None,
            })

    # Final category distribution
    cat_dist = defaultdict(int)
    lang_dist = defaultdict(int)
    for tc in test_cases:
        cat_dist[tc["category"]] += 1
        lang_dist[tc["language"]] += 1

    print(f"\nFinal distribution ({len(test_cases)} cases):")
    print("  By category:")
    for cat, count in sorted(cat_dist.items(), key=lambda x: -x[1]):
        print(f"    {cat:18s}: {count}")
    print("  By language:")
    for lang, count in sorted(lang_dist.items(), key=lambda x: -x[1]):
        print(f"    {lang:6s}: {count}")

    # Save
    output_dir = Path(__file__).parent.parent / "tests" / "cpe_data" / creator_slug
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "test_set.json"

    output = {
        "metadata": {
            "creator": creator_slug,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "n_cases": len(test_cases),
            "period": "last 3 months",
            "category_distribution": dict(cat_dist),
            "language_distribution": dict(lang_dist),
            "generator": "cpe_generate_test_set.py",
        },
        "conversations": test_cases,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to {output_path}")
    return output


def main():
    parser = argparse.ArgumentParser(description="Generate CPE test set")
    parser.add_argument("--creator", required=True, help="Creator slug (e.g., iris_bertran)")
    parser.add_argument("--n", type=int, default=50, help="Number of test cases (default: 50)")
    args = parser.parse_args()

    generate_test_set(args.creator, args.n)


if __name__ == "__main__":
    main()
