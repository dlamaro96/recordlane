// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';

test.describe.configure({ mode: 'serial' });

test('UI authors a domain, exports it, and imports it into another workspace', async ({ page }) => {
  const suffix = Date.now().toString(36);
  const domainKey = `asset_${suffix}`;
  const target = `import-${suffix}`;
  await page.goto('/#/models');
  await expect(page.getByRole('heading', { level: 1, name: 'Domain model studio' })).toBeVisible();
  await page.getByLabel('Domain key').fill(domainKey);
  await page.getByLabel('Domain name').fill(`Asset ${suffix}`);
  await page.getByLabel('Identifier attribute').fill('serial_number');
  await page.getByRole('button', { name: 'Create domain & rule' }).click();
  await expect(page.getByText(/domain and serial_number rule validated and persisted/)).toBeVisible();

  const bundleResponse = await page.request.get('/api/v1/workspace-bundle', {
    headers: { 'X-Recordlane-Role': 'administrator', 'X-Recordlane-Workspace': 'demo' },
  });
  expect(bundleResponse.ok()).toBeTruthy();
  const bundle = await bundleResponse.json();
  expect(bundle.spec.domains.some((domain: { key: string }) => domain.key === domainKey)).toBeTruthy();

  await page.getByLabel('Target workspace slug').fill(target);
  await page.getByLabel('Target workspace name').fill(`Imported ${suffix}`);
  await page.locator('label.file-button.primary input[type=file]').setInputFiles({
    name: 'recordlane-workspace-bundle.json',
    mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify(bundle)),
  });
  await expect(page.getByText(`Bundle imported into ${target}`)).toBeVisible();
  const imported = await page.request.get('/api/v1/domains', {
    headers: { 'X-Recordlane-Role': 'administrator', 'X-Recordlane-Workspace': target },
  });
  expect(imported.ok()).toBeTruthy();
  expect((await imported.json()).some((domain: { key: string }) => domain.key === domainKey)).toBeTruthy();
});

test('source, relationship, correction preview, and split controls persist backend state', async ({ page }) => {
  const suffix = Date.now().toString(36);
  await page.goto('/#/sources');
  const liveHttpSource = page.locator('.source-card').filter({ hasText: 'Vendor Portal API' });
  await liveHttpSource.getByRole('button', { name: 'Test connection' }).click();
  await expect(page.getByText('Vendor Portal API connection verified over rest')).toBeVisible();
  await page.getByLabel('Source key').fill(`file_${suffix}`);
  await page.getByLabel('Source name').fill(`File ${suffix}`);
  await page.getByLabel('Source kind').selectOption('jsonl');
  await page.getByLabel('Source location or secret reference').fill(`/data/${suffix}.jsonl`);
  await page.getByRole('button', { name: 'Save source' }).click();
  await expect(page.getByText('Source definition validated and persisted')).toBeVisible();

  await page.getByRole('button', { name: 'Relationships' }).click();
  await page.getByLabel('Relationship type').fill(`supplies_${suffix}`);
  await page.getByRole('button', { name: 'Create relationship' }).click();
  await expect(page.getByText('Governed relationship persisted with actor provenance')).toBeVisible();

  await page.getByRole('button', { name: 'Merge & repair' }).click();
  await page.getByRole('button', { name: 'Preview impact' }).click();
  await expect(page.getByText('current contributions')).toBeVisible();
  const split = page.getByRole('button', { name: 'Propose split' });
  await expect(split).toBeEnabled();
  await split.click();
  await expect(page.getByText(/Split proposal .* opened for independent approval/)).toBeVisible();
});

test('quality assistant uses authorized backend evidence and remains non-agentic', async ({ page }) => {
  await page.goto('/#/quality');
  await expect(page.getByRole('heading', { level: 1, name: 'Quality & profiling' })).toBeVisible();
  await page.getByRole('button', { name: 'Explain profile' }).click();
  await expect(page.getByText(/evidence reports \d+ invalid record/)).toBeVisible();
  await expect(page.getByText(/cannot decide or approve|causal claims require steward review/i)).toBeVisible();

  const audit = await page.request.get('/api/v1/audit', {
    headers: { 'X-Recordlane-Role': 'administrator', 'X-Recordlane-Workspace': 'demo' },
  });
  expect(audit.ok()).toBeTruthy();
  expect((await audit.json()).some((entry: { action: string }) => entry.action === 'assistant.draft_created')).toBeTruthy();
});

test('administrator can issue a scoped service identity and store a non-disclosing secret reference', async ({ page }) => {
  const suffix = Date.now().toString(36);
  const accountName = `browser-agent-${suffix}`;
  const secretName = `warehouse-token-${suffix}`;

  await page.goto('/#/access');
  await expect(page.getByRole('heading', { level: 1, name: 'Access, identities & audit' })).toBeVisible();

  await page.getByLabel('Service account name').fill(accountName);
  await page.getByRole('button', { name: 'Issue one-time credential' }).click();
  await expect(page.getByText('DISPLAYED ONCE')).toBeVisible();
  await expect(page.locator('.issued-secret code')).toContainText('rl_sa_demo_');

  await page.getByLabel('Secret reference name').fill(secretName);
  await page.getByLabel('Secret value').fill(`synthetic-${suffix}`);
  await page.getByRole('button', { name: 'Store encrypted reference' }).click();
  const secretRow = page.locator('.role-row').filter({ hasText: `secret:${secretName}` });
  await expect(secretRow).toBeVisible();
  await secretRow.getByRole('button', { name: 'Test access' }).click();
  await expect(page.getByText('Secret resolved without disclosure')).toBeVisible();

  const accountRow = page.locator('.role-row').filter({ hasText: accountName });
  await accountRow.getByRole('button', { name: 'Revoke' }).click();
  await expect(accountRow.getByRole('button', { name: 'revoked' })).toBeVisible();

  const headers = { 'X-Recordlane-Role': 'administrator', 'X-Recordlane-Workspace': 'demo' };
  const accountsResponse = await page.request.get('/api/v1/service-accounts', { headers });
  const secretsResponse = await page.request.get('/api/v1/secrets', { headers });
  expect(accountsResponse.ok()).toBeTruthy();
  expect(secretsResponse.ok()).toBeTruthy();
  const serializedAccounts = JSON.stringify(await accountsResponse.json());
  const serializedSecrets = JSON.stringify(await secretsResponse.json());
  expect(serializedAccounts).not.toContain('secret_verifier');
  expect(serializedAccounts).not.toContain('secret_salt');
  expect(serializedAccounts).not.toContain('token_prefix');
  expect(serializedSecrets).not.toContain('encrypted_value');
  expect(serializedSecrets).not.toContain(`synthetic-${suffix}`);
});
