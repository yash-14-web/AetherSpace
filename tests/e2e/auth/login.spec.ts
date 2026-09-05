import { test, expect } from '@playwright/test';

test.describe('Authentication Flows', () => {
  test('should render login page with form inputs', async ({ page }) => {
    await page.goto('/auth/login/');
    await expect(page).toHaveTitle(/Sign In/);

    const emailInput = page.locator('input[name="email"]');
    const passwordInput = page.locator('input[name="password"]');
    const submitBtn = page.getByRole('button', { name: /Sign In to Workspace/i });

    await expect(emailInput).toBeVisible();
    await expect(passwordInput).toBeVisible();
    await expect(submitBtn).toBeVisible();
  });

  test('should show validation error on invalid credentials', async ({ page }) => {
    await page.goto('/auth/login/');
    await page.fill('input[name="email"]', 'nonexistent@aetherspace.dev');
    await page.fill('input[name="password"]', 'WrongPassword123!');
    await page.click('button[type="submit"]');

    await expect(page.getByText('Invalid email address or password.')).toBeVisible();
  });

  test('should navigate to registration page', async ({ page }) => {
    await page.goto('/auth/login/');
    await page.click('text=Create an account');
    await expect(page).toHaveURL(/.*\/auth\/register\//);
    await expect(page.getByText('Join AetherSpace')).toBeVisible();
  });
});
