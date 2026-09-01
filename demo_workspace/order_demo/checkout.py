"""Checkout orchestration for the order demo."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from catalog import Catalog
from pricing import calculate_total


@dataclass(frozen=True)
class Receipt:
    total: Decimal
    item_count: int
    coupon: str | None


def checkout(catalog: Catalog, items: list[tuple[str, int]], coupon: str | None = None) -> Receipt:
    """Calculate an order and reserve its inventory."""
    total = calculate_total(catalog, items, coupon)
    catalog.reserve(items)
    return Receipt(total=total, item_count=sum(quantity for _, quantity in items), coupon=coupon)
