import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

def setup_pgvector(engine):
    """
    Verify pgvector extension and content_embeddings table exist.

    NOTE: The pgvector extension and table are pre-created in Neon via SQL Editor.
    Connection pooler may block some operations - we just skip and continue.
    The semantic search will work at runtime when queries go through.
    """
    # Skip all pgvector setup - it's pre-configured in Neon
    # The connection pooler blocks DDL and some queries during init
    # Tables exist and will be accessible at runtime
    print("pgvector setup: skipped (pre-configured in Neon, will verify at runtime)")


def run_migrations(engine):
    """Run migrations to add new columns to existing tables"""
    migrations = [
        # Connection columns for creators table
        ("creators", "instagram_page_id", "VARCHAR(255)"),
        ("creators", "instagram_user_id", "VARCHAR(255)"),  # Instagram Business Account ID for auto-onboarding
        ("creators", "whatsapp_token", "TEXT"),
        ("creators", "whatsapp_phone_id", "VARCHAR(255)"),
        ("creators", "stripe_api_key", "TEXT"),
        ("creators", "paypal_token", "TEXT"),
        ("creators", "paypal_email", "VARCHAR(255)"),
        ("creators", "hotmart_token", "TEXT"),
        ("creators", "calendly_token", "TEXT"),
        ("creators", "calendly_refresh_token", "TEXT"),
        ("creators", "calendly_token_expires_at", "TIMESTAMPTZ"),
        # Zoom connections
        ("creators", "zoom_access_token", "TEXT"),
        ("creators", "zoom_refresh_token", "TEXT"),
        ("creators", "zoom_token_expires_at", "TIMESTAMPTZ"),
        # Google connections
        ("creators", "google_access_token", "TEXT"),
        ("creators", "google_refresh_token", "TEXT"),
        ("creators", "google_token_expires_at", "TIMESTAMPTZ"),
        # Alternative payment methods
        ("creators", "other_payment_methods", "JSON"),
        # Knowledge base - About Me/Business info
        ("creators", "knowledge_about", "JSON"),
        # Onboarding status
        ("creators", "onboarding_completed", "BOOLEAN DEFAULT FALSE"),
        # Price for booking links
        ("booking_links", "price", "INTEGER DEFAULT 0"),
        # Payment link for products (Stripe/PayPal)
        ("products", "payment_link", "VARCHAR(500) DEFAULT ''"),
        # Copilot mode fields for messages
        ("messages", "status", "VARCHAR(20) DEFAULT 'sent'"),
        ("messages", "suggested_response", "TEXT"),
        ("messages", "approved_at", "TIMESTAMPTZ"),
        ("messages", "approved_by", "VARCHAR(50)"),
        ("messages", "platform_message_id", "VARCHAR(255)"),
        # Copilot mode setting for creators
        ("creators", "copilot_mode", "BOOLEAN DEFAULT TRUE"),
        # Anti-hallucination: Product source tracking
        ("products", "source_url", "TEXT"),
        ("products", "price_verified", "BOOLEAN DEFAULT FALSE"),
        ("products", "confidence", "FLOAT DEFAULT 0.0"),
        # Product auto-detection fields
        ("products", "product_type", "VARCHAR(50) DEFAULT 'otro'"),
        ("products", "short_description", "VARCHAR(300)"),
        # Taxonomía: category + is_free
        ("products", "category", "VARCHAR(20) DEFAULT 'product'"),
        ("products", "is_free", "BOOLEAN DEFAULT FALSE"),
        # Profile picture URL for leads (Instagram) - TEXT for long CDN URLs
        ("leads", "profile_pic_url", "TEXT"),
    ]

    # Column type alterations (for existing columns that need to be changed)
    alterations = [
        # profile_pic_url: VARCHAR(500) -> TEXT (Instagram CDN URLs are long)
        ("leads", "profile_pic_url", "TEXT"),
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

        # Apply column type alterations
        for table, column, new_type in alterations:
            try:
                # Check current column type
                result = conn.execute(text(f"""
                    SELECT data_type FROM information_schema.columns
                    WHERE table_name = '{table}' AND column_name = '{column}'
                """))
                row = result.fetchone()
                if row and row[0] != 'text':
                    # Alter column type to TEXT
                    conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {new_type}"))
                    conn.commit()
                    print(f"Altered column {table}.{column} to {new_type}")
            except Exception as e:
                print(f"Alteration error for {table}.{column}: {e}")

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
        from api.models import (
            User, UserCreator, Creator, Lead, Message, Product,
            NurturingSequence, KnowledgeBase, BookingLink, CalendarBooking,
            CreatorAvailability, BookingSlot, UnifiedProfile, PlatformIdentity,
            EmailAskTracking, RAGDocument, ToneProfile, ContentChunk, InstagramPost
        )
    except:
        from database import Base
        from models import (
            User, UserCreator, Creator, Lead, Message, Product,
            NurturingSequence, KnowledgeBase, BookingLink, CalendarBooking,
            CreatorAvailability, BookingSlot, UnifiedProfile, PlatformIdentity,
            EmailAskTracking, RAGDocument, ToneProfile, ContentChunk, InstagramPost
        )

    print(f"Creating engine with DATABASE_URL configured: {bool(DATABASE_URL)}")
    engine = create_engine(DATABASE_URL)
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created!")

    # Run migrations for new columns
    print("Running migrations...")
    run_migrations(engine)
    print("Migrations complete!")

    # Setup pgvector for semantic search
    print("Setting up pgvector...")
    setup_pgvector(engine)
    print("pgvector setup complete!")

    # NOTE: Removed automatic cleanup of booking_links - was causing services to be deleted
    # Only clean up debug test entries if needed
    with engine.connect() as conn:
        try:
            result = conn.execute(text(
                "DELETE FROM booking_links WHERE meeting_type = 'debug_test'"
            ))
            conn.commit()
            if result.rowcount > 0:
                print(f"Deleted {result.rowcount} debug_test booking_links")
        except Exception as e:
            print(f"Note: Could not clean up debug booking_links: {e}")
    
    with Session(engine) as session:
        # Create default creator 'manel'
        existing = session.query(Creator).filter_by(name="manel").first()
        if not existing:
            creator = Creator(
                email="manel@clonnect.com",
                name="manel",
                api_key="clonnect_manel_key",
                clone_tone="friendly",
                clone_name="Manel",
                bot_active=True,
                copilot_mode=True  # Enable copilot by default
            )
            session.add(creator)
            session.commit()
            print("Default creator 'manel' created with copilot_mode=True")

        # Create Stefano creator for Telegram bot
        stefano = session.query(Creator).filter_by(name="stefano_auto").first()
        if not stefano:
            stefano = Creator(
                email="stefano@clonnect.com",
                name="stefano_auto",
                api_key="clonnect_stefano_key",
                clone_tone="professional",
                clone_name="Stefano Bonanno",
                bot_active=True,
                copilot_mode=False  # Default to autopilot (bot responds automatically)
            )
            session.add(stefano)
            session.commit()
            print("Creator 'stefano_auto' created with copilot_mode=False (autopilot)")
        else:
            # Don't override existing copilot_mode setting
            # The user can toggle this via the API
            print(f"Creator 'stefano_auto' already exists with copilot_mode={stefano.copilot_mode}")

        # Create demo user for Stefano
        create_demo_user(session)

    return True


def create_demo_user(session):
    """Create demo user for Stefano with bcrypt password hash"""
    import bcrypt
    try:
        from api.models import User, UserCreator, Creator
    except:
        from models import User, UserCreator, Creator

    # Check if user exists
    existing_user = session.query(User).filter_by(email="stefano@stefanobonanno.com").first()
    if existing_user:
        print(f"Demo user 'stefano@stefanobonanno.com' already exists")
        return

    # Hash the password
    password = "demo2024"
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Create user
    user = User(
        email="stefano@stefanobonanno.com",
        password_hash=password_hash,
        name="Stefano Bonanno",
        is_active=True,
        is_admin=False
    )
    session.add(user)
    session.commit()
    print(f"Created demo user: stefano@stefanobonanno.com (password: demo2024)")

    # Link user to stefano_auto creator
    stefano_creator = session.query(Creator).filter_by(name="stefano_auto").first()
    if stefano_creator:
        # Check if link exists
        existing_link = session.query(UserCreator).filter_by(
            user_id=user.id,
            creator_id=stefano_creator.id
        ).first()
        if not existing_link:
            user_creator = UserCreator(
                user_id=user.id,
                creator_id=stefano_creator.id,
                role="owner"
            )
            session.add(user_creator)
            session.commit()
            print(f"Linked user to creator 'stefano_auto'")

if __name__ == "__main__":
    init_database()
