"""
Build hierarchical memory system (IMPersona-style) for a creator.

3 levels:
  Level 1 (Episodic): per-conversation summaries
  Level 2 (Semantic): grouped by topic/period
  Level 3 (Abstract): recurring behavioral patterns

Usage:
    PYTHONPATH=. python scripts/build_memories.py --creator iris_bertran --level all
    PYTHONPATH=. python scripts/build_memories.py --creator iris_bertran --level 1
"""

import argparse
import json
import logging
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_persona_dir(creator: str) -> str:
    d = os.path.join(BASE_DIR, "data", "persona", creator.replace("_", "_"))
    os.makedirs(d, exist_ok=True)
    return d


def _load_calibration(creator: str) -> Optional[Dict]:
    path = os.path.join(BASE_DIR, "calibrations", f"{creator}.json")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _load_distilled_doc(creator: str) -> Optional[str]:
    path = os.path.join(BASE_DIR, "data", "personality_extractions", f"{creator}_v2_distilled.md")
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return None


# ── DB helpers ───────────────────────────────────────────────────────

def _get_db_session():
    from api.database import SessionLocal
    if SessionLocal is None:
        raise RuntimeError("Database not configured. Set DATABASE_URL env var.")
    return SessionLocal()


def _fetch_conversations(creator_name: str, limit: int = 200) -> List[Dict]:
    """Fetch recent conversations grouped by lead."""
    from sqlalchemy import text

    session = _get_db_session()
    try:
        q = text("""
            SELECT
                l.id as lead_id,
                COALESCE(l.full_name, l.username, l.platform_user_id) as lead_name,
                m.role,
                m.content,
                m.created_at,
                m.copilot_action
            FROM messages m
            JOIN leads l ON l.id = m.lead_id
            JOIN creators c ON c.id = l.creator_id
            WHERE c.name = :cname
              AND m.content IS NOT NULL
              AND LENGTH(m.content) > 1
              AND m.created_at >= NOW() - INTERVAL '6 months'
            ORDER BY l.id, m.created_at
        """)
        rows = session.execute(q, {"cname": creator_name}).fetchall()

        # Group by lead
        convos = defaultdict(lambda: {"lead_name": "", "messages": []})
        for row in rows:
            lid = str(row.lead_id)
            convos[lid]["lead_name"] = row.lead_name or "unknown"
            convos[lid]["messages"].append({
                "role": row.role,
                "content": row.content,
                "created_at": row.created_at.isoformat() if row.created_at else "",
                "copilot_action": row.copilot_action,
            })

        # Sort by most recent message, take top N
        sorted_convos = sorted(
            convos.values(),
            key=lambda c: c["messages"][-1]["created_at"] if c["messages"] else "",
            reverse=True,
        )
        return sorted_convos[:limit]
    finally:
        session.close()


# ── Level 1: Episodic memories ──────────────────────────────────────

_TOPIC_KEYWORDS = {
    "clase": re.compile(r'\b(barre|zumba|flow4u|pilates|reformer|clase|classe|entreno|horari)\b', re.I),
    "precio": re.compile(r'\b(preu|precio|euros?|€|\d+e\b|pagar|reservar|plaza)\b', re.I),
    "grabacion": re.compile(r'\b(gravar|grabar|video|reel|coreo|shooting|tripode)\b', re.I),
    "personal": re.compile(r'\b(familia|mare|pare|fill|hermano|mama|cumple|vacaciones|feina)\b', re.I),
    "salud": re.compile(r'\b(constipada|malament|vomit|dolor|hospital|medic|metge)\b', re.I),
    "saludo": re.compile(r'^(hola|bon dia|buenas|hey|ei)\b', re.I),
}


def _detect_topic(messages: List[Dict]) -> str:
    combined = " ".join(m["content"] for m in messages if m.get("content"))
    for topic, pattern in _TOPIC_KEYWORDS.items():
        if pattern.search(combined):
            return topic
    return "general"


def _extractive_summary(messages: List[Dict]) -> str:
    """Simple extractive summary: first user message + first creator response."""
    user_msgs = [m["content"] for m in messages if m["role"] == "user" and m.get("content")]
    asst_msgs = [m["content"] for m in messages if m["role"] == "assistant" and m.get("content") and not m.get("copilot_action")]

    user_part = user_msgs[0][:80] if user_msgs else "?"
    asst_part = asst_msgs[0][:80] if asst_msgs else "?"
    return f"Lead dice: '{user_part}' — Iris responde: '{asst_part}'"


def build_level1(creator: str, conversations: List[Dict]) -> List[Dict]:
    """Generate episodic memories from conversations."""
    memories = []

    for convo in conversations:
        msgs = convo["messages"]
        if len(msgs) < 2:
            continue

        lead_name = convo["lead_name"]
        dates = [m["created_at"] for m in msgs if m.get("created_at")]
        date_str = dates[0][:10] if dates else "unknown"
        topic = _detect_topic(msgs)
        summary = _extractive_summary(msgs)

        memories.append({
            "memory": summary,
            "lead_name": lead_name,
            "date": date_str,
            "topic": topic,
            "msg_count": len(msgs),
            "embedding": None,
        })

    logger.info("[Level 1] Generated %d episodic memories", len(memories))
    return memories


# ── Level 2: Semantic memories ──────────────────────────────────────

def build_level2(level1_memories: List[Dict]) -> List[Dict]:
    """Group level 1 memories by month + topic."""
    buckets = defaultdict(list)

    for mem in level1_memories:
        date_str = mem.get("date", "")
        month = date_str[:7] if len(date_str) >= 7 else "unknown"
        topic = mem.get("topic", "general")
        buckets[(month, topic)].append(mem)

    memories = []
    for (month, topic), mems in sorted(buckets.items(), key=lambda x: (-len(x[1]), x[0])):
        leads = list(set(m["lead_name"] for m in mems))
        lead_sample = ", ".join(leads[:3])
        if len(leads) > 3:
            lead_sample += f" (+{len(leads) - 3} mas)"

        memory_text = (
            f"En {month}, {len(mems)} conversaciones sobre '{topic}' "
            f"con leads: {lead_sample}."
        )

        memories.append({
            "memory": memory_text,
            "period": month,
            "topic": topic,
            "count": len(mems),
            "pattern": f"Tema '{topic}' es recurrente con {len(leads)} leads distintos",
        })

    logger.info("[Level 2] Generated %d semantic memories", len(memories))
    return memories


# ── Level 3: Abstract memories ──────────────────────────────────────

def build_level3(
    level1_memories: List[Dict],
    level2_memories: List[Dict],
    calibration: Optional[Dict],
    doc_d: Optional[str],
) -> List[Dict]:
    """Extract recurring behavioral patterns."""
    memories = []

    # Pattern 1: Topic distribution
    topic_counts = Counter(m["topic"] for m in level1_memories)
    total = sum(topic_counts.values())
    if total > 0:
        top_topics = topic_counts.most_common(3)
        topics_str = ", ".join(f"{t} ({c}/{total})" for t, c in top_topics)
        memories.append({
            "memory": f"Los temas mas frecuentes en conversaciones son: {topics_str}",
            "confidence": 0.9,
            "source_count": total,
            "type": "topic_distribution",
        })

    # Pattern 2: Response length (from calibration)
    if calibration:
        bl = calibration.get("baseline", {})
        memories.append({
            "memory": (
                f"Iris responde con mensajes muy cortos: mediana {bl.get('median_length', '?')} chars, "
                f"maximo habitual {bl.get('soft_max', '?')} chars. "
                f"Usa emojis en {bl.get('emoji_pct', '?')}% de mensajes."
            ),
            "confidence": 0.95,
            "source_count": calibration.get("few_shot_examples", []).__len__(),
            "type": "response_style",
        })

    # Pattern 3: Language patterns (from calibration)
    if calibration:
        vocab = calibration.get("creator_vocabulary", [])
        if vocab:
            sample = ", ".join(vocab[:10])
            memories.append({
                "memory": (
                    f"Vocabulario distintivo de Iris incluye: {sample}. "
                    "Usa code-switching ca/es natural mid-sentence."
                ),
                "confidence": 0.9,
                "source_count": len(vocab),
                "type": "language_pattern",
            })

    # Pattern 4: Relationship patterns
    friend_count = sum(1 for m in level1_memories if m["topic"] == "personal")
    class_count = sum(1 for m in level1_memories if m["topic"] == "clase")
    if total > 0:
        memories.append({
            "memory": (
                f"Iris divide su tiempo entre conversaciones personales ({friend_count}/{total}) "
                f"y gestion de clases ({class_count}/{total}). "
                "Con amigos es ultra-breve y en catalan. Con leads es calida pero directa."
            ),
            "confidence": 0.85,
            "source_count": total,
            "type": "relationship_pattern",
        })

    # Pattern 5: Temporal patterns
    months = Counter(m["date"][:7] for m in level1_memories if len(m.get("date", "")) >= 7)
    if months:
        busiest = months.most_common(1)[0]
        memories.append({
            "memory": f"Mes con mas actividad: {busiest[0]} ({busiest[1]} conversaciones).",
            "confidence": 0.8,
            "source_count": sum(months.values()),
            "type": "temporal_pattern",
        })

    # Pattern 6: From Doc D if available
    if doc_d:
        memories.append({
            "memory": (
                "Iris NUNCA suena como asistente virtual. Responde como persona ocupada entre clases. "
                "Frases prohibidas: 'en que puedo ayudarte', 'no dudes en', 'estoy aqui para'. "
                "Siempre tuteo, nunca usted/voseo."
            ),
            "confidence": 1.0,
            "source_count": 30,
            "type": "identity_constraint",
        })

    logger.info("[Level 3] Generated %d abstract memories", len(memories))
    return memories


# ── Save/Load ────────────────────────────────────────────────────────

def _save_memories(memories: List[Dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        for mem in memories:
            f.write(json.dumps(mem, ensure_ascii=False, default=str) + "\n")
    logger.info("  Saved %d memories -> %s", len(memories), path)


# ── Main ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Build IMPersona-style hierarchical memories for a creator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  PYTHONPATH=. python scripts/build_memories.py --creator iris_bertran --level all
  PYTHONPATH=. python scripts/build_memories.py --creator iris_bertran --level 1 --limit 50
  PYTHONPATH=. python scripts/build_memories.py --creator iris_bertran --level 3

Levels:
  1 = Episodic (per-conversation summaries)
  2 = Semantic (grouped by topic/period)
  3 = Abstract (recurring behavioral patterns)
  all = Generate all 3 levels
        """,
    )
    parser.add_argument("--creator", required=True, help="Creator username (e.g. iris_bertran)")
    parser.add_argument("--level", required=True, choices=["1", "2", "3", "all"], help="Memory level to build")
    parser.add_argument("--limit", type=int, default=200, help="Max conversations to fetch (default 200)")
    args = parser.parse_args()

    levels = ["1", "2", "3"] if args.level == "all" else [args.level]
    persona_dir = _get_persona_dir(args.creator)
    calibration = _load_calibration(args.creator)
    doc_d = _load_distilled_doc(args.creator)

    logger.info("Building memories for: %s", args.creator)
    logger.info("Output dir: %s", persona_dir)

    # Level 1 is needed for levels 2 and 3
    l1_path = os.path.join(persona_dir, "memories_level1.jsonl")
    level1_memories = []

    if "1" in levels or "2" in levels or "3" in levels:
        # Check if level 1 already exists (reuse for level 2/3)
        if "1" not in levels and os.path.isfile(l1_path):
            logger.info("Loading existing level 1 from %s", l1_path)
            with open(l1_path, "r", encoding="utf-8") as f:
                level1_memories = [json.loads(line) for line in f if line.strip()]
        else:
            logger.info("Fetching conversations from DB (limit=%d)...", args.limit)
            conversations = _fetch_conversations(args.creator, limit=args.limit)
            logger.info("Fetched %d conversations", len(conversations))
            level1_memories = build_level1(args.creator, conversations)

    if "1" in levels:
        _save_memories(level1_memories, l1_path)

    if "2" in levels:
        level2_memories = build_level2(level1_memories)
        _save_memories(level2_memories, os.path.join(persona_dir, "memories_level2.jsonl"))

    if "3" in levels:
        l2_path = os.path.join(persona_dir, "memories_level2.jsonl")
        level2_memories = []
        if os.path.isfile(l2_path):
            with open(l2_path, "r", encoding="utf-8") as f:
                level2_memories = [json.loads(line) for line in f if line.strip()]
        level3_memories = build_level3(level1_memories, level2_memories, calibration, doc_d)
        _save_memories(level3_memories, os.path.join(persona_dir, "memories_level3.jsonl"))

    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("MEMORY SUMMARY")
    logger.info("=" * 50)
    for lvl in ["1", "2", "3"]:
        path = os.path.join(persona_dir, f"memories_level{lvl}.jsonl")
        if os.path.isfile(path):
            count = sum(1 for _ in open(path))
            logger.info("  Level %s: %d memories", lvl, count)
        else:
            logger.info("  Level %s: not generated", lvl)
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
