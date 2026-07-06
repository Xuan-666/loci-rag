# 开发指南 v5.1

> 给贡献者的开发文档。
> 开发环境、代码规范、目录布局、调试技巧、提 PR 流程。

---

## 0 · 快速上手

### 0.1 克隆 & 安装

```bash
git clone <repo-url> "本地知识库RAG问答系统"
cd "本地知识库RAG问答系统"

# Python 3.10+ 推荐 3.12
python -m venv .venv
.\.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

pip install -r requirements.txt
```

### 0.2 启动开发模式

```powershell
# 启动 Flask（默认 debug=False，改成 True 可热重载）
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'
python web_api.py
```

浏览器打开 `http://localhost:7862`。

### 0.3 调试前端

前端在 `frontend/static/app.js` + `frontend/static/custom.css`，修改后 **F5 刷新** 即可（Flask 静态文件无缓存）。

可用 Chrome DevTools → Network → 勾选 "Disable cache"。

---

## 1 · 代码规范

### 1.1 Python 风格

- **PEP 8**（`ruff` / `flake8` 强制）
- 类型注解：公共方法、对外 API 必须有
- 文档字符串：所有模块/类/公共方法必须有
- 中文注释：复杂逻辑必须有
- 命名：
  - 类名：`PascalCase`
  - 函数/变量：`snake_case`
  - 常量：`UPPER_SNAKE_CASE`
  - 私有方法：`_snake_case`

### 1.2 函数级注释（强制）

所有函数必须有 docstring：

```python
def calculate_score(question: str, doc: Document) -> float:
    """
    计算 question 与 doc 的相关性分数。

    Args:
        question: 用户问题
        doc: 文档片段

    Returns:
        0-1 之间的相关性分数，越高越相关

    Raises:
        ValueError: 当 question 为空时
    """
    if not question:
        raise ValueError("question 不能为空")
    ...
```

### 1.3 重构原则

- **小步重构**：每次改 1 处，频繁 commit
- **测试保障**：重构前确认有测试覆盖（见 5.2）
- **代码审查**：提 PR 前自审一遍
- **避免冗余**：每行代码要么有用，要么删掉

---

## 2 · 项目布局

### 2.1 目录结构

```
.
├── web_api.py              # Flask 主入口（唯一入口，v5.1 起移除 Gradio 备选）
├── loci/                   # 核心业务模块包
│   ├── rag_engine.py       # RAG 核心（混合检索 + Rerank + Fallback）
│   ├── chat_store.py       # 聊天记录 JSON 持久化
│   ├── favorites_store.py  # 收藏 JSON 持久化
│   ├── tag_manager.py      # 标签管理
│   ├── version_manager.py  # FAISS 向量库版本快照
│   ├── web_loader.py       # URL 摄取
│   ├── folder_watcher.py   # watchdog 文件夹监控
│   ├── exporters.py        # 导出模块（JSON/Markdown/PDF）
│   ├── settings_manager.py # 用户设置持久化
│   └── __init__.py         # 包标识
├── config.py               # 统一配置
│
├── frontend/               # 前端资源
│   ├── index.html          # 花叔design B版前端（Perplexity 学术图书馆风格）
│   └── static/
│       ├── app.js          # 前端逻辑（SSE 流式 + 主题切换 + 5 Tab 状态机）
│       └── custom.css      # 设计令牌（CSS 变量）+ 组件样式
│
├── docs/                   # 文档
├── data/                   # 运行时数据（.gitignore）
│   ├── chat_history.json
│   ├── favorites.json
│   ├── tags.json
│   ├── user_settings.json
│   ├── uploaded_docs/      # 上传文档存储
│   ├── vector_store/       # FAISS 索引
│   ├── vector_store_versions/  # 版本快照
│   └── uploaded_images/    # 上传图片（v4.2+）
└── README.md
```

### 2.2 模块依赖（详见 `docs/ARCHITECTURE.md`）

```
config (叶子，无依赖)
  ↑
  ├── tag_manager, chat_store, favorites_store (互不依赖)
  ↓
  rag_engine
  ↓
  web_api
```

---

## 3 · 调试技巧

### 3.1 检索链路调试

`rag_engine.py` 已内置 `[RAG Debug]` 日志：

```
[RAG Debug] query='中山大学2025年计算机学硕考什么科目？'
[RAG Debug] 混合检索 → 17 | Rerank 后 → 5
[RAG Debug]  Top1: 中山大学2025年招生简章.pdf score=0.745
[RAG Debug]  Top2: 中山大学2025年招生简章.pdf score=0.596
```

启动前 `set RAG_DEBUG=1` 即可看完整日志。

### 3.2 SSE 调试

浏览器 DevTools → Network → 找到 `api/query/stream` 请求 → Preview 标签 → 看流式事件。

或用 curl 实时观察：
```bash
curl -N -X POST http://localhost:7862/api/query/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"你好"}'
```

### 3.3 前端 Console

Chrome DevTools → Console 标签。所有 `console.log` / `console.error` 会在这里。

打开 `frontend/static/app.js` 看 `state` 对象（包含当前 session / settings）：

```js
// 在 Console 里执行
JSON.stringify(state, null, 2)
```

### 3.4 性能分析

`rag_engine.py` 的 `query()` / `stream_query()` 里可以加 `time.time()` 计时：

```python
import time
t0 = time.time()
retrieved_docs = self._hybrid_search(question, tag_filter)
print(f"[Perf] hybrid search: {(time.time()-t0)*1000:.0f}ms")
```

---

## 4 · 扩展开发

### 4.1 接入新 Embedding 模型

1. 在 `config.py` 添加配置：
   ```python
   NEW_EMBED_MODEL_PATH = "/path/to/model"
   ```
2. 在 `rag_engine.py` 添加类：
   ```python
   class NewEmbedding(BaseEmbeddings):
       def embed_query(self, text): ...
       def embed_documents(self, texts): ...
   ```
3. 在 `RAGEngine._init_embedding()` 路由：
   ```python
   if config.EMBEDDING_PROVIDER == "new":
       return NewEmbedding()
   ```

### 4.2 接入新 LLM

类似上面，在 `config.py` 加配置，`RAGEngine._init_llm()` 路由。

### 4.3 接入新文档格式

1. 在 `rag_engine.py` 添加 Loader 类：
   ```python
   class EPubLoader(BaseLoader):
       def load(self) -> List[Document]:
           ...
   ```
2. 在 `get_loader()` 注册：
   ```python
   def get_loader(file_path):
       if file_path.endswith(".epub"): return EPubLoader(file_path)
       ...
   ```

### 4.4 接入新前端框架

`web_api.py` 的 RESTful + SSE 端点可对接任意前端。

- **Vue 3**：用 `fetch` + `ReadableStream` 解 SSE
- **React**：用 `useEffect` + `EventSource`（注意 EventSource 不支持 POST，需改用 fetch）
- **原生 JS**：参考 `frontend/static/app.js`

---

## 5 · 测试策略

> ⚠️ **当前项目未集成自动化测试**（v4.2 起按用户要求删除了 tests/ 目录）。
> 手动验证流程见 5.1。

### 5.1 手动验证（推荐）

每次修改后跑一遍：

1. **健康检查**：`curl http://localhost:7862/api/health` → 应返回 `{"status":"ok"}`
2. **上传 1 个文档** → 知识库 Tab 出现文档
3. **提问知识库里的问题** → 看到 5 个 sources 命中
4. **提问知识库外的问题** → 看到黄色 fallback banner
5. **收藏 1 条问答** → 收藏 Tab 出现该条
6. **切到深色主题** → 整页背景变暗

### 5.2 e2e 端到端测试（Playwright）

```python
# 安装 Playwright
pip install playwright
playwright install chromium

# 写 e2e 脚本
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await browser.new_page()
    await page.goto("http://localhost:7862")
    await page.wait_for_selector(".chat-hero h1")
    await page.screenshot(path="e2e_home.png")
    ...
```

### 5.3 单元测试（计划中）

待 v4.3 集成。可考虑用 `pytest` + `pytest-asyncio`。

---

## 6 · 部署到生产

### 6.1 单机生产部署

```powershell
# 用 waitress（Windows 友好）替代 Flask dev server
pip install waitress
waitress-serve --host=0.0.0.0 --port=7862 web_api:app
```

或用 `gunicorn`（Linux）：
```bash
gunicorn -w 4 -b 0.0.0.0:7862 web_api:app
```

### 6.2 Docker 化（v4.3 计划）

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 7862
CMD ["python", "web_api.py"]
```

### 6.3 反向代理（Nginx）

```nginx
location / {
    proxy_pass http://localhost:7862;
    proxy_set_header Host $host;
    proxy_buffering off;  # 关键：SSE 需要关闭缓冲
    proxy_cache off;
}
```

---

## 7 · 性能调优

### 7.1 检索阶段

| 调优点 | 配置项 | 推荐值 |
|:---|:---|:---|
| 精排候选数 | `RERANK_INITIAL_K` | 10-15 |
| 精排保留数 | `RERANK_FINAL_K` | 3-5 |
| 阈值 | `RERANK_SCORE_THRESHOLD` | 0.3 |
| 向量权重 | `VECTOR_WEIGHT` | 0.7（默认） |
| BM25 权重 | `BM25_WEIGHT` | 0.3（默认） |

### 7.2 LLM 阶段

| 调优点 | 配置项 | 推荐值 |
|:---|:---|:---|
| 模型大小 | `LLM_MODEL` | 7B（速度与精度平衡） |
| Temperature | `LLM_TEMPERATURE` | 0（确定性） |
| 最大 token | `LLM_MAX_TOKENS` | 1024 |

### 7.3 前端阶段

- 限制预览文本长度（已实现 200 字符）
- Tab 切换用 `innerHTML` 重绘（已实现）
- SSE 用 `TextDecoder` 流式解码（已实现）

---

## 8 · 提 PR 流程

1. **Fork** 仓库
2. 创建分支：`git checkout -b feat/your-feature`
3. 提交：`git commit -m "feat: add your feature"`
4. 推送：`git push origin feat/your-feature`
5. 提 PR：描述改了什么 + 截图 + 是否破坏向后兼容
6. CI：自动跑 e2e（如有配置）
7. Review：通过后合并

### 8.1 Commit 规范

```
feat: 新功能
fix:  Bug 修复
docs:  文档
style: 代码风格（无功能变化）
refactor: 重构（无功能变化）
perf:  性能优化
test:  测试
chore: 构建/工具链
```

例：
```
feat: add support for .epub file format
fix: SSE event source path prefix cleanup
docs: update API.md for v4.2 endpoints
```

---

## 9 · 安全开发

- **不要**把 API Key / 密钥写进代码（用 `~/.config/env` 读）
- **不要**把 `favorites.json` / `chat_history.json` 含个人数据 commit
- **不要**绕过 `HF_HUB_OFFLINE=1` 让代码联网
- 接受 PR 前**必须** review 依赖列表（`requirements.txt`）

---

## 10 · 联系方式

- 提 Issue：<repo-url>/issues
- 邮箱：<your-email>
- 文档：`docs/` 目录

---

## 11 · 附录：依赖清单

主要 Python 包（详见 `requirements.txt`）：

| 包 | 用途 |
|:---|:---|
| `flask` | Web 框架 |
| `flask-cors` | CORS 支持 |
| `langchain` | LLM 编排 |
| `langchain-community` | LangChain 社区组件 |
| `langchain-ollama` | Ollama 集成 |
| `faiss-cpu` | 向量检索 |
| `rank-bm25` | BM25 算法 |
| `jieba` | 中文分词 |
| `sentence-transformers` | CrossEncoder 精排 |
| `pypdf` / `jin-doc-parser` | PDF 解析 |
| `python-docx` | Word 解析 |
| `openpyxl` | Excel 解析 |
| `python-pptx` | PPT 解析 |
| `striprtf` | RTF 解析 |
| `trafilatura` | 网页正文抽取 |
| `watchdog` | 文件夹监控 |
| `reportlab` | PDF 导出（v3 兼容） |

**模型清单（自动下载）：**
- `BAAI/bge-small-zh-v1.5` (~100MB)
- `BAAI/bge-reranker-base` (~300MB)
- Ollama: `deepseek-r1:7b` (~4GB)
