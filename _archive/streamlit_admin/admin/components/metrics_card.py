"""
Metric card components for the dashboard.
"""
import streamlit as st
from typing import Optional


def metric_card(
    title: str,
    value: str,
    subtitle: Optional[str] = None,
    icon: Optional[str] = None,
    delta: Optional[str] = None,
    delta_color: str = "normal"
):
    """
    Render a styled metric card.

    Args:
        title: Card title
        value: Main value to display
        subtitle: Optional subtitle text
        icon: Optional emoji icon
        delta: Optional change indicator (e.g., "+12%")
        delta_color: "normal", "inverse", or "off"
    """
    delta_html = ""
    if delta:
        if delta_color == "normal":
            color = "#10B981" if delta.startswith("+") else "#EF4444"
        elif delta_color == "inverse":
            color = "#EF4444" if delta.startswith("+") else "#10B981"
        else:
            color = "#71717A"
        delta_html = f'<span style="color: {color}; font-size: 0.875rem; margin-left: 0.5rem;">{delta}</span>'

    icon_html = f'<span style="font-size: 1.5rem; margin-right: 0.5rem;">{icon}</span>' if icon else ""
    subtitle_html = f'<p style="color: #71717A; margin: 0; font-size: 0.875rem;">{subtitle}</p>' if subtitle else ""

    st.markdown(f"""
    <div style="
        background-color: #141417;
        border: 1px solid #1F1F23;
        border-radius: 16px;
        padding: 1.5rem;
        transition: all 0.3s ease;
    ">
        <p style="color: #71717A; margin: 0 0 0.5rem 0; font-size: 0.875rem;">
            {icon_html}{title}
        </p>
        <p style="
            color: white;
            margin: 0;
            font-size: 2rem;
            font-weight: 700;
            background: linear-gradient(135deg, #8B5CF6 0%, #06B6D4 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        ">
            {value}{delta_html}
        </p>
        {subtitle_html}
    </div>
    """, unsafe_allow_html=True)


def metric_card_money(
    value: str,
    title: str,
    subtitle: Optional[str] = None,
    progress: Optional[float] = None,
    progress_label: Optional[str] = None
):
    """
    Render a large money-focused metric card with gradient background.

    Args:
        value: Money value (e.g., "€4,250")
        title: Title text
        subtitle: Optional subtitle
        progress: Optional progress value 0-100
        progress_label: Optional label for progress bar
    """
    progress_html = ""
    if progress is not None:
        progress_pct = min(100, max(0, progress))
        progress_html = f"""
        <div style="margin-top: 1rem;">
            <div style="
                background-color: rgba(255,255,255,0.2);
                border-radius: 9999px;
                height: 8px;
                width: 100%;
                overflow: hidden;
            ">
                <div style="
                    background-color: white;
                    height: 100%;
                    width: {progress_pct}%;
                    border-radius: 9999px;
                "></div>
            </div>
            <p style="color: rgba(255,255,255,0.8); margin: 0.5rem 0 0 0; font-size: 0.875rem;">
                {progress_label or f'{progress_pct:.0f}%'}
            </p>
        </div>
        """

    subtitle_html = f'<p style="color: rgba(255,255,255,0.8); margin: 0.5rem 0 0 0; font-size: 0.875rem;">{subtitle}</p>' if subtitle else ""

    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #10B981 0%, #059669 100%);
        border-radius: 16px;
        padding: 2rem;
        text-align: center;
    ">
        <p style="color: rgba(255,255,255,0.9); margin: 0; font-size: 1rem;">💰 {title}</p>
        <p style="
            color: white;
            margin: 0.5rem 0;
            font-size: 3rem;
            font-weight: 700;
        ">{value}</p>
        {subtitle_html}
        {progress_html}
    </div>
    """, unsafe_allow_html=True)


def metric_card_small(
    icon: str,
    value: str,
    label: str,
    sublabel: Optional[str] = None
):
    """
    Render a small metric card for secondary metrics.
    """
    sublabel_html = f'<span style="color: #71717A; font-size: 0.75rem; display: block;">{sublabel}</span>' if sublabel else ""

    st.markdown(f"""
    <div style="
        background-color: #141417;
        border: 1px solid #1F1F23;
        border-radius: 12px;
        padding: 1rem;
        text-align: center;
    ">
        <p style="font-size: 1.5rem; margin: 0;">{icon} {value}</p>
        <p style="color: #71717A; margin: 0.25rem 0 0 0; font-size: 0.875rem;">{label}</p>
        {sublabel_html}
    </div>
    """, unsafe_allow_html=True)


def action_card(
    icon: str,
    title: str,
    subtitle: str,
    time_ago: str,
    severity: str = "warning",
    on_click_key: Optional[str] = None
):
    """
    Render an action required card.

    Args:
        icon: Status icon (🔴, 🟠, 🟡)
        title: Action title
        subtitle: Description
        time_ago: Time string
        severity: "urgent", "warning", or "info"
        on_click_key: Optional button key
    """
    border_color = {
        "urgent": "#EF4444",
        "warning": "#F59E0B",
        "info": "#06B6D4"
    }.get(severity, "#F59E0B")

    st.markdown(f"""
    <div style="
        background-color: rgba({','.join(str(int(border_color.lstrip('#')[i:i+2], 16)) for i in (0, 2, 4))}, 0.1);
        border-left: 4px solid {border_color};
        border-radius: 0 8px 8px 0;
        padding: 1rem;
        margin-bottom: 0.5rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
    ">
        <div>
            <p style="color: white; margin: 0; font-weight: 500;">{icon} {title}</p>
            <p style="color: #71717A; margin: 0.25rem 0 0 0; font-size: 0.875rem;">{subtitle}</p>
        </div>
        <span style="color: #71717A; font-size: 0.75rem;">{time_ago}</span>
    </div>
    """, unsafe_allow_html=True)

    if on_click_key:
        return st.button("→", key=on_click_key, help="Ver detalle")
    return False


def empty_state(
    icon: str,
    title: str,
    description: str,
    action_label: Optional[str] = None,
    action_key: Optional[str] = None
):
    """
    Render an empty state with icon and optional action.
    """
    st.markdown(f"""
    <div style="
        text-align: center;
        padding: 3rem 2rem;
        background-color: #141417;
        border: 1px dashed #1F1F23;
        border-radius: 16px;
    ">
        <p style="font-size: 3rem; margin: 0;">{icon}</p>
        <p style="color: white; margin: 1rem 0 0.5rem 0; font-size: 1.125rem; font-weight: 500;">{title}</p>
        <p style="color: #71717A; margin: 0;">{description}</p>
    </div>
    """, unsafe_allow_html=True)

    if action_label and action_key:
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            return st.button(action_label, key=action_key, use_container_width=True)
    return False
