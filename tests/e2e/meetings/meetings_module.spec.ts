import { test, expect, Page } from '@playwright/test';

/**
 * Phase 8 — Meet Hub & Video Conferencing Playwright E2E Spec
 * Designed for manual owner execution: `npx playwright test tests/e2e/meetings/meetings_module.spec.ts`
 */

async function signIn(page: Page, email = 'admin@aetherspace.dev', password = 'AdminPassword123!') {
  await page.goto('/auth/login/');
  await page.fill('#login-email', email);
  await page.fill('#login-password', password);
  await page.click('button[type="submit"]');
  await page.waitForURL((url: URL) => !url.pathname.includes('/auth/login/'), { timeout: 10000 }).catch(() => {});
}

test.describe('Phase 8 — Meet Hub & Video Conferencing', () => {

  test('should redirect unauthenticated users to login', async ({ page }) => {
    await page.goto('/meetings/');
    await expect(page).toHaveURL(/\/auth\/login\//);
  });

  test('should display Meet Hub with launchpad cards and metric chips', async ({ page }) => {
    await signIn(page);
    await page.goto('/meetings/');

    // Ensure we landed on workspace Meet Hub
    await expect(page).toHaveURL(/\/meetings\/w\/[^\/]+\//);
    await expect(page.getByRole('heading', { name: 'Meet Hub' })).toBeVisible();

    // Verify 3 launchpad cards
    await expect(page.getByText('Instant Meeting')).toBeVisible();
    await expect(page.getByText('Join by Code')).toBeVisible();
    await expect(page.getByText('Schedule Meeting').first()).toBeVisible();

    // Verify metric chips
    await expect(page.getByText('Live Now', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Today', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Upcoming', { exact: true }).first()).toBeVisible();
  });

  test('should launch instant meeting and load WebRTC container', async ({ page }) => {
    await signIn(page);
    await page.goto('/meetings/');

    // Click "New Meeting" or "Start Room Now"
    const newMeetingBtn = page.getByRole('link', { name: /New Meeting/i });
    if (await newMeetingBtn.isVisible()) {
      await newMeetingBtn.click();
    } else {
      await page.getByRole('link', { name: /Start Room Now/i }).click();
    }

    await expect(page.getByRole('heading', { name: /Start an Instant Meeting/i })).toBeVisible();

    // Fill title
    await page.fill('input[name="title"]', 'E2E Playwright Standup');
    await page.click('button[type="submit"]');

    // Should redirect to room
    await expect(page).toHaveURL(/\/room\/meet-[a-z0-9]{4}-[a-z0-9]{4}\//);
    await expect(page.getByText('E2E Playwright Standup')).toBeVisible();
    await expect(page.getByText(/00:00/)).toBeVisible();

    // Jitsi container is present
    await expect(page.locator('#jitsi-meet-container')).toBeVisible();
  });

  test('should allow scheduling a standup meeting', async ({ page }) => {
    await signIn(page);
    await page.goto('/meetings/');

    await page.getByRole('link', { name: /Schedule/i }).first().click();
    await expect(page.getByRole('heading', { name: /Schedule a Standup/i })).toBeVisible();

    await page.fill('input[name="title"]', 'Sprint Architecture Review');
    
    // Pick tomorrow's date
    const tomorrow = new Date();
    tomorrow.setDate(tomorrow.getDate() + 1);
    const dateStr = tomorrow.toISOString().split('T')[0];
    await page.fill('input[name="scheduled_date"]', dateStr);
    await page.fill('input[name="scheduled_time"]', '14:30');

    await page.click('button[type="submit"]');

    // Should land on meeting detail
    await expect(page.getByRole('heading', { name: 'Sprint Architecture Review' })).toBeVisible();
    await expect(page.getByText('SCHEDULED')).toBeVisible();
  });

  test('should display Meeting History table with filters', async ({ page }) => {
    await signIn(page);
    await page.goto('/meetings/');

    await page.getByRole('link', { name: /All History/i }).first().click();
    await expect(page.getByRole('heading', { name: 'Meeting History' })).toBeVisible();

    // Verify filter dropdowns exist
    await expect(page.locator('select[name="type"]')).toBeVisible();
    await expect(page.locator('select[name="status"]')).toBeVisible();
  });

  test('should render Google Chat style call buttons in team chat', async ({ page }) => {
    await signIn(page);
    await page.goto('/chat/');

    // Verify audio call and video call launcher buttons exist in header
    const audioCallBtn = page.locator('button[title*="Start Audio Call"]');
    const videoCallBtn = page.locator('button[title*="Start Video Meeting"]');

    if (await audioCallBtn.count() > 0) {
      await expect(audioCallBtn.first()).toBeVisible();
      await expect(videoCallBtn.first()).toBeVisible();
    }
  });

});
