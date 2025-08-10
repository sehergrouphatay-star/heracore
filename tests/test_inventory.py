import os
import sys

import pytest

# Ensure the project root is on the Python path when tests are executed from the
# tests directory.
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core import Inventory, NegativeStockError


def test_fifo_issue_cost():
    inv = Inventory()
    inv.receive(item_id=1, warehouse_id=1, qty=5, cost_per_unit=2.0)
    inv.receive(item_id=1, warehouse_id=1, qty=5, cost_per_unit=3.0)

    cost, _ = inv.issue(item_id=1, warehouse_id=1, qty=7)
    # 5 units at 2.0 + 2 units at 3.0 => 10 + 6 = 16
    assert cost == pytest.approx(16.0)
    assert inv.stock_on_hand(1, 1) == pytest.approx(3.0)
    assert inv.stock_value(1, 1) == pytest.approx(9.0)


def test_negative_stock_rejected():
    inv = Inventory()
    inv.receive(item_id=1, warehouse_id=1, qty=2, cost_per_unit=1.0)
    with pytest.raises(NegativeStockError):
        inv.issue(item_id=1, warehouse_id=1, qty=3)


def test_transfer_between_warehouses():
    inv = Inventory()
    inv.receive(item_id=1, warehouse_id=1, qty=4, cost_per_unit=5.0)
    inv.transfer(item_id=1, from_wh=1, to_wh=2, qty=3)

    assert inv.stock_on_hand(1, 1) == pytest.approx(1.0)
    assert inv.stock_on_hand(1, 2) == pytest.approx(3.0)
    # Cost should be preserved in destination lot
    assert inv.stock_value(1, 2) == pytest.approx(15.0)
