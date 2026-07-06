"""
配置文件 v4.2 — 双模式Embedding + 混合检索 + Rerank + 增强分片 + Fallback
=========================================================================

改进点（对照实验3教学标准）：
  - 双模式 Embedding: bge-small-zh（HuggingFace）/ nomic-embed-text（Ollama）可切换
  - 新增 BM25 + 向量混合检索 + RRF 融合
  - 新增 CrossEncoder Rerank 精排
  - 升级分片策略：标题绑定、表格保护、增大 overlap
  - 新增 jin-document-parser 统一 Markdown 输出
  - v4.1: RAG fallback 到纯 LLM（精排分数过低时）

API 密钥从 ~/.config/env 读取，不会写入项目文件。
"""

# ⚠️ 必须在所有其他 import 之前设置，禁止 huggingface_hub 联网
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"

from pathlib import Path


# ==================== API 密钥加载（不暴露到项目文件） ====================
def _load_env() -> dict:
    """从 ~/.config/env 加载 API 密钥，仅内存中使用"""
    env_file = os.path.expanduser("~/.config/env")
    if not os.path.exists(env_file):
        return {}

    env = {}
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if value:
                    env[key] = value
    return env


_env = _load_env()

# ==================== Embedding 配置（双模式可切换） ====================
# "huggingface": BAAI/bge-small-zh-v1.5 — 中文语义最优，需首次下载 ~400MB
# "ollama":      nomic-embed-text — Ollama 本地，无需额外下载
EMBEDDING_PROVIDER = "huggingface"  # bge-small-zh 已通过 ModelScope 下载

# HuggingFace Embedding 配置
BGE_EMBED_MODEL = os.path.expanduser("~/.cache/huggingface/BAAI/bge-small-zh-v1.5")
# 国内可设置 HF_ENDPOINT=https://hf-mirror.com 加速下载
HF_ENDPOINT = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")

# Ollama Embedding 配置（当 EMBEDDING_PROVIDER="ollama" 时使用）
OLLAMA_EMBED_MODEL = "nomic-embed-text"

# ==================== LLM 配置 ====================
# LLM_PROVIDER 可选值:
#   - "ollama"  (默认): 本地 Ollama 推理,无需 API Key
#   - "openai"          : OpenAI 兼容 API(OpenAI / 通义千问 / 智谱 GLM / DeepSeek / 月之暗面)
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-r1:7b")

_ollama_url = _env.get("OLLAMA_BASE_URL", "http://localhost:11434")
if _ollama_url.endswith("/v1"):
    _ollama_url = _ollama_url[:-3]  # 去掉 OpenAI 兼容后缀
OLLAMA_BASE_URL = _ollama_url

# OpenAI 兼容配置(LLM_PROVIDER="openai" 时使用)
OPENAI_API_KEY = _env.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = _env.get("OPENAI_BASE_URL", "https://api.openai.com/v1")  # 国内可指向通义/智谱的兼容端点
OPENAI_MODEL = _env.get("OPENAI_MODEL", "gpt-4o-mini")

# ==================== Rerank 重排序配置 ====================
# 依据: BGE-Rerank 是 Cross-Encoder，输出未归一化对数几率 (logit)
#       高相关 3.0~10.0 / 中等相关 0.0~3.0 / 负数表示不相关
# 社区常见实践: RERANK_INITIAL_K 取 30-50（粗排多给候选），RERANK_FINAL_K 取 5-8（精排保留）
RERANK_ENABLED = True      # bge-reranker-base 已通过 ModelScope 下载
RERANK_MODEL = os.path.expanduser("~/.cache/huggingface/BAAI/bge-reranker-base")
RERANK_INITIAL_K = 40      # 粗排召回数量（送进 Rerank 打分）—— 30 略保守，提升到 40 拉高召回
RERANK_FINAL_K = 8         # 精排后保留数量（送给 LLM）—— 8 兼顾上下文丰富度与 LLM 注意力
# BGE Rerank 经 sentence-transformers CrossEncoder.predict() 默认 sigmoid 激活后，输出 0~1 概率
# 0.5 是 BGE 官方建议的"相关"分界线；0.5~1.0 强相关，0.3~0.5 弱相关，<0.3 通常不相关
RERANK_SCORE_THRESHOLD = 0.3  # 单文档最低分过滤线（双保险）
# 注：rag_engine.py 使用 RAG_FALLBACK_THRESHOLD 作为"最高分 < 阈值 → 启用 LLM fallback" 的判定线

# ==================== BM25 混合检索配置 ====================
# 依据: 中文场景下 BM25 关键词命中比纯向量更精准（专有名词/编号/年份等）
#       但向量检索有更好的语义泛化能力。0.6/0.4 偏向关键词，适配「带具体数据/编号」类问题
BM25_ENABLED = True
VECTOR_WEIGHT = 0.4         # 向量检索在 RRF 融合中的权重
BM25_WEIGHT = 0.6           # BM25 关键词检索在 RRF 融合中的权重
RETRIEVAL_INITIAL_K = 50    # 各自粗排召回数量，50 给 RRF 融合更多素材

# ==================== 检索通用参数 ====================
TOP_K = 5                   # (保留) 默认最终返回给 LLM 的文档块数量，当前由 RERANK_FINAL_K 覆盖
SCORE_THRESHOLD = 0.3       # (保留) FAISS 相似度阈值，当前由 RRF 融合机制代替

# ==================== 文档分片配置 ====================
CHUNK_STRATEGY = "enhanced"   # "enhanced" 增强分片 / "basic" 基础分片
CHUNK_SIZE = 500              # 文本块大小（字符数）
CHUNK_OVERLAP = 150           # 重叠大小（增强模式约 30% overlap）

# 增强分片特性开关
TABLE_AWARE = True            # 表格保护（占位符 → 切分 → 还原 → 去重）
HEADER_BINDING = True         # Markdown 标题向下合并（标题 + 正文不分离）

MAX_FILE_SIZE_MB = 50         # 单文件最大限制（MB）

# ==================== PDF 解析器选择 ====================
# "jin-doc-parser": 统一输出 Markdown（表格保留好，推荐；需 jin-document-parser）
# "pypdf":          逐页提取原文本（当前默认，无额外依赖）
PDF_PARSER = "jin-doc-parser"

# ==================== 路径配置 ====================
VECTOR_STORE_PATH = "./data/vector_store"
UPLOADED_DOCS_PATH = "./data/uploaded_docs"

# 运行时数据路径（v5.0 重构：统一到 data/ 目录）
CHAT_HISTORY_PATH = "./data/chat_history.json"
TAGS_PATH = "./data/tags.json"
FAVORITES_PATH = "./data/favorites.json"
USER_SETTINGS_PATH = "./data/user_settings.json"

# ==================== Prompt 模板 ====================
RAG_SYSTEM_PROMPT = """你是一个严格基于文档的问答助手。**你必须仅使用下面提供的参考文档内容来回答问题**，不要使用任何外部知识，不要编造任何信息。

【强制规则】
1. 只根据 {context} 中的信息回答，如果该信息确实不存在，说"参考文档中没有相关内容，无法回答"
2. 绝不要在你的回答中混入 context 之外的知识或常识
3. 如果 context 中有多个来源，用编号 [来源1] [来源2] 明确标注每条信息的出处
4. 回答要简洁、准确，用中文回答
5. 如果用户问题与 context 完全无关，仍只能回答"参考文档中没有相关内容"

【格式要求】
- 用自然段落回答，不要列表（除非用户明确要求）
- 关键数值、专有名词务必引用来源
- 不确定的内容，宁可不答也不要编造

参考文档内容：
{context}
"""

# ==================== 文件格式配置 ====================
SUPPORTED_EXTENSIONS = [
    ".pdf",
    ".docx", ".doc",
    ".txt", ".md",
    ".xlsx", ".xls",
    ".pptx", ".ppt",
    ".html", ".htm",
    ".json", ".xml",
    ".csv",
    ".rtf",
]

# ==================== 界面配置 ====================
APP_TITLE = "📚 本地知识库问答助手"
APP_DESCRIPTION = "支持多格式文档上传、智能问答 | 💾 完全本地化 | 🚀 混合检索+Rerank增强 | ✨ v4.0 多轮+流式+标签+全文+URL+版本"

# ==================== v4.0 新增配置 ====================
# 多轮对话历史
MAX_HISTORY_TURNS = 5       # 注入 prompt 的最大历史轮数
MAX_HISTORY_CHARS = 1500    # 历史文本最大总字符数

# 向量库版本管理
VERSION_ENABLED = True              # 是否启用版本快照/回滚
VERSION_KEEP_LAST = 10              # 自动清理时保留的最近版本数

# 文件夹监控
WATCHDOG_ENABLED = False            # 启动时是否自动开启监控（生产可设 True）
WATCHDOG_DEBOUNCE = 2.0             # 防抖秒数


# ==================== RAG Fallback 配置（v4.1） ====================
# 当知识库检索为空或精排分数过低时，是否回退到纯 LLM 回答
RAG_FALLBACK_ENABLED = True          # 是否启用 fallback
# 精排最高分低于此值时，启用 LLM fallback 而非用低质量文档作答
# 0.5 是 BGE 官方建议的「相关」分界线（sigmoid 后概率）
# 实测: BGE 对「不相关内容」常给 0.4~0.5，阈值 0.3 容易被低质量匹配"逃过"
#       0.5 能有效拦截「勉强相关」但「答非所问」的情况
RAG_FALLBACK_THRESHOLD = 0.5         # 0~1 概率阈值（v4.3 修复: 之前未真正生效）
RAG_FALLBACK_PROMPT = """你是一个专业的AI助手。请直接回答用户的问题，不需要参考外部文档。

问题：{question}
"""


# ==================== 启动诊断 ====================
def diagnose():
    """启动时检查关键组件状态，输出友好的配置报告"""
    issues = []

    # 检查 Embedding 模型
    if EMBEDDING_PROVIDER == "huggingface":
        if not os.path.exists(BGE_EMBED_MODEL):
            issues.append(
                f"⚠️ BGE Embedding 模型未找到: {BGE_EMBED_MODEL}\n"
                f"   请先下载: modelscope download --model BAAI/bge-small-zh-v1.5"
            )

    # 检查 Rerank 模型
    if RERANK_ENABLED:
        if not os.path.exists(RERANK_MODEL):
            issues.append(
                f"⚠️ Rerank 模型未找到: {RERANK_MODEL}\n"
                f"   Rerank 将自动禁用，不影响基础问答"
            )
            # 不会自动修改全局变量，仅在 RAGEngine 初始化时通过异常处理降级

    # 检查 jieba
    try:
        import jieba
    except ImportError:
        issues.append("⚠️ jieba 未安装，BM25 混合检索将无法使用")

    if issues:
        print("\n[Config] === 配置诊断 ===")
        for issue in issues:
            print(issue)
        print("[Config] === 诊断完成 ===\n")

    return issues


# 导入时自动运行诊断
diagnose()
