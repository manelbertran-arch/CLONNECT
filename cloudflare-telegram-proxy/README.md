# Cloudflare Telegram Proxy

Este Cloudflare Worker actúa como proxy para la API de Telegram Bot.
Útil cuando tu proveedor de hosting (ej: Railway) bloquea conexiones a telegram.org.

## Despliegue

### 1. Instalar Wrangler CLI

```bash
npm install -g wrangler
```

### 2. Autenticarse en Cloudflare

```bash
wrangler login
```

### 3. Crear un secret seguro

Genera un secret aleatorio (puedes usar este comando):

```bash
openssl rand -hex 32
```

### 4. Configurar el secret en Cloudflare

```bash
cd cloudflare-telegram-proxy
npx wrangler secret put PROXY_SECRET
# Pega el secret generado cuando te lo pida
```

### 5. Desplegar el Worker

```bash
npx wrangler deploy
```

Esto te dará una URL como: `https://clonnect-telegram-proxy.<tu-cuenta>.workers.dev`

## Configurar Railway

Añade estas variables de entorno en Railway:

| Variable | Valor |
|----------|-------|
| `TELEGRAM_PROXY_URL` | `https://clonnect-telegram-proxy.<tu-cuenta>.workers.dev` |
| `TELEGRAM_PROXY_SECRET` | El mismo secret que configuraste en Cloudflare |

## Verificar

Después de desplegar y configurar:

1. Visita `/telegram/status` en tu API
2. Debería mostrar `"send_mode": "proxy"` y `"proxy_configured": true`
3. Envía un mensaje al bot de Telegram para probar

## Límites (Plan Gratuito)

- 100,000 requests/día
- 10ms CPU time por request
- Más que suficiente para un bot de Telegram

## Seguridad

- El secret evita que terceros usen tu proxy
- El bot token nunca se almacena en Cloudflare, solo se pasa en cada request
- HTTPS end-to-end
