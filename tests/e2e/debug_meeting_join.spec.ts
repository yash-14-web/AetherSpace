import { test, expect, chromium } from '@playwright/test';

test('Verify meeting join transitions into conference and handles prejoin/errors', async () => {
  const browser = await chromium.launch({
    args: [
      '--use-fake-ui-for-media-stream',
      '--use-fake-device-for-media-stream',
    ]
  });
  const context = await browser.newContext({
    permissions: ['camera', 'microphone'],
  });
  const page = await context.newPage();

  page.on('console', msg => console.log(`[BROWSER CONSOLE ${msg.type()}]:`, msg.text()));
  page.on('pageerror', err => console.log(`[PAGE ERROR]:`, err.message));

  // 1. Login
  await page.goto('http://127.0.0.1:8000/auth/login/');
  await page.fill('#login-contributor-id', 'e2e_timetracker@aetherspace.dev');
  await page.fill('#login-password', 'Password123!');
  await page.click('button[type="submit"]');
  await page.waitForURL(url => !url.pathname.includes('/auth/login/'), { timeout: 15000 }).catch(() => {});

  // 2. Start a fresh live meeting
  await page.goto('http://127.0.0.1:8000/meetings/w/aetherspace-core/start/');
  await page.click('button[type="submit"]');
  await page.waitForURL(url => url.pathname.includes('/room/'), { timeout: 15000 }).catch(() => {});
  console.log('Meeting room URL:', page.url());

  // 3. Wait for the loading overlay to dismiss (either prejoinScreenLoaded or videoConferenceJoined)
  const loadingContainer = page.locator('#jitsi-loading-container');
  await expect(loadingContainer).toBeHidden({ timeout: 20000 });
  console.log('SUCCESS: #jitsi-loading-container is hidden!');

  // Take screenshot of the loaded media canvas (prejoin or connected)
  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/3a78f02b-1951-4cb0-a740-1399cf79289b/meeting_join_success.png',
    fullPage: false
  });

  // Verify that iframe is present and visible
  const iframe = page.locator('#jitsi-meet-container iframe');
  await expect(iframe).toBeVisible();
  console.log('SUCCESS: Jitsi iframe is visible and interactive!');

  await browser.close();
});
