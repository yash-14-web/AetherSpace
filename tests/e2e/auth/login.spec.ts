import { test, expect } from '@playwright/test';

test.describe('Authentication Flows — Login', () => {
  test('should render login page with form inputs, remember-me, and trust badges', async ({ page }) => {
    await page.goto('/auth/login/');
    await expect(page).toHaveTitle(/Sign In/);

    // Verify main headings and brand presence
    await expect(page.getByRole('heading', { name: /Welcome back!/i })).toBeVisible();

    const emailInput = page.locator('#login-email');
    const passwordInput = page.locator('#login-password');
    const rememberMeCheckbox = page.locator('#remember-me');
    const submitBtn = page.getByRole('button', { name: /Sign In/i });

    await expect(emailInput).toBeVisible();
    await expect(passwordInput).toBeVisible();
    await expect(rememberMeCheckbox).toBeVisible();
    await expect(submitBtn).toBeVisible();

    // Verify enterprise trust badges
    await expect(page.getByText('Secure. Private.')).toBeVisible();
    await expect(page.getByText('End-to-End Encryption')).toBeVisible();
    await expect(page.getByText('Role-Based Access')).toBeVisible();
  });

  test('should show validation error on invalid credentials', async ({ page }) => {
    await page.goto('/auth/login/');
    await page.fill('#login-email', 'nonexistent@aetherspace.dev');
    await page.fill('#login-password', 'WrongPassword123!');
    await page.click('button[type="submit"]');

    await expect(page.getByText('Invalid email address or password.')).toBeVisible();
  });

  test('should toggle password visibility on login page', async ({ page }) => {
    await page.goto('/auth/login/');
    const passwordInput = page.locator('#login-password');
    await passwordInput.fill('Secret123!');

    await expect(passwordInput).toHaveAttribute('type', 'password');

    // Click show password toggle button
    const toggleBtn = page.getByRole('button', { name: /Toggle password visibility/i });
    await toggleBtn.click();
    await expect(passwordInput).toHaveAttribute('type', 'text');

    // Click again to hide
    await toggleBtn.click();
    await expect(passwordInput).toHaveAttribute('type', 'password');
  });

  test('should navigate to registration page', async ({ page }) => {
    await page.goto('/auth/login/');
    await page.click('text=Accept invitation / Register');
    await expect(page).toHaveURL(/.*\/auth\/register\//);
    await expect(page.getByRole('heading', { name: /Create your account/i })).toBeVisible();
  });
});
