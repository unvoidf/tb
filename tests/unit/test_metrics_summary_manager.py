"""
MetricsSummaryManager unit tests.
"""
import pytest
import json
from unittest.mock import Mock
from scheduler.components.metrics_summary_manager import MetricsSummaryManager


@pytest.fixture
def mock_repository():
    """Mock SignalRepository."""
    repo = Mock()
    return repo


@pytest.fixture
def manager(mock_repository):
    """MetricsSummaryManager instance."""
    return MetricsSummaryManager(mock_repository)


def test_calculate_metrics_basic(manager):
    """Temel metriklerin doğru hesaplandığını test et."""
    # Arrange
    signals = [
        {
            'signal_id': 'S1',
            'direction': 'LONG',
            'confidence': 0.8,
            'signal_price': 100.0,
            'tp1_hit': 1,
            'tp2_hit': 0,
            'tp3_hit': 0,
            'sl1_hit': 0,
            'sl2_hit': 0,
            'mfe_price': 105.0,
            'mae_price': 99.0,
            'created_at': 1000000,
            'tp1_hit_at': 1001000,
            'market_context': json.dumps({'regime': 'bullish'})
        },
        {
            'signal_id': 'S2',
            'direction': 'SHORT',
            'confidence': 0.7,
            'signal_price': 200.0,
            'tp1_hit': 0,
            'tp2_hit': 0,
            'tp3_hit': 0,
            'sl1_hit': 1,
            'sl2_hit': 0,
            'mfe_price': 198.0,
            'mae_price': 205.0,
            'created_at': 2000000,
            'sl1_hit_at': 2001500,
            'market_context': json.dumps({'regime': 'bearish'})
        }
    ]
    
    # Act
    metrics = manager._calculate_metrics(signals)
    
    # Assert
    assert metrics['total_signals'] == 2
    assert metrics['long_signals'] == 1
    assert metrics['short_signals'] == 1
    assert metrics['avg_confidence'] == 0.75
    assert metrics['tp1_hit_rate'] == 0.5
    assert metrics['sl1_hit_rate'] == 0.5


def test_calculate_metrics_empty_list(manager):
    """Boş sinyal listesi ile test."""
    # Act
    metrics = manager._calculate_metrics([])
    
    # Assert
    assert metrics['total_signals'] == 0
    assert metrics['avg_confidence'] == 0


def test_generate_daily_summary_no_signals(manager, mock_repository):
    """Sinyal yoksa özet oluşturulmaz."""
    # Arrange
    mock_repository.get_signals_by_time_range.return_value = []
    
    # Act
    manager.generate_daily_summary()
    
    # Assert
    mock_repository.save_metrics_summary.assert_not_called()


def test_generate_daily_summary_with_signals(manager, mock_repository):
    """Sinyal varsa özet oluşturulur."""
    # Arrange
    signals = [
        {
            'signal_id': 'S1',
            'direction': 'LONG',
            'confidence': 0.8,
            'signal_price': 100.0,
            'tp1_hit': 1,
            'tp2_hit': 0,
            'tp3_hit': 0,
            'sl1_hit': 0,
            'sl2_hit': 0,
            'mfe_price': None,
            'mae_price': None,
            'created_at': 1000000,
            'market_context': json.dumps({'regime': 'bullish'})
        }
    ]
    mock_repository.get_signals_by_time_range.return_value = signals
    
    # Act
    manager.generate_daily_summary()
    
    # Assert
    mock_repository.save_metrics_summary.assert_called_once()

