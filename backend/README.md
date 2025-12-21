# Clonnect Creators

🤖 **Tu clon de IA para responder DMs de Instagram**

Clonnect Creators es una plataforma que permite a creadores de contenido automatizar sus DMs de Instagram con un "clon" de IA que:

- ✅ Responde con tu tono y estilo personal
- ✅ Recuerda cada seguidor y sus conversaciones anteriores
- ✅ Detecta intencion de compra automaticamente
- ✅ Guia hacia la venta de tus productos
- ✅ Escala a ti cuando es necesario
- ✅ Soporta multiples idiomas
- ✅ Integra pagos (Stripe, Hotmart) y calendarios (Calendly, Cal.com)

## 🚀 Quick Start (Local)

### 1. Clonar el repositorio

```bash
git clone https://github.com/manelbertran-arch/Clonnect-creators.git
cd Clonnect-creators
```

### 2. Crear entorno virtual

```bash
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# o: venv\Scripts\activate  # Windows
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus claves
```

**Variables requeridas:**
```env
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_your_key_here
CLONNECT_ADMIN_KEY=your_secure_admin_key_here
```

### 5. Ejecutar

```bash
# API
uvicorn api.main:app --reload --port 8000

# Dashboard (en otra terminal)
streamlit run dashboard/app.py --server.port 8501

# Admin Panel (en otra terminal)
streamlit run dashboard/admin.py --server.port 8502
```

### 6. Acceder

- **API:** http://localhost:8000
- **Dashboard:** http://localhost:8501
- **Admin:** http://localhost:8502
- **Docs:** http://localhost:8000/docs
- **Metrics:** http://localhost:8000/metrics

---

## 🚀 Deploy

### Railway

1. Fork este repositorio
2. Conecta con Railway
3. Configura variables de entorno:
   - `LLM_PROVIDER=groq`
   - `GROQ_API_KEY=tu_key`
   - `CLONNECT_ADMIN_KEY=tu_admin_key`
4. Deploy automatico desde `main`

### Render

1. Fork este repositorio
2. Crea nuevo Web Service en Render
3. Conecta el repositorio
4. Render detectara `render.yaml` automaticamente
5. Configura variables de entorno secretas

### Verificar antes de deploy

```bash
PYTHONPATH=. python3 scripts/deploy_check.py
```

---

## 🐳 Docker

```bash
docker-compose up -d
```

---

## 📱 Conectar Instagram

1. Crea una Meta App en [developers.facebook.com](https://developers.facebook.com)
2. Configura Instagram Graph API
3. Obtén el Access Token, Page ID y User ID
4. Añádelos a tu `.env`
5. Configura el Webhook apuntando a `https://tu-dominio.com/webhook/instagram`

---

## 🎯 Variables de Entorno Requeridas

| Variable | Descripcion | Requerida |
|----------|-------------|-----------|
| `LLM_PROVIDER` | Proveedor LLM (groq/openai/anthropic) | Si |
| `GROQ_API_KEY` | API key de Groq | Si (si provider=groq) |
| `OPENAI_API_KEY` | API key de OpenAI | Si (si provider=openai) |
| `CLONNECT_ADMIN_KEY` | Clave de admin | Si |
| `INSTAGRAM_ACCESS_TOKEN` | Token de Instagram | Para Instagram |
| `STRIPE_SECRET_KEY` | Clave Stripe | Para pagos |
| `TELEGRAM_ALERTS_ENABLED` | Habilitar alertas | Opcional |

Ver `.env.example` para lista completa.

---

## 🧪 Testing

```bash
# Tests completos
PYTHONPATH=. python3 scripts/lab_test_complete.py

# Verificar deploy
PYTHONPATH=. python3 scripts/deploy_check.py
```

---

## 📊 Endpoints Principales

### Health & Info
- `GET /` - Info de la API
- `GET /health` - Health check completo
- `GET /health/live` - Liveness probe
- `GET /health/ready` - Readiness probe
- `GET /metrics` - Prometheus metrics

### Autenticacion
- `POST /auth/keys` - Crear API key (admin)
- `GET /auth/keys` - Listar keys (admin)
- `DELETE /auth/keys/{prefix}` - Revocar key (admin)
- `GET /auth/verify` - Verificar key

### Bot Control
- `POST /bot/{id}/pause` - Pausar bot
- `POST /bot/{id}/resume` - Reanudar bot
- `GET /bot/{id}/status` - Estado del bot

### Admin
- `GET /admin/creators` - Listar todos los creadores
- `GET /admin/stats` - Estadisticas globales
- `GET /admin/conversations` - Todas las conversaciones
- `GET /admin/alerts` - Alertas recientes

### Creador
- `POST /creator/config` - Crear configuracion
- `GET /creator/config/{id}` - Obtener configuracion
- `PUT /creator/config/{id}` - Actualizar configuracion
- `GET /creator/list` - Listar creadores

### Productos
- `POST /creator/{id}/products` - Crear producto
- `GET /creator/{id}/products` - Listar productos
- `PUT /creator/{id}/products/{pid}` - Actualizar producto
- `DELETE /creator/{id}/products/{pid}` - Eliminar producto

### DMs
- `POST /dm/process` - Procesar DM manualmente
- `GET /dm/conversations/{id}` - Listar conversaciones
- `GET /dm/leads/{id}` - Obtener leads
- `GET /dm/metrics/{id}` - Metricas

### Webhooks
- `POST /webhook/instagram` - Instagram
- `POST /webhook/stripe` - Stripe
- `POST /webhook/hotmart` - Hotmart
- `POST /webhook/calendly` - Calendly
- `POST /webhook/calcom` - Cal.com

### GDPR
- `GET /gdpr/{cid}/export/{fid}` - Exportar datos
- `DELETE /gdpr/{cid}/delete/{fid}` - Borrar datos
- `POST /gdpr/{cid}/anonymize/{fid}` - Anonimizar

---

## 🏗️ Estructura del Proyecto

```
clonnect-creators/
├── api/
│   └── main.py              # API FastAPI
├── core/
│   ├── dm_agent.py          # Agente principal de DMs
│   ├── llm.py               # Cliente LLM (Groq/OpenAI)
│   ├── creator_config.py    # Configuracion creadores
│   ├── products.py          # Gestion de productos
│   ├── memory.py            # Memoria de seguidores
│   ├── auth.py              # Autenticacion API keys
│   ├── alerts.py            # Sistema de alertas
│   ├── metrics.py           # Metricas Prometheus
│   ├── cache.py             # Cache de respuestas
│   ├── payments.py          # Integracion Stripe/Hotmart
│   ├── calendar.py          # Integracion calendarios
│   ├── gdpr.py              # Cumplimiento GDPR
│   └── ...
├── dashboard/
│   ├── app.py               # Dashboard creadores
│   └── admin.py             # Panel admin
├── scripts/
│   ├── onboarding.py        # Wizard de onboarding
│   ├── backup.py            # Backup de datos
│   └── deploy_check.py      # Verificacion pre-deploy
├── docs/
│   ├── BETA_AGREEMENT.md    # Acuerdo beta
│   ├── ONBOARDING_CREADOR.md # Guia onboarding
│   └── CHECKLIST_INTERNO.md # Checklist interno
├── data/                    # Datos persistentes
├── requirements.txt
├── railway.json             # Config Railway
├── render.yaml              # Config Render
└── README.md
```

---

## 📄 Documentacion

- [Acuerdo Beta](docs/BETA_AGREEMENT.md) - Terminos para beta testers
- [Guia Onboarding](docs/ONBOARDING_CREADOR.md) - Guia para creadores
- [Checklist Interno](docs/CHECKLIST_INTERNO.md) - Proceso de alta

---

## 📞 Soporte

- Email: soporte@clonnect.com
- Telegram: @ClonnectSupport

---

## 📄 Licencia

Propietario - Clonnect © 2024
