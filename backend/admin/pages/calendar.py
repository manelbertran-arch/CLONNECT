"""
Calendar Page - Scheduled Calls
Display and manage calendar bookings.
"""
import streamlit as st
from datetime import datetime
from admin.utils import t
from admin.utils import load_bookings
from admin.components import empty_state


def render(creator_id: str):
    """Render the calendar page."""

    # Load data
    bookings = load_bookings(creator_id)

    # Header
    col1, col2 = st.columns([3, 1])

    with col1:
        st.markdown(f"""
        <h1 style="margin: 0; font-size: 1.75rem; font-weight: 600;">
            📅 {t('calendar.title')}
        </h1>
        """, unsafe_allow_html=True)

    with col2:
        if st.button("🔗 Calendly", use_container_width=True):
            st.info("Conectar Calendly (próximamente)")

    st.markdown("<br>", unsafe_allow_html=True)

    # Today's date
    today = datetime.now()
    today_str = today.strftime("%d %B %Y")

    st.markdown(f"""
    <p style="color: white; font-size: 1.125rem; font-weight: 500; margin-bottom: 1rem;">
        {t('calendar.today')}, {today_str}
    </p>
    """, unsafe_allow_html=True)

    # Sample bookings for demo (would come from Calendly/Cal.com integration)
    sample_bookings = [
        {
            "time": "09:00",
            "name": "@maria_fitness",
            "title": "Mentoría 1:1 - Discovery call",
            "zoom_link": "https://zoom.us/j/123456789",
            "follower_id": "ig_maria_fitness"
        },
        {
            "time": "11:30",
            "name": "@carlos_coach",
            "title": "Curso - Dudas pre-compra",
            "zoom_link": "https://zoom.us/j/987654321",
            "follower_id": "ig_carlos_coach"
        },
        {
            "time": "15:00",
            "name": None,
            "title": None,
            "zoom_link": None,
            "follower_id": None
        }
    ]

    # Calendar view
    st.markdown(f"""
    <div style="
        background-color: #141417;
        border: 1px solid #1F1F23;
        border-radius: 16px;
        padding: 1.5rem;
    ">
    """, unsafe_allow_html=True)

    for booking in sample_bookings:
        time = booking["time"]
        name = booking["name"]
        title = booking["title"]
        zoom_link = booking["zoom_link"]

        if name:
            # Has a booking
            st.markdown(f"""
            <div style="display: flex; gap: 1rem; margin-bottom: 1rem;">
                <div style="
                    color: #71717A;
                    font-size: 0.875rem;
                    font-weight: 500;
                    min-width: 50px;
                ">{time}</div>
                <div style="
                    flex: 1;
                    background: linear-gradient(135deg, rgba(139, 92, 246, 0.2) 0%, rgba(6, 182, 212, 0.2) 100%);
                    border: 1px solid rgba(139, 92, 246, 0.3);
                    border-radius: 12px;
                    padding: 1rem;
                ">
                    <p style="color: white; margin: 0; font-weight: 500;">📞 {name}</p>
                    <p style="color: #71717A; margin: 0.25rem 0 0.75rem 0; font-size: 0.875rem;">{title}</p>
                    <div style="display: flex; gap: 0.5rem;">
                        <a href="{zoom_link}" target="_blank" style="
                            background-color: #1F1F23;
                            color: #06B6D4;
                            padding: 0.25rem 0.75rem;
                            border-radius: 6px;
                            font-size: 0.75rem;
                            text-decoration: none;
                        ">{t('calendar.zoom_link')}</a>
                        <span style="
                            background-color: #1F1F23;
                            color: #71717A;
                            padding: 0.25rem 0.75rem;
                            border-radius: 6px;
                            font-size: 0.75rem;
                            cursor: pointer;
                        ">{t('calendar.view_profile')}</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            # No booking
            st.markdown(f"""
            <div style="display: flex; gap: 1rem; margin-bottom: 1rem;">
                <div style="
                    color: #71717A;
                    font-size: 0.875rem;
                    font-weight: 500;
                    min-width: 50px;
                ">{time}</div>
                <div style="
                    flex: 1;
                    border: 1px dashed #1F1F23;
                    border-radius: 12px;
                    padding: 1rem;
                    text-align: center;
                ">
                    <p style="color: #52525B; margin: 0; font-size: 0.875rem;">{t('calendar.no_calls')}</p>
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Monthly stats
    st.markdown(f"""
    <div style="
        background-color: #141417;
        border: 1px solid #1F1F23;
        border-radius: 12px;
        padding: 1rem 1.5rem;
    ">
        <p style="color: #71717A; margin: 0; font-size: 0.875rem;">
            📊 {t('calendar.this_month')}: <span style="color: white; font-weight: 500;">23 {t('calendar.calls')}</span> |
            <span style="color: #10B981;">18 {t('calendar.attended')} (78%)</span> |
            <span style="color: #F59E0B;">8 {t('calendar.bought')}</span>
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Connection buttons
    col1, col2 = st.columns(2)

    with col1:
        if st.button("📅 Conectar Calendly", use_container_width=True):
            st.info("Conectar Calendly (próximamente)")

    with col2:
        if st.button("📅 Conectar Cal.com", use_container_width=True):
            st.info("Conectar Cal.com (próximamente)")
