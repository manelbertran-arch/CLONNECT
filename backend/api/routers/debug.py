"""
Debug Router - Diagnostic and debugging endpoints
Extracted from main.py as part of refactoring
"""
import logging
import os

import httpx
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debug", tags=["debug"])

# Database imports
from api.database import DATABASE_URL, SessionLocal

# Try to import BookingLinkModel
try:
    from api.models import BookingLink as BookingLinkModel
except ImportError:
    BookingLinkModel = None


# ---------------------------------------------------------
# DATABASE DEBUG
# ---------------------------------------------------------
@router.get("/database")
async def debug_database():
    """
    Debug endpoint to check database connectivity and booking_links table.
    """
    result = {
        "DATABASE_URL_configured": DATABASE_URL is not None and DATABASE_URL != "",
        "SessionLocal_available": SessionLocal is not None,
        "BookingLinkModel_available": BookingLinkModel is not None,
        "tables": [],
        "booking_links_count": 0,
        "booking_links_sample": [],
        "error": None,
    }

    if SessionLocal and BookingLinkModel:
        try:
            from sqlalchemy import text

            db = SessionLocal()
            try:
                # Check tables
                tables_result = db.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                    )
                )
                result["tables"] = [row[0] for row in tables_result.fetchall()]

                # Check booking_links
                if "booking_links" in result["tables"]:
                    count_result = db.execute(text("SELECT COUNT(*) FROM booking_links"))
                    result["booking_links_count"] = count_result.scalar()

                    # Get sample data
                    sample_result = db.execute(
                        text(
                            "SELECT id, creator_id, meeting_type, title, platform FROM booking_links LIMIT 5"
                        )
                    )
                    result["booking_links_sample"] = [
                        {
                            "id": str(row[0]),
                            "creator_id": row[1],
                            "meeting_type": row[2],
                            "title": row[3],
                            "platform": row[4],
                        }
                        for row in sample_result.fetchall()
                    ]
            finally:
                db.close()
        except Exception as e:
            result["error"] = str(e)
            import traceback

            result["traceback"] = traceback.format_exc()
    else:
        result["error"] = "Database not configured - SessionLocal or BookingLinkModel is None"

    return result


@router.get("/products/{creator_name}")
async def debug_products(creator_name: str):
    """Debug endpoint to check products for a creator."""
    result = {"creator_name": creator_name, "creator_found": False, "products": [], "error": None}
    if SessionLocal:
        try:
            from sqlalchemy import text

            db = SessionLocal()
            try:
                # Find creator
                creator_result = db.execute(
                    text("SELECT id, name FROM creators WHERE name = :name"), {"name": creator_name}
                )
                creator_row = creator_result.fetchone()
                if creator_row:
                    result["creator_found"] = True
                    result["creator_id"] = str(creator_row[0])
                    # Get products with new taxonomy fields
                    products_result = db.execute(
                        text(
                            "SELECT id, name, price, currency, category, product_type, is_free, short_description, payment_link, is_active FROM products WHERE creator_id = :cid"
                        ),
                        {"cid": creator_row[0]},
                    )
                    result["products"] = [
                        {
                            "id": str(row[0]),
                            "name": row[1],
                            "price": row[2],
                            "currency": row[3],
                            "category": row[4],
                            "product_type": row[5],
                            "is_free": row[6],
                            "short_description": row[7],
                            "payment_link": row[8],
                            "is_active": row[9],
                        }
                        for row in products_result.fetchall()
                    ]
                    result["count"] = len(result["products"])
            finally:
                db.close()
        except Exception as e:
            result["error"] = str(e)
            import traceback

            result["traceback"] = traceback.format_exc()
    return result


@router.post("/insert-booking-link")
async def debug_insert_booking_link():
    """
    Direct test insert to booking_links - bypasses all conditions.
    This is for debugging only.
    """
    result = {
        "success": False,
        "error": None,
        "link_id": None,
        "SessionLocal": SessionLocal is not None,
        "BookingLinkModel": BookingLinkModel is not None,
    }

    # Try direct SQL insert first
    if SessionLocal:
        try:
            import uuid

            from sqlalchemy import text

            db = SessionLocal()
            try:
                test_id = str(uuid.uuid4())

                # Direct SQL INSERT
                db.execute(
                    text(
                        """
                    INSERT INTO booking_links (id, creator_id, meeting_type, title, duration_minutes, platform, is_active)
                    VALUES (:id, :creator_id, :meeting_type, :title, :duration, :platform, :is_active)
                """
                    ),
                    {
                        "id": test_id,
                        "creator_id": "test_debug",
                        "meeting_type": "debug_test",
                        "title": "Debug Test Link",
                        "duration": 30,
                        "platform": "manual",
                        "is_active": True,
                    },
                )
                db.commit()

                result["success"] = True
                result["link_id"] = test_id
                result["message"] = "Direct SQL INSERT worked!"

                # Verify it was inserted
                verify = db.execute(
                    text("SELECT COUNT(*) FROM booking_links WHERE creator_id = 'test_debug'")
                )
                result["verify_count"] = verify.scalar()

            finally:
                db.close()
        except Exception as e:
            result["error"] = str(e)
            import traceback

            result["traceback"] = traceback.format_exc()
    else:
        result["error"] = "SessionLocal is None - database not configured"

    return result


@router.get("/full-diagnosis")
async def full_diagnosis():
    """
    COMPLETE SYSTEM DIAGNOSIS - Shows everything about the system state.
    Open this URL in browser to see what's happening.
    """
    import subprocess
    from datetime import datetime, timezone

    diagnosis = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server": {},
        "database": {},
        "telegram": {},
        "creator_stefano_auto": {},
        "environment": {},
        "recent_activity": {},
    }

    # === 1. SERVER STATUS ===
    diagnosis["server"] = {
        "status": "running",
        "python_version": os.popen("python --version 2>&1").read().strip(),
        "working_directory": os.getcwd(),
        "uptime_note": "Server is responding to requests",
    }

    # === 2. DATABASE STATUS ===
    db_status = {
        "DATABASE_URL_configured": bool(DATABASE_URL),
        "SessionLocal_available": SessionLocal is not None,
        "connection_test": "not_tested",
    }

    if SessionLocal:
        try:
            from api.models import Creator, Lead, Message
            from sqlalchemy import text

            session = SessionLocal()
            try:
                # Test connection
                session.execute(text("SELECT 1"))
                db_status["connection_test"] = "SUCCESS"

                # Get tables
                tables_result = session.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                    )
                )
                db_status["tables"] = [row[0] for row in tables_result.fetchall()]

                # Count creators
                creator_count = session.query(Creator).count()
                db_status["total_creators"] = creator_count

                # Count pending responses (Messages with status='pending_approval')
                pending_count = (
                    session.query(Message)
                    .filter_by(status="pending_approval", role="assistant")
                    .count()
                )
                db_status["total_pending_responses"] = pending_count

            finally:
                session.close()
        except Exception as e:
            db_status["connection_test"] = f"FAILED: {str(e)}"

    diagnosis["database"] = db_status

    # === 3. STEFANO_AUTO SPECIFIC ===
    stefano_status = {
        "exists": False,
        "copilot_mode": None,
        "bot_active": None,
        "pending_responses_count": 0,
        "last_pending_response": None,
    }

    if SessionLocal:
        try:
            from api.models import Creator, Lead, Message

            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name="stefano_auto").first()
                if creator:
                    stefano_status["exists"] = True
                    stefano_status["copilot_mode"] = getattr(creator, "copilot_mode", None)
                    stefano_status["bot_active"] = getattr(creator, "bot_active", None)

                    # Get pending responses for stefano_auto via Lead -> Message
                    pending = (
                        session.query(Message, Lead)
                        .join(Lead, Message.lead_id == Lead.id)
                        .filter(
                            Lead.creator_id == creator.id,
                            Message.status == "pending_approval",
                            Message.role == "assistant",
                        )
                        .order_by(Message.created_at.desc())
                        .all()
                    )

                    stefano_status["pending_responses_count"] = len(pending)

                    if pending:
                        msg, lead = pending[0]
                        # Get user message for context
                        user_msg = (
                            session.query(Message)
                            .filter(Message.lead_id == lead.id, Message.role == "user")
                            .order_by(Message.created_at.desc())
                            .first()
                        )

                        stefano_status["last_pending_response"] = {
                            "id": str(msg.id),
                            "created_at": msg.created_at.isoformat() if msg.created_at else None,
                            "user_message": (
                                user_msg.content[:50] if user_msg and user_msg.content else None
                            ),
                            "suggested_response": msg.content[:50] if msg.content else None,
                            "platform": lead.platform,
                        }
            finally:
                session.close()
        except Exception as e:
            stefano_status["error"] = str(e)

    diagnosis["creator_stefano_auto"] = stefano_status

    # === 4. TELEGRAM STATUS ===
    telegram_status = {
        "bot_token_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
        "registered_bots": [],
        "webhook_status": {},
    }

    try:
        from core.telegram_registry import get_telegram_registry

        registry = get_telegram_registry()
        bots = registry.list_bots()
        telegram_status["registered_bots"] = bots

        # Check webhook for each bot
        for bot in bots:
            bot_id = bot.get("bot_id")
            bot_token = registry.get_bot_token(bot_id)
            if bot_token:
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        response = await client.get(
                            f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
                        )
                        webhook_info = response.json()
                        if webhook_info.get("ok"):
                            telegram_status["webhook_status"][bot_id] = {
                                "url": webhook_info.get("result", {}).get("url", "NOT SET"),
                                "pending_updates": webhook_info.get("result", {}).get(
                                    "pending_update_count", 0
                                ),
                                "last_error": webhook_info.get("result", {}).get(
                                    "last_error_message"
                                ),
                            }
                except Exception as e:
                    telegram_status["webhook_status"][bot_id] = {"error": str(e)}
    except Exception as e:
        telegram_status["error"] = str(e)

    diagnosis["telegram"] = telegram_status

    # === 5. ENVIRONMENT (without sensitive values) ===
    env_vars = [
        "DATABASE_URL",
        "GROQ_API_KEY",
        "TELEGRAM_BOT_TOKEN",
        "RAILWAY_PUBLIC_URL",
        "RENDER_EXTERNAL_URL",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ]

    diagnosis["environment"] = {var: "SET" if os.getenv(var) else "NOT SET" for var in env_vars}

    # === 6. QUICK SUMMARY ===
    diagnosis["summary"] = {
        "database_ok": db_status.get("connection_test") == "SUCCESS",
        "stefano_exists": stefano_status.get("exists", False),
        "copilot_mode": stefano_status.get("copilot_mode"),
        "pending_count": stefano_status.get("pending_responses_count", 0),
        "telegram_bots": len(telegram_status.get("registered_bots", [])),
        "recommendation": "",
    }

    # Build recommendation
    if not stefano_status.get("exists"):
        diagnosis["summary"]["recommendation"] = "Creator stefano_auto doesn't exist in DB!"
    elif stefano_status.get("copilot_mode") == True:
        if stefano_status.get("pending_responses_count", 0) > 0:
            diagnosis["summary"][
                "recommendation"
            ] = f"System working! {stefano_status['pending_responses_count']} messages waiting for approval in Copilot dashboard."
        else:
            diagnosis["summary"][
                "recommendation"
            ] = "Copilot mode ON but no pending messages. Send a test message to the bot."
    elif stefano_status.get("copilot_mode") == False:
        diagnosis["summary"][
            "recommendation"
        ] = "Autopilot mode - bot should respond automatically."
    else:
        diagnosis["summary"][
            "recommendation"
        ] = "copilot_mode is NULL - defaulting to True (Copilot mode)."

    return diagnosis


@router.post("/test-telegram-flow")
async def test_telegram_flow():
    """
    Simulate a Telegram message flow and report each step.
    """
    steps = []

    # Step 1: Check creator exists
    creator_id = "stefano_auto"
    try:
        from api.models import Creator

        session = SessionLocal()
        creator = session.query(Creator).filter_by(name=creator_id).first()
        session.close()

        if creator:
            steps.append(
                {"step": "1. Find creator", "status": "OK", "detail": f"Found {creator_id}"}
            )
            copilot_mode = getattr(creator, "copilot_mode", True)
            steps.append(
                {
                    "step": "2. Check copilot_mode",
                    "status": "OK",
                    "detail": f"copilot_mode = {copilot_mode}",
                }
            )
        else:
            steps.append(
                {
                    "step": "1. Find creator",
                    "status": "FAIL",
                    "detail": f"Creator {creator_id} not found!",
                }
            )
            return {"steps": steps, "conclusion": "FAILED - Creator not found"}
    except Exception as e:
        steps.append({"step": "1. Find creator", "status": "ERROR", "detail": str(e)})
        return {"steps": steps, "conclusion": f"FAILED - {e}"}

    # Step 2: Try to generate a response
    try:
        from core.dm_agent_v2 import get_dm_agent

        agent = get_dm_agent(creator_id)
        steps.append(
            {
                "step": "3. Initialize DM Agent",
                "status": "OK",
                "detail": f"Agent ready for {creator_id}",
            }
        )

        # Process a test message
        response = await agent.process_dm(
            sender_id="test_diagnosis",
            message_text="hola, esto es una prueba de diagnóstico",
            message_id="diag_001",
            username="DiagnosticTest",
            name="Test User",
        )

        steps.append(
            {
                "step": "4. Generate response",
                "status": "OK",
                "detail": f"Intent: {response.intent.value if hasattr(response.intent, 'value') else response.intent}, Response: {response.response_text[:80]}...",
            }
        )
    except Exception as e:
        steps.append({"step": "3-4. DM Agent", "status": "ERROR", "detail": str(e)})
        return {"steps": steps, "conclusion": f"FAILED at DM Agent - {e}"}

    # Step 3: Check what would happen based on copilot_mode
    if copilot_mode:
        steps.append(
            {
                "step": "5. Copilot mode action",
                "status": "INFO",
                "detail": "Would save as pending_approval (not send immediately)",
            }
        )

        # Try to create a pending response
        try:
            from core.copilot_service import get_copilot_service

            copilot = get_copilot_service()

            pending = await copilot.create_pending_response(
                creator_id=creator_id,
                lead_id="",
                follower_id="test_diagnosis",
                platform="telegram",
                user_message="TEST - diagnostic message",
                user_message_id="diag_001",
                suggested_response=response.response_text,
                intent=(
                    response.intent.value
                    if hasattr(response.intent, "value")
                    else str(response.intent)
                ),
                confidence=0.95,
                username="DiagnosticTest",
                full_name="Test User",
            )

            steps.append(
                {
                    "step": "6. Create pending response",
                    "status": "OK",
                    "detail": f"Created pending ID: {pending.id}",
                }
            )
        except Exception as e:
            steps.append({"step": "6. Create pending", "status": "ERROR", "detail": str(e)})
    else:
        steps.append(
            {
                "step": "5. Autopilot mode action",
                "status": "INFO",
                "detail": "Would send response immediately via Telegram",
            }
        )

    return {
        "steps": steps,
        "conclusion": "SUCCESS - All steps passed",
        "copilot_mode": copilot_mode,
        "note": "If copilot_mode=True, messages go to dashboard for approval. Check /copilot/stefano_auto/pending",
    }


@router.get("/agent-config/{creator_id}")
async def debug_agent_config(creator_id: str):
    """Debug: ver qué config carga el DMAgent"""
    from core.dm_agent_v2 import DMResponderAgent

    agent = DMResponderAgent(creator_id=creator_id)
    vocab = agent.creator_config.get("clone_vocabulary", "")

    # Detect preset like dm_agent does
    vocab_lower = vocab.lower() if vocab else ""
    detected_preset = None
    if "trata de usted" in vocab_lower or "evita emojis" in vocab_lower:
        detected_preset = "profesional"
    elif "ve al grano" in vocab_lower or "llamadas a la acción" in vocab_lower:
        detected_preset = "vendedor"
    elif "posiciónate como experto" in vocab_lower or "da consejos prácticos" in vocab_lower:
        detected_preset = "mentor"
    elif "tutea siempre" in vocab_lower or "amigo de confianza" in vocab_lower:
        detected_preset = "amigo"

    return {
        "clone_tone": agent.creator_config.get("clone_tone"),
        "clone_name": agent.creator_config.get("clone_name"),
        "clone_vocabulary": vocab[:500] if vocab else "(empty)",
        "clone_vocabulary_length": len(vocab) if vocab else 0,
        "detected_preset": detected_preset,
        "name": agent.creator_config.get("name"),
        "config_keys": list(agent.creator_config.keys()),
    }


@router.get("/system-prompt/{creator_id}")
async def debug_system_prompt(creator_id: str):
    """Debug: ver el system prompt que genera el DMAgent"""
    from core.dm_agent_v2 import DMResponderAgent

    agent = DMResponderAgent(creator_id=creator_id)
    prompt = agent._build_system_prompt()
    return {"prompt": prompt[:2000]}  # Primeros 2000 chars


@router.get("/citations/debug/{creator_id}")
async def debug_citations(creator_id: str, query: str = "test"):
    """Debug endpoint to check citation content index"""
    from core.citation_service import get_citation_prompt_section, get_content_index

    debug_info = {
        "creator_id": creator_id,
        "query": query,
        "cwd": os.getcwd(),
        "data_dir_exists": os.path.exists("data"),
        "content_index_dir_exists": os.path.exists("data/content_index"),
        "creator_dir_exists": os.path.exists(f"data/content_index/{creator_id}"),
        "chunks_file_exists": os.path.exists(f"data/content_index/{creator_id}/chunks.json"),
        "initial_data_exists": os.path.exists("/app/initial_data"),
        "files_in_content_index": [],
        "chunks_count": 0,
        "search_results": [],
        "citation_prompt": "",
    }

    # List files in content_index
    try:
        if os.path.exists("data/content_index"):
            debug_info["files_in_content_index"] = os.listdir("data/content_index")
        if os.path.exists(f"data/content_index/{creator_id}"):
            debug_info["creator_files"] = os.listdir(f"data/content_index/{creator_id}")
    except Exception as e:
        debug_info["list_error"] = str(e)

    # Load index and check
    try:
        index = get_content_index(creator_id)
        debug_info["chunks_count"] = len(index.chunks)
        debug_info["index_loaded"] = index._loaded
        debug_info["posts_count"] = len(index.posts_metadata)

        # Search test
        if query:
            results = index.search(query, max_results=3)
            debug_info["search_results"] = [
                {"id": r["chunk_id"], "title": r.get("title"), "relevance": r["relevance_score"]}
                for r in results
            ]

            # Get citation prompt
            citation_prompt = get_citation_prompt_section(creator_id, query)
            debug_info["citation_prompt_length"] = len(citation_prompt)
            debug_info["citation_prompt_preview"] = citation_prompt[:500] if citation_prompt else ""

    except Exception as e:
        debug_info["index_error"] = str(e)

    return {"status": "ok", "debug": debug_info}
