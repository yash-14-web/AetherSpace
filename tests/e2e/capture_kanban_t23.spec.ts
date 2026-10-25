import { test } from '@playwright/test';

test('Capture visual screenshots of T2.3 Kanban redesign', async ({ page }) => {
  // Login
  await page.goto('http://127.0.0.1:8000/auth/login/');
  await page.fill('#login-contributor-id', 'e2e_timetracker@aetherspace.dev');
  await page.fill('#login-password', 'Password123!');
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.includes('/auth/login/'), { timeout: 15000 }).catch(() => {});

  // Go to Kanban Board
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('http://127.0.0.1:8000/tasks/w/aetherspace-core/board/');
  await page.waitForLoadState('networkidle');

  // 1. Dark Mode Desktop Screenshot
  await page.evaluate(() => {
    localStorage.setItem('color-theme', 'dark');
    document.documentElement.classList.add('dark');
  });
  await page.waitForTimeout(500);

  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/3a78f02b-1951-4cb0-a740-1399cf79289b/kanban_desktop_dark.png',
    fullPage: false
  });

  // Scroll board to the right to capture Testing and Done columns with active cards
  await page.evaluate(() => {
    const boardContainer = document.querySelector('.overflow-x-auto.pb-6');
    if (boardContainer) {
      boardContainer.scrollLeft = 800;
    }
  });
  await page.waitForTimeout(300);

  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/3a78f02b-1951-4cb0-a740-1399cf79289b/kanban_desktop_dark_scrolled.png',
    fullPage: false
  });

  // 2. Light Mode Desktop Screenshot
  await page.evaluate(() => {
    localStorage.setItem('color-theme', 'light');
    document.documentElement.classList.remove('dark');
    const boardContainer = document.querySelector('.overflow-x-auto.pb-6');
    if (boardContainer) {
      boardContainer.scrollLeft = 0;
    }
  });
  await page.waitForTimeout(500);

  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/3a78f02b-1951-4cb0-a740-1399cf79289b/kanban_desktop_light.png',
    fullPage: false
  });

  // Scroll light mode
  await page.evaluate(() => {
    const boardContainer = document.querySelector('.overflow-x-auto.pb-6');
    if (boardContainer) {
      boardContainer.scrollLeft = 800;
    }
  });
  await page.waitForTimeout(300);

  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/3a78f02b-1951-4cb0-a740-1399cf79289b/kanban_desktop_light_scrolled.png',
    fullPage: false
  });

  // 3. Mobile View Screenshot (390x844) in Dark Mode
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => {
    localStorage.setItem('color-theme', 'dark');
    document.documentElement.classList.add('dark');
  });
  await page.waitForTimeout(500);

  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/3a78f02b-1951-4cb0-a740-1399cf79289b/kanban_mobile_view.png',
    fullPage: false
  });

  // Click 'Done' pill in mobile view to test mobile navigation
  const donePill = page.locator('button[\\@click*="DONE"]');
  await donePill.click();
  await page.waitForTimeout(300);

  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/3a78f02b-1951-4cb0-a740-1399cf79289b/kanban_mobile_done_stage.png',
    fullPage: false
  });
});
