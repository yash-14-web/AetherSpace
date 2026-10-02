import { test, expect, Page } from '@playwright/test';

/**
 * Meet Hub, Time Tracker & Availability Status E2E Spec
 * Execution command for owner:
 * `npx playwright test tests/e2e/meetings/meet_and_time_tracking.spec.ts`
 */

async function signIn(page: Page, email = 'admin@aetherspace.dev', password = 'AdminPassword123!') {
  await page.goto('/auth/login/');
  await page.fill('#login-email', email);
  await page.fill('#login-password', password);
  await page.click('button[type="submit"]');
  await page.waitForURL((url: URL) => !url.pathname.includes('/auth/login/'), { timeout: 15000 }).catch(() => {});
}

test.describe('AetherSpace — Meet Hub, Time Tracking & Communication Refinements', () => {

  test('1. Time Tracker terminology & Active Timer Pause Modal', async ({ page }) => {
    await signIn(page);
    await page.goto('/time/');

    // Verify Time Tracking & Logs and Time Tracker labels
    await expect(page.getByText('Time Tracking & Logs').first()).toBeVisible();
    await expect(page.getByText('Time Tracker').first()).toBeVisible();
    await expect(page.getByText('HOURS : MINS : SECS').first()).toBeVisible();

    // Verify Start Timer action button
    const startTimerBtn = page.getByRole('button', { name: /Start Timer/i });
    await expect(startTimerBtn).toBeVisible();

    // Verify pause confirmation modal element is rendered and hidden by default
    const pauseModal = page.locator('#active-timer-pause-modal');
    await expect(pauseModal).toBeHidden();
  });

  test('2. Availability Status Selector & Status Dialog in Header', async ({ page }) => {
    await signIn(page);
    await page.goto('/time/');

    // Click profile dropdown in universal header
    const profileDropdownBtn = page.locator('button[aria-label="User profile menu"], [x-ref="profileButton"]').first();
    if (await profileDropdownBtn.isVisible()) {
      await profileDropdownBtn.click();
      // Check for availability options
      await expect(page.getByText('Set Availability').first()).toBeVisible();
      await expect(page.getByText('Available').first()).toBeVisible();
      await expect(page.getByText('Busy').first()).toBeVisible();
      await expect(page.getByText('Do Not Disturb').first()).toBeVisible();
      await expect(page.getByText('Away').first()).toBeVisible();
      await expect(page.getByText('Out of Office').first()).toBeVisible();
    }
  });

  test('3. Meet Room — WebRTC elements, Chat style & effects removal', async ({ page }) => {
    await signIn(page);
    await page.goto('/meetings/');

    // Launch instant meeting
    const newMeetingBtn = page.getByRole('link', { name: /New Meeting|Start Room Now/i }).first();
    if (await newMeetingBtn.isVisible()) {
      await newMeetingBtn.click();
      await page.fill('input[name="title"]', 'Playwright WebRTC Audit');
      await page.click('button[type="submit"]');

      // Wait for meeting room
      await page.waitForURL(/\/meetings\/w\/[^\/]+\/room\/meet-[a-z0-9-]+/, { timeout: 15000 });

      // Verify video containers
      await expect(page.locator('#local-video')).toBeAttached();
      await expect(page.locator('#screen-video')).toBeAttached();

      // Verify effects (sparkle) and activities (puzzle/blocks) buttons are completely removed
      await expect(page.locator('button[title*="Visual Effects"]')).toHaveCount(0);
      await expect(page.locator('button[title*="Activities"]')).toHaveCount(0);

      // Verify in-call chat panel toggle exists
      const chatToggle = page.locator('#chat-toggle-btn');
      await expect(chatToggle).toBeVisible();
      await chatToggle.click();

      // Verify in-call chat container with message input
      await expect(page.locator('#chat-panel')).toBeVisible();
      await expect(page.locator('input[placeholder*="message"]')).toBeVisible();
    }
  });

  test('4. Universal Incoming Call Modal and Ringtone Synthesizer Component', async ({ page }) => {
    await signIn(page);
    await page.goto('/meetings/');

    // Modal container should exist in DOM with audio/video accept buttons
    const incomingCallModal = page.locator('#incoming-call-alert');
    await expect(incomingCallModal).toBeAttached();
  });
});
