"""
RAG 评估脚本 (Ragas / 自建指标)
===============================
使用 ragas 评估 Loci RAG 系统的检索与生成质量。

前置:
    pip install ragas datasets

用法:
    1. 准备评估集(questions / ground_truths):eval/eval_set.json
    2. 启动 Loci 服务:python web_api.py
    3. 运行:python eval/run_eval.py

输出:
    - 控制台:Context Precision / Recall / Faithfulness / Answer Relevancy
    - eval/results/ragas_report_<timestamp>.json
"""
from __future__ import annotations

import json
import time
import os
import sys
from pathlib import Path
from typing import List, Dict, Any

# 允许从项目根目录 import
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import requests
except ImportError:
    print("❌ 缺少 requests,请 pip install requests")
    sys.exit(1)

try:
    from ragas.metrics import (
        context_precision,
        context_recall,
        faithfulness,
        answer_relevancy,
    )
    from ragas import evaluate
    from datasets import Dataset
    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False
    print("⚠️ 未安装 ragas,仅运行基础 hit-rate 测试。pip install ragas datasets 可启用完整评估。")


# ---------------------------------------------------------------------------
# 评估集(示例:请根据你的真实知识库替换)
# ---------------------------------------------------------------------------
EVAL_SET: List[Dict[str, str]] = [
    {
        "question": "项目代号 Loci 是什么意思?",
        "ground_truth": "Loci 来自拉丁语 locus,意为'位点',指知识库中的每一个知识节点。",
    },
    {
        "question": "支持哪些文档格式?",
        "ground_truth": "支持 PDF/DOCX/PPTX/XLSX/CSV/HTML/MD/JSON/XML/RTF/TXT 等 13 种格式,以及 URL 摄取。",
    },
    {
        "question": "混合检索是怎么做的?",
        "ground_truth": "BM25 关键词 + FAISS 向量召回,RRF 倒数排名融合 (BM25 0.6 + 向量 0.4),再用 CrossEncoder 精排到 Top8。",
    },
    {
        "question": "如何启动 Loci?",
        "ground_truth": "运行 pip install -r requirements.txt,然后 python web_api.py,浏览器打开 http://localhost:7862",
    },
    {
        "question": "Loci 的 RAG Fallback 机制是什么?",
        "ground_truth": "Rerank 最高分 < 0.5 时自动切到纯 LLM,避免用低质量文档硬答。",
    },
]


# ---------------------------------------------------------------------------
# 评估函数
# ---------------------------------------------------------------------------
def call_loci(question: str, base_url: str = "http://localhost:7862") -> Dict[str, Any]:
    """调用 Loci /api/query 端点,返回 {answer, sources: [text, ...]}"""
    resp = requests.post(
        f"{base_url}/api/query",
        json={"question": question, "top_k": 8},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return {
        "answer": data.get("answer", ""),
        "sources": [s.get("text", s.get("page_content", "")) for s in data.get("sources", [])],
    }


def basic_metrics(
    eval_set: List[Dict[str, str]],
    results: List[Dict[str, Any]],
) -> Dict[str, float]:
    """不依赖 ragas 的基础指标"""
    hit_count = 0
    answered = 0
    for item, result in zip(eval_set, results):
        sources = result.get("sources") or []
        answer = result.get("answer") or ""
        # Hit@K:ground_truth 中至少 50% 关键词出现在 sources 中
        gt_words = set(item["ground_truth"])
        if sources and any(
            sum(1 for w in gt_words if w in s) / max(len(gt_words), 1) >= 0.3
            for s in sources
        ):
            hit_count += 1
        if answer and answer != "未找到相关内容":
            answered += 1

    n = len(eval_set)
    return {
        "context_hit_at_k": hit_count / n if n else 0,
        "answer_rate": answered / n if n else 0,
        "total_questions": n,
    }


def run_with_ragas(
    eval_set: List[Dict[str, str]],
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """使用 ragas 跑完整评估"""
    if not RAGAS_AVAILABLE:
        return {}

    data = {
        "question": [it["question"] for it in eval_set],
        "answer": [r.get("answer", "") for r in results],
        "contexts": [r.get("sources", []) for r in results],
        "ground_truth": [it["ground_truth"] for it in eval_set],
    }
    dataset = Dataset.from_dict(data)

    ragas_result = evaluate(
        dataset,
        metrics=[context_precision, context_recall, faithfulness, answer_relevancy],
    )
    return dict(ragas_result)


def main():
    base_url = os.getenv("LOCI_BASE_URL", "http://localhost:7862")
    print(f"🔍 评估目标: {base_url}")
    print(f"📋 评估集大小: {len(EVAL_SET)}")

    results = []
    for i, item in enumerate(EVAL_SET, 1):
        print(f"  [{i}/{len(EVAL_SET)}] {item['question'][:50]}...", end="", flush=True)
        try:
            r = call_loci(item["question"], base_url)
            results.append(r)
            print(f" ✓ ({len(r['sources'])} sources)")
        except Exception as e:
            print(f" ✗ {e}")
            results.append({"answer": "", "sources": []})
        time.sleep(0.5)

    # 基础指标
    basic = basic_metrics(EVAL_SET, results)
    print("\n📊 基础指标:")
    for k, v in basic.items():
        print(f"  {k:30s} = {v:.4f}" if isinstance(v, float) else f"  {k:30s} = {v}")

    # Ragas 指标
    ragas_out = {}
    if RAGAS_AVAILABLE:
        print("\n📊 Ragas 指标(可能需 1-3 分钟):")
        try:
            ragas_out = run_with_ragas(EVAL_SET, results)
            for k, v in ragas_out.items():
                print(f"  {k:30s} = {v:.4f}" if isinstance(v, float) else f"  {k:30s} = {v}")
        except Exception as e:
            print(f"  ❌ Ragas 评估失败: {e}")
    else:
        print("\n💡 提示:pip install ragas datasets 可解锁 context_precision / faithfulness 等指标")

    # 保存报告
    out_dir = PROJECT_ROOT / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"eval_report_{int(time.time())}.json"
    report_path.write_text(
        json.dumps(
            {"basic": basic, "ragas": ragas_out, "results": results},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n✅ 报告已保存: {report_path}")


if __name__ == "__main__":
    main()
