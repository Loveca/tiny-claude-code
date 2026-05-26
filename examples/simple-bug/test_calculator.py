from calculator import count_items


def test_count_empty_list() -> None:
    assert count_items([]) == 0


def test_count_three_items() -> None:
    assert count_items(["a", "b", "c"]) == 3
