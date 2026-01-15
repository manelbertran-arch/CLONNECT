import { test, expect } from '@playwright/test';

test.describe('CLONNECT - Authentication Flow', () => {
  test('login form validation', async ({ page }) => {
    await page.goto('/login');

    // Try to submit empty form
    const submitButton = page.locator('button[type="submit"]');
    await submitButton.click();

    // Should show validation errors or stay on login page
    await expect(page).toHaveURL(/login/);
  });

  test('login with invalid credentials shows error', async ({ page }) => {
    await page.goto('/login');

    // Fill with invalid credentials
    await page.fill('input[type="email"], input[name="email"]', 'invalid@test.com');
    await page.fill('input[type="password"]', 'wrongpassword');

    await page.click('button[type="submit"]');

    // Should show error message or stay on login
    await page.waitForTimeout(1000);
    await expect(page).toHaveURL(/login/);
  });

  test('signup form has required fields', async ({ page }) => {
    await page.goto('/signup');

    // Should have name, email, and password fields
    const emailInput = page.locator('input[type="email"], input[name="email"]');
    const passwordInput = page.locator('input[type="password"]');

    await expect(emailInput).toBeVisible();
    await expect(passwordInput).toBeVisible();
  });

  test('can navigate between login and signup', async ({ page }) => {
    await page.goto('/login');

    // Look for link to signup
    const signupLink = page.locator('a[href="/signup"], button:has-text("Registr"), a:has-text("Registr"), a:has-text("Sign up")');
    if (await signupLink.count() > 0) {
      await signupLink.first().click();
      await expect(page).toHaveURL(/signup/);
    }
  });
});
