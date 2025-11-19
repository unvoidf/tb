"""
PriceChecker: Fiyat kontrolü ve TP/SL hit detection.
Target price check, stop-loss check helpers.
"""
from typing import Dict, Optional, Tuple
from utils.logger import LoggerManager


class PriceChecker:
    """Fiyat kontrolü helper sınıfı."""
    
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
        TP hit kontrolü yapar.
        
        Args:
            current_price: Güncel fiyat
            tp_price: TP fiyatı
            direction: LONG/SHORT
            tolerance: Tolerans (0.001 = %0.1)
            
        Returns:
            True ise TP hit olmuş
        """
        if direction == 'LONG':
            # LONG: Fiyat TP'ye ulaşmalı veya geçmeli
            return current_price >= tp_price * (1 - tolerance)
        else:  # SHORT
            # SHORT: Fiyat TP'ye ulaşmalı veya geçmeli
            return current_price <= tp_price * (1 + tolerance)
    
    def check_sl_hit(
        self,
        current_price: float,
        sl_price: float,
        direction: str,
        tolerance: float = 0.001
    ) -> bool:
        """
        SL hit kontrolü yapar.
        
        Args:
            current_price: Güncel fiyat
            sl_price: SL fiyatı
            direction: LONG/SHORT
            tolerance: Tolerans
            
        Returns:
            True ise SL hit olmuş
        """
        if direction == 'LONG':
            # LONG: Fiyat SL'ye ulaşmalı veya altına düşmeli
            return current_price <= sl_price * (1 + tolerance)
        else:  # SHORT
            # SHORT: Fiyat SL'ye ulaşmalı veya üstüne çıkmalı
            return current_price >= sl_price * (1 - tolerance)
    
    def calculate_distance_to_level(
        self,
        current_price: float,
        target_price: float
    ) -> Tuple[float, float]:
        """
        Hedefe uzaklık hesaplar.
        
        Args:
            current_price: Güncel fiyat
            target_price: Hedef fiyat
            
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
        En yakın seviyeyi bulur.
        
        Args:
            current_price: Güncel fiyat
            levels: Seviyeler dict (örn: {'TP1': 100, 'TP2': 110})
            direction: LONG/SHORT
            
        Returns:
            (level_name, level_price) veya None
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

