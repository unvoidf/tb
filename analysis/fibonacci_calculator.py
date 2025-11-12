"""
FibonacciCalculator: Fibonacci retracement ve extension seviyeleri.
Swing high/low tespiti ve giriş/SL/TP seviyelerini hesaplar.
"""
import pandas as pd
from typing import Dict, List, Tuple, Optional


class FibonacciCalculator:
    """Fibonacci seviyelerini hesaplar."""
    
    def __init__(self, fib_levels: List[float] = None,
                 swing_lookback: int = 100):
        """
        FibonacciCalculator'ı başlatır.
        
        Args:
            fib_levels: Fibonacci seviyeleri
            swing_lookback: Swing high/low için geriye bakış
        """
        self.fib_levels = fib_levels or [0.236, 0.382, 0.618, 0.786]
        self.swing_lookback = swing_lookback
    
    def calculate_levels(self, df: pd.DataFrame,
                        trend_direction: str) -> Optional[Dict]:
        """
        Fibonacci seviyelerini hesaplar.
        
        Args:
            df: OHLCV DataFrame
            trend_direction: 'LONG' veya 'SHORT'
            
        Returns:
            Fibonacci seviyeleri dict
        """
        if df is None or len(df) < self.swing_lookback:
            return None
        
        swing_high, swing_low = self._find_swing_points(df)
        
        if swing_high is None or swing_low is None:
            return None
        
        if trend_direction == 'LONG':
            levels = self._calculate_retracement_levels(
                swing_high, swing_low, 'up'
            )
        elif trend_direction == 'SHORT':
            levels = self._calculate_retracement_levels(
                swing_high, swing_low, 'down'
            )
        else:
            return None
        
        return levels
    
    def _find_swing_points(self, df: pd.DataFrame) -> Tuple[float, float]:
        """
        Son N mum içinde swing high ve low noktalarını bulur.
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            (swing_high, swing_low) tuple
        """
        lookback_data = df.tail(self.swing_lookback)
        
        swing_high = lookback_data['high'].max()
        swing_low = lookback_data['low'].min()
        
        return swing_high, swing_low
    
    def _calculate_retracement_levels(
        self, high: float, low: float, direction: str
    ) -> Dict:
        """
        Fibonacci retracement seviyelerini hesaplar.
        
        Args:
            high: Swing high
            low: Swing low
            direction: 'up' veya 'down'
            
        Returns:
            Seviye dict
        """
        diff = high - low
        
        levels = {}
        
        if direction == 'up':
            # Uptrend için retracement
            for level in self.fib_levels:
                levels[f'fib_{level}'] = high - (diff * level)
        else:
            # Downtrend için retracement
            for level in self.fib_levels:
                levels[f'fib_{level}'] = low + (diff * level)
        
        levels['swing_high'] = high
        levels['swing_low'] = low
        
        return levels
    
    def suggest_entry_levels(
        self, df: pd.DataFrame, 
        trend_direction: str
    ) -> Optional[Dict]:
        """
        Giriş noktası önerir.
        
        Args:
            df: OHLCV DataFrame
            trend_direction: 'LONG' veya 'SHORT'
            
        Returns:
            Entry level bilgileri
        """
        fib_levels = self.calculate_levels(df, trend_direction)
        
        if not fib_levels:
            return None
        
        current_price = df['close'].iloc[-1]
        
        if trend_direction == 'LONG':
            # 0.618 veya 0.5 civarı ideal giriş
            ideal_entry = fib_levels.get('fib_0.618', current_price)
            stop_loss = fib_levels['swing_low']
        else:
            ideal_entry = fib_levels.get('fib_0.618', current_price)
            stop_loss = fib_levels['swing_high']
        
        return {
            'entry': ideal_entry,
            'stop_loss': stop_loss,
            'current_price': current_price,
            'all_levels': fib_levels
        }
    
    def calculate_targets(
        self, entry: float, stop_loss: float,
        trend_direction: str
    ) -> List[Dict]:
        """
        Take profit hedeflerini hesaplar.
        
        Args:
            entry: Giriş fiyatı
            stop_loss: Stop loss seviyesi
            trend_direction: 'LONG' veya 'SHORT'
            
        Returns:
            Target seviyeleri listesi
        """
        risk = abs(entry - stop_loss)
        
        targets = []
        risk_reward_ratios = [1.0, 1.618, 2.618]
        
        for ratio in risk_reward_ratios:
            if trend_direction == 'LONG':
                target_price = entry + (risk * ratio)
            else:
                target_price = entry - (risk * ratio)
            
            targets.append({
                'price': target_price,
                'risk_reward': ratio
            })
        
        return targets

