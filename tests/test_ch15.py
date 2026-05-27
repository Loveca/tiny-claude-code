"""Tests for ch15: skills and plugins."""

from __future__ import annotations

from pathlib import Path

from tiny_claude_code.cli import build_system_prompt, handle_skill_command
from tiny_claude_code.skills import SkillLoader
from tiny_claude_code.tools import ToolRegistry, create_default_registry
from tiny_claude_code.tools.plugin import PluginLoader


def write_skill(root: Path, name: str, text: str) -> None:
    path = root / ".tiny-claude-code" / "skills" / name
    path.mkdir(parents=True)
    (path / "SKILL.md").write_text(text, encoding="utf-8")


def test_skill_loader_lists_available_skills(tmp_path) -> None:
    write_skill(tmp_path, "python-debugging", "# Python Debugging\n\nRun tests first.")

    skills = SkillLoader(tmp_path).list_skills()

    assert skills[0].name == "python-debugging"
    assert "Run tests first" in skills[0].summary


def test_skill_loader_loads_full_skill(tmp_path) -> None:
    write_skill(tmp_path, "python-debugging", "# Python Debugging\n\nRun tests first.")

    text = SkillLoader(tmp_path).load("python-debugging")

    assert "# Python Debugging" in text


def test_skill_context_can_include_summaries_or_full_skills(tmp_path) -> None:
    write_skill(tmp_path, "python-debugging", "# Python Debugging\n\nRun tests first.")
    loader = SkillLoader(tmp_path)

    summary_context = loader.build_system_context()
    full_context = loader.build_system_context(["python-debugging"])

    assert "python-debugging" in summary_context
    assert "# Python Debugging" in full_context


def test_system_prompt_includes_skill_context(tmp_path) -> None:
    system = build_system_prompt(tmp_path, skill_context="Available skills:\nPython")

    assert "Available skills" in system


def test_skill_command_lists_and_shows_skills(tmp_path) -> None:
    write_skill(tmp_path, "python-debugging", "# Python Debugging\n\nRun tests first.")
    loader = SkillLoader(tmp_path)

    assert "python-debugging" in handle_skill_command(loader, "/skill list")
    assert "Run tests first" in handle_skill_command(loader, "/skill show python-debugging")


def test_plugin_loader_registers_tool(tmp_path) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "demo.py").write_text(
        """
from tiny_claude_code.tools.base import Tool

class DemoTool(Tool):
    name = "demo"
    @property
    def schema(self):
        return {"name": self.name, "input_schema": {"type": "object"}}
    def execute(self):
        return "ok"

def register_tools(registry):
    registry.register(DemoTool())
""".strip(),
        encoding="utf-8",
    )
    registry = ToolRegistry()

    results = PluginLoader(plugin_dir).load_plugins(registry)

    assert results[0].loaded
    assert registry.dispatch("demo", {}) == "ok"


def test_plugin_loader_skips_invalid_plugin(tmp_path) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "bad.py").write_text("x = 1\n", encoding="utf-8")
    registry = ToolRegistry()

    results = PluginLoader(plugin_dir).load_plugins(registry)

    assert not results[0].loaded
    assert "missing register_tools" in results[0].message


def test_default_registry_loads_plugins(tmp_path) -> None:
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    (plugin_dir / "demo.py").write_text(
        """
from tiny_claude_code.tools.base import Tool

class DemoTool(Tool):
    name = "demo"
    @property
    def schema(self):
        return {"name": self.name, "input_schema": {"type": "object"}}
    def execute(self):
        return "ok"

def register_tools(registry):
    registry.register(DemoTool())
""".strip(),
        encoding="utf-8",
    )

    registry = create_default_registry(tmp_path, plugin_dir=plugin_dir)

    assert registry.dispatch("demo", {}) == "ok"
