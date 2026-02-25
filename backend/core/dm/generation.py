"""
DM Agent Phase 4: LLM Generation.

Handles prompt finalization, learning rules, gold examples,
preference profiles, and LLM call with fallback chain.
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Dict

from core.agent_config import AGENT_THRESHOLDS
from core.dm.helpers import _determine_response_strategy, _smart_truncate_context
from core.dm.models import (
    ContextBundle,
    ENABLE_BEST_OF_N,
    ENABLE_GOLD_EXAMPLES,
    ENABLE_LEARNING_RULES,
    ENABLE_PREFERENCE_PROFILE,
    ENABLE_SELF_CONSISTENCY,
)
from services import LLMResponse

if TYPE_CHECKING:
    from core.dm.agent import DMResponderAgentV2

logger = logging.getLogger(__name__)


async def phase_llm_generation(
    agent: "DMResponderAgentV2",
    message: str,
    full_prompt: str,
    system_prompt: str,
    context: ContextBundle,
    cognitive_metadata: Dict,
) -> LLMResponse:
    """Phase 4: Prompt finalization + LLM call with fallback chain."""
    _t2 = time.monotonic()
    intent_value = context.intent_value
    _rel_type = context.rel_type
    follower = context.follower
    is_friend = context.is_friend
    current_stage = context.current_stage
    _bot_instructions = context.bot_instructions
    user_context = context.user_context
    _echo_rel_ctx = context.echo_rel_ctx
    sender_id = follower.follower_id if hasattr(follower, 'follower_id') else ""
    frustration_level = cognitive_metadata.get("frustration_level", 0) if isinstance(cognitive_metadata, dict) else 0

    # Step 5b: Determine response strategy
    strategy_hint = _determine_response_strategy(
        message=message,
        intent_value=intent_value,
        relationship_type=_rel_type,
        is_first_message=(follower.total_messages <= 1),
        is_friend=is_friend,
        follower_interests=follower.interests,
        lead_stage=current_stage,
    )
    if strategy_hint:
        cognitive_metadata["response_strategy"] = strategy_hint.split(".")[0]
        logger.info(f"[STRATEGY] {strategy_hint.split('.')[0]}")

    # Step 5c: Load learning rules
    learning_rules_section = ""
    if ENABLE_LEARNING_RULES:
        learning_rules_section = await _load_learning_rules(
            agent, intent_value, _rel_type, current_stage, sender_id, cognitive_metadata
        )

    # Step 5d: Load preference profile
    preference_profile_section = ""
    if ENABLE_PREFERENCE_PROFILE:
        preference_profile_section = await _load_preference_profile(
            agent, sender_id, cognitive_metadata
        )

    # Step 5e: Load gold examples
    gold_examples_section = ""
    if ENABLE_GOLD_EXAMPLES:
        gold_examples_section = await _load_gold_examples(
            agent, intent_value, _rel_type, current_stage, sender_id, cognitive_metadata
        )

    # Step 6: Build full prompt
    prompt_parts = [user_context]
    if _bot_instructions:
        prompt_parts.append(
            "=== INSTRUCCIONES ESPECÍFICAS PARA ESTE LEAD ===\n"
            f"{_bot_instructions}\n"
            "=== FIN INSTRUCCIONES ==="
        )
    if learning_rules_section:
        prompt_parts.append(learning_rules_section)
    if preference_profile_section:
        prompt_parts.append(preference_profile_section)
    if gold_examples_section:
        prompt_parts.append(gold_examples_section)
    if strategy_hint:
        prompt_parts.append(strategy_hint)
    if frustration_level > 0.5:
        prompt_parts.append(
            f"⚠️ NOTA: El usuario parece frustrado (nivel: {frustration_level:.0%}). "
            f"Responde con empatía y ofrece ayuda concreta."
        )
    prompt_parts.append(f"Mensaje actual:\n<user_message>\n{message}\n</user_message>")
    full_prompt = "\n\n".join(prompt_parts)

    # Cap total context
    _MAX_CONTEXT_CHARS = AGENT_THRESHOLDS.max_context_chars
    if len(system_prompt) > _MAX_CONTEXT_CHARS:
        original_len = len(system_prompt)
        system_prompt = _smart_truncate_context(system_prompt, _MAX_CONTEXT_CHARS)
        cognitive_metadata["prompt_truncated"] = True
        logger.info(f"[PROMPT] Smart-truncated system prompt from {original_len} to {len(system_prompt)} chars")

    # Log prompt size
    _est_tokens = len(system_prompt) // 4
    _section_sizes = {
        k: len(v) for k, v in [
            ("style", agent.style_prompt or ""),
            ("relational", context.relational_block),
            ("rag", context.rag_context), ("memory", context.memory_context),
            ("fewshot", context.few_shot_section), ("dna", context.dna_context),
            ("state", context.state_context), ("kb", context.kb_context),
            ("advanced", context.advanced_section),
        ] if v
    }
    logger.info(
        f"[TIMING] System prompt: {len(system_prompt)} chars (~{_est_tokens} tokens) "
        f"sections={_section_sizes}"
    )

    # LLM generation
    from core.providers.gemini_provider import generate_dm_response

    llm_messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": full_prompt},
    ]

    # Best-of-N (copilot only)
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
            logger.debug("[BestOfN] Failed, using single call: %s", bon_err)

    if best_of_n_result:
        from core.best_of_n import serialize_candidates

        llm_result = {
            "content": best_of_n_result.best.content,
            "model": best_of_n_result.best.model,
            "provider": best_of_n_result.best.provider,
            "latency_ms": best_of_n_result.total_latency_ms,
        }
        cognitive_metadata["best_of_n"] = serialize_candidates(best_of_n_result)
    else:
        _llm_max_tokens = 150
        _llm_temperature = 0.7
        if _echo_rel_ctx:
            _llm_max_tokens = _echo_rel_ctx.llm_max_tokens
            _llm_temperature = _echo_rel_ctx.llm_temperature
        llm_result = await generate_dm_response(
            llm_messages, max_tokens=_llm_max_tokens, temperature=_llm_temperature,
        )

    _t3 = time.monotonic()
    logger.info(f"[TIMING] LLM call: {int((_t3 - _t2) * 1000)}ms")

    if llm_result:
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
        logger.error("Primary cascade failed, using llm_service emergency fallback")
        llm_response = await agent.llm_service.generate(
            prompt=full_prompt, system_prompt=system_prompt
        )

    # Phase 4b: Self-consistency validation
    if ENABLE_SELF_CONSISTENCY:
        try:
            from core.reasoning.self_consistency import get_self_consistency_validator

            validator = get_self_consistency_validator(agent.llm_service)
            consistency = await validator.validate_response(
                query=message, response=llm_response.content, system_prompt=system_prompt,
            )
            if not consistency.is_consistent and consistency.response:
                logger.info(f"Self-consistency: replaced (conf={consistency.confidence:.2f})")
                llm_response.content = consistency.response
                cognitive_metadata["self_consistency_replaced"] = True
        except Exception as e:
            logger.debug(f"Self-consistency failed: {e}")

    return llm_response


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


async def _load_learning_rules(agent, intent_value, _rel_type, current_stage, sender_id, cognitive_metadata) -> str:
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
                return get_applicable_rules(
                    _c[0], intent=intent_value, relationship_type=_rel_type, lead_stage=current_stage,
                )
            finally:
                _s.close()

        _learning_rules = await asyncio.to_thread(_load_rules)
        if _learning_rules:
            lines = []
            for r in _learning_rules:
                lines.append(f"- {r['rule_text']}")
                if r.get("example_bad"):
                    lines.append(f'  NO: "{r["example_bad"]}"')
                if r.get("example_good"):
                    lines.append(f'  SI: "{r["example_good"]}"')
            cognitive_metadata["learning_rules_applied"] = len(_learning_rules)
            logger.info(f"[LEARNING] Injected {len(_learning_rules)} rules for {sender_id}")
            return (
                "=== REGLAS APRENDIDAS (del propio creador) ===\n"
                + "\n".join(lines) + "\n"
                "=== FIN REGLAS ==="
            )
    except Exception as lr_err:
        logger.debug(f"[LEARNING] Rule loading failed: {lr_err}")
    return ""


async def _load_preference_profile(agent, sender_id, cognitive_metadata) -> str:
    try:
        from services.preference_profile_service import compute_preference_profile, format_preference_profile_for_prompt

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
            cognitive_metadata["preference_profile"] = True
            logger.info(f"[PREFERENCE] Profile applied for {sender_id}")
            return format_preference_profile_for_prompt(_profile, agent.creator_id)
    except Exception as pp_err:
        logger.debug(f"[PREFERENCE] Profile loading failed: {pp_err}")
    return ""


async def _load_gold_examples(agent, intent_value, _rel_type, current_stage, sender_id, cognitive_metadata) -> str:
    try:
        from services.gold_examples_service import get_matching_examples

        def _load_examples():
            from api.database import SessionLocal
            from api.models import Creator

            _s = SessionLocal()
            try:
                _c = _s.query(Creator.id).filter_by(name=agent.creator_id).first()
                if not _c:
                    return []
                return get_matching_examples(
                    _c[0], intent=intent_value, relationship_type=_rel_type, lead_stage=current_stage,
                )
            finally:
                _s.close()

        _gold_examples = await asyncio.to_thread(_load_examples)
        if _gold_examples:
            ex_lines = []
            for ex in _gold_examples:
                ex_lines.append(
                    f"Lead: \"{ex['user_message']}\"\n"
                    f"{agent.creator_id}: \"{ex['creator_response']}\""
                )
            cognitive_metadata["gold_examples_injected"] = len(_gold_examples)
            logger.info(f"[FEWSHOT] Injected {len(_gold_examples)} examples for {sender_id}")
            return (
                f"=== EJEMPLOS DE COMO RESPONDE {agent.creator_id.upper()} ===\n"
                + "\n---\n".join(ex_lines) + "\n"
                "=== FIN EJEMPLOS ==="
            )
    except Exception as ge_err:
        logger.debug(f"[FEWSHOT] Example loading failed: {ge_err}")
    return ""
