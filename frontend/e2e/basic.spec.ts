import { test, expect } from '@playwright/test';

test.describe('CLONNECT - Basic E2E Tests', () => {
  test('homepage loads correctly', async ({ page }) => {
    await page.goto('/');

    // Should have CLONNECT branding
    await expect(page).toHaveTitle(/Clonnect|CLONNECT/i);
  });

  test('login page loads', async ({ page }) => {
    await page.goto('/login');

    // Should show login form
    const form = page.locator('form');
    await expect(form).toBeVisible();

    // Should have email and password inputs
    await expect(page.locator('input[type="email"], input[name="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
  });

  test('signup page loads', async ({ page }) => {
    await page.goto('/signup');

    // Should show signup form
    const form = page.locator('form');
    await expect(form).toBeVisible();
  });

  test('navigation works', async ({ page }) => {
    await page.goto('/');

    // Try navigating to login
    const loginLink = page.locator('a[href="/login"], button:has-text("Login"), button:has-text("Iniciar")');
    if (await loginLink.count() > 0) {
      await loginLink.first().click();
      await expect(page).toHaveURL(/login/);
    }
  });
});

test.describe('CLONNECT - Dashboard Tests (requires auth)', () => {
  test.skip('dashboard loads after login', async ({ page }) => {
    // This test requires valid credentials
    // Skip in CI, run manually with valid test credentials
    await page.goto('/login');

    // Fill login form
    await page.fill('input[type="email"], input[name="email"]', process.env.TEST_EMAIL || 'test@example.com');
    await page.fill('input[type="password"]', process.env.TEST_PASSWORD || 'testpassword');

    // Submit
    await page.click('button[type="submit"]');

    // Should redirect to dashboard
    await expect(page).toHaveURL(/dashboard|inbox/);
  });

  test.skip('inbox page loads', async ({ page }) => {
    // Requires auth - skip in default runs
    await page.goto('/inbox');
    await expect(page.locator('text=Inbox')).toBeVisible();
  });

  test.skip('leads page loads', async ({ page }) => {
    // Requires auth - skip in default runs
    await page.goto('/leads');
    await expect(page.locator('text=Leads')).toBeVisible();
  });
});

test.describe('CLONNECT - Responsive Design', () => {
  test('mobile viewport renders correctly', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');

    // Page should still be functional on mobile
    await expect(page.locator('body')).toBeVisible();
  });

  test('tablet viewport renders correctly', async ({ page }) => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await page.goto('/');

    await expect(page.locator('body')).toBeVisible();
  });
});

test.describe('CLONNECT - Performance', () => {
  test('page loads within acceptable time', async ({ page }) => {
    const startTime = Date.now();
    await page.goto('/');
    const loadTime = Date.now() - startTime;

    // Page should load within 5 seconds
    expect(loadTime).toBeLessThan(5000);
  });
});
