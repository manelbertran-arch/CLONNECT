"""Tests for core.emoji_utils — universal emoji detection."""

import pytest
from core.emoji_utils import is_emoji_char, is_emoji_only, count_emojis


class TestIsEmojiOnly:
    """is_emoji_only must detect ALL Unicode emoji, not just high codepoints."""

    # --- TRUE cases: pure emoji input ---

    @pytest.mark.parametrize("text", [
        "😊",               # High codepoint (U+1F60A)
        "💙",               # High codepoint (U+1F499)
        "😂😂",             # Multiple high codepoint
        "💖💖💖",           # Triple hearts
        "❤️",              # U+2764 + U+FE0F — THE bug case (was ord=10084)
        "✨",               # U+2728 — was failing (ord=10024)
        "⭐",               # U+2B50
        "☺️",              # U+263A + U+FE0F
        "♥️",              # U+2665 + U+FE0F
        "✅",               # U+2705
        "⚡",               # U+26A1
        "💃🏻💃🏻💃🏻❤️❤️",  # Mixed high+low codepoints — production failure
        "❤️‍🔥",            # ZWJ sequence (heart on fire)
        "👩🏽‍🚀",           # ZWJ + skin tone (woman astronaut)
        "🏴󠁧󠁢󠁥󠁮󠁧󠁿",           # Flag tag sequence (England)
        "🇪🇸",             # Regional flag (Spain)
        "❤️ ❤️",           # Emoji with space
        "👍🏻",             # Thumbs up with skin tone
        "🫠🫠",             # Modern emoji (melting face)
        "🙏🏻",             # Folded hands with skin tone
        "⭐⭐⭐⭐⭐",       # Five stars
    ])
    def test_emoji_only_true(self, text):
        assert is_emoji_only(text) is True

    # --- FALSE cases: text, numbers, empty ---

    # --- Keycap sequences ---

    @pytest.mark.parametrize("text", [
        "1⃣",               # Keycap 1 (digit + U+20E3)
        "2⃣",               # Keycap 2
        "#️⃣",              # Keycap # (with variation selector)
        "*️⃣",              # Keycap *
        "1⃣2⃣3⃣",          # Multiple keycaps
    ])
    def test_keycap_sequences(self, text):
        assert is_emoji_only(text) is True

    # --- FALSE cases: text, numbers, empty, Sk false positives ---

    @pytest.mark.parametrize("text", [
        "",                  # Empty
        "   ",               # Whitespace only
        "Hola",              # Pure text
        "123",               # Numbers (NOT keycap — no U+20E3)
        "Lol",               # Short text
        "Hola ❤️",          # Mixed text + emoji
        "ok 👍",             # Mixed text + emoji
        "Si",                # Common short response
        "💃 let's go!",     # Emoji + text
        "^",                 # Sk category — NOT emoji (was false positive with Sk)
        "`",                 # Sk category — NOT emoji
        "~",                 # Sk category — NOT emoji
        "©Iris",             # © is So but mixed with text
    ])
    def test_emoji_only_false(self, text):
        assert is_emoji_only(text) is False


class TestCountEmojis:
    """count_emojis must count visible emoji, not modifiers."""

    def test_heart_with_variation_selector(self):
        assert count_emojis("❤️") == 1  # Not 0 (old bug) or 2

    def test_dancers_and_hearts(self):
        # 💃🏻 × 3 + ❤️ × 2 = 5 visible emoji
        assert count_emojis("💃🏻💃🏻💃🏻❤️❤️") == 5

    def test_text_with_emoji(self):
        assert count_emojis("Hello ❤️ world") == 1

    def test_empty(self):
        assert count_emojis("") == 0

    def test_no_emoji(self):
        assert count_emojis("Hello world") == 0

    def test_multiple_different(self):
        assert count_emojis("😂🤣💪") == 3

    def test_sparkles(self):
        assert count_emojis("✨✨✨") == 3

    def test_stars(self):
        assert count_emojis("⭐⭐⭐") == 3


class TestIsEmojiChar:
    """is_emoji_char must handle all emoji-related Unicode characters."""

    def test_variation_selector(self):
        assert is_emoji_char("\uFE0F") is True

    def test_zwj(self):
        assert is_emoji_char("\u200D") is True

    def test_skin_tone(self):
        assert is_emoji_char("\U0001F3FB") is True

    def test_keycap(self):
        assert is_emoji_char("\u20E3") is True

    def test_regular_letter(self):
        assert is_emoji_char("a") is False

    def test_digit(self):
        assert is_emoji_char("1") is False

    def test_space(self):
        assert is_emoji_char(" ") is False

    # Sk category must NOT be treated as emoji
    def test_circumflex_not_emoji(self):
        assert is_emoji_char("^") is False

    def test_grave_accent_not_emoji(self):
        assert is_emoji_char("`") is False

    def test_tilde_not_emoji(self):
        assert is_emoji_char("~") is False
