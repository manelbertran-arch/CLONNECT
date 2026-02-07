"""
Question Remover - Removes unnecessary questions from responses.

Stefan almost never asks questions (10% of his messages).
This post-processor removes generic questions that make the bot sound unnatural.
"""

import re

# Generic questions that should ALWAYS be removed
BANNED_QUESTIONS = [
    r"¿qué tal\?",
    r"¿cómo estás\?",
    r"¿cómo vas\?",
    r"¿todo bien\?",
    r"¿y tú\?",
    r"¿y vos\?",
    r"¿qué cuentas\?",
    r"¿cómo te va\?",
    r"¿qué hay\?",
    r"¿qué onda\?",
]

# Replacements for removed questions
QUESTION_REPLACEMENTS = {
    "¿qué tal?": "😊",
    "¿cómo estás?": "",
    "¿todo bien?": "",
    "¿y tú?": "",
    "¿y vos?": "",
    "¿qué cuentas?": "",
    "¿cómo te va?": "",
}


def contains_banned_question(text: str) -> bool:
    """Check if text contains a banned question."""
    text_lower = text.lower()
    for pattern in BANNED_QUESTIONS:
        if re.search(pattern, text_lower):
            return True
    return False


def remove_banned_questions(text: str) -> str:
    """Remove banned questions from text."""
    result = text

    for question, replacement in QUESTION_REPLACEMENTS.items():
        result = re.sub(re.escape(question), replacement, result, flags=re.IGNORECASE)

    # Clean multiple spaces
    result = re.sub(r"\s+", " ", result).strip()

    return result


def should_allow_question(lead_message: str, response: str) -> bool:
    """
    Determine if a question in the response is justified.

    Allow questions when:
    1. Lead asked a question first
    2. Information is needed to complete an action
    3. It's sales/service follow-up
    """
    response_lower = response.lower()

    # If lead asked, we can respond with question
    if "?" in lead_message:
        return True

    # Necessary clarification questions
    clarification_patterns = [
        r"qué (día|hora|fecha)",
        r"cuándo (puedes|te va)",
        r"dónde (nos vemos|quedamos)",
        r"cuál (prefieres|quieres)",
    ]
    for pattern in clarification_patterns:
        if re.search(pattern, response_lower):
            return True

    # Sales follow-up
    sales_patterns = [
        r"te interesa",
        r"quieres (que te|reservar|agendar)",
        r"te paso (el link|info)",
    ]
    for pattern in sales_patterns:
        if re.search(pattern, response_lower):
            return True

    return False


def process_questions(response: str, lead_message: str, question_rate: float = 0.10) -> str:
    """
    Process and remove unnecessary questions from response.

    Args:
        response: Generated response
        lead_message: Lead's message
        question_rate: Creator's question rate (Stefan: 0.10)

    Returns:
        Response without unnecessary questions
    """
    # If no question, return as-is
    if "?" not in response:
        return response

    # If question is justified, allow it
    if should_allow_question(lead_message, response):
        return response

    # Remove banned questions
    result = remove_banned_questions(response)

    # If still has question and creator doesn't ask much
    if "?" in result and question_rate < 0.15:
        result = convert_question_to_statement(result)

    return result


def convert_question_to_statement(text: str) -> str:
    """Convert a question to a statement."""
    # Conversion patterns
    conversions = [
        (r"¿cómo te fue\?", "¡Espero que bien!"),
        (r"¿qué te pareció\?", "¡Espero que te haya gustado!"),
        (r"¿cómo te sientes\?", "¡Espero que genial!"),
        (r"¿qué tal te fue\?", "¡Espero que genial!"),
        (r"¿pudiste\?", "¡Espero que sí!"),
        (r"¿te gustó\?", "¡Espero que te haya gustado!"),
    ]

    for pattern, replacement in conversions:
        if re.search(pattern, text, re.IGNORECASE):
            return re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Fallback: keep the response as-is with its questions
    # Better to have a natural question than a truncated statement
    return text
