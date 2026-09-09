// SPDX-License-Identifier: Apache-2.0
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: 'tests',
  timeout: 30_000,
  use: { baseURL: 'http://127.0.0.1:8088', viewport: { width: 1440, height: 900 }, colorScheme: 'dark' },
  outputDir: '../../test-results/playwright',
});
