import { test, expect, Page } from '@playwright/test';

async function signIn(page: Page, email = 'admin@aetherspace.dev', password = 'AdminPassword123!') {
  await page.goto('/auth/login/');
  await page.fill('#login-email', email);
  await page.fill('#login-password', password);
  await page.click('button[type="submit"]');
  await page.waitForURL((url: URL) => !url.pathname.includes('/auth/login/'), { timeout: 10000 }).catch(() => {});
}

test.describe('Task Management (Phase 5)', () => {

  test('should require authentication to access task views', async ({ page }) => {
    // Attempt accessing tasks without auth redirects to login
    await page.goto('/tasks/');
    await expect(page).toHaveURL(/\/auth\/login\//);

    await page.goto('/tasks/my/');
    await expect(page).toHaveURL(/\/auth\/login\//);
  });

  test('should display task list with workflow metric chips and view switcher', async ({ page }) => {
    await signIn(page);

    // Navigate to tasks router
    await page.goto('/tasks/');

    // Verify view mode switcher buttons (using exact match to avoid matching 'Task List' or 'Dashboard')
    const listBtn = page.getByRole('link', { name: 'List', exact: true });
    const boardBtn = page.getByRole('link', { name: 'Board', exact: true });
    await expect(listBtn).toBeVisible();
    await expect(boardBtn).toBeVisible();

    // Verify 5 workflow status metric chips
    await expect(page.getByText('To Do', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('In Progress', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Code Review', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Testing', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Done', { exact: true }).first()).toBeVisible();

    // Verify "New Task" primary action button
    const newTaskBtn = page.getByRole('link', { name: 'New Task' });
    await expect(newTaskBtn).toBeVisible();
  });

  test('should allow creating a task with 6-digit numeric ID', async ({ page }) => {
    await signIn(page);

    await page.goto('/tasks/');
    const newTaskBtn = page.getByRole('link', { name: 'New Task' });
    await newTaskBtn.click();

    await expect(page.getByRole('heading', { name: /Create New Task/i })).toBeVisible();

    // Fill form
    await page.fill('input[name="title"]', 'E2E Automated Task Verification');
    await page.fill('textarea[name="description"]', 'Validating task creation, 6-digit collision safe IDs, and activity logging.');
    await page.selectOption('select[name="priority"]', 'HIGH');

    // Submit form
    await page.click('button[type="submit"]');

    // Should redirect to task detail view
    await expect(page.getByRole('heading', { name: 'E2E Automated Task Verification' })).toBeVisible();

    // Check 6-digit numeric ID format (e.g. #619347)
    const taskCodeBadge = page.locator('span:has-text("#")').filter({ hasText: /#[0-9]{6}/ }).first();
    await expect(taskCodeBadge).toBeVisible();

    // Verify Activity & History log contains creation entry
    await expect(page.getByText('Activity & History').first()).toBeVisible();
    await expect(page.getByText(/Created task #[0-9]{6}/).first()).toBeVisible();
  });

  test('should display Kanban board with all 5 required workflow stages', async ({ page }) => {
    await signIn(page);

    await page.goto('/tasks/');
    const boardBtn = page.getByRole('link', { name: 'Board', exact: true });
    await boardBtn.click();

    // Verify URL
    await expect(page).toHaveURL(/.*\/board\//);

    // Verify columns strictly matching required workflow:
    // To Do -> In Progress -> Code Review -> Testing -> Done
    await expect(page.getByRole('heading', { name: 'To Do' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'In Progress' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Code Review' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Testing' })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Done' })).toBeVisible();
  });

  test('should display My Tasks personal view across workspaces', async ({ page }) => {
    await signIn(page);

    await page.goto('/tasks/my/');
    await expect(page.getByRole('heading', { name: 'My Tasks' })).toBeVisible();

    // Verify status tabs
    await expect(page.getByRole('link', { name: /All \(/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /To Do \(/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /In Progress \(/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Code Review \(/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Testing \(/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Done \(/i })).toBeVisible();
  });

});
