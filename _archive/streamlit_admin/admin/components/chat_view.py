"""
Chat view component for conversations.
"""
import streamlit as st
from typing import List, Dict, Optional


def chat_message(content: str, is_user: bool, timestamp: Optional[str] = None):
    """
    Render a single chat message bubble.

    Args:
        content: Message text
        is_user: True if from user, False if from bot
        timestamp: Optional timestamp to display
    """
    if is_user:
        # User message (right aligned, gradient background)
        st.markdown(f"""
        <div style="
            display: flex;
            justify-content: flex-end;
            margin-bottom: 0.75rem;
        ">
            <div style="
                background: linear-gradient(135deg, #8B5CF6 0%, #06B6D4 100%);
                border-radius: 16px 16px 4px 16px;
                padding: 0.75rem 1rem;
                max-width: 70%;
            ">
                <p style="color: white; margin: 0; font-size: 0.9375rem;">{content}</p>
                {f'<p style="color: rgba(255,255,255,0.6); margin: 0.25rem 0 0 0; font-size: 0.75rem; text-align: right;">{timestamp}</p>' if timestamp else ''}
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        # Bot message (left aligned, dark background)
        st.markdown(f"""
        <div style="
            display: flex;
            justify-content: flex-start;
            margin-bottom: 0.75rem;
        ">
            <div style="
                background-color: #1F1F23;
                border: 1px solid #2D2D35;
                border-radius: 16px 16px 16px 4px;
                padding: 0.75rem 1rem;
                max-width: 70%;
            ">
                <p style="color: white; margin: 0; font-size: 0.9375rem;">{content}</p>
                {f'<p style="color: #71717A; margin: 0.25rem 0 0 0; font-size: 0.75rem;">{timestamp}</p>' if timestamp else ''}
            </div>
        </div>
        """, unsafe_allow_html=True)


def chat_container(messages: List[Dict], max_height: int = 400):
    """
    Render a scrollable chat container with messages.

    Args:
        messages: List of message dicts with 'role', 'content', and optional 'timestamp'
        max_height: Maximum height in pixels
    """
    st.markdown(f"""
    <div style="
        background-color: #0A0A0B;
        border: 1px solid #1F1F23;
        border-radius: 12px;
        padding: 1rem;
        max-height: {max_height}px;
        overflow-y: auto;
    " id="chat-container">
    """, unsafe_allow_html=True)

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        timestamp = msg.get("timestamp", "")

        chat_message(content, is_user=(role == "user"), timestamp=timestamp)

    st.markdown("</div>", unsafe_allow_html=True)


def conversation_list_item(
    follower_id: str,
    name: str,
    platform_icon: str,
    last_message: str,
    time_ago: str,
    status: str = "normal",
    lead_score: float = 0,
    is_selected: bool = False
):
    """
    Render a conversation list item.

    Args:
        follower_id: Unique follower ID
        name: Display name
        platform_icon: Platform emoji
        last_message: Preview of last message
        time_ago: Time since last message
        status: "urgent", "hot", "buying", or "normal"
        lead_score: Lead score 0-1
        is_selected: Whether this item is currently selected
    """
    # Status badge
    status_badges = {
        "urgent": '<span style="background: rgba(239,68,68,0.2); color: #EF4444; padding: 0.125rem 0.5rem; border-radius: 9999px; font-size: 0.75rem;">🔴 Escalado</span>',
        "hot": '<span style="background: rgba(245,158,11,0.2); color: #F59E0B; padding: 0.125rem 0.5rem; border-radius: 9999px; font-size: 0.75rem;">🔥 Hot</span>',
        "buying": '<span style="background: rgba(16,185,129,0.2); color: #10B981; padding: 0.125rem 0.5rem; border-radius: 9999px; font-size: 0.75rem;">🛒 Comprando</span>',
        "normal": ""
    }

    badge_html = status_badges.get(status, "")

    # Lead score color
    if lead_score >= 0.7:
        score_color = "#EF4444"
    elif lead_score >= 0.4:
        score_color = "#F59E0B"
    else:
        score_color = "#71717A"

    bg_color = "#1F1F23" if is_selected else "#141417"
    border_color = "#8B5CF6" if is_selected else "#1F1F23"

    st.markdown(f"""
    <div style="
        background-color: {bg_color};
        border: 1px solid {border_color};
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 0.5rem;
        cursor: pointer;
        transition: all 0.2s ease;
    ">
        <div style="display: flex; justify-content: space-between; align-items: flex-start;">
            <div style="flex: 1;">
                <p style="color: white; margin: 0; font-weight: 500;">
                    {platform_icon} {name}
                    {badge_html}
                </p>
                <p style="color: #71717A; margin: 0.25rem 0 0 0; font-size: 0.875rem;
                   overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 200px;">
                    {last_message[:50]}{'...' if len(last_message) > 50 else ''}
                </p>
            </div>
            <div style="text-align: right;">
                <p style="color: #71717A; margin: 0; font-size: 0.75rem;">{time_ago}</p>
                <p style="color: {score_color}; margin: 0.25rem 0 0 0; font-size: 0.75rem;">
                    {lead_score:.2f}
                </p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def follower_profile_card(
    follower_id: str,
    name: str,
    platform: str,
    lead_score: float,
    total_messages: int,
    first_contact: str,
    is_lead: bool,
    is_customer: bool,
    interests: List[str],
    products_discussed: List[str]
):
    """
    Render a follower profile card for the sidebar.
    """
    # Status
    if is_customer:
        status = "🟢 Cliente"
        status_color = "#10B981"
    elif is_lead:
        status = "🟡 Lead"
        status_color = "#F59E0B"
    else:
        status = "⚪ Nuevo"
        status_color = "#71717A"

    interests_html = ""
    if interests:
        tags = " ".join([f'<span style="background: #1F1F23; padding: 0.125rem 0.5rem; border-radius: 4px; margin-right: 0.25rem; font-size: 0.75rem;">{i}</span>' for i in interests[:3]])
        interests_html = f'<p style="margin: 0.5rem 0 0 0;">{tags}</p>'

    st.markdown(f"""
    <div style="
        background-color: #141417;
        border: 1px solid #1F1F23;
        border-radius: 12px;
        padding: 1rem;
    ">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
            <p style="color: white; margin: 0; font-weight: 600;">{name}</p>
            <span style="color: {status_color}; font-size: 0.875rem;">{status}</span>
        </div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;">
            <div>
                <p style="color: #71717A; margin: 0; font-size: 0.75rem;">Lead Score</p>
                <p style="color: white; margin: 0; font-weight: 500;">{lead_score:.2f}</p>
            </div>
            <div>
                <p style="color: #71717A; margin: 0; font-size: 0.75rem;">Mensajes</p>
                <p style="color: white; margin: 0; font-weight: 500;">{total_messages}</p>
            </div>
            <div>
                <p style="color: #71717A; margin: 0; font-size: 0.75rem;">Plataforma</p>
                <p style="color: white; margin: 0; font-weight: 500;">{platform}</p>
            </div>
            <div>
                <p style="color: #71717A; margin: 0; font-size: 0.75rem;">Primer contacto</p>
                <p style="color: white; margin: 0; font-weight: 500;">{first_contact[:10]}</p>
            </div>
        </div>

        {interests_html}
    </div>
    """, unsafe_allow_html=True)
