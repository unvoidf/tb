"""
Signal Generation Integration Tests: Sinyal üretimi entegrasyon testleri.
"""
import pytest
import pandas as pd
from analysis.technical_indicators import TechnicalIndicatorCalculator
from analysis.volume_analyzer import VolumeAnalyzer
from analysis.adaptive_thresholds import AdaptiveThresholdManager
from analysis.signal_generator import SignalGenerator
from analysis.ranging_strategy_analyzer import RangingStrategyAnalyzer
from scheduler.components.signal_ranker import SignalRanker


class TestSignalGeneration:
    """Sinyal üretimi entegrasyon testleri."""
    
    def test_signal_generation_flow(self, sample_ohlcv_data, sample_config):
        """Sinyal üretim akışı testi."""
        # Bileşenleri oluştur
        indicator_calc = TechnicalIndicatorCalculator(
            rsi_period=sample_config['rsi_period'],
            macd_fast=sample_config['macd_fast'],
            macd_slow=sample_config['macd_slow'],
            macd_signal=sample_config['macd_signal'],
            ema_short=sample_config['ema_short'],
            ema_medium=sample_config['ema_medium'],
            ema_long=sample_config['ema_long'],
            bb_period=sample_config['bb_period'],
            bb_std=sample_config['bb_std'],
            atr_period=sample_config['atr_period'],
            adx_period=sample_config['adx_period']
        )
        
        volume_analyzer = VolumeAnalyzer(
            volume_ma_period=sample_config['volume_ma_period'],
            spike_threshold=sample_config['volume_spike_threshold']
        )
        
        threshold_manager = AdaptiveThresholdManager(
            adx_weak_threshold=20,
            adx_strong_threshold=40
        )
        
        ranging_analyzer = RangingStrategyAnalyzer()
        
        signal_generator = SignalGenerator(
            indicator_calculator=indicator_calc,
            volume_analyzer=volume_analyzer,
            threshold_manager=threshold_manager,
            timeframe_weights={'1h': 0.40, '4h': 0.35, '1d': 0.25},
            ranging_analyzer=ranging_analyzer
        )
        
        # Multi-timeframe veri hazırla
        multi_tf_data = {
            '1h': sample_ohlcv_data,
            '4h': sample_ohlcv_data.resample('4H').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna(),
            '1d': sample_ohlcv_data.resample('1D').agg({
                'open': 'first',
                'high': 'max',
                'low': 'min',
                'close': 'last',
                'volume': 'sum'
            }).dropna()
        }
        
        # Sinyal üret
        signal = signal_generator.generate_signal(multi_tf_data)
        
        # Sonuçları kontrol et
        assert signal is not None
        assert 'direction' in signal
        assert 'confidence' in signal
        assert 'timeframe_signals' in signal
        assert signal['direction'] in ['LONG', 'SHORT', 'NEUTRAL']
        assert 0 <= signal['confidence'] <= 1
    
    def test_signal_ranking(self, sample_signal_data):
        """Sinyal sıralama testi."""
        ranker = SignalRanker()
        
        # Test sinyalleri oluştur (SignalRanker beklenen format)
        all_signals = [
            {'symbol': 'BTC/USDT', 'signal': {'direction': 'LONG', 'confidence': 0.8}},
            {'symbol': 'ETH/USDT', 'signal': {'direction': 'SHORT', 'confidence': 0.6}},
            {'symbol': 'ADA/USDT', 'signal': {'direction': 'NEUTRAL', 'confidence': 0.4}},
            {'symbol': 'SOL/USDT', 'signal': {'direction': 'LONG', 'confidence': 0.9}},
        ]
        
        # Sinyalleri sırala (top_count büyük vererek tümünü değerlendirelim)
        ranked = ranker.rank_signals(all_signals, top_count=10)
        
        # Kontroller
        assert len(ranked) >= 1
        # İlk iki elemanın skor sıralaması descending olmalı
        if len(ranked) >= 2:
            assert ranked[0]['_ranking_info']['total_score'] >= ranked[1]['_ranking_info']['total_score']
        # NEUTRAL olanlar genelde alt sıralarda kalmalı (confidence ve bonuslara bağlı)
        assert any(item['signal']['direction'] != 'NEUTRAL' for item in ranked[:1])
    
    def test_ranging_strategy_detection(self, sample_ohlcv_data, sample_config):
        """Ranging stratejisinin tespit edildiğini test eder."""
        indicator_calc = TechnicalIndicatorCalculator(
            rsi_period=sample_config['rsi_period'],
            macd_fast=sample_config['macd_fast'],
            macd_slow=sample_config['macd_slow'],
            macd_signal=sample_config['macd_signal'],
            ema_short=sample_config['ema_short'],
            ema_medium=sample_config['ema_medium'],
            ema_long=sample_config['ema_long'],
            bb_period=sample_config['bb_period'],
            bb_std=sample_config['bb_std'],
            atr_period=sample_config['atr_period'],
            adx_period=sample_config['adx_period']
        )
        
        volume_analyzer = VolumeAnalyzer(
            volume_ma_period=sample_config['volume_ma_period'],
            spike_threshold=sample_config['volume_spike_threshold']
        )
        
        threshold_manager = AdaptiveThresholdManager(
            adx_weak_threshold=20,
            adx_strong_threshold=40
        )
        
        ranging_analyzer = RangingStrategyAnalyzer()
        
        signal_generator = SignalGenerator(
            indicator_calculator=indicator_calc,
            volume_analyzer=volume_analyzer,
            threshold_manager=threshold_manager,
            timeframe_weights={'1h': 0.40, '4h': 0.35, '1d': 0.25},
            ranging_analyzer=ranging_analyzer
        )
        
        # Ranging piyasa simülasyonu: Düşük ADX, EMA alignment yok
        # Bunu test etmek için gerçek veri yerine manuel kontrol yapabiliriz
        indicators = indicator_calc.calculate_all(sample_ohlcv_data)
        regime = signal_generator._detect_market_regime(indicators)
        
        # Regime tespit edilmeli
        assert regime in ['trending_up', 'trending_down', 'ranging']
        
        # Eğer ranging ise, signal'da strategy_type olmalı
        if regime == 'ranging':
            multi_tf_data = {'1h': sample_ohlcv_data}
            signal = signal_generator.generate_signal(multi_tf_data)
            if signal and signal.get('direction') != 'NEUTRAL':
                # Ranging stratejisi kullanıldıysa custom_targets olmalı
                tf_signal = signal.get('timeframe_signals', {}).get('1h', {})
                if tf_signal.get('strategy_type') == 'ranging':
                    assert 'custom_targets' in tf_signal or 'custom_targets' in signal
    
    def test_custom_targets_in_position_calculator(self, sample_ohlcv_data):
        """PositionCalculator'ın custom targets'ı doğru kullandığını test eder."""
        from strategy.position_calculator import PositionCalculator
        from analysis.fibonacci_calculator import FibonacciCalculator
        
        fib_calc = FibonacciCalculator()
        position_calc = PositionCalculator(fib_calc)
        
        # Ranging stratejisi sinyali simüle et
        signal_with_custom_targets = {
            'direction': 'LONG',
            'strategy_type': 'ranging',
            'custom_targets': {
                'tp1': {'price': 50000.0, 'label': 'Middle Band'},
                'tp2': {'price': 51000.0, 'label': 'Upper Band'},
                'stop_loss': {'price': 48000.0, 'label': 'Stop-Loss'}
            }
        }
        
        # Position hesapla
        position = position_calc.calculate_position(
            sample_ohlcv_data,
            signal_with_custom_targets,
            atr=1000.0
        )
        
        # Custom targets kullanıldıysa, targets'lar custom_targets'tan gelmeli
        if position:
            assert 'targets' in position
            # Ranging stratejisinde custom targets kullanılmalı
            assert len(position['targets']) > 0
            # TP1 ve TP2 custom_targets'tan gelmeli
            assert position['targets'][0]['price'] == 50000.0 or position['targets'][0]['price'] == 51000.0

    def test_dominant_ranging_shortcut(self):
        """Dominant ranging sinyallerinin ortalama yerine direkt seçildiğini doğrular."""
        indicator_calc = TechnicalIndicatorCalculator()
        volume_analyzer = VolumeAnalyzer(volume_ma_period=20, spike_threshold=2.0)
        threshold_manager = AdaptiveThresholdManager()
        ranging_analyzer = RangingStrategyAnalyzer()

        signal_generator = SignalGenerator(
            indicator_calculator=indicator_calc,
            volume_analyzer=volume_analyzer,
            threshold_manager=threshold_manager,
            timeframe_weights={'1h': 0.4, '4h': 0.35, '1d': 0.25},
            ranging_analyzer=ranging_analyzer
        )

        tf_signals = {
            '1h': {
                'direction': 'SHORT',
                'confidence': 0.75,
                'strategy_type': 'ranging',
                'score_breakdown': {'source': '1h'},
                'market_context': {'regime': 'ranging'},
                'custom_targets': {'tp1': {'price': 100}}
            },
            '4h': {
                'direction': 'NEUTRAL',
                'confidence': 0.1,
                'strategy_type': 'trend',
                'score_breakdown': {'source': '4h'},
                'market_context': {'regime': 'trending'},
                'custom_targets': {}
            },
            '1d': {
                'direction': 'NEUTRAL',
                'confidence': 0.1,
                'strategy_type': 'trend',
                'score_breakdown': {'source': '1d'},
                'market_context': {'regime': 'trending'},
                'custom_targets': {}
            }
        }

        combined = signal_generator._combine_timeframe_signals(tf_signals)

        assert combined['strategy_type'] == 'ranging'
        assert combined['confidence'] == pytest.approx(0.75)
        assert combined['score_breakdown'] == tf_signals['1h']['score_breakdown']
        assert combined['market_context'] == tf_signals['1h']['market_context']
        assert combined['custom_targets'] == tf_signals['1h']['custom_targets']
