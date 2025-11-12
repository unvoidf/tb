"""
RiskRewardCalculator: R-based distance hesaplama utility.
TP/SL seviyelerini risk birimi (R) cinsinden hesaplar.
"""
from typing import Dict, Optional
from utils.logger import LoggerManager


class RiskRewardCalculator:
    """R-based risk/reward hesaplayıcı."""
    
    def __init__(self):
        """RiskRewardCalculator'ı başlatır."""
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
        TP/SL seviyelerini R cinsinden hesaplar.
        R = |signal_price - sl2_price|
        
        Args:
            signal_price: Sinyal fiyatı
            direction: LONG/SHORT
            tp1, tp2, tp3: TP seviyeleri
            sl1, sl2: SL seviyeleri
            
        Returns:
            {
                'tp1_distance_r': float,
                'tp2_distance_r': float,
                'tp3_distance_r': float,
                'sl1_distance_r': float,
                'sl2_distance_r': float (her zaman -1.0)
            }
        """
        if sl2 is None:
            self.logger.debug("SL2 None, R distance hesaplanamıyor")
            return {
                'tp1_distance_r': None,
                'tp2_distance_r': None,
                'tp3_distance_r': None,
                'sl1_distance_r': None,
                'sl2_distance_r': None
            }
        
        r = abs(signal_price - sl2)
        if r == 0:
            self.logger.warning("R = 0, distance hesaplanamıyor")
            return {
                'tp1_distance_r': None,
                'tp2_distance_r': None,
                'tp3_distance_r': None,
                'sl1_distance_r': None,
                'sl2_distance_r': None
            }
        
        def calc_r(price, is_tp):
            """Tek bir seviye için R distance hesapla."""
            if price is None:
                return None
            if direction == 'LONG':
                if is_tp:
                    return (price - signal_price) / r  # TP: pozitif (yukarı)
                else:
                    return -(signal_price - price) / r  # SL: negatif (aşağı)
            else:  # SHORT
                if is_tp:
                    return (signal_price - price) / r  # TP: pozitif (aşağı)
                else:
                    return -(price - signal_price) / r  # SL: negatif (yukarı)
        
        result = {
            'tp1_distance_r': calc_r(tp1, True),
            'tp2_distance_r': calc_r(tp2, True),
            'tp3_distance_r': calc_r(tp3, True),
            'sl1_distance_r': calc_r(sl1, False),
            'sl2_distance_r': -1.0  # SL2 her zaman -1R (tanım gereği)
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

