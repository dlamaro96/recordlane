// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';

test('real Keycloak authorization-code PKCE login creates a BFF session', async ({ page }) => {
  await expect.poll(async () => {
    const response = await page.request.get('/auth/login', { maxRedirects: 0 });
    return response.status();
  }, { timeout: 45_000 }).toBe(302);

  await page.goto('/auth/login?return_to=%2F%23%2Faccess');
  await expect(page).toHaveURL(/127\.0\.0\.1:58080\/realms\/recordlane/);
  await page.getByLabel(/username|email/i).fill('demo-steward');
  await page.getByRole('textbox', { name: 'Password' }).fill('demo-steward-change-me');
  await page.getByRole('button', { name: /sign in/i }).click();

  await expect(page).toHaveURL('http://127.0.0.1:8088/#/access');
  await expect(page.getByRole('heading', { level: 1, name: 'Access, identities & audit' })).toBeVisible();
  const session = await page.request.get('/auth/session');
  expect(await session.json()).toMatchObject({
    authenticated: true,
    workspace: 'demo',
    roles: expect.arrayContaining(['administrator', 'steward']),
  });

  const logout = await page.request.post('/auth/logout', { maxRedirects: 0 });
  expect(logout.status()).toBe(303);
  expect(logout.headers()['location']).toContain('/protocol/openid-connect/logout');
  expect(await (await page.request.get('/auth/session')).json()).toEqual({ authenticated: false });
});
