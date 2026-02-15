"""
Nurturing Page - Automated Sequences
Visual sequence editor and progress tracking.
"""
import streamlit as st
from admin.utils import t
from admin.utils import load_nurturing_followups, load_followers


def render(creator_id: str):
    """Render the nurturing page."""

    # Load data
    _followups = load_nurturing_followups(creator_id)
    _followers = load_followers(creator_id)

    # Header
    col1, col2 = st.columns([3, 1])

    with col1:
        st.markdown(f"""
        <h1 style="margin: 0; font-size: 1.75rem; font-weight: 600;">
            🔄 {t('nurturing.title')}
        </h1>
        """, unsafe_allow_html=True)

    with col2:
        if st.button(f"+ {t('nurturing.new_sequence')}", use_container_width=True):
            st.info("Crear secuencia (próximamente)")

    st.markdown("<br>", unsafe_allow_html=True)

    # Sample sequences (would come from database in production)
    sequences = [
        {
            "id": "objection_price",
            "name": "Objeción Precio",
            "trigger": "Intent = objection_price",
            "steps": 3,
            "delays": ["24h", "48h", "72h"],
            "active_count": 12,
            "conversion_complete": 34,
            "conversion_buy": 18,
            "messages": [
                "Hola! Solo quería recordarte que el curso tiene garantía de 30 días...",
                "¿Te quedó alguna duda sobre el contenido? Estoy aquí para ayudarte.",
                "Último mensaje: El precio sube la semana que viene. ¿Te interesa?"
            ]
        },
        {
            "id": "no_response",
            "name": "Interés sin respuesta",
            "trigger": "No responde en 24h",
            "steps": 2,
            "delays": ["24h", "72h"],
            "active_count": 8,
            "conversion_complete": 28,
            "conversion_buy": 12,
            "messages": [
                "Hey! Vi que te quedaste a medias. ¿Puedo ayudarte en algo?",
                "Por si acaso, aquí te dejo el link directo al curso 👇"
            ]
        }
    ]

    # Render each sequence
    for seq in sequences:
        st.markdown(f"""
        <div style="
            background-color: #141417;
            border: 1px solid #1F1F23;
            border-radius: 16px;
            padding: 1.5rem;
            margin-bottom: 1rem;
        ">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1rem;">
                <div>
                    <p style="color: white; margin: 0; font-weight: 600; font-size: 1.125rem;">
                        📧 Secuencia: {seq['name']}
                    </p>
                    <p style="color: #71717A; margin: 0.25rem 0 0 0; font-size: 0.875rem;">
                        {t('nurturing.trigger')}: {seq['trigger']}
                    </p>
                </div>
                <span style="
                    background-color: rgba(16, 185, 129, 0.2);
                    color: #10B981;
                    padding: 0.25rem 0.75rem;
                    border-radius: 9999px;
                    font-size: 0.75rem;
                ">Activa</span>
            </div>

            <!-- Steps visualization -->
            <div style="
                display: flex;
                align-items: center;
                gap: 0.5rem;
                margin: 1.5rem 0;
                padding: 1rem;
                background-color: #0A0A0B;
                border-radius: 8px;
            ">
                <span style="color: #71717A;">[+]</span>
                <span style="color: #71717A;">──▶</span>
        """, unsafe_allow_html=True)

        # Steps
        steps_html = ""
        for i, delay in enumerate(seq["delays"]):
            steps_html += f"""
                <div style="
                    background-color: #1F1F23;
                    border-radius: 8px;
                    padding: 0.5rem 1rem;
                    text-align: center;
                ">
                    <p style="color: white; margin: 0; font-weight: 500;">{i + 1}</p>
                    <p style="color: #71717A; margin: 0; font-size: 0.75rem;">{delay}</p>
                </div>
                <span style="color: #71717A;">──▶</span>
            """

        st.markdown(f"""
                {steps_html}
                <div style="
                    background-color: rgba(16, 185, 129, 0.2);
                    border-radius: 8px;
                    padding: 0.5rem 1rem;
                    text-align: center;
                ">
                    <p style="color: #10B981; margin: 0;">✓</p>
                    <p style="color: #10B981; margin: 0; font-size: 0.75rem;">FIN</p>
                </div>
            </div>

            <!-- Stats -->
            <div style="display: flex; gap: 2rem; margin-bottom: 1rem;">
                <div>
                    <span style="color: #71717A; font-size: 0.875rem;">👥 </span>
                    <span style="color: white; font-weight: 500;">{seq['active_count']}</span>
                    <span style="color: #71717A; font-size: 0.875rem;"> {t('nurturing.active_people')}</span>
                </div>
                <div>
                    <span style="color: #71717A; font-size: 0.875rem;">📊 {t('nurturing.conversion')}: </span>
                    <span style="color: white;">{seq['conversion_complete']}% {t('nurturing.complete')} → {seq['conversion_buy']}% {t('nurturing.buy')}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Action buttons
        btn_col1, btn_col2, btn_col3 = st.columns(3)

        with btn_col1:
            if st.button(f"✏️ {t('nurturing.edit')}", key=f"edit_{seq['id']}", use_container_width=True):
                st.session_state[f"editing_{seq['id']}"] = True

        with btn_col2:
            if st.button(f"⏸️ {t('nurturing.pause')}", key=f"pause_{seq['id']}", use_container_width=True):
                st.info("Secuencia pausada (demo)")

        with btn_col3:
            if st.button(f"📊 {t('nurturing.stats')}", key=f"stats_{seq['id']}", use_container_width=True):
                st.info("Estadísticas detalladas (próximamente)")

        # Edit modal (simplified)
        if st.session_state.get(f"editing_{seq['id']}"):
            with st.expander("Editar secuencia", expanded=True):
                st.text_input("Nombre", value=seq["name"])
                st.text_input("Trigger", value=seq["trigger"])

                for i, msg in enumerate(seq["messages"]):
                    st.text_area(f"Mensaje {i + 1}", value=msg, height=100)

                col1, col2 = st.columns(2)
                with col1:
                    if st.button(f"💾 {t('nurturing.save')}", key=f"save_{seq['id']}"):
                        st.success("Guardado (demo)")
                        st.session_state[f"editing_{seq['id']}"] = False
                with col2:
                    if st.button("❌ Cancelar", key=f"cancel_{seq['id']}"):
                        st.session_state[f"editing_{seq['id']}"] = False
                        st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

    # Rules info
    st.markdown(f"""
    <div style="
        background-color: rgba(139, 92, 246, 0.1);
        border-left: 4px solid #8B5CF6;
        border-radius: 0 8px 8px 0;
        padding: 1rem;
        margin-top: 1rem;
    ">
        <p style="color: #8B5CF6; margin: 0; font-weight: 500;">💡 Reglas automáticas</p>
        <p style="color: #71717A; margin: 0.5rem 0 0 0; font-size: 0.875rem;">
            ⚡ {t('nurturing.if_replies')} → {t('nurturing.exit_sequence')}<br>
            🛒 {t('nurturing.if_buys')} → {t('nurturing.move_to_customers')}
        </p>
    </div>
    """, unsafe_allow_html=True)
