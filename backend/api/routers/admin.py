"""
Admin endpoints for demo/testing purposes
"""
import os
import json
import shutil
import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

# Only enable if ENABLE_DEMO_RESET is set (default true for testing)
DEMO_RESET_ENABLED = os.getenv("ENABLE_DEMO_RESET", "true").lower() == "true"


@router.post("/reset-db")
async def reset_all_data():
    """
    Reset ALL data in the database and JSON files.
    Returns the creator to a fresh state with:
    - No leads, messages, products, sequences
    - Bot set to Paused
    - Onboarding at 0%
    """
    if not DEMO_RESET_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Demo reset is disabled. Set ENABLE_DEMO_RESET=true to enable."
        )

    results = {
        "database": {},
        "json_files": {},
        "status": "success"
    }

    # 1. Reset PostgreSQL database using SQLAlchemy
    try:
        from api.database import DATABASE_URL, engine, SessionLocal
        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                # Import models
                from api.models import Creator, Lead, Message, Product, NurturingSequence, KnowledgeBase

                # Delete in correct order (foreign key constraints)
                msg_count = session.query(Message).delete()
                results["database"]["messages"] = msg_count

                lead_count = session.query(Lead).delete()
                results["database"]["leads"] = lead_count

                prod_count = session.query(Product).delete()
                results["database"]["products"] = prod_count

                seq_count = session.query(NurturingSequence).delete()
                results["database"]["nurturing_sequences"] = seq_count

                kb_count = session.query(KnowledgeBase).delete()
                results["database"]["knowledge_base"] = kb_count

                # Reset all creators to bot_active=False
                creators = session.query(Creator).all()
                for creator in creators:
                    creator.bot_active = False
                results["database"]["creators_reset"] = len(creators)

                session.commit()
                logger.info(f"Database reset complete: {results['database']}")

            except Exception as e:
                session.rollback()
                logger.error(f"Database reset failed: {e}")
                results["database"]["error"] = str(e)
            finally:
                session.close()
    except Exception as e:
        logger.warning(f"Database not available: {e}")
        results["database"]["error"] = str(e)

    # 2. Reset JSON files
    data_dirs = [
        Path("data"),
        Path("data/creators"),
        Path("data/products"),
        Path("data/followers"),
        Path("data/nurturing"),
        Path("data/payments"),
        Path("data/analytics"),
        Path("data/gdpr"),
        Path("data/calendar"),
    ]

    json_deleted = 0
    for data_dir in data_dirs:
        if data_dir.exists():
            for json_file in data_dir.glob("*.json"):
                try:
                    # Reset file to empty state based on filename
                    if "leads" in json_file.name:
                        json_file.write_text('{"leads": []}')
                    elif "messages" in json_file.name:
                        json_file.write_text('{"messages": []}')
                    elif "conversations" in json_file.name:
                        json_file.write_text('{"conversations": []}')
                    elif "products" in json_file.name:
                        json_file.write_text('{"products": []}')
                    elif "sales" in json_file.name:
                        json_file.write_text('{"clicks": [], "sales": []}')
                    elif "metrics" in json_file.name:
                        json_file.write_text('{"messages_today": 0, "leads_today": 0, "hot_leads_count": 0, "total_messages": 0, "total_leads": 0}')
                    elif "followups" in json_file.name:
                        # Followups files are plain arrays
                        json_file.write_text('[]')
                    elif "nurturing" in json_file.name or "sequences" in json_file.name:
                        json_file.write_text('{"sequences": [], "enrolled": []}')
                    elif "payments" in json_file.name or "purchases" in json_file.name:
                        json_file.write_text('{"purchases": [], "revenue": 0}')
                    elif "config" in json_file.name:
                        # Reset config but keep basic info, set bot to inactive
                        try:
                            with open(json_file) as f:
                                config = json.load(f)
                            config["clone_active"] = False
                            config["is_active"] = False
                            config.pop("products", None)
                            json_file.write_text(json.dumps(config, indent=2))
                        except:
                            pass
                    else:
                        # Generic reset - empty object or array
                        json_file.write_text('{}')
                    json_deleted += 1
                except Exception as e:
                    logger.warning(f"Failed to reset {json_file}: {e}")

    # Also clean follower subdirectories
    followers_dir = Path("data/followers")
    if followers_dir.exists():
        for creator_dir in followers_dir.iterdir():
            if creator_dir.is_dir():
                try:
                    shutil.rmtree(creator_dir)
                    json_deleted += 1
                except Exception as e:
                    logger.warning(f"Failed to clean {creator_dir}: {e}")

    results["json_files"]["reset_count"] = json_deleted

    logger.info(f"Full reset complete: {results}")
    return results


@router.post("/reset-creator/{creator_id}")
async def reset_creator(creator_id: str):
    """
    Full reset for a creator - empties everything for demo.

    Resets:
    - All leads and conversations/messages
    - All products
    - All nurturing sequences
    - Knowledge base
    - Tone profile
    - RAG content index
    - Bot status (paused)
    - Onboarding status (not completed)

    Keeps:
    - Creator record (user, credentials, connections)
    - Instagram/WhatsApp tokens
    """
    if not DEMO_RESET_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Demo reset is disabled. Set ENABLE_DEMO_RESET=true to enable."
        )

    results = {
        "creator_id": creator_id,
        "deleted": {
            "leads": 0,
            "messages": 0,
            "products": 0,
            "sequences": 0,
            "knowledge_base": 0,
            "email_tracking": 0,
            "platform_identities": 0,
            "tone_profile": False,
            "rag_documents": 0,
            "bot_paused": False,
            "onboarding_reset": False
        }
    }

    # 1. Database reset using SQLAlchemy
    try:
        from api.database import DATABASE_URL, SessionLocal
        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import Creator, Lead, Message, Product, NurturingSequence, KnowledgeBase

                # Find creator by name
                creator = session.query(Creator).filter_by(name=creator_id).first()
                if not creator:
                    # Try by ID if it's a UUID
                    try:
                        from uuid import UUID
                        creator = session.query(Creator).filter_by(id=UUID(creator_id)).first()
                    except:
                        pass

                if creator:
                    creator_uuid = creator.id

                    # Delete messages for this creator's leads
                    leads = session.query(Lead).filter_by(creator_id=creator_uuid).all()
                    lead_ids = [l.id for l in leads]

                    if lead_ids:
                        msg_count = session.query(Message).filter(
                            Message.lead_id.in_(lead_ids)
                        ).delete(synchronize_session='fetch')
                        results["deleted"]["messages"] = msg_count

                    # Delete leads
                    lead_count = session.query(Lead).filter_by(creator_id=creator_uuid).delete()
                    results["deleted"]["leads"] = lead_count

                    # Delete products
                    prod_count = session.query(Product).filter_by(creator_id=creator_uuid).delete()
                    results["deleted"]["products"] = prod_count

                    # Delete sequences
                    seq_count = session.query(NurturingSequence).filter_by(creator_id=creator_uuid).delete()
                    results["deleted"]["sequences"] = seq_count

                    # Delete knowledge base
                    kb_count = session.query(KnowledgeBase).filter_by(creator_id=creator_uuid).delete()
                    results["deleted"]["knowledge_base"] = kb_count

                    # Delete email tracking for this creator
                    try:
                        from api.models import EmailAskTracking, PlatformIdentity
                        email_tracking_count = session.query(EmailAskTracking).filter_by(creator_id=creator_uuid).delete()
                        results["deleted"]["email_tracking"] = email_tracking_count

                        # Delete platform identities (but keep unified profiles - they're cross-creator)
                        identity_count = session.query(PlatformIdentity).filter_by(creator_id=creator_uuid).delete()
                        results["deleted"]["platform_identities"] = identity_count
                    except Exception as e:
                        logger.warning(f"Could not delete email tracking tables: {e}")

                    # Reset bot and onboarding status
                    creator.bot_active = False
                    creator.onboarding_completed = False
                    creator.copilot_mode = True  # Reset to default copilot mode
                    results["deleted"]["bot_paused"] = True
                    results["deleted"]["onboarding_reset"] = True

                    session.commit()
                    logger.info(f"Database reset complete for {creator_id}")
                else:
                    results["error"] = f"Creator '{creator_id}' not found in database"

            except Exception as e:
                session.rollback()
                logger.error(f"Database reset failed: {e}")
                results["error"] = str(e)
            finally:
                session.close()
    except Exception as e:
        logger.warning(f"Database not available: {e}")

    # 2. Delete Tone Profile
    try:
        from core.tone_service import delete_tone_profile, clear_cache
        if delete_tone_profile(creator_id):
            results["deleted"]["tone_profile"] = True
            logger.info(f"Tone profile deleted for {creator_id}")
        clear_cache(creator_id)
    except Exception as e:
        logger.warning(f"Could not delete tone profile: {e}")

    # 3. Clear RAG documents for this creator
    try:
        from core.rag import get_hybrid_rag
        rag = get_hybrid_rag()
        deleted_docs = rag.delete_by_creator(creator_id)
        results["deleted"]["rag_documents"] = deleted_docs
        logger.info(f"RAG documents deleted for {creator_id}: {deleted_docs}")
    except Exception as e:
        logger.warning(f"Could not clear RAG: {e}")

    # 4. JSON files reset
    data_dir = Path("data")
    json_patterns = [
        f"leads_{creator_id}.json",
        f"messages_{creator_id}.json",
        f"conversations_{creator_id}.json",
        f"metrics_{creator_id}.json",
        f"sales_{creator_id}.json",
        f"{creator_id}_products.json",
        f"{creator_id}_config.json",
        f"{creator_id}_sales.json",
    ]

    for pattern in json_patterns:
        # Check in data dir and subdirs
        for subdir in ["", "creators", "products", "followers"]:
            filepath = data_dir / subdir / pattern if subdir else data_dir / pattern
            if filepath.exists():
                try:
                    if "products" in pattern:
                        filepath.write_text('[]')
                    elif "config" in pattern:
                        try:
                            with open(filepath) as f:
                                config = json.load(f)
                            config["clone_active"] = False
                            config["is_active"] = False
                            filepath.write_text(json.dumps(config, indent=2))
                        except:
                            filepath.unlink()
                    else:
                        filepath.unlink()
                except Exception as e:
                    logger.warning(f"Failed to reset {filepath}: {e}")

    # 5. Clean follower directory for this creator
    followers_dir = data_dir / "followers" / creator_id
    if followers_dir.exists():
        try:
            shutil.rmtree(followers_dir)
        except:
            pass

    logger.info(f"Full reset complete for {creator_id}: {results}")
    return {"status": "success", **results}


@router.post("/reset-demo-data/{creator_id}")
async def reset_demo_data(creator_id: str):
    """
    Legacy endpoint - redirects to reset-creator.
    """
    return await reset_creator(creator_id)


@router.delete("/creators/{creator_name}")
async def delete_creator(creator_name: str):
    """
    Completely delete a creator and all associated data.
    Use with caution - this is irreversible!
    """
    if not DEMO_RESET_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="Demo reset is disabled. Set ENABLE_DEMO_RESET=true to enable."
        )

    results = {
        "creator_name": creator_name,
        "deleted": {
            "leads": 0,
            "messages": 0,
            "products": 0,
            "sequences": 0,
            "knowledge_base": 0,
            "creator": False
        }
    }

    try:
        from api.database import SessionLocal
        session = SessionLocal()
        try:
            from api.models import Creator, Lead, Message, Product, NurturingSequence, KnowledgeBase

            # Find creator by name
            creator = session.query(Creator).filter_by(name=creator_name).first()
            if not creator:
                raise HTTPException(status_code=404, detail=f"Creator '{creator_name}' not found")

            creator_uuid = creator.id

            # Delete messages for this creator's leads
            leads = session.query(Lead).filter_by(creator_id=creator_uuid).all()
            lead_ids = [l.id for l in leads]

            if lead_ids:
                msg_count = session.query(Message).filter(
                    Message.lead_id.in_(lead_ids)
                ).delete(synchronize_session='fetch')
                results["deleted"]["messages"] = msg_count

            # Delete leads
            lead_count = session.query(Lead).filter_by(creator_id=creator_uuid).delete()
            results["deleted"]["leads"] = lead_count

            # Delete products
            prod_count = session.query(Product).filter_by(creator_id=creator_uuid).delete()
            results["deleted"]["products"] = prod_count

            # Delete sequences
            seq_count = session.query(NurturingSequence).filter_by(creator_id=creator_uuid).delete()
            results["deleted"]["sequences"] = seq_count

            # Delete knowledge base
            kb_count = session.query(KnowledgeBase).filter_by(creator_id=creator_uuid).delete()
            results["deleted"]["knowledge_base"] = kb_count

            # Delete email tracking and platform identities
            try:
                from api.models import EmailAskTracking, PlatformIdentity
                session.query(EmailAskTracking).filter_by(creator_id=creator_uuid).delete()
                session.query(PlatformIdentity).filter_by(creator_id=creator_uuid).delete()
            except Exception as e:
                logger.warning(f"Could not delete email tracking: {e}")

            # Delete the creator itself
            session.delete(creator)
            results["deleted"]["creator"] = True

            session.commit()
            logger.info(f"Creator '{creator_name}' deleted completely")

        except HTTPException:
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Delete creator failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            session.close()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Clean up tone profile and RAG
    try:
        from core.tone_service import delete_tone_profile, clear_cache
        delete_tone_profile(creator_name)
        clear_cache(creator_name)
    except:
        pass

    try:
        from core.rag import get_hybrid_rag
        rag = get_hybrid_rag()
        rag.delete_by_creator(creator_name)
    except:
        pass

    return {"status": "success", **results}


@router.post("/run-migration/email-capture")
async def run_email_capture_migration():
    """
    Run migration to add email capture tables and columns.
    Safe to run multiple times (uses IF NOT EXISTS).
    """
    try:
        from api.database import SessionLocal
        from sqlalchemy import text

        session = SessionLocal()
        try:
            # Add email_capture_config column
            session.execute(text("""
                ALTER TABLE creators
                ADD COLUMN IF NOT EXISTS email_capture_config JSONB DEFAULT NULL
            """))

            # Create unified_profiles table
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS unified_profiles (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    email VARCHAR(255) UNIQUE NOT NULL,
                    name VARCHAR(255),
                    phone VARCHAR(50),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))

            # Create platform_identities table
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS platform_identities (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    unified_profile_id UUID REFERENCES unified_profiles(id),
                    creator_id UUID REFERENCES creators(id),
                    platform VARCHAR(50) NOT NULL,
                    platform_user_id VARCHAR(255) NOT NULL,
                    username VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))

            # Create unique index
            session.execute(text("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_platform_identity_unique
                ON platform_identities(platform, platform_user_id)
            """))

            # Create email_ask_tracking table
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS email_ask_tracking (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    creator_id UUID REFERENCES creators(id),
                    platform VARCHAR(50) NOT NULL,
                    platform_user_id VARCHAR(255) NOT NULL,
                    ask_level INTEGER DEFAULT 0,
                    last_asked_at TIMESTAMP WITH TIME ZONE,
                    declined_count INTEGER DEFAULT 0,
                    captured_email VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                )
            """))

            # Create index for fast lookups
            session.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_email_ask_tracking_lookup
                ON email_ask_tracking(platform, platform_user_id)
            """))

            session.commit()
            logger.info("Email capture migration completed successfully")

            return {
                "status": "success",
                "message": "Migration completed",
                "tables_created": [
                    "unified_profiles",
                    "platform_identities",
                    "email_ask_tracking"
                ],
                "columns_added": [
                    "creators.email_capture_config"
                ]
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@router.post("/refresh-all-tokens")
async def refresh_all_instagram_tokens():
    """
    Cron job: Revisar todos los tokens de Instagram y refrescar los que expiran pronto.

    Diseñado para ser llamado diariamente por un cron job.

    Refresca tokens que expiran en menos de 7 días.
    Los tokens long-lived duran 60 días y se pueden refrescar indefinidamente.
    """
    try:
        from core.token_refresh_service import refresh_all_creator_tokens
        from api.database import SessionLocal

        session = SessionLocal()
        try:
            result = await refresh_all_creator_tokens(session)
            return {
                "status": "success",
                **result
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@router.post("/refresh-token/{creator_id}")
async def refresh_creator_token(creator_id: str):
    """
    Refrescar el token de Instagram de un creator específico.

    Args:
        creator_id: Nombre o UUID del creator

    Returns:
        Estado del refresh (success/skip/error)
    """
    try:
        from core.token_refresh_service import check_and_refresh_if_needed
        from api.database import SessionLocal

        session = SessionLocal()
        try:
            result = await check_and_refresh_if_needed(creator_id, session)
            return {
                "status": "success" if result.get("success") else "error",
                **result
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Token refresh failed for {creator_id}: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@router.post("/exchange-token/{creator_id}")
async def exchange_short_lived_token(creator_id: str, short_lived_token: str):
    """
    Convertir un token short-lived (1-2h) a long-lived (60 días).

    Usar después del OAuth flow para obtener un token duradero.

    Args:
        creator_id: Nombre o UUID del creator
        short_lived_token: Token de corta duración del OAuth

    Returns:
        Nuevo token long-lived y fecha de expiración
    """
    try:
        from core.token_refresh_service import exchange_for_long_lived_token
        from api.database import SessionLocal
        from sqlalchemy import text

        # Exchange token
        new_token_data = await exchange_for_long_lived_token(short_lived_token)

        if not new_token_data:
            return {
                "status": "error",
                "error": "Failed to exchange token. Check META_APP_SECRET is configured."
            }

        # Save to database
        session = SessionLocal()
        try:
            session.execute(
                text("""
                    UPDATE creators
                    SET instagram_token = :token,
                        instagram_token_expires_at = :expires_at
                    WHERE id::text = :cid OR name = :cid
                """),
                {
                    "token": new_token_data["token"],
                    "expires_at": new_token_data["expires_at"],
                    "cid": creator_id
                }
            )
            session.commit()

            return {
                "status": "success",
                "token_prefix": new_token_data["token"][:20] + "...",
                "expires_at": new_token_data["expires_at"].isoformat(),
                "expires_in_days": new_token_data["expires_in"] // 86400
            }
        finally:
            session.close()

    except Exception as e:
        logger.error(f"Token exchange failed for {creator_id}: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/demo-status")
async def get_demo_status():
    """Check if demo reset is enabled and get current data counts"""
    counts = {}

    try:
        from api.database import DATABASE_URL, SessionLocal
        if DATABASE_URL and SessionLocal:
            session = SessionLocal()
            try:
                from api.models import Creator, Lead, Message, Product, NurturingSequence

                counts["creators"] = session.query(Creator).count()
                counts["leads"] = session.query(Lead).count()
                counts["messages"] = session.query(Message).count()
                counts["products"] = session.query(Product).count()
                counts["sequences"] = session.query(NurturingSequence).count()

                # Get bot status and onboarding status
                creators = session.query(Creator).all()
                counts["creator_statuses"] = {
                    c.name: {
                        "bot_active": c.bot_active,
                        "onboarding_completed": c.onboarding_completed,
                        "copilot_mode": c.copilot_mode,
                        "has_instagram": bool(c.instagram_token),
                    }
                    for c in creators
                }

            finally:
                session.close()
    except Exception as e:
        counts["db_error"] = str(e)

    # Check tone profiles
    try:
        from core.tone_service import list_profiles
        counts["tone_profiles"] = list_profiles()
    except Exception as e:
        counts["tone_profiles_error"] = str(e)

    # Check RAG documents
    try:
        from core.rag import get_hybrid_rag
        rag = get_hybrid_rag()
        counts["rag_documents"] = rag.count()
    except Exception as e:
        counts["rag_error"] = str(e)

    return {
        "demo_reset_enabled": DEMO_RESET_ENABLED,
        "counts": counts,
        "endpoints": {
            "reset_all": "POST /admin/reset-db",
            "reset_creator": "POST /admin/reset-creator/{creator_id}",
            "demo_status": "GET /admin/demo-status"
        }
    }


@router.post("/rescore-leads/{creator_id}")
async def rescore_leads(creator_id: str):
    """
    Re-categorizar todos los leads usando el sistema de embudo estándar.

    Categorías:
    - nuevo: Acaba de llegar, sin señales
    - interesado: Muestra curiosidad, hace preguntas
    - caliente: Pregunta precio o quiere comprar
    - cliente: Ya compró (requiere flag manual o webhook)
    - fantasma: Sin respuesta 7+ días

    Args:
        creator_id: Nombre o UUID del creator

    Returns:
        Estadísticas de leads actualizados por categoría
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message
        from sqlalchemy import text
        from core.lead_categorization import (
            calcular_categoria,
            categoria_a_status_legacy,
            CATEGORIAS_CONFIG
        )

        session = SessionLocal()
        try:
            # Get creator
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                creator = session.query(Creator).filter(
                    text("id::text = :cid")
                ).params(cid=creator_id).first()

            if not creator:
                return {"status": "error", "error": f"Creator not found: {creator_id}"}

            leads = session.query(Lead).filter_by(creator_id=creator.id).all()

            stats = {
                "total_leads": len(leads),
                "leads_updated": 0,
                "por_categoria": {
                    "nuevo": 0,
                    "interesado": 0,
                    "caliente": 0,
                    "cliente": 0,
                    "fantasma": 0
                },
                "details": []
            }

            for lead in leads:
                messages = session.query(Message).filter_by(lead_id=lead.id).order_by(Message.created_at).all()

                # Convertir a formato esperado por calcular_categoria
                mensajes_dict = [
                    {"role": m.role, "content": m.content or ""}
                    for m in messages
                ]

                # Obtener último mensaje del lead para detectar fantasma
                mensajes_usuario = [m for m in messages if m.role == "user"]
                ultimo_msg_lead = mensajes_usuario[-1].created_at if mensajes_usuario else None

                # Obtener última interacción (cualquier mensaje)
                ultima_interaccion = messages[-1].created_at if messages else None

                # Verificar si es cliente (por ahora manual, luego webhook)
                es_cliente = getattr(lead, 'has_purchased', False) if hasattr(lead, 'has_purchased') else False

                # Calcular categoría
                resultado = calcular_categoria(
                    mensajes=mensajes_dict,
                    es_cliente=es_cliente,
                    ultimo_mensaje_lead=ultimo_msg_lead,
                    dias_fantasma=7,
                    lead_created_at=lead.created_at,
                    ultima_interaccion=ultima_interaccion
                )

                # Convertir a status legacy para compatibilidad con frontend actual
                new_status = categoria_a_status_legacy(resultado.categoria)

                # Guardar cambios
                old_status = lead.status
                old_intent = lead.purchase_intent

                lead.status = new_status
                lead.purchase_intent = resultado.intent_score

                stats["leads_updated"] += 1
                stats["por_categoria"][resultado.categoria] += 1

                stats["details"].append({
                    "username": lead.username,
                    "categoria": resultado.categoria,
                    "status_legacy": new_status,
                    "old_status": old_status,
                    "intent_score": resultado.intent_score,
                    "old_intent": old_intent,
                    "razones": resultado.razones,
                    "keywords": resultado.keywords_detectados[:5],
                    "messages_count": len(messages)
                })

            session.commit()
            logger.info(f"[Rescore] Updated {stats['leads_updated']} leads for {creator_id}")

            return {
                "status": "success",
                "creator_id": creator_id,
                **stats
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Rescore failed for {creator_id}: {e}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/lead-categories")
async def get_lead_categories():
    """
    Obtener configuración de categorías de leads para el frontend.

    Retorna colores, iconos, labels y descripciones de cada categoría.
    """
    from core.lead_categorization import CATEGORIAS_CONFIG
    return {
        "status": "success",
        "categories": CATEGORIAS_CONFIG
    }


@router.delete("/cleanup-test-leads/{creator_id}")
async def cleanup_test_leads(creator_id: str):
    """
    Eliminar leads de test y leads sin username.

    Elimina:
    - Leads sin username (NULL o vacío)
    - Leads con username que empieza con 'test'
    - Leads con platform_user_id que empieza con 'test'
    """
    try:
        from api.database import SessionLocal
        from api.models import Creator, Lead, Message
        from sqlalchemy import or_, text

        session = SessionLocal()
        try:
            # Get creator
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"status": "error", "error": f"Creator not found: {creator_id}"}

            # Find test leads
            test_leads = session.query(Lead).filter(
                Lead.creator_id == creator.id,
                or_(
                    Lead.username == None,
                    Lead.username == "",
                    Lead.username.like("test%"),
                    Lead.platform_user_id.like("test%")
                )
            ).all()

            lead_ids = [l.id for l in test_leads]

            if not lead_ids:
                return {
                    "status": "success",
                    "message": "No test leads found",
                    "deleted_leads": 0,
                    "deleted_messages": 0
                }

            # Delete messages first (foreign key)
            deleted_messages = session.query(Message).filter(
                Message.lead_id.in_(lead_ids)
            ).delete(synchronize_session=False)

            # Delete leads
            deleted_leads = session.query(Lead).filter(
                Lead.id.in_(lead_ids)
            ).delete(synchronize_session=False)

            session.commit()

            logger.info(f"[Cleanup] Deleted {deleted_leads} test leads and {deleted_messages} messages for {creator_id}")

            return {
                "status": "success",
                "creator_id": creator_id,
                "deleted_leads": deleted_leads,
                "deleted_messages": deleted_messages
            }

        finally:
            session.close()

    except Exception as e:
        logger.error(f"Cleanup failed for {creator_id}: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@router.get("/debug-instagram-api/{creator_id}")
async def debug_instagram_api(creator_id: str):
    """
    Debug: Ver qué retorna la API de Instagram para conversaciones y mensajes.
    """
    import httpx

    try:
        from api.database import SessionLocal
        from api.models import Creator

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"error": f"Creator not found: {creator_id}"}

            if not creator.instagram_token:
                return {"error": "No Instagram token"}

            ig_user_id = creator.instagram_user_id or creator.instagram_page_id
            access_token = creator.instagram_token
            api_base = "https://graph.instagram.com/v21.0"

            results = {
                "ig_user_id": ig_user_id,
                "conversations": [],
                "sample_messages": []
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                # Get conversations
                conv_url = f"{api_base}/{ig_user_id}/conversations"
                conv_resp = await client.get(conv_url, params={
                    "access_token": access_token,
                    "limit": 5
                })

                if conv_resp.status_code != 200:
                    results["conversations_error"] = conv_resp.json()
                    return results

                conv_data = conv_resp.json()
                conversations = conv_data.get("data", [])
                results["conversations_count"] = len(conversations)

                # Try to get messages for first 3 conversations
                for i, conv in enumerate(conversations[:3]):
                    conv_id = conv.get("id")
                    conv_info = {"conv_id": conv_id, "conv_data": conv}

                    # Get messages
                    msg_url = f"{api_base}/{conv_id}/messages"
                    msg_resp = await client.get(msg_url, params={
                        "fields": "id,message,from,to,created_time",
                        "access_token": access_token,
                        "limit": 3
                    })

                    if msg_resp.status_code != 200:
                        conv_info["messages_error"] = msg_resp.json()
                    else:
                        msg_data = msg_resp.json()
                        conv_info["messages"] = msg_data.get("data", [])
                        conv_info["messages_count"] = len(conv_info["messages"])

                    results["sample_messages"].append(conv_info)

            return results

        finally:
            session.close()

    except Exception as e:
        return {"error": str(e)}


@router.post("/simple-dm-sync/{creator_id}")
async def simple_dm_sync(creator_id: str, max_convs: int = 20):
    """
    Simple DM sync without complex rate limiting.
    Fetches messages and saves them directly.
    """
    import httpx
    from datetime import datetime

    results = {
        "conversations_processed": 0,
        "messages_saved": 0,
        "messages_empty": 0,
        "messages_duplicate": 0,
        "leads_created": 0,
        "errors": []
    }

    try:
        from api.database import DATABASE_URL, SessionLocal
        from api.models import Creator, Lead, Message

        if not DATABASE_URL or not SessionLocal:
            return {"error": "Database not configured"}

        session = SessionLocal()
        try:
            creator = session.query(Creator).filter_by(name=creator_id).first()
            if not creator:
                return {"error": f"Creator not found: {creator_id}"}

            if not creator.instagram_token:
                return {"error": "Instagram token not configured"}

            ig_user_id = creator.instagram_user_id or creator.instagram_page_id
            access_token = creator.instagram_token
            api_base = "https://graph.instagram.com/v21.0"

            async with httpx.AsyncClient(timeout=60.0) as client:
                # Get conversations
                conv_resp = await client.get(
                    f"{api_base}/{ig_user_id}/conversations",
                    params={"access_token": access_token, "limit": max_convs}
                )

                if conv_resp.status_code != 200:
                    return {"error": f"Conversations API error: {conv_resp.json()}"}

                conversations = conv_resp.json().get("data", [])

                for conv in conversations:
                    conv_id = conv.get("id")
                    if not conv_id:
                        continue

                    try:
                        # Get messages for this conversation
                        msg_resp = await client.get(
                            f"{api_base}/{conv_id}/messages",
                            params={
                                "fields": "id,message,from,to,created_time",
                                "access_token": access_token,
                                "limit": 50
                            }
                        )

                        if msg_resp.status_code != 200:
                            error_data = msg_resp.json().get("error", {})
                            # Check for rate limit
                            if error_data.get("code") in [4, 17]:
                                results["errors"].append(f"Rate limit hit at conv {results['conversations_processed']}")
                                break
                            continue

                        messages = msg_resp.json().get("data", [])
                        if not messages:
                            continue

                        # Find the follower (non-creator participant)
                        follower_id = None
                        follower_username = None

                        for msg in messages:
                            from_data = msg.get("from", {})
                            from_id = from_data.get("id")
                            if from_id and from_id != ig_user_id:
                                follower_id = from_id
                                follower_username = from_data.get("username", "unknown")
                                break

                        if not follower_id:
                            # Check "to" field
                            for msg in messages:
                                to_data = msg.get("to", {}).get("data", [])
                                for recipient in to_data:
                                    if recipient.get("id") != ig_user_id:
                                        follower_id = recipient.get("id")
                                        follower_username = recipient.get("username", "unknown")
                                        break
                                if follower_id:
                                    break

                        if not follower_id:
                            continue

                        # Get or create lead
                        lead = session.query(Lead).filter_by(
                            creator_id=creator.id,
                            platform="instagram",
                            platform_user_id=follower_id
                        ).first()

                        if not lead:
                            lead = Lead(
                                creator_id=creator.id,
                                platform="instagram",
                                platform_user_id=follower_id,
                                username=follower_username,
                                status="new"
                            )
                            session.add(lead)
                            session.commit()
                            results["leads_created"] += 1

                        # Save messages
                        for msg in messages:
                            msg_id = msg.get("id")
                            msg_text = msg.get("message", "")

                            if not msg_text or not msg_id:
                                results["messages_empty"] += 1
                                continue

                            # Check if already exists
                            existing = session.query(Message).filter_by(
                                platform_message_id=msg_id
                            ).first()

                            if existing:
                                results["messages_duplicate"] += 1
                                continue

                            from_data = msg.get("from", {})
                            is_from_creator = from_data.get("id") == ig_user_id
                            role = "assistant" if is_from_creator else "user"

                            new_msg = Message(
                                lead_id=lead.id,
                                role=role,
                                content=msg_text,
                                platform="instagram",
                                platform_message_id=msg_id
                            )

                            # Parse timestamp
                            msg_time = msg.get("created_time")
                            if msg_time:
                                try:
                                    new_msg.created_at = datetime.fromisoformat(
                                        msg_time.replace("+0000", "+00:00")
                                    )
                                except:
                                    pass

                            session.add(new_msg)
                            results["messages_saved"] += 1

                        session.commit()
                        results["conversations_processed"] += 1

                    except Exception as e:
                        results["errors"].append(f"Conv error: {str(e)}")
                        continue

            return {"status": "success", **results}

        finally:
            session.close()

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e), **results}
