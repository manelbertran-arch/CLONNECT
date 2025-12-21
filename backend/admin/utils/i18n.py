"""
Internationalization (i18n) module for Clonnect Admin Dashboard.
Supports ES and EN languages.
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional
import streamlit as st

LOCALES_DIR = Path(__file__).parent.parent / "locales"
SUPPORTED_LANGUAGES = ["es", "en"]
DEFAULT_LANGUAGE = "es"


def load_locale(lang: str) -> Dict[str, Any]:
    """Load a locale file."""
    filepath = LOCALES_DIR / f"{lang}.json"
    try:
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        st.error(f"Error loading locale {lang}: {e}")
    return {}


def get_language() -> str:
    """Get current language from session state."""
    if "language" not in st.session_state:
        st.session_state.language = DEFAULT_LANGUAGE
    return st.session_state.language


def set_language(lang: str) -> None:
    """Set current language in session state."""
    if lang in SUPPORTED_LANGUAGES:
        st.session_state.language = lang


def get_translations() -> Dict[str, Any]:
    """Get translations for current language."""
    if "translations" not in st.session_state:
        st.session_state.translations = {}

    lang = get_language()
    if lang not in st.session_state.translations:
        st.session_state.translations[lang] = load_locale(lang)

    return st.session_state.translations.get(lang, {})


def t(key: str, **kwargs) -> str:
    """
    Translate a key to the current language.

    Usage:
        t("nav.home") -> "Home"
        t("home.greeting_morning") -> "Buenos días"
        t("common.ago", value="5") -> "hace 5"

    Args:
        key: Dot-separated key path (e.g., "nav.home")
        **kwargs: Optional format arguments

    Returns:
        Translated string or the key if not found
    """
    translations = get_translations()

    # Navigate nested dictionary
    keys = key.split(".")
    value = translations

    for k in keys:
        if isinstance(value, dict) and k in value:
            value = value[k]
        else:
            return key  # Return key if not found

    if isinstance(value, str):
        # Apply format arguments if any
        if kwargs:
            try:
                return value.format(**kwargs)
            except KeyError:
                return value
        return value

    return key


def language_selector() -> None:
    """Render a language selector widget."""
    current_lang = get_language()

    # Flag emojis
    flags = {"es": "🇪🇸", "en": "🇬🇧"}
    labels = {"es": "ES", "en": "EN"}

    # Create selector
    options = SUPPORTED_LANGUAGES
    current_index = options.index(current_lang) if current_lang in options else 0

    col1, col2 = st.columns([1, 4])
    with col1:
        selected = st.selectbox(
            "Language",
            options=options,
            index=current_index,
            format_func=lambda x: f"{flags.get(x, '')} {labels.get(x, x.upper())}",
            label_visibility="collapsed",
            key="language_selector"
        )

        if selected != current_lang:
            set_language(selected)
            st.rerun()


def get_greeting() -> str:
    """Get appropriate greeting based on time of day."""
    from datetime import datetime

    hour = datetime.now().hour

    if 5 <= hour < 12:
        return t("home.greeting_morning")
    elif 12 <= hour < 19:
        return t("home.greeting_afternoon")
    else:
        return t("home.greeting_evening")


def format_time_ago(timestamp_str: str) -> str:
    """Format a timestamp as 'X time ago'."""
    from datetime import datetime, timezone

    if not timestamp_str:
        return "-"

    try:
        # Parse ISO timestamp
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str[:-1] + '+00:00'

        if '+' in timestamp_str or timestamp_str.endswith('Z'):
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        else:
            timestamp = datetime.fromisoformat(timestamp_str).replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        diff = now - timestamp

        minutes = int(diff.total_seconds() / 60)
        hours = int(diff.total_seconds() / 3600)
        days = int(diff.total_seconds() / 86400)

        ago = t("common.ago")

        if minutes < 1:
            return "ahora" if get_language() == "es" else "now"
        elif minutes < 60:
            return f"{ago} {minutes} {t('common.min')}"
        elif hours < 24:
            unit = t("common.hour") if hours == 1 else t("common.hours")
            return f"{ago} {hours} {unit}"
        else:
            unit = t("common.day") if days == 1 else t("common.days")
            return f"{ago} {days} {unit}"

    except Exception:
        return timestamp_str[:16] if len(timestamp_str) > 16 else timestamp_str
