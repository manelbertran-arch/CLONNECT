"""
Clonnect Creators - Admin Panel
Panel de administracion para supervisar TODOS los creadores
"""

import streamlit as st
import requests
import os
from datetime import datetime
import json

# Configuracion
st.set_page_config(
    page_title="Clonnect Admin",
    page_icon="🔐",
    layout="wide"
)

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")


# =============================================================================
# AUTHENTICATION
# =============================================================================
def check_admin_auth():
    """Verificar autenticacion de admin"""
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False
        st.session_state.admin_key = ""

    return st.session_state.admin_authenticated


def admin_login():
    """Mostrar pagina de login admin"""
    st.title("🔐 Clonnect Admin Panel")
    st.markdown("---")

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("### Acceso Administrador")
        st.markdown("Introduce la clave de administrador (CLONNECT_ADMIN_KEY)")

        admin_key = st.text_input(
            "Admin Key",
            type="password",
            placeholder="Introduce tu admin key..."
        )

        if st.button("🔓 Acceder", use_container_width=True):
            if admin_key:
                # Verificar con la API
                try:
                    response = requests.get(
                        f"{API_BASE_URL}/admin/stats",
                        headers={"X-API-Key": admin_key},
                        timeout=10
                    )

                    if response.status_code == 200:
                        st.session_state.admin_authenticated = True
                        st.session_state.admin_key = admin_key
                        st.success("Acceso concedido")
                        st.rerun()
                    elif response.status_code == 403:
                        st.error("Clave de admin incorrecta")
                    else:
                        st.error(f"Error: {response.status_code}")
                except requests.exceptions.ConnectionError:
                    st.error("No se puede conectar con la API")
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("Introduce la clave de admin")


def api_request(endpoint: str, method: str = "GET", data: dict = None):
    """Hacer request a la API con admin key"""
    headers = {"X-API-Key": st.session_state.admin_key}
    url = f"{API_BASE_URL}{endpoint}"

    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=30)
        elif method == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=30)
        else:
            return None

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 401:
            st.session_state.admin_authenticated = False
            st.rerun()
        else:
            st.error(f"Error API: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"Error conexion: {e}")
        return None


# =============================================================================
# MAIN PAGES
# =============================================================================
def page_overview():
    """Pagina principal con estadisticas globales"""
    st.title("📊 Vista General")

    # Obtener stats globales
    stats = api_request("/admin/stats")

    if not stats:
        st.warning("No se pudieron cargar las estadisticas")
        return

    stats = stats.get("stats", {})

    # Metricas principales
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("👥 Creadores", stats.get("total_creators", 0))
    with col2:
        active = stats.get("active_bots", 0)
        paused = stats.get("paused_bots", 0)
        st.metric("🟢 Bots Activos", active, delta=f"-{paused} pausados")
    with col3:
        st.metric("💬 Mensajes Totales", stats.get("total_messages", 0))
    with col4:
        hot = stats.get("hot_leads", 0)
        total = stats.get("total_leads", 0)
        st.metric("🔥 Leads Calientes", hot, delta=f"de {total} totales")

    st.markdown("---")

    # Lista de creadores
    st.subheader("👥 Creadores")

    creators_data = api_request("/admin/creators")

    if creators_data and creators_data.get("creators"):
        creators = creators_data["creators"]

        for creator in creators:
            with st.expander(
                f"{'🟢' if creator.get('is_active') else '🔴'} "
                f"{creator.get('name', 'Sin nombre')} (@{creator.get('instagram_handle', 'N/A')})",
                expanded=False
            ):
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    st.write(f"**ID:** `{creator.get('creator_id')}`")
                    st.write(f"**Mensajes:** {creator.get('total_messages', 0)}")

                with col2:
                    st.write(f"**Leads totales:** {creator.get('total_leads', 0)}")
                    st.write(f"**Leads calientes:** {creator.get('hot_leads', 0)}")

                with col3:
                    status = "Activo" if creator.get("is_active") else "Pausado"
                    st.write(f"**Estado:** {status}")
                    if not creator.get("is_active"):
                        st.write(f"**Razon:** {creator.get('pause_reason', 'N/A')}")

                with col4:
                    # Botones de control
                    creator_id = creator.get("creator_id")

                    if creator.get("is_active"):
                        if st.button(f"⏸️ Pausar", key=f"pause_{creator_id}"):
                            result = api_request(
                                f"/admin/creators/{creator_id}/pause",
                                method="POST",
                                data={"reason": "Pausado desde admin panel"}
                            )
                            if result:
                                st.success(f"Bot pausado para {creator_id}")
                                st.rerun()
                    else:
                        if st.button(f"▶️ Reanudar", key=f"resume_{creator_id}"):
                            result = api_request(
                                f"/admin/creators/{creator_id}/resume",
                                method="POST"
                            )
                            if result:
                                st.success(f"Bot reanudado para {creator_id}")
                                st.rerun()

                    # Link al dashboard del creador
                    st.markdown(f"[📊 Ver Dashboard](/dashboard?creator={creator_id})")
    else:
        st.info("No hay creadores registrados")


def page_conversations():
    """Pagina de todas las conversaciones"""
    st.title("💬 Todas las Conversaciones")

    # Filtros
    col1, col2 = st.columns(2)

    with col1:
        # Obtener lista de creadores para el filtro
        creators_data = api_request("/admin/creators")
        creator_options = ["Todos"]
        if creators_data:
            for c in creators_data.get("creators", []):
                creator_options.append(c.get("creator_id", ""))

        selected_creator = st.selectbox("Filtrar por creador", creator_options)

    with col2:
        limit = st.slider("Limite de conversaciones", 10, 200, 50)

    st.markdown("---")

    # Obtener conversaciones
    endpoint = f"/admin/conversations?limit={limit}"
    if selected_creator != "Todos":
        endpoint += f"&creator_id={selected_creator}"

    data = api_request(endpoint)

    if data and data.get("conversations"):
        conversations = data["conversations"]

        st.write(f"Mostrando {len(conversations)} de {data.get('total', 0)} conversaciones")

        for conv in conversations:
            creator_id = conv.get("creator_id", "N/A")
            follower_id = conv.get("follower_id", "N/A")
            username = conv.get("username", follower_id[:8])
            score = conv.get("purchase_intent_score", 0)
            total_msgs = conv.get("total_messages", 0)
            last_contact = conv.get("last_contact", "N/A")

            # Determinar color por score
            if score >= 0.7:
                indicator = "🔥"
            elif score >= 0.4:
                indicator = "🟡"
            else:
                indicator = "⚪"

            with st.expander(
                f"{indicator} [{creator_id}] {username} - Score: {score:.0%} | {total_msgs} msgs",
                expanded=False
            ):
                col1, col2 = st.columns(2)

                with col1:
                    st.write(f"**Creador:** {creator_id}")
                    st.write(f"**Follower ID:** `{follower_id}`")
                    st.write(f"**Ultimo contacto:** {last_contact[:19] if last_contact else 'N/A'}")

                with col2:
                    st.write(f"**Score:** {score:.0%}")
                    st.write(f"**Mensajes:** {total_msgs}")

                    interests = conv.get("interests", [])
                    if interests:
                        st.write(f"**Intereses:** {', '.join(interests[:3])}")

                # Historial de mensajes
                messages = conv.get("last_messages", [])
                if messages:
                    st.markdown("**Ultimos mensajes:**")
                    for msg in messages[-6:]:
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        if role == "user":
                            st.markdown(f"👤 `{content[:200]}`")
                        else:
                            st.markdown(f"🤖 _{content[:200]}_")
    else:
        st.info("No hay conversaciones")


def page_alerts():
    """Pagina de alertas del sistema"""
    st.title("🚨 Alertas del Sistema")

    data = api_request("/admin/alerts?limit=100")

    if data:
        telegram_enabled = data.get("telegram_enabled", False)

        if telegram_enabled:
            st.success("✅ Alertas de Telegram habilitadas")
        else:
            st.warning("⚠️ Alertas de Telegram deshabilitadas")

        st.markdown("---")

        alerts = data.get("alerts", [])

        if alerts:
            for alert in reversed(alerts):
                level = alert.get("level", "info")
                title = alert.get("title", "Alert")
                message = alert.get("message", "")
                timestamp = alert.get("timestamp", "")

                if level == "critical":
                    st.error(f"🚨 **{title}** ({timestamp[:19]})\n\n{message}")
                elif level == "error":
                    st.error(f"🔴 **{title}** ({timestamp[:19]})\n\n{message}")
                elif level == "warning":
                    st.warning(f"⚠️ **{title}** ({timestamp[:19]})\n\n{message}")
                else:
                    st.info(f"ℹ️ **{title}** ({timestamp[:19]})\n\n{message}")
        else:
            st.info("No hay alertas recientes registradas")

            st.markdown("""
            **Nota:** Las alertas se envian a Telegram en tiempo real.
            Este log local solo se guarda si esta configurado.

            Para configurar alertas:
            1. Crear un bot con @BotFather
            2. Configurar las variables en .env:
               - TELEGRAM_ALERTS_ENABLED=true
               - TELEGRAM_ALERTS_BOT_TOKEN=tu_token
               - TELEGRAM_ALERTS_CHAT_ID=tu_chat_id
            """)


def page_system():
    """Pagina de estado del sistema"""
    st.title("⚙️ Estado del Sistema")

    # Health check
    try:
        response = requests.get(f"{API_BASE_URL}/health", timeout=10)
        health = response.json()

        status = health.get("status", "unknown")

        if status == "healthy":
            st.success(f"✅ Sistema Saludable")
        elif status == "degraded":
            st.warning(f"⚠️ Sistema Degradado")
        else:
            st.error(f"🔴 Sistema No Saludable")

        st.json(health)

    except Exception as e:
        st.error(f"No se puede conectar con la API: {e}")

    st.markdown("---")

    # Metricas Prometheus
    st.subheader("📊 Metricas Prometheus")

    try:
        response = requests.get(f"{API_BASE_URL}/metrics", timeout=10)
        if response.status_code == 200:
            st.code(response.text[:2000], language="text")
            st.caption("Mostrando primeras 2000 caracteres de metricas")
        else:
            st.warning("No se pudieron obtener las metricas")
    except:
        st.warning("Endpoint /metrics no disponible")


def page_api_keys():
    """Pagina de gestion de API keys"""
    st.title("🔑 API Keys")

    # Listar todas las keys
    data = api_request("/auth/keys")

    if data and data.get("keys"):
        keys = data["keys"]

        st.write(f"**Total keys:** {len(keys)}")
        st.markdown("---")

        for key in keys:
            prefix = key.get("key_prefix", "???")
            creator_id = key.get("creator_id", "N/A")
            name = key.get("name", "Sin nombre")
            created = key.get("created_at", "N/A")
            active = key.get("is_active", True)

            status_icon = "🟢" if active else "🔴"

            with st.expander(f"{status_icon} {prefix}... - {creator_id}", expanded=False):
                col1, col2 = st.columns(2)

                with col1:
                    st.write(f"**Prefijo:** `{prefix}`")
                    st.write(f"**Creador:** {creator_id}")
                    st.write(f"**Nombre:** {name}")

                with col2:
                    st.write(f"**Creada:** {created[:19] if created else 'N/A'}")
                    st.write(f"**Activa:** {'Si' if active else 'No'}")

                    if active:
                        if st.button(f"🗑️ Revocar", key=f"revoke_{prefix}"):
                            result = api_request(
                                f"/auth/keys/{prefix}",
                                method="DELETE"
                            )
                            if result:
                                st.success("Key revocada")
                                st.rerun()
    else:
        st.info("No hay API keys registradas")

    st.markdown("---")

    # Crear nueva key
    st.subheader("➕ Crear Nueva API Key")

    with st.form("create_key"):
        new_creator_id = st.text_input("Creator ID")
        new_key_name = st.text_input("Nombre (opcional)")

        if st.form_submit_button("Crear Key"):
            if new_creator_id:
                result = api_request(
                    "/auth/keys",
                    method="POST",
                    data={
                        "creator_id": new_creator_id,
                        "name": new_key_name or None
                    }
                )

                if result and result.get("api_key"):
                    st.success("Key creada exitosamente")
                    st.code(result["api_key"], language="text")
                    st.warning("⚠️ Guarda esta key, no se mostrara de nuevo")
            else:
                st.error("Creator ID requerido")


# =============================================================================
# MAIN
# =============================================================================
def main():
    """Main app"""

    if not check_admin_auth():
        admin_login()
        return

    # Sidebar
    with st.sidebar:
        st.title("🔐 Admin Panel")
        st.caption(f"API: {API_BASE_URL}")

        st.markdown("---")

        page = st.radio(
            "Navegacion",
            ["📊 Vista General", "💬 Conversaciones", "🚨 Alertas", "⚙️ Sistema", "🔑 API Keys"],
            label_visibility="collapsed"
        )

        st.markdown("---")

        if st.button("🚪 Cerrar Sesion", use_container_width=True):
            st.session_state.admin_authenticated = False
            st.session_state.admin_key = ""
            st.rerun()

    # Paginas
    if page == "📊 Vista General":
        page_overview()
    elif page == "💬 Conversaciones":
        page_conversations()
    elif page == "🚨 Alertas":
        page_alerts()
    elif page == "⚙️ Sistema":
        page_system()
    elif page == "🔑 API Keys":
        page_api_keys()


if __name__ == "__main__":
    main()
