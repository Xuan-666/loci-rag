"""
设置持久化管理器 v4.3
=========================
管理用户偏好设置的持久化。

设置存储在 user_settings.json 文件中，包含：
- rerank_enabled: 是否启用 Rerank
- fallback_enabled: 是否启用 Fallback
- streaming_enabled: 是否启用流式输出
- typewriter_enabled: 是否启用打字机效果
- theme: 主题设置

使用方法：
    from settings_manager import SettingsManager, get_settings_manager

    manager = get_settings_manager()
    settings = manager.get_settings()
    manager.update_settings({"rerank_enabled": True})
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional

# 默认设置
DEFAULT_SETTINGS = {
    "rerank_enabled": True,
    "fallback_enabled": True,
    "streaming_enabled": True,
    "typewriter_enabled": True,
    "theme": "light",
}

# 设置文件路径（v5.0 重构：统一到 data/ 目录）
SETTINGS_FILE = "./data/user_settings.json"


class SettingsManager:
    """用户设置管理器"""

    def __init__(self, settings_file: str = SETTINGS_FILE):
        self.settings_file = Path(settings_file)
        self._settings: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """从文件加载设置"""
        if self.settings_file.exists():
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    self._settings = json.load(f)
                # 合并默认设置（确保新字段有默认值）
                for key, value in DEFAULT_SETTINGS.items():
                    if key not in self._settings:
                        self._settings[key] = value
            except (json.JSONDecodeError, IOError) as e:
                print(f"[Settings] 加载设置失败: {e}，使用默认设置")
                self._settings = DEFAULT_SETTINGS.copy()
        else:
            self._settings = DEFAULT_SETTINGS.copy()

    def _save(self) -> bool:
        """保存设置到文件"""
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, ensure_ascii=False, indent=2)
            return True
        except IOError as e:
            print(f"[Settings] 保存设置失败: {e}")
            return False

    def get_settings(self) -> Dict[str, Any]:
        """获取所有设置"""
        return self._settings.copy()

    def get_setting(self, key: str, default: Any = None) -> Any:
        """获取单个设置"""
        return self._settings.get(key, default)

    def update_settings(self, updates: Dict[str, Any]) -> bool:
        """
        批量更新设置

        Args:
            updates: 要更新的设置字典

        Returns:
            是否保存成功
        """
        for key, value in updates.items():
            if key in DEFAULT_SETTINGS or key.startswith("pref_"):
                # 去掉前缀
                clean_key = key.replace("pref_", "")
                self._settings[clean_key] = value
            else:
                self._settings[key] = value
        return self._save()

    def update_setting(self, key: str, value: Any) -> bool:
        """
        更新单个设置

        Args:
            key: 设置键
            value: 设置值

        Returns:
            是否保存成功
        """
        # 去掉前缀
        clean_key = key.replace("pref_", "")
        self._settings[clean_key] = value
        return self._save()

    def reset_to_default(self) -> bool:
        """重置为默认设置"""
        self._settings = DEFAULT_SETTINGS.copy()
        return self._save()


# 全局单例
_settings_manager: Optional[SettingsManager] = None


def get_settings_manager() -> SettingsManager:
    """获取全局设置管理器单例（每次调用都会读取最新的 SETTINGS_FILE，便于测试覆盖）"""
    global _settings_manager
    if _settings_manager is None:
        # 显式传入当前模块的 SETTINGS_FILE，避免被 __init__ 默认参数在导入时绑定的旧值"冻住"
        _settings_manager = SettingsManager(settings_file=SETTINGS_FILE)
    return _settings_manager
