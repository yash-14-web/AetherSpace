import { test, expect, Page } from '@playwright/test';

/**
 * Phase 9 — Calendar, Agenda & Upcoming Deadlines Playwright E2E Spec
 * Designed for manual owner execution: `npx playwright test tests/e2e/calendar/calendar_module.spec.ts`
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

test.describe('Phase 9 — Calendar & Scheduling Module', () => {

  test('should redirect unauthenticated users from calendar to login', async ({ page }) => {
    await page.goto('/calendar/');
    await expect(page).toHaveURL(/\/auth\/login\//);
  });

  test('should load Month Calendar view with sidebar mini-calendar and category filters', async ({ page }) => {
    await signIn(page);
    await page.goto('/calendar/');

    // Router redirects to workspace calendar view
    await expect(page).toHaveURL(/\/calendar\/w\/[^\/]+\//);

    // Verify main header and controls
    await expect(page.getByRole('heading', { name: /Calendar/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /New Event/i })).toBeVisible();

    // Verify view toggle buttons (Month, Agenda, Deadlines)
    await expect(page.getByRole('link', { name: 'Month' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Agenda' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Deadlines' })).toBeVisible();

    // Verify day headers
    const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    for (const day of days) {
      await expect(page.getByText(day).first()).toBeVisible();
    }

    // Verify category filter checkboxes in sidebar
    await expect(page.getByText('Filter Categories')).toBeVisible();
    await expect(page.getByText('Events')).toBeVisible();
    await expect(page.getByText('Tasks')).toBeVisible();
    await expect(page.getByText('Bugs')).toBeVisible();
    await expect(page.getByText('Meetings')).toBeVisible();
  });

  test('should navigate to Agenda view and display timeline sections', async ({ page }) => {
    await signIn(page);
    await page.goto('/calendar/');

    // Click Agenda view
    await page.click('a:has-text("Agenda")');
    await expect(page).toHaveURL(/\/calendar\/w\/[^\/]+\/agenda\//);

    // Verify Agenda header and sidebar metrics
    await expect(page.getByRole('heading', { name: /Agenda & Schedule/i })).toBeVisible();
    await expect(page.getByText("Today's Summary")).toBeVisible();
    await expect(page.getByText('Upcoming Schedule')).toBeVisible();
  });

  test('should navigate to Upcoming Deadlines view and show grouped cards and metrics', async ({ page }) => {
    await signIn(page);
    await page.goto('/calendar/');

    // Click Deadlines view
    await page.click('a:has-text("Deadlines")');
    await expect(page).toHaveURL(/\/calendar\/w\/[^\/]+\/deadlines\//);

    // Verify Deadlines header and metrics
    await expect(page.getByRole('heading', { name: /Upcoming Deadlines/i })).toBeVisible();
    await expect(page.getByText('Deadline Summary')).toBeVisible();
    await expect(page.getByText('Total Deadlines')).toBeVisible();

    // Verify group headings exist
    await expect(page.getByText('Today')).toBeVisible();
    await expect(page.getByText('Tomorrow')).toBeVisible();
    await expect(page.getByText('Next 7 Days')).toBeVisible();
  });

  test('should create a new calendar event and view event details', async ({ page }) => {
    await signIn(page);
    await page.goto('/calendar/');

    // Click "New Event" button
    await page.click('a:has-text("New Event")');
    await expect(page).toHaveURL(/\/calendar\/w\/[^\/]+\/events\/create\//);

    // Verify create form elements
    await expect(page.getByRole('heading', { name: /Create Event/i })).toBeVisible();
    await expect(page.getByText('Connect With')).toBeVisible();
    await expect(page.getByText('Invite People')).toBeVisible();

    const titleInput = page.locator('input[name="title"]');
    await titleInput.fill('E2E Sprint Planning Session');

    // Fill dates & times
    const today = new Date().toISOString().split('T')[0];
    await page.fill('input[name="start_date"]', today);
    await page.fill('input[name="start_time"]', '14:00');
    await page.fill('input[name="end_date"]', today);
    await page.fill('input[name="end_time"]', '15:30');

    // Submit form
    await page.click('button[type="submit"]:has-text("Create Event")');

    // Wait for redirect to event detail page
    await expect(page).toHaveURL(/\/calendar\/w\/[^\/]+\/events\/\d+\//);
    await expect(page.getByRole('heading', { name: 'E2E Sprint Planning Session' })).toBeVisible();

    // Verify tabs
    await expect(page.getByRole('button', { name: 'Overview' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'People' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Connected Items' })).toBeVisible();
  });

});
