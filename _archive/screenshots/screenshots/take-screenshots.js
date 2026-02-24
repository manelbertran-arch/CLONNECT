const { chromium } = require('playwright');

async function takeScreenshots() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: '/root/.cache/ms-playwright/chromium-1194/chrome-linux/chrome'
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2, // Retina quality
  });

  const page = await context.newPage();

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

    // Wait a bit for animations to settle
    await page.waitForTimeout(1500);

    await page.screenshot({
      path: `/home/user/CLONNECT/screenshots/${route.name}.png`,
      fullPage: false,
    });

    console.log(`  Saved: ${route.name}.png`);
  }

  await browser.close();
  console.log('\nDone! All screenshots saved to /home/user/CLONNECT/screenshots/');
}

takeScreenshots().catch(console.error);
