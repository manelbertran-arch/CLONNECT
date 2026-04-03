"""
Copilot actions — approve, discard, and auto-discard pending responses.

Handles the approval workflow (send message, update DB, fire learning hooks),
manual discard, and automatic discard when creator replies directly.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def approve_response_impl(
    service,
    creator_id: str,
    message_id: str,
    edited_text: Optional[str] = None,
    chosen_index: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Aprobar (y opcionalmente editar) una respuesta y enviarla.

    Returns:
        Dict con status y detalles del envío
    """
    from api.database import SessionLocal
    from api.models import Creator, Lead, Message

    session = SessionLocal()
    try:
        creator = session.query(Creator).filter_by(name=creator_id).first()
        if not creator:
            return {"success": False, "error": "Creator not found"}

        # Buscar el mensaje
        msg = session.query(Message).filter_by(id=message_id).first()
        if not msg:
            return {"success": False, "error": "Message not found"}

        if msg.status != "pending_approval":
            return {"success": False, "error": f"Message status is {msg.status}, not pending"}

        # Obtener lead
        lead = session.query(Lead).filter_by(id=msg.lead_id).first()
        if not lead:
            return {"success": False, "error": "Lead not found"}

        # Resolve chosen_index into edited_text if a non-default candidate was chosen
        if chosen_index is not None and edited_text is None:
            bon = (msg.msg_metadata or {}).get("best_of_n", {})
            candidates = bon.get("candidates", [])
            if 0 <= chosen_index < len(candidates):
                chosen_text = candidates[chosen_index]["content"]
                if chosen_text != msg.content:
                    edited_text = chosen_text

        # Determinar texto final
        final_text = edited_text if edited_text else msg.content
        was_edited = edited_text is not None and edited_text != msg.suggested_response

        # Send message — pass copilot_action so guard knows this is approved
        from core.copilot.messaging import send_message_impl

        send_result = await send_message_impl(
            service, creator=creator, lead=lead, text=final_text,
            copilot_action="edited" if was_edited else "approved",
        )

        if not send_result.get("success"):
            return {"success": False, "error": send_result.get("error", "Failed to send")}

        # Actualizar mensaje en DB
        now = datetime.now(timezone.utc)
        msg.content = final_text
        msg.status = "edited" if was_edited else "sent"
        msg.approved_at = now
        msg.approved_by = "creator"
        msg.platform_message_id = send_result.get("message_id")

        # Copilot tracking (Phase 2)
        msg.copilot_action = "edited" if was_edited else "approved"
        if msg.created_at:
            delta = now - msg.created_at
            msg.response_time_ms = int(delta.total_seconds() * 1000)
        if was_edited and msg.suggested_response:
            msg.edit_diff = service._calculate_edit_diff(
                msg.suggested_response, final_text
            )

        # Actualizar last_contact del lead
        lead.last_contact_at = now

        # Capture best_of_n BEFORE stripping (needed for preference pairs below)
        _meta = msg.msg_metadata or {}
        _bon_candidates = _meta.get("best_of_n", {}).get("candidates")

        # Persist lightweight BoN decision summary before stripping full candidates
        if _bon_candidates:
            _chosen_idx = chosen_index if chosen_index is not None else 0
            _meta["best_of_n_decision"] = {
                "chosen_index": _chosen_idx,
                "chosen_confidence": _bon_candidates[_chosen_idx].get("confidence") if _chosen_idx < len(_bon_candidates) else None,
                "n_candidates": len(_bon_candidates),
                "best_confidence": _bon_candidates[0].get("confidence") if _bon_candidates else None,
                "creator_overrode_best": _chosen_idx != 0,
            }

        # Strip best_of_n — no longer needed once decision is taken
        msg.msg_metadata = {k: v for k, v in _meta.items() if k != "best_of_n"}

        session.commit()

        # Autolearning hook: fire-and-forget rule extraction
        try:
            from services.autolearning_analyzer import analyze_creator_action

            asyncio.create_task(analyze_creator_action(
                action="edited" if was_edited else "approved",
                creator_id=creator_id,
                creator_db_id=creator.id,
                suggested_response=msg.suggested_response,
                final_response=final_text if was_edited else None,
                edit_diff=msg.edit_diff if was_edited else None,
                intent=msg.intent,
                lead_stage=lead.status,
                relationship_type=getattr(lead, "relationship_type", None),
                source_message_id=msg.id,
            ))
        except Exception as learn_err:
            logger.debug(f"[Copilot] Autolearning hook failed: {learn_err}")

        # Preference pairs hook: fire-and-forget via unified FeedbackCapture
        try:
            from services.feedback_store import capture as feedback_capture
            from api.models import Message as _Msg

            # BUG-1 fix: fetch preceding user message for training context
            _preceding = session.query(_Msg.content).filter(
                _Msg.lead_id == msg.lead_id, _Msg.role == "user",
                _Msg.created_at < msg.created_at,
            ).order_by(_Msg.created_at.desc()).first()
            _user_msg = _preceding[0] if _preceding else None

            _signal = "copilot_edit" if was_edited else "copilot_approve"
            asyncio.create_task(feedback_capture(
                signal_type=_signal,
                creator_db_id=creator.id,
                lead_id=msg.lead_id,
                user_message=_user_msg,
                bot_response=msg.suggested_response,
                creator_response=final_text if was_edited else None,
                metadata={
                    "source_message_id": msg.id,
                    "intent": msg.intent,
                    "lead_stage": lead.status,
                    "edit_diff": msg.edit_diff if was_edited else None,
                    "best_of_n_candidates": _bon_candidates,
                    "chosen_confidence": msg.confidence_score,
                    "rejected_confidence": msg.confidence_score if was_edited else None,
                },
            ))
        except Exception as pp_err:
            logger.debug(f"[Copilot] Preference pairs hook failed: {pp_err}")

        # Invalidate caches so approved message appears in conversation
        try:
            from api.cache import api_cache

            api_cache.invalidate(f"conversations:{creator_id}")
            api_cache.invalidate(f"follower_detail:{creator_id}:{lead.platform_user_id}")
        except Exception as cache_err:
            logger.debug(f"[Copilot] Cache invalidation failed: {cache_err}")

        # Notify frontend via SSE
        try:
            from api.routers.events import notify_creator

            await notify_creator(
                creator_id,
                "message_approved",
                {
                    "follower_id": lead.platform_user_id,
                    "message_id": str(msg.id),
                },
            )
        except Exception as sse_err:
            logger.debug(f"[Copilot] SSE notification failed: {sse_err}")

        # Update follower memory with the APPROVED response
        # (not saved during process_dm in copilot mode to prevent phantom context)
        try:
            from core.dm_agent_v2 import get_dm_agent

            agent = get_dm_agent(creator_id)
            follower = await agent.memory_store.get(
                creator_id, lead.platform_user_id
            )
            if follower:
                now_iso = datetime.now(timezone.utc).isoformat()
                follower.last_messages.append(
                    {"role": "assistant", "content": final_text, "timestamp": now_iso}
                )
                follower.last_messages = follower.last_messages[-20:]
                agent.memory_store._save_to_json(follower)
                logger.debug(f"[Copilot] Updated memory for {lead.platform_user_id}")
        except Exception as mem_err:
            logger.debug(f"[Copilot] Memory update failed (non-blocking): {mem_err}")

        logger.info(
            f"[Copilot] Approved and sent message {message_id} to {lead.platform_user_id}"
        )

        return {
            "success": True,
            "message_id": str(msg.id),
            "platform_message_id": send_result.get("message_id"),
            "was_edited": was_edited,
            "final_text": final_text,
        }

    except Exception as e:
        logger.error(f"[Copilot] Error approving response: {e}")
        session.rollback()
        return {"success": False, "error": str(e)}
    finally:
        session.close()


async def discard_response_impl(
    service, creator_id: str, message_id: str, discard_reason: str = None
) -> Dict[str, Any]:
    """Descartar una respuesta sin enviarla."""
    from api.database import SessionLocal
    from api.models import Message

    session = SessionLocal()
    try:
        msg = session.query(Message).filter_by(id=message_id).first()
        if not msg:
            return {"success": False, "error": "Message not found"}

        now = datetime.now(timezone.utc)
        msg.status = "discarded"
        msg.approved_at = now
        msg.approved_by = "creator"

        # Copilot tracking (Phase 2)
        msg.copilot_action = "discarded"
        if msg.created_at:
            delta = now - msg.created_at
            msg.response_time_ms = int(delta.total_seconds() * 1000)

        # Capture best_of_n BEFORE stripping (needed for preference pairs below)
        _meta = msg.msg_metadata or {}
        _bon_candidates = _meta.get("best_of_n", {}).get("candidates")

        # Persist lightweight BoN decision summary before stripping
        if _bon_candidates:
            _meta["best_of_n_decision"] = {
                "chosen_index": None,
                "n_candidates": len(_bon_candidates),
                "best_confidence": _bon_candidates[0].get("confidence") if _bon_candidates else None,
                "creator_overrode_best": True,
            }

        # Build clean metadata: strip best_of_n, optionally add discard_reason
        _meta_clean = {k: v for k, v in _meta.items() if k != "best_of_n"}
        if discard_reason:
            _meta_clean["discard_reason"] = discard_reason
            _meta_clean["discarded_at"] = now.isoformat()
        msg.msg_metadata = _meta_clean

        session.commit()

        # Autolearning hook: fire-and-forget rule extraction from discard
        try:
            from services.autolearning_analyzer import analyze_creator_action

            # Look up creator and lead for context
            from api.models import Creator as _Cr, Lead as _Ld
            _creator = session.query(_Cr).filter_by(name=creator_id).first()
            _lead = session.query(_Ld).filter_by(id=msg.lead_id).first() if msg.lead_id else None
            if _creator:
                asyncio.create_task(analyze_creator_action(
                    action="discarded",
                    creator_id=creator_id,
                    creator_db_id=_creator.id,
                    suggested_response=msg.suggested_response,
                    discard_reason=discard_reason,
                    intent=msg.intent,
                    lead_stage=_lead.status if _lead else None,
                    relationship_type=getattr(_lead, "relationship_type", None) if _lead else None,
                    source_message_id=msg.id,
                ))
        except Exception as learn_err:
            logger.debug(f"[Copilot] Autolearning discard hook failed: {learn_err}")

        # Preference pairs hook: fire-and-forget via unified FeedbackCapture
        try:
            from services.feedback_store import capture as feedback_capture
            from api.models import Message as _Msg2

            _cr = session.query(_Cr).filter_by(name=creator_id).first() if not locals().get("_creator") else _creator
            if _cr:
                # BUG-1 fix: fetch preceding user message
                _preceding2 = session.query(_Msg2.content).filter(
                    _Msg2.lead_id == msg.lead_id, _Msg2.role == "user",
                    _Msg2.created_at < msg.created_at,
                ).order_by(_Msg2.created_at.desc()).first()
                _user_msg2 = _preceding2[0] if _preceding2 else None

                asyncio.create_task(feedback_capture(
                    signal_type="copilot_discard",
                    creator_db_id=_cr.id,
                    lead_id=msg.lead_id,
                    user_message=_user_msg2,
                    bot_response=msg.suggested_response,
                    metadata={
                        "source_message_id": msg.id,
                        "intent": msg.intent,
                        "lead_stage": _lead.status if _lead else None,
                        "best_of_n_candidates": _bon_candidates,
                        "rejected_confidence": msg.confidence_score,
                    },
                ))
        except Exception as pp_err:
            logger.debug(f"[Copilot] Preference pairs discard hook failed: {pp_err}")

        logger.info(f"[Copilot] Discarded message {message_id} reason={discard_reason}")
        return {"success": True, "message_id": str(msg.id)}

    except Exception as e:
        logger.error(f"[Copilot] Error discarding response: {e}")
        session.rollback()
        return {"success": False, "error": str(e)}
    finally:
        session.close()


def auto_discard_pending_for_lead_impl(
    service, lead_id, session=None, creator_response: str = None, creator_id: str = None,
) -> int:
    """
    Auto-discard all pending_approval suggestions for a lead.

    Called when the creator manually replies (via phone/IG echo/WA fromMe),
    which means the bot suggestion is no longer needed.

    When creator_response is provided, marks suggestions as 'resolved_externally'
    instead of 'discarded', enabling autolearning from direct replies.

    Returns count of discarded/resolved suggestions.
    """
    from api.models import Message

    # Cancel any pending debounce regeneration for this lead
    lead_key = str(lead_id)
    task = service._debounce_tasks.pop(lead_key, None)
    if task and not task.done():
        task.cancel()
        logger.info(f"[Copilot:Debounce] Cancelled regen for lead {lead_key} (creator replied)")
    service._debounce_metadata.pop(lead_key, None)

    close_session = False
    if session is None:
        from api.database import SessionLocal

        session = SessionLocal()
        close_session = True

    try:
        pending = (
            session.query(Message)
            .filter(
                Message.lead_id == lead_id,
                Message.role == "assistant",
                Message.status == "pending_approval",
            )
            .limit(20)
            .all()
        )

        count = 0
        now = datetime.now(timezone.utc)
        for msg in pending:
            if creator_response:
                # Resolved externally — creator replied directly from app
                msg.status = "resolved_externally"
                msg.copilot_action = "resolved_externally"
                # Set content to creator's actual response so comparisons SQL works
                # (suggested_response = bot original, content = creator actual)
                msg.content = creator_response
                similarity = service._compute_similarity(msg.suggested_response or "", creator_response)
                _raw_meta = msg.msg_metadata or {}
                # Capture BoN candidates before stripping
                msg._bon_candidates = _raw_meta.get("best_of_n", {}).get("candidates")
                meta = {k: v for k, v in _raw_meta.items() if k != "best_of_n"}
                meta["creator_actual_response"] = creator_response[:500]
                meta["similarity_score"] = similarity
                meta["resolved_source"] = "direct_reply"
                # Persist lightweight BoN decision summary
                if msg._bon_candidates:
                    meta["best_of_n_decision"] = {
                        "chosen_index": None,
                        "n_candidates": len(msg._bon_candidates),
                        "best_confidence": msg._bon_candidates[0].get("confidence") if msg._bon_candidates else None,
                        "creator_overrode_best": True,
                    }
                msg.msg_metadata = meta
                msg.approved_at = now
                if msg.created_at:
                    delta = now - msg.created_at
                    msg.response_time_ms = int(delta.total_seconds() * 1000)
            else:
                msg.status = "discarded"
                msg.copilot_action = "manual_override"
                # Strip best_of_n — no longer needed
                if msg.msg_metadata and "best_of_n" in msg.msg_metadata:
                    msg.msg_metadata = {k: v for k, v in msg.msg_metadata.items() if k != "best_of_n"}
            count += 1

        if count > 0:
            session.commit()

            if creator_response:
                logger.info(
                    f"[Copilot] Resolved externally {count} pending suggestion(s) for lead {lead_id}"
                )
                # Fire autolearning + preference pairs hooks for each resolved suggestion
                # Fetch lead for context
                from api.models import Lead as _Ld2
                _lead_obj = session.query(_Ld2).filter_by(id=lead_id).first()
                for msg in pending:
                    _creator_db_id = service._get_creator_db_id(creator_id, session)
                    try:
                        from services.autolearning_analyzer import analyze_creator_action

                        asyncio.create_task(analyze_creator_action(
                            action="resolved_externally",
                            creator_id=creator_id or "",
                            creator_db_id=_creator_db_id,
                            suggested_response=msg.suggested_response,
                            final_response=creator_response,
                            intent=msg.intent,
                            lead_stage=_lead_obj.status if _lead_obj else None,
                            relationship_type=getattr(_lead_obj, "relationship_type", None) if _lead_obj else None,
                            source_message_id=msg.id,
                        ))
                    except Exception as learn_err:
                        logger.debug(f"[Copilot] Autolearning resolved_externally hook failed: {learn_err}")
                    try:
                        from services.feedback_store import capture as feedback_capture
                        from api.models import Message as _Msg3

                        # BUG-1 fix: fetch preceding user message
                        _preceding3 = session.query(_Msg3.content).filter(
                            _Msg3.lead_id == lead_id, _Msg3.role == "user",
                            _Msg3.created_at < msg.created_at,
                        ).order_by(_Msg3.created_at.desc()).first()
                        _user_msg3 = _preceding3[0] if _preceding3 else None

                        asyncio.create_task(feedback_capture(
                            signal_type="copilot_resolved",
                            creator_db_id=_creator_db_id,
                            lead_id=lead_id,
                            user_message=_user_msg3,
                            bot_response=msg.suggested_response,
                            creator_response=creator_response,
                            metadata={
                                "source_message_id": msg.id,
                                "intent": msg.intent,
                                "lead_stage": _lead_obj.status if _lead_obj else None,
                                "best_of_n_candidates": getattr(msg, "_bon_candidates", None),
                            },
                        ))
                    except Exception as pairs_err:
                        logger.debug(f"[Copilot] Preference pairs resolved_externally hook failed: {pairs_err}")
            else:
                logger.info(
                    f"[Copilot] Auto-discarded {count} pending suggestion(s) for lead {lead_id}"
                )

        return count
    except Exception as e:
        logger.error(f"[Copilot] Auto-discard error for lead {lead_id}: {e}")
        if close_session:
            session.rollback()
        return 0
    finally:
        if close_session:
            session.close()
