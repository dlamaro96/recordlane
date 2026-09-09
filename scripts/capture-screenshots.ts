// SPDX-License-Identifier: Apache-2.0
import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const baseURL = process.env.RECORDLANE_URL || 'http://127.0.0.1:8088';
const output = new URL('../assets/screenshots/', import.meta.url).pathname;
const pages = ['overview','models','sources','records','entities','master','matches','inbox','corrections','quality','simulator','operations','relationships','access'];
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: 'dark' });
const page = await context.newPage();
for (const route of pages) {
  await page.goto(`${baseURL}/#${route}`);
  await page.getByRole('heading', { level: 1 }).waitFor();
  await page.screenshot({ path: `${output}/${route}-dark-1440.png`, fullPage: true });
}
await context.close();
const narrow = await browser.newContext({ viewport: { width: 390, height: 844 }, colorScheme: 'dark' });
const mobile = await narrow.newPage();
await mobile.goto(`${baseURL}/#master`);
await mobile.getByRole('heading', { level: 1 }).waitFor();
await mobile.screenshot({ path: `${output}/master-dark-390.png`, fullPage: true });
await narrow.close();
await browser.close();

