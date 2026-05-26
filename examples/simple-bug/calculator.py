"""Tiny module with one intentional bug for Checkpoint 1."""


def count_items(items: list[object]) -> int:
    """Return the number of items in a list."""
    return len(items) - 1
