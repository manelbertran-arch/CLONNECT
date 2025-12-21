"""
Clonnect Creators Dashboard - Streamlit App
Dashboard mejorado para gestionar el clon de IA
"""

import streamlit as st
import requests
import os
from datetime import datetime, timedelta
import json

# Configuracion
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

# Configuracion de pagina
st.set_page_config(
    page_title="Clonnect Creators",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizado
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 1rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .lead-hot {
        background-color: #ff4b4b;
        padding: 0.2rem 0.5rem;
        border-radius: 5px;
        color: white;
        font-size: 0.8rem;
    }
    .lead-warm {
        background-color: #ffa726;
        padding: 0.2rem 0.5rem;
        border-radius: 5px;
        color: white;
        font-size: 0.8rem;
    }
    .lead-cold {
        background-color: #42a5f5;
        padding: 0.2rem 0.5rem;
        border-radius: 5px;
        color: white;
        font-size: 0.8rem;
    }
</style>
""", unsafe_allow_html=True)

# Estado de sesion
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "api_key" not in st.session_state:
    st.session_state.api_key = ""
if "creator_id" not in st.session_state:
    st.session_state.creator_id = None
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False
if "page" not in st.session_state:
    st.session_state.page = "home"
if "test_messages" not in st.session_state:
    st.session_state.test_messages = []


def get_headers():
    """Obtener headers con API key"""
    return {"X-API-Key": st.session_state.api_key}


def api_get(endpoint: str):
    """GET request a la API"""
    try:
        resp = requests.get(
            f"{API_BASE_URL}{endpoint}",
            headers=get_headers(),
            timeout=10
        )
        if resp.status_code == 401:
            st.session_state.authenticated = False
            st.rerun()
        return resp.json() if resp.ok else None
    except Exception as e:
        st.error(f"Error de conexion: {e}")
        return None


def api_post(endpoint: str, data: dict):
    """POST request a la API"""
    try:
        resp = requests.post(
            f"{API_BASE_URL}{endpoint}",
            json=data,
            headers=get_headers(),
            timeout=30
        )
        if resp.status_code == 401:
            st.session_state.authenticated = False
            st.rerun()
        return resp.json() if resp.ok else None
    except Exception as e:
        st.error(f"Error de conexion: {e}")
        return None


def api_put(endpoint: str, data: dict = None):
    """PUT request a la API"""
    try:
        resp = requests.put(
            f"{API_BASE_URL}{endpoint}",
            json=data or {},
            headers=get_headers(),
            timeout=10
        )
        return resp.json() if resp.ok else None
    except Exception as e:
        st.error(f"Error de conexion: {e}")
        return None


def api_delete(endpoint: str):
    """DELETE request a la API"""
    try:
        resp = requests.delete(
            f"{API_BASE_URL}{endpoint}",
            headers=get_headers(),
            timeout=10
        )
        return resp.json() if resp.ok else None
    except Exception as e:
        st.error(f"Error de conexion: {e}")
        return None


def verify_api_key(api_key: str) -> dict:
    """Verificar API key"""
    try:
        resp = requests.get(
            f"{API_BASE_URL}/auth/verify",
            headers={"X-API-Key": api_key},
            timeout=10
        )
        return resp.json() if resp.ok else None
    except:
        return None


def get_lead_category(score: float) -> tuple:
    """Categorizar lead por score"""
    if score >= 0.7:
        return "hot", "🔥 Hot Lead"
    elif score >= 0.4:
        return "warm", "🌡️ Warm Lead"
    else:
        return "cold", "❄️ Cold Lead"


# =============================================
# LOGIN
# =============================================
if not st.session_state.authenticated:
    st.markdown('<p class="main-header">🤖 Clonnect Creators</p>', unsafe_allow_html=True)
    st.markdown("### Iniciar Sesion")

    with st.form("login_form"):
        api_key = st.text_input("API Key", type="password", placeholder="clk_...")
        submitted = st.form_submit_button("🔐 Entrar", type="primary", use_container_width=True)

        if submitted and api_key:
            with st.spinner("Verificando..."):
                result = verify_api_key(api_key)

            if result and result.get("valid"):
                st.session_state.authenticated = True
                st.session_state.api_key = api_key
                st.session_state.creator_id = result.get("creator_id")
                st.session_state.is_admin = result.get("is_admin", False)
                st.success("✅ Acceso concedido")
                st.rerun()
            else:
                st.error("❌ API Key invalida")

    st.divider()
    st.caption("Obtener API key: Contacta al administrador")
    st.stop()


# =============================================
# SIDEBAR (autenticado)
# =============================================
with st.sidebar:
    st.markdown('<p class="main-header">🤖 Clonnect</p>', unsafe_allow_html=True)

    if st.session_state.is_admin:
        st.success("👑 Admin")
    else:
        st.info(f"👤 {st.session_state.creator_id}")

    st.divider()

    # Selector de creador (solo admin)
    if st.session_state.is_admin:
        creator_list = api_get("/creator/list")
        creators = creator_list.get("creators", []) if creator_list else []

        if creators:
            selected_creator = st.selectbox(
                "Seleccionar Creador",
                creators,
                index=0
            )
            st.session_state.creator_id = selected_creator
        else:
            creator_id = st.text_input("ID de Creador", value="demo_creator")
            st.session_state.creator_id = creator_id
    else:
        st.markdown(f"**Creador:** {st.session_state.creator_id}")

    st.divider()

    # Navegacion
    st.markdown("### 📍 Navegacion")

    nav_items = [
        ("🏠 Dashboard", "home"),
        ("📊 Metricas", "metrics"),
        ("💬 Conversaciones", "conversations"),
        ("🎯 Leads", "leads"),
        ("📦 Productos", "products"),
        ("⚙️ Configuracion", "config"),
        ("🧪 Probar Bot", "test"),
    ]

    if st.session_state.is_admin:
        nav_items.append(("🔑 API Keys", "api_keys"))

    for label, page_id in nav_items:
        if st.button(label, use_container_width=True, key=f"nav_{page_id}"):
            st.session_state.page = page_id
            st.rerun()

    st.divider()

    # Estado del bot
    st.markdown("### ⚡ Estado del Bot")

    bot_status = api_get(f"/bot/{st.session_state.creator_id}/status")
    bot_active = bot_status.get("active", False) if bot_status else False

    col1, col2 = st.columns(2)
    with col1:
        if st.button("▶️ Activar" if not bot_active else "⏸️ Pausar", use_container_width=True):
            if bot_active:
                api_post(f"/bot/{st.session_state.creator_id}/pause", {})
            else:
                api_post(f"/bot/{st.session_state.creator_id}/resume", {})
            st.rerun()

    with col2:
        if bot_active:
            st.success("Activo")
        else:
            st.warning("Pausado")

    st.divider()

    if st.button("🚪 Cerrar Sesion", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.api_key = ""
        st.session_state.creator_id = None
        st.rerun()

    st.caption("Clonnect Creators v1.0")


# =============================================
# PAGINA: HOME / DASHBOARD
# =============================================
if st.session_state.page == "home":
    st.markdown('<p class="main-header">🏠 Dashboard</p>', unsafe_allow_html=True)

    overview = api_get(f"/dashboard/{st.session_state.creator_id}/overview")

    if overview and overview.get("status") == "ok":
        metrics = overview.get("metrics", {})

        # Metricas principales
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("💬 Mensajes", metrics.get("total_messages", 0))

        with col2:
            st.metric("👥 Seguidores", metrics.get("total_followers", 0))

        with col3:
            st.metric("🎯 Leads", metrics.get("leads", 0))

        with col4:
            st.metric("🔥 Alta Intencion", metrics.get("high_intent_followers", 0))

        # Segunda fila
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            conversion = metrics.get("conversion_rate", 0) * 100
            st.metric("📈 Conversion", f"{conversion:.1f}%")

        with col2:
            lead_rate = metrics.get("lead_rate", 0) * 100
            st.metric("🎯 Lead Rate", f"{lead_rate:.1f}%")

        with col3:
            st.metric("📦 Productos", overview.get("products_count", 0))

        with col4:
            st.metric("💰 Clientes", metrics.get("customers", 0))

        st.divider()

        # Dos columnas: Conversaciones y Leads
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("💬 Conversaciones Recientes")
            conversations = overview.get("recent_conversations", [])

            if conversations:
                for conv in conversations[:5]:
                    name = conv.get("name") or conv.get("username") or "Usuario"
                    intent = conv.get("purchase_intent", 0)
                    cat, label = get_lead_category(intent)

                    st.markdown(f"**@{conv.get('username', 'usuario')}** - {name}")
                    st.caption(f"{conv.get('total_messages', 0)} msgs | {label}")
                    st.divider()
            else:
                st.info("👋 No hay conversaciones")

        with col2:
            st.subheader("🔥 Top Leads")
            leads = overview.get("leads", [])

            if leads:
                for lead in sorted(leads, key=lambda x: x.get("purchase_intent", 0), reverse=True)[:5]:
                    intent = lead.get("purchase_intent", 0)
                    cat, label = get_lead_category(intent)

                    st.markdown(f"**@{lead.get('username', 'usuario')}**")
                    st.progress(intent, text=f"{intent:.0%} intencion")
                    st.divider()
            else:
                st.info("🌱 No hay leads aun")

    else:
        st.warning("⚠️ No se pudo cargar el dashboard")
        if st.button("➕ Crear configuracion"):
            st.session_state.page = "config"
            st.rerun()


# =============================================
# PAGINA: METRICAS
# =============================================
elif st.session_state.page == "metrics":
    st.markdown('<p class="main-header">📊 Metricas</p>', unsafe_allow_html=True)

    overview = api_get(f"/dashboard/{st.session_state.creator_id}/overview")
    metrics = overview.get("metrics", {}) if overview else {}

    # Resumen
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("📨 Total Mensajes", metrics.get("total_messages", 0))
        st.metric("👥 Total Seguidores", metrics.get("total_followers", 0))

    with col2:
        st.metric("🎯 Total Leads", metrics.get("leads", 0))
        conversion = metrics.get("conversion_rate", 0) * 100
        st.metric("📈 Tasa Conversion", f"{conversion:.1f}%")

    with col3:
        st.metric("💰 Clientes", metrics.get("customers", 0))
        lead_rate = metrics.get("lead_rate", 0) * 100
        st.metric("🎯 Lead Rate", f"{lead_rate:.1f}%")

    st.divider()

    # Distribucion de intenciones
    st.subheader("📊 Distribucion de Leads")

    conversations = api_get(f"/dm/conversations/{st.session_state.creator_id}?limit=100")
    convs = conversations.get("conversations", []) if conversations else []

    if convs:
        hot = sum(1 for c in convs if c.get("purchase_intent", 0) >= 0.7)
        warm = sum(1 for c in convs if 0.4 <= c.get("purchase_intent", 0) < 0.7)
        cold = sum(1 for c in convs if c.get("purchase_intent", 0) < 0.4)

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric("🔥 Hot Leads", hot, help="Score >= 70%")

        with col2:
            st.metric("🌡️ Warm Leads", warm, help="Score 40-70%")

        with col3:
            st.metric("❄️ Cold Leads", cold, help="Score < 40%")

        # Grafico simple con Streamlit
        import pandas as pd
        df = pd.DataFrame({
            "Categoria": ["Hot", "Warm", "Cold"],
            "Cantidad": [hot, warm, cold]
        })
        st.bar_chart(df.set_index("Categoria"))

    else:
        st.info("📊 No hay datos suficientes para mostrar metricas")

    st.divider()

    # Productos mas discutidos
    st.subheader("📦 Productos Mas Mencionados")

    if convs:
        product_mentions = {}
        for conv in convs:
            for prod in conv.get("products_discussed", []):
                product_mentions[prod] = product_mentions.get(prod, 0) + 1

        if product_mentions:
            sorted_products = sorted(product_mentions.items(), key=lambda x: x[1], reverse=True)
            for prod, count in sorted_products[:5]:
                st.markdown(f"**{prod}**: {count} menciones")
        else:
            st.info("No hay productos mencionados aun")
    else:
        st.info("No hay conversaciones con productos")


# =============================================
# PAGINA: CONVERSACIONES
# =============================================
elif st.session_state.page == "conversations":
    st.markdown('<p class="main-header">💬 Conversaciones</p>', unsafe_allow_html=True)

    data = api_get(f"/dm/conversations/{st.session_state.creator_id}?limit=50")

    if data and data.get("conversations"):
        conversations = data["conversations"]

        # Filtros
        col1, col2, col3 = st.columns(3)

        with col1:
            filter_type = st.selectbox(
                "Filtrar por",
                ["Todos", "Solo Leads", "Hot Leads", "Clientes"]
            )

        with col2:
            sort_by = st.selectbox(
                "Ordenar por",
                ["Mas reciente", "Mayor intencion", "Mas mensajes"]
            )

        with col3:
            search = st.text_input("Buscar", placeholder="@usuario")

        # Aplicar filtros
        if filter_type == "Solo Leads":
            conversations = [c for c in conversations if c.get("is_lead")]
        elif filter_type == "Hot Leads":
            conversations = [c for c in conversations if c.get("purchase_intent", 0) >= 0.7]
        elif filter_type == "Clientes":
            conversations = [c for c in conversations if c.get("is_customer")]

        if search:
            conversations = [c for c in conversations if search.lower() in c.get("username", "").lower()]

        # Ordenar
        if sort_by == "Mayor intencion":
            conversations = sorted(conversations, key=lambda x: x.get("purchase_intent", 0), reverse=True)
        elif sort_by == "Mas mensajes":
            conversations = sorted(conversations, key=lambda x: x.get("total_messages", 0), reverse=True)

        st.caption(f"Mostrando {len(conversations)} conversaciones")

        for conv in conversations:
            intent = conv.get("purchase_intent", 0)
            cat, label = get_lead_category(intent)

            with st.expander(f"@{conv.get('username', 'usuario')} - {conv.get('name', '')} | {label}"):
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.markdown(f"**Mensajes:** {conv.get('total_messages', 0)}")
                    st.markdown(f"**Primer contacto:** {conv.get('first_contact', 'N/A')[:10]}")

                with col2:
                    st.markdown(f"**Ultimo contacto:** {conv.get('last_contact', 'N/A')[:10]}")
                    st.progress(intent, text=f"Intencion: {intent:.0%}")

                with col3:
                    if conv.get("is_lead"):
                        st.success("🎯 Lead")
                    if conv.get("is_customer"):
                        st.success("💰 Cliente")

                interests = conv.get("interests", [])
                if interests:
                    st.markdown(f"**Intereses:** {', '.join(interests)}")

                products = conv.get("products_discussed", [])
                if products:
                    st.markdown(f"**Productos:** {', '.join(products)}")

                # Ver detalle
                if st.button("👁️ Ver historial", key=f"view_{conv.get('follower_id')}"):
                    detail = api_get(f"/dm/follower/{st.session_state.creator_id}/{conv.get('follower_id')}")
                    if detail:
                        st.json(detail)

    else:
        st.info("👋 No hay conversaciones aun")


# =============================================
# PAGINA: LEADS
# =============================================
elif st.session_state.page == "leads":
    st.markdown('<p class="main-header">🎯 Leads</p>', unsafe_allow_html=True)

    data = api_get(f"/dm/leads/{st.session_state.creator_id}")

    if data and data.get("leads"):
        leads = data["leads"]

        # Filtros rapidos
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("🔥 Hot", use_container_width=True):
                leads = [l for l in leads if l.get("purchase_intent", 0) >= 0.7]

        with col2:
            if st.button("🌡️ Warm", use_container_width=True):
                leads = [l for l in leads if 0.4 <= l.get("purchase_intent", 0) < 0.7]

        with col3:
            if st.button("❄️ Cold", use_container_width=True):
                leads = [l for l in leads if l.get("purchase_intent", 0) < 0.4]

        st.success(f"🎯 {len(leads)} leads encontrados")

        # Ordenar por intencion
        leads = sorted(leads, key=lambda x: x.get("purchase_intent", 0), reverse=True)

        for lead in leads:
            intent = lead.get("purchase_intent", 0)
            cat, label = get_lead_category(intent)

            col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

            with col1:
                st.markdown(f"### @{lead.get('username', 'usuario')}")
                if lead.get("name"):
                    st.caption(lead.get("name"))

            with col2:
                st.metric("Intencion", f"{intent:.0%}")

            with col3:
                st.metric("Mensajes", lead.get("total_messages", 0))

            with col4:
                st.markdown(f"<span class='lead-{cat}'>{label}</span>", unsafe_allow_html=True)

            products = lead.get("products_discussed", [])
            if products:
                st.markdown(f"**Productos:** {', '.join(products)}")

            st.divider()

    else:
        st.info("🌱 Aun no hay leads")


# =============================================
# PAGINA: PRODUCTOS
# =============================================
elif st.session_state.page == "products":
    st.markdown('<p class="main-header">📦 Productos</p>', unsafe_allow_html=True)

    data = api_get(f"/creator/{st.session_state.creator_id}/products")
    products = data.get("products", []) if data else []

    if products:
        st.success(f"📦 {len(products)} productos")

        for product in products:
            with st.expander(f"**{product.get('name')}** - {product.get('price')} {product.get('currency', 'EUR')}"):
                col1, col2 = st.columns([3, 1])

                with col1:
                    st.markdown(f"**Descripcion:** {product.get('description', 'N/A')}")
                    st.markdown(f"**Categoria:** {product.get('category', 'N/A')}")
                    st.markdown(f"**Link:** {product.get('payment_link', 'N/A')}")

                    features = product.get("features", [])
                    if features:
                        st.markdown("**Incluye:**")
                        for f in features:
                            st.markdown(f"✅ {f}")

                with col2:
                    if product.get("is_featured"):
                        st.success("⭐ Destacado")

                    if st.button(f"🗑️ Eliminar", key=f"del_{product.get('id')}"):
                        api_delete(f"/creator/{st.session_state.creator_id}/products/{product.get('id')}")
                        st.rerun()

    else:
        st.info("📦 No hay productos")

    st.divider()

    # Anadir producto
    st.subheader("➕ Anadir Producto")

    with st.form("new_product"):
        col1, col2 = st.columns(2)

        with col1:
            prod_id = st.text_input("ID", placeholder="mi-curso")
            prod_name = st.text_input("Nombre*", placeholder="Mi Curso")
            prod_price = st.number_input("Precio", min_value=0.0, step=10.0)

        with col2:
            prod_category = st.text_input("Categoria", placeholder="Cursos")
            prod_link = st.text_input("Link de pago", placeholder="https://...")
            prod_currency = st.selectbox("Moneda", ["EUR", "USD", "MXN"])

        prod_desc = st.text_area("Descripcion*", placeholder="Describe tu producto...")
        prod_features = st.text_area("Caracteristicas (una por linea)")

        submitted = st.form_submit_button("➕ Anadir", type="primary", use_container_width=True)

        if submitted and prod_name and prod_desc:
            features_list = [f.strip() for f in prod_features.split("\n") if f.strip()]

            new_product = {
                "id": prod_id or prod_name.lower().replace(" ", "-"),
                "name": prod_name,
                "description": prod_desc,
                "price": prod_price,
                "currency": prod_currency,
                "payment_link": prod_link,
                "category": prod_category,
                "features": features_list
            }

            result = api_post(f"/creator/{st.session_state.creator_id}/products", new_product)
            if result:
                st.success("✅ Producto anadido")
                st.rerun()


# =============================================
# PAGINA: CONFIGURACION
# =============================================
elif st.session_state.page == "config":
    st.markdown('<p class="main-header">⚙️ Configuracion</p>', unsafe_allow_html=True)

    config = api_get(f"/creator/config/{st.session_state.creator_id}")

    if config and "id" in config:
        st.success(f"✅ Config cargada: **{config.get('name', '')}**")
        editing = True
    else:
        st.info("➕ Crear nueva configuracion")
        config = {}
        editing = False

    with st.form("config_form"):
        st.subheader("📋 Informacion Basica")

        col1, col2 = st.columns(2)

        with col1:
            name = st.text_input("Nombre", value=config.get("name", ""))
            ig_handle = st.text_input("Instagram @", value=config.get("instagram_handle", ""))

        with col2:
            email = st.text_input("Email escalacion", value=config.get("escalation_email", ""))

        st.subheader("🎭 Personalidad")

        col1, col2, col3 = st.columns(3)
        personality = config.get("personality", {})

        with col1:
            tone = st.selectbox(
                "Tono",
                ["cercano", "profesional", "divertido", "inspirador"],
                index=["cercano", "profesional", "divertido", "inspirador"].index(
                    personality.get("tone", "cercano")
                )
            )

        with col2:
            formality = st.selectbox(
                "Formalidad",
                ["informal", "formal", "mixto"],
                index=["informal", "formal", "mixto"].index(
                    personality.get("formality", "informal")
                )
            )

        with col3:
            emoji_style = st.selectbox(
                "Emojis",
                ["none", "minimal", "moderate", "heavy"],
                index=["none", "minimal", "moderate", "heavy"].index(
                    config.get("emoji_style", "moderate")
                )
            )

        col1, col2 = st.columns(2)

        with col1:
            humor = st.checkbox("Incluir humor", value=personality.get("humor", True))

        with col2:
            empathy = st.checkbox("Mostrar empatia", value=personality.get("empathy", True))

        st.subheader("💼 Ventas")

        col1, col2 = st.columns(2)

        with col1:
            sales_style = st.selectbox(
                "Estilo de ventas",
                ["soft", "moderate", "direct"],
                index=["soft", "moderate", "direct"].index(
                    config.get("sales_style", "soft")
                )
            )

        with col2:
            max_messages = st.number_input(
                "Mensajes antes de escalar",
                min_value=5,
                max_value=50,
                value=config.get("max_messages_before_human", 15)
            )

        submitted = st.form_submit_button("💾 Guardar", type="primary", use_container_width=True)

        if submitted:
            new_config = {
                "id": st.session_state.creator_id,
                "name": name,
                "instagram_handle": ig_handle,
                "escalation_email": email,
                "personality": {
                    "tone": tone,
                    "formality": formality,
                    "humor": humor,
                    "empathy": empathy
                },
                "emoji_style": emoji_style,
                "sales_style": sales_style,
                "max_messages_before_human": max_messages
            }

            if editing:
                result = api_put(f"/creator/config/{st.session_state.creator_id}", new_config)
            else:
                result = api_post("/creator/config", new_config)

            if result:
                st.success("✅ Guardado")
                st.rerun()
            else:
                st.error("❌ Error al guardar")


# =============================================
# PAGINA: PROBAR BOT
# =============================================
elif st.session_state.page == "test":
    st.markdown('<p class="main-header">🧪 Probar el Bot</p>', unsafe_allow_html=True)

    st.info("💬 Simula una conversacion de DM para probar tu bot")

    # Historial de chat
    for msg in st.session_state.test_messages:
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.write(msg["content"])
        else:
            with st.chat_message("assistant"):
                st.write(msg["content"])
                if msg.get("intent"):
                    st.caption(f"Intent: {msg['intent']} | Confianza: {msg.get('confidence', 0):.0%}")

    # Input de chat
    user_input = st.chat_input("Escribe un mensaje...")

    if user_input:
        st.session_state.test_messages.append({"role": "user", "content": user_input})

        with st.chat_message("user"):
            st.write(user_input)

        with st.spinner("Pensando..."):
            result = api_post("/dm/process", {
                "creator_id": st.session_state.creator_id,
                "sender_id": "test_user_dashboard",
                "message": user_input
            })

        if result and result.get("response"):
            response = result["response"]
            intent = result.get("intent", "unknown")
            confidence = result.get("confidence", 0)

            st.session_state.test_messages.append({
                "role": "assistant",
                "content": response,
                "intent": intent,
                "confidence": confidence
            })

            with st.chat_message("assistant"):
                st.write(response)
                st.caption(f"Intent: {intent} | Confianza: {confidence:.0%}")
        else:
            st.error("❌ Error al procesar")

    # Botones
    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button("🗑️ Limpiar Chat", use_container_width=True):
            st.session_state.test_messages = []
            st.rerun()

    with col2:
        if st.button("💡 Ejemplos", use_container_width=True):
            st.markdown("""
            **Prueba estos mensajes:**
            - "Hola! Me encanta tu contenido"
            - "Tienes algun curso?"
            - "Cuanto cuesta?"
            - "Es muy caro para mi"
            - "Quiero comprar ahora"
            """)

    with col3:
        bot_status = api_get(f"/bot/{st.session_state.creator_id}/status")
        if bot_status and bot_status.get("active"):
            st.success("Bot Activo")
        else:
            st.warning("Bot Pausado")


# =============================================
# PAGINA: API KEYS (Solo Admin)
# =============================================
elif st.session_state.page == "api_keys" and st.session_state.is_admin:
    st.markdown('<p class="main-header">🔑 API Keys</p>', unsafe_allow_html=True)

    # Listar keys
    keys_data = api_get("/auth/keys")
    keys = keys_data.get("keys", []) if keys_data else []

    if keys:
        st.success(f"🔑 {len(keys)} API keys")

        for key in keys:
            status = "🟢 Activa" if key.get("active") else "🔴 Revocada"
            col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

            with col1:
                st.markdown(f"**{key.get('key_prefix')}...**")
                st.caption(f"Creator: {key.get('creator_id')}")

            with col2:
                st.markdown(key.get("name") or "Sin nombre")

            with col3:
                st.caption(f"Creada: {key.get('created_at', '')[:10]}")

            with col4:
                st.markdown(status)
                if key.get("active"):
                    if st.button("Revocar", key=f"revoke_{key.get('key_prefix')}"):
                        api_delete(f"/auth/keys/{key.get('key_prefix')}")
                        st.rerun()

            st.divider()
    else:
        st.info("No hay API keys")

    st.divider()

    # Crear nueva key
    st.subheader("➕ Crear API Key")

    with st.form("new_key"):
        col1, col2 = st.columns(2)

        with col1:
            key_creator = st.text_input("Creator ID*", placeholder="manel")

        with col2:
            key_name = st.text_input("Nombre (opcional)", placeholder="Production Key")

        submitted = st.form_submit_button("🔑 Crear Key", type="primary", use_container_width=True)

        if submitted and key_creator:
            result = api_post("/auth/keys", {
                "creator_id": key_creator,
                "name": key_name
            })

            if result and result.get("api_key"):
                st.success("✅ API Key creada!")
                st.code(result["api_key"])
                st.warning("⚠️ Copia esta key ahora. No se mostrara de nuevo.")
            else:
                st.error("❌ Error al crear key")


# =============================================
# FOOTER
# =============================================
st.divider()
st.markdown(
    "<p style='text-align: center; color: #666;'>🤖 <b>Clonnect Creators</b> v1.0</p>",
    unsafe_allow_html=True
)
