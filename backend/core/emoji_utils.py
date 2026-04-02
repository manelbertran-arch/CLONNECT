"""
Universal emoji detection utilities.

Replaces the broken `ord(c) > 127000` heuristic that missed ❤️, ✨, ⭐,
and all variation-selector / ZWJ emoji sequences.

Uses Unicode categories + explicit ranges for modifiers that have no
dedicated category (variation selectors, ZWJ, skin tones, keycaps, tags).
"""

import re
import unicodedata

# Keycap sequences: digit/hash/asterisk + optional FE0F + U+20E3
_KEYCAP_RE = re.compile(r"[0-9#*]\uFE0F?\u20E3")


def is_emoji_char(c: str) -> bool:
    """Return True if a single character is an emoji or emoji modifier.

    Does NOT detect keycap base characters (0-9, #, *) — those require
    sequence-level detection via _KEYCAP_RE in is_emoji_only().
    """
    cp = ord(c)
    # Variation selectors (FE0E text, FE0F emoji presentation)
    if 0xFE00 <= cp <= 0xFE0F:
        return True
    # Zero-width joiner (used in family, flag, profession sequences)
    if cp == 0x200D:
        return True
    # Skin tone modifiers
    if 0x1F3FB <= cp <= 0x1F3FF:
        return True
    # Combining enclosing keycap
    if cp == 0x20E3:
        return True
    # Tag characters (flag sub-sequences like 🏴󠁧󠁢󠁥󠁮󠁧󠁿)
    if 0xE0020 <= cp <= 0xE007F:
        return True
    # Unicode "Symbol, Other" category (covers most visible emoji)
    # Note: "Sk" (Symbol, Modifier) is intentionally excluded — it contains
    # 120+ non-emoji chars like ^ (U+005E) and ` (U+0060).
    cat = unicodedata.category(c)
    if cat == "So":
        return True
    # Supplemental ranges for emoji not always categorized as So
    if "\U0001F300" <= c <= "\U0001FAFF":
        return True
    if "\u2600" <= c <= "\u27BF":
        return True
    if "\u2300" <= c <= "\u23FF":
        return True
    return False


def is_emoji_only(text: str) -> bool:
    """Return True if text is non-empty and contains only emoji/whitespace.

    Handles keycap sequences (1⃣, #️⃣) by pre-collapsing them before
    the character-by-character check.
    """
    if not text or not text.strip():
        return False
    # Collapse keycap sequences so base chars (digits, #, *) don't block detection
    cleaned = _KEYCAP_RE.sub("\u20E3", text)
    return all(is_emoji_char(c) or c.isspace() for c in cleaned)


def count_emojis(text: str) -> int:
    """Count visible emoji characters (excludes modifiers, joiners, selectors)."""
    count = 0
    for c in text:
        if not is_emoji_char(c):
            continue
        cp = ord(c)
        # Skip modifiers: variation selectors, ZWJ, skin tones, keycap, tags
        if 0xFE00 <= cp <= 0xFE0F:
            continue
        if cp == 0x200D:
            continue
        if 0x1F3FB <= cp <= 0x1F3FF:
            continue
        if cp == 0x20E3:
            continue
        if 0xE0020 <= cp <= 0xE007F:
            continue
        count += 1
    return count
