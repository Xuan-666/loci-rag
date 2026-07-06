"""
收藏夹持久化模块
==================
提供 ``Favorite`` 数据类与 ``FavoritesStore`` 管理类，
用于问答收藏 / 笔记功能的本地 JSON 持久化。

特性：
- 单文件 JSON 存储（{items: [...]}），便于备份与迁移
- 原子写入（临时文件 + rename），避免崩溃导致数据损坏
- 容错读取：JSON 损坏或字段缺失时返回空结构，不抛异常
- 新增收藏时插入到列表头（最新的在前），与前端期望一致
- ``threading.Lock`` 保护并发写，与 chat_store / tag_manager 风格一致
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# =============================================================================
# 数据类定义
# =============================================================================

@dataclass
class Favorite:
    """单条收藏"""
    id: str                # UUID
    question: str          # 用户问题
    answer: str            # LLM 回答
    sources: List[Dict[str, Any]] = field(default_factory=list)  # 来源元数据
    created_at: str = ""   # ISO 时间字符串


# =============================================================================
# FavoritesStore 收藏夹管理类
# =============================================================================

class FavoritesStore:
    """问答收藏夹的持久化管理器（基于 JSON 文件）"""

    def __init__(self, store_path: str = "./favorites.json") -> None:
        """
        初始化收藏夹管理器：加载已有文件或创建空存储。

        :param store_path: JSON 存储文件路径
        """
        self.store_path = Path(store_path)
        # 写锁：保证 _save_to_disk 在多线程下串行执行
        self._write_lock = threading.Lock()
        # 内部缓存：{"items": [...]}
        self._data: Dict[str, Any] = self._load_from_disk()

    # -------------------------------------------------------------------------
    # 内部工具方法
    # -------------------------------------------------------------------------

    def _now(self) -> str:
        """返回当前时间字符串（格式：YYYY-MM-DD HH:MM:SS）"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _ensure_items(self) -> List[Dict[str, Any]]:
        """确保数据中包含 ``items`` 字段，不存在则创建空列表。"""
        if "items" not in self._data or not isinstance(self._data["items"], list):
            self._data["items"] = []
        return self._data["items"]

    def _load_from_disk(self) -> Dict[str, Any]:
        """从磁盘加载 JSON，损坏或缺失时返回空结构（不抛异常）"""
        if not self.store_path.exists():
            return {"items": []}
        try:
            with open(self.store_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            # 兼容旧数据：顶层是 list 时包成 dict
            if isinstance(data, list):
                return {"items": data}
            if not isinstance(data, dict):
                return {"items": []}
            if "items" not in data or not isinstance(data["items"], list):
                data["items"] = []
            return data
        except (json.JSONDecodeError, OSError, ValueError):
            return {"items": []}

    def _save_to_disk(self) -> None:
        """原子写入磁盘：先写临时文件再 rename，避免崩溃损坏。"""
        with self._write_lock:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.store_path.with_suffix(self.store_path.suffix + ".tmp")
            with open(tmp_path, "w", encoding="utf-8") as fp:
                json.dump(self._data, fp, ensure_ascii=False, indent=2)
            # Windows 上需先删除目标文件再 rename，否则可能抛 PermissionError
            if os.name == "nt" and self.store_path.exists():
                os.remove(self.store_path)
            os.replace(tmp_path, self.store_path)

    # -------------------------------------------------------------------------
    # 公共 API
    # -------------------------------------------------------------------------

    def add(
        self,
        question: str,
        answer: str,
        sources: Optional[List[Dict[str, Any]]] = None,
    ) -> Favorite:
        """
        新增一条收藏（插入到列表头，最新的在前）。

        :param question: 用户问题
        :param answer: LLM 回答
        :param sources: 来源元数据列表（可选）
        :return: 新建的 ``Favorite`` 实例
        :raises ValueError: 问题或答案为空时
        """
        if not question or not isinstance(question, str):
            raise ValueError("question 必填且必须为字符串")
        if not answer or not isinstance(answer, str):
            raise ValueError("answer 必填且必须为字符串")
        items = self._ensure_items()
        fav = Favorite(
            id=str(uuid.uuid4()),
            question=question.strip(),
            answer=answer.strip(),
            sources=list(sources) if sources else [],
            created_at=self._now(),
        )
        items.insert(0, {
            "id": fav.id,
            "question": fav.question,
            "answer": fav.answer,
            "sources": fav.sources,
            "created_at": fav.created_at,
        })
        self._save_to_disk()
        return fav

    def list_all(self) -> List[Dict[str, Any]]:
        """
        返回所有收藏（最新在前），过滤掉损坏的项。

        :return: 收藏字典列表
        """
        items = self._ensure_items()
        result: List[Dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict) and "id" in item:
                result.append(item)
        return result

    def get(self, fav_id: str) -> Optional[Dict[str, Any]]:
        """
        按 ID 查询单条收藏。

        :param fav_id: 收藏 UUID
        :return: 收藏字典；不存在时返回 None
        """
        for item in self._ensure_items():
            if isinstance(item, dict) and item.get("id") == fav_id:
                return item
        return None

    def delete(self, fav_id: str) -> bool:
        """
        按 ID 删除一条收藏。

        :param fav_id: 收藏 UUID
        :return: 成功返回 ``True``，ID 不存在返回 ``False``
        """
        items = self._ensure_items()
        new_items = [i for i in items if not (isinstance(i, dict) and i.get("id") == fav_id)]
        if len(new_items) == len(items):
            return False
        self._data["items"] = new_items
        self._save_to_disk()
        return True

    def clear_all(self) -> None:
        """清空所有收藏"""
        self._data["items"] = []
        self._save_to_disk()

    def get_stats(self) -> Dict[str, int]:
        """
        返回收藏夹统计信息。

        :return: ``{"total": N, "with_sources": M}``
        """
        items = self._ensure_items()
        with_sources = sum(
            1 for i in items
            if isinstance(i, dict) and i.get("sources")
        )
        return {"total": len(items), "with_sources": with_sources}
