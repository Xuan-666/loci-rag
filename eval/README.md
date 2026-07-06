"""
RAG 评估
========

本目录提供 Loci RAG 系统的离线评估脚本。

## 快速开始

```bash
# 1. 安装依赖(可选,无 ragas 也能跑基础指标)
pip install requests datasets ragas

# 2. 启动 Loci
python web_api.py &

# 3. 运行评估
python eval/run_eval.py
```

## 评估集

默认 `EVAL_SET` 在 `run_eval.py` 顶部,包含 5 个示例问题。
真实使用时请替换为你自己知识库相关的问题,并提供 ground_truth。

## 评估指标

### 基础指标(不需要 LLM-as-judge)

- **Context Hit@K**: 正确答案是否出现在 Top-K sources 中
- **Answer Rate**: 系统是否产生了有效答案(非"未找到相关内容")

### Ragas 指标(需要 OpenAI API Key,作为 LLM-as-judge)

- **Context Precision**: 检索结果的精确率(噪音越少分越高)
- **Context Recall**: 检索结果的召回率(覆盖 ground_truth 的比例)
- **Faithfulness**: 答案是否忠于 context(无幻觉)
- **Answer Relevancy**: 答案与问题的相关度

## 报告输出

报告保存在 `eval/results/eval_report_<timestamp>.json`,包含:

- `basic`: 基础指标
- `ragas`: Ragas 指标(若启用)
- `results`: 每个问题的详细 sources/answer

## 进阶:自定义评估集

把你的评估集放进 `eval/eval_set.json`:

```json
[
  {
    "question": "...",
    "ground_truth": "..."
  },
  ...
]
```

然后修改 `run_eval.py` 读取这个文件。
