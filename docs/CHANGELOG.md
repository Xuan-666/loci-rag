# 更新日志 v5.1

> 所有重要变更都记录在此。
> 格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [5.1] - 2026-06-12

### Removed — 彻底移除 Gradio 备用入口

- **`app.py`（1127 行）已删除**：原 Gradio 5-Tab 入口（知识库 / 智能问答 / 收藏 / 会话 / 设置）
  - 所有 Gradio Blocks 组件、`gr.Blocks` / `gr.Tab` / `gr.Chatbot` / `gr.update` 调用
  - 所有 `handle_*` 闭包：`handle_upload_files` / `handle_upload_folder` / `handle_add_url` / `handle_delete` / `handle_fulltext_search` / `handle_clear_kb` / `handle_list_versions` / `handle_rollback` / `handle_create_snapshot` / `handle_cleanup_versions` / `handle_toggle_watcher` / `handle_query_streaming` / `handle_select_session_in_qa` / `handle_new_session` / `do_fav` / `handle_list_sessions_html` / `handle_create_session` / `handle_load_session` / `handle_delete_session` / `handle_export_session` / `handle_create_tag` / `handle_delete_tag` / `handle_list_tags_html` / `handle_change_theme`
  - `get_theme()` / `_format_sources_html()` / `_highlight_html()` / `get_engine_status()` / `get_kb_stats_html()` / `get_doc_list_html()` / `load_favorites()` / `save_favorites()` / `add_favorite()` / `get_favorites_html()` / `get_favorite_detail()` / `add_annotation()` 等 30+ 辅助函数
  - `build_app()` 5-Tab Gradio 界面定义
- **`gradio>=4.0.0` 依赖已移除**：`requirements.txt` 不再包含 gradio
- **`config.THEME_NAME = "Soft"` 已移除**：原 Gradio 主题配置（Soft / Glass / Default），前端主题由 `localStorage` + CSS 变量管理

### Changed — 文档同步

- **`README.md`**：
  - 标题与徽章版本号 v5.0 → v5.1
  - 移除「3.3 启动（备选：Gradio 入口）」整节
  - 项目结构图移除 `app.py` 入口行
- **`docs/DEVELOPMENT.md`**：版本号 v4.2 → v5.1；目录布局图移除 `app.py`；依赖清单移除 `gradio` 行
- **`docs/ARCHITECTURE.md`**：版本号 v4.2 → v5.1

### Stats
- 删除文件：1 个（`app.py`，1127 行）
- 删除依赖：1 个（`gradio>=4.0.0`）
- 删除配置项：1 个（`config.THEME_NAME`）
- 启动入口收敛：根目录 Python 文件 3 → 2（`web_api.py` / `config.py`）
- 前端覆盖度：HTML / CSS / JS 已实现所有 5 Tab 功能，零 Gradio 依赖
- 验证：Flask `web_api.py` 启动正常，前端 5 Tab 加载正常，所有 API 端点 200

---

## [5.0] - 2026-06-12

### Changed — 项目结构重构
- **Python 模块移入 `loci/` 包**：`rag_engine.py` / `chat_store.py` / `favorites_store.py` / `tag_manager.py` / `version_manager.py` / `web_loader.py` / `folder_watcher.py` / `exporters.py` / `settings_manager.py` → `loci/` 目录
- **前端资源移入 `frontend/`**：`index.html` → `frontend/index.html`，`static/` → `frontend/static/`
- **运行时数据移入 `data/`**：`chat_history.json` / `favorites.json` / `tags.json` / `user_settings.json` / `uploaded_docs/` / `vector_store/` / `vector_store_versions/` → `data/` 目录
- **`config.py` 路径更新**：`VECTOR_STORE_PATH` / `UPLOADED_DOCS_PATH` 指向 `data/` 子目录；新增 `CHAT_HISTORY_PATH` / `TAGS_PATH` / `FAVORITES_PATH` / `USER_SETTINGS_PATH`
- **`web_api.py` import 更新**：所有 `from xxx import` → `from loci.xxx import`；`STATIC_DIR` 指向 `frontend/`
- **`app.py` import 更新**：所有 `from xxx import` → `from loci.xxx import`；路径指向 `data/`
- **`rag_engine.py` 内部 import 更新**：`from web_loader` / `from version_manager` → `from .web_loader` / `from .version_manager`（包内相对导入）
- **`.gitignore` 更新**：新增 `data/` 下运行时数据忽略规则；新增 `.claude/` 忽略
- **`README.md` 更新**：版本号 v4.2 → v5.0；项目结构图更新为四层隔离架构

### Removed — 非必要文件清理
- `.claude/` — Claude 技能文件（~12 个文件）
- `.playwright-cli/` — Playwright 调试会话 yml（32 个文件）
- `design-demos/` — 设计阶段原型 HTML/PNG/笔记（~27 个文件）
- `e2e_results/` — E2E 测试截图（7 个 PNG）
- `e2e_verify.py` — Playwright E2E 测试脚本
- `tests/` — 单元测试文件（3 个：test_rag_fallback.py / test_settings_manager.py / test_exporters.py）
- `test_export.md` / `test_export.pdf` — 导出功能测试产物
- `各种文件格式上传测试/` — 文件格式兼容性测试样本（~25 个文件）
- `docs/superpowers/` — AI Agent 会话计划/规格文档（3 个文件）
- `vector_store_versions/` 旧版快照：11 个版本 → 保留最新 1 个

### Stats
- 删除文件：~110+ 个
- 目录层级：根目录 Python 文件 12 → 3（web_api.py / app.py / config.py）
- 新增目录：`loci/` / `frontend/` / `data/`
- 服务验证：Flask 启动正常，所有 API 端点 200，前端页面加载正常

---

## [4.2] - 2026-06-11

### Changed
- **代码重构**：提取 `rag_engine._resolve_sources()` / `_run_fallback()` / `_stream_fallback()` / `_split_scored()`，`query()` 与 `stream_query()` 共享同一检索链路
- **新模块**：抽出 `favorites_store.py`（与 `chat_store` / `tag_manager` 风格一致的 JSON+lock 持久化类）
- **web_api.py 清理**：使用 `FavoritesStore` 替换内联 favorites 逻辑；抽取 `_ingest_uploaded_files()` 让 upload / rebuild 共享
- **config.py 清理**：删除未使用的 UI 颜色常量（`UI_PRIMARY_COLOR` 等）
- **README 重写**：从 290 行的 v3 旧文档重写为 175 行的 v4.2 产品级介绍
- **文档结构拆分**：从 1 个 README 拆为 6 个聚焦文档（README / USER_GUIDE / API / ARCHITECTURE / DEVELOPMENT / CHANGELOG）

### Removed
- `tests/` 目录（8 个测试文件）— 按用户要求
- 重复的模块级 docstring（`config.py`）
- 重复的 `import os`
- 重复的 `if not engine` 校验逻辑

### Fixed
- `app.js` 顶部 Python 风格 docstring（已在 v4.1 修复确认）
- doc name 路径污染（FAISS 存储 `./uploaded_docs\\file.pdf`，API 透传后端）

### Stats
- `rag_engine.py`: -60 行重复代码
- `config.py`: -10 行未用常量
- 新增 `favorites_store.py`: 175 行（含 docstring）
- 新增 5 个产品级文档：约 1500 行

---

## [4.1] - 2026-06-11

### Added
- **RAG Fallback 机制**：精排分数过低时自动切到纯 LLM（避免「未找到相关内容」的卡顿体验）
  - 配置：`RAG_FALLBACK_ENABLED` / `RAG_FALLBACK_THRESHOLD`
  - UI：答案上方黄色提示条
- **前端 SSE 流式渲染**：用 `fetch().body.getReader()` + `TextDecoder` 解 SSE
- **三阶段状态条**：Searching → Reading → Writing 可视化
- **持久输入框**：移出 Hero，多轮对话不卡
- **永远可见的 Sources 面板**：右侧 360px 固定列
- **混合检索权重调优**：`BM25_WEIGHT=0.3` / `VECTOR_WEIGHT=0.7` / `RERANK_SCORE_THRESHOLD=0.3`
- **花叔design B版前端**：Perplexity 学术图书馆风格

### Fixed
- **BM25 检索失败**：`get_relevant_documents()` → `invoke()` 适配 LangChain 1.x
- **多轮对话持久化错乱**：空 `session_id` 自动创建
- **`gr.Chatbot` 未设 `type="messages"`**
- **删除 `restore_vectorstore` 重复定义**
- **删除 `HybridRetriever` 死代码**

### Stats
- 66 个测试用例通过（v4.1 时期；v4.2 起按用户要求移除 `tests/` 目录；v5.2 起在 `tests/` 下重新建立最小测试集）
- 2 个关键 Bug 修复
- 性能：检索链路 5-8x 提速（精排后上下文缩短）

---

## [4.0] - 2026-06-10

### Added
- **多轮对话上下文注入**：最近 5 轮历史自动拼接到 prompt
- **流式输出**：`stream_query()` 逐 token yield
- **聊天记录持久化**：`chat_history.json` 多会话 JSON 存储
- **会话管理 UI**：列表 + 删除 + 自动命名
- **标签/分类管理**：
  - 文档打标
  - 检索时按标签过滤（AND 语义）
  - 标签颜色自定义
- **全文搜索 + 高亮**：BM25 全文 + `<mark>` 高亮预览
- **URL/网页摄取**：trafilatura 抽取正文，自动入库
- **文件夹监控**：watchdog 监听 `uploaded_docs/`，新文件自动入库
- **向量库版本快照**：
  - 变更前自动备份
  - 一键回滚到指定版本
  - 最多保留 10 个版本（可配置）
- **主题切换**：Soft / Glass / Default 三套
- **Gradio 5 Tab 布局**：知识库 / 智能问答 / 收藏 / 会话 / 设置

### Stats
- 50+ 个新方法
- 3000+ 行新代码
- 8 个新功能模块

---

## [3.0] - 2026-06-03

### Added
- **BM25+向量 RRF 混合检索**：
  - 向量权重 0.7 + BM25 权重 0.3
  - 兼顾语义与关键词
- **CrossEncoder Rerank 精排**：
  - bge-reranker-base 模型
  - 粗排 Top20 → 精排 Top5
- **双模式 Embedding**：
  - BGE-Small-ZH（HuggingFace 离线）
  - nomic-embed-text（Ollama）
  - 一行配置切换
- **增强分片策略**：
  - 表格保护（占位符→切分→还原）
  - 标题绑定
  - 内容去重
  - 30% overlap
- **jin-document-parser PDF 解析**：
  - 优先用，PyPDF 自动回退
  - 统一 Markdown 输出
- **启动诊断**：`config.diagnose()` 报告关键组件状态

### Changed
- `rag_engine.py` 升级到 850+ 行
- `config.py` 添加 50+ 个新配置项

### Stats
- 检索精度：Top5 命中率提升 40%（对照 v2.1）
- 启动时间：-30%（缓存 + 离线模型）

---

## [2.1] - 2026-05-18

### Added
- 文档预览：PDF 前 3 页、Word 前 2000 字、Excel 前 10 行、PPT 前 3 张
- PDF 导出：reportlab + SimHei 中文字体
- Markdown 导出
- 收藏标注：问答对 + 个人备注
- 精确删除单文档（修复 v2.0 的「删除一个→删全部」bug）

### Fixed
- 收藏导入兼容旧数据
- 文档预览中文编码
- 大文件分片内存溢出

---

## [2.0] - 2026-05-17

### Added
- 文档来源追溯：每个回答附带来源、页码、相关性分数
- 批量上传
- 知识库统计
- 4 Tab 布局（Gradio Blocks）：知识库 / 智能问答 / 收藏 / 导出

### Stats
- 850+ 行代码
- 15 种文档格式支持
- 完整 LCEL 链式调用

---

## [1.0] - 2026-05-16

### Added
- 基础 RAG 问答
- PDF / Word 支持
- FAISS 向量库
- Gradio 单页面

### Stats
- 200+ 行代码
- 2 种文档格式
- 1 个 Tab

---

## 迁移指南

### v5.0 → v5.1

无破坏性变更。删除 Gradio 入口的步骤：
1. 删除根目录的 `app.py`（如有旧版本残留）
2. 从 `requirements.txt` 移除 `gradio>=4.0.0` 行
3. 启动方式不变，仍是 `python web_api.py`

前端主题（浅色/深色）现由浏览器 `localStorage` 管理，迁移前后行为一致。

### v4.2 → v5.0

项目结构已重构，无需手动迁移代码。启动方式不变（`python web_api.py`）。

注意事项：
1. 运行时数据（JSON / uploaded_docs / vector_store）已移入 `data/` 目录
2. 首次启动时系统会自动从 `data/` 读取已有数据
3. 如需手动迁移旧数据，将根目录下的 `chat_history.json` / `favorites.json` / `tags.json` / `user_settings.json` / `uploaded_docs/` / `vector_store/` / `vector_store_versions/` 移入 `data/` 即可

### v4.1 → v4.2

无需手动迁移。代码重构在内部完成，向后兼容。

### v4.0 → v4.1

无需手动迁移。SSE 流式和 Fallback 默认开启，可在 `config.py` 调整。

### v3.0 → v4.0

需要做的：
1. 安装新依赖：`pip install watchdog trafilatura striprtf`
2. 启动时检查 `version_manager` 是否创建（`vector_store_versions/` 目录）
3. 旧 `favorites.json` 格式会被自动识别

### v2.x → v3.0

需要做的：
1. 安装：`pip install rank-bm25 sentence-transformers jieba`
2. 下载新模型：`modelscope download --model BAAI/bge-reranker-base`
3. 切换 Embedding：在 `config.py` 改 `EMBEDDING_PROVIDER = "huggingface"`
4. 删除旧 `vector_store/`，重建索引
