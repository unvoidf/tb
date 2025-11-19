"""
ExchangeFactory: Binance exchange instance'ları için merkezi factory.
Tüm exchange instance'larını standardize eder ve 'defaultType': 'future' garantiler.
"""
import ccxt
from typing import Optional
from utils.logger import LoggerManager


class ExchangeFactory:
    """Binance exchange instance'ları için factory sınıfı."""
    
    _logger = None
    
    @classmethod
    def _get_logger(cls):
        """Logger instance'ını döndürür (lazy initialization)."""
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
        Binance Futures exchange instance'ı oluşturur.
        
        Args:
            api_key: Binance API key (opsiyonel, sadece veri çekmek için gerekli değil)
            api_secret: Binance API secret (opsiyonel)
            testnet: Testnet kullanılacak mı (default: False)
            
        Returns:
            Yapılandırılmış Binance exchange instance'ı
        """
        logger = ExchangeFactory._get_logger()
        
        config = {
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        }
        
        # API credentials varsa ekle
        if api_key and api_secret:
            config['apiKey'] = api_key
            config['secret'] = api_secret
        
        # Testnet konfigürasyonu
        if testnet:
            config['urls'] = {
                'api': {
                    'public': 'https://testnet.binancefuture.com/fapi/v1',
                    'private': 'https://testnet.binancefuture.com/fapi/v1',
                }
            }
            logger.info("Binance Futures exchange oluşturuldu (TESTNET)")
        else:
            logger.debug("Binance Futures exchange oluşturuldu (MAINNET)")
        
        exchange = ccxt.binance(config)
        
        return exchange

