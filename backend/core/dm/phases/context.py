"""Phase 2-3: Memory & Context — intent, parallel DB/IO, context assembly."""

import asyncio
import logging
import os
import time
from typing import Dict, List

from core.agent_config import AGENT_THRESHOLDS
from core.bot_question_analyzer import QuestionType, get_bot_question_analyzer, is_short_affirmation
from core.citation_service import get_citation_prompt_section
from core.conversation_state import get_state_manager
from core.dm.models import ContextBundle, DetectionResult
from core.query_expansion import get_query_expander
from core.rag.reranker import ENABLE_RERANKING
from services.relationship_type_detector import RelationshipTypeDetector

logger = logging.getLogger(__name__)

# Feature flags for context phase
ENABLE_QUESTION_CONTEXT = os.getenv("ENABLE_QUESTION_CONTEXT", "true").lower() == "true"
ENABLE_CONVERSATION_STATE = os.getenv("ENABLE_CONVERSATION_STATE", "true").lower() == "true"
ENABLE_DNA_AUTO_CREATE = os.getenv("ENABLE_DNA_AUTO_CREATE", "true").lower() == "true"
ENABLE_QUERY_EXPANSION = os.getenv("ENABLE_QUERY_EXPANSION", "true").lower() == "true"
ENABLE_RELATIONSHIP_DETECTION = (
    os.getenv("ENABLE_RELATIONSHIP_DETECTION", "true").lower() == "true"
)
ENABLE_ADVANCED_PROMPTS = os.getenv("ENABLE_ADVANCED_PROMPTS", "false").lower() == "true"
ENABLE_CITATIONS = os.getenv("ENABLE_CITATIONS", "true").lower() == "true"
ENABLE_HIERARCHICAL_MEMORY = os.getenv("ENABLE_HIERARCHICAL_MEMORY", "false").lower() == "true"


async def phase_memory_and_context(
    agent, message: str, sender_id: str, metadata: Dict,
    cognitive_metadata: Dict, detection: DetectionResult,
) -> ContextBundle:
    """Phase 2-3: Intent classification, parallel DB/IO, context assembly."""
    ctx = ContextBundle()
    _t1 = time.monotonic()

    # Step 2: Classify intent
    intent = agent.intent_classifier.classify(message)
    intent_value = intent.value if hasattr(intent, "value") else str(intent)
    logger.debug(f"Intent classified: {intent_value}")
    _t1a = time.monotonic()

    # Step 2b: Analyze bot's last question for short affirmation context
    if ENABLE_QUESTION_CONTEXT and is_short_affirmation(message):
        try:
            hist = metadata.get("history", [])
            last_bot = next(
                (
                    m.get("content", "")
                    for m in reversed(hist)
                    if m.get("role") == "assistant"
                ),
                None,
            )
            if last_bot:
                q_type, q_conf = get_bot_question_analyzer().analyze_with_confidence(
                    last_bot
                )
                if q_type != QuestionType.UNKNOWN:
                    cognitive_metadata["question_context"] = q_type.value
        except Exception as e:
            logger.debug(f"Question context failed: {e}")

    # =================================================================
    # PHASE 2-3: PARALLEL DB/IO + CONTEXT LOADING
    # =================================================================
    # Run independent DB/IO operations concurrently to reduce latency.
    # Previously sequential (~3.8s) → now parallel (~1.2s).

    from services.dm_agent_context_integration import build_context_prompt as _build_ctx
    from services.relationship_dna_repository import get_relationship_dna as _get_raw_dna

    async def _load_conv_state():
        if not ENABLE_CONVERSATION_STATE:
            return "", {}
        try:
            state_mgr = get_state_manager()
            conv_state = await asyncio.to_thread(
                state_mgr.get_state, sender_id, agent.creator_id
            )
            state_ctx = state_mgr.build_enhanced_prompt(conv_state)
            return state_ctx, {"conversation_phase": conv_state.phase.value}
        except Exception as e:
            logger.debug(f"Conversation state failed: {e}")
            return "", {}

    # Parallel: memory (file I/O) + DNA+PostCtx (2 DB queries) + conv_state (1 DB query) + raw DNA
    follower, dna_context, (state_context, state_meta), raw_dna = await asyncio.gather(
        agent.memory_store.get_or_create(
            creator_id=agent.creator_id,
            follower_id=sender_id,
            username=metadata.get("username", sender_id),
        ),
        _build_ctx(agent.creator_id, sender_id),
        _load_conv_state(),
        asyncio.to_thread(_get_raw_dna, agent.creator_id, sender_id),
    )
    cognitive_metadata.update(state_meta)

    # Memory recall (per-lead context from past conversations)
    memory_context = ""
    if os.getenv("ENABLE_MEMORY_ENGINE", "false").lower() == "true":
        try:
            from services.memory_engine import get_memory_engine
            mem_engine = get_memory_engine()
            memory_context = await mem_engine.recall(agent.creator_id, sender_id, message)
            if memory_context:
                cognitive_metadata["memory_recalled"] = True
                cognitive_metadata["memory_chars"] = len(memory_context)
        except Exception as e:
            logger.debug(f"[MEMORY] recall failed: {e}")

    # Hierarchical memory (IMPersona-style 3-level: episodic + semantic + abstract)
    hier_memory_context = ""
    if ENABLE_HIERARCHICAL_MEMORY:
        try:
            from core.hierarchical_memory.hierarchical_memory import HierarchicalMemoryManager

            hmm = HierarchicalMemoryManager(agent.creator_id)
            lead_name = metadata.get("username", "") or (
                follower.username if hasattr(follower, "username") else ""
            )
            hier_memory_context = hmm.get_context_for_message(
                message=message,
                lead_name=lead_name,
                lead_id=sender_id,
                max_tokens=300,
            )
            if hier_memory_context:
                _hmm_stats = hmm.stats()
                cognitive_metadata["hier_memory_injected"] = True
                cognitive_metadata["hier_memory_chars"] = len(hier_memory_context)
                cognitive_metadata["hier_memory_levels"] = {
                    "L1": _hmm_stats["level1_count"],
                    "L2": _hmm_stats["level2_count"],
                    "L3": _hmm_stats["level3_count"],
                }
                logger.info(
                    "[HIER-MEM] Injected %d chars (L1=%d L2=%d L3=%d) for %s",
                    len(hier_memory_context),
                    _hmm_stats["level1_count"],
                    _hmm_stats["level2_count"],
                    _hmm_stats["level3_count"],
                    sender_id[:20],
                )
        except Exception as e:
            logger.debug(f"[HIER-MEM] Failed: {e}")

    # ECHO Engine: Load pending commitments for this lead (Sprint 4)
    commitment_text = ""
    if os.getenv("ENABLE_COMMITMENT_TRACKING", "true").lower() == "true":
        try:
            from services.commitment_tracker import get_commitment_tracker
            tracker = get_commitment_tracker()
            commitment_text = await asyncio.to_thread(
                tracker.get_pending_text, sender_id
            )
            if commitment_text:
                cognitive_metadata["commitments_pending"] = True
        except Exception as e:
            logger.debug(f"[COMMITMENT] load failed: {e}")

    _bot_instructions = ""
    if dna_context:
        logger.debug(f"DNA context loaded for {sender_id}")
    if raw_dna:
        _bot_instructions = raw_dna.get("bot_instructions", "") or ""
        metadata["dna_data"] = raw_dna  # Store for trigger check later

    # Auto-create seed DNA if none exists and lead has some history
    if ENABLE_DNA_AUTO_CREATE and not dna_context and follower.total_messages >= 2:
        try:
            hist = metadata.get("history", [])
            if len(hist) >= 2:
                det_result = RelationshipTypeDetector().detect(hist)
                detected_type = det_result.get("type", "DESCONOCIDO")
                det_confidence = det_result.get("confidence", 0)

                async def _create_seed_dna():
                    try:
                        from services.relationship_dna_repository import (
                            create_relationship_dna,
                            get_relationship_dna as _get_dna,
                        )
                        existing = await asyncio.to_thread(
                            _get_dna, agent.creator_id, sender_id
                        )
                        if existing:
                            return  # Already exists, race condition
                        await asyncio.to_thread(
                            create_relationship_dna,
                            creator_id=agent.creator_id,
                            follower_id=sender_id,
                            relationship_type=detected_type,
                            trust_score=round(det_confidence * 0.3, 2),
                            depth_level=0,
                        )
                        logger.info(
                            f"[DNA-SEED] Created seed DNA for {sender_id}: "
                            f"type={detected_type} confidence={det_confidence}"
                        )
                    except Exception as e:
                        logger.debug(f"Seed DNA creation failed: {e}")

                asyncio.create_task(_create_seed_dna())
                cognitive_metadata["relationship_type"] = detected_type
                cognitive_metadata["dna_seed_created"] = True
        except Exception as e:
            logger.debug(f"DNA auto-create check failed: {e}")

    _t1b = time.monotonic()
    logger.info(f"[TIMING] Phase 2 sub: intent={int((_t1a - _t1) * 1000)}ms parallel_io={int((_t1b - _t1a) * 1000)}ms")

    # Fast in-memory operations (no parallelization needed)
    # RAG retrieval — skip for simple intents that don't need knowledge
    _SKIP_RAG_INTENTS = {"greeting", "farewell", "thanks", "saludo", "despedida"}
    rag_query = message
    if intent_value in _SKIP_RAG_INTENTS:
        rag_results = []
        cognitive_metadata["rag_skipped"] = intent_value
        logger.info(f"[RAG] Skipped for intent={intent_value} (no knowledge needed)")
    else:
        if ENABLE_QUERY_EXPANSION:
            try:
                expanded = get_query_expander().expand(message, max_expansions=2)
                if len(expanded) > 1:
                    rag_query = " ".join(expanded)
                    cognitive_metadata["query_expanded"] = True
            except Exception as e:
                logger.debug(f"Query expansion failed: {e}")
        rag_results = agent.semantic_rag.search(
            rag_query, top_k=agent.config.rag_top_k, creator_id=agent.creator_id
        )
    if rag_results:
        logger.info(f"[RAG] query='{rag_query[:50]}' results={len(rag_results)}")
    else:
        logger.debug(f"[RAG] query='{rag_query[:50]}' results=0")

    # Note: reranking already happens inside semantic_rag.search()
    # No need for a second reranking pass here
    if ENABLE_RERANKING and rag_results:
        cognitive_metadata["rag_reranked"] = True

    rag_context = agent._format_rag_context(rag_results)

    # Relationship type detection (in-memory)
    if ENABLE_RELATIONSHIP_DETECTION:
        try:
            hist = metadata.get("history", [])
            if len(hist) >= 2:
                rel_result = RelationshipTypeDetector().detect(hist)
                if rel_result.get("confidence", 0) > 0.5:
                    cognitive_metadata["relationship_type"] = rel_result["type"]
        except Exception as e:
            logger.debug(f"Relationship detection failed: {e}")

    # A1 FIX: Detect friend/family relationship to suppress acquisition behavior
    _rel_type = cognitive_metadata.get("relationship_type", "")
    is_friend = _rel_type in ("amigo", "FAMILIA", "AMISTAD_CERCANA", "INTIMA")

    # Lead stage (depends on follower)
    current_stage = agent._get_lead_stage(follower, metadata)

    # Knowledge base lookup (in-memory after first load)
    kb_context = ""
    try:
        from services.knowledge_base import get_knowledge_base
        kb = get_knowledge_base(agent.creator_id)
        kb_result = kb.lookup(message)
        if kb_result:
            kb_context = f"Info factual relevante: {kb_result}"
            logger.debug(f"KB hit for message: {message[:50]}")
    except Exception as e:
        logger.debug(f"KB lookup failed: {e}")

    # Step 5: Build prompts - combine style, RAG and DNA context
    # Include system_prompt_override if provided (for V2 prompt)
    # PRIORITY: style_prompt first (defines HOW to write)
    prompt_override = metadata.get("system_prompt_override", "")
    # Include advanced prompt sections if enabled
    advanced_section = ""
    if ENABLE_ADVANCED_PROMPTS:
        try:
            from core.prompt_builder import build_rules_section

            creator_name = agent.personality.get("name", "el creador")
            advanced_section = build_rules_section(creator_name)
        except Exception as e:
            logger.debug(f"Advanced prompts failed: {e}")
    # Load citation context
    citation_context = ""
    if ENABLE_CITATIONS:
        try:
            citation_context = get_citation_prompt_section(agent.creator_id, message)
        except Exception as e:
            logger.debug(f"Citation loading failed: {e}")

    # A1 FIX: Suppress acquisition/sales for friends/family
    friend_context = ""
    if is_friend:
        if _rel_type == "FAMILIA":
            friend_context = (
                "IMPORTANTE: Esta persona es FAMILIAR del creador (padre, madre, hijo, etc.). "
                "NO intentes vender, ofrecer productos, ni hacer preguntas de cualificación. "
                "Habla con cariño y naturalidad. Si pide ayuda, ayúdale directamente. "
                "NO uses frases como 'contame qué te trae por acá' ni similares."
            )
            logger.info("[A1] Family member detected — suppressing acquisition behavior")
        else:
            friend_context = (
                "IMPORTANTE: Esta persona es un AMIGO/A del creador, NO un lead. "
                "NO intentes vender, ofrecer productos, ni hacer preguntas de cualificación. "
                "Habla de forma natural, personal y relajada como con un amigo cercano. "
                "NO uses frases como 'contame qué te trae por acá' ni similares."
            )
            logger.info("[A1] Friend detected — suppressing acquisition behavior")

    # Load few-shot examples from calibration (5 semantic + 5 random for relevance + diversity)
    few_shot_section = ""
    if agent.calibration:
        try:
            from services.calibration_loader import detect_message_language, get_few_shot_section

            detected_lang = detect_message_language(message)
            few_shot_section = get_few_shot_section(
                agent.calibration,
                max_examples=10,
                current_message=message,
                lead_language=detected_lang,
            )
            if detected_lang:
                cognitive_metadata["detected_language"] = detected_lang
        except Exception as e:
            logger.debug(f"Few-shot loading failed: {e}")

    # Build audio context if message comes from audio intelligence
    audio_context = ""
    audio_intel = metadata.get("audio_intel")
    if audio_intel and isinstance(audio_intel, dict):
        parts = []
        # Include full transcription so LLM sees the actual words spoken
        clean_text = (audio_intel.get("clean_text") or "").strip()
        if clean_text:
            parts.append(f"[Audio del lead]: {clean_text}")
        # Include summary if it adds value beyond clean_text
        summary = (audio_intel.get("summary") or "").strip()
        if summary and summary != clean_text:
            parts.append(f"Resumen: {summary}")
        if audio_intel.get("intent"):
            parts.append(f"Intención del audio: {audio_intel['intent']}")
        entities = audio_intel.get("entities", {})
        entity_parts = []
        for key, label in [
            ("people", "Personas"), ("places", "Lugares"),
            ("dates", "Fechas"), ("numbers", "Cifras"),
            ("products", "Productos/servicios"),
        ]:
            vals = entities.get(key, [])
            if vals:
                entity_parts.append(f"{label}: {', '.join(vals)}")
        if entity_parts:
            parts.append("Datos mencionados: " + ". ".join(entity_parts))
        actions = audio_intel.get("action_items", [])
        if actions:
            parts.append("Acciones pendientes: " + "; ".join(actions))
        if audio_intel.get("emotional_tone"):
            parts.append(f"Tono: {audio_intel['emotional_tone']}")
        if parts:
            audio_context = (
                "CONTEXTO DE AUDIO (mensaje de voz transcrito):\n"
                + "\n".join(parts)
            )
            cognitive_metadata["audio_enriched"] = True

    # Media placeholder context — when platform sends "Sent an attachment" etc.
    if metadata.get("is_media_placeholder") and not audio_context:
        audio_context = (
            "[El lead compartió contenido multimedia — reacciona "
            "con entusiasmo brevemente, no preguntes qué es]"
        )

    # ECHO Engine: Generate relational context (Sprint 4)
    relational_block = ""
    _echo_rel_ctx = None
    if os.getenv("ENABLE_RELATIONSHIP_ADAPTER", "true").lower() == "true":
        try:
            from services.relationship_adapter import (
                RelationshipAdapter,
                style_profile_from_analyzer,
            )
            from core.style_analyzer import load_profile_from_db
            from api.database import SessionLocal
            from api.models import Creator

            # Load StyleProfile for modulation
            _sp = None
            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=agent.creator_id).first()
                if creator:
                    _raw_profile = load_profile_from_db(str(creator.id))
                    _sp = style_profile_from_analyzer(_raw_profile)
            finally:
                session.close()

            adapter = RelationshipAdapter()
            _rel_type = "DESCONOCIDO"
            if isinstance(raw_dna, dict):
                _rel_type = raw_dna.get("relationship_type", "DESCONOCIDO")

            _echo_rel_ctx = adapter.get_relational_context(
                lead_status=current_stage,
                style_profile=_sp,
                commitment_text=commitment_text,
                lead_memory_summary=memory_context,
                relationship_type=_rel_type,
                lead_name=follower.username if hasattr(follower, 'username') else None,
                message_count=follower.total_messages if hasattr(follower, 'total_messages') else 0,
            )
            relational_block = _echo_rel_ctx.prompt_instructions
            if relational_block:
                cognitive_metadata["relational_adapted"] = True
                cognitive_metadata["lead_warmth"] = _echo_rel_ctx.warmth_score
        except Exception as e:
            logger.debug(f"[ECHO] Relationship Adapter failed: {e}")

    # MRPrompt ordering: Enacting → Anchoring → Recalling → Bounding
    # Bounding (IMPORTANTE guardrails) is appended last by prompt_service.build_system_prompt().

    # RECALLING: Consolidate all lead-specific context into one block so the
    # model receives a clear, unified cue to personalize its reply.
    _lead_username = (follower.username if hasattr(follower, "username") and follower.username else sender_id)
    _recall_parts = list(filter(None, [
        memory_context,    # per-lead facts from memory engine
        dna_context,       # relationship insights
        relational_block,  # ECHO: warmth / stage-specific instructions
        state_context,     # conversation phase
    ]))
    if _recall_parts:
        lead_context_block = (
            f"Sobre @{_lead_username}:\n"
            + "\n".join(_recall_parts)
            + "\nTen en cuenta esta info al responder."
        )
    else:
        lead_context_block = ""

    combined_context = "\n\n".join(
        filter(
            None,
            [
                # 1. ENACTING — examples first (strongest style signal for the model)
                few_shot_section,
                # 2. ANCHORING — creator identity + style rules (Doc D distilled)
                agent.style_prompt,
                advanced_section,        # Anti-hallucination rules (static, creator-level)
                hier_memory_context,     # IMPersona hierarchical memory (semi-static)
                # 3. RECALLING — per-lead context (consolidated)
                lead_context_block,
                # 4. FACTUAL DATA — grounding for product/info queries
                rag_context,
                kb_context,
                citation_context,
                # 5. CONDITIONAL — message-specific overrides
                friend_context,          # Friend/family safety override
                audio_context,           # Audio enrichment
                prompt_override,         # Manual system override (lowest priority)
            ],
        )
    )
    # A1: Skip products for friends to avoid LLM injecting sales language
    prompt_products = [] if is_friend else agent.products
    system_prompt = agent.prompt_builder.build_system_prompt(
        products=prompt_products, custom_instructions=combined_context
    )

    # Get conversation history from follower memory (JSON files)
    history = agent._get_history_from_follower(follower)

    # DB fallback: when JSON-backed MemoryStore has no history (files don't exist
    # on Railway for most leads), load from PostgreSQL messages table instead.
    if not history:
        from core.dm.helpers import get_history_from_db
        history = await asyncio.to_thread(
            get_history_from_db, agent.creator_id, sender_id, 20
        )
        if history:
            logger.info(f"[HISTORY-DB] Loaded {len(history)} messages from DB for {sender_id}")
            # Backfill metadata so earlier code (question context, relationship
            # detection, DNA seed) can use it on next invocation
            metadata["history"] = history

    _t1c = time.monotonic()
    logger.info(f"[TIMING] Phase 3 sub: fast_ops={int((_t1c - _t1b) * 1000)}ms")

    # Build lead_info from follower memory for richer context
    _lead_info = {}
    if follower.interests:
        _lead_info["interests"] = follower.interests[:5]
    if follower.objections_raised:
        _lead_info["objections"] = follower.objections_raised[:5]
    if follower.products_discussed:
        _lead_info["products_discussed"] = follower.products_discussed[:5]
    if follower.purchase_intent_score > 0:
        _lead_info["purchase_score"] = round(follower.purchase_intent_score, 2)
    if follower.is_customer:
        _lead_info["is_customer"] = True
    if follower.conversation_summary:
        _lead_info["summary"] = follower.conversation_summary[:200]

    user_context = agent.prompt_builder.build_user_context(
        username=follower.username or sender_id,
        stage=current_stage,
        history=history,
        lead_info=_lead_info if _lead_info else None,
        include_history=False,  # history injected as multi-turn messages in generation phase
    )

    _t2 = time.monotonic()
    logger.info(f"[TIMING] Phase 2-3 (context+RAG+prompt): {int((_t2 - _t1) * 1000)}ms")

    # Populate context bundle for downstream phases
    ctx.intent = intent
    ctx.intent_value = intent_value
    ctx.follower = follower
    ctx.dna_context = dna_context
    ctx.state_context = state_context
    ctx.raw_dna = raw_dna
    ctx.memory_context = memory_context
    ctx.commitment_text = commitment_text
    ctx.bot_instructions = _bot_instructions
    ctx.rag_results = rag_results
    ctx.rag_context = rag_context
    ctx.is_friend = is_friend
    ctx.rel_type = _rel_type
    ctx.current_stage = current_stage
    ctx.kb_context = kb_context
    ctx.system_prompt = system_prompt
    ctx.history = history
    ctx.user_context = user_context
    ctx.few_shot_section = few_shot_section
    ctx.audio_context = audio_context
    ctx.relational_block = relational_block
    ctx.echo_rel_ctx = _echo_rel_ctx
    ctx.hier_memory_context = hier_memory_context
    ctx.friend_context = friend_context
    ctx.citation_context = citation_context
    ctx.advanced_section = advanced_section
    ctx.prompt_override = prompt_override  # NOTE: stored but not read in generation phase
    ctx.cognitive_metadata = cognitive_metadata
    return ctx
