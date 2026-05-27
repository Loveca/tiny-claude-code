"""Session persistence for the interactive CLI."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

class SessionManager:
    """Save and load conversations under .tiny-claude-code/sessions."""

    def __init__(self, workspace: str | Path | None=None) -> None:
        raise NotImplementedError('TODO: implement __init__')

    def new_session_id(self) -> str:
        raise NotImplementedError('TODO: implement new_session_id')

    def save(self, session_id: str, messages: list[dict[str, Any]], metadata: dict[str, Any] | None=None) -> Path:
        raise NotImplementedError('TODO: implement save')

    def load(self, session_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError('TODO: implement load')

    def list_sessions(self) -> list[dict[str, Any]]:
        raise NotImplementedError('TODO: implement list_sessions')

    def latest_session_id(self) -> str | None:
        raise NotImplementedError('TODO: implement latest_session_id')
