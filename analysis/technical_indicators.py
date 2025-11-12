"""
TechnicalIndicatorCalculator: Teknik gösterge hesaplamaları.
RSI, MACD, EMA, Bollinger Bands, ATR, ADX hesaplar.
"""
import pandas as pd
import numpy as np
from typing import Dict, Tuple
from ta.momentum import RSIIndicator
from ta.trend import MACD, ADXIndicator, EMAIndicator
from ta.volatility import BollingerBands, AverageTrueRange
from utils.logger import LoggerManager


class TechnicalIndicatorCalculator:
    """Teknik göstergeleri hesaplar."""
    
    def __init__(self, rsi_period: int = 14,
                 macd_fast: int = 12,
                 macd_slow: int = 26,
                 macd_signal: int = 9,
                 ema_short: int = 20,
                 ema_medium: int = 50,
                 ema_long: int = 200,
                 bb_period: int = 20,
                 bb_std: int = 2,
                 atr_period: int = 14,
                 adx_period: int = 14):
        """Teknik gösterge parametrelerini başlatır."""
        self.rsi_period = rsi_period
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.ema_short = ema_short
        self.ema_medium = ema_medium
        self.ema_long = ema_long
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.atr_period = atr_period
        self.adx_period = adx_period
        self.logger = LoggerManager().get_logger('TechnicalIndicatorCalculator')
    
    def calculate_all(self, df: pd.DataFrame) -> Dict:
        """
        Tüm teknik göstergeleri hesaplar.
        Veri miktarına göre parametreleri adapte eder.
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            Tüm göstergeleri içeren dict
        """
        if df is None or len(df) < 30:  # Minimum 30 mum gerekli (50'den düşürüldü)
            return None
        
        data_length = len(df)
        
        # Veri miktarına göre parametreleri adapte et
        adaptive_params = self._get_adaptive_parameters(data_length)
        
        self.logger.debug(
            f"Adaptive parameters: data_length={data_length}, "
            f"ema_long={adaptive_params['ema_long']}, "
            f"rsi_period={adaptive_params['rsi_period']}"
        )
        
        result = {
            'rsi': self.calculate_rsi(df, adaptive_params['rsi_period']),
            'macd': self.calculate_macd(df),
            'ema': self.calculate_ema(df, adaptive_params['ema_long']),
            'bollinger': self.calculate_bollinger_bands(df),
            'atr': self.calculate_atr(df, adaptive_params['atr_period']),
            'adx': self.calculate_adx(df, adaptive_params['adx_period'])
        }
        
        return result
    
    def _get_adaptive_parameters(self, data_length: int) -> Dict:
        """
        Veri miktarına göre adaptive parametreler döndürür.
        
        Args:
            data_length: Mevcut veri uzunluğu
            
        Returns:
            Adaptive parametreler dict
        """
        return {
            'ema_long': min(self.ema_long, data_length - 10),
            'rsi_period': min(self.rsi_period, data_length - 5),
            'atr_period': min(self.atr_period, data_length - 5),
            'adx_period': min(self.adx_period, data_length - 5),
            'bb_period': min(self.bb_period, data_length - 5),
            'volume_ma_period': min(20, data_length - 5)
        }
    
    def calculate_rsi(self, df: pd.DataFrame, period: int = None) -> Dict:
        """RSI hesaplar ve sinyal üretir."""
        if period is None:
            period = self.rsi_period
            
        rsi_indicator = RSIIndicator(
            close=df['close'],
            window=period
        )
        rsi_value = rsi_indicator.rsi().iloc[-1]
        
        return {
            'value': rsi_value,
            'signal': self._get_rsi_signal(rsi_value)
        }
    
    def _get_rsi_signal(self, rsi: float) -> str:
        """RSI değerine göre sinyal belirler."""
        if rsi < 45:
            return 'LONG'
        elif rsi > 55:
            return 'SHORT'
        else:
            return 'NEUTRAL'
    
    def calculate_macd(self, df: pd.DataFrame) -> Dict:
        """MACD hesaplar ve sinyal üretir."""
        macd_indicator = MACD(
            close=df['close'],
            window_fast=self.macd_fast,
            window_slow=self.macd_slow,
            window_sign=self.macd_signal
        )
        
        macd_line = macd_indicator.macd().iloc[-1]
        signal_line = macd_indicator.macd_signal().iloc[-1]
        histogram = macd_indicator.macd_diff().iloc[-1]
        
        return {
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram,
            'signal': self._get_macd_signal(macd_line, signal_line)
        }
    
    def _get_macd_signal(self, macd: float, signal: float) -> str:
        """MACD değerine göre sinyal belirler."""
        diff = macd - signal
        threshold = abs(signal) * 0.01  # %1 fark yeterli
        
        if diff > threshold:
            return 'LONG'
        elif diff < -threshold:
            return 'SHORT'
        else:
            return 'NEUTRAL'
    
    def calculate_ema(self, df: pd.DataFrame, ema_long_period: int = None) -> Dict:
        """EMA'ları hesaplar ve sinyal üretir."""
        if ema_long_period is None:
            ema_long_period = self.ema_long
            
        ema_short = EMAIndicator(
            close=df['close'],
            window=self.ema_short
        ).ema_indicator().iloc[-1]
        
        ema_medium = EMAIndicator(
            close=df['close'],
            window=self.ema_medium
        ).ema_indicator().iloc[-1]
        
        ema_long = EMAIndicator(
            close=df['close'],
            window=ema_long_period
        ).ema_indicator().iloc[-1]
        
        current_price = df['close'].iloc[-1]
        
        # EMA Strict Alignment kontrolü (4 yapay zeka önerisi)
        # LONG: short > medium > long olmalı
        # SHORT: short < medium < long olmalı
        aligned = False
        if ema_short > ema_medium > ema_long:
            aligned = True  # Bullish alignment
        elif ema_short < ema_medium < ema_long:
            aligned = True  # Bearish alignment
        
        return {
            'ema_short': ema_short,
            'ema_medium': ema_medium,
            'ema_long': ema_long,
            'aligned': aligned,
            'signal': self._get_ema_signal(
                current_price, ema_short, ema_medium
            )
        }
    
    def _get_ema_signal(self, price: float, 
                       ema_short: float, ema_medium: float) -> str:
        """EMA konumlarına göre sinyal belirler."""
        # Daha esnek: sadece fiyatın EMA'lara göre konumu
        if price > ema_short and ema_short > ema_medium:
            return 'LONG'
        elif price < ema_short and ema_short < ema_medium:
            return 'SHORT'
        elif price > ema_medium:
            return 'LONG'  # Fiyat medium EMA üstünde = bullish eğilim
        elif price < ema_medium:
            return 'SHORT'  # Fiyat medium EMA altında = bearish eğilim
        else:
            return 'NEUTRAL'
    
    def calculate_bollinger_bands(self, df: pd.DataFrame, period: int = None) -> Dict:
        """Bollinger Bands hesaplar ve sinyal üretir."""
        if period is None:
            period = self.bb_period
            
        bb_indicator = BollingerBands(
            close=df['close'],
            window=period,
            window_dev=self.bb_std
        )
        
        bb_high = bb_indicator.bollinger_hband().iloc[-1]
        bb_low = bb_indicator.bollinger_lband().iloc[-1]
        bb_mid = bb_indicator.bollinger_mavg().iloc[-1]
        current_price = df['close'].iloc[-1]
        
        return {
            'upper': bb_high,
            'middle': bb_mid,
            'lower': bb_low,
            'signal': self._get_bb_signal(current_price, bb_low, bb_high)
        }
    
    def _get_bb_signal(self, price: float, 
                      lower: float, upper: float) -> str:
        """Bollinger Bands konumuna göre sinyal belirler."""
        middle = (upper + lower) / 2
        range_size = upper - lower
        
        # Band'lerin %30'una yakınsa sinyal ver
        lower_threshold = lower + (range_size * 0.3)
        upper_threshold = upper - (range_size * 0.3)
        
        if price <= lower_threshold:
            return 'LONG'
        elif price >= upper_threshold:
            return 'SHORT'
        elif price > middle:
            return 'LONG'  # Orta çizginin üstü = bullish eğilim
        elif price < middle:
            return 'SHORT'  # Orta çizginin altı = bearish eğilim
        else:
            return 'NEUTRAL'
    
    def calculate_atr(self, df: pd.DataFrame, period: int = None) -> float:
        """ATR hesaplar."""
        if period is None:
            period = self.atr_period
            
        atr_indicator = AverageTrueRange(
            high=df['high'],
            low=df['low'],
            close=df['close'],
            window=period
        )
        return atr_indicator.average_true_range().iloc[-1]
    
    def calculate_adx(self, df: pd.DataFrame, period: int = None) -> Dict:
        """ADX hesaplar ve trend gücünü belirler."""
        if period is None:
            period = self.adx_period
            
        adx_indicator = ADXIndicator(
            high=df['high'],
            low=df['low'],
            close=df['close'],
            window=period
        )
        
        adx_value = adx_indicator.adx().iloc[-1]
        plus_di = adx_indicator.adx_pos().iloc[-1]
        minus_di = adx_indicator.adx_neg().iloc[-1]
        
        return {
            'value': adx_value,
            'plus_di': plus_di,
            'minus_di': minus_di,
            'strength': self._get_adx_strength(adx_value),
            'signal': self._get_adx_signal(plus_di, minus_di)
        }
    
    def _get_adx_strength(self, adx: float) -> str:
        """ADX değerine göre trend gücünü belirler."""
        if adx < 20:
            return 'WEAK'
        elif adx < 40:
            return 'MODERATE'
        else:
            return 'STRONG'
    
    def _get_adx_signal(self, plus_di: float, minus_di: float) -> str:
        """DI değerlerine göre sinyal belirler."""
        if plus_di > minus_di:
            return 'LONG'
        elif plus_di < minus_di:
            return 'SHORT'
        else:
            return 'NEUTRAL'

