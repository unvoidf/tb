"""
AdaptiveThresholdManager: Dinamik eşik değerleri yönetimi.
Volatilite ve trend gücüne göre gösterge eşiklerini ayarlar.
"""
import pandas as pd
from typing import Dict
from utils.logger import LoggerManager


class AdaptiveThresholdManager:
    """Piyasa koşullarına göre eşik değerlerini ayarlar."""
    
    def __init__(self, adx_weak_threshold: float = 20,
                 adx_strong_threshold: float = 40):
        """
        AdaptiveThresholdManager'ı başlatır.
        
        Args:
            adx_weak_threshold: Zayıf trend eşiği
            adx_strong_threshold: Güçlü trend eşiği
        """
        self.adx_weak = adx_weak_threshold
        self.adx_strong = adx_strong_threshold
        self.logger = LoggerManager().get_logger('AdaptiveThresholdManager')
    
    def calculate_volatility(self, df: pd.DataFrame, 
                           atr: float) -> Dict:
        """
        Volatilite metriklerini hesaplar.
        
        Args:
            df: OHLCV DataFrame
            atr: ATR değeri
            
        Returns:
            Volatilite bilgileri dict
        """
        current_price = df['close'].iloc[-1]
        volatility_ratio = (atr / current_price) * 100
        
        return {
            'atr': atr,
            'ratio': volatility_ratio,
            'level': self._get_volatility_level(volatility_ratio)
        }
    
    def _get_volatility_level(self, ratio: float) -> str:
        """
        Volatilite seviyesini belirler.
        
        Args:
            ratio: Volatilite oranı (%)
            
        Returns:
            'LOW', 'MEDIUM', veya 'HIGH'
        """
        if ratio < 1.0:
            return 'LOW'
        elif ratio < 3.0:
            return 'MEDIUM'
        else:
            return 'HIGH'
    
    def get_adaptive_rsi_thresholds(self, adx_value: float,
                                   volatility_level: str) -> Dict[str, float]:
        """
        ADX ve volatiliteye göre RSI eşiklerini ayarlar.
        
        Args:
            adx_value: ADX değeri
            volatility_level: Volatilite seviyesi
            
        Returns:
            RSI oversold/overbought eşikleri
        """
        base_oversold = 30
        base_overbought = 70
        
        # Güçlü trend varsa eşikleri genişlet
        if adx_value > self.adx_strong:
            oversold = base_oversold - 10
            overbought = base_overbought + 10
        elif adx_value < self.adx_weak:
            # Zayıf trend, dar eşikler
            oversold = base_oversold + 5
            overbought = base_overbought - 5
        else:
            oversold = base_oversold
            overbought = base_overbought
        
        # Yüksek volatilitede eşikleri ayarla
        if volatility_level == 'HIGH':
            oversold -= 5
            overbought += 5
        
        return {
            'oversold': max(20, oversold),
            'overbought': min(80, overbought)
        }
    
    def calculate_trend_strength(self, adx_value: float) -> Dict:
        """
        Trend gücünü kategorize eder.
        
        Args:
            adx_value: ADX değeri
            
        Returns:
            Trend gücü bilgileri
        """
        if adx_value < self.adx_weak:
            strength = 'WEAK'
            confidence = 0.3
        elif adx_value < self.adx_strong:
            strength = 'MODERATE'
            confidence = 0.6
        else:
            strength = 'STRONG'
            confidence = 0.9
        
        return {
            'strength': strength,
            'confidence': confidence,
            'value': adx_value
        }
    
    def adjust_signal_confidence(
        self, base_confidence: float,
        trend_strength: Dict,
        volatility: Dict,
        direction: str = None,
        indicators: Dict = None,
        market_context: Dict = None,
        volume: Dict = None
    ) -> float:
        """
        Trend gücü, volatilite, RSI aşırılık ve çelişki cezalarına göre 
        sinyal güvenilirliğini ayarlar.
        
        4 yapay zeka (DeepSeek, ChatGPT, Perplexity) ve 1 finans uzmanının 
        ortak önerileri uygulanmıştır.
        
        Args:
            base_confidence: Temel güvenilirlik skoru
            trend_strength: Trend gücü bilgisi
            volatility: Volatilite bilgisi
            direction: Sinyal yönü (LONG/SHORT) - opsiyonel
            indicators: Teknik göstergeler dict - opsiyonel
            market_context: Market context bilgisi (volatility_percentile vb.) - opsiyonel
            volume: Volume analizi dict - opsiyonel
            
        Returns:
            Ayarlanmış güvenilirlik skoru
        """
        adjusted = base_confidence
        
        # Güçlü trend confidence artırır
        if trend_strength['strength'] == 'STRONG':
            adjusted *= 1.2
        elif trend_strength['strength'] == 'WEAK':
            adjusted *= 0.8
        
        # Crash Protection: Çok güçlü trendlerde (ADX > 45) ters yönde işlem açma güvenini sıfırla
        adx_value = trend_strength.get('value', 0)
        if adx_value > 45 and direction:
            # Trend çok güçlüyse, ters yönde işlem açma güvenini çok düşür
            if direction == 'LONG' and volatility.get('level') == 'HIGH':
                # Düşen bıçak koruması: Yüksek volatilitede LONG sinyali
                adjusted *= 0.1  # Güveni %90 kır
                self.logger.warning(
                    f"Crash protection aktif: ADX={adx_value:.1f} > 45, "
                    f"direction={direction}, volatility=HIGH. "
                    f"Confidence {base_confidence:.3f} -> {adjusted:.3f}"
                )
            elif direction == 'SHORT' and volatility.get('level') == 'HIGH':
                # Pump koruması: Yüksek volatilitede SHORT sinyali
                adjusted *= 0.1  # Güveni %90 kır
                self.logger.warning(
                    f"Pump protection aktif: ADX={adx_value:.1f} > 45, "
                    f"direction={direction}, volatility=HIGH. "
                    f"Confidence {base_confidence:.3f} -> {adjusted:.3f}"
                )
        
        # Yüksek volatilite confidence azaltır
        if volatility['level'] == 'HIGH':
            adjusted *= 0.9
        elif volatility['level'] == 'LOW':
            adjusted *= 1.05
        
        # Aşırı Yüksek Volatilite Cezası (>90 percentile) - Perplexity Önerisi
        if market_context:
            volatility_percentile = market_context.get('volatility_percentile', 0)
            if volatility_percentile > 90:
                adjusted *= 0.85  # Orta seviye ceza
                self.logger.debug(
                    f"Aşırı volatilite cezası: percentile={volatility_percentile:.1f}, "
                    f"adjusted={adjusted:.3f}"
                )
        
        # RSI Aşırılık Cezası (Finans Uzmanı + 4 AI Önerisi)
        if direction and indicators:
            rsi_data = indicators.get('rsi', {})
            rsi_value = rsi_data.get('value')
            
            if rsi_value is not None:
                if direction == 'LONG' and rsi_value > 70:
                    # RSI 70-100 arası → 0-1 ceza katsayısı
                    penalty = (rsi_value - 70) / 30
                    adjusted *= (1 - penalty * 0.3)  # Max %30 düşüş
                    self.logger.debug(
                        f"RSI aşırı alım cezası: RSI={rsi_value:.1f}, "
                        f"penalty={penalty:.2f}, adjusted={adjusted:.3f}"
                    )
                    
                elif direction == 'SHORT' and rsi_value < 30:
                    # RSI 0-30 arası → 1-0 ceza katsayısı
                    penalty = (30 - rsi_value) / 30
                    adjusted *= (1 - penalty * 0.3)  # Max %30 düşüş
                    self.logger.debug(
                        f"RSI aşırı satım cezası: RSI={rsi_value:.1f}, "
                        f"penalty={penalty:.2f}, adjusted={adjusted:.3f}"
                    )
            
            # Volume + RSI Momentum Check (ChatGPT + DeepSeek Önerisi)
            if volume and rsi_value is not None:
                volume_spike = volume.get('spike', False)
                if volume_spike:
                    if direction == 'LONG' and rsi_value < 60:
                        adjusted *= 0.9  # Momentum zayıf
                        self.logger.debug(
                            f"Volume spike ama zayıf momentum (LONG): RSI={rsi_value:.1f}, "
                            f"adjusted={adjusted:.3f}"
                        )
                    elif direction == 'SHORT' and rsi_value > 40:
                        adjusted *= 0.9  # Momentum zayıf
                        self.logger.debug(
                            f"Volume spike ama zayıf momentum (SHORT): RSI={rsi_value:.1f}, "
                            f"adjusted={adjusted:.3f}"
                        )
            
            # İndikatör Çelişki Cezası (Confluence Kontrolü) - 4 AI Önerisi
            conflicting_signals = 0
            
            # EMA Alignment Check (ChatGPT + DeepSeek Önerisi)
            ema_data = indicators.get('ema', {})
            ema_aligned = ema_data.get('aligned', False)
            if not ema_aligned:
                conflicting_signals += 1
                self.logger.debug("EMA alignment yok, çelişki +1")
            
            # MACD Histogram Check (ChatGPT + DeepSeek Önerisi)
            macd_data = indicators.get('macd', {})
            macd_histogram = macd_data.get('histogram', 0)
            if direction == 'LONG' and macd_histogram < 0:
                conflicting_signals += 1
                self.logger.debug(f"MACD histogram negatif ama LONG, çelişki +1")
            elif direction == 'SHORT' and macd_histogram > 0:
                conflicting_signals += 1
                self.logger.debug(f"MACD histogram pozitif ama SHORT, çelişki +1")
            
            # ADX +DI/-DI Yön Kontrolü (Perplexity Önerisi)
            adx_data = indicators.get('adx', {})
            plus_di = adx_data.get('plus_di', 0)
            minus_di = adx_data.get('minus_di', 0)
            
            if direction == 'LONG':
                # LONG için +DI > -DI ve fark > 10 olmalı
                if not (plus_di > minus_di and (plus_di - minus_di) > 10):
                    conflicting_signals += 1
                    self.logger.debug(
                        f"ADX yön uyumsuz (LONG): +DI={plus_di:.1f}, -DI={minus_di:.1f}, çelişki +1"
                    )
            elif direction == 'SHORT':
                # SHORT için -DI > +DI ve fark > 10 olmalı
                if not (minus_di > plus_di and (minus_di - plus_di) > 10):
                    conflicting_signals += 1
                    self.logger.debug(
                        f"ADX yön uyumsuz (SHORT): +DI={plus_di:.1f}, -DI={minus_di:.1f}, çelişki +1"
                    )
            
            # RSI/Bollinger çelişkisi (Mevcut)
            if direction == 'LONG':
                if rsi_data.get('signal') == 'SHORT':
                    conflicting_signals += 1
                bb_data = indicators.get('bollinger', {})
                if bb_data.get('signal') == 'SHORT':
                    conflicting_signals += 1
                    
            elif direction == 'SHORT':
                if rsi_data.get('signal') == 'LONG':
                    conflicting_signals += 1
                bb_data = indicators.get('bollinger', {})
                if bb_data.get('signal') == 'LONG':
                    conflicting_signals += 1
            
            # 2+ çelişki varsa %30 ceza
            if conflicting_signals >= 2:
                adjusted *= 0.7
                self.logger.info(
                    f"İndikatör çelişki cezası: {conflicting_signals} çelişki tespit edildi, "
                    f"adjusted={adjusted:.3f}"
                )
        
        return min(1.0, adjusted)

