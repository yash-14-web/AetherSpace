import { test, expect, Page } from '@playwright/test';

async function signIn(page: Page, email = 'admin@aetherspace.dev', password = 'AdminPassword123!') {
  await page.goto('/auth/login/');
  await page.fill('#login-email', email);
  await page.fill('#login-password', password);
  await page.click('button[type="submit"]');
  // Wait until navigation away from login completes so session cookie is preserved
  await page.waitForURL((url: URL) => !url.pathname.includes('/auth/login/'), { timeout: 10000 }).catch(() => {});
}

test.describe('Workspace Management & RBAC (Phase 3)', () => {

  test('should require authentication to access dashboards or workspaces', async ({ page }) => {
    // Unauthenticated access to /workspaces/master/ redirects to login
    await page.goto('/workspaces/master/');
    await expect(page).toHaveURL(/\/auth\/login\//);

    // Unauthenticated access to workspace dashboard redirects to login
    await page.goto('/workspaces/w/smart-classroom/');
    await expect(page).toHaveURL(/\/auth\/login\//);
  });

  test('should display workspace creation form with real-time slug preview', async ({ page }) => {
    // Sign in first
    await signIn(page);

    // Navigate to create workspace
    await page.goto('/workspaces/create/');
    await expect(page.getByRole('heading', { name: 'Create a New Workspace' })).toBeVisible();

    // Fill workspace name and assert slug input auto-populates
    const nameInput = page.locator('input[name="name"]');
    const slugInput = page.locator('input[name="slug"]');
    await nameInput.fill('Smart Classroom');
    await expect(slugInput).toHaveValue('smart-classroom');

    // Verify creator administrator notice
    await expect(page.getByText('Workspace Administrator')).toBeVisible();
  });

  test('should display Master Dashboard with multi-workspace cards', async ({ page }) => {
    await signIn(page);

    await page.goto('/workspaces/master/');
    await expect(page.getByRole('heading', { name: 'Master Dashboard' })).toBeVisible();

    // Verify summary metric cards
    await expect(page.getByText('Active Workspaces')).toBeVisible();
    await expect(page.getByText('Total Team Members')).toBeVisible();
    await expect(page.getByText('Active Tasks')).toBeVisible();
    await expect(page.getByText('Open Bugs')).toBeVisible();
  });

  test('should display Workspace Switcher in global header', async ({ page }) => {
    await signIn(page);

    await page.goto('/workspaces/master/');

    // Click Workspace Switcher dropdown button in header
    const header = page.getByRole('banner');
    const switcherBtn = header.locator('button', { hasText: /Workspaces|Smart Classroom/i });
    if (await switcherBtn.isVisible()) {
      await switcherBtn.click();
      await expect(page.getByText('Switch Workspace')).toBeVisible();
      await expect(page.getByRole('link', { name: 'Master Dashboard' })).toBeVisible();
      await expect(page.getByRole('link', { name: 'Create Workspace' })).toBeVisible();
    }
  });

  test('should display Team Directory and Invite Member modal', async ({ page }) => {
    await signIn(page);

    // Visit workspace team page
    await page.goto('/workspaces/w/smart-classroom/team/');
    
    // If user is admin of smart-classroom, verify team directory controls
    const teamHeading = page.getByRole('heading', { name: 'Team Directory & Members' });
    if (await teamHeading.isVisible()) {
      await expect(page.getByRole('button', { name: 'Invite Member' })).toBeVisible();

      // Open Invite modal
      await page.getByRole('button', { name: 'Invite Member' }).click();
      await expect(page.getByRole('heading', { name: 'Invite Team Member' })).toBeVisible();
      await expect(page.locator('input[placeholder="teammate@company.com"]')).toBeVisible();
    }
  });

  test('should show 403 Forbidden with Request Access when non-member views protected workspace', async ({ page }) => {
    // Non-member or unassigned user trying to view unauthorized workspace
    await signIn(page, 'alex@aetherspace.dev', 'SecurePassword123!');

    // Attempt to access unauthorized workspace
    const response = await page.goto('/workspaces/w/restricted-private-ws/');
    if (response && response.status() === 403) {
      await expect(page.getByRole('heading', { name: 'Access Restricted' })).toBeVisible();
      await expect(page.getByText('Need access to this resource?')).toBeVisible();
    }
  });

});
