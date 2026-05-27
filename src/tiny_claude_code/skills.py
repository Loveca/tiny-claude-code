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

    def __init__(self, workspace: str | Path | None = None) -> None:
        self.workspace = Path(workspace or Path.cwd())
        self.skills_dir = self.workspace / ".tiny-claude-code" / "skills"

    def list_skills(self) -> list[SkillInfo]:
        if not self.skills_dir.exists():
            return []
        skills = []
        for path in sorted(self.skills_dir.glob("*/SKILL.md")):
            text = path.read_text(encoding="utf-8")
            skills.append(
                SkillInfo(
                    name=path.parent.name,
                    path=str(path),
                    summary=self._summary(text),
                )
            )
        return skills

    def load(self, skill_name: str) -> str:
        path = self.skills_dir / skill_name / "SKILL.md"
        if not path.exists():
            raise FileNotFoundError(f"skill not found: {skill_name}")
        return path.read_text(encoding="utf-8")

    def build_system_context(self, skill_names: list[str] | None = None) -> str:
        if skill_names:
            sections = [self.load(name) for name in skill_names]
        else:
            sections = [
                f"{skill.name}: {skill.summary}" for skill in self.list_skills()
            ]
        if not sections:
            return ""
        return "Available skills:\n\n" + "\n\n".join(sections)

    def _summary(self, text: str, max_chars: int = 400) -> str:
        lines = [line.strip("# ").strip() for line in text.splitlines() if line.strip()]
        summary = " ".join(lines)
        if len(summary) <= max_chars:
            return summary
        return summary[:max_chars].rstrip() + "..."
