"""
RiskRewardCalculator: R-based distance calculation utility.
Calculates TP/SL levels in terms of risk unit (R).
"""
from typing import Dict, Optional
from utils.logger import LoggerManager


class RiskRewardCalculator:
    """R-based risk/reward calculator."""
    
    def __init__(self):
        """Initializes RiskRewardCalculator."""
        self.logger = LoggerManager().get_logger('RiskRewardCalculator')
    
    def calculate_r_distances(
        self,
        signal_price: float,
        direction: str,
        tp1: Optional[float],
        tp2: Optional[float],
        tp3: Optional[float],
        sl1: Optional[float],
        sl2: Optional[float]
    ) -> Dict[str, Optional[float]]:
        """
        Calculates TP/SL levels in terms of R.
        R = |signal_price - sl2_price|
        
        Args:
            signal_price: Signal price
            direction: LONG/SHORT
            tp1, tp2, tp3: TP levels
            sl1, sl2: SL levels
            
        Returns:
            {
                'tp1_distance_r': float,
                'tp2_distance_r': float,
                'tp3_distance_r': float,
                'sl1_distance_r': float,
                'sl2_distance_r': float (always -1.0)
            }
        """
        if sl2 is None:
            self.logger.debug("SL2 None, cannot calculate R distance")
            return {
                'tp1_distance_r': None,
                'tp2_distance_r': None,
                'tp3_distance_r': None,
                'sl1_distance_r': None,
                'sl2_distance_r': None
            }
        
        r = abs(signal_price - sl2)
        if r == 0:
            self.logger.warning("R = 0, cannot calculate distance")
            return {
                'tp1_distance_r': None,
                'tp2_distance_r': None,
                'tp3_distance_r': None,
                'sl1_distance_r': None,
                'sl2_distance_r': None
            }
        
        def calc_r(price, is_tp):
            """Calculate R distance for a single level."""
            if price is None:
                return None
            if direction == 'LONG':
                if is_tp:
                    return (price - signal_price) / r  # TP: positive (up)
                else:
                    return -(signal_price - price) / r  # SL: negative (down)
            else:  # SHORT
                if is_tp:
                    return (signal_price - price) / r  # TP: positive (down)
                else:
                    return -(price - signal_price) / r  # SL: negative (up)
        
        result = {
            'tp1_distance_r': calc_r(tp1, True),
            'tp2_distance_r': calc_r(tp2, True),
            'tp3_distance_r': calc_r(tp3, True),
            'sl1_distance_r': calc_r(sl1, False),
            'sl2_distance_r': -1.0  # SL2 always -1R (by definition)
        }

        def _format_r(value: Optional[float]) -> str:
            return f"{value:.2f}R" if value is not None else "None"

        self.logger.debug(
            "R distances: signal=%s, direction=%s, R=%.6f, TP1=%s, TP2=%s, TP3=%s, SL1=%s",
            signal_price,
            direction,
            r,
            _format_r(result['tp1_distance_r']),
            _format_r(result['tp2_distance_r']),
            _format_r(result['tp3_distance_r']),
            _format_r(result['sl1_distance_r'])
        )
        
        return result

