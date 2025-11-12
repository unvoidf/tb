"""
DynamicEntryCalculator: Üç seviye giriş hesaplayan sınıf.
IMMEDIATE, OPTIMAL ve CONSERVATIVE entry seviyelerini hesaplar.
"""
from typing import Dict, Optional, Tuple
from analysis.fibonacci_calculator import FibonacciCalculator
from strategy.position_calculator import PositionCalculator
from utils.logger import LoggerManager


class DynamicEntryCalculator:
    """Dinamik giriş seviyelerini hesaplar."""
    
    def __init__(self, fib_calculator: FibonacciCalculator, position_calc: PositionCalculator):
        """
        DynamicEntryCalculator'ı başlatır.
        
        Args:
            fib_calculator: Fibonacci hesaplayıcı
            position_calc: Pozisyon hesaplayıcı
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
        Üç seviye giriş hesaplar.
        
        Args:
            symbol: Trading pair (örn: BTC/USDT)
            direction: LONG/SHORT
            current_price: Mevcut fiyat
            df: OHLCV DataFrame (opsiyonel)
            atr: ATR değeri (opsiyonel)
            
        Returns:
            Entry levels dict
        """
        try:
            self.logger.debug(f"calculate_entry_levels: {symbol} {direction} @ {current_price}")
            
            # IMMEDIATE entry (mevcut fiyat)
            immediate_entry = self._calculate_immediate_entry(current_price, direction, timeframe, atr)
            
            # OPTIMAL entry (ATR öncelikli, uygun ise Fib 0.618 ile zenginleştir)
            optimal_entry = self._calculate_optimal_entry(
                symbol, direction, current_price, df, atr, timeframe
            )
            
            # CONSERVATIVE entry (ATR tabanlı güvenli seviye)
            conservative_entry = self._calculate_conservative_entry(
                symbol, direction, current_price, df, atr, timeframe
            )
            
            # Risk/Reward hesaplamaları
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
            self.logger.error(f"Entry levels hesaplama hatası: {str(e)}", exc_info=True)
            return self._get_fallback_entry_levels(current_price, direction)
    
    def _calculate_immediate_entry(self, current_price: float, direction: str, timeframe: str = None, atr: float = None) -> Dict:
        """Hemen giriş seviyesi."""
        if direction == 'LONG':
            price = current_price * 1.001  # %0.1 spread
            math_exp = f"Güncel Fiyat + %0.1 = {current_price:.6f} x 1.001 = {price:.6f}"
        else:
            price = current_price * 0.999
            math_exp = f"Güncel Fiyat - %0.1 = {current_price:.6f} x 0.999 = {price:.6f}"
        expectation = 'Hızlı hareket'
        if atr and timeframe:
            explanation_detail = f"ATR ({timeframe}) = {atr:.6f}, Formül: {math_exp}"
        else:
            explanation_detail = math_exp
        return {
            'price': price,
            'risk_level': 'Orta',
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
        """Optimal giriş seviyesi.
        
        Politika:
        - ATR varsa, SHORT için current + 1.0*ATR (LONG için current - 1.0*ATR)
        - ATR yoksa %1 fallback.
        """
        try:
            if atr is not None and timeframe is not None:
                if direction == 'LONG':
                    price = current_price - atr
                    form_str = f"Güncel Fiyat - ATR = {current_price:.6f} - {atr:.6f} = {price:.6f}"
                else:
                    price = current_price + atr
                    form_str = f"Güncel Fiyat + ATR = {current_price:.6f} + {atr:.6f} = {price:.6f}"
                expectation = 'ATR bazlı düzeltme'
                explanation_detail = f"ATR ({timeframe}) = {atr:.6f}, Formül: {form_str}"
            else:
                # Fallback: %1 düzeltme
                if direction == 'LONG':
                    price = current_price * 0.99
                    form_str = f"Güncel Fiyat x 0.99 = {current_price:.6f} x 0.99 = {price:.6f}"
                else:
                    price = current_price * 1.01
                    form_str = f"Güncel Fiyat x 1.01 = {current_price:.6f} x 1.01 = {price:.6f}"
                expectation = 'Standart düzeltme'
                explanation_detail = form_str
            return {
                'price': price,
                'risk_level': 'Düşük',
                'expectation': expectation,
                'explanation_detail': explanation_detail
            }
        except Exception as e:
            self.logger.warning(f"Optimal entry hesaplama hatası: {str(e)}")
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
        """En güvenli giriş seviyesi.
        
        Politika:
        - ATR varsa, SHORT için current + 2.0*ATR (LONG için current - 2.0*ATR)
        - ATR yoksa %3 fallback.
        """
        try:
            if atr is not None and timeframe is not None:
                if direction == 'LONG':
                    price = current_price - (atr * 2.0)
                    form_str = f"Güncel Fiyat - 2 x ATR = {current_price:.6f} - 2 x {atr:.6f} = {price:.6f}"
                else:
                    price = current_price + (atr * 2.0)
                    form_str = f"Güncel Fiyat + 2 x ATR = {current_price:.6f} + 2 x {atr:.6f} = {price:.6f}"
                expectation = 'ATR bazlı güvenli seviye'
                explanation_detail = f"ATR ({timeframe}) = {atr:.6f}, Formül: {form_str}"
            else:
                # Fallback: %3 düzeltme
                if direction == 'LONG':
                    price = current_price * 0.97
                    form_str = f"Güncel Fiyat x 0.97 = {current_price:.6f} x 0.97 = {price:.6f}"
                else:
                    price = current_price * 1.03
                    form_str = f"Güncel Fiyat x 1.03 = {current_price:.6f} x 1.03 = {price:.6f}"
                expectation = 'Güçlü support/resistance'
                explanation_detail = form_str
            return {
                'price': price,
                'risk_level': 'Çok Düşük',
                'expectation': expectation,
                'explanation_detail': explanation_detail
            }
        except Exception as e:
            self.logger.warning(f"Conservative entry hesaplama hatası: {str(e)}")
            return self._get_fallback_conservative_entry(current_price, direction)
    
    def _calculate_risk_reward(self, entry_data: Dict, direction: str, atr: Optional[float]) -> float:
        """Risk/Reward oranını hesaplar."""
        try:
            entry_price = entry_data['price']
            
            if not atr:
                # Fallback R/R
                return 2.0 if direction == 'LONG' else 2.0
            
            # Stop-loss: 2x ATR
            if direction == 'LONG':
                stop_loss = entry_price - (2 * atr)
                target = entry_price + (3 * atr)  # 1.5:1 R/R
            else:
                stop_loss = entry_price + (2 * atr)
                target = entry_price - (3 * atr)
            
            risk = abs(entry_price - stop_loss)
            reward = abs(target - entry_price)
            
            if risk > 0:
                return round(reward / risk, 1)
            
            return 2.0
            
        except Exception as e:
            self.logger.warning(f"Risk/Reward hesaplama hatası: {str(e)}")
            return 2.0
    
    def _calculate_price_change_pct(self, current_price: float, target_price: float) -> float:
        """Fiyat değişim yüzdesini hesaplar."""
        if current_price == 0:
            return 0.0
        return round((target_price - current_price) / current_price * 100, 2)
    
    def _is_reasonable_price(self, fib_price: float, current_price: float) -> bool:
        """Fibonacci fiyatının makul aralıkta olup olmadığını kontrol eder."""
        if current_price == 0:
            return False
        
        # %10'dan fazla sapma varsa makul değil
        change_pct = abs(fib_price - current_price) / current_price
        return change_pct <= 0.10
    
    def _get_fallback_entry_levels(self, current_price: float, direction: str) -> Dict:
        """Hata durumunda fallback entry levels."""
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
                'risk_level': 'Orta',
                'expectation': 'Hızlı hareket',
                'risk_reward': 2.0,
                'price_change_pct': 0.0
            },
            'optimal': {
                'price': optimal_price,
                'risk_level': 'Düşük',
                'expectation': 'Standart düzeltme',
                'risk_reward': 2.5,
                'price_change_pct': self._calculate_price_change_pct(current_price, optimal_price)
            },
            'conservative': {
                'price': conservative_price,
                'risk_level': 'Çok Düşük',
                'expectation': 'Güvenli seviye',
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
            'risk_level': 'Düşük',
            'expectation': 'Standart düzeltme'
        }
    
    def _get_fallback_conservative_entry(self, current_price: float, direction: str) -> Dict:
        """Conservative entry fallback."""
        if direction == 'LONG':
            price = current_price * 0.97
        else:
            price = current_price * 1.03
        
        return {
            'price': price,
            'risk_level': 'Çok Düşük',
            'expectation': 'Güvenli seviye'
        }
