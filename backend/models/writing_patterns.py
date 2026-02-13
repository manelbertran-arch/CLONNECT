"""WritingPatterns - Detailed writing style patterns for a creator.

Based on analysis of 3,061 real HUMAN messages from Stefan (bot messages excluded).
Complements CreatorDMStyle with finer-grained writing details.

Part of PHASE-1: Writing Patterns Analysis.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class WritingPatterns:
    """Detailed writing patterns extracted from real messages."""

    creator_id: str
    total_messages_analyzed: int

    # Capitalization patterns
    starts_upper_pct: float = 0.0  # % that start with uppercase
    starts_lower_pct: float = 0.0  # % that start with lowercase
    all_caps_pct: float = 0.0  # % in ALL CAPS

    # Punctuation patterns
    ends_exclamation_pct: float = 0.0  # Ends with !
    ends_question_pct: float = 0.0  # Ends with ?
    ends_period_pct: float = 0.0  # Ends with .
    ends_emoji_pct: float = 0.0  # Ends with emoji
    uses_ellipsis_pct: float = 0.0  # Contains ...
    double_exclamation_pct: float = 0.0  # Contains !!
    double_question_pct: float = 0.0  # Contains ??

    # Laugh patterns
    laugh_frequency_pct: float = 0.0
    laugh_patterns: Dict[str, int] = field(default_factory=dict)
    preferred_laugh: str = "jaja"  # Most common laugh style

    # Emoji patterns
    emoji_frequency_pct: float = 0.0  # % messages with emoji
    top_emojis: List[str] = field(default_factory=list)
    emoji_at_start_pct: float = 0.0
    emoji_at_end_pct: float = 0.0
    emoji_middle_pct: float = 0.0

    # Abbreviations used
    abbreviations: Dict[str, str] = field(default_factory=dict)

    # Common exact responses (for templating)
    common_responses: List[str] = field(default_factory=list)

    # Common openers and closers
    common_openers: List[str] = field(default_factory=list)
    common_closers: List[str] = field(default_factory=list)

    # Length stats
    length_mean: float = 0.0
    length_median: float = 0.0
    length_mode: int = 0

    # Question frequency
    question_frequency_pct: float = 0.0

    # Emoji-only message frequency
    emoji_only_pct: float = 0.0


# Stefan's writing patterns based on 3,061 real HUMAN messages (bot excluded)
STEFAN_WRITING_PATTERNS = WritingPatterns(
    creator_id="5e5c2364-c99a-4484-b986-741bb84a11cf",
    total_messages_analyzed=3061,
    # Capitalization: 86.6% start uppercase (formal but friendly)
    starts_upper_pct=0.866,
    starts_lower_pct=0.049,
    all_caps_pct=0.010,
    # Punctuation: ! is king, . is rare
    ends_exclamation_pct=0.154,
    ends_question_pct=0.109,
    ends_period_pct=0.011,  # Almost NEVER ends with period!
    ends_emoji_pct=0.101,
    uses_ellipsis_pct=0.0,  # Never uses ...
    double_exclamation_pct=0.080,  # 8% use !!
    double_question_pct=0.040,  # 4% use ??
    # Laughs: "jaja" is preferred over "jajaja"
    laugh_frequency_pct=0.067,
    laugh_patterns={
        "jaja": 137,
        "jajaja": 39,
        "😂": 16,
        "jeje": 8,
        "🤣": 3,
        "haha": 2,
    },
    preferred_laugh="jaja",
    # Emojis: 22.4%, mostly at end (81%)
    emoji_frequency_pct=0.224,
    top_emojis=["😀", "😊", "❤", "💙", "☺", "🙏🏽", "🙌🏾", "😌", "😂", "🌟"],
    emoji_at_start_pct=0.077,
    emoji_at_end_pct=0.812,  # 81% at end!
    emoji_middle_pct=0.111,
    # Abbreviations
    abbreviations={
        "q": "que",  # 89 uses
        "xq": "porque",  # 1 use
    },
    # Common exact responses (can use as templates)
    common_responses=[
        "Jajaja",
        "Cómo estás?",
        "Jaja",
        "Gracias 🙏🏽",
        "🫂",
        "Gracias",
        "Cómo estás??",
        "Gracias hermano!",
        "Hola!!",
        "Hola amigo",
        "Gracias por tu mensaje!",
        "👏",
        "😍",
        "😀",
        "Jajajaja",
        "Gracias!",
        "Hola!",
        "Gracias 💙",
        "Daleee",
        "Me encantó",
    ],
    # Common openers (first words)
    common_openers=[
        "Jajaja",
        "Gracias por tu",
        "Jaja",
        "Cómo estás?",
        "Gracias 🙏🏽",
        "Muchas gracias por",
        "Gracias por venir",
        "Gracias",
        "Cómo estás??",
        "Gracias hermano!",
        "Hola!!",
        "Espero que estés",
        "Me alegro que",
        "Hola amigo",
    ],
    # Common closers (last words)
    common_closers=[
        "gracias",
        "jajaja",
        "jaja",
        "muchas gracias",
        "cómo estás?",
        "por tu mensaje",
        "gracias!",
        "cómo estás??",
        "gracias hermano!",
        "bien y vos??",
        "hola!!",
        "buen día!",
    ],
    # Length stats
    length_mean=37.6,
    length_median=22.0,
    length_mode=18,
    # Questions
    question_frequency_pct=0.146,  # 14.6% are questions
    # Emoji-only
    emoji_only_pct=0.014,  # 1.4%
)


def get_writing_patterns(creator_id: str) -> WritingPatterns:
    """Get writing patterns for a creator.

    Args:
        creator_id: Creator identifier

    Returns:
        WritingPatterns for the creator or None
    """
    patterns = {
        "5e5c2364-c99a-4484-b986-741bb84a11cf": STEFAN_WRITING_PATTERNS,
        "stefano_bonanno": STEFAN_WRITING_PATTERNS,
    }
    return patterns.get(creator_id)


def format_writing_patterns_for_prompt(creator_id: str) -> str:
    """Format writing patterns for LLM prompt.

    Args:
        creator_id: Creator identifier

    Returns:
        Formatted string for prompt injection
    """
    patterns = get_writing_patterns(creator_id)
    if not patterns:
        return ""

    # Compact format — essential patterns only (reduces prompt tokens)
    top_responses = '", "'.join(patterns.common_responses[:5])
    top_emojis = ' '.join(patterns.top_emojis[:6])
    lines = [
        "",
        "=== PATRONES DE ESCRITURA ===",
        f"PUNTUACIÓN: NO termines con punto (suena frío). Usa ! o emoji. Risa: \"{patterns.preferred_laugh}\"",
        f"EMOJIS: {top_emojis} (pon al FINAL del mensaje)",
        f"ABREVIACIONES: \"q\" en lugar de \"que\"",
        f'RESPUESTAS FRECUENTES: "{top_responses}"',
        "=== FIN PATRONES ===",
        "",
    ]

    return "\n".join(lines)
