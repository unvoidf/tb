"""
ExchangeFactory: Central factory for Binance exchange instances.
Standardizes all exchange instances and guarantees 'defaultType': 'future'.
"""
import ccxt
from typing import Optional
from utils.logger import LoggerManager


class ExchangeFactory:
    """Factory class for Binance exchange instances."""
    
    _logger = None
    
    @classmethod
    def _get_logger(cls):
        """Returns logger instance (lazy initialization)."""
        if cls._logger is None:
            cls._logger = LoggerManager().get_logger('ExchangeFactory')
        return cls._logger
    
    @staticmethod
    def create_binance_futures(
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: bool = False
    ) -> ccxt.binance:
        """
        Creates a Binance Futures exchange instance.
        
        Args:
            api_key: Binance API key (optional, not required for just fetching data)
            api_secret: Binance API secret (optional)
            testnet: Whether to use Testnet (default: False)
            
        Returns:
            Configured Binance exchange instance
        """
        logger = ExchangeFactory._get_logger()
        
        config = {
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        }
        
        # Add API credentials if provided
        if api_key and api_secret:
            config['apiKey'] = api_key
            config['secret'] = api_secret
        
        # Testnet configuration
        if testnet:
            config['urls'] = {
                'api': {
                    'public': 'https://testnet.binancefuture.com/fapi/v1',
                    'private': 'https://testnet.binancefuture.com/fapi/v1',
                }
            }
            logger.info("Binance Futures exchange created (TESTNET)")
        else:
            logger.debug("Binance Futures exchange created (MAINNET)")
        
        exchange = ccxt.binance(config)
        
        return exchange
