import { test, expect, Page } from '@playwright/test';

async function signIn(page: Page, email = 'admin@aetherspace.dev', password = 'AdminPassword123!') {
  await page.goto('/auth/login/');
  await page.fill('#login-email', email);
  await page.fill('#login-password', password);
  await page.click('button[type="submit"]');
  await page.waitForURL((url: URL) => !url.pathname.includes('/auth/login/'), { timeout: 10000 }).catch(() => {});
}

test.describe('Chat & Real-time Collaboration (Phase 7)', () => {

  test('should require authentication to access chat views', async ({ page }) => {
    // Attempt accessing chat without auth redirects to login
    await page.goto('/chat/');
    await expect(page).toHaveURL(/\/auth\/login\//);

    await page.goto('/chat/w/demo-workspace/');
    await expect(page).toHaveURL(/\/auth\/login\//);
  });

  test('should display Chat Home (Panel 1) with metrics and quick actions', async ({ page }) => {
    await signIn(page);

    await page.goto('/chat/');
    // Verify redirection to active workspace chat home
    await expect(page).toHaveURL(/\/chat\/w\/[a-z0-9-]+\//);

    // Verify Welcome Hero Banner
    await expect(page.getByRole('heading', { name: /Team Chat & Collaboration/i })).toBeVisible();

    // Verify 4 Stat Cards
    await expect(page.getByText('Total Channels')).toBeVisible();
    await expect(page.getByText('Workspace Members')).toBeVisible();
    await expect(page.getByText('Unread')).toBeVisible();
    await expect(page.getByText('Mentions')).toBeVisible();

    // Verify Quick Actions
    await expect(page.getByRole('link', { name: /Create Channel/i }).first()).toBeVisible();
    await expect(page.getByText('Start Direct Message').first()).toBeVisible();
    await expect(page.getByText('Pinned Assets').first()).toBeVisible();
    await expect(page.getByText('Shared Files').first()).toBeVisible();
  });

  test('should display Channel View (Panel 2) with stream, input, and about drawer', async ({ page }) => {
    await signIn(page);

    await page.goto('/chat/');
    // Click on #general in the sidebar
    const generalChannelLink = page.getByRole('link', { name: /#.*general/i }).first();
    if (await generalChannelLink.isVisible()) {
      await generalChannelLink.click();
    } else {
      await page.goto('/chat/w/alpha-team/c/general/');
    }

    // Verify channel header
    await expect(page.locator('h2:has-text("general")')).toBeVisible();

    // Verify Live / Polling connection pill
    await expect(page.locator('text=/Live|Polling/').first()).toBeVisible();

    // Verify message input placeholder
    const msgInput = page.locator('textarea[name="content"]');
    await expect(msgInput).toBeVisible();

    // Verify About Channel drawer toggle
    const aboutBtn = page.getByTitle('About Channel');
    if (await aboutBtn.isVisible()) {
      await aboutBtn.click();
      await expect(page.getByText(/About #general/i)).toBeVisible();
    }
  });

  test('should display Channel Creation Form (Panel 4)', async ({ page }) => {
    await signIn(page);

    await page.goto('/chat/');
    const createBtn = page.getByTitle('Create Channel').first();
    await createBtn.click();

    await expect(page.getByRole('heading', { name: 'Create New Channel' })).toBeVisible();
    await expect(page.locator('input[name="name"]')).toBeVisible();
    await expect(page.locator('input[name="topic"]')).toBeVisible();
    await expect(page.locator('textarea[name="description"]')).toBeVisible();
    await expect(page.locator('select[name="who_can_post"]')).toBeVisible();
    await expect(page.locator('input[name="is_private"]')).toBeVisible();
  });

  test('should display Channel Details (Panel 5) with tabs', async ({ page }) => {
    await signIn(page);

    await page.goto('/chat/');
    const generalChannel = page.getByRole('link', { name: /#.*general/i }).first();
    if (await generalChannel.isVisible()) {
      await generalChannel.click();
      const detailsBtn = page.getByTitle('Channel Details');
      await detailsBtn.click();
      
      await expect(page.getByRole('button', { name: 'Overview' })).toBeVisible();
      await expect(page.getByRole('button', { name: /Members/i })).toBeVisible();
      await expect(page.getByRole('button', { name: /Pinned Messages/i })).toBeVisible();
      await expect(page.getByRole('button', { name: /Shared Files/i })).toBeVisible();
    }
  });

  test('should display Pinned Assets Hub (Panel 6)', async ({ page }) => {
    await signIn(page);

    await page.goto('/chat/');
    const pinnedLink = page.getByRole('link', { name: 'Pinned Assets' }).first();
    await pinnedLink.click();

    await expect(page.getByRole('heading', { name: 'Pinned Assets' })).toBeVisible();
    await expect(page.getByRole('button', { name: /All Assets/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Messages/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Files/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Links/i })).toBeVisible();
  });

  test('should display Shared Files Hub (Panel 7)', async ({ page }) => {
    await signIn(page);

    await page.goto('/chat/');
    const filesLink = page.getByRole('link', { name: 'Shared Files' }).first();
    await filesLink.click();

    await expect(page.getByRole('heading', { name: 'Shared Files & Attachments' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'All Files' })).toBeVisible();
    await expect(page.getByRole('link', { name: /Images/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Documents/i })).toBeVisible();
    await expect(page.getByRole('link', { name: /Archive/i })).toBeVisible();
  });

});
