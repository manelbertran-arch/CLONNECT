# Clonnect Telegram Bot Setup

Guía completa para configurar y ejecutar el bot de Telegram para testing del sistema de DM de Clonnect.

## Tabla de Contenidos

1. [Crear Bot con BotFather](#1-crear-bot-con-botfather)
2. [Configurar Variables de Entorno](#2-configurar-variables-de-entorno)
3. [Instalar Dependencias](#3-instalar-dependencias)
4. [Ejecutar en Local (Polling)](#4-ejecutar-en-local-polling)
5. [Ejecutar en Producción (Webhook)](#5-ejecutar-en-producción-webhook)
6. [Probar el Sistema](#6-probar-el-sistema)
7. [API Endpoints](#7-api-endpoints)
8. [Dashboard](#8-dashboard)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Crear Bot con BotFather

1. Abre Telegram y busca `@BotFather`

2. Envía el comando `/newbot`

3. Sigue las instrucciones:
   - Nombre del bot: `Clonnect Test Bot` (o el que prefieras)
   - Username del bot: `clonnect_test_bot` (debe terminar en `_bot`)

4. BotFather te dará un token como:
   ```
   1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   ```

5. Guarda este token, lo necesitarás en el siguiente paso.

### Comandos Opcionales en BotFather

```
/setdescription - Añadir descripción al bot
/setabouttext - Texto "About" del bot
/setuserpic - Añadir foto de perfil
/setcommands - Definir comandos disponibles
```

Para definir comandos, usa:
```
start - Iniciar conversación
help - Ver ayuda
status - Ver estado del bot
```

---

## 2. Configurar Variables de Entorno

### Opción A: Archivo .env

Copia el archivo de ejemplo y edítalo:

```bash
cp .env.example .env
```

Edita `.env`:

```bash
# Telegram Bot
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz

# Webhook URL (solo para producción)
TELEGRAM_WEBHOOK_URL=https://tu-dominio.com/webhook/telegram

# OpenAI (para respuestas inteligentes)
OPENAI_API_KEY=sk-tu-api-key
```

### Opción B: Variables de Entorno Directas

```bash
export TELEGRAM_BOT_TOKEN="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
export OPENAI_API_KEY="sk-tu-api-key"
```

---

## 3. Instalar Dependencias

```bash
# Crear entorno virtual (recomendado)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o
venv\Scripts\activate  # Windows

# Instalar dependencias
pip install python-telegram-bot>=20.0
pip install openai
pip install fastapi uvicorn
pip install streamlit requests

# O instalar todas las dependencias del proyecto
pip install -r requirements.txt
```

### requirements.txt (añadir si no existe)

```
python-telegram-bot>=20.0
openai>=1.0.0
fastapi>=0.100.0
uvicorn>=0.23.0
streamlit>=1.28.0
requests>=2.31.0
```

---

## 4. Ejecutar en Local (Polling)

El modo **polling** es ideal para desarrollo local. El bot consulta continuamente a Telegram por nuevos mensajes.

### Método 1: Script Directo

```bash
python core/telegram_adapter.py --mode polling
```

Con opciones:
```bash
python core/telegram_adapter.py --mode polling --creator-id demo-creator --log-level DEBUG
```

### Método 2: Como Módulo

```python
import asyncio
from core.telegram_adapter import run_polling

asyncio.run(run_polling("demo-creator"))
```

### Verificar que Funciona

1. Abre Telegram
2. Busca tu bot por su username
3. Envía `/start`
4. El bot debería responder

---

## 5. Ejecutar en Producción (Webhook)

El modo **webhook** es para producción. Telegram envía actualizaciones directamente a tu servidor.

### Paso 1: Iniciar la API

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

### Paso 2: Configurar el Webhook en Telegram

Tu servidor debe ser accesible públicamente con HTTPS. Puedes usar:
- Railway, Render, Heroku (hosting)
- ngrok (para testing local)

Configura el webhook:

```bash
# Usando curl
curl -X POST "https://api.telegram.org/bot<TU_TOKEN>/setWebhook" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://tu-dominio.com/webhook/telegram"}'
```

O con Python:
```python
import requests

token = "TU_TOKEN"
webhook_url = "https://tu-dominio.com/webhook/telegram"

response = requests.post(
    f"https://api.telegram.org/bot{token}/setWebhook",
    json={"url": webhook_url}
)
print(response.json())
```

### Paso 3: Verificar Webhook

```bash
curl "https://api.telegram.org/bot<TU_TOKEN>/getWebhookInfo"
```

### Usar ngrok para Testing Local

```bash
# Instalar ngrok
# https://ngrok.com/download

# Iniciar túnel
ngrok http 8000

# Copiar la URL HTTPS (ej: https://abc123.ngrok.io)
# Configurar webhook con esa URL
```

---

## 6. Probar el Sistema

### Test con API Directamente

```bash
# Health check
curl http://localhost:8000/health

# Estado del bot
curl http://localhost:8000/telegram/status

# Procesar mensaje manualmente
curl -X POST http://localhost:8000/dm/process \
     -H "Content-Type: application/json" \
     -d '{
       "creator_id": "demo-creator",
       "follower_id": "test_user_123",
       "message": "Hola, me interesa el curso",
       "platform": "telegram"
     }'
```

### Test con Dashboard Streamlit

```bash
# Iniciar dashboard
streamlit run dashboard/app.py --server.port 8501
```

Abre `http://localhost:8501` y usa la pestaña "Telegram Test".

### Test con Pytest

```bash
# Ejecutar todos los tests de Telegram
pytest tests/test_telegram.py -v

# Ejecutar test específico
pytest tests/test_telegram.py::TestIntentClassifier -v
```

### Mensajes de Prueba por Intent

| Intent | Mensaje de Prueba |
|--------|-------------------|
| GREETING | "Hola!" |
| INTEREST_SOFT | "Me interesa saber más" |
| INTEREST_STRONG | "Quiero comprar el curso" |
| OBJECTION | "Es muy caro para mí" |
| QUESTION_PRODUCT | "¿Qué incluye el curso?" |
| QUESTION_GENERAL | "¿Quién eres?" |
| COMPLAINT | "Tengo un problema" |
| THANKS | "Muchas gracias" |
| GOODBYE | "Adiós" |
| SPAM | "Gana dinero fácil" |

---

## 7. API Endpoints

### Telegram Endpoints

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/webhook/telegram` | Webhook para recibir updates de Telegram |
| GET | `/telegram/status` | Estado del bot (mensajes, errores) |
| POST | `/telegram/test` | Enviar mensaje de prueba |

### DM Endpoints

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/dm/process` | Procesar mensaje DM |
| GET | `/creator/config/{id}` | Obtener config del creador |
| POST | `/creator/config/{id}` | Actualizar config |
| GET | `/creator/{id}/products` | Listar productos |
| POST | `/creator/{id}/products` | Crear producto |

### Ejemplo de Respuesta `/dm/process`

```json
{
  "status": "ok",
  "response": "¡Hola! Me alegra que me escribas. ¿En qué puedo ayudarte?",
  "intent": "GREETING",
  "confidence": 0.85,
  "products_mentioned": [],
  "escalate": false,
  "follower_profile": {
    "follower_id": "tg_123456",
    "conversation_count": 1,
    "purchase_intent_score": 0.02
  }
}
```

---

## 8. Dashboard

### Iniciar Dashboard

```bash
streamlit run dashboard/app.py --server.port 8501
```

### Funcionalidades

1. **Inicio**: Estado del sistema, métricas, actividad reciente
2. **Telegram Test**:
   - Estado del bot (conectado/desconectado)
   - Últimos 10 mensajes recibidos
   - Respuestas enviadas
   - Test manual de DMs
3. **Analytics**: Queries trending, costos
4. **Configuración**: Configurar creador, productos

---

## 9. Troubleshooting

### El bot no responde

1. Verifica el token:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/getMe"
   ```

2. Verifica que el proceso esté corriendo:
   ```bash
   ps aux | grep telegram
   ```

3. Revisa los logs:
   ```bash
   python core/telegram_adapter.py --mode polling --log-level DEBUG
   ```

### Error "Conflict: terminated by other getUpdates request"

Esto ocurre cuando hay múltiples instancias del bot corriendo o el webhook está activo.

```bash
# Eliminar webhook
curl "https://api.telegram.org/bot<TOKEN>/deleteWebhook"

# Reiniciar bot
python core/telegram_adapter.py --mode polling
```

### OpenAI API Error

Si no tienes `OPENAI_API_KEY` configurada, el bot usará respuestas predefinidas (templates) en lugar de generación con LLM.

### Webhook no recibe updates

1. Verifica que la URL sea HTTPS
2. Verifica que el certificado SSL sea válido
3. Comprueba el webhook info:
   ```bash
   curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
   ```

### Tests fallan

```bash
# Instalar pytest
pip install pytest pytest-asyncio

# Ejecutar con más detalle
pytest tests/test_telegram.py -v --tb=long
```

---

## Arquitectura

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Telegram   │────▶│  Webhook/    │────▶│  DM Agent    │
│   Usuario    │     │  Polling     │     │  Process     │
└──────────────┘     └──────────────┘     └──────────────┘
                            │                    │
                            ▼                    ▼
                     ┌──────────────┐     ┌──────────────┐
                     │  telegram_   │     │  Intent      │
                     │  adapter.py  │     │  Classifier  │
                     └──────────────┘     └──────────────┘
                            │                    │
                            ▼                    ▼
                     ┌──────────────┐     ┌──────────────┐
                     │  Respuesta   │◀────│  Products &  │
                     │  a Usuario   │     │  Creator     │
                     └──────────────┘     └──────────────┘
```

---

## Soporte

- **Documentación**: Ver README.md
- **Issues**: https://github.com/manelbertran-arch/clonnect-memory-engine/issues
- **Tests**: `pytest tests/test_telegram.py -v`
