"""
SignalGenerator: Tüm göstergeleri birleştirip sinyal üretir.
Multi-timeframe analiz ve güvenilirlik skoru hesaplar.
"""
import pandas as pd
from typing import Dict, List, Optional
from analysis.technical_indicators import TechnicalIndicatorCalculator
from analysis.volume_analyzer import VolumeAnalyzer
from analysis.adaptive_thresholds import AdaptiveThresholdManager
from analysis.ranging_strategy_analyzer import RangingStrategyAnalyzer
from utils.logger import LoggerManager


class SignalGenerator:
    """Teknik göstergeleri birleştirerek sinyal üretir."""
    
    def __init__(self,
                 indicator_calculator: TechnicalIndicatorCalculator,
                 volume_analyzer: VolumeAnalyzer,
                 threshold_manager: AdaptiveThresholdManager,
                 timeframe_weights: Dict[str, float],
                 ranging_analyzer: RangingStrategyAnalyzer):
        """
        SignalGenerator'ı başlatır.
        
        Args:
            indicator_calculator: Teknik gösterge hesaplayıcı
            volume_analyzer: Hacim analizci
            threshold_manager: Eşik yöneticisi
            timeframe_weights: Timeframe ağırlıkları
            ranging_analyzer: Ranging stratejisi analizörü
        """
        self.indicator_calc = indicator_calculator
        self.volume_analyzer = volume_analyzer
        self.threshold_mgr = threshold_manager
        self.tf_weights = timeframe_weights
        self.ranging_analyzer = ranging_analyzer
        self.logger = LoggerManager().get_logger('SignalGenerator')
    
    def generate_signal(
        self, multi_tf_data: Dict[str, pd.DataFrame]
    ) -> Optional[Dict]:
        """
        Multi-timeframe veriden sinyal üretir.
        
        Args:
            multi_tf_data: Timeframe'lere göre DataFrame dict
            
        Returns:
            Sinyal bilgileri dict
        """
        if not multi_tf_data:
            return None
        
        tf_signals = {}
        self.logger.debug(f"generate_signal: tfs={list(multi_tf_data.keys())}")
        
        # Her timeframe için sinyal hesapla
        for tf, df in multi_tf_data.items():
            signal = self._analyze_single_timeframe(df)
            if signal:
                tf_signals[tf] = signal
                self.logger.debug(f"tf={tf} -> direction={signal['direction']}, confidence={signal['confidence']:.3f}")
        
        if not tf_signals:
            return None
        
        # Timeframe'leri birleştir
        combined_signal = self._combine_timeframe_signals(tf_signals)
        self.logger.debug(
            f"combined: direction={combined_signal['direction']}, "
            f"combined_conf_for_direction={combined_signal['combined_conf_for_direction']:.3f}, "
            f"weighted_scores={combined_signal['weighted_scores']}"
        )
        
        return combined_signal
    
    def _analyze_single_timeframe(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Tek timeframe için analiz yapar.
        Veri miktarına göre adaptive analiz uygular.
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            Analiz sonuçları dict
        """
        if df is None or len(df) < 30:  # Minimum 30 mum (50'den düşürüldü)
            self.logger.debug(f"Insufficient data for analysis: {len(df) if df is not None else 0} candles")
            return None
        
        data_length = len(df)
        
        # Veri miktarına göre adaptive parametreler
        adaptive_params = self._get_adaptive_parameters(data_length)
        
        # Teknik göstergeleri hesapla
        indicators = self.indicator_calc.calculate_all(df)
        if not indicators:
            self.logger.debug(f"Technical indicators calculation failed for {data_length} candles")
            return None
        
        regime = self._detect_market_regime(indicators)
        
        # Hacim analizi (adaptive period ile)
        volume = self.volume_analyzer.analyze(df, adaptive_params['volume_ma_period'])
        
        # Volatilite ve trend gücü
        volatility = self.threshold_mgr.calculate_volatility(
            df, indicators['atr']
        )
        trend_strength = self.threshold_mgr.calculate_trend_strength(
            indicators['adx']['value']
        )
        
        if regime == 'ranging':
            ranging_signal = self.ranging_analyzer.generate_signal(df, indicators)
            if not ranging_signal:
                self.logger.debug("Ranging analyzer returned no signal; skipping timeframe")
                return None
            
            direction = ranging_signal.get('direction', 'NEUTRAL')
            confidence = ranging_signal.get('confidence', 0.0)
            score_breakdown = ranging_signal.get('score_breakdown', {})
            custom_targets = ranging_signal.get('custom_targets', {})
            strategy_type = ranging_signal.get('strategy_type', 'ranging')
            
            market_context = self._create_market_context(
                df, indicators, volume, direction, regime
            )
            
            # Signals list - bilgi amaçlı (Bollinger & RSI bias)
            signals = [
                f"BOLL_{score_breakdown.get('bollinger_bias', 'NEUTRAL')}",
                f"RSI_{score_breakdown.get('rsi_bias', 'NEUTRAL')}"
            ]
            
            self.logger.debug(
                f"single_tf (ranging): dir={direction}, conf={confidence:.3f}, "
                f"regime={regime}, data_length={data_length}"
            )
            
            return {
                'direction': direction,
                'confidence': confidence,
                'indicators': indicators,
                'volume': volume,
                'volatility': volatility,
                'trend_strength': trend_strength,
                'signals': signals,
                'data_length': data_length,
                'adaptive_params': adaptive_params,
                'score_breakdown': score_breakdown,
                'market_context': market_context,
                'strategy_type': strategy_type,
                'custom_targets': custom_targets,
                'regime': regime
            }
        
        # Trend modunda klasik pipeline
        signals = self._collect_indicator_signals(indicators, volume)
        direction, confidence = self._determine_direction(signals)
        
        market_context = self._create_market_context(
            df, indicators, volume, direction, regime
        )
        
        adjusted_confidence = self.threshold_mgr.adjust_signal_confidence(
            confidence, trend_strength, volatility,
            direction=direction, indicators=indicators,
            market_context=market_context, volume=volume
        )
        
        self.logger.debug(
            f"single_tf (trend): dir={direction}, conf_raw={confidence:.3f}, conf_adj={adjusted_confidence:.3f}, "
            f"regime={regime}, vol={volatility}, trend={trend_strength}, data_length={data_length}"
        )
        
        score_breakdown = self._create_score_breakdown(
            indicators, volume, confidence, direction
        )
        
        return {
            'direction': direction,
            'confidence': adjusted_confidence,
            'indicators': indicators,
            'volume': volume,
            'volatility': volatility,
            'trend_strength': trend_strength,
            'signals': signals,
            'data_length': data_length,
            'adaptive_params': adaptive_params,
            'score_breakdown': score_breakdown,
            'market_context': market_context,
            'strategy_type': 'trend',
            'custom_targets': {},
            'regime': regime
        }
    
    def _get_adaptive_parameters(self, data_length: int) -> Dict:
        """
        Veri miktarına göre adaptive parametreler döndürür.
        
        Args:
            data_length: Mevcut veri uzunluğu
            
        Returns:
            Adaptive parametreler dict
        """
        return {
            'volume_ma_period': min(20, data_length - 5),
            'min_data_required': max(50, data_length - 10)
        }
    
    def _collect_indicator_signals(
        self, indicators: Dict, volume: Dict
    ) -> List[str]:
        """
        Tüm gösterge sinyallerini toplar.
        
        Args:
            indicators: Teknik göstergeler
            volume: Hacim analizi
            
        Returns:
            Sinyal listesi
        """
        signals = []
        
        signals.append(indicators['rsi']['signal'])
        signals.append(indicators['macd']['signal'])
        signals.append(indicators['ema']['signal'])
        signals.append(indicators['bollinger']['signal'])
        signals.append(indicators['adx']['signal'])
        signals.append(volume['signal'])
        
        return signals
    
    def _determine_direction(
        self, signals: List[str]
    ) -> tuple[str, float]:
        """
        Sinyal listesinden genel yön ve güvenilirlik belirler.
        
        Args:
            signals: Gösterge sinyalleri listesi
            
        Returns:
            (direction, confidence) tuple
        """
        long_count = signals.count('LONG')
        short_count = signals.count('SHORT')
        neutral_count = signals.count('NEUTRAL')
        
        total = len(signals)
        
        if long_count > short_count and long_count > neutral_count:
            direction = 'LONG'
            confidence = long_count / total
        elif short_count > long_count and short_count > neutral_count:
            direction = 'SHORT'
            confidence = short_count / total
        else:
            direction = 'NEUTRAL'
            confidence = max(long_count, short_count, neutral_count) / total
        
        return direction, confidence
    
    def _combine_timeframe_signals(
        self, tf_signals: Dict[str, Dict]
    ) -> Dict:
        """
        Farklı timeframe sinyallerini ağırlıklı birleştirir.
        
        Args:
            tf_signals: Timeframe'lere göre sinyal dict
            
        Returns:
            Birleştirilmiş sinyal
        """
        weighted_scores = {'LONG': 0, 'SHORT': 0, 'NEUTRAL': 0}
        
        ranging_candidates = [
            signal for signal in tf_signals.values()
            if signal.get('strategy_type') == 'ranging'
            and signal.get('confidence', 0) >= 0.7
        ]
        
        if ranging_candidates:
            dominant_signal = max(ranging_candidates, key=lambda s: s.get('confidence', 0))
            return {
                'direction': dominant_signal['direction'],
                'combined_conf_for_direction': dominant_signal['confidence'],
                'confidence': dominant_signal['confidence'],
                'timeframe_signals': tf_signals,
                'weighted_scores': {},
                'score_breakdown': dominant_signal.get('score_breakdown'),
                'market_context': dominant_signal.get('market_context'),
                'strategy_type': 'ranging',
                'custom_targets': dominant_signal.get('custom_targets', {})
            }
        
        for tf, signal in tf_signals.items():
            weight = self.tf_weights.get(tf, 0)
            direction = signal['direction']
            confidence = signal['confidence']
            
            weighted_scores[direction] += weight * confidence
        
        # En yüksek skoru bul
        final_direction = max(
            weighted_scores, key=weighted_scores.get
        )
        final_confidence = weighted_scores[final_direction]
        
        # Score breakdown ve market context: 4h öncelikli, yoksa fallback
        selected_score_breakdown = None
        selected_market_context = None
        selected_strategy_type = None
        selected_custom_targets = None
        preferred_order = ['4h', '1d', '1h']
        
        for tf in preferred_order:
            if tf in tf_signals and tf_signals[tf].get('score_breakdown') and tf_signals[tf]['direction'] == final_direction:
                selected_score_breakdown = tf_signals[tf]['score_breakdown']
                selected_market_context = tf_signals[tf]['market_context']
                selected_strategy_type = tf_signals[tf].get('strategy_type')
                selected_custom_targets = tf_signals[tf].get('custom_targets')
                break
        
        if selected_score_breakdown is None:
            for tf in preferred_order:
                if tf in tf_signals and tf_signals[tf].get('score_breakdown'):
                    selected_score_breakdown = tf_signals[tf]['score_breakdown']
                    selected_market_context = tf_signals[tf]['market_context']
                    selected_strategy_type = tf_signals[tf].get('strategy_type')
                    selected_custom_targets = tf_signals[tf].get('custom_targets')
                    break
        
        return {
            'direction': final_direction,
            # New explicit key for clarity (kept legacy 'confidence' for compatibility)
            'combined_conf_for_direction': final_confidence,
            'confidence': final_confidence,
            'timeframe_signals': tf_signals,
            'weighted_scores': weighted_scores,
            'score_breakdown': selected_score_breakdown,
            'market_context': selected_market_context,
            'strategy_type': selected_strategy_type if selected_strategy_type else 'trend',
            'custom_targets': selected_custom_targets if selected_custom_targets else {}
        }
    
    def _create_score_breakdown(
        self,
        indicators: Dict,
        volume: Dict,
        base_confidence: float,
        direction: str
    ) -> Dict:
        """
        Score breakdown oluşturur.
        
        Args:
            indicators: Teknik göstergeler
            volume: Hacim analizi
            base_confidence: Ham confidence skoru
            direction: Sinyal yönü
            
        Returns:
            Score breakdown dict
        """
        rsi_data = indicators.get('rsi', {})
        macd_data = indicators.get('macd', {})
        ema_data = indicators.get('ema', {})
        bb_data = indicators.get('bollinger', {})
        adx_data = indicators.get('adx', {})
        
        # Bollinger position tespiti
        bb_position = 'middle'
        if bb_data.get('signal') == 'LONG':
            bb_position = 'lower'
        elif bb_data.get('signal') == 'SHORT':
            bb_position = 'upper'
        
        return {
            'base_confidence': base_confidence,
            'rsi_value': rsi_data.get('value', 0),
            'rsi_signal': rsi_data.get('signal', 'NEUTRAL'),
            'macd_histogram': macd_data.get('histogram', 0),
            'macd_signal': macd_data.get('signal', 'NEUTRAL'),
            'ema_alignment': ema_data.get('aligned', False),
            'ema_signal': ema_data.get('signal', 'NEUTRAL'),
            'bollinger_position': bb_position,
            'bollinger_signal': bb_data.get('signal', 'NEUTRAL'),
            'adx_value': adx_data.get('value', 0),
            'adx_signal': adx_data.get('signal', 'NEUTRAL'),
            'volume_relative': volume.get('relative', 1.0),
            'volume_signal': volume.get('signal', 'NEUTRAL')
        }
    
    def _detect_market_regime(self, indicators: Dict) -> str:
        """
        EMA alignment ve ADX değerine göre piyasa rejimini belirler.
        """
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
    
    def _create_market_context(
        self,
        df: pd.DataFrame,
        indicators: Dict,
        volume: Dict,
        direction: str,
        regime: Optional[str] = None
    ) -> Dict:
        """
        Market context oluşturur.
        
        Args:
            df: OHLCV DataFrame
            indicators: Teknik göstergeler
            volume: Hacim analizi
            direction: Sinyal yönü
            regime: Önceden belirlenmiş piyasa rejimi (opsiyonel)
            
        Returns:
            Market context dict
        """
        # ATR direkt float değer döndürür, dict değil
        atr_value = indicators.get('atr', 0)
        if isinstance(atr_value, dict):
            atr_value = atr_value.get('value', 0)
        
        # ADX dict döndürür
        adx_data = indicators.get('adx', {})
        adx_value = adx_data.get('value', 0) if isinstance(adx_data, dict) else 0
        
        ema_data = indicators.get('ema', {})
        
        # Volatility percentile hesapla
        try:
            rolling_std = df['close'].rolling(14).std().dropna()
            if len(rolling_std) > 0:
                volatility_percentile = (rolling_std.rank(pct=True).iloc[-1]) * 100
            else:
                volatility_percentile = 50.0
        except:
            volatility_percentile = 50.0
        
        # Price changes hesapla
        price_changes = {}
        try:
            if len(df) >= 1:
                price_changes['last_1_candle'] = ((df['close'].iloc[-1] / df['close'].iloc[-2]) - 1) * 100 if len(df) >= 2 else 0
            if len(df) >= 4:
                price_changes['last_4_candles'] = ((df['close'].iloc[-1] / df['close'].iloc[-5]) - 1) * 100 if len(df) >= 5 else 0
            if len(df) >= 24:
                price_changes['last_24_candles'] = ((df['close'].iloc[-1] / df['close'].iloc[-25]) - 1) * 100 if len(df) >= 25 else 0
        except:
            price_changes = {'last_1_candle': 0, 'last_4_candles': 0, 'last_24_candles': 0}
        
        # EMA trend
        ema_aligned = ema_data.get('aligned', False)
        ema_signal = ema_data.get('signal', 'NEUTRAL')
        if ema_signal == 'LONG':
            ema_trend = 'up'
        elif ema_signal == 'SHORT':
            ema_trend = 'down'
        else:
            ema_trend = 'flat'
        
        # Regime değerini belirle (override öncelikli)
        computed_regime = 'ranging'
        if ema_aligned and adx_value > 25:
            if ema_trend == 'up':
                computed_regime = 'trending_up'
            elif ema_trend == 'down':
                computed_regime = 'trending_down'
        
        regime_value = regime if regime else computed_regime
        
        return {
            'atr_14': atr_value,
            'volatility_percentile': volatility_percentile,
            'price_change_pct': price_changes,
            'ema_trend': ema_trend,
            'adx_strength': adx_value,
            'regime': regime_value
        }

