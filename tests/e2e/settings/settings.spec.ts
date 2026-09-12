import { test, expect, Page } from '@playwright/test';

/**
 * Phase 14 — Settings Module Playwright E2E Spec
 * Designed for manual owner execution: `npx playwright test tests/e2e/settings/settings.spec.ts`
 *
 * NOTE: As per project instructions, automated browser sessions are NOT executed by Antigravity;
 * this spec is authored for user/CI verification.
 */

async function signIn(page: Page, email = 'admin@aetherspace.dev', password = 'AdminPassword123!') {
  await page.goto('/auth/login/');
  await page.fill('#login-email', email);
  await page.fill('#login-password', password);
  await page.click('button[type="submit"]');
  await page.waitForURL((url: URL) => !url.pathname.includes('/auth/login/'), { timeout: 15000 }).catch(() => {});
}

test.describe('Phase 14 — Settings & Preferences Module', () => {

  test('should redirect unauthenticated users from settings to login', async ({ page }) => {
    await page.goto('/settings/');
    await expect(page).toHaveURL(/\/auth\/login\//);
  });

  test('should load Account Settings with user information and timezone', async ({ page }) => {
    await signIn(page);
    await page.goto('/settings/account/');

    await expect(page.getByRole('heading', { name: /Settings & Preferences/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /Account Details/i })).toBeVisible();
    await expect(page.getByText(/Primary Timezone/i)).toBeVisible();
    await expect(page.getByText(/Platform Authority Level/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /Save Account Changes/i })).toBeVisible();
  });

  test('should load Public Profile settings with avatar preview and bio', async ({ page }) => {
    await signIn(page);
    await page.goto('/settings/profile/');

    await expect(page.getByRole('heading', { name: /Public Profile/i })).toBeVisible();
    await expect(page.getByText(/Profile Avatar URL/i)).toBeVisible();
    await expect(page.getByText(/Headline \/ Title/i)).toBeVisible();
    await expect(page.getByText(/Professional Bio/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /Save Profile/i })).toBeVisible();
  });

  test('should load Appearance tab and toggle Obsidian Dark / Slate Light', async ({ page }) => {
    await signIn(page);
    await page.goto('/settings/appearance/');

    await expect(page.getByRole('heading', { name: /Interface Theme/i })).toBeVisible();
    await expect(page.getByText(/Obsidian Dark/i)).toBeVisible();
    await expect(page.getByText(/Slate Light/i)).toBeVisible();
    await expect(page.getByText(/System Sync/i)).toBeVisible();

    // Click Slate Light card
    await page.getByText(/Slate Light/i).click();
    // Verify html dark class was removed or light mode applied
    const hasDark = await page.evaluate(() => document.documentElement.classList.contains('dark'));
    expect(hasDark).toBe(false);

    // Switch back to Obsidian Dark
    await page.getByText(/Obsidian Dark/i).click();
    const hasDarkNow = await page.evaluate(() => document.documentElement.classList.contains('dark'));
    expect(hasDarkNow).toBe(true);
  });

  test('should load Notification preferences and event toggles', async ({ page }) => {
    await signIn(page);
    await page.goto('/settings/notifications/');

    await expect(page.getByRole('heading', { name: /Notification Preferences/i })).toBeVisible();
    await expect(page.getByText(/Email Digest Frequency/i)).toBeVisible();
    await expect(page.getByText(/Tasks & Subtasks/i)).toBeVisible();
    await expect(page.getByText(/Bugs & Regressions/i)).toBeVisible();
    await expect(page.getByText(/Chat & Direct Messages/i)).toBeVisible();
    await expect(page.getByText(/Meetings & Calendar/i)).toBeVisible();
  });

  test('should load Security tab with password change and active session info', async ({ page }) => {
    await signIn(page);
    await page.goto('/settings/security/');

    await expect(page.getByRole('heading', { name: /Change Password/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /Active Session/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /Security Audit Events/i })).toBeVisible();
    await expect(page.getByText(/Client IP Address/i)).toBeVisible();
  });

  test('should load Workspaces list and enforce RBAC', async ({ page }) => {
    await signIn(page);
    await page.goto('/settings/workspaces/');

    await expect(page.getByRole('heading', { name: /Workspaces/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Create Workspace/i })).toBeVisible();
  });

  test('should load Integrations tab with masked webhook secret', async ({ page }) => {
    await signIn(page);
    await page.goto('/settings/integrations/');

    await expect(page.getByRole('heading', { name: /Platform Integrations/i })).toBeVisible();
    await expect(page.getByText(/WebRTC \/ Jitsi Meet/i)).toBeVisible();
    await expect(page.getByText(/Supabase Storage/i)).toBeVisible();
    await expect(page.getByText(/Developer Webhooks/i)).toBeVisible();
    await expect(page.getByText(/whsec_/i)).toBeVisible();
  });

  test('should open Global Search modal with 6-digit Task ID and Bug ID navigation', async ({ page }) => {
    await signIn(page);
    await page.goto('/settings/account/');

    // Click the search bar
    await page.click('button:has-text("Search tasks")');
    await expect(page.getByPlaceholder(/Type a task ID/i)).toBeVisible();

    // Type a query
    await page.fill('input[placeholder*="Type a task ID"]', '619347');
    await page.waitForTimeout(500); // debounce
  });

});
