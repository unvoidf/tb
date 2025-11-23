"""
PositionCalculator: Position calculation class.
Fibonacci and ATR based entry, stop-loss and take-profit levels.
"""
import pandas as pd
from typing import Dict, Optional
from analysis.fibonacci_calculator import FibonacciCalculator
from config.constants import SL_MULTIPLIER
from utils.logger import LoggerManager


class PositionCalculator:
    """Calculates position levels."""
    
    def __init__(self, fib_calculator: FibonacciCalculator):
        """
        Initializes PositionCalculator.
        
        Args:
            fib_calculator: Fibonacci calculator
        """
        self.fib_calc = fib_calculator
        self.logger = LoggerManager().get_logger('PositionCalculator')
    
    def calculate_position(
        self, df: pd.DataFrame,
        signal: Dict,
        atr: float
    ) -> Optional[Dict]:
        """
        Calculates position levels.
        
        Args:
            df: OHLCV DataFrame
            signal: Signal info
            atr: ATR value
            
        Returns:
            Position level dict
        """
        direction = signal['direction']
        
        if direction == 'NEUTRAL':
            return None
        
        current_price = df['close'].iloc[-1]
        self.logger.debug(f"calc_position: direction={direction}, current={current_price}")
        
        strategy_type = signal.get('strategy_type', 'trend')
        custom_targets = signal.get('custom_targets') or {}
        
        if strategy_type == 'ranging' and custom_targets:
            self.logger.debug("Ranging strategy detected, using custom targets")
            return self._build_ranging_position(
                current_price=current_price,
                direction=direction,
                custom_targets=custom_targets,
                atr=atr
            )
        
        # Fibonacci based levels
        fib_entry = self.fib_calc.suggest_entry_levels(df, direction)
        self.logger.debug(f"fib_entry: {fib_entry}")
        
        if not fib_entry:
            # Fallback: ATR based calculation
            self.logger.debug(f"fib_entry missing -> fallback ATR: atr={atr}")
            return self._calculate_atr_based_position(
                current_price, atr, direction
            )
        
        # Entry level and status
        entry, entry_status = self._determine_entry_price(
            current_price, fib_entry['entry'], direction
        )
        self.logger.debug(f"entry: {entry} status={entry_status}")
        
        # Stop-loss
        stop_loss = self._calculate_stop_loss(
            entry, atr, fib_entry['stop_loss'], direction
        )
        self.logger.debug(f"stop_loss: {stop_loss} (atr={atr}, fib_sl={fib_entry['stop_loss']})")
        
        # Take-profit levels
        targets = self.fib_calc.calculate_targets(
            entry, stop_loss, direction
        )
        self.logger.debug(f"targets: {targets}")
        
        return {
            'direction': direction,
            'entry': entry,
            'current_price': current_price,
            'stop_loss': stop_loss,
            'targets': targets,
            'risk_amount': abs(entry - stop_loss),
            'risk_percent': abs(entry - stop_loss) / entry * 100,
            'entry_status': entry_status,
            'fib_ideal_entry': fib_entry['entry'],
            'strategy_type': strategy_type
        }
    
    def _determine_entry_price(
        self, current: float, fib_entry: float, direction: str
    ) -> tuple[float, str]:
        """
        Determines entry price and returns status message.
        
        Args:
            current: Current price
            fib_entry: Fibonacci entry level
            direction: Position direction
            
        Returns:
            (Entry price, status message) tuple
        """
        # If price is already close to ideal level
        distance = abs(current - fib_entry) / current
        
        if distance < 0.02:  # Closer than 2%
            return current, "OPTIMAL"
        
        # Check price direction
        if direction == 'LONG':
            price_moved_ahead = current > fib_entry
        else:  # SHORT
            price_moved_ahead = current < fib_entry
        
        # If price moved in target direction
        if price_moved_ahead:
            # If moved more than 5%, definitely current price
            if distance > 0.05:
                return current, "PRICE_MOVED"
            # Between 2-5% is also considered moved
            else:
                return current, "PRICE_MOVED"
        
        # Price in opposite direction or not moved yet
        else:
            # Pullback expected
            if distance > 0.05:
                return fib_entry, "WAIT_FOR_PULLBACK"
            else:
                return fib_entry, "PULLBACK_EXPECTED"
    
    def _calculate_stop_loss(
        self, entry: float, atr: float,
        fib_sl: float, direction: str
    ) -> float:
        """
        Calculates stop-loss level (ATR and Fibonacci combination).
        
        Args:
            entry: Entry price
            atr: ATR value
            fib_sl: Fibonacci stop-loss
            direction: Position direction
            
        Returns:
            Stop-loss level
        """
        # ATR based stop-loss (SL_MULTIPLIER x ATR)
        if direction == 'LONG':
            atr_sl = entry - (SL_MULTIPLIER * atr)
        else:
            atr_sl = entry + (SL_MULTIPLIER * atr)
        
        # Use tighter one from Fibonacci and ATR
        if direction == 'LONG':
            return max(atr_sl, fib_sl)
        else:
            return min(atr_sl, fib_sl)
    
    def _calculate_atr_based_position(
        self, price: float, atr: float, direction: str
    ) -> Dict:
        """
        Fallback: Only ATR based position calculation.
        
        Args:
            price: Current price
            atr: ATR value
            direction: Position direction
            
        Returns:
            Position level dict
        """
        entry = price
        
        if direction == 'LONG':
            stop_loss = entry - (SL_MULTIPLIER * atr)
            tp1 = entry + (2 * atr)
            tp2 = entry + (3.236 * atr)
            tp3 = entry + (5.236 * atr)
        else:
            stop_loss = entry + (SL_MULTIPLIER * atr)
            tp1 = entry - (2 * atr)
            tp2 = entry - (3.236 * atr)
            tp3 = entry - (5.236 * atr)
        
        targets = [
            {'price': tp1, 'risk_reward': 1.0},
            {'price': tp2, 'risk_reward': 1.618},
            {'price': tp3, 'risk_reward': 2.618}
        ]
        
        return {
            'direction': direction,
            'entry': entry,
            'current_price': price,
            'stop_loss': stop_loss,
            'targets': targets,
            'risk_amount': abs(entry - stop_loss),
            'risk_percent': abs(entry - stop_loss) / entry * 100,
            'entry_status': 'CURRENT_PRICE',
            'fib_ideal_entry': None,
            'strategy_type': 'trend'
        }
    
    def _build_ranging_position(
        self,
        current_price: float,
        direction: str,
        custom_targets: Dict[str, Dict[str, float]],
        atr: float
    ) -> Dict:
        """
        Creates position with custom TP/SL levels for Ranging strategy.
        """
        stop_info = custom_targets.get('stop_loss', {})
        stop_price = stop_info.get('price')
        
        if stop_price is None:
            self.logger.warning("Custom targets missing stop_loss, falling back to ATR based levels")
            fallback = self._calculate_atr_based_position(current_price, atr, direction)
            fallback['strategy_type'] = 'ranging'
            fallback['entry_status'] = 'ATR_FALLBACK_NO_STOP'
            fallback['custom_targets'] = custom_targets
            return fallback
        
        entry = current_price
        targets = self._build_ranging_targets(
            entry=entry,
            stop_loss=stop_price,
            direction=direction,
            custom_targets=custom_targets
        )
        
        risk_amount = abs(entry - stop_price)
        risk_percent = (risk_amount / entry * 100) if entry else 0.0
        
        return {
            'direction': direction,
            'entry': entry,
            'current_price': current_price,
            'stop_loss': stop_price,
            'targets': targets,
            'risk_amount': risk_amount,
            'risk_percent': risk_percent,
            'entry_status': 'MEAN_REVERSION',
            'fib_ideal_entry': None,
            'strategy_type': 'ranging',
            'custom_targets': custom_targets
        }
    
    def _build_ranging_targets(
        self,
        entry: float,
        stop_loss: float,
        direction: str,
        custom_targets: Dict[str, Dict[str, float]]
    ) -> list:
        """Creates target list from custom target dict."""
        targets = []
        
        for key in ['tp1', 'tp2', 'tp3']:
            target_info = custom_targets.get(key)
            if not target_info:
                continue
            
            price = target_info.get('price')
            if price is None:
                continue
            
            rr = self._calculate_risk_reward(entry, stop_loss, price, direction)
            targets.append({
                'price': price,
                'risk_reward': rr,
                'label': target_info.get('label', key.upper()),
                'type': target_info.get('type', 'mean_reversion')
            })
        
        return targets
    
    def _calculate_risk_reward(
        self,
        entry: float,
        stop_loss: float,
        target_price: float,
        direction: str
    ) -> float:
        """Calculates risk/reward ratio."""
        if direction == 'LONG':
            risk = entry - stop_loss
            reward = target_price - entry
        else:
            risk = stop_loss - entry
            reward = entry - target_price
        
        if risk <= 0:
            return 0.0
        
        return max(reward / risk, 0.0)
    
    def calculate_r_distances(
        self,
        signal_price: float,
        direction: str,
        tp_levels: Dict,
        sl_levels: Dict
    ) -> Dict:
        """
        Calculates R-based distances (normalized relative to SL2).
        
        Args:
            signal_price: Signal price
            direction: LONG or SHORT
            tp_levels: {'tp1': price, 'tp2': price, 'tp3': price}
            sl_levels: {'sl1': price, 'sl2': price, 'sl3': price}
            
        Returns:
            {'tp1_r': float, 'tp2_r': float, 'tp3_r': float, 'sl1_r': float, 'sl2_r': float}
        """
        # Risk = SL2 distance
        sl2_price = sl_levels.get('sl2', sl_levels.get('sl1', signal_price))
        risk = abs(signal_price - sl2_price)
        
        if risk == 0:
            return {'tp1_r': 0, 'tp2_r': 0, 'tp3_r': 0, 'sl1_r': 0, 'sl2_r': 0}
        
        result = {}
        
        # TP R distances
        for level in ['tp1', 'tp2', 'tp3']:
            tp_price = tp_levels.get(level)
            if tp_price is not None:
                if direction == 'LONG':
                    distance = tp_price - signal_price
                else:  # SHORT
                    distance = signal_price - tp_price
                result[f'{level}_r'] = distance / risk
            else:
                result[f'{level}_r'] = 0
        
        # SL R distances (negative)
        for level in ['sl1', 'sl2']:
            sl_price = sl_levels.get(level)
            if sl_price is not None:
                if direction == 'LONG':
                    distance = sl_price - signal_price
                else:  # SHORT
                    distance = signal_price - sl_price
                result[f'{level}_r'] = distance / risk
            else:
                result[f'{level}_r'] = 0
        
        return result

