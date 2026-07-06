"""
导出模块 v4.3 - 支持 JSON/Markdown/PDF 三种格式导出
===================================================
支持收藏和会话记录的导出，带中文支持

导出格式：
- JSON: 原始数据，包含完整元信息
- Markdown: 人类可读，适合存档和分享
- PDF: 适合打印，使用reportlab生成

使用方法：
    from exporters import export_favorites_json, export_favorites_markdown, export_favorites_pdf
    from exporters import export_session_markdown, export_session_pdf

    # 导出收藏
    json_data = export_favorites_json(favorites_list)
    md_data = export_favorites_markdown(favorites_list)
    pdf_bytes = export_favorites_pdf(favorites_list)

    # 导出单个会话
    md_data = export_session_markdown(session_data)
    pdf_bytes = export_session_pdf(session_data)
"""
import io
import os
from datetime import datetime
from typing import List, Dict, Any, Optional

# Windows中文字体路径
FONT_PATHS = [
    "C:/Windows/Fonts/msyh.ttc",  # 微软雅黑
    "C:/Windows/Fonts/simsun.ttc",  # 宋体
    "C:/Windows/Fonts/simhei.ttf",  # 黑体
    "C:/Windows/Fonts/arial.ttf",  # Arial备用
]

CHINESE_FONT = "Microsoft YaHei"


def _get_chinese_font():
    """获取可用的中文字体"""
    for font_path in FONT_PATHS:
        if os.path.exists(font_path):
            return font_path
    return None


def _register_chinese_font():
    """注册中文字体到reportlab"""
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        font_path = _get_chinese_font()
        if font_path:
            pdfmetrics.registerFont(TTFont(CHINESE_FONT, font_path))
            return True
    except Exception as e:
        print(f"[Export] 注册字体失败: {e}")
    return False


# =============================================================================
# JSON 导出
# =============================================================================

def export_favorites_json(favorites: List[Dict[str, Any]]) -> str:
    """
    导出收藏为JSON格式

    Args:
        favorites: 收藏列表

    Returns:
        JSON字符串
    """
    import json
    data = {
        "export_time": datetime.now().isoformat(),
        "total": len(favorites),
        "favorites": favorites
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def export_session_json(session: Dict[str, Any], messages: List[Dict[str, Any]]) -> str:
    """
    导出会话为JSON格式

    Args:
        session: 会话元信息
        messages: 消息列表

    Returns:
        JSON字符串
    """
    import json
    data = {
        "export_time": datetime.now().isoformat(),
        "session": session,
        "messages": messages
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


# =============================================================================
# Markdown 导出
# =============================================================================

def _escape_markdown(text: str) -> str:
    """转义Markdown特殊字符"""
    if not text:
        return ""
    # 简单转义：处理常见问题
    text = text.replace("\\", "\\\\")  # 先转义反斜杠
    return text


def export_favorites_markdown(favorites: List[Dict[str, Any]], title: str = "收藏导出") -> str:
    """
    导出收藏为Markdown格式

    Args:
        favorites: 收藏列表
        title: 文档标题

    Returns:
        Markdown字符串
    """
    lines = [
        f"# {title}",
        "",
        f"**导出时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**收藏数量**: {len(favorites)}",
        "",
        "---",
        ""
    ]

    for i, fav in enumerate(reversed(favorites), 1):
        question = _escape_markdown(fav.get("question", ""))
        answer = _escape_markdown(fav.get("answer", ""))
        created_at = fav.get("created_at", "")
        sources = fav.get("sources", [])

        lines.append(f"## {i}. {question}")
        lines.append("")
        lines.append("**问**:")
        lines.append(f"{question}")
        lines.append("")
        lines.append("**答**:")
        lines.append(f"{answer}")
        lines.append("")

        if sources:
            lines.append("**参考来源**:")
            for src in sources:
                src_name = src.get("source", "未知")
                src_score = src.get("score", 0)
                lines.append(f"- [{src_name}](#) (Rerank: {src_score:.3f})")
            lines.append("")

        if created_at:
            lines.append(f"*收藏时间: {created_at}*")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def export_session_markdown(session: Dict[str, Any], messages: List[Dict[str, Any]]) -> str:
    """
    导出会话为Markdown格式

    Args:
        session: 会话元信息
        messages: 消息列表

    Returns:
        Markdown字符串
    """
    title = session.get("title", "会话导出")
    created = session.get("created_at", "")
    updated = session.get("updated_at", "")

    lines = [
        f"# {title}",
        "",
        f"**创建时间**: {created}",
        f"**更新时间**: {updated}",
        "",
        "---",
        ""
    ]

    for msg in messages:
        role = msg.get("role", "")
        content = _escape_markdown(msg.get("content", ""))

        if role == "user":
            lines.append("### 你")
        else:
            lines.append("### Loci")

        lines.append("")
        lines.append(content)
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def export_sessions_markdown(sessions: List[Dict[str, Any]], all_messages: Dict[str, List[Dict]]) -> str:
    """
    导出多个会话为单个Markdown文件

    Args:
        sessions: 会话列表
        all_messages: {session_id: messages} 映射

    Returns:
        Markdown字符串
    """
    lines = [
        "# 知识库问答会话导出",
        "",
        f"**导出时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**会话数量**: {len(sessions)}",
        "",
        "---",
        "",
        "## 目录",
        ""
    ]

    # 生成目录
    for i, sess in enumerate(sessions, 1):
        sess_id = sess.get("session_id", "")
        sess_title = sess.get("title", "未命名会话") or "未命名会话"
        lines.append(f"{i}. [{sess_title}](#{sess_id})")
    lines.append("")

    # 导出每个会话
    for i, sess in enumerate(sessions, 1):
        sess_id = sess.get("session_id", "")
        sess_title = sess.get("title", "未命名会话") or "未命名会话"
        created = sess.get("created_at", "")
        messages = all_messages.get(sess_id, [])

        lines.append(f"## {i}. {sess_title} {{#{sess_id}}}")
        lines.append("")
        lines.append(f"**创建时间**: {created}")
        lines.append(f"**消息数**: {len(messages)}")
        lines.append("")
        lines.append("---")
        lines.append("")

        for msg in messages:
            role = msg.get("role", "")
            content = _escape_markdown(msg.get("content", ""))

            if role == "user":
                lines.append("### 你")
            else:
                lines.append("### Loci")

            lines.append("")
            lines.append(content)
            lines.append("")
            lines.append("---")
            lines.append("")

    return "\n".join(lines)


# =============================================================================
# PDF 导出（使用 reportlab）
# =============================================================================

def export_favorites_pdf(favorites: List[Dict[str, Any]], title: str = "收藏导出") -> bytes:
    """
    导出收藏为PDF格式

    Args:
        favorites: 收藏列表
        title: 文档标题

    Returns:
        PDF字节数据
    """
    # 尝试注册中文字体
    has_chinese_font = _register_chinese_font()

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
    except ImportError:
        print("[Export] ⚠️ reportlab 未安装，PDF导出不可用")
        return b""

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20*mm,
        leftMargin=20*mm,
        topMargin=20*mm,
        bottomMargin=20*mm
    )

    styles = getSampleStyleSheet()

    # 创建自定义样式
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName=CHINESE_FONT if has_chinese_font else 'Helvetica-Bold'
    ) if has_chinese_font else styles['Heading1']

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=12,
        spaceAfter=6,
        spaceBefore=12,
        fontName=CHINESE_FONT if has_chinese_font else 'Helvetica-Bold'
    ) if has_chinese_font else styles['Heading2']

    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6,
        fontName=CHINESE_FONT if has_chinese_font else 'Helvetica'
    ) if has_chinese_font else styles['Normal']

    meta_style = ParagraphStyle(
        'Meta',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
        fontName=CHINESE_FONT if has_chinese_font else 'Helvetica'
    ) if has_chinese_font else styles['Normal']

    story = []

    # 标题
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", meta_style))
    story.append(Paragraph(f"收藏数量: {len(favorites)}", meta_style))
    story.append(Spacer(1, 10*mm))

    # 内容
    for i, fav in enumerate(reversed(favorites), 1):
        question = fav.get("question", "")
        answer = fav.get("answer", "")
        created_at = fav.get("created_at", "")
        sources = fav.get("sources", [])

        # 问
        story.append(Paragraph(f"<b>Q{i}. {question}</b>", heading_style))
        story.append(Spacer(1, 3*mm))

        # 答
        story.append(Paragraph(answer, body_style))
        story.append(Spacer(1, 3*mm))

        # 来源
        if sources:
            src_text = "参考: " + ", ".join([
                f"{s.get('source', '未知')}({s.get('score', 0):.2f})"
                for s in sources[:3]
            ])
            story.append(Paragraph(src_text, meta_style))

        if created_at:
            story.append(Paragraph(f"<i>{created_at}</i>", meta_style))

        story.append(Spacer(1, 8*mm))

        # 分页
        if i % 5 == 0:
            story.append(PageBreak())

    doc.build(story)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data


def export_session_pdf(session: Dict[str, Any], messages: List[Dict[str, Any]]) -> bytes:
    """
    导出单个会话为PDF格式

    Args:
        session: 会话元信息
        messages: 消息列表

    Returns:
        PDF字节数据
    """
    has_chinese_font = _register_chinese_font()

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
    except ImportError:
        print("[Export] ⚠️ reportlab 未安装，PDF导出不可用")
        return b""

    title = session.get("title", "会话导出")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20*mm,
        leftMargin=20*mm,
        topMargin=20*mm,
        bottomMargin=20*mm
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=8,
        alignment=TA_CENTER,
        fontName=CHINESE_FONT if has_chinese_font else 'Helvetica-Bold'
    ) if has_chinese_font else styles['Heading1']

    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=11,
        spaceAfter=4,
        spaceBefore=8,
        fontName=CHINESE_FONT if has_chinese_font else 'Helvetica-Bold'
    ) if has_chinese_font else styles['Heading2']

    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['Normal'],
        fontSize=10,
        spaceAfter=6,
        fontName=CHINESE_FONT if has_chinese_font else 'Helvetica'
    ) if has_chinese_font else styles['Normal']

    meta_style = ParagraphStyle(
        'Meta',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.grey,
        fontName=CHINESE_FONT if has_chinese_font else 'Helvetica'
    ) if has_chinese_font else styles['Normal']

    story = []

    # 标题
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(f"创建: {session.get('created_at', '')} | 更新: {session.get('updated_at', '')}", meta_style))
    story.append(Spacer(1, 8*mm))

    # 消息
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user":
            story.append(Paragraph("👤 你", heading_style))
        else:
            story.append(Paragraph("🤖 Loci", heading_style))

        story.append(Paragraph(content, body_style))
        story.append(Spacer(1, 4*mm))

    doc.build(story)
    pdf_data = buffer.getvalue()
    buffer.close()
    return pdf_data


# =============================================================================
# 辅助函数：保存到文件
# =============================================================================

def save_export(data, filename: str) -> str:
    """
    保存导出数据到文件

    Args:
        data: 导出数据（字符串或字节）
        filename: 文件名

    Returns:
        保存的文件路径
    """
    if isinstance(data, bytes):
        with open(filename, 'wb') as f:
            f.write(data)
    else:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(data)
    return filename
