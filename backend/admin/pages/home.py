"""
Home Page - Command Center
The main dashboard with key metrics and urgent actions.
"""
import streamlit as st
from admin.utils import t, get_greeting, format_time_ago
from admin.utils import get_dashboard_metrics, load_creator_config, get_platform_icon
from admin.components import metric_card_money, metric_card_small, action_card, empty_state


def render(creator_id: str):
    """Render the home page."""

    # Load data
    config = load_creator_config(creator_id)
    metrics = get_dashboard_metrics(creator_id)

    creator_name = config.get("name", creator_id) if config else creator_id
    is_active = config.get("is_active", True) if config else True

    # Header
    col1, col2 = st.columns([3, 1])

    with col1:
        greeting = get_greeting()
        st.markdown(f"""
        <h1 style="margin: 0; font-size: 2rem; font-weight: 600;">
            {greeting}, {creator_name} 👋
        </h1>
        """, unsafe_allow_html=True)

    with col2:
        if is_active:
            st.markdown(f"""
            <div style="
                background: rgba(16, 185, 129, 0.2);
                color: #10B981;
                padding: 0.5rem 1rem;
                border-radius: 9999px;
                text-align: center;
                font-weight: 500;
            ">🟢 {t('home.bot_active')}</div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="
                background: rgba(239, 68, 68, 0.2);
                color: #EF4444;
                padding: 0.5rem 1rem;
                border-radius: 9999px;
                text-align: center;
                font-weight: 500;
            ">🔴 {t('home.bot_paused')}</div>
            """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Main Revenue Card
    revenue = metrics.get("total_revenue", 0)
    today_revenue = metrics.get("today_revenue", 0)
    today_sales = metrics.get("today_sales", 0)

    # Calculate goal progress (assuming 5000 EUR monthly goal)
    monthly_goal = 5000
    progress = (revenue / monthly_goal * 100) if monthly_goal > 0 else 0

    metric_card_money(
        value=f"€ {revenue:,.0f}",
        title=t("home.revenue_this_month"),
        subtitle=f"+€{today_revenue:,.0f} {t('home.today')}  •  {today_sales} {t('home.sales')}  •  ↑23% {t('home.vs_yesterday')}",
        progress=progress,
        progress_label=f"{progress:.0f}% {t('home.of_goal')}"
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # Secondary Metrics
    col1, col2, col3 = st.columns(3)

    with col1:
        hot_leads = metrics.get("hot_leads_count", 0)
        metric_card_small(
            icon="🔥",
            value=str(hot_leads),
            label=t("home.hot_leads"),
            sublabel=f"+3 {t('home.new')}"
        )

    with col2:
        response_rate = metrics.get("response_rate", 0)
        metric_card_small(
            icon="💬",
            value=f"{response_rate}%",
            label=t("home.response_rate"),
            sublabel="↑2%"
        )

    with col3:
        # Placeholder for calls - would come from calendar integration
        metric_card_small(
            icon="📅",
            value="3",
            label=t("home.calls_today"),
            sublabel=""
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Action Required Section
    st.markdown(f"""
    <h3 style="margin: 0 0 1rem 0; font-size: 1.125rem; font-weight: 500;">
        ⚡ {t('home.action_required')}
    </h3>
    """, unsafe_allow_html=True)

    escalations = metrics.get("escalations", [])
    hot_leads_list = metrics.get("hot_leads", [])[:3]

    has_actions = len(escalations) > 0 or len(hot_leads_list) > 0

    if not has_actions:
        empty_state(
            icon="🎉",
            title=t("home.no_actions"),
            description=t("home.no_actions_desc")
        )
    else:
        # Show escalations first (urgent)
        for esc in escalations[:3]:
            follower_id = esc.get("follower_id", "Unknown")
            reason = esc.get("reason", "Escalación pendiente")
            timestamp = esc.get("timestamp", "")

            action_card(
                icon="🔴",
                title=f"@{follower_id}",
                subtitle=reason[:50],
                time_ago=format_time_ago(timestamp),
                severity="urgent",
                on_click_key=f"action_esc_{follower_id}"
            )

        # Show hot leads without recent response
        for lead in hot_leads_list:
            follower_id = lead.get("follower_id", "Unknown")
            score = lead.get("purchase_intent_score", 0)
            last_contact = lead.get("last_contact", "")
            name = lead.get("name") or lead.get("username") or follower_id

            action_card(
                icon="🟠",
                title=f"@{name}",
                subtitle=f"Lead caliente (score: {score:.2f})",
                time_ago=format_time_ago(last_contact),
                severity="warning",
                on_click_key=f"action_lead_{follower_id}"
            )

    # Quick Stats (collapsible)
    st.markdown("<br>", unsafe_allow_html=True)

    with st.expander("📊 Más estadísticas"):
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Total Seguidores", metrics.get("total_followers", 0))
        with col2:
            st.metric("Mensajes Recibidos", metrics.get("messages_received", 0))
        with col3:
            st.metric("Mensajes Enviados", metrics.get("messages_sent", 0))
        with col4:
            st.metric("Escalaciones Pendientes", metrics.get("pending_escalations", 0))
