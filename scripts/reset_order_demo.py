"""Restore the intentionally broken order_demo implementation for recording."""

from __future__ import annotations

import argparse
from pathlib import Path


BROKEN_PRICING = '''"""Pricing rules for the order demo."""

from __future__ import annotations

from decimal import Decimal

from catalog import Catalog

TAX_RATE = Decimal("0.08")
COUPONS = {"SAVE10": Decimal("10.00"), "WELCOME5": Decimal("5.00")}


def calculate_total(catalog: Catalog, items: list[tuple[str, int]], coupon: str | None = None) -> float:
    """Return the order total.

    The demo deliberately uses float arithmetic and subtracts the coupon after
    tax. Both behaviors conflict with the documented business rules.
    """
    subtotal = sum(float(catalog.product(sku).price) * quantity for sku, quantity in items)
    discount = COUPONS.get(coupon or "", Decimal("0.00"))
    if coupon and coupon not in COUPONS:
        raise ValueError(f"Unknown coupon: {coupon}")
    return round(subtotal * float(Decimal("1") + TAX_RATE) - float(discount), 2)
'''

BROKEN_CATALOG = '''"""In-memory product catalog used by the order demo."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


class OutOfStockError(ValueError):
    """Raised when an order requests more stock than is available."""


@dataclass
class Product:
    sku: str
    name: str
    price: Decimal
    stock: int


class Catalog:
    def __init__(self, products: list[Product]) -> None:
        self._products = {product.sku: product for product in products}

    def product(self, sku: str) -> Product:
        try:
            return self._products[sku]
        except KeyError as error:
            raise ValueError(f"Unknown SKU: {sku}") from error

    def reserve(self, items: list[tuple[str, int]]) -> None:
        """Reserve each requested item.

        This implementation intentionally has a transaction bug: it decrements
        earlier items before discovering a later item has insufficient stock.
        """
        for sku, quantity in items:
            product = self.product(sku)
            if quantity <= 0:
                raise ValueError("Quantity must be positive.")
            if product.stock < quantity:
                raise OutOfStockError(f"Insufficient stock for {sku}.")
            product.stock -= quantity
'''


def reset_order_demo(workspace: Path) -> tuple[Path, Path]:
    target = Path(workspace).expanduser().resolve()
    required_files = (target / "pricing.py", target / "catalog.py")
    if not target.is_dir() or not (target / "tests").is_dir() or not all(path.is_file() for path in required_files):
        raise ValueError("Target must be an order_demo directory containing pricing.py, catalog.py, and tests/.")
    (target / "pricing.py").write_text(BROKEN_PRICING, encoding="utf-8")
    (target / "catalog.py").write_text(BROKEN_CATALOG, encoding="utf-8")
    return target / "pricing.py", target / "catalog.py"


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore the broken order_demo baseline.")
    default = Path(__file__).resolve().parents[1] / "demo_workspace" / "order_demo"
    parser.add_argument("--workspace", type=Path, default=default)
    args = parser.parse_args()
    try:
        pricing, catalog = reset_order_demo(args.workspace)
    except ValueError as error:
        parser.error(str(error))
    print(f"Reset order_demo implementation: {pricing.parent}")
    print(f"Changed: {pricing.name}, {catalog.name}")
    print("Expected baseline after pytest: 5 failed, 1 passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
