"""Long-term project memory stored as Markdown notes."""
from __future__ import annotations
import re
from datetime import datetime, timezone
from pathlib import Path

class MemoryManager:
    """Persist and retrieve simple keyword-matched memories."""

    def __init__(self, workspace: str | Path | None=None) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def save(self, category: str, title: str, content: str) -> Path:
        raise NotImplementedError('TODO: implement save')

    def load_relevant(self, query: str, limit: int=5) -> list[str]:
        raise NotImplementedError('TODO: implement load_relevant')

    def build_index(self) -> Path:
        raise NotImplementedError('TODO: implement build_index')

    def build_system_context(self, query: str='') -> str:
        raise NotImplementedError('TODO: implement build_system_context')

    def _read_frontmatter(self, text: str) -> dict[str, str]:
        raise NotImplementedError('TODO: implement _read_frontmatter')

    def _slugify(self, title: str) -> str:
        raise NotImplementedError('TODO: implement _slugify')
