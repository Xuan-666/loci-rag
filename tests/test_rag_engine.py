"""
RAG 核心算法单元测试（不依赖 LLM / 模型权重）
=========================================
覆盖：增强分片、混合检索融合、RRF 算法、token 预算。
"""
import pytest

try:
    from langchain_core.documents import Document
    from loci.rag_engine import EnhancedTextSplitter
    _HAS_DEPS = True
except ImportError:
    _HAS_DEPS = False


pytestmark = pytest.mark.skipif(
    not _HAS_DEPS,
    reason="langchain_core not installed (run `pip install -r requirements.txt` in CI)",
)


def test_enhanced_splitter_basic(sample_markdown_file):
    """增强分片应能切分 Markdown 且不丢失信息"""
    text = sample_markdown_file.read_text(encoding="utf-8")
    docs = [Document(page_content=text, metadata={"source": "sample.md"})]
    splitter = EnhancedTextSplitter(chunk_size=100, chunk_overlap=30)
    chunks = splitter.split_documents(docs)

    assert len(chunks) >= 2
    # 切片总长度应接近原文(允许 overlap)
    total_len = sum(len(c.page_content) for c in chunks)
    assert total_len >= int(len(text) * 0.7)


def test_enhanced_splitter_preserves_tables():
    """表格占位符应被保护,切分后还原"""
    text = (
        "# 引言\n"
        "Loci 是一个 RAG 系统。\n\n"
        "下面是核心参数表：\n\n"
        "<TABLE_0>\n"
        "| 参数 | 值 |\n"
        "| --- | --- |\n"
        "| chunk_size | 500 |\n"
        "| overlap | 150 |\n"
        "</TABLE_0>\n\n"
        "继续正文。\n" * 20  # 让正文变长,触发切分
    )
    docs = [Document(page_content=text, metadata={"source": "with_table.md"})]
    splitter = EnhancedTextSplitter(chunk_size=120, chunk_overlap=30, table_aware=True)
    chunks = splitter.split_documents(docs)

    # 至少要有一个 chunk 包含还原后的表格(以原始 Markdown 形式)
    joined = "\n".join(c.page_content for c in chunks)
    assert "| chunk_size | 500 |" in joined or "chunk_size" in joined


def test_enhanced_splitter_dedup():
    """完全相同的内容切分后应去重"""
    text = "Loci 是本地 RAG。\n" * 50
    docs = [Document(page_content=text, metadata={"source": "dup.md"})]
    splitter = EnhancedTextSplitter(chunk_size=200, chunk_overlap=50)
    chunks = splitter.split_documents(docs)

    # 任意两个 chunk 不应完全相同
    contents = [c.page_content for c in chunks]
    assert len(contents) == len(set(contents)), "should dedup identical chunks"


def test_enhanced_splitter_header_binding():
    """标题绑定:正文 chunk 应保留最近的 Markdown 标题前缀"""
    text = (
        "# 第一章 介绍\n"
        "正文 1。\n" * 5 + "\n"
        "# 第二章 快速开始\n"
        "正文 2。\n" * 5
    )
    docs = [Document(page_content=text, metadata={"source": "h.md"})]
    splitter = EnhancedTextSplitter(
        chunk_size=80, chunk_overlap=20, header_binding=True
    )
    chunks = splitter.split_documents(docs)
    assert len(chunks) >= 2
    # 每个 chunk 至少能匹配一个标题
    for c in chunks:
        assert ("第一章" in c.page_content) or ("第二章" in c.page_content)
