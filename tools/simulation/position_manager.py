"""
Position Manager
----------------
Manages position slots and liquidation price calculations.
"""
from dataclasses import dataclass
from typing import Dict, Tuple


def calculate_liquidation_price(
    direction: str, 
    entry_price: float, 
    quantity: float, 
    margin: float, 
    mmr: float
) -> float:
    """
    Approximates Binance isolated-margin liquidation math for a netted slot.
    """
    if quantity <= 0 or entry_price <= 0:
        return 0.0

    try:
        notional = entry_price * quantity
        if direction == 'LONG':
            denom = quantity * (1 - mmr)
            if denom <= 0:
                return 0.0
            return max(0.0, (notional - margin) / denom)
        else:
            denom = quantity * (1 + mmr)
            if denom <= 0:
                return 0.0
            return max(0.0, (notional + margin) / denom)
    except Exception:
        return 0.0


@dataclass
class PositionSlot:
    """
    Binance hedge mode mantığıyla LONG ve SHORT için ayrı net pozisyon slot'u.
    Aynı yönde gelen tüm işlemler bu slot altında birleşir.
    """
    direction: str
    total_quantity: float = 0.0
    total_notional: float = 0.0
    avg_entry_price: float = 0.0
    margin: float = 0.0
    liquidation_price: float = 0.0

    def is_active(self) -> bool:
        """Checks if position slot has an active position."""
        return self.total_quantity > 0 and self.margin > 0

    def preview_after_add(
        self, 
        quantity: float, 
        entry_price: float, 
        margin_added: float, 
        mmr: float
    ) -> Tuple[float, float, float, float]:
        """Previews position state after adding new position."""
        new_qty = self.total_quantity + quantity
        new_notional = self.total_notional + (entry_price * quantity)
        new_avg = (new_notional / new_qty) if new_qty > 0 else 0.0
        new_margin = self.margin + margin_added
        new_liq = calculate_liquidation_price(
            self.direction, new_avg, new_qty, new_margin, mmr
        )
        return new_qty, new_avg, new_margin, new_liq

    def apply_add(
        self, 
        quantity: float, 
        entry_price: float, 
        margin_added: float, 
        mmr: float
    ) -> None:
        """Adds position to slot and updates liquidation price."""
        self.total_quantity += quantity
        self.total_notional += entry_price * quantity
        if self.total_quantity > 0:
            self.avg_entry_price = self.total_notional / self.total_quantity
        else:
            self.avg_entry_price = 0.0
        self.margin += margin_added
        self.liquidation_price = calculate_liquidation_price(
            self.direction,
            self.avg_entry_price,
            self.total_quantity,
            self.margin,
            mmr
        )

    def apply_reduce(
        self, 
        quantity: float, 
        margin_released: float, 
        mmr: float
    ) -> None:
        """Reduces position from slot and updates liquidation price."""
        quantity = min(quantity, self.total_quantity)
        self.total_quantity -= quantity
        self.total_notional = self.avg_entry_price * self.total_quantity
        self.margin = max(0.0, self.margin - margin_released)

        if self.total_quantity <= 0 or self.margin <= 0:
            self.reset()
        else:
            self.liquidation_price = calculate_liquidation_price(
                self.direction,
                self.avg_entry_price,
                self.total_quantity,
                self.margin,
                mmr
            )

    def reset(self) -> None:
        """Resets position slot to empty state."""
        self.total_quantity = 0.0
        self.total_notional = 0.0
        self.avg_entry_price = 0.0
        self.margin = 0.0
        self.liquidation_price = 0.0


def get_position_slot(
    position_book: Dict[str, Dict[str, PositionSlot]], 
    symbol: str, 
    direction: str
) -> PositionSlot:
    """Gets or creates position slot for symbol/direction combination."""
    if symbol not in position_book:
        position_book[symbol] = {
            'LONG': PositionSlot('LONG'),
            'SHORT': PositionSlot('SHORT')
        }
    return position_book[symbol][direction]

