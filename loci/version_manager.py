"""
向量库版本管理器

设计要点：
- snapshot_dir 默认放在 vector_store 同级的 vector_store_versions/
- 每次 snapshot 复制 vector_store/ 全部内容到 <version_id>/ 子目录
- 每个版本目录里同时保存 _meta.json 便于回放
- 全局 _versions_index.json 提供快速索引（label / size / created_at）
- rollback 采用"先备份再替换"的两段式：
    1. 把当前 vector_store 复制到 _backup_xxx/ 临时目录
    2. 把目标版本复制到 _restore_xxx/ 临时目录
    3. 原子替换：清空 vector_store 后，把 _restore 内容搬回
    4. 任何阶段失败都尽量回滚到 _backup，保证原数据不丢
"""
from __future__ import annotations

import json
import os
import random
import shutil
import string
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# 索引文件名 / 元信息文件名（带下划线前缀便于排序在前）
INDEX_FILE = "_versions_index.json"
META_FILE = "_meta.json"
# 临时目录前缀（用于 rollback 过程中的备份/还原）
BACKUP_PREFIX = "_backup_"
RESTORE_PREFIX = "_restore_"


@dataclass
class VersionRecord:
    """一个版本快照的元信息"""
    version_id: str       # 形如 "v_20260610_100500_abc123"
    label: str            # 用户可命名（如 "auto" / "manual" / "before_delete_xxx"）
    created_at: str       # ISO 时间
    size_mb: float        # 快照大小
    note: str = ""        # 可选备注
    doc_count: int = 0    # 该版本包含的文档数（仅元信息）


class VersionManager:
    """向量库版本管理：快照 / 回滚 / 清理 / 查询"""

    def __init__(self, vector_store_path: str, snapshot_dir: Optional[str] = None) -> None:
        """
        初始化版本管理器

        参数:
            vector_store_path: 当前向量库目录（FAISS 文件所在）
            snapshot_dir:      快照存储目录（默认 ./vector_store_versions/）
        """
        self.vector_store_path = Path(vector_store_path)
        # 默认快照目录 = vector_store 同级的 vector_store_versions
        if snapshot_dir is None:
            self.snapshot_dir = self.vector_store_path.parent / "vector_store_versions"
        else:
            self.snapshot_dir = Path(snapshot_dir)
        # 确保快照根目录与索引文件存在
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.snapshot_dir / INDEX_FILE
        if not self.index_path.exists():
            self._write_index({})
        # 加载已有快照的最大序号，用于在 created_at 相同时提供稳定排序
        existing_idx = self._read_index()
        self._max_seq = max(
            [int(v.get("seq", 0)) for v in existing_idx.values()] + [0]
        )

    # ------------------------------------------------------------------ #
    # 内部工具方法
    # ------------------------------------------------------------------ #
    def _generate_version_id(self) -> str:
        """生成版本 ID：v_YYYYMMDD_HHMMSS_{6位随机字符}"""
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return f"v_{ts}_{rand}"

    def _iso_now(self) -> str:
        """当前时间的 ISO 字符串（微秒级，减少同秒冲突）"""
        return datetime.now().isoformat(timespec="microseconds")

    def _dir_size_mb(self, path: Path) -> float:
        """递归统计目录占用空间（MB，保留 2 位小数）"""
        total_bytes = 0
        # 遍历目录中的所有文件累加大小
        for root, _, files in os.walk(path):
            for name in files:
                try:
                    total_bytes += os.path.getsize(Path(root) / name)
                except OSError:
                    # 单个文件无法读取时跳过，避免整体失败
                    continue
        return round(total_bytes / (1024 * 1024), 2)

    def _read_index(self) -> Dict[str, Dict[str, Any]]:
        """读取全局索引；不存在或损坏时返回空 dict"""
        if not self.index_path.exists():
            return {}
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_index(self, data: Dict[str, Dict[str, Any]]) -> None:
        """把全局索引写回磁盘"""
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _save_meta(self, version_dir: Path, record: VersionRecord) -> None:
        """把 VersionRecord 写入版本目录下的 _meta.json"""
        meta_path = version_dir / META_FILE
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(asdict(record), f, ensure_ascii=False, indent=2)

    def _load_meta(self, version_dir: Path) -> Optional[VersionRecord]:
        """从 _meta.json 还原 VersionRecord；失败时返回 None"""
        meta_path = version_dir / META_FILE
        if not meta_path.exists():
            return None
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return VersionRecord(**data)
        except (json.JSONDecodeError, OSError, TypeError):
            return None

    def _safe_rmtree(self, path: Optional[Path]) -> None:
        """安全删除目录；路径为 None 或不存在时静默忽略"""
        if path is None or not path.exists():
            return
        try:
            shutil.rmtree(path)
        except OSError:
            # 删除失败时不影响主流程
            pass

    def _backup_current(self) -> Optional[Path]:
        """把当前 vector_store 内容复制到 snapshot 下的临时备份目录"""
        if not self.vector_store_path.exists():
            return None
        try:
            if not any(self.vector_store_path.iterdir()):
                return None
        except OSError:
            return None
        backup_path = self.snapshot_dir / f"{BACKUP_PREFIX}{self._generate_version_id()}"
        try:
            shutil.copytree(self.vector_store_path, backup_path)
            return backup_path
        except Exception:
            self._safe_rmtree(backup_path)
            return None

    def _swap_with(self, source: Path) -> bool:
        """用 source 目录的内容替换 vector_store/ 的内容"""
        if not source.exists():
            return False
        # 确保目标目录存在
        self.vector_store_path.mkdir(parents=True, exist_ok=True)
        # 清空目标目录现有内容（保留目录本身）
        for child in list(self.vector_store_path.iterdir()):
            try:
                if child.is_file() or child.is_symlink():
                    child.unlink()
                else:
                    shutil.rmtree(child)
            except OSError:
                continue
        # 把 source 内容逐项复制到 vector_store（跳过元信息文件）
        try:
            for item in source.iterdir():
                if item.name == META_FILE:
                    continue
                dest = self.vector_store_path / item.name
                if item.is_dir():
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
        except Exception:
            return False
        return True

    # ------------------------------------------------------------------ #
    # 对外 API
    # ------------------------------------------------------------------ #
    def snapshot(self, label: str = "auto", note: str = "",
                 doc_count: int = 0) -> VersionRecord:
        """
        创建当前向量库的完整快照

        - 复制 vector_store/ 内容到 snapshot_dir/<version_id>/
        - 失败时清理半成品目录并抛 RuntimeError
        """
        if not self.vector_store_path.exists():
            raise RuntimeError(f"vector_store 目录不存在: {self.vector_store_path}")
        version_id = self._generate_version_id()
        target = self.snapshot_dir / version_id
        # 复制前先确保目标不存在
        try:
            shutil.copytree(self.vector_store_path, target)
        except Exception as e:
            # 清理可能残留的半成品
            self._safe_rmtree(target)
            raise RuntimeError(f"快照创建失败: {e}") from e
        # 计算大小并写入元信息
        size_mb = self._dir_size_mb(target)
        record = VersionRecord(
            version_id=version_id,
            label=label,
            created_at=self._iso_now(),
            size_mb=size_mb,
            note=note,
            doc_count=doc_count,
        )
        self._save_meta(target, record)
        # 同步更新全局索引（包含 seq 序号用于稳定排序）
        self._max_seq += 1
        idx = self._read_index()
        idx[version_id] = {
            "label": label,
            "created_at": record.created_at,
            "size_mb": size_mb,
            "doc_count": doc_count,
            "note": note,
            "seq": self._max_seq,
        }
        self._write_index(idx)
        return record

    def list_versions(self) -> List[VersionRecord]:
        """返回所有版本（按 created_at 倒序，相同时间用 seq 序号兜底）"""
        idx = self._read_index()
        # 暂存 (record, seq) 元组，便于用 seq 做稳定排序
        records_with_seq: List[tuple] = []
        for vid, info in idx.items():
            seq = int(info.get("seq", 0))
            vdir = self.snapshot_dir / vid
            # 优先从 _meta.json 读取（更权威）
            meta = self._load_meta(vdir)
            if meta is not None:
                records_with_seq.append((meta, seq))
            else:
                # 兜底：仅用索引中的信息构造记录
                records_with_seq.append((VersionRecord(
                    version_id=vid,
                    label=info.get("label", "unknown"),
                    created_at=info.get("created_at", ""),
                    size_mb=float(info.get("size_mb", 0.0)),
                    note=info.get("note", ""),
                    doc_count=int(info.get("doc_count", 0)),
                ), seq))
        # 主排序 created_at 倒序，seq 序号作为稳定兜底
        records_with_seq.sort(key=lambda x: (x[0].created_at, x[1]), reverse=True)
        return [r for r, _ in records_with_seq]

    def rollback(self, version_id: str) -> bool:
        """
        回滚到指定版本

        步骤：
            1. 把当前 vector_store 备份到临时目录
            2. 把目标版本复制到另一个临时目录
            3. 替换 vector_store
            4. 任何阶段失败都尝试用 backup 恢复
        """
        target_dir = self.snapshot_dir / version_id
        if not target_dir.exists() or not target_dir.is_dir():
            return False
        # 1. 备份当前状态
        backup_path = self._backup_current()
        # 2. 准备目标内容到临时目录
        restore_path = self.snapshot_dir / f"{RESTORE_PREFIX}{self._generate_version_id()}"
        try:
            shutil.copytree(target_dir, restore_path)
        except Exception:
            self._safe_rmtree(restore_path)
            self._safe_rmtree(backup_path)
            return False
        # 3. 原子替换 vector_store
        if not self._swap_with(restore_path):
            # 失败：尝试从 backup 还原
            if backup_path is not None:
                self._swap_with(backup_path)
            self._safe_rmtree(restore_path)
            self._safe_rmtree(backup_path)
            return False
        # 4. 清理临时目录
        self._safe_rmtree(restore_path)
        self._safe_rmtree(backup_path)
        return True

    def delete_version(self, version_id: str) -> bool:
        """删除指定版本的快照目录与索引项"""
        target_dir = self.snapshot_dir / version_id
        if not target_dir.exists():
            return False
        shutil.rmtree(target_dir)
        # 从索引中移除
        idx = self._read_index()
        if version_id in idx:
            idx.pop(version_id, None)
            self._write_index(idx)
        return True

    def cleanup_old_versions(self, keep_last: int = 5) -> int:
        """只保留最近 N 个版本，删除更早的，返回实际删除数量"""
        records = self.list_versions()
        # list_versions 已按时间倒序，超出部分就是要删的
        to_delete = records[keep_last:]
        deleted = 0
        for record in to_delete:
            if self.delete_version(record.version_id):
                deleted += 1
        return deleted

    def get_stats(self) -> Dict[str, Any]:
        """返回汇总统计信息"""
        records = self.list_versions()
        if not records:
            return {
                "total_versions": 0,
                "total_size_mb": 0.0,
                "oldest": "",
                "newest": "",
            }
        total_size = round(sum(r.size_mb for r in records), 2)
        # 列表已按 created_at 倒序：第 0 个最新，最后一个最旧
        return {
            "total_versions": len(records),
            "total_size_mb": total_size,
            "oldest": records[-1].created_at,
            "newest": records[0].created_at,
        }
