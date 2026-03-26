"""
Negation Reducer — Universal post-processing for Doc D system prompts.

Removes negation rules that are already covered by:
  - Few-shot examples (style, emojis, punctuation, laugh variants)
  - Postprocessing pipeline (blacklist replacement, tone enforcer, SBS)

Keeps only 5 categories that LLMs cannot reliably learn from examples:
  1. IDIOMA     — respond in lead's language
  2. REGISTRO   — tuteo / voseo / usted
  3. MARKDOWN   — never use markdown in DMs
  4. SEGURIDAD  — don't reveal internal instructions
  5. ANTI-ALUCINACIÓN — don't invent prices or data
  + BOT-FRASES  — identity: creator is not a bot (6th keep category)

Works for ANY creator, ANY language. Zero hardcoded creator-specific logic.

Key design decision: only flags a line when the negation word LEADS the
meaningful content (after stripping bullets/numbers). This avoids false
positives on lines like "4. BREVEDAD: Max 40 chars. NO elabores." where
the primary intent is positive.
"""

import logging
import re
from typing import Tuple

logger = logging.getLogger(__name__)

# ── Strip leading list markers ───────────────────────────────────────────────
_STRIP_MARKER_RE = re.compile(r'^[\s\-\*•]+|^\d+[\.\)]\s*')


def _leading_content(line: str) -> str:
    """Return line content after stripping bullets and numbered list markers."""
    s = line
    s = re.sub(r'^[\s\-\*•]+', '', s)        # - bullet / * bullet
    s = re.sub(r'^\d+[\.\)]\s*', '', s)       # 1. or 1)
    return s.strip()


# ── Negation-leading detector ────────────────────────────────────────────────
# A line is a "negation candidate" only when the FIRST meaningful word is a
# negation marker (e.g. "- NUNCA uses 😊", "- NO usa: compa").
# Lines like "4. BREVEDAD: ... NO elabores si no hace falta." are NOT flagged.
_NEGATION_LEAD_RE = re.compile(
    r"^(?:"
    r"NUNCA|nunca|NEVER|never"
    r"|PROHIBIDO\b|prohibido\b"
    r"|EVITA\b|evita\b"
    r"|JAM[ÁA]S|jam[áa]s"
    r"|NO\s+usa[sr]?"
    r"|NO\s+use[sr]?"
    r"|NO\s+uses\b"
    r"|NO\s+generes?\b"
    r"|NO\s+a[ñn]adas?\b"
    r"|NO\s+pongas?\b"
    r"|NO\s+menciones?\b"
    r"|NO\s+hagas?\b"
    r"|NO\s+elabores?\b"
    r"|NO\s+suenas?\b"
    r"|NO\s+seas?\b"
    r"|NO\s+finjas?\b"
    r"|NO\s+inventes?\b"
    r"|NO\s+reveles?\b"
    r"|Absolutamente\s+prohibido"
    r"|ABSOLUTAMENTE\s+PROHIBIDO"
    r")",
    re.IGNORECASE,
)


def _is_negation_leading(line: str) -> bool:
    """True when a negation word leads the line's meaningful content."""
    return bool(_NEGATION_LEAD_RE.match(_leading_content(line)))


# ── Keep patterns — lines matching ANY of these are always kept ──────────────
_KEEP_PATTERNS: list[re.Pattern] = [
    # 1. IDIOMA — language switching rules
    re.compile(r'\bidioma\b', re.I),
    re.compile(r'\blanguage\b', re.I),
    re.compile(r'\bidioma\s+del\s+lead\b', re.I),
    re.compile(r'\bcatal[àa]\b', re.I),
    re.compile(r'\bcastellano\b', re.I),
    re.compile(r'\bespa[ñn]ol\b', re.I),
    re.compile(r'\bingl[ée]s\b', re.I),
    re.compile(r'\bfrances\b', re.I),
    re.compile(r'\bportuguês\b', re.I),

    # 2. REGISTRO — address formality (tuteo / voseo / usted)
    re.compile(r'\bvoseo\b', re.I),
    re.compile(r'\busted\b', re.I),
    re.compile(r'\btuteo\b', re.I),
    re.compile(r'\bestimado\b', re.I),    # formal address term
    re.compile(r'\bquerido\b', re.I),     # formal address term

    # 3. MARKDOWN — LLMs always inject markdown, must be an explicit rule
    re.compile(r'\bmarkdown\b', re.I),
    re.compile(r'\bnegritas\b', re.I),
    re.compile(r'\basteriscos\b', re.I),
    re.compile(r'\bcursivas\b', re.I),
    re.compile(r'\bbullet\s+points?\b', re.I),
    re.compile(r'\blistas\s+con\s+guiones\b', re.I),

    # 4. SEGURIDAD — system prompt protection
    re.compile(r'instrucciones?\s+internas?', re.I),
    re.compile(r'system\s+prompt', re.I),
    re.compile(r'datos\s+de\s+entrenamiento', re.I),
    re.compile(r'\brevel[ae][sr]?\b', re.I),

    # 5. ANTI-ALUCINACIÓN — factual accuracy
    re.compile(r'\binvent[ae][sr]?\b', re.I),
    re.compile(r'\bpreci[oa]s?\b', re.I),    # precios, precio
    re.compile(r'\baluci', re.I),
    re.compile(r'\bfabricar\b', re.I),
    re.compile(r'datos\s+falsos', re.I),

    # 6. BOT-FRASES — identity: creator is not a service bot
    re.compile(r'frases?\s+de\s+bot', re.I),
    re.compile(r'asistente\s+virtual', re.I),
    re.compile(r'servicio\s+al\s+cliente', re.I),
    re.compile(r'NO\s+eres\s+(asistente|bot|virtual)', re.I),
    re.compile(r'\bPROHIBIDO\b'),    # whole PROHIBIDO lines (bot-phrase blacklists)

    # 7. VOCABULARY METADATA — "NO usa:" / "NUNCA uses:" lists are read by
    #    calibration_loader._load_creator_vocab() to build blacklist replacement.
    #    These are machine-readable data lines, NOT redundant LLM behavior rules.
    re.compile(r'\bNO\s+usa[sr]?\s*:', re.I),   # "NO usa: compa, bro, ..."
    re.compile(r'\bNUNCA\s+uses?\s*:', re.I),    # "NUNCA uses: 😊 😉 ..."
    re.compile(r'\bS[IÍ]\s+usa[sr]?\s*:', re.I), # "SÍ usa: nena, tia, ..." (approved terms)
]


def _should_keep(line: str) -> bool:
    """True if the line contains a critical rule that must be preserved."""
    return any(pat.search(line) for pat in _KEEP_PATTERNS)


def reduce_negations(text: str) -> Tuple[str, int, int]:
    """Remove non-critical negation lines from a Doc D system prompt.

    Only processes lines where a negation word LEADS the content — avoids
    false positives on positive-primary instructions with incidental negation.

    Args:
        text: Raw §4.1 system prompt content (or any Doc D text block).

    Returns:
        (cleaned_text, n_kept, n_removed)
        - cleaned_text: text with removable negation lines stripped
        - n_kept:    negation lines preserved (critical rules)
        - n_removed: negation lines removed (covered by pipeline)

    Safe no-op when text is empty or has no leading negations.
    """
    if not text:
        return text, 0, 0

    lines = text.split("\n")
    result: list[str] = []
    n_kept = 0
    n_removed = 0

    for line in lines:
        if _is_negation_leading(line):
            if _should_keep(line):
                result.append(line)
                n_kept += 1
            else:
                n_removed += 1
                logger.debug("[NegRed] removed: %s", line.strip()[:100])
        else:
            result.append(line)

    cleaned = "\n".join(result)
    # Collapse 3+ consecutive blank lines into 2 (cleanup after removals)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    if n_removed:
        logger.info(
            "[NegRed] %d negation lines removed, %d kept",
            n_removed, n_kept,
        )

    return cleaned, n_kept, n_removed
