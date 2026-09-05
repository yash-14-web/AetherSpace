import { test, expect } from '@playwright/test';

test.describe('Landing Page & Base Shell (Phase 2.5)', () => {
  test('should display hero section, branding, and navigation', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/AetherSpace/);

    // Verify brand logo in header
    const brand = page.locator('header a[href="/"]');
    await expect(brand).toBeVisible();
    await expect(brand.locator('img')).toBeVisible();

    // Verify public navigation items in header (scoped to navigation landmark)
    const nav = page.getByRole('navigation');
    await expect(nav.getByRole('link', { name: 'Features' })).toBeVisible();
    await expect(nav.getByRole('link', { name: 'Solutions' })).toBeVisible();
    await expect(nav.getByRole('link', { name: 'Resources' })).toBeVisible();
    await expect(nav.getByRole('link', { name: 'Pricing' })).toBeVisible();
    await expect(nav.getByRole('link', { name: 'About' })).toBeVisible();

    // Verify header authentication links (scoped to banner landmark)
    const header = page.getByRole('banner');
    await expect(header.getByRole('link', { name: 'Sign In' })).toBeVisible();
    await expect(header.getByRole('link', { name: /Get Started/i })).toBeVisible();

    // Verify hero section headline and primary call to action
    await expect(page.getByRole('heading', { name: /Your Team.*One AetherSpace/i })).toBeVisible();
    await expect(page.locator('main').getByRole('link', { name: /Get Started Free/i })).toBeVisible();

    // Verify trust metrics
    await expect(page.getByText('Secure by design')).toBeVisible();
    await expect(page.getByText('Built for small teams')).toBeVisible();
    await expect(page.getByText('Fast & intuitive')).toBeVisible();

    // Verify all-in-one workspace 6 feature cards by their headings
    await expect(page.getByRole('heading', { name: 'Task Management' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Bug Tracking' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Team Chat' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Meet Hub' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Calendar & Agenda' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Files & Sharing' })).toBeVisible();

    // Verify 4 value pillars
    await expect(page.getByRole('heading', { name: 'Collaborate Seamlessly' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Stay Organized' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Secure & Private' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Simple & Intuitive' })).toBeVisible();

    // Verify bottom CTA banner
    await expect(page.getByRole('heading', { name: /Ready to create your workspace\?/i })).toBeVisible();
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
