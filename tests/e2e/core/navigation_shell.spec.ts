import { test, expect, Page } from '@playwright/test';

async function signIn(page: Page, email = 'admin@aetherspace.dev', password = 'AdminPassword123!') {
  await page.goto('/auth/login/');
  await page.fill('#login-email', email);
  await page.fill('#login-password', password);
  await page.click('button[type="submit"]');
  await page.waitForURL((url: URL) => !url.pathname.includes('/auth/login/'), { timeout: 10000 }).catch(() => {});
}

test.describe('Main Application Shell & Navigation (Phase 4)', () => {

  test('should display complete 10-item global icon rail', async ({ page }) => {
    await signIn(page);
    await page.goto('/workspaces/master/');

    // Assert Global Rail is visible
    const aside = page.locator('aside');
    await expect(aside).toBeVisible();

    // Verify 10 Global Rail elements by their titles/roles
    await expect(aside.locator('a[title="Dashboard"]')).toBeVisible();
    await expect(aside.locator('a[title="Time Tracking"]')).toBeVisible();
    await expect(aside.locator('a[title="Calendar"]')).toBeVisible();
    await expect(aside.locator('a[title="Files"]')).toBeVisible();
    await expect(aside.locator('a[title="Meet Hub"]')).toBeVisible();
    await expect(aside.locator('a[title="Chat"]')).toBeVisible();
    await expect(aside.locator('a[title="Notifications"]')).toBeVisible();
    await expect(aside.locator('a[title="Profile"]')).toBeVisible();
    await expect(aside.locator('a[title="Settings"]')).toBeVisible();
    await expect(aside.locator('button[title="Toggle Theme"]')).toBeVisible();
  });

  test('should display Workspace Tree with contextual links when workspace is active', async ({ page }) => {
    await signIn(page);
    await page.goto('/workspaces/w/smart-classroom/');

    // Assert Workspace Tree items
    await expect(page.getByRole('link', { name: 'Dashboard' }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: 'Team Members' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Project Details' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Team Chat' })).toBeVisible();
  });

  test('should open and close Universal Search modal with keyboard and button', async ({ page }) => {
    await signIn(page);
    await page.goto('/workspaces/master/');

    // Click search trigger in header
    const searchTrigger = page.locator('header button', { hasText: /Search tasks/i });
    await searchTrigger.click();

    // Search modal should be visible
    const searchModal = page.locator('input[placeholder*="Type a task"]');
    await expect(searchModal).toBeVisible();

    // Press Escape to dismiss
    await page.keyboard.press('Escape');
    await expect(searchModal).not.toBeVisible();
  });

  test('should toggle notifications dropdown from header bell', async ({ page }) => {
    await signIn(page);
    await page.goto('/workspaces/master/');

    const header = page.getByRole('banner');
    const notifBtn = header.locator('button[aria-label="Notifications"]');
    await notifBtn.click();

    await expect(header.getByText('Notifications', { exact: true })).toBeVisible();
    await expect(header.getByText('View All Notifications →')).toBeVisible();
  });

  test('should open User Profile dropdown menu and display user information', async ({ page }) => {
    await signIn(page);
    await page.goto('/workspaces/master/');

    const header = page.getByRole('banner');
    // Avatar button has initials AD
    const avatarBtn = header.locator('button', { hasText: /AD/i });
    await avatarBtn.click();

    await expect(header.getByText('admin@aetherspace.dev')).toBeVisible();
    await expect(header.getByRole('link', { name: 'My Profile' })).toBeVisible();
    await expect(header.getByRole('link', { name: 'Sign Out' })).toBeVisible();
  });

  test('should navigate to placeholder modules and render roadmap details', async ({ page }) => {
    await signIn(page);

    // Calendar
    await page.goto('/calendar/');
    await expect(page.getByRole('heading', { name: 'Calendar & Agenda' })).toBeVisible();

    // Files
    await page.goto('/files/');
    await expect(page.getByRole('heading', { name: 'Files & Storage' })).toBeVisible();

    // Meet Hub
    await page.goto('/meetings/');
    await expect(page.getByRole('heading', { name: 'Meet Hub' })).toBeVisible();
  });

  test('should open mobile navigation drawer on mobile viewport', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await signIn(page);
    await page.goto('/workspaces/master/');

    const header = page.getByRole('banner');
    const hamburgerBtn = header.locator('button[aria-label="Toggle mobile menu"]');
    await expect(hamburgerBtn).toBeVisible();

    await hamburgerBtn.click();
    // In mobile view, drawer slides in
    await expect(page.locator('aside a[title="Dashboard"]')).toBeVisible();
  });

});
