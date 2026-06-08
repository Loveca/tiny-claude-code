"""Session persistence for the interactive CLI."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def _serialize(obj: Any) -> Any:
    """Recursively convert Anthropic SDK objects to JSON-serializable types."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(item) for item in obj]
    if hasattr(obj, "model_dump"):
        return _serialize(obj.model_dump())
    if hasattr(obj, "__dict__"):
        return {k: _serialize(v) for k, v in obj.__dict__.items() if not k.startswith("_")}
    return str(obj)


class SessionManager:
    """Save and load conversations under .tiny-claude-code/sessions."""

    def __init__(self, workspace: str | Path | None=None) -> None:
        self.workspace = Path(workspace or Path.cwd())
        self.session_dir = self.workspace / ".tiny-claude-code" / "sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def new_session_id(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")

    def save(self, session_id: str, messages: list[dict[str, Any]], metadata: dict[str, Any] | None=None) -> Path:
        payload = {
            "id": session_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "metadata": metadata or {},
            "messages": _serialize(messages),
        }
        path = self.session_dir / f"{session_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load(self, session_id: str) -> list[dict[str, Any]]:
        path = self.session_dir / f"{session_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        return list(payload.get("messages", []))

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions = []
        for path in self.session_dir.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            sessions.append({
                "id": payload.get("id", path.stem),
                "updated_at": payload.get("updated_at", ""),
                "path": str(path),
                "metadata": payload.get("metadata", {}),
            })
        return sorted(sessions, key=lambda item: item["updated_at"], reverse=True)

    def latest_session_id(self) -> str | None:
        sessions = self.list_sessions()
        if not sessions:
            return None
        return str(sessions[0]["id"])
