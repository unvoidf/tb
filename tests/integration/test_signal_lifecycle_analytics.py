"""
Signal Lifecycle Analytics Integration Test.
Sinyal yaşam döngüsünün tüm adımlarını test eder.
"""
import pytest
import tempfile
import os
import json
import time
from data.signal_database import SignalDatabase
from data.signal_repository import SignalRepository
from scheduler.components.metrics_summary_manager import MetricsSummaryManager


@pytest.fixture
def temp_db():
    """Geçici test database."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db = SignalDatabase(db_path=path)
    yield db, path
    try:
        os.unlink(path)
    except:
        pass


@pytest.fixture
def repository(temp_db):
    """SignalRepository instance."""
    db, _ = temp_db
    return SignalRepository(db)


@pytest.fixture
def metrics_manager(repository):
    """MetricsSummaryManager instance."""
    return MetricsSummaryManager(repository)


def test_complete_signal_lifecycle(repository):
    """
    Bir sinyalin tüm yaşam döngüsünü test eder:
    1. Sinyal kaydedilir (score_breakdown, market_context ile)
    2. Snapshot kaydedilir
    3. MFE/MAE güncellenir
    4. Alternative entry hit olur
    5. Sinyal finalize edilir
    """
    # 1. Sinyal kaydet
    signal_data = {
        'signal_id': 'LIFECYCLE_TEST_001',
        'symbol': 'BTCUSDT',
        'direction': 'LONG',
        'signal_price': 50000.0,
        'confidence': 0.85,
        'tp1_price': 51000.0,
        'tp2_price': 52000.0,
        'sl_price': 49000.0,
        'optimal_entry_price': 49800.0,
        'conservative_entry_price': 49700.0,
        'score_breakdown': json.dumps({
            'trend': 0.9,
            'momentum': 0.8,
            'volume': 0.85,
            'support_resistance': 0.8
        }),
        'market_context': json.dumps({
            'regime': 'bullish',
            'volatility': 'medium',
            'trend': 'uptrend',
            'volume_24h': 1500000000
        }),
        'tp1_r': 2.0,
        'tp2_r': 4.0,
        'sl_r': -2.0
    }
    repository.save_signal(signal_data)
    
    # Verify signal saved
    signal = repository.get_signal_by_id('LIFECYCLE_TEST_001')
    assert signal is not None
    assert signal['confidence'] == 0.85
    assert signal['is_active'] == 1
    
    # 2. Snapshot kaydet (3 tane)
    timestamps = [1000000, 1000060, 1000120]
    prices = [50100.0, 50200.0, 50300.0]
    for ts, price in zip(timestamps, prices):
        repository.save_price_snapshot('LIFECYCLE_TEST_001', ts, price, 'tracker_tick')
    
    # Verify snapshots
    snapshots = repository.get_price_snapshots('LIFECYCLE_TEST_001')
    assert len(snapshots) == 3
    assert snapshots[0]['price'] == 50100.0
    
    # 3. MFE/MAE güncelle
    repository.update_mfe_mae(
        signal_id='LIFECYCLE_TEST_001',
        mfe_price=50500.0,  # Favor
        mfe_at=1000150,
        mae_price=49900.0,  # Adverse
        mae_at=1000180
    )
    
    # Verify MFE/MAE
    signal = repository.get_signal_by_id('LIFECYCLE_TEST_001')
    assert signal['mfe_price'] == 50500.0
    assert signal['mae_price'] == 49900.0
    
    # 4. Alternative entry hit
    repository.update_alternative_entry_hit('LIFECYCLE_TEST_001', 'optimal', 1000200)
    repository.update_alternative_entry_hit('LIFECYCLE_TEST_001', 'conservative', 1000220)
    
    # Verify alt entries
    signal = repository.get_signal_by_id('LIFECYCLE_TEST_001')
    assert signal['optimal_entry_hit'] == 1
    assert signal['conservative_entry_hit'] == 1
    
    # 5. Finalize signal
    repository.finalize_signal('LIFECYCLE_TEST_001', 51500.0, 'tp1_reached')
    
    # Verify finalization
    signal = repository.get_signal_by_id('LIFECYCLE_TEST_001')
    assert signal['is_active'] == 0
    assert signal['final_outcome'] == 'tp1_reached'
    assert signal['final_price'] == 51500.0


def test_rejected_signal_tracking(repository):
    """Reddedilen sinyal kaydını test eder."""
    # Arrange
    rejected = {
        'signal_id': 'REJECTED_001',
        'symbol': 'ETHUSDT',
        'direction': 'SHORT',
        'confidence': 0.55,
        'rejected_reason': 'confidence_too_low',
        'score_breakdown': json.dumps({'momentum': 0.5}),
        'market_context': json.dumps({'regime': 'neutral'})
    }
    
    # Act
    repository.save_rejected_signal(rejected)
    
    # Assert
    conn = repository.database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM rejected_signals WHERE signal_id = ?", ('REJECTED_001',))
    result = cursor.fetchone()
    assert result is not None
    assert result['rejected_reason'] == 'confidence_too_low'


def test_metrics_summary_generation(repository, metrics_manager):
    """Metrics summary oluşturulmasını test eder."""
    # Arrange: Birkaç sinyal kaydet
    base_time = int(time.time()) - 12 * 3600  # 12 saat önce
    
    for i in range(5):
        signal_data = {
            'signal_id': f'METRIC_TEST_{i}',
            'symbol': f'COIN{i}USDT',
            'direction': 'LONG' if i % 2 == 0 else 'SHORT',
            'signal_price': 100.0 + i * 10,
            'confidence': 0.7 + i * 0.05,
            'tp1_hit': 1 if i < 3 else 0,
            'tp2_hit': 1 if i < 2 else 0,
            'sl_hit': 1 if i >= 3 else 0,
            'mfe_price': (100.0 + i * 10) * 1.02,
            'mae_price': (100.0 + i * 10) * 0.99,
            'created_at': base_time,
            'score_breakdown': json.dumps({'trend': 0.8}),
            'market_context': json.dumps({'regime': 'bullish'})
        }
        repository.save_signal(signal_data)
    
    # Act
    metrics_manager.generate_daily_summary()
    
    # Assert
    conn = repository.database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM signal_metrics_summary ORDER BY period_start DESC LIMIT 1")
    result = cursor.fetchone()
    assert result is not None
    
    metrics = json.loads(result['metrics_json'])
    assert metrics['total_signals'] == 5
    assert metrics['long_signals'] == 3
    assert metrics['short_signals'] == 2


def test_signal_with_all_analytics_fields(repository):
    """Tüm analytics alanlarıyla bir sinyalin kaydedilip okunmasını test eder."""
    # Arrange
    complete_signal = {
        'signal_id': 'COMPLETE_001',
        'symbol': 'BNBUSDT',
        'direction': 'LONG',
        'signal_price': 300.0,
        'confidence': 0.88,
        'tp1_price': 310.0,
        'tp2_price': 320.0,
        'sl_price': 290.0,
        'optimal_entry_price': 298.0,
        'conservative_entry_price': 296.0,
        'score_breakdown': json.dumps({
            'trend': 0.9,
            'momentum': 0.88,
            'volume': 0.87,
            'support_resistance': 0.85,
            'rsi': 0.82,
            'macd': 0.86
        }),
        'market_context': json.dumps({
            'regime': 'bullish',
            'volatility': 'low',
            'trend': 'strong_uptrend',
            'volume_24h': 2000000000,
            'btc_correlation': 0.75
        }),
        'tp1_r': 2.0,
        'tp2_r': 4.0,
        'sl_r': -2.0
    }
    
    # Act
    repository.save_signal(complete_signal)
    
    # Assert
    signal = repository.get_signal_by_id('COMPLETE_001')
    assert signal is not None
    
    # Check score_breakdown
    score_bd = json.loads(signal['score_breakdown'])
    assert score_bd['trend'] == 0.9
    assert score_bd['momentum'] == 0.88
    
    # Check market_context
    market_ctx = json.loads(signal['market_context'])
    assert market_ctx['regime'] == 'bullish'
    assert market_ctx['volume_24h'] == 2000000000
    
    # Check R distances
    assert signal['tp1_r'] == 2.0
    assert signal['tp2_r'] == 4.0

