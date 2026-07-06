/**
 * Loci PPT · PDF 导出脚本（v2）
 * 1) Playwright 逐页导出 19 个单页 PDF
 * 2) pdf-lib 合并为多页交付版
 */
const path = require('path');
const fs = require('fs');
const playwright = require('playwright');
const { chromium } = playwright;
const { PDFDocument } = require('pdf-lib');

const SLIDES_DIR = path.join(__dirname, 'docs', 'presentation', 'slides');
const OUTPUT_PDF = path.join(__dirname, 'docs', 'presentation', 'loci-presentation.pdf');
const TEMP_DIR = path.join(__dirname, 'docs', 'presentation', '_pdf_tmp');

function toFileUrl(p) {
  return 'file:///' + p.replace(/\\/g, '/');
}

async function exportOne(browser, slideFile, outPath) {
  // 每个 slide 用独立 page，避免缓存/尺寸污染
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await ctx.newPage();
  const url = toFileUrl(path.join(SLIDES_DIR, slideFile));
  await page.goto(url, { waitUntil: 'networkidle', timeout: 60000 });
  // 等待字体加载稳定
  await page.evaluate(() => document.fonts && document.fonts.ready);
  await page.waitForTimeout(800);
  await page.pdf({
    path: outPath,
    width: '1920px',
    height: '1080px',
    printBackground: true,
    margin: { top: 0, right: 0, bottom: 0, left: 0 },
    preferCSSPageSize: false,
  });
  await ctx.close();
}

async function main() {
  if (!fs.existsSync(SLIDES_DIR)) throw new Error('未找到 slides: ' + SLIDES_DIR);
  if (fs.existsSync(TEMP_DIR)) fs.rmSync(TEMP_DIR, { recursive: true });
  fs.mkdirSync(TEMP_DIR, { recursive: true });

  // 19 张 slides 按数字顺序
  const slideFiles = fs.readdirSync(SLIDES_DIR)
    .filter(f => /^\d{2}-.+\.html$/.test(f))
    .sort();

  console.log('[INFO] 找到 ' + slideFiles.length + ' 张 slides');
  if (slideFiles.length === 0) throw new Error('没有可导出的 slide');

  const browser = await chromium.launch();
  const tempPdfs = [];
  for (let i = 0; i < slideFiles.length; i++) {
    const f = slideFiles[i];
    const out = path.join(TEMP_DIR, f.replace('.html', '.pdf'));
    console.log('[PDF] (' + (i + 1) + '/' + slideFiles.length + ') ' + f);
    await exportOne(browser, f, out);
    tempPdfs.push(out);
  }
  await browser.close();

  // 合并 PDF
  console.log('[INFO] 合并 ' + tempPdfs.length + ' 个 PDF ...');
  const finalDoc = await PDFDocument.create();
  for (const p of tempPdfs) {
    const bytes = fs.readFileSync(p);
    const sub = await PDFDocument.load(bytes);
    const pages = await finalDoc.copyPages(sub, sub.getPageIndices());
    pages.forEach(pg => finalDoc.addPage(pg));
  }
  const merged = await finalDoc.save();
  fs.writeFileSync(OUTPUT_PDF, merged);
  const stat = fs.statSync(OUTPUT_PDF);
  console.log('[OK] PDF 已生成: ' + OUTPUT_PDF + ' (' + (stat.size / 1024).toFixed(1) + ' KB, ' + finalDoc.getPageCount() + ' 页)');

  // 清理临时目录
  fs.rmSync(TEMP_DIR, { recursive: true });
}

main().catch((e) => {
  console.error('FATAL:', e);
  process.exit(1);
});
