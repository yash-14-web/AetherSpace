import { test, expect, Page } from '@playwright/test';

async function signIn(page: Page, email = 'admin@aetherspace.dev', password = 'AdminPassword123!') {
  await page.goto('/auth/login/');
  await page.fill('#login-email', email);
  await page.fill('#login-password', password);
  await page.click('button[type="submit"]');
  await page.waitForURL((url: URL) => !url.pathname.includes('/auth/login/'), { timeout: 10000 }).catch(() => {});
}

test.describe('Bug Tracking (Phase 6)', () => {

  test('should require authentication to access bug views', async ({ page }) => {
    // Attempt accessing bugs without auth redirects to login
    await page.goto('/bugs/');
    await expect(page).toHaveURL(/\/auth\/login\//);

    await page.goto('/bugs/my/');
    await expect(page).toHaveURL(/\/auth\/login\//);
  });

  test('should display Bug Dashboard with metric cards and charts', async ({ page }) => {
    await signIn(page);

    await page.goto('/bugs/');
    // Switch to Dashboard view
    const dashboardBtn = page.getByTestId('bug-dashboard-switcher');
    await dashboardBtn.click();

    await expect(page.getByRole('heading', { name: 'Bug Dashboard' })).toBeVisible();

    // Verify 5 metric cards
    await expect(page.getByText('Total Bugs')).toBeVisible();
    await expect(page.getByText('Open', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('In Progress', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Resolved', { exact: true }).first()).toBeVisible();
    await expect(page.getByText('Closed', { exact: true }).first()).toBeVisible();

    // Verify "+ Raise Bug" primary button
    const raiseBugBtn = page.getByTestId('raise-bug-btn').first();
    await expect(raiseBugBtn).toBeVisible();
  });

  test('should display Bug List with status tabs and search toolbar', async ({ page }) => {
    await signIn(page);

    await page.goto('/bugs/');
    await expect(page.getByRole('heading', { name: 'Bug List' })).toBeVisible();

    // Verify status filter tabs
    await expect(page.getByRole('link', { name: /All Bugs/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Open/i }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /In Progress/i }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /Resolved/i }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /Closed/i }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: /My Bugs/i })).toBeVisible();

    // Verify search input
    const searchInput = page.locator('input[placeholder*="Search"]');
    await expect(searchInput).toBeVisible();
  });

  test('should allow raising a new bug with collision-safe B-###### ID', async ({ page }) => {
    await signIn(page);

    await page.goto('/bugs/');
    const raiseBugBtn = page.getByTestId('raise-bug-btn').first();
    await raiseBugBtn.click();

    await expect(page.getByRole('heading', { name: /Raise New Bug/i })).toBeVisible();

    // Fill defect form
    await page.fill('input[name="title"]', 'E2E Automated Defect Verification');
    await page.fill('textarea[name="description"]', 'Validating bug reporting, B-###### ID collision safety, and audit trail.');
    await page.selectOption('select[name="priority"]', 'CRITICAL');
    await page.selectOption('select[name="severity"]', 'SEV1');
    await page.fill('textarea[name="steps_to_reproduce"]', '1. Trigger e2e run\n2. Verify defect reporting');
    await page.fill('textarea[name="expected_result"]', 'Defect logged successfully');
    await page.fill('textarea[name="actual_result"]', 'Error 500 thrown');

    // Submit form
    await page.click('button[type="submit"]');

    // Should redirect to bug detail view
    await expect(page.getByRole('heading', { name: 'E2E Automated Defect Verification' })).toBeVisible();

    // Verify B-###### format (e.g. B-882316)
    const bugCodeBadge = page.locator('span').filter({ hasText: /^B-[0-9]{6}$/ }).first();
    await expect(bugCodeBadge).toBeVisible();

    // Verify Steps to Reproduce and Results are visible
    await expect(page.getByText('Steps to Reproduce')).toBeVisible();
    await expect(page.getByText('Expected Result')).toBeVisible();
    await expect(page.getByText('Actual Result')).toBeVisible();

    // Verify Activity & History tab
    const activityTab = page.getByRole('button', { name: /Activity & History/i });
    await expect(activityTab).toBeVisible();
  });

  test('should display My Bugs cross-workspace personal view', async ({ page }) => {
    await signIn(page);

    await page.goto('/bugs/my/');
    await expect(page.getByRole('heading', { name: 'My Bugs' })).toBeVisible();

    // Verify personal tabs
    await expect(page.getByRole('link', { name: /Assigned to Me/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Reported by Me/i })).toBeVisible();
  });

});
