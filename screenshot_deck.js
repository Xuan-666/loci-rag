/**
 * Loci PPT 渲染验证脚本（v4 · 本地 node_modules 加载）
 */
const path = require('path');
const fs = require('fs');

// 用本地 node_modules 加载 playwright（安装于 npm install playwright@1.60.0 --no-save）
const playwright = require('playwright');
const { chromium } = playwright;

const SLIDES_DIR = path.join(__dirname, 'docs', 'presentation', 'slides');
const THUMBS_DIR = path.join(__dirname, 'docs', 'presentation', 'thumbs');
const DECK_INDEX = path.join(__dirname, 'docs', 'presentation', 'index.html');

function toFileUrl(p) {
  return 'file:///' + p.replace(/\\/g, '/');
}

async function main() {
  if (!fs.existsSync(THUMBS_DIR)) fs.mkdirSync(THUMBS_DIR, { recursive: true });
  console.log('[INFO] SLIDES_DIR: ' + SLIDES_DIR);
  console.log('[INFO] THUMBS_DIR: ' + THUMBS_DIR);
  console.log('[INFO] slides 数量: ' + fs.readdirSync(SLIDES_DIR).length);

  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await ctx.newPage();

  const errors = [];
  page.on('pageerror', (e) => errors.push('PAGE ERROR: ' + e.message));
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push('CONSOLE ERROR: ' + msg.text());
  });

  // 19 张 slides
  for (let i = 1; i <= 19; i++) {
    const num = String(i).padStart(2, '0');
    const fileName = fs.readdirSync(SLIDES_DIR).find(f => f.startsWith(num + '-'));
    if (!fileName) { console.log('[SKIP] ' + num + ' not found'); continue; }
    const slidePath = toFileUrl(path.join(SLIDES_DIR, fileName));
    try {
      await page.goto(slidePath, { waitUntil: 'domcontentloaded', timeout: 30000 });
    } catch (e) {
      console.log('[ERR] ' + num + ' - ' + e.message);
      continue;
    }
    await page.waitForTimeout(2000);
    const out = path.join(THUMBS_DIR, num + '.png');
    await page.screenshot({ path: out, fullPage: false });
    console.log('[OK] ' + num + ' -> ' + fileName);
  }

  // 概览 grid
  await page.goto(toFileUrl(DECK_INDEX) + '?ov=grid', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
  await page.screenshot({ path: path.join(THUMBS_DIR, '_overview_grid.png'), fullPage: false });
  console.log('[OK] overview grid');

  // 概览 gallery
  await page.goto(toFileUrl(DECK_INDEX) + '?ov=gallery', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
  await page.screenshot({ path: path.join(THUMBS_DIR, '_overview_gallery.png'), fullPage: false });
  console.log('[OK] overview gallery');

  // 演示模式 #1
  await page.goto(toFileUrl(DECK_INDEX) + '#1', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
  await page.screenshot({ path: path.join(THUMBS_DIR, '_present_01.png'), fullPage: false });
  console.log('[OK] present mode #1');

  await browser.close();

  console.log('\n=== 完成 ===');
  console.log('截图目录: ' + THUMBS_DIR);
  console.log('错误数: ' + errors.length);
  if (errors.length > 0) {
    console.log('\n错误明细:');
    errors.forEach((e) => console.log('  - ' + e));
  }
}

main().catch((e) => {
  console.error('FATAL:', e);
  process.exit(1);
});
