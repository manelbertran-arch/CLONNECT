"""Phase 5: Post-processing — guardrails, validation, formatting, scoring."""

import asyncio
import logging
import os
import re
import time
import unicodedata
from typing import Dict

from core.agent_config import AGENT_THRESHOLDS
from core.dm.models import ContextBundle, DetectionResult, DMResponse
from core.dm.text_utils import _message_mentions_product
from core.feature_flags import flags
from core.output_validator import validate_links
from core.reflexion_engine import get_reflexion_engine
from core.response_fixes import apply_all_response_fixes
from services import LLMResponse
from services.length_controller import detect_message_type, enforce_length
from services.message_splitter import get_message_splitter
from services.question_remover import process_questions

logger = logging.getLogger(__name__)

# Cache for echo fallback pools
_echo_pool_cache: dict = {}


def _load_echo_fallback_pool(creator_id: str) -> list:
    """Load creator's short_response_pool for echo fallback.

    Sources (in priority order):
    1. Calibration data → short_response_pool (mined from real messages <15 chars)
    2. Few-shot examples → extract short responses (<15 chars)
    3. Empty list (caller should skip replacement)
    """
    if creator_id in _echo_pool_cache:
        return _echo_pool_cache[creator_id]

    pool = []

    # 1. Try calibration short_response_pool
    try:
        from services.calibration_loader import load_calibration
        cal = load_calibration(creator_id)
        if cal:
            pool = cal.get("short_response_pool", [])
            if not pool:
                # 2. Extract from few-shot examples
                examples = cal.get("few_shot_examples", [])
                for ex in examples:
                    resp = ex.get("response", "").strip()
                    if resp and len(resp) < 15:
                        pool.append(resp)
    except Exception as e:
        logger.debug("_load_echo_fallback_pool: failed for %s: %s", creator_id, e)

    if not pool:
        logger.warning("anti_echo: no short_response_pool for %s, skipping", creator_id)

    _echo_pool_cache[creator_id] = pool
    return pool


async def phase_postprocessing(
    agent, message: str, sender_id: str, metadata: Dict,
    llm_response: LLMResponse, context: ContextBundle,
    detection: DetectionResult, cognitive_metadata: Dict,
) -> DMResponse:
    """Phase 5: Guardrails, validation, formatting, scoring."""
    _t3 = time.monotonic()
    # Alias context fields for code compatibility
    intent_value = context.intent_value
    follower = context.follower
    history = context.history
    rag_results = context.rag_results

    _arc5_safety_status = "OK"
    _arc5_safety_reason = None
    _arc5_rule_violations: list = []

    response_content = llm_response.content

    # A2 FIX: Detect repetitive loops — LOG ONLY, do NOT replace.
    # Replacing with a hardcoded "Jajaja 😂" destroys correct responses when
    # the ground-truth reply happens to match the last bot message in history
    # (e.g., short acknowledgments: "Tranqui", "Dale", or schedule deferrals).
    # Marking the flag lets downstream monitoring track occurrences without
    # degrading response quality.
    try:
        last_bot_msgs = [
            m["content"] for m in history
            if m.get("role") == "assistant" and m.get("content")
        ][-1:]
        if last_bot_msgs and response_content:
            resp_norm = response_content.strip().lower()
            prev_norm = last_bot_msgs[0].strip().lower()
            if resp_norm and prev_norm and resp_norm == prev_norm:
                logger.warning(
                    "[A2] Repetitive loop detected — response is exact duplicate of last message "
                    "(passing through; not replacing)"
                )
                # Do NOT replace response_content — let the correct response through.
    except Exception as e:
        logger.debug(f"Loop detection failed: {e}")

    # A2b: Detect intra-response repetition anywhere in the string
    # (e.g. "Que vagi be germana JAJAJAJAJAJAJAJA..." — loop starts mid-response)
    # Only trigger on longer responses (> 50 chars) to avoid chopping natural
    # short expressions like "jajajaja" (8 chars) or "dale dale" (9 chars).
    try:
        if response_content and len(response_content) > 50:
            _resp_lower = response_content.lower()
            _match = re.search(r'(.{2,8})\1{4,}', _resp_lower)
            if _match:
                _pat = _match.group(1)
                _count = _resp_lower.count(_pat)
                _coverage = (_count * len(_pat)) / len(_resp_lower)
                if _coverage > 0.5 and _count > 5:
                    # Keep prefix before the loop + one clean occurrence (not * 3,
                    # which itself looks like a repetition loop to readers).
                    _prefix = response_content[:_match.start()]
                    _pat_orig = response_content[_match.start():_match.start() + len(_pat)]
                    response_content = _prefix + _pat_orig
                    logger.warning(
                        f"[A2b] Intra-response repetition: "
                        f"'{_pat}' covers {_coverage:.0%} of response ({_count}x) — truncated"
                    )
                    llm_response.content = response_content
    except Exception as e:
        logger.debug(f"Intra-response repetition detection failed: {e}")

    # A2c: Sentence-level deduplication
    # Handles longer repeated phrases (≥9 chars) that A2b's char-limited regex misses.
    # Also handles space-separated repetitions that break A2b's adjacency requirement.
    # Example: "On estas?  On estas?  On estas?" → "On estas?"
    # Trigger: any sentence appears 3+ times in the response.
    try:
        if response_content and len(response_content) > 30:
            _sents = re.split(r'(?<=[.!?\n])\s*|\s{2,}', response_content.strip())
            _sents = [s.strip() for s in _sents if len(s.strip()) > 3]
            if len(_sents) >= 3:
                _norm = [s.lower().strip('¡¿ ') for s in _sents]
                _max_count = max((_norm.count(n) for n in set(_norm)), default=0)
                if _max_count >= 3:
                    _seen: set = set()
                    _kept = []
                    for s, n in zip(_sents, _norm):
                        if n not in _seen:
                            _seen.add(n)
                            _kept.append(s)
                    _fixed = ' '.join(_kept).strip()
                    if _fixed and _fixed != response_content:
                        _removed = len(_sents) - len(_kept)
                        logger.warning(
                            f"[A2c] Sentence repetition: '{_norm[0][:30]}' x{_max_count}"
                            f" — dedup {len(_sents)}→{len(_kept)} sentences"
                        )
                        response_content = _fixed
                        llm_response.content = response_content
    except Exception as e:
        logger.debug(f"Sentence dedup failed: {e}")

    # A3: Echo detector — bot copied lead's message (Jaccard >= 0.55).
    # Qwen3-14B repeats/paraphrases input when it doesn't know what to say.
    # Threshold lowered from 0.70→0.55 because semantic echoes (rephrased
    # with 2-3 extra words like "tio", "crack") scored Jaccard ~0.64 and
    # slipped through.  Papers: semantic embeddings beat Jaccard (0.829 vs
    # 0.711 balanced accuracy) but add latency.  0.55 catches paraphrases
    # without false-flagging short agreements like "si, vale".
    _ECHO_THRESHOLD = float(os.environ.get("ECHO_JACCARD_THRESHOLD", "0.55"))
    try:
        if response_content and message:
            def _norm_words(text: str) -> set:
                # NFD decompose + strip combining diacritics (accents)
                # so "entès"=="entes", "Sí"=="si" — critical for Catalan
                text = unicodedata.normalize('NFD', text.lower())
                text = re.sub(r'[\u0300-\u036f]', '', text)
                text = re.sub(r'[^\w\s]', '', text)
                return set(text.split())
            _lead_words = _norm_words(message)
            _bot_words = _norm_words(response_content)
            if len(_lead_words) >= 3 and _bot_words:
                _union = _lead_words | _bot_words
                _jaccard = len(_lead_words & _bot_words) / len(_union)
                if _jaccard >= _ECHO_THRESHOLD:
                    import random
                    # Load creator's short_response_pool from calibration
                    _echo_pool = _load_echo_fallback_pool(agent.creator_id)
                    if _echo_pool:
                        _fallback = random.choice(_echo_pool)
                        logger.warning(
                            "[A3] Echo detected (Jaccard=%.2f) — replacing '%s...' with '%s'",
                            _jaccard, response_content[:40], _fallback,
                        )
                        response_content = _fallback
                    else:
                        logger.warning(
                            "[A3] Echo detected (Jaccard=%.2f) but no short_response_pool for %s, skipping replacement",
                            _jaccard, agent.creator_id,
                        )
    except Exception as e:
        logger.debug(f"Echo detection failed: {e}")

    # Step 7a: Output validation (links only — price validation handled by guardrails)
    if flags.output_validation:
        try:
            known_links = [p.get("url", "") for p in agent.products if p.get("url")]
            link_issues, corrected = validate_links(response_content, known_links)
            if link_issues:
                logger.warning(f"Output validation: {len(link_issues)} link issues")
                response_content = corrected  # Apply corrections
        except Exception as e:
            logger.debug(f"Output validation failed: {e}")

    # Step 7a2: Apply response fixes (typos, formatting, patterns)
    if flags.response_fixes:
        try:
            fixed_response = apply_all_response_fixes(
                response_content, creator_id=agent.creator_id,
            )
            if fixed_response and fixed_response != response_content:
                logger.debug("Response fixes applied")
                response_content = fixed_response
        except Exception as e:
            logger.debug(f"Response fixes failed: {e}")

    # Step 7a2b3: Blacklist word/emoji replacement from Doc D
    # Replaces prohibited address terms ('compa'→'nena') and forbidden emojis (🥰→🩷).
    # Reads creator's Doc D — no-op if no Doc D exists. Universal across creators.
    if flags.blacklist_replacement:
        try:
            from services.calibration_loader import apply_blacklist_replacement

            response_content, _bl_changed = apply_blacklist_replacement(
                response_content, agent.creator_id
            )
        except Exception as e:
            logger.debug(f"Blacklist replacement failed: {e}")

    # Step 7a2c: Question removal
    # Loads creator's question_rate from profile. Skips if no data available.
    if flags.question_removal:
        try:
            response_content = process_questions(
                response_content, message, creator_id=agent.creator_id,
            )
        except Exception as e:
            logger.debug(f"Question removal failed: {e}")

    # Step 7a3: Reflexion analysis for response quality (legacy)
    if flags.reflexion:
        try:
            prev_bot = [
                m.get("content", "")
                for m in history  # history is already in scope (line 45); metadata has no "history" key
                if m.get("role") == "assistant"
            ]
            r_result = get_reflexion_engine().analyze_response(
                response=response_content,
                user_message=message,
                previous_bot_responses=prev_bot[-5:],
            )
            if r_result.needs_revision:
                cognitive_metadata["reflexion_issues"] = r_result.issues
                cognitive_metadata["reflexion_severity"] = r_result.severity
        except Exception as e:
            logger.debug(f"Reflexion failed: {e}")

    # Step 7a4: QUALITY GATE — Score Before You Speak (SBS)
    # SBS evaluates persona alignment via CPU-only scoring (~1ms).
    #   score >= 0.7 (ALIGNMENT_THRESHOLD) -> send as-is (0 extra LLM calls)
    #   score <  0.7 -> retry with primary model at temp=0.5 (1 extra call max)
    #                   picks max(initial, retry) — never outputs a worse retry
    #                   if user_prompt missing or retry fails, returns original
    # When SBS is disabled, PPA runs standalone as fallback (elif branch below).
    if flags.score_before_speak and agent.calibration:
        try:
            from core.reasoning.ppa import score_before_speak

            follower_name = (follower or {}).get("full_name", "") or (follower or {}).get("username", "")
            # BUG-PP-2 fix: DetectionResult has no .language field; read from cognitive_metadata
            # where the context phase deposits it (key: "detected_language"). Fallback "ca".
            _detected_lang = cognitive_metadata.get("detected_language", "ca")
            sbs_result = await score_before_speak(
                response=response_content,
                calibration=agent.calibration,
                system_prompt=context.system_prompt,
                user_prompt=cognitive_metadata.get("_full_prompt", ""),
                lead_name=follower_name,
                detected_language=_detected_lang,
                creator_id=agent.creator_id,
                creator_name=getattr(agent, "creator_name", ""),
            )
            if sbs_result.path != "pass":
                response_content = sbs_result.response
                logger.info(
                    "[SBS] path=%s score=%.2f calls=%d",
                    sbs_result.path, sbs_result.alignment_score, sbs_result.total_llm_calls,
                )
        except Exception as e:
            logger.debug(f"Score Before You Speak failed: {e}")

    # Step 7a4b: Post Persona Alignment (PPA) — fallback when SBS is disabled
    elif flags.ppa and agent.calibration:
        try:
            from core.reasoning.ppa import apply_ppa

            follower_name = (follower or {}).get("full_name", "") or (follower or {}).get("username", "")
            _detected_lang = cognitive_metadata.get("detected_language", "ca")
            ppa_result = await apply_ppa(
                response=response_content,
                calibration=agent.calibration,
                lead_name=follower_name,
                detected_language=_detected_lang,
                creator_id=agent.creator_id,
                creator_name=getattr(agent, "creator_name", ""),
            )
            if ppa_result.was_refined:
                response_content = ppa_result.response
                logger.info("[PPA] Response refined (score=%.2f)", ppa_result.alignment_score)
        except Exception as e:
            logger.debug(f"PPA failed: {e}")

    # Step 7b: Apply guardrails validation
    if flags.guardrails and hasattr(agent, "guardrails"):
        try:
            # Build allowed URLs from creator's products and booking links
            creator_urls = []
            for p in agent.products:
                url = p.get("url", "")
                if url:
                    creator_urls.append(url)
            # Extract unique domains from product URLs for whitelist
            creator_domains = set()
            for u in creator_urls:
                # Extract domain: "https://www.example.com/path" -> "example.com"
                try:
                    domain = u.split("//")[-1].split("/")[0].replace("www.", "")
                    creator_domains.add(domain)
                except Exception as e:
                    logger.warning(f"Failed to parse URL domain '{u}': {e}")
            guardrail_result = agent.guardrails.validate_response(
                query=message,
                response=response_content,
                context={
                    "products": agent.products,
                    "allowed_urls": list(creator_domains),
                },
            )
            if not guardrail_result.get("valid", True):
                logger.warning(f"Guardrail triggered: {guardrail_result.get('reason')}")
                if guardrail_result.get("corrected_response"):
                    response_content = guardrail_result["corrected_response"]
                    _arc5_safety_status = "REGEN"
                else:
                    _arc5_safety_status = "BLOCK"
                _arc5_safety_reason = guardrail_result.get("reason")
                _reason = guardrail_result.get("reason") or "unknown"
                _arc5_rule_violations.append(_reason)
                cognitive_metadata["guardrail_triggered"] = guardrail_result.get("reason")
        except Exception as e:
            logger.debug(f"Guardrails check failed: {e}")

    # Step 7c: Apply soft length guidance based on message type  (BUG-PP-5: was "Step 7b" — duplicate)
    try:
        msg_type = detect_message_type(message)
        response_content = enforce_length(response_content, message, creator_id=agent.creator_id)
        cognitive_metadata["message_type"] = msg_type
    except Exception as e:
        logger.debug(f"Length control failed: {e}")

    # Step 7b2: Style normalization (emoji/exclamation matching from baseline)
    _pre_normalization_response = response_content  # capture for bot_natural_rates measurement
    try:
        from core.dm.style_normalizer import normalize_style, ENABLE_STYLE_NORMALIZER
        if ENABLE_STYLE_NORMALIZER:
            response_content = normalize_style(response_content, agent.creator_id)
            if response_content != _pre_normalization_response:
                logger.debug("Style normalized: '%s' → '%s'", _pre_normalization_response[:40], response_content[:40])
    except Exception as e:
        logger.debug(f"Style normalization failed: {e}")

    # Step 7c: Format response for Instagram
    formatted_content = agent.instagram_service.format_message(response_content)

    # Step 7d: Inject payment link for purchase_intent if missing
    if intent_value.lower() in ("purchase_intent", "want_to_buy") and agent.products:
        msg_lower = message.lower()
        resp_lower = formatted_content.lower()
        for p in agent.products:
            pname = p.get("name") or ""
            plink = p.get("payment_link") or p.get("url") or ""
            # Match product in user message OR bot response
            mentioned = (
                _message_mentions_product(pname, msg_lower)
                or _message_mentions_product(pname, resp_lower)
            )
            if pname and mentioned and plink and plink not in resp_lower:
                formatted_content = f"{formatted_content}\n\n{plink}"
                cognitive_metadata["payment_link_injected"] = plink
                logger.info(f"[Step 7d] Injected payment link for '{pname}': {plink}")
                break

    _t4 = time.monotonic()
    logger.info(f"[TIMING] Phase 5 (post-processing): {int((_t4 - _t3) * 1000)}ms")

    # CloneScore real-time logging (non-blocking, CPU-only style_fidelity)
    if flags.clone_score:
        try:
            from services.clone_score_engine import CloneScoreEngine
            cs_engine = CloneScoreEngine()
            score_result = await cs_engine.evaluate_single(
                agent.creator_id, message, formatted_content, {}
            )
            cognitive_metadata["clone_score"] = score_result.get("overall_score", 0)
            _style = score_result.get("dimension_scores", {}).get("style_fidelity", 0)
            logger.info(f"[CLONE_SCORE] style={_style:.1f}")
        except Exception as e:
            logger.debug(f"[CLONE_SCORE] eval failed: {e}")

    # Step 9: Update lead score (synchronous - needed for response)
    new_stage = agent._update_lead_score(follower, intent_value, metadata)

    # Step 9a: Update conversation state machine (fire-and-forget)
    # BUG-PP-4 fix: get_state + update_state are sync DB calls — must run off the event loop.
    try:
        from core.conversation_state import get_state_manager

        _state_mgr = get_state_manager()
        _creator_id_snap = agent.creator_id
        _msg_snap, _intent_snap, _resp_snap = message, intent_value, formatted_content

        def _do_state_update():
            conv_state = _state_mgr.get_state(sender_id, _creator_id_snap)
            _state_mgr.update_state(conv_state, _msg_snap, _intent_snap, _resp_snap)

        await asyncio.to_thread(_do_state_update)
    except Exception as e:
        logger.debug(f"[STATE] update failed: {e}")

    # Step 9c: Email capture (non-blocking) — disabled by default
    if flags.email_capture:
        try:
            formatted_content = agent._step_email_capture(
                message=message,
                formatted_content=formatted_content,
                intent_value=intent_value,
                sender_id=sender_id,
                follower=follower,
                platform=metadata.get("platform", "instagram"),
                cognitive_metadata=cognitive_metadata,
            )
        except Exception as e:
            logger.warning(f"Email capture step failed (non-blocking): {e}")

    # Steps 8, 8b, 9b: Run in background thread (non-blocking)
    asyncio.create_task(
        agent._background_post_response(
            follower=follower,
            message=message,
            formatted_content=formatted_content,
            intent_value=intent_value,
            sender_id=sender_id,
            metadata=metadata,
            cognitive_metadata=cognitive_metadata,
        )
    )

    # Memory extraction (extract facts from conversation — fire-and-forget)
    # Skip for PERSONAL relationships (family/friends — no commercial facts needed)
    _rel_category = cognitive_metadata.get("relationship_category", "TRANSACTIONAL")
    _skip_memory = _rel_category == "PERSONAL"
    if _skip_memory:
        logger.debug("[MEMORY] Skipping fact extraction for PERSONAL lead (%s)", sender_id[:20])
    if flags.memory_engine and not _skip_memory:
        try:
            from services.memory_engine import get_memory_engine
            from services.memory_extraction import get_memory_extractor
            mem_engine = get_memory_engine()
            # BUG-MEM-04 fix: include last 3 messages from history for multi-turn context
            recent_history = [
                {"role": m.get("role", "user"), "content": m.get("content", "")}
                for m in (history[-3:] if history else [])
                if m.get("content")
            ]
            conversation_msgs = recent_history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": formatted_content},
            ]
            # BUG-001 fix: track task for drain (CC: DreamTask registry pattern)
            task = asyncio.create_task(
                mem_engine.add(agent.creator_id, sender_id, conversation_msgs)
            )
            get_memory_extractor(mem_engine).track_task(task)
        except Exception as e:
            logger.warning("[MEMORY] extraction setup failed for lead=%s: %s", sender_id[:20], e)

    # ECHO Engine: Detect commitments in bot response (Sprint 4 — fire-and-forget)
    if flags.commitment_tracking:
        try:
            from services.commitment_tracker import get_commitment_tracker

            async def _detect_commitments():
                try:
                    tracker = get_commitment_tracker()
                    tracker.detect_and_store(
                        response_text=formatted_content,
                        creator_id=agent.creator_id,
                        lead_id=sender_id,
                    )
                except Exception as e:
                    logger.debug(f"[COMMITMENT] detection failed: {e}")

            asyncio.create_task(_detect_commitments())
        except Exception as e:
            logger.debug(f"[COMMITMENT] setup failed: {e}")

    # Step 10: Escalation notification (async, lightweight)
    asyncio.create_task(
        agent._check_and_notify_escalation(
            intent_value=intent_value,
            follower=follower,
            sender_id=sender_id,
            message=message,
            metadata=metadata,
        )
    )

    # Step 10b: Message splitting (store in metadata for caller)
    message_parts = None
    if flags.message_splitting:
        try:
            splitter = get_message_splitter()
            if splitter.should_split(formatted_content):
                parts = splitter.split(formatted_content, message)
                message_parts = [{"text": p.text, "delay": p.delay_before} for p in parts]
                logger.debug(f"Message split into {len(parts)} parts")
        except Exception as e:
            logger.debug(f"Message splitting failed: {e}")

    _t5 = time.monotonic()
    logger.info(
        f"[TIMING] Phase 5 (post+mem+nurture): {int((_t5 - _t3) * 1000)}ms "
        f"(guardrails={int((_t4 - _t3) * 1000)} async={int((_t5 - _t4) * 1000)})"
    )
    # A4: Include model/provider/latency in metadata for auditing
    llm_meta = llm_response.metadata or {}

    # Confidence scoring (multi-factor)
    if flags.confidence_scorer:
        try:
            from core.confidence_scorer import calculate_confidence
            scored_confidence = calculate_confidence(
                intent=intent_value,
                response_text=formatted_content,
                response_type="llm_generation",
                creator_id=agent.creator_id,
            )
        except Exception:
            scored_confidence = AGENT_THRESHOLDS.default_scored_confidence
    else:
        scored_confidence = AGENT_THRESHOLDS.default_scored_confidence

    _dm_metadata = {
        "model": llm_response.model,
        "provider": llm_meta.get("provider", "unknown"),
        "latency_ms": llm_meta.get("latency_ms", 0),
        "rag_results": len(rag_results),
        "history_length": len(history),
        "follower_id": sender_id,
        "message_parts": message_parts,
        "pre_normalization_response": _pre_normalization_response,
    }
    if cognitive_metadata.get("best_of_n"):
        _dm_metadata["best_of_n"] = cognitive_metadata["best_of_n"]

    # ARC5: build PostGenMetadata and enrich _dm_metadata with typed structure
    if flags.typed_metadata:
        try:
            from datetime import datetime, timezone
            from core.metadata.models import MessageMetadata, PostGenMetadata
            _arc5_postgen = PostGenMetadata(
                post_gen_ts=datetime.now(timezone.utc),
                safety_status=_arc5_safety_status,
                safety_reason=_arc5_safety_reason,
                pii_redacted_types=[],
                rule_violations=_arc5_rule_violations,
                length_regen_triggered=cognitive_metadata.get("truncation_recovery", False),
            )
            cognitive_metadata["_arc5_postgen_meta"] = _arc5_postgen
            _typed_msg_meta = MessageMetadata(
                detection=cognitive_metadata.get("_arc5_detection_meta"),
                generation=cognitive_metadata.get("_arc5_generation_meta"),
                post_gen=_arc5_postgen,
            )
            _dm_metadata["_arc5_typed_metadata"] = _typed_msg_meta.model_dump(
                mode="json", exclude_none=True
            )
        except Exception as _arc5_err:
            logger.warning("[ARC5] postgen metadata failed: %s", _arc5_err)

    return DMResponse(
        content=formatted_content,
        intent=intent_value,
        lead_stage=new_stage.value if hasattr(new_stage, "value") else str(new_stage),
        confidence=scored_confidence,
        tokens_used=llm_response.tokens_used,
        metadata=_dm_metadata,
    )
