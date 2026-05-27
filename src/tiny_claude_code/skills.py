"""Skill loading from .tiny-claude-code/skills."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass
class SkillInfo:
    name: str
    path: str
    summary: str

class SkillLoader:
    """Discover and load local SKILL.md files."""

    def __init__(self, workspace: str | Path | None=None) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def list_skills(self) -> list[SkillInfo]:
        raise NotImplementedError('TODO: implement list_skills')

    def load(self, skill_name: str) -> str:
        raise NotImplementedError('TODO: implement load')

    def build_system_context(self, skill_names: list[str] | None=None) -> str:
        raise NotImplementedError('TODO: implement build_system_context')

    def _summary(self, text: str, max_chars: int=400) -> str:
        raise NotImplementedError('TODO: implement _summary')
