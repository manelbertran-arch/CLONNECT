"""G3+G4: Token distribution analytics and context health warnings.

Observability-only module — reads prompt composition and emits structured
logs. Does NOT modify the prompt or the pipeline.

Usage (in generation.py, after existing prompt-size logging):

    from core.dm.context_analytics import analyze_token_distribution, check_context_health
    analytics = analyze_token_distribution(_section_sizes, system_prompt, history)
    for warning in check_context_health(analytics):
        ...
"""

import logging
import os

logger = logging.getLogger(__name__)

# ── Thresholds (all overridable via env vars) ─────────────────────────────────
CONTEXT_WARNING_THRESHOLD = float(os.getenv("CONTEXT_WARNING_THRESHOLD", "0.80"))
CONTEXT_CRITICAL_THRESHOLD = float(os.getenv("CONTEXT_CRITICAL_THRESHOLD", "0.90"))
SECTION_WARNING_THRESHOLD = float(os.getenv("SECTION_WARNING_THRESHOLD", "0.40"))
DEFAULT_MODEL_CONTEXT_WINDOW = int(os.getenv("MODEL_CONTEXT_WINDOW", "32768"))

# chars → tokens rough estimate (same formula used elsewhere in the pipeline)
_CHARS_PER_TOKEN = int(os.getenv("CONTEXT_CHARS_PER_TOKEN", "4"))

# ── Prometheus metrics (optional — graceful no-op if prometheus_client absent) ─
try:
    from prometheus_client import Counter, REGISTRY as _REGISTRY

    def _get_or_create_counter(name: str, doc: str, labelnames: list | None = None) -> Counter:
        # Registry stores collectors by base name (strips _total suffix for Counters)
        base = name[:-6] if name.endswith("_total") else name
        if base in _REGISTRY._names_to_collectors:
            return _REGISTRY._names_to_collectors[base]
        return Counter(name, doc, labelnames or [], registry=_REGISTRY)

    _CONTEXT_TOKENS_TOTAL = _get_or_create_counter(
        "context_tokens_total",
        "Cumulative estimated tokens measured by context_analytics",
    )
    _CONTEXT_HEALTH_WARNINGS_TOTAL = _get_or_create_counter(
        "context_health_warnings_total",
        "Number of context health warnings emitted",
        ["level"],
    )
    _PROMETHEUS_AVAILABLE = True
except Exception:
    _PROMETHEUS_AVAILABLE = False


def _chars_to_tokens(chars: int) -> int:
    return max(0, chars // _CHARS_PER_TOKEN)


def analyze_token_distribution(
    section_sizes: dict,
    system_prompt: str,
    history_messages: list,
    model_context_window: int = DEFAULT_MODEL_CONTEXT_WINDOW,
) -> dict:
    """Analyse token distribution across prompt sections.

    Args:
        section_sizes: {section_name: char_count} — already computed by
            generation.py (values are len() of each section string).
        system_prompt: fully assembled system prompt (post-truncation).
        history_messages: list of {"role": ..., "content": ...} dicts.
        model_context_window: usable token budget for this model.

    Returns:
        {
            "sections": {name: {"chars": int, "tokens": int, "pct_of_total": float}},
            "history_tokens": int,
            "history_pct_of_total": float,
            "system_prompt_tokens": int,
            "total_tokens": int,
            "context_window": int,
            "usage_ratio": float,          # total / context_window
            "largest_section": str,
            "largest_section_pct": float,
            "over_section_threshold": bool, # any section > SECTION_WARNING_THRESHOLD
        }
    """
    try:
        # Section token breakdown
        section_data: dict = {}
        for name, char_count in section_sizes.items():
            if char_count and char_count > 0:
                section_data[name] = {
                    "chars": char_count,
                    "tokens": _chars_to_tokens(char_count),
                }

        # History tokens (sum all message contents)
        history_chars = sum(
            len(msg.get("content", ""))
            for msg in (history_messages or [])
            if isinstance(msg, dict)
        )
        history_tokens = _chars_to_tokens(history_chars)

        # Full system prompt tokens (reflects actual post-truncation size)
        system_prompt_tokens = _chars_to_tokens(len(system_prompt))

        # Total: use system_prompt_tokens as the authoritative number since it
        # already includes all assembled sections. Add history on top.
        total_tokens = system_prompt_tokens + history_tokens

        # Pct of total for each section
        for name in section_data:
            pct = (section_data[name]["tokens"] / total_tokens * 100) if total_tokens else 0
            section_data[name]["pct_of_total"] = round(pct, 1)

        history_pct = round(history_tokens / total_tokens * 100, 1) if total_tokens else 0

        # Largest section (include history as a virtual section)
        all_sections = {**{n: d["tokens"] for n, d in section_data.items()}, "history": history_tokens}
        largest_section = max(all_sections, key=lambda k: all_sections[k]) if all_sections else "none"
        largest_tokens = all_sections.get(largest_section, 0)
        largest_pct = round(largest_tokens / total_tokens * 100, 1) if total_tokens else 0

        usage_ratio = total_tokens / model_context_window if model_context_window else 0

        # Any individual section over the per-section threshold?
        section_threshold_tokens = total_tokens * SECTION_WARNING_THRESHOLD
        over_section_threshold = any(
            d["tokens"] >= section_threshold_tokens for d in section_data.values()
        ) or (history_tokens >= section_threshold_tokens)

        analytics = {
            "sections": section_data,
            "history_tokens": history_tokens,
            "history_pct_of_total": history_pct,
            "system_prompt_tokens": system_prompt_tokens,
            "total_tokens": total_tokens,
            "context_window": model_context_window,
            "usage_ratio": round(usage_ratio, 3),
            "largest_section": largest_section,
            "largest_section_pct": largest_pct,
            "over_section_threshold": over_section_threshold,
        }

        # Emit the compact distribution log
        section_parts = ", ".join(
            f"{n}={d['tokens']}({d['pct_of_total']:.0f}%)"
            for n, d in sorted(section_data.items(), key=lambda x: -x[1]["tokens"])
        )
        if history_tokens:
            section_parts += f", history={history_tokens}({history_pct:.0f}%)"
        logger.info(
            "[TokenAnalytics] Distribution: %s | Total: %d/%d (%.0f%%) | Largest: %s(%.0f%%)",
            section_parts,
            total_tokens,
            model_context_window,
            usage_ratio * 100,
            largest_section,
            largest_pct,
        )

        if _PROMETHEUS_AVAILABLE and total_tokens > 0:
            _CONTEXT_TOKENS_TOTAL.inc(total_tokens)

        return analytics

    except Exception as exc:
        logger.warning("[TokenAnalytics] analyze_token_distribution failed: %s", exc)
        return {}


def check_context_health(analytics: dict) -> list:
    """Generate health warnings from token distribution analytics.

    Args:
        analytics: output of analyze_token_distribution().

    Returns:
        list of {level: "info"|"warning"|"critical", message: str,
                 section: str|None, tokens_involved: int}
    """
    if not analytics:
        return []

    warnings = []
    total = analytics.get("total_tokens", 0)
    window = analytics.get("context_window", DEFAULT_MODEL_CONTEXT_WINDOW)
    ratio = analytics.get("usage_ratio", 0.0)
    largest = analytics.get("largest_section", "")
    largest_pct = analytics.get("largest_section_pct", 0.0)

    # CRITICAL: >90% context usage
    if ratio >= CONTEXT_CRITICAL_THRESHOLD:
        warnings.append({
            "level": "critical",
            "message": (
                f"Context usage at {ratio * 100:.0f}% ({total}/{window} tokens). "
                f"Responses may degrade. Largest section: {largest} at {largest_pct:.0f}%."
            ),
            "section": largest,
            "tokens_involved": total,
        })

    # WARNING: >80% context usage (only if not already critical)
    elif ratio >= CONTEXT_WARNING_THRESHOLD:
        warnings.append({
            "level": "warning",
            "message": (
                f"Context usage at {ratio * 100:.0f}% ({total}/{window} tokens). "
                f"Largest section: {largest} at {largest_pct:.0f}%."
            ),
            "section": largest,
            "tokens_involved": total,
        })

    # WARNING: any single section dominates (>40% of total)
    if analytics.get("over_section_threshold") and ratio < CONTEXT_CRITICAL_THRESHOLD:
        section_data = analytics.get("sections", {})
        threshold_pct = SECTION_WARNING_THRESHOLD * 100
        # Find which section(s) are over threshold
        over = []
        section_threshold = total * SECTION_WARNING_THRESHOLD
        for name, data in section_data.items():
            if data.get("tokens", 0) >= section_threshold:
                over.append(f"{name}({data['pct_of_total']:.0f}%)")
        if analytics.get("history_tokens", 0) >= section_threshold:
            over.append(f"history({analytics['history_pct_of_total']:.0f}%)")
        if over:
            warnings.append({
                "level": "warning",
                "message": (
                    f"Section(s) consuming >{threshold_pct:.0f}% of context budget: "
                    + ", ".join(over)
                ),
                "section": over[0].split("(")[0] if over else None,
                "tokens_involved": int(total * SECTION_WARNING_THRESHOLD),
            })

    if _PROMETHEUS_AVAILABLE:
        for w in warnings:
            _CONTEXT_HEALTH_WARNINGS_TOTAL.labels(level=w["level"]).inc()

    return warnings
