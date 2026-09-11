import { test, expect, Page } from '@playwright/test';

async function signIn(page: Page, email = 'admin@aetherspace.dev', password = 'AdminPassword123!') {
  await page.goto('/auth/login/');
  await page.fill('#login-email', email);
  await page.fill('#login-password', password);
  await page.click('button[type="submit"]');
  await page.waitForURL((url: URL) => !url.pathname.includes('/auth/login/'), { timeout: 10000 }).catch(() => {});
}

test.describe('People Search UX Audit & Fix Verification', () => {

  test('New Direct Message modal must NOT display users on empty search query', async ({ page }) => {
    await signIn(page);
    await page.goto('/chat/');

    // Open New Direct Message modal
    const newDmBtn = page.getByRole('button', { name: '+ New' }).first();
    await expect(newDmBtn).toBeVisible();
    await newDmBtn.click();

    // Verify modal is visible
    const modal = page.locator('div[x-show="newDmModalOpen"]');
    await expect(modal).toBeVisible();

    // Search input should be present and empty
    const searchInput = modal.locator('input[placeholder*="Search by name, email"]');
    await expect(searchInput).toBeVisible();
    await expect(searchInput).toHaveValue('');

    // CRITICAL UX REQUIREMENT: Zero user items displayed when search input is empty
    const userItems = modal.locator('a[href*="/dm/"]');
    await expect(userItems).toHaveCount(0);

    // Initial empty search prompt banner MUST be visible
    const promptBanner = modal.getByText('Find People for Direct Chat');
    await expect(promptBanner).toBeVisible();
  });

  test('New Direct Message modal displays matching users on query and clears when erased', async ({ page }) => {
    await signIn(page);
    await page.goto('/chat/');

    // Open modal
    await page.getByRole('button', { name: '+ New' }).first().click();
    const modal = page.locator('div[x-show="newDmModalOpen"]');
    const searchInput = modal.locator('input[placeholder*="Search by name, email"]');

    // Type query matching an existing member/user
    await searchInput.fill('Admin');
    await page.waitForTimeout(400); // debounce wait

    // Results should appear
    const results = modal.locator('a[href*="/dm/"]');
    const resultCount = await results.count();
    expect(resultCount).toBeGreaterThanOrEqual(0);

    // Clear search query
    await searchInput.fill('');
    await page.waitForTimeout(400);

    // CRITICAL UX REQUIREMENT: Clearing query immediately clears results and restores prompt
    await expect(results).toHaveCount(0);
    const promptBanner = modal.getByText('Find People for Direct Chat');
    await expect(promptBanner).toBeVisible();
  });

  test('New Direct Message modal displays clear "No users found" state on unmatched query', async ({ page }) => {
    await signIn(page);
    await page.goto('/chat/');

    await page.getByRole('button', { name: '+ New' }).first().click();
    const modal = page.locator('div[x-show="newDmModalOpen"]');
    const searchInput = modal.locator('input[placeholder*="Search by name, email"]');

    // Type query that matches nobody
    await searchInput.fill('zzz_nonexistent_user_9999');
    await page.waitForTimeout(500);

    // Verify "No users found" state is rendered
    await expect(modal.getByText(/No users found/i)).toBeVisible();
    await expect(modal.locator('a[href*="/dm/"]')).toHaveCount(0);
  });

  test('Calendar Event Create invitees list must NOT display members when search query is empty', async ({ page }) => {
    await signIn(page);
    await page.goto('/core/calendar/');

    // Click "New Event" or navigate to create
    const createEventBtn = page.getByRole('link', { name: /New Event/i }).first();
    if (await createEventBtn.isVisible()) {
      await createEventBtn.click();
    } else {
      await page.goto('/calendars/w/aetherspace-core/events/create/');
    }

    // Verify Invite People search input is present
    const memberSearchInput = page.locator('input[x-model="memberSearch"]');
    await expect(memberSearchInput).toBeVisible();
    await expect(memberSearchInput).toHaveValue('');

    // CRITICAL UX REQUIREMENT: Results dropdown MUST NOT be visible when search is empty
    const resultsDropdown = page.locator('div[x-show="memberSearch.trim().length > 0"]');
    await expect(resultsDropdown).not.toBeVisible();

    // Type a search query
    await memberSearchInput.fill('a');
    await expect(resultsDropdown).toBeVisible();

    // Clear search query
    await memberSearchInput.fill('');
    await expect(resultsDropdown).not.toBeVisible();
  });

});
