// =============================================================================
// Loci · 本地知识库 RAG 问答系统 - 前端应用
// 设计: 花叔design B版 (Perplexity 学术图书馆)
// 5 个 Tab: 智能问答 / 知识库 / 收藏 / 会话 / 设置; SSE 流式问答
// =============================================================================
'use strict';

// =============================================================================
// 全局状态
// =============================================================================
const API_BASE = '';  // 同一域名
const state = {
  currentTab: 'chat',
  engineStatus: null,
  documents: [],
  tags: [],
  favorites: [],
  sessions: [],
  currentSessionId: null,
  // 流式状态
  streaming: false,
  eventSource: null,
  // 当前 session 历史
  messages: [],
  // 检索状态
  sources: [],
  isFallback: false,
  // 主题
  darkMode: false,
  // 知识库子 Tab
  kbSubTab: 'docs',
  // 导出选中状态
  selectedFavs: new Set(),
  selectedSess: new Set(),
  // 用户设置（后端持久化）
  userSettings: null,
};

// =============================================================================
// API 调用层
// =============================================================================
async function api(path, options = {}) {
  const url = API_BASE + path;
  const opts = {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  };
  if (options.body && typeof options.body !== 'string') {
    opts.body = JSON.stringify(options.body);
  }
  try {
    const resp = await fetch(url, opts);
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`API ${resp.status}: ${text}`);
    }
    return await resp.json();
  } catch (e) {
    console.error('[API]', e);
    showToast('错误', e.message, 'error');
    throw e;
  }
}

async function apiUpload(files) {
  const fd = new FormData();
  for (const f of files) fd.append('files', f);
  const resp = await fetch('/api/knowledge_base/upload', { method: 'POST', body: fd });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`上传失败: ${text}`);
  }
  return await resp.json();
}

// =============================================================================
// 工具
// =============================================================================
function $(sel, root = document) { return root.querySelector(sel); }
function $$(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

function escHtml(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function fmtTime(s) {
  if (!s) return '';
  return s.replace('T', ' ').slice(0, 16);
}

function showToast(title, msg, type = 'info') {
  let layer = $('#toastLayer');
  if (!layer) {
    layer = document.createElement('div');
    layer.id = 'toastLayer';
    layer.style.cssText = 'position:fixed;top:20px;right:20px;z-index:9999;display:flex;flex-direction:column;gap:8px;';
    document.body.appendChild(layer);
  }
  const colors = { info: 'var(--accent)', success: '#4a9b6e', error: '#b85c38', warn: 'var(--warning)' };
  const t = document.createElement('div');
  t.style.cssText = `background:var(--bg-card);border:1px solid var(--line);border-left:3px solid ${colors[type]};border-radius:8px;padding:10px 14px;min-width:240px;box-shadow:var(--shadow-2);font-size:13px;animation:slideIn 0.3s;`;
  t.innerHTML = `<div style="font-weight:500;margin-bottom:2px">${escHtml(title)}</div><div style="color:var(--ink-soft);font-size:12px">${escHtml(msg)}</div>`;
  layer.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

// =============================================================================
// 引擎状态初始化
// =============================================================================
async function loadEngineStatus() {
  try {
    state.engineStatus = await api('/api/engine_status');
    updateEnginePill();
  } catch (e) {
    console.error('loadEngineStatus failed', e);
  }
}

function updateEnginePill() {
  const pill = $('#enginePill');
  if (!pill || !state.engineStatus) return;
  const s = state.engineStatus;
  pill.innerHTML = `<span class="dot"></span>ollama · ${escHtml(s.llm_model)}`;
}

// =============================================================================
// Tab 切换
// =============================================================================
function switchTab(tab) {
  state.currentTab = tab;
  $$('.nav-item').forEach(n => n.classList.toggle('active', n.dataset.tab === tab));
  $$('.tab-panel').forEach(p => p.classList.toggle('active', p.dataset.panel === tab));
  // 切换时刷新对应数据
  if (tab === 'kb') refreshKnowledgeBase();
  else if (tab === 'fav') refreshFavorites();
  else if (tab === 'sess') refreshSessions();
  else if (tab === 'set') renderSettings();
}

// =============================================================================
// Tab 1: 知识库
// =============================================================================
async function refreshKnowledgeBase() {
  try {
    const [docsRes, tagsRes, statsRes] = await Promise.all([
      api('/api/knowledge_base'),
      api('/api/tags'),
      api('/api/knowledge_base/stats'),
    ]);
    state.documents = docsRes.documents;
    state.tags = tagsRes.tags;
    renderKnowledgeBase(docsRes.documents, tagsRes.tags, statsRes);
  } catch (e) {
    console.error('refreshKnowledgeBase failed', e);
  }
}

function renderKnowledgeBase(docs, tags, stats) {
  const root = $('#panel-kb');
  if (!root) return;
  // 上次选中的子面板（文档 / 图片），默认文档
  const subTab = state.kbSubTab || 'docs';
  root.innerHTML = `
    <div class="kb-wrap">
      <div class="page-head">
        <div>
          <div class="page-eyebrow">No. 01 · Library</div>
          <h1 class="page-title">知识<em>库</em></h1>
        </div>
        <div class="page-actions">
          <button class="ghost-btn" id="rebuildBtn">↻ 重建索引</button>
        </div>
      </div>

      <div class="kb-subtabs">
        <button class="kb-subtab ${subTab === 'docs' ? 'active' : ''}" data-sub="docs">
          📄 文档 <span class="ct">${docs.length}</span>
        </button>
        <button class="kb-subtab ${subTab === 'images' ? 'active' : ''}" data-sub="images">
          🖼 图片 <span class="ct" id="imgCount">…</span>
        </button>
      </div>

      <div class="kb-grid">
        <aside>
          <div class="upload-zone" id="uploadZone">
            <div class="icon">↥</div>
            <h3>拖入文档</h3>
            <p>或点击此处选择文件</p>
            <span class="formats">PDF · DOCX · PPTX · XLSX · MD · TXT · CSV</span>
            <input type="file" id="fileInput" multiple style="display:none" accept=".pdf,.docx,.doc,.pptx,.ppt,.xlsx,.xls,.md,.txt,.csv,.html,.json,.xml,.rtf">
          </div>

          <!-- URL 摄取 -->
          <div class="url-ingest-zone" id="urlIngestZone">
            <div class="url-ingest-label">🔗 网页摄取</div>
            <div class="url-ingest-form">
              <input type="url" id="urlInput" placeholder="输入 URL 或网页链接…" />
              <button class="url-ingest-btn" id="urlIngestBtn">抓取</button>
            </div>
            <div class="url-ingest-tip">支持 http/https 链接，自动提取正文入库</div>
          </div>

          <div class="upload-zone upload-zone-images" id="uploadZoneImg" style="display:${subTab === 'images' ? 'block' : 'none'}">
            <div class="icon">🖼</div>
            <h3>拖入图片</h3>
            <p>或点击此处选择图片</p>
            <span class="formats">PNG · JPG · GIF · WEBP · SVG</span>
            <input type="file" id="fileInputImg" multiple style="display:none" accept=".png,.jpg,.jpeg,.gif,.bmp,.webp,.svg">
          </div>

          <div class="tag-panel">
            <h4><span>标签</span><span class="count">${tags.length}</span></h4>
            <div class="tag-list" id="tagList">
              ${tags.map(t => `<span class="tag" data-name="${escHtml(t.name)}" style="border-color:${escHtml(t.color)};color:${escHtml(t.color)}">${escHtml(t.name)}</span>`).join('') || '<i style="color:var(--ink-faint);font-size:11.5px">还没有标签</i>'}
            </div>
            <button class="tag-add" id="addTagBtn">+ 新建标签</button>
          </div>

          <div class="stat-strip">
            <div class="stat-block">
              <div class="lbl">文档</div>
              <div class="val">${stats.num_docs}</div>
            </div>
            <div class="stat-block">
              <div class="lbl">块</div>
              <div class="val">${stats.num_chunks}</div>
            </div>
            <div class="stat-block">
              <div class="lbl">索引</div>
              <div class="val">${stats.vector_store_size_mb.toFixed(1)}<span class="unit">MB</span></div>
            </div>
            ${stats.versions ? `<div class="stat-block">
              <div class="lbl">版本</div>
              <div class="val">${stats.versions.total}</div>
            </div>
            <div class="stat-block">
              <div class="lbl">版本占用</div>
              <div class="val">${(stats.versions.size_mb || 0).toFixed(1)}<span class="unit">MB</span></div>
            </div>` : ''}
          </div>
        </aside>

        <div id="kbContent">
          ${subTab === 'docs' ? renderDocsPanel(docs) : '<div style="padding:60px 20px;text-align:center;color:var(--ink-faint)"><i>加载中…</i></div>'}
        </div>
      </div>
    </div>

    <!-- 文档预览 Modal -->
    <div class="modal-mask" id="previewModal" style="display:none">
      <div class="modal">
        <div class="modal-head">
          <div>
            <div class="modal-eyebrow" id="previewExt">.txt</div>
            <div class="modal-title" id="previewTitle">filename.txt</div>
          </div>
          <button class="icon-btn" id="previewClose">×</button>
        </div>
        <div class="modal-meta" id="previewMeta"></div>
        <div class="modal-body" id="previewBody"></div>
        <div class="modal-foot">
          <span class="truncated-hint" id="previewTruncated" style="display:none">⚠ 内容已截断，仅显示前 8KB / 5 页</span>
          <button class="ghost-btn" id="previewOpenRaw">↗ 在新窗口打开原文件</button>
        </div>
      </div>
    </div>

    <!-- 图片灯箱 -->
    <div class="modal-mask" id="imgLightbox" style="display:none">
      <div class="lightbox">
        <button class="icon-btn lightbox-close" id="imgLightboxClose">×</button>
        <img id="imgLightboxImg" alt="">
        <div class="lightbox-cap" id="imgLightboxCap"></div>
      </div>
    </div>
  `;

  // 子 Tab 切换
  $$('.kb-subtab').forEach(t => t.addEventListener('click', () => {
    state.kbSubTab = t.dataset.sub;
    refreshKnowledgeBase();
  }));

  // 上传交互
  const uploadZone = $('#uploadZone');
  const fileInput = $('#fileInput');
  uploadZone.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', async (e) => {
    if (e.target.files.length > 0) await handleUpload(e.target.files);
    e.target.value = '';
  });

  // 图片上传
  const uploadZoneImg = $('#uploadZoneImg');
  const fileInputImg = $('#fileInputImg');
  if (uploadZoneImg && fileInputImg) {
    uploadZoneImg.addEventListener('click', () => fileInputImg.click());
    fileInputImg.addEventListener('change', async (e) => {
      if (e.target.files.length > 0) await handleImageUpload(e.target.files);
      e.target.value = '';
    });
  }

  // URL 摄取
  const urlInput = $('#urlInput');
  const urlIngestBtn = $('#urlIngestBtn');
  if (urlIngestBtn && urlInput) {
    urlIngestBtn.addEventListener('click', () => {
      const url = urlInput.value.trim();
      if (!url) { showToast('请输入 URL', '链接不能为空', 'warn'); return; }
      handleUrlIngest(url, urlIngestBtn, urlInput);
    });
    urlInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); urlIngestBtn.click(); }
    });
  }

  // 标签
  $('#addTagBtn').addEventListener('click', handleAddTag);

  // 重建
  $('#rebuildBtn').addEventListener('click', handleRebuild);

  // 文档操作
  $$('.doc-del').forEach(b => b.addEventListener('click', (e) => {
    e.stopPropagation();
    const name = b.dataset.name;
    handleDeleteDoc(name);
  }));
  $$('.doc-tag-edit').forEach(b => b.addEventListener('click', (e) => {
    e.stopPropagation();
    const name = b.dataset.name;
    handleAddTagToDoc(name);
  }));
  $$('.doc-preview').forEach(b => b.addEventListener('click', (e) => {
    e.stopPropagation();
    handlePreviewDoc(b.dataset.name);
  }));

  // 加载图片列表
  if (subTab === 'images') loadImagesPanel();

  // Modal 关闭
  $('#previewClose')?.addEventListener('click', closePreviewModal);
  $('#previewModal')?.addEventListener('click', (e) => {
    if (e.target.id === 'previewModal') closePreviewModal();
  });
  $('#imgLightboxClose')?.addEventListener('click', () => {
    $('#imgLightbox').style.display = 'none';
  });
  $('#imgLightbox')?.addEventListener('click', (e) => {
    if (e.target.id === 'imgLightbox') $('#imgLightbox').style.display = 'none';
  });
}

/**
 * 渲染「文档」子面板
 */
function renderDocsPanel(docs) {
  return `
    <div class="doc-list" id="docList">
      <div class="doc-list-head">
        <span class="col-name">文件名</span>
        <span class="col-tag">标签</span>
        <span class="col-act" style="text-align:right">操作</span>
      </div>
      <div id="docListBody">
        ${docs.length === 0 ? '<div style="padding:40px;text-align:center;color:var(--ink-faint)"><i>知识库为空，请先上传文档</i></div>' : docs.map(d => renderDocRow(d)).join('')}
      </div>
    </div>
  `;
}

/**
 * 加载「图片」子面板
 */
async function loadImagesPanel() {
  const content = $('#kbContent');
  if (!content) return;
  try {
    const res = await api('/api/images');
    const images = res.images || [];
    const counter = $('#imgCount');
    if (counter) counter.textContent = images.length;
    content.innerHTML = `
      <div class="img-grid-wrap">
        <div class="img-grid-head">
          <span class="col-name">图片名</span>
          <span class="col-size">大小</span>
          <span class="col-act">操作</span>
        </div>
        <div class="img-grid" id="imgGrid">
          ${images.length === 0
            ? '<div style="padding:60px 20px;text-align:center;color:var(--ink-faint)"><i>还没有图片，点击左侧「拖入图片」或直接拖入图片文件即可上传</i></div>'
            : images.map(img => `
              <div class="img-card" data-name="${escHtml(img.name)}">
                <div class="img-thumb">
                  <img src="${escHtml(img.url)}" alt="${escHtml(img.name)}" loading="lazy">
                </div>
                <div class="img-info">
                  <div class="img-name" title="${escHtml(img.name)}">${escHtml(img.name)}</div>
                  <div class="img-meta">${img.size_kb} KB</div>
                </div>
                <div class="img-actions">
                  <button class="icon-btn img-view" data-url="${escHtml(img.url)}" data-name="${escHtml(img.name)}" title="查看">⤢</button>
                  <button class="icon-btn img-del" data-name="${escHtml(img.name)}" title="删除">×</button>
                </div>
              </div>
            `).join('')}
        </div>
      </div>
    `;
    $$('.img-view').forEach(b => b.addEventListener('click', (e) => {
      e.stopPropagation();
      $('#imgLightboxImg').src = b.dataset.url;
      $('#imgLightboxCap').textContent = b.dataset.name;
      $('#imgLightbox').style.display = 'flex';
    }));
    $$('.img-del').forEach(b => b.addEventListener('click', (e) => {
      e.stopPropagation();
      handleDeleteImage(b.dataset.name);
    }));
  } catch (e) {
    content.innerHTML = `<div style="padding:60px 20px;text-align:center;color:var(--clay)">⚠ 加载图片列表失败: ${escHtml(e.message)}</div>`;
  }
}

/**
 * 打开文档预览
 */
async function handlePreviewDoc(name) {
  const modal = $('#previewModal');
  const titleEl = $('#previewTitle');
  const extEl = $('#previewExt');
  const metaEl = $('#previewMeta');
  const bodyEl = $('#previewBody');
  const truncEl = $('#previewTruncated');
  if (!modal) return;
  titleEl.textContent = name;
  extEl.textContent = '';
  metaEl.textContent = '加载中…';
  bodyEl.innerHTML = '<i style="color:var(--ink-faint)">加载中…</i>';
  truncEl.style.display = 'none';
  modal.style.display = 'flex';
  try {
    const data = await api(`/api/knowledge_base/documents/${encodeURIComponent(name)}/preview`);
    extEl.textContent = data.ext;
    metaEl.innerHTML = `
      <span class="badge kind-${escHtml(data.kind)}">${escHtml(data.kind)}</span>
      <span>${data.size_kb} KB</span>
      <span>· ${data.ext}</span>
    `;
    if (data.truncated) truncEl.style.display = '';
    if (data.kind === 'image') {
      bodyEl.innerHTML = `<div style="text-align:center"><img src="/api/knowledge_base/documents/${encodeURIComponent(name)}/file" alt="${escHtml(name)}" style="max-width:100%;max-height:60vh;border-radius:6px"></div>`;
    } else if (data.kind === 'pdf') {
      bodyEl.innerHTML = `<pre class="preview-pre">${escHtml(data.content || '')}</pre>`;
    } else {
      bodyEl.innerHTML = `<pre class="preview-pre">${escHtml(data.content || '')}</pre>`;
    }
    // 绑定"打开原文件"
    const openRaw = $('#previewOpenRaw');
    if (openRaw) openRaw.onclick = () => window.open(`/api/knowledge_base/documents/${encodeURIComponent(name)}/file`, '_blank');
  } catch (e) {
    bodyEl.innerHTML = `<i style="color:var(--clay)">⚠ 加载失败: ${escHtml(e.message)}</i>`;
  }
}

function closePreviewModal() {
  const modal = $('#previewModal');
  if (modal) modal.style.display = 'none';
}

async function handleImageUpload(files) {
  showToast('上传中', `处理 ${files.length} 张图片…`, 'info');
  try {
    const fd = new FormData();
    for (const f of files) fd.append('files', f);
    const resp = await fetch('/api/images/upload', { method: 'POST', body: fd });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(text || '上传失败');
    }
    const res = await resp.json();
    showToast('上传成功', `已添加 ${res.count} 张图片`, 'success');
    if (state.kbSubTab === 'images') loadImagesPanel();
    else {
      const counter = $('#imgCount');
      if (counter) {
        const cur = parseInt(counter.textContent || '0', 10) || 0;
        counter.textContent = cur + res.count;
      }
    }
  } catch (e) {
    showToast('上传失败', e.message, 'error');
  }
}

async function handleUrlIngest(url, btn, inputEl) {
  btn.disabled = true;
  btn.textContent = '抓取中…';
  try {
    const res = await api('/api/knowledge_base/ingest_url', {
      method: 'POST',
      body: { url },
    });
    showToast('抓取成功', `已入库 ${res.chunks} 个文本块`, 'success');
    inputEl.value = '';
    refreshKnowledgeBase();
  } catch (e) {
    showToast('抓取失败', e.message, 'error');
  } finally {
    btn.disabled = false;
    btn.textContent = '抓取';
  }
}

async function handleDeleteImage(name) {
  if (!confirm(`确认删除图片「${name}」？`)) return;
  try {
    await api(`/api/images/${encodeURIComponent(name)}`, { method: 'DELETE' });
    showToast('已删除', name, 'success');
    loadImagesPanel();
  } catch (e) {
    showToast('删除失败', e.message, 'error');
  }
}

function renderDocRow(doc) {
  const ext = doc.name.split('.').pop().toLowerCase();
  const tagsHtml = doc.tags.length === 0
    ? '<i style="color:var(--ink-faint);font-size:11px">无</i>'
    : doc.tags.map(t => `<span class="tag accent" style="font-size:10.5px;padding:2px 6px">${escHtml(t)}</span>`).join(' ');
  return `
    <div class="doc-row" data-name="${escHtml(doc.name)}">
      <div class="col-name">
        <div class="doc-icon ${ext}">${ext.toUpperCase().slice(0,4)}</div>
        <div class="doc-info">
          <div class="doc-name">${escHtml(doc.name)}</div>
          <div class="doc-path">uploaded_docs/</div>
        </div>
      </div>
      <div class="col-tag">${tagsHtml}</div>
      <div class="col-act">
        <button class="icon-btn doc-preview" data-name="${escHtml(doc.name)}" title="预览">◐</button>
        <button class="icon-btn doc-tag-edit" data-name="${escHtml(doc.name)}" title="添加标签">⚑</button>
        <button class="icon-btn doc-del" data-name="${escHtml(doc.name)}" title="删除">×</button>
      </div>
    </div>
  `;
}

async function handleUpload(files) {
  showToast('上传中', `处理 ${files.length} 个文件…`, 'info');
  try {
    const res = await apiUpload(files);
    showToast('上传成功', `${res.uploaded.length} 个文件已加入知识库`, 'success');
    refreshKnowledgeBase();
  } catch (e) {
    showToast('上传失败', e.message, 'error');
  }
}

async function handleDeleteDoc(name) {
  if (!confirm(`确认删除「${name}」？\n相关向量数据也会被清除。`)) return;
  try {
    await api(`/api/knowledge_base/documents/${encodeURIComponent(name)}`, { method: 'DELETE' });
    showToast('已删除', name, 'success');
    refreshKnowledgeBase();
  } catch (e) {
    showToast('删除失败', e.message, 'error');
  }
}

async function handleAddTag() {
  const name = prompt('新建标签名称:');
  if (!name) return;
  const color = prompt('标签颜色 (HEX, 例如 #0a6b6e):', '#0a6b6e') || '#0a6b6e';
  try {
    await api('/api/tags', { method: 'POST', body: { name, color } });
    showToast('标签已创建', name, 'success');
    refreshKnowledgeBase();
  } catch (e) {
    showToast('创建失败', e.message, 'error');
  }
}

async function handleAddTagToDoc(docName) {
  const tag = prompt(`为「${docName}」添加标签:`);
  if (!tag) return;
  try {
    await api(`/api/knowledge_base/documents/${encodeURIComponent(docName)}/tags`, {
      method: 'POST', body: { tag }
    });
    showToast('已添加', tag, 'success');
    refreshKnowledgeBase();
  } catch (e) {
    showToast('添加失败', e.message, 'error');
  }
}

async function handleRebuild() {
  if (!confirm('重新构建索引将扫描 uploaded_docs 目录并重建向量库。继续？')) return;
  showToast('重建中', '正在扫描文档…', 'info');
  try {
    const res = await api('/api/knowledge_base/rebuild', { method: 'POST' });
    showToast('重建完成', `载入 ${res.loaded_chunks} 个文档块`, 'success');
    refreshKnowledgeBase();
  } catch (e) {
    showToast('重建失败', e.message, 'error');
  }
}

// 全局拖拽上传
function setupGlobalDragDrop() {
  const overlay = $('#dragOverlay');
  let dragCount = 0;
  window.addEventListener('dragenter', (e) => {
    if (!e.dataTransfer.types.includes('Files')) return;
    e.preventDefault();
    dragCount++;
    overlay?.classList.add('show');
  });
  window.addEventListener('dragleave', (e) => {
    e.preventDefault();
    dragCount--;
    if (dragCount <= 0) { overlay?.classList.remove('show'); dragCount = 0; }
  });
  window.addEventListener('dragover', (e) => e.preventDefault());
  window.addEventListener('drop', async (e) => {
    e.preventDefault();
    overlay?.classList.remove('show');
    dragCount = 0;
    const files = Array.from(e.dataTransfer?.files || []);
    if (files.length > 0) {
      switchTab('kb');
      await handleUpload(files);
    }
  });
}

// =============================================================================
// Tab 2: 智能问答 (核心 - SSE 流式)
// =============================================================================
function renderChat() {
  const root = $('#panel-chat');
  if (!root) return;
  if (!root.innerHTML.trim()) {
    root.innerHTML = `
      <div class="chat-wrap">
        <div class="chat-main">
          <div class="chat-inner">
            <div class="chat-hero" id="chatHero">
              <h1>Ask <em>anything</em> from your library.</h1>
              <p class="lede">基于本地知识库的智能问答。检索 · 精排 · 流式生成 · 自动溯源。</p>
              <div class="followups">
                <button class="followup" data-q="中山大学2025年计算机学硕考什么科目？"><span class="arrow">→</span><span>中山大学2025年计算机学硕考什么科目？</span></button>
                <button class="followup" data-q="PVQC 单词表里 polymorphism 怎么翻译？"><span class="arrow">→</span><span>PVQC 单词表里 polymorphism 怎么翻译？</span></button>
                <button class="followup" data-q="数据库设计包括哪几个阶段？"><span class="arrow">→</span><span>数据库设计包括哪几个阶段？</span></button>
                <button class="followup" data-q="什么是 LangGraph？它在研报智能体里起什么作用？"><span class="arrow">→</span><span>什么是 LangGraph？它在研报智能体里起什么作用？</span></button>
              </div>
            </div>
            <div class="conv" id="chatConv"></div>
          </div>
          <div class="chat-composer" id="chatComposer">
            <form class="search-box" id="chatForm">
              <span class="lead-icon">⌕</span>
              <input type="text" id="chatInput" placeholder="向你的知识库提问…  (Ctrl+Enter 发送)" autocomplete="off">
              <button type="submit" class="search-submit">Ask →</button>
            </form>
            <div class="search-meta">
              <span>混合检索 · Rerank · SSE 流式</span>
              <span class="scope-on" id="scopeInfo">本地知识库</span>
            </div>
          </div>
        </div>
        <aside class="sources-panel" id="sourcesPanel">
          <div class="sp-head">
            <div class="sp-eyebrow">Sources</div>
            <h3>本轮引用</h3>
          </div>
          <div class="sp-body" id="sourcesBody">
            <div class="sp-empty">本轮检索到的来源将在这里出现。<br>每条来源都可追溯到原文片段。</div>
          </div>
        </aside>
      </div>
    `;

    $('#chatForm').addEventListener('submit', (e) => {
      e.preventDefault();
      const input = $('#chatInput');
      const q = input.value.trim();
      if (!q || state.streaming) return;
      input.value = '';
      askQuestion(q);
    });
    $$('.followup').forEach(b => b.addEventListener('click', () => {
      if (state.streaming) return;
      askQuestion(b.dataset.q);
    }));

    // 事件委托：收藏 / 复制 / 重新生成（按钮在 appendTurn 后才存在于 DOM）
    const conv = $('#chatConv');
    if (conv) {
      conv.addEventListener('click', (e) => {
        const btn = e.target.closest('.regenerate-btn');
        if (!btn || state.streaming) return;
        const q = btn.dataset.q;
        if (!q) return;
        regenerateLastAnswer(q);
      });
    }
  }
}

async function askQuestion(question) {
  if (state.streaming) return;
  state.streaming = true;
  state.sources = [];
  state.isFallback = false;

  // 隐藏 hero
  const hero = $('#chatHero');
  if (hero) hero.style.display = 'none';

  // 历史转成 [(user, assistant), ...] 用于多轮
  const history = state.messages.map(m => [m.role === 'user' ? m.content : '', m.role === 'assistant' ? m.content : '']).filter(p => p[0] || p[1]);

  // 构造用户消息
  const userMsg = { role: 'user', content: question, ts: new Date().toISOString() };
  state.messages.push(userMsg);
  appendTurn(userMsg);

  // 构造 assistant 占位（流式填充）
  const assistantMsg = { role: 'assistant', content: '', ts: new Date().toISOString(), sources: [], fallback: false, phases: { search: true, read: false, write: false } };
  state.messages.push(assistantMsg);
  const assistantEl = appendTurn(assistantMsg);

  try {
    const resp = await fetch('/api/query/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, session_id: state.currentSessionId, history }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6).trim();
        if (!data) continue;
        try {
          const evt = JSON.parse(data);
          handleStreamEvent(evt, assistantMsg, assistantEl);
        } catch (e) {
          console.error('parse SSE event failed', e, data);
        }
      }
    }
  } catch (e) {
    showToast('查询失败', e.message, 'error');
    assistantMsg.content = `⚠️ ${e.message}`;
    updateTurnContent(assistantEl, assistantMsg);
  } finally {
    state.streaming = false;
  }
}

// ---------------------------------------------------------------------------
// 重新生成：移除最后一轮 AI 回答，重新跑 SSE（复用同一 session_id）
// ---------------------------------------------------------------------------
async function regenerateLastAnswer(question) {
  // 1. 找到最后一个 assistant 消息的 DOM 元素并移除
  const conv = $('#chatConv');
  if (!conv) return;
  const turns = $$('.conv-turn', conv);
  let lastAssistantIdx = -1;
  for (let i = turns.length - 1; i >= 0; i--) {
    if (turns[i].dataset.role === 'assistant') {
      lastAssistantIdx = i;
      break;
    }
  }
  if (lastAssistantIdx >= 0) {
    turns[lastAssistantIdx].remove();
  }

  // 2. 从 state.messages 中移除最后一个 assistant 消息
  for (let i = state.messages.length - 1; i >= 0; i--) {
    if (state.messages[i].role === 'assistant') {
      state.messages.splice(i, 1);
      break;
    }
  }

  // 3. 清空引用面板
  state.sources = [];
  state.isFallback = false;
  renderSourcesPanel();

  // 4. 重新运行 SSE（不再加用户消息，history 包含之前所有轮）
  const history = state.messages
    .filter(m => m.role === 'assistant')
    .map(m => ['', m.content]);

  state.streaming = true;

  // 构造 assistant 占位
  const assistantMsg = {
    role: 'assistant', content: '', ts: new Date().toISOString(),
    sources: [], fallback: false, phases: { search: true, read: false, write: false }
  };
  state.messages.push(assistantMsg);
  const assistantEl = appendTurn(assistantMsg);

  try {
    const resp = await fetch('/api/query/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, session_id: state.currentSessionId, history }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6).trim();
        if (!data) continue;
        try {
          const evt = JSON.parse(data);
          handleStreamEvent(evt, assistantMsg, assistantEl);
        } catch (e) {
          console.error('parse SSE event failed', e, data);
        }
      }
    }
  } catch (e) {
    showToast('重新生成失败', e.message, 'error');
    assistantMsg.content = `⚠️ ${e.message}`;
    updateTurnContent(assistantEl, assistantMsg);
  } finally {
    state.streaming = false;
  }
}

function handleStreamEvent(evt, assistantMsg, assistantEl) {
  if (evt.type === 'sources') {
    state.sources = evt.sources || [];
    state.isFallback = !!evt.fallback;
    assistantMsg.sources = state.sources;
    assistantMsg.fallback = state.isFallback;
    assistantMsg.phases.search = true;
    assistantMsg.phases.read = true;
    renderSourcesPanel();
    updateTurnContent(assistantEl, assistantMsg);
  } else if (evt.type === 'token') {
    assistantMsg.phases.write = true;
    const useTypewriter = localStorage.getItem('pref_typewriter') !== '0';
    if (useTypewriter) {
      // 打字机效果：每次累积 buffer，逐步渲染
      if (!assistantMsg._twBuf) assistantMsg._twBuf = '';
      if (!assistantMsg._twTimer) assistantMsg._twTimer = null;
      assistantMsg._twBuf += evt.content || '';
      if (!assistantMsg._twTimer) {
        const flush = () => {
          if (!assistantMsg._twBuf) {
            assistantMsg._twTimer = null;
            return;
          }
          assistantMsg.content += assistantMsg._twBuf[0];
          assistantMsg._twBuf = assistantMsg._twBuf.slice(1);
          updateTurnContent(assistantEl, assistantMsg);
          const conv = $('#chatConv');
          if (conv) conv.parentElement.scrollTop = conv.parentElement.scrollHeight;
          if (assistantMsg._twBuf) {
            assistantMsg._twTimer = setTimeout(flush, 18);
          } else {
            assistantMsg._twTimer = null;
          }
        };
        flush();
      }
    } else {
      // 直接渲染
      assistantMsg.content += evt.content || '';
      updateTurnContent(assistantEl, assistantMsg);
      const conv = $('#chatConv');
      if (conv) conv.parentElement.scrollTop = conv.parentElement.scrollHeight;
    }
  } else if (evt.type === 'done') {
    // 打字机缓冲未完则立即flush
    if (assistantMsg._twTimer) {
      clearTimeout(assistantMsg._twTimer);
      assistantMsg._twTimer = null;
    }
    if (assistantMsg._twBuf) {
      assistantMsg.content += assistantMsg._twBuf;
      assistantMsg._twBuf = '';
      updateTurnContent(assistantEl, assistantMsg);
    }
    if (evt.session_id) state.currentSessionId = evt.session_id;
    if (state.currentTab === 'sess') refreshSessions();
  } else if (evt.type === 'error') {
    if (assistantMsg._twTimer) { clearTimeout(assistantMsg._twTimer); assistantMsg._twTimer = null; }
    assistantMsg.content += `\n⚠️ ${evt.content}`;
    updateTurnContent(assistantEl, assistantMsg);
  }
}

function appendTurn(msg) {
  const conv = $('#chatConv');
  if (!conv) return null;
  const el = document.createElement('div');
  el.className = `conv-turn ${msg.role}`;
  el.dataset.role = msg.role;
  conv.appendChild(el);
  updateTurnContent(el, msg);
  return el;
}

function updateTurnContent(el, msg) {
  if (!el) return;
  if (msg.role === 'user') {
    el.innerHTML = `
      <div class="conv-avatar">U</div>
      <div class="conv-body">
        <div class="conv-meta">
          <span class="name">你</span>
          <span class="time">${fmtTime(msg.ts)}</span>
        </div>
        <div class="conv-text"><p>${escHtml(msg.content)}</p></div>
      </div>
    `;
  } else {
    // Assistant
    const phases = msg.phases || { search: false, read: false, write: false };
    const phasesHtml = `
      <div class="phases">
        <span class="phase ${phases.search ? 'done' : 'live'}"><span class="check">✓</span> Searching</span>
        <span class="phase-arrow">→</span>
        <span class="phase ${phases.read ? 'done' : (phases.search ? 'live' : '')}"><span class="check">✓</span> Reading</span>
        <span class="phase-arrow">→</span>
        <span class="phase ${phases.write ? 'done' : (phases.read ? 'live' : '')}"><span class="check">✓</span> Writing</span>
      </div>
    `;
    const fallbackBanner = msg.fallback
      ? `<div class="fallback-banner"><span class="mark">⚐</span>此回答由 LLM 直接生成，知识库中未找到相关内容</div>`
      : '';
    // 简易 markdown 渲染（粗体/代码/换行）
    const htmlContent = simpleMarkdown(msg.content);
    el.innerHTML = `
      <div class="conv-avatar">L</div>
      <div class="conv-body">
        <div class="conv-meta">
          <span class="name">Loci</span>
          <span class="time">${fmtTime(msg.ts)}</span>
        </div>
        ${phases.search ? phasesHtml : ''}
        ${fallbackBanner}
        <div class="conv-text" data-streaming="${state.streaming && !msg.content ? '1' : '0'}">${htmlContent || '<span style="color:var(--ink-faint)">…</span>'}</div>
        <div class="answer-actions">
          <button class="act-btn fav-btn" data-q="${escHtml(getLastUserQuestion())}" data-a="${escHtml(msg.content)}"><span class="ico">★</span> 收藏</button>
          <button class="act-btn copy-btn"><span class="ico">⎘</span> 复制</button>
          <button class="act-btn regenerate-btn" data-q="${escHtml(getLastUserQuestion())}"><span class="ico">↻</span> 重新生成</button>
        </div>
      </div>
    `;
    // 绑定收藏
    const favBtn = el.querySelector('.fav-btn');
    if (favBtn) favBtn.addEventListener('click', () => handleFavorite(favBtn.dataset.q, favBtn.dataset.a));
    const copyBtn = el.querySelector('.copy-btn');
    if (copyBtn) copyBtn.addEventListener('click', () => {
      navigator.clipboard.writeText(msg.content);
      showToast('已复制', '答案已复制到剪贴板', 'success');
    });
  }
}

function getLastUserQuestion() {
  for (let i = state.messages.length - 1; i >= 0; i--) {
    if (state.messages[i].role === 'user') return state.messages[i].content;
  }
  return '';
}

function simpleMarkdown(text) {
  if (!text) return '';
  // 转义HTML
  let html = escHtml(text);
  // 粗体
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // 行内代码
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // 段落分割
  const paras = html.split(/\n\n+/).map(p => `<p>${p.replace(/\n/g, '<br>')}</p>`);
  return paras.join('');
}

function renderSourcesPanel() {
  const body = $('#sourcesBody');
  if (!body) return;
  if (state.sources.length === 0) {
    body.innerHTML = `<div class="sp-empty">${state.isFallback ? '未命中知识库，已回退到 LLM 直接回答。' : '本轮未检索到来源'}</div>`;
    return;
  }
  body.innerHTML = state.sources.map((s, i) => `
    <div class="src-card" id="src-${i}">
      <div class="src-head">
        <span class="src-idx">[${i + 1}]</span>
        <span class="src-name">${escHtml(s.source)}</span>
        ${s.page != null ? `<span class="src-page">第${Number(s.page) + 1}页</span>` : ''}
      </div>
      <div class="src-score">Rerank: ${(s.score || 0).toFixed(3)}</div>
      <div class="src-preview">${escHtml(s.preview || '')}</div>
    </div>
  `).join('');
}

async function handleFavorite(q, a) {
  try {
    await api('/api/favorites', {
      method: 'POST',
      body: { question: q, answer: a, sources: state.sources }
    });
    showToast('已收藏', q.slice(0, 30), 'success');
  } catch (e) {
    showToast('收藏失败', e.message, 'error');
  }
}

// =============================================================================
// Tab 3: 收藏
// =============================================================================
async function refreshFavorites() {
  try {
    const res = await api('/api/favorites');
    state.favorites = res.favorites;
    renderFavorites(res.favorites);
  } catch (e) {
    console.error('refreshFavorites failed', e);
  }
}

function renderFavorites(items) {
  const root = $('#panel-fav');
  if (!root) return;
  root.innerHTML = `
    <div class="fav-wrap">
      <div class="page-head">
        <div>
          <div class="page-eyebrow">No. 03 · Bookmarks</div>
          <h1 class="page-title">收<em>藏</em></h1>
        </div>
        <div class="page-actions">
          <button class="ghost-btn" id="exportFavBtn">↧ 导出</button>
        </div>
      </div>

      <!-- 导出选项面板 -->
      <div class="export-panel" id="exportPanel" style="display:none">
        <div class="export-panel-head">
          <span>选择导出项目</span>
          <button class="icon-btn" id="closeExportPanel">×</button>
        </div>
        <div class="export-options">
          <label class="export-checkbox"><input type="checkbox" id="selectAllFavs"> 全选</label>
          <div class="export-formats">
            <label><input type="radio" name="exportFormat" value="json" checked> JSON</label>
            <label><input type="radio" name="exportFormat" value="markdown"> Markdown</label>
            <label><input type="radio" name="exportFormat" value="pdf"> PDF</label>
          </div>
        </div>
        <div class="export-actions">
          <span class="export-count" id="exportCount">已选 0 项</span>
          <button class="ghost-btn" id="doExportBtn">确认导出</button>
        </div>
      </div>

      <div class="fav-toolbar">
        <div class="fav-search">
          <input type="text" id="favSearch" placeholder="搜索收藏…">
        </div>
        <div class="fav-meta">共 ${items.length} 条</div>
      </div>
      <div class="fav-list" id="favList">
        ${items.length === 0 ? `<div class="fav-empty" style="padding:60px 0;text-align:center;color:var(--ink-faint)"><i>还没有收藏的问答。在智能问答里点击「★ 收藏」即可保存。</i></div>` : items.map((f, i) => `
          <div class="fav-card ${state.selectedFavs?.has(f.id) ? 'selected' : ''}" data-id="${escHtml(f.id)}">
            <div class="fav-check"><input type="checkbox" class="fav-sel" ${state.selectedFavs?.has(f.id) ? 'checked' : ''}></div>
            <div class="fav-num">№ ${String(items.length - i).padStart(2, '0')}</div>
            <div class="fav-q">${escHtml(f.question)}</div>
            <div class="fav-a">${simpleMarkdown(f.answer)}</div>
            <div class="fav-meta">
              <span>${escHtml(f.created_at || '')}</span>
              <button class="icon-btn fav-del" data-id="${escHtml(f.id)}" title="删除">×</button>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
  $$('.fav-del').forEach(b => b.addEventListener('click', () => handleDeleteFavorite(b.dataset.id)));

  // 搜索
  const searchInput = $('#favSearch');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      const q = e.target.value.toLowerCase();
      $$('.fav-card').forEach(c => {
        c.style.display = c.textContent.toLowerCase().includes(q) ? '' : 'none';
      });
    });
  }

  // 导出面板
  initExportPanel();

  // 全选
  $('#selectAllFavs')?.addEventListener('change', (e) => {
    if (e.target.checked) {
      state.selectedFavs = new Set(items.map(f => f.id));
    } else {
      state.selectedFavs = new Set();
    }
    updateFavSelection();
  });

  // 确认导出
  $('#doExportBtn')?.addEventListener('click', () => doExport('favorites'));
}

async function handleDeleteFavorite(id) {
  if (!confirm('确认删除此收藏？')) return;
  try {
    await api(`/api/favorites/${id}`, { method: 'DELETE' });
    showToast('已删除', '', 'success');
    refreshFavorites();
  } catch (e) {
    showToast('删除失败', e.message, 'error');
  }
}


// Tab 4: 会话
// =============================================================================
async function refreshSessions() {
  try {
    const res = await api('/api/chat/sessions');
    state.sessions = res.sessions;
    renderSessions(res.sessions);
  } catch (e) {
    console.error('refreshSessions failed', e);
  }
}

function renderSessions(items) {
  const root = $('#panel-sess');
  if (!root) return;
  // 当前选中的 session id
  const activeId = state.currentSessionId || (items[0]?.session_id ?? null);
  root.innerHTML = `
    <div class="page-head">
      <div>
        <div class="page-eyebrow">No. 04 · Conversations</div>
        <h1 class="page-title">会<em>话</em></h1>
      </div>
      <div class="page-actions">
        <button class="ghost-btn" id="refreshSessBtn" title="刷新会话列表">↻ 刷新</button>
        <button class="ghost-btn" id="exportSessBtn">↧ 导出</button>
        <button class="primary-btn" id="newSessBtn">+ 新建会话</button>
      </div>
    </div>

    <!-- 导出选项面板 -->
    <div class="export-panel" id="sessExportPanel" style="display:none">
      <div class="export-panel-head">
        <span>选择导出会话</span>
        <button class="icon-btn" id="closeSessExportPanel">×</button>
      </div>
      <div class="export-options">
        <label class="export-checkbox"><input type="checkbox" id="selectAllSess"> 全选</label>
        <div class="export-formats">
          <label><input type="radio" name="sessExportFormat" value="markdown" checked> Markdown</label>
          <label><input type="radio" name="sessExportFormat" value="json"> JSON</label>
          <label><input type="radio" name="sessExportFormat" value="pdf"> PDF</label>
        </div>
      </div>
      <div class="export-actions">
        <span class="export-count" id="sessExportCount">已选 0 项</span>
        <button class="ghost-btn" id="doSessExportBtn">确认导出</button>
      </div>
    </div>

    <div class="sess-wrap">
      <div class="sess-list" id="sessList">
        ${items.length === 0 ? `<div style="padding:60px 24px;text-align:center;color:var(--ink-faint)"><i>还没有会话，去智能问答开始第一段对话吧。</i></div>` : items.map(s => `
          <div class="sess-row ${s.session_id === activeId ? 'active' : ''} ${state.selectedSess?.has(s.session_id) ? 'selected' : ''}" data-id="${escHtml(s.session_id)}">
            <div class="sess-check"><input type="checkbox" class="sess-sel" ${state.selectedSess?.has(s.session_id) ? 'checked' : ''}></div>
            <div class="sess-title">${escHtml(s.title || '(未命名)')}</div>
            <div class="sess-meta">
              <span>${escHtml((s.updated_at || '').slice(0, 16))}</span>
              <span>· ${escHtml(String(s.message_count || 0))} 轮</span>
            </div>
            <button class="icon-btn sess-del" data-id="${escHtml(s.session_id)}" title="删除">×</button>
          </div>
        `).join('')}
      </div>
      <div class="sess-detail" id="sessDetail">
        ${activeId ? `<div style="color:var(--ink-faint);padding:40px;text-align:center"><i>请选择左侧任意会话，或新建会话开始记录…</i></div>` : `<div style="color:var(--ink-faint);padding:40px;text-align:center"><i>请选择左侧任意会话</i></div>`}
      </div>
    </div>
  `;
  // 行点击：选择 + 加载详情
  $$('.sess-row').forEach(r => r.addEventListener('click', (e) => {
    if (e.target.classList.contains('sess-del')) return;
    const sid = r.dataset.id;
    if (!sid) return;
    state.currentSessionId = sid;
    // 列表 active 切换
    $$('.sess-row').forEach(x => x.classList.toggle('active', x.dataset.id === sid));
    loadSessionDetail(sid);
  }));
  // 删除按钮
  $$('.sess-del').forEach(b => b.addEventListener('click', (e) => {
    e.stopPropagation();
    handleDeleteSession(b.dataset.id);
  }));
  // 新建会话：重置 chat 区域
  $('#newSessBtn')?.addEventListener('click', () => {
    state.currentSessionId = null;
    state.messages = [];
    state.sources = [];
    state.isFallback = false;
    const conv = $('#chatConv');
    if (conv) conv.innerHTML = '';
    const hero = $('#chatHero');
    if (hero) hero.style.display = '';
    switchTab('chat');
    showToast('新会话', '已开启空会话', 'success');
  });
  // 刷新按钮
  $('#refreshSessBtn')?.addEventListener('click', () => {
    showToast('刷新中', '正在重新拉取会话…', 'info');
    refreshSessions();
  });

  // 初始化会话导出面板
  initSessExportPanel();

  // 自动加载第一个会话的详情（首次进入时）
  if (activeId && !$('#sessDetail').dataset.loaded) {
    $('#sessDetail').dataset.loaded = '1';
    loadSessionDetail(activeId);
  }
}

async function loadSession(sid) {
  if (!sid) {
    showToast('加载失败', '会话 ID 为空', 'error');
    return;
  }
  try {
    const res = await api(`/api/chat/sessions/${sid}`);
    state.messages = res.messages || [];
    state.currentSessionId = sid;
    // 切换到 chat tab
    switchTab('chat');
    const hero = $('#chatHero');
    if (hero) hero.style.display = 'none';
    const conv = $('#chatConv');
    if (conv) {
      conv.innerHTML = '';
      // 给每条消息补 ts，appendTurn 需要
      const now = new Date().toISOString();
      state.messages.forEach(m => {
        const enriched = Object.assign({}, m, { ts: m.ts || now });
        appendTurn(enriched);
      });
    }
    showToast('已加载', `会话：${(res.session?.title || '新会话').slice(0, 20)}`, 'success');
  } catch (e) {
    showToast('加载失败', e.message, 'error');
  }
}

/**
 * 渲染会话详情面板（仅在「会话」tab 内显示历史消息）。
 * 与 loadSession 的区别：loadSession 会切换到 chat tab 并把消息注入聊天框，
 * loadSessionDetail 只在右侧详情面板展示。
 */
async function loadSessionDetail(sid) {
  if (!sid) return;
  const detail = $('#sessDetail');
  if (!detail) return;
  detail.innerHTML = `<div style="color:var(--ink-faint);padding:40px;text-align:center"><i>加载中…</i></div>`;
  try {
    const res = await api(`/api/chat/sessions/${sid}`);
    const sess = res.session || {};
    const msgs = res.messages || [];
    detail.innerHTML = `
      <div class="detail-head">
        <div class="detail-title">${escHtml(sess.title || '未命名会话')}</div>
        <div class="detail-meta">
          <span>${escHtml(sess.created_at || '')}</span>
          <span> · ${escHtml(String(sess.message_count || msgs.length))} 轮 · ${escHtml(sess.updated_at || '')}</span>
        </div>
        <div class="detail-actions" style="margin-top:12px;display:flex;gap:8px">
          <button class="ghost-btn" id="detailContinueBtn">↳ 在智能问答中继续</button>
          <button class="danger-btn" id="detailDelBtn">× 删除该会话</button>
        </div>
      </div>
      <div class="detail-msgs">
        ${msgs.length === 0 ? `<div style="color:var(--ink-faint);padding:24px;text-align:center"><i>该会话暂无消息</i></div>` : msgs.map(m => `
          <div class="detail-msg ${escHtml(m.role)}">
            <div class="detail-msg-meta">${escHtml(m.role === 'user' ? '你' : 'Loci')}</div>
            <div class="detail-msg-text">${simpleMarkdown(m.content || '')}</div>
          </div>
        `).join('')}
      </div>
    `;
    // 绑定按钮
    $('#detailContinueBtn')?.addEventListener('click', () => loadSession(sid));
    $('#detailDelBtn')?.addEventListener('click', () => handleDeleteSession(sid));
  } catch (e) {
    detail.innerHTML = `<div style="color:var(--clay);padding:40px;text-align:center">⚠️ 加载失败: ${escHtml(e.message)}</div>`;
  }
}

async function handleDeleteSession(sid) {
  if (!confirm('确认删除此会话？')) return;
  try {
    await api(`/api/chat/sessions/${sid}`, { method: 'DELETE' });
    if (state.currentSessionId === sid) state.currentSessionId = null;
    showToast('已删除', '', 'success');
    refreshSessions();
  } catch (e) {
    showToast('删除失败', e.message, 'error');
  }
}

// =============================================================================
// Tab 5: 设置
// =============================================================================
async function loadSettings() {
  try {
    const settings = await api('/api/settings');
    state.userSettings = settings;
    // 同步到 localStorage
    localStorage.setItem('pref_rerank', settings.rerank_enabled ? '1' : '0');
    localStorage.setItem('pref_fallback', settings.fallback_enabled ? '1' : '0');
    localStorage.setItem('pref_streaming', settings.streaming_enabled ? '1' : '0');
    localStorage.setItem('pref_typewriter', settings.typewriter_enabled ? '1' : '0');
    localStorage.setItem('theme', settings.theme || 'light');
  } catch (e) {
    console.error('loadSettings failed', e);
  }
}

async function saveSetting(key, value) {
  // 同时保存到 localStorage 和后端
  localStorage.setItem(`pref_${key}`, value ? '1' : '0');
  try {
    await api('/api/settings', {
      method: 'POST',
      body: { [key]: value }
    });
  } catch (e) {
    console.error('saveSetting failed', e);
  }
}

function renderSettings() {
  const root = $('#panel-set');
  if (!root) return;
  const s = state.engineStatus || {};

  // 读取用户偏好（优先从后端，其次 localStorage）
  const pref = {
    rerank: state.userSettings?.rerank_enabled ?? (localStorage.getItem('pref_rerank') !== '0'),
    fallback: state.userSettings?.fallback_enabled ?? (localStorage.getItem('pref_fallback') !== '0'),
    streaming: state.userSettings?.streaming_enabled ?? (localStorage.getItem('pref_streaming') !== '0'),
    typewriter: state.userSettings?.typewriter_enabled ?? (localStorage.getItem('pref_typewriter') !== '0'),
  };

  root.innerHTML = `
    <div class="set-wrap">
      <div class="page-head">
        <div>
          <div class="page-eyebrow">No. 05 · Settings</div>
          <h1 class="page-title">设<em>置</em></h1>
        </div>
      </div>

      <!-- 系统状态卡片 -->
      <div class="set-card">
        <div class="set-card-head">
          <span class="set-card-icon">◈</span>
          <h2>系统状态</h2>
        </div>
        <div class="set-card-body">
          <div class="status-pills">
            <span class="pill pill-ok">● LLM</span>
            <span class="pill pill-ok">● Embedding</span>
            <span class="pill ${s.rerank_enabled ? 'pill-ok' : 'pill-warn'}">● Rerank</span>
          </div>
          <div class="kv-grid">
            <div class="kv"><span class="k">Embedding</span><span class="v">${escHtml(s.embedding_provider || '-')} · ${escHtml((s.embedding_model || '').split(/[\\\\/]/).pop() || '-')}</span></div>
            <div class="kv"><span class="k">LLM</span><span class="v">${escHtml(s.llm_model || '-')}</span></div>
            <div class="kv"><span class="k">Ollama</span><span class="v">${escHtml(s.ollama_base_url || '-')}</span></div>
            <div class="kv"><span class="k">混合检索</span><span class="v">${s.bm25_enabled ? `BM25(${s.bm25_weight}) + 向量(${s.vector_weight})` : '纯向量'}</span></div>
            <div class="kv"><span class="k">Rerank</span><span class="v">${s.rerank_enabled ? `top${s.rerank_initial_k}→top${s.rerank_final_k} · 阈值${s.rerank_score_threshold}` : '未启用'}</span></div>
            <div class="kv"><span class="k">分片</span><span class="v">${escHtml(s.chunk_strategy || '-')} (size=${s.chunk_size}, overlap=${s.chunk_overlap})</span></div>
            <div class="kv"><span class="k">版本管理</span><span class="v">${s.version_enabled ? '启用' : '未启用'}</span></div>
            <div class="kv"><span class="k">Fallback</span><span class="v">${s.rag_fallback_enabled ? `启用 · 阈值${s.rag_fallback_threshold}` : '未启用'}</span></div>
          </div>
        </div>
      </div>

      <!-- 功能开关 -->
      <div class="set-card">
        <div class="set-card-head">
          <span class="set-card-icon">⚙</span>
          <h2>功能开关</h2>
        </div>
        <div class="set-card-body">
          <div class="toggle-row" id="togRerank">
            <div class="toggle-info">
              <div class="toggle-name">启用 Rerank</div>
              <div class="toggle-desc">关闭后会直接送 top-K 进 LLM，更快但精度下降</div>
            </div>
            <label class="switch">
              <input type="checkbox" id="swRerank" ${pref.rerank ? 'checked' : ''}>
              <span class="slider"></span>
            </label>
          </div>
          <div class="toggle-row" id="togFallback">
            <div class="toggle-info">
              <div class="toggle-name">知识库未命中时 Fallback 到 LLM</div>
              <div class="toggle-desc">关闭则一律回答「知识库无相关内容」</div>
            </div>
            <label class="switch">
              <input type="checkbox" id="swFallback" ${pref.fallback ? 'checked' : ''}>
              <span class="slider"></span>
            </label>
          </div>
          <div class="toggle-row" id="togStreaming">
            <div class="toggle-info">
              <div class="toggle-name">流式输出</div>
              <div class="toggle-desc">逐字渲染，打字机效果</div>
            </div>
            <label class="switch">
              <input type="checkbox" id="swStreaming" ${pref.streaming ? 'checked' : ''}>
              <span class="slider"></span>
            </label>
          </div>
        </div>
      </div>

      <!-- 主题 -->
      <div class="set-card">
        <div class="set-card-head">
          <span class="set-card-icon">◑</span>
          <h2>主题</h2>
        </div>
        <div class="set-card-body">
          <p class="desc">切换浅色（暖纸白）与深色（墨色）主题</p>
          <div style="display:flex;gap:10px">
            <button class="ghost-btn" id="themeBtnLight">☀ 浅色</button>
            <button class="ghost-btn" id="themeBtnDark">☾ 深色</button>
          </div>
        </div>
      </div>

      <!-- 危险操作 -->
      <div class="set-card set-card-danger">
        <div class="set-card-head">
          <span class="set-card-icon">⚠</span>
          <h2>危险操作</h2>
        </div>
        <div class="set-card-body">
          <div style="display:flex;gap:10px;flex-wrap:wrap">
            <button class="danger-btn" id="clearSessionBtn">⤭ 清空会话</button>
            <button class="danger-btn" id="rebuildIdxBtn">↻ 重建索引</button>
            <button class="danger-btn" id="clearKbBtn">× 清空知识库</button>
          </div>
        </div>
      </div>
    </div>
  `;

  // 绑定开关
  $('#swRerank')?.addEventListener('change', (e) => {
    saveSetting('rerank_enabled', e.target.checked);
    showToast('已保存', 'Rerank 设置已更新', 'success');
  });
  $('#swFallback')?.addEventListener('change', (e) => {
    saveSetting('fallback_enabled', e.target.checked);
    showToast('已保存', 'Fallback 设置已更新', 'success');
  });
  $('#swStreaming')?.addEventListener('change', (e) => {
    saveSetting('typewriter_enabled', e.target.checked);
    showToast('已保存', e.target.checked ? '打字机效果已开启' : '打字机效果已关闭', 'success');
  });

  $('#themeBtnLight')?.addEventListener('click', () => {
    document.body.classList.remove('dark');
    state.darkMode = false;
    localStorage.setItem('theme', 'light');
    saveSetting('theme', 'light');
  });
  $('#themeBtnDark')?.addEventListener('click', () => {
    document.body.classList.add('dark');
    state.darkMode = true;
    localStorage.setItem('theme', 'dark');
    saveSetting('theme', 'dark');
  });
  $('#clearSessionBtn')?.addEventListener('click', () => {
    if (confirm('清空所有会话记录？')) {
      state.sessions.forEach(s => api(`/api/chat/sessions/${s.session_id}`, { method: 'DELETE' }).catch(() => {}));
      showToast('已清空', '会话记录已清空', 'success');
      setTimeout(refreshSessions, 500);
    }
  });
  $('#rebuildIdxBtn')?.addEventListener('click', handleRebuild);
  $('#clearKbBtn')?.addEventListener('click', () => {
    if (confirm('清空全部知识库？此操作不可恢复！')) {
      showToast('提示', '请在终端重启服务以清空向量库', 'warn');
    }
  });
}

// =============================================================================
// 导出功能（v4.3: JSON + Markdown + PDF，多选支持）
// =============================================================================

/**
 * 初始化导出面板
 */
function initExportPanel() {
  const exportBtn = $('#exportFavBtn');
  const exportPanel = $('#exportPanel');
  const closeBtn = $('#closeExportPanel');

  exportBtn?.addEventListener('click', () => {
    exportPanel.style.display = exportPanel.style.display === 'none' ? 'block' : 'none';
  });

  closeBtn?.addEventListener('click', () => {
    exportPanel.style.display = 'none';
  });

  // 收藏勾选
  $$('.fav-sel').forEach(cb => {
    cb.addEventListener('change', () => {
      const card = cb.closest('.fav-card');
      const id = card?.dataset.id;
      if (!id) return;
      if (cb.checked) {
        state.selectedFavs.add(id);
        card?.classList.add('selected');
      } else {
        state.selectedFavs.delete(id);
        card?.classList.remove('selected');
      }
      updateExportCount();
    });
  });
}

/**
 * 更新导出计数
 */
function updateExportCount() {
  const count = state.selectedFavs.size;
  const countEl = $('#exportCount');
  if (countEl) countEl.textContent = `已选 ${count} 项`;
}

/**
 * 更新收藏选中状态UI
 */
function updateFavSelection() {
  $$('.fav-card').forEach(card => {
    const id = card.dataset.id;
    const cb = card.querySelector('.fav-sel');
    if (state.selectedFavs.has(id)) {
      card.classList.add('selected');
      if (cb) cb.checked = true;
    } else {
      card.classList.remove('selected');
      if (cb) cb.checked = false;
    }
  });
  updateExportCount();
}

/**
 * 执行导出
 */
async function doExport(type) {
  let ids = [];
  let format = 'json';
  let endpoint = '';

  if (type === 'favorites') {
    ids = Array.from(state.selectedFavs);
    const fmtRadio = document.querySelector('input[name="exportFormat"]:checked');
    format = fmtRadio ? fmtRadio.value : 'json';
    endpoint = '/api/export/favorites';
  } else if (type === 'sessions') {
    ids = Array.from(state.selectedSess);
    const fmtRadio = document.querySelector('input[name="sessExportFormat"]:checked');
    format = fmtRadio ? fmtRadio.value : 'markdown';
    endpoint = '/api/export/sessions';
  }

  try {
    const resp = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids, format })
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({ error: '导出失败' }));
      showToast('导出失败', err.error || '未知错误', 'error');
      return;
    }

    // PDF/ZIP 直接下载
    const contentType = resp.headers.get('Content-Type') || '';
    if (contentType.includes('pdf') || contentType.includes('zip')) {
      const blob = await resp.blob();
      const disposition = resp.headers.get('Content-Disposition') || '';
      const match = disposition.match(/filename=(.+)/);
      const filename = match ? match[1].replace(/"/g, '') : `export.${format}`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } else {
      // JSON/Markdown 返回
      const data = await resp.json();
      const blob = new Blob([data.data], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = data.filename;
      a.click();
      URL.revokeObjectURL(url);
    }

    showToast('导出成功', `已导出 ${ids.length || '全部'} 条记录`, 'success');

    // 关闭面板
    const panel = type === 'favorites' ? $('#exportPanel') : $('#sessExportPanel');
    if (panel) panel.style.display = 'none';

  } catch (e) {
    showToast('导出失败', e.message, 'error');
  }
}

/**
 * 初始化会话导出面板
 */
function initSessExportPanel() {
  const exportBtn = $('#exportSessBtn');
  const exportPanel = $('#sessExportPanel');
  const closeBtn = $('#closeSessExportPanel');

  exportBtn?.addEventListener('click', () => {
    exportPanel.style.display = exportPanel.style.display === 'none' ? 'block' : 'none';
  });

  closeBtn?.addEventListener('click', () => {
    exportPanel.style.display = 'none';
  });

  // 全选
  $('#selectAllSess')?.addEventListener('change', (e) => {
    if (e.target.checked) {
      state.selectedSess = new Set(state.sessions.map(s => s.session_id));
    } else {
      state.selectedSess = new Set();
    }
    updateSessSelection();
  });

  // 确认导出
  $('#doSessExportBtn')?.addEventListener('click', () => doExport('sessions'));
}

/**
 * 更新会话选中状态UI
 */
function updateSessSelection() {
  $$('.sess-row').forEach(row => {
    const id = row.dataset.id;
    const cb = row.querySelector('.sess-sel');
    if (state.selectedSess.has(id)) {
      row.classList.add('selected');
      if (cb) cb.checked = true;
    } else {
      row.classList.remove('selected');
      if (cb) cb.checked = false;
    }
  });
  const countEl = $('#sessExportCount');
  if (countEl) countEl.textContent = `已选 ${state.selectedSess.size} 项`;
}

// =============================================================================
// 启动
// =============================================================================
async function init() {
  // 加载用户设置
  await loadSettings();

  // Tab 切换
  $$('.nav-item').forEach(item => {
    item.addEventListener('click', () => switchTab(item.dataset.tab));
  });

  // 主题切换
  const savedTheme = localStorage.getItem('theme') || state.userSettings?.theme || 'light';
  if (savedTheme === 'dark') {
    state.darkMode = true;
    document.body.classList.add('dark');
  }
  $('#themeToggle')?.addEventListener('click', () => {
    state.darkMode = !state.darkMode;
    document.body.classList.toggle('dark', state.darkMode);
    localStorage.setItem('theme', state.darkMode ? 'dark' : 'light');
    saveSetting('theme', state.darkMode ? 'dark' : 'light');
  });

  // 全局拖拽
  setupGlobalDragDrop();

  // 快捷键
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      $('#chatInput')?.focus();
    }
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      $('#chatForm')?.requestSubmit();
    }
  });

  // 加载引擎状态
  await loadEngineStatus();

  // 渲染所有 tab 内容（默认显示 chat）
  renderChat();
  switchTab('chat');

  // 预加载其他 tab
  api('/api/knowledge_base').then(r => state.documents = r.documents).catch(() => {});
  api('/api/tags').then(r => state.tags = r.tags).catch(() => {});
  api('/api/chat/sessions').then(r => state.sessions = r.sessions).catch(() => {});
  api('/api/favorites').then(r => state.favorites = r.favorites).catch(() => {});
}

// 启动
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
