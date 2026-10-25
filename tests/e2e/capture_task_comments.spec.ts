import { test } from '@playwright/test';

test.setTimeout(60000);

test('Capture Task Detail Comments tab in Dark and Light mode matching mockup', async ({ page }) => {
  // Login
  await page.goto('http://127.0.0.1:8000/auth/login/');
  await page.fill('#login-contributor-id', 'e2e_timetracker@aetherspace.dev');
  await page.fill('#login-password', 'Password123!');
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.includes('/auth/login/'), { timeout: 15000 }).catch(() => {});

  // 1. Desktop Dark - 1440x900
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('http://127.0.0.1:8000/tasks/w/aetherspace-core/156656/?tab=comments');
  await page.evaluate(() => {
    localStorage.setItem('color-theme', 'dark');
    document.documentElement.classList.add('dark');
  });
  await page.waitForTimeout(500);

  // Type @yo in the main composer to demonstrate live mention popover
  const textarea = page.locator('#main-comment-editor');
  await textarea.click();
  await textarea.pressSequentially('@yo', { delay: 100 });
  await page.waitForTimeout(500);

  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/3a78f02b-1951-4cb0-a740-1399cf79289b/comments_tab_dark_mention_active.png',
    fullPage: false
  });

  // Clear textarea
  await textarea.fill('');
  await textarea.dispatchEvent('input');
  await page.waitForTimeout(400);

  // Click Reply button on first comment to open inline reply composer
  const replyBtn = page.locator('button:has-text("Reply")').first();
  if (await replyBtn.count() > 0) {
    await replyBtn.click();
    await page.waitForTimeout(400);
  }

  // Scroll down slightly to show cards and threaded reply composer
  await page.evaluate(() => {
    const scrollEl = document.querySelector('main') || window;
    scrollEl.scrollBy(0, 320);
    window.scrollBy(0, 320);
  });
  await page.waitForTimeout(400);

  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/3a78f02b-1951-4cb0-a740-1399cf79289b/comments_tab_dark_scrolled.png',
    fullPage: false
  });

  // 2. Desktop Light Mode
  await page.evaluate(() => {
    localStorage.setItem('color-theme', 'light');
    document.documentElement.classList.remove('dark');
    const scrollEl = document.querySelector('main') || window;
    scrollEl.scrollTo(0, 0);
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(500);

  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/3a78f02b-1951-4cb0-a740-1399cf79289b/comments_tab_light_feed.png',
    fullPage: false
  });
});
