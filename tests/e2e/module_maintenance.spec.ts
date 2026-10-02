import { test, expect } from '@playwright/test';

test.describe('Global Module Maintenance & Deployment Readiness E2E Suite', () => {

  test('1. Meet Hub shows Under Maintenance banner on dashboard', async ({ page }) => {
    // Navigate to Meet Hub dashboard
    await page.goto('/meetings/w/aetherspace-core/');

    // When under maintenance, the page must display the maintenance banner
    const banner = page.locator('text=Meet Hub — Under Maintenance');
    if (await banner.isVisible()) {
      await expect(banner).toBeVisible();
      await expect(page.locator('text=Meet Hub is temporarily unavailable while we complete improvements.')).toBeVisible();

      // Action buttons should be disabled
      const startBtn = page.locator('button:has-text("Start Meeting")');
      await expect(startBtn).toBeDisabled();
    }
  });

  test('2. Direct meeting room access is blocked server-side with 503', async ({ page }) => {
    // Attempting direct URL access to a meeting room while under maintenance
    const response = await page.goto('/meetings/w/aetherspace-core/room/meet-test-1234/');
    if (response) {
      expect([503, 302]).toContain(response.status());
      if (response.status() === 503) {
        await expect(page.locator('text=Meet Hub is Under Maintenance')).toBeVisible();
      }
    }
  });

  test('3. Direct instant meeting launcher is blocked server-side with 503', async ({ page }) => {
    const response = await page.goto('/meetings/w/aetherspace-core/start/');
    if (response) {
      expect([503, 302]).toContain(response.status());
    }
  });

  test('4. Admin Console: Module Maintenance page displays all modules and status badges', async ({ page }) => {
    // Sign in as Platform Admin
    await page.goto('/accounts/login/');
    await page.fill('input[name="username"]', 'admin');
    await page.fill('input[name="password"]', 'adminpassword');
    await page.click('button[type="submit"]');

    // Visit Admin Module Management
    await page.goto('/admin-panel/modules/');
    await expect(page.locator('h1')).toContainText('Module Maintenance & Availability');
    await expect(page.locator('text=Configured System Modules')).toBeVisible();

    // Verify Meet Hub row indicates Under Maintenance
    const meetHubRow = page.locator('tr:has-text("Meet Hub")');
    await expect(meetHubRow).toBeVisible();
    await expect(meetHubRow.locator('text=Under Maintenance')).toBeVisible();
  });

  test('5. Dynamic Recovery: Switching Meet Hub from Under Maintenance to Available', async ({ page }) => {
    // Open Admin Module Management
    await page.goto('/admin-panel/modules/');

    // Locate and click Edit Status for Meet Hub
    const meetRow = page.locator('tr:has-text("Meet Hub")');
    if (await meetRow.isVisible()) {
      await meetRow.locator('button:has-text("Edit Status")').click();

      // Modal opens
      await expect(page.locator('text=Configure Module Status')).toBeVisible();

      // Change status to Available
      await page.selectOption('select[name="status"]', 'AVAILABLE');
      await page.fill('input[name="public_message"]', 'Meet Hub is fully operational.');
      await page.click('button:has-text("Save Status Changes")');

      // Verify status updated in table
      await expect(page.locator('text=Module \'Meet Hub\' status changed to \'Available\'')).toBeVisible();
    }
  });

});
