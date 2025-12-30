import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

def run_migrations(engine):
    """Run migrations to add new columns to existing tables"""
    migrations = [
        # Connection columns for creators table
        ("creators", "instagram_page_id", "VARCHAR(255)"),
        ("creators", "whatsapp_token", "TEXT"),
        ("creators", "whatsapp_phone_id", "VARCHAR(255)"),
        ("creators", "stripe_api_key", "TEXT"),
        ("creators", "paypal_token", "TEXT"),
        ("creators", "paypal_email", "VARCHAR(255)"),
        ("creators", "hotmart_token", "TEXT"),
        ("creators", "calendly_token", "TEXT"),
        # Alternative payment methods
        ("creators", "other_payment_methods", "JSON"),
    ]

    with engine.connect() as conn:
        for table, column, col_type in migrations:
            try:
                # Check if column exists
                result = conn.execute(text(f"""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = '{table}' AND column_name = '{column}'
                """))
                if result.fetchone() is None:
                    # Column doesn't exist, add it
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                    conn.commit()
                    print(f"Added column {column} to {table}")
            except Exception as e:
                print(f"Migration error for {table}.{column}: {e}")

def init_database():
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    if not DATABASE_URL:
        print("No DATABASE_URL - skipping DB init")
        return False

    # Fix Railway's postgres:// to postgresql:// for SQLAlchemy 1.4+
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        print("Fixed DATABASE_URL scheme: postgres:// -> postgresql://")

    try:
        from api.database import Base
        from api.models import Creator, Lead, Message, Product, NurturingSequence, KnowledgeBase, BookingLink, CalendarBooking
    except:
        from database import Base
        from models import Creator, Lead, Message, Product, NurturingSequence, KnowledgeBase, BookingLink, CalendarBooking

    print(f"Creating engine with DATABASE_URL configured: {bool(DATABASE_URL)}")
    engine = create_engine(DATABASE_URL)
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created!")

    # Run migrations for new columns
    print("Running migrations...")
    run_migrations(engine)
    print("Migrations complete!")

    # Clean up booking_links
    with engine.connect() as conn:
        try:
            # Fix wrong creator_id
            result = conn.execute(text(
                "UPDATE booking_links SET creator_id = 'manel' WHERE creator_id = 'test_debug'"
            ))
            conn.commit()
            if result.rowcount > 0:
                print(f"Fixed {result.rowcount} booking_links: creator_id test_debug -> manel")

            # Delete debug test entries
            result = conn.execute(text(
                "DELETE FROM booking_links WHERE meeting_type = 'debug_test'"
            ))
            conn.commit()
            if result.rowcount > 0:
                print(f"Deleted {result.rowcount} debug_test booking_links")
        except Exception as e:
            print(f"Note: Could not clean up booking_links: {e}")
    
    with Session(engine) as session:
        existing = session.query(Creator).filter_by(name="manel").first()
        if not existing:
            creator = Creator(
                email="manel@clonnect.com",
                name="manel",
                api_key="clonnect_manel_key",
                clone_tone="friendly",
                clone_name="Manel",
                bot_active=True
            )
            session.add(creator)
            session.commit()
            print("Default creator 'manel' created")
    return True

if __name__ == "__main__":
    init_database()
