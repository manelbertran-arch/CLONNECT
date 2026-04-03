"""Phase 4: LLM Generation — prompt finalization + LLM call with fallback chain."""

import asyncio
import logging
import os
import time
from typing import Dict

from core.agent_config import AGENT_THRESHOLDS
from core.dm.models import ContextBundle
from core.dm.strategy import _determine_response_strategy
from core.dm.text_utils import (
    _classify_user_message,
    _smart_truncate_context,
    get_adaptive_max_tokens,
    get_length_hint,
)
from core.reasoning.self_consistency import get_self_consistency_validator
from services import LLMResponse

logger = logging.getLogger(__name__)


def _truncate_if_looping(text: str) -> tuple[bool, str]:
    """Detect and truncate character-level repetition loops.

    Returns (was_degenerate, cleaned_text).
    """
    if len(text) < 20:
        return False, text

    MIN_SUB = 10
    lower = text.lower()
    n = len(lower)

    # Cap scan start at 30 to avoid false positives on mid-sentence repetitions
    scan_limit = min(30, n - MIN_SUB)
    for start in range(scan_limit):
        sub = lower[start:start + MIN_SUB]
        pos = lower.find(sub, start + MIN_SUB)
        if pos != -1:
            trunc = text[:pos].rstrip(" ,!?¡¿")
            if len(trunc) >= 3:
                return True, trunc

    return False, text


# Feature flags for generation phase
ENABLE_LEARNING_RULES = os.getenv("ENABLE_LEARNING_RULES", "false").lower() == "true"
ENABLE_PREFERENCE_PROFILE = os.getenv("ENABLE_PREFERENCE_PROFILE", "false").lower() == "true"
ENABLE_GOLD_EXAMPLES = os.getenv("ENABLE_GOLD_EXAMPLES", "false").lower() == "true"
ENABLE_BEST_OF_N = os.getenv("ENABLE_BEST_OF_N", "false").lower() == "true"
ENABLE_SELF_CONSISTENCY = os.getenv("ENABLE_SELF_CONSISTENCY", "false").lower() == "true"
ENABLE_LENGTH_HINTS = os.getenv("ENABLE_LENGTH_HINTS", "true").lower() == "true"
ENABLE_QUESTION_HINTS = os.getenv("ENABLE_QUESTION_HINTS", "true").lower() == "true"


def _maybe_question_hint(creator_id: str) -> str:
    """Return a question-suppression hint if bot over-questions vs creator baseline.

    Reads creator's question_rate_pct from baseline and the bot's measured natural
    question rate from creator_profiles(bot_natural_rates). If bot rate > creator rate,
    returns "NO incluyas pregunta en este mensaje." with probability:
        suppress_prob = 1 - (creator_rate / bot_natural_rate)

    Returns empty string if no suppression needed or no data available.
    """
    import random
    try:
        from core.dm.style_normalizer import _load_baseline, _load_bot_natural_rates

        baseline = _load_baseline(creator_id)
        if not baseline:
            return ""
        punct = baseline.get("punctuation", {})
        creator_q_rate = punct.get("has_question_msg_pct", punct.get("question_rate_pct"))
        if creator_q_rate is None:
            return ""

        bot_rates = _load_bot_natural_rates(creator_id)
        if not bot_rates or bot_rates.get("question_rate") is None:
            return ""  # No measured data → don't intervene

        bot_q_rate = float(bot_rates["question_rate"])
        if bot_q_rate <= 0 or creator_q_rate >= bot_q_rate:
            return ""  # Bot already under-questions or matches → no suppression

        suppress_prob = 1.0 - (creator_q_rate / bot_q_rate)
        if random.random() < suppress_prob:
            logger.info(
                "[Q-HINT] Suppressing question (creator=%.1f%%, bot_natural=%.1f%%, p=%.2f)",
                creator_q_rate, bot_q_rate, suppress_prob,
            )
            return "NO incluyas pregunta en este mensaje."
        return ""
    except Exception as e:
        logger.debug("[Q-HINT] Failed: %s", e)
        return ""


async def phase_llm_generation(
    agent, message: str, full_prompt: str, system_prompt: str,
    context: ContextBundle, cognitive_metadata: Dict,
    detection=None,
) -> LLMResponse:
    """Phase 4: Prompt finalization + LLM call with fallback chain."""
    _t2 = time.monotonic()
    # Alias context fields for code compatibility
    intent_value = context.intent_value
    _rel_type = context.rel_type
    follower = context.follower
    is_friend = context.is_friend
    current_stage = context.current_stage
    user_context = context.user_context
    relational_block = context.relational_block
    rag_context = context.rag_context
    memory_context = context.memory_context
    few_shot_section = context.few_shot_section
    dna_context = context.dna_context
    state_context = context.state_context
    kb_context = context.kb_context
    advanced_section = context.advanced_section
    _echo_rel_ctx = context.echo_rel_ctx
    history = context.history
    rag_results = context.rag_results
    frustration_level = detection.frustration_level if detection is not None else 0
    sender_id = follower.follower_id if hasattr(follower, 'follower_id') else ""

    # Step 5b: Determine response strategy
    strategy_hint = _determine_response_strategy(
        message=message,
        intent_value=intent_value,
        relationship_type="",  # Relationship scorer: zero injection into strategy
        is_first_message=(follower.total_messages <= 1 and not history),
        is_friend=False,  # Product suppression only — never affects strategy text
        follower_interests=follower.interests,
        lead_stage=current_stage,
        history_len=len(history),
    )
    if strategy_hint:
        cognitive_metadata["response_strategy"] = strategy_hint.split(".")[0]
        logger.info(f"[STRATEGY] {strategy_hint.split('.')[0]}")

    # Step 5c: Load learning rules (autolearning feedback loop)
    learning_rules_section = ""
    if ENABLE_LEARNING_RULES:
        try:
            from services.learning_rules_service import get_applicable_rules

            def _load_rules():
                from api.database import SessionLocal
                from api.models import Creator
                _s = SessionLocal()
                try:
                    _c = _s.query(Creator.id).filter_by(name=agent.creator_id).first()
                    if not _c:
                        return []
                    _creator_db_id = _c[0]
                finally:
                    _s.close()
                return get_applicable_rules(
                    _creator_db_id, intent=intent_value,
                    relationship_type=_rel_type,
                    lead_stage=current_stage,
                )

            _learning_rules = await asyncio.to_thread(_load_rules)
            if _learning_rules:
                lines = ["[LEARNING RULES — Apply these behavioral corrections to your response:]"]
                for r in _learning_rules:
                    lines.append(f"- {r['rule_text']}")
                    if r.get("example_bad"):
                        lines.append(f'  NO: "{r["example_bad"]}"')
                    if r.get("example_good"):
                        lines.append(f'  SI: "{r["example_good"]}"')
                learning_rules_section = "\n".join(lines)
                cognitive_metadata["learning_rules_applied"] = len(_learning_rules)
                logger.info(f"[LEARNING] Injected {len(_learning_rules)} rules for {sender_id}")

                # Track injection count (times_applied) — fire-and-forget, no confidence change
                _injected_ids = [r["id"] for r in _learning_rules]
                asyncio.create_task(_track_rules_applied(_injected_ids))
        except Exception as lr_err:
            logger.debug(f"[LEARNING] Rule loading failed: {lr_err}")

    # Step 5d: Load preference profile
    preference_profile_section = ""
    if ENABLE_PREFERENCE_PROFILE:
        try:
            from services.preference_profile_service import (
                compute_preference_profile,
                format_preference_profile_for_prompt,
            )

            def _load_profile():
                from api.database import SessionLocal
                from api.models import Creator
                _s = SessionLocal()
                try:
                    _c = _s.query(Creator.id).filter_by(name=agent.creator_id).first()
                    if not _c:
                        return None
                    return compute_preference_profile(_c[0])
                finally:
                    _s.close()

            _profile = await asyncio.to_thread(_load_profile)
            if _profile:
                preference_profile_section = format_preference_profile_for_prompt(
                    _profile, agent.creator_id
                )
                cognitive_metadata["preference_profile"] = True
                logger.info(f"[PREFERENCE] Profile applied for {sender_id}")
        except Exception as pp_err:
            logger.debug(f"[PREFERENCE] Profile loading failed: {pp_err}")

    # Step 5e: Load gold examples (few-shot) — style reference only, no lead data leakage
    gold_examples_section = ""
    if ENABLE_GOLD_EXAMPLES:
        try:
            from services.gold_examples_service import get_matching_examples, detect_language

            # Detect conversation language for filtering
            _conv_language = detect_language(message) if message else None

            def _load_examples():
                from api.database import SessionLocal
                from api.models import Creator
                _s = SessionLocal()
                try:
                    _c = _s.query(Creator.id).filter_by(name=agent.creator_id).first()
                    if not _c:
                        return []
                    return get_matching_examples(
                        _c[0], intent=intent_value,
                        relationship_type=_rel_type,
                        lead_stage=current_stage,
                        language=_conv_language,
                    )
                finally:
                    _s.close()

            _gold_examples = await asyncio.to_thread(_load_examples)
            if _gold_examples:
                _header = "=== EJEMPLOS DE ESTILO DEL CREATOR (referencia de tono y formato, NO copies literalmente) ==="
                ex_lines = [_header]
                for ex in _gold_examples:
                    _intent_tag = f" [{ex['intent']}]" if ex.get("intent") else ""
                    ex_lines.append(f"- \"{ex['creator_response']}\"{_intent_tag}")
                gold_examples_section = "\n".join(ex_lines)
                cognitive_metadata["gold_examples_injected"] = len(_gold_examples)
                logger.info(f"[FEWSHOT] Injected {len(_gold_examples)} examples for {sender_id}")
        except Exception as ge_err:
            logger.debug(f"[FEWSHOT] Example loading failed: {ge_err}")

    # Step 6: Build full prompt — pure message as last content, no XML wrappers.
    # User context (username, stage, interests) is already in system_prompt via
    # relational_block + dna_context + state_context. No need to repeat here.
    prompt_parts = []
    if learning_rules_section:
        prompt_parts.append(learning_rules_section)
    if preference_profile_section:
        prompt_parts.append(preference_profile_section)
    if gold_examples_section:
        prompt_parts.append(gold_examples_section)
    if strategy_hint:
        prompt_parts.append(strategy_hint)

    # Per-message question suppression hint (data-driven).
    # If the bot over-questions relative to creator baseline, probabilistically
    # inject "NO hagas pregunta" to bring question_rate closer to target.
    _q_hint = _maybe_question_hint(agent.creator_id) if ENABLE_QUESTION_HINTS else ""
    if _q_hint:
        prompt_parts.append(_q_hint)
        cognitive_metadata["question_hint"] = _q_hint

    prompt_parts.append(message)
    full_prompt = "\n\n".join(prompt_parts)
    # Store for SBS retry — allows regenerating with identical prompt at lower temperature
    cognitive_metadata["_full_prompt"] = full_prompt

    # Cap total context to ~12K tokens to control LLM cost/latency
    _MAX_CONTEXT_CHARS = AGENT_THRESHOLDS.max_context_chars
    if len(system_prompt) > _MAX_CONTEXT_CHARS:
        original_len = len(system_prompt)
        system_prompt = _smart_truncate_context(system_prompt, _MAX_CONTEXT_CHARS)
        cognitive_metadata["prompt_truncated"] = True
        logger.info(f"[PROMPT] Smart-truncated system prompt from {original_len} to {len(system_prompt)} chars")

    # Log prompt size for latency diagnosis
    _est_tokens = len(system_prompt) // 4
    _section_sizes = {
        k: len(v) for k, v in [
            ("style", agent.style_prompt or ""),
            ("relational", relational_block),
            ("rag", rag_context), ("memory", memory_context),
            ("fewshot", few_shot_section), ("dna", dna_context),
            ("state", state_context), ("kb", kb_context),
            ("advanced", advanced_section),
        ] if v
    }
    logger.info(
        f"[TIMING] System prompt: {len(system_prompt)} chars (~{_est_tokens} tokens) "
        f"sections={_section_sizes}"
    )

    # LLM generation: Flash-Lite → GPT-4o-mini (2 providers, nothing else)
    # Path: webhook → process_dm() → generate_dm_response() → gemini/openai
    from core.providers.gemini_provider import generate_dm_response

    # Build multi-turn messages: system + history turns + current user message.
    # History is passed as separate user/assistant messages so the LLM sees full
    # conversational context (vs the old single-message flattened format).
    llm_messages = [{"role": "system", "content": system_prompt}]
    if history:
        # Use last 10 messages; ensure we start with a user turn (Gemini requirement)
        history_slice = history[-10:]
        while history_slice and history_slice[0].get("role") != "user":
            history_slice = history_slice[1:]
        # Merge consecutive same-role messages (Gemini requires strict alternating turns)
        deduped: list = []
        for msg in history_slice:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role not in ("user", "assistant") or not content:
                continue
            if deduped and deduped[-1]["role"] == role:
                # Append to previous turn; skip exact duplicates
                if content != deduped[-1]["content"]:
                    deduped[-1]["content"] += "\n" + content
            else:
                deduped.append({"role": role, "content": content})
        for msg in deduped:
            content = msg["content"]
            # Truncate very long individual messages to control token spend
            if len(content) > 600:
                content = content[:597] + "..."
            llm_messages.append({"role": msg["role"], "content": content})
    llm_messages.append({"role": "user", "content": full_prompt})

    # Best-of-N: generate 3 candidates at different temperatures (copilot only)
    best_of_n_result = None
    if ENABLE_BEST_OF_N:
        try:
            from core.copilot_service import get_copilot_service
            _is_copilot = get_copilot_service().is_copilot_enabled(agent.creator_id)
            if _is_copilot:
                from core.best_of_n import generate_best_of_n, serialize_candidates
                best_of_n_result = await generate_best_of_n(
                    llm_messages, 150, intent_value, "llm_generation", agent.creator_id
                )
        except Exception as bon_err:
            logger.warning("[BestOfN] Failed, using single call: %s", bon_err, exc_info=True)

    if best_of_n_result:
        llm_result = {
            "content": best_of_n_result.best.content,
            "model": best_of_n_result.best.model,
            "provider": best_of_n_result.best.provider,
            "latency_ms": best_of_n_result.total_latency_ms,
        }
        cognitive_metadata["best_of_n"] = serialize_candidates(best_of_n_result)
    else:
        # A4/A5: generate_dm_response returns dict with model/provider/latency
        # Priority: ECHO adapter (highest) > adaptive calibration > calibration baseline > hardcoded default
        _llm_temperature = 0.7  # universal default
        _cal_baseline = (agent.calibration or {}).get("baseline", {}) if agent.calibration else {}
        if _cal_baseline.get("temperature") is not None:
            _llm_temperature = float(_cal_baseline["temperature"])
        # max_tokens: read from calibration (per-creator optimal), fallback 100.
        # Calibration-derived limit (e.g. iris_bertran=100) prevents Gemini
        # repetition loops from running long before truncation.
        _llm_max_tokens = int(_cal_baseline["max_tokens"]) if _cal_baseline.get("max_tokens") else 100
        _msg_category = _classify_user_message(message)
        cognitive_metadata["max_tokens_category"] = _msg_category
        if ENABLE_LENGTH_HINTS:
            cognitive_metadata["length_hint"] = get_length_hint(message)
            logger.info(f"[LENGTH-HINT] category={_msg_category} hint='{cognitive_metadata['length_hint']}'")
        if _echo_rel_ctx:
            _llm_max_tokens = _echo_rel_ctx.llm_max_tokens
            _llm_temperature = _echo_rel_ctx.llm_temperature

        # Temperature dual — DISABLED (suspect in 8.30→7.23 regression).
        # Was reducing temp to 0.4 when RAG active, killing personality.
        # TODO: re-enable after bisect confirms it's not the culprit.
        cognitive_metadata["temperature_used"] = _llm_temperature

        llm_result = await generate_dm_response(
            llm_messages,
            max_tokens=_llm_max_tokens,
            temperature=_llm_temperature,
        )

    _t3 = time.monotonic()
    logger.info(f"[TIMING] LLM call: {int((_t3 - _t2) * 1000)}ms")

    if llm_result:
        # Universal safety: strip any thinking-model artifacts before
        # the response reaches post-processing or the user.
        # The provider (deepinfra_provider) already strips, but this
        # catches cases from Gemini, OpenAI, or any new provider.
        from core.providers.deepinfra_provider import strip_thinking_artifacts
        _raw_content = llm_result["content"]
        _clean_content = strip_thinking_artifacts(_raw_content)
        if _clean_content != _raw_content:
            logger.info(
                "[THINK-STRIP] Removed thinking artifacts from %s response: %r→%r",
                llm_result.get("provider", "?"),
                _raw_content[:60], _clean_content[:60],
            )
            llm_result = {**llm_result, "content": _clean_content}
        llm_response = LLMResponse(
            content=llm_result["content"],
            model=llm_result.get("model", "unknown"),
            tokens_used=0,
            metadata={
                "provider": llm_result.get("provider", "unknown"),
                "latency_ms": llm_result.get("latency_ms", 0),
            },
        )
    else:
        # Both Flash-Lite and GPT-4o-mini failed — emergency fallback
        logger.error("Primary cascade failed, using llm_service emergency fallback")
        llm_response = await agent.llm_service.generate(
            prompt=full_prompt, system_prompt=system_prompt
        )

    # Layer 2: Post-processing repetition loop detector — DISABLED.
    # Suspect in 8.30→7.23 regression: MIN_SUB=10 too aggressive,
    # catches normal phrases like "Buaaaaa tiaaaa" repeated naturally.
    # TODO: re-enable with higher MIN_SUB after bisect.
    # _loop_found, _clean_content = _truncate_if_looping(llm_response.content)
    # if _loop_found:
    #     logger.warning(
    #         "[LOOP-DETECTOR] Repetition truncated: %r -> %r",
    #         llm_response.content[:80], _clean_content[:80],
    #     )
    #     llm_response.content = _clean_content
    #     cognitive_metadata["loop_truncated"] = True

    # Phase 4b: Self-consistency validation (expensive, default OFF)
    if ENABLE_SELF_CONSISTENCY:
        try:
            validator = get_self_consistency_validator(agent.llm_service)
            consistency = await validator.validate_response(
                query=message,
                response=llm_response.content,
                system_prompt=system_prompt,
            )
            if not consistency.is_consistent and consistency.response:
                logger.info(
                    f"Self-consistency: replaced (conf={consistency.confidence:.2f})"
                )
                llm_response.content = consistency.response
                cognitive_metadata["self_consistency_replaced"] = True
        except Exception as e:
            logger.debug(f"Self-consistency failed: {e}")

    return llm_response


async def _track_rules_applied(rule_ids: list) -> None:
    """Fire-and-forget: increment times_applied for injected rules (without touching confidence).
    Uses individual ORM updates (max 5 rules) — safe, no array binding issues.
    """
    if not rule_ids:
        return
    try:
        import uuid as _uuid
        from api.database import SessionLocal
        from api.models import LearningRule

        def _do_increment():
            s = SessionLocal()
            try:
                for rid_str in rule_ids:
                    try:
                        rid = _uuid.UUID(rid_str) if isinstance(rid_str, str) else rid_str
                    except (ValueError, AttributeError):
                        continue
                    rule = s.query(LearningRule).filter_by(id=rid).first()
                    if rule:
                        rule.times_applied = (rule.times_applied or 0) + 1
                s.commit()
            except Exception:
                s.rollback()
            finally:
                s.close()

        await asyncio.to_thread(_do_increment)
    except Exception:
        pass  # Never block generation for tracking
