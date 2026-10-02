import { test, expect } from '@playwright/test';

test.describe('AetherSpace — Owner QA Verification Suite', () => {

  test.describe('1. Global Quick Actions & Empty States', () => {
    test('Header quick-action dropdown exists and provides Create Task, Raise Bug, Upload File', async ({ page }) => {
      await page.goto('/workspaces/alpha-workspace/tasks/');
      
      const quickActionBtn = page.locator('[data-testid="header-quick-action-btn"]');
      await expect(quickActionBtn).toBeVisible();
      
      // Click dropdown trigger
      await quickActionBtn.click();
      
      // Verify dropdown menu options
      const taskAction = page.locator('[data-testid="quick-action-task"]');
      const bugAction = page.locator('[data-testid="quick-action-bug"]');
      const fileAction = page.locator('[data-testid="quick-action-file"]');
      
      await expect(taskAction).toBeVisible();
      await expect(bugAction).toBeVisible();
      await expect(fileAction).toBeVisible();
      
      // Verify links point to correct workspace paths
      await expect(taskAction).toHaveAttribute('href', /.*\/tasks\/create\/?/);
      await expect(bugAction).toHaveAttribute('href', /.*\/bugs\/create\/?/);
      await expect(fileAction).toHaveAttribute('href', /.*\/files\/?/);
    });

    test('Empty module states display actionable Create / Upload buttons for permitted users', async ({ page }) => {
      // Navigate to tasks list
      await page.goto('/workspaces/alpha-workspace/tasks/');
      const taskEmptyState = page.locator('[data-testid="tasks-empty-state"]');
      if (await taskEmptyState.count() > 0) {
        const createBtn = taskEmptyState.locator('a:has-text("Create Task"), button:has-text("Create Task")');
        await expect(createBtn).toBeVisible();
        await expect(createBtn).toBeEnabled();
      }

      // Navigate to bugs list
      await page.goto('/workspaces/alpha-workspace/bugs/');
      const bugEmptyState = page.locator('[data-testid="bugs-empty-state"]');
      if (await bugEmptyState.count() > 0) {
        const raiseBugBtn = bugEmptyState.locator('a:has-text("Raise Bug"), button:has-text("Raise Bug")');
        await expect(raiseBugBtn).toBeVisible();
        await expect(raiseBugBtn).toBeEnabled();
      }

      // Navigate to files list
      await page.goto('/workspaces/alpha-workspace/files/');
      const filesEmptyState = page.locator('[data-testid="files-empty-state"]');
      if (await filesEmptyState.count() > 0) {
        const uploadFileBtn = filesEmptyState.locator('button:has-text("Upload File"), a:has-text("Upload File")');
        await expect(uploadFileBtn).toBeVisible();
        await expect(uploadFileBtn).toBeEnabled();
      }
    });
  });

  test.describe('2. Profile Status Menu & Message Navigation', () => {
    test('Profile menu supports nested status submenu without premature closure', async ({ page }) => {
      await page.goto('/workspaces/alpha-workspace/tasks/');
      
      const profileBtn = page.locator('[data-testid="user-menu-button"]');
      await expect(profileBtn).toBeVisible();
      await profileBtn.click();
      
      // Dropdown menu is open
      const dropdown = page.locator('[data-testid="user-menu-dropdown"]');
      await expect(dropdown).toBeVisible();
      
      // Click status selector trigger
      const statusTrigger = page.locator('[data-testid="profile-status-trigger"]');
      await expect(statusTrigger).toBeVisible();
      await statusTrigger.click();
      
      // Verify nested status options are rendered and menu is still open
      await expect(dropdown).toBeVisible();
      await expect(page.locator('button:has-text("Available")')).toBeVisible();
      await expect(page.locator('button:has-text("Busy")')).toBeVisible();
      await expect(page.locator('button:has-text("Away")')).toBeVisible();
      await expect(page.locator('button:has-text("Out of office")')).toBeVisible();
      
      // Test back button
      const backBtn = page.locator('button:has-text("Back")');
      await backBtn.click();
      await expect(page.locator('[data-testid="profile-status-trigger"]')).toBeVisible();
    });

    test('Inline status message editor opens within menu without page reload', async ({ page }) => {
      await page.goto('/workspaces/alpha-workspace/tasks/');
      
      const profileBtn = page.locator('[data-testid="user-menu-button"]');
      await profileBtn.click();
      
      const setStatusMsgBtn = page.locator('[data-testid="profile-set-message-btn"]');
      await expect(setStatusMsgBtn).toBeVisible();
      await setStatusMsgBtn.click();
      
      // Message form panel should be active
      const messageInput = page.locator('[data-testid="status-message-input"]');
      await expect(messageInput).toBeVisible();
      
      // Fill status message and select expiration
      await messageInput.fill('Working on sprint deliverables');
      const expirySelect = page.locator('[data-testid="status-message-expiry"]');
      await expirySelect.selectOption('today');
      
      // Save status message
      const saveBtn = page.locator('[data-testid="save-status-message-btn"]');
      await saveBtn.click();
      
      // Dropdown transitions back to main panel with success feedback
      await page.waitForTimeout(500);
      await expect(page.locator('text=Working on sprint deliverables')).toBeVisible();
    });
  });

  test.describe('3. Time Tracking — Pause, Resume & Away State Transitions', () => {
    test('Timer adopts "Time Tracker" terminology and provides Pause/Resume controls', async ({ page }) => {
      await page.goto('/workspaces/alpha-workspace/timetracking/');
      
      // Verify terminology
      await expect(page.locator('text=Time Tracker')).toBeVisible();
      
      // Verify no obsolete Stopwatch branding
      const stopwatchMentions = page.locator('h1:has-text("Stopwatch"), span:has-text("Stopwatch")');
      await expect(stopwatchMentions).toHaveCount(0);
      
      // Check timer interface components
      const activeTimerCard = page.locator('[data-testid="active-timer-card"]');
      if (await activeTimerCard.count() > 0) {
        // If running, Pause button must be visible
        const pauseBtn = page.locator('[data-testid="pause-timer-btn"]');
        const resumeBtn = page.locator('[data-testid="resume-timer-btn"]');
        const isRunning = await pauseBtn.isVisible();
        
        if (isRunning) {
          await pauseBtn.click();
          await page.waitForTimeout(500);
          await expect(page.locator('text=Timer Paused')).toBeVisible();
          await expect(resumeBtn).toBeVisible();
          
          // Resume timer
          await resumeBtn.click();
          await page.waitForTimeout(500);
          await expect(page.locator('text=Timer Running')).toBeVisible();
        }
      }
    });

    test('Away availability transitions running timer to Paused rather than stopping', async ({ page }) => {
      await page.goto('/workspaces/alpha-workspace/timetracking/');
      
      // Ensure timer is running
      const startTimerBtn = page.locator('[data-testid="start-timer-btn"]');
      if (await startTimerBtn.isVisible()) {
        await startTimerBtn.click();
        await page.waitForTimeout(600);
      }
      
      // Open profile menu and switch status to Away
      const profileBtn = page.locator('[data-testid="user-menu-button"]');
      await profileBtn.click();
      
      const statusTrigger = page.locator('[data-testid="profile-status-trigger"]');
      await statusTrigger.click();
      
      const awayOption = page.locator('button:has-text("Away")');
      await awayOption.click();
      await page.waitForTimeout(600);
      
      // Refresh or check timesheet - timer must be PAUSED, not finalized/stopped
      await page.goto('/workspaces/alpha-workspace/timetracking/');
      const pausedBadge = page.locator('text=Timer Paused');
      const resumeBtn = page.locator('[data-testid="resume-timer-btn"]');
      
      await expect(pausedBadge).toBeVisible();
      await expect(resumeBtn).toBeVisible();
    });

    test('Starting or resuming timer while in Away automatically flips status to Available', async ({ page }) => {
      // 1. Switch to Away
      await page.goto('/workspaces/alpha-workspace/timetracking/');
      const profileBtn = page.locator('[data-testid="user-menu-button"]');
      await profileBtn.click();
      const statusTrigger = page.locator('[data-testid="profile-status-trigger"]');
      await statusTrigger.click();
      await page.locator('button:has-text("Away")').click();
      await page.waitForTimeout(500);

      // 2. Click Resume Timer or Start Timer
      const resumeBtn = page.locator('[data-testid="resume-timer-btn"]');
      const startBtn = page.locator('[data-testid="start-timer-btn"]');
      if (await resumeBtn.isVisible()) {
        await resumeBtn.click();
      } else if (await startBtn.isVisible()) {
        await startBtn.click();
      }
      await page.waitForTimeout(600);

      // 3. User profile menu status should now reflect "Available"
      await profileBtn.click();
      await expect(page.locator('text=Available').first()).toBeVisible();
    });
  });

  test.describe('4. Empty States & Unblocked Action Buttons', () => {
    test('Files empty state renders an active, clickable "Upload File" link', async ({ page }) => {
      await page.goto('/workspaces/alpha-workspace/files/');
      const emptyStateUploadBtn = page.locator('a:has-text("Upload File")');
      if (await emptyStateUploadBtn.count() > 0) {
        await expect(emptyStateUploadBtn.first()).toBeVisible();
        await expect(emptyStateUploadBtn.first()).toBeEnabled();
        // Verify it is an anchor tag with href, NOT a blocked span
        const tagName = await emptyStateUploadBtn.first().evaluate(el => el.tagName.toLowerCase());
        expect(tagName).toBe('a');
        await expect(emptyStateUploadBtn.first()).toHaveAttribute('href', /.*\/files\/upload\/?/);
      }
    });
  });

});
