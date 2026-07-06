/**
 * Loci PPT · PDF 元数据补全脚本
 * 设置标题/作者/主题等 PDF 元数据
 */
const fs = require('fs');
const path = require('path');
const { PDFDocument } = require('pdf-lib');

const PDF_PATH = path.join(__dirname, 'docs', 'presentation', 'loci-presentation.pdf');

async function main() {
  const bytes = fs.readFileSync(PDF_PATH);
  const doc = await PDFDocument.load(bytes);
  doc.setTitle('Loci · 本地知识库 RAG 智能问答系统 · 项目演示');
  doc.setAuthor('炳材');
  doc.setSubject('NLP 实验 3 · 19 页项目演示');
  doc.setKeywords(['Loci', 'RAG', 'LangChain', 'FAISS', 'Ollama', '本地知识库']);
  doc.setProducer('huashu-design · Playwright · pdf-lib');
  doc.setCreator('Loci Presentation Pipeline');
  const out = await doc.save();
  fs.writeFileSync(PDF_PATH, out);
  console.log('[OK] 元数据已写入');
  console.log('  Title:    ' + doc.getTitle());
  console.log('  Author:   ' + doc.getAuthor());
  console.log('  Subject:  ' + doc.getSubject());
  console.log('  Keywords: ' + doc.getKeywords());
  console.log('  Pages:    ' + doc.getPageCount());
}

main().catch((e) => { console.error(e); process.exit(1); });
