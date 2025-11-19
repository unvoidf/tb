"""
MarketAnalyzer: Piyasa rejimi ve koşul analizi.
Global market condition, regime detection, circuit breaker checks.
"""
import pandas as pd
from typing import Dict, Optional
from utils.logger import LoggerManager


class MarketAnalyzer:
    """Piyasa analiz helper sınıfı."""
    
    def __init__(self, market_data_manager=None, indicator_calculator=None, volume_analyzer=None):
        """
        MarketAnalyzer'ı başlatır.
        
        Args:
            market_data_manager: Market data manager (BTC correlation için)
            indicator_calculator: Technical indicator calculator (opsiyonel, circuit breaker için)
            volume_analyzer: Volume analyzer (opsiyonel, volume climax için)
        """
        self.market_data = market_data_manager
        self.indicator_calc = indicator_calculator
        self.volume_analyzer = volume_analyzer
        self.logger = LoggerManager().get_logger('MarketAnalyzer')
    
    def detect_market_regime(self, indicators: Dict) -> str:
        """
        EMA alignment ve ADX değerine göre piyasa rejimini belirler.
        
        Args:
            indicators: Teknik göstergeler
            
        Returns:
            Market regime: 'trending_up', 'trending_down', 'ranging'
        """
        try:
            ema_data = indicators.get('ema', {}) if isinstance(indicators, dict) else {}
            adx_data = indicators.get('adx', {}) if isinstance(indicators, dict) else {}
            
            ema_aligned = ema_data.get('aligned', False)
            ema_signal = ema_data.get('signal', 'NEUTRAL')
            
            adx_value = adx_data.get('value', 0) if isinstance(adx_data, dict) else 0
            
            if ema_aligned and adx_value > 25:
                if ema_signal == 'LONG':
                    return 'trending_up'
                if ema_signal == 'SHORT':
                    return 'trending_down'
            
            return 'ranging'
        except Exception:
            return 'ranging'
    
    def check_global_market_condition(self) -> str:
        """
        Global piyasa koşulunu kontrol eder (BTC bazlı).
        
        Returns:
            Market condition: 'BULLISH', 'BEARISH_CRASH', 'NEUTRAL'
        """
        if not self.market_data:
            return 'NEUTRAL'
        
        try:
            # BTC 1h ve 4h verilerini al
            btc_1h = self.market_data.fetch_ohlcv('BTC/USDT', '1h', 50)
            btc_4h = self.market_data.fetch_ohlcv('BTC/USDT', '4h', 50)
            
            if btc_1h is None or btc_4h is None:
                return 'NEUTRAL'
            
            # 1h son 10 mum: %5'ten fazla düşüş
            recent_1h = btc_1h.tail(10)
            price_change_1h = ((recent_1h['close'].iloc[-1] - recent_1h['close'].iloc[0]) / 
                              recent_1h['close'].iloc[0]) * 100
            
            # 4h son 5 mum: %8'den fazla düşüş
            recent_4h = btc_4h.tail(5)
            price_change_4h = ((recent_4h['close'].iloc[-1] - recent_4h['close'].iloc[0]) / 
                              recent_4h['close'].iloc[0]) * 100
            
            if price_change_1h < -5 and price_change_4h < -8:
                self.logger.warning(
                    f"BTC crash detected: 1h={price_change_1h:.2f}%, 4h={price_change_4h:.2f}%"
                )
                return 'BEARISH_CRASH'
            
            return 'NEUTRAL'
            
        except Exception as e:
            self.logger.error(f"Global market check error: {str(e)}")
            return 'NEUTRAL'
    
    def check_intraday_circuit_breaker(self, multi_tf_data: Dict[str, pd.DataFrame]) -> bool:
        """
        Intraday circuit breaker kontrolü.
        
        Args:
            multi_tf_data: Multi-timeframe data
            
        Returns:
            True ise circuit breaker aktif (sinyal reddedilmeli)
        """
        try:
            if '1h' not in multi_tf_data:
                return False
            
            df_1h = multi_tf_data['1h']
            if len(df_1h) < 10:
                return False
            
            # Son 6 saatte %10+ volatilite
            recent = df_1h.tail(6)
            max_price = recent['high'].max()
            min_price = recent['low'].min()
            volatility = ((max_price - min_price) / min_price) * 100
            
            if volatility > 10:
                self.logger.warning(f"Circuit breaker: 6h volatility={volatility:.2f}%")
                return True
            
            return False
            
        except Exception:
            return False
    
    def check_volume_climax(self, multi_tf_data: Dict[str, pd.DataFrame]) -> bool:
        """
        Volume climax kontrolü.
        
        Args:
            multi_tf_data: Multi-timeframe data
            
        Returns:
            True ise volume climax var (dikkatli olunmalı)
        """
        try:
            if '1h' not in multi_tf_data:
                return False
            
            df_1h = multi_tf_data['1h']
            if len(df_1h) < 20:
                return False
            
            recent_volume = df_1h['volume'].tail(3).mean()
            avg_volume = df_1h['volume'].tail(20).mean()
            
            # Son 3 mumda ortalama hacmin 3x üstü
            if recent_volume > avg_volume * 3:
                self.logger.info(f"Volume climax detected: recent={recent_volume/avg_volume:.1f}x avg")
                return True
            
            return False
            
        except Exception:
            return False
    
    def create_market_context(self, indicators: Dict, regime: str, symbol: str = None) -> str:
        """
        Market context string oluşturur.
        
        Args:
            indicators: Göstergeler
            regime: Market regime
            symbol: Trading pair
            
        Returns:
            Market context string (kısa özet)
        """
        try:
            adx = indicators.get('adx', 0)
            rsi = indicators.get('rsi', 50)
            
            context_parts = [
                f"Regime: {regime}",
                f"ADX: {adx:.1f}",
                f"RSI: {rsi:.1f}"
            ]
            
            return " | ".join(context_parts)
        except Exception:
            return "Market context unavailable"

