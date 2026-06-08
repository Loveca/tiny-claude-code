"""Long-term project memory stored as Markdown notes."""
from __future__ import annotations
import re
from datetime import datetime, timezone
from pathlib import Path

class MemoryManager:
    """Persist and retrieve simple keyword-matched memories."""

    def __init__(self, workspace: str | Path | None=None) -> None:
        self.workspace = Path(workspace or Path.cwd())
        self.memory_dir = self.workspace / ".tiny-claude-code" / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def save(self, category: str, title: str, content: str) -> Path:
        slug = self._slugify(title)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        path = self.memory_dir / f"{timestamp}-{slug}.md"
        text = (
            "---\n"
            f"category: {category}\n"
            f"title: {title}\n"
            f"created_at: {datetime.now(timezone.utc).isoformat()}\n"
            "---\n\n"
            f"{content.strip()}\n"
        )
        path.write_text(text, encoding="utf-8")
        self.build_index()
        return path

    def load_relevant(self, query: str, limit: int=5) -> list[str]:
        terms = {term.lower() for term in re.findall(r"[\w一-鿿]+", query)}
        if not terms:
            return []

        scored: list[tuple[int, str]] = []
        for path in self.memory_dir.glob("*.md"):
            if path.name == "MEMORY.md":
                continue
            text = path.read_text(encoding="utf-8")
            lowered = text.lower()
            score = sum(1 for term in terms if term in lowered)
            if score:
                scored.append((score, text))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [text for _, text in scored[:limit]]

    def build_index(self) -> Path:
        entries = []
        for path in sorted(self.memory_dir.glob("*.md")):
            if path.name == "MEMORY.md":
                continue
            meta = self._read_frontmatter(path.read_text(encoding="utf-8"))
            title = meta.get("title", path.stem)
            category = meta.get("category", "general")
            entries.append(f"- [{title}](./{path.name}) - {category}")

        index = self.memory_dir / "MEMORY.md"
        body = "# Project Memory\n\n" + (
            "\n".join(entries) if entries else "No memories yet."
        )
        index.write_text(body + "\n", encoding="utf-8")
        return index

    def build_system_context(self, query: str='') -> str:
        if query:
            memories = self.load_relevant(query, limit=5)
        else:
            memories = [
                path.read_text(encoding="utf-8")
                for path in sorted(self.memory_dir.glob("*.md"), reverse=True)
                if path.name != "MEMORY.md"
            ][:5]
        if not memories:
            return ""
        return "Relevant project memories:\n\n" + "\n\n".join(memories)

    def _read_frontmatter(self, text: str) -> dict[str, str]:
        if not text.startswith("---\n"):
            return {}
        _, frontmatter, _ = text.split("---", 2)
        meta = {}
        for line in frontmatter.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip()] = value.strip()
        return meta

    def _slugify(self, title: str) -> str:
        slug = re.sub(r"[^\w一-鿿]+", "-", title.lower()).strip("-")
        return slug or "memory"
