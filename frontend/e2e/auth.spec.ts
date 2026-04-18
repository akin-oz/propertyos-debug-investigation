/**
 * Auth E2E tests:
 *  - Login happy path (valid credentials → redirected to dashboard)
 *  - Login invalid credentials (error message shown, stay on /login)
 *  - /unauthorized renders without requiring a session
 *  - Protected route without session → redirected to /login
 *  - Refresh-during-login does not lose the authenticated state
 */

import { test, expect } from '@playwright/test';
import {
  installApiMocks,
  loginAs,
  TENANT_A,
} from './helpers/api-mocks';

// ---------------------------------------------------------------------------
// Login — happy path
// ---------------------------------------------------------------------------

test('login happy path: valid credentials redirect to dashboard', async ({ page }) => {
  await installApiMocks(page);
  await page.goto('/login');

  await loginAs(page, TENANT_A);

  // Should land on dashboard (or root which redirects there)
  await expect(page).toHaveURL(/\/(dashboard)?$/);

  // Dashboard heading is visible
  await expect(page.getByRole('heading', { name: /dashboard/i })).toBeVisible();
});

test('login happy path: revenue card renders after login', async ({ page }) => {
  await installApiMocks(page);
  await page.goto('/login');
  await loginAs(page, TENANT_A);

  // Wait for the revenue card — heading "Total Revenue"
  await expect(page.getByText('Total Revenue')).toBeVisible();
  // The formatted amount for 1234.56
  await expect(page.getByText(/USD\s+1[,.]234\.56/)).toBeVisible();
});

// ---------------------------------------------------------------------------
// Login — invalid credentials
// ---------------------------------------------------------------------------

test('login: invalid credentials show error, stay on /login', async ({ page }) => {
  await installApiMocks(page);
  await page.goto('/login');

  await page.fill('#email', TENANT_A.email);
  await page.fill('#password', 'wrong-password');
  await page.click('button[type="submit"]');

  // Should stay on /login — no redirect
  await expect(page).toHaveURL(/\/login/);

  // An error message appears (the login form shows a red alert div)
  await expect(
    page.locator('[class*="red"]').filter({ hasText: /invalid|credentials|authentication/i }),
  ).toBeVisible({ timeout: 5_000 });
});

test('login: empty fields — browser validation prevents submit', async ({ page }) => {
  await installApiMocks(page);
  await page.goto('/login');

  // Click submit with nothing filled in
  await page.click('button[type="submit"]');

  // Page should still be on /login (browser required-field validation fires)
  await expect(page).toHaveURL(/\/login/);
});

// ---------------------------------------------------------------------------
// /unauthorized — accessible without session
// ---------------------------------------------------------------------------

test('/unauthorized renders Access Denied without requiring login', async ({ page }) => {
  await installApiMocks(page);
  // Navigate directly — no auth, no redirect expected
  await page.goto('/unauthorized');

  await expect(page.getByRole('heading', { name: /access denied/i })).toBeVisible();
  await expect(page.getByText(/you don.t have permission/i)).toBeVisible();

  // Return to Dashboard link exists
  await expect(page.getByRole('link', { name: /return to dashboard/i })).toBeVisible();
});

// ---------------------------------------------------------------------------
// Protected route without session → redirect to /login
// ---------------------------------------------------------------------------

test('unauthenticated visit to /dashboard redirects to /login', async ({ page }) => {
  await installApiMocks(page);

  // No session in storage — clear it explicitly
  await page.goto('/login'); // load the app once so localStorage API is available
  await page.evaluate(() => localStorage.clear());

  // Now navigate to a protected route
  await page.goto('/dashboard');

  // ProtectedRoute should redirect to /login
  await page.waitForURL('**/login', { timeout: 8_000 });
  await expect(page).toHaveURL(/\/login/);
});

// ---------------------------------------------------------------------------
// Refresh-during-login does not lose state
// ---------------------------------------------------------------------------

test('page reload while authenticated keeps the session', async ({ page }) => {
  await installApiMocks(page);
  await page.goto('/login');
  await loginAs(page, TENANT_A);

  // Confirm on dashboard with revenue
  await expect(page.getByText('Total Revenue')).toBeVisible();

  // Reload — LocalAuthClient reads localStorage['base360-auth-token'] on init,
  // then calls /api/v1/auth/me to validate → session restored.
  await page.reload();

  // Should stay on dashboard (not redirected to /login)
  await expect(page).not.toHaveURL(/\/login/);
  await expect(page.getByText('Total Revenue')).toBeVisible({ timeout: 10_000 });
});

test('reload on /dashboard after login preserves property selection', async ({ page }) => {
  await installApiMocks(page);
  await page.goto('/login');
  await loginAs(page, TENANT_A);

  // Wait for property dropdown and revenue to settle
  await expect(page.getByText('Total Revenue')).toBeVisible();
  const selectedBefore = await page.locator('select').inputValue();

  await page.reload();

  // Still authenticated → still on dashboard → same property loaded
  await expect(page.getByText('Total Revenue')).toBeVisible({ timeout: 10_000 });
  // Dashboard auto-selects the first property — should match
  const selectedAfter = await page.locator('select').inputValue();
  expect(selectedAfter).toBe(selectedBefore);
});
