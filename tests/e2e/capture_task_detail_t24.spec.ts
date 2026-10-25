import { test } from '@playwright/test';

test.setTimeout(120000);

test('Capture 7-tab Task Detail in Dark and Light mode + Mobile', async ({ page }) => {
  // Login
  await page.goto('http://127.0.0.1:8000/auth/login/');
  await page.fill('#login-contributor-id', 'e2e_timetracker@aetherspace.dev');
  await page.fill('#login-password', 'Password123!');
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.includes('/auth/login/'), { timeout: 15000 }).catch(() => {});

  const tabs = [
    { name: 'overview', file: 'tab1_overview' },
    { name: 'subtasks', file: 'tab2_subtasks' },
    { name: 'attachments', file: 'tab3_attachments' },
    { name: 'code_reviews', file: 'tab4_code_reviews' },
    { name: 'comments', file: 'tab5_comments' },
    { name: 'defects', file: 'tab6_defects' },
    { name: 'activity', file: 'tab7_activity' }
  ];

  // 1. DESKTOP OBSIDIAN DARK
  await page.setViewportSize({ width: 1440, height: 900 });
  for (const t of tabs) {
    await page.goto(`http://127.0.0.1:8000/tasks/w/aetherspace-core/156656/?tab=${t.name}`);
    await page.evaluate(() => {
      localStorage.setItem('color-theme', 'dark');
      document.documentElement.classList.add('dark');
    });
    await page.waitForTimeout(200);
    await page.screenshot({
      path: `C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/3a78f02b-1951-4cb0-a740-1399cf79289b/desktop_dark_${t.file}.png`,
      fullPage: false
    });
  }

  // 2. DESKTOP CLEAN SLATE LIGHT
  for (const t of tabs) {
    await page.goto(`http://127.0.0.1:8000/tasks/w/aetherspace-core/156656/?tab=${t.name}`);
    await page.evaluate(() => {
      localStorage.setItem('color-theme', 'light');
      document.documentElement.classList.remove('dark');
    });
    await page.waitForTimeout(200);
    await page.screenshot({
      path: `C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/3a78f02b-1951-4cb0-a740-1399cf79289b/desktop_light_${t.file}.png`,
      fullPage: false
    });
  }

  // 3. MOBILE VIEWPORT (iPhone 14 Pro: 393 x 852)
  await page.setViewportSize({ width: 393, height: 852 });
  // Dark Mobile Overview, Subtasks, Attachments
  for (const t of tabs.slice(0, 3)) {
    await page.goto(`http://127.0.0.1:8000/tasks/w/aetherspace-core/156656/?tab=${t.name}`);
    await page.evaluate(() => {
      localStorage.setItem('color-theme', 'dark');
      document.documentElement.classList.add('dark');
    });
    await page.waitForTimeout(200);
    await page.screenshot({
      path: `C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/3a78f02b-1951-4cb0-a740-1399cf79289b/mobile_dark_${t.file}.png`,
      fullPage: false
    });
  }

  // Scroll down to capture Time Tracking card in Dark & Light modes
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('http://127.0.0.1:8000/tasks/w/aetherspace-core/156656/?tab=overview');
  await page.evaluate(() => {
    localStorage.setItem('color-theme', 'dark');
    document.documentElement.classList.add('dark');
    const scrollEl = document.querySelector('main') || window;
    scrollEl.scrollTo(0, 500);
  });
  await page.waitForTimeout(300);
  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/3a78f02b-1951-4cb0-a740-1399cf79289b/desktop_dark_overview_scrolled.png'
  });

  await page.evaluate(() => {
    localStorage.setItem('color-theme', 'light');
    document.documentElement.classList.remove('dark');
    const scrollEl = document.querySelector('main') || window;
    scrollEl.scrollTo(0, 500);
  });
  await page.waitForTimeout(300);
  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/3a78f02b-1951-4cb0-a740-1399cf79289b/desktop_light_overview_scrolled.png'
  });

  // Mobile scrolled captures
  await page.setViewportSize({ width: 393, height: 852 });
  await page.evaluate(() => {
    localStorage.setItem('color-theme', 'dark');
    document.documentElement.classList.add('dark');
    const scrollEl = document.querySelector('main') || window;
    scrollEl.scrollTo(0, 600);
  });
  await page.waitForTimeout(300);
  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/3a78f02b-1951-4cb0-a740-1399cf79289b/mobile_dark_overview_scrolled.png'
  });

  await page.evaluate(() => {
    localStorage.setItem('color-theme', 'light');
    document.documentElement.classList.remove('dark');
    const scrollEl = document.querySelector('main') || window;
    scrollEl.scrollTo(0, 600);
  });
  await page.waitForTimeout(300);
  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/3a78f02b-1951-4cb0-a740-1399cf79289b/mobile_light_overview_scrolled.png'
  });
});
