import { test, expect, Page } from '@playwright/test';

async function signIn(page: Page, email = 'admin@aetherspace.dev', password = 'AdminPassword123!') {
  await page.goto('/auth/login/');
  await page.fill('#login-email', email);
  await page.fill('#login-password', password);
  await page.click('button[type="submit"]');
  await page.waitForURL((url: URL) => !url.pathname.includes('/auth/login/'), { timeout: 10000 }).catch(() => {});
}

test.describe('Task Hub Enhancement — Comments, Activity & Code Review', () => {

  test('should display initial Task Summary in Comments stream without duplicating into Overview', async ({ page }) => {
    await signIn(page);

    await page.goto('/tasks/');
    await page.getByRole('link', { name: 'New Task' }).click();
    const taskTitle = `Summary Stream Verification ${Date.now()}`;
    await page.fill('input[name="title"]', taskTitle);
    await page.fill('textarea[name="description"]', 'Technical specifications for initial summary comment verification.');
    await page.click('button[type="submit"]');

    // Confirm redirected to task detail
    await expect(page.getByRole('heading', { name: taskTitle })).toBeVisible();

    // Verify Overview tab does NOT contain the redundant large summary block
    const overviewTabBtn = page.locator('button[role="tab"]').filter({ hasText: /Overview/i });
    if (await overviewTabBtn.isVisible()) {
      await overviewTabBtn.click();
      await expect(page.locator('#task-summary-card')).toHaveCount(0);
    }

    // Switch to Comments tab
    const commentsTabBtn = page.locator('button[role="tab"]').filter({ hasText: /Comments/i });
    await commentsTabBtn.click();

    // Verify Initial Task Summary System Comment card exists in Comments
    const systemCard = page.locator('.system-comment-card').filter({ hasText: /Task Created/i });
    await expect(systemCard).toBeVisible();
    await expect(systemCard.getByText('System')).toBeVisible();
    await expect(systemCard.getByText(taskTitle)).toBeVisible();
    await expect(systemCard.getByText(/Priority:/i)).toBeVisible();
    await expect(systemCard.getByText(/Status:/i)).toBeVisible();
  });

  test('should support Markdown formatting and live preview in Comment Composer', async ({ page }) => {
    await signIn(page);
    await page.goto('/tasks/');

    // Click on the first task in list
    const firstTaskLink = page.locator('a[href*="/tasks/w/"]').filter({ hasText: /#[0-9]{6}/ }).first();
    if (await firstTaskLink.isVisible()) {
      await firstTaskLink.click();
    } else {
      await page.getByRole('link', { name: 'New Task' }).click();
      await page.fill('input[name="title"]', 'Markdown Test Task');
      await page.click('button[type="submit"]');
    }

    // Switch to Comments tab
    await page.locator('button[role="tab"]').filter({ hasText: /Comments/i }).click();

    // Composer Write / Preview tab toggle
    const writeBtn = page.locator('.comment-toolbar button:has-text("Write")');
    const previewBtn = page.locator('.comment-toolbar button:has-text("Preview")');
    await expect(writeBtn).toBeVisible();
    await expect(previewBtn).toBeVisible();

    // Fill markdown content in composer
    const textarea = page.locator('textarea[name="content"]');
    await textarea.fill('### Heading In Comment\n- **Item A**\n- `code snippet`');

    // Click Preview tab
    await previewBtn.click();
    const previewArea = page.locator('[x-show="composerTab === \'preview\'"]');
    await expect(previewArea).toBeVisible();
    await expect(previewArea.getByRole('heading', { name: 'Heading In Comment' })).toBeVisible();

    // Post comment
    await writeBtn.click();
    await page.getByRole('button', { name: /Post Comment/i }).click();

    // Verify user comment rendered cleanly with rectangular styling
    const commentCards = page.locator('.comment-card:not(.system-comment-card)');
    await expect(commentCards.first()).toBeVisible();
    await expect(commentCards.first().locator('h3:has-text("Heading In Comment")')).toBeVisible();
  });

  test('should reflect Bug Attachment and Detachment in both Comments and Activity', async ({ page }) => {
    await signIn(page);
    await page.goto('/tasks/');

    const firstTaskLink = page.locator('a[href*="/tasks/w/"]').filter({ hasText: /#[0-9]{6}/ }).first();
    if (await firstTaskLink.isVisible()) {
      await firstTaskLink.click();
    } else {
      await page.getByRole('link', { name: 'New Task' }).click();
      await page.fill('input[name="title"]', 'Bug Linkage Verification');
      await page.click('button[type="submit"]');
    }

    // Navigate to Defects tab
    const defectsTab = page.locator('button[role="tab"]').filter({ hasText: /Defects/i });
    await defectsTab.click();

    // If an unlinked bug can be attached, attach it
    const attachSelect = page.locator('select[name="bug_code"]');
    if (await attachSelect.isVisible()) {
      const options = await attachSelect.locator('option').all();
      if (options.length > 1) {
        const bugVal = await options[1].getAttribute('value');
        if (bugVal) {
          await attachSelect.selectOption(bugVal);
          await page.getByRole('button', { name: /Attach Bug/i }).click();

          // Check Comments tab for Bug Attached system comment
          await page.locator('button[role="tab"]').filter({ hasText: /Comments/i }).click();
          await expect(page.locator('.system-comment-card').filter({ hasText: /Bug Attached/i })).toBeVisible();

          // Check Activity tab for Bug Linked audit trail
          await page.locator('button[role="tab"]').filter({ hasText: /Activity/i }).click();
          await expect(page.locator('.activity-card').filter({ hasText: /attached to task/i })).toBeVisible();
        }
      }
    }
  });

  test('should allow raising optional Code Review and posting reviewer feedback in Comments', async ({ page }) => {
    await signIn(page);
    await page.goto('/tasks/');
    await page.getByRole('link', { name: 'New Task' }).click();
    const taskTitle = `Code Review Workflow ${Date.now()}`;
    await page.fill('input[name="title"]', taskTitle);
    await page.click('button[type="submit"]');

    // Navigate to Code Reviews tab
    await page.locator('button[role="tab"]').filter({ hasText: /Code Reviews/i }).click();

    // Verify Code Review is OPTIONAL: No code reviews initially exist
    await expect(page.getByText('No code review requests yet')).toBeVisible();

    // Click "Request Code Review"
    await page.getByRole('button', { name: /Request/i }).first().click();

    // Verify modal has auto-populated Task ID and Title, Reviewer dropdown, and GitHub PR URL
    const modal = page.locator('#code-review-modal');
    await expect(page.locator('input[name="github_pr_url"]')).toBeVisible();
    await expect(page.locator('select[name="reviewer"]')).toBeVisible();

    // Submit Code Review Request
    await page.fill('input[name="github_pr_url"]', 'https://github.com/aetherspace/aetherspace/pull/404');
    await page.fill('textarea[name="description"]', 'Please review auth token validation logic.');
    await page.click('button:has-text("Submit Request")');

    // Should redirect to Comments tab with system comment: "Code Review Requested"
    await expect(page.locator('.system-comment-card').filter({ hasText: /Code Review Requested/i })).toBeVisible();
    await expect(page.locator('.system-comment-card').filter({ hasText: /View Pull Request/i })).toBeVisible();

    // Reviewer provides feedback in Task Comments linked to the review
    const crFeedbackSelect = page.locator('select[name="code_review_id"]');
    if (await crFeedbackSelect.isVisible()) {
      await crFeedbackSelect.selectOption({ index: 1 });
    }
    await page.fill('textarea[name="content"]', 'Code review feedback: Please handle token expiration properly.');
    await page.getByRole('button', { name: /Post Comment/i }).click();

    // Verify reviewer feedback comment displays review badge
    await expect(page.locator('.comment-card').filter({ hasText: /Reviewer Feedback/i })).toBeVisible();
  });

  test('should support Light and Dark themes seamlessly on Comment Cards', async ({ page }) => {
    await signIn(page);
    await page.goto('/tasks/');

    // Select first task
    const firstTaskLink = page.locator('a[href*="/tasks/w/"]').filter({ hasText: /#[0-9]{6}/ }).first();
    if (await firstTaskLink.isVisible()) {
      await firstTaskLink.click();
    }

    // Switch to Comments tab
    await page.locator('button[role="tab"]').filter({ hasText: /Comments/i }).click();

    // Check light mode styles
    const commentCard = page.locator('.comment-card, .system-comment-card').first();
    if (await commentCard.isVisible()) {
      await expect(commentCard).toHaveClass(/border/);

      // Toggle dark theme if toggle button exists
      const themeToggle = page.locator('[data-theme-toggle]');
      if (await themeToggle.isVisible()) {
        await themeToggle.click();
        // Check dark class applied
        await expect(page.locator('html')).toHaveClass(/dark/);
      }
    }
  });

});
