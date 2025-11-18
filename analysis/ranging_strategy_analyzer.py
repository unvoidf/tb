"""
RangingStrategyAnalyzer: Bollinger Bands + RSI tabanlı mean-reversion strateji analizörü.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Union, Tuple

import pandas as pd

from utils.logger import LoggerManager


@dataclass
class RangingSignalResult:
    """Ranging stratejisi analiz sonucu."""

    direction: str
    confidence: float
    score_breakdown: Dict[str, float]
    custom_targets: Dict[str, Dict[str, float]]
    strategy_type: str = "ranging"

    def to_dict(self) -> Dict:
        """Dict formatına dönüştürür."""
        return {
            "direction": self.direction,
            "confidence": self.confidence,
            "score_breakdown": self.score_breakdown,
            "custom_targets": self.custom_targets,
            "strategy_type": self.strategy_type,
        }


class RangingStrategyAnalyzer:
    """
    Mean-reversion stratejisi için Bollinger Bands ve RSI verilerini kullanır.

    LONG/SHORT kararlarında Bollinger alt/üst bant yakınlığını ve RSI aşırılıklarını
    birleştirerek güven skorunu hesaplar. Ayrıca TP/SL hedefleri üretir.
    """

    def __init__(
        self,
        logger_manager: Optional[LoggerManager] = None,
        min_stop_distance_percent: float = 0.5,
    ):
        self.logger = (
            logger_manager.get_logger("RangingStrategyAnalyzer")
            if logger_manager
            else LoggerManager().get_logger("RangingStrategyAnalyzer")
        )
        try:
            # Yüzdelik değeri orana çevir (örn: 0.5 -> 0.005)
            ratio = max(float(min_stop_distance_percent), 0.0) / 100.0
        except (TypeError, ValueError):
            ratio = 0.005
            self.logger.warning(
                f"Invalid min_stop_distance_percent value, using default 0.5%"
            )
        # Minimum %0.1 (0.001) sınırı ile aşırı düşük değerleri engelle
        self.min_stop_distance_ratio = max(ratio, 0.001)
        
        # Debug: Hangi değerin kullanıldığını logla
        self.logger.debug(
            f"RangingStrategyAnalyzer initialized with min_stop_distance_percent={min_stop_distance_percent}% "
            f"(ratio={self.min_stop_distance_ratio:.6f})"
        )

    def generate_signal(
        self, df: pd.DataFrame, indicators: Dict[str, Dict], return_reason: bool = False
    ) -> Union[Optional[Dict], Tuple[Optional[Dict], str]]:
        """
        Ranging stratejisine göre sinyal üretir.

        Args:
            df: OHLCV DataFrame
            indicators: Teknik gösterge sonuçları (bollinger, rsi vb.)
            return_reason: True ise (signal, reason) tuple döndürür

        Returns:
            Sinyal dict (direction, confidence, score_breakdown, custom targets)
            veya (signal, reason) tuple
        """
        def _ret(sig, reason=None):
            if return_reason:
                return sig, (reason or "NO_SIGNAL")
            return sig

        if df is None or len(df) < 30:
            self.logger.debug(
                "RangingStrategyAnalyzer.generate_signal -> insufficient data: %s",
                len(df) if df is not None else 0,
            )
            return _ret(None, "INSUFFICIENT_DATA")

        bollinger = indicators.get("bollinger")
        rsi = indicators.get("rsi")

        if not bollinger or not rsi:
            self.logger.debug(
                "RangingStrategyAnalyzer.generate_signal -> missing indicators: "
                "bollinger=%s, rsi=%s",
                bool(bollinger),
                bool(rsi),
            )
            return _ret(None, "MISSING_INDICATORS")

        close_price = df["close"].iloc[-1]
        bb_upper = bollinger.get("upper")
        bb_lower = bollinger.get("lower")
        bb_middle = bollinger.get("middle")

        if None in (bb_upper, bb_lower, bb_middle):
            self.logger.debug(
                "RangingStrategyAnalyzer.generate_signal -> incomplete bollinger data"
            )
            return _ret(None, "INCOMPLETE_DATA")

        bb_range = bb_upper - bb_lower
        if bb_range <= 0:
            self.logger.debug(
                "RangingStrategyAnalyzer.generate_signal -> invalid bollinger range: %s",
                bb_range,
            )
            return _ret(None, "INVALID_DATA")

        # Mean reversion için fiyatın banda çok yakın olması gerekiyor
        # %10'luk bir alan kullan (önceden %20 idi, çok genişti)
        lower_threshold = bb_lower + bb_range * 0.1
        upper_threshold = bb_upper - bb_range * 0.1

        # Normalized Position Kontrolü (Breakout/Breakdown Filtresi)
        # Mean reversion için fiyatın Bollinger bantları içinde olması gerekir
        # normalized_position: 0.0 = alt band, 1.0 = üst band
        # > 1.0 = breakout (üst bandın üzeri), < 0.0 = breakdown (alt bandın altı)
        normalized_position = (close_price - bb_lower) / bb_range if bb_range > 0 else 0.5
        
        if normalized_position > 1.0:
            # Breakout durumu: Fiyat üst bandın üzerinde
            # Mean reversion değil, trend devam ediyor olabilir
            self.logger.info(
                f"Sinyal reddedildi: Normalized Position {normalized_position:.3f} > 1.0 "
                f"(Breakout durumu). Fiyat üst bandın {(normalized_position - 1.0) * 100:.1f}% üzerinde. "
                f"Mean reversion için uygun değil."
            )
            return _ret(None, "FILTER_BREAKOUT")
        
        if normalized_position < 0.0:
            # Breakdown durumu: Fiyat alt bandın altında
            # Mean reversion değil, trend devam ediyor olabilir
            self.logger.info(
                f"Sinyal reddedildi: Normalized Position {normalized_position:.3f} < 0.0 "
                f"(Breakdown durumu). Fiyat alt bandın {abs(normalized_position) * 100:.1f}% altında. "
                f"Mean reversion için uygun değil."
            )
            return _ret(None, "FILTER_BREAKDOWN")

        bb_bias = self._detect_bollinger_bias(
            close_price, lower_threshold, upper_threshold
        )
        rsi_bias, rsi_value = self._detect_rsi_bias(rsi)

        direction, confidence = self._resolve_direction_and_confidence(
            bb_bias, rsi_bias, close_price, bb_lower, bb_upper, rsi_value
        )

        if direction == "NEUTRAL":
            result = RangingSignalResult(
                direction="NEUTRAL",
                confidence=confidence,
                score_breakdown=self._build_score_breakdown(
                    bb_bias, rsi_bias, rsi_value, close_price, bb_lower, bb_upper
                ),
                custom_targets={},
            ).to_dict()
            # NEUTRAL sinyaller de bir sinyaldir, ama confidence düşük olabilir.
            # SignalGenerator bunları kullanabilir (veto için vs).
            return _ret(result, "NEUTRAL_DIRECTION")

        # ATR değerini al (Volatilite bazlı stop için)
        atr_data = indicators.get("atr")
        # ATR bazen dict, bazen float gelebiliyor, kontrol et
        atr_val = None
        if isinstance(atr_data, dict):
            atr_val = atr_data.get("value")
        elif isinstance(atr_data, (int, float)):
            atr_val = float(atr_data)
            
        custom_targets = self._build_custom_targets(
            direction, close_price, bb_lower, bb_middle, bb_upper, atr_val
        )

        # Risk/Reward Kontrolü (Endüstri Standardı: Min 1:1.5)
        tp_price = custom_targets.get("tp1", {}).get("price")
        sl_price = custom_targets.get("stop_loss", {}).get("price")
        
        if tp_price and sl_price:
            risk = abs(close_price - sl_price)
            reward = abs(tp_price - close_price)
            
            if risk > 0:
                rr_ratio = reward / risk
                if rr_ratio < 1.5:
                    self.logger.info(
                        f"Sinyal reddedildi: Yetersiz Risk/Reward Oranı ({rr_ratio:.2f} < 1.5). "
                        f"Risk={risk:.4f}, Reward={reward:.4f}"
                    )
                    return _ret(None, "FILTER_R_R")
            else:
                self.logger.warning("Risk 0 hesaplandı, sinyal reddedildi.")
                return _ret(None, "INVALID_RISK")

        score_breakdown = self._build_score_breakdown(
            bb_bias, rsi_bias, rsi_value, close_price, bb_lower, bb_upper
        )

        self.logger.debug(
            "RangingStrategyAnalyzer.generate_signal -> dir=%s, conf=%.3f, "
            "rsi=%.2f, price=%.4f, bb_bias=%s",
            direction,
            confidence,
            rsi_value if rsi_value is not None else -1,
            close_price,
            bb_bias,
        )

        result = RangingSignalResult(
            direction=direction,
            confidence=confidence,
            score_breakdown=score_breakdown,
            custom_targets=custom_targets,
        ).to_dict()
        
        return _ret(result, "SUCCESS")

    def _detect_bollinger_bias(
        self, price: float, lower_threshold: float, upper_threshold: float
    ) -> str:
        """Bollinger alt/üst band yakınlığına göre bias döndürür."""
        if price <= lower_threshold:
            return "LONG"
        if price >= upper_threshold:
            return "SHORT"
        return "NEUTRAL"

    def _detect_rsi_bias(self, rsi_data: Dict) -> tuple[str, Optional[float]]:
        """RSI değerine göre bias döndürür."""
        rsi_value = rsi_data.get("value")
        if rsi_value is None:
            return "NEUTRAL", None

        if rsi_value <= 35:
            return "LONG", rsi_value
        if rsi_value >= 65:
            return "SHORT", rsi_value
        return "NEUTRAL", rsi_value

    def _resolve_direction_and_confidence(
        self,
        bb_bias: str,
        rsi_bias: str,
        price: float,
        bb_lower: float,
        bb_upper: float,
        rsi_value: Optional[float],
    ) -> tuple[str, float]:
        """
        Bollinger ve RSI sinyallerini birleştirerek yön ve confidence belirler.
        """
        # Her iki sinyal de aynı yönde
        if bb_bias in ("LONG", "SHORT") and bb_bias == rsi_bias:
            confidence = 0.8
            confidence += self._band_proximity_bonus(
                bb_bias, price, bb_lower, bb_upper
            )
            confidence += self._rsi_extremity_bonus(bb_bias, rsi_value)
            return bb_bias, min(confidence, 0.95)

        # Bollinger belirleyici, RSI nötr
        if bb_bias in ("LONG", "SHORT") and rsi_bias == "NEUTRAL":
            confidence = 0.65 + self._band_proximity_bonus(
                bb_bias, price, bb_lower, bb_upper
            )
            return bb_bias, min(confidence, 0.8)

        # RSI belirleyici, Bollinger nötr
        # Mean reversion için fiyatın banda yakın olması gerekiyor
        if rsi_bias in ("LONG", "SHORT") and bb_bias == "NEUTRAL":
            # Fiyatın banda yakınlığını kontrol et
            band_range = bb_upper - bb_lower
            if band_range > 0:
                normalized_position = (price - bb_lower) / band_range
                # Fiyat bandın %15'lik alt veya üst bölgesinde olmalı
                if rsi_bias == "LONG" and normalized_position > 0.15:
                    # Fiyat alt banda yakın değil, sinyal üretme
                    return "NEUTRAL", 0.4
                if rsi_bias == "SHORT" and normalized_position < 0.85:
                    # Fiyat üst banda yakın değil, sinyal üretme
                    return "NEUTRAL", 0.4
            confidence = 0.6 + self._rsi_extremity_bonus(rsi_bias, rsi_value)
            # Fiyat banda yakınsa, proximity bonus ekle
            confidence += self._band_proximity_bonus(
                rsi_bias, price, bb_lower, bb_upper
            )
            return rsi_bias, min(confidence, 0.75)

        # Çelişki varsa sinyal üretme
        return "NEUTRAL", 0.4

    def _band_proximity_bonus(
        self, direction: str, price: float, bb_lower: float, bb_upper: float
    ) -> float:
        """Fiyatın banda yakınlığına göre küçük bir bonus hesaplar."""
        if direction == "LONG":
            distance = max(price - bb_lower, 0.0)
            band_range = bb_upper - bb_lower
            proximity = 1 - min(distance / band_range, 1)
            return proximity * 0.1
        if direction == "SHORT":
            distance = max(bb_upper - price, 0.0)
            band_range = bb_upper - bb_lower
            proximity = 1 - min(distance / band_range, 1)
            return proximity * 0.1
        return 0.0

    def _rsi_extremity_bonus(
        self, direction: str, rsi_value: Optional[float]
    ) -> float:
        """RSI aşırılığına bağlı confidence bonusu."""
        if rsi_value is None:
            return 0.0

        if direction == "LONG" and rsi_value <= 25:
            return 0.1
        if direction == "SHORT" and rsi_value >= 75:
            return 0.1
        return 0.0

    def _build_custom_targets(
        self,
        direction: str,
        current_price: float,
        bb_lower: float,
        bb_middle: float,
        bb_upper: float,
        atr: Optional[float] = None,
    ) -> Dict[str, Dict[str, float]]:
        """Ranging stratejisi için TP/SL hedefleri oluşturur."""
        band_range = bb_upper - bb_lower
        if band_range <= 0:
            return {}

        targets = {
            "tp1": {
                "price": bb_middle,
                "label": "Bollinger Middle Band",
                "type": "mean_reversion",
            },
            "tp2": {
                "price": bb_upper if direction == "LONG" else bb_lower,
                "label": (
                    "Bollinger Upper Band" if direction == "LONG" else "Bollinger Lower Band"
                ),
                "type": "mean_reversion",
            },
        }

        # Stop-loss hesaplama: ATR varsa onu kullan, yoksa band buffer kullan
        # Endüstri standardı: Volatilite bazlı stop (ATR Trailing Stop mantığı)
        
        # ATR Multiplier: Ranging piyasada gürültüden kaçmak için 1.5 - 2 ATR idealdir.
        atr_sl_multiplier = 2.0 
        
        if atr:
            if direction == "LONG":
                stop_price = current_price - (atr * atr_sl_multiplier)
                # Eğer Bollinger alt bandı ATR stop'tan daha aşağıdaysa, bandı kullan (daha geniş alan)
                # Ancak mean reversion'da çok geniş stop istemeyiz. ATR genelde daha güvenlidir.
                # Stop, girişin altında olmalı.
                stop_price = min(stop_price, bb_lower - (band_range * 0.02)) 
            else: # SHORT
                stop_price = current_price + (atr * atr_sl_multiplier)
                stop_price = max(stop_price, bb_upper + (band_range * 0.02))
                
            sl_label = f"ATR Stop ({atr_sl_multiplier}x)"
        else:
            # Fallback: Bollinger Band Buffer (Eski yöntem, ama buffer artırıldı)
            buffer = band_range * 0.10 # %5 -> %10 buffer
            
            if direction == "LONG":
                base_stop = bb_lower - buffer
                # Minimum mesafe kontrolü
                min_stop_dist = current_price * 0.01 # Min %1 stop
                stop_price = min(base_stop, current_price - min_stop_dist)
            else:
                base_stop = bb_upper + buffer
                min_stop_dist = current_price * 0.01 # Min %1 stop
                stop_price = max(base_stop, current_price + min_stop_dist)
                
            sl_label = "Bollinger Band Breach (+Buffer)"

        # Güvenlik kontrolü: Stop fiyatı negatif olamaz
        stop_price = max(stop_price, 0.0)

        targets["stop_loss"] = {
            "price": stop_price,
            "label": sl_label,
            "type": "protective",
        }

        return targets

    def _build_score_breakdown(
        self,
        bb_bias: str,
        rsi_bias: str,
        rsi_value: Optional[float],
        price: float,
        bb_lower: float,
        bb_upper: float,
    ) -> Dict[str, float]:
        """Sinyal bileşenlerini açıklayan score breakdown oluşturur."""
        band_range = bb_upper - bb_lower
        normalized_position = (
            0.0 if band_range == 0 else (price - bb_lower) / band_range
        )

        return {
            "bollinger_bias": bb_bias,
            "rsi_bias": rsi_bias,
            "rsi_value": rsi_value if rsi_value is not None else 0.0,
            "normalized_price_position": normalized_position,
        }

