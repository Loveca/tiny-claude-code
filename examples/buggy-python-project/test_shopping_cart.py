from shopping_cart import apply_discount, cart_total, is_free_shipping


def test_apply_discount_uses_percentage() -> None:
    assert apply_discount(100, 20) == 80
    assert apply_discount(50, 10) == 45


def test_cart_total_uses_quantity() -> None:
    items = [
        {"price": 10, "quantity": 2},
        {"price": 5, "quantity": 3},
    ]

    assert cart_total(items) == 35


def test_free_shipping_threshold_is_inclusive() -> None:
    assert is_free_shipping(50)
    assert is_free_shipping(51)
    assert not is_free_shipping(49.99)
