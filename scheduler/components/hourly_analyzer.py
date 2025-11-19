"""
HourlyAnalyzer: Saatlik analiz yapan bileşen.
Top coinleri analiz eder ve sinyal üretir.
"""
from typing import List, Dict
from utils.logger import LoggerManager
from data.coin_filter import CoinFilter
from data.coin_filter import CoinFilter
from analysis.signal_generator import SignalGenerator
from data.market_data_manager import MarketDataManager


class HourlyAnalyzer:
    """Saatlik analiz yapan bileşen."""
    
    def __init__(self, coin_filter: CoinFilter, market_data: MarketDataManager, signal_generator: SignalGenerator):
        """
        HourlyAnalyzer'ı başlatır.
        
        Args:
            coin_filter: Coin filter
            market_data: Market data manager
            signal_generator: Signal generator
        """
        self.coin_filter = coin_filter
        self.market_data = market_data
        self.signal_gen = signal_generator
        self.logger = LoggerManager().get_logger('HourlyAnalyzer')
    
    def analyze_top_coins(self, top_count: int = 20) -> List[Dict]:
        """
        Top coinleri analiz eder.
        
        Args:
            top_count: Analiz edilecek coin sayısı
            
        Returns:
            Analiz sonuçları listesi
        """
        try:
            self.logger.info(f"Top {top_count} coin analiz ediliyor")
            
            # Top hacimli coinleri al
            symbols = self.coin_filter.get_top_volume_coins(top_count)
            
            if not symbols:
                self.logger.warning("Coin listesi alınamadı")
                return []
            
            # Her coin için sinyal üret
            all_signals = []
            
            for symbol in symbols:
                try:
                    # Multi-timeframe veri çek
                    timeframes = ['1h', '4h', '1d']
                    multi_tf_data = self.market_data.fetch_multi_timeframe(symbol, timeframes)
                    
                    if multi_tf_data:
                        signal_data = self.signal_gen.generate_signal(multi_tf_data, symbol=symbol)
                    else:
                        signal_data = None

                    if signal_data:
                        all_signals.append({
                            'symbol': symbol,
                            'signal': signal_data
                        })
                except Exception as e:
                    self.logger.error(f"{symbol} analiz hatası: {str(e)}")
            
            self.logger.info(f"Toplam {len(all_signals)} coin analiz edildi")
            return all_signals
            
        except Exception as e:
            self.logger.error(f"Saatlik analiz hatası: {str(e)}", exc_info=True)
            return []
