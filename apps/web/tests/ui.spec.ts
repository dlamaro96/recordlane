// SPDX-License-Identifier: Apache-2.0
import { expect, test } from '@playwright/test';

test('all operator workspaces render live API state without console errors', async ({ page }) => {
  const errors: string[] = [];
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1, name: 'Operational overview' })).toBeVisible();
  for (const name of ['Model studio', 'Sources', 'Source records', 'Entity explorer', 'Master record',
    'Match workbench', 'Survivorship', 'Steward inbox', 'Merge & repair', 'Quality',
    'Config simulator', 'Publication', 'Relationships', 'Access & audit']) {
    await page.getByRole('button', { name }).click();
    await expect(page.locator('h1')).toBeVisible();
  }
  expect(errors).toEqual([]);
});

test('mobile layout has no horizontal document overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/#/master');
  await expect(page.getByRole('heading', { level: 1, name: 'Master record' })).toBeVisible();
  const dimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    content: document.documentElement.scrollWidth,
  }));
  expect(dimensions.content).toBeLessThanOrEqual(dimensions.viewport);
});
