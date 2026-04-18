/**
 * Shared mock data and network intercept helpers for Playwright E2E tests.
 *
 * All tests intercept the backend at http://localhost:8000 so that no live
 * Supabase / FastAPI instance is required.  Auth is simulated via the
 * LocalAuthClient which calls /api/v1/auth/login and stores a token in
 * localStorage['base360-auth-token'].
 */

import type { Page } from '@playwright/test';

// ---------------------------------------------------------------------------
// Tenant fixtures
// ---------------------------------------------------------------------------

export const TENANT_A = {
  email: 'sunset@propertyflow.com',
  password: 'client_a_2024',
  token: 'e2e-token-tenant-a',
  user: {
    id: 'user-id-tenant-a',
    email: 'sunset@propertyflow.com',
    tenant_id: 'tenant-a',
    app_metadata: { tenant_id: 'tenant-a' },
    user_metadata: { tenant_id: 'tenant-a' },
    is_admin: false,
  },
  properties: {
    data: [{ id: 'prop-001', name: 'Beach House Alpha', timezone: 'America/Los_Angeles' }],
    total: 1,
  },
  revenue: {
    property_id: 'prop-001',
    total_revenue: '1234.56',
    currency: 'USD',
    reservations_count: 5,
  },
} as const;

export const TENANT_B = {
  email: 'ocean@propertyflow.com',
  password: 'client_b_2024',
  token: 'e2e-token-tenant-b',
  user: {
    id: 'user-id-tenant-b',
    email: 'ocean@propertyflow.com',
    tenant_id: 'tenant-b',
    app_metadata: { tenant_id: 'tenant-b' },
    user_metadata: { tenant_id: 'tenant-b' },
    is_admin: false,
  },
  properties: {
    data: [{ id: 'prop-001', name: 'Oceanview Suite', timezone: 'America/New_York' }],
    total: 1,
  },
  revenue: {
    property_id: 'prop-001',
    total_revenue: '789.00',
    currency: 'USD',
    reservations_count: 3,
  },
} as const;

// ---------------------------------------------------------------------------
// Tenant lookup by token
// ---------------------------------------------------------------------------

type TenantFixture = typeof TENANT_A | typeof TENANT_B;

function tenantByToken(token: string): TenantFixture | null {
  if (token === TENANT_A.token) return TENANT_A;
  if (token === TENANT_B.token) return TENANT_B;
  return null;
}

function tokenFromAuthHeader(headers: Record<string, string>): string {
  return (headers['authorization'] || '').replace(/^Bearer\s+/i, '');
}

// ---------------------------------------------------------------------------
// Route installer
// ---------------------------------------------------------------------------

/**
 * Installs all backend mock routes on `page`.  Call once per test before
 * navigating anywhere.  Routes survive page.reload() and React Router
 * navigations; they are torn down automatically when the page is closed.
 */
export async function installApiMocks(page: Page): Promise<void> {
  // POST /api/v1/auth/login
  await page.route('**/api/v1/auth/login', async (route) => {
    let body: { email?: string; password?: string } = {};
    try { body = JSON.parse(route.request().postData() || '{}'); } catch { /* ok */ }

    const tenant =
      body.email === TENANT_A.email && body.password === TENANT_A.password ? TENANT_A
        : body.email === TENANT_B.email && body.password === TENANT_B.password ? TENANT_B
          : null;

    if (tenant) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ access_token: tenant.token, token_type: 'bearer', user: tenant.user }),
      });
    } else {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Invalid login credentials' }),
      });
    }
  });

  // GET /api/v1/auth/me  — session validation, called by LocalAuthClient on every getSession()
  await page.route('**/api/v1/auth/me', async (route) => {
    const tenant = tenantByToken(tokenFromAuthHeader(route.request().headers()));
    if (tenant) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(tenant.user) });
    } else {
      await route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'Unauthorized' }) });
    }
  });

  // POST /api/v1/auth/logout
  await page.route('**/api/v1/auth/logout', async (route) => {
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
  });

  // GET /api/v1/properties
  await page.route('**/api/v1/properties*', async (route) => {
    const tenant = tenantByToken(tokenFromAuthHeader(route.request().headers()));
    if (tenant) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(tenant.properties) });
    } else {
      await route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'Unauthorized' }) });
    }
  });

  // GET /api/v1/dashboard/summary
  await page.route('**/api/v1/dashboard/summary*', async (route) => {
    const tenant = tenantByToken(tokenFromAuthHeader(route.request().headers()));
    if (tenant) {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(tenant.revenue) });
    } else {
      await route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: 'Unauthorized' }) });
    }
  });
}

// ---------------------------------------------------------------------------
// Auth helpers
// ---------------------------------------------------------------------------

/**
 * Fills the login form and submits it.  Waits for navigation away from /login.
 */
export async function loginAs(page: Page, tenant: TenantFixture): Promise<void> {
  await page.fill('#email', tenant.email);
  await page.fill('#password', tenant.password);
  await page.click('button[type="submit"]');
  // LocalAuthClient triggers window.location.href after signOut, and React Router
  // redirects after login.  Wait until we leave the login page.
  await page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 10_000 });
}

/**
 * Clicks the "Sign out" button and waits for the redirect back to /login.
 */
export async function logout(page: Page): Promise<void> {
  await page.getByRole('button', { name: /sign out/i }).click();
  await page.waitForURL('**/login', { timeout: 10_000 });
}

/**
 * Returns all auth-related keys currently in localStorage.
 */
export async function authStorageKeys(page: Page): Promise<string[]> {
  return page.evaluate(() =>
    Object.keys(localStorage).filter(
      (k) => k === 'base360-auth-token' || k.startsWith('sb-'),
    ),
  );
}

/**
 * Asserts all auth storage is empty (localStorage auth keys + all of sessionStorage).
 */
export async function assertStorageCleared(page: Page): Promise<void> {
  const authKeys = await authStorageKeys(page);
  if (authKeys.length > 0) {
    throw new Error(`Auth storage still present after logout: ${authKeys.join(', ')}`);
  }

  const ssLength = await page.evaluate(() => sessionStorage.length);
  if (ssLength > 0) {
    throw new Error(`sessionStorage not empty after logout: ${ssLength} item(s)`);
  }
}
