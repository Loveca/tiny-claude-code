#!/usr/bin/env python3
"""Development tool for tiny-claude-code.

Usage:
    python scripts/dev.py test --ch 01     Run tests for chapter 01
    python scripts/dev.py test --all       Run all tests
    python scripts/dev.py run              Run your agent (real LLM)
    python scripts/dev.py run --ref        Run reference implementation
    python scripts/dev.py check            Check remaining TODOs
"""

import argparse
import os
import shutil
import subprocess
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS_ALL_DIR = os.path.join(PROJECT_ROOT, "tests_all")
TESTS_DIR = os.path.join(PROJECT_ROOT, "tests")
SRC_DIR = os.path.join(PROJECT_ROOT, "src")


def cmd_test(args):
    """Run tests for a specific chapter or all chapters."""
    if args.all:
        # Copy all test files
        for f in os.listdir(TESTS_ALL_DIR):
            if f.startswith("test_") and f.endswith(".py"):
                shutil.copy2(os.path.join(TESTS_ALL_DIR, f), os.path.join(TESTS_DIR, f))
        subprocess.run(
            [sys.executable, "-m", "pytest", TESTS_DIR, "-v"],
            cwd=PROJECT_ROOT,
        )
        return

    if not args.ch:
        print("Specify --ch N or --all")
        return

    ch_num = int(args.ch)
    test_file = f"test_ch{ch_num:02d}.py"
    src_path = os.path.join(TESTS_ALL_DIR, test_file)

    if not os.path.exists(src_path):
        print(f"No test file found for chapter {ch_num}: {test_file}")
        sys.exit(1)

    # Copy test file to working tests directory
    dst_path = os.path.join(TESTS_DIR, test_file)
    shutil.copy2(src_path, dst_path)

    # Run pytest
    subprocess.run(
        [sys.executable, "-m", "pytest", dst_path, "-v"],
        cwd=PROJECT_ROOT,
    )


def cmd_run(args):
    """Run the agent with real LLM."""
    if args.ref:
        package = "tiny_claude_code_ref"
    else:
        package = "tiny_claude_code"

    module_path = os.path.join(SRC_DIR, package, "cli.py")
    env = os.environ.copy()
    env["PYTHONPATH"] = SRC_DIR

    subprocess.run(
        [sys.executable, module_path],
        cwd=PROJECT_ROOT,
        env=env,
    )


def cmd_check(args):
    """Check remaining TODOs / NotImplementedError in skeleton code."""
    skeleton_dir = os.path.join(SRC_DIR, "tiny_claude_code")
    todos = []
    for root, dirs, files in os.walk(skeleton_dir):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if "raise NotImplementedError" in line or "TODO" in line:
                        rel = os.path.relpath(fpath, PROJECT_ROOT)
                        todos.append(f"  {rel}:{i}  {line.strip()}")

    if not todos:
        print("All TODOs completed!")
    else:
        print(f"Remaining TODOs ({len(todos)}):")
        for t in todos:
            print(t)


def main():
    parser = argparse.ArgumentParser(description="tiny-claude-code dev tool")
    sub = parser.add_subparsers(dest="command")

    # test
    test_parser = sub.add_parser("test", help="Run tests")
    test_parser.add_argument("--ch", type=str, help="Chapter number (e.g. 01)")
    test_parser.add_argument("--all", action="store_true", help="Run all tests")

    # run
    run_parser = sub.add_parser("run", help="Run the agent")
    run_parser.add_argument("--ref", action="store_true", help="Use reference implementation")

    # check
    sub.add_parser("check", help="Check remaining TODOs")

    args = parser.parse_args()

    if args.command == "test":
        cmd_test(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "check":
        cmd_check(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
