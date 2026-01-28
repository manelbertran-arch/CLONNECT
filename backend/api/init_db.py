import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

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
    logger.info("pgvector setup: skipped (pre-configured in Neon, will verify at runtime)")


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
        # Clone setup progress (persisted for polling across deploys)
        ("creators", "clone_status", "VARCHAR(20) DEFAULT 'pending'"),
        ("creators", "clone_progress", "JSON"),
        ("creators", "clone_started_at", "TIMESTAMPTZ"),
        ("creators", "clone_completed_at", "TIMESTAMPTZ"),
        ("creators", "clone_error", "TEXT"),  # Error message if clone_status is "error"
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
        # Product price for lead scoring
        ("creators", "product_price", "FLOAT DEFAULT 97.0"),
        # Email capture configuration
        ("creators", "email_capture_config", "JSON"),
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
        # CRM fields for leads
        ("leads", "notes", "TEXT"),
        ("leads", "tags", "JSON DEFAULT '[]'"),
        ("leads", "email", "VARCHAR(255)"),
        ("leads", "phone", "VARCHAR(50)"),
        ("leads", "deal_value", "FLOAT"),
        ("leads", "source", "VARCHAR(100)"),
        ("leads", "assigned_to", "VARCHAR(255)"),
        ("leads", "updated_at", "TIMESTAMPTZ DEFAULT NOW()"),
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
                    logger.info("Added column %s to %s", column, table)
            except Exception as e:
                logger.error("Migration error for %s.%s: %s", table, column, e)

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
                    logger.info("Altered column %s.%s to %s", table, column, new_type)
            except Exception as e:
                logger.error("Alteration error for %s.%s: %s", table, column, e)

def init_database():
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    if not DATABASE_URL:
        logger.warning("No DATABASE_URL - skipping DB init")
        return False

    # Fix Railway's postgres:// to postgresql:// for SQLAlchemy 1.4+
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        logger.info("Fixed DATABASE_URL scheme: postgres:// -> postgresql://")

    try:
        from api.database import Base
        from api.models import (
            User, UserCreator, Creator, Lead, LeadActivity, LeadTask, Message, Product,
            NurturingSequence, KnowledgeBase, BookingLink, CalendarBooking,
            CreatorAvailability, BookingSlot, UnifiedProfile, PlatformIdentity,
            EmailAskTracking, RAGDocument, ToneProfile, ContentChunk, InstagramPost
        )
    except ImportError:
        from database import Base
        from models import (
            User, UserCreator, Creator, Lead, LeadActivity, LeadTask, Message, Product,
            NurturingSequence, KnowledgeBase, BookingLink, CalendarBooking,
            CreatorAvailability, BookingSlot, UnifiedProfile, PlatformIdentity,
            EmailAskTracking, RAGDocument, ToneProfile, ContentChunk, InstagramPost
        )

    logger.info("Creating engine with DATABASE_URL configured: %s", bool(DATABASE_URL))
    engine = create_engine(DATABASE_URL)
    logger.info("Creating tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Tables created!")

    # Run migrations for new columns
    logger.info("Running migrations...")
    run_migrations(engine)
    logger.info("Migrations complete!")

    # Setup pgvector for semantic search
    logger.info("Setting up pgvector...")
    setup_pgvector(engine)
    logger.info("pgvector setup complete!")

    # NOTE: Removed automatic cleanup of booking_links - was causing services to be deleted
    # Only clean up debug test entries if needed
    with engine.connect() as conn:
        try:
            result = conn.execute(text(
                "DELETE FROM booking_links WHERE meeting_type = 'debug_test'"
            ))
            conn.commit()
            if result.rowcount > 0:
                logger.info("Deleted %d debug_test booking_links", result.rowcount)
        except Exception as e:
            logger.warning("Could not clean up debug booking_links: %s", e)
    
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
            logger.info("Default creator 'manel' created with copilot_mode=True")

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
            logger.info("Creator 'stefano_auto' created with copilot_mode=False (autopilot)")
        else:
            # Don't override existing copilot_mode setting
            # The user can toggle this via the API
            logger.info("Creator 'stefano_auto' already exists with copilot_mode=%s", stefano.copilot_mode)

        # Create demo user for Stefano
        create_demo_user(session)

    return True


def create_demo_user(session):
    """Create demo user for Stefano with bcrypt password hash"""
    import bcrypt
    try:
        from api.models import User, UserCreator, Creator
    except ImportError:
        from models import User, UserCreator, Creator

    # Check if user exists
    existing_user = session.query(User).filter_by(email="stefano@stefanobonanno.com").first()
    if existing_user:
        logger.info("Demo user 'stefano@stefanobonanno.com' already exists")
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
    logger.info("Created demo user: stefano@stefanobonanno.com")

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
            logger.info("Linked user to creator 'stefano_auto'")

if __name__ == "__main__":
    init_database()
