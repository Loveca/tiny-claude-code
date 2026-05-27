"""Base class for all tools."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any

class Tool(ABC):
    """Minimal interface shared by all tools."""
    name: str

    @property
    @abstractmethod
    def schema(self) -> dict[str, Any]:
        """Anthropic tool schema shown to the model."""
        raise NotImplementedError('TODO: implement schema')

    @abstractmethod
    def execute(self, **kwargs: Any) -> str:
        """Run the tool with model-provided input."""
        raise NotImplementedError('TODO: implement execute')
