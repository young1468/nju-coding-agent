from pathlib import Path

import pytest

from scripts.reset_order_demo import BROKEN_CATALOG, BROKEN_PRICING, reset_order_demo


def test_reset_order_demo_restores_only_two_implementation_files(tmp_path: Path) -> None:
    target = tmp_path / "order_demo"
    (target / "tests").mkdir(parents=True)
    pricing = target / "pricing.py"
    catalog = target / "catalog.py"
    tests = target / "tests" / "test_demo.py"
    pricing.write_text("correct pricing", encoding="utf-8")
    catalog.write_text("correct catalog", encoding="utf-8")
    tests.write_text("keep me", encoding="utf-8")

    reset_order_demo(target)

    assert pricing.read_text(encoding="utf-8") == BROKEN_PRICING
    assert catalog.read_text(encoding="utf-8") == BROKEN_CATALOG
    assert tests.read_text(encoding="utf-8") == "keep me"


def test_reset_order_demo_rejects_wrong_target(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="order_demo"):
        reset_order_demo(tmp_path)
