"""
Liquidation Safety Filter
-------------------------
Utility functions for fast liquidation risk control.
Tests different risk/leverage combinations for a signal and
filters those with very small difference between SL and liquidation.
"""
import os
from typing import List, Dict, Tuple, Optional
from tools.simulation.position_manager import calculate_liquidation_price
from utils.logger import LoggerManager


class LiquidationSafetyFilter:
    """Filter for liquidation risk control."""
    
    def __init__(self, mmr: float = 0.004, min_sl_liq_buffer: Optional[float] = None):
        """
        Initializes LiquidationSafetyFilter.
        
        Args:
            mmr: Maintenance Margin Rate (default: 0.004 = 0.4%)
            min_sl_liq_buffer: Minimum buffer between SL and liquidation (default: reads from .env or 0.01 = 1%)
        """
        self.mmr = mmr
        self.min_sl_liq_buffer = min_sl_liq_buffer or self._load_min_sl_liq_buffer()
        self.logger = LoggerManager().get_logger('LiquidationSafetyFilter')
    
    def filter_unsafe_combinations(
        self,
        entry_price: float,
        sl_price: float,
        direction: str,
        balance: float,
        risk_ranges: List[float],
        leverage_ranges: List[int]
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Tests risk/leverage combinations and returns safe ones.
        
        Args:
            entry_price: Entry price
            sl_price: Stop loss price
            direction: LONG or SHORT
            balance: Account balance
            risk_ranges: List of risk percentages to test (e.g. [0.5, 1.0, 1.5, ...])
            leverage_ranges: List of leverage values to test (e.g. [1, 2, 3, ...])
            
        Returns:
            (safe_combinations, unsafe_combinations) tuple
            Each combination: {'risk': float, 'leverage': int, 'liq_price': float, 'sl_liq_diff_pct': float}
        """
        safe_combinations = []
        unsafe_combinations = []
        
        # SL distance
        sl_distance_pct = abs(entry_price - sl_price) / entry_price
        if sl_distance_pct == 0:
            self.logger.warning("SL distance is 0, cannot calculate liquidation")
            return safe_combinations, unsafe_combinations
        
        for risk_percent in risk_ranges:
            for leverage in leverage_ranges:
                # Calculate position size
                risk_amount = balance * (risk_percent / 100)
                position_size_usd = risk_amount / sl_distance_pct
                margin_required = position_size_usd / leverage
                quantity = position_size_usd / entry_price
                
                # Calculate liquidation price
                liq_price = calculate_liquidation_price(
                    direction=direction,
                    entry_price=entry_price,
                    quantity=quantity,
                    margin=margin_required,
                    mmr=self.mmr
                )
                
                if liq_price <= 0:
                    continue
                
                # Calculate difference between SL and liquidation
                if direction == 'LONG':
                    # LONG: SL < Entry, Liq < Entry
                    # Difference between SL and Liq
                    sl_liq_diff = abs(sl_price - liq_price)
                    sl_liq_diff_pct = (sl_liq_diff / entry_price) * 100
                else:
                    # SHORT: SL > Entry, Liq > Entry
                    sl_liq_diff = abs(sl_price - liq_price)
                    sl_liq_diff_pct = (sl_liq_diff / entry_price) * 100
                
                combination = {
                    'risk': risk_percent,
                    'leverage': leverage,
                    'liq_price': liq_price,
                    'sl_liq_diff_pct': sl_liq_diff_pct,
                    'margin_required': margin_required,
                    'position_size_usd': position_size_usd
                }
                
                # Buffer check: There must be at least 1% difference between SL and liquidation
                if sl_liq_diff_pct < (self.min_sl_liq_buffer * 100):
                    unsafe_combinations.append(combination)
                    self.logger.debug(
                        f"Unsafe: Risk {risk_percent}% | Leverage {leverage}x | "
                        f"SL-Liq diff: {sl_liq_diff_pct:.2f}% < {self.min_sl_liq_buffer*100:.1f}%"
                    )
                else:
                    safe_combinations.append(combination)
        
        return safe_combinations, unsafe_combinations
    
    def find_optimal_safe_combination(
        self,
        entry_price: float,
        sl_price: float,
        direction: str,
        balance: float,
        risk_ranges: Optional[List[float]] = None,
        leverage_ranges: Optional[List[int]] = None
    ) -> Optional[Dict]:
        """
        Finds the best among safe combinations.
        
        Args:
            entry_price: Entry price
            sl_price: Stop loss price
            direction: LONG or SHORT
            balance: Account balance
            risk_ranges: Risk percentages to test (default: [0.5, 1.0, 1.5, 2.0, 2.5, 3.0])
            leverage_ranges: Leverage values to test (default: [1, 2, 3, 4, 5, 7, 10])
            
        Returns:
            Best safe combination or None
        """
        if risk_ranges is None:
            # Load from .env or use defaults
            risk_ranges = self._load_risk_ranges()
        
        if leverage_ranges is None:
            # Load from .env or use defaults
            leverage_ranges = self._load_leverage_ranges()
        
        safe_combinations, unsafe_combinations = self.filter_unsafe_combinations(
            entry_price=entry_price,
            sl_price=sl_price,
            direction=direction,
            balance=balance,
            risk_ranges=risk_ranges,
            leverage_ranges=leverage_ranges
        )
        
        if not safe_combinations:
            self.logger.warning(
                f"No safe combinations found for {direction} signal "
                f"(Entry: ${entry_price:.4f}, SL: ${sl_price:.4f})"
            )
            return None
        
        # Select best combination: Highest leverage, highest risk (but safe)
        # Priority: Those with large enough SL-Liq difference, then high leverage
        best = max(
            safe_combinations,
            key=lambda x: (x['sl_liq_diff_pct'], x['leverage'], x['risk'])
        )
        
        self.logger.info(
            f"Optimal safe combination: Risk {best['risk']}% | Leverage {best['leverage']}x | "
            f"SL-Liq diff: {best['sl_liq_diff_pct']:.2f}%"
        )
        
        return best
    
    def calculate_liquidation_risk_percentage(
        self,
        entry_price: float,
        sl_price: float,
        direction: str,
        balance: float,
        risk_ranges: Optional[List[float]] = None,
        leverage_ranges: Optional[List[int]] = None
    ) -> float:
        """
        Calculates liquidation risk percentage.
        
        Args:
            entry_price: Entry price
            sl_price: Stop loss price
            direction: LONG or SHORT
            balance: Account balance
            risk_ranges: Risk percentages to test (default: reads from .env)
            leverage_ranges: Leverage values to test (default: reads from .env)
            
        Returns:
            Liquidation risk percentage (0-100): (Unsafe combinations / All combinations) * 100
        """
        if risk_ranges is None:
            risk_ranges = self._load_risk_ranges()
        
        if leverage_ranges is None:
            leverage_ranges = self._load_leverage_ranges()
        
        safe_combinations, unsafe_combinations = self.filter_unsafe_combinations(
            entry_price=entry_price,
            sl_price=sl_price,
            direction=direction,
            balance=balance,
            risk_ranges=risk_ranges,
            leverage_ranges=leverage_ranges
        )
        
        total_combinations = len(safe_combinations) + len(unsafe_combinations)
        
        if total_combinations == 0:
            return 0.0
        
        risk_percentage = (len(unsafe_combinations) / total_combinations) * 100
        return round(risk_percentage, 2)
    
    def _load_risk_ranges(self) -> List[float]:
        """Load risk ranges from .env or use defaults."""
        default = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
        val = os.getenv('SAFETYFILTER_RISK_RANGES')
        if not val:
            return default
        try:
            return [float(x.strip()) for x in val.split(',') if x.strip()]
        except Exception:
            return default
    
    def _load_leverage_ranges(self) -> List[int]:
        """Load leverage ranges from .env or use defaults."""
        default = [1, 2, 3, 4, 5, 7, 10, 12, 15, 20]
        val = os.getenv('SAFETYFILTER_LEVERAGE_RANGES')
        if not val:
            return default
        try:
            return [int(x.strip()) for x in val.split(',') if x.strip()]
        except Exception:
            return default
    
    def _load_min_sl_liq_buffer(self) -> float:
        """Load minimum SL-Liq buffer from .env or use default."""
        try:
            val = os.getenv('SAFETYFILTER_MIN_SL_LIQ_BUFFER')
            return float(val) if val is not None else 0.01
        except Exception:
            return 0.01

