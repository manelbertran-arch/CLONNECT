"""
Purga hechos contaminados en lead_memories que describen acciones del bot
en lugar de hechos sobre el lead.

Marca is_active=False — NO borra. Imprime muestra antes de actuar.
"""
import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)

BOT_PATTERNS = [
    "%El bot le pidio%",
    "%El bot respondio%",
    "%El bot dijo%",
    "%el bot le%",
    "%no llego al bot%",
    "%No m'apareix%",
    "%no m'apareix%",
    "%bot le pregunto%",
    "%bot le envio%",
    "%bot prometio%",
    "%bot indico%",
    "% bot %",          # cualquier mención de "bot" en medio del texto
    "%El bot%",
    "%el bot%",
]

with engine.connect() as conn:
    total = conn.execute(text("SELECT COUNT(*) FROM lead_memories WHERE is_active=true")).scalar()

    where_clauses = " OR ".join(
        f"fact_text ILIKE :p{i}" for i in range(len(BOT_PATTERNS))
    )
    params = {f"p{i}": p for i, p in enumerate(BOT_PATTERNS)}

    count_q = text(f"SELECT COUNT(*) FROM lead_memories WHERE is_active=true AND ({where_clauses})")
    contaminated_count = conn.execute(count_q, params).scalar()

    sample_q = text(f"""
        SELECT id, fact_text, fact_type, created_at
        FROM lead_memories
        WHERE is_active=true AND ({where_clauses})
        ORDER BY created_at DESC
        LIMIT 10
    """)
    samples = conn.execute(sample_q, params).fetchall()

    print(f"Total lead_memories activos: {total}")
    print(f"Contaminados (mencionan al bot): {contaminated_count}")
    print("\n--- MUESTRA (hasta 10) ---")
    for row in samples:
        print(f"  ID: {row.id} | type: {row.fact_type}")
        print(f"  Fact: {row.fact_text[:150]}")
        print()

    if contaminated_count == 0:
        print("Sin contaminados. No se hace nada.")
    else:
        confirm = input(f"\n¿Marcar {contaminated_count} como is_active=False? [y/N]: ")
        if confirm.lower() == "y":
            update_q = text(
                f"UPDATE lead_memories SET is_active=false WHERE is_active=true AND ({where_clauses})"
            )
            result = conn.execute(update_q, params)
            conn.commit()
            print(f"✓ {result.rowcount} hechos contaminados marcados como inactivos")
        else:
            print("Cancelado.")
