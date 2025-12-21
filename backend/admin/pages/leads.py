"""
Leads Page - Visual CRM Pipeline
Kanban-style pipeline board for lead management.
"""
import streamlit as st
from admin.utils import t, format_time_ago
from admin.utils import get_pipeline_data, get_platform_icon, load_products
from admin.components import empty_state


def render(creator_id: str):
    """Render the leads page."""

    # Load data
    pipeline = get_pipeline_data(creator_id)
    products = load_products(creator_id)

    # Calculate pipeline value
    avg_ticket = sum(p.get("price", 0) for p in products) / len(products) if products else 297
    pipeline_value = len(pipeline.get("hot", [])) * avg_ticket + len(pipeline.get("active", [])) * avg_ticket * 0.3

    # Header
    col1, col2 = st.columns([3, 1])

    with col1:
        st.markdown(f"""
        <h1 style="margin: 0; font-size: 1.75rem; font-weight: 600;">
            👥 {t('leads.title')}
        </h1>
        """, unsafe_allow_html=True)

    with col2:
        if st.button(f"+ {t('leads.import')}", use_container_width=True):
            st.info("Importar leads (próximamente)")

    st.markdown("<br>", unsafe_allow_html=True)

    # Pipeline columns
    col1, col2, col3, col4 = st.columns(4)

    columns_config = [
        (col1, "new", t("leads.column_new"), "#71717A"),
        (col2, "active", t("leads.column_active"), "#06B6D4"),
        (col3, "hot", t("leads.column_hot"), "#F59E0B"),
        (col4, "customers", t("leads.column_customers"), "#10B981"),
    ]

    for col, key, title, color in columns_config:
        with col:
            leads_in_column = pipeline.get(key, [])
            count = len(leads_in_column)

            # Column header
            st.markdown(f"""
            <div style="
                background-color: #141417;
                border: 1px solid #1F1F23;
                border-top: 3px solid {color};
                border-radius: 12px;
                padding: 1rem;
                min-height: 500px;
            ">
                <div style="
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 1rem;
                ">
                    <span style="color: white; font-weight: 600;">{title}</span>
                    <span style="
                        background-color: #1F1F23;
                        color: {color};
                        padding: 0.125rem 0.5rem;
                        border-radius: 9999px;
                        font-size: 0.875rem;
                    ">{count}</span>
                </div>
            """, unsafe_allow_html=True)

            # Lead cards
            if leads_in_column:
                for lead in leads_in_column[:10]:
                    follower_id = lead.get("follower_id", "")
                    name = lead.get("name") or lead.get("username") or follower_id
                    score = lead.get("purchase_intent_score", 0)
                    platform_icon = get_platform_icon(follower_id)

                    # Determine border color based on score
                    if score >= 0.7:
                        border_class = "#EF4444"
                    elif score >= 0.4:
                        border_class = "#F59E0B"
                    else:
                        border_class = "#1F1F23"

                    # For customers, show revenue instead of score
                    if key == "customers":
                        value_display = f"€{avg_ticket:.0f}"
                        value_color = "#10B981"
                    else:
                        value_display = f"{score:.2f}"
                        value_color = color

                    st.markdown(f"""
                    <div style="
                        background-color: #0A0A0B;
                        border: 1px solid #1F1F23;
                        border-left: 3px solid {border_class};
                        border-radius: 8px;
                        padding: 0.75rem;
                        margin-bottom: 0.5rem;
                        cursor: pointer;
                        transition: all 0.2s ease;
                    ">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="color: white; font-size: 0.875rem;">{platform_icon} @{name[:12]}</span>
                            <span style="color: {value_color}; font-size: 0.75rem; font-weight: 500;">
                                {value_display}
                            </span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <p style="color: #52525B; text-align: center; font-size: 0.875rem; padding: 2rem 0;">
                    Sin leads
                </p>
                """, unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)

    # Pipeline value footer
    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(f"""
    <div style="
        background-color: #141417;
        border: 1px solid #1F1F23;
        border-radius: 12px;
        padding: 1rem 1.5rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
    ">
        <span style="color: #71717A;">💰 {t('leads.pipeline_value')}:</span>
        <span style="
            color: #10B981;
            font-size: 1.5rem;
            font-weight: 700;
        ">€{pipeline_value:,.0f} <span style="color: #71717A; font-size: 0.875rem; font-weight: 400;">{t('leads.potential')}</span></span>
    </div>
    """, unsafe_allow_html=True)
