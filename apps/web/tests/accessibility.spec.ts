// SPDX-License-Identifier: Apache-2.0
import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

const routes = [
  'overview', 'models', 'sources', 'records', 'entities', 'master', 'matches',
  'survivorship', 'inbox', 'corrections', 'quality', 'simulator', 'operations',
  'relationships', 'access',
];

test('every light-mode workspace has no detectable WCAG A/AA violation', async ({ page }) => {
  for (const route of routes) {
    await page.goto(`/#/${route}`);
    await expect(page.locator('main h1')).toBeVisible();
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
      .analyze();
    expect(results.violations, `${route}: ${JSON.stringify(results.violations, null, 2)}`).toEqual([]);
  }
});
