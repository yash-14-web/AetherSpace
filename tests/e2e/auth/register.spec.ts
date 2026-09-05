import { test, expect } from '@playwright/test';

test.describe('Authentication Flows — Registration', () => {
  test('should render registration form with all required fields', async ({ page }) => {
    await page.goto('/auth/register/');
    await expect(page).toHaveTitle(/Create Your Account/);

    await expect(page.getByRole('heading', { name: /Create your account/i })).toBeVisible();
    await expect(page.locator('#register-fullname')).toBeVisible();
    await expect(page.locator('#register-email')).toBeVisible();
    await expect(page.locator('#register-password')).toBeVisible();
    await expect(page.locator('#register-confirm-password')).toBeVisible();
    await expect(page.locator('#agree-terms')).toBeVisible();
    await expect(page.getByRole('button', { name: /Create Account/i })).toBeVisible();
  });

  test('should show client-side password strength meter update on typing', async ({ page }) => {
    await page.goto('/auth/register/');
    const passwordInput = page.locator('#register-password');

    await passwordInput.fill('abc');
    await expect(page.getByText(/Strength:/i)).toBeVisible();
    await expect(page.getByText('Weak')).toBeVisible();

    await passwordInput.fill('ComplexPass123!#$');
    await expect(page.getByText('Strong')).toBeVisible();
  });

  test('should show validation error on password mismatch', async ({ page }) => {
    await page.goto('/auth/register/');
    await page.fill('#register-fullname', 'Playwright Tester');
    await page.fill('#register-email', 'tester@aetherspace.dev');
    await page.fill('#register-password', 'Pass12345678!');
    await page.fill('#register-confirm-password', 'DifferentPass99!');
    await page.check('#agree-terms');
    await page.click('button[type="submit"]');

    await expect(page.getByText('Passwords do not match.')).toBeVisible();
  });
});
