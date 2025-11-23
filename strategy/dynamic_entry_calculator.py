"""
DynamicEntryCalculator: Class calculating three levels of entry.
Calculates IMMEDIATE, OPTIMAL and CONSERVATIVE entry levels.
"""
from typing import Dict, Optional, Tuple
from analysis.fibonacci_calculator import FibonacciCalculator
from strategy.position_calculator import PositionCalculator
from config.constants import SL_MULTIPLIER
from utils.logger import LoggerManager


class DynamicEntryCalculator:
    """Calculates dynamic entry levels."""
    
    def __init__(self, fib_calculator: FibonacciCalculator, position_calc: PositionCalculator):
        """
        Initializes DynamicEntryCalculator.
        
        Args:
            fib_calculator: Fibonacci calculator
            position_calc: Position calculator
        """
        self.fib_calc = fib_calculator
        self.position_calc = position_calc
        self.logger = LoggerManager().get_logger('DynamicEntryCalculator')
    
    def calculate_entry_levels(
        self, 
        symbol: str, 
        direction: str, 
        current_price: float,
        df: Optional[object] = None,
        atr: Optional[float] = None,
        timeframe: Optional[str] = None
    ) -> Dict[str, Dict]:
        """
        Calculates three levels of entry.
        
        Args:
            symbol: Trading pair (e.g. BTC/USDT)
            direction: LONG/SHORT
            current_price: Current price
            df: OHLCV DataFrame (optional)
            atr: ATR value (optional)
            
        Returns:
            Entry levels dict
        """
        try:
            self.logger.debug(f"calculate_entry_levels: {symbol} {direction} @ {current_price}")
            
            # IMMEDIATE entry (current price)
            immediate_entry = self._calculate_immediate_entry(current_price, direction, timeframe, atr)
            
            # OPTIMAL entry (ATR priority, enrich with Fib 0.618 if suitable)
            optimal_entry = self._calculate_optimal_entry(
                symbol, direction, current_price, df, atr, timeframe
            )
            
            # CONSERVATIVE entry (ATR based safe level)
            conservative_entry = self._calculate_conservative_entry(
                symbol, direction, current_price, df, atr, timeframe
            )
            
            # Risk/Reward calculations
            immediate_rr = self._calculate_risk_reward(immediate_entry, direction, atr)
            optimal_rr = self._calculate_risk_reward(optimal_entry, direction, atr)
            conservative_rr = self._calculate_risk_reward(conservative_entry, direction, atr)
            
            return {
                'atr': atr,
                'timeframe': timeframe,
                'immediate': {
                    'price': immediate_entry['price'],
                    'risk_level': immediate_entry['risk_level'],
                    'expectation': immediate_entry['expectation'],
                    'explanation_detail': immediate_entry.get('explanation_detail'),
                    'risk_reward': immediate_rr,
                    'price_change_pct': 0.0
                },
                'optimal': {
                    'price': optimal_entry['price'],
                    'risk_level': optimal_entry['risk_level'],
                    'expectation': optimal_entry['expectation'],
                    'explanation_detail': optimal_entry.get('explanation_detail'),
                    'risk_reward': optimal_rr,
                    'price_change_pct': self._calculate_price_change_pct(current_price, optimal_entry['price'])
                },
                'conservative': {
                    'price': conservative_entry['price'],
                    'risk_level': conservative_entry['risk_level'],
                    'expectation': conservative_entry['expectation'],
                    'explanation_detail': conservative_entry.get('explanation_detail'),
                    'risk_reward': conservative_rr,
                    'price_change_pct': self._calculate_price_change_pct(current_price, conservative_entry['price'])
                }
            }
            
        except Exception as e:
            self.logger.error(f"Entry levels calculation error: {str(e)}", exc_info=True)
            return self._get_fallback_entry_levels(current_price, direction)
    
    def _calculate_immediate_entry(self, current_price: float, direction: str, timeframe: str = None, atr: float = None) -> Dict:
        """Immediate entry level."""
        if direction == 'LONG':
            price = current_price * 1.001  # %0.1 spread
            math_exp = f"Current Price + 0.1% = {current_price:.6f} x 1.001 = {price:.6f}"
        else:
            price = current_price * 0.999
            math_exp = f"Current Price - 0.1% = {current_price:.6f} x 0.999 = {price:.6f}"
        expectation = 'Fast movement'
        if atr and timeframe:
            explanation_detail = f"ATR ({timeframe}) = {atr:.6f}, Formula: {math_exp}"
        else:
            explanation_detail = math_exp
        return {
            'price': price,
            'risk_level': 'Medium',
            'expectation': expectation,
            'explanation_detail': explanation_detail
        }

    def _calculate_optimal_entry(
        self,
        symbol: str,
        direction: str,
        current_price: float,
        df: Optional[object] = None,
        atr: Optional[float] = None,
        timeframe: str = None
    ) -> Dict:
        """Optimal entry level.
        
        Policy:
        - If ATR exists, for SHORT current + 1.0*ATR (for LONG current - 1.0*ATR)
        - If no ATR, 1% fallback.
        """
        try:
            if atr is not None and timeframe is not None:
                if direction == 'LONG':
                    price = current_price - atr
                    form_str = f"Current Price - ATR = {current_price:.6f} - {atr:.6f} = {price:.6f}"
                else:
                    price = current_price + atr
                    form_str = f"Current Price + ATR = {current_price:.6f} + {atr:.6f} = {price:.6f}"
                expectation = 'ATR based correction'
                explanation_detail = f"ATR ({timeframe}) = {atr:.6f}, Formula: {form_str}"
            else:
                # Fallback: 1% correction
                if direction == 'LONG':
                    price = current_price * 0.99
                    form_str = f"Current Price x 0.99 = {current_price:.6f} x 0.99 = {price:.6f}"
                else:
                    price = current_price * 1.01
                    form_str = f"Current Price x 1.01 = {current_price:.6f} x 1.01 = {price:.6f}"
                expectation = 'Standard correction'
                explanation_detail = form_str
            return {
                'price': price,
                'risk_level': 'Low',
                'expectation': expectation,
                'explanation_detail': explanation_detail
            }
        except Exception as e:
            self.logger.warning(f"Optimal entry calculation error: {str(e)}")
            return self._get_fallback_optimal_entry(current_price, direction)

    def _calculate_conservative_entry(
        self,
        symbol: str,
        direction: str,
        current_price: float,
        df: Optional[object] = None,
        atr: Optional[float] = None,
        timeframe: str = None
    ) -> Dict:
        """Safest entry level.
        
        Policy:
        - If ATR exists, for SHORT current + 2.0*ATR (for LONG current - 2.0*ATR)
        - If no ATR, 3% fallback.
        """
        try:
            if atr is not None and timeframe is not None:
                if direction == 'LONG':
                    price = current_price - (atr * SL_MULTIPLIER)
                    form_str = f"Current Price - {SL_MULTIPLIER} x ATR = {current_price:.6f} - {SL_MULTIPLIER} x {atr:.6f} = {price:.6f}"
                else:
                    price = current_price + (atr * SL_MULTIPLIER)
                    form_str = f"Current Price + {SL_MULTIPLIER} x ATR = {current_price:.6f} + {SL_MULTIPLIER} x {atr:.6f} = {price:.6f}"
                expectation = 'ATR based safe level'
                explanation_detail = f"ATR ({timeframe}) = {atr:.6f}, Formula: {form_str}"
            else:
                # Fallback: 3% correction
                if direction == 'LONG':
                    price = current_price * 0.97
                    form_str = f"Current Price x 0.97 = {current_price:.6f} x 0.97 = {price:.6f}"
                else:
                    price = current_price * 1.03
                    form_str = f"Current Price x 1.03 = {current_price:.6f} x 1.03 = {price:.6f}"
                expectation = 'Strong support/resistance'
                explanation_detail = form_str
            return {
                'price': price,
                'risk_level': 'Very Low',
                'expectation': expectation,
                'explanation_detail': explanation_detail
            }
        except Exception as e:
            self.logger.warning(f"Conservative entry calculation error: {str(e)}")
            return self._get_fallback_conservative_entry(current_price, direction)
    
    def _calculate_risk_reward(self, entry_data: Dict, direction: str, atr: Optional[float]) -> float:
        """Calculates Risk/Reward ratio."""
        try:
            entry_price = entry_data['price']
            
            if not atr:
                # Fallback R/R
                return 2.0 if direction == 'LONG' else 2.0
            
            # Stop-loss: SL_MULTIPLIER x ATR
            if direction == 'LONG':
                stop_loss = entry_price - (SL_MULTIPLIER * atr)
                target = entry_price + (3 * atr)  # 1.5:1 R/R
            else:
                stop_loss = entry_price + (SL_MULTIPLIER * atr)
                target = entry_price - (3 * atr)
            
            risk = abs(entry_price - stop_loss)
            reward = abs(target - entry_price)
            
            if risk > 0:
                return round(reward / risk, 1)
            
            return 2.0
            
        except Exception as e:
            self.logger.warning(f"Risk/Reward calculation error: {str(e)}")
            return 2.0
    
    def _calculate_price_change_pct(self, current_price: float, target_price: float) -> float:
        """Calculates price change percentage."""
        if current_price == 0:
            return 0.0
        return round((target_price - current_price) / current_price * 100, 2)
    
    def _is_reasonable_price(self, fib_price: float, current_price: float) -> bool:
        """Checks if Fibonacci price is within reasonable range."""
        if current_price == 0:
            return False
        
        # If deviation is more than 10%, it is not reasonable
        change_pct = abs(fib_price - current_price) / current_price
        return change_pct <= 0.10
    
    def _get_fallback_entry_levels(self, current_price: float, direction: str) -> Dict:
        """Fallback entry levels in case of error."""
        if direction == 'LONG':
            immediate_price = current_price * 1.001
            optimal_price = current_price * 0.99
            conservative_price = current_price * 0.97
        else:
            immediate_price = current_price * 0.999
            optimal_price = current_price * 1.01
            conservative_price = current_price * 1.03
        
        return {
            'immediate': {
                'price': immediate_price,
                'risk_level': 'Medium',
                'expectation': 'Fast movement',
                'risk_reward': 2.0,
                'price_change_pct': 0.0
            },
            'optimal': {
                'price': optimal_price,
                'risk_level': 'Low',
                'expectation': 'Standard correction',
                'risk_reward': 2.5,
                'price_change_pct': self._calculate_price_change_pct(current_price, optimal_price)
            },
            'conservative': {
                'price': conservative_price,
                'risk_level': 'Very Low',
                'expectation': 'Safe level',
                'risk_reward': 3.0,
                'price_change_pct': self._calculate_price_change_pct(current_price, conservative_price)
            }
        }
    
    def _get_fallback_optimal_entry(self, current_price: float, direction: str) -> Dict:
        """Optimal entry fallback."""
        if direction == 'LONG':
            price = current_price * 0.99
        else:
            price = current_price * 1.01
        
        return {
            'price': price,
            'risk_level': 'Low',
            'expectation': 'Standard correction'
        }
    
    def _get_fallback_conservative_entry(self, current_price: float, direction: str) -> Dict:
        """Conservative entry fallback."""
        if direction == 'LONG':
            price = current_price * 0.97
        else:
            price = current_price * 1.03
        
        return {
            'price': price,
            'risk_level': 'Very Low',
            'expectation': 'Safe level'
        }
