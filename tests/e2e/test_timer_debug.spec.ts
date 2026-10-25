import { test } from '@playwright/test';

test('Debug timer network request and console errors', async ({ page }) => {
  const requests: any[] = [];
  const responses: any[] = [];
  const consoleMessages: string[] = [];

  page.on('console', msg => {
    console.log(`[CONSOLE ${msg.type()}] ${msg.text()}`);
  });

  page.on('request', req => {
    if (req.url().includes('/timer/')) {
      console.log(`[REQ] ${req.method()} ${req.url()} data: ${req.postData()}`);
    }
  });

  page.on('response', async res => {
    if (res.url().includes('/timer/')) {
      let body = '';
      try {
        body = await res.text();
      } catch (e) {}
      console.log(`[RES] ${res.status()} ${res.url()} -> ${body.slice(0, 300)}`);
    }
  });

  // 1. Login
  await page.goto('http://127.0.0.1:8000/auth/login/');
  await page.fill('#login-contributor-id', 'e2e_timetracker@aetherspace.dev');
  await page.fill('#login-password', 'Password123!');
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.includes('/auth/login/'), { timeout: 15000 }).catch(() => {});

  // 2. Navigate to task detail overview
  await page.goto('http://127.0.0.1:8000/tasks/w/aetherspace-core/156656/?tab=overview');
  await page.waitForTimeout(1000);

  // 3. Find timer button
  console.log('--- Clicking Start Timer ---');
  const timerBtn = page.locator('button[title*="Timer"], button:has-text("Start Timer")').first();
  await timerBtn.click();
  await page.waitForTimeout(1500);

  console.log('--- Clicking Pause Timer ---');
  const pauseBtn = page.locator('button[title*="Pause Timer"]').first();
  await pauseBtn.click();
  await page.waitForTimeout(1500);

  console.log('--- Clicking Resume Timer ---');
  const resumeBtn = page.locator('button[title*="Start Timer"], button[title*="Resume Timer"]').first();
  await resumeBtn.click();
  await page.waitForTimeout(1500);

  console.log('--- Clicking Stop Timer ---');
  const stopBtn = page.locator('button[title*="Stop & Save Time Entry"]').first();
  await stopBtn.click();
  await page.waitForTimeout(2000);

  console.log('=== CONSOLE MESSAGES ===');
  consoleMessages.forEach(m => console.log(m));

  console.log('=== RESPONSES ===');
  responses.forEach(r => console.log(JSON.stringify(r, null, 2)));
});
