"""
Script para migrar datos JSON a PostgreSQL
"""
import os
import json
import glob
from datetime import datetime

def migrate_followers():
    """Migrar followers de JSON a PostgreSQL"""
    try:
        from api.database import DATABASE_URL
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from api.models import Creator, Lead, Message
        
        if not DATABASE_URL:
            print("No DATABASE_URL")
            return
        
        engine = create_engine(DATABASE_URL)
        session = Session(engine)
        
        # Obtener creator manel
        creator = session.query(Creator).filter_by(name="manel").first()
        if not creator:
            print("Creator manel not found")
            return
        
        # Buscar archivos JSON de followers
        json_files = glob.glob("data/followers/manel/*.json")
        print(f"Found {len(json_files)} follower files")
        
        migrated = 0
        for filepath in json_files:
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                
                follower_id = data.get("follower_id", "")
                if not follower_id or follower_id.startswith("obj_") or follower_id.startswith("test"):
                    continue
                
                # Verificar si ya existe
                existing = session.query(Lead).filter_by(
                    creator_id=creator.id,
                    platform_user_id=follower_id
                ).first()
                
                if existing:
                    print(f"  Skip {follower_id} (exists)")
                    continue
                
                # Determinar plataforma
                platform = "telegram" if follower_id.startswith("tg_") else "instagram"
                
                # Crear lead
                lead = Lead(
                    creator_id=creator.id,
                    platform=platform,
                    platform_user_id=follower_id,
                    username=data.get("username", ""),
                    full_name=data.get("name", ""),
                    status="lead" if data.get("is_lead") else "new",
                    score=int(data.get("purchase_intent_score", 0) * 100),
                    purchase_intent=data.get("purchase_intent_score", 0.0),
                    context={
                        "interests": data.get("interests", []),
                        "products_discussed": data.get("products_discussed", []),
                        "preferred_language": data.get("preferred_language", "es"),
                        "is_customer": data.get("is_customer", False)
                    }
                )
                session.add(lead)
                session.flush()
                
                # Migrar mensajes
                messages = data.get("last_messages", [])
                for msg in messages:
                    message = Message(
                        lead_id=lead.id,
                        role=msg.get("role", "user"),
                        content=msg.get("content", ""),
                        intent=msg.get("intent")
                    )
                    session.add(message)
                
                migrated += 1
                print(f"  Migrated {follower_id} with {len(messages)} messages")
                
            except Exception as e:
                print(f"  Error {filepath}: {e}")
        
        session.commit()
        print(f"\nMigrated {migrated} followers to PostgreSQL")
        session.close()
        
    except Exception as e:
        print(f"Migration error: {e}")

if __name__ == "__main__":
    migrate_followers()
