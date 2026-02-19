import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

logger = logging.getLogger(__name__)

# ---- SQL Injection Prevention: Whitelist validation for DDL operations ----
# Table names, column names, and column types used in run_migrations() are all
# hardcoded in the migrations list below. These whitelists ensure that even if
# the list were somehow modified, only known-safe identifiers could be used.

ALLOWED_MIGRATION_TABLES = frozenset(
    {
        "creators",
        "booking_links",
        "products",
        "messages",
        "leads",
    }
)

ALLOWED_MIGRATION_COLUMNS = frozenset(
    {
        "instagram_page_id",
        "instagram_user_id",
        "whatsapp_token",
        "whatsapp_phone_id",
        "stripe_api_key",
        "paypal_token",
        "paypal_email",
        "hotmart_token",
        "calendly_token",
        "calendly_refresh_token",
        "calendly_token_expires_at",
        "zoom_access_token",
        "zoom_refresh_token",
        "zoom_token_expires_at",
        "google_access_token",
        "google_refresh_token",
        "google_token_expires_at",
        "other_payment_methods",
        "knowledge_about",
        "onboarding_completed",
        "clone_status",
        "clone_progress",
        "clone_started_at",
        "clone_completed_at",
        "clone_error",
        "price",
        "payment_link",
        "status",
        "suggested_response",
        "approved_at",
        "approved_by",
        "platform_message_id",
        "copilot_mode",
        "product_price",
        "email_capture_config",
        "source_url",
        "price_verified",
        "confidence",
        "product_type",
        "short_description",
        "category",
        "is_free",
        "profile_pic_url",
        "notes",
        "tags",
        "email",
        "phone",
        "deal_value",
        "source",
        "assigned_to",
        "updated_at",
    }
)

# Allowed SQL types for column definitions (prefix-matched for types with defaults)
ALLOWED_COLUMN_TYPES = frozenset(
    {
        "VARCHAR(255)",
        "VARCHAR(500)",
        "VARCHAR(300)",
        "VARCHAR(50)",
        "VARCHAR(100)",
        "VARCHAR(20)",
        "VARCHAR(20) DEFAULT 'pending'",
        "VARCHAR(50) DEFAULT 'otro'",
        "VARCHAR(20) DEFAULT 'sent'",
        "VARCHAR(500) DEFAULT ''",
        "TEXT",
        "JSON",
        "JSON DEFAULT '[]'",
        "BOOLEAN DEFAULT FALSE",
        "BOOLEAN DEFAULT TRUE",
        "FLOAT",
        "FLOAT DEFAULT 0.0",
        "FLOAT DEFAULT 97.0",
        "INTEGER DEFAULT 0",
        "TIMESTAMPTZ",
        "TIMESTAMPTZ DEFAULT NOW()",
    }
)


def _validate_migration_table(table: str) -> str:
    """Validate table name against whitelist for DDL migrations."""
    if table not in ALLOWED_MIGRATION_TABLES:
        raise ValueError(f"Migration table '{table}' not in allowed whitelist")
    return table


def _validate_migration_column(column: str) -> str:
    """Validate column name against whitelist for DDL migrations."""
    if column not in ALLOWED_MIGRATION_COLUMNS:
        raise ValueError(f"Migration column '{column}' not in allowed whitelist")
    return column


def _validate_migration_col_type(col_type: str) -> str:
    """Validate column type against whitelist for DDL migrations."""
    if col_type not in ALLOWED_COLUMN_TYPES:
        raise ValueError(f"Migration column type '{col_type}' not in allowed whitelist")
    return col_type


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
        (
            "creators",
            "instagram_user_id",
            "VARCHAR(255)",
        ),  # Instagram Business Account ID for auto-onboarding
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
                # Validate all identifiers against whitelists (SQL injection prevention)
                _validate_migration_table(table)
                _validate_migration_column(column)
                _validate_migration_col_type(col_type)

                # Check if column exists (parameterized query for values)
                result = conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = :table AND column_name = :column"
                    ),
                    {"table": table, "column": column},
                )
                if result.fetchone() is None:
                    # Column doesn't exist, add it
                    # DDL: table/column names validated above, col_type whitelisted
                    conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {col_type}'))
                    conn.commit()
                    logger.info("Added column %s to %s", column, table)
            except Exception as e:
                logger.error("Migration error for %s.%s: %s", table, column, e)

        # Apply column type alterations
        for table, column, new_type in alterations:
            try:
                # Validate all identifiers against whitelists (SQL injection prevention)
                _validate_migration_table(table)
                _validate_migration_column(column)
                _validate_migration_col_type(new_type)

                # Check current column type (parameterized query for values)
                result = conn.execute(
                    text(
                        "SELECT data_type FROM information_schema.columns "
                        "WHERE table_name = :table AND column_name = :column"
                    ),
                    {"table": table, "column": column},
                )
                row = result.fetchone()
                if row and row[0] != "text":
                    # Alter column type (DDL: identifiers validated above)
                    conn.execute(
                        text(f'ALTER TABLE "{table}" ALTER COLUMN "{column}" TYPE {new_type}')
                    )
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
            BookingLink,
            BookingSlot,
            CalendarBooking,
            ContentChunk,
            Creator,
            CreatorAvailability,
            EmailAskTracking,
            InstagramPost,
            KnowledgeBase,
            Lead,
            LeadActivity,
            LeadTask,
            Message,
            NurturingSequence,
            PlatformIdentity,
            Product,
            RAGDocument,
            ToneProfile,
            UnifiedProfile,
            User,
            UserCreator,
        )
    except ImportError:
        from database import Base
        from models import (  # noqa: F401
            BookingLink,
            BookingSlot,
            CalendarBooking,
            ContentChunk,
            Creator,
            CreatorAvailability,
            EmailAskTracking,
            InstagramPost,
            KnowledgeBase,
            Lead,
            LeadActivity,
            LeadTask,
            Message,
            NurturingSequence,
            PlatformIdentity,
            Product,
            RAGDocument,
            ToneProfile,
            UnifiedProfile,
            User,
            UserCreator,
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
            result = conn.execute(
                text("DELETE FROM booking_links WHERE meeting_type = 'debug_test'")
            )
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
                bot_active=False,  # Test creator — activate manually
                copilot_mode=True,
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
                bot_active=False,  # Test creator — activate manually
                copilot_mode=False,
            )
            session.add(stefano)
            session.commit()
            logger.info("Creator 'stefano_auto' created with copilot_mode=False (autopilot)")
        else:
            # Don't override existing copilot_mode setting
            # The user can toggle this via the API
            logger.info(
                "Creator 'stefano_auto' already exists with copilot_mode=%s", stefano.copilot_mode
            )

        # Create demo user for Stefano
        create_demo_user(session)

    return True


def create_demo_user(session):
    """Create demo user for Stefano with bcrypt password hash"""
    import bcrypt

    try:
        from api.models import Creator, User, UserCreator
    except ImportError:
        from models import Creator, User, UserCreator

    # Check if user exists
    existing_user = session.query(User).filter_by(email="stefano@stefanobonanno.com").first()
    if existing_user:
        logger.info("Demo user 'stefano@stefanobonanno.com' already exists")
        return

    # Hash the password
    password = "demo2024"
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    # Create user
    user = User(
        email="stefano@stefanobonanno.com",
        password_hash=password_hash,
        name="Stefano Bonanno",
        is_active=True,
        is_admin=False,
    )
    session.add(user)
    session.commit()
    logger.info("Created demo user: stefano@stefanobonanno.com")

    # Link user to stefano_auto creator
    stefano_creator = session.query(Creator).filter_by(name="stefano_auto").first()
    if stefano_creator:
        # Check if link exists
        existing_link = (
            session.query(UserCreator)
            .filter_by(user_id=user.id, creator_id=stefano_creator.id)
            .first()
        )
        if not existing_link:
            user_creator = UserCreator(user_id=user.id, creator_id=stefano_creator.id, role="owner")
            session.add(user_creator)
            session.commit()
            logger.info("Linked user to creator 'stefano_auto'")


if __name__ == "__main__":
    init_database()
