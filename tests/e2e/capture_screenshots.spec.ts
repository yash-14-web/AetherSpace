import { test } from '@playwright/test';

test('Capture visual screenshots of all 4 resolved time tracking defects', async ({ page }) => {
  // Login
  await page.goto('/auth/login/');
  await page.fill('#login-contributor-id', 'e2e_timetracker@aetherspace.dev');
  await page.fill('#login-password', 'Password123!');
  await page.click('button[type="submit"]');
  await page.waitForURL((url: URL) => !url.pathname.includes('/auth/login/'), { timeout: 15000 }).catch(() => {});

  // Go to Timesheet Dashboard
  await page.setViewportSize({ width: 1440, height: 950 });
  await page.goto('/timetracking/w/aetherspace-core/');
  await page.waitForLoadState('networkidle');

  // Defect 1: Active Timer — Task Selector Layout (In-flow accordion, no circular timer/description overlap)
  await page.getByTestId('active-timer-task-selector').click();
  await page.waitForSelector('[data-testid="active-timer-task-dropdown"]', { state: 'visible', timeout: 5000 });
  await page.waitForTimeout(300);

  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/535e0b22-5b14-4eef-aa57-2b2ed1427168/defect1_active_timer_task_selector_inflow.png',
    fullPage: false
  });

  // Select defect B-363855 to close selector
  const bugOption = page.getByTestId('active-timer-bug-B-363855');
  if (await bugOption.isVisible()) {
    await bugOption.click();
  } else {
    await page.getByTestId('active-timer-task-selector').click();
  }

  // Defect 2: Work Item Association & Entry Source ("Timer Entry" vs "Manual Entry" pills)
  const timesheetSection = page.locator('#timesheet-section');
  await timesheetSection.scrollIntoViewIfNeeded();
  await page.waitForTimeout(300);

  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/535e0b22-5b14-4eef-aa57-2b2ed1427168/defect2_work_item_and_entry_source.png',
    fullPage: false
  });

  // Defect 3: View Day — Functional Day View with Detailed Day Banner and Day Navigation
  await page.getByTestId('view-day-btn').click();
  await page.waitForURL((url: URL) => url.search.includes('date_range=today'), { timeout: 8000 });
  await page.waitForSelector('[data-testid="detailed-day-view-banner"]', { state: 'visible', timeout: 5000 });
  await page.waitForTimeout(400);

  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/535e0b22-5b14-4eef-aa57-2b2ed1427168/defect3_view_day_banner_and_nav.png',
    fullPage: false
  });

  // Defect 4: Rich Text — Bullet and Numbered Lists in modal preview and timesheet
  await page.getByTestId('log-time-manually-btn').click();
  await page.waitForSelector('#modal-work-description', { state: 'visible', timeout: 5000 });
  await page.locator('#modal-work-description').fill('### Quality Assurance Checklist\n- Validated **in-flow selector** layout\n- Confirmed `B-363855` defect bug fix category\n1. Run Playwright E2E test suite\n2. Inspect rich-text lists');
  await page.getByTestId('toggle-markdown-preview-btn').click();
  await page.waitForSelector('[data-testid="modal-markdown-preview-container"]', { state: 'visible', timeout: 5000 });
  await page.waitForTimeout(400);

  await page.screenshot({
    path: 'C:/Users/M.Yaswanth/.gemini/antigravity-ide/brain/535e0b22-5b14-4eef-aa57-2b2ed1427168/defect4_rich_text_lists_preview.png',
    fullPage: false
  });
});

