import { test, expect } from '@playwright/test';

test.describe('Authentication Flows — Password Recovery', () => {
  test('should render forgot password form and handle submission', async ({ page }) => {
    await page.goto('/auth/forgot-password/');
    await expect(page).toHaveTitle(/Forgot Password/);

    await expect(page.getByRole('heading', { name: /Forgot your password\?/i })).toBeVisible();
    const emailInput = page.locator('#forgot-email');
    await expect(emailInput).toBeVisible();

    await emailInput.fill('developer@aetherspace.dev');
    await page.click('button[type="submit"]');

    // Should render recovery dispatched confirmation
    await expect(page.getByText('Recovery email dispatched')).toBeVisible();
  });

  test('should handle invalid or expired password reset link gracefully', async ({ page }) => {
    await page.goto('/auth/reset-password/invalid-uid/invalid-token/');
    await expect(page.getByText('Link Invalid or Expired')).toBeVisible();
    await expect(page.getByRole('link', { name: /Request New Reset Link/i })).toBeVisible();
  });
});
