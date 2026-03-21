"""
Purgar gold examples contaminados (respuestas de error del sistema).
Marca is_active=False, NO borra. Imprime muestra antes de actuar.
"""
import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)

CONTAMINATION_PATTERNS = [
    "%error%",
    "%Lo siento%",
    "%hubo un error%",
    "%procesando tu mensaje%",
    "%Por favor intenta de nuevo%",
    "%intenta de nuevo%",
]

with engine.connect() as conn:
    # Contar total
    total = conn.execute(text("SELECT COUNT(*) FROM gold_examples")).scalar()

    # Construir query OR con ILIKE
    where_clauses = " OR ".join(
        f"creator_response ILIKE :p{i}" for i in range(len(CONTAMINATION_PATTERNS))
    )
    params = {f"p{i}": p for i, p in enumerate(CONTAMINATION_PATTERNS)}

    count_q = text(f"SELECT COUNT(*) FROM gold_examples WHERE is_active=True AND ({where_clauses})")
    contaminated_count = conn.execute(count_q, params).scalar()

    # Mostrar 5 ejemplos antes de actuar
    sample_q = text(f"""
        SELECT id, creator_response, source, created_at
        FROM gold_examples WHERE is_active=True AND ({where_clauses}) LIMIT 5
    """)
    samples = conn.execute(sample_q, params).fetchall()

    print(f"Total gold_examples: {total}")
    print(f"Contaminados (is_active=True): {contaminated_count}")
    print("\n--- MUESTRA (5 ejemplos) ---")
    for row in samples:
        print(f"  ID: {row.id} | source: {row.source}")
        print(f"  Response: {row.creator_response[:120]}")
        print()

    # Pedir confirmación
    confirm = input(f"\n¿Marcar {contaminated_count} como is_active=False? [y/N]: ")
    if confirm.lower() == "y":
        update_q = text(f"UPDATE gold_examples SET is_active=False WHERE is_active=True AND ({where_clauses})")
        result = conn.execute(update_q, params)
        conn.commit()
        print(f"✓ {result.rowcount} gold examples marcados como inactivos")
    else:
        print("Cancelado, no se hizo ningún cambio")
