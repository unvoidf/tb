"""
Pytest Configuration: Test konfigürasyonu ve fixture'lar.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List


@pytest.fixture
def sample_ohlcv_data():
    """Örnek OHLCV verisi fixture'ı."""
    dates = pd.date_range(start='2024-01-01', periods=200, freq='1H')
    
    # Rastgele fiyat verisi oluştur
    np.random.seed(42)
    base_price = 50000
    prices = []
    current_price = base_price
    
    for _ in range(200):
        # %1-3 arası değişim
        change = np.random.uniform(-0.03, 0.03)
        current_price *= (1 + change)
        prices.append(current_price)
    
    # OHLCV verisi oluştur
    ohlcv_records = []
    for i, (date, price) in enumerate(zip(dates, prices)):
        # High/Low/Close için küçük varyasyonlar
        high = price * (1 + np.random.uniform(0, 0.02))
        low = price * (1 - np.random.uniform(0, 0.02))
        close = price * (1 + np.random.uniform(-0.01, 0.01))
        volume = np.random.uniform(1000, 10000)
        
        ohlcv_records.append({
            'timestamp': date,
            'open': price,
            'high': high,
            'low': low,
            'close': close,
            'volume': volume
        })
    
    df = pd.DataFrame(ohlcv_records)
    df.set_index('timestamp', inplace=True)
    return df


@pytest.fixture
def sample_technical_indicators():
    """Örnek teknik gösterge verisi fixture'ı."""
    return {
        'rsi': {'value': 65.5, 'signal': 'LONG'},
        'macd': {'value': 0.5, 'signal': 'LONG', 'histogram': 0.2},
        'ema': {'short': 50000, 'medium': 49500, 'long': 49000, 'signal': 'LONG'},
        'bollinger': {
            'upper': 52000, 'middle': 50000, 'lower': 48000,
            'signal': 'NEUTRAL'
        },
        'atr': {'value': 500, 'signal': 'NEUTRAL'},
        'adx': {'value': 35, 'signal': 'LONG'}
    }


@pytest.fixture
def sample_volume_analysis():
    """Örnek hacim analizi fixture'ı."""
    return {
        'current_volume': 5000,
        'average_volume': 3000,
        'volume_ratio': 1.67,
        'spike_detected': True,
        'signal': 'LONG'
    }


@pytest.fixture
def sample_signal_data():
    """Örnek sinyal verisi fixture'ı."""
    return {
        'symbol': 'BTC/USDT',
        'direction': 'LONG',
        'confidence': 0.75,
        'timeframe': '1h',
        'indicators': {
            'rsi': 65.5,
            'macd': 0.5,
            'ema_trend': 'LONG',
            'bollinger_position': 'NEUTRAL',
            'adx': 35
        },
        'volume': {
            'spike': True,
            'ratio': 1.67
        },
        'risk_level': 'medium',
        'leverage': 3
    }


@pytest.fixture
def sample_config():
    """Örnek konfigürasyon fixture'ı."""
    return {
        'rsi_period': 14,
        'macd_fast': 12,
        'macd_slow': 26,
        'macd_signal': 9,
        'ema_short': 20,
        'ema_medium': 50,
        'ema_long': 200,
        'bb_period': 20,
        'bb_std': 2,
        'atr_period': 14,
        'adx_period': 14,
        'volume_ma_period': 20,
        'volume_spike_threshold': 1.5,
        'risk_low': 0.01,
        'risk_medium': 0.03,
        'risk_high': 0.05,
        'leverage_min': 1,
        'leverage_max': 10
    }


@pytest.fixture
def mock_telegram_update():
    """Mock Telegram update fixture'ı."""
    class MockUser:
        """Mock Telegram user for testing."""
        def __init__(self):
            self.id = 123456789
            self.username = "testuser"
            self.first_name = "Test"
    
    class MockMessage:
        """Mock Telegram message for testing."""
        def __init__(self):
            self.text = "/test"
            self.message_id = 1
            self.reply_to_message = None
        
        async def reply_text(self, text: str):
            return MockMessage()
    
    class MockUpdate:
        """Mock Telegram update for testing."""
        def __init__(self):
            self.effective_user = MockUser()
            self.message = MockMessage()
    
    return MockUpdate()


@pytest.fixture
def mock_telegram_context():
    """Mock Telegram context fixture'ı."""
    class MockContext:
        """Mock Telegram context for testing."""
        def __init__(self):
            self.args = ['BTC']
    
    return MockContext()
