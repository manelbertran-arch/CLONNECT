# Deploy Bot Telegram a Render

Guía para deployar el bot de Telegram de Clonnect en Render.com

## Prerequisitos

- Cuenta en [Render](https://render.com) (login con GitHub)
- Token de bot de Telegram (de @BotFather)

## Pasos de Deploy

### 1. Acceder a Render

1. Ve a https://render.com
2. Login con tu cuenta de GitHub

### 2. Crear Background Worker

1. Click en **"New +"** → **"Background Worker"**
2. Conecta tu repositorio GitHub si no lo has hecho

### 3. Configurar el servicio

| Campo | Valor |
|-------|-------|
| **Name** | `clonnect-telegram-bot` |
| **Repository** | `manelbertran-arch/clonnect-creators` |
| **Branch** | `main` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `PYTHONPATH=. python core/telegram_adapter.py --mode polling` |

### 4. Configurar Variables de Entorno

En la sección **Environment Variables**, añade:

| Key | Value |
|-----|-------|
| `TELEGRAM_BOT_TOKEN` | `8447917197:AAGkRBqus2uEQ4cLwVoi6GICSYgoTaYDyYA` |
| `OPENAI_API_KEY` | *(tu API key de OpenAI, opcional)* |

### 5. Deploy

1. Click en **"Create Background Worker"**
2. Espera ~2-3 minutos mientras Render:
   - Clona el repositorio
   - Instala dependencias
   - Arranca el bot

### 6. Verificar logs

En el dashboard del servicio, click en **"Logs"**.

Deberías ver:
```
Starting Telegram bot in polling mode (creator: demo-creator)
DM Agent initialized for creator: demo-creator
Bot @clonnect_test_bot is running (polling)
```

## Verificación

1. Abre Telegram
2. Busca tu bot: `@clonnect_test_bot`
3. Envía: `Hola`
4. El bot debe responder con un mensaje personalizado

## Mensajes de Prueba

| Mensaje | Intent Esperado |
|---------|-----------------|
| "Hola" | GREETING |
| "Me interesa el curso" | INTEREST_SOFT |
| "Quiero comprar" | INTEREST_STRONG |
| "Es muy caro" | OBJECTION |
| "¿Qué incluye?" | QUESTION_PRODUCT |
| "Gracias" | THANKS |

## Troubleshooting

### El bot no responde

1. Verifica en Render Logs que no hay errores
2. Verifica que `TELEGRAM_BOT_TOKEN` está configurado
3. Reinicia el servicio: Dashboard → Manual Deploy → Deploy

### Error "Token invalid"

1. Genera nuevo token en @BotFather: `/token`
2. Actualiza la variable en Render: Dashboard → Environment → Edit

### Build falla

1. Verifica que `requirements.txt` existe
2. Revisa los logs de build para ver el error específico

## Comandos del Bot

| Comando | Descripción |
|---------|-------------|
| `/start` | Inicia conversación |
| `/help` | Muestra ayuda |
| `/status` | Estado del bot |

## Costos

Render ofrece plan gratuito con limitaciones:
- Background workers: Requiere plan de pago ($7/mes)
- Alternativa gratuita: Railway ($5 crédito gratis/mes)

## Links

- [Render Dashboard](https://dashboard.render.com)
- [Render Docs - Background Workers](https://render.com/docs/background-workers)
- [Telegram BotFather](https://t.me/BotFather)
