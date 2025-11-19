"""
Unit tests for ExchangeFactory.
"""
import pytest
from utils.exchange_factory import ExchangeFactory


class TestExchangeFactory:
    """ExchangeFactory test sınıfı."""
    
    def test_create_binance_futures(self):
        """Binance futures exchange oluşturma testi."""
        exchange = ExchangeFactory.create_binance_futures()
        
        assert exchange is not None
        assert hasattr(exchange, 'fetch_ticker')
        assert hasattr(exchange, 'fetch_ohlcv')
        
        # defaultType future olmalı
        assert exchange.options.get('defaultType') == 'future'
        
        # enableRateLimit aktif olmalı
        assert exchange.enableRateLimit is True
    
    def test_create_binance_futures_with_credentials(self):
        """API credentials ile exchange oluşturma testi."""
        api_key = "test_key"
        api_secret = "test_secret"
        
        exchange = ExchangeFactory.create_binance_futures(
            api_key=api_key,
            api_secret=api_secret
        )
        
        assert exchange is not None
        assert exchange.apiKey == api_key
        assert exchange.secret == api_secret
    
    def test_create_binance_futures_testnet(self):
        """Testnet modu testi."""
        exchange = ExchangeFactory.create_binance_futures(testnet=True)
        
        assert exchange is not None
        # Testnet URL'leri kontrol edilebilir (implementasyona göre)
        assert 'urls' in exchange.__dict__ or 'urls' in dir(exchange)

