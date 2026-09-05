import { test, expect } from '@playwright/test';

test.describe('Landing Page & Base Shell', () => {
  test('should display hero section, branding, and navigation', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/AetherSpace/);

    // Verify brand logo link
    const brand = page.locator('header a[href="/"]');
    await expect(brand).toBeVisible();

    // Verify primary call to action
    const getStartedBtn = page.getByRole('link', { name: /Get Started Free/i });
    await expect(getStartedBtn).toBeVisible();

    // Verify feature sections by their headings
    await expect(page.getByRole('heading', { name: 'Agile Tasks' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Bug Tracking' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Supabase RBAC' })).toBeVisible();
  });

  test('should toggle theme between dark and light mode', async ({ page }) => {
    await page.goto('/');
    const themeBtn = page.getByRole('button', { name: /Toggle Theme/i });
    await expect(themeBtn).toBeVisible();

    // Click to toggle
    await themeBtn.click();
    // Verify html tag class reflects change or color-theme in localStorage
    const themeInStorage = await page.evaluate(() => localStorage.getItem('color-theme'));
    expect(['light', 'dark']).toContain(themeInStorage);
  });
});
