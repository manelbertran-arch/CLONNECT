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

logger = logging.getLogger(__name__)

# Feature flags for context phase
ENABLE_QUESTION_CONTEXT = os.getenv("ENABLE_QUESTION_CONTEXT", "true").lower() == "true"
ENABLE_CONVERSATION_STATE = os.getenv("ENABLE_CONVERSATION_STATE", "true").lower() == "true"
ENABLE_DNA_AUTO_CREATE = os.getenv("ENABLE_DNA_AUTO_CREATE", "true").lower() == "true"
ENABLE_QUERY_EXPANSION = os.getenv("ENABLE_QUERY_EXPANSION", "true").lower() == "true"
ENABLE_RAG = os.getenv("ENABLE_RAG", "true").lower() == "true"
ENABLE_RELATIONSHIP_DETECTION = (
    os.getenv("ENABLE_RELATIONSHIP_DETECTION", "true").lower() == "true"
)
ENABLE_ADVANCED_PROMPTS = os.getenv("ENABLE_ADVANCED_PROMPTS", "false").lower() == "true"
ENABLE_CITATIONS = os.getenv("ENABLE_CITATIONS", "true").lower() == "true"
ENABLE_HIERARCHICAL_MEMORY = os.getenv("ENABLE_HIERARCHICAL_MEMORY", "false").lower() == "true"
ENABLE_EPISODIC_MEMORY = os.getenv("ENABLE_EPISODIC_MEMORY", "false").lower() == "true"


def _episodic_search(creator_slug: str, sender_id: str, message: str) -> str:
    """Search conversation_embeddings for past messages relevant to current message.

    Runs synchronously (called via asyncio.to_thread).
    Handles ID resolution: conversation_embeddings may use UUID or slug for creator_id,
    and lead UUID or platform_user_id for follower_id.

    Returns formatted context string for the Recalling block, or "".
    """
    from core.semantic_memory_pgvector import SemanticMemoryPgvector

    # Strategy: try slug+platform_id first (Stefano pattern),
    # then UUID+lead_uuid (Iris pattern) via DB lookup
    sm = SemanticMemoryPgvector(creator_slug, sender_id)
    results = sm.search(message, k=3, min_similarity=0.45)

    if not results:
        # Try UUID-based lookup
        try:
            from api.database import SessionLocal
            from api.models import Creator
            session = SessionLocal()
            try:
                creator = session.query(Creator).filter_by(name=creator_slug).first()
                if creator:
                    from sqlalchemy import text
                    lead = session.execute(
                        text("SELECT id FROM leads WHERE platform_user_id = :pid AND creator_id = :cid LIMIT 1"),
                        {"pid": sender_id, "cid": str(creator.id)},
                    ).fetchone()
                    if lead:
                        sm2 = SemanticMemoryPgvector(str(creator.id), str(lead[0]))
                        results = sm2.search(message, k=3, min_similarity=0.45)
            finally:
                session.close()
        except Exception:
            pass

    if not results:
        return ""

    # Format for Recalling block — factual, concise
    lines = []
    for r in results:
        role = "lead" if r["role"] == "user" else "tú"
        content = r["content"][:150]
        if len(r["content"]) > 150:
            content += "..."
        lines.append(f"- {role}: \"{content}\"")

    return "Conversaciones pasadas relevantes:\n" + "\n".join(lines)


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
                    cognitive_metadata["question_confidence"] = q_conf
                    cognitive_metadata["is_short_affirmation"] = True
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

    # Episodic memory: search conversation_embeddings for past messages relevant
    # to the current message. Complements Memory Engine facts with raw conversation
    # snippets the lead actually said. Skip for short/casual messages.
    episodic_context = ""
    if ENABLE_EPISODIC_MEMORY and len(message.strip()) >= 15:
        try:
            episodic_context = await asyncio.to_thread(
                _episodic_search, agent.creator_id, sender_id, message
            )
            if episodic_context:
                cognitive_metadata["episodic_recalled"] = True
                cognitive_metadata["episodic_chars"] = len(episodic_context)
        except Exception as e:
            logger.debug(f"[EPISODIC] search failed: {e}")

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
    # RAG retrieval — Self-RAG simplified: only activate for product-related queries.
    # Casual/social messages get ZERO retrieval (prevents IG caption noise injection).
    _PRODUCT_KEYWORDS = {
        "precio", "preu", "cuanto", "cuánto", "horario", "horari", "clase",
        "classe", "reserv", "apunt", "pack", "bono", "barre", "pilates",
        "reformer", "zumba", "flow", "entreno", "entrenament", "sesion",
        "sessió", "cuesta", "costa", "taller", "hipopresivos", "heels",
        "hiit", "masterclass", "workshop", "precio", "price", "cost",
    }
    _PRODUCT_INTENTS = {
        "question_product", "question_price", "interest_strong",
        "purchase_intent", "objection_price",
    }
    msg_lower = message.lower()
    _needs_retrieval = (
        ENABLE_RAG
        and (
            intent_value in _PRODUCT_INTENTS
            or any(kw in msg_lower for kw in _PRODUCT_KEYWORDS)
        )
    )

    rag_query = message
    rag_results = []
    if not ENABLE_RAG:
        cognitive_metadata["rag_disabled"] = True
    elif not _needs_retrieval:
        cognitive_metadata["rag_skipped"] = "no_product_signal"
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
        # Filter out IG captions — only keep product_catalog and faq sources
        if rag_results:
            _useful_types = {"product_catalog", "faq", "knowledge_base"}
            filtered = [
                r for r in rag_results
                if r.get("metadata", {}).get("type", "") in _useful_types
            ]
            if filtered:
                rag_results = filtered
                cognitive_metadata["rag_filtered"] = True
            # If no product chunks match, keep original results but log warning
            elif rag_results:
                logger.debug("[RAG] No product/faq results — using IG captions as fallback")

    if rag_results:
        logger.info(f"[RAG] query='{rag_query[:50]}' results={len(rag_results)}")
        if ENABLE_RERANKING:
            cognitive_metadata["rag_reranked"] = True
    else:
        logger.debug(f"[RAG] query='{rag_query[:50]}' results=0")

    rag_context = agent._format_rag_context(rag_results)

    # Relationship scoring (multi-signal, USER-only, gradated)
    _rel_score = None
    if ENABLE_RELATIONSHIP_DETECTION:
        try:
            from services.relationship_scorer import get_relationship_scorer

            # Extract USER-only messages for scoring (never assistant messages)
            hist = metadata.get("history", [])
            user_msgs = [m for m in hist if m.get("role") == "user"]

            # Get lead facts from memory_context (already computed above).
            # Parse the formatted string to extract fact texts for the scorer.
            # The scorer checks for PERSONAL_MARKERS ("madre", "amigo", ...) in text,
            # so text-only extraction is sufficient — fact_type "general" is OK.
            lead_facts = []
            if memory_context:
                import re as _re
                _time_re = _re.compile(
                    r'\s*\(hace[^)]*\)\s*(?:\[PENDIENTE\])?\s*$', _re.IGNORECASE
                )
                for _line in memory_context.split('\n'):
                    _line = _line.strip()
                    if (not _line
                            or _line.startswith('===')
                            or _line.startswith('Hechos')
                            or _line.startswith('Resumen')):
                        continue
                    _line = _line.lstrip('- •').strip()
                    _line = _time_re.sub('', _line).strip()
                    if len(_line) > 5:
                        lead_facts.append({"fact_type": "general", "fact_text": _line})

            # Calculate days span from follower data
            days_span = 0
            if hasattr(follower, "first_contact_at") and hasattr(follower, "last_contact_at"):
                if follower.first_contact_at and follower.last_contact_at:
                    days_span = max(0, (follower.last_contact_at - follower.first_contact_at).days)

            # Get lead status from DB (set by lead scoring system)
            lead_db_status = ""
            if hasattr(follower, "status"):
                lead_db_status = follower.status or ""
            elif hasattr(follower, "relationship_type"):
                lead_db_status = follower.relationship_type or ""

            scorer = get_relationship_scorer()
            _rel_score = scorer.score_sync(
                user_messages=user_msgs,
                lead_facts=lead_facts,
                days_span=days_span,
                lead_status=lead_db_status,
            )
            cognitive_metadata["relationship_score"] = _rel_score.score
            cognitive_metadata["relationship_category"] = _rel_score.category
            cognitive_metadata["relationship_signals"] = _rel_score.signals
            if _rel_score.category != "TRANSACTIONAL":
                logger.info(
                    "[REL] %s: score=%.2f category=%s signals=%s",
                    sender_id[:20], _rel_score.score, _rel_score.category, _rel_score.signals,
                )
        except Exception as e:
            logger.debug(f"Relationship scoring failed: {e}")

    # Silent product suppression only — ZERO prompt injection.
    # Only PERSONAL (score > 0.8) suppresses products; CLOSE/CASUAL/TRANSACTIONAL = normal.
    # _rel_type kept empty so strategy.py receives no relationship signal.
    is_friend = _rel_score.suppress_products if _rel_score else False
    _rel_type = ""

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

    # Product suppression is handled by gradated scoring:
    # is_friend=True (score > 0.8, PERSONAL only) → products stripped from prompt
    # CLOSE (0.6-0.8) and below: products visible, no extra instructions.
    # Doc D already defines tone for personal conversations — no extra
    # friend_context instructions needed (they contradict Doc D).
    friend_context = ""

    # Load few-shot examples from calibration (intent-stratified + semantic hybrid)
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
                detected_intent=intent_value,
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

    # Build Recalling block: consolidate all per-lead context into one coherent section
    # with an explicit usage trigger (MRPrompt pattern) so the LLM actually uses the data.
    def _build_recalling_block(
        username: str,
        relational: str,
        memory: str,
        dna: str,
        state: str,
        frustration_note: str = "",
        context_notes: str = "",
        episodic: str = "",
    ) -> str:
        """Consolidate per-lead context into a single 'Sobre @username' block
        with a Recalling trigger that instructs the LLM to use it naturally."""
        parts = [p for p in [relational, memory, dna, state, frustration_note, context_notes, episodic] if p]
        if not parts:
            return ""
        header = f"Sobre @{username}:"
        footer = "Usa esta info naturalmente en tu respuesta — no la repitas textual."
        return header + "\n" + "\n".join(parts) + "\n" + footer

    # Frustration note — factual, no behavior instruction (v2)
    _frustration_note = ""
    if detection is not None:
        _fsig = getattr(detection, "frustration_signals", None)
        if _fsig is not None:
            _fl = getattr(_fsig, "level", 0)
            _fr = getattr(_fsig, "reasons", [])
            if _fl == 1:
                _frustration_note = "Nota: el lead puede estar algo molesto."
            elif _fl == 2:
                _reason_str = ", ".join(r.split(":")[0] for r in _fr[:3]) if _fr else ""
                _frustration_note = (
                    f"Nota: el lead parece frustrado ({_reason_str}). No vendas ahora."
                    if _reason_str else "Nota: el lead parece frustrado. No vendas ahora."
                )
            elif _fl >= 3:
                _frustration_note = (
                    "Nota: el lead está muy frustrado. "
                    f"Prioriza resolver su problema o escalar a {agent.creator_id}."
                )

    # Context detection notes — factual observations for Recalling block
    _context_notes_str = ""
    if detection is not None:
        _csig = getattr(detection, "context_signals", None)
        if _csig is not None:
            _cnotes = getattr(_csig, "context_notes", [])
            if _cnotes:
                _context_notes_str = "\n".join(_cnotes)

    # Question Context — resolve affirmation collapse for short messages
    # When the lead says "Si", "Vale", "Ok" etc., the LLM often generates a
    # generic "Genial!" instead of acting on what it asked. This note tells
    # the LLM what the affirmation refers to.
    if ENABLE_QUESTION_CONTEXT:
        _q_ctx = cognitive_metadata.get("question_context")
        _q_conf = cognitive_metadata.get("question_confidence", 0)
        if _q_ctx and _q_ctx != "unknown" and _q_conf >= 0.7:
            _Q_NOTES = {
                "purchase": "El lead confirma que quiere comprar/apuntarse.",
                "payment": "El lead confirma el método de pago.",
                "booking": "El lead confirma la reserva o cita.",
                "interest": "El lead confirma interés en tus servicios.",
                "information": "El lead pide más información.",
                "confirmation": "El lead confirma lo que le propusiste.",
            }
            _q_note = _Q_NOTES.get(_q_ctx, "")
            if _q_note:
                _context_notes_str = (
                    (_context_notes_str + "\n" + _q_note)
                    if _context_notes_str else _q_note
                )
                logger.info("[QUESTION_CONTEXT] Injected: %s (conf=%.2f)", _q_ctx, _q_conf)

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
            # Use local var to avoid clobbering _rel_type="" set by the scorer
            _echo_rel_type = "DESCONOCIDO"
            if isinstance(raw_dna, dict):
                _echo_rel_type = raw_dna.get("relationship_type", "DESCONOCIDO")

            _echo_rel_ctx = adapter.get_relational_context(
                lead_status=current_stage,
                style_profile=_sp,
                commitment_text=commitment_text,
                lead_memory_summary=memory_context,
                relationship_type=_echo_rel_type,
                lead_name=follower.username if hasattr(follower, 'username') else None,
                message_count=follower.total_messages if hasattr(follower, 'total_messages') else 0,
                has_doc_d=bool(agent.style_prompt),
            )
            relational_block = _echo_rel_ctx.prompt_instructions
            if relational_block:
                cognitive_metadata["relational_adapted"] = True
                cognitive_metadata["lead_warmth"] = _echo_rel_ctx.warmth_score
        except Exception as e:
            logger.debug(f"[ECHO] Relationship Adapter failed: {e}")

    # Ordering: STATIC sections first (cacheable prefix for Gemini 90% discount),
    # then VARIABLE sections that change per lead/message.
    combined_context = "\n\n".join(
        filter(
            None,
            [
                # --- STATIC per creator (cacheable prefix) ---
                agent.style_prompt,       # HOW to write (Doc D distilled)
                few_shot_section,        # Calibration examples (10 selected)
                advanced_section,        # Anti-hallucination rules
                citation_context,        # Source attribution rules
                # --- SEMI-STATIC (creator-level, refreshed periodically) ---
                hier_memory_context,     # IMPersona: L3 abstract + L2 patterns + L1 episodic
                # --- VARIABLE per lead/message ---
                friend_context,          # Friend/family override (critical)
                _build_recalling_block(  # Consolidated lead data + Recalling trigger
                    username=follower.username or sender_id,
                    relational=relational_block,
                    memory=memory_context,
                    dna=dna_context,
                    state=state_context,
                    frustration_note=_frustration_note,
                    context_notes=_context_notes_str,
                    episodic=episodic_context,
                ),
                rag_context,             # RAG chunks relevant to message
                kb_context,              # Factual knowledge base lookup
                audio_context,           # Audio message context
                prompt_override,         # Manual override (lowest)
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
