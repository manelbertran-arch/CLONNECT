"""
Inbox Page - Conversations
WhatsApp-style conversation list and chat view.
"""
import streamlit as st
from admin.utils import t, format_time_ago
from admin.utils import load_followers, load_escalations, get_platform_icon, get_platform_name
from admin.components import chat_message, conversation_list_item, follower_profile_card, empty_state


def render(creator_id: str):
    """Render the inbox page."""

    # Load data
    followers = load_followers(creator_id)
    escalations = load_escalations(creator_id)

    # Get escalated follower IDs
    escalated_ids = {e.get("follower_id") for e in escalations if e.get("status") == "pending"}

    # Header
    st.markdown(f"""
    <h1 style="margin: 0 0 1rem 0; font-size: 1.75rem; font-weight: 600;">
        💬 {t('inbox.title')}
    </h1>
    """, unsafe_allow_html=True)

    if not followers:
        empty_state(
            icon="💬",
            title=t("inbox.no_conversations"),
            description="Las conversaciones aparecerán aquí cuando empieces a recibir mensajes."
        )
        return

    # Initialize session state for selected conversation
    if "selected_conversation" not in st.session_state:
        st.session_state.selected_conversation = None

    # Search and filters
    col1, col2 = st.columns([3, 1])

    with col1:
        search = st.text_input(
            "search",
            placeholder=f"🔍 {t('inbox.search_placeholder')}",
            label_visibility="collapsed"
        )

    with col2:
        filter_options = [
            t("inbox.filter_all"),
            t("inbox.filter_urgent"),
            t("inbox.filter_hot"),
            t("inbox.filter_resolved")
        ]
        filter_selected = st.selectbox(
            "filter",
            filter_options,
            label_visibility="collapsed"
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Filter followers
    filtered_followers = followers

    if search:
        search_lower = search.lower()
        filtered_followers = [
            f for f in filtered_followers
            if search_lower in f.get("follower_id", "").lower()
            or search_lower in f.get("name", "").lower()
            or search_lower in f.get("username", "").lower()
        ]

    if filter_selected == t("inbox.filter_urgent"):
        filtered_followers = [f for f in filtered_followers if f.get("follower_id") in escalated_ids]
    elif filter_selected == t("inbox.filter_hot"):
        filtered_followers = [f for f in filtered_followers if f.get("purchase_intent_score", 0) >= 0.7]

    # Sort by last contact (most recent first)
    filtered_followers = sorted(
        filtered_followers,
        key=lambda x: x.get("last_contact", ""),
        reverse=True
    )

    # Two-column layout: List | Chat
    col1, col2 = st.columns([1, 2])

    with col1:
        st.markdown(f"""
        <div style="
            background-color: #141417;
            border: 1px solid #1F1F23;
            border-radius: 12px;
            padding: 0.5rem;
            max-height: 600px;
            overflow-y: auto;
        ">
        """, unsafe_allow_html=True)

        for follower in filtered_followers[:30]:
            follower_id = follower.get("follower_id", "")
            name = follower.get("name") or follower.get("username") or follower_id
            score = follower.get("purchase_intent_score", 0)
            last_contact = follower.get("last_contact", "")

            # Get last message preview
            last_messages = follower.get("last_messages", [])
            last_msg_preview = last_messages[-1].get("content", "")[:40] if last_messages else ""

            # Determine status
            if follower_id in escalated_ids:
                status = "urgent"
            elif score >= 0.7:
                status = "hot"
            elif follower.get("is_customer"):
                status = "buying"
            else:
                status = "normal"

            is_selected = st.session_state.selected_conversation == follower_id

            # Create a button for each conversation
            if st.button(
                f"{get_platform_icon(follower_id)} {name[:15]}",
                key=f"conv_{follower_id}",
                use_container_width=True
            ):
                st.session_state.selected_conversation = follower_id
                st.rerun()

            # Show additional info
            st.markdown(f"""
            <div style="
                padding: 0 0.5rem 0.75rem 0.5rem;
                border-bottom: 1px solid #1F1F23;
                margin-bottom: 0.5rem;
            ">
                <div style="display: flex; justify-content: space-between;">
                    <span style="color: #71717A; font-size: 0.75rem;">{last_msg_preview}...</span>
                    <span style="color: #71717A; font-size: 0.75rem;">{format_time_ago(last_contact)}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 0.25rem;">
                    <span style="color: {'#EF4444' if status == 'urgent' else '#F59E0B' if status == 'hot' else '#10B981' if status == 'buying' else '#71717A'}; font-size: 0.75rem;">
                        {'🔴 Escalado' if status == 'urgent' else '🔥 Hot' if status == 'hot' else '🛒 Cliente' if status == 'buying' else ''}
                    </span>
                    <span style="color: #71717A; font-size: 0.75rem;">Score: {score:.2f}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        selected_id = st.session_state.selected_conversation

        if selected_id:
            # Find selected follower
            selected_follower = next(
                (f for f in followers if f.get("follower_id") == selected_id),
                None
            )

            if selected_follower:
                # Chat header
                name = selected_follower.get("name") or selected_follower.get("username") or selected_id
                platform = get_platform_name(selected_id)
                score = selected_follower.get("purchase_intent_score", 0)

                st.markdown(f"""
                <div style="
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding-bottom: 1rem;
                    border-bottom: 1px solid #1F1F23;
                    margin-bottom: 1rem;
                ">
                    <div>
                        <p style="color: white; margin: 0; font-weight: 600; font-size: 1.125rem;">
                            {get_platform_icon(selected_id)} {name}
                        </p>
                        <p style="color: #71717A; margin: 0; font-size: 0.875rem;">
                            {platform} • {t('inbox.lead_score')}: {score:.2f}
                        </p>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Chat messages
                messages = selected_follower.get("last_messages", [])

                st.markdown(f"""
                <div style="
                    background-color: #0A0A0B;
                    border: 1px solid #1F1F23;
                    border-radius: 12px;
                    padding: 1rem;
                    height: 350px;
                    overflow-y: auto;
                ">
                """, unsafe_allow_html=True)

                if messages:
                    for msg in messages[-20:]:
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        chat_message(content, is_user=(role == "user"))
                else:
                    st.markdown(f"""
                    <p style="color: #71717A; text-align: center; padding: 2rem;">
                        {t('inbox.no_messages')}
                    </p>
                    """, unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)

                # Reply input
                st.markdown("<br>", unsafe_allow_html=True)

                reply_col1, reply_col2 = st.columns([4, 1])

                with reply_col1:
                    reply_text = st.text_input(
                        "reply",
                        placeholder=f"💬 {t('inbox.reply_placeholder')}",
                        label_visibility="collapsed"
                    )

                with reply_col2:
                    if st.button(f"📤 {t('inbox.send')}", use_container_width=True):
                        if reply_text:
                            st.success("Mensaje enviado (demo)")

                # Action buttons
                st.markdown("<br>", unsafe_allow_html=True)

                btn_col1, btn_col2, btn_col3 = st.columns(3)

                with btn_col1:
                    if st.button(f"🏷️ Tags", use_container_width=True):
                        st.info("Gestión de tags (próximamente)")

                with btn_col2:
                    if st.button(f"💰 Marcar venta", use_container_width=True):
                        st.success("Venta registrada (demo)")

                with btn_col3:
                    if st.button(f"⏸️ Pausar bot", use_container_width=True):
                        st.info("Bot pausado para este usuario (demo)")

                # Follower profile sidebar
                st.markdown("<br>", unsafe_allow_html=True)

                with st.expander("👤 Perfil del seguidor"):
                    follower_profile_card(
                        follower_id=selected_id,
                        name=name,
                        platform=platform,
                        lead_score=score,
                        total_messages=selected_follower.get("total_messages", 0),
                        first_contact=selected_follower.get("first_contact", ""),
                        is_lead=selected_follower.get("is_lead", False),
                        is_customer=selected_follower.get("is_customer", False),
                        interests=selected_follower.get("interests", []),
                        products_discussed=selected_follower.get("products_discussed", [])
                    )

        else:
            # No conversation selected
            st.markdown(f"""
            <div style="
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 400px;
                background-color: #141417;
                border: 1px dashed #1F1F23;
                border-radius: 12px;
            ">
                <p style="font-size: 3rem; margin: 0;">💬</p>
                <p style="color: #71717A; margin: 1rem 0 0 0;">Selecciona una conversación</p>
            </div>
            """, unsafe_allow_html=True)
