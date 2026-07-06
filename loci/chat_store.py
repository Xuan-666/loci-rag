"""
聊天记录持久化模块
====================
提供 ``ChatStore`` 类，用于多会话聊天记录的本地 JSON 持久化。

特性：
- 单文件存储，便于备份与迁移
- 原子写入（临时文件 + rename），避免崩溃导致数据损坏
- 容错读取：JSON 损坏或字段缺失时返回空结构，不抛异常
- 会话自动按更新时间倒序返回
"""

import json
import uuid
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


# =============================================================================
# ChatStore 聊天记录持久化类
# =============================================================================

class ChatStore:
    """多会话聊天记录持久化管理器（基于 JSON 文件）"""

    def __init__(self, store_path: str = "./chat_history.json") -> None:
        """
        初始化存储管理器：加载已有文件或创建空存储。

        :param store_path: JSON 存储文件路径
        """
        # 统一使用 pathlib.Path 便于跨平台处理
        self.store_path = Path(store_path)
        # 写锁：保证 _save_to_disk 在多线程下串行执行，避免并发覆盖
        self._write_lock = threading.Lock()
        # 内部缓存结构：{"sessions": {<session_id>: {...}}}
        self._data: Dict[str, Any] = self._load_from_disk()

    # -------------------------------------------------------------------------
    # 内部工具方法
    # -------------------------------------------------------------------------

    def _now(self) -> str:
        """返回当前时间字符串（格式：YYYY-MM-DD HH:MM:SS）"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _ensure_sessions(self) -> Dict[str, Any]:
        """确保数据中包含 ``sessions`` 字段，不存在则创建空 dict。"""
        if "sessions" not in self._data or not isinstance(self._data["sessions"], dict):
            self._data["sessions"] = {}
        return self._data["sessions"]

    def _load_from_disk(self) -> Dict[str, Any]:
        """从磁盘加载 JSON，损坏或缺失时返回空结构（不抛异常）"""
        # 文件不存在则直接返回空结构
        if not self.store_path.exists():
            return {"sessions": {}}
        try:
            # 显式指定 utf-8 编码，兼容中文会话标题
            with open(self.store_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            # 校验顶层结构，缺失关键字段则重置
            if not isinstance(data, dict) or "sessions" not in data:
                return {"sessions": {}}
            return data
        except (json.JSONDecodeError, OSError, ValueError):
            # 任何读取异常（损坏、权限、编码错误）都降级为空结构
            return {"sessions": {}}

    def _save_to_disk(self) -> None:
        """原子写入磁盘：先写临时文件再 rename，避免崩溃损坏。"""
        # 加锁保证多线程下整个写流程串行，避免临时文件被覆盖或目标被并发删除
        with self._write_lock:
            # 确保父目录存在
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            # 临时文件与目标文件位于同一目录，保证 rename 原子性
            tmp_path = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
            with open(tmp_path, "w", encoding="utf-8") as fp:
                # ensure_ascii=False 保留中文字符；indent=2 便于人工查看
                json.dump(self._data, fp, ensure_ascii=False, indent=2)
            # 在 Windows 上需先删除目标文件再 rename，否则可能抛 PermissionError
            if os.name == "nt" and self.store_path.exists():
                os.remove(self.store_path)
            os.replace(tmp_path, self.store_path)

    def _auto_title(self, content: str) -> str:
        """根据首条 user 消息生成默认标题（截取前 30 字）"""
        # 去除首尾空白后再截断，避免标题全为空白
        stripped = content.strip()
        if len(stripped) <= 30:
            return stripped or "新会话"
        return stripped[:30] + "..."

    def _normalize_message(self, role: str, content: str) -> Dict[str, str]:
        """构造标准消息结构，自动补充 timestamp 字段"""
        return {
            "role": role,
            "content": content,
            "timestamp": self._now(),
        }

    # -------------------------------------------------------------------------
    # 公共 API：会话管理
    # -------------------------------------------------------------------------

    def create_session(self, title: Optional[str] = None) -> str:
        """
        创建新会话并返回 session_id（UUID 字符串）。

        :param title: 可选会话标题，未提供时为 ``"新会话"``
        :return: 新会话的 UUID 标识
        """
        sessions = self._ensure_sessions()
        # 使用 uuid4 保证全局唯一性
        session_id = str(uuid.uuid4())
        timestamp = self._now()
        sessions[session_id] = {
            "title": title or "新会话",
            "created_at": timestamp,
            "updated_at": timestamp,
            "messages": [],
        }
        # 落盘后再返回，确保外部可立即通过其他方法读取
        self._save_to_disk()
        return session_id

    def list_sessions(self) -> List[Dict[str, Any]]:
        """
        返回所有会话摘要列表，按 ``updated_at`` 倒序排序。

        每项包含：session_id、title、created_at、updated_at、message_count
        """
        sessions = self._ensure_sessions()
        summaries: List[Dict[str, Any]] = []
        for session_id, payload in sessions.items():
            # 缺失 messages 字段时按 0 计算，兼容损坏数据
            messages = payload.get("messages", []) or []
            summaries.append({
                "session_id": session_id,
                "title": payload.get("title", "新会话"),
                "created_at": payload.get("created_at", ""),
                "updated_at": payload.get("updated_at", ""),
                "message_count": len(messages),
            })
        # 按 updated_at 降序：最新的会话排在最前
        summaries.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
        return summaries

    def get_messages(self, session_id: str) -> List[Dict[str, str]]:
        """
        返回指定会话的所有消息，格式为 ``[{"role": ..., "content": ...}]``。

        :param session_id: 会话 UUID
        :return: 消息列表；会话不存在时返回空列表
        """
        sessions = self._ensure_sessions()
        payload = sessions.get(session_id)
        if not payload:
            return []
        messages = payload.get("messages", []) or []
        # 外部接口仅暴露 role/content 两个字段，过滤多余字段
        return [
            {"role": msg.get("role", ""), "content": msg.get("content", "")}
            for msg in messages
            if isinstance(msg, dict)
        ]

    def append_message(self, session_id: str, role: str, content: str) -> None:
        """
        向指定会话追加一条消息，并在会话不存在时自动创建。

        :param session_id: 会话 UUID
        :param role: 消息角色（user / assistant）
        :param content: 消息正文
        """
        sessions = self._ensure_sessions()
        # 会话不存在则自动创建，并智能推断标题
        if session_id not in sessions:
            inferred_title = self._auto_title(content) if role == "user" else "新会话"
            timestamp = self._now()
            sessions[session_id] = {
                "title": inferred_title,
                "created_at": timestamp,
                "updated_at": timestamp,
                "messages": [],
            }
        payload = sessions[session_id]
        # 初始化 messages 列表，兼容历史数据
        if "messages" not in payload or not isinstance(payload["messages"], list):
            payload["messages"] = []
        payload["messages"].append(self._normalize_message(role, content))
        # 若标题仍为默认占位符且当前是首条 user 消息，则用其内容自动推断标题
        if role == "user" and payload.get("title") == "新会话":
            payload["title"] = self._auto_title(content)
        # 每次追加消息都刷新 updated_at，便于按活跃度排序
        payload["updated_at"] = self._now()
        self._save_to_disk()

    def delete_session(self, session_id: str) -> bool:
        """
        删除指定会话。

        :param session_id: 会话 UUID
        :return: 删除成功返回 ``True``，会话不存在返回 ``False``
        """
        sessions = self._ensure_sessions()
        if session_id not in sessions:
            return False
        del sessions[session_id]
        self._save_to_disk()
        return True

    def clear_all(self) -> None:
        """清空所有聊天记录（重置为空的 sessions 结构）"""
        self._data = {"sessions": {}}
        self._save_to_disk()

    def export_session(self, session_id: str) -> Dict[str, Any]:
        """
        导出单会话为可序列化 dict（用于 PDF / Markdown 导出）。

        :param session_id: 会话 UUID
        :return: 包含完整会话信息的 dict；会话不存在时返回空 dict
        """
        sessions = self._ensure_sessions()
        payload = sessions.get(session_id)
        if not payload:
            return {}
        # 深拷贝避免外部修改影响内部状态
        return {
            "session_id": session_id,
            "title": payload.get("title", ""),
            "created_at": payload.get("created_at", ""),
            "updated_at": payload.get("updated_at", ""),
            "messages": list(payload.get("messages", []) or []),
        }
