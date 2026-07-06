# Loci 演示文稿 · 设计规范

> 给本 deck 的 19 页 HTML 幻灯片使用的统一设计 token。
> 严格沿用 Loci 项目的 design system（暖米色 + 墨绿/土陶 accent），确保演示文稿与产品视觉一致。

---

## 1. 尺寸与网格

- **画布**: 1920 × 1080 (16:9，标准 1080p)
- **内边距**: 左右 120px，上下 90px
- **12 栏网格**: 单栏宽 ≈ 130px，栏间距 24px
- **内容区最大宽**: 1680px

## 2. 配色（与项目 custom.css 完全一致）

| 角色 | 颜色 | 用途 |
|---|---|---|
| `--bg` | `#f4f1ea` | 暖米色底（像旧书页） |
| `--bg-soft` | `#ece8de` | 更深暖灰，分区背景 |
| `--bg-card` | `#faf8f2` | 卡片背景（比底色略亮） |
| `--ink` | `#1a1814` | 主文字（接近黑棕） |
| `--ink-soft` | `#57524a` | 次要文字 |
| `--ink-faint` | `#8a857b` | 辅助文字 |
| `--line` | `#d9d3c5` | 分割线 |
| `--line-soft` | `#e6e0d2` | 浅分割线 |
| `--accent` | `#0a6b6e` | **墨绿** · 主 accent（Perplexity 同源） |
| `--accent-soft` | `#cee5e5` | 墨绿浅色 |
| `--accent-deep` | `#014d52` | 墨绿深色 |
| `--clay` | `#b85c38` | **土陶橙** · 第二 accent |
| `--clay-soft` | `#f3dccd` | 土陶浅色 |
| `--gold` | `#c89b3c` | 引用编号高亮 |
| `--warning` | `#c08a1a` | 警告条 |

## 3. 字体

- **Display（标题）**: `Fraunces, "Source Serif Pro", Georgia, serif`
  - 字重：300-900（variable）
  - 字距：-0.02em（标题）
- **Body（正文）**: `Manrope, "PingFang SC", system-ui, sans-serif`
  - 字重：400/500/600/700
- **Mono（代码/数据）**: `"JetBrains Mono", "SF Mono", Consolas, monospace`

## 4. 字号尺度

| 用途 | 字号 | 行高 | 字重 |
|---|---|---|---|
| 章节扉页大标题 | 144px | 1.0 | 300 |
| 章节扉页副标题 | 40px | 1.3 | 400 |
| H1（页内主标题） | 88px | 1.05 | 400 |
| H2（页内副标题） | 56px | 1.1 | 500 |
| H3（小标题） | 36px | 1.2 | 500 |
| 正文 | 24px | 1.6 | 400 |
| 辅助文字 | 18px | 1.5 | 400 |
| 数字大屏 | 160px | 1.0 | 300 (Fraunces) |
| 引文 | 32px | 1.45 | 400 italic |
| 标签/Eyebrow | 14px | 1.0 | 600 letter-spacing 0.18em uppercase |

## 5. 组件签名

- **页码**: 右下角 `18px Manrope` 灰色，格式 `01 / 19`
- **Eyebrow（眉头）**: 每页左上角小标签，墨绿色，uppercase letter-spacing 0.18em
- **Hero element**: 至少一处需要 120% 精致的细节，其他 80%
- **金色角标**: 数字 KPI 前缀用 gold 色 `#c89b3c` Fraunces 字体
- **引用前缀**: 「内联 [n] 标号」用 `[1]` 形式，gold 色

## 6. 反 AI slop 自检

- ❌ 紫渐变 → ✅ 暖米色 + 墨绿/土陶
- ❌ 圆角卡片+左 border accent → ✅ 暖米底色 + 1px 实线
- ❌ emoji 作图标 → ✅ 仅在数据/标签上保留 1-2 个必要 emoji
- ❌ Inter/Roboto → ✅ Fraunces + Manrope
- ❌ CSS 剪影画产品 → ✅ 真实 ASCII 流程图/JSON 片段

## 7. 19 页大纲

| # | 文件 | 标题 | 叙事角色 |
|---|---|---|---|
| 01 | `01-cover.html` | Loci · 演示封面 | hero |
| 02 | `02-toc.html` | 目录 | 索引 |
| 03 | `03-chapter1.html` | Chapter 1 · 项目背景 | 章节扉页 |
| 04 | `04-objectives.html` | 项目目标 | 概念 |
| 05 | `05-significance.html` | 痛点与价值 | 数据/对比 |
| 06 | `06-context.html` | 项目来源与定位 | 过渡 |
| 07 | `07-chapter2.html` | Chapter 2 · 系统设计 | 章节扉页 |
| 08 | `08-tech-stack.html` | 技术栈全景 | 矩阵 |
| 09 | `09-architecture.html` | 系统架构 | 架构图 |
| 10 | `10-rag-pipeline.html` | RAG 检索流水线 | 核心流程 |
| 11 | `11-persistence.html` | 数据持久化层 | 列表+对比 |
| 12 | `12-chapter3.html` | Chapter 3 · 实施评估 | 章节扉页 |
| 13 | `13-capability.html` | 核心能力矩阵 | 表格 |
| 14 | `14-performance.html` | 性能指标与测试 | 数据 |
| 15 | `15-evolution.html` | 版本演进 | 时间线 |
| 16 | `16-chapter4.html` | Chapter 4 · 反思与总结 | 章节扉页 |
| 17 | `17-lessons.html` | 经验教训与挑战 | 引语/对比 |
| 18 | `18-future.html` | 未来改进 | 列表 |
| 19 | `19-thanks.html` | 致谢 / Q&A | 结尾 |

## 8. 通用页面结构

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght,SOFT,WONK@9..144,300..900,0..100,0..1&family=Manrope:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    /* 使用上面的 design tokens */
  </style>
</head>
<body>
  <div class="page">
    <div class="eyebrow">CHAPTER 01 · 项目背景</div>
    <h1 class="title">...</h1>
    <!-- 内容 -->
    <div class="page-num">01 / 19</div>
  </div>
</body>
</html>
```

## 9. CSS 通用变量（每页可独立 inline）

```css
:root {
  --bg: #f4f1ea;
  --bg-soft: #ece8de;
  --bg-card: #faf8f2;
  --ink: #1a1814;
  --ink-soft: #57524a;
  --ink-faint: #8a857b;
  --line: #d9d3c5;
  --line-soft: #e6e0d2;
  --accent: #0a6b6e;
  --accent-soft: #cee5e5;
  --accent-deep: #014d52;
  --clay: #b85c38;
  --clay-soft: #f3dccd;
  --gold: #c89b3c;
  --warning: #c08a1a;
  --font-display: 'Fraunces', 'Source Serif Pro', Georgia, serif;
  --font-body: 'Manrope', 'PingFang SC', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', 'SF Mono', Consolas, monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 1920px; height: 1080px; overflow: hidden; }
body {
  font-family: var(--font-body);
  background: var(--bg);
  color: var(--ink);
  font-size: 24px;
  line-height: 1.6;
}
.page {
  width: 1920px; height: 1080px;
  padding: 90px 120px;
  position: relative;
}
.eyebrow {
  font-size: 14px; font-weight: 600;
  letter-spacing: 0.18em; text-transform: uppercase;
  color: var(--accent); margin-bottom: 24px;
}
.page-num {
  position: absolute; bottom: 36px; right: 120px;
  font-size: 18px; color: var(--ink-faint);
  font-variant-numeric: tabular-nums;
  letter-spacing: 0.05em;
}
```
