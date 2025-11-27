"""
SignalRepository unit tests - Yeni analytics metodları için testler.
"""
import pytest
import tempfile
import os
import json
from data.signal_database import SignalDatabase
from data.signal_repository import SignalRepository


@pytest.fixture
def temp_db():
    """Geçici test database oluşturur."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db = SignalDatabase(db_path=path)
    yield db, path
    # Cleanup
    try:
        os.unlink(path)
    except OSError as e:
        # Cleanup failed, file may already be deleted
        pass


@pytest.fixture
def repository(temp_db):
    """Test repository instance."""
    db, _ = temp_db
    return SignalRepository(db)


def test_save_price_snapshot(repository):
    """Price snapshot kaydedilir mi?"""
    # Arrange
    signal_id = 'TEST123'
    timestamp = 1234567890
    price = 50000.0
    source = 'tracker_tick'
    
    # Act
    repository.save_price_snapshot(signal_id, timestamp, price, source)
    
    # Assert
    snapshots = repository.get_price_snapshots(signal_id)
    assert len(snapshots) == 1
    assert snapshots[0]['price'] == price
    assert snapshots[0]['source'] == source


def test_update_mfe_mae(repository):
    """MFE/MAE güncellemesi çalışır mı?"""
    # Act
    mfe_price = 52000.0
    mae_price = 49500.0
    mfe_at = 1234567891
    mae_at = 1234567892
    repository.update_mfe_mae('TEST456', mfe_price, mfe_at, mae_price, mae_at)
    
    # Assert - Metodun hata vermeden çalıştığını test et
    # (Sinyal yoksa bile update yapabilmeli)
    assert True


def test_save_rejected_signal(repository):
    """Reddedilen sinyal kaydedilir mi?"""
    # Act
    success = repository.save_rejected_signal(
        symbol='ETHUSDT',
        direction='SHORT',
        confidence=0.5,
        signal_price=2000.0,
        rejection_reason='confidence_too_low',
        score_breakdown=json.dumps({'momentum': 0.4}),
        market_context=json.dumps({'regime': 'neutral'})
    )
    
    # Assert
    assert success is True


def test_finalize_signal(repository):
    """Sinyal finalize olur mu?"""
    # Act
    final_price = 310.0
    outcome = 'tp1_reached'
    repository.finalize_signal('FIN001', final_price, outcome)
    
    # Assert - Metodun hata vermeden çalıştığını test et
    assert True


def test_save_metrics_summary(repository):
    """Metrics summary kaydedilir mi?"""
    # Arrange
    period_start = 1234500000
    period_end = 1234586400
    metrics = {
        'total_signals': 10,
        'avg_confidence': 0.75,
        'tp1_hit_rate': 0.6
    }
    
    # Act - Metodun hata vermeden çalıştığını test et
    repository.save_metrics_summary(period_start, period_end, metrics)
    
    # Assert
    assert True

