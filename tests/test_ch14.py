"""Tests for ch14: real project challenges."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_buggy_python_project_contains_three_challenge_tests() -> None:
    test_file = ROOT / "examples" / "buggy-python-project" / "test_shopping_cart.py"
    text = test_file.read_text(encoding="utf-8")

    assert text.count("def test_") == 3
    assert "apply_discount" in text
    assert "cart_total" in text
    assert "is_free_shipping" in text


def test_buggy_python_project_initially_fails() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "examples/buggy-python-project", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "failed" in result.stdout


def test_tiny_web_app_challenge_has_missing_about_route() -> None:
    app_file = ROOT / "examples" / "tiny-web-app" / "app.py"
    test_file = ROOT / "examples" / "tiny-web-app" / "test_app.py"

    assert '"/about"' not in app_file.read_text(encoding="utf-8")
    assert '"/about"' in test_file.read_text(encoding="utf-8")


def test_tiny_web_app_initially_fails_one_challenge() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "examples/tiny-web-app", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "failed" in result.stdout
