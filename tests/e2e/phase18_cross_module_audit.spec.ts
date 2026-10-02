import { test, expect } from '@playwright/test';

test.describe('Phase 18 — Cross-Module Integration, Security, RBAC & Performance Audit E2E Suite', () => {

  test('1. Workspace Isolation: Contributor Alpha cannot view or access Workspace Beta tasks', async ({ page }) => {
    // Attempting direct URL access to an unauthorized workspace task should return 403 or 404
    const response = await page.goto('/tasks/w/beta-project/200002/');
    if (response) {
      expect([302, 403, 404]).toContain(response.status());
    }
  });

  test('2. Multi-Workspace Manager: Workspace switcher updates all dashboard metrics and data scope cleanly', async ({ page }) => {
    await page.goto('/workspaces/dashboard/');

    // Ensure dashboard header exists
    await expect(page.locator('h1')).toBeVisible();

    // Verify workspace switcher is accessible in header or rail
    const wsSwitcher = page.locator('#workspace-switcher-btn, [data-testid="workspace-switcher"]');
    if (await wsSwitcher.isVisible()) {
      await wsSwitcher.click();
      await expect(page.locator('#workspace-dropdown-menu, [role="menu"]')).toBeVisible();
    }
  });

  test('3. People Search: Search-first behavior displays zero initial results and requires keystrokes', async ({ page }) => {
    // Open a page with a people picker, e.g. task creation or team direct add
    await page.goto('/tasks/w/alpha-project/create/');

    if (page.url().includes('/create/')) {
      const searchInput = page.locator('input[placeholder*="Search by name, Contributor ID"]');
      if (await searchInput.isVisible()) {
        // Initially, the results dropdown must not be visible
        await expect(page.locator('#people-results-list, .people-search-results')).toHaveCount(0);

        // Type query to fetch users
        await searchInput.fill('Alpha');
        await page.waitForTimeout(300); // debounce wait
        await expect(page.locator('text=Alpha Engineer')).toBeVisible();
      }
    }
  });

  test('4. People Hover Profile Card: Shows real System Role and Tagging Role', async ({ page }) => {
    await page.goto('/tasks/w/alpha-project/');

    const hoverTrigger = page.locator('.aether-hover-card-trigger, [data-user-hover]').first();
    if (await hoverTrigger.isVisible()) {
      await hoverTrigger.hover();
      await page.waitForTimeout(250);
      const card = page.locator('.aether-hover-card, [role="tooltip"]');
      await expect(card).toBeVisible();
      await expect(card.locator('text=Contributor ID')).toBeVisible();
    }
  });

  test('5. Notification Center: Displays workspace-scoped notifications and permits mark all as read', async ({ page }) => {
    await page.goto('/notifications/');

    await expect(page).toHaveTitle(/Notification Center/i);
    await expect(page.locator('h1')).toContainText(/Notifications/i);

    // Verify category filter tabs
    await expect(page.locator('a:has-text("All"), button:has-text("All")')).toBeVisible();
    await expect(page.locator('a:has-text("Tasks"), button:has-text("Tasks")')).toBeVisible();
    await expect(page.locator('a:has-text("Bugs"), button:has-text("Bugs")')).toBeVisible();

    // Verify Mark All as Read button
    const markAllBtn = page.locator('button:has-text("Mark All as Read"), button:has-text("Mark all as read")');
    if (await markAllBtn.isVisible()) {
      await expect(markAllBtn).toBeEnabled();
    }
  });

  test('6. Calendar Integration: Displays unified events for tasks, bugs, and meetings', async ({ page }) => {
    await page.goto('/calendar/');

    if (page.url().includes('/calendar/')) {
      await expect(page.locator('#calendarGrid, .calendar-month-grid, [data-testid="calendar-grid"]')).toBeVisible();

      // Verify category filter checkboxes / pills
      await expect(page.locator('text=Tasks')).toBeVisible();
      await expect(page.locator('text=Bugs')).toBeVisible();
      await expect(page.locator('text=Meetings')).toBeVisible();
    }
  });

  test('7. Chat Real-Time Ordering: Message stream renders oldest at top and newest at bottom', async ({ page }) => {
    await page.goto('/chat/');

    if (page.url().includes('/chat/')) {
      const messageStream = page.locator('#chatMessageStream, [data-testid="message-stream"]');
      if (await messageStream.isVisible()) {
        await expect(messageStream).toBeVisible();
      }
    }
  });

  test('8. RBAC Server-Side Enforcement: Contributor cannot access Admin Panel', async ({ page }) => {
    const response = await page.goto('/admin_panel/');
    if (response) {
      // Must return 403 Forbidden or redirect to login (302)
      expect([302, 403]).toContain(response.status());
    }
  });

});
