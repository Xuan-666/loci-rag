# 用户手册 v5.1

> 给最终用户的 5 Tab 详细使用说明。
> 看完就会用，能解决 95% 的日常问题。

---

## 0 · 启动 & 访问

```powershell
cd "本地知识库RAG问答系统 - 副本"
$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'
python web_api.py
```

启动后看到：
```
============================================================
  Loci · 本地知识库 RAG 问答系统
  Flask Web API (花叔design B版)
============================================================
  📚 文档: 10 个
  💬 会话: 0 个
  🏷️  标签: 0 个
  ⭐ 收藏: 0 个
============================================================
  🌐 访问: http://localhost:7862
============================================================
```

浏览器打开 **http://localhost:7862** 即可。

---

## 1 · 智能问答 Tab（💬）

### 1.1 首次进入

页面中央是 Hero 区域：
- 标题 `Ask anything from your library.`
- 4 个**快捷提问**（点击即可提问）
- 底部**持久输入框**（位于屏幕下方，不会被对话遮挡）

### 1.2 提问

1. 在底部输入框输入问题
2. 点击 `Ask →` 或按 `Ctrl+Enter`
3. 等待三阶段状态条（Searching → Reading → Writing）走完
4. 答案逐字浮现（流式输出）
5. 右侧 **Sources 面板** 实时显示命中片段 + Rerank 分数

### 1.3 三阶段状态条

| 阶段 | 含义 | 时间 |
|:---|:---|:---|
| 🔍 **Searching** | BM25+向量混合检索中 | 100-500ms |
| 📖 **Reading** | Rerank 精排 + 阈值过滤 | 200-800ms |
| ✍️ **Writing** | LLM 逐 token 生成 | 5-30s（视模型） |

### 1.4 RAG Fallback 模式

当**知识库无答案**或**精排分数过低**时：

- 答案上方出现**黄色提示条**：`🤖 LLM 直接回答`（未使用本地知识库）
- LLM 仍会回答，但**不基于**你的文档
- 此时 Sources 面板为空（因为没有引用）

触发条件（`config.py` 可调）：
```python
RAG_FALLBACK_ENABLED = True
RAG_FALLBACK_THRESHOLD = 0.3
```

### 1.5 答案下方操作按钮

| 按钮 | 作用 |
|:---|:---|
| ⭐ 收藏 | 把当前问答存入「收藏」Tab |
| 📋 复制 | 把答案文字复制到剪贴板 |
| 🔄 重新生成 | 用相同问题重新调用 LLM |
| 👍 / 👎 | 反馈答案质量（v4.3 计划） |

### 1.6 多轮对话

每次提问会自动加入当前会话的历史。最多保留最近 5 轮，超出会被截断。

**新建会话**：点击右上角 `+ 新建会话`（会话 Tab）

---

## 2 · 知识库 Tab（📚）

### 2.1 上传文档

3 种方式：

**方式 1：点击上传**
1. 点击 `选择文件` 按钮
2. 选 1 个或多个文件
3. 等待入库完成（进度条 + Toast 通知）

**方式 2：拖拽上传**
1. 把文件**拖到页面任意位置**
2. 自动切到知识库 Tab
3. 自动开始上传

**方式 3：URL 摄取**
1. 切到「URL 摄取」子 Tab
2. 粘贴网页 URL（支持批量）
3. 点击「摄取」→ 自动用 trafilatura 抽正文 → 入库

### 2.2 支持的文件格式（15 种）

| 类型 | 扩展名 |
|:---|:---|
| PDF | `.pdf` |
| Word | `.docx`, `.doc` |
| Excel | `.xlsx`, `.xls` |
| PowerPoint | `.pptx`, `.ppt` |
| 文本 | `.txt`, `.md`, `.html`, `.htm` |
| 数据 | `.json`, `.xml`, `.csv` |
| RTF | `.rtf` |
| 网页 | 通过 URL 摄取 |

### 2.3 标签管理

**添加标签到文档：**
1. 在文档行右侧 `🏷️` 按钮
2. 输入标签名（已存在的会高亮提示）
3. 回车确认

**筛选文档：** 点击顶部标签芯片，多选即为「AND 语义」

**新建全局标签：** 切到「标签」子 Tab → 点 `+ 新建标签`

### 2.4 全文搜索

切到「全文搜索」子 Tab：
- 输入关键词 → BM25 检索全文
- 命中片段用 `<mark>` 高亮
- 点击片段可跳到对应文档

### 2.5 重建索引

切到「索引管理」子 Tab：
- 点「重建索引」→ 重新扫描 `uploaded_docs/` 全部文件
- 入库前会自动做版本快照（可回滚）
- 适用于：升级代码后、修改了分片参数等场景

---

## 3 · 收藏 Tab（⭐）

### 3.1 收藏内容

每条收藏包含：
- 用户问题
- LLM 回答
- 来源（如果非 fallback）
- 收藏时间

### 3.2 搜索收藏

顶部搜索框 → 实时过滤（按问题/答案文本匹配）

### 3.3 导出收藏

点 `📤 导出 JSON` → 下载 `favorites-YYYYMMDD.json`

### 3.4 删除收藏

点收藏卡右上角 `×` → 二次确认弹窗

---

## 4 · 会话 Tab（🗂️）

### 4.1 会话列表

每条会话显示：
- 会话标题（取自首条问题前 30 字）
- 更新时间
- 对话轮数

### 4.2 新建会话

点 `+ 新建会话` → 切到智能问答 Tab → 提问即可

### 4.3 删除会话

点会话行右侧 `×` → 二次确认弹窗 → 同步清除 `chat_history.json` 里对应数据

---

## 5 · 设置 Tab（⚙️）

### 5.1 引擎状态

显示当前配置（只读）：
- Embedding 模型 + 路径
- LLM 模型 + Ollama 地址
- BM25 / Rerank 权重
- Chunk size / overlap
- Fallback 阈值

### 5.2 主题切换

| 主题 | 效果 |
|:---|:---|
| ☀️ Light | 暖米色背景 + 墨绿 accent（默认） |
| 🌙 Dark | 暗色背景 + 同色系 accent |
| 📚 Sepia | 羊皮纸背景 + 棕色 accent（v4.3 计划） |

切换主题**实时生效**，无需刷新。

### 5.3 危险操作

| 操作 | 作用 |
|:---|:---|
| 🔄 重建索引 | 删除现有 FAISS → 重新扫描 uploaded_docs/ |
| 🧹 清空聊天记录 | 删 `chat_history.json` 全部会话 |
| ⭐ 清空收藏 | 删 `favorites.json` 全部条目 |
| 📦 恢复版本 | 从 `vector_store_versions/` 选一个版本回滚 |

每个操作都有二次确认弹窗。

---

## 6 · 快捷键

| 键位 | 作用 |
|:---|:---|
| `Ctrl+K` | 聚焦底部输入框 |
| `Ctrl+Enter` | 发送问题（输入框聚焦时） |
| `Esc` | 关闭弹窗 |
| `Tab` | 切换 Tab（浏览器默认） |

---

## 7 · 常见问题

### Q1: 启动后 502 / 端口被占用

```powershell
# 找到占用 7862 端口的进程
Get-NetTCPConnection -LocalPort 7862 -ErrorAction SilentlyContinue
# 杀掉
Stop-Process -Id <PID> -Force
```

或修改 `web_api.py` 末尾的 `port=7862`。

### Q2: Ollama 连接失败

确保 Ollama 服务在运行：
```powershell
ollama serve
```

或检查 `config.OLLAMA_BASE_URL` 是否正确（默认 `http://localhost:11434`）。

### Q3: Embedding 模型加载慢 / 失败

首次加载会从 HuggingFace 下载约 100MB 模型。已开启 `HF_HUB_OFFLINE=1`，需要预下载：
```powershell
modelscope download --model BAAI/bge-small-zh-v1.5
```

### Q4: 问答"答非所问"

1. 切到「知识库」Tab → 看下文档是不是入库成功
2. 切到「设置」Tab → 看 Rerank 分数
3. 调小 `RERANK_SCORE_THRESHOLD`（如 0.2）→ 重启
4. 若仍无答案 → 系统会自动 fallback 到 LLM（看黄条提示）

### Q5: 答案生成太慢

- 换更小的模型：`ollama pull qwen2.5:3b` + 修改 `config.LLM_MODEL`
- 调小 `RERANK_FINAL_K`（5 → 3）：上下文缩短，LLM 更快
- 关闭 Rerank：`RERANK_ENABLED = False`（快但精度下降）

### Q6: 收藏数据丢失

收藏存在 `favorites.json`，可手动备份。若文件损坏，下次启动会**自动重建空文件**（不报错）。

### Q7: Windows GBK 编码错误

启动前**务必**设置：
```powershell
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONUTF8='1'
```

或在系统环境变量里永久设置。

### Q8: 怎么完全卸载

1. 删除项目文件夹
2. （可选）删除 Ollama 模型：`ollama rm deepseek-r1:7b`
3. （可选）删除 HuggingFace 缓存：`rm -rf ~/.cache/huggingface`

所有数据都是项目本地，**无任何云端残留**。

---

## 8 · 隐私声明

- 0 网络请求（除首次下载模型）
- 0 API Key
- 0 第三方追踪
- 0 文档外发

你上传的每一份文档、每一条问答、每一个收藏，都**只存在你的电脑里**。
