"""Pricing rules for the order demo."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from catalog import Catalog

TAX_RATE = Decimal("0.08")
COUPONS = {"SAVE10": Decimal("10.00"), "WELCOME5": Decimal("5.00")}


def calculate_total(catalog: Catalog, items: list[tuple[str, int]], coupon: str | None = None) -> Decimal:
    """Return the order total.

    The total is computed entirely with Decimal, the coupon is applied before
    tax, and the final amount is rounded to two decimal places.
    """
    subtotal = sum((catalog.product(sku).price * quantity for sku, quantity in items), Decimal("0"))
    discount = COUPONS.get(coupon or "", Decimal("0.00"))
    if coupon and coupon not in COUPONS:
        raise ValueError(f"Unknown coupon: {coupon}")
    discounted = subtotal - discount
    total = discounted * (Decimal("1") + TAX_RATE)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
