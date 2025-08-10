from __future__ import annotations

"""Core inventory logic for HREAXS.

This module implements a small in-memory inventory system that focuses on the
most critical business rules from the project specification:

* Stock is stored in lots per item and warehouse.
* Cost of goods is calculated using the FIFO (first‑in, first‑out) method.
* Movements that would result in negative stock are rejected.
* Transfers are atomic and keep lot level cost information.

The goal of this file is to provide a reliable core that can later be wired to
APIs or a database layer.  Keeping it lightweight makes it easy to unit test and
reason about the behaviour of the system.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple


@dataclass
class StockLot:
    """Represents a quantity of an item received at a specific cost."""

    item_id: int
    warehouse_id: int
    qty: float
    cost_per_unit: float
    received_at: datetime = field(default_factory=datetime.utcnow)
    lot_no: Optional[str] = None
    expiry_date: Optional[datetime] = None
    id: int = field(default_factory=int)


@dataclass
class Consumption:
    """Internal helper describing consumption from a lot."""

    lot: StockLot
    qty: float

    @property
    def cost(self) -> float:
        return self.qty * self.lot.cost_per_unit


class InventoryError(Exception):
    """Base error class for inventory issues."""


class NegativeStockError(InventoryError):
    """Raised when an operation would result in negative stock."""


class Inventory:
    """In-memory inventory implementation with FIFO valuation."""

    def __init__(self) -> None:
        # item_id -> warehouse_id -> list[StockLot]
        self._lots: Dict[int, Dict[int, List[StockLot]]] = {}
        self._lot_seq = 1

    # ------------------------------------------------------------------
    # Utility methods
    def _next_lot_id(self) -> int:
        lot_id = self._lot_seq
        self._lot_seq += 1
        return lot_id

    def _get_lots(self, item_id: int, warehouse_id: int) -> List[StockLot]:
        return self._lots.setdefault(item_id, {}).setdefault(warehouse_id, [])

    # ------------------------------------------------------------------
    # Public API
    def receive(
        self,
        item_id: int,
        warehouse_id: int,
        qty: float,
        cost_per_unit: float,
        *,
        lot_no: Optional[str] = None,
        expiry_date: Optional[datetime] = None,
    ) -> StockLot:
        """Register receipt of stock for an item.

        Returns the created :class:`StockLot` instance.
        """

        if qty <= 0:
            raise ValueError("Quantity must be positive")
        lot = StockLot(
            id=self._next_lot_id(),
            item_id=item_id,
            warehouse_id=warehouse_id,
            qty=qty,
            cost_per_unit=cost_per_unit,
            lot_no=lot_no,
            expiry_date=expiry_date,
        )
        self._get_lots(item_id, warehouse_id).append(lot)
        return lot

    def _consume(
        self, item_id: int, warehouse_id: int, qty: float
    ) -> List[Consumption]:
        """Consume stock following FIFO and return list of consumed lots."""

        lots = self._get_lots(item_id, warehouse_id)
        total_available = sum(l.qty for l in lots)
        if qty > total_available + 1e-9:  # small tolerance for float operations
            raise NegativeStockError(
                f"Cannot consume {qty} from item {item_id} in warehouse {warehouse_id}; "
                f"only {total_available} available"
            )

        remaining = qty
        consumed: List[Consumption] = []
        while remaining > 1e-9 and lots:
            lot = lots[0]
            take = min(lot.qty, remaining)
            lot.qty -= take
            remaining -= take
            consumed.append(Consumption(lot=lot, qty=take))
            if lot.qty <= 1e-9:
                lots.pop(0)
        return consumed

    def issue(
        self, item_id: int, warehouse_id: int, qty: float
    ) -> Tuple[float, List[Consumption]]:
        """Issue stock from a warehouse.

        Returns a tuple of ``(cost_of_goods, consumptions)``.
        """

        if qty <= 0:
            raise ValueError("Quantity must be positive")
        consumed = self._consume(item_id, warehouse_id, qty)
        cost = sum(c.cost for c in consumed)
        return cost, consumed

    def transfer(
        self, item_id: int, from_wh: int, to_wh: int, qty: float
    ) -> float:
        """Transfer stock between warehouses.

        The function consumes stock from ``from_wh`` and creates equivalent
        lots in ``to_wh`` with the same unit cost.  Returns the total cost of
        transferred goods.
        """

        cost, consumptions = self.issue(item_id, from_wh, qty)
        for c in consumptions:
            # recreate lot in destination warehouse with same cost
            self.receive(
                item_id=item_id,
                warehouse_id=to_wh,
                qty=c.qty,
                cost_per_unit=c.lot.cost_per_unit,
                lot_no=c.lot.lot_no,
                expiry_date=c.lot.expiry_date,
            )
        return cost

    # ------------------------------------------------------------------
    # Reporting helpers
    def stock_on_hand(self, item_id: int, warehouse_id: Optional[int] = None) -> float:
        """Return stock on hand for an item.

        If ``warehouse_id`` is ``None`` the quantity across all warehouses is
        returned.
        """

        if warehouse_id is None:
            return sum(
                lot.qty
                for wh_lots in self._lots.get(item_id, {}).values()
                for lot in wh_lots
            )
        return sum(l.qty for l in self._get_lots(item_id, warehouse_id))

    def stock_value(self, item_id: int, warehouse_id: Optional[int] = None) -> float:
        """Return the FIFO valuation of stock on hand for an item."""

        if warehouse_id is None:
            return sum(
                lot.qty * lot.cost_per_unit
                for wh_lots in self._lots.get(item_id, {}).values()
                for lot in wh_lots
            )
        return sum(
            l.qty * l.cost_per_unit for l in self._get_lots(item_id, warehouse_id)
        )


__all__ = ["Inventory", "InventoryError", "NegativeStockError", "StockLot"]
