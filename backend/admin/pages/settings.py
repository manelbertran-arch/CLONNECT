"""
Settings Page - Configuration
Creator settings, connections, and bot configuration.
"""
import streamlit as st
from admin.utils import t
from admin.utils import load_creator_config, save_creator_config, load_products, save_products
from admin.components import empty_state


def render(creator_id: str):
    """Render the settings page."""

    # Load data
    config = load_creator_config(creator_id)
    products = load_products(creator_id)

    if not config:
        st.error(f"No se encontró configuración para {creator_id}")
        return

    # Header
    st.markdown(f"""
    <h1 style="margin: 0 0 1rem 0; font-size: 1.75rem; font-weight: 600;">
        ⚙️ {t('settings.title')}
    </h1>
    """, unsafe_allow_html=True)

    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        f"🎭 {t('settings.tab_personality')}",
        f"🔗 {t('settings.tab_connections')}",
        f"🤖 {t('settings.tab_bot')}",
        f"🛍️ {t('settings.tab_products')}"
    ])

    # ===== PERSONALITY TAB =====
    with tab1:
        st.markdown("<br>", unsafe_allow_html=True)

        # Basic info
        col1, col2 = st.columns(2)

        with col1:
            name = st.text_input(
                t("settings.visible_name"),
                value=config.get("name", "")
            )

        with col2:
            instagram_handle = st.text_input(
                "Instagram Handle",
                value=config.get("instagram_handle", "")
            )

        st.markdown("<br>", unsafe_allow_html=True)

        # Personality settings
        personality = config.get("personality", {})

        col1, col2, col3 = st.columns(3)

        tone_options = [t("settings.tone_friendly"), t("settings.tone_professional"), t("settings.tone_formal")]
        tone_values = ["cercano", "profesional", "formal"]

        formality_options = [t("settings.formality_informal"), t("settings.formality_neutral"), t("settings.formality_formal")]
        formality_values = ["informal", "neutral", "formal"]

        energy_options = [t("settings.energy_high"), t("settings.energy_medium"), t("settings.energy_low")]
        energy_values = ["alta", "media", "baja"]

        with col1:
            current_tone = personality.get("tone", "cercano")
            tone_idx = tone_values.index(current_tone) if current_tone in tone_values else 0
            tone = st.selectbox(t("settings.tone"), tone_options, index=tone_idx)

        with col2:
            current_formality = personality.get("formality", "informal")
            formality_idx = formality_values.index(current_formality) if current_formality in formality_values else 0
            formality = st.selectbox(t("settings.formality"), formality_options, index=formality_idx)

        with col3:
            current_energy = personality.get("energy", "alta")
            energy_idx = energy_values.index(current_energy) if current_energy in energy_values else 0
            energy = st.selectbox(t("settings.energy"), energy_options, index=energy_idx)

        st.markdown("<br>", unsafe_allow_html=True)

        col1, col2, col3 = st.columns(3)

        with col1:
            humor = st.checkbox(t("settings.use_humor"), value=personality.get("humor", True))
        with col2:
            emojis = st.checkbox(t("settings.use_emojis"), value=config.get("emoji_style", "moderate") != "none")
        with col3:
            empathy = st.checkbox(t("settings.show_empathy"), value=personality.get("empathy", True))

        st.markdown("<br>", unsafe_allow_html=True)

        # Vocabulary
        vocabulary = st.text_area(
            t("settings.favorite_words"),
            value=", ".join(config.get("vocabulary", [])),
            height=80,
            help="Palabras que el bot usará frecuentemente"
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # Preview
        st.markdown(f"""
        <p style="color: #71717A; margin-bottom: 0.5rem;">{t('settings.preview')}:</p>
        <div style="
            background-color: #1F1F23;
            border: 1px solid #2D2D35;
            border-radius: 12px;
            padding: 1rem;
        ">
            <p style="color: white; margin: 0; font-style: italic;">
                "¡Ey! Qué tal? Me alegra que escribas. El curso es brutal, vas a flipar con todo lo que incluye 🚀"
            </p>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Save button
        if st.button(f"💾 {t('settings.save_changes')}", use_container_width=True, key="save_personality"):
            # Update config
            config["name"] = name
            config["instagram_handle"] = instagram_handle
            config["personality"] = {
                "tone": tone_values[tone_options.index(tone)],
                "formality": formality_values[formality_options.index(formality)],
                "energy": energy_values[energy_options.index(energy)],
                "humor": humor,
                "empathy": empathy
            }
            config["vocabulary"] = [v.strip() for v in vocabulary.split(",") if v.strip()]
            config["emoji_style"] = "moderate" if emojis else "none"

            if save_creator_config(creator_id, config):
                st.success(f"✅ {t('common.success')}")
            else:
                st.error(f"❌ {t('common.error')}")

    # ===== CONNECTIONS TAB =====
    with tab2:
        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown(f"### {t('settings.channels')}")

        col1, col2, col3 = st.columns(3)

        # Instagram
        with col1:
            ig_token = config.get("instagram_access_token", "")
            ig_connected = bool(ig_token)

            st.markdown(f"""
            <div style="
                background-color: #141417;
                border: 1px solid #1F1F23;
                border-radius: 12px;
                padding: 1.5rem;
                text-align: center;
            ">
                <p style="font-size: 2rem; margin: 0;">📸</p>
                <p style="color: white; margin: 0.5rem 0; font-weight: 500;">Instagram</p>
                <p style="color: {'#10B981' if ig_connected else '#71717A'}; margin: 0; font-size: 0.875rem;">
                    {'✅ ' + t('settings.connected') if ig_connected else '⚪ ' + t('settings.not_configured')}
                </p>
                {f'<p style="color: #71717A; margin: 0.25rem 0 0 0; font-size: 0.75rem;">@{config.get("instagram_handle", "")}</p>' if ig_connected else ''}
            </div>
            """, unsafe_allow_html=True)

            btn_label = t("settings.disconnect") if ig_connected else t("settings.connect")
            if st.button(btn_label, key="ig_connect", use_container_width=True):
                st.info("Configuración de Instagram (próximamente)")

        # Telegram
        with col2:
            tg_token = config.get("telegram_token", "")
            tg_connected = bool(tg_token)

            st.markdown(f"""
            <div style="
                background-color: #141417;
                border: 1px solid #1F1F23;
                border-radius: 12px;
                padding: 1.5rem;
                text-align: center;
            ">
                <p style="font-size: 2rem; margin: 0;">📱</p>
                <p style="color: white; margin: 0.5rem 0; font-weight: 500;">Telegram</p>
                <p style="color: {'#10B981' if tg_connected else '#71717A'}; margin: 0; font-size: 0.875rem;">
                    {'✅ ' + t('settings.connected') if tg_connected else '⚪ ' + t('settings.not_configured')}
                </p>
            </div>
            """, unsafe_allow_html=True)

            btn_label = t("settings.disconnect") if tg_connected else t("settings.connect")
            if st.button(btn_label, key="tg_connect", use_container_width=True):
                st.info("Configuración de Telegram (próximamente)")

        # WhatsApp
        with col3:
            wa_connected = False

            st.markdown(f"""
            <div style="
                background-color: #141417;
                border: 1px solid #1F1F23;
                border-radius: 12px;
                padding: 1.5rem;
                text-align: center;
            ">
                <p style="font-size: 2rem; margin: 0;">💬</p>
                <p style="color: white; margin: 0.5rem 0; font-weight: 500;">WhatsApp</p>
                <p style="color: #71717A; margin: 0; font-size: 0.875rem;">
                    ⚪ {t('settings.not_configured')}
                </p>
            </div>
            """, unsafe_allow_html=True)

            if st.button(t("settings.connect"), key="wa_connect", use_container_width=True):
                st.info("WhatsApp Business (próximamente)")

        st.markdown("<br>", unsafe_allow_html=True)

        st.markdown(f"### {t('settings.payments')}")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"""
            <div style="
                background-color: #141417;
                border: 1px solid #1F1F23;
                border-radius: 12px;
                padding: 1.5rem;
                text-align: center;
            ">
                <p style="font-size: 2rem; margin: 0;">💳</p>
                <p style="color: white; margin: 0.5rem 0; font-weight: 500;">Stripe</p>
                <p style="color: #71717A; margin: 0; font-size: 0.875rem;">
                    ⚪ {t('settings.not_configured')}
                </p>
            </div>
            """, unsafe_allow_html=True)

            if st.button(t("settings.connect"), key="stripe_connect", use_container_width=True):
                st.info("Conectar Stripe (próximamente)")

        with col2:
            st.markdown(f"""
            <div style="
                background-color: #141417;
                border: 1px solid #1F1F23;
                border-radius: 12px;
                padding: 1.5rem;
                text-align: center;
            ">
                <p style="font-size: 2rem; margin: 0;">🔥</p>
                <p style="color: white; margin: 0.5rem 0; font-weight: 500;">Hotmart</p>
                <p style="color: #71717A; margin: 0; font-size: 0.875rem;">
                    ⚪ {t('settings.not_configured')}
                </p>
            </div>
            """, unsafe_allow_html=True)

            if st.button(t("settings.connect"), key="hotmart_connect", use_container_width=True):
                st.info("Conectar Hotmart (próximamente)")

    # ===== BOT TAB =====
    with tab3:
        st.markdown("<br>", unsafe_allow_html=True)

        is_active = config.get("is_active", True)

        col1, col2 = st.columns([1, 2])

        with col1:
            st.markdown(f"""
            <div style="
                background: {'linear-gradient(135deg, rgba(16, 185, 129, 0.2) 0%, rgba(5, 150, 105, 0.2) 100%)' if is_active else 'rgba(239, 68, 68, 0.1)'};
                border: 1px solid {'#10B981' if is_active else '#EF4444'};
                border-radius: 16px;
                padding: 2rem;
                text-align: center;
            ">
                <p style="font-size: 3rem; margin: 0;">{'🟢' if is_active else '🔴'}</p>
                <p style="color: white; margin: 0.5rem 0; font-weight: 600; font-size: 1.25rem;">
                    Bot {'Activo' if is_active else 'Pausado'}
                </p>
            </div>
            """, unsafe_allow_html=True)

            if is_active:
                if st.button("⏸️ Pausar Bot", use_container_width=True, key="pause_bot"):
                    config["is_active"] = False
                    save_creator_config(creator_id, config)
                    st.rerun()
            else:
                if st.button("▶️ Activar Bot", use_container_width=True, key="activate_bot"):
                    config["is_active"] = True
                    save_creator_config(creator_id, config)
                    st.rerun()

        with col2:
            st.markdown("### Configuración del Bot")

            max_messages = st.slider(
                "Mensajes antes de escalar a humano",
                min_value=5, max_value=30,
                value=config.get("max_messages_before_human", 15)
            )

            mention_price_after = st.slider(
                "Mencionar precio después de N mensajes",
                min_value=1, max_value=10,
                value=config.get("mention_price_after_messages", 3)
            )

            auto_payment_link = st.checkbox(
                "Enviar link de pago automáticamente",
                value=config.get("auto_send_payment_link", True)
            )

            if st.button(f"💾 {t('settings.save_changes')}", key="save_bot"):
                config["max_messages_before_human"] = max_messages
                config["mention_price_after_messages"] = mention_price_after
                config["auto_send_payment_link"] = auto_payment_link

                if save_creator_config(creator_id, config):
                    st.success(f"✅ {t('common.success')}")

    # ===== PRODUCTS TAB =====
    with tab4:
        st.markdown("<br>", unsafe_allow_html=True)

        if not products:
            empty_state(
                icon="🛍️",
                title="No hay productos",
                description="Añade productos para que el bot pueda venderlos"
            )
        else:
            for i, product in enumerate(products):
                is_active = product.get("is_active", True)
                is_featured = product.get("is_featured", False)

                status_icon = "🟢" if is_active else "🔴"
                featured_badge = "⭐" if is_featured else ""

                with st.expander(f"{status_icon} {featured_badge} {product.get('name', 'Sin nombre')} - €{product.get('price', 0)}"):
                    col1, col2 = st.columns([2, 1])

                    with col1:
                        st.write(f"**Descripción:** {product.get('description', '-')}")
                        st.write(f"**Categoría:** {product.get('category', '-')}")
                        st.write(f"**Link:** {product.get('payment_link', '-')}")

                    with col2:
                        st.write(f"**ID:** `{product.get('id', '-')}`")
                        st.write(f"**Activo:** {'Sí' if is_active else 'No'}")

                    btn_col1, btn_col2 = st.columns(2)

                    with btn_col1:
                        new_status = not is_active
                        if st.button(
                            f"{'🟢 Activar' if not is_active else '🔴 Desactivar'}",
                            key=f"toggle_prod_{i}",
                            use_container_width=True
                        ):
                            products[i]["is_active"] = new_status
                            if save_products(creator_id, products):
                                st.rerun()

                    with btn_col2:
                        if st.button("🗑️ Eliminar", key=f"delete_prod_{i}", use_container_width=True):
                            products.pop(i)
                            if save_products(creator_id, products):
                                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        if st.button("➕ Añadir Producto", use_container_width=True):
            st.info("Editor de productos (próximamente)")
