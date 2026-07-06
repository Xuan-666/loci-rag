"""
共享测试 fixtures 与配置
"""
import sys
import os
import pytest
import tempfile
import shutil
from pathlib import Path

# 把项目根目录加入 sys.path,让 `from loci.xxx import ...` 能工作
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def tmp_data_dir():
    """为每个测试创建一个隔离的临时 data/ 目录"""
    tmpdir = Path(tempfile.mkdtemp(prefix="loci_test_"))
    yield tmpdir
    # 清理
    if tmpdir.exists():
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def sample_text_file(tmp_data_dir):
    """创建一个简单的文本文件供分片/解析测试"""
    p = tmp_data_dir / "sample.txt"
    p.write_text(
        "Loci 是一个本地知识库 RAG 问答系统。\n"
        "支持 BM25 + 向量混合检索。\n"
        "支持 CrossEncoder 精排。\n"
        "支持 SSE 流式输出。\n"
        "支持 15 种文档格式。\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def sample_markdown_file(tmp_data_dir):
    """创建一个带标题的 Markdown 文件,用于测试增强分片"""
    p = tmp_data_dir / "sample.md"
    p.write_text(
        "# 第一章 Loci 介绍\n"
        "Loci 是一个本地知识库 RAG 问答系统,代号来自拉丁语 locus,意为'位点'。\n\n"
        "## 1.1 核心能力\n"
        "支持 BM25 + 向量混合检索,支持 CrossEncoder 精排。\n\n"
        "## 1.2 设计哲学\n"
        "本地、私密、可版本管理。\n\n"
        "# 第二章 快速开始\n"
        "运行 `python web_api.py` 即可启动 Web 服务。\n",
        encoding="utf-8",
    )
    return p
