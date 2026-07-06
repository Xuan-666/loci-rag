"""
Loci · 本地知识库 RAG 问答系统 - Flask Web API
================================================
基于花叔design B版 (Perplexity 学术图书馆) 设计风格的Web前端配套API。

主要职责：
- 暴露 RAGEngine / ChatStore / TagManager / FavoritesStore 给前端
- 提供 SSE 流式问答端点
- 提供静态HTML服务 (index.html)
- 复用现有所有后端能力，不重复实现

启动方式：python web_api.py
默认端口：7862
"""
import os
import sys
import time
from datetime import datetime  # v4.3 修复: 导出端点需要 datetime.now()
from pathlib import Path
from typing import Optional, List, Dict, Any

# 字符编码（避免 Windows GBK 问题）
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
os.environ.setdefault("PYTHONUTF8", "1")

from flask import Flask, request, jsonify, Response, send_from_directory, stream_with_context
from flask_cors import CORS

# 复用现有后端
import config
from loci.rag_engine import RAGEngine
from loci.chat_store import ChatStore
from loci.tag_manager import TagManager
from loci.favorites_store import FavoritesStore

# =============================================================================
# 全局状态
# =============================================================================
ROOT_DIR = Path(__file__).parent.resolve()
STATIC_DIR = ROOT_DIR / "frontend"  # 前端资源移入 frontend/ 目录

engine = RAGEngine()
chat_store = ChatStore(getattr(config, "CHAT_HISTORY_PATH", "./data/chat_history.json"))
tag_manager = TagManager(getattr(config, "TAGS_PATH", "./data/tags.json"))
favorites_store = FavoritesStore("./data/favorites.json")


# =============================================================================
# Flask App
# =============================================================================
app = Flask(__name__, static_folder=None)
CORS(app)


# =============================================================================
# 静态首页 + static 资源
# =============================================================================
@app.route("/")
def index():
    """serve index.html (Perplexity 学术图书馆风格前端)"""
    return send_from_directory(str(STATIC_DIR), "index.html")


@app.route("/static/<path:filename>")
def static_files(filename):
    """serve static/*.js, *.css etc."""
    return send_from_directory(str(STATIC_DIR / "static"), filename)


@app.route("/favicon.ico")
def favicon():
    return ("", 204)


# =============================================================================
# 健康检查
# =============================================================================
@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "ts": time.time()})


# =============================================================================
# 引擎状态
# =============================================================================
@app.route("/api/engine_status")
def api_engine_status():
    """返回引擎状态摘要（设置页 + 顶栏使用）"""
    return jsonify({
        "embedding_provider": config.EMBEDDING_PROVIDER,
        "embedding_model": config.BGE_EMBED_MODEL if config.EMBEDDING_PROVIDER == "huggingface" else config.OLLAMA_EMBED_MODEL,
        "llm_model": config.LLM_MODEL,
        "ollama_base_url": config.OLLAMA_BASE_URL,
        "bm25_enabled": config.BM25_ENABLED,
        "bm25_weight": config.BM25_WEIGHT,
        "vector_weight": config.VECTOR_WEIGHT,
        "rerank_enabled": config.RERANK_ENABLED,
        "rerank_initial_k": config.RERANK_INITIAL_K,
        "rerank_final_k": config.RERANK_FINAL_K,
        "rerank_score_threshold": config.RERANK_SCORE_THRESHOLD,
        "chunk_strategy": config.CHUNK_STRATEGY,
        "chunk_size": config.CHUNK_SIZE,
        "chunk_overlap": config.CHUNK_OVERLAP,
        "version_enabled": config.VERSION_ENABLED,
        "rag_fallback_enabled": config.RAG_FALLBACK_ENABLED,
        "rag_fallback_threshold": config.RAG_FALLBACK_THRESHOLD,
    })


# =============================================================================
# 文档入库辅助（upload + rebuild 共享）
# =============================================================================
# 不支持的格式（前端会得到清晰错误提示，不会再误报 DOCX/PPTX 加载失败）
_UNSUPPORTED_HINT = {
    ".doc": "旧版 .doc 二进制格式不支持，请用 Word 另存为 .docx 后再上传",
    ".ppt": "旧版 .ppt 二进制格式不支持，请用 PowerPoint 另存为 .pptx 后再上传",
}


def _ingest_uploaded_files(file_names: List[str]) -> int:
    """
    共享入库流程：把 uploaded_docs/ 下指定文件名加载到向量库。
    返回成功加载的 chunk 数量（部分文件失败不会影响其他文件）。
    """
    from loci.rag_engine import get_loader
    upload_dir = Path(config.UPLOADED_DOCS_PATH)
    all_chunks: List = []
    failed: List[str] = []
    for name in file_names:
        path = upload_dir / name
        if not path.exists():
            continue
        # 旧版二进制格式 .doc / .ppt 在 get_loader 阶段就被明确拒绝
        # 避免日志中出现「DOCX 加载失败」之类误导信息
        ext = path.suffix.lower()
        if ext in _UNSUPPORTED_HINT:
            print(f"[API] 跳过「{name}」: {_UNSUPPORTED_HINT[ext]}")
            failed.append(f"{name}({_UNSUPPORTED_HINT[ext]})")
            continue
        loader = get_loader(str(path))
        if not loader:
            continue
        try:
            all_chunks.extend(loader.load())
        except Exception as e:
            print(f"[API] 「{name}」加载异常: {e}")
            continue
    if all_chunks:
        ok, _ = engine.load_documents(file_paths=[str(upload_dir / n) for n in file_names])
        if not ok:
            return 0
    return len(all_chunks)


# =============================================================================
# 知识库
# =============================================================================
@app.route("/api/knowledge_base")
def api_kb_list():
    """文档列表（带标签，自动剥离路径前缀）"""
    docs = []
    for name in engine.get_doc_names():
        clean_name = Path(name).name  # 剥离 ./uploaded_docs\\ 前缀
        docs.append({"name": clean_name, "tags": tag_manager.get_doc_tags(clean_name)})
    return jsonify({"documents": docs})


@app.route("/api/knowledge_base/stats")
def api_kb_stats():
    """知识库统计"""
    s = engine.get_stats()
    out = {
        "num_docs": s["num_docs"],
        "num_chunks": s["num_chunks"],
        "vector_store_size_mb": round(s["vector_store_size_mb"], 2),
    }
    if engine.version_manager:
        v = engine.version_manager.get_stats()
        out["versions"] = {
            "total": v.get("total_versions", 0),
            "size_mb": v.get("total_size_mb", 0),
        }
    return jsonify(out)


@app.route("/api/knowledge_base/upload", methods=["POST"])
def api_kb_upload():
    """上传文档（multipart: files[]）"""
    if "files" not in request.files:
        return jsonify({"error": "没有文件"}), 400
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "没有文件"}), 400

    upload_dir = Path(config.UPLOADED_DOCS_PATH)
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved: List[str] = []
    rejected: List[Dict[str, str]] = []  # v4.3 修复: 收集被拒文件及原因
    for f in files:
        safe_name = Path(f.filename).name
        ext = Path(safe_name).suffix.lower()
        if ext in _UNSUPPORTED_HINT:
            # 旧版二进制格式直接拒绝，明确告诉前端为什么
            rejected.append({"name": safe_name, "reason": _UNSUPPORTED_HINT[ext]})
            continue
        f.save(str(upload_dir / safe_name))
        saved.append(safe_name)

    chunks = _ingest_uploaded_files(saved) if saved else 0
    if chunks == 0 and saved:
        return jsonify({
            "error": "入库失败",
            "saved": saved,
            "rejected": rejected,
        }), 500
    return jsonify({
        "uploaded": saved,
        "rejected": rejected,
        "chunks": chunks,
    })


@app.route("/api/knowledge_base/documents/<path:name>", methods=["DELETE"])
def api_kb_delete(name):
    """删除文档（接受带或不带路径的 doc name）"""
    # 兼容带 ./uploaded_docs\\ 前缀的历史数据
    candidates = [name, Path(name).name, f"./uploaded_docs\\{name}"]
    if not any(engine.delete_document(c) for c in candidates):
        return jsonify({"error": "删除失败"}), 400
    # 同时删除 uploaded_docs 里的物理文件
    p = Path(config.UPLOADED_DOCS_PATH) / Path(name).name
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass
    return jsonify({"deleted": name})


@app.route("/api/knowledge_base/rebuild", methods=["POST"])
def api_kb_rebuild():
    """重新构建索引（扫描 uploaded_docs）"""
    upload_dir = Path(config.UPLOADED_DOCS_PATH)
    if not upload_dir.exists():
        return jsonify({"error": "uploaded_docs 不存在"}), 400
    file_names = [
        f.name for f in upload_dir.iterdir()
        if f.is_file() and f.suffix.lower() in config.SUPPORTED_EXTENSIONS
    ]
    chunks = _ingest_uploaded_files(file_names)
    return jsonify({"loaded_chunks": chunks, "files": file_names})


# -----------------------------------------------------------------------------
# URL/网页摄取（v4.3 新增）
# -----------------------------------------------------------------------------
@app.route("/api/knowledge_base/ingest_url", methods=["POST"])
def api_kb_ingest_url():
    """
    从 URL 抓取网页正文并入库知识库。

    请求 JSON:
        url:  str (必填，http/https URL)
        tags: [str, ...]  (可选，关联标签)

    Returns:
        {"url": str, "chunks": int, "title": str}
    """
    from loci.web_loader import is_valid_url
    data = request.get_json(force=True, silent=True) or {}
    url = (data.get("url") or "").strip()
    tags = data.get("tags") or []

    if not url:
        return jsonify({"error": "url 必填"}), 400
    if not is_valid_url(url):
        return jsonify({"error": "URL 格式不合法，需以 http:// 或 https:// 开头"}), 400

    try:
        ok, msg = engine.add_url(url, tags=tags if tags else None)
        if not ok:
            return jsonify({"error": msg or "URL 入库失败"}), 500
        # 从 msg 中尝试解析 chunks 数量
        import re
        m = re.search(r"(\d+)\s*个文本块", msg)
        chunks = int(m.group(1)) if m else 1
        title_m = re.search(r"url_([a-f0-9]+)\.html", msg) or re.search(r"成功加载 .+?，生成 (\d+) 个文本块", msg)
        return jsonify({"url": url, "chunks": chunks, "message": msg})
    except Exception as e:
        return jsonify({"error": f"URL 摄取失败: {e}"}), 500


# -----------------------------------------------------------------------------
# 文档预览（v4.2 补充）
# -----------------------------------------------------------------------------
# 支持预览的扩展名（可直接文本/表格/Markdown/PDF/图片）
_PREVIEW_TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".htm", ".log", ".yaml", ".yml", ".rtf"}
_PREVIEW_TABLE_EXTS = {".xlsx", ".xls", ".csv"}


def _safe_read_text(path: Path, max_bytes: int = 8192) -> str:
    """安全读取文本类文件（截断到 max_bytes，避免大文件 OOM）"""
    try:
        with open(path, "rb") as fp:
            data = fp.read(max_bytes)
        # 替换控制字符
        return data.decode("utf-8", errors="replace")
    except Exception as e:
        return f"[读取失败: {e}]"


def _read_pdf_text(path: Path, max_pages: int = 5) -> str:
    """读取 PDF 前 N 页文本（轻量预览）"""
    try:
        from langchain_community.document_loaders import PyPDFLoader
        loader = PyPDFLoader(str(path))
        docs = loader.load()[:max_pages]
        return "\n\n".join(d.page_content for d in docs)
    except Exception as e:
        return f"[PDF 解析失败: {e}]"


def _read_docx_text(path: Path) -> str:
    """读取 docx 文本"""
    try:
        from docx import Document as DocxDocument
        doc = DocxDocument(str(path))
        return "\n".join(p.text for p in doc.paragraphs[:200])
    except Exception as e:
        return f"[DOCX 解析失败: {e}]"


def _read_excel_to_csv(path: Path, max_rows: int = 50) -> str:
    """读取 xlsx 前 N 行转 CSV"""
    try:
        import pandas as pd
        df = pd.read_excel(str(path), nrows=max_rows)
        return df.to_csv(index=False)
    except Exception as e:
        return f"[Excel 解析失败: {e}]"


@app.route("/api/knowledge_base/documents/<path:name>/preview", methods=["GET"])
def api_kb_doc_preview(name):
    """
    返回文档预览文本（轻量级，截断到安全大小）。
    适用：txt/md/csv/json/xml/html/pdf/docx/xlsx/pptx 等。
    """
    # 兼容路径
    p = Path(config.UPLOADED_DOCS_PATH) / Path(name).name
    if not p.exists():
        return jsonify({"error": "文件不存在"}), 404

    stat = p.stat()
    ext = p.suffix.lower()
    info = {
        "name": p.name,
        "ext": ext,
        "size_bytes": stat.st_size,
        "size_kb": round(stat.st_size / 1024, 1),
        "modified": stat.st_mtime,
    }
    # 文本类
    if ext in _PREVIEW_TEXT_EXTS:
        content = _safe_read_text(p, max_bytes=8192)
        return jsonify({**info, "kind": "text", "content": content, "truncated": stat.st_size > 8192})
    # PDF
    if ext == ".pdf":
        content = _read_pdf_text(p, max_pages=5)
        return jsonify({**info, "kind": "pdf", "content": content, "truncated": True})
    # DOCX
    if ext in {".docx"}:
        content = _read_docx_text(p)
        return jsonify({**info, "kind": "docx", "content": content, "truncated": True})
    # XLSX/XLS
    if ext in {".xlsx", ".xls"}:
        content = _read_excel_to_csv(p)
        return jsonify({**info, "kind": "table", "content": content, "truncated": True})
    # PPTX
    if ext in {".pptx", ".ppt"}:
        return jsonify({**info, "kind": "pptx", "content": "[PPT 预览暂不支持，仅显示元数据]", "truncated": True})
    # 图片
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}:
        return jsonify({**info, "kind": "image", "content": "", "truncated": False})
    # 其它二进制
    return jsonify({**info, "kind": "binary", "content": "[二进制文件，无文本预览]", "truncated": False})


@app.route("/api/knowledge_base/documents/<path:name>/file", methods=["GET"])
def api_kb_doc_file(name):
    """返回文档原文件（用于图片预览 / 浏览器打开）"""
    p = Path(config.UPLOADED_DOCS_PATH) / Path(name).name
    if not p.exists():
        return jsonify({"error": "文件不存在"}), 404
    return send_from_directory(str(p.parent), p.name, as_attachment=False)


# -----------------------------------------------------------------------------
# 图片管理（v4.2 补充）
# -----------------------------------------------------------------------------
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}
IMAGES_DIR = ROOT_DIR / "data" / "uploaded_images"


@app.route("/api/images", methods=["GET"])
def api_images_list():
    """列出已上传的图片"""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    images = []
    for f in IMAGES_DIR.iterdir():
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
            stat = f.stat()
            images.append({
                "name": f.name,
                "url": f"/api/images/{f.name}",
                "size_kb": round(stat.st_size / 1024, 1),
                "modified": stat.st_mtime,
            })
    images.sort(key=lambda x: x["modified"], reverse=True)
    return jsonify({"images": images, "total": len(images)})


@app.route("/api/images/upload", methods=["POST"])
def api_images_upload():
    """上传图片到 uploaded_images/ 目录"""
    if "files" not in request.files:
        return jsonify({"error": "没有文件"}), 400
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "没有文件"}), 400
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    saved = []
    for f in files:
        ext = Path(f.filename).suffix.lower()
        if ext not in IMAGE_EXTS:
            continue
        safe = Path(f.filename).name
        f.save(str(IMAGES_DIR / safe))
        saved.append(safe)
    return jsonify({"uploaded": saved, "count": len(saved)})


@app.route("/api/images/<path:name>", methods=["GET"])
def api_images_file(name):
    """返回图片文件"""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    p = IMAGES_DIR / Path(name).name
    if not p.exists():
        return jsonify({"error": "图片不存在"}), 404
    return send_from_directory(str(IMAGES_DIR), p.name, as_attachment=False)


@app.route("/api/images/<path:name>", methods=["DELETE"])
def api_images_delete(name):
    """删除图片"""
    p = IMAGES_DIR / Path(name).name
    if p.exists():
        try:
            p.unlink()
        except OSError as e:
            return jsonify({"error": f"删除失败: {e}"}), 500
    return jsonify({"deleted": name})


# =============================================================================
# 标签
# =============================================================================
@app.route("/api/tags")
def api_tags_list():
    tags = tag_manager.list_tags()
    return jsonify({"tags": [{"name": t.name, "color": t.color} for t in tags]})


@app.route("/api/tags", methods=["POST"])
def api_tags_create():
    data = request.get_json() or {}
    name = (data.get("name") or "").strip()
    color = data.get("color") or "#3B82F6"
    if not name:
        return jsonify({"error": "name 必填"}), 400
    try:
        tag = tag_manager.create_tag(name, color)
        return jsonify({"name": tag.name, "color": tag.color})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/tags/<name>", methods=["DELETE"])
def api_tags_delete(name):
    if not tag_manager.delete_tag(name):
        return jsonify({"error": "删除失败"}), 400
    return jsonify({"deleted": name})


@app.route("/api/knowledge_base/documents/<path:name>/tags", methods=["POST"])
def api_kb_doc_add_tag(name):
    data = request.get_json() or {}
    tag = (data.get("tag") or "").strip()
    if not tag:
        return jsonify({"error": "tag 必填"}), 400
    try:
        tag_manager.add_tag_to_doc(name, tag)
        return jsonify({"name": name, "tag": tag})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/knowledge_base/documents/<path:name>/tags/<tag>", methods=["DELETE"])
def api_kb_doc_remove_tag(name, tag):
    tag_manager.remove_tag_from_doc(name, tag)
    return jsonify({"name": name, "tag": tag})


# =============================================================================
# 问答 (SSE 流式)
# =============================================================================
def _clean_source(raw_src: str) -> str:
    """清理 source 字段中的路径前缀"""
    if not raw_src:
        return "未知"
    return Path(raw_src).name or raw_src


@app.route("/api/query/stream", methods=["POST"])
def api_query_stream():
    """
    SSE 流式问答。

    请求 JSON:
        question:    str (必填)
        session_id:  str (可选；为空时自动创建)
        history:     [("user_q", "assistant_a"), ...]  (可选)
        tag_filter:  ["标签1", ...]  (可选)

    SSE 事件:
        sources: {"type":"sources", "sources":[{source,page,score,preview},...], "fallback"?: bool, "session_id": str}
        token:   {"type":"token", "content":"..."}
        done:    {"type":"done", "session_id": str, "auto_created": bool}
        error:   {"type":"error", "content":"..."}
    """
    data = request.get_json(force=True, silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question 必填"}), 400
    session_id = data.get("session_id")
    history = data.get("history") or []
    tag_filter = data.get("tag_filter") or None

    # 没有 session_id 时自动创建
    auto_created = False
    if not session_id:
        session_id = chat_store.create_session(title=question[:30])
        auto_created = True

    def generate():
        import json
        full_answer = ""
        try:
            for event in engine.stream_query(question, history=history, tag_filter=tag_filter):
                etype = event.get("type")
                if etype == "sources":
                    sources_data = [
                        {
                            "source": _clean_source(doc.metadata.get("source", "未知")),
                            "page": doc.metadata.get("page", 0),
                            "score": float(score) if score is not None else 0.0,
                            "preview": doc.page_content[:200].replace("\n", " "),
                        }
                        for doc, score in event.get("sources", [])
                    ]
                    payload = {
                        "type": "sources",
                        "sources": sources_data,
                        "fallback": event.get("fallback", False),
                        "session_id": session_id,
                    }
                    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                elif etype == "token":
                    content = event.get("content", "")
                    full_answer += content
                    yield f"data: {json.dumps({'type':'token','content':content}, ensure_ascii=False)}\n\n"
                elif etype == "done":
                    # 持久化到聊天记录
                    try:
                        chat_store.append_message(session_id, "user", question)
                        chat_store.append_message(session_id, "assistant", full_answer)
                    except Exception as e:
                        print(f"[API] 保存聊天记录失败: {e}")
                    yield f"data: {json.dumps({'type':'done','session_id':session_id,'auto_created':auto_created}, ensure_ascii=False)}\n\n"
                elif etype == "error":
                    yield f"data: {json.dumps({'type':'error','content':event.get('content','')}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','content':str(e)}, ensure_ascii=False)}\n\n"

    resp = Response(stream_with_context(generate()), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    resp.headers["Connection"] = "keep-alive"
    return resp


# =============================================================================
# 聊天会话
# =============================================================================
@app.route("/api/chat/sessions")
def api_chat_sessions():
    return jsonify({"sessions": chat_store.list_sessions()})


@app.route("/api/chat/sessions", methods=["POST"])
def api_chat_sessions_create():
    data = request.get_json(silent=True) or {}
    return jsonify({"session_id": chat_store.create_session(title=data.get("title"))})


@app.route("/api/chat/sessions/<sid>")
def api_chat_session_detail(sid):
    msgs = chat_store.get_messages(sid)
    sess = next((s for s in chat_store.list_sessions() if s.get("session_id") == sid), None)
    return jsonify({"session": sess, "messages": msgs})


@app.route("/api/chat/sessions/<sid>", methods=["DELETE"])
def api_chat_sessions_delete(sid):
    if not chat_store.delete_session(sid):
        return jsonify({"error": "删除失败"}), 400
    return jsonify({"deleted": sid})


# =============================================================================
# 收藏（FavoritesStore 统一管理）
# =============================================================================
@app.route("/api/favorites")
def api_favorites_list():
    return jsonify({"favorites": favorites_store.list_all()})


@app.route("/api/favorites", methods=["POST"])
def api_favorites_add():
    data = request.get_json(force=True, silent=True) or {}
    try:
        fav = favorites_store.add(
            question=data.get("question", ""),
            answer=data.get("answer", ""),
            sources=data.get("sources") or [],
        )
        return jsonify({
            "id": fav.id,
            "question": fav.question,
            "answer": fav.answer,
            "sources": fav.sources,
            "created_at": fav.created_at,
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/favorites/<fid>", methods=["DELETE"])
def api_favorites_delete(fid):
    if not favorites_store.delete(fid):
        return jsonify({"error": "删除失败"}), 400
    return jsonify({"deleted": fid})


# =============================================================================
# 导出（v4.3: JSON + Markdown + PDF，支持收藏和会话）
# =============================================================================
from loci.exporters import (
    export_favorites_json, export_favorites_markdown, export_favorites_pdf,
    export_session_json, export_session_markdown, export_session_pdf,
    export_sessions_markdown
)


# =============================================================================
# 用户设置（v4.3: 持久化到 user_settings.json）
# =============================================================================
from loci.settings_manager import get_settings_manager


@app.route("/api/settings", methods=["GET"])
def api_settings_get():
    """获取用户设置"""
    manager = get_settings_manager()
    return jsonify(manager.get_settings())


@app.route("/api/settings", methods=["POST"])
def api_settings_update():
    """更新用户设置"""
    data = request.get_json(force=True, silent=True) or {}
    if not data:
        return jsonify({"error": "没有数据"}), 400
    manager = get_settings_manager()
    # 支持批量更新和单个更新
    if isinstance(data, dict) and len(data) == 1:
        # 单个更新
        key, value = list(data.items())[0]
        ok = manager.update_setting(key, value)
    else:
        # 批量更新
        ok = manager.update_settings(data)
    if ok:
        return jsonify({"success": True, "settings": manager.get_settings()})
    return jsonify({"error": "保存失败"}), 500


@app.route("/api/settings/reset", methods=["POST"])
def api_settings_reset():
    """重置设置为默认值"""
    manager = get_settings_manager()
    ok = manager.reset_to_default()
    if ok:
        return jsonify({"success": True, "settings": manager.get_settings()})
    return jsonify({"error": "重置失败"}), 500


@app.route("/api/export/favorites", methods=["POST"])
def api_export_favorites():
    """
    导出收藏。

    请求 JSON:
        ids:   [str, ...]  (可选，为空则导出全部)
        format: "json" | "markdown" | "pdf"  (默认 "json")

    Returns:
        JSON: {"format": str, "data": str/bytes, "filename": str}
        或直接返回 PDF 文件流
    """
    data = request.get_json(force=True, silent=True) or {}
    ids = data.get("ids") or []  # 空列表表示全部
    fmt = (data.get("format") or "json").lower()

    # 筛选收藏（favorites_store.list_all() 返回的是 dict 列表，不是对象）
    all_favs = favorites_store.list_all()
    if ids:
        filtered = [f for f in all_favs if f.get("id") in ids]
    else:
        filtered = all_favs

    # 转为统一 dict 列表（兼容字段命名）
    fav_dicts = [
        {
            "id": f.get("id", ""),
            "question": f.get("question", ""),
            "answer": f.get("answer", ""),
            "sources": f.get("sources") or [],
            "created_at": f.get("created_at", ""),
        }
        for f in filtered
    ]

    if fmt == "markdown":
        content = export_favorites_markdown(fav_dicts)
        return jsonify({
            "format": "markdown",
            "data": content,
            "filename": f"favorites_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        })
    elif fmt == "pdf":
        pdf_bytes = export_favorites_pdf(fav_dicts)
        if not pdf_bytes:
            return jsonify({"error": "PDF生成失败，请确保已安装 reportlab"}), 500
        resp = Response(pdf_bytes, mimetype="application/pdf")
        resp.headers["Content-Disposition"] = f"attachment; filename=favorites_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        return resp
    else:
        # 默认 JSON
        content = export_favorites_json(fav_dicts)
        return jsonify({
            "format": "json",
            "data": content,
            "filename": f"favorites_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        })


@app.route("/api/export/sessions", methods=["POST"])
def api_export_sessions():
    """
    导出会话。

    请求 JSON:
        ids:   [str, ...]  (可选，为空则导出全部)
        format: "json" | "markdown" | "pdf"  (默认 "markdown")
        single_id: str  (可选，导出单个会话时指定)

    Returns:
        JSON 或文件流
    """
    data = request.get_json(force=True, silent=True) or {}
    ids = data.get("ids") or []
    fmt = (data.get("format") or "markdown").lower()
    single_id = data.get("single_id")

    # 单会话导出
    if single_id:
        msgs = chat_store.get_messages(single_id)
        sess = next((s for s in chat_store.list_sessions() if s.get("session_id") == single_id), {})
        if not sess:
            return jsonify({"error": "会话不存在"}), 404

        if fmt == "pdf":
            pdf_bytes = export_session_pdf(sess, msgs)
            if not pdf_bytes:
                return jsonify({"error": "PDF生成失败"}), 500
            resp = Response(pdf_bytes, mimetype="application/pdf")
            safe_title = "".join(c for c in (sess.get("title") or "session") if c.isalnum() or c in " -_")
            resp.headers["Content-Disposition"] = f"attachment; filename={safe_title}.pdf"
            return resp
        elif fmt == "json":
            content = export_session_json(sess, msgs)
            return jsonify({
                "format": "json",
                "data": content,
                "filename": f"session_{single_id[:8]}.json"
            })
        else:
            content = export_session_markdown(sess, msgs)
            safe_title = "".join(c for c in (sess.get("title") or "session") if c.isalnum() or c in " -_")
            return jsonify({
                "format": "markdown",
                "data": content,
                "filename": f"{safe_title}.md"
            })

    # 批量导出
    all_sessions = chat_store.list_sessions()
    if ids:
        sessions_to_export = [s for s in all_sessions if s.get("session_id") in ids]
    else:
        sessions_to_export = all_sessions

    # 收集所有消息
    all_msgs = {}
    for s in sessions_to_export:
        sid = s.get("session_id")
        if sid:
            all_msgs[sid] = chat_store.get_messages(sid)

    if fmt == "markdown":
        content = export_sessions_markdown(sessions_to_export, all_msgs)
        return jsonify({
            "format": "markdown",
            "data": content,
            "filename": f"sessions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        })
    elif fmt == "pdf":
        # 批量PDF导出为ZIP
        try:
            import zipfile
            import io
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                for s in sessions_to_export:
                    sid = s.get("session_id")
                    if sid:
                        msgs = all_msgs.get(sid, [])
                        pdf_bytes = export_session_pdf(s, msgs)
                        if pdf_bytes:
                            safe_title = "".join(c for c in (s.get("title") or sid[:8]) if c.isalnum() or c in " -_")
                            zf.writestr(f"{safe_title}.pdf", pdf_bytes)
            zip_buffer.seek(0)
            resp = Response(zip_buffer.getvalue(), mimetype="application/zip")
            resp.headers["Content-Disposition"] = f"attachment; filename=sessions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
            return resp
        except Exception as e:
            return jsonify({"error": f"ZIP打包失败: {e}"}), 500
    else:
        # JSON批量
        all_data = []
        for s in sessions_to_export:
            sid = s.get("session_id")
            if sid:
                all_data.append({
                    "session": s,
                    "messages": all_msgs.get(sid, [])
                })
        import json
        content = json.dumps({
            "export_time": datetime.now().isoformat(),
            "total_sessions": len(all_data),
            "sessions": all_data
        }, ensure_ascii=False, indent=2)
        return jsonify({
            "format": "json",
            "data": content,
            "filename": f"sessions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        })


# =============================================================================
# 启动
# =============================================================================
def _print_banner() -> None:
    """打印启动横幅"""
    print("=" * 60)
    print("  Loci · 本地知识库 RAG 问答系统")
    print("  Flask Web API (花叔design B版)")
    print("=" * 60)
    print(f"  📚 文档: {len(engine.get_doc_names())} 个")
    print(f"  💬 会话: {len(chat_store.list_sessions())} 个")
    print(f"  🏷️  标签: {len(tag_manager.list_tags())} 个")
    print(f"  ⭐ 收藏: {favorites_store.get_stats()['total']} 个")
    print("=" * 60)
    print(f"  🌐 访问: http://localhost:7862")
    print(f"  📡 API:  http://localhost:7862/api/*")
    print("=" * 60)


if __name__ == "__main__":
    _print_banner()
    app.run(host="0.0.0.0", port=7862, debug=False, threaded=True)
