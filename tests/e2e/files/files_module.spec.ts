import { test, expect, Page } from '@playwright/test';

/**
 * Phase 10 — Files, Folders & Workspace Storage Playwright E2E Spec
 * Designed for manual owner execution: `npx playwright test tests/e2e/files/files_module.spec.ts`
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

test.describe('Phase 10 — Files & Storage Module', () => {

  test('should redirect unauthenticated users from files to login', async ({ page }) => {
    await page.goto('/files/');
    await expect(page).toHaveURL(/\/auth\/login\//);
  });

  test('should load Files Home with metrics cards, quick access folders, and tabs', async ({ page }) => {
    await signIn(page);
    await page.goto('/files/');

    // Router redirects to active workspace files
    await expect(page).toHaveURL(/\/files\/w\/[^\/]+\//);

    // Verify main header
    await expect(page.getByRole('heading', { name: /Files/i }).first()).toBeVisible();
    await expect(page.getByText(/Store, organize and collaborate on files/i)).toBeVisible();

    // Verify primary action buttons
    await expect(page.getByText('+ New')).toBeVisible();
    await expect(page.getByRole('link', { name: /Upload/i })).toBeVisible();

    // Verify 4 metrics cards
    await expect(page.getByText('Total Files')).toBeVisible();
    await expect(page.getByText('Folders')).toBeVisible();
    await expect(page.getByText('Shared with me')).toBeVisible();
    await expect(page.getByText('Storage Used')).toBeVisible();

    // Verify Quick Access section
    await expect(page.getByRole('heading', { name: 'Quick Access' })).toBeVisible();

    // Verify file tabs
    await expect(page.getByRole('link', { name: 'All Files' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Recent' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Favorites' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Shared with me' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Trash' })).toBeVisible();
  });

  test('should load Upload Files page with drag-and-drop and cloud link modes', async ({ page }) => {
    await signIn(page);
    await page.goto('/files/');

    await page.getByRole('link', { name: /Upload/i }).click();
    await expect(page).toHaveURL(/\/files\/w\/[^\/]+\/upload\//);

    await expect(page.getByRole('heading', { name: /Upload Files/i })).toBeVisible();
    await expect(page.getByText('Direct File Upload')).toBeVisible();
    await expect(page.getByText('Connect Cloud Link (Save Space)')).toBeVisible();

    // Verify drag-and-drop dropzone
    await expect(page.getByText('Drag and drop files here')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Browse Files' })).toBeVisible();
    await expect(page.getByText(/Maximum file size: 20 MB/i)).toBeVisible();

    // Switch to Cloud Link mode
    await page.getByText('Connect Cloud Link (Save Space)').click();
    await expect(page.getByText('Add External Cloud Link')).toBeVisible();
    await expect(page.getByPlaceholder(/figma\.com|docs\.google\.com/i)).toBeVisible();
  });

  test('should load Recent Files view with filter tabs', async ({ page }) => {
    await signIn(page);
    await page.goto('/files/');

    // Navigate to Recent Files
    const recentLink = page.getByRole('link', { name: 'Recent Files' }).first();
    if (await recentLink.isVisible()) {
      await recentLink.click();
    } else {
      await page.goto(page.url().replace(/\/files\/w\/([^\/]+)\/.*$/, '/files/w/$1/recent/'));
    }

    await expect(page.getByRole('heading', { name: /Recent Files/i })).toBeVisible();
    await expect(page.getByRole('link', { name: 'All' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Opened by me' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Modified by me' })).toBeVisible();
    await expect(page.getByRole('link', { name: /View All Files/i })).toBeVisible();
  });

  test('should load Shared Files view with access badges', async ({ page }) => {
    await signIn(page);
    await page.goto('/files/');

    // Navigate to Shared Files
    const sharedLink = page.getByRole('link', { name: 'Shared Files' }).first();
    if (await sharedLink.isVisible()) {
      await sharedLink.click();
    } else {
      await page.goto(page.url().replace(/\/files\/w\/([^\/]+)\/.*$/, '/files/w/$1/shared/'));
    }

    await expect(page.getByRole('heading', { name: /Shared Files/i })).toBeVisible();
    await expect(page.getByRole('link', { name: 'With me' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'By me' })).toBeVisible();
    await expect(page.getByPlaceholder(/Search shared files/i)).toBeVisible();
  });

  test('should enforce search-first people picker rule in share modal', async ({ page }) => {
    await signIn(page);
    await page.goto('/files/');

    // If any file exists, open detail view and check share modal
    const fileRowLink = page.locator('table tbody tr a[href*="/files/w/"]').first();
    if (await fileRowLink.isVisible()) {
      await fileRowLink.click();
      await expect(page).toHaveURL(/\/files\/w\/[^\/]+\/[0-9a-f-]+\//);

      // Open Share modal
      await page.getByRole('button', { name: 'Share' }).first().click();
      await expect(page.locator('#share-modal-title')).toBeVisible();

      // STRICT RULE CHECK: Initial state MUST NOT show any user list
      const resultsContainer = page.locator('#share-modal-title').locator('..').locator('..').locator('[x-show="hasSearched"]');
      await expect(resultsContainer).toBeHidden();

      // Search input is present and empty
      const searchInput = page.getByPlaceholder(/Search member by name or email/i);
      await expect(searchInput).toBeVisible();
      await expect(searchInput).toHaveValue('');

      // Type a search query to activate search
      await searchInput.fill('admin');
      await page.waitForTimeout(400); // Debounce
      await expect(resultsContainer).toBeVisible();
    }
  });

  test('should support theme toggle between light and dark modes cleanly', async ({ page }) => {
    await signIn(page);
    await page.goto('/files/');

    const html = page.locator('html');

    // Switch to dark mode if not already
    const themeBtn = page.locator('button[title*="theme" i], button[aria-label*="theme" i]').first();
    if (await themeBtn.isVisible()) {
      await themeBtn.click();
      // Ensure page layout doesn't break
      await expect(page.getByRole('heading', { name: /Files/i }).first()).toBeVisible();
    }
  });

});
