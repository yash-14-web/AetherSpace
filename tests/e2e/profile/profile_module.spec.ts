import { test, expect, Page } from '@playwright/test';

/**
 * Phase 12 — Profile Module Playwright E2E Spec
 * Designed for manual owner execution: `npx playwright test tests/e2e/profile/profile_module.spec.ts`
 *
 * NOTE: As per project instructions, automated browser sessions are NOT executed by Antigravity;
 * this spec is authored for user/CI verification.
 */

async function signIn(page: Page, email = 'admin@aetherspace.dev', password = 'AdminPassword123!') {
  await page.goto('/auth/login/');
  await page.fill('#login-email', email);
  await page.fill('#login-password', password);
  await page.click('button[type="submit"]');
  await page.waitForURL((url: URL) => !url.pathname.includes('/auth/login/'), { timeout: 15000 }).catch(() => {});
}

test.describe('Phase 12 — Profile Module', () => {

  test('should redirect unauthenticated users from profile to login', async ({ page }) => {
    await page.goto('/profile/');
    await expect(page).toHaveURL(/\/auth\/login\//);
  });

  test('should load My Profile overview with banner, metrics, tabs, and overview cards', async ({ page }) => {
    await signIn(page);
    await page.goto('/profile/');

    // Router redirects to accounts profile
    await expect(page).toHaveURL(/\/accounts\/profile\/|\/profile\//);

    // Verify 4 high-level metric cards
    await expect(page.getByText('Assigned Tasks').first()).toBeVisible();
    await expect(page.getByText('Assigned Defects').first()).toBeVisible();
    await expect(page.getByText('Workspaces').first()).toBeVisible();
    await expect(page.getByText('Total Activity').first()).toBeVisible();

    // Verify sub-navigation tabs
    await expect(page.getByRole('link', { name: /Overview/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /My Tasks/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /My Bugs/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Activity/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Workspace Roles/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Edit Profile/i })).toBeVisible();

    // Verify Overview sections
    await expect(page.getByText(/About & Professional Bio/i)).toBeVisible();
    await expect(page.getByText(/Account Information/i)).toBeVisible();
  });

  test('should load Edit Profile page with avatar manager and details form', async ({ page }) => {
    await signIn(page);
    await page.goto('/accounts/profile/edit/');

    // Verify header and breadcrumbs
    await expect(page.getByRole('heading', { name: /Profile Picture/i })).toBeVisible();
    await expect(page.getByRole('heading', { name: /Personal Details & Contact/i })).toBeVisible();

    // Verify avatar management modes (Upload, URL, Themes)
    await expect(page.getByText('Upload Image')).toBeVisible();
    await expect(page.getByText(/Image URL \(0 KB\)/i)).toBeVisible();
    await expect(page.getByText(/Themes \(0 KB\)/i)).toBeVisible();

    // Verify form inputs
    await expect(page.locator('#profile-fullname')).toBeVisible();
    await expect(page.locator('#profile-headline')).toBeVisible();
    await expect(page.locator('#profile-timezone')).toBeVisible();
    await expect(page.locator('#profile-bio')).toBeVisible();

    // Verify action buttons
    await expect(page.getByRole('button', { name: /Save Changes/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Cancel/i })).toBeVisible();
  });

  test('should navigate between Profile sub-views and filter tasks', async ({ page }) => {
    await signIn(page);

    // 1. My Tasks
    await page.goto('/accounts/profile/tasks/');
    await expect(page.getByRole('link', { name: /All Tasks/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /To Do/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /In Progress/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Done/i })).toBeVisible();
    await expect(page.getByPlaceholder(/Search tasks/i)).toBeVisible();

    // 2. My Bugs
    await page.goto('/accounts/profile/bugs/');
    await expect(page.getByRole('link', { name: /All Bugs/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Assigned to Me/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Reported by Me/i })).toBeVisible();
    await expect(page.getByPlaceholder(/Search defects/i)).toBeVisible();

    // 3. Activity Stream
    await page.goto('/accounts/profile/activity/');
    await expect(page.getByRole('link', { name: /All Activities/i })).toBeVisible();
    await expect(page.getByText(/Text-based chronological audit/i)).toBeVisible();

    // 4. Workspace Roles
    await page.goto('/accounts/profile/roles/');
    await expect(page.getByText(/Workspace Memberships & Role Assignments/i)).toBeVisible();
    await expect(page.getByText(/Role Permissions & Capabilities/i)).toBeVisible();
  });

  test('should access profile from universal header dropdown', async ({ page }) => {
    await signIn(page);
    await page.goto('/workspaces/master/');

    const header = page.getByRole('banner');
    const avatarBtn = header.locator('button', { hasText: /AD/i });
    await avatarBtn.click();

    const profileLink = header.getByRole('link', { name: 'My Profile' });
    await expect(profileLink).toBeVisible();
    await profileLink.click();

    await expect(page).toHaveURL(/\/accounts\/profile\/|\/profile\//);
    await expect(page.getByText('Assigned Tasks').first()).toBeVisible();
  });

});
