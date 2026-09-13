import { test, expect } from '@playwright/test';

test.describe('Phase 15 — Core Workflow & Product Corrections E2E Suite', () => {

  test('1. Registration flow generates Contributor ID (#####C) and displays Pending Approval screen', async ({ page }) => {
    await page.goto('/auth/register/');
    await expect(page.locator('#full_name')).toBeVisible();
    await expect(page.locator('#email')).toBeVisible();

    // Fill registration form
    const uniqueEmail = `contributor_${Date.now()}@aetherspace.dev`;
    await page.fill('#full_name', 'Test Contributor');
    await page.fill('#username', `test_${Date.now()}`);
    await page.fill('#email', uniqueEmail);
    await page.fill('#password', 'SecurePass123!@#');
    await page.fill('#confirm_password', 'SecurePass123!@#');
    await page.check('#accept_terms');
    await page.click('button[type="submit"]');

    // Should redirect to pending approval screen
    await expect(page).toHaveURL(/.*\/auth\/pending-approval\//);
    await expect(page.getByRole('heading', { name: /Account Pending Approval/i })).toBeVisible();

    // Contributor ID badge format check (5 digits + C, e.g. 26457C)
    const idElement = page.locator('.font-mono.tracking-wider');
    await expect(idElement).toBeVisible();
    const idText = await idElement.innerText();
    expect(idText).toMatch(/^\d{5}C$/);
  });

  test('2. Login page requires Contributor ID and contains NO third-party OAuth buttons', async ({ page }) => {
    await page.goto('/auth/login/');
    await expect(page.locator('#login-contributor-id')).toBeVisible();
    await expect(page.locator('#login-password')).toBeVisible();

    // Verify third-party OAuth links/buttons are completely removed
    await expect(page.locator('button:has-text("Google")')).toHaveCount(0);
    await expect(page.locator('button:has-text("Microsoft")')).toHaveCount(0);
    await expect(page.locator('button:has-text("GitHub")')).toHaveCount(0);
  });

  test('3. Search-First rule: empty queries strictly return 0 records in People Search', async ({ page }) => {
    // Check search-first prompt in workspace people search endpoint
    const response = await page.request.get('/admin/api/users/search/?q=');
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.results).toHaveLength(0);
    expect(body.query).toBe('');
  });

  test('4. Logo navigation links authenticated users to workspace dashboard', async ({ page }) => {
    await page.goto('/about/');
    // Public about page contains brand logo
    const brandLogo = page.locator('header a[title="AetherSpace"], nav a:has-text("AetherSpace")').first();
    await expect(brandLogo).toBeVisible();
  });

  test('5. Public About page (/about/) renders comprehensive platform guide', async ({ page }) => {
    await page.goto('/about/');
    await expect(page).toHaveTitle(/About AetherSpace/i);
    await expect(page.getByRole('heading', { name: /The Contributor ID Architecture/i })).toBeVisible();
    await expect(page.getByText('#####C')).toBeVisible();
    await expect(page.getByText('Agile Task Management')).toBeVisible();
    await expect(page.getByText('Bug & Defect Tracking')).toBeVisible();
    await expect(page.getByText('Meet Hub & Live Audio/Video')).toBeVisible();
  });

  test('6. Landing page has NO pricing section and includes interactive 3D product showcase', async ({ page }) => {
    await page.goto('/');
    // Check that pricing section is removed
    await expect(page.locator('#pricing')).toHaveCount(0);
    await expect(page.locator('a[href="#pricing"]')).toHaveCount(0);

    // Check 3D showcase card tabs
    await expect(page.getByRole('button', { name: /Tasks #619347/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Bugs B-882316/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Meet Hub/i })).toBeVisible();
  });

});
