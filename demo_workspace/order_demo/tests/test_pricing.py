from decimal import Decimal

import pytest

from catalog import Catalog, Product
from pricing import calculate_total


def make_catalog() -> Catalog:
    return Catalog([
        Product("BOOK", "Python Book", Decimal("100.00"), 5),
        Product("PEN", "Blue Pen", Decimal("0.10"), 20),
    ])


def test_coupon_is_applied_before_tax_using_decimal() -> None:
    total = calculate_total(make_catalog(), [("BOOK", 1)], coupon="SAVE10")

    assert total == Decimal("97.20")
    assert isinstance(total, Decimal)


def test_decimal_prices_are_rounded_to_two_places() -> None:
    total = calculate_total(make_catalog(), [("PEN", 3)])

    assert total == Decimal("0.32")


def test_unknown_coupon_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown coupon"):
        calculate_total(make_catalog(), [("BOOK", 1)], coupon="NOT_REAL")
