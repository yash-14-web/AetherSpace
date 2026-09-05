import { test, expect } from '@playwright/test';

test.describe('Error Handling Pages', () => {
  test('should render 400 Bad Request error page', async ({ page }) => {
    const response = await page.goto('/test/400/');
    expect(response?.status()).toBe(400);
    await expect(page.getByText('Invalid Request')).toBeVisible();
    await expect(page.getByRole('button', { name: /Go Back/i })).toBeVisible();
  });

  test('should render 403 Forbidden page with Request Access button', async ({ page }) => {
    const response = await page.goto('/test/403/');
    expect(response?.status()).toBe(403);
    await expect(page.getByText('Access Restricted')).toBeVisible();
    await expect(page.getByRole('button', { name: /Request Access/i })).toBeVisible();
  });

  test('should render 404 Not Found error page on missing route', async ({ page }) => {
    const response = await page.goto('/non-existent-workspace-route-404/');
    expect(response?.status()).toBe(404);
    await expect(page.getByText('Page Not Found')).toBeVisible();
  });
});
