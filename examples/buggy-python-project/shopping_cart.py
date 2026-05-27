"""Small intentionally buggy shopping cart module for ch14."""

from __future__ import annotations


def apply_discount(price: float, percent: float) -> float:
    """Return price after applying a percentage discount."""
    return price - percent


def cart_total(items: list[dict[str, float]]) -> float:
    """Return total price for items with price and quantity."""
    return sum(item["price"] for item in items)


def is_free_shipping(total: float) -> bool:
    """Free shipping starts at 50."""
    return total > 50
