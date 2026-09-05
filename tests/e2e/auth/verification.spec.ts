import { test, expect } from '@playwright/test';

test.describe('Authentication Flows — Account Verification', () => {
  test('should render email verification checklist and instructions', async ({ page }) => {
    await page.goto('/auth/verify/');
    await expect(page).toHaveTitle(/Verify Your Email/);

    await expect(page.getByRole('heading', { name: /Verify your email/i })).toBeVisible();
    await expect(page.getByText('Check your inbox (and spam folder)')).toBeVisible();
    await expect(page.getByText('Click the verification link provided')).toBeVisible();
    await expect(page.getByText('Start collaborating across your workspaces')).toBeVisible();
  });

  test('should display invalid link state on bad verification tokens', async ({ page }) => {
    await page.goto('/auth/verify/invalid-uid/invalid-token/');
    await expect(page.getByText('This verification link is invalid or has expired.')).toBeVisible();
    await expect(page.getByRole('button', { name: /Resend Verification Link/i })).toBeVisible();
  });
});
