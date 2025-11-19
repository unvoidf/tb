"""
Integration tests for signal generation pipeline.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from analysis.signal_generator import SignalGenerator
from analysis.technical_indicators import TechnicalIndicatorCalculator
from analysis.volume_analyzer import VolumeAnalyzer
from analysis.adaptive_thresholds import AdaptiveThresholdManager


class TestSignalPipeline:
    """Signal generation pipeline integration tests."""
    
    @pytest.fixture
    def signal_components(self):
        """Signal generation bileşenleri fixture."""
        indicator_calc = TechnicalIndicatorCalculator()
        volume_analyzer = VolumeAnalyzer()
        threshold_manager = AdaptiveThresholdManager()
        
        return {
            'indicator_calc': indicator_calc,
            'volume_analyzer': volume_analyzer,
            'threshold_manager': threshold_manager
        }
    
    def test_signal_generator_initialization(self, signal_components):
        """SignalGenerator başlatma testi."""
        from analysis.ranging_strategy_analyzer import RangingStrategyAnalyzer
        
        ranging_analyzer = RangingStrategyAnalyzer()
        timeframe_weights = {'1h': 0.40, '4h': 0.35, '1d': 0.25}
        
        signal_gen = SignalGenerator(
            indicator_calculator=signal_components['indicator_calc'],
            volume_analyzer=signal_components['volume_analyzer'],
            threshold_manager=signal_components['threshold_manager'],
            timeframe_weights=timeframe_weights,
            ranging_analyzer=ranging_analyzer
        )
        
        assert signal_gen is not None
        assert signal_gen.indicator_calc is not None
        assert signal_gen.volume_analyzer is not None
        assert signal_gen.threshold_mgr is not None
    
    def test_signal_generation_with_empty_data(self, signal_components):
        """Boş veri ile sinyal üretme testi."""
        from analysis.ranging_strategy_analyzer import RangingStrategyAnalyzer
        
        ranging_analyzer = RangingStrategyAnalyzer()
        timeframe_weights = {'1h': 0.40, '4h': 0.35, '1d': 0.25}
        
        signal_gen = SignalGenerator(
            indicator_calculator=signal_components['indicator_calc'],
            volume_analyzer=signal_components['volume_analyzer'],
            threshold_manager=signal_components['threshold_manager'],
            timeframe_weights=timeframe_weights,
            ranging_analyzer=ranging_analyzer
        )
        
        # Boş veri
        result = signal_gen.generate_signal({})
        
        assert result is None

