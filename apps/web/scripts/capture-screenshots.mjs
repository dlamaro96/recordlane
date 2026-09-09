// SPDX-License-Identifier: Apache-2.0
import { chromium } from 'playwright';
import { createHash } from 'node:crypto';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const output=resolve(process.cwd(),'../../assets/screenshots');
const base=process.env.RECORDLANE_SCREENSHOT_URL ?? 'http://127.0.0.1:8088';
const routes=['overview','models','sources','records','entities','master','matches','inbox','corrections','quality','simulator','operations','relationships','access'];
await mkdir(output,{recursive:true});
const browser=await chromium.launch(); const page=await browser.newPage({viewport:{width:1440,height:900},colorScheme:'dark'});
const errors=[]; page.on('console',message=>{if(message.type()==='error')errors.push(message.text())});
const captures=[];
for(const route of routes){
  await page.goto(`${base}/#/${route}`,{waitUntil:'networkidle'}); await page.locator('h1').waitFor();
  const path=resolve(output,`${route}-dark-1440.png`); await page.screenshot({path,fullPage:true});
  captures.push(path);
}
await page.evaluate(()=>localStorage.setItem('rl-theme','light')); await page.goto(`${base}/#/overview`,{waitUntil:'networkidle'});
const light=resolve(output,'overview-light-1440.png'); await page.screenshot({path:light,fullPage:true}); captures.push(light);
await page.setViewportSize({width:390,height:844}); await page.evaluate(()=>localStorage.setItem('rl-theme','dark')); await page.goto(`${base}/#/master`,{waitUntil:'networkidle'});
const dimensions=await page.evaluate(()=>({clientWidth:document.documentElement.clientWidth,scrollWidth:document.documentElement.scrollWidth}));
if(dimensions.scrollWidth>dimensions.clientWidth) throw new Error(`mobile overflow: ${JSON.stringify(dimensions)}`);
const narrow=resolve(output,'master-dark-390.png'); await page.screenshot({path:narrow,fullPage:true}); captures.push(narrow);
await browser.close(); if(errors.length) throw new Error(`browser console errors: ${errors.join('; ')}`);
const files=[]; for(const path of captures){const data=await readFile(path);files.push({file:path.split('/').at(-1),sha256:createHash('sha256').update(data).digest('hex')})}
await writeFile(resolve(output,'manifest.json'),JSON.stringify({generated_at:new Date().toISOString(),base_url:base,tool:'Playwright 1.63.0 Chromium',files},null,2)+'\n');
console.log(`Captured ${captures.length} real application screenshots from ${base}`);
