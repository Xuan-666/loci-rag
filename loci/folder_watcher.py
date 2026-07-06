"""
folder_watcher
==============
后台线程监控指定目录，当支持的后缀（PDF/DOCX/...）文件被创建、修改或移动进来时，
经过防抖（debounce）后批量回调用户提供的 callback。

设计要点：
- 使用 watchdog 的 PollingObserver（Windows 上更稳定，不依赖 ReadDirectoryChangesW）
- 子线程运行 Observer，主线程不阻塞
- 同一文件短时间内多次事件（on_created + on_modified + on_moved）合并为一次回调
- callback 放在 try/except 中，异常只打印警告，不影响监控线程
- 共享状态用 threading.Lock 保护
"""

import os
import threading
import time
import traceback
from pathlib import Path
from typing import Callable, Dict, List, Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver


# =============================================================================
# 1. watchdog 事件处理器（私有）
# =============================================================================

class _DebouncedHandler(FileSystemEventHandler):
    """将 watchdog 事件转发给 FolderWatcher 的内部方法。"""

    def __init__(self, watcher: "FolderWatcher") -> None:
        """保存外层 watcher 引用。"""
        super().__init__()
        self._watcher = watcher

    def _dispatch(self, event: FileSystemEvent) -> None:
        """过滤目录事件后转发，非目录事件才入队。"""
        if event.is_directory:
            return
        self._watcher._on_file_event(event)

    def on_created(self, event: FileSystemEvent) -> None:
        """文件创建事件。"""
        self._dispatch(event)

    def on_modified(self, event: FileSystemEvent) -> None:
        """文件修改事件。"""
        self._dispatch(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        """
        文件移动事件。
        watchdog 的 MovedEvent 使用 dest_path（新位置），复制大文件时
        经常会先创建临时文件再移动到目标，所以这里取目标路径入队。
        """
        target = getattr(event, "dest_path", None) or getattr(event, "target_path", None)
        if not target:
            return
        wrapped = _FakeEvent(src_path=target, is_directory=False)
        self._watcher._on_file_event(wrapped)


class _FakeEvent:
    """测试或 on_moved 场景下构造的轻量事件对象，仅暴露 watchdog 用到的字段。"""

    def __init__(self, src_path: str, is_directory: bool = False) -> None:
        """保存路径与是否为目录。"""
        self.src_path = src_path
        self.is_directory = is_directory


# =============================================================================
# 2. 文件夹监控器
# =============================================================================

class FolderWatcher:
    """后台线程监控文件夹，新文件出现时自动回调。"""

    # 支持的文档后缀（小写，含点号）
    SUPPORTED_EXTS = {
        ".pdf", ".docx", ".doc", ".xlsx", ".xls",
        ".pptx", ".ppt", ".txt", ".md", ".html",
        ".htm", ".json", ".xml", ".csv", ".rtf",
    }

    def __init__(
        self,
        watch_dir: str,
        callback: Callable[[List[str]], None],
        debounce_seconds: float = 2.0,
        use_polling: bool = True,
        polling_interval: float = 0.5,
    ) -> None:
        """
        初始化监控器（不启动）。

        参数:
            watch_dir: 监控目录路径；不存在会自动创建
            callback: 文件就绪后的回调函数，接收文件路径列表
            debounce_seconds: 防抖时间（秒），同一文件多次事件合并
            use_polling: True 使用 PollingObserver（Windows 稳定），False 用原生 Observer
            polling_interval: 轮询间隔（仅在 use_polling=True 时生效）
        """
        self._watch_dir = watch_dir
        self._callback = callback
        self._debounce_seconds = debounce_seconds
        self._use_polling = use_polling
        self._polling_interval = polling_interval

        # 线程安全：共享状态都用同一把锁保护
        self._lock = threading.Lock()
        self._observer: Optional[object] = None
        self._running = False

        # 待处理文件路径 -> 首次入队时间戳
        self._pending: Dict[str, float] = {}
        # 防抖定时器
        self._flush_timer: Optional[threading.Timer] = None

    # ------------------------- 生命周期 -------------------------

    def start(self) -> None:
        """启动后台监控线程（Observer）。"""
        with self._lock:
            if self._running:
                return
            # 确保目录存在
            os.makedirs(self._watch_dir, exist_ok=True)

            handler = _DebouncedHandler(self)
            if self._use_polling:
                self._observer = PollingObserver(timeout=self._polling_interval)
            else:
                self._observer = Observer()

            self._observer.schedule(handler, self._watch_dir, recursive=False)
            self._observer.daemon = True
            self._observer.start()
            self._running = True

        print(f"[Watcher] 监控目录: {self._watch_dir}")

    def stop(self) -> None:
        """停止监控，等待线程结束（graceful shutdown）。"""
        with self._lock:
            if not self._running:
                return
            # 取消尚未触发的防抖定时器
            if self._flush_timer is not None:
                self._flush_timer.cancel()
                self._flush_timer = None
            observer = self._observer
            self._running = False

        # 在锁外等待停止，避免死锁
        if observer is not None:
            try:
                observer.stop()
                observer.join(timeout=5)
            except Exception as e:
                print(f"[Watcher] 停止 Observer 异常: {e}")
        print(f"[Watcher] 已停止监控: {self._watch_dir}")

    def is_running(self) -> bool:
        """返回是否正在运行。"""
        with self._lock:
            return self._running

    # ------------------------- 事件入口 -------------------------

    def _on_file_event(self, event) -> None:
        """
        watchdog 事件回调：过滤目录事件、过滤非支持扩展名、加入待处理队列。
        该方法在 Observer 线程中执行，必须快速返回。
        """
        path = getattr(event, "src_path", None)
        if not path:
            return
        if getattr(event, "is_directory", False):
            return

        ext = os.path.splitext(path)[1].lower()
        if ext not in self.SUPPORTED_EXTS:
            return

        # 文件可能还在写入中，等到 debounce 之后再确认
        with self._lock:
            now = time.monotonic()
            if path not in self._pending:
                self._pending[path] = now
            self._schedule_flush_locked()

    # ------------------------- 防抖 & 刷新 -------------------------

    def _schedule_flush_locked(self) -> None:
        """
        安排一次防抖刷新（必须在持有 _lock 时调用）。
        每次新事件都重置定时器，从而合并短时间内的多次事件。
        """
        if self._flush_timer is not None:
            self._flush_timer.cancel()
        self._flush_timer = threading.Timer(self._debounce_seconds, self._flush)
        self._flush_timer.daemon = True
        self._flush_timer.start()

    def _flush(self) -> None:
        """
        定时器到期回调：取出待处理队列，做存在性校验后调用 callback。
        在定时器线程中执行。
        """
        with self._lock:
            pending = self._pending
            self._pending = {}
            self._flush_timer = None

        if not pending:
            return

        # 过滤：文件可能已被删除；只保留仍然存在的
        ready_files: List[str] = []
        for path in pending.keys():
            if os.path.exists(path) and os.path.isfile(path):
                ready_files.append(path)

        if not ready_files:
            return

        # 回调异常不影响监控线程
        try:
            self._callback(ready_files)
        except Exception as e:
            print(f"[Watcher] ⚠️ callback 执行异常: {e}")
            traceback.print_exc()
