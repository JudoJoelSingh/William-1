"""
Memory Settings Module for William-1 Persistent Memory Layer (v0.3).
Centralises all configurable memory behaviour flags and reads/writes them
from the SQLite memory_settings table so they persist across restarts.

Settings managed here:
  memory_enabled        – bool  – master on/off toggle
  auto_capture          – bool  – auto-capture facts from conversation
  confirm_before_save   – bool  – ask user before every save
  retention_days        – int   – default days to keep episodic summaries
  top_k                 – int   – max memories injected into prompt
  max_token_budget      – int   – max ~tokens worth of memory context
  local_only            – bool  – block memory content from leaving machine
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from memory.memory_store import MemoryStore


_DEFAULTS: dict[str, Any] = {
    "memory_enabled": True,
    "auto_capture": True,
    "confirm_before_save": False,
    "retention_days": 30,
    "top_k": 5,
    "max_token_budget": 500,
    "local_only": False,
}


class MemorySettings:
    """
    Thin wrapper around the memory_settings SQLite table.
    All reads fall back to _DEFAULTS if the key is absent.
    """

    def __init__(self, store: "MemoryStore"):
        self._store = store
        self._bootstrap_defaults()

    def _bootstrap_defaults(self) -> None:
        """Write defaults only for keys not yet present in the DB."""
        for key, default_val in _DEFAULTS.items():
            existing = self._store.get_setting(key, default=None)   # type: ignore[arg-type]
            if existing is None:
                self._store.set_setting(key, str(default_val).lower()
                                        if isinstance(default_val, bool)
                                        else str(default_val))

    # ------------------------------------------------------------------
    # Typed getters
    # ------------------------------------------------------------------

    def get_bool(self, key: str) -> bool:
        raw = self._store.get_setting(key, str(_DEFAULTS.get(key, False)).lower())
        return raw.lower() in ("true", "1", "yes")

    def get_int(self, key: str) -> int:
        raw = self._store.get_setting(key, str(_DEFAULTS.get(key, 0)))
        try:
            return int(raw)
        except (ValueError, TypeError):
            return int(_DEFAULTS.get(key, 0))

    # ------------------------------------------------------------------
    # Named property accessors
    # ------------------------------------------------------------------

    @property
    def memory_enabled(self) -> bool:
        return self.get_bool("memory_enabled")

    @memory_enabled.setter
    def memory_enabled(self, value: bool) -> None:
        self._store.set_setting("memory_enabled", "true" if value else "false")

    @property
    def auto_capture(self) -> bool:
        return self.get_bool("auto_capture")

    @auto_capture.setter
    def auto_capture(self, value: bool) -> None:
        self._store.set_setting("auto_capture", "true" if value else "false")

    @property
    def confirm_before_save(self) -> bool:
        return self.get_bool("confirm_before_save")

    @confirm_before_save.setter
    def confirm_before_save(self, value: bool) -> None:
        self._store.set_setting("confirm_before_save", "true" if value else "false")

    @property
    def retention_days(self) -> int:
        return self.get_int("retention_days")

    @retention_days.setter
    def retention_days(self, value: int) -> None:
        self._store.set_setting("retention_days", str(max(0, int(value))))

    @property
    def top_k(self) -> int:
        return max(1, min(10, self.get_int("top_k")))

    @top_k.setter
    def top_k(self, value: int) -> None:
        self._store.set_setting("top_k", str(max(1, min(10, int(value)))))

    @property
    def max_token_budget(self) -> int:
        return max(100, self.get_int("max_token_budget"))

    @max_token_budget.setter
    def max_token_budget(self, value: int) -> None:
        self._store.set_setting("max_token_budget", str(max(100, int(value))))

    @property
    def local_only(self) -> bool:
        return self.get_bool("local_only")

    @local_only.setter
    def local_only(self, value: bool) -> None:
        self._store.set_setting("local_only", "true" if value else "false")

    # ------------------------------------------------------------------
    # Bulk helpers
    # ------------------------------------------------------------------

    def as_dict(self) -> dict:
        return {
            "memory_enabled": self.memory_enabled,
            "auto_capture": self.auto_capture,
            "confirm_before_save": self.confirm_before_save,
            "retention_days": self.retention_days,
            "top_k": self.top_k,
            "max_token_budget": self.max_token_budget,
            "local_only": self.local_only,
        }

    def apply_dict(self, updates: dict) -> list[str]:
        """Apply a dict of setting updates. Returns list of applied keys."""
        applied = []
        for key, value in updates.items():
            if key not in _DEFAULTS:
                continue
            if isinstance(_DEFAULTS[key], bool):
                setattr(self, key, str(value).lower() in ("true", "1", "yes"))
            elif isinstance(_DEFAULTS[key], int):
                setattr(self, key, int(value))
            else:
                self._store.set_setting(key, str(value))
            applied.append(key)
        return applied
