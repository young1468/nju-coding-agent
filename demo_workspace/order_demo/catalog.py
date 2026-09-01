"""In-memory product catalog used by the order demo."""

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
        """Reserve each requested item atomically.

        All stock levels are validated before any stock is changed, so a failed
        order never partially reserves inventory.
        """
        # Validate every request before mutating anything.
        requested: dict[str, int] = {}
        for sku, quantity in items:
            product = self.product(sku)
            if quantity <= 0:
                raise ValueError("Quantity must be positive.")
            requested[sku] = requested.get(sku, 0) + quantity
            if product.stock < requested[sku]:
                raise OutOfStockError(f"Insufficient stock for {sku}.")

        # All validations passed; now reserve the stock.
        for sku, quantity in items:
            self.product(sku).stock -= quantity
