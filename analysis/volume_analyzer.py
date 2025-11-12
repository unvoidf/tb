"""
VolumeAnalyzer: Hacim analizi sınıfı.
Volume spike detection ve relative volume hesaplamaları.
"""
import pandas as pd
from typing import Dict


class VolumeAnalyzer:
    """Hacim analizi yapar."""
    
    def __init__(self, volume_ma_period: int = 20,
                 spike_threshold: float = 1.5):
        """
        VolumeAnalyzer'ı başlatır.
        
        Args:
            volume_ma_period: Hacim ortalaması periyodu
            spike_threshold: Spike threshold (örn: 1.5 = %150)
        """
        self.volume_ma_period = volume_ma_period
        self.spike_threshold = spike_threshold
    
    def analyze(self, df: pd.DataFrame, period: int = None) -> Dict:
        """
        Hacim analizini yapar.
        
        Args:
            df: OHLCV DataFrame
            period: Volume MA periyodu (adaptive)
            
        Returns:
            Hacim analiz sonuçları dict
        """
        if period is None:
            period = self.volume_ma_period
            
        if df is None or len(df) < period:
            return None
        
        volume_ma = self._calculate_volume_ma(df, period)
        current_volume = df['volume'].iloc[-1]
        relative_volume = current_volume / volume_ma if volume_ma > 0 else 0
        is_spike = relative_volume >= self.spike_threshold
        
        return {
            'current': current_volume,
            'average': volume_ma,
            'relative': relative_volume,
            'is_spike': is_spike,
            'signal': self._get_volume_signal(relative_volume, df)
        }
    
    def _calculate_volume_ma(self, df: pd.DataFrame, period: int = None) -> float:
        """
        Hacim ortalamasını hesaplar.
        
        Args:
            df: OHLCV DataFrame
            period: MA periyodu
            
        Returns:
            Volume MA değeri
        """
        if period is None:
            period = self.volume_ma_period
            
        return df['volume'].rolling(
            window=period
        ).mean().iloc[-1]
    
    def _get_volume_signal(self, relative_volume: float, 
                          df: pd.DataFrame) -> str:
        """
        Hacim ve fiyat hareketine göre sinyal üretir.
        
        Args:
            relative_volume: Göreceli hacim
            df: OHLCV DataFrame
            
        Returns:
            Sinyal: LONG, SHORT, veya NEUTRAL
        """
        # Son 2 mumun fiyat hareketine bak
        price_change = (
            (df['close'].iloc[-1] - df['close'].iloc[-2]) / 
            df['close'].iloc[-2]
        )
        
        # Hacim spike varsa daha güçlü sinyal
        if relative_volume >= self.spike_threshold:
            if price_change > 0:
                return 'LONG'
            elif price_change < 0:
                return 'SHORT'
        
        # Normal hacimde daha yumuşak eşikler
        if price_change > 0.002:  # %0.2 üstü
            return 'LONG'
        elif price_change < -0.002:  # %0.2 altı
            return 'SHORT'
        else:
            return 'NEUTRAL'
    
    def get_volume_trend(self, df: pd.DataFrame, 
                        periods: int = 5) -> str:
        """
        Son N periyottaki hacim trendini belirler.
        
        Args:
            df: OHLCV DataFrame
            periods: İncelenecek periyot sayısı
            
        Returns:
            'INCREASING', 'DECREASING', veya 'STABLE'
        """
        if df is None or len(df) < periods:
            return 'STABLE'
        
        recent_volumes = df['volume'].tail(periods)
        
        # Linear regression ile trend
        x = range(len(recent_volumes))
        y = recent_volumes.values
        
        if len(x) < 2:
            return 'STABLE'
        
        slope = (
            (len(x) * sum(xi * yi for xi, yi in zip(x, y)) - 
             sum(x) * sum(y)) /
            (len(x) * sum(xi ** 2 for xi in x) - sum(x) ** 2)
        )
        
        if slope > 0.1:
            return 'INCREASING'
        elif slope < -0.1:
            return 'DECREASING'
        else:
            return 'STABLE'

