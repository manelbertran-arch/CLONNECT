"""Phase 4: LLM Generation — prompt finalization + LLM call with fallback chain."""

import asyncio
import logging
import os
import time
from typing import Dict

from core.agent_config import AGENT_THRESHOLDS
from core.dm.models import ContextBundle
from core.dm.strategy import _determine_response_strategy
from core.dm.text_utils import _smart_truncate_context
from core.reasoning.self_consistency import get_self_consistency_validator
from services import LLMResponse

logger = logging.getLogger(__name__)

# Feature flags for generation phase
ENABLE_LEARNING_RULES = os.getenv("ENABLE_LEARNING_RULES", "false").lower() == "true"
ENABLE_PREFERENCE_PROFILE = os.getenv("ENABLE_PREFERENCE_PROFILE", "false").lower() == "true"
ENABLE_GOLD_EXAMPLES = os.getenv("ENABLE_GOLD_EXAMPLES", "false").lower() == "true"
ENABLE_BEST_OF_N = os.getenv("ENABLE_BEST_OF_N", "false").lower() == "true"
ENABLE_SELF_CONSISTENCY = os.getenv("ENABLE_SELF_CONSISTENCY", "false").lower() == "true"
ENABLE_CHAIN_OF_THOUGHT = os.getenv("ENABLE_CHAIN_OF_THOUGHT", "false").lower() == "true"


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
    _bot_instructions = context.bot_instructions
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
        is_first_message=(follower.total_messages <= 1),
        is_friend=False,  # Product suppression only — never affects strategy text
        follower_interests=follower.interests,
        lead_stage=current_stage,
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
                    return get_applicable_rules(
                        _c[0], intent=intent_value,
                        relationship_type=_rel_type,
                        lead_stage=current_stage,
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

    # Step 5e: Load gold examples (few-shot)
    gold_examples_section = ""
    if ENABLE_GOLD_EXAMPLES:
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
                        _c[0], intent=intent_value,
                        relationship_type=_rel_type,
                        lead_stage=current_stage,
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
                gold_examples_section = "\n---\n".join(ex_lines)
                cognitive_metadata["gold_examples_injected"] = len(_gold_examples)
                logger.info(f"[FEWSHOT] Injected {len(_gold_examples)} examples for {sender_id}")
        except Exception as ge_err:
            logger.debug(f"[FEWSHOT] Example loading failed: {ge_err}")

    # Step 6: Build full prompt — pure message as last content, no XML wrappers.
    # User context (username, stage, interests) is already in system_prompt via
    # relational_block + dna_context + state_context. No need to repeat here.
    prompt_parts = []
    if _bot_instructions:
        prompt_parts.append(_bot_instructions)
    if learning_rules_section:
        prompt_parts.append(learning_rules_section)
    if preference_profile_section:
        prompt_parts.append(preference_profile_section)
    if gold_examples_section:
        prompt_parts.append(gold_examples_section)
    if strategy_hint:
        prompt_parts.append(strategy_hint)
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

    # Step 5f: Chain of Thought reasoning for complex queries
    # Only fires when flag is ON — adds extra LLM call (500 tokens) for health/product/multi-part queries
    if ENABLE_CHAIN_OF_THOUGHT and hasattr(agent, "chain_of_thought"):
        try:
            _is_complex, _query_type = agent.chain_of_thought._is_complex_query(message)
            if _is_complex:
                _cot_result = await agent.chain_of_thought.generate(
                    message,
                    context={"creator_name": agent.creator_id, "products": agent.products},
                )
                if _cot_result.reasoning_steps:
                    _cot_section = "\n".join(f"- {s}" for s in _cot_result.reasoning_steps)
                    system_prompt = system_prompt + "\n\n" + _cot_section
                    cognitive_metadata["cot_applied"] = True
                    cognitive_metadata["cot_query_type"] = _query_type
                    logger.info(
                        f"[COT] Applied {len(_cot_result.reasoning_steps)} reasoning steps "
                        f"for {_query_type} query"
                    )
        except Exception as _cot_err:
            logger.debug(f"[COT] Chain of Thought failed: {_cot_err}")

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
        for msg in history_slice:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("user", "assistant") and content:
                # Truncate very long individual messages to control token spend
                if len(content) > 600:
                    content = content[:597] + "..."
                llm_messages.append({"role": role, "content": content})
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
        # Priority: ECHO adapter (highest) > calibration baseline > hardcoded default
        _llm_max_tokens = 100   # conservative default (was 150 — too permissive)
        _llm_temperature = 0.7  # universal default
        _cal_baseline = (agent.calibration or {}).get("baseline", {}) if agent.calibration else {}
        if _cal_baseline.get("temperature") is not None:
            _llm_temperature = float(_cal_baseline["temperature"])
        if _cal_baseline.get("max_tokens") is not None:
            _llm_max_tokens = int(_cal_baseline["max_tokens"])
        if _echo_rel_ctx:
            _llm_max_tokens = _echo_rel_ctx.llm_max_tokens
            _llm_temperature = _echo_rel_ctx.llm_temperature
        llm_result = await generate_dm_response(
            llm_messages,
            max_tokens=_llm_max_tokens,
            temperature=_llm_temperature,
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
        # Both Flash-Lite and GPT-4o-mini failed — emergency fallback
        logger.error("Primary cascade failed, using llm_service emergency fallback")
        llm_response = await agent.llm_service.generate(
            prompt=full_prompt, system_prompt=system_prompt
        )

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
