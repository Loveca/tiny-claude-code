"""Tests for ch03: File Tools."""

from pathlib import Path

from tiny_claude_code.tools.file_read import ReadTool
from tiny_claude_code.tools.file_write import WriteTool
from tiny_claude_code.tools.search import SearchTool


def test_read_file_with_line_window(tmp_path: Path) -> None:
    target = tmp_path / "notes.txt"
    target.write_text("a\nb\nc\nd\n", encoding="utf-8")

    result = ReadTool().execute("notes.txt", offset=1, limit=2, workspace=str(tmp_path))

    assert result == "b\nc"


def test_read_lists_directory(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg").mkdir()

    result = ReadTool().execute(".", workspace=str(tmp_path))

    assert "a.py" in result
    assert "pkg/" in result


def test_read_rejects_path_escape(tmp_path: Path) -> None:
    result = ReadTool().execute("../secret.txt", workspace=str(tmp_path))

    assert "escapes workspace" in result


def test_write_creates_file(tmp_path: Path) -> None:
    result = WriteTool().execute("hello.py", content="print('hello')\n", workspace=str(tmp_path))

    assert "Wrote" in result
    assert (tmp_path / "hello.py").read_text(encoding="utf-8") == "print('hello')\n"


def test_write_edits_exact_text(tmp_path: Path) -> None:
    target = tmp_path / "hello.py"
    target.write_text("print('helo')\n", encoding="utf-8")

    result = WriteTool().execute(
        "hello.py",
        old_text="helo",
        new_text="hello",
        workspace=str(tmp_path),
    )

    assert "Edited" in result
    assert target.read_text(encoding="utf-8") == "print('hello')\n"


def test_write_edit_missing_old_text_does_not_modify(tmp_path: Path) -> None:
    target = tmp_path / "hello.py"
    target.write_text("print('hello')\n", encoding="utf-8")

    result = WriteTool().execute(
        "hello.py",
        old_text="missing",
        new_text="replacement",
        workspace=str(tmp_path),
    )

    assert "not found" in result
    assert target.read_text(encoding="utf-8") == "print('hello')\n"


def test_write_rejects_incomplete_edit(tmp_path: Path) -> None:
    target = tmp_path / "hello.py"
    target.write_text("print('hello')\n", encoding="utf-8")

    result = WriteTool().execute("hello.py", old_text="hello", workspace=str(tmp_path))

    assert "both old_text and new_text" in result
    assert target.read_text(encoding="utf-8") == "print('hello')\n"


def test_write_rejects_mixed_write_and_edit(tmp_path: Path) -> None:
    result = WriteTool().execute(
        "hello.py",
        content="new",
        old_text="old",
        new_text="new",
        workspace=str(tmp_path),
    )

    assert "either content" in result


def test_search_glob(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "b.txt").write_text("", encoding="utf-8")

    result = SearchTool().execute("*.py", workspace=str(tmp_path))

    assert "a.py" in result
    assert "b.txt" not in result


def test_search_grep(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("alpha\nneedle\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("beta\n", encoding="utf-8")

    result = SearchTool().execute("needle", type="grep", workspace=str(tmp_path))

    assert "a.py:2" in result
    assert "needle" in result


def test_read_truncates_large_file(tmp_path: Path) -> None:
    target = tmp_path / "big.txt"
    target.write_text("x" * 100, encoding="utf-8")

    result = ReadTool(max_output_chars=10).execute("big.txt", workspace=str(tmp_path))

    assert "[truncated]" in result


def test_search_limits_results(tmp_path: Path) -> None:
    for index in range(5):
        (tmp_path / f"{index}.py").write_text("", encoding="utf-8")

    result = SearchTool(max_results=2).execute("*.py", workspace=str(tmp_path))

    assert "[truncated]" in result
    assert len([line for line in result.splitlines() if line.endswith(".py")]) == 2
