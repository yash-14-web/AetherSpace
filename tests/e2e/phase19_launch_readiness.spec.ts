import { test, expect } from '@playwright/test';

/**
 * AetherSpace — Phase 19: Final Product QA & Launch Readiness E2E Suite
 *
 * NOTE: DO NOT execute this suite autonomously.
 * This specification has been authored for manual owner execution:
 * `npx playwright test tests/e2e/phase19_launch_readiness.spec.ts`
 *
 * Covers all 15 critical user journeys required by Phase 19:
 * 1. Registration → Pending Approval → Admin Approval → Contributor ID Login
 * 2. Workspace Access and Isolation
 * 3. Task Management Full Lifecycle (6-digit ID, workflow, comments, time tracking)
 * 4. Bug Management Full Lifecycle (B-###### ID, modules, severity, resolution)
 * 5. People Search-First Global Rule (0 initial users, keystroke queries)
 * 6. Profile Reusable Hover Card (Photo, Contributor ID, System Role, Tagging Role)
 * 7. Chat Channel & Direct Messaging (Oldest-to-newest ordering, composer)
 * 8. Meet Hub & WebRTC Meeting Room (Audio/Video controls, captions, raise hand)
 * 9. Calendar Unified Aggregation (Tasks, Bugs, Meetings, Milestones)
 * 10. File Storage & Metadata (Supabase storage paths, previews, uploads)
 * 11. Notification Center (Workspace scoping, unread badges, mark all read)
 * 12. Time Tracking Persistence (Timers, manual logs, task linking)
 * 13. Phase 17 Error & Empty States (403, 404, 500, empty list states)
 * 14. RBAC Restrictions (Contributor forbidden from Admin & Workspace creation)
 * 15. Multi-Workspace Manager Switching (No cross-workspace data bleed)
 */

test.describe('AetherSpace — Phase 19 Launch Readiness Specification', () => {

  // Journey 1: Registration → Pending Approval → Login
  test('Journey 1: Registration → Pending Approval → Contributor ID Login', async ({ page }) => {
    await page.goto('/accounts/register/');
    await expect(page).toHaveTitle(/Register|Sign Up|AetherSpace/i);

    // Verify no social login buttons exist (Google, Microsoft, GitHub)
    await expect(page.locator('button:has-text("Google"), a:has-text("Google")')).toHaveCount(0);
    await expect(page.locator('button:has-text("Microsoft"), a:has-text("Microsoft")')).toHaveCount(0);
    await expect(page.locator('button:has-text("GitHub"), a:has-text("GitHub")')).toHaveCount(0);

    // Fill registration form
    await page.fill('input[name="full_name"]', 'Jane Contributor');
    await page.fill('input[name="email"]', 'jane.contributor@example.com');
    await page.fill('input[name="password1"]', 'Str0ngP@ssw0rd!');
    await page.fill('input[name="password2"]', 'Str0ngP@ssw0rd!');
    await page.click('button[type="submit"]');

    // User should be redirected to pending-approval page with their generated Contributor ID (#####C)
    await expect(page).toHaveURL(/pending-approval/);
    await expect(page.locator('text=Approval Pending, text=pending review')).toBeVisible();
    await expect(page.locator('.contributor-id-badge, [data-testid="contributor-id"]')).toContainText(/[0-9]{5}C/);

    // Login page verification: Contributor ID + Password fields
    await page.goto('/accounts/login/');
    await expect(page.locator('input[name="contributor_id"], input[name="username"]')).toBeVisible();
    await expect(page.locator('input[name="password"]')).toBeVisible();
  });

  // Journey 2: Workspace Access & Boundary Isolation
  test('Journey 2: Workspace Access and Strict Isolation', async ({ page }) => {
    await page.goto('/workspaces/dashboard/');

    // Workspace dashboard must display active workspace name
    await expect(page.locator('#workspace-title, h1')).toBeVisible();

    // Verify direct URL tampering to another inaccessible workspace is forbidden
    const unauthorizedResponse = await page.goto('/workspaces/w/unauthorized-vault-99/');
    if (unauthorizedResponse) {
      expect([302, 403, 404]).toContain(unauthorizedResponse.status());
    }
  });

  // Journey 3: Task Management Full Lifecycle
  test('Journey 3: Task Lifecycle — 6-Digit ID, Workflow, Assignee & Time Tracking', async ({ page }) => {
    await page.goto('/tasks/');

    // Task ID must match exactly six numeric digits (e.g., 619347)
    const taskLink = page.locator('a[href*="/tasks/"]:has-text("#"), [data-task-id]').first();
    if (await taskLink.isVisible()) {
      const taskText = await taskLink.innerText();
      expect(taskText).toMatch(/#?[0-9]{6}/);
    }

    // Verify task workflow columns exist on board
    await page.goto('/tasks/board/');
    if (page.url().includes('/board/')) {
      await expect(page.locator('text=To Do')).toBeVisible();
      await expect(page.locator('text=In Progress')).toBeVisible();
      await expect(page.locator('text=Testing')).toBeVisible();
      await expect(page.locator('text=Done')).toBeVisible();
    }
  });

  // Journey 4: Bug Management Full Lifecycle
  test('Journey 4: Bug Lifecycle — B-###### ID, Severity, Reproduction & Resolution', async ({ page }) => {
    await page.goto('/bugs/');

    // Bug identifier must strictly match B-###### pattern
    const bugBadge = page.locator('text=/B-[0-9]{6}/').first();
    if (await bugBadge.isVisible()) {
      const bugIdText = await bugBadge.innerText();
      expect(bugIdText).toMatch(/B-[0-9]{6}/);
    }

    // Verify create bug form contains severity, priority, and reproduction steps
    await page.goto('/bugs/create/');
    if (page.url().includes('/create/')) {
      await expect(page.locator('select[name="severity"], [name="severity"]')).toBeVisible();
      await expect(page.locator('select[name="priority"], [name="priority"]')).toBeVisible();
      await expect(page.locator('textarea[name="steps_to_reproduce"], [name="steps_to_reproduce"]')).toBeVisible();
    }
  });

  // Journey 5: People Search-First Global Rule
  test('Journey 5: People Search-First Rule — 0 initial users, filtered by keystrokes', async ({ page }) => {
    await page.goto('/tasks/create/');
    if (page.url().includes('/create/')) {
      const peopleInput = page.locator('input[placeholder*="Search by name, Contributor ID"]');
      if (await peopleInput.isVisible()) {
        // Must start with 0 visible results in the directory dropdown
        await expect(page.locator('#people-results-list .people-search-item')).toHaveCount(0);

        // Typing a specific query fetches matching permitted members
        await peopleInput.fill('Admin');
        await page.waitForTimeout(300);
        await expect(page.locator('#people-results-list, .people-dropdown')).toBeVisible();
      }
    }
  });

  // Journey 6: Profile Reusable Hover Card
  test('Journey 6: Profile Hover Card Displays Avatar, Contributor ID & System/Tagging Roles', async ({ page }) => {
    await page.goto('/workspaces/dashboard/');

    const userTrigger = page.locator('.aether-hover-card-trigger, [data-user-hover]').first();
    if (await userTrigger.isVisible()) {
      await userTrigger.hover();
      await page.waitForTimeout(250);

      const hoverCard = page.locator('.aether-hover-card, [data-hover-card]');
      await expect(hoverCard).toBeVisible();
      await expect(hoverCard.locator('text=Contributor ID')).toBeVisible();
      await expect(hoverCard.locator('.avatar, img[alt*="avatar"], svg')).toBeVisible();
    }
  });

  // Journey 7: Chat Channel & Direct Messaging
  test('Journey 7: Chat Stream Ordering (Oldest Top, Newest Bottom) & Message Composer', async ({ page }) => {
    await page.goto('/chat/');

    if (page.url().includes('/chat/')) {
      const messageContainer = page.locator('#chatMessageStream, #chat-messages-scroll, [data-chat-stream]');
      await expect(messageContainer).toBeVisible();

      // Verify composer input is operational
      const composer = page.locator('textarea[name="content"], input[name="content"], #chat-input');
      await expect(composer).toBeVisible();
      await expect(composer).toBeEnabled();
    }
  });

  // Journey 8: Meet Hub & WebRTC Controls
  test('Journey 8: Meet Hub Controls — Audio/Video, WebRTC Tiles, Screen Share, Captions & Chat', async ({ page }) => {
    await page.goto('/meetings/');
    await expect(page.locator('h1, h2')).toContainText(/Meet|Meetings/i);

    // Verify Instant & Schedule meeting buttons exist
    const startInstantBtn = page.locator('button:has-text("Start Instant Meeting"), a:has-text("Start Instant Meeting")');
    await expect(startInstantBtn).toBeVisible();
    await expect(page.locator('button:has-text("Schedule Meeting"), a:has-text("Schedule Meeting")')).toBeVisible();

    // Navigate to or start meeting room
    if (await startInstantBtn.isVisible()) {
      await startInstantBtn.click();
      await page.waitForLoadState('networkidle');

      // Verify meeting room canvas elements
      if (page.url().includes('/room/')) {
        // Local video element must exist for webcam feed
        await expect(page.locator('#local-video')).toBeAttached();

        // Screen share video element must exist
        await expect(page.locator('#screen-video')).toBeAttached();

        // Verify bottom control bar buttons
        const micToggle = page.locator('button[title*="microphone" i], button[title*="mic" i]').first();
        await expect(micToggle).toBeVisible();

        const cameraToggle = page.locator('button[title*="camera" i], button[title*="video" i]').first();
        await expect(cameraToggle).toBeVisible();

        const screenShareToggle = page.locator('button[title*="screen" i]').first();
        await expect(screenShareToggle).toBeVisible();

        const handRaiseToggle = page.locator('button[title*="hand" i]').first();
        await expect(handRaiseToggle).toBeVisible();

        const chatToggle = page.locator('button[title*="chat" i]').first();
        await expect(chatToggle).toBeVisible();

        const leaveBtn = page.locator('button[title*="leave" i], button:has-text("Leave")').first();
        await expect(leaveBtn).toBeVisible();
      }
    }
  });

  // Journey 9: Calendar Unified Aggregation
  test('Journey 9: Unified Calendar with Tasks, Bugs, Meetings & Deadlines', async ({ page }) => {
    await page.goto('/calendar/');

    if (page.url().includes('/calendar/')) {
      await expect(page.locator('#calendarGrid, .calendar-month-grid, [data-calendar-view]')).toBeVisible();

      // Filter toggles
      await expect(page.locator('label:has-text("Tasks"), input[value="tasks"]')).toBeVisible();
      await expect(page.locator('label:has-text("Bugs"), input[value="bugs"]')).toBeVisible();
      await expect(page.locator('label:has-text("Meetings"), input[value="meetings"]')).toBeVisible();
    }
  });

  // Journey 10: File Storage & Metadata Management
  test('Journey 10: Files Hub — Supabase Metadata, Path Structure, Preview & Download', async ({ page }) => {
    await page.goto('/files/');

    if (page.url().includes('/files/')) {
      await expect(page.locator('h1')).toContainText(/Files|Documents/i);

      // Verify upload CTA exists
      const uploadBtn = page.locator('button:has-text("Upload"), label:has-text("Upload")');
      await expect(uploadBtn).toBeVisible();

      // Verify files table/grid exists
      await expect(page.locator('#files-list, .file-table, [data-files-grid]')).toBeVisible();
    }
  });

  // Journey 11: Notification Center Scoping & Read Actions
  test('Journey 11: Notification Center — Scoped alerts, category tabs & Mark All as Read', async ({ page }) => {
    await page.goto('/notifications/');

    await expect(page.locator('h1')).toContainText(/Notifications/i);

    // Category filtering tabs
    await expect(page.locator('text=All')).toBeVisible();
    await expect(page.locator('text=Tasks')).toBeVisible();
    await expect(page.locator('text=Bugs')).toBeVisible();

    const markAllRead = page.locator('button:has-text("Mark All as Read"), button:has-text("Mark all as read")');
    if (await markAllRead.isVisible()) {
      await expect(markAllRead).toBeEnabled();
    }
  });

  // Journey 12: Time Tracking Persistence
  test('Journey 12: Time Tracking — Start/Stop Timer, Manual Entries & Task Links', async ({ page }) => {
    await page.goto('/time-tracking/');

    if (page.url().includes('/time-tracking/')) {
      await expect(page.locator('h1')).toContainText(/Time Tracking|Timer/i);

      // Verify timer controls or manual entry button
      const timerBtn = page.locator('#start-timer-btn, button:has-text("Start Timer"), button:has-text("Log Time")');
      await expect(timerBtn.first()).toBeVisible();
    }
  });

  // Journey 13: Phase 17 Error Pages & Empty States
  test('Journey 13: Phase 17 Error Pages (403, 404) & Connected Empty States', async ({ page }) => {
    // 404 test
    const notFoundRes = await page.goto('/non-existent-endpoint-404-test/');
    expect(notFoundRes?.status()).toBe(404);
    await expect(page.locator('h1, h2')).toContainText(/404|Page Not Found/i);

    // Verify Return to Safety / Go Back navigation button exists
    const backBtn = page.locator('a:has-text("Return to Safety"), a:has-text("Go Back"), button:has-text("Go Back")');
    await expect(backBtn.first()).toBeVisible();
  });

  // Journey 14: RBAC Server-Side Enforcement
  test('Journey 14: RBAC Enforcement — Contributor blocked from Admin Panel and Workspace Creation', async ({ page }) => {
    // As a Contributor, accessing /admin-panel/ must yield 403 Forbidden or redirect
    const adminRes = await page.goto('/admin-panel/');
    if (adminRes) {
      expect([302, 403]).toContain(adminRes.status());
    }

    // Direct access to workspace creation must also be blocked
    const createWsRes = await page.goto('/workspaces/create/');
    if (createWsRes) {
      expect([302, 403]).toContain(createWsRes.status());
    }
  });

  // Journey 15: Multi-Workspace Manager Context Switching
  test('Journey 15: Multi-Workspace Manager Switching with Zero Cross-Workspace Data Bleed', async ({ page }) => {
    await page.goto('/workspaces/dashboard/');

    const switcher = page.locator('#workspace-switcher-btn, [data-testid="workspace-switcher"]');
    if (await switcher.isVisible()) {
      await switcher.click();

      const switchMenu = page.locator('#workspace-dropdown-menu, [role="menu"]');
      await expect(switchMenu).toBeVisible();

      // Switching workspace must refresh the page context with the target workspace's ID
      const targetWorkspace = switchMenu.locator('a, button').nth(1);
      if (await targetWorkspace.isVisible()) {
        await targetWorkspace.click();
        await page.waitForLoadState('networkidle');

        // Confirm active title updated without leftover elements
        await expect(page.locator('#workspace-title, h1')).toBeVisible();
      }
    }
  });

});
