# HTTP API 参考 v5.1

> 给前端开发者 / 集成方看的 HTTP 接口文档。
> Base URL: `http://localhost:7862`
> 编码：所有 JSON 使用 UTF-8。

---

## 0 · 通用约定

### 0.1 响应格式

**JSON 端点：**
```json
{
  "...": "..."
}
```

**错误响应：**
```json
{ "error": "错误信息" }
```
HTTP 状态码：`400` 客户端错误 / `500` 服务端错误

### 0.2 SSE 端点（`/api/query/stream`）

Content-Type: `text/event-stream`
格式：`data: {json}\n\n`（注意双换行）

事件类型：
- `sources` — 携带来源列表
- `token`   — 单个答案片段
- `done`    — 流结束
- `error`   — 错误

### 0.3 路径命名

所有 API 前缀 `/api/`，RESTful 风格：
- `GET`    — 读取
- `POST`   — 创建 / 触发
- `DELETE` — 删除

---

## 1 · 健康检查

### `GET /api/health`

健康检查。

**Response 200：**
```json
{ "status": "ok", "ts": 1749630000.123 }
```

---

## 2 · 引擎状态

### `GET /api/engine_status`

读取当前引擎配置（设置页 + 顶栏使用）。

**Response 200：**
```json
{
  "embedding_provider": "huggingface",
  "embedding_model": "BAAI/bge-small-zh-v1.5",
  "llm_model": "deepseek-r1:7b",
  "ollama_base_url": "http://localhost:11434",
  "bm25_enabled": true,
  "bm25_weight": 0.3,
  "vector_weight": 0.7,
  "rerank_enabled": true,
  "rerank_initial_k": 10,
  "rerank_final_k": 5,
  "rerank_score_threshold": 0.3,
  "chunk_strategy": "enhanced",
  "chunk_size": 500,
  "chunk_overlap": 150,
  "version_enabled": true,
  "rag_fallback_enabled": true,
  "rag_fallback_threshold": 0.3
}
```

---

## 3 · 知识库

### `GET /api/knowledge_base`

文档列表（带标签）。

**Response 200：**
```json
{
  "documents": [
    { "name": "中山大学2025年招生简章.pdf", "tags": ["招生", "2025"] },
    { "name": "PVQC专业英语词汇.md", "tags": ["英语", "词汇"] }
  ]
}
```

### `GET /api/knowledge_base/stats`

知识库统计。

**Response 200：**
```json
{
  "num_docs": 10,
  "num_chunks": 150,
  "vector_store_size_mb": 12.34,
  "versions": { "total": 3, "size_mb": 36.5 }
}
```

### `POST /api/knowledge_base/upload`

上传文档（multipart/form-data）。

**Request：**
```
POST /api/knowledge_base/upload
Content-Type: multipart/form-data
files[] = @file1.pdf
files[] = @file2.docx
```

**Response 200：**
```json
{
  "uploaded": ["file1.pdf", "file2.docx"],
  "chunks": 87
}
```

**Response 400：**
```json
{ "error": "没有文件" }
```

### `POST /api/knowledge_base/rebuild`

重建索引（扫描 `uploaded_docs/` 全部文件）。

**Response 200：**
```json
{
  "loaded_chunks": 150,
  "files": ["file1.pdf", "file2.docx", ...]
}
```

### `DELETE /api/knowledge_base/documents/<name>`

删除文档。

**Response 200：**
```json
{ "deleted": "中山大学2025年招生简章.pdf" }
```

---

## 4 · 标签

### `GET /api/tags`

列出所有标签。

**Response 200：**
```json
{
  "tags": [
    { "name": "招生", "color": "#3B82F6" },
    { "name": "2025", "color": "#10B981" }
  ]
}
```

### `POST /api/tags`

创建标签。

**Request：**
```json
{ "name": "英语", "color": "#F59E0B" }
```

**Response 200：**
```json
{ "name": "英语", "color": "#F59E0B" }
```

**Response 400：**
```json
{ "error": "name 必填" }
```

### `DELETE /api/tags/<name>`

删除标签。

**Response 200：**
```json
{ "deleted": "英语" }
```

### `POST /api/knowledge_base/documents/<name>/tags`

给文档加标签。

**Request：**
```json
{ "tag": "英语" }
```

**Response 200：**
```json
{ "name": "PVQC专业英语词汇.md", "tag": "英语" }
```

### `DELETE /api/knowledge_base/documents/<name>/tags/<tag>`

移除文档标签。

**Response 200：**
```json
{ "name": "PVQC专业英语词汇.md", "tag": "英语" }
```

---

## 5 · 问答（SSE 流式）

### `POST /api/query/stream`

SSE 流式问答（**核心端点**）。

**Request：**
```json
{
  "question": "中山大学2025年计算机学硕考什么科目？",
  "session_id": "uuid-可选-不传则自动创建",
  "history": [["user_q", "assistant_a"]],
  "tag_filter": ["招生"]
}
```

| 字段 | 类型 | 必填 | 说明 |
|:---|:---|:---|:---|
| `question` | string | ✅ | 用户问题 |
| `session_id` | string | ❌ | 会话 ID，不传则自动创建 |
| `history` | array | ❌ | 多轮历史，格式 `[[user, assistant], ...]` |
| `tag_filter` | array | ❌ | 标签过滤（AND 语义） |

**Response（SSE 事件流）：**

```
data: {"type":"sources","sources":[{"source":"中山大学2025年招生简章.pdf","page":12,"score":0.745,"preview":"..."}],"fallback":false,"session_id":"abc-123"}

data: {"type":"token","content":"中山"}

data: {"type":"token","content":"大学"}

data: {"type":"token","content":"2025"}

...

data: {"type":"done","session_id":"abc-123","auto_created":true}
```

**SSE 事件详细说明：**

| 事件 | 字段 | 含义 |
|:---|:---|:---|
| `sources` | `sources: [{source, page, score, preview}]` | 来源列表（先发送，让 UI 立即展示） |
| `sources` | `fallback: bool` | 是否为 fallback 模式（无 KB 上下文） |
| `sources` | `session_id: str` | 当前会话 ID |
| `token` | `content: str` | 单个答案片段（多个 token 累加 = 完整答案） |
| `done` | `session_id: str` | 当前会话 ID（用于更新前端） |
| `done` | `auto_created: bool` | 本次是否自动创建了会话 |
| `error` | `content: str` | 错误信息 |

**前端解析示例（JS）：**
```js
const resp = await fetch('/api/query/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ question, history, tag_filter })
});

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
      // payload.type: 'sources' | 'token' | 'done' | 'error'
      handleEvent(payload);
    }
  }
}
```

---

## 6 · 聊天会话

### `GET /api/chat/sessions`

列出所有会话。

**Response 200：**
```json
{
  "sessions": [
    { "session_id": "abc-123", "title": "中山大学考研咨询", "updated_at": "2026-06-11 14:30:00", "message_count": 4 }
  ]
}
```

### `POST /api/chat/sessions`

创建会话。

**Request：**
```json
{ "title": "我的新会话" }
```

**Response 200：**
```json
{ "session_id": "abc-123" }
```

### `GET /api/chat/sessions/<id>`

读取单会话详情（含消息）。

**Response 200：**
```json
{
  "session": { "session_id": "abc-123", "title": "...", "updated_at": "..." },
  "messages": [
    { "role": "user", "content": "...", "timestamp": "..." },
    { "role": "assistant", "content": "...", "timestamp": "..." }
  ]
}
```

### `DELETE /api/chat/sessions/<id>`

删除会话。

**Response 200：**
```json
{ "deleted": "abc-123" }
```

---

## 7 · 收藏

### `GET /api/favorites`

列出所有收藏（最新在前）。

**Response 200：**
```json
{
  "favorites": [
    {
      "id": "uuid-1",
      "question": "中山大学2025年计算机学硕考什么科目？",
      "answer": "...",
      "sources": [{ "source": "...", "page": 12, "score": 0.745 }],
      "created_at": "2026-06-11 14:30:00"
    }
  ]
}
```

### `POST /api/favorites`

新增收藏。

**Request：**
```json
{
  "question": "中山大学2025年计算机学硕考什么科目？",
  "answer": "政治、英语一、数学一、计算机学科专业基础...",
  "sources": [{ "source": "...", "page": 12, "score": 0.745 }]
}
```

**Response 200：**
```json
{
  "id": "uuid-1",
  "question": "...",
  "answer": "...",
  "sources": [...],
  "created_at": "2026-06-11 14:30:00"
}
```

**Response 400：**
```json
{ "error": "question 必填且必须为字符串" }
```

### `DELETE /api/favorites/<id>`

删除收藏。

**Response 200：**
```json
{ "deleted": "uuid-1" }
```

---

## 8 · 错误码总览

| HTTP Code | 含义 | 常见原因 |
|:---|:---|:---|
| 200 | OK | 成功 |
| 400 | Bad Request | 参数缺失 / 文件不存在 / 字段格式错误 |
| 404 | Not Found | 路由不存在 / 会话 ID 不存在 |
| 500 | Internal Error | 向量库损坏 / LLM 调用失败 / 文件写入失败 |

---

## 9 · 调用示例（curl）

### 健康检查
```bash
curl http://localhost:7862/api/health
```

### 引擎状态
```bash
curl http://localhost:7862/api/engine_status
```

### 上传文档
```bash
curl -F "files=@test.pdf" -F "files=@test.docx" http://localhost:7862/api/knowledge_base/upload
```

### 删除文档
```bash
curl -X DELETE "http://localhost:7862/api/knowledge_base/documents/test.pdf"
```

### 标签管理
```bash
# 创建
curl -X POST http://localhost:7862/api/tags -H "Content-Type: application/json" -d '{"name":"英语","color":"#F59E0B"}'

# 列表
curl http://localhost:7862/api/tags

# 删除
curl -X DELETE http://localhost:7862/api/tags/英语
```

### 收藏
```bash
# 新增
curl -X POST http://localhost:7862/api/favorites -H "Content-Type: application/json" \
  -d '{"question":"Q","answer":"A","sources":[]}'

# 列表
curl http://localhost:7862/api/favorites

# 删除
curl -X DELETE http://localhost:7862/api/favorites/<id>
```

### 流式问答（curl）
```bash
curl -N -X POST http://localhost:7862/api/query/stream \
  -H "Content-Type: application/json" \
  -d '{"question":"中山大学2025年计算机学硕考什么科目？"}'
```
（`-N` 禁用缓冲，可看到实时流）

---

## 10 · 调用示例（Python）

```python
import requests

# 1. 上传文档
with open("test.pdf", "rb") as f:
    r = requests.post(
        "http://localhost:7862/api/knowledge_base/upload",
        files={"files": f}
    )
print(r.json())

# 2. 流式问答
with requests.post(
    "http://localhost:7862/api/query/stream",
    json={"question": "PVQC 单词表里 polymorphism 怎么翻译？"},
    stream=True
) as r:
    for line in r.iter_lines():
        if line:
            decoded = line.decode('utf-8')
            if decoded.startswith('data: '):
                import json
                payload = json.loads(decoded[6:])
                if payload['type'] == 'token':
                    print(payload['content'], end='', flush=True)

# 3. 收藏问答
r = requests.post(
    "http://localhost:7862/api/favorites",
    json={"question": "Q", "answer": "A"}
)
print(r.json())
```

---

## 11 · CORS

所有 `/api/*` 端点启用 CORS（`Access-Control-Allow-Origin: *`）。
前端可从任意域名调用（生产环境建议加上白名单）。
