"""
RangingStrategyAnalyzer: Bollinger Bands + RSI tabanlı mean-reversion strateji analizörü.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

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

    def __init__(self, logger_manager: Optional[LoggerManager] = None):
        self.logger = (
            logger_manager.get_logger("RangingStrategyAnalyzer")
            if logger_manager
            else LoggerManager().get_logger("RangingStrategyAnalyzer")
        )

    def generate_signal(
        self, df: pd.DataFrame, indicators: Dict[str, Dict]
    ) -> Optional[Dict]:
        """
        Ranging stratejisine göre sinyal üretir.

        Args:
            df: OHLCV DataFrame
            indicators: Teknik gösterge sonuçları (bollinger, rsi vb.)

        Returns:
            Sinyal dict (direction, confidence, score_breakdown, custom targets)
        """
        if df is None or len(df) < 30:
            self.logger.debug(
                "RangingStrategyAnalyzer.generate_signal -> insufficient data: %s",
                len(df) if df is not None else 0,
            )
            return None

        bollinger = indicators.get("bollinger")
        rsi = indicators.get("rsi")

        if not bollinger or not rsi:
            self.logger.debug(
                "RangingStrategyAnalyzer.generate_signal -> missing indicators: "
                "bollinger=%s, rsi=%s",
                bool(bollinger),
                bool(rsi),
            )
            return None

        close_price = df["close"].iloc[-1]
        bb_upper = bollinger.get("upper")
        bb_lower = bollinger.get("lower")
        bb_middle = bollinger.get("middle")

        if None in (bb_upper, bb_lower, bb_middle):
            self.logger.debug(
                "RangingStrategyAnalyzer.generate_signal -> incomplete bollinger data"
            )
            return None

        bb_range = bb_upper - bb_lower
        if bb_range <= 0:
            self.logger.debug(
                "RangingStrategyAnalyzer.generate_signal -> invalid bollinger range: %s",
                bb_range,
            )
            return None

        lower_threshold = bb_lower + bb_range * 0.2
        upper_threshold = bb_upper - bb_range * 0.2

        bb_bias = self._detect_bollinger_bias(
            close_price, lower_threshold, upper_threshold
        )
        rsi_bias, rsi_value = self._detect_rsi_bias(rsi)

        direction, confidence = self._resolve_direction_and_confidence(
            bb_bias, rsi_bias, close_price, bb_lower, bb_upper, rsi_value
        )

        if direction == "NEUTRAL":
            return RangingSignalResult(
                direction="NEUTRAL",
                confidence=confidence,
                score_breakdown=self._build_score_breakdown(
                    bb_bias, rsi_bias, rsi_value, close_price, bb_lower, bb_upper
                ),
                custom_targets={},
            ).to_dict()

        custom_targets = self._build_custom_targets(
            direction, close_price, bb_lower, bb_middle, bb_upper
        )

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

        return RangingSignalResult(
            direction=direction,
            confidence=confidence,
            score_breakdown=score_breakdown,
            custom_targets=custom_targets,
        ).to_dict()

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
        if rsi_bias in ("LONG", "SHORT") and bb_bias == "NEUTRAL":
            confidence = 0.6 + self._rsi_extremity_bonus(rsi_bias, rsi_value)
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

        # Stop-loss: band dışına %10 buffer
        buffer = band_range * 0.1
        safety_gap = max(band_range * 0.05, abs(current_price) * 0.001)

        if direction == "LONG":
            base_stop = bb_lower - buffer
            stop_price = min(base_stop, current_price - safety_gap)
            stop_price = max(stop_price, 0.0)
        else:
            base_stop = bb_upper + buffer
            stop_price = max(base_stop, current_price + safety_gap)

        targets["stop_loss"] = {
            "price": stop_price,
            "label": "Bollinger Band Breach",
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

