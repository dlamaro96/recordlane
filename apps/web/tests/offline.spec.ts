// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';

test('offline core ingests, matches, approves, and publishes to the local consumer', async ({ page }) => {
  const suffix = Date.now().toString(36);
  const numericSuffix = Date.now().toString().slice(-10);
  const localId = `offline-${suffix}`;
  const operator = {
    'X-Recordlane-Role': 'integration_operator',
    'X-Recordlane-User': 'offline.operator',
  };
  const approver = {
    'X-Recordlane-Role': 'approver',
    'X-Recordlane-User': 'offline.approver',
  };
  const ingested = await page.request.post('/api/v1/sources/erp-postgres/ingest', {
    headers: operator,
    data: {
      domain: 'supplier',
      records: [{
        local_id: localId,
        version: '1',
        sequence: 1,
        values: {
          name: `Offline Supply ${suffix}`,
          tax_id: `AE${numericSuffix}`,
          country: 'AE',
          status: 'active',
        },
        verification: { tax_id: true },
      }],
    },
  });
  expect(ingested.ok()).toBeTruthy();

  const records = await (await page.request.get('/api/v1/source-records', { headers: approver })).json();
  const record = records.find((row: { local_id: string }) => row.local_id === localId);
  expect(record?.entity_id).toBeTruthy();
  const tasks = await (await page.request.get('/api/v1/review-tasks', { headers: approver })).json();
  const task = tasks.find((row: { entity_id: string; kind: string; status: string }) =>
    row.entity_id === record.entity_id && row.kind === 'master_approval' && row.status === 'open');
  expect(task?.id).toBeTruthy();
  const approved = await page.request.post(`/api/v1/review-tasks/${task.id}/decision`, {
    headers: approver,
    data: { decision: 'approve', reason: 'Offline acceptance evidence reviewed' },
  });
  expect(approved.ok()).toBeTruthy();
  const relayed = await page.request.post('/api/v1/operations/relay', { headers: operator });
  expect(relayed.ok()).toBeTruthy();
  expect((await relayed.json()).delivered).toBeGreaterThanOrEqual(1);
});
