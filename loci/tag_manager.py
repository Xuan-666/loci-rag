"""
标签管理模块
================
提供 ``Tag`` / ``DocTagBinding`` 数据类与 ``TagManager`` 管理类，
用于本地知识库 RAG 系统的标签 / 分类管理。

特性：
- 单文件 JSON 存储，便于备份与迁移
- 原子写入（临时文件 + rename），避免崩溃导致数据损坏
- 容错读取：JSON 损坏或字段缺失时返回空结构，不抛异常
- ``add_tag_to_doc`` 幂等：重复添加不重复计数
- ``remove_tag_from_doc`` 自动维护 ``doc_count``
- ``threading.Lock`` 保护并发写，与 chat_store 风格一致
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# =============================================================================
# 数据类定义
# =============================================================================

@dataclass
class Tag:
    """标签定义：名称（唯一）、显示颜色、创建时间、关联文档数。"""
    name: str           # 标签名（全局唯一）
    color: str = "#3B82F6"  # 显示颜色（HEX 格式）
    created_at: str = ""    # ISO 时间字符串
    doc_count: int = 0      # 关联文档数（自动维护）


@dataclass
class DocTagBinding:
    """文档-标签绑定关系：哪个文档绑定了哪个标签。"""
    doc_name: str       # 文档名（与 Document.metadata 中 source 对应）
    tag: str            # 绑定的标签名


# =============================================================================
# TagManager 标签管理类
# =============================================================================

class TagManager:
    """标签与文档-标签绑定的持久化管理器（基于 JSON 文件）"""

    def __init__(self, store_path: str = "./tags.json") -> None:
        """
        初始化标签管理器：加载已有文件或创建空存储。

        :param store_path: JSON 存储文件路径
        """
        # 统一使用 pathlib.Path 便于跨平台处理
        self.store_path = Path(store_path)
        # 写锁：保证 _save_to_disk 在多线程下串行执行，避免并发覆盖
        self._write_lock = threading.Lock()
        # 内部缓存：{"tags": {...}, "bindings": {...}}
        self._data: Dict[str, Any] = self._load_from_disk()

    # -------------------------------------------------------------------------
    # 内部工具方法
    # -------------------------------------------------------------------------

    def _now(self) -> str:
        """返回当前时间字符串（格式：YYYY-MM-DD HH:MM:SS）"""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _ensure_tags(self) -> Dict[str, Any]:
        """确保数据中包含 ``tags`` 字段，不存在则创建空 dict。"""
        if "tags" not in self._data or not isinstance(self._data["tags"], dict):
            self._data["tags"] = {}
        return self._data["tags"]

    def _ensure_bindings(self) -> Dict[str, Any]:
        """确保数据中包含 ``bindings`` 字段，不存在则创建空 dict。"""
        if "bindings" not in self._data or not isinstance(self._data["bindings"], dict):
            self._data["bindings"] = {}
        return self._data["bindings"]

    def _load_from_disk(self) -> Dict[str, Any]:
        """从磁盘加载 JSON，损坏或缺失时返回空结构（不抛异常）"""
        # 文件不存在则直接返回空结构
        if not self.store_path.exists():
            return {"tags": {}, "bindings": {}}
        try:
            # 显式指定 utf-8 编码，兼容中文标签
            with open(self.store_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
            # 校验顶层结构，缺失关键字段则重置
            if not isinstance(data, dict):
                return {"tags": {}, "bindings": {}}
            # 容错：缺失字段时填充空 dict，避免后续 KeyError
            if "tags" not in data or not isinstance(data["tags"], dict):
                data["tags"] = {}
            if "bindings" not in data or not isinstance(data["bindings"], dict):
                data["bindings"] = {}
            return data
        except (json.JSONDecodeError, OSError, ValueError):
            # 任何读取异常（损坏、权限、编码错误）都降级为空结构
            return {"tags": {}, "bindings": {}}

    def _save_to_disk(self) -> None:
        """原子写入磁盘：先写临时文件再 rename，避免崩溃损坏。"""
        # 加锁保证多线程下整个写流程串行，避免临时文件被覆盖
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

    def _make_tag(self, name: str, color: str) -> Tag:
        """构造 Tag 数据类实例（不写入存储），由 list_tags 内部使用。"""
        return Tag(
            name=name,
            color=color,
            created_at=self._now(),
            doc_count=0,
        )

    # -------------------------------------------------------------------------
    # 公共 API：标签 CRUD
    # -------------------------------------------------------------------------

    def create_tag(self, name: str, color: str = "#3B82F6") -> Tag:
        """
        创建新标签，重名时抛出 ``ValueError``。

        :param name: 标签名（全局唯一）
        :param color: 显示颜色，HEX 字符串
        :return: 新创建的 ``Tag`` 实例
        :raises ValueError: 标签已存在时
        """
        tags = self._ensure_tags()
        if not name or not isinstance(name, str):
            raise ValueError("标签名不能为空")
        if name in tags:
            raise ValueError(f"标签已存在: {name}")
        # 写入存储：保存 color 与 created_at，doc_count 启动为 0
        tags[name] = {
            "color": color,
            "created_at": self._now(),
        }
        self._save_to_disk()
        return Tag(name=name, color=color, created_at=tags[name]["created_at"], doc_count=0)

    def delete_tag(self, name: str) -> bool:
        """
        删除标签，并清除该标签的所有绑定。

        :param name: 标签名
        :return: 成功返回 ``True``，标签不存在返回 ``False``
        """
        tags = self._ensure_tags()
        if name not in tags:
            return False
        # 先删除标签定义
        del tags[name]
        # 再清除所有文档中对该标签的绑定
        bindings = self._ensure_bindings()
        for doc_name, tag_list in list(bindings.items()):
            if name in tag_list:
                tag_list.remove(name)
            # 绑定列表为空时清理，避免累积空键
            if not tag_list:
                del bindings[doc_name]
        self._save_to_disk()
        return True

    def list_tags(self) -> List[Tag]:
        """
        返回所有标签列表，按 ``doc_count`` 降序排序。

        :return: ``Tag`` 列表
        """
        tags = self._ensure_tags()
        bindings = self._ensure_bindings()
        # 统计每个标签在绑定中出现的次数
        count_map: Dict[str, int] = {name: 0 for name in tags}
        for tag_list in bindings.values():
            for tag_name in tag_list:
                if tag_name in count_map:
                    count_map[tag_name] += 1
        # 组装 Tag 数据类
        result: List[Tag] = []
        for name, payload in tags.items():
            result.append(Tag(
                name=name,
                color=payload.get("color", "#3B82F6"),
                created_at=payload.get("created_at", ""),
                doc_count=count_map.get(name, 0),
            ))
        # 按 doc_count 降序；并列时按 created_at 升序（先创建在前）
        result.sort(key=lambda t: (-t.doc_count, t.created_at))
        return result

    def rename_tag(self, old_name: str, new_name: str) -> bool:
        """
        重命名标签，同时更新所有文档的绑定关系。

        :param old_name: 原标签名
        :param new_name: 新标签名
        :return: 成功返回 ``True``，原标签不存在或新名冲突返回 ``False``
        """
        tags = self._ensure_tags()
        if old_name not in tags:
            return False
        # 新名已存在则不允许覆盖
        if new_name in tags and new_name != old_name:
            return False
        # 取出原标签定义并以新名写入
        payload = tags.pop(old_name)
        tags[new_name] = payload
        # 同步更新所有文档绑定
        bindings = self._ensure_bindings()
        for doc_name, tag_list in bindings.items():
            for idx, current in enumerate(tag_list):
                if current == old_name:
                    tag_list[idx] = new_name
        self._save_to_disk()
        return True

    # -------------------------------------------------------------------------
    # 公共 API：文档绑定
    # -------------------------------------------------------------------------

    def add_tag_to_doc(self, doc_name: str, tag_name: str) -> None:
        """
        给文档添加一个标签（幂等）：重复添加不会重复计数。

        :param doc_name: 文档名
        :param tag_name: 标签名（不存在时自动创建）
        """
        # 自动创建未定义的标签，避免 UI 层需要先建标签才能绑定
        if tag_name not in self._ensure_tags():
            self.create_tag(tag_name)
        bindings = self._ensure_bindings()
        # 初始化文档的标签列表
        if doc_name not in bindings:
            bindings[doc_name] = []
        tag_list = bindings[doc_name]
        # 幂等：已存在则直接返回
        if tag_name in tag_list:
            return
        tag_list.append(tag_name)
        self._save_to_disk()

    def remove_tag_from_doc(self, doc_name: str, tag_name: str) -> None:
        """
        移除文档的某个标签，绑定为空时清理空键。

        :param doc_name: 文档名
        :param tag_name: 标签名
        """
        bindings = self._ensure_bindings()
        if doc_name not in bindings:
            return
        tag_list = bindings[doc_name]
        if tag_name not in tag_list:
            return
        tag_list.remove(tag_name)
        # 列表为空时删除该键，避免存储中堆积空列表
        if not tag_list:
            del bindings[doc_name]
        self._save_to_disk()

    def set_doc_tags(self, doc_name: str, tag_names: List[str]) -> None:
        """
        设置文档的完整标签集合（替换式）：旧标签集合会被清空。

        :param doc_name: 文档名
        :param tag_names: 新的标签名列表（重复值会被去重）
        """
        # 自动创建未定义的标签
        for tag_name in tag_names:
            if tag_name and tag_name not in self._ensure_tags():
                self.create_tag(tag_name)
        bindings = self._ensure_bindings()
        # 去重并保持顺序，避免重复绑定影响 doc_count
        unique_tags = list(dict.fromkeys(t for t in tag_names if t))
        if unique_tags:
            bindings[doc_name] = unique_tags
        elif doc_name in bindings:
            # 传空列表则清理
            del bindings[doc_name]
        self._save_to_disk()

    def get_doc_tags(self, doc_name: str) -> List[str]:
        """
        获取文档绑定的所有标签名（按绑定顺序）。

        :param doc_name: 文档名
        :return: 标签名列表；无绑定时返回空列表
        """
        bindings = self._ensure_bindings()
        payload = bindings.get(doc_name, [])
        # 过滤非字符串项，兼容损坏数据
        return [t for t in payload if isinstance(t, str)]

    def filter_docs_by_tags(
        self,
        doc_names: List[str],
        include_tags: Optional[List[str]] = None,
        exclude_tags: Optional[List[str]] = None,
    ) -> List[str]:
        """
        按标签过滤文档列表（AND 语义）：
        - 文档必须包含 ``include_tags`` 中的全部标签
        - 文档不能包含 ``exclude_tags`` 中任何一个标签

        :param doc_names: 候选文档名列表
        :param include_tags: 必须包含的标签（None 表示不过滤）
        :param exclude_tags: 必须排除的标签（None 表示不过滤）
        :return: 过滤后的文档名列表（保持原顺序）
        """
        include_set = set(include_tags) if include_tags else set()
        exclude_set = set(exclude_tags) if exclude_tags else set()
        bindings = self._ensure_bindings()
        result: List[str] = []
        for doc_name in doc_names:
            doc_tags = set(bindings.get(doc_name, []))
            # 必须包含所有 include_tags
            if include_set and not include_set.issubset(doc_tags):
                continue
            # 不能包含任何 exclude_tags
            if exclude_set and (exclude_set & doc_tags):
                continue
            result.append(doc_name)
        return result

    def get_tag_cloud(self) -> List[Tag]:
        """
        返回标签云数据：按 ``doc_count`` 降序，最多 20 个。

        :return: ``Tag`` 列表（最多 20 项）
        """
        return self.list_tags()[:20]

    # -------------------------------------------------------------------------
    # 公共 API：统计
    # -------------------------------------------------------------------------

    def get_stats(self) -> Dict[str, int]:
        """
        返回整体统计信息：标签总数、绑定总数、被打标的文档数。

        :return: ``{"total_tags": N, "total_bindings": M, "tagged_docs": K}``
        """
        tags = self._ensure_tags()
        bindings = self._ensure_bindings()
        total_bindings = sum(len(v) for v in bindings.values() if isinstance(v, list))
        # 只统计有非空绑定的文档
        tagged_docs = sum(1 for v in bindings.values() if isinstance(v, list) and v)
        return {
            "total_tags": len(tags),
            "total_bindings": total_bindings,
            "tagged_docs": tagged_docs,
        }
