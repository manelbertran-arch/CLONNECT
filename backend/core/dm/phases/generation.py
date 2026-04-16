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
ENABLE_PREFERENCE_PROFILE = os.getenv("ENABLE_PREFERENCE_PROFILE", "false").lower() == "true"
ENABLE_GOLD_EXAMPLES = os.getenv("ENABLE_GOLD_EXAMPLES", "false").lower() == "true"
ENABLE_BEST_OF_N = os.getenv("ENABLE_BEST_OF_N", "false").lower() == "true"
ENABLE_SELF_CONSISTENCY = os.getenv("ENABLE_SELF_CONSISTENCY", "false").lower() == "true"
ENABLE_LENGTH_HINTS = os.getenv("ENABLE_LENGTH_HINTS", "true").lower() == "true"
ENABLE_QUESTION_HINTS = os.getenv("ENABLE_QUESTION_HINTS", "true").lower() == "true"

# G6: Truncation recovery — retry count (operational param, not content heuristic)
MAX_TRUNCATION_RETRIES = int(os.getenv("MAX_TRUNCATION_RETRIES", "2"))


def _is_truncated_by_api(finish_reason: str | None) -> bool:
    """Return True iff the API explicitly signalled max_tokens was hit.

    Mirrors Claude Code's isWithheldMaxOutputTokens() which checks
    stop_reason === 'max_tokens'. All Clonnect providers normalize their
    API signal to OpenAI standard: finish_reason == 'length' means the
    model stopped because max_tokens was exhausted.

    Returns False when finish_reason is absent — never infers truncation
    from response content (zero hardcoding policy).
    """
    return finish_reason == "length"


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


def _build_style_anchor(creator_id: str) -> str:
    """Build a style anchor from creator's profile data.

    Returns a short reminder string with raw numbers from the profile,
    or empty string if no profile data exists.
    """
    try:
        from core.dm.style_normalizer import _load_baseline

        baseline = _load_baseline(creator_id)
        if not baseline:
            logger.warning("style_anchor: no profile for %s, skipping", creator_id)
            return ""

        parts = []
        length = baseline.get("length", {})
        emoji = baseline.get("emoji", {})
        punct = baseline.get("punctuation", {})

        median_len = length.get("char_median")
        if median_len is not None:
            parts.append(f"mensajes de ~{median_len} chars")

        emoji_rate = emoji.get("emoji_rate_pct")
        if emoji_rate is not None:
            parts.append(f"emoji rate: {emoji_rate:.0f}%")

        question_rate = punct.get("has_question_msg_pct", punct.get("question_rate_pct"))
        if question_rate is not None:
            parts.append(f"question rate: {question_rate:.0f}%")

        excl_rate = punct.get("exclamation_rate_pct", punct.get("has_exclamation_msg_pct"))
        if excl_rate is not None:
            parts.append(f"exclamation rate: {excl_rate:.0f}%")

        if parts:
            return "RECUERDA: " + ", ".join(parts) + "."
        return ""
    except Exception as e:
        logger.debug("style_anchor: failed for %s: %s", creator_id, e)
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

    # Step 5c: Learning rules — removed from runtime injection (April 2026).
    # Per TextGrad (Nature'24) and RBR (NeurIPS'24), rules competed with Doc D
    # persona description and showed neutral-to-negative impact. Rules are now
    # consumed by PersonaCompiler (weekly batch) which compiles behavioral
    # patterns into Doc D updates. See services/learning_rules_service.py.

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

    # Style Anchor: inject quantitative style reminder from creator profile
    if os.environ.get("ENABLE_STYLE_ANCHOR") == "true":
        _anchor = _build_style_anchor(agent.creator_id)
        if _anchor:
            full_prompt += "\n" + _anchor

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

    # G3+G4: Token distribution analytics + context health warnings (observability only)
    try:
        from core.dm.context_analytics import analyze_token_distribution, check_context_health
        _analytics = analyze_token_distribution(
            section_sizes=_section_sizes,
            system_prompt=system_prompt,
            history_messages=history,
        )
        for _w in check_context_health(_analytics):
            _lvl = _w["level"]
            if _lvl == "critical":
                logger.error("[ContextHealth] CRITICAL: %s", _w["message"])
            elif _lvl == "warning":
                logger.warning("[ContextHealth] WARNING: %s", _w["message"])
            else:
                logger.info("[ContextHealth] INFO: %s", _w["message"])
    except Exception as _analytics_err:
        logger.debug("[TokenAnalytics] Skipped: %s", _analytics_err)

    # G5: Cache boundary prefix metrics (Sprint 4)
    _cache_prefix = cognitive_metadata.get("cache_prefix_chars", 0)
    if _cache_prefix > 0:
        _cache_ratio = _cache_prefix / len(system_prompt) if system_prompt else 0
        logger.info(
            "[CacheBoundary] prefix=%d/%d chars (%.0f%% cacheable)",
            _cache_prefix, len(system_prompt), _cache_ratio * 100,
        )

    # LLM generation: Flash-Lite → GPT-4o-mini (2 providers, nothing else)
    # Path: webhook → process_dm() → generate_dm_response() → gemini/openai
    from core.providers.gemini_provider import generate_dm_response

    # Build multi-turn messages: system + history turns + current user message.
    # History is passed as separate user/assistant messages so the LLM sees full
    # conversational context (vs the old single-message flattened format).
    llm_messages = [{"role": "system", "content": system_prompt}]
    if history:
        from core.dm.history_compactor import ENABLE_HISTORY_COMPACTION
        if ENABLE_HISTORY_COMPACTION:
            # Sprint 2.7: CC-faithful pipeline order.
            # CC (sessionMemoryCompact.ts:324-397) operates on ALL raw messages
            # with zero dedup — Anthropic API accepts consecutive same-role.
            # Gemini requires strict alternation, so we dedup AFTER selection.
            #
            # Pipeline: ALL raw → filter invalid → select(budget) → truncate(600) → dedup → API
            raw_pool: list = []
            for msg in history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role not in ("user", "assistant") or not content:
                    continue
                raw_pool.append({"role": role, "content": content})

            try:
                from core.dm.history_compactor import select_and_compact
                _total_budget = 10 * 600  # 6000 chars — same as uniform truncation
                _creator_profile = {}
                try:
                    import json as _json
                    _sp_path = os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                        "evaluation_profiles", agent.creator_id, "style_profile.json",
                    )
                    if os.path.exists(_sp_path):
                        with open(_sp_path) as _f:
                            _creator_profile = _json.load(_f)
                        logger.info("[HISTORY-COMPACT] Loaded style_profile for %s from %s", agent.creator_id, _sp_path)
                    else:
                        logger.warning("[HISTORY-COMPACT] style_profile.json not found at %s — compactor will use uniform scoring", _sp_path)
                except Exception as _profile_err:
                    logger.error("[HISTORY-COMPACT] Failed to load style_profile for %s: %s", agent.creator_id, _profile_err)
                _existing_facts: list = cognitive_metadata.get(
                    "memory_facts", []
                )
                compacted = select_and_compact(
                    raw_pool, _creator_profile, _total_budget,
                    existing_facts=_existing_facts,
                )
                # Post-selection: filter boundaries, dedup same-role (Gemini),
                # truncate per-message at 600 chars (matching legacy behavior).
                for msg in compacted:
                    if msg.get("_is_compact_boundary"):
                        continue
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    if not content:
                        continue
                    if len(content) > 600:
                        content = content[:597] + "..."
                    if llm_messages and llm_messages[-1]["role"] == role:
                        llm_messages[-1]["content"] += "\n" + content
                    else:
                        llm_messages.append({"role": role, "content": content})
                logger.info(
                    "[HISTORY-COMPACT] select_and_compact: %d→%d msgs (pool=%d)",
                    len(history), len(compacted), len(raw_pool),
                )
            except Exception as _hc_err:
                logger.warning("[HISTORY-COMPACT] Failed, falling back to uniform: %s", _hc_err)
                # Fallback: last 10 messages with uniform truncation
                fallback = raw_pool[-10:]
                while fallback and fallback[0].get("role") != "user":
                    fallback = fallback[1:]
                for msg in fallback:
                    content = msg["content"]
                    if len(content) > 600:
                        content = content[:597] + "..."
                    # Same-role dedup for Gemini strict alternation
                    if llm_messages and llm_messages[-1]["role"] == msg["role"]:
                        llm_messages[-1]["content"] += "\n" + content
                    else:
                        llm_messages.append({"role": msg["role"], "content": content})
        else:
            # Original uniform truncation (feature flag OFF) — exact legacy behavior
            history_slice = history[-10:]
            while history_slice and history_slice[0].get("role") != "user":
                history_slice = history_slice[1:]
            deduped: list = []
            for msg in history_slice:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role not in ("user", "assistant") or not content:
                    continue
                if deduped and deduped[-1]["role"] == role:
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
        # Calibration-derived limit prevents Gemini
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

        # G6: Truncation recovery — retry only when API signals max_tokens was hit.
        # Detection: finish_reason == "length" (OpenAI standard, propagated by all providers).
        # Cap: 2x calibration max_tokens (data-driven per creator). If no finish_reason
        # available, skip silently — never infer truncation from response content.
        _finish_reason = llm_result.get("finish_reason") if llm_result else None
        if llm_result and _finish_reason is None:
            logger.debug("[TruncationRecovery] finish_reason not available from provider — skipping")
        elif llm_result and _is_truncated_by_api(_finish_reason):
            # Retry cap derived from calibration. Multiplier is env-configurable;
            # _llm_max_tokens is already calibration-derived.
            _retry_multiplier = float(os.getenv("TRUNCATION_RETRY_MULTIPLIER", "2.0"))
            _retry_cap = int(_llm_max_tokens * _retry_multiplier)
            _best_result = llm_result
            for _retry_n in range(MAX_TRUNCATION_RETRIES):
                logger.warning(
                    "[TruncationRecovery] API signalled max_tokens hit (finish_reason=length, "
                    "attempt %d/%d), retrying with max_tokens=%d",
                    _retry_n + 1, MAX_TRUNCATION_RETRIES, _retry_cap,
                )
                try:
                    _retry_result = await generate_dm_response(
                        llm_messages,
                        max_tokens=_retry_cap,
                        temperature=_llm_temperature,
                    )
                    if _retry_result:
                        # Keep the longest result; stop if API no longer signals truncation
                        if len(_retry_result.get("content", "")) > len(_best_result.get("content", "")):
                            _best_result = _retry_result
                        if not _is_truncated_by_api(_retry_result.get("finish_reason")):
                            _best_result = _retry_result
                            logger.info(
                                "[TruncationRecovery] Recovered on attempt %d (max_tokens=%d)",
                                _retry_n + 1, _retry_cap,
                            )
                            break
                except Exception as _retry_err:
                    logger.warning("[TruncationRecovery] Retry %d failed: %s", _retry_n + 1, _retry_err)
                    break
            if _best_result is not llm_result:
                cognitive_metadata["truncation_recovery"] = True
            llm_result = _best_result

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
        # CCEE evaluation mode or DISABLE_FALLBACK: never fall through to emergency fallback.
        if os.environ.get("CCEE_NO_FALLBACK") or os.environ.get("DISABLE_FALLBACK") == "true":
            logger.error("[NO-FALLBACK] Primary provider returned None and fallback disabled — raising to skip case")
            raise RuntimeError("Primary provider returned empty, no fallback allowed (CCEE_NO_FALLBACK or DISABLE_FALLBACK)")
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
        except Exception as e:
            logger.debug(f"Self-consistency failed: {e}")

    return llm_response


