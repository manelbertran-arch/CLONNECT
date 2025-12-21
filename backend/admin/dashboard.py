#!/usr/bin/env python3
"""
Clonnect Creators Admin Dashboard v2.0
A modern, dark-themed admin panel for managing the DM bot.
"""
import os
import sys
from pathlib import Path

import streamlit as st

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Page config (must be first Streamlit command)
st.set_page_config(
    page_title="Clonnect Admin",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Import utilities and pages
from admin.utils import t, get_language, set_language, language_selector, get_creators

from admin.pages import home, inbox, leads, nurturing, revenue, calendar, settings


# =============================================================================
# CUSTOM CSS
# =============================================================================

def load_custom_css():
    """Load custom CSS styles."""
    css_path = Path(__file__).parent / "styles" / "custom.css"
    if css_path.exists():
        with open(css_path) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# =============================================================================
# AUTHENTICATION
# =============================================================================

def check_auth() -> bool:
    """Check authentication with CLONNECT_ADMIN_KEY."""
    admin_key = os.getenv("CLONNECT_ADMIN_KEY", "admin123")

    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    # Login page
    st.markdown("""
    <div style="
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 80vh;
    ">
    """, unsafe_allow_html=True)

    st.markdown("""
    <div style="
        background-color: #141417;
        border: 1px solid #1F1F23;
        border-radius: 24px;
        padding: 3rem;
        max-width: 400px;
        margin: 0 auto;
        text-align: center;
    ">
        <p style="font-size: 3rem; margin: 0;">🤖</p>
        <h1 style="color: white; margin: 1rem 0; font-size: 1.75rem;">Clonnect Admin</h1>
        <p style="color: #71717A; margin: 0 0 2rem 0;">Introduce tu clave de acceso</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        password = st.text_input(
            t("auth.password_label"),
            type="password",
            key="login_password",
            label_visibility="collapsed",
            placeholder="🔐 Clave de acceso..."
        )

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button(t("auth.login_button"), use_container_width=True):
            if password == admin_key:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error(f"❌ {t('auth.error_wrong_key')}")

    st.markdown("</div>", unsafe_allow_html=True)

    return False


def logout():
    """Log out the user."""
    st.session_state.authenticated = False
    st.rerun()


# =============================================================================
# SIDEBAR
# =============================================================================

def render_sidebar() -> tuple:
    """Render sidebar and return selected page and creator."""

    with st.sidebar:
        # Logo and title
        st.markdown("""
        <div style="
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.5rem 0 1rem 0;
        ">
            <span style="font-size: 2rem;">🤖</span>
            <span style="
                font-size: 1.5rem;
                font-weight: 700;
                background: linear-gradient(135deg, #8B5CF6 0%, #06B6D4 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            ">CLONNECT</span>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        # Creator selector
        creators = get_creators()
        creator_id = st.selectbox(
            "Creador",
            creators,
            index=0,
            label_visibility="collapsed"
        )

        st.markdown("---")

        # Navigation
        pages = {
            f"🏠 {t('nav.home')}": "home",
            f"💬 {t('nav.inbox')}": "inbox",
            f"👥 {t('nav.leads')}": "leads",
            f"🔄 {t('nav.nurturing')}": "nurturing",
            f"💰 {t('nav.revenue')}": "revenue",
            f"📅 {t('nav.calendar')}": "calendar",
            f"⚙️ {t('nav.settings')}": "settings",
        }

        selected = st.radio(
            "nav",
            list(pages.keys()),
            label_visibility="collapsed"
        )

        st.markdown("---")

        # Language selector
        col1, col2 = st.columns([1, 1])

        with col1:
            current_lang = get_language()
            flags = {"es": "🇪🇸", "en": "🇬🇧"}
            labels = {"es": "ES", "en": "EN"}

            lang_options = ["es", "en"]
            current_idx = lang_options.index(current_lang) if current_lang in lang_options else 0

            new_lang = st.selectbox(
                "Lang",
                lang_options,
                index=current_idx,
                format_func=lambda x: f"{flags.get(x, '')} {labels.get(x, x.upper())}",
                label_visibility="collapsed",
                key="lang_select"
            )

            if new_lang != current_lang:
                set_language(new_lang)
                st.rerun()

        with col2:
            if st.button(f"🚪", key="logout_btn", help=t("auth.logout_button")):
                logout()

        # Version
        st.markdown("""
        <div style="
            position: absolute;
            bottom: 1rem;
            left: 1rem;
            color: #52525B;
            font-size: 0.75rem;
        ">
            v2.0 | Clonnect
        </div>
        """, unsafe_allow_html=True)

    return pages[selected], creator_id


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Main application entry point."""

    # Load custom CSS
    load_custom_css()

    # Check authentication
    if not check_auth():
        return

    # Render sidebar and get selection
    page, creator_id = render_sidebar()

    # Render selected page
    if page == "home":
        home.render(creator_id)
    elif page == "inbox":
        inbox.render(creator_id)
    elif page == "leads":
        leads.render(creator_id)
    elif page == "nurturing":
        nurturing.render(creator_id)
    elif page == "revenue":
        revenue.render(creator_id)
    elif page == "calendar":
        calendar.render(creator_id)
    elif page == "settings":
        settings.render(creator_id)
    else:
        st.error(f"Página no encontrada: {page}")


if __name__ == "__main__":
    main()
