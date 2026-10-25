import { test, expect } from '@playwright/test';

test('Capture visual screenshots of redesigned Project Details page and cleaned Team page', async ({ page }) => {
  // 1. Login as admin
  await page.goto('/auth/login/');
  await page.fill('#login-contributor-id', 'e2e_timetracker@aetherspace.dev');
  await page.fill('#login-password', 'Password123!');
  await page.click('button[type="submit"]');
  await page.waitForURL((url: URL) => !url.pathname.includes('/auth/login/'), { timeout: 15000 }).catch(() => {});

  // 2. Go to Project Details (Dark Mode Desktop)
  await page.setViewportSize({ width: 1440, height: 950 });
  await page.goto('/workspaces/w/aetherspace-core/project/');
  await page.waitForLoadState('networkidle');

  // Ensure dark mode is active
  await page.evaluate(() => {
    localStorage.setItem('color-theme', 'dark');
    document.documentElement.classList.add('dark');
  });
  await page.waitForTimeout(500);

  // Capture Project Details - Dark Mode
  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/535e0b22-5b14-4eef-aa57-2b2ed1427168/project_details_dark_desktop.png',
    fullPage: true
  });

  // 3. Open Edit Modal and capture
  const editBtn = page.locator('button:has-text("Edit Details")');
  if (await editBtn.isVisible()) {
    await editBtn.click();
    await page.waitForTimeout(400);
    await page.screenshot({
      path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/535e0b22-5b14-4eef-aa57-2b2ed1427168/project_details_edit_modal_dark.png',
      fullPage: false
    });
    // Close modal
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
  }

  // 4. Switch to Light Mode (Clean Slate)
  await page.evaluate(() => {
    localStorage.setItem('color-theme', 'light');
    document.documentElement.classList.remove('dark');
  });
  await page.waitForTimeout(500);

  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/535e0b22-5b14-4eef-aa57-2b2ed1427168/project_details_light_desktop.png',
    fullPage: true
  });

  // 5. Mobile Layout (Dark Mode)
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => {
    localStorage.setItem('color-theme', 'dark');
    document.documentElement.classList.add('dark');
  });
  await page.waitForTimeout(500);

  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/535e0b22-5b14-4eef-aa57-2b2ed1427168/project_details_dark_mobile.png',
    fullPage: true
  });

  // 6. Verify Team page - no duplicate search bar in header
  await page.setViewportSize({ width: 1440, height: 950 });
  await page.goto('/workspaces/w/aetherspace-core/team/');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(500);

  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/535e0b22-5b14-4eef-aa57-2b2ed1427168/team_page_no_duplicate_search.png',
    fullPage: false
  });
});
