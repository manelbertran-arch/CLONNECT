/**
 * Cloudflare Worker - Telegram API Proxy
 *
 * This worker acts as a proxy to the Telegram Bot API.
 * Use this when your hosting provider (e.g., Railway) blocks connections to telegram.org.
 *
 * Deploy: npx wrangler deploy
 * Set secret: npx wrangler secret put PROXY_SECRET
 */

export default {
  async fetch(request, env) {
    // CORS headers for preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type, X-Telegram-Proxy-Secret',
        }
      });
    }

    // Only allow POST
    if (request.method !== 'POST') {
      return new Response(JSON.stringify({ error: 'Method not allowed' }), {
        status: 405,
        headers: { 'Content-Type': 'application/json' }
      });
    }

    // Verify secret (for security) - only if PROXY_SECRET is configured
    const authHeader = request.headers.get('X-Telegram-Proxy-Secret');
    if (env.PROXY_SECRET && authHeader !== env.PROXY_SECRET) {
      return new Response(JSON.stringify({ error: 'Unauthorized' }), {
        status: 401,
        headers: { 'Content-Type': 'application/json' }
      });
    }

    try {
      const body = await request.json();
      const { bot_token, method, params } = body;

      if (!bot_token || !method) {
        return new Response(JSON.stringify({ error: 'Missing bot_token or method' }), {
          status: 400,
          headers: { 'Content-Type': 'application/json' }
        });
      }

      // Call Telegram API
      const telegramUrl = `https://api.telegram.org/bot${bot_token}/${method}`;
      const response = await fetch(telegramUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params || {})
      });

      const data = await response.json();

      return new Response(JSON.stringify(data), {
        status: response.status,
        headers: {
          'Content-Type': 'application/json',
          'Access-Control-Allow-Origin': '*'
        }
      });

    } catch (error) {
      return new Response(JSON.stringify({
        error: error.message,
        ok: false
      }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' }
      });
    }
  }
};
