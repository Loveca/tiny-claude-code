"""ch21: the CLI writes streamed text immediately instead of at the end."""

from __future__ import annotations

from tiny_claude_code.cli import StreamPrinter


def test_text_is_written_before_the_turn_ends(capsys) -> None:
    printer = StreamPrinter()

    printer("Hel")
    assert capsys.readouterr().out == "Hel"
    printer("lo")
    assert capsys.readouterr().out == "lo"


def test_no_newline_is_added_between_deltas(capsys) -> None:
    printer = StreamPrinter()

    printer("Hel")
    printer("lo")
    printer("\n")

    assert capsys.readouterr().out == "Hello\n"


def test_final_response_is_recognised_as_shown() -> None:
    printer = StreamPrinter()
    printer("Hello")
    printer("\n")

    assert printer.shown_finally("Hello")


def test_unstreamed_final_message_is_not_reported_as_shown() -> None:
    printer = StreamPrinter()
    printer("Working on it")
    printer("\n")

    # The max-turns message is returned by the loop without being streamed.
    assert not printer.shown_finally("Error: maximum number of turns reached.")


def test_empty_response_is_never_reported_as_shown() -> None:
    printer = StreamPrinter()
    printer("Hello")
    printer("\n")

    assert not printer.shown_finally("")
