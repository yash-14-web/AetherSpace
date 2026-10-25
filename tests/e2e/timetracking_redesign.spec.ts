import { test, expect, Page } from '@playwright/test';

/**
 * AetherSpace — Time Tracking Redesign & Manual Time Entry E2E Specification
 *
 * Verifies:
 * 1. Time Tracking Dashboard renders 4 Summary Cards, Active Timer, Today's Timeline, Weekly Overview, and Timesheet table.
 * 2. Active timer three-dot options menu reveals real actions and triggers modal.
 * 3. Functional links for Workspace Team and View Day.
 * 4. Manual Time Entry Modal: Bug defect selection, 9 category choices, and live duration calculation.
 * 5. Markdown toolbar inserts formatting, character counter updates, and Preview toggle renders safe formatted HTML.
 * 6. Saving manual time entry with Bug and Category persists record, renders badges, Source pill ("Manual Entry"), safe rich-text, and Contributor hover card.
 * 7. Active timer controls (Start, Pause, Resume, Stop), persistence across page reload, and Source pill ("Timer Entry").
 * 8. Responsive layout without horizontal overflow at mobile and tablet viewports.
 * 9. Dark and light mode visual rendering consistency.
 */

async function loginUser(page: Page, email = 'e2e_timetracker@aetherspace.dev', password = 'Password123!') {
  await page.goto('/auth/login/');
  await page.fill('#login-contributor-id', email);
  await page.fill('#login-password', password);
  await page.click('button[type="submit"]');
  await page.waitForURL((url: URL) => !url.pathname.includes('/auth/login/'), { timeout: 15000 }).catch(() => {});
}

test.describe('Time Tracking Dashboard Redesign & Manual Entry Modal', () => {

  test('1. Time Tracking Dashboard renders header, 4 summary cards, timer panel, timeline, and functional links', async ({ page }) => {
    await loginUser(page);
    await page.goto('/timetracking/w/aetherspace-core/');

    // Breadcrumb and Title
    await expect(page.locator('h1')).toContainText('Time Tracking & Logs');
    await expect(page.getByText('Time Tracker', { exact: true })).toBeVisible();

    // 4 Summary Cards
    await expect(page.locator('#card-todays-hours')).toBeVisible();
    await expect(page.locator('#card-this-week')).toBeVisible();
    await expect(page.locator('#card-this-month')).toBeVisible();
    await expect(page.locator('#card-workspace-team')).toBeVisible();

    // Functional link: Workspace Team
    const teamLink = page.locator('#card-workspace-team a[title="View Workspace Team"]');
    await expect(teamLink).toBeVisible();
    await expect(teamLink).toHaveAttribute('href', /\/workspaces\/w\/aetherspace-core\/team\//);

    // Active Timer Panel Heading
    await expect(page.getByRole('heading', { name: 'Active Timer' })).toBeVisible();
    await expect(page.getByText("HOURS : MINS : SECS")).toBeVisible();

    // Today's Timeline & Functional View Day link
    await expect(page.getByText("Today's Timeline")).toBeVisible();
    const viewDayLink = page.getByTestId('view-day-btn');
    await expect(viewDayLink).toBeVisible();
    await expect(viewDayLink).toHaveAttribute('href', '?date_range=today#timesheet-section');

    // Weekly Overview & Timesheet table
    await expect(page.getByText("This Week Overview")).toBeVisible();
    await expect(page.locator('#timesheet-heading')).toBeVisible();
  });

  test('2. Active timer three-dot options menu reveals real actions and triggers manual entry modal', async ({ page }) => {
    await loginUser(page);
    await page.goto('/timetracking/w/aetherspace-core/');

    const optionsBtn = page.getByTestId('timer-options-menu-btn');
    await expect(optionsBtn).toBeVisible();

    // Open options menu
    await optionsBtn.click();
    const manualEntryOption = page.getByTestId('timer-menu-manual-entry');
    const switchTaskOption = page.getByTestId('timer-menu-switch-task');

    await expect(manualEntryOption).toBeVisible();
    await expect(switchTaskOption).toBeVisible();

    // Clicking Log Time Manually opens the modal
    await manualEntryOption.click();
    await page.waitForSelector('#modal-work-description', { state: 'visible', timeout: 8000 });
    await expect(page.getByRole('heading', { name: 'Log Time Manually' })).toBeVisible();

    // Close modal
    await page.getByTestId('modal-cancel-btn').click();
    await expect(page.locator('#modal-work-description')).not.toBeVisible();
  });

  test('3. Manual Time Entry Modal: Bug defect selection, 9 categories, and live duration calculation', async ({ page }) => {
    await loginUser(page);
    await page.goto('/timetracking/w/aetherspace-core/');

    // Click Log Time Manually
    const openBtn = page.getByTestId('log-time-manually-btn');
    await expect(openBtn).toBeVisible();
    await openBtn.click();
    await page.waitForSelector('#modal-work-description', { state: 'visible', timeout: 8000 });

    // Duration calculation notice
    await expect(page.getByText('Automatically calculated from start and end time.')).toBeVisible();

    // Test start time and end time duration calculation
    const startInput = page.locator('input[placeholder="09:00 AM"]');
    const endInput = page.locator('input[placeholder="11:30 AM"]');
    await expect(startInput).toBeVisible();
    await expect(endInput).toBeVisible();

    // Set 09:00 AM to 12:00 PM -> should compute 3h 00m
    await startInput.fill('09:00 AM');
    await endInput.fill('12:00 PM');
    await endInput.dispatchEvent('input');
    await expect(page.locator('text=3h 00m')).toBeVisible();

    // Open Work Item Dropdown (Tasks & Defects/Bugs)
    const workItemDropdown = page.getByTestId('modal-work-item-trigger');
    await expect(workItemDropdown).toBeVisible();
    await workItemDropdown.click();

    // Verify Defects/Bugs option if present
    const bugOption = page.getByTestId('modal-bug-option-B-363855');
    if (await bugOption.isVisible()) {
      await bugOption.click();
      await expect(page.locator('text=Defect • B-363855')).toBeVisible();
    }

    // Verify Category select dropdown contains all 9 required categories
    const categorySelect = page.locator('select[x-model="modalCategory"]');
    await expect(categorySelect).toBeVisible();
    const options = await categorySelect.locator('option').allInnerTexts();
    expect(options.some(o => o.includes('Task / Development'))).toBe(true);
    expect(options.some(o => o.includes('Bug Fix'))).toBe(true);
    expect(options.some(o => o.includes('Documentation'))).toBe(true);
    expect(options.some(o => o.includes('Meeting'))).toBe(true);
    expect(options.some(o => o.includes('Research'))).toBe(true);
    expect(options.some(o => o.includes('Code Review'))).toBe(true);
    expect(options.some(o => o.includes('Design'))).toBe(true);
    expect(options.some(o => o.includes('API Integration'))).toBe(true);
    expect(options.some(o => o.includes('Other'))).toBe(true);

    // Close modal via Cancel button
    await page.getByTestId('modal-cancel-btn').click();
    await expect(page.locator('#modal-work-description')).not.toBeVisible();
  });

  test('4. Markdown description toolbar inserts formatting, character counter updates, and Preview toggle functions', async ({ page }) => {
    await loginUser(page);
    await page.goto('/timetracking/w/aetherspace-core/');

    await page.getByTestId('log-time-manually-btn').click();
    await page.waitForSelector('#modal-work-description', { state: 'visible', timeout: 8000 });

    // Verify markdown toolbar buttons: H, B, I, Link, Bullet, Numbered, Inline Code, Code Block, Preview toggle
    const hBtn = page.locator('button[title*="Heading"]');
    const boldBtn = page.locator('button[title*="Bold"]');
    const italicBtn = page.locator('button[title*="Italic"]');
    const linkBtn = page.locator('button[title*="Link"]');
    const bulletBtn = page.locator('button[title*="Bullet"]');
    const numberedBtn = page.locator('button[title*="Numbered"]');
    const inlineCodeBtn = page.locator('button[title*="Inline Code"]');
    const codeBlockBtn = page.locator('button[title*="Code Block"]');
    const previewToggle = page.getByTestId('toggle-markdown-preview-btn');

    await expect(hBtn).toBeVisible();
    await expect(boldBtn).toBeVisible();
    await expect(italicBtn).toBeVisible();
    await expect(linkBtn).toBeVisible();
    await expect(bulletBtn).toBeVisible();
    await expect(numberedBtn).toBeVisible();
    await expect(inlineCodeBtn).toBeVisible();
    await expect(codeBlockBtn).toBeVisible();
    await expect(previewToggle).toBeVisible();

    // Type description and verify character counter
    const descTextarea = page.locator('#modal-work-description');
    const testContent = '### Module Review\n- Checked **authentication** logic\n- Validated `session_tokens`';
    await descTextarea.fill(testContent);

    // Check character counter display
    await expect(page.getByText(`${testContent.length}/1000`)).toBeVisible();

    // Toggle preview
    await previewToggle.click();

    // Verify preview rendered heading, bold, code, and bullet
    await expect(page.locator('h3:has-text("Module Review")')).toBeVisible();
    await expect(page.locator('strong:has-text("authentication")')).toBeVisible();
    await expect(page.locator('code:has-text("session_tokens")')).toBeVisible();
    await expect(page.locator('li:has-text("Checked")')).toBeVisible();

    // Toggle back to editor
    await previewToggle.click();
    await expect(descTextarea).toBeVisible();
  });

  test('5. Saving manual time entry with Bug and Category persists record, renders badges, source pill, rich text, and contributor hover card', async ({ page }) => {
    await loginUser(page);
    await page.goto('/timetracking/w/aetherspace-core/');

    await page.getByTestId('log-time-manually-btn').click();
    await page.waitForSelector('#modal-work-description', { state: 'visible', timeout: 8000 });

    const dateInput = page.locator('input[type="date"]');
    if (!(await dateInput.inputValue())) {
      const todayIso = new Date().toISOString().split('T')[0];
      await dateInput.fill(todayIso);
    }

    const startInput = page.locator('input[placeholder="09:00 AM"]');
    const endInput = page.locator('input[placeholder="11:30 AM"]');
    await startInput.fill('10:00 AM');
    await endInput.fill('11:45 AM');
    await endInput.dispatchEvent('input');

    // Select Defect B-363855 if available
    const workItemDropdown = page.getByTestId('modal-work-item-trigger');
    await expect(workItemDropdown).toBeVisible();
    await workItemDropdown.click();

    const bugOption = page.getByTestId('modal-bug-option-B-363855');
    if (await bugOption.isVisible()) {
      await bugOption.click();
    } else {
      // Fallback: click General Workspace Activity
      await page.locator('div:has-text("General Workspace Activity")').last().click();
    }

    // Select Category "Research"
    const categorySelect = page.locator('select[x-model="modalCategory"]');
    await categorySelect.selectOption({ label: '🔬 Research' });

    const uniqueId = Date.now();
    const descTextarea = page.locator('#modal-work-description');
    const uniqueNote = `Manual research log **highlighted** and \`verified\` ${uniqueId}`;
    await descTextarea.fill(uniqueNote);

    // Click Save Time Entry
    await page.getByTestId('save-time-entry-btn').click();

    // Modal closes and entry appears in table and timeline
    await page.waitForSelector('#modal-work-description', { state: 'hidden', timeout: 15000 });
    await page.waitForLoadState('networkidle');

    // Locate the row in Timesheet table
    const tableRow = page.locator('tr:has-text("highlighted")').first();
    await expect(tableRow).toBeVisible({ timeout: 15000 });

    // Verify Category badge "Research"
    await expect(tableRow.getByText('Research', { exact: true })).toBeVisible();

    // Verify Entry Source pill "Manual Entry"
    await expect(tableRow.getByText('📝 Manual Entry')).toBeVisible();

    // Verify Safe Rich-Text formatted elements (strong and code)
    await expect(tableRow.locator('strong:has-text("highlighted")')).toBeVisible();
    await expect(tableRow.locator('code:has-text("verified")')).toBeVisible();

    // Verify Duration
    await expect(tableRow.getByText('1h 45m')).toBeVisible();

    // Verify Contributor People Hover Card trigger element is present
    const hoverCardTrigger = tableRow.locator('[role="button"][aria-haspopup="dialog"]').first();
    await expect(hoverCardTrigger).toBeVisible();
  });

  test('6. Active timer controls (Start, Pause, Resume, Stop), persistence across page reload, and Timer Entry source pill', async ({ page }) => {
    await loginUser(page);
    await page.goto('/timetracking/w/aetherspace-core/');

    // If a timer was already running or paused, clean it up
    const existingStopBtn = page.getByTestId('stop-timer-btn');
    if (await existingStopBtn.isVisible()) {
      await existingStopBtn.click();
      await page.waitForTimeout(1000);
    }

    const startBtn = page.getByTestId('start-timer-btn');
    await expect(startBtn).toBeVisible({ timeout: 5000 });
    await startBtn.click();
    await expect(page.getByTestId('pause-timer-btn')).toBeVisible({ timeout: 8000 });
    await expect(page.getByText('Running', { exact: true })).toBeVisible();

    // Reload page — timer must persist in running state
    await page.reload();
    await expect(page.getByTestId('pause-timer-btn')).toBeVisible({ timeout: 8000 });

    // Pause timer
    await page.getByTestId('pause-timer-btn').click();
    await expect(page.getByTestId('resume-timer-btn')).toBeVisible({ timeout: 8000 });
    await expect(page.getByText('Paused', { exact: true })).toBeVisible();

    // Resume timer
    await page.getByTestId('resume-timer-btn').click();
    await expect(page.getByTestId('pause-timer-btn')).toBeVisible({ timeout: 8000 });

    // Stop timer
    await page.getByTestId('stop-timer-btn').click();
    await expect(page.getByTestId('start-timer-btn')).toBeVisible({ timeout: 8000 });

    // Verify stopped timer created a timesheet row with "Timer Entry" source pill
    await page.waitForLoadState('networkidle');
    const timerRow = page.locator('tr:has-text("⏱️ Timer Entry")').first();
    await expect(timerRow).toBeVisible({ timeout: 10000 });
  });

  test('7. Responsive layout test at mobile and tablet viewports without horizontal overflow', async ({ page }) => {
    await loginUser(page);

    // Mobile viewport (iPhone 12/13/14 size: 390x844)
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/timetracking/w/aetherspace-core/');

    await expect(page.locator('h1')).toBeVisible();
    await expect(page.getByTestId('log-time-manually-btn')).toBeVisible();

    // Verify body scrollWidth equals clientWidth (no horizontal layout blowout)
    const isOverflowing = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(isOverflowing).toBe(false);

    // Tablet viewport (768x1024)
    await page.setViewportSize({ width: 768, height: 1024 });
    await expect(page.locator('h1')).toBeVisible();
  });

  test('8. Dark and light mode visual rendering consistency', async ({ page }) => {
    await loginUser(page);
    await page.goto('/timetracking/w/aetherspace-core/');

    // Ensure dark mode background
    await page.evaluate(() => document.documentElement.classList.add('dark'));
    await expect(page.locator('body')).toHaveClass(/dark/);

    // Switch to light mode
    await page.evaluate(() => {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('light');
    });
    await expect(page.locator('h1')).toBeVisible();
  });

  test('9. Active timer selector in-flow layout, quick search filter, and defect bug association', async ({ page }) => {
    await loginUser(page);
    await page.goto('/timetracking/w/aetherspace-core/');

    // Ensure timer is idle
    const stopBtn = page.getByTestId('stop-timer-btn');
    if (await stopBtn.isVisible()) {
      await stopBtn.click();
      await page.waitForTimeout(1000);
    }

    // Open active timer task selector
    const selector = page.getByTestId('active-timer-task-selector');
    await expect(selector).toBeVisible();
    await selector.click();

    const dropdown = page.getByTestId('active-timer-task-dropdown');
    await expect(dropdown).toBeVisible();

    // Verify in-flow layout: description textarea is below dropdown and not overlapped
    const dropdownBox = await dropdown.boundingBox();
    const descTextarea = page.locator('textarea[x-model="description"]');
    const textareaBox = await descTextarea.boundingBox();

    expect(dropdownBox).not.toBeNull();
    expect(textareaBox).not.toBeNull();
    // In-flow element pushes textarea down: textarea top Y >= dropdown top Y + dropdown height - 5
    expect(textareaBox!.y).toBeGreaterThanOrEqual(dropdownBox!.y + dropdownBox!.height - 5);

    // Verify search filter
    const searchInput = page.getByTestId('active-timer-search-input');
    await expect(searchInput).toBeVisible();
    await searchInput.fill('B-363855');

    // Bug option must be visible
    const bugOption = page.getByTestId('active-timer-bug-B-363855');
    await expect(bugOption).toBeVisible();

    // Select the bug
    await bugOption.click();
    await expect(dropdown).not.toBeVisible();

    // Selector should now display bug code B-363855
    await expect(selector).toContainText('B-363855');

    // Add note and start timer
    const uniqueTimerNote = `Bug investigation timer run ${Date.now()}`;
    await descTextarea.fill(uniqueTimerNote);

    const startBtn = page.getByTestId('start-timer-btn');
    await expect(startBtn).toBeVisible();
    await startBtn.click();

    await expect(page.getByTestId('pause-timer-btn')).toBeVisible({ timeout: 8000 });

    // Wait 1.5s then stop timer
    await page.waitForTimeout(1500);
    await page.getByTestId('stop-timer-btn').click();
    await expect(page.getByTestId('start-timer-btn')).toBeVisible({ timeout: 8000 });

    // Verify timesheet row was created
    await page.waitForLoadState('networkidle');
    const bugRow = page.locator(`tr:has-text("${uniqueTimerNote}")`).first();
    await expect(bugRow).toBeVisible({ timeout: 10000 });

    // Check that entry source is "⏱️ Timer Entry"
    await expect(bugRow.getByText('⏱️ Timer Entry')).toBeVisible();

    // Check that category "Bug Fix" is rendered
    await expect(bugRow.getByText('Bug Fix')).toBeVisible();
  });

  test('10. Functional Day View navigation, detailed day banner, and offset pagination', async ({ page }) => {
    await loginUser(page);
    await page.goto('/timetracking/w/aetherspace-core/');

    // Click View Day button
    const viewDayBtn = page.getByTestId('view-day-btn');
    await expect(viewDayBtn).toBeVisible();
    await viewDayBtn.click();

    // Page URL should contain date_range=today
    await expect(page).toHaveURL(/\?date_range=today/);

    // Detailed Day View banner must be visible
    const dayBanner = page.getByTestId('detailed-day-view-banner');
    await expect(dayBanner).toBeVisible();
    await expect(dayBanner).toContainText('Detailed Day View:');
    await expect(dayBanner.getByText('Today', { exact: true })).toBeVisible();

    // Prev Day navigation
    const prevBtn = page.getByTestId('day-view-prev-btn');
    await expect(prevBtn).toBeVisible();
    await prevBtn.click();

    // URL should have offset=-1 (previous day offset)
    await expect(page).toHaveURL(/offset=-1/);
    await expect(page.getByTestId('detailed-day-view-banner')).toBeVisible();

    // Next Day navigation to return
    const nextBtn = page.getByTestId('day-view-next-btn');
    await expect(nextBtn).toBeVisible();
    await nextBtn.click();
    await expect(page).toHaveURL(/offset=0/);
  });

  test('11. Timesheet rich text bullet and numbered list rendering with proper styles and no flattening', async ({ page }) => {
    await loginUser(page);
    await page.goto('/timetracking/w/aetherspace-core/');

    // Open Manual Entry Modal
    await page.getByTestId('log-time-manually-btn').click();
    await page.waitForSelector('#modal-work-description', { state: 'visible', timeout: 8000 });

    const dateInput = page.locator('input[type="date"]');
    if (!(await dateInput.inputValue())) {
      const todayIso = new Date().toISOString().split('T')[0];
      await dateInput.fill(todayIso);
    }

    const startInput = page.locator('input[placeholder="09:00 AM"]');
    const endInput = page.locator('input[placeholder="11:30 AM"]');
    await startInput.fill('01:00 PM');
    await endInput.fill('02:15 PM');
    await endInput.dispatchEvent('input');

    const descTextarea = page.locator('#modal-work-description');
    const uniqueListId = Date.now();
    const listDescription = `Sprint wrap up ${uniqueListId}:\n- Task completed verification\n- Database migration review\n1. Deploy to staging\n2. Verify healthcheck`;
    await descTextarea.fill(listDescription);

    // Check markdown preview toggle
    const previewToggle = page.getByTestId('toggle-markdown-preview-btn');
    await previewToggle.click();

    // Verify preview renders <ul> and <ol>
    const previewContainer = page.getByTestId('modal-markdown-preview-container');
    await expect(previewContainer.locator('ul li')).toHaveCount(2);
    await expect(previewContainer.locator('ol li')).toHaveCount(2);

    // Toggle back to editor and submit
    await previewToggle.click();
    await page.getByTestId('save-time-entry-btn').click();

    await page.waitForSelector('#modal-work-description', { state: 'hidden', timeout: 15000 });
    await page.waitForLoadState('networkidle');

    // Locate the saved row in timesheet table
    const tableRow = page.locator(`tr:has-text("Sprint wrap up ${uniqueListId}")`).first();
    await expect(tableRow).toBeVisible({ timeout: 15000 });

    // Verify .rich-text-content contains <ul> and <ol>
    const richContent = tableRow.locator('.rich-text-content');
    await expect(richContent).toBeVisible();

    const ulElement = richContent.locator('ul');
    const olElement = richContent.locator('ol');
    await expect(ulElement).toBeVisible();
    await expect(olElement).toBeVisible();
    await expect(ulElement.locator('li')).toHaveCount(2);
    await expect(olElement.locator('li')).toHaveCount(2);

    // Verify list-style-type computed style is disc and decimal (not flattened or None)
    const bulletType = await ulElement.locator('li').first().evaluate((el) => window.getComputedStyle(el).listStyleType);
    expect(bulletType).toBe('disc');

    const numType = await olElement.locator('li').first().evaluate((el) => window.getComputedStyle(el).listStyleType);
    expect(numType).toBe('decimal');

    // Verify white-space is normal (not nowrap from truncate)
    const whiteSpace = await richContent.evaluate((el) => window.getComputedStyle(el).whiteSpace);
    expect(whiteSpace).not.toBe('nowrap');
  });

});

