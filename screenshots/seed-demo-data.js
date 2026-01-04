// Seed script to create demo data for screenshots
const API_URL = 'http://localhost:8000';

async function seedData() {
  console.log('Seeding demo data...');

  // Create products
  const products = [
    {
      name: 'Curso Trading Pro',
      description: '20h de vídeo, comunidad Telegram, Q&A semanales, plantillas, acceso de por vida',
      price: 297,
      currency: 'EUR',
      payment_link: 'https://pay.stripe.com/trading-pro',
      is_active: true
    },
    {
      name: 'Mentoría 1:1',
      description: 'Sesiones personalizadas de coaching en trading',
      price: 500,
      currency: 'EUR',
      payment_link: 'https://pay.stripe.com/mentoria',
      is_active: true
    },
    {
      name: 'Pack Plantillas Excel',
      description: 'Plantillas para gestión de portafolio y análisis técnico',
      price: 47,
      currency: 'EUR',
      payment_link: 'https://gumroad.com/plantillas',
      is_active: true
    }
  ];

  for (const product of products) {
    try {
      const res = await fetch(`${API_URL}/api/products`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(product)
      });
      console.log(`  Product: ${product.name} - ${res.ok ? 'OK' : 'FAIL'}`);
    } catch (e) {
      console.log(`  Product: ${product.name} - ERROR: ${e.message}`);
    }
  }

  // Create followers/conversations
  const followers = [
    { follower_id: 'tg_carlos123', name: 'Carlos García', platform: 'telegram', purchase_intent: 0.72 },
    { follower_id: 'ig_maria456', name: 'María López', platform: 'instagram', purchase_intent: 0.45 },
    { follower_id: 'tg_pedro789', name: 'Pedro Martínez', platform: 'telegram', purchase_intent: 0.88 },
    { follower_id: 'wa_ana321', name: 'Ana Ruiz', platform: 'whatsapp', purchase_intent: 0.15 },
    { follower_id: 'ig_luis654', name: 'Luis Fernández', platform: 'instagram', purchase_intent: 0.62 },
  ];

  for (const follower of followers) {
    try {
      // Try creating via leads endpoint
      const res = await fetch(`${API_URL}/api/leads`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: follower.name,
          platform: follower.platform,
          follower_id: follower.follower_id
        })
      });
      console.log(`  Lead: ${follower.name} - ${res.ok ? 'OK' : 'FAIL'}`);
    } catch (e) {
      console.log(`  Lead: ${follower.name} - ERROR: ${e.message}`);
    }
  }

  // Update creator config
  try {
    const configRes = await fetch(`${API_URL}/api/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        clone_name: 'Manel',
        clone_tone: 'friendly',
        clone_vocabulary: '- Tutea siempre al usuario\n- Usa emojis (1-2 por mensaje)\n- Sé cercano y conversacional',
        clone_active: true
      })
    });
    console.log(`  Config: ${configRes.ok ? 'OK' : 'FAIL'}`);
  } catch (e) {
    console.log(`  Config: ERROR - ${e.message}`);
  }

  console.log('\nDone seeding!');
}

seedData().catch(console.error);
