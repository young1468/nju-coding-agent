"""A small command-line interface kept compatible for the demo."""

from __future__ import annotations

import argparse
from decimal import Decimal

from catalog import Catalog, Product
from checkout import checkout


def demo_catalog() -> Catalog:
    return Catalog([
        Product("BOOK", "Python Book", Decimal("100.00"), 5),
        Product("PEN", "Blue Pen", Decimal("0.10"), 20),
    ])


def parse_item(value: str) -> tuple[str, int]:
    sku, separator, raw_quantity = value.partition(":")
    if not separator:
        raise argparse.ArgumentTypeError("Items must use SKU:QUANTITY.")
    try:
        return sku, int(raw_quantity)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Quantity must be an integer.") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a demo order.")
    parser.add_argument("items", nargs="+", type=parse_item)
    parser.add_argument("--coupon")
    args = parser.parse_args(argv)
    receipt = checkout(demo_catalog(), args.items, coupon=args.coupon)
    print(f"items={receipt.item_count} total={receipt.total:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
