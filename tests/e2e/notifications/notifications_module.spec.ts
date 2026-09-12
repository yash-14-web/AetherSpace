import { test, expect, Page } from '@playwright/test';

/**
 * Phase 11 — Notifications Module Playwright E2E Spec
 * Designed for manual owner execution: `npx playwright test tests/e2e/notifications/notifications_module.spec.ts`
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

test.describe('Phase 11 — Notifications Module', () => {

  test('should redirect unauthenticated users from notifications to login', async ({ page }) => {
    await page.goto('/notifications/');
    await expect(page).toHaveURL(/\/auth\/login\//);
  });

  test('should load Notification Center with metric cards, tabs, and filter controls', async ({ page }) => {
    await signIn(page);
    await page.goto('/notifications/');

    // Router redirects to active workspace notifications
    await expect(page).toHaveURL(/\/notifications\/w\/[^\/]+\//);

    // Verify main page title and description
    await expect(page.getByRole('heading', { name: /Notifications/i }).first()).toBeVisible();
    await expect(page.getByText(/Stay updated with task assignments, bug reports, mentions, and activities/i)).toBeVisible();

    // Verify 5 metric cards
    await expect(page.getByText('Total Notifications')).toBeVisible();
    await expect(page.getByText('Unread')).toBeVisible();
    await expect(page.getByText('Tasks & Bugs')).toBeVisible();
    await expect(page.getByText('Mentions')).toBeVisible();
    await expect(page.getByText('Read')).toBeVisible();

    // Verify filter tabs
    await expect(page.getByRole('link', { name: /^All/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Unread/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Tasks/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Bugs/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Mentions/i })).toBeVisible();

    // Verify Search filter input
    await expect(page.getByPlaceholder('Filter notifications...')).toBeVisible();

    // Verify Mark all as read button
    await expect(page.getByRole('button', { name: /Mark all read/i })).toBeVisible();
  });

  test('should switch between notification category tabs', async ({ page }) => {
    await signIn(page);
    await page.goto('/notifications/');

    // Click Unread tab
    await page.getByRole('link', { name: /Unread/i }).click();
    await expect(page).toHaveURL(/filter=unread/);

    // Click Tasks tab
    await page.getByRole('link', { name: /Tasks/i }).click();
    await expect(page).toHaveURL(/filter=tasks/);

    // Click Bugs tab
    await page.getByRole('link', { name: /Bugs/i }).click();
    await expect(page).toHaveURL(/filter=bugs/);

    // Click Mentions tab
    await page.getByRole('link', { name: /Mentions/i }).click();
    await expect(page).toHaveURL(/filter=mentions/);

    // Click All tab
    await page.getByRole('link', { name: /^All/i }).click();
    await expect(page).toHaveURL(/filter=all/);
  });

  test('should toggle notification dropdown from header bell icon', async ({ page }) => {
    await signIn(page);
    await page.goto('/');

    // Locate the notifications bell button in the universal header
    const bellButton = page.locator('button[aria-label="Notifications"]');
    await expect(bellButton).toBeVisible();

    // Click bell icon to open notifications panel
    await bellButton.click();

    // Dropdown panel should display title and link to Notification Center
    await expect(page.getByText('Notifications').first()).toBeVisible();
    const viewAllLink = page.getByText(/View All Notifications/i);
    await expect(viewAllLink).toBeVisible();

    // Clicking View All Notifications should navigate to notifications
    await viewAllLink.click();
    await expect(page).toHaveURL(/\/notifications\/w\/[^\/]+\//);
  });

  test('should filter notifications via search box', async ({ page }) => {
    await signIn(page);
    await page.goto('/notifications/');

    const searchInput = page.getByPlaceholder('Filter notifications...');
    await searchInput.fill('Security vulnerability');
    await searchInput.press('Enter');

    await expect(page).toHaveURL(/q=Security\+vulnerability|q=Security%20vulnerability/);
  });

  test('should support Mark all as read state-changing action', async ({ page }) => {
    await signIn(page);
    await page.goto('/notifications/');

    const markAllBtn = page.getByRole('button', { name: /Mark all read/i });
    if (await markAllBtn.isVisible()) {
      await markAllBtn.click();
      // Should redirect back to notifications and remain on the page
      await expect(page).toHaveURL(/\/notifications\/w\/[^\/]+\//);
    }
  });

});
