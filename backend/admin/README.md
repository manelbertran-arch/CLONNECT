# Clonnect Admin Dashboard

Panel de administración para Clonnect Creators.

## Ejecución Local

```bash
# Desde la raíz del proyecto
streamlit run admin/dashboard.py --server.port 8501

# O usando el script
./scripts/start_dashboard.sh
```

## Variables de Entorno

- `CLONNECT_ADMIN_KEY`: Clave de acceso al panel (default: `admin123`)
- `DASHBOARD_PORT`: Puerto del dashboard (default: `8501`)

## Páginas

1. **Dashboard**: Métricas generales, leads calientes, actividad reciente
2. **Conversaciones**: Historial de chats por seguidor
3. **Seguidores**: Lista y filtros de leads
4. **Escalaciones**: Conversaciones que necesitan atención humana
5. **Configuración**: Personalidad del bot, tokens, etc.
6. **Productos**: CRUD de productos

## Deploy en Railway

Para correr el dashboard en Railway, crea un servicio separado con:

```
Start Command: streamlit run admin/dashboard.py --server.port $PORT --server.address 0.0.0.0 --server.headless true
```
