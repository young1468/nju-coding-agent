from decimal import Decimal

import pytest

from catalog import Catalog, OutOfStockError, Product
from checkout import checkout


def test_failed_order_does_not_partially_reserve_stock() -> None:
    catalog = Catalog([
        Product("BOOK", "Python Book", Decimal("100.00"), 1),
        Product("PEN", "Blue Pen", Decimal("0.10"), 0),
    ])

    with pytest.raises(OutOfStockError):
        checkout(catalog, [("BOOK", 1), ("PEN", 1)])

    assert catalog.product("BOOK").stock == 1
    assert catalog.product("PEN").stock == 0


def test_successful_order_reserves_stock_and_returns_receipt() -> None:
    catalog = Catalog([Product("BOOK", "Python Book", Decimal("100.00"), 2)])

    receipt = checkout(catalog, [("BOOK", 1)], coupon="WELCOME5")

    assert receipt.total == Decimal("102.60")
    assert receipt.item_count == 1
    assert catalog.product("BOOK").stock == 1
