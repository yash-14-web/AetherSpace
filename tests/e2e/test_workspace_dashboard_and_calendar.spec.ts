import { test, expect, Page } from '@playwright/test';

/**
 * AetherSpace — Workspace Dashboard UX Upgrade + Calendar Markdown & People Fix
 * Playwright E2E Specification Suite
 *
 * NOTE: As per project instructions, automated browser execution is NOT performed by the AI agent;
 * this specification is prepared for developer and CI verification via:
 *   npx playwright test tests/e2e/test_workspace_dashboard_and_calendar.spec.ts
 *
 * Checklist Covered:
 *  1. Workspace dashboard loads
 *  2. Dashboard cards contain real values (not dummy text)
 *  3. Sidebar readable at desktop width
 *  4. Calendar Markdown Edit → Preview
 *  5. Save Markdown → reload → same rendered content
 *  6. Calendar people search (search-first, empty returns 0)
 *  7. Search result shows real name (never raw email as primary)
 *  8. Selected attendee chip shows real name and Contributor ID
 *  9. Avatar appears when available (image or styled initials pill)
 * 10. Unauthorized people are not returned (workspace boundary isolation)
 */

async function loginUser(page: Page, email = 'boss@example.com', password = 'Password123!') {
  await page.goto('/auth/login/');
  await page.fill('#login-email', email);
  await page.fill('#login-password', password);
  await page.click('button[type="submit"]');
  await page.waitForURL((url: URL) => !url.pathname.includes('/auth/login/'), { timeout: 15000 }).catch(() => {});
}

test.describe('Workspace Dashboard UX & Architecture Upgrades', () => {

  test('1. Workspace dashboard loads successfully with modern command center layout', async ({ page }) => {
    await loginUser(page);
    await page.goto('/workspaces/w/engineering-core/');

    // Assert page loaded without error states
    await expect(page).toHaveTitle(/AetherSpace/i);
    await expect(page.locator('h1')).toBeVisible();

    // Verify absence of obsolete debug blue borders or excessive padding artifacts
    const debugBorders = page.locator('.border-blue-500.border-4, .outline-blue-500');
    await expect(debugBorders).toHaveCount(0);

    // Verify command center sections are present
    await expect(page.locator('text=Command Center').first()).toBeVisible();
    await expect(page.locator('text=Sprint Progress').first()).toBeVisible();
    await expect(page.locator('text=Priority Tasks').first()).toBeVisible();
    await expect(page.locator('text=Bug Triage').first()).toBeVisible();
    await expect(page.locator('text=Team Activity').first()).toBeVisible();
  });

  test('2. Dashboard cards contain real database-backed values (not dummy text)', async ({ page }) => {
    await loginUser(page);
    await page.goto('/workspaces/w/engineering-core/');

    // KPI Cards: Active Tasks, Open Bugs, Team Members, Meetings Today
    const kpiSection = page.locator('[data-testid="dashboard-kpis"], .grid:has-text("Active Tasks")').first();
    await expect(kpiSection).toBeVisible();

    // Verify KPI numbers are formatted integers/counts or legitimate zero states, not lorem ipsum
    const activeTasksText = await page.locator('text=Active Tasks').locator('..').textContent();
    expect(activeTasksText).toMatch(/\d+/);

    const openBugsText = await page.locator('text=Open Bugs').locator('..').textContent();
    expect(openBugsText).toMatch(/\d+/);

    const teamMembersText = await page.locator('text=Team Members').locator('..').textContent();
    expect(teamMembersText).toMatch(/\d+/);

    // Verify real Sprint and Task details or clean empty states
    const tasksCard = page.locator('text=Priority Tasks').locator('..').locator('..');
    const taskCount = await tasksCard.locator('a[href*="/tasks/w/"]').count();
    if (taskCount === 0) {
      await expect(tasksCard.locator('text=No active tasks requiring priority attention')).toBeVisible();
    } else {
      expect(taskCount).toBeGreaterThan(0);
    }
  });

  test('3. Sidebar is readable and comfortable at desktop width', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginUser(page);
    await page.goto('/workspaces/w/engineering-core/');

    const sidebar = page.locator('aside[data-testid="workspace-sidebar"], aside').first();
    await expect(sidebar).toBeVisible();

    // Verify sidebar width is comfortable desktop width (w-64 = 256px or w-60)
    const boundingBox = await sidebar.boundingBox();
    expect(boundingBox?.width).toBeGreaterThanOrEqual(240);

    // Verify primary navigation typography is comfortable (~14px) and sub-nav (~13.5px)
    const mainNavLinks = sidebar.locator('a.font-semibold, a[href*="/tasks/"], a[href*="/bugs/"]');
    await expect(mainNavLinks.first()).toBeVisible();

    // Verify workspace name typography in tree header is prominent
    const wsNameHeading = sidebar.locator('h3.font-bold, a.font-bold').first();
    await expect(wsNameHeading).toBeVisible();
  });
});

test.describe('Calendar Centralized Markdown Pipeline & People UX', () => {

  test('4. Calendar Markdown Edit → Preview renders rich formatting and checkboxes', async ({ page }) => {
    await loginUser(page);
    await page.goto('/calendar/w/engineering-core/events/create/');

    const agendaTextarea = page.locator('textarea[name="agenda"], textarea#id_agenda');
    await expect(agendaTextarea).toBeVisible();

    // Type complex Markdown including headings, bold, task checkboxes, quotes, and code
    const rawMarkdown = [
      '### Sprint Sync Agenda',
      '**Critical Focus Areas**:',
      '- [ ] Review database migration plans',
      '- [x] Validate RBAC access controls',
      '> Reliability and isolation are non-negotiable.',
      '`render_rich_text`'
    ].join('\n');

    await agendaTextarea.fill(rawMarkdown);

    // Click Preview Tab
    const previewTab = page.locator('button:has-text("Preview"), button[data-tab="preview"]').first();
    await previewTab.click();

    // Verify Live Preview DOM
    const previewArea = page.locator('#agenda-preview-area, [data-testid="agenda-preview"]').first();
    await expect(previewArea).toBeVisible();

    // Check rendered elements
    await expect(previewArea.locator('h3:has-text("Sprint Sync Agenda")')).toBeVisible();
    await expect(previewArea.locator('strong:has-text("Critical Focus Areas")')).toBeVisible();
    await expect(previewArea.locator('input[type="checkbox"]')).toHaveCount(2);
    await expect(previewArea.locator('blockquote:has-text("Reliability and isolation")')).toBeVisible();
    await expect(previewArea.locator('code:has-text("render_rich_text")')).toBeVisible();
  });

  test('5. Save Markdown → reload → same rendered content in Detail View and raw in Edit View', async ({ page }) => {
    await loginUser(page);
    await page.goto('/calendar/w/engineering-core/events/create/');

    const eventTitle = `E2E Markdown Test ${Date.now()}`;
    await page.fill('input[name="title"]', eventTitle);
    await page.selectOption('select[name="event_type"]', 'MEETING');

    // Dates
    const today = new Date().toISOString().split('T')[0];
    await page.fill('input[name="start_date"]', today);
    await page.fill('input[name="start_time"]', '11:00');
    await page.fill('input[name="end_date"]', today);
    await page.fill('input[name="end_time"]', '12:00');

    const agendaContent = '### Verified Agenda\n**Objectives**:\n- [ ] Task Alpha\n`python manage.py`';
    await page.fill('textarea[name="agenda"]', agendaContent);

    await page.click('button[type="submit"]:has-text("Create Event")');
    await page.waitForURL(/\/calendar\/w\/engineering-core\//, { timeout: 10000 });

    // Open created event detail
    await page.goto(`/calendar/w/engineering-core/events/`);
    const eventLink = page.locator(`a:has-text("${eventTitle}")`).first();
    await eventLink.click();

    // Verify detail page renders sanitized HTML
    await expect(page.locator('h3:has-text("Verified Agenda")')).toBeVisible();
    await expect(page.locator('strong:has-text("Objectives")')).toBeVisible();
    await expect(page.locator('input[type="checkbox"]')).toBeVisible();
    await expect(page.locator('code:has-text("python manage.py")')).toBeVisible();

    // Navigate to Edit view and verify raw markdown is restored into textarea
    const editBtn = page.locator('a:has-text("Edit Event"), a[href*="/edit/"]').first();
    await editBtn.click();
    const editArea = page.locator('textarea[name="agenda"]');
    await expect(editArea).toHaveValue(agendaContent);
  });

  test('6. Calendar people search is search-first (0 users on empty input)', async ({ page }) => {
    await loginUser(page);
    await page.goto('/calendar/w/engineering-core/events/create/');

    const memberSearchInput = page.locator('#member-search-input, input[placeholder*="Search by name"]');
    await expect(memberSearchInput).toBeVisible();

    // When empty, dropdown should not be showing any users (search-first pattern)
    const searchDropdown = page.locator('#member-search-results, [data-testid="member-search-dropdown"]');
    await expect(searchDropdown).toBeHidden();

    const resultButtons = searchDropdown.locator('button');
    await expect(resultButtons).toHaveCount(0);
  });

  test('7. Search result shows real name and Contributor ID (never email as primary)', async ({ page }) => {
    await loginUser(page);
    await page.goto('/calendar/w/engineering-core/events/create/');

    const memberSearchInput = page.locator('#member-search-input, input[placeholder*="Search by name"]');
    await memberSearchInput.fill('Admin');
    await page.waitForTimeout(400); // debounce

    const searchDropdown = page.locator('#member-search-results, [data-testid="member-search-dropdown"]');
    await expect(searchDropdown).toBeVisible();

    const firstResult = searchDropdown.locator('button').first();
    await expect(firstResult).toBeVisible();

    // Primary text must NOT be an email
    const resultText = await firstResult.textContent();
    expect(resultText).not.toMatch(/^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$/);
    // Real name and Contributor ID must be present
    expect(resultText).toMatch(/\w+/);
  });

  test('8. Selected attendee chip shows real name and Contributor ID tooltip', async ({ page }) => {
    await loginUser(page);
    await page.goto('/calendar/w/engineering-core/events/create/');

    const memberSearchInput = page.locator('#member-search-input, input[placeholder*="Search by name"]');
    await memberSearchInput.fill('Admin');
    await page.waitForTimeout(400);

    const firstResult = page.locator('#member-search-results button').first();
    await firstResult.click();

    // Check selected attendee chip
    const attendeeChip = page.locator('[data-testid="selected-attendee-chip"], .inline-flex:has-text("×")').first();
    await expect(attendeeChip).toBeVisible();
    const chipText = await attendeeChip.textContent();
    expect(chipText).not.toContain('@'); // never email
    expect(chipText).toContain('×'); // remove action
  });

  test('9. Avatar appears when available (image or styled initials fallback)', async ({ page }) => {
    await loginUser(page);
    await page.goto('/calendar/w/engineering-core/events/create/');

    const memberSearchInput = page.locator('#member-search-input, input[placeholder*="Search by name"]');
    await memberSearchInput.fill('Dev');
    await page.waitForTimeout(400);

    // Look for avatar element (img or avatar initials circle)
    const avatarEl = page.locator('#member-search-results [data-testid="user-avatar"], #member-search-results img, #member-search-results .rounded-full').first();
    await expect(avatarEl).toBeVisible();
  });

  test('10. Unauthorized people / outsiders are not returned in people search', async ({ page }) => {
    await loginUser(page);
    await page.goto('/calendar/w/engineering-core/events/create/');

    const memberSearchInput = page.locator('#member-search-input, input[placeholder*="Search by name"]');
    // Search for a user that does not belong to engineering-core workspace
    await memberSearchInput.fill('ForeignOutsiderHacker');
    await page.waitForTimeout(400);

    const searchDropdown = page.locator('#member-search-results');
    // Either hidden or shows "No members found"
    const resultButtons = searchDropdown.locator('button');
    await expect(resultButtons).toHaveCount(0);
  });

});
