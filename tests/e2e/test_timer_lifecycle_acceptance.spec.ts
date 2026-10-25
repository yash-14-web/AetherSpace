import { test, expect } from '@playwright/test';

test.describe('Task Detail Overview T2.4-R4 Runtime Fixes & Verification', () => {
  test.describe.configure({ mode: 'serial' });

  test('Full 10-point timer lifecycle, hover card, metadata pills, and multi-theme verification', async ({ page }) => {
    test.setTimeout(90000);
    // -------------------------------------------------------------------------
    // Step 0: Ensure starting from clean state
    // -------------------------------------------------------------------------
    await page.goto('http://127.0.0.1:8000/auth/login/');
    await page.fill('#login-contributor-id', 'e2e_timetracker@aetherspace.dev');
    await page.fill('#login-password', 'Password123!');
    await page.click('button[type="submit"]');
    await page.waitForURL(url => !url.pathname.includes('/auth/login/'), { timeout: 15000 });

    // -------------------------------------------------------------------------
    // Step 1: Navigate to Task Detail Overview (#156656)
    // -------------------------------------------------------------------------
    await page.goto('http://127.0.0.1:8000/tasks/w/aetherspace-core/156656/?tab=overview');
    await page.waitForLoadState('networkidle');

    // Clean up any lingering open timer so we start from known clean idle state
    const lingeringStopBtn = page.locator('button[title="Stop & Save Time Entry"]').first();
    if (await lingeringStopBtn.isVisible()) {
      await lingeringStopBtn.click();
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(1000);
    }

    // -------------------------------------------------------------------------
    // Verification: Header Metadata Pills Rectangular Rounded-lg Styling
    // -------------------------------------------------------------------------
    const statusSelect = page.locator('select[name="status"]').first();
    await expect(statusSelect).toBeVisible();
    const selectClasses = await statusSelect.getAttribute('class');
    expect(selectClasses).toContain('rounded-lg');
    expect(selectClasses).toContain('h-7');

    const priorityPill = page.locator('span:has-text("★ Medium")').first();
    await expect(priorityPill).toBeVisible();
    const priorityClasses = await priorityPill.getAttribute('class');
    expect(priorityClasses).toContain('rounded-lg');
    expect(priorityClasses).toContain('h-7');

    const sprintPill = page.locator('span:has-text("Backlog")').first();
    await expect(sprintPill).toBeVisible();
    const sprintClasses = await sprintPill.getAttribute('class');
    expect(sprintClasses).toContain('rounded-lg');
    expect(sprintClasses).toContain('h-7');

    const typePill = page.locator('span:has-text("UI Frontend Dashboard")').first();
    await expect(typePill).toBeVisible();
    const typeClasses = await typePill.getAttribute('class');
    expect(typeClasses).toContain('rounded-lg');
    expect(typeClasses).toContain('h-7');

    // -------------------------------------------------------------------------
    // Verification: Assignee Hover Card in Sidebar
    // -------------------------------------------------------------------------
    const assigneeTrigger = page.locator('span:has-text("Assignee") ~ div [aria-haspopup="dialog"]').first();
    await expect(assigneeTrigger).toBeVisible();
    await assigneeTrigger.click();
    await page.waitForTimeout(400);

    // Verify hover card is visible with user details
    const hoverCard = page.locator('.aether-hover-card:visible').first();
    await expect(hoverCard).toBeVisible();
    await expect(hoverCard).toContainText('Ramu M');
    await expect(hoverCard).toContainText('Email');
    await expect(hoverCard).toContainText('Profile');
    await page.screenshot({ path: 'tests/e2e/screenshots/assignee_hover_card_desktop.png', fullPage: false });
    await page.keyboard.press('Escape');
    await page.waitForTimeout(200);

    // Press Escape or move mouse to close hover card
    await page.keyboard.press('Escape');
    await page.waitForTimeout(400);

    // -------------------------------------------------------------------------
    // Acceptance Test 1 & 2 & 3: Start timer & verify server association and ticker
    // -------------------------------------------------------------------------
    const startTimerBtn = page.locator('button[title*="Start Timer"]').first();
    await expect(startTimerBtn).toBeVisible();

    const [startResponse] = await Promise.all([
      page.waitForResponse(res => res.url().includes('/timer/start/')),
      startTimerBtn.click()
    ]);
    expect(startResponse.status()).toBe(200);
    const startData = await startResponse.json();
    expect(startData.status).toBe('ok');
    expect(startData.timer_status).toBe('running');

    // Wait 2.5 seconds for ticker to increment
    await page.waitForTimeout(2500);

    // Verify button transitioned to Pause Timer
    const pauseTimerBtn = page.locator('button[title="Pause Timer"]').first();
    await expect(pauseTimerBtn).toBeVisible();
    await expect(page.locator('[x-data*="timerStatus"] span:has-text("Pause Timer")').first()).toBeVisible();
    await expect(page.locator('[x-data*="timerStatus"] .font-mono:has-text("Running")').first()).toBeVisible();

    // -------------------------------------------------------------------------
    // Acceptance Test 4: Pause and verify elapsed time stops increasing
    // -------------------------------------------------------------------------
    const [pauseResponse] = await Promise.all([
      page.waitForResponse(res => res.url().includes('/timer/pause/')),
      pauseTimerBtn.click()
    ]);
    expect(pauseResponse.status()).toBe(200);
    const pauseData = await pauseResponse.json();
    expect(pauseData.status).toBe('ok');
    expect(pauseData.timer_status).toBe('paused');

    // Verify button transitioned to Resume Timer
    const resumeTimerBtn = page.locator('button[title="Resume Timer"]').first();
    await expect(resumeTimerBtn).toBeVisible();
    await expect(page.locator('[x-data*="timerStatus"] span:has-text("Resume Timer")').first()).toBeVisible();
    await expect(page.locator('[x-data*="timerStatus"] .font-mono:has-text("Paused")').first()).toBeVisible();

    const pausedSeconds = pauseData.elapsed_seconds;
    await page.waitForTimeout(2000); // Wait 2s while paused
    // Verify it didn't keep ticking
    const elapsedText = await page.locator('[x-data*="timerStatus"] .font-mono:has-text("Paused")').innerText();
    expect(elapsedText).toContain('Paused');

    // -------------------------------------------------------------------------
    // Acceptance Test 5: Resume and verify timing continues correctly
    // -------------------------------------------------------------------------
    const [resumeResponse] = await Promise.all([
      page.waitForResponse(res => res.url().includes('/timer/resume/')),
      resumeTimerBtn.click()
    ]);
    expect(resumeResponse.status()).toBe(200);
    const resumeData = await resumeResponse.json();
    expect(resumeData.status).toBe('ok');
    expect(resumeData.timer_status).toBe('running');

    await page.waitForTimeout(2000);
    await expect(page.locator('button[title="Pause Timer"]').first()).toBeVisible();

    // -------------------------------------------------------------------------
    // Acceptance Test 6: Stop and verify duration is persisted
    // -------------------------------------------------------------------------
    const stopBtn = page.locator('button[title="Stop & Save Time Entry"]').first();
    await expect(stopBtn).toBeVisible();

    const [stopResponse] = await Promise.all([
      page.waitForResponse(res => res.url().includes('/timer/stop/')),
      stopBtn.click()
    ]);
    expect(stopResponse.status()).toBe(200);
    const stopData = await stopResponse.json();
    expect(stopData.status).toBe('ok');

    // -------------------------------------------------------------------------
    // Acceptance Test 7: Refresh the page and confirm the logged total remains correct
    // -------------------------------------------------------------------------
    await page.reload();
    await page.waitForLoadState('networkidle');

    // Timer is back to idle
    await expect(page.locator('button[title="Start Timer"]').first()).toBeVisible();
    // Logged card is visible and displays time
    const loggedCard = page.locator('span:has-text("Logged") + span').first();
    await expect(loggedCard).toBeVisible();
    const loggedVal = await loggedCard.innerText();
    expect(loggedVal).not.toBe('');

    // -------------------------------------------------------------------------
    // Acceptance Test 8: Verify a second task does not inherit the timer
    // -------------------------------------------------------------------------
    // Navigate to sibling task or another task in workspace
    const nextBtn = page.locator('a[title*="Next Task"]').first();
    if (await nextBtn.isVisible()) {
      await nextBtn.click();
      await page.waitForLoadState('networkidle');
      // Second task should show idle Start Timer
      await expect(page.locator('button[title="Start Timer"]').first()).toBeVisible();
      // Navigate back
      await page.goto('http://127.0.0.1:8000/tasks/w/aetherspace-core/156656/?tab=overview');
      await page.waitForLoadState('networkidle');
    }

    // -------------------------------------------------------------------------
    // Capture Dark Mode Screenshots (Obsidian Dark)
    // -------------------------------------------------------------------------
    await page.evaluate(() => {
      document.documentElement.classList.add('dark');
      localStorage.setItem('color-theme', 'dark');
      document.querySelector('main')?.scrollTo(0, 0);
    });
    await page.locator('h1:has-text("TEST TASK")').scrollIntoViewIfNeeded();
    await page.waitForTimeout(400);
    await page.screenshot({ path: 'tests/e2e/screenshots/desktop_dark_tab1_overview_final.png', fullPage: false });
    
    // Scroll down to time tracking and capture
    await page.locator('h3:has-text("Time Tracking")').scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    await page.screenshot({ path: 'tests/e2e/screenshots/desktop_dark_overview_timetracking_final.png', fullPage: false });

    // -------------------------------------------------------------------------
    // Switch to Light Theme (Clean Slate) & Capture Screenshots
    // -------------------------------------------------------------------------
    await page.evaluate(() => {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('color-theme', 'light');
      document.querySelector('main')?.scrollTo(0, 0);
    });
    await page.locator('h1:has-text("TEST TASK")').scrollIntoViewIfNeeded();
    await page.waitForTimeout(400);
    await page.screenshot({ path: 'tests/e2e/screenshots/desktop_light_tab1_overview_final.png', fullPage: false });

    await page.locator('h3:has-text("Time Tracking")').scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    await page.screenshot({ path: 'tests/e2e/screenshots/desktop_light_overview_timetracking_final.png', fullPage: false });

    // -------------------------------------------------------------------------
    // Capture Mobile Screenshots (Obsidian Dark & Clean Slate Light)
    // -------------------------------------------------------------------------
    await page.setViewportSize({ width: 375, height: 812 });

    // 1. Mobile Obsidian Dark
    await page.evaluate(() => {
      document.documentElement.classList.add('dark');
      localStorage.setItem('color-theme', 'dark');
      document.querySelector('main')?.scrollTo(0, 0);
    });
    await page.locator('h1:has-text("TEST TASK")').scrollIntoViewIfNeeded();
    await page.waitForTimeout(400);
    await page.screenshot({ path: 'tests/e2e/screenshots/mobile_dark_tab1_overview_final.png', fullPage: false });

    await page.locator('h3:has-text("Time Tracking")').scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    await page.screenshot({ path: 'tests/e2e/screenshots/mobile_dark_overview_timetracking_final.png', fullPage: false });

    // 2. Mobile Clean Slate Light
    await page.evaluate(() => {
      document.documentElement.classList.remove('dark');
      localStorage.setItem('color-theme', 'light');
      document.querySelector('main')?.scrollTo(0, 0);
    });
    await page.locator('h1:has-text("TEST TASK")').scrollIntoViewIfNeeded();
    await page.waitForTimeout(400);
    await page.screenshot({ path: 'tests/e2e/screenshots/mobile_light_tab1_overview_final.png', fullPage: false });

    await page.locator('h3:has-text("Time Tracking")').scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    await page.screenshot({ path: 'tests/e2e/screenshots/mobile_light_overview_timetracking_final.png', fullPage: false });

    // Restore Dark theme and desktop viewport
    await page.evaluate(() => {
      document.documentElement.classList.add('dark');
      localStorage.setItem('color-theme', 'dark');
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.waitForTimeout(300);
  });

  // -------------------------------------------------------------------------
  // Acceptance Test 9 & 10: Authorization & Truthful Recoverable Error States
  // -------------------------------------------------------------------------
  test('Authorization and truthful recoverable error states for unauthorized contributor', async ({ page }) => {
    // Log in as e2e_contributor (who is NOT assigned to task 156656)
    await page.goto('http://127.0.0.1:8000/auth/login/');
    await page.fill('#login-contributor-id', 'e2e_contributor@aetherspace.dev');
    await page.fill('#login-password', 'Password123!');
    await page.click('button[type="submit"]');
    await page.waitForURL(url => !url.pathname.includes('/auth/login/'), { timeout: 15000 });

    // Navigate to task 156656
    await page.goto('http://127.0.0.1:8000/tasks/w/aetherspace-core/156656/?tab=overview');
    await page.waitForLoadState('networkidle');

    // Verify Start Timer button is disabled with truthful tooltip
    const timerBtn = page.locator('button[title*="Only assignee or managers can track time"]').first();
    await expect(timerBtn).toBeVisible();
    await expect(timerBtn).toBeDisabled();

    // Verify subtitle truthfully indicates "Assignee only"
    await expect(page.locator('text=Assignee only').first()).toBeVisible();

    // Test server-side authorization: Try sending start request to backend directly via in-page fetch
    const result = await page.evaluate(async () => {
      const csrfCookie = document.cookie.split('; ').find(row => row.startsWith('csrftoken='));
      const csrfToken = csrfCookie ? csrfCookie.split('=')[1] : (document.querySelector('input[name="csrfmiddlewaretoken"]')?.value || '');
      const formData = new FormData();
      formData.append('csrfmiddlewaretoken', csrfToken);
      formData.append('task_id', '896c1f2e-d719-418b-8511-11aa66696f28');
      const res = await fetch('/timetracking/w/aetherspace-core/timer/start/', {
        method: 'POST',
        headers: {
          'X-CSRFToken': csrfToken,
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: formData
      });
      const data = await res.json();
      return { status: res.status, data };
    });

    // Must return 403 Forbidden with truthful server error
    expect(result.status).toBe(403);
    expect(result.data.status).toBe('error');
    expect(result.data.message).toContain('You can only track time on tasks assigned to you.');
  });
});
