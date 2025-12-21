"""
Revenue Page - Money and Payments
Displays revenue metrics, transactions, and funnel analysis.
"""
import streamlit as st
from datetime import datetime
from admin.utils import t, format_time_ago
from admin.utils import get_revenue_metrics, load_payments
from admin.components import metric_card, metric_card_small, empty_state


def render(creator_id: str):
    """Render the revenue page."""

    # Header
    st.markdown(f"""
    <h1 style="margin: 0 0 1rem 0; font-size: 1.75rem; font-weight: 600;">
        💰 {t('revenue.title')}
    </h1>
    """, unsafe_allow_html=True)

    # Date selector
    col1, col2 = st.columns([3, 1])
    with col2:
        current_month = datetime.now().strftime("%B %Y")
        st.markdown(f"""
        <div style="
            background-color: #141417;
            border: 1px solid #1F1F23;
            border-radius: 8px;
            padding: 0.5rem 1rem;
            text-align: center;
            cursor: pointer;
        ">📅 {current_month} ▼</div>
        """, unsafe_allow_html=True)

    # Load data
    metrics = get_revenue_metrics(creator_id)

    month_revenue = metrics.get("month_revenue", 0)
    month_transactions = metrics.get("month_transactions", 0)
    by_source = metrics.get("by_source", {})
    recent_payments = metrics.get("recent_payments", [])
    funnel = metrics.get("funnel", {})

    st.markdown("<br>", unsafe_allow_html=True)

    # Main Revenue Display
    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #10B981 0%, #059669 100%);
        border-radius: 20px;
        padding: 2.5rem;
        text-align: center;
        margin-bottom: 2rem;
    ">
        <p style="color: rgba(255,255,255,0.8); margin: 0; font-size: 1rem;">{t('revenue.this_month')}</p>
        <p style="
            color: white;
            margin: 0.5rem 0;
            font-size: 4rem;
            font-weight: 700;
            letter-spacing: -2px;
        ">€ {month_revenue:,.0f}</p>
        <p style="color: rgba(255,255,255,0.8); margin: 0; font-size: 1rem;">
            ↑ 34% {t('revenue.vs_last_month')}  •  {t('revenue.projection')}: €15,800
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Revenue by Source
    col1, col2, col3 = st.columns(3)

    stripe_revenue = by_source.get("stripe", 0)
    hotmart_revenue = by_source.get("hotmart", 0)

    with col1:
        metric_card_small(
            icon="💳",
            value=f"€{stripe_revenue:,.0f}",
            label="Stripe",
            sublabel=f"{len([p for p in recent_payments if p.get('source') == 'stripe'])} ventas"
        )

    with col2:
        metric_card_small(
            icon="🔥",
            value=f"€{hotmart_revenue:,.0f}",
            label="Hotmart",
            sublabel=f"{len([p for p in recent_payments if p.get('source') == 'hotmart'])} ventas"
        )

    with col3:
        metric_card_small(
            icon="📊",
            value=str(month_transactions),
            label=t("revenue.transactions"),
            sublabel=t("revenue.this_month").lower()
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Two columns: Transactions and Funnel
    col1, col2 = st.columns([3, 2])

    with col1:
        st.markdown(f"""
        <h3 style="margin: 0 0 1rem 0; font-size: 1.125rem; font-weight: 500;">
            📋 {t('revenue.recent_transactions')}
        </h3>
        """, unsafe_allow_html=True)

        if recent_payments:
            for payment in recent_payments[:8]:
                status = payment.get("status", "pending")
                status_icon = "✅" if status == "completed" else "⏳" if status == "pending" else "❌"
                follower_id = payment.get("follower_id", "Unknown")
                product = payment.get("product_name", payment.get("product_id", "Unknown"))
                amount = payment.get("amount", 0)
                source = payment.get("source", "unknown").title()
                timestamp = payment.get("timestamp", "")

                st.markdown(f"""
                <div style="
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 0.75rem;
                    background-color: #141417;
                    border: 1px solid #1F1F23;
                    border-radius: 8px;
                    margin-bottom: 0.5rem;
                ">
                    <div style="display: flex; align-items: center; gap: 0.75rem;">
                        <span>{status_icon}</span>
                        <div>
                            <p style="color: white; margin: 0; font-weight: 500;">@{follower_id[:15]}</p>
                            <p style="color: #71717A; margin: 0; font-size: 0.8125rem;">{product}</p>
                        </div>
                    </div>
                    <div style="text-align: right;">
                        <p style="color: #10B981; margin: 0; font-weight: 600;">€{amount:,.0f}</p>
                        <p style="color: #71717A; margin: 0; font-size: 0.75rem;">{source} • {format_time_ago(timestamp)}</p>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            empty_state(
                icon="💸",
                title=t("empty_states.no_revenue"),
                description=t("empty_states.no_revenue_desc")
            )

    with col2:
        st.markdown(f"""
        <h3 style="margin: 0 0 1rem 0; font-size: 1.125rem; font-weight: 500;">
            📊 {t('revenue.funnel')}
        </h3>
        """, unsafe_allow_html=True)

        messages = funnel.get("messages", 0)
        leads = funnel.get("leads", 0)
        hot = funnel.get("hot", 0)
        customers = funnel.get("customers", 0)

        # Calculate percentages
        leads_pct = (leads / messages * 100) if messages > 0 else 0
        hot_pct = (hot / messages * 100) if messages > 0 else 0
        customers_pct = (customers / messages * 100) if messages > 0 else 0

        funnel_items = [
            (t("revenue.messages"), messages, 100, "#71717A"),
            ("Leads", leads, leads_pct, "#F59E0B"),
            ("Hot Leads", hot, hot_pct, "#EF4444"),
            ("Clientes", customers, customers_pct, "#10B981"),
        ]

        st.markdown(f"""
        <div style="
            background-color: #141417;
            border: 1px solid #1F1F23;
            border-radius: 12px;
            padding: 1.5rem;
        ">
        """, unsafe_allow_html=True)

        for label, value, pct, color in funnel_items:
            bar_width = max(5, min(100, pct if pct > 0 else (value / max(messages, 1) * 100)))
            st.markdown(f"""
            <div style="margin-bottom: 1rem;">
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.25rem;">
                    <span style="color: #71717A; font-size: 0.875rem;">{label}</span>
                    <span style="color: white; font-weight: 500;">{value:,}</span>
                </div>
                <div style="
                    background-color: #1F1F23;
                    border-radius: 4px;
                    height: 8px;
                    overflow: hidden;
                ">
                    <div style="
                        background-color: {color};
                        height: 100%;
                        width: {bar_width}%;
                        border-radius: 4px;
                    "></div>
                </div>
                <span style="color: #71717A; font-size: 0.75rem;">{pct:.1f}%</span>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        # Insight
        st.markdown(f"""
        <div style="
            background-color: rgba(6, 182, 212, 0.1);
            border-left: 4px solid #06B6D4;
            border-radius: 0 8px 8px 0;
            padding: 1rem;
            margin-top: 1rem;
        ">
            <p style="color: #06B6D4; margin: 0; font-weight: 500;">💡 {t('revenue.insight')}</p>
            <p style="color: #71717A; margin: 0.5rem 0 0 0; font-size: 0.875rem;">
                Los leads con objeción "precio" convierten 28% más si reciben la secuencia de nurturing.
            </p>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Payment connections
    col1, col2 = st.columns(2)

    with col1:
        if st.button(f"🔗 {t('revenue.connect_stripe')}", use_container_width=True):
            st.info("Conectar Stripe (próximamente)")

    with col2:
        if st.button(f"🔗 {t('revenue.connect_hotmart')}", use_container_width=True):
            st.info("Conectar Hotmart (próximamente)")
