"""
SignalGenerator: Tüm göstergeleri birleştirip sinyal üretir.
Multi-timeframe analiz ve güvenilirlik skoru hesaplar.
"""
import pandas as pd
from typing import Dict, List, Optional, Union, Tuple
from analysis.technical_indicators import TechnicalIndicatorCalculator
from analysis.volume_analyzer import VolumeAnalyzer
from analysis.adaptive_thresholds import AdaptiveThresholdManager
from analysis.ranging_strategy_analyzer import RangingStrategyAnalyzer
from analysis.generators.market_analyzer import MarketAnalyzer
from utils.logger import LoggerManager


class SignalGenerator:
    """Teknik göstergeleri birleştirerek sinyal üretir."""
    
    def __init__(self,
                 indicator_calculator: TechnicalIndicatorCalculator,
                 volume_analyzer: VolumeAnalyzer,
                 threshold_manager: AdaptiveThresholdManager,
                 timeframe_weights: Dict[str, float],
                 ranging_analyzer: RangingStrategyAnalyzer,
                 market_data_manager=None):
        """
        SignalGenerator'ı başlatır.
        
        Args:
            indicator_calculator: Teknik gösterge hesaplayıcı
            volume_analyzer: Hacim analizci
            threshold_manager: Eşik yöneticisi
            timeframe_weights: Timeframe ağırlıkları
            ranging_analyzer: Ranging stratejisi analizörü
            market_data_manager: Market data manager (opsiyonel, BTC correlation için)
        """
        self.indicator_calc = indicator_calculator
        self.volume_analyzer = volume_analyzer
        self.threshold_mgr = threshold_manager
        self.tf_weights = timeframe_weights
        self.ranging_analyzer = ranging_analyzer
        self.market_data = market_data_manager
        self.market_analyzer = MarketAnalyzer(
            market_data_manager, 
            indicator_calculator, 
            volume_analyzer
        )
        self.logger = LoggerManager().get_logger('SignalGenerator')
    
    def generate_signal(
        self, multi_tf_data: Dict[str, pd.DataFrame], symbol: str = None, return_reason: bool = False
    ) -> Union[Optional[Dict], Tuple[Optional[Dict], str]]:
        """
        Multi-timeframe veriden sinyal üretir.
        
        Args:
            multi_tf_data: Timeframe'lere göre DataFrame dict
            symbol: Trading pair (örn: BTC/USDT) - BTC correlation check için
            return_reason: True ise (signal, reason) tuple döndürür
            
        Returns:
            Sinyal bilgileri dict veya None (filtreleme sonucu)
            veya (signal, reason) tuple
        """
        def _ret(sig, reason=None):
            if return_reason:
                return sig, (reason or "NO_SIGNAL")
            return sig

        if not multi_tf_data:
            return _ret(None, "INVALID_DATA")
        
        # 1. BTC Correlation Check (Bitcoin Kraldır Filtresi)
        if symbol and symbol != 'BTC/USDT':
            market_state = self.market_analyzer.check_global_market_condition()
            if market_state == 'BEARISH_CRASH':
                self.logger.warning(
                    f"{symbol} LONG sinyali reddedildi: Global piyasa (BTC) çöküşte. "
                    f"Bitcoin Kraldır filtresi aktif."
                )
                return _ret(None, "FILTER_BTC_CRASH")
            # market_state == 'NEUTRAL' durumunda _check_global_market_condition içinde zaten log basılıyor
        
        tf_signals = {}
        self.logger.debug(f"generate_signal: symbol={symbol}, tfs={list(multi_tf_data.keys())}")
        
        # En son ret nedeni (öncelik sırasına göre)
        last_rejection_reason = "NO_SIGNAL"

        # Her timeframe için sinyal hesapla
        for tf, df in multi_tf_data.items():
            # return_reason=True ile çağır ki nedeni öğrenelim
            signal, reason = self._analyze_single_timeframe(df, tf, multi_tf_data, return_reason=True)
            if signal:
                tf_signals[tf] = signal
                self.logger.debug(f"tf={tf} -> direction={signal['direction']}, confidence={signal['confidence']:.3f}")
            else:
                # Sinyal yoksa nedenini kaydet (R_R önemli)
                if reason != "NO_SIGNAL":
                    last_rejection_reason = reason

        if not tf_signals:
            return _ret(None, last_rejection_reason)
        
        # Timeframe'leri birleştir
        combined_signal = self._combine_timeframe_signals(tf_signals, multi_tf_data)
        
        # 2. Intraday Circuit Breaker (4h EMA kontrolü)
        if combined_signal and combined_signal.get('direction') == 'LONG':
            circuit_breaker_active = self.market_analyzer.check_intraday_circuit_breaker(multi_tf_data)
            if circuit_breaker_active:
                self.logger.warning(
                    f"{symbol} LONG sinyali reddedildi: Intraday circuit breaker aktif. "
                    f"Serbest düşüş tespit edildi."
                )
                return _ret(None, "FILTER_CIRCUIT_BREAKER")
            # circuit_breaker_active == False durumunda _check_intraday_circuit_breaker içinde zaten log basılıyor
        
        # 3. Volume Climax Check (Ranging LONG için)
        if combined_signal and combined_signal.get('strategy_type') == 'ranging':
            if combined_signal.get('direction') == 'LONG':
                volume_climax_ok = self.market_analyzer.check_volume_climax(multi_tf_data)
                if not volume_climax_ok:
                    self.logger.warning(
                        f"{symbol} Ranging LONG sinyali reddedildi: Volume climax yok. "
                        f"Düşük hacimli düşüş - panik satışlar bitmemiş."
                    )
                    return _ret(None, "FILTER_VOLUME_CLIMAX")
                # volume_climax_ok == True durumunda _check_volume_climax içinde zaten log basılıyor
        
        self.logger.debug(
            f"combined: direction={combined_signal['direction']}, "
            f"combined_conf_for_direction={combined_signal['combined_conf_for_direction']:.3f}, "
            f"weighted_scores={combined_signal['weighted_scores']}"
        )
        
        return _ret(combined_signal, "SUCCESS")
    
    def _analyze_single_timeframe(
        self, df: pd.DataFrame, tf: str = None, multi_tf_data: Dict = None, return_reason: bool = False
    ) -> Union[Optional[Dict], Tuple[Optional[Dict], str]]:
        """
        Tek timeframe için analiz yapar.
        Veri miktarına göre adaptive analiz uygular.
        
        Args:
            df: OHLCV DataFrame
            return_reason: True ise (signal, reason) tuple döndürür
            
        Returns:
            Analiz sonuçları dict veya (result, reason)
        """
        def _ret(sig, reason=None):
            if return_reason:
                return sig, (reason or "NO_SIGNAL")
            return sig

        # REPAINTING FIX: Sinyal üretimi için SADECE kapanmış mumları kullan.
        # Son mum (iloc[-1]) henüz kapanmadığı için sürekli değişir (repainting).
        # Bu yüzden son mumu analizden hariç tutuyoruz.
        closed_df = df.iloc[:-1]
        
        if closed_df is None or len(closed_df) < 30:  # Minimum 30 mum (50'den düşürüldü)
            self.logger.debug(f"Insufficient data for analysis: {len(closed_df) if closed_df is not None else 0} candles")
            return _ret(None, "INSUFFICIENT_DATA")
        
        data_length = len(closed_df)
        
        # Veri miktarına göre adaptive parametreler
        adaptive_params = self._get_adaptive_parameters(data_length)
        
        # Teknik göstergeleri hesapla (Kapanmış mumlar üzerinden)
        indicators = self.indicator_calc.calculate_all(closed_df)
        if not indicators:
            self.logger.debug(f"Technical indicators calculation failed for {data_length} candles")
            return _ret(None, "INDICATOR_ERROR")
        
        regime = self.market_analyzer.detect_market_regime(indicators)
        
        # Hacim analizi (adaptive period ile)
        volume = self.volume_analyzer.analyze(closed_df, adaptive_params['volume_ma_period'])
        
        # Volatilite ve trend gücü
        volatility = self.threshold_mgr.calculate_volatility(
            closed_df, indicators['atr']
        )
        trend_strength = self.threshold_mgr.calculate_trend_strength(
            indicators['adx']['value']
        )
        
        if regime == 'ranging':
            # Ranging analyzer'a return_reason=True gönder
            # closed_df gönderildiği için ranging analizi de kapanmış mumlara göre yapılacak
            ranging_signal, reason = self.ranging_analyzer.generate_signal(closed_df, indicators, return_reason=True)
            
            if not ranging_signal:
                self.logger.debug(f"Ranging analyzer returned no signal ({reason}); skipping timeframe")
                return _ret(None, reason)
            
            direction = ranging_signal.get('direction', 'NEUTRAL')
            confidence = ranging_signal.get('confidence', 0.0)
            score_breakdown = ranging_signal.get('score_breakdown', {})
            custom_targets = ranging_signal.get('custom_targets', {})
            strategy_type = ranging_signal.get('strategy_type', 'ranging')
            
            market_context = self._create_market_context(
                closed_df, indicators, volume, direction, regime
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
            
            return _ret({
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
            }, "SUCCESS")
        
        # Trend modunda klasik pipeline
        signals = self._collect_indicator_signals(indicators, volume)
        direction, confidence = self._determine_direction(signals, indicators)
        
        market_context = self._create_market_context(
            closed_df, indicators, volume, direction, regime
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
        
        return _ret({
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
        }, "SUCCESS")
    
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
        self, signals: List[str], indicators: Dict = None
    ) -> tuple[str, float]:
        """
        Sinyal listesinden genel yön ve güvenilirlik belirler.
        
        EXTREME CONSENSUS PENALTY: 100% agreement often indicates trend exhaustion
        SWEET SPOT BONUS: 67-85% agreement is optimal (4-5 out of 6 indicators)
        
        Args:
            signals: Gösterge sinyalleri listesi
            indicators: Teknik göstergeler (RSI kontrolü için)
            
        Returns:
            (direction, confidence) tuple
        """
        long_count = signals.count('LONG')
        short_count = signals.count('SHORT')
        neutral_count = signals.count('NEUTRAL')
        
        total = len(signals)
        
        if long_count > short_count and long_count > neutral_count:
            direction = 'LONG'
            raw_confidence = long_count / total
        elif short_count > long_count and short_count > neutral_count:
            direction = 'SHORT'
            raw_confidence = short_count / total
        else:
            direction = 'NEUTRAL'
            raw_confidence = max(long_count, short_count, neutral_count) / total
            return direction, raw_confidence
        
        # EXTREME CONSENSUS PENALTY (Data: 0.90-0.95 range = 11% win rate)
        if raw_confidence >= 0.95:  # 6/6 or very high consensus
            if indicators:
                rsi_data = indicators.get('rsi', {})
                rsi_value = rsi_data.get('value', 50)
                
                # Check for overbought/oversold extremes (trend exhaustion)
                if direction == 'LONG' and rsi_value > 75:
                    raw_confidence *= 0.50  # 50% penalty
                    self.logger.warning(
                        f"EXTREME CONSENSUS PENALTY: {direction} with RSI={rsi_value:.1f} "
                        f"(likely trend exhaustion). Confidence {raw_confidence/0.50:.3f} -> {raw_confidence:.3f}"
                    )
                elif direction == 'SHORT' and rsi_value < 25:
                    raw_confidence *= 0.50  # 50% penalty
                    self.logger.warning(
                        f"EXTREME CONSENSUS PENALTY: {direction} with RSI={rsi_value:.1f} "
                        f"(likely trend exhaustion). Confidence {raw_confidence/0.50:.3f} -> {raw_confidence:.3f}"
                    )
        
        # SWEET SPOT BONUS (Data: 0.75-0.80 range = 51% win rate)
        elif 0.67 <= raw_confidence <= 0.85:  # 4-5 out of 6 indicators
            raw_confidence *= 1.10  # 10% bonus to sweet spot
            self.logger.debug(
                f"Sweet spot bonus: {raw_confidence/1.10:.3f} -> {raw_confidence:.3f}"
            )
        
        return direction, raw_confidence
    
    def _combine_timeframe_signals(
        self, tf_signals: Dict[str, Dict], multi_tf_data: Dict = None
    ) -> Dict:
        """
        Farklı timeframe sinyallerini ağırlıklı birleştirir.
        Güven skoru hassasiyeti (Boost) uygular.
        """
        weighted_scores = {'LONG': 0, 'SHORT': 0, 'NEUTRAL': 0}
        
        # Önce günlük trendi kontrol et (Veto mekanizması)
        daily_trend_signal = tf_signals.get('1d', {})
        daily_trend = daily_trend_signal.get('direction', 'NEUTRAL')
        daily_trend_strength = daily_trend_signal.get('trend_strength', {})
        daily_adx = daily_trend_strength.get('value', 0) if isinstance(daily_trend_strength, dict) else 0
        
        # Güçlü Trend Tanımı: ADX > 25 (Endüstri standardı)
        is_strong_trend = daily_adx > 25
        
        # Ranging adaylarını filtrele (Trend Dictatorship)
        ranging_candidates = []
        for signal in tf_signals.values():
            if signal.get('strategy_type') == 'ranging' and signal.get('confidence', 0) >= 0.7:
                signal_direction = signal.get('direction', 'NEUTRAL')
                
                # Trend Veto: Güçlü trend varsa tersine işlem açma
                if is_strong_trend:
                    if (daily_trend == 'SHORT' and signal_direction == 'LONG') or \
                       (daily_trend == 'LONG' and signal_direction == 'SHORT'):
                        self.logger.warning(
                            f"Ranging sinyali reddedildi: Güçlü trend "
                            f"(ADX={daily_adx:.1f} > 25). Trend Dictatorship aktif."
                        )
                        continue
                
                # Confidence Cap: Trend tersi işlem max %70 güven alır
                raw_conf = signal.get('confidence', 0)
                capped_conf = min(raw_conf, 0.70)
                if capped_conf < raw_conf:
                     signal['confidence'] = capped_conf
                
                ranging_candidates.append(signal)
        
        # Eğer ranging sinyali varsa ve trend vetosuna takılmadıysa onu seç
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
        
        # Trend Sinyali Hesaplama
        for tf, signal in tf_signals.items():
            weight = self.tf_weights.get(tf, 0)
            direction = signal['direction']
            confidence = signal['confidence']
            
            weighted_scores[direction] += weight * confidence
        
        final_direction = max(weighted_scores, key=weighted_scores.get)
        final_confidence = weighted_scores[final_direction]
        
        # Confidence Adjustment (REVERSED LOGIC based on data analysis)
        # Data shows: 0.75-0.80 = 51% WR, 0.90-0.95 = 11% WR
        # High confidence often indicates trend exhaustion (all indicators overbought)
        if final_direction == daily_trend and is_strong_trend:
            # Günlük trend ile aynı yöndeyiz ve trend güçlü
            
            # HIGH CONFIDENCE = TREND EXHAUSTION RISK
            if final_confidence >= 0.85:
                boost = -0.10  # PENALTY instead of bonus
                self.logger.warning(
                    f"High confidence penalty applied: {final_confidence:.3f} -> "
                    f"{final_confidence + boost:.3f} (trend exhaustion risk, ADX={daily_adx:.1f})"
                )
            # SWEET SPOT (0.70-0.80) = OPTIMAL RANGE
            elif 0.70 <= final_confidence <= 0.80:
                boost = 0.05  # Small bonus to sweet spot
                self.logger.info(
                    f"Sweet spot bonus applied: {final_confidence:.3f} -> "
                    f"{final_confidence + boost:.3f}"
                )
            else:
                boost = 0.0
                
            # Cap at 0.85 (data-driven maximum)
            final_confidence = max(0.60, min(final_confidence + boost, 0.85))
            
        else:
            # Trend zayıfsa veya yön belirsizse, confidence %75'i geçemez
            final_confidence = min(final_confidence, 0.75)

        # ... (Geri kalan kod aynı) ...
        
        # Score breakdown ve market context: 4h öncelikli
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
            # Fallback
            for tf in preferred_order:
                if tf in tf_signals and tf_signals[tf].get('score_breakdown'):
                    selected_score_breakdown = tf_signals[tf]['score_breakdown']
                    selected_market_context = tf_signals[tf]['market_context']
                    selected_strategy_type = tf_signals[tf].get('strategy_type')
                    selected_custom_targets = tf_signals[tf].get('custom_targets')
                    break
        
        return {
            'direction': final_direction,
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

