const { chromium } = require('playwright');

// Mock data for all API endpoints - using actual Railway paths
const mockData = {
  '/dashboard/manel/overview': {
    creator_name: 'Manel',
    clone_active: true,
    metrics: {
      total_messages: 1247,
      total_followers: 856,
      leads: 34,
      customers: 12,
      high_intent_followers: 8,
      conversion_rate: 0.35
    }
  },
  '/payments/manel/revenue': {
    total_revenue: 4850,
    bot_attributed_revenue: 3200,
    period: '30d'
  },
  '/dm/conversations/manel': {
    conversations: [
      {
        follower_id: 'tg_carlos123',
        name: 'Carlos García',
        username: 'carlosgarcia',
        platform: 'telegram',
        last_contact: new Date(Date.now() - 3600000).toISOString(),
        total_messages: 24,
        purchase_intent: 0.72,
        is_lead: true,
        last_messages: [
          { role: 'user', content: 'Hola! Me interesa el curso de trading', timestamp: new Date(Date.now() - 7200000).toISOString() },
          { role: 'assistant', content: '¡Hola Carlos! Me alegra que te interese. El curso incluye 20h de vídeo y comunidad privada. ¿Te cuento más?', timestamp: new Date(Date.now() - 7100000).toISOString() }
        ]
      },
      {
        follower_id: 'ig_maria456',
        name: 'María López',
        username: 'marialopez_fit',
        platform: 'instagram',
        last_contact: new Date(Date.now() - 86400000).toISOString(),
        total_messages: 8,
        purchase_intent: 0.45,
        is_lead: true,
        last_messages: [
          { role: 'user', content: '¿Cuánto cuesta la mentoría?', timestamp: new Date(Date.now() - 90000000).toISOString() }
        ]
      },
      {
        follower_id: 'tg_pedro789',
        name: 'Pedro Martínez',
        username: 'pedrom',
        platform: 'telegram',
        last_contact: new Date(Date.now() - 172800000).toISOString(),
        total_messages: 45,
        purchase_intent: 0.88,
        is_lead: true,
        is_customer: false,
        last_messages: []
      },
      {
        follower_id: 'wa_ana321',
        name: 'Ana Ruiz',
        username: 'ana.ruiz',
        platform: 'whatsapp',
        last_contact: new Date(Date.now() - 259200000).toISOString(),
        total_messages: 12,
        purchase_intent: 0.95,
        is_customer: true,
        last_messages: []
      },
      {
        follower_id: 'ig_luis654',
        name: 'Luis Fernández',
        username: 'luisfer',
        platform: 'instagram',
        last_contact: new Date(Date.now() - 345600000).toISOString(),
        total_messages: 6,
        purchase_intent: 0.25,
        is_lead: true,
        last_messages: []
      }
    ]
  },
  '/creator/manel/products': {
    products: [
      { id: '1', name: 'Curso Trading Pro', description: '20h vídeo + comunidad + Q&A semanales', price: 297, currency: 'EUR', type: 'course', sales_count: 12, revenue: 3564, is_active: true, payment_link: 'https://pay.stripe.com/trading' },
      { id: '2', name: 'Mentoría 1:1', description: 'Sesiones personalizadas de coaching', price: 500, currency: 'EUR', type: 'service', sales_count: 3, revenue: 1500, is_active: true, payment_link: 'https://pay.stripe.com/mentoria' },
      { id: '3', name: 'Pack Plantillas Excel', description: 'Gestión de portafolio y análisis', price: 47, currency: 'EUR', type: 'template', sales_count: 8, revenue: 376, is_active: true, payment_link: 'https://gumroad.com/plantillas' }
    ]
  },
  '/payments/manel/purchases': {
    purchases: [
      { id: '1', product_name: 'Curso Trading Pro', amount: 297, currency: 'EUR', platform: 'stripe', created_at: new Date(Date.now() - 86400000).toISOString(), bot_attributed: true },
      { id: '2', product_name: 'Mentoría 1:1', amount: 500, currency: 'EUR', platform: 'stripe', created_at: new Date(Date.now() - 172800000).toISOString(), bot_attributed: true },
      { id: '3', product_name: 'Pack Plantillas', amount: 47, currency: 'EUR', platform: 'gumroad', created_at: new Date(Date.now() - 259200000).toISOString(), bot_attributed: false }
    ]
  },
  '/nurturing/manel/sequences': {
    sequences: [
      { type: 'abandoned', is_active: true, enrolled_count: 5, sent_count: 23, steps: [{ delay_hours: 1, message: 'Ey! Vi que estabas interesado...' }, { delay_hours: 24, message: 'Hola de nuevo!' }] },
      { type: 'interest_cold', is_active: true, enrolled_count: 12, sent_count: 45, steps: [{ delay_hours: 24, message: 'Hey! Vi que te interesó...' }] },
      { type: 're_engagement', is_active: false, enrolled_count: 0, sent_count: 8, steps: [] },
      { type: 'post_purchase', is_active: true, enrolled_count: 3, sent_count: 18, steps: [{ delay_hours: 24, message: 'Gracias por confiar!' }] }
    ]
  },
  '/nurturing/manel/stats': {
    total: 94, pending: 20, sent: 74, cancelled: 0
  },
  '/creator/config/manel': {
    clone_name: 'Manel',
    clone_tone: 'friendly',
    clone_vocabulary: '- Tutea siempre al usuario\n- Usa emojis (1-2 por mensaje)\n- Sé cercano y conversacional\n- Responde como un amigo de confianza\n- Muestra empatía y comprensión',
    clone_active: true
  },
  '/connections/manel': {
    telegram: { connected: true, masked_token: '123***789' },
    instagram: { connected: false },
    whatsapp: { connected: false },
    stripe: { connected: true },
    paypal: { connected: false },
    google: { connected: false }
  },
  '/creator/config/manel/knowledge': {
    items: [],
    faqs: [
      { id: '1', question: '¿Cuánto cuesta el curso?', answer: 'El Curso Trading Pro tiene un precio de 297€ con acceso de por vida.' },
      { id: '2', question: '¿Qué incluye?', answer: '20h de vídeo, comunidad Telegram, Q&A semanales y plantillas Excel.' },
      { id: '3', question: '¿Hay garantía?', answer: 'Sí, 30 días de garantía de devolución sin preguntas.' }
    ],
    about: {
      bio: 'Trader profesional desde 2018, especializado en criptomonedas.',
      specialties: ['Trading', 'Criptomonedas', 'Análisis técnico'],
      experience: '6 años',
      target_audience: 'Personas que quieren aprender a invertir'
    }
  },
  '/dm/conversations/manel/archived': []
};

async function takeScreenshots() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: '/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome'
  });

  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2
  });

  const page = await context.newPage();

  // Intercept Railway.app API calls
  await page.route('**/web-production-9f69.up.railway.app/**', async (route) => {
    const url = route.request().url();
    console.log('Intercepting Railway:', url);

    // Extract the path part after domain
    let path = '';
    try {
      const urlObj = new URL(url);
      path = urlObj.pathname;
    } catch (e) {
      path = url;
    }

    // Find matching mock data
    let responseData = null;
    for (const [pattern, data] of Object.entries(mockData)) {
      if (path.includes(pattern) || path === pattern) {
        responseData = data;
        break;
      }
    }

    if (responseData) {
      console.log('  -> Returning mock for:', path);
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(responseData)
      });
    } else {
      console.log('  -> No mock for:', path, '- returning empty');
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({})
      });
    }
  });

  const routes = [
    { path: '/dashboard', name: '01-dashboard' },
    { path: '/inbox', name: '02-inbox' },
    { path: '/leads', name: '03-leads' },
    { path: '/nurturing', name: '04-nurturing' },
    { path: '/products', name: '05-products' },
    { path: '/settings', name: '06-settings-personality' },
    { path: '/settings?tab=connections', name: '07-settings-connections' },
    { path: '/settings?tab=knowledge', name: '08-settings-knowledge' },
  ];

  for (const route of routes) {
    console.log(`Taking screenshot of ${route.path}...`);
    await page.goto(`http://localhost:8080${route.path}`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(2000); // Wait for animations

    await page.screenshot({
      path: `/home/user/CLONNECT/screenshots/${route.name}.png`,
      fullPage: false
    });
    console.log(`  Saved: ${route.name}.png`);
  }

  await browser.close();
  console.log('\nDone! All screenshots with mock data saved.');
}

takeScreenshots().catch(console.error);
