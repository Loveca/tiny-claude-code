"""Example tool plugin for ch15."""

from __future__ import annotations

from typing import Any

from tiny_claude_code.tools.base import Tool


class WeatherTool(Tool):
    name = "weather"

    @property
    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": "Return a deterministic demo weather report.",
            "input_schema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        }

    def execute(self, city: str) -> str:
        return f"{city}: sunny, 22C"


def register_tools(registry: Any) -> None:
    registry.register(WeatherTool())
