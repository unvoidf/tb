"""
Unit tests for MarketDataManager.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from data.market_data_manager import MarketDataManager
from utils.retry_handler import RetryHandler


class TestMarketDataManager:
    """MarketDataManager test sınıfı."""
    
    @pytest.fixture
    def retry_handler(self):
        """Retry handler fixture."""
        return RetryHandler(max_attempts=3, backoff_base=2, initial_delay=0.1)
    
    @pytest.fixture
    def market_data(self, retry_handler):
        """MarketDataManager fixture."""
        with patch('data.market_data_manager.ExchangeFactory') as mock_factory:
            mock_exchange = MagicMock()
            mock_exchange.load_markets.return_value = {
                'BTC/USDT': {},
                'ETH/USDT': {}
            }
            mock_factory.create_binance_futures.return_value = mock_exchange
            
            manager = MarketDataManager(retry_handler)
            return manager
    
    def test_initialization(self, market_data):
        """Başlatma testi."""
        assert market_data is not None
        assert market_data.exchange is not None
        assert market_data.retry_handler is not None
        assert market_data.logger is not None
    
    def test_is_valid_symbol(self, market_data):
        """Sembol validasyonu testi."""
        market_data.valid_symbols = {'BTC/USDT', 'ETH/USDT'}
        
        assert market_data.is_valid_symbol('BTC/USDT') is True
        assert market_data.is_valid_symbol('ETH/USDT') is True
        assert market_data.is_valid_symbol('INVALID/USDT') is False
    
    def test_fetch_ohlcv_invalid_symbol(self, market_data):
        """Geçersiz sembol için OHLCV çekme testi."""
        market_data.valid_symbols = {'BTC/USDT'}
        
        result = market_data.fetch_ohlcv('INVALID/USDT', '1h', 100)
        assert result is None
    
    def test_get_latest_price_invalid_symbol(self, market_data):
        """Geçersiz sembol için fiyat çekme testi."""
        market_data.valid_symbols = {'BTC/USDT'}
        
        result = market_data.get_latest_price('INVALID/USDT')
        assert result is None

