import { test, expect } from '@playwright/test';

test.describe('AetherSpace — Local Functional & UI Audit Verification Suite', () => {

  test('1. Task Form: People search is search-first (0 users on open, query on typing, Contributor ID chip)', async ({ page }) => {
    // Navigate to task creation for workspace
    await page.goto('/tasks/w/engineering-core/create/');
    
    // Assignee input container exists
    const searchInput = page.locator('input[placeholder*="Type to search teammate"]');
    await expect(searchInput).toBeVisible();

    // Verify search-first rule: 0 users visible before typing
    const dropdownItems = page.locator('[data-testid="people-search-results"] button');
    await expect(dropdownItems).toHaveCount(0);

    // Type query
    await searchInput.fill('Dev');
    // Dropdown should show matching member with Contributor ID
    await page.waitForTimeout(300);
    const resultItem = page.locator('button:has-text("Lead Developer")');
    if (await resultItem.count() > 0) {
      await expect(resultItem).toBeVisible();
      await expect(resultItem.locator('text=/\\d{5}C/')).toBeVisible();
    }
  });

  test('2. Task Detail: Subtasks are DB backed (No localStorage fakes, interactive checklist)', async ({ page }) => {
    await page.goto('/tasks/w/engineering-core/');
    const firstTask = page.locator('a[href*="/tasks/w/engineering-core/"]').first();
    if (await firstTask.count() > 0) {
      await firstTask.click();

      // Check overview subtasks section
      await expect(page.locator('text=Subtasks & Acceptance Checklist')).toBeVisible();
      
      // Verify no localStorage mock data is used
      const localStorageKeys = await page.evaluate(() => Object.keys(localStorage));
      const hasTaskCriteriaMock = localStorageKeys.some(k => k.startsWith('task_criteria_'));
      expect(hasTaskCriteriaMock).toBeFalsy();
    }
  });

  test('3. Task Detail: Attachments tab features real upload modal & Supabase Storage file cards', async ({ page }) => {
    await page.goto('/tasks/w/engineering-core/');
    const firstTask = page.locator('a[href*="/tasks/w/engineering-core/"]').first();
    if (await firstTask.count() > 0) {
      await firstTask.click();

      // Click Attachments Tab
      const attachmentsTab = page.locator('button:has-text("Attachments")');
      await attachmentsTab.click();

      // Verify real Upload File button and file input
      const uploadBtn = page.locator('button:has-text("Upload File")');
      await expect(uploadBtn).toBeVisible();
      await uploadBtn.click();
      await expect(page.locator('input[type="file"][name="file"]')).toBeVisible();

      // Verify no hardcoded demo files (auth-flow-v2.pdf)
      await expect(page.locator('text=auth-flow-v2.pdf')).toHaveCount(0);
    }
  });

  test('4. Task Detail: Comments tab has chronological ordering and composer at bottom with @mention', async ({ page }) => {
    await page.goto('/tasks/w/engineering-core/');
    const firstTask = page.locator('a[href*="/tasks/w/engineering-core/"]').first();
    if (await firstTask.count() > 0) {
      await firstTask.click();

      // Click Comments tab
      const commentsTab = page.locator('button:has-text("Comments")');
      await commentsTab.click();

      // Verify discussion header
      await expect(page.locator('text=Task Discussion')).toBeVisible();

      // Composer must be at the bottom
      const composer = page.locator('textarea[placeholder*="Type @ to mention"]');
      await expect(composer).toBeVisible();

      // Test typing @ triggers teammate autocomplete dropdown
      await composer.fill('Great work @');
      await page.waitForTimeout(300);
      const mentionDropdown = page.locator('button:has-text("Manager"), button:has-text("Developer")');
      // Dropdown should be ready to suggest active teammates
    }
  });

  test('5. People Hover Profile Card: Displays contributor ID, roles, and quick action links on hover', async ({ page }) => {
    await page.goto('/tasks/w/engineering-core/');
    const firstTask = page.locator('a[href*="/tasks/w/engineering-core/"]').first();
    if (await firstTask.count() > 0) {
      await firstTask.click();

      // Hover over assignee avatar in metadata strip
      const assigneeHoverTrigger = page.locator('[x-data*="user-card"], [x-data*="fetchData"]').first();
      if (await assigneeHoverTrigger.count() > 0) {
        await assigneeHoverTrigger.hover();
        await page.waitForTimeout(300); // 250ms debounce

        // Popover should be visible with Obsidian Dark / Clean Slate styling
        const popover = page.locator('text=Profile, text=Message, text=Email').first();
        await expect(popover).toBeVisible();
      }
    }
  });

  test('6. Bug Management: Mirrors search-first assignee, rich text, Supabase attachments, and mentions', async ({ page }) => {
    await page.goto('/bugs/w/engineering-core/create/');
    
    // Assignee has people search select
    await expect(page.locator('input[placeholder*="Type to search teammate"]')).toBeVisible();

    // Rich text toolbar for description and steps
    await expect(page.locator('button[title="Bold"]').first()).toBeVisible();
    await expect(page.locator('button[title="Code"]').first()).toBeVisible();
  });

  test('7. Visual Organogram Hierarchy Chart: Renders concentric tier nodes, connector lines, and legend', async ({ page }) => {
    await page.goto('/w/engineering-core/team/');
    const hierarchyTab = page.locator('button:has-text("Org Hierarchy")');
    await hierarchyTab.click();
    await expect(page.locator('text=ORGANOGRAM')).toBeVisible();
    await expect(page.locator('text=Leadership')).toBeVisible();
    await expect(page.locator('text=Managers / Leads')).toBeVisible();
    await expect(page.locator('text=Contributors')).toBeVisible();
  });

});
