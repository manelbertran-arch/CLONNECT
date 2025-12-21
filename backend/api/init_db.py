import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

def init_database():
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    if not DATABASE_URL:
        print("No DATABASE_URL - skipping DB init")
        return False
    
    try:
        from api.database import Base
        from api.models import Creator, Lead, Message, Product, NurturingSequence, KnowledgeBase
    except:
        from database import Base
        from models import Creator, Lead, Message, Product, NurturingSequence, KnowledgeBase
    
    engine = create_engine(DATABASE_URL)
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created!")
    
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
