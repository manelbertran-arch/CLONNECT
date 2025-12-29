import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Get DATABASE_URL and fix Railway's postgres:// to postgresql://
DATABASE_URL = os.getenv("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    print(f"Fixed DATABASE_URL scheme: postgres:// -> postgresql://")

print(f"DATABASE_URL configured: {bool(DATABASE_URL)}")

engine = None
SessionLocal = None

if DATABASE_URL:
    try:
        engine = create_engine(DATABASE_URL, echo=False)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        print(f"SQLAlchemy engine created successfully")
    except Exception as e:
        print(f"Failed to create SQLAlchemy engine: {e}")
        import traceback
        traceback.print_exc()

Base = declarative_base()

def get_db():
    if SessionLocal is None:
        raise Exception("Database not configured")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
