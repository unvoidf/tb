"""
PriceChecker: Price check and TP/SL hit detection.
Target price check, stop-loss check helpers.
"""
from typing import Dict, Optional, Tuple
from utils.logger import LoggerManager


class PriceChecker:
    """Price check helper class."""
    
    def __init__(self):
        self.logger = LoggerManager().get_logger('PriceChecker')
    
    def check_tp_hit(
        self,
        current_price: float,
        tp_price: float,
        direction: str,
        tolerance: float = 0.001
    ) -> bool:
        """
        Checks for TP hit.
        
        Args:
            current_price: Current price
            tp_price: TP price
            direction: LONG/SHORT
            tolerance: Tolerance (0.001 = 0.1%)
            
        Returns:
            True if TP hit
        """
        if direction == 'LONG':
            # LONG: Price must reach or exceed TP
            return current_price >= tp_price * (1 - tolerance)
        else:  # SHORT
            # SHORT: Price must reach or pass TP
            return current_price <= tp_price * (1 + tolerance)
    
    def check_sl_hit(
        self,
        current_price: float,
        sl_price: float,
        direction: str,
        tolerance: float = 0.001
    ) -> bool:
        """
        Checks for SL hit.
        
        Args:
            current_price: Current price
            sl_price: SL price
            direction: LONG/SHORT
            tolerance: Tolerance
            
        Returns:
            True if SL hit
        """
        if direction == 'LONG':
            # LONG: Price must reach or drop below SL
            return current_price <= sl_price * (1 + tolerance)
        else:  # SHORT
            # SHORT: Price must reach or rise above SL
            return current_price >= sl_price * (1 - tolerance)
    
    def calculate_distance_to_level(
        self,
        current_price: float,
        target_price: float
    ) -> Tuple[float, float]:
        """
        Calculates distance to target.
        
        Args:
            current_price: Current price
            target_price: Target price
            
        Returns:
            (absolute_distance, percent_distance)
        """
        absolute_distance = target_price - current_price
        percent_distance = (absolute_distance / current_price) * 100
        
        return (absolute_distance, percent_distance)
    
    def get_nearest_level(
        self,
        current_price: float,
        levels: Dict[str, float],
        direction: str
    ) -> Optional[Tuple[str, float]]:
        """
        Finds the nearest level.
        
        Args:
            current_price: Current price
            levels: Levels dict (e.g., {'TP1': 100, 'TP2': 110})
            direction: LONG/SHORT
            
        Returns:
            (level_name, level_price) or None
        """
        if not levels:
            return None
        
        nearest = None
        min_distance = float('inf')
        
        for name, price in levels.items():
            distance = abs(price - current_price)
            if distance < min_distance:
                min_distance = distance
                nearest = (name, price)
        
        return nearest

