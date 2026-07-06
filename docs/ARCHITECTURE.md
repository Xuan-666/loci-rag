# 架构文档 v5.1

> 给架构师 / 高级开发看的系统级设计文档。
> 模块边界、数据流、性能调优点、扩展点。

---

## 0 · 系统全景

```
┌────────────────────────────────────────────────────────────────────────┐
│  浏览器 (Chrome/Edge/Firefox)                                           │
│  frontend/index.html + frontend/static/app.js + frontend/static/custom.css                        │
└────────────────────────────┬───────────────────────────────────────────┘
                             │ HTTP / SSE
┌────────────────────────────▼───────────────────────────────────────────┐
│  Flask Web API (web_api.py)                                              │
│  ├── /api/query/stream  ←  SSE 流式问答                                │
│  ├── /api/knowledge_base/*  ←  KB CRUD                                 │
│  ├── /api/tags/*             ←  标签管理                                 │
│  ├── /api/chat/sessions/*    ←  会话管理                                 │
│  ├── /api/favorites/*        ←  收藏管理                                 │
│  ├── /api/engine_status      ←  引擎诊断                                 │
│  └── /api/health             ←  健康检查                                 │
└────────────────────────────┬───────────────────────────────────────────┘
                             │ Python 调用
┌────────────────────────────▼───────────────────────────────────────────┐
│  业务逻辑层                                                               │
│  RAGEngine    ChatStore    TagManager    FavoritesStore    VersionMgr  │
│  (核心 RAG)  (会话持久化) (标签管理)   (收藏持久化)   (索引快照)         │
└────────────────────────────┬───────────────────────────────────────────┘
                             │ LangChain LCEL 链
┌────────────────────────────▼───────────────────────────────────────────┐
│  算法层                                                                 │
│  PDFLoader / DOCXLoader / ExcelLoader / PPTXLoader / TextLoader / WebLdr│
│  EnhancedTextSplitter                                                  │
│  HuggingFaceBGEEmbedding / OllamaEmbedding                              │
│  HybridRetriever (BM25 + FAISS RRF)                                    │
│  CrossEncoderReranker                                                   │
└────────────────────────────┬───────────────────────────────────────────┘
                             │ TCP / Disk
┌────────────────────────────▼───────────────────────────────────────────┐
│  数据层                                                                 │
│  uploaded_docs/  vector_store/  vector_store_versions/                  │
│  chat_history.json  favorites.json  tags.json                           │
│  Ollama service (localhost:11434)                                       │
│  HuggingFace cache (./.cache/huggingface)                               │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 1 · 模块依赖图

```
                     ┌─────────────────┐
                     │     config      │  ← 0 依赖（被所有模块 import）
                     └────────┬────────┘
                              │
       ┌──────────────────────┼──────────────────────┐
       ▼                      ▼                      ▼
┌──────────────┐    ┌──────────────────┐    ┌──────────────────┐
│ tag_manager  │    │   chat_store     │    │ favorites_store  │  ← 纯 JSON 存储
│ (独立)       │    │   (独立)         │    │ (v5.1 提取)      │
└──────┬───────┘    └────────┬─────────┘    └────────┬─────────┘
       │                     │                       │
       │     ┌───────────────┼───────────────────────┘
       │     │               │
       ▼     ▼               ▼
┌─────────────────────────────────────┐
│            web_api.py               │  ← Flask 路由层
│     (RESTful + SSE endpoint)        │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│            rag_engine               │  ← 核心业务逻辑
│  ├── load_documents / add_url       │
│  ├── _hybrid_search (BM25+向量RRF)  │
│  ├── _resolve_sources (v5.1 提取)   │
│  ├── query / stream_query           │
│  ├── _run_fallback / _stream_fallback│
│  └── delete_document / rebuild      │
└────────────────┬────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────┐
│     version_manager / web_loader    │  ← 可选增强
│     folder_watcher (watchdog)       │
└─────────────────────────────────────┘
```

**关键依赖原则：**
- `config` 是叶子节点，不依赖任何业务模块
- `favorites_store` / `chat_store` / `tag_manager` 互不依赖（独立可替换）
- `rag_engine` 依赖所有存储模块（用于查询文档名、写入 chat）
- `web_api` 是唯一串联所有模块的地方（路由层）

---

## 2 · RAG 检索链路（核心流程）

### 2.1 完整流水线

```
用户问题
   │
   ▼
[1] 混合检索 (HybridRetriever)
    ├── BM25 召回 Top20 (rank-bm25 + jieba)
    ├── FAISS 向量召回 Top20 (cosine similarity)
    └── RRF 融合 → Top20 候选
   │
   ▼
[2] Rerank 精排 (CrossEncoderReranker)
    └── bge-reranker-base 打分 → Top10
   │
   ▼
[3] 阈值过滤 (RERANK_SCORE_THRESHOLD=0.3)
    └── 过滤掉分数 < 0.3 的低质匹配
   │
   ▼
[4] Fallback 决策
    ├── 若过滤后还有结果 → 走 LLM 生成路径
    └── 若过滤后无结果 → 检查 RAG_FALLBACK_ENABLED
        ├── True  → 走 fallback 路径（纯 LLM，无上下文）
        └── False → 返回 "未找到相关内容"
   │
   ▼
[5] LLM 生成 (OllamaChat)
    ├── 构造 prompt: system + context(top5 docs) + history + question
    └── LCEL: prompt | llm | StrOutputParser()
   │
   ▼
[6] 流式输出 (SSE)
    └── events: sources → token* → done
```

### 2.2 v5.1 关键抽象：`_resolve_sources()`

```python
def _resolve_sources(self, question, tag_filter) -> Tuple[str, List]:
    """公共检索链路，被 query() 和 stream_query() 共享。"""
    # 1. KB 校验
    # 2. 混合检索
    # 3. Rerank 精排
    # 4. 阈值过滤
    # 5. Fallback 决策
    
    if vectorstore is None or llm is None:
        return ("empty", None)
    if not retrieved_docs:
        return ("empty", None)
    if not scored_docs:
        return ("fallback" if config.RAG_FALLBACK_ENABLED else "empty", None)
    return ("ok", scored_docs)
```

**为什么提取？**
- 原本 `query()` 和 `stream_query()` 各有 ~60 行几乎一样的代码
- 改一处要改两处，容易出 bug
- 提取后行为完全一致，单测也好写

---

## 3 · 数据持久化层

### 3.1 存储风格统一

| 类 | 存储 | 锁 | 原子写 | 容错读 |
|:---|:---|:---|:---|:---|
| `ChatStore` | `chat_history.json` | ✅ | ✅ | ✅ |
| `TagManager` | `tags.json` | ✅ | ✅ | ✅ |
| `FavoritesStore` (v5.1) | `favorites.json` | ✅ | ✅ | ✅ |
| `VersionManager` | `vector_store_versions/` | 文件级 | 文件 rename | N/A |

**JSON 存储的 4 个共同特征：**
1. 顶层是 dict（`{"items": [...]}`），方便后续扩展字段
2. 写入用 `temp + rename` 原子操作
3. 读取容错：JSON 损坏返回空结构，不抛异常
4. 写操作加 `threading.Lock`

### 3.2 FAISS 向量库

- **存储路径**：`./vector_store/` (单文件：`index.faiss` + `index.pkl`)
- **元数据**：`source` / `page` / `chunk_id` / `tags` 存在 `index.pkl` 里
- **版本快照**：每次大规模变更前，`VersionManager.create_version()` 把 `vector_store/` 整个目录复制到 `vector_store_versions/v_YYYYMMDD_HHMMSS/`
- **回滚**：把指定版本的目录复制回 `vector_store/`，重启服务即可

---

## 4 · 前后端协议

### 4.1 SSE 流式问答（最复杂的一个端点）

```
POST /api/query/stream
Content-Type: application/json
{
  "question": "...",
  "session_id": "...",  // 可选，不传则自动创建
  "history": [["user_q", "assistant_a"], ...],
  "tag_filter": ["标签1", ...]
}

↓ Server-Sent Events (流式响应)

event 1: data: {"type":"sources", "sources":[{...}], "fallback":false, "session_id":"..."}
event 2: data: {"type":"token", "content":"中山"}
event 3: data: {"type":"token", "content":"大学"}
event 4: data: {"type":"token", "content":"..."}
...
event N: data: {"type":"done", "session_id":"...", "auto_created":true}
```

**前端解析（`frontend/static/app.js`）：**
```js
const reader = resp.body.getReader();
const decoder = new TextDecoder();
let buffer = '';
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  const events = buffer.split('\n\n');
  buffer = events.pop() || '';
  for (const evt of events) {
    if (evt.startsWith('data: ')) {
      const payload = JSON.parse(evt.slice(6));
      handleStreamEvent(payload);  // 更新 UI
    }
  }
}
```

### 4.2 端点总览（详见 `docs/API.md`）

| 端点 | 方法 | 用途 |
|:---|:---|:---|
| `/api/health` | GET | 健康检查 |
| `/api/engine_status` | GET | 引擎配置摘要 |
| `/api/knowledge_base` | GET | 文档列表 |
| `/api/knowledge_base/stats` | GET | 统计 |
| `/api/knowledge_base/upload` | POST | 上传 |
| `/api/knowledge_base/rebuild` | POST | 重建索引 |
| `/api/knowledge_base/documents/<n>` | DELETE | 删除 |
| `/api/tags` | GET/POST | 标签 CRUD |
| `/api/tags/<n>` | DELETE | 标签删除 |
| `/api/query/stream` | POST | SSE 流式问答 |
| `/api/chat/sessions` | GET/POST | 会话 |
| `/api/chat/sessions/<id>` | GET/DELETE | 单会话 |
| `/api/favorites` | GET/POST | 收藏 |
| `/api/favorites/<id>` | DELETE | 单条删除 |

---

## 5 · 性能调优点

### 5.1 检索阶段

| 瓶颈 | 调优点 |
|:---|:---|
| BM25 索引构建慢 | 文档入库时增量构建，全量重建仅在 `rebuild` 时触发 |
| FAISS 召回慢 | `nprobe` 参数调小（默认即可）；chunk 数 > 100k 时考虑改用 HNSW |
| Rerank 慢 | `RERANK_INITIAL_K` 调小（10-15），送入 Rerank 的候选越少越快 |
| 阈值过低 | 调到 0.3+ 过滤低质匹配，减少后续 LLM 上下文长度 |

### 5.2 LLM 阶段

| 瓶颈 | 调优点 |
|:---|:---|
| Token 输出慢 | 换更小的模型（`deepseek-r1:1.5b` 速度 5x）；或量化（Q4/Q5） |
| 上下文过长 | 调小 `RERANK_FINAL_K`（3-5）；截断 `top_docs` 的 page_content |
| 重复生成 | 设置 `temperature=0` 或加 repetition_penalty |

### 5.3 前端阶段

| 瓶颈 | 调优点 |
|:---|:---|
| SSE 解析卡顿 | 用 `TextDecoder` 流式解码，按 `\n\n` 切分（已实现） |
| Sources 面板渲染慢 | 限制预览文本长度 200 字符（已实现） |
| Tab 切换重渲染 | 用 `innerHTML` 全量重绘（已实现），避免 React 重框架开销 |

---

## 6 · 扩展点

### 6.1 接入新 Embedding 模型

修改 `config.py`：
```python
EMBEDDING_PROVIDER = "huggingface"  # 或 "ollama"
BGE_EMBED_MODEL = "新模型路径"
```

或在 `rag_engine.py` 的 `HuggingFaceBGEEmbedding` 类里换模型。

### 6.2 接入新 LLM

修改 `config.py`：
```python
LLM_PROVIDER = "ollama"  # 或 "openai"（需自行实现 wrapper）
LLM_MODEL = "qwen2.5:7b"
OLLAMA_BASE_URL = "http://localhost:11434"
```

### 6.3 接入新 Reranker

`rag_engine.py` 的 `CrossEncoderReranker` 类可替换为 `BGEReranker`（FlagEmbedding）或自训练模型。

### 6.4 接入新文档格式

在 `rag_engine.py` 添加新的 Loader 类（继承 `BaseLoader`），并在 `get_loader()` 注册：
```python
def get_loader(file_path: str) -> BaseLoader:
    if file_path.endswith(".epub"): return EPubLoader(file_path)
    ...
```

### 6.5 接入新前端

`web_api.py` 的 RESTful 设计可对接任意前端（React/Vue/原生）。SSE 端点兼容所有支持 `fetch().body.getReader()` 的现代浏览器。

---

## 7 · 安全与隐私

- **离线运行**：默认 0 网络请求（HF_HUB_OFFLINE=1）
- **数据本地**：所有数据（向量库、聊天、收藏、标签）都存本地 JSON/二进制文件
- **LLM 本地**：Ollama 跑在 localhost:11434，文档不外发
- **可选 API Key**：若改用 OpenAI/智谱等云端 LLM，密钥从 `~/.config/env` 读取（不入 git）

---

## 8 · 已知限制

| 项 | 说明 |
|:---|:---|
| FAISS 单机 | 不支持分布式（可换 Milvus/Qdrant） |
| JSON 存储 | 10w+ 收藏/会话后读写会变慢（可换 SQLite） |
| 大文件分片 | 单文件 > 100MB 时分片较慢（可用 asyncio 优化） |
| 中文 Rerank | bge-reranker-base 英文友好，中文可换 BAAI/bge-reranker-large 或 qwen-rerank |

---

## 9 · 演进路线

| 版本 | 计划 |
|:---|:---|
| v4.3 | React/Vue 前端框架；SQLite 替代 JSON 存储 |
| v4.4 | 多用户隔离（基于 user_id 的标签/会话/收藏隔离） |
| v4.5 | WebSocket 替代 SSE（支持双向通信） |
| v5.0 | 拆分为前端 / 后端 / 算法 3 个独立服务；引入 Milvus 向量库 |
