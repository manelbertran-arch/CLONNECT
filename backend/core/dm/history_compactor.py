"""History Compactor — positional message selection (recency-first).

Adapted from Claude Code's calculateMessagesToKeepIndex pattern
(sessionMemoryCompact.ts:324-397): expand backwards from most recent messages
until char budget exhausted, then stop.

Sprint 2.3 (2026-04-11): CC-faithful rewrite after forensic diff.
  Removed: MAX_OUTPUT_MESSAGES hard limit (not in CC — CC uses only token budget),
  slot reservation, topic hints, content type breakdown, per-message truncation of
  kept messages, dead code (importance scoring, compact_history).
  Added: dedup-safe output, budget-only expansion.

Selection strategy: most recent messages are kept, oldest are dropped.
Pure recency — no importance scoring. Budget is char-based (CC uses tokens).
Dropped messages get a minimal summary (counts + facts + verbatim marker).
"""

import logging
import os
import re
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Feature flag — default OFF for safe rollout
ENABLE_HISTORY_COMPACTION = os.getenv("ENABLE_HISTORY_COMPACTION", "false").lower() == "true"

# MIN_RECENT_MESSAGES: Guarantee this many of the most recent substantive
# messages survive. CC uses minTextBlockMessages=5 (sessionMemoryCompact.ts:59).
# DM conversations are shorter than coding sessions; 3 preserves the thread.
MIN_RECENT_MESSAGES = int(os.getenv("COMPACTOR_MIN_RECENT_MESSAGES", "3"))

# LLM-generated summary (CC: extractSessionMemory, sessionMemory.ts:272-350).
# Default OFF — template-based summary is zero-cost and sufficient for most DMs.
ENABLE_LLM_SUMMARY = os.getenv("ENABLE_LLM_SUMMARY", "false").lower() == "true"

# Sprint 2.6: Summary + verbatim marker injection — default OFF.
# ~142 chars of Spanish meta-text contaminated style context (50/50 CCEE cases).
# When OFF, compactor output = boundary + kept messages only (clean context).
ENABLE_COMPACTOR_SUMMARY = os.getenv("ENABLE_COMPACTOR_SUMMARY", "false").lower() == "true"
ENABLE_VERBATIM_MARKER = os.getenv("ENABLE_VERBATIM_MARKER", "false").lower() == "true"

# --- Compact boundary marker (CC: messages.ts:4530-4555) ---
COMPACT_BOUNDARY_CONTENT = os.getenv(
    "COMPACTOR_BOUNDARY_MARKER",
    "[__COMPACT_BOUNDARY__]",
)


def is_compact_boundary(message: Dict) -> bool:
    """Check if a message is a compact boundary marker.

    CC equivalent: isCompactBoundaryMessage (messages.ts:4608-4612).
    """
    return message.get("_is_compact_boundary") is True or (
        message.get("content", "").strip() == COMPACT_BOUNDARY_CONTENT
    )


def create_compact_boundary(
    messages_summarized: int,
    trigger: str = "auto",
) -> Dict:
    """Create a compact boundary marker message.

    CC equivalent: createCompactBoundaryMessage (messages.ts:4530-4555).
    """
    from datetime import datetime, timezone
    return {
        "role": "user",
        "content": COMPACT_BOUNDARY_CONTENT,
        "importance": 0.0,
        "_is_compact_boundary": True,
        "_compact_metadata": {
            "trigger": trigger,
            "messages_summarized": messages_summarized,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }


# ---- Content type patterns (derived from DB sample analysis) ----
_MEDIA_REF_PATTERN = re.compile(
    r"^\[(?:audio|image|video|🏷️ Sticker|Media/Attachment|🎤 Audio)\]",
    re.IGNORECASE,
)
_PURE_REACTION_PATTERN = re.compile(r"^[\U0001F000-\U0001FFFF\s\u2600-\u27BF\u200D\uFE0F]+$")


def _is_substantive(text: str) -> bool:
    """A message has substantive text content (not just media/emoji).

    Analogous to CC's hasTextBlocks() (sessionMemoryCompact.ts:135-150).
    """
    if not text or not text.strip():
        return False
    stripped = text.strip()
    if _MEDIA_REF_PATTERN.match(stripped):
        return False
    if _PURE_REACTION_PATTERN.match(stripped):
        return False
    return True


# ---------------------------------------------------------------------------
# select_and_compact — Budget-only expansion (CC pattern)
# ---------------------------------------------------------------------------

def select_and_compact(
    all_messages: List[Dict],
    creator_profile: dict,
    total_budget_chars: int,
    existing_facts: Optional[List[str]] = None,
) -> List[Dict]:
    """Select messages from the full history pool within budget.

    CC-faithful positional selection (calculateMessagesToKeepIndex,
    sessionMemoryCompact.ts:324-397):

    1. Start with no messages kept (equivalent to CC's lastSummarizedIndex=-1
       → startIndex=messages.length).
    2. Expand backwards: add messages until total_budget_chars exhausted.
       CC expands until maxTokens hit (line 382-384). No message count limit.
    3. Guarantee MIN_RECENT_MESSAGES substantive messages (CC: minTextBlockMessages).
    4. If messages were dropped, prepend a summary (CC: getCompactUserSummaryMessage,
       prompt.ts:345-355) with counts + facts + verbatim marker.
    5. Filter old compact boundaries (CC: line 579-581).

    Differences from CC:
    - Char-based budget vs token-based (no tokenizer in DM hot path).
    - Template summary vs pre-computed session memory file.
    - No per-message truncation of kept messages (CC doesn't truncate either).

    Returns:
        List of dicts in chronological order. Total chars <= total_budget_chars.
    """
    if not all_messages:
        return []

    # --- Phase 0: Detect compact boundary floor (CC: line 370-371) ---
    boundary_floor = 0
    for i in range(len(all_messages) - 1, -1, -1):
        if is_compact_boundary(all_messages[i]):
            boundary_floor = i + 1
            break

    # Filter old boundaries (CC: line 579-581)
    filtered = [m for m in all_messages if not is_compact_boundary(m)]
    n = len(filtered)
    if n == 0:
        return []

    # Recalculate floor after filtering
    _boundaries_before_floor = sum(
        1 for i in range(min(boundary_floor, len(all_messages)))
        if is_compact_boundary(all_messages[i])
    )
    boundary_floor = max(0, boundary_floor - _boundaries_before_floor)

    # --- Phase 1: Backward expansion until budget exhausted (CC: line 364-393) ---
    # CC: startIndex = messages.length (no messages kept), expand backward.
    # Stop when maxTokens hit. No message count limit in CC.
    start_index = n
    total_chars = 0
    substantive_count = 0

    for i in range(n - 1, max(boundary_floor - 1, -1), -1):
        msg_chars = len(filtered[i].get("content", ""))

        # Stop if adding this message exceeds budget (CC: line 382-384)
        if total_chars + msg_chars > total_budget_chars:
            # But keep expanding if we haven't met MIN_RECENT_MESSAGES
            # (CC: line 357-360 checks both minTokens AND minTextBlockMessages)
            if substantive_count >= MIN_RECENT_MESSAGES:
                break
            # Skip this oversized message but continue looking for shorter ones
            continue

        start_index = i
        total_chars += msg_chars
        if _is_substantive(filtered[i].get("content", "")):
            substantive_count += 1

    # --- Phase 2: Build output ---
    kept = filtered[start_index:]
    dropped = filtered[:start_index]

    # If no drops, return kept messages directly — no summary needed
    if not dropped:
        return [
            {"role": m["role"], "content": m["content"], "importance": 1.0}
            for m in kept
        ]

    # --- Phase 3: Build summary for dropped messages (CC: prompt.ts:345-355) ---
    # Sprint 2.6: Summary injection gated by ENABLE_COMPACTOR_SUMMARY (default OFF).
    # When OFF, compactor output = boundary + kept messages only (clean context).
    summary_msg = None
    if ENABLE_COMPACTOR_SUMMARY:
        if ENABLE_LLM_SUMMARY:
            summary_msg = _build_llm_summary(dropped, existing_facts)
        else:
            summary_msg = _build_dropped_summary(dropped, existing_facts)

    result = []
    if summary_msg:
        # CC: createUserMessage with isCompactSummary=true (sessionMemoryCompact.ts:477-481)
        result.append({
            "role": "user",
            "content": summary_msg,
            "importance": 1.0,
            "_is_context_summary": True,
        })

    # CC: boundaryMarker before messagesToKeep (compact.ts:330-338)
    result.append(create_compact_boundary(messages_summarized=len(dropped)))

    # CC: messagesToKeep — kept whole, no per-message truncation
    for m in kept:
        result.append({
            "role": m["role"],
            "content": m["content"],
            "importance": 1.0,
        })

    if result:
        n_kept = sum(
            1 for m in result
            if m.get("importance") == 1.0 and not m.get("_is_context_summary")
        )
        total_out_chars = sum(len(m["content"]) for m in result)
        logger.info(
            "[HistoryCompactor] select_and_compact: %d→%d msgs "
            "(kept=%d, dropped=%d). %d/%d chars.",
            n, len(result), n_kept, len(dropped),
            total_out_chars, total_budget_chars,
        )

    return result


# Maximum chars for the dropped-message summary.
MAX_SUMMARY_CHARS = int(os.getenv("COMPACTOR_MAX_SUMMARY_CHARS", "500"))


def _truncate_section(section_content: str, max_chars: int) -> str:
    """Truncate a summary section at a logical boundary.

    Follows CC's flushSessionSection pattern (prompts.ts:298-323).
    """
    if len(section_content) <= max_chars:
        return section_content

    truncation_marker = " [... truncado]"
    cut_at = max_chars - len(truncation_marker)
    if cut_at <= 0:
        return section_content[:max_chars]

    pipe_pos = section_content.rfind(" | ", 0, cut_at)
    if pipe_pos > 0:
        return section_content[:pipe_pos] + truncation_marker

    space_pos = section_content.rfind(" ", 0, cut_at)
    if space_pos > 0:
        return section_content[:space_pos] + truncation_marker

    return section_content[:cut_at] + truncation_marker


def _build_dropped_summary(
    dropped_msgs: List[Dict],
    existing_facts: Optional[List[str]] = None,
) -> Optional[str]:
    """Build a context summary for excluded messages.

    CC's approach (sessionMemoryCompact.ts:437-503):
    - Uses pre-computed session memory (structured markdown sections).
    - Wraps in: "This session is being continued..." (prompt.ts:345-355).
    - Appends: "Recent messages are preserved verbatim." (prompt.ts:353-354).

    Clonnect adaptation:
    - Template with counts + MemoryEngine facts + verbatim marker.
    - No topic hints, no content type breakdown (not in CC).

    Returns None if fewer than 3 messages dropped.
    """
    if len(dropped_msgs) < 3:
        return None

    n_dropped = len(dropped_msgs)
    n_user = sum(1 for m in dropped_msgs if m.get("role") == "user")
    n_assistant = n_dropped - n_user

    # Section 1: Counts (CC: summary header with message count)
    section_counts = (
        f"[Contexto anterior: {n_dropped} mensajes previos no incluidos "
        f"({n_user} del usuario, {n_assistant} del creador)]"
    )

    # Section 2: Facts from MemoryEngine (CC equivalent: session memory content)
    section_facts = ""
    if existing_facts:
        facts_budget = MAX_SUMMARY_CHARS - len(section_counts) - 80
        raw_facts = "[Datos recordados: " + " | ".join(existing_facts) + "]"
        section_facts = _truncate_section(raw_facts, max(50, facts_budget))

    # CC: "Recent messages are preserved verbatim." (prompt.ts:353-354)
    # Sprint 2.6: Gated by ENABLE_VERBATIM_MARKER (default OFF).
    verbatim_marker = "[Los mensajes siguientes se conservan literalmente.]" if ENABLE_VERBATIM_MARKER else ""

    sections = [s for s in [section_counts, section_facts, verbatim_marker] if s]
    return "\n".join(sections)


# --- LLM Summary (CC: extractSessionMemory, sessionMemory.ts:272-350) ---
LLM_SUMMARY_PROMPT = os.getenv("COMPACTOR_LLM_SUMMARY_PROMPT", """\
Eres un asistente que resume conversaciones previas de manera concisa.

A continuación tienes mensajes de una conversación entre un usuario y un creador \
que no caben en el contexto. Resume los puntos clave en máximo {max_chars} caracteres:
- Temas tratados
- Preguntas del usuario y respuestas del creador
- Acuerdos o compromisos mencionados
- Tono/estado emocional de la conversación

Mensajes:
{messages}

{facts_section}\
Escribe SOLO el resumen, sin preámbulo ni explicación. Usa el mismo idioma de los mensajes.""")

LLM_SUMMARY_MODEL = os.getenv("COMPACTOR_LLM_SUMMARY_MODEL", "")


def _build_llm_summary(
    dropped_msgs: List[Dict],
    existing_facts: Optional[List[str]] = None,
) -> Optional[str]:
    """Build a context summary using an LLM call.

    CC equivalent: runForkedAgent (sessionMemory.ts:318-325).
    Falls back to template on failure.
    """
    import time

    if len(dropped_msgs) < 3:
        return None

    msg_lines = []
    for m in dropped_msgs:
        content = m.get("content", "")
        if _is_substantive(content):
            role_label = "Usuario" if m.get("role") == "user" else "Creador"
            msg_lines.append(f"  {role_label}: {content[:200]}")

    if not msg_lines:
        return _build_dropped_summary(dropped_msgs, existing_facts)

    messages_text = "\n".join(msg_lines)

    facts_section = ""
    if existing_facts:
        facts_text = "\n".join(f"  - {f}" for f in existing_facts[:10])
        facts_section = f"Datos conocidos sobre el usuario:\n{facts_text}\n\n"

    prompt = LLM_SUMMARY_PROMPT.format(
        max_chars=MAX_SUMMARY_CHARS - 100,
        messages=messages_text,
        facts_section=facts_section,
    )

    start_ms = time.monotonic()
    try:
        llm_summary = _call_summary_llm(prompt)
    except Exception as e:
        logger.warning("[HistoryCompactor] LLM summary failed: %s. Falling back to template.", e)
        return _build_dropped_summary(dropped_msgs, existing_facts)

    elapsed_ms = (time.monotonic() - start_ms) * 1000
    logger.info("[HistoryCompactor] LLM summary: %.0fms, %d chars", elapsed_ms, len(llm_summary))

    if not llm_summary or not llm_summary.strip():
        return _build_dropped_summary(dropped_msgs, existing_facts)

    n_dropped = len(dropped_msgs)
    n_user = sum(1 for m in dropped_msgs if m.get("role") == "user")
    n_assistant = n_dropped - n_user
    header = (
        f"[Contexto anterior: {n_dropped} mensajes resumidos "
        f"({n_user} del usuario, {n_assistant} del creador)]"
    )
    verbatim = "[Los mensajes siguientes se conservan literalmente.]" if ENABLE_VERBATIM_MARKER else ""

    summary_body = _truncate_section(
        llm_summary.strip(),
        MAX_SUMMARY_CHARS - len(header) - len(verbatim) - 10,
    )

    sections = [s for s in [header, summary_body, verbatim] if s]
    return "\n".join(sections)


def _call_summary_llm(prompt: str) -> str:
    """Call the LLM for summary generation.

    CC equivalent: runForkedAgent (sessionMemory.ts:318-325).
    """
    model = LLM_SUMMARY_MODEL

    if not model or "gemini" in model.lower():
        try:
            import google.generativeai as genai
            _api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_AI_API_KEY")
            if _api_key:
                genai.configure(api_key=_api_key)
                _model_name = model if model else "gemini-2.0-flash-lite"
                m = genai.GenerativeModel(_model_name)
                response = m.generate_content(prompt)
                if response and response.text:
                    return response.text.strip()
        except Exception as e:
            logger.debug("[HistoryCompactor] Gemini summary failed: %s", e)

    raise RuntimeError("No LLM provider available for summary generation")
