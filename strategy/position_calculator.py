"""
PositionCalculator: Pozisyon hesaplama sınıfı.
Fibonacci ve ATR bazlı giriş, stop-loss ve take-profit seviyeleri.
"""
import pandas as pd
from typing import Dict, Optional
from analysis.fibonacci_calculator import FibonacciCalculator
from utils.logger import LoggerManager


class PositionCalculator:
    """Pozisyon seviyelerini hesaplar."""
    
    def __init__(self, fib_calculator: FibonacciCalculator):
        """
        PositionCalculator'ı başlatır.
        
        Args:
            fib_calculator: Fibonacci hesaplayıcı
        """
        self.fib_calc = fib_calculator
        self.logger = LoggerManager().get_logger('PositionCalculator')
    
    def calculate_position(
        self, df: pd.DataFrame,
        signal: Dict,
        atr: float
    ) -> Optional[Dict]:
        """
        Pozisyon seviyelerini hesaplar.
        
        Args:
            df: OHLCV DataFrame
            signal: Sinyal bilgisi
            atr: ATR değeri
            
        Returns:
            Pozisyon seviyesi dict
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
        
        # Fibonacci bazlı seviyeler
        fib_entry = self.fib_calc.suggest_entry_levels(df, direction)
        self.logger.debug(f"fib_entry: {fib_entry}")
        
        if not fib_entry:
            # Fallback: ATR bazlı hesaplama
            self.logger.debug(f"fib_entry missing -> fallback ATR: atr={atr}")
            return self._calculate_atr_based_position(
                current_price, atr, direction
            )
        
        # Giriş seviyesi ve durum
        entry, entry_status = self._determine_entry_price(
            current_price, fib_entry['entry'], direction
        )
        self.logger.debug(f"entry: {entry} status={entry_status}")
        
        # Stop-loss
        stop_loss = self._calculate_stop_loss(
            entry, atr, fib_entry['stop_loss'], direction
        )
        self.logger.debug(f"stop_loss: {stop_loss} (atr={atr}, fib_sl={fib_entry['stop_loss']})")
        
        # Take-profit seviyeleri
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
        Giriş fiyatını belirler ve durum mesajı döndürür.
        
        Args:
            current: Mevcut fiyat
            fib_entry: Fibonacci giriş seviyesi
            direction: Pozisyon yönü
            
        Returns:
            (Giriş fiyatı, durum mesajı) tuple
        """
        # Eğer fiyat zaten ideal seviyeye yakınsa
        distance = abs(current - fib_entry) / current
        
        if distance < 0.02:  # %2'den yakınsa
            return current, "OPTIMAL"
        
        # Fiyatın yönünü kontrol et
        if direction == 'LONG':
            price_moved_ahead = current > fib_entry
        else:  # SHORT
            price_moved_ahead = current < fib_entry
        
        # Fiyat hedef yönünde hareket etmişse
        if price_moved_ahead:
            # %5'ten fazla kaçmışsa kesinlikle güncel fiyat
            if distance > 0.05:
                return current, "PRICE_MOVED"
            # %2-5 arası da kaçmış sayılır
            else:
                return current, "PRICE_MOVED"
        
        # Fiyat ters yönde veya henüz hareketsiz
        else:
            # Düzeltme beklenebilir
            if distance > 0.05:
                return fib_entry, "WAIT_FOR_PULLBACK"
            else:
                return fib_entry, "PULLBACK_EXPECTED"
    
    def _calculate_stop_loss(
        self, entry: float, atr: float,
        fib_sl: float, direction: str
    ) -> float:
        """
        Stop-loss seviyesini hesaplar (ATR ve Fibonacci kombinasyonu).
        
        Args:
            entry: Giriş fiyatı
            atr: ATR değeri
            fib_sl: Fibonacci stop-loss
            direction: Pozisyon yönü
            
        Returns:
            Stop-loss seviyesi
        """
        # ATR bazlı stop-loss (2x ATR)
        if direction == 'LONG':
            atr_sl = entry - (2 * atr)
        else:
            atr_sl = entry + (2 * atr)
        
        # Fibonacci ve ATR'den daha sıkı olanı kullan
        if direction == 'LONG':
            return max(atr_sl, fib_sl)
        else:
            return min(atr_sl, fib_sl)
    
    def _calculate_atr_based_position(
        self, price: float, atr: float, direction: str
    ) -> Dict:
        """
        Fallback: Sadece ATR bazlı pozisyon hesaplama.
        
        Args:
            price: Mevcut fiyat
            atr: ATR değeri
            direction: Pozisyon yönü
            
        Returns:
            Pozisyon seviyesi dict
        """
        entry = price
        
        if direction == 'LONG':
            stop_loss = entry - (2 * atr)
            tp1 = entry + (2 * atr)
            tp2 = entry + (3.236 * atr)
            tp3 = entry + (5.236 * atr)
        else:
            stop_loss = entry + (2 * atr)
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
        Ranging stratejisi için custom TP/SL seviyeleriyle pozisyon oluşturur.
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
        """Custom target dict'inden hedef listesi oluşturur."""
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
        """Risk/ödül oranını hesaplar."""
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
        R-based distances hesaplar (SL2'ye göre normalize edilmiş).
        
        Args:
            signal_price: Sinyal fiyatı
            direction: LONG veya SHORT
            tp_levels: {'tp1': price, 'tp2': price, 'tp3': price}
            sl_levels: {'sl1': price, 'sl2': price, 'sl3': price}
            
        Returns:
            {'tp1_r': float, 'tp2_r': float, 'tp3_r': float, 'sl1_r': float, 'sl2_r': float}
        """
        # Risk = SL2 mesafesi
        sl2_price = sl_levels.get('sl2', sl_levels.get('sl1', signal_price))
        risk = abs(signal_price - sl2_price)
        
        if risk == 0:
            return {'tp1_r': 0, 'tp2_r': 0, 'tp3_r': 0, 'sl1_r': 0, 'sl2_r': 0}
        
        result = {}
        
        # TP R mesafeleri
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
        
        # SL R mesafeleri (negatif)
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

