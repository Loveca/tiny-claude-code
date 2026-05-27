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

    def __init__(self, plugin_dir: str | Path | None=None) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def load_plugins(self, registry: Any) -> list[PluginResult]:
        raise NotImplementedError('TODO: implement load_plugins')

    def _load_one(self, path: Path, registry: Any) -> PluginResult:
        raise NotImplementedError('TODO: implement _load_one')

    def _import_module(self, path: Path) -> ModuleType:
        raise NotImplementedError('TODO: implement _import_module')
