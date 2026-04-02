"""
Create Proposition Chunks with Contextual Embedding (Anthropic method).

Takes knowledge_base Q&A, product data, and synthesized expertise/values
and creates atomic, self-contained proposition chunks. Each chunk is
embedded with a contextual prefix so the vector captures
"Iris + fitness + Barcelona + [content]".

Source types:
  - faq: Factual Q&A from knowledge_base
  - expertise: Creator's domain knowledge and teaching philosophy
  - objection_handling: How to address common concerns
  - values: Creator's core values and approach
  - policies: Booking, payment, membership rules

Usage:
  railway run python3 scripts/create_proposition_chunks.py
  railway run python3 scripts/create_proposition_chunks.py --dry-run
"""

import argparse
import hashlib
import json
import logging
import sys
import time
import uuid
from typing import Dict, List, Optional, Tuple

# Add parent dir to path
sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ─── Iris contextual prefix (Anthropic method) ───────────────────────
# Prepended to each chunk BEFORE embedding so the vector captures
# creator identity + domain + location context.
# DEPRECATED: Hardcoded prefix replaced by universal build_contextual_prefix().
# Kept as fallback ONLY if DB is unreachable during chunk creation for iris_bertran.
_IRIS_LEGACY_PREFIX = (
    "Iris Bertran (@iraais5) es instructora de fitness en Barcelona "
    "(Igualada/Odena, comarca Anoia). Imparte clases de barre, zumba, "
    "Flow4U (heels dance) y pilates reformer personal en Dinamic Sport Gym "
    "y su estudio propio. Habla castellano, catalán y mezcla ambos idiomas. "
    "Tiene un estilo cercano, cálido y directo con sus alumnas.\n\n"
)

# Default creator — can be overridden by --creator-id CLI arg
IRIS_CREATOR_ID_SLUG = "iris_bertran"
IRIS_CREATOR_ID_UUID = "8e9d1705-4772-40bd-83b1-c6821c5593bf"


def _get_context_prefix(creator_id: str) -> str:
    """Get contextual prefix for any creator (Anthropic Contextual Retrieval)."""
    try:
        from core.contextual_prefix import build_contextual_prefix
        prefix = build_contextual_prefix(creator_id)
        if prefix:
            return prefix
    except Exception as e:
        logger.warning(f"Universal prefix failed for {creator_id}: {e}")
    # Fallback for Iris only
    if creator_id == "iris_bertran":
        return _IRIS_LEGACY_PREFIX
    return ""


# ─── Proposition Chunks Definition ────────────────────────────────────
# Each chunk is atomic (self-contained), under 512 tokens, and has a
# source_type for RAG boost scoring.


def build_proposition_chunks() -> List[Dict]:
    """Build all proposition chunks from available data sources."""
    chunks = []

    # ── 1. FAQ from knowledge_base (DB) ──────────────────────────────
    chunks.extend(_build_faq_chunks_from_db())

    # ── 2. Expertise chunks (synthesized from Iris profile) ──────────
    chunks.extend(_build_expertise_chunks())

    # ── 3. Objection handling chunks ─────────────────────────────────
    chunks.extend(_build_objection_chunks())

    # ── 4. Values chunks ─────────────────────────────────────────────
    chunks.extend(_build_values_chunks())

    # ── 5. Policies chunks ───────────────────────────────────────────
    chunks.extend(_build_policies_chunks())

    return chunks


def _build_faq_chunks_from_db() -> List[Dict]:
    """Load knowledge_base Q&A and create atomic FAQ chunks."""
    from api.database import SessionLocal
    from sqlalchemy import text

    s = SessionLocal()
    try:
        rows = s.execute(
            text("SELECT question, answer FROM knowledge_base WHERE creator_id = :cid"),
            {"cid": IRIS_CREATOR_ID_UUID},
        ).fetchall()
    finally:
        s.close()

    chunks = []
    for row in rows:
        q, a = row[0], row[1]
        # Atomic proposition: self-contained Q&A
        content = f"PREGUNTA: {q}\nRESPUESTA: {a}"
        chunks.append(
            {
                "content": content,
                "source_type": "faq",
                "title": q,
                "source_id": f"kb_{hashlib.md5(q.encode()).hexdigest()[:12]}",
            }
        )

    logger.info(f"Built {len(chunks)} FAQ chunks from knowledge_base")
    return chunks


def _build_expertise_chunks() -> List[Dict]:
    """Synthesize expertise chunks from Iris's known domain knowledge."""
    expertise = [
        {
            "title": "Qué es barre fitness y por qué Iris lo recomienda",
            "content": (
                "Barre fitness es una disciplina que combina técnicas de ballet clásico, "
                "pilates y trabajo de fuerza. En las clases de Iris se trabaja fuerza, "
                "control corporal y elegancia, todo acompañado de coreografía que cambia "
                "cada mes. Es apto para todos los niveles sin experiencia previa. Iris "
                "adapta los ejercicios a cada persona. Es de bajo impacto, ideal para "
                "quienes buscan tonificar sin machacar articulaciones."
            ),
        },
        {
            "title": "Qué es Flow4U y cómo funciona",
            "content": (
                "Flow4U es la clase de heels dance (baile con tacones) que Iris imparte "
                "con Albert Sala. Cada mes se aprende una nueva coreografía con música "
                "diferente. No se necesita experiencia previa ni ser socia del gimnasio. "
                "Es los jueves a las 20:15h en Dinamic Sport Gym. Cuesta 9€ para no "
                "socios, con precio reducido para socios."
            ),
        },
        {
            "title": "Pilates reformer personal con Iris",
            "content": (
                "Iris ofrece sesiones de pilates reformer individuales (1:1) en su "
                "estudio propio. Es entrenamiento supervisado y personalizado con "
                "máquina reformer. Sesión individual: 40€/hora. Bono de 6 sesiones: "
                "220€ (36.67€/sesión). Se paga por Bizum directamente a Iris. Para "
                "reservar, contactar por DM o WhatsApp."
            ),
        },
        {
            "title": "Sunday Bonus Session: qué incluye y cuándo es",
            "content": (
                "La Sunday Bonus Session es una sesión especial de domingos que incluye "
                "tres actividades: zumba a las 9:30h, barre a las 10:30h e hipopresivos "
                "a las 12:30h. Solo disponible en temporada de invierno. Precio: socios "
                "3€, no socios 5€. Hay que reservar y pagar en recepción de Dinamic Sport."
            ),
        },
        {
            "title": "Zumba con Iris: estilo y filosofía",
            "content": (
                "Las clases de zumba de Iris tienen coreografías originales propias. "
                "Su filosofía es soltar, disfrutar y pasarlo bien. Coreo nueva cada mes "
                "para mantener la motivación. Los lunes en Dinamic Sport Gym. Es la "
                "clase más enérgica y divertida del horario semanal de Iris."
            ),
        },
        {
            "title": "Dinamic Sport Gym: ubicación y relación con Iris",
            "content": (
                "Dinamic Sport Gym (@dinamicsportgym) está en Igualada/Odena, comarca "
                "del Anoia, provincia de Barcelona. Es donde Iris imparte la mayoría "
                "de sus clases grupales (barre, zumba, Flow4U, Sunday Bonus). No es "
                "necesario ser socio del gimnasio para asistir a las clases de Iris, "
                "aunque los socios tienen precios reducidos."
            ),
        },
    ]

    chunks = []
    for ex in expertise:
        chunks.append(
            {
                "content": ex["content"],
                "source_type": "expertise",
                "title": ex["title"],
                "source_id": f"exp_{hashlib.md5(ex['title'].encode()).hexdigest()[:12]}",
            }
        )

    logger.info(f"Built {len(chunks)} expertise chunks")
    return chunks


def _build_objection_chunks() -> List[Dict]:
    """Build chunks for common objection handling."""
    objections = [
        {
            "title": "Objeción de precio: las clases son caras",
            "content": (
                "Cuando alguien dice que las clases son caras, Iris responde con cercanía. "
                "Los precios son muy accesibles: barre desde 3€ (socios) o 5€ (no socios), "
                "Flow4U 9€, Sunday Bonus 3-5€. El reformer personal a 40€/sesión es "
                "competitivo para entrenamiento 1:1 supervisado. El bono de 6 sesiones "
                "(220€) reduce el coste a 36.67€/sesión. Iris nunca presiona, ofrece "
                "opciones y deja que la persona decida."
            ),
        },
        {
            "title": "Objeción de tiempo: no tengo tiempo",
            "content": (
                "Cuando alguien dice que no tiene tiempo, Iris es comprensiva y flexible. "
                "Las clases grupales son de una hora y hay opciones varios días de la "
                "semana: lunes (zumba), martes y jueves (barre), jueves (Flow4U), "
                "domingos (Sunday Bonus en invierno). El reformer se adapta al horario "
                "de cada persona. Iris anima a empezar con una clase suelta sin compromiso."
            ),
        },
        {
            "title": "Objeción de nivel: no tengo experiencia",
            "content": (
                "Iris siempre tranquiliza a quien dice que no tiene experiencia. Todas "
                "sus clases están pensadas para todos los niveles. Iris adapta los "
                "ejercicios a cada persona. No necesitas experiencia previa ni en barre, "
                "ni en Flow4U, ni en zumba. El reformer personal es aún más adaptable "
                "porque es 1:1 y Iris ajusta todo al nivel de cada alumna."
            ),
        },
        {
            "title": "Objeción de compromiso: no quiero apuntarme al gimnasio",
            "content": (
                "No hace falta ser socia de Dinamic Sport para asistir a las clases "
                "de Iris. Puedes venir como no socia pagando un precio ligeramente "
                "superior (barre 5€ vs 3€ socios). Flow4U, Sunday Bonus y el reformer "
                "personal no requieren membresía del gimnasio. Iris invita a probar "
                "una clase suelta primero para ver si le gusta."
            ),
        },
        {
            "title": "Objeción de confianza: no sé si es para mí",
            "content": (
                "Cuando alguien duda si la clase es para ella, Iris la anima con "
                "cercanía. Invita a probar una clase suelta sin compromiso. Comparte "
                "que sus alumnas van de todos los niveles y edades. El ambiente es "
                "divertido y sin juicio. Iris adapta los ejercicios individualmente. "
                "Suele decir 'ven a probar y ya decides' con su estilo cercano y cálido."
            ),
        },
    ]

    chunks = []
    for obj in objections:
        chunks.append(
            {
                "content": obj["content"],
                "source_type": "objection_handling",
                "title": obj["title"],
                "source_id": f"obj_{hashlib.md5(obj['title'].encode()).hexdigest()[:12]}",
            }
        )

    logger.info(f"Built {len(chunks)} objection_handling chunks")
    return chunks


def _build_values_chunks() -> List[Dict]:
    """Build chunks about Iris's core values and approach."""
    values = [
        {
            "title": "Filosofía de Iris: cercanía y comunidad",
            "content": (
                "Iris trata a sus alumnas como amigas, no como clientas. Su comunicación "
                "es cercana, cálida y directa. Mezcla castellano y catalán de forma "
                "natural. Usa expresiones cariñosas como 'nena', 'cuca', 'tia'. "
                "Nunca presiona para vender, sino que invita y comparte. Su objetivo "
                "es crear comunidad alrededor del movimiento y el bienestar."
            ),
        },
        {
            "title": "Iris como creadora de contenido fitness",
            "content": (
                "Iris es creadora de contenido fitness en Instagram (@iraais5). "
                "Comparte su día a día, entrenamientos, coreografías y momentos "
                "personales. Su contenido refleja su estilo de vida real, no es "
                "una imagen fabricada. Graba reels de sus clases, comparte recetas "
                "y momentos con sus alumnas. Es auténtica y transparente."
            ),
        },
        {
            "title": "Iris: formación y trayectoria profesional",
            "content": (
                "Iris Bertran es instructora certificada de fitness con formación en "
                "barre, zumba, pilates reformer y heels dance. Se forma continuamente, "
                "los miércoles tiene formación de heels de 17:30 a 19:30. Trabaja en "
                "Dinamic Sport Gym y tiene su propio estudio de reformer. También "
                "imparte masterclasses los sábados."
            ),
        },
    ]

    chunks = []
    for val in values:
        chunks.append(
            {
                "content": val["content"],
                "source_type": "values",
                "title": val["title"],
                "source_id": f"val_{hashlib.md5(val['title'].encode()).hexdigest()[:12]}",
            }
        )

    logger.info(f"Built {len(chunks)} values chunks")
    return chunks


def _build_policies_chunks() -> List[Dict]:
    """Build chunks about booking, payment, and membership policies."""
    policies = [
        {
            "title": "Cómo reservar clases grupales con Iris",
            "content": (
                "Para reservar clases grupales (barre, zumba, Flow4U, Sunday Bonus) "
                "hay que llamar a recepción de Dinamic Sport Gym y reservar plaza. "
                "También se puede escribir a Iris por DM de Instagram y ella te apunta. "
                "Se paga en recepción antes de la clase. No hace falta ser socia del "
                "gimnasio."
            ),
        },
        {
            "title": "Cómo reservar y pagar reformer personal",
            "content": (
                "Para pilates reformer personal hay que contactar directamente con "
                "Iris por DM de Instagram o WhatsApp. Se paga por Bizum a Iris. "
                "Sesión individual: 40€/hora. Bono 6 sesiones: 220€. Las sesiones "
                "son en el estudio propio de Iris, no en Dinamic Sport."
            ),
        },
        {
            "title": "Métodos de pago aceptados",
            "content": (
                "Para clases grupales en Dinamic Sport: pago en recepción (efectivo "
                "o tarjeta según el gimnasio). Para reformer personal y pagos directos "
                "a Iris: Bizum. Iris gestiona los pagos de reformer directamente, "
                "no a través del gimnasio."
            ),
        },
        {
            "title": "Horario semanal completo de Iris",
            "content": (
                "Horario semanal de Iris Bertran: Lunes — Zumba. Martes — Barre + "
                "Reformer personal. Miércoles — Formación Heels 17:30-19:30. Jueves "
                "— Barre + Flow4U (20:15h) + Reformer. Viernes — Reformer + Grabaciones "
                "de contenido. Sábado — Masterclasses + Reformer. Domingo — Sunday "
                "Bonus Session (solo temporada invierno): zumba 9:30h, barre 10:30h, "
                "hipopresivos 12:30h."
            ),
        },
    ]

    chunks = []
    for pol in policies:
        chunks.append(
            {
                "content": pol["content"],
                "source_type": "policies",
                "title": pol["title"],
                "source_id": f"pol_{hashlib.md5(pol['title'].encode()).hexdigest()[:12]}",
            }
        )

    logger.info(f"Built {len(chunks)} policies chunks")
    return chunks


# ─── Insert into DB ───────────────────────────────────────────────────


def insert_chunks(chunks: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """
    Insert proposition chunks into content_chunks + content_embeddings.

    Uses contextual embedding: prepends IRIS_CONTEXT_PREFIX to each chunk
    content before generating the embedding vector, but stores the original
    content (without prefix) in content_chunks.

    Returns (inserted, skipped) counts.
    """
    from core.embeddings import generate_embeddings_batch, store_embedding

    if dry_run:
        logger.info(f"[DRY RUN] Would insert {len(chunks)} chunks")
        for c in chunks:
            logger.info(f"  [{c['source_type']}] {c['title']}")
            logger.info(f"    Content ({len(c['content'])} chars): {c['content'][:100]}...")
        return len(chunks), 0

    from api.database import SessionLocal
    from sqlalchemy import text

    s = SessionLocal()

    # Check existing chunks to avoid duplicates (by source_id)
    existing_ids = set()
    try:
        rows = s.execute(
            text(
                "SELECT source_id FROM content_chunks WHERE creator_id = :cid AND source_id IS NOT NULL"
            ),
            {"cid": IRIS_CREATOR_ID_SLUG},
        ).fetchall()
        existing_ids = {r[0] for r in rows}
    except Exception:
        pass

    # Filter out existing
    new_chunks = [c for c in chunks if c["source_id"] not in existing_ids]
    skipped = len(chunks) - len(new_chunks)
    if skipped:
        logger.info(f"Skipping {skipped} chunks that already exist (by source_id)")

    if not new_chunks:
        logger.info("No new chunks to insert")
        s.close()
        return 0, skipped

    # Generate embeddings in batch with universal contextual prefix
    # (Anthropic Contextual Retrieval: +49% quality)
    context_prefix = _get_context_prefix(IRIS_CREATOR_ID_SLUG)
    texts_for_embedding = [context_prefix + c["content"] for c in new_chunks]
    logger.info(f"Generating {len(texts_for_embedding)} embeddings (batch, prefix={len(context_prefix)} chars)...")
    embeddings = generate_embeddings_batch(texts_for_embedding)

    inserted = 0
    for i, chunk in enumerate(new_chunks):
        embedding = embeddings[i]
        if embedding is None:
            logger.warning(f"Failed to embed chunk: {chunk['title']}")
            continue

        chunk_id = str(uuid.uuid4())

        try:
            # Insert content_chunk
            s.execute(
                text(
                    """
                    INSERT INTO content_chunks (id, creator_id, chunk_id, content, source_type,
                        source_id, title, chunk_index, total_chunks)
                    VALUES (:id, :creator_id, :chunk_id, :content, :source_type,
                        :source_id, :title, 0, 1)
                """
                ),
                {
                    "id": chunk_id,
                    "creator_id": IRIS_CREATOR_ID_SLUG,
                    "chunk_id": chunk_id,
                    "content": chunk["content"],
                    "source_type": chunk["source_type"],
                    "source_id": chunk.get("source_id"),
                    "title": chunk["title"],
                },
            )

            # Store embedding
            store_embedding(
                chunk_id=chunk_id,
                creator_id=IRIS_CREATOR_ID_SLUG,
                content=chunk["content"],
                embedding=embedding,
            )

            inserted += 1
            logger.info(f"  ✓ [{chunk['source_type']}] {chunk['title']}")

        except Exception as e:
            logger.error(f"  ✗ Failed to insert '{chunk['title']}': {e}")
            s.rollback()
            continue

    s.commit()
    s.close()

    return inserted, skipped


# ─── Verify ───────────────────────────────────────────────────────────


def verify_search():
    """Verify proposition chunks are searchable via RAG."""
    from core.embeddings import generate_embedding, search_similar

    test_queries = [
        "¿Cuánto cuesta barre?",
        "No tengo experiencia, ¿puedo ir?",
        "Es muy caro para mí",
        "¿Cómo reservo una clase?",
        "¿Qué horario tiene Iris?",
    ]

    print("\n" + "=" * 60)
    print("VERIFICATION: Search test queries against proposition chunks")
    print("=" * 60)

    for query in test_queries:
        emb = generate_embedding(query)
        if not emb:
            print(f"\n❌ Could not embed: {query}")
            continue

        results = search_similar(emb, IRIS_CREATOR_ID_SLUG, top_k=3, min_similarity=0.30)
        print(f"\n🔍 Query: '{query}'")
        if not results:
            print("   No results found")
        for r in results:
            print(f"   [{r['source_type']}] sim={r['similarity']:.3f} — {r['content'][:80]}...")


# ─── Main ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create proposition chunks for Iris")
    parser.add_argument("--dry-run", action="store_true", help="Print chunks without inserting")
    parser.add_argument("--verify-only", action="store_true", help="Only run verification search")
    args = parser.parse_args()

    if args.verify_only:
        verify_search()
        sys.exit(0)

    logger.info("Building proposition chunks...")
    chunks = build_proposition_chunks()
    logger.info(f"Total chunks built: {len(chunks)}")

    by_type = {}
    for c in chunks:
        by_type.setdefault(c["source_type"], []).append(c)
    for t, cs in sorted(by_type.items()):
        logger.info(f"  {t}: {len(cs)}")

    inserted, skipped = insert_chunks(chunks, dry_run=args.dry_run)
    logger.info(f"\nResult: {inserted} inserted, {skipped} skipped (duplicates)")

    if not args.dry_run and inserted > 0:
        logger.info("\nRunning verification...")
        verify_search()
