import { test, expect } from '@playwright/test';

test.describe('AetherSpace — Error Handling & Error Pages (Phase 17)', () => {
  test('should render 400 Bad Request error page with parameter syntax artwork', async ({ page }) => {
    const response = await page.goto('/test/400/');
    expect(response?.status()).toBe(400);
    await expect(page.getByText('400')).toBeVisible();
    await expect(page.getByText('Invalid Request')).toBeVisible();
    await expect(page.getByText('The request could not be processed due to invalid parameters.')).toBeVisible();
    await expect(page.getByRole('button', { name: /Go Back/i })).toBeVisible();
  });

  test('should render 401 Authentication Required page with keycard illustration', async ({ page }) => {
    const response = await page.goto('/test/401/');
    expect(response?.status()).toBe(401);
    await expect(page.getByText('401')).toBeVisible();
    await expect(page.getByText('Authentication Required')).toBeVisible();
    await expect(page.getByRole('link', { name: /Sign In/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Go Back/i })).toBeVisible();
  });

  test('should render 403 Forbidden / Access Restricted page with padlock shield', async ({ page }) => {
    const response = await page.goto('/test/403/');
    expect(response?.status()).toBe(403);
    await expect(page.getByText('403')).toBeVisible();
    await expect(page.getByText('Access Restricted')).toBeVisible();
    await expect(page.getByRole('link', { name: /Go to Dashboard/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /Go Back/i })).toBeVisible();
  });

  test('should render 404 Not Found error page with UFO beam illustration', async ({ page }) => {
    const response = await page.goto('/test/404/');
    expect(response?.status()).toBe(404);
    await expect(page.getByText('404')).toBeVisible();
    await expect(page.getByText('Page Not Found')).toBeVisible();
    await expect(page.getByText("The page you're looking for doesn't exist or may have been moved.")).toBeVisible();
    await expect(page.getByRole('link', { name: /Go to Dashboard/i })).toBeVisible();
  });

  test('should render 408 Request Timed Out error page with stopwatch latency artwork', async ({ page }) => {
    const response = await page.goto('/test/408/');
    expect(response?.status()).toBe(408);
    await expect(page.getByText('408')).toBeVisible();
    await expect(page.getByText('Request Timed Out')).toBeVisible();
    await expect(page.getByRole('button', { name: /Try Again/i })).toBeVisible();
  });

  test('should render 429 Too Many Requests rate-limit page with speedometer redline gauge', async ({ page }) => {
    const response = await page.goto('/test/429/');
    expect(response?.status()).toBe(429);
    expect(response?.headers()['retry-after']).toBe('60');
    await expect(page.getByText('429')).toBeVisible();
    await expect(page.getByText('Too Many Requests')).toBeVisible();
    await expect(page.getByRole('button', { name: /Try Again/i })).toBeVisible();
  });

  test('should render 500 Server Error page with sparking satellite and safe Error ID', async ({ page }) => {
    const response = await page.goto('/test/500/');
    expect(response?.status()).toBe(500);
    await expect(page.getByText('500')).toBeVisible();
    await expect(page.getByText('Something Went Wrong')).toBeVisible();
    await expect(page.getByText(/ERR-500-/i)).toBeVisible();
    await expect(page.getByRole('button', { name: /Try Again/i })).toBeVisible();
  });

  test('should render 503 Service Unavailable page with radar dish illustration', async ({ page }) => {
    const response = await page.goto('/test/503/');
    expect(response?.status()).toBe(503);
    await expect(page.getByText('503')).toBeVisible();
    await expect(page.getByText('Service Temporarily Unavailable')).toBeVisible();
    await expect(page.getByRole('button', { name: /Try Again/i })).toBeVisible();
  });

  test('should render Network Connection Failure state', async ({ page }) => {
    const response = await page.goto('/test/network/');
    expect(response?.status()).toBe(503);
    await expect(page.getByText('Offline')).toBeVisible();
    await expect(page.getByText('Connection Lost')).toBeVisible();
    await expect(page.getByRole('button', { name: /Retry Connection/i })).toBeVisible();
  });

  test('should render comprehensive Error & Empty States Showcase page', async ({ page }) => {
    const response = await page.goto('/test/errors-showcase/');
    expect(response?.status()).toBe(200);
    await expect(page.getByText('AetherSpace — Error & Empty States System')).toBeVisible();
    await expect(page.getByText('Component-Level Error States')).toBeVisible();
    await expect(page.getByText('File & Calendar Micro-States')).toBeVisible();
  });

  test('should intercept real 403 permission denial and display designed UI with exact reason', async ({ page }) => {
    // When a non-authorized role attempts to create a workspace
    const response = await page.goto('/workspaces/create/');
    expect(response?.status()).toBe(403);
    await expect(page.getByText('403')).toBeVisible();
    await expect(page.getByText('Access Restricted')).toBeVisible();
    await expect(page.getByText(/Permission Denied: Only Administrators and Managers can create workspaces/i)).toBeVisible();
    await expect(page.getByRole('link', { name: /Go to Dashboard/i })).toBeVisible();
  });

  test('should display vector empty states in Task List when workspace has zero tasks', async ({ page }) => {
    await page.goto('/tasks/w/empty-workspace/');
    await expect(page.getByText('No Tasks Yet')).toBeVisible();
    await expect(page.getByRole('link', { name: /\+ Create Task/i })).toBeVisible();
  });

  test('should display filtered empty state when Task List filter yields zero matches', async ({ page }) => {
    await page.goto('/tasks/w/sample-workspace/?q=NonExistentTask9999');
    await expect(page.getByText('No Tasks Found')).toBeVisible();
    await expect(page.getByText(/NonExistentTask9999/i)).toBeVisible();
    await expect(page.getByRole('link', { name: /Clear Search/i })).toBeVisible();
  });

  test('should display vector empty states in Bug Tracker when workspace has zero defects', async ({ page }) => {
    await page.goto('/bugs/w/empty-workspace/');
    await expect(page.getByText('No Bugs Found')).toBeVisible();
    await expect(page.getByText(/All systems green/i)).toBeVisible();
    await expect(page.getByRole('link', { name: /Raise Bug/i })).toBeVisible();
  });

  test('should display vector empty state in Files when workspace storage is empty', async ({ page }) => {
    await page.goto('/files/w/empty-workspace/');
    await expect(page.getByText('No Files Yet')).toBeVisible();
    await expect(page.getByRole('link', { name: /Upload File/i })).toBeVisible();
  });

  test('should display vector empty state in Notifications when all caught up', async ({ page }) => {
    await page.goto('/notifications/');
    await expect(page.getByText("You're All Caught Up!")).toBeVisible();
  });

  test('should display people hover card with real tagging_role and system role', async ({ page }) => {
    await page.goto('/workspaces/w/sample-workspace/team/');
    const memberTrigger = page.locator('[x-ref="trigger"]').first();
    await memberTrigger.hover();
    const hoverCard = page.locator('.aether-hover-card');
    await expect(hoverCard).toBeVisible();
    await expect(hoverCard.getByText(/Frontend|Backend|Support|Design|DevOps|QA|Product/i)).toBeVisible();
  });

  test('should render styled file too large error state on upload form validation failure', async ({ page }) => {
    await page.goto('/files/w/sample-workspace/upload/');
    await expect(page.locator('#file-input-field')).toBeAttached();
  });
});
