"""Dynamic tool plugin loading."""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any


@dataclass
class PluginResult:
    path: str
    loaded: bool
    message: str


class PluginLoader:
    """Load Python files that expose register_tools(registry)."""

    def __init__(self, plugin_dir: str | Path | None = None) -> None:
        self.plugin_dir = Path(plugin_dir) if plugin_dir else None

    def load_plugins(self, registry: Any) -> list[PluginResult]:
        if self.plugin_dir is None or not self.plugin_dir.exists():
            return []

        results = []
        for path in sorted(self.plugin_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            results.append(self._load_one(path, registry))
        return results

    def _load_one(self, path: Path, registry: Any) -> PluginResult:
        try:
            module = self._import_module(path)
            register = getattr(module, "register_tools", None)
            if register is None:
                return PluginResult(str(path), False, "missing register_tools")
            register(registry)
            return PluginResult(str(path), True, "loaded")
        except Exception as exc:  # noqa: BLE001 - plugin boundary.
            return PluginResult(str(path), False, str(exc))

    def _import_module(self, path: Path) -> ModuleType:
        name = f"tiny_claude_code_plugin_{path.stem}"
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot import plugin: {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

