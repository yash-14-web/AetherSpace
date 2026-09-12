import { test, expect } from '@playwright/test';

test.describe('Phase 13 — Admin Panel (Manual Owner Verification)', () => {

  test('should redirect unauthenticated users to login', async ({ page }) => {
    await page.goto('/admin-panel/');
    await expect(page).toHaveURL(/.*\/auth\/login\/.*/);
  });

  test('should render platform admin dashboard when authenticated', async ({ page }) => {
    // Note: Use authenticated platform admin credentials
    await page.goto('/auth/login/');
    await page.fill('#login-email', 'admin@aetherspace.dev');
    await page.fill('#login-password', 'Password123!');
    await page.click('button[type="submit"]');

    await page.goto('/admin-panel/');
    await expect(page).toHaveTitle(/Admin Console/);
    await expect(page.getByRole('heading', { name: /Platform Administration/i })).toBeVisible();

    // Verify root administrator pill
    await expect(page.getByText('Root Administrator')).toBeVisible();

    // Verify key metrics cards
    await expect(page.getByText('Total Users')).toBeVisible();
    await expect(page.getByText('Total Workspaces')).toBeVisible();
    await expect(page.getByText('Storage Consumed')).toBeVisible();
  });

  test('should enforce Search-First rule in People Selector', async ({ page }) => {
    await page.goto('/admin-panel/users/');
    await expect(page).toHaveTitle(/User Management/);

    // Open People Selector modal
    const openBtn = page.getByRole('button', { name: /Search People/i });
    if (await openBtn.isVisible()) {
      await openBtn.click();

      // Empty query prompt must be visible
      await expect(page.getByText(/Search team members/i)).toBeVisible();

      // Type query to fetch
      const searchInput = page.locator('#admin-people-search-input');
      await searchInput.fill('admin');
      await page.waitForTimeout(400);

      // Results appear
      await expect(page.locator('.people-search-result')).toBeVisible();
    }
  });

  test('should inspect Storage & Files and run sync audit', async ({ page }) => {
    await page.goto('/admin-panel/storage/');
    await expect(page).toHaveTitle(/Storage & Files Administration/);

    await expect(page.getByText('Real PostgreSQL + Supabase')).toBeVisible();
    await expect(page.getByRole('link', { name: /Run Storage Sync Audit/i })).toBeVisible();
    await expect(page.getByText('Workspace Quota Breakdown')).toBeVisible();
  });

  test('should view Integrations with zero secret disclosure', async ({ page }) => {
    await page.goto('/admin-panel/integrations/');
    await expect(page).toHaveTitle(/Platform Integrations/);
    await expect(page.getByText('Zero Secret Disclosure Enforced')).toBeVisible();
    await expect(page.getByText('Supabase PostgreSQL Database')).toBeVisible();
    await expect(page.getByText('Supabase Object Storage')).toBeVisible();
  });

  test('should display System Overview and Performance telemetry', async ({ page }) => {
    await page.goto('/admin-panel/system/');
    await expect(page).toHaveTitle(/System Overview/);
    await expect(page.getByText('System Runtime & Infrastructure')).toBeVisible();

    await page.goto('/admin-panel/performance/');
    await expect(page).toHaveTitle(/Performance Indicators/);
    await expect(page.getByText('Database Roundtrip')).toBeVisible();
    await expect(page.getByText('Not Configured')).toBeVisible(); // Honest APM indicator
  });

});
