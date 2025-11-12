"""
Technical Indicators Unit Tests: Teknik gösterge testleri.
"""
import pytest
import pandas as pd
import numpy as np
from analysis.technical_indicators import TechnicalIndicatorCalculator


class TestTechnicalIndicatorCalculator:
    """TechnicalIndicatorCalculator testleri."""
    
    def test_rsi_calculation(self, sample_ohlcv_data):
        """RSI hesaplama testi."""
        calc = TechnicalIndicatorCalculator()
        indicators = calc.calculate_all(sample_ohlcv_data)
        
        assert 'rsi' in indicators
        assert 0 <= indicators['rsi']['value'] <= 100
        assert indicators['rsi']['signal'] in ['LONG', 'SHORT', 'NEUTRAL']
    
    def test_macd_calculation(self, sample_ohlcv_data):
        """MACD hesaplama testi."""
        calc = TechnicalIndicatorCalculator()
        indicators = calc.calculate_all(sample_ohlcv_data)
        
        assert 'macd' in indicators
        assert 'macd' in indicators['macd']  # Gerçek yapı: macd, signal, histogram
        assert 'signal' in indicators['macd']
        assert indicators['macd']['signal'] in ['LONG', 'SHORT', 'NEUTRAL']
    
    def test_ema_calculation(self, sample_ohlcv_data):
        """EMA hesaplama testi."""
        calc = TechnicalIndicatorCalculator()
        indicators = calc.calculate_all(sample_ohlcv_data)
        
        assert 'ema' in indicators
        assert 'ema_short' in indicators['ema']  # Gerçek yapı: ema_short, ema_medium, ema_long
        assert 'ema_medium' in indicators['ema']
        assert 'ema_long' in indicators['ema']
        assert 'signal' in indicators['ema']
        assert indicators['ema']['signal'] in ['LONG', 'SHORT', 'NEUTRAL']
    
    def test_bollinger_bands_calculation(self, sample_ohlcv_data):
        """Bollinger Bands hesaplama testi."""
        calc = TechnicalIndicatorCalculator()
        indicators = calc.calculate_all(sample_ohlcv_data)
        
        assert 'bollinger' in indicators
        assert 'upper' in indicators['bollinger']
        assert 'middle' in indicators['bollinger']
        assert 'lower' in indicators['bollinger']
        assert 'signal' in indicators['bollinger']
        assert indicators['bollinger']['signal'] in ['LONG', 'SHORT', 'NEUTRAL']
    
    def test_atr_calculation(self, sample_ohlcv_data):
        """ATR hesaplama testi."""
        calc = TechnicalIndicatorCalculator()
        indicators = calc.calculate_all(sample_ohlcv_data)
        
        assert 'atr' in indicators
        assert indicators['atr'] > 0  # ATR tek değer döndürüyor
        # assert 'signal' in indicators['atr']  # ATR'de signal yok
    
    def test_adx_calculation(self, sample_ohlcv_data):
        """ADX hesaplama testi."""
        calc = TechnicalIndicatorCalculator()
        indicators = calc.calculate_all(sample_ohlcv_data)
        
        assert 'adx' in indicators
        assert 0 <= indicators['adx']['value'] <= 100
        assert 'signal' in indicators['adx']
    
    def test_insufficient_data(self):
        """Yetersiz veri testi."""
        calc = TechnicalIndicatorCalculator()
        
        # Çok az veri ile test
        small_data = pd.DataFrame({
            'open': [100, 101, 102],
            'high': [101, 102, 103],
            'low': [99, 100, 101],
            'close': [100, 101, 102],
            'volume': [1000, 1100, 1200]
        })
        
        result = calc.calculate_all(small_data)
        assert result is None
    
    def test_empty_dataframe(self):
        """Boş DataFrame testi."""
        calc = TechnicalIndicatorCalculator()
        empty_df = pd.DataFrame()
        
        result = calc.calculate_all(empty_df)
        assert result is None
    
    def test_none_dataframe(self):
        """None DataFrame testi."""
        calc = TechnicalIndicatorCalculator()
        
        result = calc.calculate_all(None)
        assert result is None
