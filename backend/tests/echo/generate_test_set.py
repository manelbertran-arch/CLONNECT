"""
Test Set Generator for ECHO Engine.

Extracts real creator conversations from the database and generates
stratified test sets for CloneScore evaluation.

Usage:
    # Generate from DB (requires DATABASE_URL)
    python -m tests.echo.generate_test_set --creator stefano --output tests/echo/test_sets/stefano_v1.json

    # Generate with limits
    python -m tests.echo.generate_test_set --creator stefano --min-pairs 100 --max-pairs 200

    # Dry run (show stats without writing)
    python -m tests.echo.generate_test_set --creator stefano --dry-run
"""
import os
import sys
import json
import re
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MIN_CONVERSATION_LENGTH = 3  # Exclude convos with < 3 messages
MIN_RESPONSE_LENGTH = 10     # Exclude very short creator responses (chars)
MAX_RESPONSE_LENGTH = 500    # Cap for very long responses
HISTORY_WINDOW = 10          # Max messages of history per test case

# Stratification targets (percentages)
STRATIFICATION = {
    "lead_category": {
        "nuevo": 0.25,
        "interesado": 0.30,
        "caliente": 0.20,
        "cliente": 0.15,
        "fantasma": 0.10,
    },
    "topic": {
        "ventas": 0.40,
        "soporte": 0.15,
        "casual": 0.20,
        "contenido": 0.15,
        "otro": 0.10,
    },
}

# Intent-to-topic mapping
INTENT_TOPIC_MAP = {
    "purchase": "ventas",
    "pricing": "ventas",
    "info": "ventas",
    "interest": "ventas",
    "booking": "ventas",
    "help": "soporte",
    "complaint": "soporte",
    "support": "soporte",
    "greeting": "casual",
    "farewell": "casual",
    "personal": "casual",
    "content": "contenido",
    "media": "contenido",
}


# ---------------------------------------------------------------------------
# Topic classifier (rule-based fallback when intent is NULL)
# ---------------------------------------------------------------------------

TOPIC_PATTERNS = {
    "ventas": [
        r"(?:cuanto|cu[aá]nto)\s+cuesta",
        r"precio",
        r"comprar",
        r"pagar",
        r"descuento",
        r"oferta",
        r"curso",
        r"plan\s+personalizado",
        r"inscrib",
        r"apuntar",
    ],
    "soporte": [
        r"no\s+(?:puedo|funciona|carga)",
        r"error",
        r"problema",
        r"ayuda",
        r"acceso",
        r"no\s+me\s+deja",
    ],
    "contenido": [
        r"video",
        r"post",
        r"reel",
        r"story",
        r"contenido",
        r"receta",
        r"consejo",
    ],
    "casual": [
        r"hola",
        r"buenas",
        r"que\s+tal",
        r"como\s+(?:estas|andas|va)",
        r"jaja",
        r"gracias",
    ],
}


def classify_topic(message: str, intent: str | None = None) -> str:
    """Classify a message into a topic category."""
    if intent and intent in INTENT_TOPIC_MAP:
        return INTENT_TOPIC_MAP[intent]

    text = message.lower()
    topic_scores: dict[str, int] = defaultdict(int)

    for topic, patterns in TOPIC_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text):
                topic_scores[topic] += 1

    if topic_scores:
        return max(topic_scores, key=topic_scores.get)
    return "otro"


def has_media_content(message_content: str, metadata: dict | None = None) -> bool:
    """Check if a message contains media references."""
    if metadata:
        msg_type = metadata.get("type", "")
        if msg_type in ("image", "video", "audio", "story_mention", "story_reply"):
            return True
    indicators = ["[audio transcrito]", "[imagen]", "[video]", "[sticker]"]
    return any(ind in message_content.lower() for ind in indicators)


def detect_language_style(text: str) -> str:
    """Detect language formality style."""
    informal_markers = [
        "jaja", "jeje", "xq", "tb", "bro", "tio", "crack", "nah",
        "vamos", "dale", "ey", "buenisimo", "pasada",
    ]
    formal_markers = [
        "usted", "estimado", "cordialmente", "atentamente",
        "le informo", "a su disposicion",
    ]

    lower = text.lower()
    informal_count = sum(1 for m in informal_markers if m in lower)
    formal_count = sum(1 for m in formal_markers if m in lower)

    if formal_count > informal_count:
        return "es_formal"
    return "es_informal"


# ---------------------------------------------------------------------------
# Database extraction
# ---------------------------------------------------------------------------

def get_db_session():
    """Get a database session. Requires DATABASE_URL env var."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise EnvironmentError(
            "DATABASE_URL not set. Set it to extract real conversations."
        )

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(database_url)
    Session = sessionmaker(bind=engine)
    return Session()


def resolve_creator_id(session, creator_name: str) -> str:
    """Resolve creator name to UUID."""
    from api.models import Creator

    creator = (
        session.query(Creator)
        .filter(Creator.name.ilike(f"%{creator_name}%"))
        .first()
    )
    if not creator:
        raise ValueError(f"Creator '{creator_name}' not found in database")
    return str(creator.id)


def extract_conversations(session, creator_id: str, limit: int = 500) -> list[dict]:
    """
    Extract real conversations from the database.

    Returns list of conversation groups, each with:
    - lead info (id, status, username)
    - ordered messages (role, content, intent, created_at)
    """
    from api.models import Lead, Message
    from sqlalchemy import func

    # Get leads with sufficient conversation history
    leads_with_messages = (
        session.query(
            Lead.id,
            Lead.status,
            Lead.username,
            Lead.platform,
            Lead.score,
            func.count(Message.id).label("msg_count"),
        )
        .join(Message, Message.lead_id == Lead.id)
        .filter(Lead.creator_id == creator_id)
        .filter(Message.content.isnot(None))
        .filter(Message.content != "")
        .group_by(Lead.id)
        .having(func.count(Message.id) >= MIN_CONVERSATION_LENGTH)
        .order_by(func.count(Message.id).desc())
        .limit(limit)
        .all()
    )

    conversations = []
    for lead_row in leads_with_messages:
        lead_id = str(lead_row.id)

        messages = (
            session.query(Message)
            .filter(Message.lead_id == lead_row.id)
            .filter(Message.content.isnot(None))
            .filter(Message.content != "")
            .order_by(Message.created_at.asc())
            .all()
        )

        msg_list = []
        for msg in messages:
            msg_list.append({
                "role": msg.role,
                "content": msg.content,
                "intent": getattr(msg, "intent", None),
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
                "metadata": getattr(msg, "msg_metadata", None) or {},
            })

        conversations.append({
            "lead_id": lead_id,
            "lead_status": lead_row.status or "nuevo",
            "lead_username": lead_row.username,
            "lead_platform": lead_row.platform,
            "lead_score": lead_row.score,
            "messages": msg_list,
            "message_count": len(msg_list),
        })

    logger.info(
        f"Extracted {len(conversations)} conversations "
        f"({sum(c['message_count'] for c in conversations)} total messages)"
    )
    return conversations


# ---------------------------------------------------------------------------
# Test pair generation
# ---------------------------------------------------------------------------

def generate_test_pairs(conversations: list[dict]) -> list[dict]:
    """
    Generate test pairs from conversations.

    For each conversation, find user→assistant exchanges and create test pairs
    using the assistant's real response as the ground truth.
    """
    pairs = []
    pair_id = 0

    for conv in conversations:
        msgs = conv["messages"]
        for i, msg in enumerate(msgs):
            # Look for assistant responses to user messages
            if msg["role"] != "assistant":
                continue
            if i == 0:
                continue  # Skip if no preceding user message

            # Find the preceding user message
            prev_user_msg = None
            for j in range(i - 1, -1, -1):
                if msgs[j]["role"] == "user":
                    prev_user_msg = msgs[j]
                    break

            if not prev_user_msg:
                continue

            real_response = msg["content"].strip()

            # Apply filters
            if len(real_response) < MIN_RESPONSE_LENGTH:
                continue
            if len(real_response) > MAX_RESPONSE_LENGTH:
                continue

            follower_message = prev_user_msg["content"].strip()
            if not follower_message:
                continue

            # Skip media-only messages (no text)
            if has_media_content(follower_message) and len(follower_message) < 20:
                continue

            # Build conversation history (up to HISTORY_WINDOW messages before this exchange)
            history_start = max(0, i - HISTORY_WINDOW)
            history = []
            for h in range(history_start, i):
                history.append({
                    "role": msgs[h]["role"],
                    "content": msgs[h]["content"],
                })

            # Classify topic
            topic = classify_topic(
                follower_message,
                intent=prev_user_msg.get("intent"),
            )

            # Detect style
            language = detect_language_style(real_response)

            pair_id += 1
            pairs.append({
                "id": f"test_{pair_id:04d}",
                "context": _generate_context_description(
                    conv["lead_status"], topic, follower_message
                ),
                "conversation_history": history,
                "lead_category": conv["lead_status"],
                "lead_id": conv["lead_id"],
                "real_response": real_response,
                "follower_message": follower_message,
                "metadata": {
                    "topic": topic,
                    "has_media": has_media_content(
                        follower_message, prev_user_msg.get("metadata")
                    ),
                    "language": language,
                    "lead_username": conv.get("lead_username"),
                    "lead_score": conv.get("lead_score"),
                    "original_intent": prev_user_msg.get("intent"),
                    "response_length": len(real_response),
                },
            })

    logger.info(f"Generated {len(pairs)} test pairs from {len(conversations)} conversations")
    return pairs


def _generate_context_description(lead_status: str, topic: str, message: str) -> str:
    """Generate a human-readable context description."""
    status_labels = {
        "nuevo": "Lead NUEVO",
        "interesado": "Lead INTERESADO",
        "caliente": "Lead CALIENTE",
        "cliente": "CLIENTE",
        "fantasma": "Lead FANTASMA",
    }
    topic_labels = {
        "ventas": "consulta comercial",
        "soporte": "pide soporte",
        "casual": "conversacion casual",
        "contenido": "pregunta sobre contenido",
        "otro": "mensaje general",
    }

    status_label = status_labels.get(lead_status, f"Lead {lead_status.upper()}")
    topic_label = topic_labels.get(topic, topic)

    # Truncate message for description
    short_msg = message[:60] + "..." if len(message) > 60 else message
    return f"{status_label} — {topic_label}: \"{short_msg}\""


# ---------------------------------------------------------------------------
# Stratified sampling
# ---------------------------------------------------------------------------

def stratified_sample(
    pairs: list[dict],
    target_count: int = 100,
    stratification: dict | None = None,
) -> list[dict]:
    """
    Sample test pairs with stratification by lead_category and topic.

    Tries to match target distribution but fills with available data.
    """
    if stratification is None:
        stratification = STRATIFICATION

    if len(pairs) <= target_count:
        logger.warning(
            f"Only {len(pairs)} pairs available, less than target {target_count}"
        )
        return pairs

    # Group by lead_category
    by_category: dict[str, list] = defaultdict(list)
    for pair in pairs:
        by_category[pair["lead_category"]].append(pair)

    selected = []
    remaining = []
    category_targets = stratification.get("lead_category", {})

    for category, target_pct in category_targets.items():
        category_target = int(target_count * target_pct)
        available = by_category.get(category, [])

        if len(available) <= category_target:
            selected.extend(available)
        else:
            # Further stratify by topic within this category
            by_topic: dict[str, list] = defaultdict(list)
            for p in available:
                by_topic[p["metadata"]["topic"]].append(p)

            topic_targets = stratification.get("topic", {})
            category_selected = []
            for topic, topic_pct in topic_targets.items():
                topic_target = max(1, int(category_target * topic_pct))
                topic_available = by_topic.get(topic, [])
                category_selected.extend(topic_available[:topic_target])

            # Fill remaining from unselected
            selected_ids = {p["id"] for p in category_selected}
            unselected = [p for p in available if p["id"] not in selected_ids]

            while len(category_selected) < category_target and unselected:
                category_selected.append(unselected.pop(0))

            selected.extend(category_selected[:category_target])
            remaining.extend(
                [p for p in available if p["id"] not in {s["id"] for s in selected}]
            )

    # Fill to target with remaining pairs
    selected_ids = {p["id"] for p in selected}
    fill_pool = [p for p in pairs if p["id"] not in selected_ids]
    while len(selected) < target_count and fill_pool:
        selected.append(fill_pool.pop(0))

    logger.info(f"Stratified sample: {len(selected)} pairs selected")
    return selected


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def compute_stats(pairs: list[dict]) -> dict:
    """Compute statistics about the test set."""
    if not pairs:
        return {"total": 0}

    categories = Counter(p["lead_category"] for p in pairs)
    topics = Counter(p["metadata"]["topic"] for p in pairs)
    languages = Counter(p["metadata"]["language"] for p in pairs)
    media_count = sum(1 for p in pairs if p["metadata"]["has_media"])

    response_lengths = [p["metadata"].get("response_length", len(p["real_response"])) for p in pairs]
    history_lengths = [len(p["conversation_history"]) for p in pairs]

    return {
        "total": len(pairs),
        "by_category": dict(categories),
        "by_topic": dict(topics),
        "by_language": dict(languages),
        "media_count": media_count,
        "avg_response_length": sum(response_lengths) / len(response_lengths),
        "min_response_length": min(response_lengths),
        "max_response_length": max(response_lengths),
        "avg_history_length": sum(history_lengths) / len(history_lengths),
        "category_distribution": {
            k: round(v / len(pairs), 2) for k, v in categories.items()
        },
        "topic_distribution": {
            k: round(v / len(pairs), 2) for k, v in topics.items()
        },
    }


def print_stats(stats: dict) -> None:
    """Print test set statistics in a readable format."""
    print(f"\n{'='*60}")
    print(f"  ECHO Test Set Statistics")
    print(f"{'='*60}")
    print(f"  Total pairs: {stats['total']}")
    print(f"\n  By Lead Category:")
    for cat, count in sorted(stats.get("by_category", {}).items()):
        pct = stats.get("category_distribution", {}).get(cat, 0) * 100
        print(f"    {cat:15s}: {count:4d} ({pct:.0f}%)")
    print(f"\n  By Topic:")
    for topic, count in sorted(stats.get("by_topic", {}).items()):
        pct = stats.get("topic_distribution", {}).get(topic, 0) * 100
        print(f"    {topic:15s}: {count:4d} ({pct:.0f}%)")
    print(f"\n  Response Length:")
    print(f"    avg: {stats.get('avg_response_length', 0):.0f} chars")
    print(f"    min: {stats.get('min_response_length', 0)} chars")
    print(f"    max: {stats.get('max_response_length', 0)} chars")
    print(f"    media messages: {stats.get('media_count', 0)}")
    print(f"    avg history: {stats.get('avg_history_length', 0):.1f} messages")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Save/load test sets
# ---------------------------------------------------------------------------

def save_test_set(
    pairs: list[dict],
    output_path: str | Path,
    creator_name: str,
    stats: dict | None = None,
) -> Path:
    """Save test set to JSON file."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "creator": creator_name,
        "stats": stats or compute_stats(pairs),
        "test_cases": pairs,
    }

    with open(output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved {len(pairs)} test pairs to {output}")
    return output


def load_test_set(path: str | Path) -> tuple[list[dict], dict]:
    """Load test set from JSON file. Returns (test_cases, metadata)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    test_cases = data.get("test_cases", data if isinstance(data, list) else [])
    metadata = {k: v for k, v in data.items() if k != "test_cases"}
    return test_cases, metadata


# ---------------------------------------------------------------------------
# Synthetic test set (for development/testing without DB)
# ---------------------------------------------------------------------------

def generate_synthetic_test_set(count: int = 100) -> list[dict]:
    """
    Generate a synthetic test set for development/testing.

    Uses realistic patterns based on Stefano's communication style.
    """
    import random

    random.seed(42)

    templates = {
        "nuevo": {
            "ventas": [
                ("Hola! Vi tu video sobre nutricion", "Ey que bien!! 💪 Me alegra que te haya gustado, de que video me hablas?"),
                ("Buenas, quiero info sobre tus cursos", "Hola! 😊 Claro que si, tengo varios cursos. Que es lo que buscas exactamente?"),
                ("Me interesa mejorar mi alimentacion", "Genial! 💪 Eso es lo primero, reconocer que quieres cambiar. Cuentame, que tipo de alimentacion llevas ahora?"),
                ("Cuanto cuesta el plan personalizado?", "Buenas! El plan personalizado de 3 meses esta a 297€ 🔥 Incluye seguimiento semanal conmigo. Te cuento mas?"),
            ],
            "casual": [
                ("Hola Stefano!", "Buenaaas! 😊 Que tal? En que te puedo ayudar?"),
                ("Hey que tal!", "Ey buenas! 💪 Todo bien por aqui, tu que tal?"),
            ],
        },
        "interesado": {
            "ventas": [
                ("Cuanto cuesta el curso?", "El curso de Nutricion Consciente esta a 197€ bro 🔥 Incluye 12 modulos + comunidad privada. Te paso mas info?"),
                ("Que incluye el curso?", "Te cuento! 📋 12 modulos, recetas, lista de compras, comunidad privada y 3 meses de soporte directo conmigo 💪"),
                ("Se puede pagar a plazos?", "Si! Puedes pagar en 3 cuotas de 66€ cada una 🙌 Asi es mas facil. Te interesa?"),
                ("He visto otros cursos mas baratos", "Buena pregunta! 😊 Lo que diferencia mi curso es que es 100% personalizado, no un PDF generico. Trabajamos juntos tu caso"),
                ("Cuanto tiempo dura el acceso?", "Tienes acceso de por vida al material! 🔥 Y el soporte directo conmigo es por 3 meses. Que te parece?"),
            ],
            "casual": [
                ("Bro que tal el finde?", "Buenisimo tio! 🔥 Fui a la playa y entrene un poco. Tu que tal?"),
                ("Jaja me dio risa tu ultimo reel", "Jajaja me alegro! 😂 Cual te gusto mas?"),
            ],
            "contenido": [
                ("Vi tu ultimo video, muy bueno!", "Gracias! 😊 Me alegra que te haya gustado. Cual te resonó más?"),
                ("Tienes recetas faciles?", "Si! 💪 En mi ebook de Recetas Fit hay 50 recetas super faciles. Esta a 19€ y te cambia la vida jaja"),
            ],
        },
        "caliente": {
            "ventas": [
                ("Me encanto, como puedo pagar?", "Vamoooos 🔥🔥 Te mando el link de pago! Es super facil, pagas y tienes acceso inmediato 💪"),
                ("Ok me apunto al curso", "Genial!! 🔥🔥 Te paso el link ahora mismo. Bienvenido a la comunidad! 💪"),
                ("197 es mucho para mi", "Te entiendo! 🙏 Piensa que son menos de 7€ al dia. Ademas puedes pagar en 3 cuotas. Te paso la info?"),
                ("Dame el link de pago", "Aqui lo tienes! 🔥 En cuanto pagues ya tienes acceso a todo. Si tienes alguna duda me dices 💪"),
            ],
        },
        "cliente": {
            "soporte": [
                ("No puedo acceder al modulo 3", "Tranqui! 🙏 Dame 5 min que reviso tu cuenta y te aviso. Disculpa las molestias"),
                ("Como descargo el ebook?", "Facil! 📱 Ve a la seccion 'Mis recursos' y ahi lo tienes en PDF. Si no lo ves me avisas!"),
                ("El video no carga", "Hmm dejame ver! 🤔 Prueba a cerrar sesion y entrar de nuevo. Si sigue igual me dices y lo reviso"),
            ],
            "casual": [
                ("Gracias por todo Stefano!", "A ti crack! 💪 Me alegra mucho ver tus resultados. Sigue asi!"),
                ("Llevo 2 semanas y ya veo cambios", "VAMOS! 🔥🔥 Eso es lo que me gusta oir. Sigue con el plan que los resultados se multiplican!"),
            ],
        },
        "fantasma": {
            "casual": [
                ("Ey Stefano, sigo aqui jaja", "Buenaaas!! 😊 Que alegria verte por aqui de nuevo! Sigues con ganas de mejorar tu alimentacion?"),
                ("Perdon por desaparecer", "Tranqui! 🙏 Lo importante es que estas de vuelta. Cuentame, como te ha ido?"),
            ],
            "ventas": [
                ("Sigo pensando en el curso", "Me alegra! 😊 Mira, justo ahora tenemos una promo especial. Te interesa que te cuente?"),
            ],
        },
    }

    pairs = []
    pair_id = 0

    # Generate proportional pairs
    for _ in range(count):
        # Pick category weighted
        category_weights = list(STRATIFICATION["lead_category"].items())
        categories = [c for c, _ in category_weights]
        weights = [w for _, w in category_weights]
        category = random.choices(categories, weights=weights, k=1)[0]

        # Pick topic
        available_topics = list(templates.get(category, {}).keys())
        if not available_topics:
            available_topics = ["casual"]
        topic = random.choice(available_topics)

        # Pick template
        template_list = templates.get(category, {}).get(topic, [])
        if not template_list:
            template_list = [("Hola!", "Buenas! 😊 En que te puedo ayudar?")]
        follower_msg, real_response = random.choice(template_list)

        pair_id += 1
        context = _generate_context_description(category, topic, follower_msg)

        # Build some history for non-greeting messages
        history = []
        if pair_id % 3 != 0:
            history = [
                {"role": "user", "content": "Hola Stefano"},
                {"role": "assistant", "content": "Buenas! 😊 Que tal?"},
            ]

        pairs.append({
            "id": f"test_{pair_id:04d}",
            "context": context,
            "conversation_history": history,
            "lead_category": category,
            "lead_id": f"synthetic-lead-{pair_id:04d}",
            "real_response": real_response,
            "follower_message": follower_msg,
            "metadata": {
                "topic": topic,
                "has_media": False,
                "language": "es_informal",
                "synthetic": True,
                "response_length": len(real_response),
            },
        })

    return pairs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Generate ECHO Engine test sets from real creator conversations"
    )
    parser.add_argument(
        "--creator",
        type=str,
        default="stefano",
        help="Creator name to extract conversations for",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output file path (default: test_sets/{creator}_v1.json)",
    )
    parser.add_argument(
        "--min-pairs",
        type=int,
        default=100,
        help="Minimum number of test pairs to generate",
    )
    parser.add_argument(
        "--max-pairs",
        type=int,
        default=200,
        help="Maximum number of test pairs to keep",
    )
    parser.add_argument(
        "--synthetic",
        action="store_true",
        help="Generate synthetic test set (no DB required)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show stats without writing to file",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.synthetic:
        logger.info("Generating synthetic test set...")
        pairs = generate_synthetic_test_set(count=args.max_pairs)
    else:
        logger.info(f"Extracting conversations for creator: {args.creator}")
        session = get_db_session()
        try:
            creator_id = resolve_creator_id(session, args.creator)
            conversations = extract_conversations(session, creator_id)
            pairs = generate_test_pairs(conversations)
            pairs = stratified_sample(pairs, target_count=args.max_pairs)
        finally:
            session.close()

    if len(pairs) < args.min_pairs and not args.synthetic:
        logger.warning(
            f"Only generated {len(pairs)} pairs, below minimum {args.min_pairs}. "
            f"Supplementing with synthetic data..."
        )
        synthetic = generate_synthetic_test_set(count=args.min_pairs - len(pairs))
        pairs.extend(synthetic)

    stats = compute_stats(pairs)
    print_stats(stats)

    if args.dry_run:
        logger.info("Dry run — not writing to file.")
        return

    output_path = args.output or str(
        Path(__file__).parent / "test_sets" / f"{args.creator}_v1.json"
    )
    save_test_set(pairs, output_path, args.creator, stats)
    print(f"Test set saved to: {output_path}")


if __name__ == "__main__":
    main()
